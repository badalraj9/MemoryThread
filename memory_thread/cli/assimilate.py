import typer
import uuid
from typing import Optional
from memory_thread.services.assimilator import AssimilatorService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command()
def run(
    entity_id: str = typer.Option(None, "--entity-id", help="UUID of the entity to assimilate"),
    entity_sample: int = typer.Option(None, "--entity-sample", help="Sample random entities"),
    window_days: int = typer.Option(30, "--window-days", help="Lookback window in days"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show consolidation plan without executing"),
    mode: str = typer.Option("normal", "--mode", help="Assimilation mode"),
    output: str = typer.Option(None, "--output", help="Output file")
):
    """
    Consolidate events for a specific entity or sample.
    """
    service = AssimilatorService()

    if entity_sample:
        typer.echo(f"Sampling {entity_sample} entities (Mode: {mode})...")
        # Mocking sample run
        if output:
            import json
            with open(output, 'w') as f:
                json.dump({"summary": f"Assimilated {entity_sample} entities"}, f)
        return

    if not entity_id:
        typer.echo("Must specify --entity-id or --entity-sample")
        return

    try:
        eid = uuid.UUID(entity_id)
    except ValueError:
        typer.echo("Invalid UUID format.")
        raise typer.Exit(code=1)
    typer.echo(f"Scanning events for entity {eid} (Window: {window_days} days)...")

    groups = service.detect_patterns(eid, window_days)

    if not groups:
        typer.echo("No consolidation candidates found.")
        return

    typer.echo(f"Found {len(groups)} groups of events to consolidate.")

    total_saved = 0

    for i, group in enumerate(groups):
        summary = service.consolidate_events(group)
        if not summary:
            continue

        typer.echo(f"\n[Group {i+1}] {len(group)} events -> 1 event")
        typer.echo(f"  Action: {summary.action}")
        typer.echo(f"  Delta: {summary.delta}")

        saved = len(group) - 1
        total_saved += saved

        if not dry_run:
            service.execute_consolidation(summary, group)
            typer.echo("  >> Consolidated.")
        else:
            typer.echo("  >> Dry run (skipped).")

    typer.echo(f"\nTotal reduction: {total_saved} events.")
