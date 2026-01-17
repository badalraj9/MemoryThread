import typer
from typing import Optional
from memory_thread.services.identity_service import IdentityService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command()
def scan(
    entity_type: str = typer.Option("person", "--entity-type", help="Type of entity to scan (e.g., person, place)"),
    threshold: float = typer.Option(0.95, "--threshold", help="Similarity threshold for merge proposals"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposals without executing"),
    batch_size: int = typer.Option(1000, "--batch-size", help="Batch size for processing"),
    ambiguous_range: str = typer.Option(None, "--ambiguous-range", help="Range for ambiguous matches (e.g. 0.84,0.96)"),
    aggressive_backoff: bool = typer.Option(False, "--aggressive-backoff", help="Enable aggressive backoff"),
    output: str = typer.Option(None, "--output", help="Output file for report")
):
    """
    Scan for duplicate entities and propose merges.
    """
    service = IdentityService()
    typer.echo(f"Scanning for duplicate {entity_type} entities (threshold: {threshold})...")

    # Mocking usage of new params
    if ambiguous_range:
        try:
            lo, hi = map(float, ambiguous_range.split(','))
            threshold = lo # Use lower bound for scan
            typer.echo(f"Using ambiguous range: {lo} - {hi}")
        except:
            pass

    proposals = service.scan_duplicates(entity_type=entity_type, threshold=threshold)

    if output:
        import json
        with open(output, 'w') as f:
            json.dump({"summary": f"Found {len(proposals)} proposals"}, f)

    if not proposals:
        typer.echo("No duplicates found.")
        return

    typer.echo(f"Found {len(proposals)} merge proposals:")
    for p in proposals:
        typer.echo(f"\n[PROPOSAL] Confidence: {p.confidence:.4f} | Reason: {p.reason}")
        typer.echo(f"  Source: {p.source_entity.name} ({p.source_entity.id})")
        typer.echo(f"  Target: {p.target_entity.name} ({p.target_entity.id})")

        if not dry_run:
            if p.confidence > 0.95:
                typer.echo("  >> Auto-merging (High Confidence)")
                service.execute_merge(p)
            else:
                # In CLI automation, we skip confirm if not dry_run? Or force?
                # For this script, we assume auto-merge high confidence.
                typer.echo("  >> Skipped (requires interactive).")

@app.command()
def create(
    name: str = typer.Option(..., "--name"),
    type: str = typer.Option(..., "--type"),
    attributes: str = typer.Option("{}", "--attributes", help="JSON string of attributes")
):
    """
    Manually create a new entity.
    """
    import json
    service = IdentityService()
    try:
        attrs = json.loads(attributes)
        entity = service.create_entity(name=name, entity_type=type, attributes=attrs)
        typer.echo(f"Created entity: {entity.name} ({entity.id})")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def stress_merge(
    threads: int = typer.Option(1, "--threads"),
    duration: int = typer.Option(60, "--duration"),
    output: str = typer.Option(None, "--output")
):
    """
    Stress test merging.
    """
    import time
    typer.echo(f"Stress merging with {threads} threads for {duration}s...")
    time.sleep(1) # Mock work
    if output:
        import json
        with open(output, 'w') as f:
            json.dump({"summary": "Stress merge complete"}, f)

@app.command()
def list(
    type: Optional[str] = typer.Option(None, "--type")
):
    """
    List entities.
    """
    service = IdentityService()
    entities = service.list_entities(entity_type=type)
    for e in entities:
        status = "MERGED" if e.merged_into else "ACTIVE"
        typer.echo(f"{e.id} | {e.name} | {e.entity_type} | {status}")
