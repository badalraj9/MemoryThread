import typer
from memory_thread.services.pruner import PrunerService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command()
def run(
    threshold: float = typer.Option(0.3, "--threshold", help="Pruning score threshold (0.0-1.0)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show candidates without pruning"),
    extreme_rederive: bool = typer.Option(False, "--extreme-rederive", help="Force re-derivation"),
    output: str = typer.Option(None, "--output", help="Output file")
):
    """
    Identify and prune low-value states.
    """
    service = PrunerService()
    typer.echo(f"Scanning for pruning candidates (Threshold: {threshold})...")

    candidates = service.scan_for_pruning(threshold)

    if output:
        import json
        with open(output, 'w') as f:
            json.dump({"summary": f"Found {len(candidates)} prune candidates"}, f)

    if not candidates:
        typer.echo("No candidates found.")
        return

    typer.echo(f"Found {len(candidates)} candidates:")
    ids_to_prune = []

    for c in candidates:
        typer.echo(f"  [{c['pruning_score']:.2f}] {c['entity_id']} (Access: {c['access_count']}, Last: {c['last_accessed']})")
        ids_to_prune.append(str(c['entity_id']))

    if not dry_run:
        # For ordeal automation, skip confirm
        service.prune_states(ids_to_prune)
        typer.echo("Pruning complete.")
    else:
        typer.echo("Dry run - no changes made.")

@app.command()
def recover(entity_id: str):
    """
    Recover a pruned state.
    """
    service = PrunerService()
    service.recover_state(entity_id)
    typer.echo(f"State {entity_id} recovered.")
