import uuid
import datetime
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import StateDerivationService, TMSService

def test_5000_trees_problem():
    print("Running '5000 Trees' Verification...")

    tms = TMSService()
    entity_id = uuid.uuid4()

    # Initial State (Empty)
    state = EntityState(
        entity_id=entity_id,
        namespace="user",
        current_value={"tree_count": 0},
        truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
        last_event_id=uuid.uuid4()
    )
    print(f"T=0: {state.current_value}")

    # Event 1: PLANT 5000
    e1 = tms.create_event(ActorEnum.USER, ActionEnum.PLANT, entity_id, {"tree_count": 5000})
    state = StateDerivationService.apply_event(state, e1)
    print(f"T=1 (PLANT 5000): {state.current_value}")
    assert state.current_value["tree_count"] == 5000

    # Event 2: ADD 10
    e2 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, entity_id, {"tree_count": 10})
    state = StateDerivationService.apply_event(state, e2)
    print(f"T=2 (ADD 10): {state.current_value}")
    assert state.current_value["tree_count"] == 5010

    # Event 3: REMOVE 20
    e3 = tms.create_event(ActorEnum.USER, ActionEnum.REMOVE, entity_id, {"tree_count": 20})
    state = StateDerivationService.apply_event(state, e3)
    print(f"T=3 (REMOVE 20): {state.current_value}")
    assert state.current_value["tree_count"] == 4990

    print("✅ Verification Successful! Final Answer: 4990 Trees.")

if __name__ == "__main__":
    test_5000_trees_problem()
