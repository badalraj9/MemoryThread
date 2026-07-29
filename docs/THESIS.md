# Thesis — A Truth-Preserving Graph-Native Memory Layer for AI Agents

Academic reference. Formal problem definition, core model, methodology, and evaluation.

---

## Abstract

Memory Thread is a cognitive memory layer for AI agents that attaches truth metadata and provenance to every memory. It combines event-sourced memory updates, truth-vector scoring, write-ahead logging, graceful degradation, and truth-aware graph-native recall. The current implementation validates correctness and durability properties while providing a measured high-throughput batched direct SDK mode reaching 2.7K–4.8K events per second locally.

---

## 1. Problem Definition

AI agents operate in environments where information arrives from sources of varying reliability — user input (high authority), model inference (low authority), system logs, and external APIs. Conventional memory systems treat all stored information as equally reliable, using vector similarity for retrieval without modeling:

- **Confidence** — the degree of certainty in the content itself
- **Authority** — the trust level of the information source  
- **Freshness** — the temporal relevance of a memory  
- **Corroboration** — the number of independent observations supporting a claim  
- **Causal Provenance** — the chain of events that led to a belief  

This creates a class of failures where agents:
1. Treat hallucinated model outputs as factual (no confidence tracking)
2. Weight unreliable sources equally with direct user statements (no authority)
3. Recall stale preferences as current requirements (no temporal decay)
4. Cannot explain *why* they believe something (no causal chain)
5. Cannot detect contradictions across time or between agents (no conflict resolution)

---

## 2. Core Model

### 2.1 Truth Vector

Every memory carries a 4-dimensional vector:

| Component | Domain | Semantics |
|---|---|---|
| `confidence` | [0.0, 1.0] | Certainty in the content — how sure are we this is correct? |
| `authority` | [0.0, 1.0] | Source trust level — USER=1.0, AGENT=0.5, SYSTEM=0.8 |
| `freshness` | [0.0, 1.0] | Temporal relevance — exponential decay from creation time |
| `corroboration` | ℕ₀ | Independent confirmations — scaled logarithmically |

The normalized truth score is a weighted average:

```
truth_score = (w₁·confidence + w₂·authority + w₃·freshness + w₄·log(1+corroboration)) / Σwᵢ
```

Default weights: `w = [1.0, 1.2, 0.8, 0.6]`, capped at 1.0. Weights are configurable and auto-normalize.

### 2.2 Freshness Decay

Freshness decays exponentially from the moment of creation:

```
freshness(t) = freshness₀ · e^(-λ · Δt)
```

| Memory Type | λ | Half-life | Rationale |
|---|---|---|---|
| `fact` | 0.001 | ~693 days | Foundational knowledge changes slowly |
| `preference` | 0.01 | ~69 days | User tastes evolve over months |
| `event` | 0.1 | ~7 days | Ephemeral by nature |
| `prediction` | 0.5 | ~1.4 days | Rapidly becomes obsolete |
| `identity` | 0.0 | ∞ | Immutable (user name, etc.) |

### 2.3 Event Sourcing

Memory Thread uses event sourcing rather than state snapshots. Every `remember()` creates an **Event** — an immutable record containing:

- The action (`PLANT`, `UPDATE`, `LINK`, `UNLINK`, `MERGE`)
- The actor (`USER`, `AGENT`, `SYSTEM`)
- A truth vector describing the event's epistemic status
- The delta (changed fields)
- Optional causal antecedents linking to prior events

Entity state is **derived** by replaying all events for that entity. This enables:
- **Replay**: reconstruct state at any point in time.
- **Auditability**: every change has complete provenance.
- **Golden Thread**: causal chain tracing without database queries.

### 2.4 Write-Ahead Log

Memory Thread uses an application-level WAL because a single logical memory write may span multiple storage systems (PostgreSQL events table, entity_state table, relations table, GraphEngine). The WAL acts as a unified durability boundary:

```
sync mode:   WAL.append() + flush → WAL.commit() + flush → return
batched mode: WAL.append() (buffer) → WAL.commit() (buffer) → return → flush()/close()
```

---

## 3. Graph-Native Retrieval

### 3.1 Graph Construction

Events materialize into an in-memory iGraph with typed nodes and truth-weighted edges:

- **Entity nodes** represent concepts, facts, and preferences
- **Event nodes** represent state changes with provenance
- **Belief nodes** represent agent-specific convictions
- **Edge types** encode causal (`causes`), temporal (`modifies`), relational (`relates`), and epistemic (`supports`, `contradicts`) relationships

### 3.2 Spreading Activation

Retrieval uses spreading activation — a BFS from seed nodes with signal decay:

1. **Seed resolution**: PostgreSQL full-text search (`tsvector @@ plainto_tsquery`) maps queries to entity IDs
2. **Signal propagation**: Each hop attenuates: `child_activation = parent × edge_confidence × decay_per_hop`
3. **Scoring**: `final_score = √(activation × truth_score)` — geometric mean of graph relevance and epistemic quality
4. **Hybrid fallback**: Keyword FTS supplements graph results when activation yields fewer than `top_k` results

This differs fundamentally from vector similarity: the graph encodes causal relationships and authority flow, so traversal embodies *reasoning* rather than *matching*.

### 3.3 Golden Thread

The Golden Thread reconstructs a complete causal chain for any entity by traversing the reversed `causes` and `modifies` edge structure. The trace includes every event that affected the entity, the truth vector at each step, narrative generation, and consistency verification — all server-side, using zero database queries.

---

## 4. Multi-Agent Belief Architecture

The Galaxy subsystem extends the core model for multi-agent scenarios:

- **Agents** register with an authority level and operate within namespace-isolated belief spaces
- **Beliefs** link to factual entities via `about` edges and to their originating agent via `holds` edges
- **Cross-agent links** (`supports`/`contradicts`) connect beliefs across agent boundaries via dual writes (PostgreSQL `belief_bridges` table + GraphEngine edges)
- **Contradiction detection** identifies cycles in the `contradicts` edge structure, enabling real-time conflict discovery

---

## 5. Evaluation

### 5.1 Write Throughput

Benchmark on single machine, local PostgreSQL. Events per second (EPS):

| Scenario | Sync | Batched | Speedup |
|---|---:|---:|---:|
| 1 producer, no cognitive work | 277.2 EPS | 4,780.7 EPS | 17.25× |
| 4 producers, no cognitive work | 267.0 EPS | 3,164.8 EPS | 11.85× |
| 4 producers + cognitive work | 222.9 EPS | 2,719.0 EPS | 12.20× |

Batched mode achieves these throughputs by accepting writes into a memory buffer; durability requires explicit `flush()` or `close()`.

### 5.2 Graph Operations

| Operation | 1K nodes | 10K nodes | 100K nodes |
|---|---:|---:|---:|
| Graph rebuild (full event replay) | ~15ms | ~120ms | ~250ms |
| Spreading activation (depth=3) | <1ms | <5ms | <20ms |
| Golden Thread trace | <2ms | <5ms | <10ms |
| Contradiction cycle detection | <5ms | <20ms | <50ms |

### 5.3 Crash Recovery

WAL recovery validated at 5 checkpoint sizes (10, 30, 50, 70, 90 committed entries). Post-crash rebuild produces identical graph state to pre-crash. Zero data loss in sync mode; in batched mode, writes since last `flush()` are lost by design.

### 5.4 Test Coverage

20 integration test files covering: API endpoints, PostgreSQL persistence, latency profiles, Golden Thread reconstruction, truth-quality ranking, durability boundaries, WAL recovery, namespace isolation, contradiction detection, decay curves, graph export, graceful degradation, and SSE event bus.

---

## 6. Related Work

| System | Approach | Limitations vs Memory Thread |
|---|---|---|
| Vector databases (Pinecone, Weaviate, Qdrant) | Embedding similarity | No truth metadata, no causal chains, no authority weighting |
| MemGPT / Letta | Stateful LLM memory | No formal truth model, no multi-agent support |
| LangChain Memory | Conversation buffering | No graph structure, no provenance tracking |
| Knowledge graphs (Neo4j, etc.) | Property graph model | No event sourcing, no truth vectors, slower recall |

Memory Thread is the only system that combines event-sourced provenance, truth-vector scoring, graph-native retrieval, and multi-agent belief modeling in a single coherent architecture.

---

## 7. Limitations and Future Work

- **Write throughput ceiling**: ~4.8K EPS with shared WAL; target 9K EPS requires WAL sharding or per-thread WAL files.
- **Cold-start recall**: Graph-dependent; falls back to FTS but with lower precision. Warm-up by pre-seeding from PostgreSQL.
- **Contradiction detection**: Current Tier 1 uses key-based matching. Tier 2 (embedding pre-filter + NLI classifier) would improve recall.
- **Frontend**: Architecture designed but Cognitive Renderer (Three.js particles + D3 physics) not yet implemented.
- **Formal semantics**: Crash-recovery model for batched mode is empirically validated but not formally specified.

---

## 8. Conclusion

Memory Thread demonstrates that a graph-native, truth-vector-aware memory layer can provide both high throughput (4.8K EPS batched) and rich epistemic guarantees (confidence, authority, freshness, corroboration, provenance). The system is production-ready for single-writer single-namespace deployments; multi-agent Galaxy extends the same guarantees to cross-agent scenarios. The cost of truth-awareness is modest: ~17% throughput overhead for full truth vector computation versus simple state storage, and ~250ms startup time for graph rebuild at 100K events.