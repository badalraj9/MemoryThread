# Memory Thread

> **A Truth-Preserving Cognitive Memory System for AI**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![API Docs](https://img.shields.io/badge/docs-OpenAPI-orange.svg)](#api-documentation)

---

## Overview

Memory Thread (MT) is a **cognitive memory layer** for AI systems that solves the fundamental problem of **truth preservation** in multi-agent environments. Unlike traditional vector databases, MT tracks the _provenance_, _confidence_, and _decay_ of every piece of information.

### Key Features

| Feature               | Description                                                  |
| --------------------- | ------------------------------------------------------------ |
| **Truth Vectors**     | Every memory has confidence, authority, and freshness scores |
| **Galaxy Schema**     | OLAP-style queries across fact and belief dimensions         |
| **Multi-Agent**       | Each agent has its own belief dimension                      |
| **Graceful Fallback** | DB → File → Memory (never loses data)                        |
| **RBAC**              | Role-based access control with audit logging                 |
| **Time Travel**       | Event-sourced history reconstruction                         |

---

## Quick Start

### Installation

```bash
# Basic installation
pip install memory-thread

# With all extras
pip install memory-thread[full]

# Development
pip install memory-thread[dev]
```

### From Source

```bash
git clone https://github.com/badalraj/MemoryThread.git
cd MemoryThread
pip install -e .[dev]
```

### Basic Usage

```python
from memory_thread.sdk import MemoryClient

# Create a client
mt = MemoryClient(namespace="my_app")

# Store memories with truth metadata
mt.remember("User prefers dark mode", confidence=0.9, source="observation")
mt.remember("Project deadline is Friday", confidence=1.0, source="user")

# Recall with truth filtering
results = mt.recall("user preferences", min_truth_score=0.5)

for memory in results.memories:
    print(f"{memory.content} (truth: {memory.truth_score:.2f})")
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory Thread Architecture                │
├─────────────────────────────────────────────────────────────┤
│  SDK / API Layer                                             │
│  ├── MemoryClient (Python SDK)                               │
│  ├── REST API (FastAPI)                                      │
│  └── TUI (Terminal Interface)                                │
├─────────────────────────────────────────────────────────────┤
│  Galaxy Schema (OLAP for Cognition)                          │
│  ├── Fact Store (Layer 0) - Immutable, content-addressed     │
│  ├── Belief Store (Layer 1) - Agent-specific interpretations │
│  └── Query Engine (Layer 2) - SLICE/DICE/DRILL/ROLLUP        │
├─────────────────────────────────────────────────────────────┤
│  Core Services                                               │
│  ├── TMS (Truth Maintenance System)                          │
│  ├── Identity Service                                        │
│  ├── Timewarp Engine (Event Sourcing)                        │
│  └── Contemplator (Self-Observation)                         │
├─────────────────────────────────────────────────────────────┤
│  Storage                                                     │
│  ├── PostgreSQL (Events/States)                              │
│  ├── Qdrant (Vector Search)                                  │
│  └── File Fallback (~/.mt/)                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Galaxy Schema

The Galaxy Schema applies **OLAP data warehouse principles to cognition**:

```python
# Store raw facts (immutable, deduplicated)
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
mt.query_galaxy("ROLL_UP", entity_query="authentication")  # Summarize
```

---

## API Documentation

### REST API

Start the API server:

```bash
uvicorn memory_thread.api.server:app --reload
```

Access documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints

| Method | Endpoint           | Description     |
| ------ | ------------------ | --------------- |
| POST   | `/memory/remember` | Store a memory  |
| POST   | `/memory/recall`   | Recall memories |
| POST   | `/galaxy/fact`     | Ingest a fact   |
| POST   | `/galaxy/belief`   | Derive a belief |
| POST   | `/galaxy/query`    | OLAP query      |
| GET    | `/galaxy/stats`    | Get statistics  |
| GET    | `/health`          | Health check    |

---

## TUI (Terminal Interface)

```bash
python -m memory_thread.utils.cli_bridge
```

### Commands

| Command           | Description                   |
| ----------------- | ----------------------------- |
| `just type`       | Auto-remembered, LLM responds |
| `/recall <query>` | Search memories               |
| `/galaxy stats`   | Show fact/belief counts       |
| `/provider list`  | List LLM providers            |
| `/secure`         | Toggle secure mode            |
| `/help`           | Show all commands             |

---

## Configuration

### Environment Variables

```bash
# Database
MT_POSTGRES_URL=postgresql://user:pass@localhost/mt
MT_QDRANT_URL=http://localhost:6333

# LLM Providers (or use /secure mode)
GROQ_API_KEY=your_key
OPENROUTER_API_KEY=your_key

# Identity
MT_USER=yourname
MT_ROLE=admin
```

---

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=memory_thread

# Specific test file
pytest tests/test_sdk.py -v
```

---

## Project Structure

```
MemoryThread/
├── memory_thread/
│   ├── api/              # REST API (FastAPI)
│   ├── db/               # Database clients
│   ├── nervous/          # Access control, vault, fabric
│   ├── services/         # Core services (TMS, Galaxy, etc.)
│   └── utils/            # CLI, logging, embeddings
├── tests/                # Test suite
├── docs/                 # Documentation
├── pyproject.toml        # Modern packaging
└── README.md
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing`
3. Write tests for your changes
4. Ensure tests pass: `pytest`
5. Submit a pull request

---

## Citation

If you use Memory Thread in research, please cite:

```bibtex
@software{memorythread2024,
  title = {Memory Thread: A Truth-Preserving Cognitive Memory System},
  author = {Raj, Badal},
  year = {2024},
  url = {https://github.com/badalraj/MemoryThread}
}
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Truth Maintenance Systems (TMS) research
- OLAP/Galaxy Schema concepts from data warehousing
- The open-source AI community
