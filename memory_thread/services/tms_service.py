import uuid
import datetime
import json
import math
from typing import Dict, Any, List, Optional
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class TruthVectorService:
    """
    Service for Truth Vector operations including scoring and freshness decay.
    Truth Vectors are 4D representations: (confidence, authority, freshness, corroboration)
    """

    # Decay rates by memory type (lambda values for exponential decay)
    DECAY_RATES = {
        "fact": 0.001,  # Very slow - facts persist
        "preference": 0.01,  # Medium - preferences evolve
        "event": 0.1,  # Fast - events become stale
        "prediction": 0.5,  # Very fast - predictions expire
        "identity": 0.0,  # Never decay - core identity
    }

    @staticmethod
    def calculate_score(vector: TruthVector) -> float:
        """
        Calculates composite truth score from vector components.

        Formula: score = W1*clamp(confidence) + W2*clamp(authority)
                 + W3*clamp(freshness) + W4*log(1+clamp(corroboration))

        Weights are normalized to sum to 1.0 in settings, so the weighted
        average naturally stays in [0, 1].  The final min(1.0) is defense
        in depth against future weight misconfiguration.

        Args:
            vector: TruthVector with confidence, authority, freshness, corroboration

        Returns:
            Weighted composite score in [0.0, 1.0]
        """
        W1 = settings.TMS_WEIGHT_CONFIDENCE
        W2 = settings.TMS_WEIGHT_AUTHORITY
        W3 = settings.TMS_WEIGHT_FRESHNESS
        W4 = settings.TMS_WEIGHT_CORROBORATION

        total_weight = W1 + W2 + W3 + W4

        c = max(0.0, min(1.0, float(vector.confidence)))
        a = max(0.0, min(1.0, float(vector.authority)))
        f = max(0.0, min(1.0, float(vector.freshness)))
        corr = max(0.0, float(vector.corroboration))

        corr_score = math.log(1 + corr)
        corr_score = min(corr_score, 1.0)

        score = ((W1 * c) + (W2 * a) + (W3 * f) + (W4 * corr_score)) / total_weight
        return min(score, 1.0)

    @staticmethod
    def decay_freshness(
        vector: TruthVector, event_time: datetime.datetime, memory_type: str = "event"
    ) -> float:
        """
        Calculates decayed freshness based on elapsed time.

        Formula: freshness(t) = freshness_0 * e^(-lambda * days_elapsed)

        Args:
            vector: Current TruthVector
            event_time: When the event occurred
            memory_type: Type of memory (fact, preference, event, prediction, identity)

        Returns:
            Decayed freshness value (minimum 0.01 to prevent complete loss)
        """
        now = datetime.datetime.utcnow()

        # Handle timezone-naive datetimes
        if event_time.tzinfo is not None:
            event_time = event_time.replace(tzinfo=None)

        days_elapsed = (now - event_time).total_seconds() / 86400.0

        # Get decay rate for memory type
        rate = TruthVectorService.DECAY_RATES.get(memory_type, 0.02)

        # Identity never decays
        if rate == 0:
            return 1.0

        # Exponential decay with floor
        decayed = vector.freshness * math.exp(-rate * days_elapsed)
        return max(0.01, decayed)

    @staticmethod
    def merge_vectors(v1: TruthVector, v2: TruthVector) -> TruthVector:
        """
        Merges two truth vectors using weighted averaging.
        Higher authority source wins - weights derived from authority.

        All components are clamped to valid ranges after merge:
          confidence  [0.0, 1.0]
          authority   [0.0, 1.0]
          freshness   [0.0, 1.0]
          corroboration >= 0

        Args:
            v1: First TruthVector
            v2: Second TruthVector

        Returns:
            Merged TruthVector
        """
        total_authority = v1.authority + v2.authority
        if total_authority == 0:
            w1, w2 = 0.5, 0.5
        else:
            w1 = v1.authority / total_authority
            w2 = v2.authority / total_authority

        merged_corroboration = max(0.0, v1.corroboration + v2.corroboration + 1)
        return TruthVector(
            confidence=max(0.0, min(1.0, w1 * v1.confidence + w2 * v2.confidence)),
            authority=max(0.0, min(1.0, max(v1.authority, v2.authority))),
            freshness=max(0.0, min(1.0, max(v1.freshness, v2.freshness))),
            corroboration=merged_corroboration,
        )


class StateDerivationService:
    """
    Service for deriving entity state from events.
    Implements: S(t+1) = apply(S(t), Event)
    """

    @staticmethod
    def apply_event(current_state: EntityState, event: Event) -> EntityState:
        """
        Derives S(t+1) from S(t) + Event.
        Strategy: Merges delta into current_value based on action type.

        Args:
            current_state: Current entity state
            event: Event to apply

        Returns:
            New EntityState after applying event

        Raises:
            ValueError: If event object_id doesn't match entity_id
        """
        if event.object_id != current_state.entity_id:
            raise ValueError(
                f"Event object_id {event.object_id} doesn't match entity_id {current_state.entity_id}"
            )

        # Create new value dictionary (immutable copy)
        new_value = current_state.current_value.copy()

        # Apply Delta based on action type
        for k, v in event.delta.items():
            if (
                isinstance(v, (int, float))
                and k in new_value
                and isinstance(new_value[k], (int, float))
            ):
                # Numeric operations based on action
                if event.action in [ActionEnum.ADD, ActionEnum.PLANT]:
                    new_value[k] += v
                elif event.action == ActionEnum.REMOVE:
                    new_value[k] -= v
                elif event.action == ActionEnum.UPDATE:
                    new_value[k] = v
                else:
                    # Default: replace
                    new_value[k] = v
            else:
                # Non-numeric or new key: direct replacement
                new_value[k] = v

        return EntityState(
            entity_id=current_state.entity_id,
            namespace=current_state.namespace,
            current_value=new_value,
            truth_vector=TruthVectorService.merge_vectors(
                current_state.truth_vector, event.truth_vector
            ),
            version=current_state.version + 1,
            last_event_id=event.id,
            updated_at=datetime.datetime.utcnow(),
        )


class TMSService:
    """
    Truth Management System Service.
    Core service for creating events and managing entity state.
    """

    def __init__(self):
        # Lazy import to avoid circular dependencies
        self._pg = None

    @property
    def pg(self):
        """Lazy-load PostgresClient to avoid initialization issues."""
        if self._pg is None:
            from memory_thread.db.postgres_client import PostgresClient

            self._pg = PostgresClient()
        return self._pg

    def create_event(
        self,
        actor: ActorEnum,
        action: ActionEnum,
        object_id: uuid.UUID,
        delta: Dict[str, Any],
        namespace: str = "user",
        confidence: float = 1.0,
        authority: float = 1.0,
    ) -> Event:
        """
        Creates a new event with default Truth Vector.

        Args:
            actor: Who performed the action (USER, AGENT, SYSTEM)
            action: Type of action (ADD, REMOVE, UPDATE, etc.)
            object_id: Target entity ID
            delta: Changes to apply
            namespace: Event namespace
            confidence: Initial confidence (0-1)
            authority: Initial authority (0-1)

        Returns:
            Created Event with assigned ID and timestamp
        """
        tv = TruthVector(
            confidence=confidence,
            authority=authority,
            freshness=1.0,  # New events are fresh
            corroboration=0.0,  # No corroboration yet
        )

        event = Event(
            actor=actor,
            action=action,
            object_id=object_id,
            delta=delta,
            namespace=namespace,
            truth_vector=tv,
        )

        log.info(f"Created Event: {event.id} ({action.value} on {object_id})")
        return event

    def get_current_state(self, entity_id: uuid.UUID) -> Optional[EntityState]:
        """
        Fetches current entity state from database.

        Args:
            entity_id: UUID of the entity

        Returns:
            EntityState if found, None otherwise
        """
        try:
            with self.pg.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT entity_id, namespace, current_value, truth_vector, 
                           version, last_event_id, updated_at
                    FROM entity_state 
                    WHERE entity_id = %s
                """,
                    (str(entity_id),),
                )

                row = cur.fetchone()

                if not row:
                    log.debug(f"No state found for entity {entity_id}")
                    return None

                # Parse truth_vector from JSON if needed
                tv_data = row["truth_vector"]
                if isinstance(tv_data, str):
                    tv_data = json.loads(tv_data)

                # Parse current_value from JSON if needed
                current_value = row["current_value"]
                if isinstance(current_value, str):
                    current_value = json.loads(current_value)

                return EntityState(
                    entity_id=uuid.UUID(str(row["entity_id"])),
                    namespace=row["namespace"],
                    current_value=current_value,
                    truth_vector=TruthVector(**tv_data),
                    version=row["version"],
                    last_event_id=uuid.UUID(str(row["last_event_id"])),
                    updated_at=row["updated_at"],
                )

        except Exception as e:
            log.error(f"Error fetching state for entity {entity_id}: {e}")
            return None

    def save_state(self, state: EntityState) -> bool:
        """
        Persists entity state to database (upsert).

        Args:
            state: EntityState to save

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.pg.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO entity_state 
                        (entity_id, namespace, current_value, truth_vector, 
                         version, last_event_id, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_id) DO UPDATE SET
                        current_value = EXCLUDED.current_value,
                        truth_vector = EXCLUDED.truth_vector,
                        version = EXCLUDED.version,
                        last_event_id = EXCLUDED.last_event_id,
                        updated_at = EXCLUDED.updated_at
                """,
                    (
                        str(state.entity_id),
                        state.namespace,
                        json.dumps(state.current_value),
                        state.truth_vector.model_dump_json(),
                        state.version,
                        str(state.last_event_id),
                        state.updated_at,
                    ),
                )

            log.debug(f"Saved state for entity {state.entity_id} (v{state.version})")
            return True

        except Exception as e:
            log.error(f"Error saving state for entity {state.entity_id}: {e}")
            return False

    def persist_event(self, event: Event) -> bool:
        """
        Persists event to the event log.

        Args:
            event: Event to persist

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.pg.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO events 
                        (id, namespace, timestamp, actor, action, object_id, 
                         delta, antecedents, truth_vector)
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

            log.debug(f"Persisted event {event.id}")
            return True

        except Exception as e:
            log.error(f"Error persisting event {event.id}: {e}")
            return False

    def persist_and_save(self, event: Event, state: EntityState) -> bool:
        """
        Persists event and saves state in a single transaction.
        If state save fails, event insert rolls back too.

        Args:
            event: Event to persist
            state: EntityState to save

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.pg.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO events 
                        (id, namespace, timestamp, actor, action, object_id, 
                         delta, antecedents, truth_vector)
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
                        (entity_id, namespace, current_value, truth_vector, 
                         version, last_event_id, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entity_id) DO UPDATE SET
                        current_value = EXCLUDED.current_value,
                        truth_vector = EXCLUDED.truth_vector,
                        version = EXCLUDED.version,
                        last_event_id = EXCLUDED.last_event_id,
                        updated_at = EXCLUDED.updated_at
                """,
                    (
                        str(state.entity_id),
                        state.namespace,
                        json.dumps(state.current_value),
                        state.truth_vector.model_dump_json(),
                        state.version,
                        str(state.last_event_id),
                        state.updated_at,
                    ),
                )

            log.debug(f"Persisted event {event.id} and saved state for {state.entity_id}")
            return True

        except Exception as e:
            log.error(f"Error in transactional persist: {e}")
            return False
