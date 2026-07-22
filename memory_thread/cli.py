"""
MT CLI — Memory Thread setup, management, and operations.

Usage:
    mt init                    Initialize workspace
    mt serve                   Start API server
    mt migrate                 Run database migrations
    mt status                  System health + memory stats
    mt search <query>          Search memories
    mt recall <query>          Cross-namespace recall
    mt list                    List registered projects
    mt forget <entity-id>      Delete a memory
    mt audit                   View audit log
    mt snapshot                Create state checkpoint
    mt export                  Export memories to file
    mt consolidate             Merge repetitive events
    mt decay                   Apply freshness decay
    mt prune                   Remove low-value memories
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

if sys.platform == "win32":
    import subprocess

    subprocess.run(["chcp", "65001"], capture_output=True, shell=True)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console()

app = typer.Typer(
    name="mt",
    help="Memory Thread — Truth-preserving cognitive memory for AI.",
    add_completion=False,
)


def _client():
    from memory_thread.sdk import MemoryClient

    ns = os.environ.get("MT_NAMESPACE", "default")
    return MemoryClient(namespace=ns, use_db=True)


def _resolve_namespace() -> str:
    from pathlib import Path
    from memory_thread.config.settings import settings

    mt_config_path = Path(settings.MT_PROJECT_DIR) / "config.json"
    if mt_config_path.exists():
        try:
            with open(mt_config_path) as f:
                config = json.load(f)
                if config.get("namespace"):
                    return config["namespace"]
        except Exception:
            pass

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
        if parent == parent.parent:
            break

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
    ns = os.environ.get("MT_USER", "global")
    config = {"namespace": ns, "type": "global"}
    with open(config_path, "w") as f:
        json.dump(config, f)
    return ns


def _ensure_mt_dir(path: str = "."):
    from pathlib import Path

    mt_dir = Path(path) / ".mt"
    mt_dir.mkdir(parents=True, exist_ok=True)
    return mt_dir


@app.command()
def init(
    path: str = typer.Argument(".", help="Project root directory"),
    namespace: Optional[str] = typer.Option(None, "--ns", help="Namespace for this project"),
):
    """Initialize MT workspace in a project directory."""
    project_root = os.path.abspath(path)
    mt_dir = os.path.join(project_root, ".mt")
    if os.path.exists(mt_dir):
        console.print(f"[yellow]Already initialized: {mt_dir}[/yellow]")
        return
    os.makedirs(mt_dir, exist_ok=True)
    ns = namespace or os.path.basename(project_root).lower().replace(" ", "_")
    config = {
        "namespace": ns,
        "created_at": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "user": os.environ.get("MT_USER", "user"),
    }
    config_path = os.path.join(mt_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    gitignore_path = os.path.join(mt_dir, ".gitignore")
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("# MT workspace files\n*.jsonl\nwal/\nvault/\n")
    console.print(
        Panel(
            f"[green]Initialized[/green]\n"
            f"  Project:   [cyan]{os.path.basename(project_root)}[/cyan]\n"
            f"  Namespace: [cyan]{ns}[/cyan]\n"
            f"  Config:    [dim]{config_path}[/dim]",
            title="MT Init",
            border_style="green",
        )
    )


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to listen on"),
    workers: int = typer.Option(1, "--workers", help="Worker processes"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes"),
):
    """Start the Memory Thread API server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install memory-thread[api][/red]")
        raise typer.Exit(1)
    namespace = _resolve_namespace()
    console.print(f"[cyan]Memory Thread API server[/cyan]")
    console.print(f"  Host:     {host}")
    console.print(f"  Port:     {port}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Namespace: {namespace}")
    console.print(f"  API docs: http://{host}:{port}/docs")
    console.print()
    uvicorn.run(
        "memory_thread.api.server:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level="warning",
    )


@app.command()
def migrate(
    path: str = typer.Option(".", "--path", help="Project root path"),
    status: bool = typer.Option(False, "--status", help="Show pending migrations only"),
):
    """Run database migrations."""
    from pathlib import Path
    from memory_thread.db.migrations.runner import MigrationRunner
    from memory_thread.config.settings import settings

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


@app.command()
def status(as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON")):
    """System health and memory statistics."""
    client = _client()
    try:
        stats = client.get_stats()
        health = client.get_health()
        if as_json:
            console.print(json.dumps({**stats, **health}, indent=2))
            return
        table = Table(title="System Status", show_lines=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Memories", str(stats.get("total_memories", 0)))
        table.add_row("Events", str(stats.get("total_events", 0)))
        table.add_row("Avg Truth", f"{stats.get('avg_truth_score', 0):.0%}")
        table.add_row("DB", stats.get("db_type", "memory"))
        table.add_row("Namespace", os.environ.get("MT_NAMESPACE", "default"))
        low = health.get("low_truth_memories", 0)
        stale = health.get("stale_memories", 0)
        hscore = health.get("health_score", 1.0)
        if low > 0:
            table.add_row("Low Truth", f"[yellow]{low}[/yellow]")
        if stale > 0:
            table.add_row("Stale", f"[yellow]{stale}[/yellow]")
        color = "green" if hscore > 0.8 else "yellow" if hscore > 0.5 else "red"
        table.add_row("Health Score", f"[{color}]{hscore:.0%}[/{color}]")
        console.print(table)
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", min=1, max=100, help="Max results"),
    min_score: float = typer.Option(0.3, "--min-score", "-m", min=0, max=1, help="Min truth score"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search memories in the current namespace."""
    client = _client()
    result = client.recall(query, top_k=top_k, min_truth_score=min_score)
    if as_json:
        data = [
            {"content": m.content, "truth_score": m.truth_score, "entity_id": str(m.entity_id)}
            for m in result.memories
        ]
        console.print(
            json.dumps({"query": query, "total": result.total_found, "memories": data}, indent=2)
        )
        return
    if not result.memories:
        console.print(f"[yellow]No memories found for:[/yellow] {query}")
        return
    table = Table(title=f"Search: '{query}'", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", style="cyan", width=7)
    table.add_column("Content", style="white")
    for i, m in enumerate(result.memories, 1):
        sc = "green" if m.truth_score > 0.7 else "yellow" if m.truth_score > 0.4 else "red"
        table.add_row(
            str(i),
            f"[{sc}]{m.truth_score:.0%}[/{sc}]",
            m.content[:100] + ("..." if len(m.content) > 100 else ""),
        )
    console.print(table)
    console.print(f"[dim]{result.total_found} total matches[/dim]")


@app.command()
def recall(
    query: str = typer.Argument(..., help="Search query"),
    project: Optional[str] = typer.Option(None, "--from", help="Search specific project namespace"),
    top_k: int = typer.Option(5, "--top-k", help="Number of results"),
):
    """Search memories across namespaces."""
    client = _client()
    namespace = project if project else _resolve_namespace()
    result = client.recall(query, top_k=top_k, project=namespace)
    console.print(f"\n[bold]Results from:[/bold] {namespace}")
    if result.memories:
        for i, mem in enumerate(result.memories, 1):
            console.print(f"\n[cyan]{i}.[/cyan] {mem.content[:100]}...")
            console.print(
                f"   [yellow]Score:[/yellow] {mem.truth_score:.3f} | [yellow]Confidence:[/yellow] {mem.confidence:.2f}"
            )
    else:
        console.print("[dim]No memories found.[/dim]")


@app.command()
def list_projects():
    """List all registered MT projects."""
    try:
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute(
                "SELECT name, namespace, path, last_accessed FROM projects ORDER BY last_accessed DESC"
            )
            rows = cur.fetchall()
        if not rows:
            console.print("[dim]No projects registered. Run 'mt init' to register.[/dim]")
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
        console.print(f"[red]{e}[/red]")


@app.command()
def forget(
    entity_id: str = typer.Argument(..., help="Entity UUID to delete"),
):
    """Delete a memory by entity ID."""
    client = _client()
    try:
        eid = uuid.UUID(entity_id)
        if client.forget(eid):
            console.print(f"[green]Deleted: {entity_id[:8]}...[/green]")
        else:
            console.print(f"[yellow]Entity not found: {entity_id[:8]}...[/yellow]")
    except ValueError:
        console.print("[red]Invalid UUID[/red]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@app.command()
def audit(
    limit: int = typer.Option(20, "--limit", "-n", help="Max entries"),
    as_json: bool = typer.Option(False, "--json", "-j"),
):
    """View the security audit log."""
    try:
        from memory_thread.nervous.audit_ledger import ledger

        entries = ledger.query(limit=limit)
        if as_json:
            console.print(
                json.dumps(
                    [e.to_dict() if hasattr(e, "to_dict") else str(e) for e in entries], indent=2
                )
            )
            return
        console.print(f"[cyan]Audit Log[/cyan] (last {limit}):")
        for e in entries:
            console.print(f"  {e}")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@app.command()
def snapshot():
    """Create a state checkpoint."""
    client = _client()
    try:
        snap_hash = client.take_snapshot()
        if snap_hash:
            console.print(f"[green]Snapshot:[/green] {snap_hash}")
        else:
            console.print("[yellow]No data to snapshot[/yellow]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@app.command("export")
def export_memories(
    output: str = typer.Option("memories.json", "--output", "-o", help="Output file"),
):
    """Export all memories to a JSON file."""
    client = _client()
    result = client.recall("", top_k=100000, min_truth_score=0.0)
    data = [
        {
            "entity_id": str(m.entity_id),
            "content": m.content,
            "truth_score": m.truth_score,
            "confidence": m.confidence,
        }
        for m in result.memories
    ]
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    console.print(f"[green]Exported {len(data)} memories to {output}[/green]")


@app.command()
def consolidate(
    window_days: int = typer.Option(30, "--window", "-w", help="Window in days"),
):
    """Merge repetitive memories into summaries."""
    client = _client()
    try:
        count = client.consolidate(window_days=window_days)
        console.print(f"[green]Consolidated {count} events[/green]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@app.command()
def decay(
    rate: float = typer.Option(0.01, "--rate", "-r", help="Decay rate per call"),
):
    """Apply memory freshness decay."""
    client = _client()
    try:
        affected = client.apply_decay(rate)
        console.print(f"[green]Decay applied to {affected} memories[/green]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


@app.command()
def prune(
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Min truth score to keep"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove low-value memories below a truth score threshold."""
    if not force:
        console.print(f"[yellow]Will delete memories below {threshold:.0%} truth score[/yellow]")
        if not typer.confirm("Proceed?"):
            console.print("[dim]Cancelled[/dim]")
            return
    client = _client()
    try:
        count = client.prune(threshold)
        console.print(f"[green]Pruned {count} memories[/green]")
    except Exception as e:
        console.print(f"[red]{e}[/red]")


def run():
    app()


if __name__ == "__main__":
    run()
