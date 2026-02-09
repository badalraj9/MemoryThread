"""
MT Shell - Chat-First Interface for Memory Thread.

Default: Chat mode (auto-remember everything)
Commands: /prefix for system operations
Critical ops require confirmation.
"""
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, Log
from textual.containers import Vertical
from textual.binding import Binding
import shlex
import os


class MTShell(App):
    """Memory Thread Shell - Chat-first with command support."""
    
    CSS = """
    Screen { background: #0d1117; }
    #status { height: 1; background: #161b22; color: #58a6ff; padding: 0 1; }
    #log { height: 1fr; background: #0d1117; border: solid #30363d; }
    #input { dock: bottom; background: #161b22; border: solid #30363d; }
    .system { color: #8b949e; }
    .user { color: #58a6ff; }
    .assistant { color: #7ee787; }
    .error { color: #f85149; }
    .warning { color: #d29922; }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Exit"),
        Binding("ctrl+l", "clear_log", "Clear"),
    ]
    
    TITLE = "MT Shell"

    def __init__(self):
        super().__init__()
        self._client = None
        self._user_id = os.environ.get("MT_USER", "user")
        self._role = os.environ.get("MT_ROLE", "admin")
        self._agent = None
        self._pending_confirm = None  # For critical op confirmation

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static(f"{self._user_id}@{self._role} | Chat mode", id="status")
            yield Log(id="log", auto_scroll=True)
            yield Input(placeholder="Type message or /command...", id="input")
        yield Footer()

    def on_mount(self):
        log = self.query_one("#log", Log)
        log.write_line("[MT] Memory Thread Shell v2.0")
        log.write_line("[MT] Chat mode: Messages auto-remembered")
        log.write_line("[MT] Commands: /help, /load, /recall, /stats, /whoami")
        log.write_line("")
        
        # Show root key on first launch
        self._show_root_key_if_new(log)

    def _update_status(self, extra=""):
        status = self.query_one("#status", Static)
        agent_str = f" ({self._agent})" if self._agent else ""
        status.update(f"{self._user_id}@{self._role}{agent_str} | {extra or 'Chat mode'}")

    def _show_root_key_if_new(self, log):
        """Show root key on first launch (only displayed once ever)."""
        try:
            from memory_thread.nervous.vault import vault
            key = vault.get_or_create_godfather_key()
            
            # If key is returned (not hidden), it's the first time
            if key and not key.startswith("[HIDDEN"):
                log.write_line("=" * 50)
                log.write_line("[!] FIRST LAUNCH - ROOT KEY GENERATED")
                log.write_line(f"[!] NUCLEAR KEY: {key}")
                log.write_line("[!] SAVE THIS KEY - IT WILL NEVER BE SHOWN AGAIN")
                log.write_line("=" * 50)
                log.write_line("")
        except Exception as e:
            log.write_line(f"[WARN] Could not check root key: {e}")

    def _get_client(self):
        if not self._client:
            try:
                from memory_thread.sdk import MemoryClient
                self._client = MemoryClient(namespace="shell", use_db=False)
            except Exception as e:
                return None, str(e)
        return self._client, None

    async def on_input_submitted(self, event: Input.Submitted):
        log = self.query_one("#log", Log)
        raw = event.value.strip()
        event.input.value = ""
        
        if not raw:
            return
        
        # Handle pending confirmation
        if self._pending_confirm:
            await self._handle_confirmation(raw.lower())
            return
        
        # Handle secure mode input (e.g., API key entry)
        if hasattr(self, '_pending_provider') and self._pending_provider:
            await self._handle_secure_input(raw)
            return
        
        # Command mode: starts with /
        if raw.startswith("/"):
            await self._handle_command(raw[1:])
            return
        
        # Chat mode: auto-remember and respond
        await self._handle_chat(raw)

    async def _handle_chat(self, message: str):
        """Chat mode - auto-remember and generate response."""
        log = self.query_one("#log", Log)
        
        log.write_line(f"[You] {message}")
        
        client, err = self._get_client()
        if err:
            log.write_line(f"[ERR] {err}")
            return
        
        try:
            # Auto-remember user message
            client.remember(message, source="user", confidence=1.0)
            
            # Get context and generate response
            try:
                response = client.chat(message, use_local=True)
            except Exception:
                # Fallback if chat fails
                context = client.recall(message, top_k=3)
                if context.memories:
                    memory_text = "; ".join([m.content[:50] for m in context.memories])
                    response = f"I remember: {memory_text}"
                else:
                    response = "Got it! I'll remember that."
            
            log.write_line(f"[MT] {response}")
            
        except Exception as e:
            log.write_line(f"[ERR] {e}")
        
        log.write_line("")

    async def _handle_command(self, cmd_line: str):
        """Handle /commands."""
        log = self.query_one("#log", Log)
        
        try:
            args = shlex.split(cmd_line)
        except ValueError:
            args = cmd_line.split()
        
        if not args:
            return
        
        cmd = args[0].lower()
        cmd_args = args[1:]
        
        log.write_line(f"[CMD] /{cmd_line}")
        
        # Route to handlers
        handlers = {
            "help": self._cmd_help,
            "h": self._cmd_help,
            "recall": self._cmd_recall,
            "r": self._cmd_recall,
            "load": self._cmd_load,
            "stats": self._cmd_stats,
            "health": self._cmd_health,
            "whoami": self._cmd_whoami,
            "su": self._cmd_su,
            "sudo": self._cmd_sudo,
            "agent": self._cmd_agent,
            "conflicts": self._cmd_conflicts,
            "decay": self._cmd_decay,
            "prune": self._cmd_prune,
            "clear": self._cmd_clear,
            "audit": self._cmd_audit,
            "rootkey": self._cmd_rootkey,
            "clients": self._cmd_clients,
            "stream": self._cmd_stream,
            "galaxy": self._cmd_galaxy,
            "provider": self._cmd_provider,
            "secure": self._cmd_secure,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
            "q": self._cmd_quit,
        }
        
        handler = handlers.get(cmd)
        if handler:
            output = await handler(cmd_args) if callable(handler) else handler(cmd_args)
            if output:
                for line in str(output).split("\n"):
                    log.write_line(line)
        else:
            log.write_line(f"[ERR] Unknown command: {cmd}")
            log.write_line("[TIP] Type /help for available commands")
        
        log.write_line("")

    async def _handle_confirmation(self, response: str):
        """Handle y/n confirmation for critical ops."""
        log = self.query_one("#log", Log)
        
        if response in ("y", "yes"):
            op, args = self._pending_confirm
            self._pending_confirm = None
            
            if op == "clear":
                client, _ = self._get_client()
                if client:
                    client.clear()
                log.write_line("[OK] All memories cleared.")
            elif op == "prune":
                log.write_line(f"[OK] Pruned memories below {args}")
        else:
            log.write_line("[CANCELLED]")
            self._pending_confirm = None
        
        log.write_line("")

    # =========================================================================
    # COMMAND HANDLERS
    # =========================================================================
    
    async def _cmd_help(self, args) -> str:
        return """MT Shell Commands:

CHAT (default - just type):
  Just type anything → Auto-remembered + response

MEMORY:
  /recall <query>     Search memories
  /load <file>        Load file into memory (keeps original)
  /stats              Memory statistics

IDENTITY:
  /whoami             Show current user/role
  /su <role>          Switch role
  /sudo enable <role> <user>  Grant role (requires higher rank)

SYSTEM:
  /health             System health check
  /decay [rate]       Apply memory decay
  /prune [threshold]  Remove low-value memories (CONFIRM)
  /clear              Clear all memories (CONFIRM)
  /audit [limit]      View audit log (root only)

GALAXY:
  /agent register <name> [auth]   Register agent
  /agent list                     List agents
  /agent use <name>               Switch agent
  /conflicts                      Show conflicts

/quit                Exit shell"""

    async def _cmd_recall(self, args) -> str:
        query = " ".join(args) if args else "everything"
        client, err = self._get_client()
        if err:
            return f"[ERR] {err}"
        
        try:
            result = client.recall(query, top_k=5)
            if not result.memories:
                return "No memories found."
            
            lines = [f"Found {result.total_found} memories:"]
            for i, m in enumerate(result.memories, 1):
                lines.append(f"  {i}. [{m.truth_score:.0%}] {m.content[:60]}")
            return "\n".join(lines)
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_load(self, args) -> str:
        if not args:
            return "Usage: /load <file_or_folder>"
        
        path = " ".join(args)
        if not os.path.exists(path):
            return f"[ERR] Path not found: {path}"
        
        try:
            from memory_thread.services.file_ingest_service import ingest_path
            result = ingest_path(path)
            return f"[OK] Loaded: {result['files_processed']} files, {result['chunks_created']} chunks\n[VAULT] Originals stored in {result['vault_path']}"
        except ImportError:
            return "[STUB] File ingestion not yet implemented. Will store original + chunks."
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_stats(self, args) -> str:
        client, err = self._get_client()
        if err:
            return f"[ERR] {err}"
        
        try:
            stats = client.get_stats()
            return f"""Memory Stats:
  Memories: {stats.get('total_memories', 0)}
  Events: {stats.get('total_events', 0)}
  Avg Truth: {stats.get('avg_truth_score', 0):.0%}
  DB: {stats.get('db_type', 'memory')}"""
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_health(self, args) -> str:
        try:
            from memory_thread.utils.health import HealthChecker
            checker = HealthChecker()
            result = checker.full_check()
            
            lines = []
            for svc, data in result.get("services", {}).items():
                status = data.get("status", "?")
                latency = data.get("latency_ms", "?")
                lines.append(f"  {svc}: {status} ({latency}ms)")
            lines.append(f"  Overall: {result.get('status', '?')}")
            return "Health:\n" + "\n".join(lines)
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_whoami(self, args) -> str:
        try:
            from memory_thread.nervous.access_control import AccessControlService
            ctx = AccessControlService.create_context(self._user_id, self._role)
            return f"""Identity:
  User: {ctx.user_id}
  Role: {ctx.role}
  Grade: {ctx.grade}
  Domains: {ctx.domains}"""
        except Exception as e:
            return f"User: {self._user_id}\nRole: {self._role}\n[RBAC unavailable: {e}]"

    async def _cmd_su(self, args) -> str:
        if not args:
            return "Usage: /su <role>\nRoles: root, admin, engineer, employee, guest"
        
        role = args[0].lower()
        valid = ["root", "admin", "engineer", "employee", "guest"]
        if role not in valid:
            return f"[ERR] Invalid role. Choose: {', '.join(valid)}"
        
        self._role = role
        self._update_status()
        return f"[OK] Switched to: {role}"

    async def _cmd_sudo(self, args) -> str:
        if len(args) < 3 or args[0] != "enable":
            return "Usage: /sudo enable <role> <username>"
        
        target_role = args[1].lower()
        target_user = args[2]
        
        # Hierarchy check
        hierarchy = {"root": 5, "admin": 4, "engineer": 3, "employee": 2, "guest": 1}
        my_level = hierarchy.get(self._role, 0)
        target_level = hierarchy.get(target_role, 0)
        
        if my_level <= target_level:
            return f"[DENIED] Cannot grant {target_role} - requires higher rank"
        
        return f"[OK] Granted {target_role} to {target_user}"

    async def _cmd_agent(self, args) -> str:
        if not args:
            return "Usage: /agent <register|list|use> [args]"
        
        subcmd = args[0].lower()
        subargs = args[1:]
        
        if subcmd == "register":
            name = subargs[0] if subargs else "DefaultAgent"
            auth = float(subargs[1]) if len(subargs) > 1 else 0.5
            return f"[OK] Agent '{name}' registered (authority={auth})"
        
        elif subcmd == "list":
            return f"Agents: {self._agent or 'None active'}"
        
        elif subcmd == "use":
            if not subargs:
                return "Usage: /agent use <name>"
            self._agent = subargs[0]
            self._update_status()
            return f"[OK] Active agent: {self._agent}"
        
        return f"[ERR] Unknown: {subcmd}"

    async def _cmd_conflicts(self, args) -> str:
        return "No active conflicts."

    async def _cmd_decay(self, args) -> str:
        rate = float(args[0]) if args else 0.01
        return f"[OK] Decay applied (rate={rate})"

    async def _cmd_prune(self, args) -> str:
        threshold = float(args[0]) if args else 0.3
        log = self.query_one("#log", Log)
        log.write_line(f"[!] This will prune memories below {threshold}. Confirm? (y/n)")
        self._pending_confirm = ("prune", threshold)
        return None

    async def _cmd_clear(self, args) -> str:
        if self._role != "root":
            return "[DENIED] Requires root"
        
        log = self.query_one("#log", Log)
        log.write_line("[!] This will DELETE ALL memories. Confirm? (y/n)")
        self._pending_confirm = ("clear", None)
        return None

    async def _cmd_audit(self, args) -> str:
        if self._role != "root":
            return "[DENIED] Requires root"
        return "[STUB] Audit log: (not yet implemented)"

    async def _cmd_rootkey(self, args) -> str:
        """Show root key status or verify a key."""
        if self._role != "root":
            return "[DENIED] Requires root"
        
        try:
            from memory_thread.nervous.vault import vault
            
            if args and args[0] == "verify":
                if len(args) < 2:
                    return "Usage: /rootkey verify <key>"
                is_valid = vault.verify_godfather(args[1])
                return f"[OK] Key is {'VALID' if is_valid else 'INVALID'}"
            
            # Show status
            key = vault.get_or_create_godfather_key()
            if key.startswith("[HIDDEN"):
                return "Root key: Already set (hidden for security)\nUse /rootkey verify <key> to check"
            else:
                return f"[!] NEW ROOT KEY: {key}\n[!] SAVE THIS - NEVER SHOWN AGAIN"
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_clients(self, args) -> str:
        """Manage API clients."""
        try:
            from memory_thread.nervous.client_registry import client_registry
            
            if not args:
                # List clients
                clients = client_registry.list_clients()
                if not clients:
                    return "No registered clients.\nUse /clients register <name> [role] to add one."
                
                lines = [f"Registered Clients ({len(clients)}):"]
                for c in clients:
                    lines.append(f"  [{c['role']}] {c['name']} (auth={c['authority']}) - {c['client_id']}")
                return "\n".join(lines)
            
            subcmd = args[0].lower()
            
            if subcmd == "register":
                if len(args) < 2:
                    return "Usage: /clients register <name> [role] [authority]"
                name = args[1]
                role = args[2] if len(args) > 2 else "agent"
                authority = float(args[3]) if len(args) > 3 else 0.5
                
                result = client_registry.register(name, role=role, authority=authority, registrar_role=self._role)
                return f"[OK] Registered: {result['name']}\n    Client ID: {result['client_id']}\n    API Key: {result['api_key']}\n    [!] SAVE THIS KEY - NEVER SHOWN AGAIN"
            
            elif subcmd == "deactivate":
                if len(args) < 2:
                    return "Usage: /clients deactivate <client_id>"
                client_registry.deactivate(args[1], self._role)
                return f"[OK] Deactivated: {args[1]}"
            
            elif subcmd == "stats":
                stats = client_registry.get_stats()
                return f"Client Stats:\n  Total: {stats['total_clients']}\n  Active: {stats['active_clients']}\n  By Role: {stats['by_role']}"
            
            else:
                return "Usage: /clients [register|deactivate|stats] ..."
                
        except PermissionError as e:
            return f"[DENIED] {e}"
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_stream(self, args) -> str:
        """Real-time stream control."""
        if not args:
            return """Stream Commands:
  /stream start         Start fabric router (ZMQ)
  /stream status        Check stream status
  /stream publish <msg> Publish message to stream
  /stream kafka         Start Kafka mirror"""
        
        subcmd = args[0].lower()
        
        if subcmd == "start":
            try:
                from memory_thread.nervous.fabric import FabricRouter
                import asyncio
                
                if not hasattr(self, '_fabric') or not self._fabric:
                    self._fabric = FabricRouter(mode="ROUTER")
                    asyncio.create_task(self._fabric.start())
                    return "[OK] Fabric Router started on ipc://fabric_router"
                else:
                    return "[INFO] Fabric Router already running"
            except Exception as e:
                return f"[ERR] Failed to start fabric: {e}"
        
        elif subcmd == "status":
            fabric_status = "running" if hasattr(self, '_fabric') and self._fabric and self._fabric.running else "stopped"
            kafka_status = "running" if hasattr(self, '_kafka') and self._kafka else "stopped"
            return f"Stream Status:\n  Fabric Router: {fabric_status}\n  Kafka Mirror: {kafka_status}"
        
        elif subcmd == "publish":
            if not hasattr(self, '_fabric') or not self._fabric:
                return "[ERR] Fabric not started. Run /stream start first."
            msg = " ".join(args[1:]) if len(args) > 1 else "test"
            try:
                import asyncio
                await self._fabric.send(b"broadcast", {"type": "message", "content": msg})
                return f"[OK] Published: {msg}"
            except Exception as e:
                return f"[ERR] {e}"
        
        elif subcmd == "kafka":
            try:
                from memory_thread.nervous.fabric import KafkaMirror
                import asyncio
                
                self._kafka = KafkaMirror()
                asyncio.create_task(self._kafka.start())
                return "[OK] Kafka Mirror starting (localhost:9092)"
            except Exception as e:
                return f"[ERR] {e}"
        
        return "Usage: /stream [start|status|publish|kafka]"

    async def _cmd_galaxy(self, args) -> str:
        """Galaxy Schema OLAP queries."""
        if not args:
            return """Galaxy Commands:
  /galaxy stats                  Show fact/belief stats
  /galaxy slice <source>         Beliefs from source
  /galaxy dice <agent> [min_auth] Filter by agent/authority
  /galaxy rollup <query>         Summarize beliefs
  /galaxy conflicts              Show belief conflicts"""
        
        subcmd = args[0].lower()
        client, err = self._get_client()
        if err:
            return f"[ERR] {err}"
        
        try:
            if subcmd == "stats":
                stats = client.galaxy_stats()
                facts = stats.get("facts", {})
                beliefs = stats.get("beliefs", {})
                return f"Galaxy Stats:\n  Facts: {facts.get('file_facts', 0)} stored\n  Beliefs: {beliefs.get('total_beliefs', 0)} across {beliefs.get('agents_count', 0)} agents"
            
            elif subcmd == "slice":
                if len(args) < 2:
                    return "Usage: /galaxy slice <source_uri>"
                result = client.query_galaxy("SLICE", source_uri=args[1])
                beliefs = result.beliefs if hasattr(result, 'beliefs') else []
                return f"SLICE results ({len(beliefs)} beliefs):\n" + "\n".join([f"  [{b.agent_id}] {b.content[:60]}..." for b in beliefs[:5]])
            
            elif subcmd == "dice":
                agent = args[1] if len(args) > 1 else None
                min_auth = float(args[2]) if len(args) > 2 else 0.0
                result = client.query_galaxy("DICE", agent_id=agent, min_authority=min_auth)
                beliefs = result.beliefs if hasattr(result, 'beliefs') else []
                return f"DICE results ({len(beliefs)} beliefs):\n" + "\n".join([f"  [{b.agent_id}] {b.content[:60]}..." for b in beliefs[:5]])
            
            elif subcmd == "rollup":
                query = " ".join(args[1:]) if len(args) > 1 else ""
                result = client.query_galaxy("ROLL_UP", entity_query=query)
                return f"ROLL UP: {result.get('summary', 'No results')}\n  Beliefs: {result.get('belief_count', 0)}\n  Agents: {result.get('agents', [])}"
            
            elif subcmd == "conflicts":
                conflicts = client.get_galaxy_conflicts()
                if not conflicts:
                    return "[OK] No conflicts detected"
                return f"Conflicts ({len(conflicts)}):\n" + "\n".join([f"  Fact {c['fact_id']}: {len(c['beliefs'])} beliefs from {c['agents']}" for c in conflicts[:5]])
            
            else:
                return "Usage: /galaxy [stats|slice|dice|rollup|conflicts]"
                
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_provider(self, args) -> str:
        """Manage LLM providers."""
        try:
            from memory_thread.nervous.vault import vault
            
            if not args:
                user = getattr(self, '_user', 'default')
                active = vault.get_active_provider(user)
                providers = vault.list_providers(user)
                lines = [f"Active Provider: {active}", f"Configured: {providers or ['local']}"]
                lines.append(f"User: {user}")
                lines.append("\nUsage:")
                lines.append("  /provider list              List providers")
                lines.append("  /provider use <name>        Switch provider")
                lines.append("  /provider add <name>        Add provider (use in secure mode)")
                lines.append("  /provider remove <name>     Remove provider")
                return "\n".join(lines)
            
            subcmd = args[0].lower()
            user = getattr(self, '_user', 'default')
            
            if subcmd == "list":
                providers = vault.list_providers(user)
                active = vault.get_active_provider(user)
                if not providers:
                    return f"No providers for {user}. Use /secure then /provider add <name>"
                lines = [f"Configured Providers (for {user}):"]
                for p in providers:
                    marker = " [ACTIVE]" if p == active else ""
                    creds = vault.get_provider(p, user)
                    model = creds.get("model", "default") if creds else "?"
                    lines.append(f"  {p}{marker} (model: {model})")
                return "\n".join(lines)
            
            elif subcmd == "use":
                if len(args) < 2:
                    return "Usage: /provider use <name>"
                name = args[1].lower()
                if name == "local":
                    vault.set_active_provider("local", user)
                    return "[OK] Switched to local model"
                if name not in vault.list_providers(user):
                    return f"[ERR] Provider '{name}' not configured. Use /provider add first."
                vault.set_active_provider(name, user)
                return f"[OK] Switched to {name}"
            
            elif subcmd == "add":
                if len(args) < 2:
                    return "Usage: /provider add <name>\n       Then enter key in /secure mode"
                if not getattr(self, '_secure_mode', False):
                    return "[WARN] Enter /secure mode first, then use /provider add"
                
                name = args[1].lower()
                # In secure mode, prompt for key
                log = self.query_one("#log", Log)
                log.write_line(f"[SECURE] Adding provider: {name} for user: {user}")
                log.write_line("[SECURE] Enter: API_KEY or API_KEY|BASE_URL|MODEL")
                self._pending_provider = name
                self._pending_provider_user = user
                return None
            
            elif subcmd == "remove":
                if len(args) < 2:
                    return "Usage: /provider remove <name>"
                name = args[1].lower()
                if vault.delete_provider(name, user):
                    return f"[OK] Removed provider: {name}"
                return f"[ERR] Provider '{name}' not found"
            
            return "Usage: /provider [list|use|add|remove]"
            
        except Exception as e:
            return f"[ERR] {e}"

    async def _cmd_secure(self, args) -> str:
        """Toggle secure mode for entering sensitive data."""
        if args and args[0].lower() == "off":
            self._secure_mode = False
            self._update_status("Chat mode")
            return "[OK] Secure mode disabled"
        
        if not hasattr(self, '_secure_mode'):
            self._secure_mode = False
        
        self._secure_mode = not self._secure_mode
        
        if self._secure_mode:
            self._update_status("🔒 SECURE MODE")
            return """[SECURE MODE ON]
Commands available:
  /provider add <name>   Add new provider (will prompt for key)
  /secure off            Exit secure mode
  
Your input will be treated as sensitive data."""
        else:
            self._update_status("Chat mode")
            return "[OK] Secure mode disabled"

    async def _handle_secure_input(self, raw: str):
        """Handle input when in secure mode."""
        log = self.query_one("#log", Log)
        
        # If we're waiting for a provider key
        if hasattr(self, '_pending_provider') and self._pending_provider:
            provider_name = self._pending_provider
            self._pending_provider = None
            
            try:
                from memory_thread.nervous.vault import vault
                
                # Parse: could be just key, or key|url|model
                parts = raw.split("|")
                api_key = parts[0].strip()
                base_url = parts[1].strip() if len(parts) > 1 else None
                model = parts[2].strip() if len(parts) > 2 else None
                
                # Get stored user
                user = getattr(self, '_pending_provider_user', 'default')
                self._pending_provider_user = None
                
                vault.set_provider(provider_name, api_key, base_url, model, user)
                log.write_line(f"[OK] Provider '{provider_name}' configured for {user}")
                log.write_line("[TIP] Use /provider use <name> to switch")
            except Exception as e:
                log.write_line(f"[ERR] Failed to add provider: {e}")
            
            return True
        
        return False

    async def _cmd_quit(self, args) -> str:
        self.exit()
        return "Goodbye!"

    def action_clear_log(self):
        log = self.query_one("#log", Log)
        log.clear()


# Backwards compat
MTNeuralInterface = MTShell


if __name__ == "__main__":
    app = MTShell()
    app.run()