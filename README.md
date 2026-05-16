<p align="center">
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="Status">
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-purple" alt="License">
  <img src="https://img.shields.io/badge/tests-20%2F20%20passing-success" alt="Tests">
  <img src="https://img.shields.io/badge/security-audited-important" alt="Security">
</p>

<h1 align="center">Memory Thread</h1>
<p align="center"><em>A truth-preserving, graph-native cognitive memory layer for AI agents</em></p>

---

## What is this?

Memory Thread is not a vector database. Memory isn't a bag of embeddings — it's a **causal graph** of events, entities, beliefs, and relationships. Memory Thread materializes this graph in memory (iGraph backend) and uses it as the primary cognitive fabric for retrieval, reasoning, and context management.

Every memory carries **provenance, confidence, authority, freshness, and corroboration** metadata. Retrieval uses **graph spreading activation** — not flat vector similarity — to find what matters.

---

## Features

| Capability | What it does |
|---|---|
| **Truth Vectors** | 4D scoring: confidence, authority, freshness, corroboration → normalized `truth_score` |
| **Event Sourcing** | Every write is an event. State is *derived*, enabling replay, audit, and causal tracing |
| **Graph-Native Recall** | iGraph spreading activation along truth-weighted edges — not vector similarity |
| **Golden Thread** | Complete causal chain for any entity (all events, antecedents, truth evolution) |
| **Memory Tiers** | Core (context window) → Episodic (iGraph) → Semantic (PostgreSQL) |
| **Proactive Context** | ContextMonitor injects relevant memories *without being queried* |
| **Workflow Induction** | AWM-style procedural memory from successful agent trajectories |
| **Merkle Attestation** | Tamper-proof checkpoint chain for enterprise/regulatory use |
| **Multi-Agent Galaxy** | Per-agent belief spaces with cross-agent contradiction detection |
| **WAL Durability** | Write-ahead log: `sync` mode (~277 EPS) or `batched` mode (~4,780 EPS) |
| **Namespace Isolation** | Per-namespace memory spaces with cross-namespace blocking |
| **Encrypted Vault** | Provider API keys encrypted at rest (Fernet AES, not base64) |
| **API Auth** | Optional `MT_API_KEY` bearer token on all HTTP endpoints |

---

## Quick Start

```bash
pip install -e ".[full]"

# CLI
mt --help

# API server
mt-api

# OpenAI-compatible proxy (with Ollama by default)
mt-serve
```

### In Python

```python
from memory_thread.sdk import MemoryClient

client = MemoryClient(namespace="demo", use_db=False)

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

Point any OpenAI-compatible app to `http://localhost:8000/v1`.

---

## Architecture

```
                     ┌──────────────┐
                     │  MemoryClient │  ← Public SDK (sdk/)
                     │ remember()   │
                     │ recall()     │
                     └──────┬───────┘
                            │
                ┌───────────┼──────────────┐
                ▼           ▼              ▼
         ┌──────────┐ ┌──────────┐ ┌──────────────┐
         │   WAL    │ │  Events  │ │ GraphEngine  │
         │(crash    │ │(in mem)  │ │(iGraph in    │
         │ safety)  │ │          │ │ memory)      │
         └──────────┘ └──────────┘ └──────┬───────┘
                │              │          │
                ▼              ▼          ▼
         ┌─────────────────────────────────────┐
         │        Persistence Layer            │
         │  ┌──────────┐  ┌──────────────────┐ │
         │  │PostgreSQL │  │ Qdrant (optional)│ │
         │  │ events   │  │ vector store     │ │
         │  │ entity_  │  │ fallback recall  │ │
         │  │ state    │  └──────────────────┘ │
         │  │ relations│                       │
         │  └──────────┘                       │
         └─────────────────────────────────────┘
                            │
                ┌───────────┼──────────────┐
                ▼           ▼              ▼
         ┌──────────┐ ┌──────────┐ ┌──────────────┐
         │ Golden   │ │ Recall   │ │ Decay/Prune  │
         │ Thread   │ │(graph    │ │(topology-    │
         │(graph    │ │ primary) │ │ aware)       │
         │ native)  │ │          │ │              │
         └──────────┘ └──────────┘ └──────────────┘
```

### Write Path

```
remember()
  → normalize metadata
  → create Event (TruthVector, action, actor, antecedents, thread_id)
  → WAL.append(event)
  → persist to PostgreSQL (events + entity_state)
  → WAL.commit(event)
  → GraphEngine.apply_event(event) — adds node + edges to iGraph
  → schedule async enrichment (Qdrant, embedding, NER, inference)
  → return entity_id
```

### Read Path

```
recall(query, mode="hybrid")
  → resolve query to seed nodes:
      1. UUID → direct graph lookup
      2. name/content → graph search
      3. vector fallback → Qdrant → graph seeds
  → GraphEngine.activation(seeds, max_depth=3, decay=0.5, threshold=0.3)
      — BFS along truth-weighted edges
      — seed starts at 1.0, each hop: edge.confidence × decay
  → score: sqrt(activation × truth_score)
  → fill from vector search if too few results
  → return top-K
```

### Graph Model

| Node | Label | Key Attributes |
|------|-------|----------------|
| Entity | `entity` | `entity_id, namespace, content, truth_vector, importance` |
| Event | `event` | `event_id, action, actor, timestamp, truth_vector, delta` |
| Belief | `belief` | `belief_id, agent_id, content, confidence, authority` |
| Agent | `agent` | `agent_id, authority` |
| Thread | `thread` | `thread_id, title, created_by, status` |
| Workflow | `workflow` | `workflow_id, title, success_count` |

| Edge | Direction | Purpose |
|------|-----------|---------|
| `modifies` | Event → Entity | Entity state timeline |
| `causes` | Event → Event | Causal DAG |
| `relates` | Entity → Entity | Knowledge graph |
| `about` | Belief → Entity | Belief target |
| `holds` | Agent → Belief | Belief ownership |
| `supports` / `contradicts` | Belief → Belief | Cross-agent agreement |
| `contains` | Thread → Event/Entity | Thread membership |
| `has_step` | Workflow → Step | Procedural ordering |

---

## Truth Vector

Every memory carries four dimensions, combined into a normalized score:

| Component | Range | Meaning |
|-----------|-------|---------|
| `confidence` | 0.0–1.0 | Certainty in the content |
| `authority` | 0.0–1.0 | Source trust (USER=1.0, AGENT=0.5) |
| `freshness` | 0.0–1.0 | Temporal relevance (exponential decay) |
| `corroboration` | 0+ | Independent confirmations (log scale) |

```python
score = (W1·conf + W2·auth + W3·fresh + W4·log(1+corr)) / (W1+W2+W3+W4)
```

Weights are configurable, defaulting to `[1.0, 1.2, 0.8, 0.6]`, normalized to sum to 1.0. Score capped at 1.0.

---

## CLI

```bash
mt                              # Full CLI with sub-commands
mt ask "what is the meaning of life"
mt search "quantum computing"
mt whoami
mt provider list
mt provider create groq --key <key>
mt client-admin list
mt galaxy list --depth 2
mt galaxy diff --ns1 alpha --ns2 beta
```

| Command | Purpose |
|---------|---------|
| `mt ask` | Chat with LLM + memory context |
| `mt search` | Semantic memory search |
| `mt whoami` | Show identity context |
| `mt status` | System health |
| `mt provider *` | CRUD for LLM providers |
| `mt client-admin *` | API key management |
| `mt galaxy *` | Schema inspection across namespaces |

---

## Durability

| Mode | Return | Durable | Throughput |
|------|--------|---------|------------|
| `sync` | After WAL flush | Each `remember()` | ~277 EPS |
| `batched` | After buffer accept | `flush()` or `close()` | ~4,780 EPS |

---

## Security

| Feature | Detail |
|---------|--------|
| **Vault Encryption** | Provider API keys encrypted at rest with Fernet (AES-CBC) |
| **API Authentication** | Optional `MT_API_KEY` bearer token on all routes |
| **CORS** | Restricted to `MT_ALLOWED_ORIGINS` env var, limited methods |
| **SQL Injection** | All queries parameterized — no string interpolation |
| **WAL Integrity** | Atomic compaction with `tempfile.mkstemp`, verified on recovery |
| **Secrets Guardrails** | Auto-redaction of API keys, private keys, PII in proxy |
| **Secure SDK** | Allowlisted method access on `SecureMemoryClient` |
| **Role System** | RBAC with clearance grades, `/su` zero-auth escalation removed |

---

## Tests

```bash
pytest tests/ -q
```

| Test | Coverage |
|------|----------|
| `test_golden_thread_reconstruction.py` | Causal chain correctness |
| `test_truth_retrieval_quality.py` | Truth-weighted recall quality |
| `test_memory_client_durability_modes.py` | Sync/batched durability |
| `test_wal_recovery.py` | Crash recovery (5 parametrized sizes) |
| `test_qdrant_dimension_guard.py` | Vector dimension mismatch safety |
| `test_namespace_isolation.py` | Cross-namespace blocking |
| `test_contradiction_accuracy.py` | Precision/recall of contradiction detection |
| `test_decay_curves.py` | Freshness decay matches paper spec |
| `test_graceful_degradation.py` | Behavior under dependency failures |

---

## Project Structure

```
memory_thread/
├── sdk/                    # Public SDK (client.py, models/, slab_ingest/)
├── cli/                    # CLI commands (main.py, provider.py, client_admin.py, galaxy.py)
├── api/                    # FastAPI server
├── services/               # Core services
│   ├── graph_engine.py     # iGraph materialized view
│   ├── golden_thread.py    # Causal chain tracing
│   ├── memory_tiers.py     # Hot/warm/cold management
│   ├── context_monitor.py  # Proactive context injection
│   ├── thread_service.py   # Session management
│   ├── workflow_induction.py
│   ├── attestation_service.py
│   ├── tms_service.py      # Truth vector math
│   └── wal.py              # Write-ahead log
├── nervous/                # Security & access
│   ├── vault.py            # Encrypted credential store
│   ├── access_control.py   # RBAC
│   ├── client_registry.py  # API key management
│   ├── audit_ledger.py     # Audit trail
│   └── galaxy_core.py      # Multi-agent orchestration
├── models/                 # Pydantic schemas
├── db/                     # PostgreSQL, Qdrant, SQLite clients
├── config/                 # Settings
└── utils/                  # Helpers, embeddings, secure_sdk
```

---

## Status

| Phase | Feature | Status |
|-------|---------|--------|
| SDK | Monolith split → `sdk/` package | ✅ |
| CLI | God class split into sub-commands | ✅ |
| 1 | GraphEngine (iGraph backend) | ✅ |
| 2 | Golden Thread (graph-native) | ✅ |
| 3 | Graph-primary recall | ✅ |
| 4 | Topology-aware decay + prune | ✅ |
| 5 | Multi-agent galaxy | ✅ |
| 6 | Session & thread layer | ✅ |
| 7 | Memory tiers | ✅ |
| 8 | Proactive context injection | ✅ |
| 9 | Workflow induction (AWM) | ✅ |
| 10 | Merkle attestation | ✅ |
| — | Security audit (12 fixes) | ✅ |
| — | Fernet vault encryption | ✅ |
| — | API auth + CORS restrict | ✅ |
