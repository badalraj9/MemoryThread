"""
MT CLI Bridge - The "OpenCode" style Interface for Memory Thread.

ARCHITECTURE:
- Bridge: Manages state (Scope, Depth, Provider) that SDK doesn't know about.
- SDK: Dumb storage engine. Bridge tells it what to do.
- UI: TUI layer mocking OpenCode aesthetics.
"""
import sys
import os
import time
import glob
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- LOGGING & WARNING SUPPRESSION ---
import logging
import warnings

# 1. Global Logging Configuration
logging.basicConfig(
    filename='mt.log',
    level=logging.ERROR,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    filemode='w'
)

# 2. Monkeypatch MT's internal logger to prevent it from resetting to INFO
# This is required because utils.logger.get_logger() hardcodes level to INFO
try:
    import memory_thread.utils.logger
    def quiet_get_logger(name):
        logger = logging.getLogger(name)
        logger.setLevel(logging.ERROR)
        logger.propagate = False
        return logger
    memory_thread.utils.logger.get_logger = quiet_get_logger
except ImportError:
    pass

# 3. Silence 3rd party libraries
for lib in ["urllib3", "transformers", "httpx", "httpcore", "apscheduler", "tzlocal"]:
    logging.getLogger(lib).setLevel(logging.ERROR)
    logging.getLogger(lib).propagate = False

# 4. Suppress Warnings
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.prompt import Prompt
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.align import Align
    from rich.tree import Tree
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# --- ASSETS ---
LOGO_LINES = [
    r" __  __                                      _____ _                        _ ",
    r"|  \/  | ___ _ __ ___   ___  _ __ _   _     |_   _| |__  _ __ ___  __ _  __| |",
    r"| |\/| |/ _ \ '_ ` _ \ / _ \| '__| | | |______| | | '_ \| '__/ _ \/ _` |/ _` |",
    r"| |  | |  __/ | | | | | (_) | |  | |_| |______| | | | | | | |  __/ (_| | (_| |",
    r"|_|  |_|\___|_| |_| |_|\___/|_|   \__, |      |_| |_| |_|_|  \___|\__,_|\__,_|",
    r"                                  |___/                                       ",
]

# --- BRIDGE LOGIC (The Brains) ---

class ModelManager:
    """Manages Local and Cloud Models."""
    def __init__(self):
        self.providers = {
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "meta-llama/llama-3.1-405b-instruct",
            "local": "smollm:135m"
        }

    def get_model_id(self, provider: str) -> str:
        return self.providers.get(provider, "local")

class ConversationManager:
    """
    Manages short-term conversation history (Contextuality).
    Implements a PERSISTENT sliding window buffer effectively acting as a 'Working Memory'.
    Saves state to ~/.mt/history.json to survive restarts.
    """
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.history: List[Dict[str, Any]] = []
        self.storage_path = Path.home() / ".mt" / "history.json"
        self._ensure_storage()
        self.load()

    def _ensure_storage(self):
        if not self.storage_path.parent.exists():
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self):
        if self.storage_path.exists():
            try:
                import json
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as e:
                # If corrupt, start fresh
                self.history = []

    def save(self):
        try:
            import json
            # Atomic write to prevent corruption
            tmp_path = self.storage_path.with_suffix(".tmp")
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2)
            os.replace(tmp_path, self.storage_path)
        except:
            pass

    def add_turn(self, role: str, content: str):
        priority = self._calculate_priority(content)
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "priority": priority
        })

        if len(self.history) > self.max_turns * 2:
            self._smart_prune()

        self.save()

    def _calculate_priority(self, content: str) -> int:
        """Simple heuristic for TUI context retention."""
        score = 1 # Default
        lower_content = content.lower()

        # High Priority Keywords (Instructions, Facts, Config)
        high_keywords = ["remember", "always", "config", "key", "api", "set", "use", "important", "never"]
        if any(w in lower_content for w in high_keywords):
            score += 2

        # Length Heuristic (Longer messages usually contain more info)
        if len(content) > 50: score += 1

        # Low Priority (Ack, short output)
        if len(content) < 10 and "ok" in lower_content: score -= 1

        return max(1, score)

    def _smart_prune(self):
        """Removes low priority items first, preserving important context."""
        # separate into priority buckets
        scored_items = []
        for i, item in enumerate(self.history):
            # Recency bias: Last 4 messages are always kept regardless of priority
            if i >= len(self.history) - 4:
                priority = 99
            else:
                priority = item.get("priority", 1)
            scored_items.append((priority, i))

        # Sort by priority (lowest first), then by index (oldest first)
        scored_items.sort(key=lambda x: (x[0], x[1]))

        # Remove the items with lowest effective priority
        # We need to remove (len - limit) items
        to_remove_count = len(self.history) - (self.max_turns * 2)
        if to_remove_count > 0:
            indices_to_remove = set(x[1] for x in scored_items[:to_remove_count])

            # Rebuild history
            new_history = [item for i, item in enumerate(self.history) if i not in indices_to_remove]
            self.history = new_history

    def clear(self):
        # Guardrail: Don't just delete, archive it first.
        self.archive()
        self.history = []
        self.save()

    def archive(self):
        """Moves current history to an archive file so nothing is ever truly lost."""
        if not self.history: return

        try:
            timestamp = int(time.time())
            archive_path = self.storage_path.parent / f"history_{timestamp}.json"
            import json
            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2)
        except:
            pass

    def get_context_block(self) -> str:
        if not self.history:
            return ""

        block = "\nIMMEDIATE CONVERSATION HISTORY (Working Memory):\n"
        for msg in self.history:
            role = msg['role'].upper()
            content = msg['content']
            if len(content) > 1000: content = content[:1000] + "...(truncated)"
            block += f"[{role}]: {content}\n"
        block += "\n--- End of Working Memory ---\n"
        return block

class AgentManager:
    """Defines Agent Roles."""
    AGENTS = {
        "coder": {
            "role": "Senior Software Engineer",
            "namespace": "project",
            "prompt": "You are a Coder. Focus on code quality, testing, and implementation details."
        },
        "architect": {
            "role": "System Architect",
            "namespace": "global",
            "prompt": "You are an Architect. precise, high-level, focus on patterns and scalability."
        },
        "reviewer": {
            "role": "Code Reviewer",
            "namespace": "project",
            "prompt": "You are a Reviewer. Be critical, look for bugs, security issues, and style violations."
        }
    }

class BridgeState:
    """
    Manages state that lives ONLY in the CLI.
    """
    def __init__(self):
        self.agent = "coder"
        self.provider = self._detect_provider()
        self.variant = "surface" # surface | deep

        # Short-term memory buffer
        self.conversation = ConversationManager()

        # We re-init SDK when agent changes (namespace switch)
        from memory_thread.sdk import MemoryClient
        from memory_thread.utils.secure_sdk import SecureMemoryClient

        self._sdk_class = MemoryClient
        self._secure_class = SecureMemoryClient

        # Security State
        self.secure_mode = False
        self.smart_mode = False # Layer VI toggle
        self.current_user_role = "employee" # Default role
        self.client = self._init_client()

    def _detect_provider(self) -> str:
        if os.environ.get("GROQ_API_KEY") and "your_" not in os.environ.get("GROQ_API_KEY"):
            return "groq"
        if os.environ.get("OPENROUTER_API_KEY") and "your_" not in os.environ.get("OPENROUTER_API_KEY"):
            return "openrouter"
        return "local"

    def _init_client(self):
        """Initialize SDK based on current AGENT's namespace or Security Context."""
        if self.secure_mode:
            # Use Enterprise Secure Wrapper
            # We use a fixed user ID for demo purposes
            return self._secure_class(user_id="demo-user", role=self.current_user_role)
        else:
            # Standard Mode
            agent_cfg = AgentManager.AGENTS.get(self.agent, AgentManager.AGENTS["coder"])
            ns = agent_cfg["namespace"]
            return self._sdk_class(namespace=ns, use_db=False)

    def set_agent(self, name: str):
        if name in AgentManager.AGENTS:
            self.agent = name
            if not self.secure_mode:
                self.client = self._init_client()
            return True
        return False

    def toggle_security(self):
        self.secure_mode = not self.secure_mode
        self.client = self._init_client()
        return self.secure_mode

    def toggle_smart(self):
        self.smart_mode = not self.smart_mode
        return self.smart_mode

    def set_role(self, role: str):
        # Validate role exists in our policy
        valid_roles = ["guest", "employee", "developer", "researcher", "executive", "root"]
        if role.lower() in valid_roles:
            self.current_user_role = role.lower()
            if self.secure_mode:
                self.client = self._init_client()
            return True
        return False

    def view_audit(self):
        """View Audit Logs (Root only)."""
        if not self.secure_mode or not hasattr(self.client, 'audit_log'):
             return "Audit logs only available in Secure Mode."

        logs = self.client.audit_log(limit=20)
        if not logs:
            return "No audit logs found or Access Denied."

        output = "[bold underline]OPERATIONAL AUDIT LEDGER[/]\n"
        for entry in logs:
            ts = entry.get('timestamp', '')[:19]
            actor = entry.get('actor', {}).get('role', 'unknown').upper()
            action = entry.get('type', 'UNKNOWN')
            target = entry.get('target', '')

            color = "red" if "DENIED" in action else "green"
            output += f"[{color}]{ts} | {actor} | {action} | {target}[/]\n"

        return output

    def handle_grant(self, args: str):
        if not self.secure_mode: return "Enable Secure Mode first (/secure)"
        parts = args.split()
        if len(parts) < 3: return "Usage: /grant <role> <domain> <score>"
        try:
            score = float(parts[2])
            if self.client.grant(parts[0], parts[1], score):
                return f"[green]Granted {score} authority to {parts[0]} on {parts[1]}[/]"
            else:
                return "[red]Grant Denied (Check Audit Log)[/]"
        except Exception as e: return f"[red]Error: {e}[/]"

    def handle_revoke(self, args: str):
        if not self.secure_mode: return "Enable Secure Mode first (/secure)"
        parts = args.split()
        if len(parts) < 2: return "Usage: /revoke <role> <domain>"
        try:
            if self.client.revoke(parts[0], parts[1]):
                return f"[yellow]Revoked authority from {parts[0]} on {parts[1]}[/]"
            else:
                return "[red]Revoke Denied (Check Audit Log)[/]"
        except Exception as e: return f"[red]Error: {e}[/]"

    def set_variant(self, variant: str):
        if variant in ["surface", "deep"]:
            self.variant = variant
            return True
        return False

    def chat(self, user_input: str) -> str:
        """
        Intelligent Chat Bridge.
        1. Inject Agent Persona
        2. Inject Context (File/Memory)
        3. Inject Conversation History (Short-term)
        4. Call MT
        """
        # 1. Update Short-term History
        self.conversation.add_turn("user", user_input)

        # Context Injection (@file)
        context_buffer = ""
        words = user_input.split()
        clean_input = []
        for w in words:
            if w.startswith("@") and os.path.exists(w[1:]):
                try:
                    with open(w[1:], 'r') as f:
                        context_buffer += f"\n--- File: {w[1:]} ---\n{f.read(2000)}\n"
                except:
                    pass
            else:
                clean_input.append(w)

        final_query = " ".join(clean_input)

        # Agent Persona Injection
        agent_cfg = AgentManager.AGENTS[self.agent]
        sys_prompt = f"Role: {agent_cfg['role']}\n{agent_cfg['prompt']}\n"

        # Add File Context
        if context_buffer:
            sys_prompt += f"\nLOCAL FILE CONTEXT:\n{context_buffer}\n"

        # Add Conversation History (The "Contextuality" Fix)
        history_block = self.conversation.get_context_block()
        if history_block:
            sys_prompt += f"\n{history_block}\n"

        # Variant Logic (Depth)
        top_k = 10 if self.variant == "deep" else 3
        # Note: top_k isn't directly passed to chat() in current SDK,
        # but the SDK's chat method does its own recall.
        # Ideally we'd modify SDK to accept top_k, but we can't touch it.
        # The bridge handles the prompt construction.

        # We prepend system prompt to the query for now as SDK handles raw chat
        # Ideally SDK would accept system_prompt arg, but bridge can wrapper it.
        # Wait, SDK.chat DOES accept system_prompt.
        # def chat(self, user_message: str, system_prompt: Optional[str] = None, use_local: bool = True) -> str:

        # Check if client supports smart_loop (SecureClient does, Base might not)
        kwargs = {}
        if hasattr(self.client, 'chat') and 'smart_loop' in self.client.chat.__code__.co_varnames:
             kwargs['smart_loop'] = self.smart_mode

        response = self.client.chat(
            user_message=final_query,
            system_prompt=sys_prompt,
            use_local=(self.provider=="local"),
            **kwargs
        )

        # Record Response
        self.conversation.add_turn("assistant", response)

        return response

    def get_graph_insight(self, query: str) -> Any:
        """Fetch graph relations for the query context."""
        # Fix: SDK doesn't have a public 'graph' attribute check.
        # We rely on get_related returning data.

        # 1. Find relevant nodes
        results = self.client.recall(query, top_k=2)
        if not results.memories: return None

        insight_tree = None
        if RICH_AVAILABLE:
            insight_tree = Tree("Knowledge Graph")
        else:
            insight_text = ""

        seen_edges = set()
        has_relations = False

        for mem in results.memories:
            # 2. Get connections for this memory's entity
            # Fix: Use self.client.get_related() instead of non-existent get_related_entities()
            related = self.client.get_related(mem.entity_id)
            if not related: continue

            has_relations = True

            label = f"[bold]{mem.content[:50]}...[/]"
            if RICH_AVAILABLE:
                node = insight_tree.add(label)
            else:
                insight_text += f"{label}\n"

            for r in related:
                # relation structure from graph_service:
                # {'id': ..., 'source_entity_id': ..., 'target_entity_id': ..., 'relation_type': ...}
                # Wait, SDK.get_related calls GraphService.get_relations which returns raw rows (dicts).
                # We need to resolve target name if possible, or just show ID.
                # SDK.infer_user_relations logic stores "target" in memory content usually.
                # But here we are getting raw DB relations.

                target = str(r.get('target_entity_id'))
                # Try to resolve target name if it's in our memory cache
                if hasattr(self.client, '_memories') and uuid.UUID(target) in self.client._memories:
                     target_state = self.client._memories[uuid.UUID(target)]
                     target_content = target_state.current_value.get('content', target)
                     target = target_content[:30]

                relation_type = r.get('relation_type', 'RELATED')

                edge_sig = (mem.entity_id, target, relation_type)
                if edge_sig in seen_edges: continue
                seen_edges.add(edge_sig)

                # Format: └─ [WORKS_AT] -> Google
                if RICH_AVAILABLE:
                    node.add(f"[{relation_type}] -> {target}")
                else:
                    insight_text += f"  └─ [{relation_type}] -> {target}\n"

        if not has_relations:
            return None

        if RICH_AVAILABLE:
            return insight_tree
        else:
            return insight_text

    def ingest_project(self) -> int:
        count = 0
        allowed = ['.py', '.md', '.txt', '.json', '.js', '.ts', '.html', '.css', '.rs', '.go']
        ignored_dirs = ['node_modules', '.git', 'venv', '__pycache__', 'dist', 'build', '.idea', '.vscode']

        for root, dirs, files in os.walk("."):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignored_dirs]

            for file in files:
                if os.path.splitext(file)[1] in allowed:
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read(2000)
                            if content.strip():
                                self.client.remember(f"File {path}:\n{content}", source="ingest")
                                count += 1
                    except Exception:
                        # Ignore encoding errors or permission issues
                        pass
        return count


# --- UI LAYER ---
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import NestedCompleter
    from prompt_toolkit.styles import Style as PStyle
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.filters import Condition
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

class MTInterface:
    BG = "#0f0f0f"
    DIM = "#525252"

    def __init__(self):
        self.console = Console(highlight=False, soft_wrap=True) if RICH_AVAILABLE else None
        self.graph_mode = False # F3 to toggle
        try: from dotenv import load_dotenv; load_dotenv()
        except: pass

        self.bridge = BridgeState()

        # OpenCode Command Structure
        self.completer = None
        if PROMPT_TOOLKIT_AVAILABLE:
            self.completer = NestedCompleter.from_nested_dict({
                '/agents': {'coder': None, 'architect': None, 'reviewer': None},
                '/variants': {'surface': None, 'deep': None},
                '/conf': {'groq': None, 'openrouter': None, 'local': None},
                '/login': {
                    'guest': None, 'employee': None, 'developer': None,
                    'researcher': None, 'executive': None, 'root': None
                },
                '/secure': None,
                '/audit': None,
                '/grant': None, '/revoke': None,
                '/smart': None,
                '/ingest': None, '/clear': None, '/quit': None, '/help': None,
            })

        self.p_style = None
        if PROMPT_TOOLKIT_AVAILABLE:
            self.p_style = PStyle.from_dict({
                'prompt': '#3B82F6 bold',
                'input': '#EEEEEE',
                'completion-menu': 'bg:#1e1e1e #eeeeee',
                'completion-menu.completion.current': 'bg:#3B82F6 #ffffff',
                'bottom-toolbar': 'bg:default #666666',
                'bottom-toolbar.key': '#ffffff bold',
                'bottom-toolbar.val': '#ffffff',
                'bottom-toolbar.sep': '#3B82F6',
                'bottom-toolbar.on': '#55ff55 bold',
                'bottom-toolbar.off': '#999999',
            })

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_logo(self):
        if not self.console:
            print("Memory Thread v1.0")
            return
        self.console.print()
        # Cyber/Neural Style Gradient
        for i, line in enumerate(LOGO_LINES):
            # Fade from Cyan to Purple
            if i < 2: style = "bold cyan"
            elif i < 4: style = "bold blue"
            else: style = "bold purple"

            self.console.print(Align.center(line, style=style))
        self.console.print()
        self.console.print(Align.center("[dim]Memory Thread v1.0 • Neural CLI[/]"))
        self.console.print()

    def get_bottom_toolbar(self):
        # OpenCode Style Footer
        ag = self.bridge.agent.capitalize()
        pr = self.bridge.provider
        var = self.bridge.variant
        graph = "ON" if self.graph_mode else "OFF"
        g_style = "class:bottom-toolbar.on" if self.graph_mode else "class:bottom-toolbar.off"

        # Security Status
        sec_status = ""
        if self.bridge.secure_mode:
            role = self.bridge.current_user_role.upper()
            sec_status = f" · [SECURE: {role}]"

        # Smart Status
        smart_status = ""
        if self.bridge.smart_mode:
            smart_status = " · [SMART: ON]"

        return [
            ('class:bottom-toolbar.key', ' Agent '), ('class:bottom-toolbar.val', f'{ag} '),
            ('class:bottom-toolbar.key', ' Model '), ('class:bottom-toolbar.val', f'{pr} '),
            ('class:bottom-toolbar.sep', f' · {var}'),
            ('class:bottom-toolbar.sep', ' · Graph:'), (g_style, f' {graph} '),
            ('class:bottom-toolbar.on', sec_status),
            ('class:bottom-toolbar.on', smart_status),
            ('class:bottom-toolbar', '    '),
            ('class:bottom-toolbar', 'F3 Graph  ctrl+t variants  / help')
        ]

    def _handle_conf(self, provider):
        """Quick Switch Provider"""
        if provider in ["groq", "openrouter", "local"]:
            self.bridge.provider = provider
            self.console.print(f"[green]Switched model to {provider}[/]")
        else:
            self.console.print("[red]Unknown provider[/]")

    def run(self):
        self.clear_screen()
        self.print_logo()

        if not PROMPT_TOOLKIT_AVAILABLE:
            print("Error: 'prompt_toolkit' is not installed. Please run 'pip install prompt_toolkit'.")
            return
        if not RICH_AVAILABLE:
             print("Warning: 'rich' is not installed. UI will be degraded. Please run 'pip install rich'.")

        # --- Key Bindings ---
        bindings = KeyBindings()

        @bindings.add('f3')
        def _(event):
            self.graph_mode = not self.graph_mode
            # Force refresh of toolbar
            # app.invalidate() is hard to reach here without reference to app,
            # but next render will pick it up.

        @bindings.add('enter') # Enter submits
        def _(event):
             event.current_buffer.validate_and_handle()

        @bindings.add('escape', 'enter') # Alt+Enter for newline
        def _(event):
            event.current_buffer.insert_text('\n')

        @bindings.add('c-t') # Ctrl+T to toggle variant
        def _(event):
            new_var = "deep" if self.bridge.variant == "surface" else "surface"
            self.bridge.set_variant(new_var)

        session = PromptSession(
            completer=self.completer,
            style=self.p_style,
            multiline=True,
            key_bindings=bindings
        )

        while True:
            try:
                self.console.print()
                user_input = session.prompt([('class:prompt', '▌ ')], bottom_toolbar=self.get_bottom_toolbar)

                if not user_input.strip(): continue
                user_input = user_input.strip()

                if user_input.startswith("/"):
                    parts = user_input.split()
                    cmd = parts[0].lower()
                    arg = parts[1] if len(parts) > 1 else ""

                    if cmd == "/quit": break
                    elif cmd == "/agents":
                        if self.bridge.set_agent(arg): self.console.print(f"[green]Agent: {arg}[/]")
                        else: self.console.print("[red]Use: /agents <coder|architect|reviewer>[/]")
                    elif cmd == "/variants":
                        if self.bridge.set_variant(arg): self.console.print(f"[green]Variant: {arg}[/]")
                        else: self.console.print("[red]Use: /variants <surface|deep>[/]")
                    elif cmd == "/conf": self._handle_conf(arg)
                    elif cmd == "/login":
                        if self.bridge.set_role(arg):
                            self.console.print(f"[green]Logged in as: {arg.upper()}[/]")
                            if not self.bridge.secure_mode:
                                self.console.print("[dim]Note: Security mode is OFF. Type /secure to enable.[/]")
                        else: self.console.print("[red]Unknown role. Use: guest, employee, developer, researcher, executive, root[/]")
                    elif cmd == "/secure":
                        state = self.bridge.toggle_security()
                        status = "ENABLED" if state else "DISABLED"
                        color = "green" if state else "red"
                        self.console.print(f"[{color}]Enterprise Security: {status}[/]")
                    elif cmd == "/smart":
                        state = self.bridge.toggle_smart()
                        status = "ENABLED" if state else "DISABLED"
                        self.console.print(f"[cyan]Smart Reflection Loop: {status}[/]")
                    elif cmd == "/audit":
                        log_view = self.bridge.view_audit()
                        self.console.print(Panel(log_view, title="Audit Log", border_style="red"))
                    elif cmd == "/grant":
                        self.console.print(self.bridge.handle_grant(arg))
                    elif cmd == "/revoke":
                        self.console.print(self.bridge.handle_revoke(arg))
                    elif cmd == "/ingest":
                         with Live(Spinner("dots", text="Scanning..."), transient=True):
                             c = self.bridge.ingest_project()
                         self.console.print(f"[green]Ingested {c} files[/]")
                    elif cmd == "/clear":
                        self.bridge.client.clear()
                        self.console.print("[green]Cleared memory[/]")
                    elif cmd == "/help":
                        self.console.print("[dim]/agents, /variants, /conf, /login, /secure, /smart, /grant, /revoke, /audit, /ingest, /clear, /quit[/]")
                    else: self.console.print(f"[red]Unknown: {cmd}[/]")
                    continue

                # --- CHAT ---
                with Live(Spinner("dots", style=self.DIM), transient=True, refresh_per_second=10):
                    # We can't easily get the 'recall_result' from chat() directly without refactoring SDK return types.
                    # For Layer V Lite, we will do a manual recall in the bridge to show sources,
                    # mirroring what the chat loop sees.

                    # 1. Get Sources first
                    sources_view = None
                    if self.bridge.secure_mode:
                         # Use top_k=5 matching SecureClient default
                         res = self.bridge.client.recall(user_input, top_k=5)
                         if res.memories:
                             s_text = "[bold]Evidence:[/]\n"
                             for i, m in enumerate(res.memories, 1):
                                 src_label = getattr(m, 'source', 'unknown')
                                 s_text += f"{i}. {m.content[:60]}... [dim]({src_label})[/]\n"
                             sources_view = Panel(s_text, title="Reasoning Sources", border_style="blue")

                    # 2. Get Response
                    response = self.bridge.chat(user_input)

                    # 3. Graph Insight
                    graph_insight = None
                    if self.graph_mode:
                         graph_insight = self.bridge.get_graph_insight(user_input)

                if sources_view:
                    self.console.print(sources_view)

                if graph_insight:
                    title = "Knowledge Graph"
                    if RICH_AVAILABLE:
                         self.console.print(Panel(graph_insight, title=title, border_style="yellow", padding=(0, 1)))
                    else:
                         print(f"--- {title} ---\n{graph_insight}")

                self.console.print()
                self.console.print(response)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Bye[/]")
                break
            except EOFError:
                break
            except Exception as e:
                self.console.print(f"[red]Err: {e}[/]")

if __name__ == "__main__":
    if not RICH_AVAILABLE:
        print("Install rich: pip install rich")
    if not PROMPT_TOOLKIT_AVAILABLE:
        print("Install prompt_toolkit: pip install prompt_toolkit")

    try:
        MTInterface().run()
    except KeyboardInterrupt:
        pass
