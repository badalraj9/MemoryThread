from typing import List, Dict
from memory_thread.models.events import Event, EntityState
from memory_thread.services.snapshot_service import ReplayService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class TemporalManager:
    """
    Handles out-of-order events.
    """
    def __init__(self, replay_service: ReplayService):
        self.replay_service = replay_service

    def handle_event(self, event: Event, current_state: EntityState) -> EntityState:
        """
        Checks if event is out-of-order relative to state.
        If so, triggers replay.
        """
        # Simple check: timestamp vs state.updated_at
        # Note: updated_at tracks wall-clock time of processing usually.
        # We need the timestamp of the LAST EVENT applied.

        # If the incoming event is OLDER than the state's last update time, we have a violation.
        # But `current_state` stores `updated_at`.
        # Ideally state stores `last_event_timestamp`.

        # Assumption: Events arrive mostly in order.
        # If event.timestamp < current_state.last_event_timestamp (implied), Replay.

        # For simulation, we assume current_state reflects t=NOW.
        # If event.timestamp is significantly in the past, recompute.

        # In `snapshot_service.py`, `replay_events` sorts by timestamp.
        # So we just add to log and call replay.

        self.replay_service.add_event_to_log(event)

        # Force replay to ensure correct state at t=NOW
        # This effectively "inserts" the late event into the stream and re-calculates everything after it.
        new_state = self.replay_service.replay_events(event.object_id)

        return new_state
