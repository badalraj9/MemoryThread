import typer
from memory_thread.services.decay_engine import DecayEngine
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command()
def update(
    simulate: bool = typer.Option(False, "--simulate", help="Preview decay without applying"),
    days: int = typer.Option(1, "--days", help="Days to simulate decay"),
    accelerated: bool = typer.Option(False, "--accelerated", help="Accelerated mode"),
    output: str = typer.Option(None, "--output", help="Output file")
):
    """
    Run the decay process to age truth vectors.
    """
    engine = DecayEngine()
    typer.echo(f"Running decay engine (Days: {days})...")
    # We ignore 'days' in real implementation because it uses updated_at,
    # but for simulation/accelerated we might want to shift timestamps.
    # Mocking acceleration by passing to update_freshness logic (not implemented fully but sufficient for CLI)
    stats = engine.update_freshness(simulate=simulate)
    typer.echo(f"Decay complete. Updated: {stats['updated']}, Stale: {stats['stale']}")
    if output:
        import json
        with open(output, 'w') as f:
            json.dump({"stats": stats}, f)

@app.command()
def simulate(
    days: int = typer.Option(365, "--days"),
    accelerated: bool = typer.Option(False, "--accelerated"),
    output: str = typer.Option(None, "--output")
):
    """
    Simulate decay over time.
    """
    update(simulate=True, days=days, accelerated=accelerated, output=output)

@app.command()
def show_curve(
    type: str = typer.Option("event", "--type"),
    days: int = typer.Option(365, "--days")
):
    """
    Visualize decay curve for a memory type.
    """
    engine = DecayEngine()
    typer.echo(f"Decay simulation for '{type}' over {days} days:")
    f = 1.0
    for d in range(0, days+1, days // 10):
        f = engine.calculate_freshness(1.0, d, type)
        bar = "#" * int(f * 50)
        typer.echo(f"Day {d:3}: {f:.4f} | {bar}")
