import typer
import os
import json
import threading
from pathlib import Path
from typing import Optional
from memory_thread.cli import identity, assimilate, prune, decay, maintenance
from memory_thread.cli import debug
from memory_thread.utils.logger import get_logger
from memory_thread.db.migrations.runner import MigrationRunner

log = get_logger(__name__)

app = typer.Typer(name="nebula", help="Memory Thread Management CLI")

app.add_typer(identity.app, name="identity", help="Identity management and deduplication")
app.add_typer(assimilate.app, name="assimilate", help="Event consolidation engine")
app.add_typer(prune.app, name="prune", help="State pruning engine")
app.add_typer(decay.app, name="decay", help="Truth vector decay engine")
app.add_typer(maintenance.app, name="maintenance", help="Orchestration of maintenance jobs")

app.add_typer(debug.app, name="debug", help="Debug tools")
app.command("load-fixtures")(debug.load_fixtures)
app.command("ingest-provenance")(debug.ingest_provenance)


def _resolve_namespace() -> str:
    """Resolve namespace by checking .mt/ config, walking up directories, or falling back to global."""
    from memory_thread.config.settings import settings

    # First check .mt/ in current directory
    mt_config_path = Path(settings.MT_PROJECT_DIR) / "config.json"
    if mt_config_path.exists():
        try:
            with open(mt_config_path) as f:
                config = json.load(f)
                if config.get("namespace"):
                    return config["namespace"]
        except Exception:
            pass

    # Walk up directories like git
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        mt_dir = parent / ".mt"
        if mt_dir.exists():
            config_path = mt_dir / "config.json"
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        if config.get("namespace"):
                            return config["namespace"]
                except Exception:
                    pass

        # Stop at filesystem root
        if parent == parent.parent:
            break

    # Fall back to global
    return _get_global_namespace()


def _get_global_namespace() -> str:
    """Get or create global namespace from ~/.mt/config.json."""
    from memory_thread.config.settings import settings

    global_dir = Path(settings.MT_GLOBAL_DIR)
    global_dir.mkdir(parents=True, exist_ok=True)
    config_path = global_dir / "config.json"

    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("namespace", "global")
        except Exception:
            pass

    # Create global config
    namespace = os.environ.get("MT_USER", "global")
    config = {"namespace": namespace, "type": "global"}
    with open(config_path, "w") as f:
        json.dump(config, f)

    return namespace


def _ensure_mt_dir(path: str = ".") -> Path:
    """Ensure .mt directory exists in the given path."""
    mt_dir = Path(path) / ".mt"
    mt_dir.mkdir(parents=True, exist_ok=True)
    return mt_dir


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
    workers: int = typer.Option(1, "--workers", help="Number of worker processes"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """
    Start the Memory Thread REST API server.

    Runs the FastAPI server at http://localhost:8000
    """
    try:
        import uvicorn
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        import time

        console = Console()

        # Resolve namespace
        namespace = _resolve_namespace()

        # Show startup banner
        banner = Panel(
            Text("Memory Thread  v1.0.0", justify="center", style="bold cyan"),
            border_style="cyan",
            padding=(0, 0),
        )
        console.print(banner)
        console.print()

        # Service status table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="green")
        table.add_column(style="cyan")
        table.add_column(style="dim")

        # Check PostgreSQL
        postgres_status = "connecting..."
        try:
            from memory_thread.db.postgres_client import PostgresClient

            pg = PostgresClient()
            with pg.get_cursor() as cur:
                cur.execute("SELECT 1")
            postgres_status = "connected"
        except Exception as e:
            postgres_status = f"unavailable ({type(e).__name__})"

        embeddings_status = "loading..."
        try:
            embeddings_status = "loaded"
        except Exception:
            embeddings_status = "unavailable"

        table.add_row("✓ PostgreSQL", "PostgreSQL", postgres_status)

        console.print(table)
        console.print()

        # Connection info
        console.print(
            f"  [cyan]Connection URL:[/cyan]  [bold]mt://{host}:{port}/{namespace}[/bold]"
        )
        console.print(f"  [cyan]API Docs:[/cyan]        [link]http://{host}:{port}/docs[/link]")
        console.print()
        console.print("[dim]Press Ctrl+C to stop[/dim]")
        console.print("─" * 50)

        uvicorn.run(
            "memory_thread.api.server:app",
            host=host,
            port=port,
            workers=workers,
            reload=reload,
            log_level="warning",
        )
    except ImportError:
        console = Console()
        console.print("[bold red]![/bold red] uvicorn not installed. Run: pip install uvicorn")
        raise typer.Exit(1)
    except Exception as e:
        console = Console()
        console.print(f"[bold red]![/bold red] Failed to start server: {e}")
        raise typer.Exit(1)


@app.command("init")
def init_command(
    shared: bool = typer.Option(
        False, "--shared", help="Create project-level shared memories that can be committed to git"
    ),
    path: str = typer.Option(".", "--path", help="Path to initialize (default: current directory)"),
):
    """
    Initialize MT in the current or specified directory.

    Generates a namespace from the folder name and registers the project.
    """
    from rich.console import Console

    console = Console()

    project_path = Path(path).resolve()
    project_name = project_path.name
    namespace = project_name.lower().replace(" ", "_").replace("-", "_")

    # Ensure .mt directory
    mt_dir = _ensure_mt_dir(path)

    # Write project config
    config = {
        "namespace": namespace,
        "name": project_name,
        "path": str(project_path),
        "shared": shared,
        "type": "project",
    }
    with open(mt_dir / "config.json", "w") as f:
        json.dump(config, f)

    # Try to register in projects table
    try:
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (name, path, namespace, initialized_at, last_accessed)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON CONFLICT (namespace) DO UPDATE SET
                    last_accessed = NOW(),
                    path = EXCLUDED.path,
                    name = EXCLUDED.name
            """,
                (project_name, str(project_path), namespace),
            )

        log.info(f"Initialized MT project: {project_name} (namespace: {namespace})")
    except Exception as e:
        log.warning(f"Could not register in DB: {e}")

    console.print(f"[green]✓[/green] Initialized MT project: [bold]{project_name}[/bold]")
    console.print(f"  [cyan]Namespace:[/cyan] {namespace}")
    console.print(f"  [cyan]Path:[/cyan] {project_path}")
    if shared:
        console.print(
            f"  [cyan]Shared memories enabled[/cyan] (.mt/ folder will be committed to git)"
        )


@app.command("list")
def list_projects():
    """List all registered MT projects."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    try:
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute("""
                SELECT name, namespace, path, initialized_at, last_accessed
                FROM projects
                ORDER BY last_accessed DESC
            """)
            rows = cur.fetchall()

        if not rows:
            console.print("[dim]No projects registered. Run 'mt init' to register a project.[/dim]")
            return

        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("Namespace", style="green")
        table.add_column("Path", style="dim")
        table.add_column("Last Accessed", style="yellow")

        for row in rows:
            table.add_row(row["name"], row["namespace"], row["path"], str(row["last_accessed"]))

        console.print(table)

    except Exception as e:
        log.error(f"Failed to list projects: {e}")
        console.print(f"[red]![/red] Error: {e}")


@app.command("reflect")
def reflect():
    """Run MT daily reflection and print insight summary."""
    from rich.console import Console

    console = Console()

    from memory_thread.services.contemplator import Contemplator

    contemplator = Contemplator(auto_start=False)
    result = contemplator.daily_reflection()
    summary = contemplator.generate_insight_summary()
    console.print(summary)


@app.command("recall")
def recall_command(
    query: str = typer.Argument(..., help="Search query"),
    project: Optional[str] = typer.Option(None, "--from", help="Search specific project namespace"),
    top_k: int = typer.Option(5, "--top-k", help="Number of results to return"),
):
    """
    Search memories from current project or specified project.
    """
    from rich.console import Console

    console = Console()

    namespace = project if project else _resolve_namespace()

    try:
        from memory_thread.sdk import MemoryClient

        mt = MemoryClient(namespace=namespace)
        result = mt.recall(query, top_k=top_k)

        console.print(f"\n[bold]Results from:[/bold] {namespace}")
        if result.memories:
            for i, mem in enumerate(result.memories, 1):
                console.print(f"\n[cyan]{i}.[/cyan] {mem.content[:100]}...")
                console.print(
                    f"   [yellow]Score:[/yellow] {mem.truth_score:.3f} | [yellow]Confidence:[/yellow] {mem.confidence:.2f} | [yellow]Authority:[/yellow] {mem.authority:.2f}"
                )
        else:
            console.print("[dim]No memories found.[/dim]")

    except Exception as e:
        log.error(f"Recall failed: {e}")
        console.print(f"[red]✗[/red] Error: {e}")


@app.command("ingest")
def ingest_command(
    path: str = typer.Argument(..., help="File or directory path to ingest"),
):
    """
    Ingest a file or directory into Memory Thread.

    Parses files using intelligence services (code, document, log, data)
    and stores structured facts in the Galaxy Schema.
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    from memory_thread.services.file_ingest_service import ingest_path

    try:
        result = ingest_path(path)

        console.print(f"\n[bold green]✓ Ingestion complete[/bold green]\n")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan")
        table.add_column(style="green")

        if "folder_path" in result:
            table.add_row("Files processed", str(result.get("files_processed", 0)))
            table.add_row("Chunks created", str(result.get("chunks_created", 0)))
            table.add_row("Code facts", str(result.get("code_facts", 0)))
        else:
            table.add_row("File", result.get("original_name", "unknown"))
            table.add_row("Chunks created", str(result.get("chunks_created", 0)))
            table.add_row("Doc facts", str(result.get("doc_facts", 0)))
            table.add_row("Log facts", str(result.get("log_facts", 0)))
            table.add_row("Data facts", str(result.get("data_facts", 0)))

        console.print(table)

        if result.get("errors"):
            console.print(f"\n[yellow]Errors:[/yellow]")
            for err in result["errors"]:
                console.print(
                    f"  [red]✗[/red] {err.get('file', 'unknown')}: {err.get('error', 'unknown error')}"
                )

    except Exception as e:
        log.error(f"Ingest failed: {e}")
        console.print(f"[bold red]✗[/bold red] Error: {e}")


@app.command("migrate")
def migrate_command(
    path: str = typer.Option(".", "--path", help="Path to migrate (default: current directory)"),
    status: bool = typer.Option(False, "--status", help="Show pending migrations only"),
):
    """
    Run database migrations.

    Scans the migrations/ folder and applies any pending migrations.
    """
    from rich.console import Console

    console = Console()

    project_path = Path(path).resolve()
    runner = MigrationRunner(project_path)

    if status:
        pending = runner.get_pending()
        if pending:
            console.print(f"[yellow]Pending migrations ({len(pending)}):[/yellow]")
            for m in pending:
                console.print(f"  - {m}")
        else:
            console.print("[green]No pending migrations.[/green]")
        return

    applied = runner.run_migrations()
    console.print(f"[green]Applied {len(applied)} migration(s).[/green]")


def run():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    app()
