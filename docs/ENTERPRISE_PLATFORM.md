# Enterprise AI Agent Platform
## MT as the Central Memory Brain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ENTERPRISE AI AGENT PLATFORM                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    MT Core (NAS/Server)                           │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│   │  │  Code Memory │  │ Doc Memory   │  │  Chat Memory │             │   │
│   │  │  (Git repos)│  │ (PDFs, Wiki)  │  │ (Conversations)            │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│   │  │  API Memory  │  │  DB Schema   │  │  User Memory │             │   │
│   │  │  (REST/gRPC) │  │  (tables)    │  │  (prefs, history)           │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│   │                                                                     │   │
│   │         ▲ Truth Vectors (confidence, authority, decay)            │   │
│   │         ▼ Galaxy Schema (facts → beliefs → agents)                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                              REST/gRPC                                      │
│                                    │                                         │
│   ┌───────────────────────────────┴───────────────────────────────────────┐ │
│   │                     Agent Connectors                                  │ │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │ │
│   │  │  CLI Agent  │  │  Web UI     │  │  IDE Plugin │  │  Slack Bot  │   │ │
│   │  │  (mt chat)  │  │  (browser)  │  │  (VS Code)  │  │  @mt help   │   │ │
│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Architecture

### MT Server (NAS/Workstation)

```python
# Runs on powerful machine (NAS/workstation)
# All enterprise memory stored here

# Start MT server
mt serve --host 0.0.0.0 --port 8000 --workers 4
```

### Agent Connectors (Client Side)

| Connector | Interface | Use Case |
|-----------|-----------|----------|
| **CLI** | `mt chat` | Developers |
| **Web** | http://nas:8000 | Non-technical |
| **IDE** | VS Code extension | Coding |
| **Slack** | @mtbot in channel | Team collaboration |
| **API** | REST/GraphQL | Custom integrations |

## What Each Connector Can Do

### 1. CLI Connector
```bash
# Connect to enterprise MT
mt --server http://192.168.1.100:8000 chat

# Ask anything with full memory context
mt ask "what did we decide about the auth redesign?"
mt ask "show me the api documentation for user service"
```

### 2. Web UI
```
Browser → http://nas:8000
  ├── Chat interface
  ├── Memory search
  ├── Agent management
  └── Admin dashboard
```

### 3. IDE Plugin
```
VS Code / JetBrains
  ├── Ctrl+Shift+M: Ask about codebase
  ├── Auto-remembers code changes
  ├── Suggests based on past solutions
  └── Debug with memory of similar bugs
```

### 4. Slack Bot
```
@mt help
  → What did we discuss about project X?
  → Summarize the architecture decision
  → Who worked on feature Y?
```

## Multi-Tenant Enterprise Setup

```yaml
# docker-compose.enterprise.yml
services:
  mt-core:
    image: memorythread/mt:latest
    volumes:
      - ./data:/data  # All memory lives here
    ports:
      - "8000:8000"
    environment:
      - MT_MULTI_TENANT=true
      - MT_AUTH_ENABLED=true
      - MT_ADmins=user1,user2

  mt-web:
    image: memorythread/mt-web:latest
    depends_on:
      - mt-core
    
  # Optional: Per-department agents
  dev-agent:
    image: memorythread/agent-code
    environment:
      - MT_SERVER=http://mt-core:8000
      - AGENT_TYPE=developer
      
  support-agent:
    image: memorythread/agent-support
    environment:
      - MT_SERVER=http://mt-core:8000
      - AGENT_TYPE=support
```

## Enterprise Memory Categories

| Memory Type | Source | Who Uses |
|-------------|--------|----------|
| **Code** | Git repos, PRs | Developers |
| **Docs** | Wiki, PDFs, Google Docs | Everyone |
| **Chat** | Slack, Teams, Meetings | Everyone |
| **API** | REST/gRPC specs | Developers |
| **Database** | Schemas, queries | Data team |
| **User** | Preferences, history | All agents |
| **Decisions** | Meeting notes, RFCs | Leadership |

## Agent Types for Enterprise

```python
# Pre-built enterprise agents
agents = {
    "developer": {
        "tools": ["read_code", "grep", "run_tests", "git"],
        "memory": "code + docs",
        "description": "Helps with coding tasks"
    },
    "support": {
        "tools": ["read_docs", "search_kb", "create_ticket"],
        "memory": "docs + chat",
        "description": "Customer support assistant"
    },
    "analyst": {
        "tools": ["query_db", "read_reports", "generate_chart"],
        "memory": "db + docs + chat",
        "description": "Data analysis assistant"
    },
    "researcher": {
        "tools": ["search_web", "read_papers", "summarize"],
        "memory": "docs + chat",
        "description": "Research and benchmarking"
    },
    "manager": {
        "tools": ["read_reports", "search_decisions", "list_tasks"],
        "memory": "decisions + chat",
        "description": "Project and team management"
    }
}
```

## Example Enterprise Session

```
User (Slack): @mt what was the decision about the new payment API?

[MT Agent]:
  → Search memory for "payment API decision"
  → Found: Meeting notes from 2024-03-15
  → Found: RFC-042 by @john about Stripe migration
  → Found: 3 beliefs from different team members
  
  Response:
  Based on our memory:
  - Decision: Migrate to Stripe (meeting Mar 15)
  - Owner: @john 
  - Timeline: Q2 2024
  - Concerns raised by security team (resolved)
  
  Confidence: 0.92 (3 sources, high authority)
```

## Security & Access Control

```python
# Enterprise auth
- API keys per team/department
- Namespace isolation (like departments)
- Role-based memory access
- Audit log of all queries

# Data privacy
- On-premise (data never leaves company)
- Encrypt at rest
- Backup to cold storage
```

## Deployment on NAS

```bash
# 1. Install on NAS (DSM, TrueNAS, etc.)
docker run -d \
  --name mt-enterprise \
  -p 8000:8000 \
  -v /volume1/mt-data:/data \
  -e MT_MULTI_TENANT=true \
  memorythread/mt:latest

# 2. Connect agents/clients
export MT_SERVER=http://nas-ip:8000
export MT_API_KEY=enterprise-key

# 3. Ingest all company knowledge
mt ingest --type code --path /path/to/repos
mt ingest --type docs --path /path/to/wiki
```

## The Power

```
┌─────────────────────────────────────────────────────────────────┐
│  Traditional Enterprise Search                                  │
│  → Google: "find documents containing X"                       │
│  → Algolia: "find code matching Y"                             │
│  → Separate systems, no memory                                 │
├─────────────────────────────────────────────────────────────────┤
│  MT Enterprise Platform                                         │
│  → ONE system remembers EVERYTHING                             │
│  → Code + Docs + Chat + Decisions + API                        │
│  → Agents with memory across sessions                          │
│  → Truth scores (know what to trust)                           │
│  → Multi-agent collaboration (different perspectives)          │
│  → On-premise (your data, your control)                        │
└─────────────────────────────────────────────────────────────────┘
```

## Future: The AI Operating System

```
            ┌──────────────────────────────────────┐
            │         MT Core (The Brain)         │
            │   - All company memory               │
            │   - Truth vectors                    │
            │   - Galaxy Schema                    │
            │   - Agent orchestration              │
            └──────────────┬───────────────────────┘
                           │
      ┌────────────────────┼────────────────────┐
      ▼                    ▼                    ▼
┌──────────┐        ┌──────────┐        ┌──────────┐
│ Code AI  │        │ Docs AI  │        │ Chat AI │
│ (devs)   │        │ (all)    │        │ (all)   │
└──────────┘        └──────────┘        └──────────┘

All connected to same memory → One source of truth → 
The company "brain" that never forgets
```

---

*This turns MT into the **central intelligence layer** for the entire enterprise - an AI operating system where every tool, bot, and person connects to the same persistent memory.*