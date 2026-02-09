# MT CLI Reference

**Version 2.0** | Autonomy-First Design

> MT is autonomous — `chat()` auto-remembers, extracts entities, detects contradictions, and builds context.
> Regular users just type `mt` and talk. Higher clearance grades unlock inspection and maintenance.

---

## Quick Start

```bash
# Interactive chat (default — everything is auto-remembered)
mt

# One-shot question with memory context
mt ask "What do you know about my project?"

# Search stored memories
mt search "project deadline"

# System status
mt status
```

---

## Command Reference by RBAC Grade

### E-CLASS (Guest) — Basic Access

| Command               | Description                                     |
| --------------------- | ----------------------------------------------- |
| `mt`                  | Interactive chat — auto-remember + LLM response |
| `mt ask "<question>"` | One-shot question with memory context           |
| `mt whoami`           | Show current user, role, grade, namespace       |

### C-CLASS (Employee) — Inspection

| Command                        | Description                                                     |
| ------------------------------ | --------------------------------------------------------------- |
| `mt status`                    | Combined stats + health (memory count, truth scores, freshness) |
| `mt search "<query>"`          | Search memories (vector + keyword)                              |
| `mt search "<query>" --hybrid` | Hybrid search (vector + keyword + graph)                        |
| `mt load <file\|folder>`       | Ingest file or folder into memory                               |

### B-CLASS (Developer) — Deep Inspection

| Command                                      | Description                                   |
| -------------------------------------------- | --------------------------------------------- |
| `mt galaxy`                                  | Galaxy Schema status (facts, beliefs, agents) |
| `mt conflicts`                               | Show belief conflicts across agents           |
| `mt provenance <uuid>`                       | Full event history for a memory               |
| `mt agent register <name> [--authority 0.9]` | Register new agent                            |
| `mt agent list`                              | List registered agents                        |
| `mt agent use <name>`                        | Switch active agent                           |
| `mt provider list`                           | List LLM providers                            |
| `mt provider set <name> --key <api_key>`     | Configure provider                            |
| `mt provider use <name>`                     | Switch active provider                        |

### A-CLASS (Researcher) — Tuning & Maintenance

| Command                        | Description                                  |
| ------------------------------ | -------------------------------------------- |
| `mt decay [--rate 0.01]`       | Apply exponential freshness decay            |
| `mt consolidate [--window 30]` | Consolidate repetitive events into summaries |
| `mt export [--format json]`    | Export all memories                          |
| `mt snapshot`                  | Create checkpoint of current state           |

### S-CLASS (Executive) — Operations

| Command                      | Description                                       |
| ---------------------------- | ------------------------------------------------- |
| `mt prune [--threshold 0.3]` | Remove low-truth memories (confirmation required) |
| `mt audit [--limit 50]`      | View audit log                                    |
| `mt clients list`            | List registered API clients                       |
| `mt clients create <name>`   | Create new API client                             |
| `mt clients revoke <key>`    | Revoke API client key                             |

### SSS-CLASS (Godfather) — Nuclear

| Command                        | Description                                  |
| ------------------------------ | -------------------------------------------- |
| `mt clear --force`             | **Erase all memories** (double confirmation) |
| `mt rootkey rotate`            | Rotate root API key                          |
| `mt su <role>`                 | Switch role for session                      |
| `mt sudo grant <role> <user>`  | Grant role to user                           |
| `mt sudo revoke <role> <user>` | Revoke role from user                        |

---

## RBAC Grade Hierarchy

```
SSS-CLASS (Godfather)  ─▶ can grant ─▶ S-CLASS
S-CLASS   (Executive)  ─▶ can grant ─▶ A-CLASS
A-CLASS   (Researcher) ─▶ can grant ─▶ B-CLASS
B-CLASS   (Developer)  ─▶ can grant ─▶ C-CLASS
C-CLASS   (Employee)   ─▶ can grant ─▶ E-CLASS
E-CLASS   (Guest)      ─▶ no grant power
```

---

## Environment Variables

| Variable       | Default   | Description              |
| -------------- | --------- | ------------------------ |
| `MT_ROLE`      | `guest`   | Current user's RBAC role |
| `MT_USER`      | `default` | Current user ID          |
| `MT_NAMESPACE` | `default` | Memory namespace         |

---

## Examples

```bash
# Chat (everything is auto-remembered)
mt
> My project deadline is March 15th
# MT auto-remembers this, extracts "March 15th", detects if you previously said a different date

# One-shot question
mt ask "When is my project deadline?"

# Search memories with minimum truth score
mt search "deadline" --min-truth 0.5

# Load a project directory
mt load ./docs/

# Check system health
mt status

# Manage agents
mt agent register SecurityBot --authority 0.9
mt agent use SecurityBot

# Maintenance operations
mt decay --rate 0.01
mt consolidate --window 30
mt prune --threshold 0.3

# RBAC management (SSS-CLASS only)
mt sudo grant developer alice
mt su admin
```
