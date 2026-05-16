# Graph-Neural Core Architecture

> **Canonical design document for integrating graph as the primary cognitive fabric of MemoryThread.**
> A new agent or developer can read this document and continue the implementation from any phase.

---

## Table of Contents

1. [Motivation & Design Goals](#1-motivation--design-goals)
2. [Core Insight: The Graph Is Already There](#2-core-insight-the-graph-is-already-there)
3. [Graph Model](#3-graph-model)
4. [System Architecture](#4-system-architecture)
5. [Component: GraphEngine](#5-component-graphengine)
6. [Component: Event Model Changes](#6-component-event-model-changes)
7. [Component: Golden Thread](#7-component-golden-thread)
8. [Component: Graph-Primary Recall](#8-component-graph-primary-recall)
9. [Component: Topology-Aware Decay & Prune](#9-component-topology-aware-decay--prune)
10. [Component: Galaxy Unified Graph](#10-component-galaxy-unified-graph)
11. [Risk Matrix](#11-risk-matrix)
12. [Phase Plan](#12-phase-plan)
13. [Testing Strategy](#13-testing-strategy)
14. [Key Design Decisions](#14-key-design-decisions)
15. [Appendix: iGraph vs NetworkX](#15-appendix-igraph-vs-networkx)

---

## 1. Motivation & Design Goals

### Problem Statement

MemoryThread's current retrieval is **flat**: every `recall()` embeds a query, scores each memory independently, and returns a ranked list. This ignores the **topological structure** that already exists in the data:

- Event antecedents form a causal DAG
- Entity relations form a knowledge graph
- Galaxy beliefs form a cross-agent belief graph
- Contradiction detection requires graph cycles

Flat retrieval = fast matching, bad reasoning. The graph topology IS the cognition.

### Design Goals

1. **Materialize the implicit graph** — the event log already IS a graph (entities = nodes, events = edges, antecedents = causal links). Make it traversable.
2. **Graph-primary retrieval** — query resolves to seed nodes → activation propagates along truth-weighted edges → return activated subgraph. This replaces flat vector scoring.
3. **Truth × Graph fusion** — truth vectors propagate through edges. Authority flows. Contradictions are cycles.
4. **Unify the 3 graph silos** — `relations` table, `belief_bridges`, and event `antecedents` all become edges in ONE materialized graph.
5. **Zero regression on existing API** — all public APIs (`remember`, `recall`, `flush`, `close`) keep the same signatures. Changes are internal or config-gated.

### Non-Goals

- Visual graph rendering (this is an infrastructure change, not a UI one)
- Replacing PostgreSQL (it stays as the event store and read-model persistence)
- Replacing the event-sourcing model (graph is a derived view, not a new primary store)
- Breaking existing WAL format (new action types serialize the same way)

---

## 2. Core Insight: The Graph Is Already There

The following features already operate on implicit graph structures. They just don't materialize them.

| Feature | What It Does | Implicit Graph | File | Lines |
|---------|-------------|----------------|------|-------|
| **Golden Thread** | Walks antecedents → classifies event chain → finds related paths → narrative | Causal DAG traversal | `services/golden_thread.py` | 442 |
| **Galaxy Schema** | Agents → facts → beliefs → bridges (supports/contradicts) | Multi-agent belief graph | `nervous/galaxy_core.py` | 250 |
| **Decay Engine** | Per-type exponential freshness decay over entity_state | Topology-aware node lifecycle | `services/decay_engine.py` | 106 |
| **Pruner** | Scores by recency + frequency + importance | Graph-aware GC | `services/pruner.py` | 115 |
| **AutoBridge** | Semantic search → relationship analysis → create typed edges | Automated edge induction | `nervous/auto_bridge.py` | 103 |
| **Retrieval** | 5-signal fusion scoring (vector, keyword, graph, importance, recency) | Flat scoring, graph path BROKEN | `services/retrieval_service.py` | 76 |
| **GraphService** | CRUD on `relations` table | No in-memory, Postgres-only | `services/graph_service.py` | 71 |

**Key insight:** The graph is already there. Every one of these features traverses or processes graph structures. But each one:
- Hits PostgreSQL for every hop (golden thread = N queries per event)
- Rebuilds its own ad-hoc graph from scratch (conflict resolution scans ALL events)
- Has no shared in-memory representation

A single `GraphEngine` that materializes the event log into an **in-memory iGraph** eliminates ALL of these round-trips and enables graph algorithms as first-class operations.

---

## 3. Graph Model

### Node Types

| Type | Label | Key Attributes | Source |
|------|-------|---------------|--------|
| Entity | `entity` | `entity_id, namespace, entity_type, content, truth_vector, created_at, updated_at, importance, access_count` | `events` table (projected), `entities` table |
| Event | `event` | `event_id, action, actor, namespace, timestamp, truth_vector, delta` | `events` table (each row = 1 node) |
| Belief | `belief` | `belief_id, agent_id, content, confidence, authority, fact_id` | Galaxy `beliefs` table |
| Agent | `agent` | `agent_id, authority` | Galaxy `agents` table |

### Edge Types

| Type | Direction | Attributes | Source | Maps To |
|------|-----------|------------|--------|---------|
| `causes` | Event → Event | — | Event `antecedents` array | Causal DAG |
| `modifies` | Event → Entity | `action` | Event `object_id` | Entity state timeline |
| `relates` | Entity → Entity | `relation_type, confidence, is_inferred, metadata` | `relations` table | Knowledge graph |
| `about` | Belief → Entity | — | Belief `fact_id` | Belief references entity |
| `holds` | Agent → Belief | `confidence` | Galaxy belief creation | Agent belief ownership |
| `supports` | Belief → Belief | `confidence` | Galaxy `belief_bridges` | Cross-agent agreement |
| `contradicts` | Belief → Belief | `confidence` | Galaxy `belief_bridges` | Cross-agent conflict |

### Truth on Edges

Every edge carries a **truth-weighted confidence**:

```
edge.confidence ∈ [0.0, 1.0]

For "relates" edges:   confidence × source_entity.truth_vector.authority
For "causes" edges:    event.truth_vector.confidence
For "supports"/"contradicts": bridge.confidence
```

When activation propagates along an edge, the propagated signal is attenuated by `edge.truth_weighted_confidence × decay_per_hop`.

### Graph Invariants

```
1. Every Event node has exactly 1 outgoing "modifies" edge to its object Entity
2. Every Event may have 0..N outgoing "causes" edges to antecedent Events
3. Every "causes" edge MUST point to an Event whose timestamp is earlier
   → invariant: the causal DAG is acyclic (enforced at insert)
4. Every belief bridges table row → exactly 1 edge in the graph
5. Every entity MUST be reachable from at least 1 Event via "modifies" edges
```

---

## 4. System Architecture

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
       │   WAL    │ │  Events  │ │ GraphEngine  │  ← NEW component
       │(crash    │ │(in mem)  │ │(iGraph in    │
       │ safety)  │ │          │ │ memory)      │
       └──────────┘ └──────────┘ └──────┬───────┘
              │              │          │
              ▼              ▼          ▼
        ┌────────────────────────────────────────┐
        │        Persistence Layer              │
        │  ┌──────────────────────────────────┐ │
        │  │PostgreSQL                        │ │
        │  │ events (search_vector tsvector   │ │
        │  │   + GIN index for FTS)           │ │
        │  │ entity_state                     │ │
        │  │ relations                        │ │
        │  └──────────────────────────────────┘ │
        └────────────────────────────────────────┘
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

### Read vs Write Path

**Write path (unchanged flow, GraphEngine added):**
```
remember()
  → normalize metadata
  → create Event
  → WAL.append(event)
  → persist to PostgreSQL (events + entity_state)
  → WAL.commit(event)
  → GraphEngine.apply_event(event)    ← NEW (non-blocking, synchronous)
  → schedule async enrichment (NER, relation inference)
  → return entity_id
```

**Read path (changes significantly):**
```
recall(query)
  → resolve query to seed nodes (entity match + FTS fallback)
  → GraphEngine.activation(seeds, max_depth=3, truth_threshold=0.3)
  → score activated subgraph by activation × truth_vector
  → if not enough results: fallback to keyword search via Postgres FTS
  → return scored results
```

### Startup Sequence

```
1. Load settings
2. Connect to PostgreSQL
3. GraphEngine.rebuild(pg)
   → Single query: "SELECT * FROM events ORDER BY timestamp"
   → Apply each event to iGraph (entities, events, antecedents, relations)
   → Load belief_bridges → add supports/contradicts edges
   → Load agents → add agent nodes
   → Verify invariants
5. Start API server / CLI
```

Total startup time for 100K events: ~250ms (iGraph), ~2s (NetworkX).

---

## 5. Component: GraphEngine

### File

`memory_thread/services/graph_engine.py` (NEW — ~350 lines)

### Responsibility

The **single in-memory materialized view** of all graph data in the system. Every component that needs graph traversal, topology, or relationship data goes through GraphEngine. It is rebuilt from the event log on startup and updated incrementally on each write.

### Interface

```python
class GraphEngine:
    """
    In-memory materialized graph backed by iGraph.
    Rebuilt from events on startup. Updated incrementally on each remember().
    Thread-safe for concurrent reads (iGraph C core is read-safe).
    """

    def __init__(self):
        self.graph: ig.Graph = ig.Graph(directed=True)
        self.node_index: Dict[str, str] = {}  # {entity_uuid: igraph_vertex_name}

    # ── Lifecycle ──────────────────────────────────────────

    def rebuild(self, pg: PostgresClient) -> None:
        """FULL REBUILD from PostgreSQL events table. Called once on startup."""

    def apply_event(self, event: Event) -> None:
        """Apply one event to the graph. Called on every remember()."""

    def clear(self) -> None:
        """Reset graph to empty. For testing."""

    # ── Traversal ──────────────────────────────────────────

    def activation(
        self,
        seeds: List[str],
        max_depth: int = 3,
        decay_per_hop: float = 0.5,
        truth_threshold: float = 0.0,
        edge_types: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Spreading activation from seed nodes.
        Returns {node_id: activation_score} where activation_score ∈ [0, 1].
        Activation = seed_activation × Π(edge_confidence × decay) per path.
        Multiple paths to same node → max activation is kept.
        """

    def get_neighbors(
        self, node_id: str, direction: str = "both", edge_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """Get immediate neighbors (replaces GraphService.get_relations)."""

    def shortest_path(
        self, source_id: str, target_id: str, weight: Optional[str] = None
    ) -> List[str]:
        """Shortest path between two nodes (replaces QueryEngine.find_path)."""

    def subgraph(self, node_ids: List[str]) -> "ig.Graph":
        """Extract induced subgraph for a set of nodes."""

    # ── Topological Analytics ──────────────────────────────

    def centrality(self, node_id: str) -> float:
        """Degree centrality of node."""

    def bridge_score(self, node_id: str) -> float:
        """Betweenness centrality — how many shortest paths pass through this node."""

    def pagerank(self, personalized: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """PageRank with optional personalization vector."""

    def community(self) -> List[List[str]]:
        """Leiden community detection. Returns groups of node_ids."""

    def contradiction_cycles(self) -> List[List[str]]:
        """Find cycles in the graph formed by 'contradicts' edges."""

    # ── Persistence ────────────────────────────────────────

    def sync_relations_to_db(self, pg: PostgresClient) -> None:
        """Write all 'relates' edges to the relations table (read-model sync)."""

    def snapshot(self, path: str) -> None:
        """Binary snapshot of the iGraph to disk (fast restart)."""

    def load_snapshot(self, path: str) -> bool:
        """Load binary snapshot. Returns False if snapshot doesn't exist or is stale."""

    # ── Internal ───────────────────────────────────────────

    def _ensure_node(self, entity_id: str, node_type: str, **attrs) -> str:
        """Add node if not exists, return its vertex name."""

    def _resolve(self, entity_id: str) -> Optional[str]:
        """Resolve UUID to iGraph vertex name. Returns None if not in graph."""
```

### Implementation Details

**Rebuild from events:**
```python
def rebuild(self, pg):
    rows = pg.fetch_all("SELECT * FROM events ORDER BY timestamp")
    for row in rows:
        event = Event.model_validate(row)  # or dict parse
        self._apply(event)

    # Load relations table → "relates" edges
    rels = pg.fetch_all("SELECT * FROM relations")
    for rel in rels:
        self.graph.add_edge(
            str(rel['source_entity_id']),
            str(rel['target_entity_id']),
            type="relates",
            relation_type=rel['relation_type'],
            confidence=rel['confidence'],
            metadata=rel.get('metadata', {}),
        )

    # Load belief_bridges → "supports"/"contradicts" edges
    bridges = pg.fetch_all("SELECT * FROM belief_bridges")
    for bridge in bridges:
        self.graph.add_edge(
            str(bridge['belief_a_id']),
            str(bridge['belief_b_id']),
            type=bridge['relationship'],  # "supports" or "contradicts"
            confidence=bridge['confidence'],
        )
```

**apply_event handles all action types:**
```python
def _apply(self, event: Event):
    entity_id = str(event.object_id)
    event_id = str(event.id)

    # 1. Ensure entity node exists
    self._ensure_node(entity_id, type="entity", namespace=event.namespace)

    # 2. Create event node
    self.graph.add_vertex(
        event_id,
        type="event",
        action=event.action.value,
        actor=event.actor.value,
        namespace=event.namespace,
        timestamp=event.timestamp.isoformat(),
        truth_confidence=event.truth_vector.confidence,
        truth_authority=event.truth_vector.authority,
        truth_freshness=event.truth_vector.freshness,
    )

    # 3. Edge: event → entity (modifies)
    self.graph.add_edge(event_id, entity_id, type="modifies", action=event.action.value)

    # 4. Edge: antecedents → this event (causes)
    for ant in event.antecedents:
        ant_id = str(ant)
        if ant_id in self.graph:  # antecedent might be from a different namespace
            self.graph.add_edge(ant_id, event_id, type="causes")

    # 5. Handle LINK action (create typed edge between entities)
    if event.action == ActionEnum.LINK and "target_id" in event.delta:
        target_id = str(event.delta["target_id"])
        rel_type = event.delta.get("relation_type", "related_to")
        self._ensure_node(target_id, type="entity")
        self.graph.add_edge(
            entity_id, target_id,
            type="relates",
            relation_type=rel_type,
            confidence=event.truth_vector.confidence,
            is_inferred=event.delta.get("is_inferred", False),
        )

    # 6. Handle UNLINK action (remove typed edge between entities)
    if event.action == ActionEnum.UNLINK and "target_id" in event.delta:
        target_id = str(event.delta["target_id"])
        rel_type = event.delta.get("relation_type")
        # Find and remove matching edges
        edges_to_remove = []
        for e in self.graph.es:
            if (e.source == entity_id and e.target == target_id
                    and e["type"] == "relates"
                    and (rel_type is None or e["relation_type"] == rel_type)):
                edges_to_remove.append(e.index)
        for idx in sorted(edges_to_remove, reverse=True):
            self.graph.delete_edges(idx)
```

**Activation propagation:**
```python
def activation(self, seeds, max_depth=3, decay_per_hop=0.5,
               truth_threshold=0.0, edge_types=None):
    """
    BFS-based spreading activation.
    
    Algorithm:
    1. Each seed starts with activation = 1.0
    2. For each hop:
       a. Find all outgoing edges from current frontier
       b. Filter by edge_types (if specified)
       c. Compute propagated activation:
          activation(child) = activation(parent) × edge_confidence × decay
       d. If multiple paths reach same node, keep MAX
       e. If activation < truth_threshold, stop propagating
    3. Return {node_id: activation_score} for all reached nodes
    """
    activation_map = {seed: 1.0 for seed in seeds if seed in self.graph}
    frontier = set(seeds)
    visited = set(seeds)

    for depth in range(max_depth):
        next_frontier = set()
        for node in frontier:
            current_act = activation_map.get(node, 0.0)
            edges = self.graph.incident(node, mode="out")
            for e in edges:
                target = self.graph.vs[e.target]["name"]
                if edge_types and e["type"] not in edge_types:
                    continue
                edge_conf = e.get("confidence", 1.0) if "confidence" in e.attributes() else 1.0
                propagated = current_act * edge_conf * decay_per_hop
                if propagated < truth_threshold:
                    continue
                if propagated > activation_map.get(target, 0.0):
                    activation_map[target] = propagated
                if target not in visited:
                    next_frontier.add(target)
                    visited.add(target)
        frontier = next_frontier
        if not frontier:
            break

    return activation_map
```

### Thread Safety

iGraph's C core is **read-safe for concurrent access**. Writes (apply_event) must be serialized:
- Use a `threading.Lock` around `_apply()` (fast — microsecond-scale)
- `activation()`, `centrality()`, etc. need no lock (C core is safe)

```
GraphEngine.read_lock = threading.Lock()   # for apply_event only
# All traversal methods run lock-free
```

### Error Handling

```
- Missing antecedent (antecedent event not yet in graph):
  → Log warning and skip edge. Eventual consistency.
- Duplicate edge (same source, target, type):
  → iGraph allows MultiDiGraph. We keep duplicates with different timestamps.
  → On conflict edges, keep ALL (multiple contradictions over time).
- Database unavailable at startup:
  → GraphEngine starts empty, populates as events are remembered.
  → Graceful degradation: recall falls back to keyword-only via FTS.
```

---

## 6. Component: Event Model Changes

### File

`memory_thread/models/events.py` — +3 lines

### Changes

```python
class ActionEnum(str, Enum):
    PLANT = "PLANT"     # existing
    ADD = "ADD"         # existing
    REMOVE = "REMOVE"   # existing
    UPDATE = "UPDATE"   # existing
    OBSERVE = "OBSERVE" # existing
    INFER = "INFER"     # existing
    LINK = "LINK"       # NEW: create typed edge between two entities
    UNLINK = "UNLINK"   # NEW: remove typed edge
    MERGE = "MERGE"     # NEW: merge two entities into one
```

### LINK Event Payload

When `action == "LINK"`, the `delta` dict must contain:

```json
{
  "target_id": "uuid-of-target-entity",
  "relation_type": "works_with|trusts|located_in|part_of|...",
  "is_inferred": false,
  "metadata": {"source": "explicit", ...}
}
```

The `object_id` of the event is the **source** entity. The `delta.target_id` is the **target** entity. The event's `truth_vector.confidence` becomes the edge weight.

### UNLINK Event Payload

```json
{
  "target_id": "uuid-of-target-entity",
  "relation_type": "works_with"  // optional, removes all edges if omitted
}
```

### MERGE Event Payload

```json
{
  "target_id": "uuid-of-target-entity",
  "strategy": "authority|temporal"
}
```

Merges source entity (object_id) into target entity (delta.target_id). All edges from source are rewired to target.

### SDK Method Additions

In `memory_thread/sdk.py` (additive, non-breaking):

```python
class MemoryClient:
    def add_relation(self, source_id, target_id, relation_type, confidence=1.0, metadata=None):
        """Emit a LINK event to create a typed edge between entities."""

    def remove_relation(self, source_id, target_id, relation_type=None):
        """Emit an UNLINK event to remove typed edge(s)."""

    def merge_entities(self, source_id, target_id, strategy="authority"):
        """Emit a MERGE event to consolidate two entities."""
```

All three methods are convenience wrappers around `remember()` with the appropriate action type. They go through the same WAL + event sourcing path as any other memory operation.

---

## 7. Component: Golden Thread

### File

`memory_thread/services/golden_thread.py` — rewrite internals (~442 lines → ~300 lines)

### What Stays

- `GoldenThreadResult` dataclass — **unchanged**
- `ThreadEvent` dataclass — **unchanged**
- `trace(entity_id)` public method signature — **unchanged**
- Event classification logic (`_classify_event_type`) — **unchanged**
- Narrative generation (`_generate_narrative`) — **unchanged**
- `render_rich()` for CLI — **unchanged**

### What Changes

**Before (3 Postgres round-trips per trace):**
```python
def trace(self, entity_id):
    self.ancestry.rebuild_cache(entity_id)    # 1 Postgres query
    trace = self.replay.capture_trace(entity_id)  # N Postgres queries
    is_consistent = self.replay.replay_trace(trace)  # N Postgres queries
    related_paths = self._find_related_paths(entity_id)  # 1 Postgres query
    ...
```

**After (0 Postgres round-trips per trace):**
```python
def trace(self, entity_id, namespace=None):
    # All data is already in-memory via GraphEngine
    entity_node = str(entity_id)
    
    # Collect ancestor events via BFS over "causes" edges (reversed)
    ancestor_events = self._collect_ancestors(entity_node)
    
    # Collect events that modified this entity
    entity_events = self._collect_entity_events(entity_node)
    
    # Build trace dict in the same format as ReplayService.capture_trace
    trace = self._build_trace(entity_node, ancestor_events, entity_events)
    
    # Verify consistency (in-memory, no DB)
    is_consistent, inconsistencies = self._verify_consistency(trace)
    
    # Find related paths via graph neighbors
    related_paths = self._graph_neighbors_paths(entity_node)
    
    # Build thread events (same classification logic, different source)
    thread_events = self._build_thread_events(trace)
    
    # Same result construction
    ...
```

**Key change:** `ReplayService`, `AncestryCache`, `QueryEngine` are no longer used directly. The `_find_related_paths` method stops hitting Postgres and reads from GraphEngine instead.

### Internal Methods

```python
def _collect_ancestors(self, entity_node: str) -> List[Dict]:
    """BFS over reversed 'causes' edges to find all ancestor events."""
    queue = [entity_node]
    visited = set()
    ancestors = []
    
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        
        # Follow "causes" edges backwards (target → source)
        for e in self.graph.es:
            if e["type"] == "causes" and self.graph.vs[e.target]["name"] == node:
                source = self.graph.vs[e.source]["name"]
                queue.append(source)
                ancestors.append(self._node_to_event_dict(e.source))
    
    return ancestors

def _collect_entity_events(self, entity_node: str) -> List[Dict]:
    """Get all events that modified this entity, in chronological order."""
    events = []
    for e in self.graph.es:
        if e["type"] == "modifies" and e.target == entity_node:
            events.append(self._node_to_event_dict(e.source))
    events.sort(key=lambda x: x.get("timestamp", ""))
    return events

def _verify_consistency(self, trace: Dict) -> Tuple[bool, List[str]]:
    """Verify that replaying events produces the same current state."""
    # Same logic as ReplayService.replay_trace but reads from graph
    derived_state = {}
    inconsistencies = []
    
    for evt in trace.get("events", []):
        delta = evt.get("delta", {})
        for key, value in delta.items():
            if key in derived_state and derived_state[key] != value:
                inconsistencies.append(f"Field '{key}' changed: {derived_state[key]} → {value}")
            derived_state[key] = value
    
    final_state = trace.get("final_state", {})
    for key, value in final_state.items():
        if key in derived_state and derived_state[key] != value:
            inconsistencies.append(f"Replay mismatch for '{key}': {derived_state[key]} vs {value}")
    
    return len(inconsistencies) == 0, inconsistencies

def _graph_neighbors_paths(self, entity_node: str) -> List[Dict]:
    """Get related paths from GraphEngine instead of GraphService."""
    neighbors = graph_engine.get_neighbors(entity_node, direction="both")
    return [
        {
            "source": str(entity_node),
            "target": n.get("target", ""),
            "relation": n.get("relation_type", "UNKNOWN"),
            "confidence": n.get("confidence", 0.0),
        }
        for n in neighbors[:10]
    ]
```

### Migration Strategy

1. Implement the graph-native version alongside the existing one
2. Run both in parallel during development, compare outputs
3. Golden thread narrative must be identical (or better) for all test entities
4. Only after output parity is confirmed, remove the old Postgres-heavy path

---

## 8. Component: Graph-Primary Recall

### File

`memory_thread/sdk.py` — recall method changes (~50 lines)
`memory_thread/services/retrieval_service.py` — rewrite (~76 lines → ~100 lines)

### The Core Change

**Before:** Vector search was primary. Graph was dead code (broken import).

```
embed(query) → Qdrant search → flat score → sort → return top K
```

**After:** Graph activation is primary. Postgres FTS resolves seeds.

```
FTS query → entity_ids (seeds) → graph activation → score → return
                                    ↓
               (fallback) keyword search via FTS if too few results
```

### New Recall Pipeline

```python
def recall(
    self,
    query: str,
    top_k: int = 10,
    min_truth_score: float = 0.0,
    namespace: Optional[str] = None,
    mode: str = "hybrid",  # "graph" | "keyword" | "hybrid"
    max_graph_depth: int = 3,
    graph_decay: float = 0.5,
) -> List[Dict]:
    """
    Recall memories using graph-primary retrieval with keyword fallback.
    
    Args:
        mode: "graph" = graph activation only
              "keyword" = keyword search via Postgres FTS only
              "hybrid" = graph primary, keyword fallback (default)
    """
    if mode == "keyword":
        return self._recall_keyword(query, top_k)
    
    # Step 1: Resolve query to seed nodes via FTS
    seeds = self._resolve_query_to_nodes(query)
    
    # Step 2: Spreading activation
    activated = graph_engine.activation(
        seeds=seeds,
        max_depth=max_graph_depth,
        decay_per_hop=graph_decay,
        truth_threshold=min_truth_score,
        edge_types=["relates", "causes", "supports"],
    )
    
    # Step 3: Score activated nodes by activation × truth
    scored = self._score_activated(activated)
    
    # Step 4: Fallback if graph returned too few results
    if mode == "hybrid" and len(scored) < top_k:
        keyword_results = self._recall_keyword(query, top_k - len(scored))
        scored = self._hybrid_fusion(scored, keyword_results)
    
    return scored[:top_k]
```

### Seed Resolution

```python
def _resolve_query_to_nodes(self, query: str) -> List[str]:
    """
    Find seed nodes for a query via Postgres FTS.
    
    Strategy:
    1. Check if query contains explicit entity mentions (names/UUIDs)
    2. If so, resolve to existing graph nodes
    3. If not, use Postgres FTS to find matching entities
    4. Return top 5 matching nodes as seeds
    """
    seeds = []
    
    # 1. UUID match
    try:
        uuid.UUID(query.strip())
        entity_node = str(query.strip())
        if entity_node in graph_engine.graph:
            seeds.append(entity_node)
    except ValueError:
        pass
    
    # 2. Named entity resolution (from content)
    if not seeds:
        for v in graph_engine.graph.vs:
            if v["type"] == "entity":
                content = v.get("content", "")
                name = v.get("name", "")
                if query.lower() in str(content).lower() or query.lower() in str(name).lower():
                    seeds.append(v["name"])
    
    # 3. Postgres FTS fallback for seed resolution
    if not seeds:
        fts_results = pg.execute("""
            SELECT entity_id FROM events
            WHERE search_vector @@ plainto_tsquery('english', %s)
            AND object_id IS NOT NULL
            LIMIT 5
        """, (query,))
        for row in fts_results:
            entity_id = str(row['entity_id'])
            if entity_id in graph_engine.node_index:
                seeds.append(entity_id)
    
    return seeds[:5]
```

### Activation Scoring

```python
def _score_activated(self, activated: Dict[str, float]) -> List[Dict]:
    """
    Convert activation map to scored results.
    Score = activation × truth_score (geometric mean).
    """
    scored = []
    for node_id, activation_score in activated.items():
        if node_id not in graph_engine.graph:
            continue
        
        node = graph_engine.graph.vs.find(name=node_id)
        if node["type"] != "entity":
            continue  # only return entity nodes as results
        
        truth_vector = {
            "confidence": node.get("truth_confidence", 0.5),
            "authority": node.get("truth_authority", 0.5),
            "freshness": node.get("truth_freshness", 0.5),
        }
        truth_score = calculate_truth_score(truth_vector)
        
        final_score = math.sqrt(activation_score * truth_score)
        
        scored.append({
            "id": node_id,
            "content": node.get("content", ""),
            "score": final_score,
            "activation": activation_score,
            "truth_score": truth_score,
            "node_type": node["type"],
        })
    
    return sorted(scored, key=lambda x: -x["score"])
```

### Revision of retrieval_service.py

The existing `retrieval_service.py` is largely replaced. The new version:

```python
# memory_thread/services/retrieval_service.py
# Replaces: flat scoring pipeline with graph-primary activation

from memory_thread.services.graph_engine import graph_engine

def retrieve_by_activation(
    seeds: List[str],
    top_k: int = 10,
    max_depth: int = 3,
    decay: float = 0.5,
    truth_threshold: float = 0.0,
) -> List[Dict]:
    """Graph-primary retrieval via spreading activation."""
    activated = graph_engine.activation(
        seeds=seeds,
        max_depth=max_depth,
        decay_per_hop=decay,
        truth_threshold=truth_threshold,
    )
    return _score_and_sort(activated)

def retrieve_by_keyword(query: str, top_k: int = 10) -> List[Dict]:
    """Keyword retrieval via Postgres FTS."""
    candidates = pg.execute("""
        SELECT entity_id, ts_rank(search_vector, plainto_tsquery('english', %s)) AS score
        FROM events
        WHERE search_vector @@ plainto_tsquery('english', %s)
        ORDER BY score DESC
        LIMIT %s
    """, (query, query, top_k))
    return [{"id": str(c["entity_id"]), "score": c["score"]} for c in candidates]

def _score_and_sort(activated: Dict[str, float]) -> List[Dict]:
    """Score activated nodes and return sorted results."""
    # Same logic as _score_activated above
    ...

# The old retrieve_memories() function is deprecated but kept
# for backward compatibility until Phase 3 is finalized.
```

### Config Flags

In `memory_thread/config/settings.py`:

```python
# Graph Retrieval
MT_RECALL_MODE: str = "hybrid"  # "graph" | "keyword" | "hybrid"
RECALL_GRAPH_MAX_DEPTH: int = 3
RECALL_GRAPH_DECAY: float = 0.5
RECALL_GRAPH_MIN_SEEDS: int = 1
RECALL_FTS_FALLBACK: bool = True
```

### Migration Strategy (Critical)

This is the **highest risk change** in the entire project. Rollout plan:

1. **Phase 3a:** Add `recall_graph()` method to SDK (NEW method, doesn't touch existing `recall()`)
2. **Phase 3b:** Add `mode` parameter to `recall()` with default `"keyword"` (unchanged behavior)
3. **Phase 3c:** Run both paths in shadow mode — compare recall_graph vs recall results silently
4. **Phase 3d:** When graph quality is verified, change default to `"hybrid"`
5. **Phase 3e:** After sufficient burn-in, remove `"keyword"` mode (or keep as opt-in)

Each step is reversible. Gating via `MT_RECALL_MODE` env var means rollback = flip one env var.

---

## 9. Component: Topology-Aware Decay & Prune

### File

`memory_thread/services/pruner.py` — +15 lines

### Decay Enhancement

The existing decay engine scores by time alone. The topology-aware version adds a **graph connectivity factor**:

```python
# In pruner.py, augment calculate_pruning_score():

def calculate_pruning_score(self, state: Dict) -> float:
    """Same existing logic + graph topology factor."""
    now = datetime.now()
    last_accessed = state.get('last_accessed') or now
    access_count = state.get('access_count', 0)
    days_idle = (now - last_accessed).days

    # Existing factors (unchanged computation):
    recency_score = max(0.0, 1.0 - (days_idle / 90.0))
    freq_score = min(1.0, math.log(access_count + 1) / math.log(100))
    truth_vector = state.get('truth_vector', {})
    importance = truth_vector.get('authority', 0.5)

    # NEW: Topology factor
    entity_id = str(state.get('entity_id', ''))
    topology_factor = self._get_topology_factor(entity_id)

    # Updated weights (topology gets 20%):
    score = (
        recency_score * 0.4
        + importance * 0.25
        + freq_score * 0.15
        + topology_factor * 0.20
    )
    return score

def _get_topology_factor(self, entity_id: str) -> float:
    """Higher score for structurally important nodes."""
    if entity_id not in graph_engine.graph:
        return 0.0
    centrality = graph_engine.centrality(entity_id)
    bridge = graph_engine.bridge_score(entity_id)
    return min(1.0, (centrality * 2 + bridge * 3) / 5)
    # Bridge nodes get 3x weight → harder to prune
```

### Config Flag

```python
# In settings.py:
PRUNE_USE_TOPOLOGY: bool = False   # Default OFF = exact old behavior
```

When `False`, `_get_topology_factor()` returns `0.0` and the old scoring formula is used. This means **zero regression risk** — the feature is opt-in.

### Behavior With Topology-Aware Pruning

| Node Type | Centrality | Bridge Score | Topology Factor | Effect |
|-----------|-----------|-------------|-----------------|--------|
| Hub (many connections) | 0.8 | 0.3 | 0.50 | ~harder to prune (retained 50% more) |
| Bridge (connects clusters) | 0.2 | 0.9 | 0.62 | ~much harder to prune |
| Leaf (isolated) | 0.0 | 0.0 | 0.00 | ~normal pruning |
| Isolated node | 0.0 | 0.0 | 0.00 | ~normal pruning |

---

## 10. Component: Galaxy Unified Graph

### File

`memory_thread/nervous/galaxy_core.py` — +50 lines (additive)

### What Changes

Currently, Galaxy has its own separate graph infrastructure:
- `GalaxyBridge` with a separate `belief_bridges` table
- `AgentMemorySpace` with per-agent memory namespaces
- `ConflictGraph` (NetworkX) rebuilt from scratch each time

**After unification:** All galaxy data becomes edges in the single materialized GraphEngine graph.

### Belief Bridge Migration

```python
# In GalaxyBridge.link_beliefs(), DUAL-WRITE to both:

def link_beliefs(self, belief_a, belief_b, relationship, confidence):
    # 1. Keep writing to belief_bridges table (existing behavior)
    self.pg.execute("INSERT INTO belief_bridges ...")
    
    # 2. Also write to GraphEngine (NEW)
    graph_engine.graph.add_edge(
        str(belief_a['id']),
        str(belief_b['id']),
        type=relationship,  # "supports" or "contradicts"
        confidence=confidence,
        agent_a=belief_a.get('agent_id', ''),
        agent_b=belief_b.get('agent_id', ''),
        timestamp=time.time(),
    )
```

Dual-write ensures zero data loss during migration. The `belief_bridges` table can be dropped after sufficient burn-in.

### Cross-Agent Query via Graph

```python
# In GalaxyCore.query_galaxy(), new graph-native path:

def query_galaxy_graph(self, query: str, requesting_agent: Optional[str] = None):
    """Cross-agent query using graph traversal instead of multi-collection search."""
    # 1. Find the requesting agent's node
    agent_node = f"agent_{requesting_agent}" if requesting_agent else None
    
    # 2. Resolve query to belief nodes
    # (text search over belief node attributes)
    belief_seeds = []
    for v in graph_engine.graph.vs:
        if v["type"] == "belief" and query.lower() in str(v.get("content", "")).lower():
            belief_seeds.append(v["name"])
    
    # 3. Activate from these beliefs, following supports/contradicts edges
    activated = graph_engine.activation(
        seeds=belief_seeds,
        max_depth=2,
        decay_per_hop=0.3,
        edge_types=["supports", "contradicts", "about"],
    )
    
    # 4. Separate into primary (requesting agent) and secondary (other agents)
    primary = []
    secondary = []
    for node_id, act_score in activated.items():
        if node_id not in graph_engine.graph:
            continue
        node = graph_engine.graph.vs.find(name=node_id)
        node_agent = node.get("agent_id", "")
        result = {"id": node_id, "content": node.get("content", ""), "activation": act_score}
        if node_agent == requesting_agent:
            primary.append(result)
        else:
            result["source_agent"] = node_agent
            secondary.append(result)
    
    return {"primary": primary, "secondary": secondary}
```

### Conflict Resolution Enhancement

The existing `ConflictGraph` is rebuilt from scratch every time. With the unified graph, contradiction edges already exist:

```python
# In conflict_resolution.py:

def detect_conflicts_fast(self) -> List[List[str]]:
    """Find contradiction clusters using existing graph edges."""
    # GraphEngine already has 'contradicts' edges from belief bridges
    # Just find connected components of the contradiction subgraph
    cycles = graph_engine.contradiction_cycles()
    return cycles

def resolve(self, conflict: List[str], strategy: str = "authority") -> Dict:
    """Resolve conflict using graph topology + truth vectors."""
    if strategy == "authority":
        # Highest-authority node in the conflict cluster wins
        return max(conflict, key=lambda n: self._node_authority(n))
    
    elif strategy == "centrality":
        # Most central node in the conflict cluster wins
        return max(conflict, key=lambda n: graph_engine.centrality(n))
    
    elif strategy == "temporal":
        # Most recent wins
        return max(conflict, key=lambda n: self._node_timestamp(n))
    
    # Default: authority-weighted consensus
    ...
```

---

## 11. Risk Matrix

### Legend

| Risk | IO | Explanation |
|------|----|-------------|
| **LOW** | Safe to implement at any time, no behavior change | Files added, enums extended, new optional params |
| **MEDIUM** | Changes internal behavior; same API contract must be preserved | Golden thread rewrite (same output, faster impl) |
| **HIGH** | Changes user-facing behavior; requires careful rollout | Recall mode change (graph-primary vs vector-primary) |

### Detailed Matrix

| Change | File(s) | Lines Changed | Risk | Why | Mitigation |
|--------|---------|---------------|------|-----|------------|
| **GraphEngine class** | `services/graph_engine.py` | NEW ~350 | **LOW** | New file, zero existing code depends on it | Build + test in isolation with existing event data |
| **ActionEnum: LINK/UNLINK/MERGE** | `models/events.py` | +3 | **LOW** | Backward-compatible enum extension | Old WAL readers skip unknown actions |
| **SDK: add_relation/remove_relation** | `sdk.py` | +60 | **LOW** | New public methods, don't touch existing methods | Same pattern as existing SDK methods |
| **Golden Thread rewrite** | `services/golden_thread.py` | ~442 rewrite | **MEDIUM** | Same API, same output contract. Complex 442-line logic must produce identical narratives. | Run old+new in parallel; compare output for every test entity before swapping |
| **Recall graph-primary** | `sdk.py`, `retrieval_service.py` | ~100 | **HIGH** | Changes what users see and in what order. This is the point of the change, but it's a behavior break. | New method first (`recall_graph()`), config-gated swap (`MT_RECALL_MODE`), shadow-mode comparison before default flip |
| **Topology-aware pruner** | `services/pruner.py` | +15 | **LOW** | Additive factor, gated by config flag | `PRUNE_USE_TOPOLOGY = False` preserves exact old behavior |
| **Topology-aware decay** | `services/decay_engine.py` | +10 | **LOW** | Same pattern as pruner | Config flag default OFF |
| **Galaxy → unified graph** | `nervous/galaxy_core.py` | +50 | **LOW** | Dual-write preserves existing tables | belief_bridges table still written to; graph is additional |
| **WAL format** | `services/wal.py` | 0 | **LOW** | Same JSONL format. New action types serialize identically to existing ones. | No format change required |
| **relations table role** | `services/graph_service.py` | ~71 obsolete | **LOW** | Table stays; GraphService becomes wrapper around GraphEngine | Never delete the table; just stop writing to it directly |
| **Retrieval scoring weights** | `config/settings.py` | +5 | **LOW** | New config keys with safe defaults | `SCORE_WEIGHT_GRAPH` already exists; just making it functional |
| **graph_service.py dead code removal** | `services/graph_service.py` | ~71 remove | **LOW** | Only removal if GraphEngine proves stable | Keep file as deprecated wrapper until Phase 5 |

### Files That NEVER Change

| File | Reason |
|------|--------|
| `db/postgres_schema.sql` | Schema stays. Only new tables/columns if needed. |
| `db/schema_phase_*.sql` | Existing migrations are immutable. |
| `db/postgres_client.py` | Connection pooling stays. GraphEngine uses PostgresClient the same way. |
| `db/sqlite_client.py` | Same Postgres-compatible interface. |
| `db/qdrant_client.py` | REMOVED — Qdrant no longer used. FTS replaces vector search. |
| `api/server.py` | All existing endpoints unchanged. New endpoints optional. |
| `cli.py` (~1223 lines) | CLI commands unchanged. Underlying calls change transparently. |
| `tests/conftest.py` | Existing fixtures unchanged. New fixtures added. |
| `docker-compose.yml` | Qdrant service removed. Only Postgres remains. |
| `setup.py` / `pyproject.toml` | Only add `python-igraph` dependency. |

### Rollback Plan

Every change has a rollback:

| Change | Rollback |
|--------|----------|
| GraphEngine | Delete file, `sdk.py` catches import error, skips graph |
| LINK/UNLINK actions | Remove from ActionEnum, replay ignores them |
| Golden Thread rewrite | Revert to old `golden_thread.py` (keep file as `golden_thread_v1.py` during transition) |
| Graph-primary recall | Set `MT_RECALL_MODE=keyword` → keyword-only via FTS |
| Topology-aware pruner | Set `PRUNE_USE_TOPOLOGY=False` → exact old behavior |
| Galaxy unified graph | Dual-write ensures belief_bridges table is always current |

---

## 12. Phase Plan

### Phase 0 — Design (Complete)

- This document
- Approval of architecture
- Dependency confirmed: `python-igraph` installs cleanly

### Phase 1 — GraphEngine Core (1 week, LOW risk)

**Deliverable:** `GraphEngine` class with iGraph backend, rebuild from events, activation propagation, and comprehensive tests.

**Files created:**
- `memory_thread/services/graph_engine.py` (~350 lines)

**Files modified:**
- `memory_thread/models/events.py` — +3 lines (LINK/UNLINK/MERGE enum values)
- `memory_thread/sdk.py` — +60 lines (add_relation, remove_relation, merge_entities methods)
- `memory_thread/config/settings.py` — +5 lines (graph retrieval config)
- `pyproject.toml` — +1 line (`python-igraph` dependency)

**Tests:**
- `tests/test_graph_engine.py` (NEW):
  - `test_rebuild_from_events` — create events, rebuild graph, verify nodes+edges
  - `test_apply_event_all_types` — all 9 action types produce correct graph mutations
  - `test_activation_basic` — 2-hop chain, verify activation scores
  - `test_activation_max_path` — multiple paths to same node, verify max wins
  - `test_activation_edge_filter` — filter by edge type
  - `test_activation_truth_threshold` — propagation stops below threshold
  - `test_cycle_detection` — contradiction cycles
  - `test_centrality_and_bridge` — verify centrality/bridge scores
  - `test_rebuild_idempotent` — rebuild twice produces same graph
  - `test_concurrent_reads` — read from graph while writing (thread safety)
  - `test_missing_antecedent` — antecedent not yet in graph, verify graceful skip
  - `test_large_rebuild` — 10K events, measure time (target <500ms)

**Acceptance criteria:**
- [ ] `GraphEngine.rebuild()` loads 10K events in <500ms
- [ ] `GraphEngine.activation()` returns correct scores for known graph topologies
- [ ] All 9 action types produce correct graph mutations
- [ ] LINK/UNLINK/MERGE events are created through SDK and correctly materialized
- [ ] Thread safety verified (concurrent read during write)
- [ ] iGraph is swappable (NetworkX fallback if needed)

### Phase 2 — Golden Thread Migration (1 week, MEDIUM risk)

**Deliverable:** Golden thread produces identical output using GraphEngine, with measurable speedup.

**Files modified:**
- `memory_thread/services/golden_thread.py` — rewrite internals

**Tests:**
- `tests/test_golden_thread_reconstruction.py` — expand existing:
  - Parameterized: every existing golden thread test case
  - Compare old vs new output (narrative, events, truth scores) — MUST BE IDENTICAL
  - Timing comparison (target: 10x faster for entity with 100 events)

**Acceptance criteria:**
- [ ] Every existing golden thread test passes with new implementation
- [ ] Output narrative is identical for all test entities (same words)
- [ ] Speedup: entity with 100 events → <5ms vs old ~500ms
- [ ] Graceful when entity not in graph (falls back gracefully)

### Phase 3 — Graph-Primary Recall (2 weeks, HIGH risk)

**Deliverable:** `recall()` with `MT_RECALL_MODE` config. Default is `"hybrid"`. Graph mode available via `recall_graph()`.

**Files modified:**
- `memory_thread/sdk.py` — recall method + recall_graph + seed resolution
- `memory_thread/services/retrieval_service.py` — rewrite to support both paths
- `memory_thread/config/settings.py` — recall mode config

**Tests:**
- `tests/test_truth_retrieval_quality.py` — expand:
  - Compare graph-primary vs vector-primary recall quality
  - Measure precision@k, recall@k for both modes
  - Cold-start scenario (empty graph) → must fallback to vector
  - Sparse graph scenario (few connections) → hybrid mode fills from vector
  - Rich graph scenario (many connections) → graph mode outperforms vector

**Shadow mode infrastructure:**
- `tests/test_recall_shadow_mode.py` (NEW):
  - Run both modes on same queries
  - Log differences in results
  - Measure result overlap (Jaccard similarity)
  - Assert graph results are never worse than vector (by configurable margin)

**Acceptance criteria:**
- [ ] `MT_RECALL_MODE=keyword` produces keyword-only results via Postgres FTS
- [ ] `MT_RECALL_MODE=graph` produces relevant results with meaningful topology
- [ ] `MT_RECALL_MODE=hybrid` never returns FEWER results than keyword alone
- [ ] Seed resolution works with entity IDs, names, and arbitrary text via FTS
- [ ] Cold-start: empty graph falls back to 100% keyword FTS
- [ ] Config-gated rollback works (flip env var, restart, exact old behavior)
- [ ] Latency: graph recall < 20ms for 1000-node graph

### Phase 4 — Topology-Aware Decay & Prune (3 days, LOW risk)

**Deliverable:** Existing decay/prune enhanced with graph topology factor. Default OFF.

**Files modified:**
- `memory_thread/services/pruner.py` — +15 lines
- `memory_thread/services/decay_engine.py` — +10 lines
- `memory_thread/config/settings.py` — +2 lines

**Tests:**
- `tests/test_decay_curves.py` — expand:
  - Verify topology factor contribution
  - Verify topology factor = 0 when PRUNE_USE_TOPOLOGY=False
- `tests/test_prune_topology.py` (NEW):
  - Hub node retained longer than leaf node under same access pattern
  - Bridge node retained longer than non-bridge under same access pattern

**Acceptance criteria:**
- [ ] `PRUNE_USE_TOPOLOGY=False` produces IDENTICAL pruning scores to pre-graph
- [ ] `PRUNE_USE_TOPOLOGY=True` retains high-centrality nodes longer
- [ ] No new dependencies, no schema changes

### Phase 5 — Galaxy Unification (1 week, LOW risk)

**Deliverable:** Galaxy uses unified GraphEngine for cross-agent queries. Dual-write to belief_bridges table.

**Files modified:**
- `memory_thread/nervous/galaxy_core.py` — +50 lines
- `memory_thread/nervous/conflict_resolution.py` — +30 lines
- `memory_thread/nervous/auto_bridge.py` — verify bridge edges reach GraphEngine

**Tests:**
- `tests/test_galaxy_unification.py` (NEW):
  - Cross-agent query via graph returns same results as via table scan
  - Conflict detection via graph cycles matches old connected_components
  - Dual-write: belief_bridges table and graph both contain same edges

**Acceptance criteria:**
- [ ] Galaxy cross-agent queries work via graph traversal (not per-agent search)
- [ ] Conflict detection uses existing graph edges (no full scan)
- [ ] Dual-write: both belief_bridges table and graph are consistent
- [ ] AutoBridge creates edges that reach GraphEngine

---

## 13. Testing Strategy

### Test Pyramid

```
         ╱─────╲
        ╱ E2E  ╲          1 test: full startup → remember → recall → verify
       ╱────────╲
      ╱Integration╲       5 tests: GraphEngine + PostgreSQL, GraphEngine + SDK
     ╱──────────────╲
    ╱  Unit Tests    ╲   20+ tests: GraphEngine in isolation with fake events
   ╱────────────────────╲
```

### GraphEngine Unit Tests (Phase 1)

**File:** `tests/test_graph_engine.py`

```python
# Test data: synthetic events with known graph topology

def test_rebuild_from_events():
    """Create 10 events with antecedents, rebuild graph, verify."""
    events = [
        Event(action=ActionEnum.ADD, object_id=uuid.uuid4(), ...),  # 0
        Event(action=ActionEnum.ADD, object_id=uuid.uuid4(), ..., antecedents=[events[0].id]),  # 1
        ...
    ]
    engine = GraphEngine()
    for e in events:
        engine.apply_event(e)
    
    assert len(engine.graph.vs) == 2 + 10  # 2 entities + 10 events
    assert len(engine.graph.es) == 12  # 10 modifies + 1 causes

def test_activation_basic():
    """2-hop: A → B → C. Activate from A. B should get score, C should get decayed."""
    A, B, C = "a", "b", "c"
    engine.graph.add_vertex(A, type="entity")
    engine.graph.add_vertex(B, type="entity")
    engine.graph.add_vertex(C, type="entity")
    engine.graph.add_edge(A, B, type="relates", confidence=1.0)
    engine.graph.add_edge(B, C, type="relates", confidence=1.0)
    
    result = engine.activation([A], max_depth=2, decay_per_hop=0.5)
    
    assert result[A] == 1.0          # seed
    assert result[B] == 0.5          # 1.0 × 1.0 × 0.5
    assert result[C] == 0.25         # 0.5 × 1.0 × 0.5

def test_activation_max_path():
    """Multiple paths to same node: max activation wins."""
    ...

def test_cycle_detection():
    """Contradiction cycles: A → B → C → A via contradicts edges."""
    ...
```

### Shadow Mode (Phase 3)

```python
def test_shadow_mode_recall_quality():
    """Both recall modes on same queries. Graph must be at least as good."""
    queries = ["who is Elon Musk?", "Python async patterns", ...]
    
    for q in queries:
        keyword_results = client.recall(q, mode="keyword")
        graph_results = client.recall(q, mode="graph")
        
        assert len(graph_results) >= len(keyword_results) * 0.8  # at most 20% fewer
        assert graph_results[0]["score"] >= 0.3  # meaningful scores
```

### Performance Tests

```python
def test_large_rebuild_performance(benchmark):
    """10K events rebuild must complete within 500ms."""
    events = generate_synthetic_events(10000)
    engine = GraphEngine()
    
    def _rebuild():
        for e in events:
            engine.apply_event(e)
    
    result = benchmark(_rebuild)
    assert result < 0.5  # 500ms

def test_activation_large_graph(benchmark):
    """Activation on 10K-node graph must complete within 50ms."""
    graph = generate_large_graph(10000, 50000)
    engine = GraphEngine()
    engine.graph = graph
    
    def _activate():
        engine.activation(seeds=["node_0"], max_depth=3)
    
    result = benchmark(_activate)
    assert result < 0.05  # 50ms
```

---

## 14. Key Design Decisions

### Decision 1: iGraph over NetworkX

**Chosen:** iGraph (version 1.0.0+, pre-compiled wheels, no CMake needed)

**Rationale:**
- NetworkX activation BFS over 10K nodes: ~50ms
- iGraph activation BFS over 10K nodes: ~2ms
- NetworkX memory for 50K nodes: ~100MB Python objects
- iGraph memory for 50K nodes: ~8MB C structs
- iGraph C core is read-safe for concurrent threads
- NetworkX is NOT thread-safe for any operation
- Both provide equivalent algorithms; iGraph is 10-50x faster at everything

**Trade-off:** Different API (`G.vs[n]` instead of `G.nodes[n]`). Mitigated by the `GraphEngine` wrapper — nothing outside the engine knows which library is underneath.

### Decision 2: Single graph, not multiple graphs

**Chosen:** One `GraphEngine` with one `igraph.Graph` containing all node types (entity, event, belief, agent) and all edge types (relates, causes, modifies, supports, contradicts, about, holds).

**Rationale:**
- Cross-type queries become trivial: "find events about this entity" = single edge traversal
- Multi-agent queries become simple: "find beliefs connected to this agent" = follow 2 edges
- Contradiction cycles span both entity relations AND belief bridges — can't detect in separate graphs
- One rebuild from one SQL query, one in-memory structure to maintain

**Trade-off:** Graph size grows with event count. 100K events = ~110K nodes. iGraph handles millions of nodes efficiently in memory (~8MB per 50K nodes). At MT's current scale (likely <100K events), this is negligible.

### Decision 3: Graph rebuilt from events, not persisted separately

**Chosen:** Graph is a derived state, rebuilt from the event log on startup. No separate graph persistence.

**Rationale:**
- Follows existing MT DNA: everything is derived from events
- No consistency problem between event log and graph (graph is always derivable from events)
- No write amplification (events → graph is a one-way sync)
- Snapshot is optional optimization, not required for correctness

**Trade-off:** Startup time. 100K events → ~250ms rebuild. Acceptable for a Python service startup. Can add binary snapshot later if needed.

### Decision 4: Activation replaces flat scoring, with FTS fallback

**Chosen:** Graph activation is PRIMARY retrieval mechanism. Postgres FTS is used for SEED RESOLUTION and fallback.

**Rationale:**
- Graph-connected retrieval produces STRUCTURED results (paths, context, contradictions)
- Flat vector scoring produces INDEPENDENT results (no awareness of relationships)
- For well-connected entities, graph is strictly better (returns the subgraph, not just the node)
- For cold queries (no seed entity), FTS fills the gap

**Trade-off:** Two retrieval paths to maintain. FTS replaces the old Qdrant vector path entirely.

### Decision 5: Config-gated rollback for retrieval change

**Chosen:** Every behavior change has a configuration flag that preserves old behavior.

**Rationale:**
- `MT_RECALL_MODE=keyword` = keyword-only via FTS (pre-graph approximation)
- `PRUNE_USE_TOPOLOGY=False` = exact pre-graph pruning
- Rollback = flip one env var and restart
- No data migration required to roll back

**Trade-off:** More config keys to maintain. But they're simple bools/enums with clear defaults.

---

## 15. Appendix: iGraph vs NetworkX

### API Comparison

| Operation | NetworkX | iGraph |
|-----------|----------|--------|
| Create graph | `nx.MultiDiGraph()` | `ig.Graph(directed=True)` |
| Add vertex | `G.add_node(id, attr=v)` | `G.add_vertex(id, attr=v)` |
| Add edge | `G.add_edge(u, v, attr=v)` | `G.add_edge(u, v, attr=v)` |
| Get vertex attr | `G.nodes[n]['attr']` | `G.vs[n]['attr']` |
| Get edge attr | `G.edges[e]['attr']` | `G.es[e]['attr']` |
| Find vertex | `G.nodes[n]` (KeyError if missing) | `G.vs.find(name=n)` (ValueError if missing) |
| BFS | `nx.bfs_edges(G, source)` | `G.bfsiter(source)` |
| Shortest path | `nx.shortest_path(G, s, t)` | `G.get_shortest_paths(s, t)` |
| PageRank | `nx.pagerank(G)` | `G.pagerank()` |
| Connected comps | `nx.connected_components(G)` | `G.connected_components()` |
| Community detection | `nx.community.louvain_communities(G)` | `G.community_leiden()` |
| Centrality | `nx.degree_centrality(G)` | `G.degree(loops=False)` (normalize manually) |
| Delete vertex | `G.remove_node(n)` | `G.delete_vertices(n)` |
| Delete edge | `G.remove_edge(u, v)` | `G.delete_edges(e)` |
| Number of vertices | `G.number_of_nodes()` | `G.vcount()` |
| Number of edges | `G.number_of_edges()` | `G.ecount()` |

### Performance Comparison (10K nodes, 50K edges)

| Operation | NetworkX | iGraph | Speedup |
|-----------|----------|--------|---------|
| Graph construction | ~2.0s | ~50ms | 40x |
| BFS (single source) | ~15ms | ~0.5ms | 30x |
| Shortest path | ~8ms | ~0.3ms | 27x |
| PageRank | ~500ms | ~10ms | 50x |
| Degree centrality | ~5ms | ~0.1ms | 50x |
| Memory (50K nodes) | ~100MB | ~8MB | 12x |
| Serialization (GML) | ~800ms | ~50ms | 16x |

### When to Use NetworkX Instead

Despite iGraph being faster, NetworkX is better for:

1. **Rapid prototyping** — Python-native, easier debug, better error messages
2. **Small graphs** (< 1000 nodes) — performance difference is negligible
3. **Complex graph algorithms** — NetworkX has more exotic algorithms (isomorphism, graph automorphism, etc.)
4. **Existing code** — MT's conflict_resolution.py already uses NetworkX

**Recommendation:** Default to iGraph for GraphEngine. Keep NetworkX for conflict_resolution.py's specific use case (it only uses `connected_components`, graph is small, performance is irrelevant there).

---

## 16. Phase 6 — Session & Thread Layer

**Goal:** Group events into conversation sessions. Make recall thread-aware so an agent can retrieve not just individual events but the full conversation context that produced them.

**Complexity:** LOW

**Why now:** Without threads, the graph has events as disconnected nodes. An agent asking "what were we discussing in the auth refactor session?" gets individual events with no grouping. Threads turn a flat event list into contextual narratives.

### Graph Model

```
Thread node (type: "thread"):
  name: "thread-uuid"
  type: "thread"
  title: "Auth module refactor discussion"
  created_by: "agent-coder-1"
  started_at: "2026-05-14T10:00:00"
  status: "active" | "archived"

Edge (type: "contains"):
  Thread → Event
  Thread → Entity (entities created/modified during thread)
  Thread → Thread (parent/child for sub-threads)
```

### Data Model

```python
@dataclass
class Thread:
    thread_id: uuid.UUID
    title: str
    created_by: str           # agent_id or "user"
    started_at: datetime
    status: str               # "active" | "archived"
    parent_thread_id: Optional[uuid.UUID]  # for sub-threads / branching
```

### Event Changes

Add an optional `thread_id` field to every Event. When present, GraphEngine creates a `contains` edge from thread to event.

```python
class Event(BaseModel):
    # ... existing fields ...
    thread_id: Optional[uuid.UUID] = None   # NEW
```

### SDK Changes

```python
class MemoryClient:
    def create_thread(self, title: str, parent_thread_id: Optional[str] = None) -> Thread: ...

    def remember(self, content, thread_id: Optional[str] = None, ...) -> EntityState:
        # If thread_id provided, event gets "contains" edge to thread

    def get_thread(self, thread_id: str) -> ThreadResult:
        """Retrieve full thread with all its events, in order."""

    def search_threads(self, query: str) -> List[Thread]:
        """Search across thread titles and their event content."""
```

### Retrieval Enhancement

When a query matches a thread, the retrieval result includes:
- The matched event
- Its sibling events (same thread, ±5 positions for context)
- The thread title as summary
- Thread-level truth score (aggregated from constituent events)

```python
def recall(query, ..., thread_context=True):
    results = graph_engine.activation(seeds)
    if thread_context:
        for r in results:
            r["thread_context"] = graph_engine.get_thread_context(r["id"])
    return results
```

### API

```
POST   /threads                    → create thread
GET    /threads/:id                → get thread with events
GET    /threads                    → list/search threads
POST   /memory/remember            → (add optional thread_id param)
```

### Tests

```python
def test_thread_grouping():
    """Events in same thread are connected via 'contains' edges."""
def test_thread_context_in_recall():
    """Recall returns sibling events when thread_context=True."""
def test_thread_nesting():
    """Parent/child thread structure is traversable."""
def test_thread_search():
    """Search across thread titles and event content."""
```

### Acceptance Criteria

- [ ] Events can be tagged with `thread_id` at creation time
- [ ] GraphEngine creates `contains` edges between thread and events
- [ ] Recall with `thread_context=True` returns sibling events
- [ ] Threads can nest (parent/child for branching discussions)
- [ ] Thread search works across titles and event content

---

## 17. Phase 7 — Memory Tiers (Hot/Warm/Cold)

**Goal:** Not all memory belongs in the LLM's context window. Three tiers with automatic promotion/demotion based on access patterns, truth scores, and graph topology.

**Complexity:** MEDIUM-HIGH

**Why now:** Without tiers, every recall floods the agent with ALL matching events regardless of recency or relevance. Tiers let the system budget context: what's hot stays accessible, what's cold is summarized, what's gone is truly pruned.

### Tier Architecture

| Tier | Storage | Latency | Capacity | Promotion Trigger | Demotion Trigger |
|------|---------|---------|----------|-------------------|------------------|
| **Core** | LLM context window (injected as system prompt) | Instant | ~8K tokens (~20 facts) | Activation > 0.8, accessed in last N turns | Activation drops below 0.4 |
| **Episodic** | GraphEngine (in-memory iGraph) | ~1ms | Unlimited (limited by RAM) | Activation > 0.3, accessed in last 7 days | No access for 7 days, or summarized |
| **Semantic** | Summarized facts + archived event chains | ~10ms (reload to episodic) | Unlimited | Summarization pipeline consolidates episodic | Never (immutable) |

### Memory Router

A lightweight policy decides what goes where:

```python
class MemoryRouter:
    """
    Decides promotion/demotion between tiers.
    Uses heuristic scoring with optional RL policy.
    """

    def score_for_core(self, node_id: str, current_context: Dict) -> float:
        """
        Factors:
        - Current graph activation (from ongoing agent activity)
        - Recency (last accessed timestamp)
        - Topology (hub/bridge nodes stay hot longer)
        - Task relevance (semantic similarity to current task)
        - Handoff relevance (pushed as context in agent handoffs)
        """
        ...

    def promote_to_core(self, node_id: str):
        """Inject node's content into agent's context window."""

    def demote_to_episodic(self, node_id: str):
        """Move from core to episodic (remove from context, keep in graph)."""

    def summarize_to_semantic(self, thread_id: str):
        """
        Consolidate a thread's events into extracted facts.
        - Run LLM summarization on thread events
        - Store extracted facts as new entity nodes
        - Archive original events (keep in DB, remove from active graph)
        """
        ...

    def promote_to_episodic(self, node_id: str):
        """Reload semantic fact back into active graph."""
```

### Summarization Pipeline

```python
def summarize_thread(thread_id: str) -> List[Dict]:
    """Convert a thread's event chain into extracted, timeless facts."""
    events = graph_engine.get_thread_events(thread_id)

    # LLM call: "Given these events, what are the verified facts?"
    facts = llm_summarize(events)

    for fact in facts:
        fact_node = create_entity(fact["content"], truth_vector=fact["truth"])
        graph_engine.add_edge(thread_id, fact_node, type="summarized_to")

    # Archive old events
    for e in events:
        graph_engine.unload_event(e)  # keep in Postgres, remove from active iGraph
```

### Config

```python
MEMORY_TIER_CORE_MAX_TOKENS: int = 8000
MEMORY_TIER_EPISODIC_DAYS: int = 7
MEMORY_TIER_SUMMARIZE_AFTER_EVENTS: int = 50
MEMORY_TIER_ROUTER_POLICY: str = "heuristic"  # or "rl"
```

### Tests

```python
def test_promotion_demotion_cycle():
    """Node moves core → episodic → semantic based on access pattern."""
def test_summarization_preserves_truth():
    """Summarized facts retain truth vector from source events."""
def test_router_scores_hub_higher():
    """Bridge nodes score higher for core retention than leaves."""
def test_semantic_reload():
    """Archived fact can be reloaded to episodic on request."""
```

### Acceptance Criteria

- [ ] Three tiers exist: core, episodic, semantic
- [ ] Router scores nodes for promotion/demotion using activation + topology + recency
- [ ] Core tier is injected into agent context window as structured facts
- [ ] Episodic tier is the in-memory graph (everything in GraphEngine)
- [ ] Summarization pipeline consolidates threads into extracted facts
- [ ] Semantic tier stores summarized facts in Postgres (archived, not lost)
- [ ] Archived facts can be reloaded to active graph on demand

---

## 18. Phase 8 — Proactive Context Injection

**Goal:** The system doesn't wait to be queried. It observes the agent's ongoing activity and preemptively pushes relevant graph context into the agent's context window.

**Complexity:** MEDIUM

**Why now:** This is the difference between a memory *database* (waits for SQL query) and a memory *system* (surfaces what's relevant without being asked). An agent shouldn't have to say "remember X" — MT should already have injected X by the time the agent needs it.

### Architecture

```
Agent activity (conversation, code, actions)
    │
    ▼
Context Monitor (runs on each agent turn)
    │
    ├──► Extract entities from current agent text (spaCy or LLM)
    ├──► Resolve to graph nodes
    ├──► GraphEngine.activation(seeds, max_depth=2, decay=0.7)
    ├──► Score activated nodes (activation × truth × recency)
    └──► Return top-K nodes for injection
          │
          ▼
    Injection Formatter
          │
          ├──► Format as structured context: facts, contradictions, recent changes
          ├──► Deduplicate against already-injected context
          ├──► Respect token budget (max 20% of context window)
          └──► Inject into agent's system prompt
```

### Context Monitor

```python
class ContextMonitor:
    """
    Observes agent activity and surfaces relevant graph context.
    Runs after every agent action/response.
    """

    def __init__(self, graph_engine: GraphEngine):
        self.graph = graph_engine
        self.active_seeds: Set[str] = set()
        self.injected_ids: Set[str] = set()  # track what's already in context

    def observe(self, agent_text: str, max_tokens: int = 2000) -> str:
        """
        Given the agent's current text output:
        1. Extract entity mentions
        2. Activate graph from those seeds
        3. Format activated subgraph as context
        4. Deduplicate against already-injected
        5. Return context string to prepend to prompt
        """
        seeds = self._extract_entities(agent_text)
        activated = self.graph.activation(seeds, max_depth=2, decay_per_hop=0.7)

        new_items = []
        for node_id, score in sorted(activated.items(), key=lambda x: -x[1]):
            if node_id in self.injected_ids:
                continue
            if score < 0.3:
                continue
            new_items.append(self._format_node(node_id, score))
            self.injected_ids.add(node_id)

        # Prune stale injections (scores dropped, or token budget exceeded)
        context = self._format_injection(new_items, max_tokens)

        # Update active seeds (decay old ones, add new ones)
        self._decay_seeds()
        self.active_seeds.update(seeds)

        return context

    def _extract_entities(self, text: str) -> List[str]:
        """Extract entity mentions from text. Uses graph's search_nodes + optional NER."""
        mentions = []
        for word in text.split():
            matches = self.graph.search_nodes(word, attr="content")
            mentions.extend(matches)
        return list(set(mentions))[:10]

    def _format_injection(self, items: List[Dict], max_tokens: int) -> str:
        """Format activated context for injection into system prompt."""
        if not items:
            return ""
        lines = ["[Relevant Context]", ""]
        token_count = 3  # header
        for item in items:
            entry = f"- {item['content']} (confidence: {item['confidence']:.0%}, source: {item['source']})"
            entry_tokens = len(entry) // 4  # rough estimate
            if token_count + entry_tokens > max_tokens:
                break
            lines.append(entry)
            token_count += entry_tokens
        lines.append("")
        return "\n".join(lines)
```

### Integration

```python
# In agent runtime:
def agent_step(input_text):
    context = context_monitor.observe(input_text, max_tokens=2000)
    full_prompt = context + "\n" + agent_system_prompt + "\n" + input_text
    response = llm.generate(full_prompt)
    return response
```

### Config

```python
CONTEXT_INJECTION_ENABLED: bool = True
CONTEXT_INJECTION_MAX_TOKENS: int = 2000
CONTEXT_INJECTION_ACTIVATION_THRESHOLD: float = 0.3
CONTEXT_INJECTION_MAX_DEPTH: int = 2
CONTEXT_INJECTION_DECAY: float = 0.7
```

### Tests

```python
def test_entity_extraction_from_text():
    """Extract entity mentions from agent conversation."""
def test_activation_on_observation():
    """Observing agent text triggers graph activation."""
def test_deduplication():
    """Already-injected context is not re-injected."""
def test_token_budget_respected():
    """Injection respects max_tokens limit."""
def test_context_improves_response():
    """Agent response quality improves with injected context."""
```

### Acceptance Criteria

- [ ] Context monitor extracts entity mentions from agent text
- [ ] Graph activation runs on each agent turn
- [ ] Injected context is deduplicated (same entity not re-injected)
- [ ] Token budget is respected
- [ ] Stale context decays (removed after N turns without re-activation)
- [ ] Agent can still explicitly query MT even without injection (manual query always works)

---

## 19. Phase 9 — Procedural Memory (AWM-style Workflow Induction)

**Goal:** Extract reusable workflows from successful agent action trajectories in the event graph. Store them so agents can reuse learned procedures instead of rediscovering them.

**Complexity:** MEDIUM

**Why now:** The event graph already records every action agents take. AWM-style induction mines these trajectories for patterns. Each time an agent successfully deploys code, the steps are in the graph. Phase 8 extracts *what* happened, but Phase 9 extracts *how* it happened — the reusable procedure.

### Graph Model

```
Workflow node (type: "workflow"):
  name: "workflow-uuid"
  title: "Deploy to production"
  description: "Steps to deploy code to production"
  created_from: "thread-uuid"     # provenance
  success_count: 12
  avg_duration_seconds: 340

Step edges (type: "has_step", order: int):
  Workflow → Step (entities representing action steps)

Example steps for "Deploy to production":
  1. "Run test suite"                    (step, order=1)
  2. "Build Docker image"                (step, order=2)
  3. "Push to registry"                  (step, order=3)
  4. "Deploy to staging"                 (step, order=4)
  5. "Verify health check"               (step, order=5)
  6. "Promote to production"             (step, order=6)
```

### Workflow Induction Module

```python
class WorkflowInduction:
    """
    Mines the event graph for reusable procedural patterns.
    Inspired by AWM (Agent Workflow Memory).
    """

    def __init__(self, graph_engine: GraphEngine):
        self.graph = graph_engine

    def extract_workflow(self, thread_id: str) -> Optional[Dict]:
        """
        Given a thread representing a successful task completion:
        1. Collect all events in the thread, ordered
        2. Extract action description from each event delta
        3. Send to LLM for workflow extraction:
           "Given these actions, identify the reusable workflow.
            Abstract specific values into parameters."
        4. Store as Workflow node in graph
        5. Return workflow dict
        """
        events = self._get_thread_actions(thread_id)
        if len(events) < 2:
            return None

        workflow = self._llm_induct(events)
        if not workflow:
            return None

        workflow_node = self._store_workflow(thread_id, workflow)
        return workflow_node

    def match_workflow(self, agent_input: str) -> Optional[Dict]:
        """
        Given current agent input, find matching workflow.
        Uses semantic similarity + graph search.
        """
        candidates = self.graph.search_nodes(agent_input, attr="title")
        for c in candidates:
            vattrs = self.graph.graph.vs.find(name=c).attributes()
            if vattrs.get("type") == "workflow":
                return self._format_workflow(c)
        return None

    def _llm_induct(self, events: List[Dict]) -> Optional[Dict]:
        """
        LLM prompt:
        "Given this action sequence, extract reusable steps.
         Replace specific values (e.g., 'deploy app-v3' → deploy {version})
         with parameter placeholders."
        """
        ...

    def _store_workflow(self, thread_id: str, workflow: Dict) -> str:
        """Store workflow as nodes + edges in graph."""
        node_id = f"workflow_{uuid.uuid4()}"
        self.graph.graph.add_vertex(
            node_id,
            type="workflow",
            title=workflow["title"],
            description=workflow["description"],
            created_from=thread_id,
            success_count=1,
        )
        for i, step in enumerate(workflow["steps"]):
            step_id = f"step_{uuid.uuid4()}"
            self.graph.graph.add_vertex(step_id, type="step", description=step, order=i)
            self.graph.graph.add_edge(node_id, step_id, type="has_step", order=i)
        return node_id

    def increment_success(self, workflow_id: str):
        """Increment success counter when workflow is reused successfully."""
        v = self.graph.graph.vs.find(name=workflow_id)
        v["success_count"] = v.attributes().get("success_count", 0) + 1
```

### Retrieval

When an agent starts a new task, MT can recommend workflows:

```python
def recall(query, ..., recommend_workflows=True):
    results = graph_engine.activation(seeds)
    if recommend_workflows:
        workflow = induction.match_workflow(query)
        if workflow:
            results.insert(0, {"type": "workflow", "content": workflow})
    return results
```

### Config

```python
WORKFLOW_INDUCTION_ENABLED: bool = True
WORKFLOW_MIN_EVENTS: int = 2
WORKFLOW_USE_LLM: bool = True     # False = heuristic only
WORKFLOW_LLM_MODEL: str = "gpt-4o-mini"
```

### Tests

```python
def test_workflow_extraction():
    """Thread with deployment steps produces a workflow."""
def test_workflow_matching():
    """Agent query 'deploy' matches 'Deploy to production' workflow."""
def test_workflow_success_counting():
    """Reusing a workflow increments its success counter."""
def test_workflow_with_parameters():
    """Specific values are abstracted into parameters."""
```

### Acceptance Criteria

- [ ] Workflow induction module extracts procedural patterns from successful threads
- [ ] Workflows stored as nodes in the graph with `has_step` edges
- [ ] Semantic matching retrieves relevant workflow for agent input
- [ ] Success counting enables confidence scoring for workflows
- [ ] Parameters are abstracted (specific → {placeholder})

---

## 20. Phase 10 — Memory Attestation & Audit

**Goal:** Cryptographic proof of what an agent knew at a given point in time. Immutable audit trail for enterprise/regulatory use.

**Complexity:** LOW-MEDIUM

**Why now:** For an agent swarm in production, you need to prove: "At timestamp T, agent A knew fact F with confidence C, based on source S." The event sourcing and graph already capture this. Phase 10 adds the cryptographic chain that makes it verifiable by third parties.

### Merkle Chain

```
Every N events (or on explicit checkpoint):
  ┌────────────────────────────────────────┐
  │ Checkpoint K                            │
  │  hash = H(                              │
  │    previous_hash,                       │
  │    last_event_id,                       │
  │    root_state_hash,                     │
  │    timestamp,                           │
  │    thread_id                            │
  │  )                                      │
  │  stored in: attestation_chain table     │
  └────────────────────────────────────────┘

Verification:
  Given event_id E and claimed truth_vector T at timestamp S:
  1. Find checkpoint containing E
  2. Recompute hash from checkpoint data
  3. Compare against stored hash
  4. If match: the state at that point is attested
```

### Data Model

```python
@dataclass
class AttestationCheckpoint:
    checkpoint_id: int
    previous_hash: str
    last_event_id: uuid.UUID
    root_state_hash: str       # hash of all entity_state at this point
    thread_id: Optional[str]
    timestamp: datetime
    hash: str                  # SHA-256 of all above fields + previous_hash
```

### Implementation

```python
class AttestationService:
    """
    Builds and verifies a Merkle chain of memory checkpoints.
    Each checkpoint attests to the state of the entire system at a point in time.
    """

    def __init__(self, pg: PostgresClient):
        self.pg = pg
        self._ensure_table()

    def _ensure_table(self):
        self.pg.execute("""
            CREATE TABLE IF NOT EXISTS attestation_chain (
                checkpoint_id SERIAL PRIMARY KEY,
                previous_hash TEXT NOT NULL,
                last_event_id UUID NOT NULL,
                root_state_hash TEXT NOT NULL,
                thread_id TEXT,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                hash TEXT NOT NULL UNIQUE
            );
        """)

    def checkpoint(self, last_event_id: str, thread_id: Optional[str] = None) -> Dict:
        """Create a new attestation checkpoint."""
        previous = self._get_last_checkpoint()
        previous_hash = previous["hash"] if previous else "0" * 64

        root_state = self._compute_root_state_hash()

        payload = f"{previous_hash}:{last_event_id}:{root_state}:{thread_id}"
        hash = hashlib.sha256(payload.encode()).hexdigest()

        self.pg.execute("""
            INSERT INTO attestation_chain
                (previous_hash, last_event_id, root_state_hash, thread_id, hash)
            VALUES (%s, %s, %s, %s, %s)
        """, (previous_hash, last_event_id, root_state_hash, thread_id, hash))

        return {
            "checkpoint_id": checkpoint_id,
            "hash": hash,
            "previous_hash": previous_hash,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def verify(self, event_id: str, claimed_truth: Dict) -> bool:
        """Verify that an event's truth vector is attested."""
        checkpoint = self._find_checkpoint_for_event(event_id)
        if not checkpoint:
            return False

        # Recompute and compare
        replayed_truth = self._replay_to_event(event_id)
        return replayed_truth == claimed_truth

    def verify_chain_integrity(self) -> List[str]:
        """Verify all checkpoints from genesis to latest. Return any breaks."""
        ...
```

### Graph Integration

The attestation system hooks into event creation:

```python
def remember(self, ...):
    event = self._create_event(...)
    self.wal.append(event)
    self.pg.insert(event)
    self.graph.apply_event(event)

    # Checkpoint every N events
    if self.event_count % ATTESATION_CHECKPOINT_INTERVAL == 0:
        self.attestation.checkpoint(
            last_event_id=str(event.id),
            thread_id=event.thread_id,
        )
```

### API

```
POST  /attestation/checkpoint           → create attestation checkpoint
GET   /attestation/verify/:event_id     → verify an event's attested state
GET   /attestation/chain                → get full attestation chain
GET   /attestation/verify-chain         → verify chain integrity
```

### Config

```python
ATTESTATION_ENABLED: bool = False
ATTESTATION_CHECKPOINT_INTERVAL: int = 100  # events between checkpoints
```

### Tests

```python
def test_checkpoint_creation():
    """Creating a checkpoint stores it in attestation_chain table."""
def test_chain_integrity():
    """Modifying an event breaks the chain."""
def test_verification():
    """Original event verifies against its checkpoint."""
def test_tamper_detection():
    """Tampered checkpoint hash is detected."""
```

### Acceptance Criteria

- [ ] Attestation checkpoints are created every N events
- [ ] Each checkpoint references the previous (Merkle chain)
- [ ] Chain integrity verification detects tampering
- [ ] API endpoints for creating and verifying checkpoints
- [ ] Works with thread context (thread_id in checkpoint)
- [ ] Exportable proof for third-party verification

---

## Phase Summary & Timing

### Current Status

| Phase | Status | Risk |
|-------|--------|------|
| 0.5 | ✅ Complete | LOW |
| 1 | ✅ Complete | LOW |
| 2 | ✅ Complete | MEDIUM |
| 3 | 🔲 Pending | HIGH |
| 4 | 🔲 Pending | LOW |
| 5 | 🔲 Pending | LOW |

### Forward Plan

| Phase | Title | Estimated Effort | Risk | Dependencies |
|-------|-------|-----------------|------|--------------|
| **3** | Graph-Primary Recall | 2 weeks | HIGH | Phase 1 (GraphEngine) |
| **4** | Topology-Aware Decay & Prune | 3 days | LOW | Phase 1 (topology methods) |
| **5** | Galaxy Unified Graph | 1 week | LOW | Phase 1 (dual-write pattern) |
| **6** | Session & Thread Layer | 4 days | LOW | Phase 1 (graph node types) |
| **7** | Memory Tiers | 1-2 weeks | MED-HIGH | Phase 6 (threads for summarization) |
| **8** | Proactive Context Injection | 1 week | MED | Phase 7 (tiers for injection source) |
| **9** | Procedural Memory (AWM) | 1 week | MED | Phase 6 (threads = trajectories) |
| **10** | Memory Attestation | 3 days | LOW | Phase 1 (event chain) |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-05-14 | Badal Raj | Initial architecture document (Phases 0.5-5) |
| 1.1 | 2026-05-15 | Badal Raj | Added Phases 6-10 (Threads, Tiers, Injection, AWM, Attestation) |

## Related Documents

- `docs/ARCHITECTURE.md` — Original system architecture (pre-graph)
- `memory_thread/services/graph_engine.py` — GraphEngine implementation (Phase 1+)
- `memory_thread/services/golden_thread.py` — Golden thread (Phase 2)
- `memory_thread/nervous/galaxy_core.py` — Multi-agent orchestration (Phase 5 DI)
- `tests/test_graph_engine.py` — GraphEngine tests
- `tests/test_golden_thread_reconstruction.py` — Golden thread tests
- `pyproject.toml` — Dependencies: python-igraph
