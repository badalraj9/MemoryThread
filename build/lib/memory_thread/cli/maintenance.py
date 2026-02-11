import typer
from memory_thread.services.maintenance_orchestrator import MaintenanceOrchestrator
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command()
def run_all():
    """
    Run all maintenance jobs immediately.
    """
    orchestrator = MaintenanceOrchestrator()
    typer.echo("Running all maintenance jobs...")
    orchestrator.run_all()
    typer.echo("Done.")

@app.command()
def schedule():
    """
    Start the maintenance scheduler daemon (Not implemented in prototype).
    """
    typer.echo("Scheduler daemon not yet implemented.")
