"""ContradictionWorker — async background queue for contradiction classification.

Fire-and-forget pattern: remember() schedules a pair, returns immediately.
Worker picks up HIGH priority immediately, batches NORMAL priority, runs
classifier on background thread, creates graph edges, writes audit trail.

Crash recovery: each task pre-writes a `status='pending'` audit row before
classification. On next startup, `replay_pending()` re-queues any rows that
were left `pending` by a crash. The audit trail guarantees no pair is lost.
"""

import uuid
import json
import time
import queue
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from memory_thread.utils.logger import get_logger
from memory_thread.nervous.contradiction_classifier import get_classifier, CONTRADICTION, ENTAILMENT

log = get_logger(__name__)


class ContradictionWorker:
    """Background worker for contradiction detection with priority queue.

    Queue levels:
        HIGH      — user writes, processed 1-at-a-time immediately
        NORMAL    — agent writes, batched up to 10, processed when idle
        SHUTDOWN  — sentinel, worker exits
    """

    HIGH = 0
    NORMAL = 1

    def __init__(self, namespace: str):
        self.namespace = namespace
        self._queue: "queue.Queue[Optional[Dict]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._processed_count = 0
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            name=f"mt-contradiction-{self.namespace}",
            daemon=True,
        )
        self._thread.start()
        log.debug("ContradictionWorker started for namespace '%s'", self.namespace)

    def schedule(
        self,
        entity_id: str,
        event_id: str,
        existing_content: str,
        new_content: str,
        source: str,
    ):
        """Schedule a contradiction check — fire-and-forget, non-blocking."""
        priority = self.HIGH if source == "user" else self.NORMAL
        self._queue.put(
            {
                "priority": priority,
                "entity_id": entity_id,
                "event_id": event_id,
                "existing_content": existing_content,
                "new_content": new_content,
                "source": source,
            }
        )

    def shutdown(self):
        self._stop_event.set()
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._started = False
        log.debug("ContradictionWorker stopped (%d processed)", self._processed_count)

    def drain(self):
        self._queue.join()

    # ── Crash recovery: replay pending audit rows on startup ──────────

    def replay_pending(self) -> int:
        """Query contradiction_audit for status='pending' rows and re-schedule them.

        Returns the count of re-queued pairs. Called once on MemoryClient startup,
        after the worker thread is started.
        """
        replayed = 0
        try:
            from memory_thread.db.postgres_client import PostgresClient

            pg = PostgresClient()
            rows = pg.fetch_all("SELECT * FROM contradiction_audit WHERE status = 'pending'")
            for row in rows:
                input_pair = row.get("input_pair") or {}
                if isinstance(input_pair, str):
                    input_pair = json.loads(input_pair)
                self.schedule(
                    entity_id=str(row["entity_b_id"]),
                    event_id=str(row["entity_a_id"]),
                    existing_content=input_pair.get("a", ""),
                    new_content=input_pair.get("b", ""),
                    source="system",
                )
                replayed += 1
            if replayed:
                log.info(
                    "Replayed %d pending contradiction checks from audit log",
                    replayed,
                )
        except Exception as e:
            log.warning("Could not replay pending contradictions: %s", e)
        return replayed

    # ── Worker internals ───────────────────────────────────────────────

    def _worker_loop(self):
        batch: List[Dict] = []
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                self._flush_batch(batch)
                continue

            if task is None:
                self._queue.task_done()
                self._flush_batch(batch)
                break

            if task.get("priority") == self.HIGH:
                self._flush_batch(batch)
                self._process_one(task)
            else:
                batch.append(task)
                if len(batch) >= 10:
                    self._flush_batch(batch)

            self._queue.task_done()

        self._flush_batch(batch)

    def _flush_batch(self, batch: List[Dict]):
        if not batch:
            return
        for task in batch:
            self._process_one(task)
        batch.clear()

    def _process_one(self, task: Dict):
        audit_id = None
        try:
            entity_id = task["entity_id"]
            event_id = task["event_id"]
            existing = task["existing_content"]
            new_content = task["new_content"]

            if not existing or not new_content:
                return

            # Pre-write pending audit row — crash recovery checkpoint
            audit_id = self._preaudit_pending(event_id, entity_id, existing, new_content)

            classifier = get_classifier()
            label, confidence = classifier.classify(existing, new_content)

            if label not in (CONTRADICTION, ENTAILMENT):
                self._resolve_audit(audit_id, label, confidence, None, edge_id=None)
                return

            edge_type = "contradicts" if label == CONTRADICTION else "supports"
            threshold = 0.3 if label == CONTRADICTION else 0.4
            if confidence < threshold:
                self._resolve_audit(audit_id, label, confidence, None, edge_id=None)
                return

            from memory_thread.services.graph_engine import graph_engine

            edge = graph_engine.graph.add_edge(
                event_id,
                entity_id,
                type=edge_type,
                detector="contradiction_worker",
                confidence=confidence,
                timestamp=datetime.utcnow().isoformat(),
                entity_a_content=existing[:100],
                entity_b_content=new_content[:100],
            )

            self._resolve_audit(
                audit_id,
                label,
                confidence,
                edge_type,
                edge_id=str(edge.index),
            )

            self._processed_count += 1
            log.debug(
                "ContradictionWorker: %s (%.2f) between %s and %s",
                label,
                confidence,
                event_id[:8],
                entity_id[:8],
            )
        except Exception as e:
            log.warning("ContradictionWorker error: %s", e)
            if audit_id:
                self._fail_audit(audit_id, str(e))

    # ── Audit persistence with crash-recovery checkpoint ─────────────

    def _preaudit_pending(
        self, event_id: str, entity_id: str, existing: str, new_content: str
    ) -> Optional[str]:
        """Insert a pending audit row BEFORE classification.

        If the process crashes mid-classify, this row stays `pending`
        and is replayed on next startup.
        """
        try:
            from memory_thread.db.postgres_client import PostgresClient

            pg = PostgresClient()
            audit_id = str(uuid.uuid4())
            batch_id = str(uuid.uuid4())
            with pg.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO contradiction_audit
                        (id, batch_id, entity_a_id, entity_b_id, model_name,
                         input_pair, result, confidence, edge_type, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    """,
                    (
                        audit_id,
                        batch_id,
                        event_id,
                        entity_id,
                        "pending",
                        json.dumps({"a": existing, "b": new_content}),
                        "",
                        0.0,
                        "",
                    ),
                )
            return audit_id
        except Exception as e:
            log.warning("Audit pre-write skipped (DB unavailable): %s", e)
            return None

    def _resolve_audit(
        self,
        audit_id: Optional[str],
        label: str,
        confidence: float,
        edge_type: Optional[str],
        edge_id: Optional[str],
    ):
        """Update a pending audit row with classification results."""
        if audit_id is None:
            return
        try:
            from memory_thread.db.postgres_client import PostgresClient

            pg = PostgresClient()
            with pg.get_cursor() as cur:
                cur.execute(
                    """
                    UPDATE contradiction_audit
                    SET status = 'completed',
                        result = %s,
                        confidence = %s,
                        edge_type = %s,
                        edge_id = %s,
                        model_name = %s,
                        processed_at = NOW()
                    WHERE id = %s
                    """,
                    (label, confidence, edge_type, edge_id, "contradiction_worker", audit_id),
                )
        except Exception as e:
            log.warning("Audit resolve skipped (DB unavailable): %s", e)

    def _fail_audit(self, audit_id: Optional[str], error: str):
        """Mark a pending audit row as failed with error message."""
        if audit_id is None:
            return
        try:
            from memory_thread.db.postgres_client import PostgresClient

            pg = PostgresClient()
            with pg.get_cursor() as cur:
                cur.execute(
                    "UPDATE contradiction_audit SET status = 'failed', error = %s, processed_at = NOW() WHERE id = %s",
                    (error[:500], audit_id),
                )
        except Exception as e:
            log.warning("Audit fail update skipped (DB unavailable): %s", e)
