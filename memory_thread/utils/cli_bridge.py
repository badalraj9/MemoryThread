"""
MT Neural Interface - Professional Galaxy TUI
"""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Static, Input, ListView, ListItem,
    Label, Tree, DataTable, Log, TabbedContent, TabPane
)
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from textual import events
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
import uuid

# MT imports
from memory_thread.sdk import MemoryClient
from memory_thread.core.galaxy import GalaxyCore  # Your new core

# ============================================================================
# DATA MODELS
# ============================================================================

class AgentUniverse:
    def __init__(self, agent_id: str, active: bool = False):
        self.agent_id = agent_id
        self.active = active
        self.fact_count = 0
        self.belief_count = 0
        self.activity_pct = 0.0

class Conflict:
    def __init__(self, fact_id: str, agents: List[str], severity: str):
        self.fact_id = fact_id
        self.agents = agents
        self.severity = severity
        self.timestamp = datetime.now()

class FactEntry:
    def __init__(self, fact_id: str, source: str, preview: str):
        self.fact_id = fact_id
        self.source = source
        self.preview = preview
        self.timestamp = datetime.now()

# ============================================================================
# CUSTOM WIDGETS
# ============================================================================

class AgentUniversePanel(Static):
    """Shows active agent universes"""
    
    def __init__(self):
        super().__init__()
        self.universes: List[AgentUniverse] = []
    
    def compose(self) -> ComposeResult:
        yield Static("AGENT UNIVERSES", classes="panel-title")
        yield ListView(id="universe-list")
    
    def update_universes(self, universes: List[AgentUniverse]):
        self.universes = universes
        list_view = self.query_one("#universe-list", ListView)
        list_view.clear()
        
        for u in universes:
            indicator = "●" if u.active else "○"
            line = f"{indicator} {u.agent_id:15} [{u.activity_pct:>3.0f}%]"
            item = ListItem(Label(line))
            list_view.append(item)

class ConflictPanel(Static):
    """Shows active conflicts detected by Galaxy"""
    
    def compose(self) -> ComposeResult:
        yield Static("ACTIVE CONFLICTS", classes="panel-title")
        yield ListView(id="conflict-list")
    
    def update_conflicts(self, conflicts: List[Conflict]):
        list_view = self.query_one("#conflict-list", ListView)
        list_view.clear()
        
        if not conflicts:
            list_view.append(ListItem(Label("[dim]No conflicts detected[/]")))
            return
        
        for c in conflicts:
            agents_str = " vs ".join(c.agents)
            severity_color = {
                "LOW": "green",
                "MEDIUM": "yellow", 
                "HIGH": "red"
            }.get(c.severity, "white")
            
            item = ListItem(Label(
                f"[bold]!{/] {c.fact_id[:8]}\n"
                f"  {agents_str}\n"
                f"  [{severity_color}]{c.severity}[/]"
            ))
            list_view.append(item)

class FactStreamPanel(Static):
    """Shows recent facts ingested into galaxy"""
    
    def compose(self) -> ComposeResult:
        yield Static("RECENT FACTS", classes="panel-title")
        yield DataTable(id="fact-table")
    
    def on_mount(self):
        table = self.query_one("#fact-table", DataTable)
        table.add_columns("ID", "Source", "Preview", "Age")
        table.zebra_stripes = True
    
    def update_facts(self, facts: List[FactEntry]):
        table = self.query_one("#fact-table", DataTable)
        table.clear()
        
        for f in facts:
            age = self._format_age(f.timestamp)
            table.add_row(
                f.fact_id[:8],
                f.source[:15],
                f.preview[:30] + "...",
                age
            )
    
    def _format_age(self, timestamp: datetime) -> str:
        delta = datetime.now() - timestamp
        if delta.seconds < 60:
            return f"{delta.seconds}s ago"
        elif delta.seconds < 3600:
            return f"{delta.seconds // 60}m ago"
        else:
            return f"{delta.seconds // 3600}h ago"

class ChatPanel(ScrollableContainer):
    """Main chat interface with conflict notifications"""
    
    def compose(self) -> ComposeResult:
        yield Log(id="chat-log", auto_scroll=True)
        yield Input(placeholder="▌ Type your message...", id="chat-input")
    
    def add_message(self, role: str, content: str, conflict: bool = False):
        log = self.query_one("#chat-log", Log)
        
        color = {
            "user": "cyan",
            "assistant": "white",
            "system": "yellow"
        }.get(role, "white")
        
        log.write_line(f"[{color}]{role.upper()}:[/] {content}")
        
        if conflict:
            log.write_line("[red]⚠ Conflict detected - press 'c' to resolve[/]")

# ============================================================================
# MAIN APP
# ============================================================================

class MTNeuralInterface(App):
    """Memory Thread Neural Interface"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    .panel-title {
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    
    #universe-list, #conflict-list {
        height: 10;
        border: solid $primary;
    }
    
    #fact-table {
        height: 6;
        border: solid $primary;
    }
    
    #chat-log {
        height: 1fr;
        border: solid $accent;
        margin: 1 0;
    }
    
    #chat-input {
        border: solid $accent;
    }
    
    Input {
        background: $surface;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("u", "show_universes", "Universes"),
        Binding("c", "show_conflicts", "Conflicts"),
        Binding("f", "show_facts", "Facts"),
        Binding("slash", "search", "Search"),
        Binding("question_mark", "help", "Help"),
        Binding("s", "toggle_secure", "Security"),
        Binding("g", "toggle_galaxy", "Galaxy"),
    ]
    
    TITLE = "MT NEURAL INTERFACE v2.0"
    
    # Reactive properties
    secure_mode = reactive(False)
    galaxy_active = reactive(True)
    active_agent = reactive("SecurityBot")
    
    def __init__(self):
        super().__init__()
        self.galaxy: Optional[GalaxyCore] = None
        self.universes: List[AgentUniverse] = []
        self.conflicts: List[Conflict] = []
        self.facts: List[FactEntry] = []
        
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Horizontal():
            # Left column
            with Vertical(classes="left-panel"):
                yield AgentUniversePanel()
                yield ConflictPanel()
            
            # Right column (main)
            with Vertical(classes="main-panel"):
                yield FactStreamPanel()
                yield ChatPanel()
        
        yield Footer()
    
    def on_mount(self):
        """Initialize Galaxy core and start monitoring"""
        self.initialize_galaxy()
        self.set_interval(2.0, self.update_status)
    
    def initialize_galaxy(self):
        """Initialize the Galaxy architecture"""
        # This will use your actual GalaxyCore
        from memory_thread.core.galaxy import GalaxyCore
        from memory_thread.services.persistence import PersistenceEngine
        
        # Initialize core components
        pg_client = None  # Your Postgres client
        qdrant_client = None  # Your Qdrant client
        
        self.galaxy = GalaxyCore(pg_client, qdrant_client)
        
        # Register default agents
        self.galaxy.register_agent("SecurityBot", authority=0.9)
        self.galaxy.register_agent("MarketingBot", authority=0.5)
        self.galaxy.register_agent("AuditBot", authority=0.8)
        
        # Initialize UI state
        self.universes = [
            AgentUniverse("SecurityBot", active=True),
            AgentUniverse("MarketingBot"),
            AgentUniverse("AuditBot"),
        ]
    
    async def update_status(self):
        """Periodic update of UI state from Galaxy"""
        if not self.galaxy:
            return
        
        # Update agent activity
        for universe in self.universes:
            # Query Galaxy for agent activity
            facts = await self.galaxy.get_agent_facts(universe.agent_id)
            universe.fact_count = len(facts)
            universe.activity_pct = (universe.fact_count / 100.0) * 100  # Mock
        
        # Update conflicts
        conflicts = await self.galaxy.get_active_conflicts()
        self.conflicts = [
            Conflict(
                fact_id=c.fact_id,
                agents=[b.agent_id for b in c.beliefs],
                severity=self._compute_severity(c)
            )
            for c in conflicts
        ]
        
        # Update recent facts
        recent = await self.galaxy.get_recent_facts(limit=10)
        self.facts = [
            FactEntry(
                fact_id=str(f.id),
                source=f.source_uri,
                preview=f.content[:50]
            )
            for f in recent
        ]
        
        # Refresh UI
        self.refresh_panels()
    
    def _compute_severity(self, conflict) -> str:
        """Compute conflict severity based on authority divergence"""
        authorities = [b.agent_authority for b in conflict.beliefs]
        if not authorities:
            return "LOW"
        
        max_auth = max(authorities)
        min_auth = min(authorities)
        divergence = max_auth - min_auth
        
        if divergence > 0.5:
            return "HIGH"
        elif divergence > 0.3:
            return "MEDIUM"
        else:
            return "LOW"
    
    def refresh_panels(self):
        """Refresh all UI panels with current data"""
        universe_panel = self.query_one(AgentUniversePanel)
        universe_panel.update_universes(self.universes)
        
        conflict_panel = self.query_one(ConflictPanel)
        conflict_panel.update_conflicts(self.conflicts)
        
        fact_panel = self.query_one(FactStreamPanel)
        fact_panel.update_facts(self.facts)
    
    async def on_input_submitted(self, event: Input.Submitted):
        """Handle chat input"""
        chat_panel = self.query_one(ChatPanel)
        user_input = event.value
        
        if not user_input.strip():
            return
        
        # Clear input
        event.input.value = ""
        
        # Show user message
        chat_panel.add_message("user", user_input)
        
        # Process through Galaxy
        if self.galaxy:
            # Ingest as fact
            fact, belief = await self.galaxy.ingest(
                agent_id=self.active_agent,
                raw_observation={"text": user_input, "source": "user:input"}
            )
            
            # Generate response (mock - integrate with your LLM)
            response = await self.generate_response(user_input, belief)
            
            # Check for conflicts
            has_conflict = len(self.conflicts) > 0
            
            # Show response
            chat_panel.add_message("assistant", response, conflict=has_conflict)
    
    async def generate_response(self, user_input: str, belief) -> str:
        """Generate response using LLM (integrate with your chat logic)"""
        # This should call your actual LLM integration
        return f"Processing: {user_input}"
    
    # ========================================================================
    # ACTIONS (Key Bindings)
    # ========================================================================
    
    def action_show_universes(self):
        """Show detailed universe view"""
        self.push_screen(UniverseDetailScreen(self.universes))
    
    def action_show_conflicts(self):
        """Show conflict resolution screen"""
        if self.conflicts:
            self.push_screen(ConflictResolutionScreen(self.conflicts[0]))
        else:
            self.notify("No active conflicts")
    
    def action_show_facts(self):
        """Show fact browser"""
        self.push_screen(FactBrowserScreen(self.facts))
    
    def action_search(self):
        """Open search interface"""
        self.notify("Search not implemented yet")
    
    def action_help(self):
        """Show help screen"""
        self.push_screen(HelpScreen())
    
    def action_toggle_secure(self):
        """Toggle secure mode"""
        self.secure_mode = not self.secure_mode
        status = "ENABLED" if self.secure_mode else "DISABLED"
        self.notify(f"Secure Mode: {status}")
    
    def action_toggle_galaxy(self):
        """Toggle galaxy architecture"""
        self.galaxy_active = not self.galaxy_active
        status = "ACTIVE" if self.galaxy_active else "INACTIVE"
        self.notify(f"Galaxy: {status}")
    
    def watch_secure_mode(self, secure: bool):
        """Update header when secure mode changes"""
        self.sub_title = "[SECURE]" if secure else ""
    
    def watch_galaxy_active(self, active: bool):
        """Update header when galaxy toggles"""
        status = "GALAXY ON" if active else "GALAXY OFF"
        self.sub_title = f"{self.sub_title} {status}".strip()

# ============================================================================
# DETAIL SCREENS
# ============================================================================

class UniverseDetailScreen(Screen):
    """Detailed view of agent universes"""
    pass

class ConflictResolutionScreen(Screen):
    """Interactive conflict resolution"""
    pass

class FactBrowserScreen(Screen):
    """Browse and search facts"""
    pass

class HelpScreen(Screen):
    """Help and keybindings"""
    
    BINDINGS = [("escape", "app.pop_screen", "Close")]
    
    def compose(self) -> ComposeResult:
        yield Static("""
# MT NEURAL INTERFACE - HELP

## Keybindings

q         - Quit application
u         - Show universe details
c         - Resolve conflicts
f         - Browse facts
/         - Search
?         - This help screen
s         - Toggle secure mode
g         - Toggle galaxy architecture

## Concepts

AGENT UNIVERSES
Each agent maintains their own fact space and beliefs.
Galaxy architecture automatically links related beliefs.

CONFLICTS
When agents disagree about the same fact, conflicts are detected.
Press 'c' to resolve using authority, consensus, or manual selection.

FACTS vs BELIEFS
Facts are immutable observations.
Beliefs are agent interpretations of facts.
        """, id="help-text")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = MTNeuralInterface()
    app.run()
