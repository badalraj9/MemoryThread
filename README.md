# Memory Thread

Memory Thread is a **truth-preserving, graph-native cognitive memory layer** for AI agents. It stores memories with provenance, confidence, authority, freshness, and corroboration metadata, then retrieves them via **graph spreading activation** instead of flat vector scoring.

The key insight: memory isn't a bag of vectors — it's a **causal graph** of events, entities, beliefs, and their relationships. Memory Thread materializes this graph in memory (iGraph backend) and uses it as its primary cognitive fabric for retrieval, reasoning, and context management.

---

## Core Concepts

### Truth Vector

Every memory carries four dimensions of metadata:

| Component | Range | Meaning |
|-----------|-------|---------|
| `confidence` | 0.0–1.0 | Certainty in the content itself |
| `authority` | 0.0–1.0 | Trust level of the source (USER=1.0, AGENT=0.5) |
| `freshness` | 0.0–1.0 | Temporal relevance (decays over time) |
| `corroboration` | 0+ | Independent confirmations (logarithmic boost) |

Combined into a `truth_score = (conf×0.4 + auth×0.35 + fresh×0.25) + log1p(corroboration)×0.1`, capped at 1.0.

### Event Sourcing

Writes create **events**, not state snapshots. Entity state is **derived** from the event log. This enables replay, auditability, causal chain tracing (Golden Thread), and crash recovery.

### Materialized Graph

Every event, entity, belief, agent relationship, and thread is materialized into a **single in-memory iGraph**. The graph is rebuilt from PostgreSQL on startup (~250ms for 100K events) and updated incrementally on each write. All retrievals go through graph traversal — vector search is a fallback.

### WAL Durability

An application-level write-ahead log protects accepted operations across multiple storage systems (PostgreSQL, Qdrant, in-memory). Two modes: `sync` (durable at each call) and `batched` (durable at explicit `flush()` / `close()`).

---

## Architecture

### High-Level Data Flow

```
                   ┌──────────────┐
                   │  MemoryClient │  ← Public SDK (unchanged API)
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
  → create Event (with TruthVector, action, actor, antecedents, thread_id)
  → WAL.append(event) for crash recovery
  → persist to PostgreSQL (events + entity_state tables)
  → WAL.commit(event)
  → GraphEngine.apply_event(event) — adds node + edges to in-memory iGraph
  → schedule async enrichment (Qdrant indexing, embedding, NER, relation inference)
  → return entity_id
```

All action types (`PLANT`, `ADD`, `REMOVE`, `UPDATE`, `OBSERVE`, `INFER`, `LINK`, `UNLINK`, `MERGE`) produce consistent graph mutations.

### Read Path

```
recall(query, mode="hybrid")
  → resolve query to seed nodes:
      1. UUID match → direct graph lookup
      2. Entity name/content match → graph search
      3. Vector fallback → Qdrant semantic search → resolve to graph seeds
  → GraphEngine.activation(seeds, max_depth=3, decay_per_hop=0.5, truth_threshold=0.3)
      — BFS spreading activation along truth-weighted edges
      — seed starts at 1.0, each hop attenuates by edge.confidence × decay
      — multiple paths to same node → max activation wins
      — stops at threshold
  → score activated nodes by sqrt(activation × truth_score)
  → if mode="hybrid" and too few results: fill from Qdrant vector search
  → return top-K scored results
```

### Graph Model

| Node Type | Label | Key Attributes |
|-----------|-------|----------------|
| Entity | `entity` | `entity_id, namespace, entity_type, content, truth_vector, importance` |
| Event | `event` | `event_id, action, actor, namespace, timestamp, truth_vector, delta` |
| Belief | `belief` | `belief_id, agent_id, content, confidence, authority, fact_id` |
| Agent | `agent` | `agent_id, authority` |
| Thread | `thread` | `thread_id, title, created_by, started_at, status` |
| Workflow | `workflow` | `workflow_id, title, description, success_count` |
| Step | `step` | `step_id, description, order` |

| Edge Type | Direction | Description |
|-----------|-----------|-------------|
| `modifies` | Event → Entity | Entity state timeline |
| `causes` | Event → Event | Causal DAG (antecedents) |
| `relates` | Entity → Entity | Knowledge graph (typed relations via LINK/UNLINK) |
| `about` | Belief → Entity | Belief references a fact/entity |
| `holds` | Agent → Belief | Agent belief ownership |
| `supports` / `contradicts` | Belief → Belief | Cross-agent agreement/conflict |
| `contains` | Thread → Event/Entity | Thread membership |
| `has_step` | Workflow → Step | Procedural step ordering |
| `summarized_to` | Thread → Entity | Semantic summarization link |

Every edge carries truth-weighted confidence. Activation propagates along edges attenuated by `edge.confidence × decay_per_hop`.

---

## Components

### GraphEngine (`services/graph_engine.py`)
The single in-memory materialized view of all graph data. Backed by iGraph (C core, thread-safe reads). Provides spreading activation, centrality, bridge scores, PageRank, Leiden community detection, contradiction cycle detection, and snapshot/load. Rebuilt from PostgreSQL on startup, updated incrementally on each `remember()`.

### Golden Thread (`services/golden_thread.py`)
Traces the complete causal chain of an entity from origin to present state — all events, antecedents, truth evolution, and consistency verification. Uses GraphEngine (0 Postgres queries) instead of the old replay-based approach (~250x faster). Outputs a human-readable narrative with `render_rich()` for CLI.

### Memory Tiers (`services/memory_tiers.py`)
Three-tier memory management:

| Tier | Location | Access | Capacity |
|------|----------|--------|----------|
| **Core** | LLM context window (injected as system prompt) | Instant | ~8K tokens |
| **Episodic** | In-memory iGraph | ~1ms | Unlimited (RAM-bound) |
| **Semantic** | Summarized facts in PostgreSQL | ~10ms (reload) | Unlimited |

A `MemoryRouter` scores nodes for tier placement using activation, recency, centrality, and bridge scores. A `SummarizationPipeline` consolidates threads into extracted facts when they age out of episodic.

### Context Monitor (`services/context_monitor.py`)
Proactive context injection — the difference between a memory *database* (waits for query) and a memory *system* (surfaces what's relevant without being asked). On each agent turn:
1. Extracts entity mentions from agent text
2. Resolves them to graph nodes
3. Runs graph activation to find related context
4. Deduplicates against already-injected context
5. Returns formatted context to prepend to the agent's prompt
6. Prunes stale injections after N inactive turns

### Thread Layer (`services/thread_service.py`)
Groups events into conversation sessions via `contains` edges in the graph. Thread-aware recall returns sibling events (±5 positions for context). Threads can nest (parent/child for branching discussions). Thread search works across titles and event content.

### Workflow Induction (`services/workflow_induction.py`)
AWM-style procedural memory. Extracts reusable workflows from successful agent action trajectories in the event graph. Stores them as Workflow nodes with `has_step` edges. Semantic matching retrieves relevant workflows for agent input. Success counting enables confidence scoring.

### Attestation Service (`services/attestation_service.py`)
Merkle chain of event checkpoints for enterprise/regulatory use. Each checkpoint attests to system state at a point in time. Verification detects tampering — if any event or hash is modified, the chain breaks. Proves "at timestamp T, agent A knew fact F with confidence C."

### Content Resolver (`services/content_resolver.py`)
Shared utility that resolves entity node IDs to their latest content by finding the most recent `modifies` event. Used by retrieval, context monitor, and memory tiers — eliminates copy-pasted resolution logic.

### Galaxy Core (`nervous/galaxy_core.py`)
Multi-agent orchestration with per-agent fact/belief spaces in Qdrant, belief bridges (supports/contradicts), and cross-agent queries. Contradiction cycles detected via graph traversal. ConflictResolver uses authority, centrality, or temporal strategies.

### Proxy Server (`proxy.py`)
OpenAI-compatible API server (`mt-serve`). Works as a transparent middleware between any OpenAI-compatible backend (Ollama, vLLM, OpenAI, OpenRouter) and the client. Automatically:
- Remembers conversations via MT
- Injects relevant context via ContextMonitor
- Redacts secrets (API keys, private keys, PII) via guardrails
- Assigns thread IDs for session grouping

---

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Optional dependencies:

```bash
pip install -e ".[db]"       # PostgreSQL + Qdrant
pip install -e ".[api]"      # FastAPI + uvicorn
pip install -e ".[cli]"      # Typer + Rich
pip install -e ".[full]"     # all extras
```

## Basic Usage

```python
from memory_thread.sdk import MemoryClient

client = MemoryClient(
    namespace="demo",
    use_db=False,
    durability_mode="batched",
)

memory_id = client.remember(
    "User prefers dark mode",
    source="user",
    confidence=0.95,
    authority=0.9,
)

client.flush()
results = client.recall("dark mode", min_truth_score=0.0)
print(results.format())
client.close()
```

### Proxy Server

```bash
mt-serve                                          # Ollama backend (default)
mt-serve --backend https://api.openai.com/v1      # OpenAI
mt-serve --backend https://api.openrouter.ai/v1   # OpenRouter
```

Then point any OpenAI-compatible app to `http://localhost:8000/v1`.

### Durability Modes

| Mode | Return Boundary | Durable Boundary | Throughput |
|------|----------------|------------------|------------|
| `sync` | After WAL flush | Each `remember()` | ~277 EPS |
| `batched` | After WAL buffer accept | `flush()` or `close()` | ~4,780 EPS |

### Commands

| Command | Description |
|---------|-------------|
| `mt` | CLI entry point (Typer app, ~1223 lines) |
| `mt-api` | FastAPI server |
| `mt-serve` | OpenAI-compatible proxy with MT guardrails |
| `memorythread` | TUI control centre (Textual) |

---

## Key Files

| File | Purpose |
|------|---------|
| `memory_thread/sdk.py` | Public SDK — `MemoryClient` (2680 lines, to be split) |
| `memory_thread/models/events.py` | Event, EntityState, TruthVector, ActionEnum, ActorEnum |
| `memory_thread/services/graph_engine.py` | Core iGraph-backed graph (539 lines) |
| `memory_thread/services/golden_thread.py` | Causal chain tracing via graph (497 lines) |
| `memory_thread/services/thread_service.py` | Conversation session management (247 lines) |
| `memory_thread/services/context_monitor.py` | Proactive context injection (206 lines) |
| `memory_thread/services/memory_tiers.py` | Hot/warm/cold memory management (236 lines) |
| `memory_thread/services/workflow_induction.py` | AWM-style procedural memory (222 lines) |
| `memory_thread/services/attestation_service.py` | Merkle chain attestation (285 lines) |
| `memory_thread/services/content_resolver.py` | Entity content resolution utility (39 lines) |
| `memory_thread/services/pruner.py` | Topology-aware pruning (135 lines) |
| `memory_thread/services/decay_engine.py` | Topology-aware decay (142 lines) |
| `memory_thread/proxy.py` | OpenAI-compatible proxy (343 lines) |
| `memory_thread/nervous/galaxy_core.py` | Multi-agent orchestration (356 lines) |
| `memory_thread/nervous/conflict_resolution.py` | Contradiction detection & resolution |
| `memory_thread/config/settings.py` | All config flags (206 lines) |
| `docs/GRAPH_CORE_ARCHITECTURE.md` | Full architecture design doc (2252 lines) |
| `docs/continuity.md` | Session handover — what's built, what remains |

---

## Verification

```bash
pytest tests/ -q
pytest test_cognitive_simulation.py -q   # End-to-end: 3 sessions, cross-thread, contradictions
```

Key test files:
- `tests/test_golden_thread_reconstruction.py` — graph-native golden thread correctness
- `tests/test_truth_retrieval_quality.py` — truth-weighted recall quality
- `tests/test_memory_client_durability_modes.py` — sync/batched durability boundaries
- `tests/test_wal_recovery.py` — WAL crash recovery
- `tests/test_qdrant_dimension_guard.py` — vector dimension safety
- `tests/test_namespace_isolation.py` — namespace isolation

---

## Status

### Implemented

| Phase | Feature | Files |
|-------|---------|-------|
| 0.5 | Schema cleanup + Galaxy DI | Archived 7 schema files, GalaxyCore accepts GraphEngine |
| 1 | GraphEngine (iGraph backend) | `services/graph_engine.py` |
| 2 | Golden Thread (graph-native) | `services/golden_thread.py` — 250x faster, 0 Postgres queries |
| 3 | Graph-primary recall | `recall_graph()`, `_resolve_seeds()`, `retrieve_by_activation()` |
| 4 | Topology-aware decay + prune | Config-gated (PRUNE_USE_TOPOLOGY, DECAY_USE_TOPOLOGY) |
| 5 | Galaxy unified graph | Dual-write bridges, contradiction cycles via graph |
| 6 | Session & thread layer | `services/thread_service.py`, thread nodes, contains edges |
| 7 | Memory tiers | `services/memory_tiers.py`, Router scoring, SummarizationPipeline |
| 8 | Proactive context injection | `services/context_monitor.py`, entity extraction, dedup, token budget |
| 9 | Workflow induction (AWM-style) | `services/workflow_induction.py`, extract + match workflows |
| 10 | Memory attestation | `services/attestation_service.py`, Merkle chain, tamper detection |

### Remaining

| Priority | Task | Effort |
|----------|------|--------|
| HIGH | Split `sdk.py` god class (2680 lines → `sdk/` package) | 1-2 days |
| HIGH | Split `cli.py` god class (1223 lines) | 1 day |
| MEDIUM | Consolidate `api/server.py` + `api/main.py` | — |
| MEDIUM | Typed event delta validation (Pydantic discriminated unions) | — |
| LOW | Graph snapshot on startup/shutdown | — |
| LOW | Delta validation in `_apply` (LINK validates target_id exists, etc.) | — |
| LOW | Dynamic decay rates per edge type | — |

---

## Documentation

| File | Purpose |
|------|---------|
| `docs/README.md` | Documentation map |
| `docs/GRAPH_CORE_ARCHITECTURE.md` | Full 2252-line graph-neural core architecture |
| `docs/continuity.md` | Session handover — what's built and what remains |
| `docs/THESIS.md` | Thesis-ready system description |
| `test_cognitive_simulation.py` | Runnable end-to-end demo |
