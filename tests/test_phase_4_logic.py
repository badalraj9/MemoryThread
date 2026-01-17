import uuid
import datetime
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import TMSService
from memory_thread.services.snapshot_service import SnapshotService, ReplayService
from memory_thread.services.transaction_manager import TransactionManager
from memory_thread.services.temporal_manager import TemporalManager

def test_phase_4_logic():
    print("## PHASE 4 LOGIC VERIFICATION\n")

    # Setup
    tms = TMSService()
    snap_svc = SnapshotService()
    replay_svc = ReplayService(snap_svc)

    # ---------------------------------------------------------
    # TEST 1: SNAPSHOT & REPLAY
    # ---------------------------------------------------------
    print("--- Test 1: Snapshot & Replay ---")
    eid = uuid.uuid4()

    # Events
    e1 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, eid, {"count": 10})
    e2 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, eid, {"count": 20})

    replay_svc.add_event_to_log(e1)
    replay_svc.add_event_to_log(e2)

    # Replay from scratch
    state = replay_svc.replay_events(eid)
    print(f"State after replay (expected 30): {state.current_value}")

    # Take Snapshot
    snap_id = snap_svc.take_snapshot(state)

    # Add Event 3
    e3 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, eid, {"count": 5})
    replay_svc.add_event_to_log(e3)

    # Replay using Snapshot
    # The service should load snapshot (30) and apply e3 (+5) -> 35
    state_snap = replay_svc.replay_events(eid)
    print(f"State after snapshot+replay (expected 35): {state_snap.current_value}")

    if state_snap.current_value.get("count") == 35:
        print("✅ PASS")
    else:
        print("❌ FAIL")

    # ---------------------------------------------------------
    # TEST 2: TRANSACTION MANAGER (Supply Chain)
    # ---------------------------------------------------------
    print("\n--- Test 2: Transaction Manager (Transfer) ---")
    factory = uuid.uuid4()
    warehouse = uuid.uuid4()

    # Initial States
    s_factory = EntityState(entity_id=factory, namespace="supply", current_value={"inventory": 1000}, truth_vector=TruthVector(confidence=1, authority=1, freshness=1, corroboration=1), last_event_id=uuid.uuid4())
    s_warehouse = EntityState(entity_id=warehouse, namespace="supply", current_value={"inventory": 0}, truth_vector=TruthVector(confidence=1, authority=1, freshness=1, corroboration=1), last_event_id=uuid.uuid4())

    context = {factory: s_factory, warehouse: s_warehouse}

    # Transfer Event
    tx_mgr = TransactionManager()
    event = tms.create_event(ActorEnum.SYSTEM, ActionEnum.UPDATE, factory, {"transfer_to": str(warehouse), "qty": 200})

    new_states = tx_mgr.process_transaction(event, context)

    f_val = new_states[factory].current_value.get("inventory")
    w_val = new_states[warehouse].current_value.get("inventory")

    print(f"Factory: {f_val} (Expected 800)")
    print(f"Warehouse: {w_val} (Expected 200)")

    if f_val == 800 and w_val == 200:
        print("✅ PASS")
    else:
        print("❌ FAIL")

    # ---------------------------------------------------------
    # TEST 3: TEMPORAL MANAGER (Out of Order)
    # ---------------------------------------------------------
    print("\n--- Test 3: Temporal Manager (Re-ordering) ---")
    temp_mgr = TemporalManager(replay_svc)
    eid_t = uuid.uuid4()

    # Event T=10
    e_late = tms.create_event(ActorEnum.USER, ActionEnum.UPDATE, eid_t, {"status": "awake"})
    e_late.timestamp = datetime.datetime.utcnow() + datetime.timedelta(seconds=10) # Future

    # Event T=5
    e_early = tms.create_event(ActorEnum.USER, ActionEnum.UPDATE, eid_t, {"status": "asleep"})
    e_early.timestamp = datetime.datetime.utcnow() # Now

    # Ingest Late First
    replay_svc.add_event_to_log(e_late)
    s_t = replay_svc.replay_events(eid_t)
    print(f"State at T=10: {s_t.current_value['status']}") # Should be awake

    # Ingest Early (Out of order)
    # Logic: Should insert e_early, then re-apply e_late.
    # Result depends on logic. "awake" overrides "asleep" if later.
    s_t_new = temp_mgr.handle_event(e_early, s_t)

    # If correctly reordered, e_early applies, then e_late applies.
    # Final state should still be "awake" (because T=10 > T=5).
    # If NOT reordered (FIFO), e_early would overwrite e_late -> "asleep".

    print(f"State after OOO insert: {s_t_new.current_value['status']}")

    if s_t_new.current_value['status'] == "awake":
        print("✅ PASS (Correctly ordered by time)")
    else:
        print("❌ FAIL (FIFO override)")

if __name__ == "__main__":
    test_phase_4_logic()
