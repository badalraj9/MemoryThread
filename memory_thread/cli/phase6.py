import typer
import uuid
import json
from datetime import datetime

from memory_thread.services.snapshot_service import SnapshotService
from memory_thread.services.ancestry_cache import AncestryCache
from memory_thread.services.timewarp_engine import TimewarpEngine
from memory_thread.models.events import Event, ActorEnum, ActionEnum, TruthVector
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(help="Phase 6 Tools (Snapshot, Ancestry, Timewarp)")

# --- SNAPSHOT ---
snapshot_app = typer.Typer(help="Snapshot Management")
app.add_typer(snapshot_app, name="snapshot")

@snapshot_app.command("create")
def create_snapshot(entity_id: str):
    service = SnapshotService()
    # Need to fetch current state first to snapshot it.
    # We can use ReplayService.capture_trace logic or just query DB.
    # Helper:
    from memory_thread.services.replay_service import ReplayService
    replay = ReplayService()
    try:
        trace = replay.capture_trace(uuid.UUID(entity_id))
        from memory_thread.models.events import EntityState
        state = EntityState(**trace['final_state'])

        hash = service.take_snapshot(state)
        log.info(f"Snapshot created: {hash}")
    except Exception as e:
        log.error(f"Failed: {e}")

@snapshot_app.command("restore")
def restore_snapshot(entity_id: str):
    service = SnapshotService()
    state = service.get_latest_snapshot(uuid.UUID(entity_id))
    if state:
        log.info(f"Latest Snapshot: {state.updated_at} | Value: {state.current_value}")
    else:
        log.info("No snapshot found.")

# --- ANCESTRY ---
ancestry_app = typer.Typer(help="Ancestry Cache")
app.add_typer(ancestry_app, name="ancestry")

@ancestry_app.command("rebuild")
def rebuild_ancestry(entity_id: str):
    service = AncestryCache()
    service.rebuild_cache(uuid.UUID(entity_id))
    log.info("Ancestry cache rebuilt.")

@ancestry_app.command("show")
def show_ancestry(entity_id: str):
    service = AncestryCache()
    # Cache is in-memory, so this only shows if rebuilt in this process or persistent storage used.
    # Since we use in-memory dict, we must rebuild first to see anything in this CLI run.
    service.rebuild_cache(uuid.UUID(entity_id))
    chain = service.get_ancestry(uuid.UUID(entity_id))
    log.info(f"Ancestry Chain ({len(chain)} events): {chain[:5]}...")

# --- TIMEWARP ---
timewarp_app = typer.Typer(help="Timewarp Correction")
app.add_typer(timewarp_app, name="timewarp")

@timewarp_app.command("insert")
def insert_late_event(
    entity_id: str,
    action: str = "ADD",
    delta_json: str = '{"value": 1}',
    minutes_ago: int = 10
):
    service = TimewarpEngine()

    # Construct Event
    evt = Event(
        id=uuid.uuid4(),
        namespace="user",
        timestamp=datetime.utcnow() - json.timedelta(minutes=minutes_ago) if False else datetime.utcnow(), # Fix import
        actor=ActorEnum.USER,
        action=ActionEnum[action],
        object_id=uuid.UUID(entity_id),
        delta=json.loads(delta_json),
        antecedents=[],
        truth_vector=TruthVector(confidence=1, authority=1, freshness=1, corroboration=0)
    )
    # Manual timestamp adjust
    from datetime import timedelta
    evt.timestamp = datetime.utcnow() - timedelta(minutes=minutes_ago)

    res = service.insert_late_event(evt)
    log.info(f"Result: {res}")

if __name__ == "__main__":
    app()
