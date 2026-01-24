"""
Round-Trip Persistence Test - Real PostgreSQL
"""
import uuid
import json
from datetime import datetime

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import TMSService, StateDerivationService

def run_test():
    print("="*60)
    print("ROUND-TRIP PERSISTENCE TEST (Real PostgreSQL)")
    print("="*60)

    # Test connection
    pc = PostgresClient()
    health = pc.health_check()
    print(f"Step 1: Postgres Health: {health['status']}")

    # Create test data
    tms = TMSService()
    entity_id = uuid.uuid4()
    print(f"Step 2: Testing with entity ID: {entity_id}")

    # Create events
    events = [
        tms.create_event(ActorEnum.USER, ActionEnum.UPDATE, entity_id, {"name": "Badal"}),
        tms.create_event(ActorEnum.USER, ActionEnum.UPDATE, entity_id, {"occupation": "developer"}),
        tms.create_event(ActorEnum.USER, ActionEnum.UPDATE, entity_id, {"project": "Memory Thread"}),
    ]
    print(f"Step 3: Created {len(events)} events")

    # WRITE events to DB
    with pc.get_cursor() as cur:
        for e in events:
            cur.execute("""
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(e.id), e.namespace, e.timestamp,
                e.actor.value, e.action.value, str(e.object_id),
                json.dumps(e.delta), [], e.truth_vector.model_dump_json()
            ))
    print("Step 4: WROTE events to PostgreSQL")

    # Derive state
    state = EntityState(
        entity_id=entity_id,
        namespace="user",
        current_value={},
        truth_vector=TruthVector(confidence=1, authority=1, freshness=1, corroboration=0),
        last_event_id=uuid.uuid4()
    )
    for e in events:
        state = StateDerivationService.apply_event(state, e)
    print(f"Step 5: Derived state: {state.current_value}")

    # WRITE state to DB
    with pc.get_cursor() as cur:
        cur.execute("""
            INSERT INTO entity_state (entity_id, namespace, current_value, truth_vector, version, last_event_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            str(state.entity_id), state.namespace,
            json.dumps(state.current_value), state.truth_vector.model_dump_json(),
            state.version, str(state.last_event_id), datetime.utcnow()
        ))
    print("Step 6: WROTE state to PostgreSQL")

    # CLEAR Python memory
    stored_entity_id = str(entity_id)
    del events, state, tms
    print("Step 7: CLEARED Python memory")

    print()
    print("-"*60)
    print("READING BACK FROM DATABASE...")
    print("-"*60)

    # READ events back
    with pc.get_cursor() as cur:
        cur.execute("SELECT * FROM events WHERE object_id = %s ORDER BY timestamp", (stored_entity_id,))
        rows = cur.fetchall()
    print(f"Step 8: READ {len(rows)} events from PostgreSQL")
    for r in rows:
        print(f"        {r['action']}: {r['delta']}")

    # READ state back
    with pc.get_cursor() as cur:
        cur.execute("SELECT * FROM entity_state WHERE entity_id = %s", (stored_entity_id,))
        row = cur.fetchone()
        
    print("Step 9: READ state from PostgreSQL")
    read_state = json.loads(row["current_value"]) if isinstance(row["current_value"], str) else row["current_value"]
    print(f"        State: {read_state}")

    # VERIFY
    print()
    print("="*60)
    print("VERIFICATION")
    print("="*60)
    assert read_state.get("name") == "Badal", "Name mismatch!"
    assert read_state.get("occupation") == "developer", "Occupation mismatch!"
    assert read_state.get("project") == "Memory Thread", "Project mismatch!"
    print("  name:       Badal")
    print("  occupation: developer")
    print("  project:    Memory Thread")
    print()
    print("ALL DATA VERIFIED!")
    print("WRITE -> CLEAR MEMORY -> READ = SUCCESS")
    print("="*60)
    return True

if __name__ == "__main__":
    run_test()
