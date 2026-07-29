# Architecture — How It Works

Data flow, graph model, key services, and design rationale. Assumes you've read [SUMMARY.md](SUMMARY.md) for problem/benchmarks.

---

## Quick Answers

| Question | Answer | Code Location |
|---|---|---|
| Where does a `remember()` call go? | Event → WAL → PostgreSQL → GraphEngine (in-memory iGraph) → async enrichment | `sdk/client.py:remember()` |
| How does recall work? | FTS seed resolution → graph spreading activation → √(activation × truth_score) scoring | `services/retrieval_service.py` |
| What is GraphEngine? | In-memory iGraph rebuilt from event log on startup, updated incrementally on every write | `services/graph_engine.py` (725 lines) |
| What happens on crash? | WAL has every accepted write; GraphEngine rebuilds from PostgreSQL events table on restart | `services/wal.py` + `graph_engine.py:rebuild()` |
| How does the frontend get updates? | SSE delta stream (`/api/events/stream`) pushes graph mutations to connected clients | `services/event_bus.py` |
| How does multi-agent work? | Per-agent beliefs linked by `supports`/`contradicts` edges; contradiction cycles detected via graph | `nervous/galaxy_core.py` |

---

## Write Path

```
MemoryClient.remember()
  → 1. Normalize metadata (source → authority mapping)
  → 2. Create Event(action=PLANT, actor=USER|AGENT, truth_vector=..., delta=...)
  → 3. WAL.append(event)        # sync: flushed; batched: buffered
  → 4. PostgreSQL insert (events + entity_state)
  → 5. WAL.commit(event.id)     # second durability boundary
  → 6. GraphEngine.apply_event()  # incremental, microseconds
  → 7. Queue async enrichment (NER, relations)  # non-blocking
  → return entity_id
```

### Durability Boundaries

| Mode | `remember()` Returns After | Data Durable After | Throughput |
|---|---|---|---|
| `sync` | WAL append + commit flushed to disk | Each call | ~277 EPS |
| `batched` | WAL append + commit accepted to memory buffer | `flush()` or `close()` | ~4,780 EPS |

**Batched mode is NOT durable-at-return.** Use for ingestion pipelines; call `flush()` at checkpoints, `close()` on shutdown.

---

## Read Path (Graph-Primary Recall)

```
client.recall("dark mode")
  → FTS: search_vector @@ plainto_tsquery("dark mode") → top 5 entity_ids (seeds)
  → GraphEngine.activation(seeds, depth=3, decay=0.5, threshold=0.3)
      BFS from seeds: child_activation = parent × edge_confidence × decay
      Multiple paths to same node → MAX
      Stop when activation < threshold
  → Score = √(activation × truth_vector_score)
  → If < top_k results: keyword FTS fallback → hybrid fusion
```

**Why graph over vector search:** Vector search has no concept of causality, authority flow, or contradiction. Graph traversal provides reasoning — not just similarity — by following truth-weighted edges.

---

## Graph Model

### Nodes

| Type | Created When | Key Attributes |
|---|---|---|
| `entity` | First `remember()` for a concept | `entity_id`, `namespace`, `content`, `truth_vector`, `importance` |
| `event` | Every `remember()` call | `event_id`, `action`, `actor`, `timestamp`, `truth_vector`, `delta` |
| `belief` | Agent forms belief | `belief_id`, `agent_id`, `content`, `confidence`, `fact_id` |
| `agent` | Agent registration | `agent_id`, `authority` |

### Edges

| Type | From → To | Created By | Purpose |
|---|---|---|---|
| `modifies` | Event → Entity | Every `remember()` | Entity state timeline |
| `causes` | Event → Event | `antecedents` in event | Causal DAG |
| `relates` | Entity → Entity | `add_relation()` / LINK event | Knowledge graph |
| `about` | Belief → Entity | Belief creation | Belief target |
| `holds` | Agent → Belief | Belief creation | Ownership |
| `supports`/`contradicts` | Belief → Belief | `link_beliefs()` | Cross-agent agreement/conflict |

Every edge carries `confidence ∈ [0,1]`. Activation propagation: `child = parent × edge_confidence × decay`.

---

## Key Services

| Service | Lines | Responsibility |
|---|---|---|
| `services/graph_engine.py` | 725 | iGraph materialized view: `activation()`, `contradiction_cycles()`, `snapshot()` |
| `services/golden_thread.py` | 442 | Causal chain via graph BFS — 0 Postgres queries |
| `services/retrieval_service.py` | 180 | Orchestrates recall: FTS seeds → graph activation → scoring → fallback |
| `services/wal.py` | 525 | Write-ahead log: `append()`, `commit()`, `flush()`, `compact()` |
| `services/event_bus.py` | 380 | SSE fan-out for real-time frontend deltas |
| `services/tms_service.py` | 459 | Truth vector math: weights, normalization, decay |
| `services/context_monitor.py` | 280 | Proactive context injection: entity extraction, token budgeting |
| `services/decay_engine.py` | 106 | Freshness decay curves per memory type |
| `services/pruner.py` | 115 | Memory lifecycle scoring (opt-in topology-awareness) |
| `services/workflow_induction.py` | 320 | AWM-style procedural memory from agent trajectories |
| `services/attestation_service.py` | 290 | Merkle checkpoint chain for tamper-proof audit |
| `services/memory_tiers.py` | 190 | Hot/warm/cold routing with summarization |
| `services/proxy.py` | 420 | OpenAI-compatible proxy with memory injection + secret redaction |
| `nervous/galaxy_core.py` | 340 | Multi-agent belief spaces, dual-write bridges |
| `nervous/conflict_resolution.py` | 180 | Contradiction detection via graph cycles |

See the source in `memory_thread/services/` for full implementations (35 modules, ~9,600 lines).

---

## GraphEngine (`services/graph_engine.py`)

The engine is an in-memory iGraph materialized from the PostgreSQL events table. It is **not a separate database** — it's a derived view for fast graph traversal.

```python
# Lifecycle
rebuild(pg)        # Called once on startup. SELECT * FROM events → apply
apply_event(event) # Called on every remember(). Microsecond. Lock-protected.

# Traversal (read-safe, no lock)
activation(seeds, max_depth=3, decay=0.5, threshold=0.3, edge_types=None)
get_neighbors(node_id, direction="both", edge_types=None)
shortest_path(source, target, weight=None)
contradiction_cycles()

# Topology
centrality(node_id)
bridge_score(node_id)  # betweenness centrality
pagerank(personalized=None)
community()            # Leiden community detection

# Persistence
snapshot(path)           # Binary iGraph snapshot for fast restart
load_snapshot(path)      # ~50ms load vs ~250ms rebuild
sync_relations_to_db(pg) # Write edges back to relations table
```

**Thread safety:** iGraph C core is read-safe. Only `apply_event()` needs `threading.Lock` (microseconds). All traversal is lock-free.

---

## Golden Thread (`services/golden_thread.py`)

Causal chain for any entity, 0 Postgres queries:

```
trace(entity_id)
  → BFS over reversed "causes" edges → ancestor events
  → Collect all events that modified this entity
  → Build trace, verify consistency by replaying in-memory
  → Find related paths via graph neighbors
  → Classify events, generate narrative
  → Return GoldenThreadResult
```

**Why it's fast:** Old version made 3+ Postgres queries. New version does all traversal in iGraph memory.

---

## Multi-Agent Galaxy (`nervous/galaxy_core.py`)

```
register_agent(id, authority)     → agent node in GraphEngine + agents table
create_belief(agent, content, ...) → belief node + "holds" edge to agent + "about" edge to fact
link_beliefs(a, b, "supports")     → dual write: belief_bridges table + GraphEngine edge
query_galaxy_graph(query, agent)   → activation over supports/contradicts/about edges
detect_conflicts_fast()            → contradiction_cycles() in GraphEngine
```

**Dual write:** Data always goes to PostgreSQL first (source of truth), then to GraphEngine (for fast graph queries).

---

## Frontend Architecture (Scaffolded)

### Built (Structure Complete)

```
components/
├── AppShell.tsx              # Root wrapper
├── LandingPage.tsx           # Cinematic intro
├── MemorySpace.tsx           # /explore route
├── SearchOverlay.tsx         # Minimal search input over canvas
├── NodeInspector.tsx         # Slide-over detail panel
└── cognitive-field/
    ├── CognitiveCanvas.tsx         # React lifecycle (mount/resize/unmount)
    ├── CognitiveFieldEngine.ts     # "Brain stem" — runtime orchestration
    ├── ParticleRenderer.ts         # Three.js GPU particles (BufferGeometry)
    ├── ShaderPipeline.ts           # GLSL vertex/fragment shaders
    ├── FlowField.ts                # Ambient particle drift
    ├── ForceSimulation.ts          # D3 physics (positions only, no DOM)
    ├── ActivationEngine.ts         # Visual BFS propagation
    ├── AnimationDirector.ts        # Cognitive events → particle choreography
    ├── CameraController.ts         # Inertia, overshoot, smooth focus
    ├── SelectionManager.ts         # Raycaster picking
    └── InspectorManager.ts         # Open/close/populate NodeInspector
```

### SSE Data Sync

Frontend receives real-time deltas via EventSource at `/api/events/stream`:

```json
{
  "type": "delta",
  "seq": 142,
  "changes": {
    "nodes_added": [{"id": "uuid", "type": "entity", "truth_confidence": 0.85}],
    "nodes_removed": ["uuid1"],
    "nodes_updated": [{"id": "uuid", "truth_confidence": 0.7}],
    "edges_added": [{"source": "uuid", "target": "uuid", "type": "relates"}],
    "edges_removed": ["source:target"]
  }
}
```

On delta: apply to `graph-store.ts` (Zustand), re-heat D3 simulation with `alpha(0.3).restart()`, AnimationDirector choreographs response.

### Dual Activation

| Engine | Location | Purpose |
|---|---|---|
| `ActivationEngine` | Frontend (`ActivationEngine.ts`) | Visual BFS animation, 60 FPS, zero API calls |
| `GraphEngine.activation()` | Backend (`graph_engine.py`) | Truth-aware reasoning with authority/conflict/temporal decay |

---

## Configuration

All env vars. See `config/settings.py`.

```bash
# Recall
MT_RECALL_MODE=hybrid                    # graph | keyword | hybrid
RECALL_GRAPH_MAX_DEPTH=3
RECALL_GRAPH_DECAY=0.5
RECALL_FTS_FALLBACK=true

# WAL
WAL_DURABILITY_MODE=batched              # sync | batched
WAL_BATCH_SIZE=100
WAL_FLUSH_INTERVAL_MS=50
WAL_COMPACTION_THRESHOLD=10000

# Topology (opt-in, default OFF = zero regression)
PRUNE_USE_TOPOLOGY=false
DECAY_USE_TOPOLOGY=false

# Security
MT_API_KEY=                              # Bearer auth (optional)
MT_ALLOWED_ORIGINS=http://localhost:5173
MT_SECRET_KEY=                           # 32-byte base64 Fernet key

# Proxy
MT_PROXY_BACKEND=http://localhost:11434/v1
```

---

## Startup

1. Load settings from env
2. Connect PostgreSQL pool
3. `GraphEngine.rebuild(pg)` — `SELECT * FROM events ORDER BY timestamp` → apply each event (~250ms for 100K)
4. Load `relations` table → "relates" edges
5. Load `belief_bridges` → "supports"/"contradicts" edges
6. Start FastAPI (uvicorn) + SSE EventBus

**No PostgreSQL?** GraphEngine starts empty, populates on writes. Recall falls back to keyword-only via FTS.

---

## Key Files by Task

| Task | File |
|---|---|
| Change truth vector weights | `services/tms_service.py:calculate_truth_score()` |
| Modify recall algorithm | `services/retrieval_service.py` |
| Add graph edge type | `services/graph_engine.py:_apply()` + `models/events.py:ActionEnum` |
| Change decay curves | `services/decay_engine.py:calculate_freshness()` |
| Modify pruning | `services/pruner.py:calculate_pruning_score()` |
| Add API endpoint | `api/server.py` or `api/routers/` |
| Frontend event | `frontend/src/event-bus/EventBus.ts` |

---

## Design Decisions

| Decision | Why | Trade-off |
|---|---|---|
| iGraph over NetworkX | 10x faster at 100K+ nodes; C core; read-safe | Extra dependency |
| Event sourcing + GraphEngine | Graph is derived view; Postgres is source of truth | ~250ms rebuild on startup |
| Graph-primary recall | Topology IS reasoning; vector sim is insufficient | Cold start needs FTS seeds |
| Dual-write Galaxy | Zero data loss; belief_bridges table preserved | Minor write overhead |
| Config-gated topology | Zero regression risk; flip env var to rollback | Features off by default |
| SSE deltas not full refetch | Frontend at scale; incremental D3 re-heat | Reconnect needs full sync |
| Monochrome palette | Motion/brightness communicate; color for semantics | Less visual variety |

---

## Debugging

| Symptom | Likely Cause | Fix |
|---|---|---|
| Recall empty | GraphEngine not rebuilt, no FTS seeds | `GET /health/ready` |
| Slow `remember()` in batched | WAL flush interval too low | Increase `WAL_FLUSH_INTERVAL_MS` |
| Frontend not updating | SSE disconnected | Check `/api/events/stream` in Network tab |
| Cross-namespace leak | Namespace not passed | Always set `namespace` in `MemoryClient()` |
| Contradiction not found | Tier 2 (semantic) not built | Use `check_contradiction()` for Tier 1 (key-match) |