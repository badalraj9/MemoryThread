"""
Memory Thread Chat TUI.

Interactive chat interface with memory context.
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
    ListView,
    ListItem,
    Input,
    Label,
)
from textual.events import Key, Mount
from textual import work
from textual.binding import Binding

import httpx


API_BASE = "http://localhost:8000"
OLLAMA_BASE = "http://localhost:11434"

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


class Message(Static):
    """A chat message."""

    def __init__(self, role: str, content: str, sources: int = 0):
        super().__init__()
        self.role = role
        self.content = content
        self.sources = sources

    def compose(self) -> ComposeResult:
        if self.role == "user":
            yield Container(
                Label(self.content, markup=True),
                id="user-message",
            )
        elif self.role == "system":
            yield Container(
                Label(self.content, markup=True),
                id="system-message",
            )
        else:
            yield Container(
                Label(self.content, markup=True),
                Label(f"── recalled {self.sources} memories ──", markup=True, id="sources-label")
                if self.sources
                else None,
                id="mt-message",
            )


class ModelPickerModal(Static):
    """Modal for selecting AI model."""

    def __init__(self, models: List[Dict], current: str):
        super().__init__("Select Model")
        self.models = models
        self.current = current
        self.selected = current

    def compose(self) -> ComposeResult:
        yield ListView(id="model-list")
        yield Horizontal(
            Button("Cancel", variant="default", id="model-cancel"),
            Button("Select", variant="primary", id="model-select"),
        )

    def on_mount(self) -> None:
        list_view = self.query_one("#model-list", ListView)
        for model in self.models:
            label = f"✓ {model['name']}" if model["name"] == self.current else model["name"]
            list_view.append(ListItem(Label(label)))

    def on_list_view_selected(self, event) -> None:
        if event.list_view.index is not None:
            self.selected = self.models[event.list_view.index]["name"]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "model-select":
            self.dismiss(self.selected)
        else:
            self.dismiss(None)


class NamespacePickerModal(Static):
    """Modal for selecting namespace."""

    def __init__(self, namespaces: List[str], current: str):
        super().__init__("Select Namespace")
        self.namespaces = namespaces
        self.current = current
        self.selected = current

    def compose(self) -> ComposeResult:
        yield ListView(id="namespace-list")
        yield Horizontal(
            Button("Cancel", variant="default", id="ns-cancel"),
            Button("Select", variant="primary", id="ns-select"),
        )

    def on_mount(self) -> None:
        list_view = self.query_one("#namespace-list", ListView)
        for ns in self.namespaces:
            label = f"✓ {ns}" if ns == self.current else ns
            list_view.append(ListItem(Label(label)))

    def on_list_view_selected(self, event) -> None:
        if event.list_view.index is not None:
            self.selected = self.namespaces[event.list_view.index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ns-select":
            self.dismiss(self.selected)
        else:
            self.dismiss(None)


class MemoryChat(App):
    """Memory Thread Chat TUI."""

    CSS = f"""
    Screen {{
        background: {COLORS["bg"]};
    }}

    #main-container {{
        layout: horizontal;
        height: 100%;
    }}

    #chat-panel {{
        width: 70%;
        background: {COLORS["bg"]};
        layout: vertical;
    }}

    #sidebar-panel {{
        width: 30%;
        background: {COLORS["panel"]};
        layout: vertical;
    }}

    #chat-messages {{
        height: 80%;
        background: {COLORS["bg"]};
        padding: 1;
    }}

    #chat-messages Container {{
        margin-bottom: 1;
    }}

    #user-message {{
        align: right;
        background: {COLORS["accent"]};
        color: {COLORS["bg"]};
        padding: 0 1;
        width: 70%;
    }}

    #mt-message {{
        align: left;
        background: {COLORS["panel"]};
        padding: 0 1;
        width: 90%;
    }}

    #system-message {{
        align: center;
        color: {COLORS["warning"]};
        text-style: italic;
    }}

    #sources-label {{
        color: {COLORS["dim"]};
    }}

    #input-container {{
        height: 20%;
        background: {COLORS["panel"]};
        padding: 1;
    }}

    #message-input {{
        height: 100%;
    }}

    .sidebar-section {{
        height: auto;
        padding: 1;
        border-bottom: solid {COLORS["dim"]};
    }}

    .sidebar-title {{
        color: {COLORS["accent"]};
        text-style: bold;
    }}

    .memory-item {{
        color: {COLORS["text"]};
    }}

    .memory-stale {{
        color: {COLORS["dim"]};
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

    .flag-item {{
        color: {COLORS["warning"]};
    }}

    #model-info, #namespace-info {{
        color: {COLORS["text"]};
    }}

    #error-banner {{
        background: {COLORS["error"]};
        color: white;
        padding: 1;
        text-align: center;
    }}

    #welcome-message {{
        color: {COLORS["accent"]};
    }}

    #typing-indicator {{
        color: {COLORS["dim"]};
        display: none;
    }}

    .typing {{
        display: block;
    }}
    """

    BINDINGS = [
        ("enter", "send_message", "Send"),
        ("shift+enter", "newline", "Newline"),
        ("m", "open_model_picker", "Model"),
        ("n", "open_namespace_picker", "Namespace"),
        ("c", "clear_chat", "Clear"),
        ("escape", "quit", "Quit"),
        ("up", "scroll_up", "Up"),
        ("down", "scroll_down", "Down"),
    ]

    def __init__(self, model: Optional[str] = None, namespace: Optional[str] = None):
        super().__init__()
        self.model = model or "ollama/llama2"
        self.namespace = namespace or "default"
        self.messages: List[Dict] = []
        self.recalled_memories: List[Dict] = []
        self.contradictions: List[Dict] = []
        self.available_models: List[Dict] = []
        self.server_running = False
        self.llm_configured = False

    async def on_mount(self) -> None:
        """Initialize the app."""
        self.title = "Memory Thread Chat"
        await self.check_server()
        if self.server_running:
            await self.load_models()
            await self.load_namespace()
            await self.show_welcome()

    async def check_server(self) -> None:
        """Check if MT server is running."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/health", timeout=3)
                self.server_running = resp.status_code == 200
        except Exception:
            self.server_running = False

    async def load_models(self) -> None:
        """Load available models."""
        self.available_models = [{"name": "ollama/llama2", "provider": "ollama"}]

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    for model in data.get("models", []):
                        self.available_models.append(
                            {"name": f"ollama/{model['name']}", "provider": "ollama"}
                        )
        except Exception:
            pass

        groq_key = self.getenv("GROQ_API_KEY")
        if groq_key:
            self.llm_configured = True
            self.available_models.extend(
                [
                    {"name": "groq/llama-3.3-70b", "provider": "groq"},
                    {"name": "groq/mixtral-8x7b", "provider": "groq"},
                ]
            )

    async def load_namespace(self) -> None:
        """Load namespace from config."""
        ns = self.getenv("MT_NAMESPACE")
        if ns:
            self.namespace = ns

        config_path = Path(".mt") / "config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    self.namespace = config.get("namespace", "default")
            except Exception:
                pass

        for parent in Path(".").parents:
            config_path = parent / ".mt" / "config.json"
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        self.namespace = config.get("namespace", "default")
                        break
                except Exception:
                    pass

    def getenv(self, key: str) -> Optional[str]:
        """Get environment variable."""
        import os

        return os.environ.get(key)

    async def show_welcome(self) -> None:
        """Show welcome message with memory count."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{API_BASE}/stats?namespace={self.namespace}")
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("total_memories", 0)
                    self.messages.append(
                        {
                            "role": "system",
                            "content": f"Welcome! I have {count} memories about your project.",
                            "sources": 0,
                        }
                    )
        except Exception:
            self.messages.append(
                {
                    "role": "system",
                    "content": "Welcome! I have 0 memories about your project.",
                    "sources": 0,
                }
            )
        self.refresh_messages()

    def compose(self) -> ComposeResult:
        if not self.server_running:
            yield Static("⚠ MT Server not running - run 'mt serve' first", id="error-banner")

        with Horizontal(id="main-container"):
            with Vertical(id="chat-panel"):
                yield ScrollableContainer(id="chat-messages")
                yield Static("MT is thinking...", id="typing-indicator")
                with Horizontal(id="input-container"):
                    yield Input(placeholder="Type a message...", id="message-input")

            with Vertical(id="sidebar-panel"):
                yield Static("RECALLED", classes="sidebar-section")
                yield ScrollableContainer(id="recalled-list")
                yield Static("FLAGGED", classes="sidebar-section")
                yield ScrollableContainer(id="flagged-list")
                yield Static("MODEL", classes="sidebar-section")
                yield Label(f"Current: {self.model}", id="model-info")
                yield Label(f"Namespace: {self.namespace}", id="namespace-info")
                yield Label("[M] Change Model | [N] Change NS", id="model-hint")

    def on_mount(self) -> None:
        """Set up after mounting."""
        self.refresh_messages()

    def refresh_messages(self) -> None:
        """Refresh the message display."""
        container = self.query_one("#chat-messages", ScrollableContainer)
        container.remove_children()
        for msg in self.messages:
            container.mount(Message(msg["role"], msg["content"], msg.get("sources", 0)))

    def refresh_sidebar(self) -> None:
        """Refresh the sidebar."""
        recalled = self.query_one("#recalled-list", ScrollableContainer)
        recalled.remove_children()

        for mem in self.recalled_memories[:10]:
            content = (mem.get("content", "") or "")[:50]
            trust = mem.get("trust_score", 0)
            is_stale = False

            css_class = (
                "trust-high" if trust > 0.7 else "trust-medium" if trust > 0.4 else "trust-low"
            )
            prefix = "~" if is_stale else ""

            recalled.mount(
                Static(
                    f"{prefix}{content}... [{trust:.2f}]",
                    classes=f"memory-item {css_class}",
                )
            )

        flagged = self.query_one("#flagged-list", ScrollableContainer)
        flagged.remove_children()

        for flag in self.contradictions[:5]:
            flagged.mount(
                Static(
                    f"⚠ {flag.get('description', 'Contradiction')[:50]}",
                    classes="flag-item",
                )
            )

    @work(exclusive=True)
    async def action_send_message(self) -> None:
        """Send a message."""
        if not self.server_running:
            return

        input_widget = self.query_one("#message-input", Input)
        message = input_widget.value.strip()
        if not message:
            return

        input_widget.value = ""

        self.messages.append({"role": "user", "content": message, "sources": 0})
        self.refresh_messages()

        self.query_one("#typing-indicator").set_class(True, "typing")

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{API_BASE}/memory/remember",
                    json={
                        "content": message,
                        "source": "user",
                        "namespace": self.namespace,
                    },
                    timeout=10,
                )

                resp = await client.post(
                    f"{API_BASE}/memory/recall",
                    json={
                        "query": message,
                        "top_k": 5,
                        "namespace": self.namespace,
                    },
                    timeout=10,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    self.recalled_memories = data.get("memories", [])

                    context = "\n".join(m.get("content", "") for m in self.recalled_memories)

                    chat_resp = await client.post(
                        f"{API_BASE}/chat",
                        json={
                            "message": message,
                            "context": context,
                            "provider": "groq",
                            "model": "llama-3.3-70b-versatile",
                        },
                        timeout=30,
                    )

                    if chat_resp.status_code == 200:
                        response = chat_resp.json()
                        mt_message = response.get("response", "I don't have a response.")

                        self.messages.append(
                            {
                                "role": "mt",
                                "content": mt_message,
                                "sources": len(self.recalled_memories),
                            }
                        )

                        await client.post(
                            f"{API_BASE}/memory/remember",
                            json={
                                "content": mt_message,
                                "source": "agent",
                                "namespace": self.namespace,
                            },
                            timeout=10,
                        )
                    else:
                        self.messages.append(
                            {
                                "role": "system",
                                "content": "Failed to get response from LLM",
                                "sources": 0,
                            }
                        )

        except Exception as e:
            self.messages.append({"role": "system", "content": f"Error: {str(e)}", "sources": 0})

        self.query_one("#typing-indicator").set_class(False, "typing")
        self.refresh_messages()
        self.refresh_sidebar()

    def action_newline(self) -> None:
        """Insert newline in input."""
        input_widget = self.query_one("#message-input", Input)
        input_widget.value += "\n"

    async def action_open_model_picker(self) -> None:
        """Open model picker."""
        modal = ModelPickerModal(self.available_models, self.model)
        result = await self.push_screen_wait(modal)
        if result:
            self.model = result
            self.query_one("#model-info", Label).update(f"Current: {self.model}")

    async def action_open_namespace_picker(self) -> None:
        """Open namespace picker."""
        namespaces = ["default", self.namespace]
        if self.namespace not in namespaces:
            namespaces.append(self.namespace)

        modal = NamespacePickerModal(namespaces, self.namespace)
        result = await self.push_screen_wait(modal)
        if result:
            self.namespace = result
            self.query_one("#namespace-info", Label).update(f"Namespace: {self.namespace}")

    def action_clear_chat(self) -> None:
        """Clear chat display."""
        self.messages = []
        self.recalled_memories = []
        self.contradictions = []
        self.refresh_messages()
        self.refresh_sidebar()

    def action_scroll_up(self) -> None:
        """Scroll chat up."""
        self.query_one("#chat-messages", ScrollableContainer).scroll_up()

    def action_scroll_down(self) -> None:
        """Scroll chat down."""
        self.query_one("#chat-messages", ScrollableContainer).scroll_down()


def run(model: Optional[str] = None, namespace: Optional[str] = None):
    """Run the Chat TUI."""
    app = MemoryChat(model=model, namespace=namespace)
    app.run()


if __name__ == "__main__":
    run()
