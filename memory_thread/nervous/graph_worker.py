"""AsyncGraphWorker — background projection from PostgreSQL into igraph.

Strategy 3: decouples the write path from graph construction.
  - Sync path appends to PG only (thin write)
  - This worker replays events into igraph asynchronously
  - Graph is eventually consistent, always safe to rebuild

Idempotent: _apply() checks _vertex_exists() before creating nodes,
so replaying already-applied events is a no-op.
"""

import uuid
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from memory_thread.models.events import Event, TruthVector
from memory_thread.services.graph_engine import graph_engine
from memory_thread.services.metrics import incr, observe

log = logging.getLogger(__name__)

CURSOR_TABLE = "ingestion_cursor"
BATCH_SIZE = 1000
POLL_SECONDS = 1.0


class AsyncGraphWorker:
    """Replay events from PostgreSQL into igraph on a background thread.

    Usage:
        worker = AsyncGraphWorker(pg_client)
        worker.start()          # daemon thread
        ...
        worker.stop()
    """

    def __init__(self, pg, batch_size: int = BATCH_SIZE, poll_interval: float = POLL_SECONDS):
        self.pg = pg
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # ── Replay readiness tracking (Fix #2) ──────────────────────────────
        # Lets the server accept traffic immediately and gate readiness on
        # initial replay completion instead of blocking startup on a full
        # (possibly very large) events-table replay.
        self._replaying = False
        self._initial_replay_done = False
        self._replay_processed = 0
        self._ensure_cursor_table()

    # ── Schema bootstrap ──────────────────────────────────────────────

    def _ensure_cursor_table(self):
        with self.pg.get_cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {CURSOR_TABLE} (
                    system_key VARCHAR(100) PRIMARY KEY,
                    last_event_id UUID,
                    last_processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute(f"""
                INSERT INTO {CURSOR_TABLE} (system_key, last_event_id)
                SELECT 'graph_worker', NULL
                WHERE NOT EXISTS (SELECT 1 FROM {CURSOR_TABLE} WHERE system_key = 'graph_worker')
            """)

    def _ensure_influence_table(self):
        with self.pg.get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS galaxy_influence_matrix (
                    requesting_namespace VARCHAR(255) NOT NULL,
                    observed_namespace VARCHAR(255) NOT NULL,
                    trust_weight FLOAT NOT NULL CHECK (trust_weight >= 0.0 AND trust_weight <= 1.0),
                    PRIMARY KEY (requesting_namespace, observed_namespace)
                )
            """)

    # ── Public API ────────────────────────────────────────────────────

    def flush(self):
        """Process all pending events synchronously. Used by tests and sync mode."""
        flush_start = time.perf_counter()
        processed = 0
        while self._process_batch():
            processed += self.batch_size
        self._replaying = False
        self._initial_replay_done = True
        flush_ms = (time.perf_counter() - flush_start) * 1000.0
        observe("graph_worker_flush_ms", flush_ms)
        log.info("AsyncGraphWorker flush complete (%dms, ~%d events)", int(flush_ms), processed)
        return processed

    def start(self):
        if self._running:
            return
        self._running = True
        # Mark replay in-progress so readiness probes report "not ready" until
        # the first catch-up burst completes (Fix #2).
        self._replaying = True
        self._initial_replay_done = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info(
            "AsyncGraphWorker started (batch=%d, poll=%.1fs)", self.batch_size, self.poll_interval
        )

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("AsyncGraphWorker stopped")

    # ── Readiness / observability (Fix #2) ────────────────────────────────

    def is_initial_replay_done(self) -> bool:
        """True once the first catch-up burst has completed.

        Used by the /health/ready probe to gate traffic on graph readiness
        without blocking server startup on a large replay.
        """
        return self._initial_replay_done

    def is_replaying(self) -> bool:
        """True while there is a backlog of events being replayed."""
        return self._replaying

    def replay_progress(self) -> dict:
        """Return a small status dict for health/metrics endpoints."""
        return {
            "replaying": self._replaying,
            "initial_replay_done": self._initial_replay_done,
            "events_processed": self._replay_processed,
        }

    # ── Main loop ─────────────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                processed = self._process_batch()
                if processed:
                    self._replaying = True
                else:
                    # Caught up (or nothing to do). Initial replay is complete.
                    if self._replaying:
                        self._replaying = False
                        self._initial_replay_done = True
                    time.sleep(self.poll_interval)
            except Exception:
                log.warning("AsyncGraphWorker batch error", exc_info=True)
                time.sleep(self.poll_interval * 5)

    def _process_batch(self) -> bool:
        with self.pg.get_cursor() as cur:
            # Fix #4: self-heal Defect A — if the graph is empty but the DB has
            # events, the cursor must be advanced past them (e.g. after a crash/
            # graph reset). Reset cursor to NULL so we replay from the beginning.
            if graph_engine.graph.vcount() == 0:
                cur.execute("SELECT EXISTS(SELECT 1 FROM events LIMIT 1)")
                has_events = cur.fetchone()[0]
                if has_events:
                    log.warning(
                        "Fix #4 self-heal: graph is empty but events exist — resetting "
                        "ingestion cursor to NULL for full replay."
                    )
                    incr("graph_worker_self_heal_total")
                    cur.execute(
                        f"UPDATE {CURSOR_TABLE} SET last_event_id = NULL, "
                        f"last_processed_at = NOW() WHERE system_key = 'graph_worker'"
                    )

            cur.execute(
                f"SELECT last_event_id FROM {CURSOR_TABLE} WHERE system_key = 'graph_worker'"
            )
            row = cur.fetchone()
            cursor_id = row["last_event_id"] if row else None

            if cursor_id:
                cur.execute(
                    """
                    SELECT * FROM events
                    WHERE timestamp > (SELECT timestamp FROM events WHERE id = %s)
                       OR (timestamp = (SELECT timestamp FROM events WHERE id = %s) AND id > %s)
                    ORDER BY timestamp, id
                    LIMIT %s
                    """,
                    (cursor_id, cursor_id, cursor_id, self.batch_size),
                )
            else:
                cur.execute(
                    "SELECT * FROM events ORDER BY timestamp, id LIMIT %s",
                    (self.batch_size,),
                )

            rows = cur.fetchall()
            if not rows:
                return False

            self._replay_processed += len(rows)

            for row in rows:
                tv_data = row["truth_vector"]
                if isinstance(tv_data, str):
                    tv_data = json.loads(tv_data)

                event = Event(
                    id=row["id"],
                    namespace=row["namespace"],
                    timestamp=row["timestamp"],
                    actor=row["actor"],
                    action=row["action"],
                    object_id=row["object_id"],
                    delta=row["delta"]
                    if isinstance(row["delta"], dict)
                    else json.loads(row["delta"]),
                    antecedents=[uuid.UUID(str(a)) for a in (row["antecedents"] or [])],
                    truth_vector=TruthVector(
                        confidence=tv_data.get("confidence", 0.5),
                        authority=tv_data.get("authority", 0.5),
                        freshness=tv_data.get("freshness", 1.0),
                        corroboration=tv_data.get("corroboration", 0.0),
                    ),
                )
                graph_engine._apply(event)

            last_row = rows[-1]
            cur.execute(
                f"UPDATE {CURSOR_TABLE} SET last_event_id = %s, last_processed_at = NOW() WHERE system_key = 'graph_worker'",
                (last_row["id"],),
            )

        return True
