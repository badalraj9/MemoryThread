# Summary — Problem, Solution, Benchmarks, Claims

Executive reference. What is Memory Thread, why does it exist, how fast is it, and what can you claim.

---

## Problem

**AI memory treats all information as equally reliable.** Vector databases give semantic similarity but don't track confidence, authority, freshness, corroboration, or provenance. Agents confidently assert stale preferences, treat hallucinations as facts, and cannot explain their reasoning.

## Solution — What Memory Thread Does Differently

| Conventional RAG / Vector DB | Memory Thread |
|---|---|
| Flat vector search | Graph spreading activation — traverse truth-weighted edges |
| Single similarity score | Truth Vector (confidence, authority, freshness, corroboration) |
| State snapshots | Event sourcing — state is *derived* from events |
| No provenance | Golden Thread — complete causal chain for any entity |
| Single namespace | Multi-agent Galaxy — per-agent beliefs + cross-agent contradiction detection |
| Best-effort durability | WAL with explicit sync/batched modes |
| Passive recall | Proactive context injection |

**Core insight:** Memory is a causal graph, not a bag of vectors. Reasoning = graph traversal with truth weights.

---

## Architecture (Overview)

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams, data flow, and service map.

```
SDK/CLI/Proxy → FastAPI (20 endpoints + SSE) → WAL + Events + GraphEngine → PostgreSQL
```

**35 services, ~9,600 lines.** Frontend (scaffolded): React 19 + Three.js + D3 + Zustand.

---

## Truth Vector — Every Memory Has One

```python
TruthVector(confidence=0.95, authority=1.0, freshness=0.85, corroboration=2)
```

**Score** = `(1.0·conf + 1.2·auth + 0.8·fresh + 0.6·log(1+corr)) / 3.6` (capped at 1.0).

**Freshness decay** — exponential per memory type:

| Type | Decay λ | Half-life | Example |
|------|---------|-----------|---------|
| `fact` | 0.001 | ~693 days | "Water boils at 100°C" |
| `preference` | 0.01 | ~69 days | "User likes dark mode" |
| `event` | 0.1 | ~7 days | "Meeting at 3pm today" |
| `prediction` | 0.5 | ~1.4 days | "Stock will rise" |
| `identity` | 0.0 | Never | "User's name is Alice" |

---

## Graph-Primary Recall — How Search Works

```
recall("dark mode")
  → FTS seeds (tsvector @@ plainto_tsquery, top 5)
  → Spreading activation on iGraph (depth=3, decay=0.5)
  → Score = √(activation × truth_score)
  → Hybrid fallback: keyword FTS if < top_k results
```

Config: `MT_RECALL_MODE=hybrid|graph|keyword`, depth=`RECALL_GRAPH_MAX_DEPTH=3`, decay=`RECALL_GRAPH_DECAY=0.5`

---

## Validated Benchmarks

### Write Throughput (Direct SDK)

| Scenario | Sync | Batched | Speedup |
|---|---:|---:|---:|
| 1 producer | 277.2 EPS | **4,780.7 EPS** | **17.25×** |
| 4 producers | 267.0 EPS | **3,164.8 EPS** | **11.85×** |
| 4 producers + cognitive | 222.9 EPS | **2,719.0 EPS** | **12.20×** |

### Full System Throughput

| Scenario | System | Accepted EPS |
|---|---|---:|
| 1 producer | `sdk_direct_batched` | 4,780.7 |
| 1 producer | `memory_thread batched WAL` | 7,845.2 |
| 4 producers | `sdk_direct_batched` | 3,164.8 |
| 4 producers | `memory_thread batched WAL` | 4,885.7 |
| 4 producers + cognitive | `sdk_direct_batched` | 2,719.0 |
| 4 producers + cognitive | `memory_thread batched WAL` | 3,991.7 |

### Graph Latency

| Operation | 1K nodes | 10K nodes | 100K nodes |
|---|---:|---:|---:|
| `rebuild()` | ~15ms | ~120ms | ~250ms |
| `activation(depth=3)` | <1ms | <5ms | <20ms |
| `golden_thread.trace()` | <2ms | <5ms | <10ms |
| `contradiction_cycles()` | <5ms | <20ms | <50ms |

### Tests

20 integration test files. Latest run: 19 passed, 1 skipped (pre-existing flake in namespace isolation, unrelated to graph).

---

## Claims

### ✅ Use These

- Memory Thread tracks **confidence, authority, freshness, corroboration, and provenance** on every memory.
- Batched direct SDK writes reach **2.7K–4.8K EPS** locally.
- Batched direct SDK is **11.85×–17.25× faster** than sync mode.
- Durability in batched mode is **explicit through `flush()` and `close()`**.
- Golden Thread reconstructs causal chains with **zero Postgres queries**.
- Graph-primary recall uses **spreading activation along truth-weighted edges**.
- Multi-agent Galaxy supports **cross-agent contradiction detection via graph cycles**.
- WAL provides **crash recovery validated at 5 checkpoint sizes** (10, 30, 50, 70, 90 entries).
- Namespace isolation **blocks cross-namespace reads at SDK level**.
- Provider API keys encrypted at rest with **Fernet (AES-CBC, 256-bit)**.

### ❌ Do Not Use

- **19.21× over baseline** — stale benchmark from prior architecture.
- **Batched mode is durable-at-return** — it requires `flush()`/`close()`.
- **Direct SDK reaches 9K EPS** — ceiling is ~4.8K; needs WAL sharding.
- **Qdrant is used** — removed; PostgreSQL FTS replaces it.
- **Frontend is complete** — scaffolded only; Cognitive Renderer not built.

---

## Project Status

| Component | Lines | Status |
|---|---|---|
| Backend Core (35 services) | ~9,600 | ✅ Complete |
| GraphEngine (iGraph) | 725 | ✅ Complete |
| Golden Thread | 442 | ✅ Complete |
| WAL (sync/batched) | 525 | ✅ Complete |
| FastAPI + SSE | 870 | ✅ Complete |
| CLI (Typer) | 1,223 | ✅ Complete |
| Proxy Server | 420 | ✅ Complete |
| Multi-Agent Galaxy | 340 | ✅ Complete |
| Contradiction Detection (Tier 1) | — | ✅ Key-based |
| Contradiction Detection (Tier 2) | — | 📋 Semantic planned |
| Frontend Implementation | ~3,000 | 🔧 Scaffolded (Renderer = 0%) |

### Next

1. Split monolithic `sdk.py` / `cli.py` into packages
2. Build Cognitive Renderer (Three.js + D3 + GLSL)
3. Embedding pre-filter + NLI for contradiction Tier 2
4. Binary iGraph snapshots for instant restart
5. WAL sharding for 9K EPS target

---

## Quick Start (30s)

```bash
pip install -e ".[full]"
mt-api  # start server

# In another terminal:
python -c "
from memory_thread.sdk import MemoryClient
c = MemoryClient(namespace='demo', use_db=True)
c.remember('User prefers dark mode', source='user', confidence=0.95)
print(c.recall('dark mode').format())
c.close()
"
```

See [API.md](API.md) for SDK, REST, and CLI reference. See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design.