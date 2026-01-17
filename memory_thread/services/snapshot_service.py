import uuid
import json
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime

from memory_thread.models.events import EntityState, TruthVector
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class SnapshotService:
    def __init__(self):
        self.pg = PostgresClient()

    def take_snapshot(self, state: EntityState) -> str:
        """
        Persists current state as a checkpoint in Postgres.
        Returns the snapshot hash.
        """
        state_json = state.model_dump_json() # Use Pydantic V2
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()

        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO snapshots (entity_id, last_event_id, state_data, truth_vector, timestamp, state_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                str(state.entity_id),
                str(state.last_event_id),
                json.dumps(state.current_value),
                state.truth_vector.model_dump_json(),
                state.updated_at,
                state_hash
            ))
            snap_id = cur.fetchone()[0]

        log.info(f"Snapshot taken for {state.entity_id} at {state.updated_at} (ID: {snap_id})")
        return state_hash

    def get_latest_snapshot(self, entity_id: uuid.UUID, before_time: Optional[datetime] = None) -> Optional[EntityState]:
        """
        Retrieves the most recent snapshot for an entity.
        If before_time is provided, gets the latest snapshot BEFORE that time (for Timewarp).
        """
        query = """
            SELECT entity_id, last_event_id, state_data, truth_vector, timestamp
            FROM snapshots
            WHERE entity_id = %s
        """
        params = [str(entity_id)]

        if before_time:
            query += " AND timestamp < %s"
            params.append(before_time)

        query += " ORDER BY timestamp DESC LIMIT 1"

        with self.pg.get_cursor() as cur:
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        if not row:
            return None

        # Reconstruct State
        # We need namespace. Snapshots table doesn't have it (schema oversight?).
        # We can fetch it from entities table or assume 'user' or pass it in.
        # Let's fetch from entities table for correctness.
        with self.pg.get_cursor() as cur:
            cur.execute("SELECT namespace FROM entities WHERE id = %s", (str(entity_id),))
            ns_row = cur.fetchone()
            # Handle RealDictCursor (dict) or standard cursor (tuple)
            if ns_row:
                if isinstance(ns_row, dict):
                    namespace = ns_row.get('namespace', "user")
                else:
                    namespace = ns_row[0]
            else:
                namespace = "user"

        tv_data = row['truth_vector']
        if isinstance(tv_data, str): tv_data = json.loads(tv_data)

        return EntityState(
            entity_id=row['entity_id'],
            namespace=namespace,
            current_value=row['state_data'],
            truth_vector=TruthVector(**tv_data),
            version=0, # Snapshot doesn't track version explicitly in Phase 4 schema, assume synced
            last_event_id=row['last_event_id'],
            updated_at=row['timestamp']
        )

    def compact_snapshots(self, entity_id: uuid.UUID, retention_days: int = 30):
        """
        Deletes old snapshots, keeping only 1 per day/week based on policy.
        For now: Delete everything older than retention_days.
        """
        with self.pg.get_cursor() as cur:
            cur.execute("""
                DELETE FROM snapshots
                WHERE entity_id = %s AND timestamp < NOW() - INTERVAL '%s days'
            """, (str(entity_id), retention_days))
        log.info(f"Compacted snapshots for {entity_id}")
