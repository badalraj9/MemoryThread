# Memory Thread 🧠

**The Truth-Aware Memory Engine for AI Agents**

Memory Thread (MT) is an event-sourced memory system that gives AI agents the ability to remember facts, handle contradictions, and know when to say "I don't know."

> _Not a vector database. Not a chatbot. A Truth Maintenance System._

---

## 🎯 What Makes MT Different

| Feature            | Typical AI Memory   | Memory Thread             |
| ------------------ | ------------------- | ------------------------- |
| **Data Model**     | Key-value / Vectors | Events → States           |
| **Uncertainty**    | Hidden or none      | Explicit (Truth Vectors)  |
| **Contradictions** | Last-write-wins     | Higher authority wins     |
| **"I don't know"** | Empty response      | Formal `None` with reason |
| **Audit Trail**    | Logs (maybe)        | Immutable event log       |

### Core Capabilities

- **🔄 Deterministic Replay** — Reconstruct any entity's state at any point in time
- **📊 Truth Vectors** — 4D truth scoring: (Confidence, Authority, Freshness, Corroboration)
- **⏱️ Memory Decay** — Facts fade naturally based on configurable decay curves
- **🔀 Contradiction Resolution** — Mathematical resolution based on authority
- **⚡ High Performance** — ~3,600 EPS full pipeline, ~40,000+ transport layer

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ (event store)
- Qdrant (optional, for vector search)

### Installation

```bash
git clone https://github.com/badalraj9/MemoryThread.git
cd MemoryThread
pip install -r requirements.txt
```

### Set Up Database

```bash
# Create database
psql -U postgres -c "CREATE DATABASE memory_thread_db;"

# Apply schema
psql -U postgres -d memory_thread_db -f memory_thread/db/schema_phase_3_4.sql
```

### Configure Environment

```bash
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=your_password
export POSTGRES_DB=memory_thread_db
export POSTGRES_HOST=localhost
```

### Run the API

```bash
uvicorn memory_thread.api.main:app --host 0.0.0.0 --port 8000
```

### Test It

```bash
# Health check
curl http://localhost:8000/health

# Ingest a memory
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "producer_id": "agent-001",
    "events": [{
      "content": "User prefers dark mode",
      "timestamp": "2025-01-01T10:00:00Z"
    }]
  }'
```

---

## 📡 API Reference

### Health & Monitoring

| Endpoint            | Method | Description                           |
| ------------------- | ------ | ------------------------------------- |
| `GET /`             | GET    | Quick health check                    |
| `GET /health`       | GET    | Detailed health with service statuses |
| `GET /health/ready` | GET    | Kubernetes readiness probe            |
| `GET /health/live`  | GET    | Kubernetes liveness probe             |
| `GET /metrics`      | GET    | Prometheus-compatible metrics         |
| `GET /version`      | GET    | Version and build info                |

### Event Ingestion

| Endpoint                | Method | Description                 |
| ----------------------- | ------ | --------------------------- |
| `POST /register`        | POST   | Register a producer         |
| `POST /ingest`          | POST   | Ingest a batch of events    |
| `GET /control/throttle` | GET    | Get current system pressure |

### Maintenance

| Endpoint                          | Method | Description                   |
| --------------------------------- | ------ | ----------------------------- |
| `GET /maintenance/proposals`      | GET    | Get duplicate merge proposals |
| `POST /maintenance/approve/merge` | POST   | Approve a merge proposal      |
| `GET /maintenance/health/stats`   | GET    | Dashboard metrics             |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MEMORY THREAD                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ FastAPI     │  │ ZMQ Fabric  │  │ Slab        │        │
│  │ Gateway     │→ │ (Transport) │→ │ Allocator   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                                  │                │
│         ▼                                  ▼                │
│  ┌─────────────────────────────────────────────────┐      │
│  │          TRUTH MANAGEMENT SYSTEM (TMS)          │      │
│  │  • Truth Vector Scoring                         │      │
│  │  • State Derivation                             │      │
│  │  • Freshness Decay                              │      │
│  └─────────────────────────────────────────────────┘      │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │ PostgreSQL   │  │ Qdrant       │                       │
│  │ (Events)     │  │ (Vectors)    │                       │
│  └──────────────┘  └──────────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📚 Documentation

| Document                                                                               | Description                        |
| -------------------------------------------------------------------------------------- | ---------------------------------- |
| [Unified System Overview](docs/thesis_reference/00_Unified_System_Overview.md)         | Philosophy and high-level concepts |
| [Architectural Layers](docs/thesis_reference/02_Architectural_Layers.md)               | Deep dive into system layers       |
| [Mathematical Specifications](docs/thesis_reference/06_Mathematical_Specifications.md) | Truth Vector algebra               |
| [End-to-End Workflow](docs/thesis_reference/07_End_to_End_Workflow.md)                 | Data flow from API to storage      |

---

## 🧪 Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test suites
pytest tests/test_tms_complete.py -v      # TMS logic
pytest tests/test_realworld_scenarios.py -v  # AI agent simulation
pytest tests/test_persistence_roundtrip.py -v  # Database persistence
```

---

## 📊 Benchmarks

```bash
# Full pipeline benchmark
python benchmarks/benchmark_realworld.py

# Expected results (i5-12450H):
# • Event Creation: ~50,000 EPS
# • State Derivation: ~30,000 EPS
# • Full Pipeline: ~3,600 EPS
```

---

## 🤝 Contributing

We welcome contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting.

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

---

**Built for AI that needs to remember.** 🚀
