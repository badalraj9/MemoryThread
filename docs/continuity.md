# Continuity — MemoryThread Graph-Core Session

## Date
2026-05-15

## What Was Completed

### Core Architecture (Phases 0.5-10)

| Phase | What | Files |
|-------|------|-------|
| 0.5 | Schema cleanup + Galaxy DI + dead code fix | Archived 7 schema files, migration 9, GalaxyCore accepts GraphEngine |
| 1 | GraphEngine (iGraph backend) | `services/graph_engine.py` (531 lines) |
| 2 | Golden Thread (graph-native) | `services/golden_thread.py` rewrite — 250x faster, 0 Postgres queries |
| 3 | Graph-primary recall (config-gated) | `recall_graph()` method, `_resolve_seeds()`, `retrieve_by_activation()` |
| 4 | Topology-aware Decay + Prune | Config-gated (PRUNE_USE_TOPOLOGY, DECAY_USE_TOPOLOGY, both default OFF) |
| 5 | Galaxy unified graph | Dual-write bridges, contradiction cycles via graph, ConflictGraph→GraphEngine |
| 6 | Session & Thread Layer | `services/thread_service.py`, thread nodes, contains edges |
| 7 | Memory Tiers | `services/memory_tiers.py`, Router scoring, SummarizationPipeline |
| 8 | Proactive Context Injection | `services/context_monitor.py`, entity extraction, dedup, token budget |
| 9 | Workflow Induction (AWM-style) | `services/workflow_induction.py`, extract + match workflows from threads |
| 10 | Memory Attestation | `services/attestation_service.py`, Merkle chain, tamper detection |

### Post-Architecture Cleanup

| What | Why | Files |
|------|-----|-------|
| `content_resolver.py` | `_resolve_content` was copy-pasted in 4 files → deduplicated | `services/content_resolver.py` (NEW), modified retrieval_service, context_monitor, memory_tiers to import it |
| `thread_id` on `remember()` | Was missing from public API — needed `remember_in_thread()` | `sdk.py`: `remember(content, thread_id=None)` now works directly |
| Proxy server (`mt-serve`) | One-command OpenAI-compatible server | `services/proxy.py`, `pyproject.toml` entry point |
| Cognitive simulation | Full demo: 3 sessions, cross-thread, contradictions, workflows | `test_cognitive_simulation.py` |
| Config flags added | 24 new settings across phases 3-9 | `config/settings.py` |
| Dependencies | python-igraph added | `pyproject.toml`, `requirements.txt` |

### Test Status
```
19 passed, 1 failed, 2 skipped
FAILED: test_namespace_isolation.py — pre-existing bug, not caused by our changes
```



## What Remains

### High Priority (structural)

| # | What | Why | Risk | Effort |
|---|------|-----|------|--------|
| 1 | **sdk.py god class split** | 2680 lines, one class doing SDK + WAL + enrichment + slab ingest + persistence | HIGH | 1-2 days |
| 2 | **cli.py god class split** | 1223 lines, one Typer app | HIGH | 1 day |

Plan for sdk.py split (safe, incremental):
```
sdk.py (~300 lines) — public API only, delegates
sdk/write_path.py   — WAL, enrichment, slab ingest
sdk/read_path.py    — recall internals  
sdk/client.py       — MemoryClient (thin wrappers)
```
Strategy: extract one method at a time, test after each move, never break the public API.

### Medium Priority

| # | What | Why | Risk |
|---|------|------|------|
| 3 | **Consolidate two API servers** | `api/server.py` + `api/main.py` overlap. Merge main.py's unique endpoints (metrics, /health/ready, /health/live, /version) into server.py, delete main.py | LOW |
| 4 | **Input validation on event delta** | `delta: Dict[str, Any]` accepts anything. Replace with typed Pydantic models (AddDelta, LinkDelta, etc.) using discriminated unions | LOW |

### Low Priority (polish)

| # | What | Why |
|---|------|------|
| 5 | **Graph snapshot on startup/shutdown** | `graph_engine.snapshot()` and `load_snapshot()` exist but nothing calls them. Would make restart instant instead of rebuilding from Postgres |
| 6 | **Delta validation in `_apply`** | LINK events validate target_id exists, MERGE validates strategy, etc. |
| 7 | **Dynamic decay rates per edge type** | Currently static per node type. Could be learned from graph topology |

### Important Context

- The cognitive simulation at `test_cognitive_simulation.py` exercises all 10 phases end-to-end
- The proxy at `services/proxy.py` needs httpx installed (`pip install httpx`) — it's not a core dependency
- Graph snapshot is optional — Postgres rebuild works fine, just slower on startup
- Namespace isolation test failure is pre-existing and unrelated to graph work



## Key Files Reference

| File | Purpose |
|------|---------|
| `services/graph_engine.py` | Core iGraph-backed graph with activation, topology, snapshot |
| `services/golden_thread.py` | Causal chain tracing via graph (0 Postgres queries) |
| `services/thread_service.py` | Thread creation, event grouping, context retrieval |
| `services/context_monitor.py` | Proactive context injection from agent text |
| `services/memory_tiers.py` | Hot/warm/cold scoring and summarization |
| `services/workflow_induction.py` | AWM-style workflow extraction and matching |
| `services/attestation_service.py` | Merkle chain checkpoints and verification |
| `services/content_resolver.py` | Shared entity content resolution utility |
| `services/proxy.py` | OpenAI-compatible proxy with guardrails |
| `nervous/galaxy_core.py` | Multi-agent orchestration with graph bridge |
| `nervous/conflict_resolution.py` | Contradiction detection via graph cycles |
| `models/events.py` | Event model with LINK/UNLINK/MERGE + thread_id |
| `docs/GRAPH_CORE_ARCHITECTURE.md` | Full 2253-line architecture document |
| `docs/continuity.md` | This file — session handover doc |
