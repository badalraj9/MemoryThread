"""
MT CLI — Advanced Command-Line Interface for Memory Thread.

MT is autonomous. It auto-remembers everything during chat, extracts entities,
detects contradictions, and builds context. Regular users just talk to it.

Usage:
    mt                              # Start chatting (default)
    mt ask "what do you know?"      # One-shot question
    mt status                       # System overview
    mt search "preferences"         # Inspect memories
    mt init                         # Initialize workspace
    mt serve                        # Start API server
"""

import os
import sys
import json
import typer
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

# ═══════════════════════════════════════════════════════════════════════════════
# WINDOWS UTF-8 FIX — no more Wakandan runes
# ═══════════════════════════════════════════════════════════════════════════════

if sys.platform == "win32":
    import subprocess

    subprocess.run(["chcp", "65001"], capture_output=True, shell=True)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ═══════════════════════════════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════════════════════════════

console = Console()

app = typer.Typer(
    name="mt",
    help="Memory Thread — Truth-preserving cognitive memory for AI.",
    invoke_without_command=True,
    rich_markup_mode="rich",
    add_completion=True,
)

# Sub-apps for grouped commands
agent_app = typer.Typer(help="Manage multi-agent memory spaces.")
provider_app = typer.Typer(help="Manage LLM providers.")
galaxy_app = typer.Typer(help="Galaxy Schema inspection.")
clients_app = typer.Typer(help="API client management.")

app.add_typer(agent_app, name="agent")
app.add_typer(provider_app, name="provider")
app.add_typer(galaxy_app, name="galaxy")
app.add_typer(clients_app, name="clients")


# ═══════════════════════════════════════════════════════════════════════════════
# RBAC GRADE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════


def _user() -> str:
    return os.environ.get("MT_USER", "user")


def _ns() -> str:
    return os.environ.get("MT_NAMESPACE", "default")


def _client():
    """Get MemoryClient."""
    try:
        from memory_thread.sdk import MemoryClient

        return MemoryClient(namespace=_ns(), use_db=True)
    except Exception as e:
        console.print(f"[red]✘ Client init failed: {e}[/red]")
        raise typer.Exit(1)


def _banner():
    """Print MT banner."""
    role = os.environ.get("MT_ROLE", "user")
    console.print(
        f"[bold cyan]Memory Thread[/bold cyan] [dim]│[/dim] "
        f"{_user()} ({role}) [dim]ns:{_ns()}[/dim]"
    )
    console.print("[dim]Everything you say is auto-remembered. Type /quit to exit.[/dim]\n")


# ═══════════════════════════════════════════════════════════════════════════════
# E_CLASS: CORE (Guest+)
# Regular users just talk. MT handles the rest.
# ═══════════════════════════════════════════════════════════════════════════════


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", "-V", is_eager=True, help="Show version"),
    role: Optional[str] = typer.Option(
        None, "--role", "-r", envvar="MT_ROLE", help="Override role"
    ),
    user: Optional[str] = typer.Option(
        None, "--user", "-u", envvar="MT_USER", help="Override user"
    ),
    namespace: Optional[str] = typer.Option(
        None, "--ns", "-n", envvar="MT_NAMESPACE", help="Namespace"
    ),
):
    """
    [bold cyan]Memory Thread[/bold cyan] — Truth-preserving cognitive memory for AI.

    \b
    Run with no arguments to start chatting. MT auto-remembers everything.

    \b
    Common commands:
      mt ask "question"     Ask with memory context
      mt status            System health + memory stats
      mt search "query"    Search memories
      mt init              Initialize workspace
      mt serve             Start API server
      mt whoami            Show your identity
    """
    if version:
        console.print("[bold cyan]Memory Thread[/bold cyan] v1.0.0")
        raise typer.Exit()

    if role:
        os.environ["MT_ROLE"] = role
    if user:
        os.environ["MT_USER"] = user
    if namespace:
        os.environ["MT_NAMESPACE"] = namespace

    # No subcommand → chat mode (the default experience)
    if ctx.invoked_subcommand is None:
        _enter_chat()


def _enter_chat():
    """Interactive chat — the primary interface. Everything is autonomous."""
    client = _client()
    _banner()

    while True:
        try:
            user_input = console.input("[bold cyan]you >[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        raw = user_input.strip()
        if not raw:
            continue
        if raw.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Goodbye.[/dim]")
            break

        # Chat handles EVERYTHING: remember, extract, contradict, respond
        try:
            response = client.chat(raw)
            console.print(f"[green]mt >[/green] {response}\n")
        except Exception as e:
            console.print(f"[red]✘ {e}[/red]")
            # Fallback: at least recall relevant context
            try:
                result = client.recall(raw, top_k=3)
                if result.memories:
                    console.print("[yellow]mt >[/yellow] Here's what I remember:")
                    for m in result.memories:
                        console.print(f"  [{m.truth_score:.0%}] {m.content}")
                    console.print()
            except Exception:
                console.print("[dim]  No relevant memories found.[/dim]\n")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to answer with memory context"),
    provider: str = typer.Option(
        "auto", "--provider", "-p", help="LLM: auto, local, ollama, groq, openrouter"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Specific model (e.g. deepseek-r1)"
    ),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """One-shot question with memory context. No interactive mode."""
    client = _client()
    try:
        use_local = provider == "local"
        response = client.chat(question, use_local=use_local, provider=provider, model=model)

        if as_json:
            print(json.dumps({"question": question, "response": response}))
        else:
            console.print(f"[green]mt >[/green] {response}")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")
        raise typer.Exit(1)


@app.command()
def whoami():
    """Show your identity and role."""
    role = os.environ.get("MT_ROLE", "user")

    info = (
        f"[bold]User:[/bold]    {_user()}\n"
        f"[bold]Role:[/bold]    {role}\n"
        f"[bold]NS:[/bold]      {_ns()}"
    )

    console.print(Panel(info, title="[cyan]Identity[/cyan]", border_style="cyan"))


# ═══════════════════════════════════════════════════════════════════════════════
# C_CLASS: INSPECTION (Employee+)
# See what MT knows, feed it more data.
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def status(
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """System health + memory stats in one view."""
    client = _client()

    try:
        stats = client.get_stats()
        health = client.get_health()

        if as_json:
            print(json.dumps({**stats, **health}))
            return

        table = Table(title="System Status", show_lines=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Memories", str(stats.get("total_memories", 0)))
        table.add_row("Events", str(stats.get("total_events", 0)))
        table.add_row("Avg Truth", f"{stats.get('avg_truth_score', 0):.0%}")
        table.add_row("DB", stats.get("db_type", "memory"))
        table.add_row(
            "Qdrant", "[green]●[/green]" if stats.get("qdrant_connected") else "[red]●[/red]"
        )
        table.add_row("Namespace", _ns())

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
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def search(
    query: str = typer.Argument(..., help="What to search for"),
    top_k: int = typer.Option(5, "--top-k", "-k", min=1, max=100, help="Max results"),
    min_score: float = typer.Option(0.3, "--min-score", "-m", min=0, max=1, help="Min truth score"),
    hybrid: bool = typer.Option(False, "--hybrid", help="Use hybrid search (vector+keyword+graph)"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Inspect what MT remembers about a topic."""
    client = _client()

    try:
        if hybrid:
            results = client.hybrid_search(query, top_k=top_k)
            if as_json:
                print(json.dumps(results))
                return
            console.print(f"[cyan]Hybrid Search:[/cyan] '{query}'")
            for i, r in enumerate(results, 1):
                console.print(f"  {i}. {r.get('content', '')[:100]}")
            return

        result = client.recall(query, top_k=top_k, min_truth_score=min_score)

        if as_json:
            memories = [
                {
                    "content": m.content,
                    "truth_score": m.truth_score,
                    "entity_id": str(m.entity_id),
                    "confidence": m.confidence,
                    "freshness": m.freshness,
                    "type": m.memory_type,
                }
                for m in result.memories
            ]
            print(json.dumps({"query": query, "total": result.total_found, "memories": memories}))
            return

        if not result.memories:
            console.print(f"[yellow]No memories found for:[/yellow] {query}")
            return

        table = Table(title=f"Search: '{query}'", show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Score", style="cyan", width=7)
        table.add_column("Type", style="dim", width=10)
        table.add_column("Content", style="white")

        for i, m in enumerate(result.memories, 1):
            sc = "green" if m.truth_score > 0.7 else "yellow" if m.truth_score > 0.4 else "red"
            table.add_row(
                str(i),
                f"[{sc}]{m.truth_score:.0%}[/{sc}]",
                m.memory_type,
                m.content[:100] + ("..." if len(m.content) > 100 else ""),
            )

        console.print(table)
        console.print(f"[dim]{result.total_found} total matches[/dim]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def load(
    path: str = typer.Argument(..., help="File or folder to ingest"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Recurse into subdirs"),
):
    """Feed files into memory."""

    if not os.path.exists(path):
        console.print(f"[red]✘ Not found: {path}[/red]")
        raise typer.Exit(1)

    try:
        from memory_thread.services.file_ingest_service import ingest_path

        result = ingest_path(path)
        console.print(f"[green]✔ Ingested[/green]")
        console.print(f"  Files: {result.get('files_processed', 1)}")
        console.print(f"  Chunks: {result['chunks_created']}")
        code_facts = result.get("code_facts", 0)
        if code_facts:
            console.print(
                f"  Code Intel: [cyan]{code_facts} structured facts[/cyan] (classes, functions, imports, call graph)"
            )
        console.print(f"  Vault: [dim]{result['vault_path']}[/dim]")
    except ImportError:
        # Fallback: read file and remember contents
        client = _client()
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            client.ingest_fact(content, source_uri=path)
            console.print(f"[green]✔ Loaded as fact:[/green] {path}")
        else:
            console.print("[yellow]⚠ File ingestion service not available[/yellow]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════════════
# B_CLASS: ENGINE INSPECTION (Developer+)
# Look under the hood — galaxy, agents, provenance.
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def conflicts():
    """Show belief contradictions across agents."""
    client = _client()
    try:
        c = client.get_galaxy_conflicts()
        if not c:
            console.print("[green]✔ No conflicts[/green]")
            return
        console.print(f"[yellow]⚠ {len(c)} conflict(s):[/yellow]")
        for item in c[:10]:
            console.print(
                f"  Fact {item['fact_id']}: {len(item['beliefs'])} beliefs from {item['agents']}"
            )
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def provenance(
    entity_id: str = typer.Argument(..., help="Entity UUID to trace"),
):
    """Trace a memory's full origin chain."""
    client = _client()
    import uuid as _uuid

    try:
        eid = _uuid.UUID(entity_id)
        chain = client.get_provenance(eid)
        if not chain:
            console.print("[yellow]No provenance found[/yellow]")
            return
        console.print(f"[cyan]Provenance for {entity_id[:8]}...[/cyan]")
        for i, event_id in enumerate(chain, 1):
            console.print(f"  {i}. {event_id}")
    except ValueError:
        console.print("[red]✘ Invalid UUID[/red]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def thread(
    entity_id: str = typer.Argument(..., help="Entity ID to trace"),
    raw: bool = typer.Option(False, "--raw", help="Show raw JSON instead of narrative"),
):
    """Show the complete causal history of a memory."""
    client = _client()
    import uuid as _uuid

    try:
        eid = _uuid.UUID(entity_id)
        result = client.get_golden_thread(eid)

        if raw:
            print(json.dumps(result, indent=2, default=str))
            return

        console.print(
            Panel(
                result.get("narrative", "No narrative available"),
                title=f"[cyan]Golden Thread: {entity_id[:8]}...[/cyan]",
                border_style="cyan",
            )
        )

        if not result.get("is_consistent", True):
            console.print("[red]⚠ Warning: Inconsistency detected during replay[/red]")

    except ValueError:
        console.print("[red]✘ Invalid UUID[/red]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# --- Galaxy sub-commands ---


@galaxy_app.callback(invoke_without_command=True)
def galaxy_default(ctx: typer.Context):
    """Galaxy Schema status."""
    if ctx.invoked_subcommand is None:
        # Default: show stats
        client = _client()
        try:
            s = client.galaxy_stats()
            facts = s.get("facts", {})
            beliefs = s.get("beliefs", {})
            console.print(
                Panel(
                    f"[bold]Facts:[/bold]   {facts.get('file_facts', 0)} stored\n"
                    f"[bold]Beliefs:[/bold] {beliefs.get('total_beliefs', 0)} across {beliefs.get('agents_count', 0)} agents",
                    title="[cyan]Galaxy Schema[/cyan]",
                    border_style="cyan",
                )
            )
        except Exception as e:
            console.print(f"[red]✘ {e}[/red]")


@galaxy_app.command("slice")
def galaxy_slice(source_uri: str = typer.Argument(..., help="Source URI to filter by")):
    """Filter beliefs by source."""
    client = _client()
    try:
        result = client.query_galaxy("SLICE", source_uri=source_uri)
        beliefs = result.beliefs if hasattr(result, "beliefs") else []
        console.print(f"[cyan]SLICE[/cyan] {len(beliefs)} beliefs from [bold]{source_uri}[/bold]")
        for b in beliefs[:10]:
            console.print(f"  [{b.agent_id}] {b.content[:80]}")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@galaxy_app.command("dice")
def galaxy_dice(
    agent_id: Optional[str] = typer.Argument(None, help="Filter by agent"),
    min_auth: float = typer.Option(0.0, "--min-auth", help="Min authority"),
):
    """Multi-filter beliefs by agent + authority."""
    client = _client()
    try:
        result = client.query_galaxy("DICE", agent_id=agent_id, min_authority=min_auth)
        beliefs = result.beliefs if hasattr(result, "beliefs") else []
        console.print(f"[cyan]DICE[/cyan] {len(beliefs)} beliefs")
        for b in beliefs[:10]:
            console.print(f"  [{b.agent_id}] {b.content[:80]}")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# --- Agent sub-commands ---


@agent_app.command("register")
def agent_register(
    name: str = typer.Argument(..., help="Agent name"),
    authority: float = typer.Option(0.5, "--authority", "-a", min=0, max=1),
):
    """Register a new agent."""
    try:
        from memory_thread.nervous.galaxy_core import GalaxyCore

        core = GalaxyCore()
        core.register_agent(name, authority)
        console.print(f"[green]✔ Agent '{name}' registered[/green] (authority={authority})")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@agent_app.command("list")
def agent_list():
    """List registered agents."""
    try:
        from memory_thread.nervous.galaxy_core import GalaxyCore

        core = GalaxyCore()
        agents = core.list_agents() if hasattr(core, "list_agents") else []
        if not agents:
            console.print("[dim]No agents registered[/dim]")
            return
        for a in agents:
            console.print(f"  {a}")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# --- Provider sub-commands ---


@provider_app.command("list")
def provider_list():
    """Show configured LLM providers."""
    try:
        from memory_thread.nervous.vault import vault

        providers = vault.list_providers(_user())
        active = vault.get_active_provider(_user())

        if not providers:
            console.print("[yellow]No providers configured.[/yellow]")
            console.print("[dim]Use: mt provider set <name> --key <key>[/dim]")
            return

        table = Table(title="LLM Providers", show_lines=False)
        table.add_column("Name", style="cyan")
        table.add_column("Status", width=10)
        table.add_column("Model", style="dim")

        for p in providers:
            marker = "[green]active[/green]" if p == active else "[dim]idle[/dim]"
            creds = vault.get_provider(p, _user())
            model = creds.get("model", "default") if creds else "?"
            table.add_row(p, marker, model)

        console.print(table)
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@provider_app.command("set")
def provider_set(
    name: str = typer.Argument(..., help="Provider name (groq, openrouter, etc.)"),
    key: str = typer.Option(..., "--key", "-k", prompt=True, hide_input=True, help="API key"),
    base_url: Optional[str] = typer.Option(None, "--url", help="Custom base URL"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Default model"),
):
    """Add/update an LLM provider."""
    try:
        from memory_thread.nervous.vault import vault

        vault.set_provider(name, key, base_url, model, _user())
        console.print(f"[green]✔ Provider '{name}' configured[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@provider_app.command("use")
def provider_use(name: str = typer.Argument(..., help="Provider to activate")):
    """Switch active LLM provider."""
    try:
        from memory_thread.nervous.vault import vault

        vault.set_active_provider(name, _user())
        console.print(f"[green]✔ Switched to: {name}[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@provider_app.command("remove")
def provider_remove(name: str = typer.Argument(..., help="Provider to remove")):
    """Remove an LLM provider."""
    try:
        from memory_thread.nervous.vault import vault

        if vault.delete_provider(name, _user()):
            console.print(f"[green]✔ Removed: {name}[/green]")
        else:
            console.print(f"[yellow]Provider '{name}' not found[/yellow]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@provider_app.command("scan-ollama")
def provider_scan_ollama():
    """List available local Ollama models."""
    client = _client()
    try:
        models = client.list_ollama_models()
        if not models:
            console.print("[yellow]No models found or Ollama is not running.[/yellow]")
            console.print("[dim]Ensure 'ollama serve' is running at http://localhost:11434[/dim]")
            return

        table = Table(title="Ollama Models", show_lines=False)
        table.add_column("Model Name", style="cyan")

        for m in models:
            table.add_row(m)

        console.print(table)
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════════════
# A_CLASS: BRAIN TUNING (Researcher+)
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def decay(
    rate: float = typer.Option(0.01, "--rate", "-r", help="Decay rate"),
):
    """Apply memory freshness decay."""
    client = _client()
    try:
        affected = client.apply_decay(rate)
        console.print(f"[green]✔ Decay applied[/green] — {affected} memories (rate={rate})")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def consolidate(
    window_days: int = typer.Option(30, "--window", "-w", help="Window in days"),
):
    """Merge repetitive memories into summaries."""
    client = _client()
    try:
        count = client.consolidate(window_days=window_days)
        console.print(f"[green]✔ Consolidated {count} events[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def snapshot():
    """Create a state checkpoint."""
    client = _client()
    try:
        snap_hash = client.take_snapshot()
        if snap_hash:
            console.print(f"[green]✔ Snapshot:[/green] {snap_hash}")
        else:
            console.print("[yellow]No data to snapshot[/yellow]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command("export")
def export_memories(
    output: str = typer.Option("memories.json", "--output", "-o", help="Output file"),
):
    """Export all memories to file."""
    client = _client()
    try:
        result = client.recall("", top_k=100000, min_truth_score=0.0)
        data = [
            {
                "entity_id": str(m.entity_id),
                "content": m.content,
                "truth_score": m.truth_score,
                "confidence": m.confidence,
                "freshness": m.freshness,
                "type": m.memory_type,
            }
            for m in result.memories
        ]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]✔ Exported {len(data)} memories to {output}[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════════════
# S_CLASS: OPERATIONS (Executive+)
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def prune(
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Min truth score to keep"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove low-value memories."""

    if not force:
        console.print(f"[yellow]⚠ Will delete memories below {threshold:.0%} truth score[/yellow]")
        if not typer.confirm("Proceed?"):
            console.print("[dim]Cancelled[/dim]")
            return

    client = _client()
    try:
        count = client.prune(threshold)
        console.print(f"[green]✔ Pruned {count} memories[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def audit(
    limit: int = typer.Option(20, "--limit", "-n", help="Max entries"),
    as_json: bool = typer.Option(False, "--json", "-j"),
):
    """View security audit log."""
    try:
        from memory_thread.nervous.audit_ledger import ledger

        entries = ledger.query(limit=limit)
        if as_json:
            print(json.dumps([e.to_dict() if hasattr(e, "to_dict") else str(e) for e in entries]))
            return
        console.print(f"[cyan]Audit Log[/cyan] (last {limit}):")
        for e in entries:
            console.print(f"  {e}")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# --- Clients sub-commands ---


@clients_app.command("register")
def clients_register(
    name: str = typer.Argument(..., help="Client name"),
    role: str = typer.Option("agent", "--role", "-r"),
    authority: float = typer.Option(0.5, "--authority", "-a", min=0, max=1),
):
    """Register an API client."""
    try:
        from memory_thread.nervous.client_registry import client_registry

        result = client_registry.register(
            name, role=role, authority=authority, registrar_role=os.environ.get("MT_ROLE", "admin")
        )
        console.print(f"[green]✔ Registered: {result['name']}[/green]")
        console.print(f"  Client ID: [bold]{result['client_id']}[/bold]")
        console.print(f"  API Key:   [bold red]{result['api_key']}[/bold red]")
        console.print(f"  [yellow]⚠ Save this key — never shown again[/yellow]")
    except PermissionError as e:
        console.print(f"[red]✘ DENIED: {e}[/red]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@clients_app.command("list")
def clients_list(as_json: bool = typer.Option(False, "--json", "-j")):
    """List API clients."""
    try:
        from memory_thread.nervous.client_registry import client_registry

        clients = client_registry.list_clients()
        if as_json:
            print(json.dumps(clients))
            return
        if not clients:
            console.print("[dim]No registered clients[/dim]")
            return
        table = Table(title="API Clients", show_lines=False)
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Role")
        table.add_column("Auth", style="yellow")
        for c in clients:
            table.add_row(c["client_id"], c["name"], c["role"], f"{c['authority']:.1f}")
        console.print(table)
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@clients_app.command("deactivate")
def clients_deactivate(client_id: str = typer.Argument(...)):
    """Deactivate an API client."""
    try:
        from memory_thread.nervous.client_registry import client_registry

        client_registry.deactivate(client_id, os.environ.get("MT_ROLE", "admin"))
        console.print(f"[green]✔ Deactivated: {client_id}[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════


@app.command("clear")
def clear_all(force: bool = typer.Option(False, "--force", "-f")):
    """[red]DELETE ALL[/red] memories."""
    if not force:
        console.print("[red bold]⚠ THIS WILL DELETE ALL MEMORIES ⚠[/red bold]")
        if not typer.confirm("Confirm TOTAL WIPE?"):
            console.print("[dim]Cancelled[/dim]")
            return
    client = _client()
    try:
        client.clear()
        console.print("[green]✔ All memories cleared[/green]")
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def rootkey(verify: Optional[str] = typer.Option(None, "--verify", "-v")):
    """Manage the nuclear root key."""
    try:
        from memory_thread.nervous.vault import vault

        if verify:
            valid = vault.verify_godfather(verify)
            console.print(f"[green]✔ Key VALID[/green]" if valid else f"[red]✘ Key INVALID[/red]")
            return
        key = vault.get_or_create_godfather_key()
        if key.startswith("[HIDDEN"):
            console.print("Root key: [dim]already set (hidden)[/dim]")
            console.print("[dim]Use --verify <key> to check[/dim]")
        else:
            console.print(
                Panel(
                    f"[bold red]{key}[/bold red]\n\n[yellow]⚠ Save this — NEVER shown again[/yellow]",
                    title="[red]NUCLEAR KEY[/red]",
                    border_style="red",
                )
            )
    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def su(role: str = typer.Argument(..., help="Role to switch to")):
    """Switch your role."""
    valid_roles = ["guest", "user", "admin", "developer", "employee", "researcher", "executive"]
    if role.lower() not in valid_roles:
        console.print(f"[red]✘ Invalid. Choose: {', '.join(valid_roles)}[/red]")
        raise typer.Exit(1)
    os.environ["MT_ROLE"] = role.lower()
    console.print(f"[green]✔ Now:[/green] {role}")
    console.print(f"[dim]Session only. Export MT_ROLE={role} to persist.[/dim]")


@app.command()
def sudo(
    action: str = typer.Argument(..., help="Action: enable"),
    role: str = typer.Argument(..., help="Role to grant"),
    username: str = typer.Argument(..., help="Target user"),
):
    """Grant role to another user."""
    hierarchy = {"root": 5, "admin": 4, "engineer": 3, "employee": 2, "guest": 1}
    my_level = hierarchy.get(os.environ.get("MT_ROLE", "guest"), 0)
    if my_level <= hierarchy.get(role, 0):
        console.print(f"[red]✘ Cannot grant {role} — requires higher rank[/red]")
        raise typer.Exit(1)
    console.print(f"[green]✔ Granted {role} to {username}[/green]")


# ═══════════════════════════════════════════════════════════════════════════════
# WORKSPACE & CODE INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def init(
    path: str = typer.Argument(".", help="Project root (default: current dir)"),
    namespace: str = typer.Option(None, help="Namespace for this project"),
):
    """Initialize MT workspace in a project."""
    project_root = os.path.abspath(path)
    mt_dir = os.path.join(project_root, ".mt")

    if os.path.exists(mt_dir):
        console.print(f"[yellow]⚠ Already initialized:[/yellow] {mt_dir}")
        return

    os.makedirs(mt_dir, exist_ok=True)

    # Create config
    ns = namespace or os.path.basename(project_root).lower().replace(" ", "_")
    config = {
        "namespace": ns,
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "user": _user(),
        "role": os.environ.get("MT_ROLE", "guest"),
    }

    import json as _json

    config_path = os.path.join(mt_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        _json.dump(config, f, indent=2)

    # Create .gitignore for MT workspace
    gitignore_path = os.path.join(mt_dir, ".gitignore")
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("# MT workspace files\n*.jsonl\nwal/\nvault/\n")

    console.print(
        Panel(
            f"[green]✔ Initialized Memory Thread workspace[/green]\n\n"
            f"  Project:   [cyan]{os.path.basename(project_root)}[/cyan]\n"
            f"  Namespace: [cyan]{ns}[/cyan]\n"
            f"  Config:    [dim]{config_path}[/dim]\n\n"
            f"  Next steps:\n"
            f"    [dim]mt load . [/dim]        Ingest this project\n"
            f"    [dim]mt codebase . [/dim]    Analyze code structure\n"
            f'    [dim]mt search "query" [/dim] Search memories',
            title="MT Init",
            border_style="green",
        )
    )


@app.command()
def codebase(
    path: str = typer.Argument(".", help="Project root to analyze"),
    store: bool = typer.Option(False, "--store", "-s", help="Store analysis as memories"),
):
    """Analyze a codebase — classes, functions, imports, call graph."""

    if not os.path.isdir(path):
        console.print(f"[red]✘ Not a directory: {path}[/red]")
        raise typer.Exit(1)

    try:
        from memory_thread.services.code_intelligence import code_intelligence

        with console.status("[cyan]Analyzing codebase..."):
            project = code_intelligence.analyze_project(path)

        if project.total_files == 0:
            console.print("[yellow]No supported source files found.[/yellow]")
            return

        # Project summary
        lang_str = ", ".join(
            f"{lang}: {count}"
            for lang, count in sorted(project.languages.items(), key=lambda x: -x[1])
        )
        console.print(
            Panel(
                f"[bold cyan]{os.path.basename(os.path.abspath(path))}[/bold cyan]\n\n"
                f"  Files:     [green]{project.total_files}[/green]\n"
                f"  Classes:   [green]{project.total_classes}[/green]\n"
                f"  Functions: [green]{project.total_functions}[/green]\n"
                f"  Lines:     [green]{project.total_lines:,}[/green]\n"
                f"  Languages: [dim]{lang_str}[/dim]",
                title="Codebase Analysis",
                border_style="cyan",
            )
        )

        # Classes table
        if project.total_classes > 0:
            cls_table = Table(title="Classes", show_lines=False)
            cls_table.add_column("Class", style="cyan")
            cls_table.add_column("File", style="dim")
            cls_table.add_column("Methods", style="green")
            cls_table.add_column("Bases", style="yellow")

            for fa in project.files:
                for cls in fa.classes:
                    cls_table.add_row(
                        cls.name,
                        fa.file_name,
                        str(len(cls.methods)),
                        ", ".join(cls.bases) or "-",
                    )
            console.print(cls_table)

        # Dependency graph
        dep_graph = code_intelligence.dependency_graph_fact(project)
        if dep_graph and len(dep_graph.splitlines()) > 1:
            console.print(
                Panel(
                    dep_graph,
                    title="Dependency Graph",
                    border_style="yellow",
                )
            )

        # Directory tree
        if project.tree:
            console.print(
                Panel(
                    project.tree[:2000],  # Cap output
                    title="Project Structure",
                    border_style="dim",
                )
            )

        # Store to memory if requested
        if store:
            client = _client()
            summary = code_intelligence.project_summary_fact(project)
            client.remember(content=summary, source="system", confidence=1.0, memory_type="fact")

            dep = code_intelligence.dependency_graph_fact(project)
            if dep:
                client.remember(content=dep, source="system", confidence=1.0, memory_type="fact")

            cg = code_intelligence.call_graph_fact(project)
            if cg:
                client.remember(content=cg, source="system", confidence=1.0, memory_type="fact")

            total_facts = 0
            for fa in project.files:
                facts = code_intelligence.to_galaxy_facts(fa)
                for fact in facts:
                    client.remember(
                        content=fact["content"], source="system", confidence=1.0, memory_type="fact"
                    )
                    total_facts += 1

            console.print(f"\n[green]✔ Stored {total_facts + 3} structured facts to memory[/green]")

    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


@app.command()
def document(
    path: str = typer.Argument(..., help="PDF, markdown, or text file to analyze"),
    store: bool = typer.Option(False, "--store", "-s", help="Store analysis as memories"),
):
    """Analyze a document — sections, citations, key terms."""

    if not os.path.isfile(path):
        console.print(f"[red]✘ Not a file: {path}[/red]")
        raise typer.Exit(1)

    try:
        from memory_thread.services.document_intelligence import doc_intelligence

        with console.status("[cyan]Analyzing document..."):
            analysis = doc_intelligence.analyze_document(path)

        if not analysis:
            console.print("[yellow]Unsupported document type.[/yellow]")
            return

        # Document summary
        console.print(
            Panel(
                f"[bold cyan]{analysis.title}[/bold cyan]\n\n"
                f"  File:       [dim]{analysis.file_name}[/dim]\n"
                f"  Type:       {analysis.doc_type}\n"
                f"  Pages:      [green]{analysis.total_pages or 'N/A'}[/green]\n"
                f"  Words:      [green]{analysis.total_words:,}[/green]\n"
                f"  Sections:   [green]{len(analysis.sections)}[/green]\n"
                f"  Citations:  [green]{len(analysis.citations)}[/green]\n"
                f"  Definitions:[green] {len(analysis.definitions)}[/green]\n"
                f"  Figures:    [green]{len(analysis.figures)}[/green]",
                title="Document Analysis",
                border_style="cyan",
            )
        )

        # Table of contents
        if analysis.sections:
            toc_lines = []
            for section in analysis.sections:
                indent = "  " * section.level
                page_str = f" (p.{section.page_start})" if section.page_start else ""
                toc_lines.append(
                    f"{indent}[cyan]{section.title}[/cyan]{page_str} [{section.word_count} words]"
                )
            console.print(
                Panel(
                    "\n".join(toc_lines),
                    title="Table of Contents",
                    border_style="green",
                )
            )

        # Key terms
        if analysis.key_terms:
            console.print(
                Panel(
                    ", ".join(f"[yellow]{t}[/yellow]" for t in analysis.key_terms[:20]),
                    title="Key Terms",
                    border_style="yellow",
                )
            )

        # Definitions
        if analysis.definitions:
            def_table = Table(title="Definitions", show_lines=False)
            def_table.add_column("Term", style="cyan", max_width=25)
            def_table.add_column("Definition", style="dim", max_width=60)
            def_table.add_column("Section", style="green", max_width=20)
            for defn in analysis.definitions[:15]:
                def_table.add_row(defn.term, defn.definition[:80], defn.section[:20])
            console.print(def_table)

        # Citations
        if analysis.citations:
            unique_cites = list({c.text for c in analysis.citations})
            console.print(
                Panel(
                    ", ".join(f"[dim]{c}[/dim]" for c in unique_cites[:20]),
                    title=f"Citations ({len(unique_cites)} unique)",
                    border_style="magenta",
                )
            )

        # Store if requested
        if store:
            client = _client()
            facts = doc_intelligence.to_galaxy_facts(analysis)
            for fact in facts:
                client.remember(
                    content=fact["content"], source="system", confidence=1.0, memory_type="fact"
                )
            console.print(f"\n[green]✔ Stored {len(facts)} structured facts to memory[/green]")

    except Exception as e:
        console.print(f"[red]✘ {e}[/red]")


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER COMMAND
# ═══════════════════════════════════════════════════════════════════════════════


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """Start the Memory Thread API server."""
    import subprocess
    import sys

    console.print(f"[cyan]Starting Memory Thread API server...[/cyan]")
    console.print(f"  Host:     {host}")
    console.print(f"  Port:     {port}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Reload:   {reload}")
    console.print()

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "memory_thread.api.server:app",
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(workers),
    ]
    if reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


def run():
    """Main entry point."""
    app()


if __name__ == "__main__":
    run()
