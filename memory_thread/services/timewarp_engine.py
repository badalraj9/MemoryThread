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
from memory_thread.config.settings import settings

log = get_logger(__name__)

STATE_DELTA_THRESHOLD = 0.5


class TimewarpEngine:
    def __init__(self, namespace: Optional[str] = None):
        self.snapshot_service = SnapshotService()
        self.replay_service = ReplayService()
        self.pg = PostgresClient()
        self.tms = TMSService()
        self.namespace = namespace

    def insert_late_event(self, event: Event) -> Dict[str, Any]:
        """
        Inserts a late event and repairs the timeline.
        1. Insert event into DB (Chronological/Append log).
        2. Identify affected entities.
        3. Recompute state from T(event).
        """
        old_state = self.tms.get_current_state(event.object_id)

        new_state = self._recompute_state(event.object_id, event.timestamp)

        if new_state is None:
            log.error(f"Timewarp: Could not recompute state for {event.object_id}")
            return {"status": "error", "message": "Failed to recompute state"}

        if old_state:
            self._compare_states(old_state, new_state)

        with self.pg.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    str(event.id),
                    event.namespace,
                    event.timestamp,
                    event.actor.value,
                    event.action.value,
                    str(event.object_id),
                    json.dumps(event.delta),
                    [str(uid) for uid in event.antecedents],
                    event.truth_vector.model_dump_json(),
                ),
            )

            cur.execute(
                """
                INSERT INTO entity_state 
                    (entity_id, namespace, current_value, truth_vector, version, last_event_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    current_value = EXCLUDED.current_value,
                    truth_vector = EXCLUDED.truth_vector,
                    version = EXCLUDED.version,
                    last_event_id = EXCLUDED.last_event_id,
                    updated_at = EXCLUDED.updated_at
            """,
                (
                    str(new_state.entity_id),
                    new_state.namespace,
                    json.dumps(new_state.current_value),
                    new_state.truth_vector.model_dump_json(),
                    new_state.version,
                    str(new_state.last_event_id),
                    datetime.utcnow(),
                ),
            )

        log.info(f"Timewarp: Repaired state for {event.object_id} after late event {event.id}")
        return {"status": "repaired", "new_state": new_state.current_value}

    def _compare_states(self, old_state: EntityState, new_state: EntityState):
        """Compare old and new state, flag significant deltas."""
        try:
            changed_keys = []
            for key in set(old_state.current_value.keys()) | set(new_state.current_value.keys()):
                old_val = old_state.current_value.get(key)
                new_val = new_state.current_value.get(key)

                if old_val != new_val:
                    if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                        delta = abs(new_val - old_val)
                        if old_val != 0:
                            relative_delta = delta / abs(old_val)
                            if relative_delta > STATE_DELTA_THRESHOLD:
                                changed_keys.append((key, old_val, new_val, relative_delta))
                        elif delta > STATE_DELTA_THRESHOLD:
                            changed_keys.append((key, old_val, new_val, delta))
                    else:
                        changed_keys.append((key, old_val, new_val, "replaced"))

            if changed_keys:
                log.warning(
                    f"Significant state delta detected for {old_state.entity_id}: {changed_keys}"
                )
        except Exception as e:
            log.debug(f"State comparison failed: {e}")

    def _recompute_state(
        self, entity_id: uuid.UUID, before_timestamp: Optional[datetime] = None
    ) -> Optional[EntityState]:
        """
        Rebuilds state from scratch (or nearest snapshot) using ALL events in DB.
        If before_timestamp provided, only use events up to that point.
        """
        try:
            snapshot = self.snapshot_service.get_nearest_snapshot(entity_id, before_timestamp)

            with self.pg.get_cursor() as cur:
                if self.namespace:
                    if snapshot:
                        cur.execute(
                            """
                            SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                            FROM events
                            WHERE namespace = %s AND object_id = %s AND timestamp > %s
                            ORDER BY timestamp ASC
                        """,
                            (self.namespace, str(entity_id), snapshot.timestamp.isoformat()),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                            FROM events
                            WHERE namespace = %s AND object_id = %s
                            ORDER BY timestamp ASC
                        """,
                            (self.namespace, str(entity_id)),
                        )
                else:
                    if snapshot:
                        cur.execute(
                            """
                            SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                            FROM events
                            WHERE object_id = %s AND timestamp > %s
                            ORDER BY timestamp ASC
                        """,
                            (str(entity_id), snapshot.timestamp.isoformat()),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                            FROM events
                            WHERE object_id = %s
                            ORDER BY timestamp ASC
                        """,
                            (str(entity_id),),
                        )

                rows = cur.fetchall()

            if not rows:
                return snapshot if snapshot else None

            from memory_thread.models.events import TruthVector
            from memory_thread.services.tms_service import StateDerivationService

            if snapshot:
                current_state = EntityState(
                    entity_id=entity_id,
                    namespace=snapshot.namespace,
                    current_value=snapshot.current_value,
                    truth_vector=snapshot.truth_vector,
                    version=snapshot.version,
                    last_event_id=snapshot.last_event_id,
                )
            else:
                first = rows[0]
                tv_data = first["truth_vector"]
                if isinstance(tv_data, str):
                    tv_data = json.loads(tv_data)

                current_state = EntityState(
                    entity_id=entity_id,
                    namespace=first["namespace"],
                    current_value={},
                    truth_vector=TruthVector(**tv_data),
                    version=0,
                    last_event_id=first["id"],
                )

            for r in rows:
                tv_data = r["truth_vector"]
                if isinstance(tv_data, str):
                    tv_data = json.loads(tv_data)

                evt = Event(
                    id=r["id"],
                    namespace=r["namespace"],
                    timestamp=r["timestamp"],
                    actor=r["actor"],
                    action=r["action"],
                    object_id=r["object_id"],
                    delta=r["delta"],
                    antecedents=r["antecedents"] or [],
                    truth_vector=TruthVector(**tv_data),
                )

                current_state = StateDerivationService.apply_event(current_state, evt)

            return current_state

        except Exception as e:
            log.error(f"State recomputation failed: {e}")
            return None
