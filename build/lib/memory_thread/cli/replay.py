import typer
import json
import logging
from uuid import UUID
from typing import Optional
from pathlib import Path

from memory_thread.services.replay_service import ReplayService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(help="Deterministic Replay Debugger (Phase 6.1)")

@app.command("capture")
def capture_trace(
    entity_id: str = typer.Option(..., help="UUID of the entity to capture"),
    output: str = typer.Option("trace.json", help="Output file path")
):
    """
    Captures a Golden Trace (events + final state) for an entity.
    """
    service = ReplayService()
    try:
        log.info(f"Capturing trace for {entity_id}...")
        trace = service.capture_trace(UUID(entity_id))
        service.save_trace(trace, output)
        log.info(f"Trace saved to {output} ({len(trace['events'])} events)")
    except Exception as e:
        log.error(f"Capture failed: {e}")
        raise typer.Exit(code=1)

@app.command("verify")
def verify_trace(
    trace_file: str = typer.Option(..., "--trace", help="Path to golden trace JSON")
):
    """
    Replays a Golden Trace and verifies the final state matches.
    """
    service = ReplayService()
    try:
        log.info(f"Loading trace from {trace_file}...")
        trace = service.load_trace(trace_file)

        log.info(f"Replaying {len(trace['events'])} events...")
        success, diffs, final_state = service.replay_trace(trace)

        if success:
            log.info("✅ VERIFICATION PASSED: State matches exactly.")
        else:
            log.error("❌ VERIFICATION FAILED: Divergence detected.")
            for line in diffs:
                log.error(line)
            raise typer.Exit(code=1)

    except Exception as e:
        log.error(f"Verification process error: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
