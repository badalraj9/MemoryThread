"""PersistenceService — Postgres/SQLite persistence for MemoryClient."""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class PersistenceService:
    """Postgres (primary) / SQLite (fallback) persistence layer."""

    def __init__(self, namespace: str):
        self.namespace = namespace
        self._pg = None
        self._sqlite = None
        self.db_type = "memory"

    # ── Connection ─────────────────────────────────────────────────────

    def connect(self):
        try:
            from memory_thread.db.postgres_client import PostgresClient

            self._pg = PostgresClient()
            self.db_type = "postgres"
            log.info("PostgreSQL connected")
        except Exception as e:
            log.warning(f"PostgreSQL unavailable: {e}. Trying SQLite...")
            self._pg = None
            try:
                from memory_thread.db.sqlite_client import SQLiteClient

                self._sqlite = SQLiteClient()
                self.db_type = "sqlite"
                log.info("SQLite connected (fallback mode)")
            except Exception as e2:
                log.warning(f"SQLite also failed: {e2}. Using in-memory only.")
                self._sqlite = None
                self.db_type = "memory"

    @property
    def pg(self):
        return self._pg

    @property
    def sqlite(self):
        return self._sqlite

    # ── Write ──────────────────────────────────────────────────────────

    def save(self, entity_id, content, memory_type, state, event):
        if self._pg:
            try:
                self._save_postgres(entity_id, content, memory_type, state, event)
            except Exception as e:
                log.warning(f"Postgres persist failed: {e}")
        elif self._sqlite:
            try:
                self._save_sqlite(entity_id, content, memory_type, state, event)
            except Exception as e:
                log.warning(f"SQLite persist failed: {e}")

    def _save_postgres(self, entity_id, content, memory_type, state, event):
        with self._pg.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    str(event.id),
                    event.namespace,
                    event.timestamp,
                    event.actor.value,
                    event.action.value,
                    str(event.object_id),
                    json.dumps(event.delta),
                    [uid for uid in event.antecedents],
                    json.dumps(
                        {
                            "confidence": event.truth_vector.confidence,
                            "authority": event.truth_vector.authority,
                            "freshness": event.truth_vector.freshness,
                            "corroboration": event.truth_vector.corroboration,
                        }
                    ),
                ),
            )
            cur.execute(
                """
                INSERT INTO entity_state (entity_id, namespace, current_value, truth_vector, last_event_id, updated_at, version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    current_value = EXCLUDED.current_value,
                    truth_vector = EXCLUDED.truth_vector,
                    last_event_id = EXCLUDED.last_event_id,
                    updated_at = EXCLUDED.updated_at,
                    version = entity_state.version + 1
                """,
                (
                    str(entity_id),
                    self.namespace,
                    json.dumps(state.current_value),
                    json.dumps(
                        {
                            "confidence": state.truth_vector.confidence,
                            "authority": state.truth_vector.authority,
                            "freshness": state.truth_vector.freshness,
                            "corroboration": state.truth_vector.corroboration,
                        }
                    ),
                    str(event.id),
                    datetime.utcnow(),
                    state.version if hasattr(state, "version") else 1,
                ),
            )

    def _save_sqlite(self, entity_id, content, memory_type, state, event):
        self._sqlite.save_state(
            entity_id=str(entity_id),
            namespace=self.namespace,
            current_value=state.current_value,
            truth_vector={
                "confidence": state.truth_vector.confidence,
                "authority": state.truth_vector.authority,
                "freshness": state.truth_vector.freshness,
                "corroboration": state.truth_vector.corroboration,
            },
            last_event_id=str(event.id),
        )

    def delete(self, entity_id):
        if not self._pg:
            return
        try:
            with self._pg.get_cursor() as cur:
                cur.execute(
                    "DELETE FROM entity_state WHERE entity_id = %s",
                    (str(entity_id),),
                )
        except Exception:
            pass

    # ── Read ───────────────────────────────────────────────────────────

    def load_all(self, namespace: str) -> dict:
        from memory_thread.models.events import EntityState, TruthVector

        result = {}
        if not self._pg:
            return result

        try:
            with self._pg.get_cursor() as cur:
                cur.execute(
                    "SELECT entity_id, namespace, current_value, truth_vector "
                    "FROM entity_state WHERE namespace = %s",
                    (namespace,),
                )
                for row in cur.fetchall():
                    raw_id = row["entity_id"]
                    entity_id = raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(raw_id)
                    current_value = (
                        row["current_value"]
                        if isinstance(row["current_value"], dict)
                        else json.loads(row["current_value"])
                    )
                    tv_data = (
                        row["truth_vector"]
                        if isinstance(row["truth_vector"], dict)
                        else json.loads(row["truth_vector"])
                    )
                    state = EntityState(
                        entity_id=entity_id,
                        namespace=row["namespace"],
                        current_value=current_value,
                        truth_vector=TruthVector(**tv_data),
                        last_event_id=uuid.uuid4(),
                    )
                    result[entity_id] = state
        except Exception as e:
            log.warning(f"Failed to load from DB: {e}")

        return result
