import uuid
import datetime
from typing import Dict, Any, List
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TruthVectorService:
    @staticmethod
    def calculate_score(vector: TruthVector) -> float:
        # Placeholder weights - moving to settings later
        W1, W2, W3, W4 = 1.0, 1.0, 1.0, 1.0

        # Simple heuristic for now
        # log(1 + corroboration)
        import math
        corr_score = math.log(1 + vector.corroboration)

        score = (W1 * vector.confidence) + \
                (W2 * vector.authority) + \
                (W3 * vector.freshness) + \
                (W4 * corr_score)
        return score

    @staticmethod
    def decay_freshness(vector: TruthVector, event_time: datetime.datetime) -> float:
        # Placeholder decay logic
        # For now, just return current freshness
        return vector.freshness

class StateDerivationService:
    @staticmethod
    def apply_event(current_state: EntityState, event: Event) -> EntityState:
        """
        Derives S(t+1) from S(t) + Event.
        Strategy: Merges delta into current_value.
        """
        if event.object_id != current_state.entity_id:
            raise ValueError("Event object_id mismatch")

        # Create new value dictionary (copy)
        new_value = current_state.current_value.copy()

        # Apply Delta (Simple dictionary merge/update for now)
        # For numeric fields like 'tree_count', we might want mathematical ops
        # But since delta is generic JSON, we assume 'replace' or specific logic per field type
        # Simplistic implementation: key-value update
        for k, v in event.delta.items():
            if isinstance(v, (int, float)) and k in new_value and isinstance(new_value[k], (int, float)):
                # If both are numbers, add them?
                # The "5000 Trees" problem implies ADD/REMOVE actions carry a numeric delta.
                # Event: Action=ADD, delta={tree_count: 10} -> S_new = S_old + 10
                if event.action in [ActionEnum.ADD, ActionEnum.PLANT]:
                     new_value[k] += v
                elif event.action == ActionEnum.REMOVE:
                     new_value[k] -= v
                elif event.action == ActionEnum.UPDATE:
                     new_value[k] = v
            else:
                # Default replacement
                new_value[k] = v

        # Resolve Truth Vector
        # If new event has higher Authority/Score, it dominates.
        # But here we are deriving state *from* an accepted event, so the state inherits the event's truth
        # combined with previous state?
        # For Phase 3.4, we assume the latest event in the DAG becomes the current truth state
        # but we must track version.

        return EntityState(
            entity_id=current_state.entity_id,
            namespace=current_state.namespace,
            current_value=new_value,
            truth_vector=event.truth_vector, # State adopts latest event truth
            version=current_state.version + 1,
            last_event_id=event.id,
            updated_at=datetime.datetime.utcnow()
        )

class TMSService:
    def __init__(self):
        pass

    def create_event(self,
                     actor: ActorEnum,
                     action: ActionEnum,
                     object_id: uuid.UUID,
                     delta: Dict[str, Any],
                     namespace: str = "user") -> Event:

        # Default Truth Vector (can be enhanced later)
        tv = TruthVector(
            confidence=1.0,
            authority=1.0,
            freshness=1.0,
            corroboration=0.0
        )

        event = Event(
            actor=actor,
            action=action,
            object_id=object_id,
            delta=delta,
            namespace=namespace,
            truth_vector=tv
        )

        # In a real app, we would write to DB here
        log.info(f"Created Event: {event.id} ({action} {object_id})")
        return event

    def get_current_state(self, entity_id: uuid.UUID) -> EntityState:
        # Mock fetch from DB
        # In reality: SELECT * FROM entity_state WHERE entity_id = ...
        pass
