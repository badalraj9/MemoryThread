# MT Shell Commands Reference

## Chat Mode (Default)

Just type anything → Auto-remembered + LLM response

```
Hello, remember my project deadline is March 15th
```

---

## Memory Commands

| Command           | Description                           |
| ----------------- | ------------------------------------- |
| `/recall <query>` | Search memories                       |
| `/load <file>`    | Ingest file (keeps original in vault) |
| `/load <folder>`  | Ingest folder recursively             |
| `/stats`          | Memory statistics                     |

---

## Identity & RBAC

| Command                       | Description                       |
| ----------------------------- | --------------------------------- |
| `/whoami`                     | Show current user/role/grade      |
| `/su <role>`                  | Switch role for session           |
| `/sudo enable <role> <user>`  | Grant role (requires higher rank) |
| `/sudo disable <role> <user>` | Revoke role                       |

### Role Hierarchy

```
root (SSS_CLASS)      ─▶ can grant ─▶ admin
admin (S_CLASS)       ─▶ can grant ─▶ engineer
engineer (B_CLASS)    ─▶ can grant ─▶ employee
employee (C_CLASS)    ─▶ can grant ─▶ guest
guest (E_CLASS)       ─▶ no grant power
```

---

## Galaxy (Multi-Agent)

| Command                              | Description            |
| ------------------------------------ | ---------------------- |
| `/agent register <name> [authority]` | Register new agent     |
| `/agent list`                        | List registered agents |
| `/agent use <name>`                  | Switch active agent    |
| `/conflicts`                         | Show belief conflicts  |

---

## System

| Command          | Description                |
| ---------------- | -------------------------- |
| `/health`        | System health check        |
| `/audit [limit]` | View audit log (root only) |

---

## Maintenance

| Command              | Description               | Approval           |
| -------------------- | ------------------------- | ------------------ |
| `/decay [rate]`      | Apply memory decay        | Auto               |
| `/prune [threshold]` | Remove low-value memories | **Confirm**        |
| `/clear`             | Clear all memories        | **Confirm (root)** |

---

## Exit

`/quit` or `/exit` or `/q`

---

## Examples

```bash
# Chat (auto-remember)
I need to remember that the API key is abc123

# Search
/recall api key

# Load documents
/load ./docs/architecture.md
/load ./src/

# RBAC
/sudo enable engineer alice
/sudo disable guest bob

# Agent mode
/agent register SecurityBot 0.9
/agent use SecurityBot
```
