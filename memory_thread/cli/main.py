import typer
import os
import json
import threading
from pathlib import Path
from typing import Optional
from memory_thread.cli import identity, assimilate, prune, decay, maintenance
from memory_thread.cli import debug
from memory_thread.utils.logger import get_logger

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
        from memory_thread.api.server import app as fastapi_app

        log.info(f"Starting MT server on {host}:{port}")
        print(f"[*] Starting Memory Thread API server at http://{host}:{port}")
        print(f"    Docs: http://{host}:{port}/docs")
        print(f"    Press Ctrl+C to stop")

        uvicorn.run(
            "memory_thread.api.server:app",
            host=host,
            port=port,
            workers=workers,
            reload=reload,
        )
    except ImportError:
        print("[!] uvicorn not installed. Run: pip install uvicorn")
        raise typer.Exit(1)
    except Exception as e:
        print(f"[!] Failed to start server: {e}")
        raise typer.Exit(1)


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
    from memory_thread.db.postgres_client import PostgresClient

    project_path = Path(path).resolve()
    project_name = project_path.name
    namespace = project_name.lower().replace(" ", "_").replace("-", "_")

    pg = PostgresClient()

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

    # Register in projects table
    try:
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
        print(f"✓ Initialized MT project: {project_name}")
        print(f"  Namespace: {namespace}")
        print(f"  Path: {project_path}")
        if shared:
            print(f"  Shared memories enabled (.mt/ folder will be committed to git)")
    except Exception as e:
        log.error(f"Failed to register project: {e}")
        print(f"✗ Failed to initialize: {e}")


@app.command("list")
def list_projects():
    """List all registered MT projects."""
    from memory_thread.db.postgres_client import PostgresClient

    pg = PostgresClient()

    try:
        with pg.get_cursor() as cur:
            cur.execute("""
                SELECT name, namespace, path, initialized_at, last_accessed
                FROM projects
                ORDER BY last_accessed DESC
            """)
            rows = cur.fetchall()

        if not rows:
            print("No projects registered. Run 'mt init' to register a project.")
            return

        print(f"{'Name':<20} {'Namespace':<20} {'Path':<40} {'Last Accessed'}")
        print("-" * 100)
        for row in rows:
            print(
                f"{row['name']:<20} {row['namespace']:<20} {row['path']:<40} {row['last_accessed']}"
            )

    except Exception as e:
        log.error(f"Failed to list projects: {e}")
        print(f"[!] Error: {e}")


@app.command("reflect")
def reflect():
    """Run MT daily reflection and print insight summary."""
    from memory_thread.services.contemplator import Contemplator

    contemplator = Contemplator(auto_start=False)
    result = contemplator.daily_reflection()
    summary = contemplator.generate_insight_summary()
    print(summary)


@app.command("recall")
def recall_command(
    query: str = typer.Argument(..., help="Search query"),
    project: Optional[str] = typer.Option(None, "--from", help="Search specific project namespace"),
    top_k: int = typer.Option(5, "--top-k", help="Number of results to return"),
):
    """
    Search memories from current project or specified project.
    """
    from memory_thread.sdk import MemoryClient

    namespace = project if project else _resolve_namespace()

    try:
        mt = MemoryClient(namespace=namespace)
        result = mt.recall(query, top_k=top_k)

        print(f"\n=== Results from: {namespace} ===")
        for i, mem in enumerate(result.memories, 1):
            print(f"\n{i}. {mem.content[:100]}...")
            print(
                f"   Score: {mem.truth_score:.3f} | Confidence: {mem.confidence:.2f} | Authority: {mem.authority:.2f}"
            )

        if not result.memories:
            print("No memories found.")

    except Exception as e:
        log.error(f"Recall failed: {e}")
        print(f"✗ Error: {e}")


@app.command("migrate")
def migrate_command(
    path: str = typer.Option(".", "--path", help="Path to migrate (default: current directory)"),
    status: bool = typer.Option(False, "--status", help="Show pending migrations only"),
):
    """
    Run database migrations.

    Scans the migrations/ folder and applies any pending migrations.
    """
    from memory_thread.db.migrations.runner import MigrationRunner

    project_path = Path(path).resolve()
    runner = MigrationRunner(project_path)

    if status:
        pending = runner.get_pending()
        if pending:
            print(f"Pending migrations ({len(pending)}):")
            for m in pending:
                print(f"  - {m}")
        else:
            print("No pending migrations.")
        return

    applied = runner.run_migrations()
    print(f"Applied {len(applied)} migration(s).")


def run():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    app()
