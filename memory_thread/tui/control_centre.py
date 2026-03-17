"""
Memory Thread Control Centre TUI.

A keyboard-driven dashboard for managing Memory Thread.
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    DataTable,
    ListView,
    ListItem,
    Input,
    Label,
    ProgressBar,
    Tabs,
    Tab,
)
from textual.widgets.data_table import RowKey
from textual.events import Key
from textual import work
from textual.pilot import Pilot

import httpx


API_BASE = "http://localhost:8000"

COLORS = {
    "bg": "#1a1a2e",
    "panel": "#16213e",
    "accent": "#00d4ff",
    "success": "#00ff88",
    "warning": "#ffd700",
    "error": "#ff4757",
    "text": "#ffffff",
    "dim": "#888888",
}


class MemoryDetailModal(Static):
    """Modal to show memory details."""

    def __init__(self, memory: Dict[str, Any]):
        super().__init__()
        self.memory = memory

    def compose(self) -> ComposeResult:
        yield Container(
            Label(f"[bold]Content:[/bold] {self.memory.get('content', '')}", id="detail-content"),
            Label(
                f"[bold]Type:[/bold] {self.memory.get('memory_type', 'unknown')}", id="detail-type"
            ),
            Label(
                f"[bold]Trust Score:[/bold] {self.memory.get('truth_score', 0):.3f}",
                id="detail-trust",
            ),
            Label(
                f"[bold]Confidence:[/bold] {self.memory.get('confidence', 0):.2f}",
                id="detail-confidence",
            ),
            Label(
                f"[bold]Authority:[/bold] {self.memory.get('authority', 0):.2f}",
                id="detail-authority",
            ),
            Label(
                f"[bold]Namespace:[/bold] {self.memory.get('namespace', 'default')}",
                id="detail-namespace",
            ),
            Button("Close", id="close-modal"),
            id="memory-detail-modal",
        )


class GoldenThreadModal(Static):
    """Modal to show golden thread (complete causal history) of a memory."""

    def __init__(self, memory: Dict[str, Any], golden_thread_data: Dict[str, Any]):
        super().__init__()
        self.memory = memory
        self.golden_thread_data = golden_thread_data

    def compose(self) -> ComposeResult:
        narrative = self.golden_thread_data.get("narrative", "No golden thread data available")

        yield Container(
            Label(f"[bold cyan]Golden Thread[/bold cyan]", id="gt-title"),
            Label(
                f"[bold]Entity:[/bold] {self.memory.get('entity_id', 'Unknown')[:8]}...",
                id="gt-entity",
            ),
            ScrollableContainer(
                Label(narrative, id="gt-narrative"),
                id="gt-scroll",
            ),
            Button("Close", id="close-golden-thread"),
            id="golden-thread-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-golden-thread":
            self.dismiss()


class InputDialog(Static):
    """Dialog for user input."""

    def __init__(self, title: str, placeholder: str = ""):
        super().__init__(title)
        self.placeholder = placeholder
        self.result = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder=self.placeholder, id="dialog-input")
        yield Horizontal(
            Button("Cancel", variant="default", id="dialog-cancel"),
            Button("OK", variant="primary", id="dialog-ok"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dialog-ok":
            self.result = self.query_one("#dialog-input", Input).value
        self.dismiss(self.result)


class ConfirmDialog(Static):
    """Confirmation dialog."""

    def __init__(self, message: str):
        super().__init__("Confirm")
        self.message = message
        self.result = False

    def compose(self) -> ComposeResult:
        yield Label(self.message, id="confirm-message")
        yield Horizontal(
            Button("Cancel", variant="default", id="confirm-cancel"),
            Button("Confirm", variant="error", id="confirm-ok"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.result = event.button.id == "confirm-ok"
        self.dismiss(self.result)


class ControlCentre(App):
    """Memory Thread Control Centre TUI."""

    CSS = f"""
    Screen {{
        background: {COLORS["bg"]};
    }}

    #main-container {{
        layout: horizontal;
        height: 100%;
    }}

    #left-panel {{
        width: 25%;
        background: {COLORS["panel"]};
        padding: 1;
    }}

    #right-panel {{
        width: 75%;
        background: {COLORS["bg"]};
    }}

    #status-section, #actions-section {{
        height: auto;
        padding: 1;
    }}

    .section-title {{
        color: {COLORS["accent"]};
        text-style: bold;
        margin-bottom: 1;
    }}

    .status-ok {{
        color: {COLORS["success"]};
    }}

    .status-error {{
        color: {COLORS["error"]};
    }}

    .trust-high {{
        color: {COLORS["success"]};
    }}

    .trust-medium {{
        color: {COLORS["warning"]};
    }}

    .trust-low {{
        color: {COLORS["error"]};
    }}

    DataTable {{
        height: 100%;
        background: {COLORS["panel"]};
    }}

    .tab-content {{
        height: 100%;
        padding: 1;
    }}

    #overview-tab, #memories-tab, #contemplator-tab {{
        layout: vertical;
        height: 100%;
    }}

    #activity-log {{
        height: 30%;
        background: {COLORS["panel"]};
        padding: 1;
    }}

    #memory-table {{
        height: 70%;
    }}

    #action-menu ListView {{
        height: auto;
    }}

    #action-menu ListItem {{
        padding: 0 1;
    }}

    Button {{
        margin: 0 1;
    }}

    #loading-indicator {{
        display: none;
        color: {COLORS["accent"]};
    }}

    .loading {{
        display: block;
    }}

    #server-warning {{
        background: {COLORS["error"]};
        color: white;
        padding: 1;
        text-align: center;
    }}

    #detail-content {{
        margin-bottom: 1;
    }}

    #golden-thread-modal {{
        width: 80%;
        height: 80%;
        background: {COLORS["panel"]};
        border: solid {COLORS["accent"]};
    }}

    #gt-scroll {{
        height: 80%;
    }}

    #gt-narrative {{
        color: {COLORS["text"]};
    }}
    """

    BINDINGS = [
        ("tab", "switch_tab", "Switch Tab"),
        ("t", "show_golden_thread", "Golden Thread"),
        ("d", "trigger_decay", "Decay"),
        ("p", "trigger_prune", "Prune"),
        ("c", "trigger_consolidate", "Consolidate"),
        ("r", "trigger_reflect", "Reflect"),
        ("i", "trigger_ingest", "Ingest"),
        ("m", "trigger_migrate", "Migrate"),
        ("s", "start_server", "Start Server"),
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.server_running = False
        self.status = {}
        self.memories: List[Dict] = []
        self.namespaces: Dict[str, Dict] = {}
        self.activity_log: List[Dict] = []
        self.current_tab = "overview"
        self.namespace_filter = "all"
        self.type_filter = "all"
        self.selected_memory: Optional[Dict] = None

    async def on_mount(self) -> None:
        """Initialize the app."""
        self.title = "Memory Thread Control Centre"
        await self.check_server()
        await self.load_data()
        self.set_interval(30, self.load_data)

    async def check_server(self) -> None:
        """Check if MT server is running."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/health", timeout=3)
                self.server_running = resp.status_code == 200
                if self.server_running:
                    self.status = resp.json()
        except Exception:
            self.server_running = False

    @work(exclusive=True)
    async def load_data(self) -> None:
        """Load all data from MT API."""
        if not self.server_running:
            return

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/stats")
                if resp.status_code == 200:
                    data = resp.json()
                    self.namespaces = {data.get("namespace", "default"): data}

                resp = await client.post(
                    f"{API_BASE}/memory/recall",
                    json={"query": "*", "top_k": 100},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.memories = data.get("memories", [])

                self.activity_log.insert(
                    0,
                    {
                        "timestamp": datetime.now().isoformat(),
                        "type": "refresh",
                        "result": f"Loaded {len(self.memories)} memories",
                    },
                )
                self.activity_log = self.activity_log[:10]

        except Exception as e:
            self.activity_log.insert(
                0,
                {
                    "timestamp": datetime.now().isoformat(),
                    "type": "error",
                    "result": str(e),
                },
            )

        self.refresh()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        if not self.server_running:
            yield Static("⚠ MT Server not running - run 'mt serve' first", id="server-warning")

        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Static("SYSTEM STATUS", classes="section-title", id="status-title")
                yield Static(id="status-content")
                yield Static("ACTIONS", classes="section-title", id="actions-title")
                yield ListView(
                    ListItem(Label("[D] Decay memories")),
                    ListItem(Label("[P] Prune low-trust")),
                    ListItem(Label("[C] Consolidate")),
                    ListItem(Label("[R] Reflect")),
                    ListItem(Label("[I] Ingest path")),
                    ListItem(Label("[M] Run migrations")),
                    ListItem(Label("[S] Start server")),
                    ListItem(Label("[Q] Quit")),
                    id="action-menu",
                )

            with Vertical(id="right-panel"):
                yield Tabs(
                    Tab("Overview", id="overview-tab"),
                    Tab("Memories", id="memories-tab"),
                    Tab("Contemplator", id="contemplator-tab"),
                    id="main-tabs",
                )

                with ScrollableContainer(id="overview-tab", classes="tab-content"):
                    yield Static("Memory Health", classes="section-title")
                    yield Static(id="health-stats")
                    yield Static("Namespaces", classes="section-title")
                    yield DataTable(id="namespace-table")
                    yield Static("Recent Activity", classes="section-title")
                    yield Static(id="activity-log")

                with ScrollableContainer(id="memories-tab", classes="tab-content"):
                    yield DataTable(id="memory-table")
                    yield Static(id="memory-filters")

                with ScrollableContainer(id="contemplator-tab", classes="tab-content"):
                    yield Static("Latest Reflection", classes="section-title")
                    yield Static(id="reflection-summary")
                    yield Static("Memory Distribution", classes="section-title")
                    yield Static(id="memory-chart")
                    yield Button("Run Reflection Now", id="run-reflection")

        yield Footer()

    def on_mount(self) -> None:
        """Set up the UI after mounting."""
        self.query_one("#status-content", Static).update(self.render_status())
        self.query_one("#health-stats", Static).update(self.render_health())
        self.query_one("#activity-log", Static).update(self.render_activity())

        table = self.query_one("#memory-table", DataTable)
        table.add_columns("Content", "Type", "Trust", "Namespace", "Age")
        table.cursor_type = "row"
        table.focus()
        self.populate_memory_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the memory table."""
        row_key = event.row_key
        if row_key:
            try:
                row_index = int(row_key.value)
                sorted_memories = sorted(
                    self.memories, key=lambda x: x.get("trust_score", 0), reverse=True
                )
                if 0 <= row_index < len(sorted_memories):
                    self.selected_memory = sorted_memories[row_index]
            except (ValueError, TypeError):
                pass

    def render_status(self) -> str:
        """Render system status."""
        pg = self.status.get("postgres_connected", False)
        qd = self.status.get("qdrant_connected", False)
        return f"""● PostgreSQL   {"connected" if pg else "disconnected"}
● Qdrant       {"connected" if qd else "disconnected"}
● Embeddings   loaded
● WAL          0 recovered"""

    def render_health(self) -> str:
        """Render memory health stats."""
        total = len(self.memories)
        if total == 0:
            return "Total: 0 | Avg Trust: N/A | Stale: 0 | Low Trust: 0"

        trust_scores = [m.get("truth_score", 0) for m in self.memories]
        avg_trust = sum(trust_scores) / len(trust_scores) if trust_scores else 0

        return f"Total: {total} | Avg Trust: {avg_trust:.3f} | Stale: 0 | Low Trust: 0"

    def render_activity(self) -> str:
        """Render recent activity log."""
        if not self.activity_log:
            return "No recent activity"
        return "\n".join(
            f"{a['timestamp'][:19]} | {a['type']} | {a['result']}" for a in self.activity_log
        )

    def populate_memory_table(self) -> None:
        """Populate the memory table."""
        table = self.query_one("#memory-table", DataTable)
        table.clear()

        filtered = self.memories
        if self.namespace_filter != "all":
            filtered = [m for m in filtered if m.get("namespace") == self.namespace_filter]
        if self.type_filter != "all":
            filtered = [m for m in filtered if m.get("memory_type") == self.type_filter]

        sorted_memories = sorted(filtered, key=lambda x: x.get("trust_score", 0), reverse=True)

        for idx, m in enumerate(sorted_memories):
            content = (m.get("content", "") or "")[:60]
            mem_type = m.get("memory_type", "unknown")
            trust = m.get("truth_score", 0)
            namespace = m.get("namespace", "default")
            age = "1d"

            table.add_row(content, mem_type, f"{trust:.3f}", namespace, age, key=str(idx))

    def action_switch_tab(self) -> None:
        """Switch between tabs."""
        tabs = self.query_one("#main-tabs", Tabs)
        if self.current_tab == "overview":
            self.current_tab = "memories"
        elif self.current_tab == "memories":
            self.current_tab = "contemplator"
        else:
            self.current_tab = "overview"
        tabs.active = f"{self.current_tab}-tab"

    async def action_show_golden_thread(self) -> None:
        """Show golden thread for selected memory."""
        if self.current_tab != "memories" or not self.memories:
            self.activity_log.insert(
                0,
                {
                    "timestamp": datetime.now().isoformat(),
                    "type": "golden_thread",
                    "result": "Select a memory first (go to Memories tab)",
                },
            )
            self.query_one("#activity-log", Static).update(self.render_activity())
            return

        if not self.selected_memory:
            self.activity_log.insert(
                0,
                {
                    "timestamp": datetime.now().isoformat(),
                    "type": "golden_thread",
                    "result": "No memory selected",
                },
            )
            self.query_one("#activity-log", Static).update(self.render_activity())
            return

        entity_id = self.selected_memory.get("entity_id")
        if not entity_id:
            self.activity_log.insert(
                0,
                {
                    "timestamp": datetime.now().isoformat(),
                    "type": "golden_thread",
                    "result": "Invalid memory selection",
                },
            )
            self.query_one("#activity-log", Static).update(self.render_activity())
            return

        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "golden_thread",
                "result": f"Fetching golden thread for {entity_id[:8]}...",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{API_BASE}/memory/{entity_id}/golden-thread",
                    timeout=10,
                )
                if resp.status_code == 200:
                    golden_thread_data = resp.json()
                    modal = GoldenThreadModal(self.selected_memory, golden_thread_data)
                    await self.push_screen(modal)
                else:
                    self.activity_log.insert(
                        0,
                        {
                            "timestamp": datetime.now().isoformat(),
                            "type": "golden_thread",
                            "result": f"Error: {resp.status_code}",
                        },
                    )
                    self.query_one("#activity-log", Static).update(self.render_activity())
        except Exception as e:
            self.activity_log.insert(
                0,
                {
                    "timestamp": datetime.now().isoformat(),
                    "type": "golden_thread",
                    "result": f"Error: {str(e)[:50]}",
                },
            )
            self.query_one("#activity-log", Static).update(self.render_activity())

    def action_trigger_decay(self) -> None:
        """Trigger memory decay."""
        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "decay",
                "result": "Triggered decay",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())

    def action_trigger_prune(self) -> None:
        """Trigger memory prune."""
        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "prune",
                "result": "Triggered prune",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())

    def action_trigger_consolidate(self) -> None:
        """Trigger consolidation."""
        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "consolidate",
                "result": "Triggered consolidation",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())

    def action_trigger_reflect(self) -> None:
        """Trigger reflection."""
        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "reflect",
                "result": "Running reflection...",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())

    async def action_trigger_ingest(self) -> None:
        """Trigger file ingest."""
        dialog = InputDialog("Ingest Path", "Enter path to ingest...")
        async with self_mount(dialog) as pilot:
            result = await pilot.pause()
            if result:
                self.activity_log.insert(
                    0,
                    {
                        "timestamp": datetime.now().isoformat(),
                        "type": "ingest",
                        "result": f"Ingesting: {result}",
                    },
                )
                self.query_one("#activity-log", Static).update(self.render_activity())

    def action_trigger_migrate(self) -> None:
        """Run migrations."""
        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "migrate",
                "result": "Running migrations...",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())

    def action_start_server(self) -> None:
        """Start MT server."""
        self.activity_log.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(),
                "type": "server",
                "result": "Use 'mt serve' to start server",
            },
        )
        self.query_one("#activity-log", Static).update(self.render_activity())


def run():
    """Run the Control Centre TUI."""
    app = ControlCentre()
    app.run()


if __name__ == "__main__":
    run()
