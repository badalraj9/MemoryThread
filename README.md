<p align="center">
  <pre align="center">
 __  __                                 _____ _                        _ 
|  \/  | ___ _ __ ___   ___  _ __ _   |_   _| |__  _ __ ___  __ _  __| |
| |\/| |/ _ \ '_ ` _ \ / _ \| '__| | | || | | '_ \| '__/ _ \/ _` |/ _` |
| |  | |  __/ | | | | | (_) | |  | |_| || | | | | | | |  __/ (_| | (_| |
|_|  |_|\___|_| |_| |_|\___/|_|   \__, ||_| |_| |_|_|  \___|\__,_|\__,_|
                                  |___/                                   
  </pre>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/License-MIT-9370DB?logo=opensourceinitiative&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Tests-20%20files-brightgreen?logo=pytest&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Graph-iGraph-5428A0?logo=graphql&logoColor=white" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Frontend-Scaffolded-grey?logo=react&logoColor=white" /></a>
</p>

<p align="center">
  <b>A truth-preserving, graph-native cognitive memory layer for AI agents</b><br>
  <i>Not a vector database. Memory is a causal graph — retrieve by spreading activation, not cosine similarity.</i>
</p>

---

## Why Memory Thread?

Most memory systems treat memories as **bags of vectors** — store an embedding, retrieve by cosine similarity, call it a day. This works for *search*. It fails at *reasoning*.

Memory Thread is built on a different premise: **memory is a causal graph** of events, entities, beliefs, and their relationships. Every write is an event with provenance. Every retrieval traverses a truth-weighted graph. Every memory carries confidence, authority, freshness, and corroboration metadata.

| Instead of… | Memory Thread does… |
|---|---|
| Flat vector search | Graph spreading activation along truth-weighted edges |
| Storing state snapshots | Event sourcing — state is *derived* from events |
| Single monolithic SDK | Modular `sdk/` package with clean separation |
| Base64 "encryption" for keys | Fernet AES-CBC encryption at rest |
| Open CORS to everywhere | Restricted origins + bearer token auth |

---

## Capabilities

| Capability | Description |
|---|---|
| **🧠 Truth Vectors** | 4D scoring: confidence, authority, freshness, corroboration. Weights configurable, normalized to 1.0. |
| **🔗 Graph-Native Recall** | iGraph spreading activation along truth-weighted edges. Not vector similarity — *reasoning*. |
| **🧵 Golden Thread** | Complete causal chain for any entity. Every event, antecedent, and truth evolution. Zero Postgres queries. |
| **📦 Memory Tiers** | Core (LLM context) → Episodic (iGraph) → Semantic (PostgreSQL). Hot/warm/cold management. |
| **👁️ Proactive Context** | ContextMonitor injects relevant memories *without being queried*. Entity extraction, dedup, token budgeting. |
| **🔄 Workflow Induction** | AWM-style procedural memory. Extracts reusable workflows from successful agent trajectories. |
| **🔐 Merkle Attestation** | Tamper-proof checkpoint chain. Audit-proof: "at timestamp T, agent A knew fact F with confidence C." |
| **🌌 Multi-Agent Galaxy** | Per-agent belief spaces. Cross-agent contradiction detection. Belief bridges (supports/contradicts). |
| **📝 WAL Durability** | Write-ahead log: sync mode (~277 EPS) or batched mode (~4,780 EPS). |
| **🚧 Namespace Isolation** | Per-namespace memory spaces. Cross-namespace reads blocked at SDK level. |
| **🔑 Encrypted Vault** | Provider API keys encrypted at rest with Fernet (AES-CBC, 256-bit). Not base64. |
| **📡 SSE Event Stream** | Real-time graph mutation events pushed to connected clients via Server-Sent Events. |
| **🔍 Postgres FTS + Graph** | Hybrid recall: FTS for seed resolution + graph activation for reasoning. Qdrant removed. |
| **🛡️ API Auth** | Optional `MT_API_KEY` bearer token on all HTTP endpoints. CORS restricted to `MT_ALLOWED_ORIGINS`. |
| **🧪 20 Integration Tests** | Golden thread, decay curves, WAL recovery, contradiction accuracy, namespace isolation, graceful degradation. |

---

## Quick Start

```bash
# Install
pip install -e ".[full]"

# CLI
mt --help

# API server
mt-api

# OpenAI-compatible proxy (Ollama by default)
mt-serve
```

### Python SDK

```python
from memory_thread.sdk import MemoryClient

client = MemoryClient(namespace="demo", use_db=True)

eid = client.remember(
    "User prefers dark mode",
    source="user",
    confidence=0.95,
    authority=0.9,
)

results = client.recall("dark mode", min_truth_score=0.0)
print(results.format())
client.close()
```

### Proxy Server

```bash
mt-serve                                          # Ollama (default)
mt-serve --backend https://api.openai.com/v1      # OpenAI
mt-serve --backend https://api.openrouter.ai/v1   # OpenRouter
```

Point any OpenAI-compatible app to `http://localhost:8000/v1`. Memory injection, context retrieval, and secret redaction happen automatically.

---

## Architecture Overview

```
                    ┌──────────────────┐
                    │   MemoryClient    │  ← Public SDK (unchanged API)
                    │  remember/recall  │
                    └───────┬──────────┘
                            │
                ┌───────────┼──────────────┐
                ▼           ▼              ▼
         ┌──────────┐ ┌──────────┐ ┌──────────────┐
         │   WAL    │ │  Events  │ │ GraphEngine  │  ← In-memory iGraph (725 lines)
         │(crash    │ │(in-mem)  │ │              │
         │ safety)  │ │          │ │  725 lines   │
         └──────────┘ └──────────┘ └──────┬───────┘
                │              │          │
                ▼              ▼          ▼
         ┌────────────────────────────────────────┐
         │         Persistence Layer               │
         │  ┌──────────────────────────────────┐   │
         │  │ PostgreSQL                       │   │
         │  │ events (tsvector + GIN for FTS)  │   │
         │  │ entity_state                     │   │
         │  │ relations / threads / beliefs    │   │
         │  └──────────────────────────────────┘   │
         └────────────────────────────────────────┘
                                 │
                     ┌───────────┼──────────────────┐
                     ▼           ▼                  ▼
              ┌──────────┐ ┌──────────┐ ┌──────────────────┐
              │ Golden   │ │ Recall   │ │ SSE Event Bus    │
              │ Thread   │ │(graph    │ │(real-time pushes │
              │(causal   │ │ primary) │ │ to frontend)     │
              │ chain)   │ │          │ │                  │
              └──────────┘ └──────────┘ └──────────────────┘
```

**Backend is fully built:** FastAPI server (870 lines, 20+ endpoints), iGraph engine (725 lines), 35 service modules (9,595 total lines), SSE event bus, and 20 integration tests.

**Frontend is scaffolded:** React 19, D3, Three.js, Framer Motion, Zustand, TanStack Router, Tailwind v4 — Cognitive Renderer architecture designed, implementation pending.

---

## Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete system architecture (backend + frontend) with Mermaid diagrams |
| [API.md](docs/API.md) | SDK usage, API endpoints, durability modes |
| [SUMMARY.md](docs/SUMMARY.md) | Problem statement, solution overview, architecture summary, benchmarks |
| [THESIS.md](docs/THESIS.md) | Thesis-ready system description with claims and evaluation |

---

## Project Structure

```
memory_thread/                          # Python backend (BUILT)
├── sdk/                    # Public SDK
│   ├── client.py           # MemoryClient — main API surface
│   ├── models.py           # RecallResult, Memory, etc.
│   └── enrichment.py       # Async enrichment pipeline
├── cli/                    # CLI commands (Typer)
├── api/                    # FastAPI server
│   ├── server.py           # 20+ endpoints + SSE event stream (870 lines)
│   └── routers/            # Maintenance routes
├── services/               # 35 service modules (9,595 total lines)
│   ├── graph_engine.py     # iGraph cognitive graph (725 lines)
│   ├── golden_thread.py    # Causal chain tracing
│   ├── tms_service.py      # Truth vector math (459 lines)
│   ├── event_bus.py        # SSE fan-out for real-time events
│   ├── wal.py              # Write-ahead log (525 lines)
│   ├── decay_engine.py     # Freshness decay curves
│   ├── context_monitor.py  # Proactive context injection
│   ├── contemplator.py     # Reflection/consolidation
│   ├── pruner.py           # Memory pruning
│   ├── workflow_induction.py
│   ├── fact_store.py / belief_store.py
│   ├── galaxy_query.py     # Multi-agent OLAP queries
│   ├── timewarp_engine.py  # Temporal graph queries
│   ├── file_ingest_service.py
│   └── ... (35 total)
├── nervous/                # Security & access control
│   ├── vault.py            # Fernet-encrypted credential store
│   ├── galaxy_core.py      # Multi-agent orchestration
│   ├── client_registry.py  # API key registry
│   └── audit_ledger.py     # Audit trail
├── models/                 # Pydantic schemas
│   ├── events.py           # Event, TruthVector, EntityState
│   ├── entity.py           # Entity, MergeProposal
│   └── provenance.py       # Actor, Origin, ProvenanceEnvelope
├── db/                     # Database clients + migrations
│   ├── postgres_client.py
│   └── sqlite_client.py
├── config/                 # Pydantic-settings
│   └── settings.py
└── utils/                  # Health check, logging

frontend/                               # TypeScript frontend (SCAFFOLDED)
├── src/
│   ├── api/                # REST API wrapper, SSE client
│   ├── event-bus/          # Internal EventBus with typed events
│   ├── store/              # Zustand store (graph data, selection, filters)
│   ├── types/              # All type definitions
│   ├── components/
│   │   ├── AppShell.tsx            # Root wrapper
│   │   ├── LandingPage.tsx         # Cinematic intro
│   │   ├── MemorySpace.tsx         # /explore route
│   │   ├── SearchOverlay.tsx       # Minimal search input over canvas
│   │   ├── NodeInspector.tsx       # Detail slide-over panel
│   │   └── cognitive-field/        # Core rendering engine
│   │       ├── CognitiveCanvas.tsx      # React lifecycle
│   │       ├── CognitiveFieldEngine.ts  # Runtime orchestration ("brain stem")
│   │       ├── ParticleRenderer.ts      # Three.js GPU particles
│   │       ├── ShaderPipeline.ts        # GLSL vertex/fragment shaders
│   │       ├── FlowField.ts             # Ambient particle drift
│   │       ├── ForceSimulation.ts       # D3 physics only
│   │       ├── ActivationEngine.ts      # Visual BFS propagation
│   │       ├── AnimationDirector.ts     # Cognitive events → particle choreography
│   │       ├── CameraController.ts      # Inertia, focus, overshoot
│   │       ├── SelectionManager.ts      # Raycaster picking
│   │       └── InspectorManager.ts      # Open/close/populate NodeInspector
│   ├── App.tsx             # Root with TanStack Router
│   ├── main.tsx            # Entry point
│   └── index.css           # Tailwind v4 dark academic theme
├── package.json            # React 19, D3, Framer Motion, Zustand, etc.
├── vite.config.ts          # Vite 8 + React + Tailwind + API proxy
└── DESIGN_SPEC.md          # Original design spec (legacy)

docs/
├── ARCHITECTURE.md
├── API.md
├── SUMMARY.md
├── THESIS.md
└── README.md               # Documentation map
```

---

## Testing

```bash
pytest tests/ -q       # 20 test files
```

| Test | Verifies |
|------|----------|
| `test_api_endpoints.py` | All REST endpoints respond correctly |
| `test_postgres_integration.py` | PostgreSQL persistence layer |
| `test_latency_profile.py` | Write/read throughput benchmarks |
| `test_golden_thread_reconstruction.py` | Causal chain correctness via graph traversal |
| `test_truth_retrieval_quality.py` | Truth-weighted recall ranks high-truth memories higher |
| `test_memory_client_durability_modes.py` | Sync/batched durability boundaries, WAL flush, compaction |
| `test_wal_recovery.py` | Crash recovery at 5 sizes (10, 30, 50, 70, 90 entries) |
| `test_qdrant_dimension_guard.py` | Qdrant-free init + keyword recall fallback after removal |
| `test_namespace_isolation.py` | Cross-namespace reads blocked. Truth scores isolated. |
| `test_contradiction_accuracy.py` | Precision and recall of contradiction detection |
| `test_contradiction_edge.py` | Edge cases in contradiction detection |
| `test_contradiction_classifier.py` | Contradiction classifier |
| `test_decay_curves.py` | Freshness decay matches mathematical specification |
| `test_graph_export.py` | Graph JSON export correctness |
| `test_graceful_degradation.py` | Behavior under Postgres failures |
| `test_scale_ceiling.py` | Scale ceiling benchmarks |
| `test_event_bus.py` | SSE event bus pub/sub |

---

## Security

| Layer | Detail |
|-------|--------|
| **Vault Encryption** | Provider API keys encrypted at rest with Fernet (AES-CBC, 256-bit key derived from `MT_SECRET_KEY`). Not base64. |
| **API Authentication** | Optional `MT_API_KEY` bearer token verified via constant-time comparison on all routes. |
| **CORS** | Restricted to `MT_ALLOWED_ORIGINS` env var. Methods limited to GET, POST, DELETE, OPTIONS. |
| **SQL Injection** | All queries use parameterized `psycopg2.sql` identifiers — zero string interpolation. |
| **WAL Integrity** | Atomic compaction via `tempfile.mkstemp` + `os.replace`. No TOCTOU race. |
| **Proxy Guardrails** | Auto-redaction of API keys, private keys, SSNs, email, GitHub tokens, AWS keys. |
| **Secure SDK** | `SecureMemoryClient` restricts passthrough to explicit allowlist — no reflection bypass. |
| **RBAC** | Role-based access with clearance grades. Zero-auth `/su` escalation removed. |
| **Client Provisioning** | `mt client-admin create/list/revoke` — API key management with hashed secrets. One-time key reveal on creation. |

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <sub>Built with ❤️ for agents that need to <i>remember</i>, not just <i>search</i>.</sub>
</p>