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

### Option 3: Python API

```python
from memory_thread.sdk import MemoryClient

# Fast init (no DB connections)
mt = MemoryClient(namespace="my_app", use_db=False)

# Store memories with truth metadata
mt.remember("User prefers dark mode", confidence=0.9, source="observation")
mt.remember("Project deadline is Friday", confidence=1.0, source="user")

# Chat with memory context using cloud LLM
response = mt.chat("What are my preferences?", provider="groq")
print(response)
```

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