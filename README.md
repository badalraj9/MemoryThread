# Memory Thread

> **A Truth-Preserving Cognitive Memory System for AI**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](#docker)

---

## What is Memory Thread?

Memory Thread (MT) is a **cognitive memory layer** for AI systems that solves the fundamental problem of **truth preservation** in multi-agent environments. Unlike traditional vector databases, MT tracks the _provenance_, _confidence_, and _decay_ of every piece of information.

### Why MT?

```
Traditional Vector DB          Memory Thread
────────────────────          ──────────────
All data = equal              Truth vectors: confidence, authority, freshness
No decay                      Freshness decays over time  
No provenance                 Full event sourcing & audit trail
Single agent                  Multi-agent belief dimensions
```

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and start everything with one command
git clone https://github.com/badalraj/MemoryThread.git
cd MemoryThread
docker compose up -d

# Access the API at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Option 2: From Source

```bash
# Clone the repository
git clone https://github.com/badalraj/MemoryThread.git
cd MemoryThread

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .

# Start PostgreSQL and Qdrant (or use Docker)
# Then run:
mt serve
```

### Option 3: Python API (Recommended)

```python
from memory_thread.sdk import MemoryClient

# Connect using connection string (connects to local server by default)
mt = MemoryClient.connect("mt://localhost:8000/my-project")

# Or use environment variable MT_URL
# mt = MemoryClient.connect_from_env()

# Store memories with truth metadata
mt.remember("User prefers dark mode", confidence=0.9, source="user")
mt.remember("Project deadline is Friday", confidence=1.0, source="user")

# Chat with memory context using cloud LLM
response = mt.chat("What are my preferences?", provider="groq")
print(response)
```

**Connection String Format:**
- `mt://localhost:8000/default` - Local server, default namespace
- `mt://localhost:8000/my-project` - Local server, custom namespace
- `mt://api.memorythread.io/org/project?api_key=sk-xxx` - Cloud server with auth

---

## CLI Commands

```bash
# Start API server
mt serve                                    # http://localhost:8000
mt serve --port 9000                        # Custom port
mt serve --workers 4                       # Multiple workers

# Initialize workspace
mt init                                     # Create .mt/config.json

# Chat with memory
mt ask "what do you remember about me?"     # One-shot question
mt                                          # Interactive chat mode

# Search & manage memories
mt search "preferences"                     # Search memories
mt status                                   # System health + stats

# Galaxy Schema (OLAP queries)
mt galaxy stats                            # Fact/belief counts
mt galaxy slice --source code              # Filter by source
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Memory Thread Architecture                    │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │  REST API   │  │  Python SDK  │  │   CLI (mt)  │  │  Docker Compose │ │
│  │  FastAPI    │  │MemoryClient │  │  Typer+Rich │  │  PostgreSQL     │ │
│  │   :8000     │  │   (Python)   │  │             │  │  Qdrant         │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘ │
│         └───────────────┼─────────────────┼─────────────────┘         │
│                         ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                      Core Services                                 ││
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────┐  ││
│  │  │    TMS     │  │   Galaxy   │  │   Decay    │  │   WAL       │  ││
│  │  │  Service   │  │   Schema   │  │  Engine    │  │ (fsync)     │  ││
│  │  │ (Truth)    │  │  (OLAP)    │  │ (Forget)   │  │ (Crash-safe)│  ││
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └──────┬──────┘  ││
│  └────────┼───────────────┼───────────────┼───────────────┼─────────┘│
│           ▼               ▼               ▼               ▼          │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                       Persistence Layer                             ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  ││
│  │  │  PostgreSQL │  │   Qdrant    │  │   SQLite    │  │   WAL     │  ││
│  │  │  (Events)   │  │  (Vectors)  │  │ (Fallback)  │  │  Files    │  ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  ││
│  └────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## How It Works: Memory Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Autonomous Chat Flow                               │
└──────────────────────────────────────────────────────────────────────────┘

 User Input: "My name is John and I work at Acme"
      │
      ├─▶ 1. remember() ──────────────────────────────────────▶ WAL.prewrite
      │        ├── Create TruthVector (confidence, authority, freshness)
      │        ├── Entity extraction (NER)
      │        ├── Relation inference  
      │        ├── Persist to PostgreSQL + Qdrant
      │        └── WAL.commit (crash-safe)
      │
      ├─▶ 2. check_contradiction() ─────────────────────────────▶ Flag conflicts
      │
      ├─▶ 3. recall() ──────────────────────────────────────────▶ Query memories
      │        └── Vector search + truth filtering
      │
      ├─▶ 4. build_context() ──────────────────────────────────▶ Aggregate context
      │
      ├─▶ 5. generate_response() ──────────────────────────────▶ LLM (Groq/OpenRouter)
      │        └── Prompt = system + context + user message
      │
      └─▶ 6. remember(response, source="agent") ──────────────▶ Store with lower authority
```

---

## Configuration

### Environment Variables

```bash
# Database (optional - falls back to in-memory)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=memorythread
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password

# Vector DB (optional - falls back to keyword search)
QDRANT_HOST=localhost
QDRANT_PORT=6333

# LLM Providers (for chat functionality)
GROQ_API_KEY=your_groq_key          # Get from https://console.groq.com
OPENROUTER_API_KEY=your_key         # Get from https://openrouter.ai/keys

# Identity
MT_USER=yourname
MT_NAMESPACE=default
```

### Docker Compose Override

Create `docker-compose.override.yml` to customize:

```yaml
services:
  mt-api:
    environment:
      - GROQ_API_KEY=your_key
    volumes:
      - ./data:/data
```

---

## API Documentation

Start the server: `mt serve` or `uvicorn memory_thread.api.server:app`

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Method | Endpoint           | Description                   |
|--------|--------------------|-------------------------------|
| POST   | `/memory/remember` | Store a memory with truth     |
| POST   | `/memory/recall`   | Search memories (vector/keyword) |
| POST   | `/galaxy/fact`     | Ingest a fact (L0)            |
| POST   | `/galaxy/belief`   | Derive a belief (L1)          |
| POST   | `/galaxy/query`    | OLAP query (SLICE/DICE/ROLL)  |
| GET    | `/health`          | Health check                  |

---

## Galaxy Schema (OLAP for Cognition)

```python
# Store raw facts (immutable)
fact_id = mt.ingest_fact(
    content=code,
    source_uri="file://auth.py",
    content_type="code"
)

# Multiple agents derive beliefs from the same fact
mt.derive_belief(fact_id, "Handles JWT securely", agent_id="SecurityBot", confidence=0.95)
mt.derive_belief(fact_id, "Needs refactoring", agent_id="CodeReviewer", authority=0.8)

# OLAP-style queries
mt.query_galaxy("SLICE", source_uri="file://auth.py")  # All beliefs about auth.py
mt.query_galaxy("DICE", agent_id="SecurityBot", min_authority=0.8)
```

---

## Truth Vectors

Every memory has a truth vector:

| Component     | Range  | Description                              |
|---------------|--------|------------------------------------------|
| Confidence    | [0,1]  | Certainty in the information            |
| Authority     | [0,1]  | Source credibility (user=1.0, agent=0.5)|
| Freshness    | [0,1]  | Temporal relevance (decays over time)   |
| Corroboration | [0,∞)  | Independent confirmations                |

```python
# Query with truth filtering
results = mt.recall("user preferences", min_truth_score=0.5)
```

---

## Timewarp

Memory Thread supports **temporal repair** through its Timewarp engine. When a late event arrives (e.g., backdated information), Timewarp:

1. Inserts the late event into the event log
2. Recomputes entity state from the nearest snapshot or from scratch
3. Compares new state to old and flags significant deltas
4. Updates the entity state in a single transaction

```python
from memory_thread.services.timewarp_engine import TimewarpEngine

engine = TimewarpEngine()
result = engine.insert_late_event(late_event)
```

This ensures the timeline remains consistent even with out-of-order events.

---

## Contemplator

The **Contemplator** is MT's self-observation engine. It runs periodic reflections to:

- Assess memory health (truth score distribution)
- Detect conflicts across agent beliefs
- Identify access anomalies
- Find stale domains (low freshness)
- Recommend consolidation candidates

```python
from memory_thread.services.contemplator import Contemplator

contemplator = Contemplator(auto_start=True)  # Runs daily automatically
reflection = contemplator.daily_reflection()
summary = contemplator.generate_insight_summary()
print(summary)
```

The Contemplator persists insights to the `insights_log` table and loads previous reflections on startup.

---

## Replay

Memory Thread supports **event replay** for state reconstruction:

1. **Snapshot Service** - Creates checkpoints of entity state
2. **Replay Service** - Rebuilds state from snapshots + subsequent events
3. **Timewarp Integration** - Uses nearest snapshot to optimize replay

```python
from memory_thread.services.replay_service import ReplayService
from memory_thread.services.snapshot_service import SnapshotService

replay = ReplayService()
snapshot = SnapshotService()

# Create a checkpoint
snap_id = snapshot.take_snapshot(entity_state)

# Rebuild from snapshot
rebuilt = replay.replay_from_snapshot(entity_id, snap_id.timestamp)
```

---

## Golden Thread

The **Golden Thread** is Memory Thread's audit trail - a chronological record of all state changes that can reconstruct the entire history of any entity. It combines:

- **Event Sourcing**: Every change is an event
- **WAL (Write-Ahead Log)**: Crash-safe persistence
- **Audit Ledger**: Immutable record of access and modifications

```python
from memory_thread.nervous.audit_ledger import AuditLedger

ledger = AuditLedger()
entries = ledger.query(entity_id=my_entity, limit=100)

for entry in entries:
    print(f"{entry.timestamp}: {entry.action} by {entry.actor}")
```

The Golden Thread ensures traceability and enables debugging, compliance, and state recovery.

---

## External Dependencies

Memory Thread requires the following external services:

- **PostgreSQL** - Event storage and entity state
- **Qdrant** - Vector similarity search (optional, falls back to keyword)

Qdrant can be installed separately:
```bash
# Download Qdrant
curl -L https://get.qdrant.io -o qdrant.sh
bash qdrant.sh

# Or use Docker
docker run -p 6333:6333 qdrant/qdrant
```

---

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=memory_thread

# Specific test
pytest tests/test_sdk.py -v
```

---

## Project Structure

```
MemoryThread/
├── memory_thread/
│   ├── api/              # REST API (FastAPI)
│   ├── db/               # Database clients (PostgreSQL, Qdrant, SQLite)
│   ├── nervous/          # Vault, Galaxy Core, Audit
│   ├── services/         # Core services (TMS, WAL, Decay)
│   └── utils/            # CLI, embeddings, logging
├── tests/                # Test suite
├── docs/                 # Architecture & design docs
├── docker-compose.yml    # One-command startup
├── pyproject.toml        # Python packaging
└── README.md
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Truth Maintenance Systems (TMS) research
- OLAP/Galaxy Schema concepts from data warehousing
- The open-source AI community