import uuid
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
import json

from memory_thread.models.events import Event, EntityState
from memory_thread.services.snapshot_service import SnapshotService
from memory_thread.services.replay_service import ReplayService
from memory_thread.services.tms_service import TMSService
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TimewarpEngine:
    def __init__(self):
        self.snapshot_service = SnapshotService()
        self.replay_service = ReplayService()
        self.pg = PostgresClient()
        self.tms = TMSService()

    def insert_late_event(self, event: Event) -> Dict[str, Any]:
        """
        Inserts a late event and repairs the timeline.
        1. Insert event into DB (Chronological/Append log).
        2. Identify affected entities.
        3. Recompute state from T(event).
        """
        # 1. Insert (Log it)
        # Note: 'timestamp' is the semantic time. 'created_at' (if exists) is system time.
        # We trust the event's timestamp.
        with self.pg.get_cursor() as cur:
             cur.execute("""
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(event.id), event.namespace, event.timestamp,
                event.actor.value, event.action.value, str(event.object_id),
                json.dumps(event.delta),
                [str(uid) for uid in event.antecedents],
                event.truth_vector.model_dump_json()
            ))

        # 2. Recompute State
        # Uses inline state reconstruction for timewarp operations.
        # This replays all events from scratch (or nearest snapshot) to rebuild state.

        new_state = self._recompute_state(event.object_id)

        # 3. Update State in DB
        # Check for conflicts? (If new state differs significantly from old, maybe flag).
        # For now, just overwrite "Current State".

        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entity_state
                SET current_value = %s, truth_vector = %s, last_event_id = %s, updated_at = %s, version = version + 1
                WHERE entity_id = %s
            """, (
                json.dumps(new_state.current_value),
                new_state.truth_vector.model_dump_json(),
                str(new_state.last_event_id),
                datetime.utcnow(),
                str(new_state.entity_id)
            ))

        log.info(f"Timewarp: Repaired state for {event.object_id} after late event {event.id}")
        return {"status": "repaired", "new_state": new_state.current_value}

    def _recompute_state(self, entity_id: uuid.UUID) -> EntityState:
        """
        Rebuilds state from scratch (or nearest snapshot) using ALL events in DB (including the new late one).
        """
        # 1. Get all events sorted by time
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                FROM events
                WHERE object_id = %s
                ORDER BY timestamp ASC
            """, (str(entity_id),))
            rows = cur.fetchall()

        # 2. Replay
        # Start from empty state
        # (Optimization: Use snapshot service later, for now full replay for correctness)

        if not rows:
            return None

        from memory_thread.models.events import TruthVector
        from memory_thread.services.tms_service import StateDerivationService

        # Initial State
        first = rows[0]
        tv_data = first['truth_vector']
        if isinstance(tv_data, str): tv_data = json.loads(tv_data)

        current_state = EntityState(
            entity_id=entity_id,
            namespace=first['namespace'],
            current_value={},
            truth_vector=TruthVector(**tv_data), # Placeholder
            version=0,
            last_event_id=first['id']
        )

        for r in rows:
            tv_data = r['truth_vector']
            if isinstance(tv_data, str): tv_data = json.loads(tv_data)

            evt = Event(
                id=r['id'],
                namespace=r['namespace'],
                timestamp=r['timestamp'],
                actor=r['actor'],
                action=r['action'],
                object_id=r['object_id'],
                delta=r['delta'],
                antecedents=r['antecedents'] or [],
                truth_vector=TruthVector(**tv_data)
            )

            current_state = StateDerivationService.apply_event(current_state, evt)

        return current_state
