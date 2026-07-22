# Contradiction Detection — Build Plan

## Architecture

```
remember(content)
  → store memory immediately (sub-ms)
  → embed → ANN search → find top-20 candidates
  → push to ContradictionQueue with priority
  → return entity_id (no wait)

ContradictionWorker (background thread):
  high priority → process immediately
  normal priority → batch up, process when idle

For each candidate pair:
  NLI/API classifies: CONTRADICTION | ENTAILMENT | NEUTRAL
  If CONTRADICTION:
    → graph.add_edge(memory_A, memory_B, type="contradicts",
        detector="...", confidence=..., timestamp=..., batch_id=...)
    → audit_log.append({...})
  If ENTAILMENT:
    → graph.add_edge(memory_A, memory_B, type="supports", ...)

On crash → audit log has checkpoint → worker resumes WHERE status="pending"
```

## What Exists (can use today)

| Component | File | Status |
|-----------|------|--------|
| `graph.add_edge(src, tgt, type=..., **attrs)` | `graph_engine.py` | Ready |
| `"contradicts"` edge type | `galaxy_core.py:117`, `conflict_resolution.py:40` | Already in use |
| `contradiction_cycles()` — find all `contradicts` clusters | `graph_engine.py:393-416` | Ready |
| Tier 1 key-based `check_contradiction()` | `meta_stability_service.py:103-132` | Ready |
| `AuditLedger` — file-based JSONL | `audit_ledger.py` | Extendable |
| `check_contradiction()` SDK/API/MCP/session tool | `client.py`, `server.py`, `mcp_server.py` | Ready |
| `tms_health` Postgres table | `meta_stability_service.py:175-209` | Ready |
| `_apply()` adds edges for modifies/causes/contains/relates | `graph_engine.py:486-572` | Pattern to follow |

## What Needs Building

### 1. ContradictionClassifier (abstract + implementations)

```
ContradictionClassifier
├── APIProviderClassifier   — LLM call (OpenAI/Claude), simplest + most accurate
├── LocalNLClassifier       — sentence-transformers + NLI model, optional
└── LightweightClassifier   — all-MiniLM-L6-v2 + heuristic (fallback, no GPU)
```

Config in `settings.py`:
```python
CONTRADICTION_MODE = "api"        # "api" | "local" | "lightweight" | "auto"
CONTRADICTION_API_PROVIDER = ""   # "openai" | "anthropic" | ...
```

**API mode prompt:**
```
You are a contradiction detection system.
Do these two statements contradict each other?
Respond with exactly one word: CONTRADICTION, ENTAILMENT, or NEUTRAL.

1: "<existing memory content>"
2: "<new content>"
```

### 2. Embedding pre-filter (`embed_text()` + ANN index)

- The `embed_text()` call in `meta_stability_service.py:63` is **broken** — function was removed with old embedding stack
- Build locally: `sentence-transformers/all-MiniLM-L6-v2` (80MB, CPU, ~5ms per embed)
- In-memory HNSW index for similarity search: on write, find top-20 most similar memories
- This is the gatekeeper — without it, NLI/API must scan all memories (O(n))

### 3. Edge creation for contradictions

When classifier returns CONTRADICTION:
```python
graph_engine.graph.add_edge(
    str(memory_A_id), str(memory_B_id),
    type="contradicts",
    detector=classifier_name,   # "claude-3-haiku" | "deberta-v3-nli" | "miniLM-heuristic"
    confidence=0.92,
    timestamp=datetime.utcnow().isoformat(),
    batch_id=str(batch_uuid),
    entity_a_content=content_a[:100],
    entity_b_content=content_b[:100],
)
```

When classifier returns ENTAILMENT:
```python
graph_engine.graph.add_edge(
    str(memory_A_id), str(memory_B_id),
    type="supports",
    detector=classifier_name,
    confidence=0.92,
    timestamp=datetime.utcnow().isoformat(),
    batch_id=str(batch_uuid),
)
```

### 4. Contradiction audit schema (Postgres table)

```sql
CREATE TABLE IF NOT EXISTS contradiction_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL,
    entity_a_id UUID NOT NULL,
    entity_b_id UUID NOT NULL,
    model_name TEXT NOT NULL,
    input_pair JSONB NOT NULL,       -- {"a": "...", "b": "..."}
    result TEXT NOT NULL,             -- "CONTRADICTION" | "ENTAILMENT" | "NEUTRAL"
    confidence FLOAT,
    edge_type TEXT,                   -- "contradicts" | "supports" | NULL
    edge_id TEXT,                     -- iGraph edge ID if edge was created
    status TEXT DEFAULT 'pending',   -- "pending" | "completed" | "failed"
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    error TEXT
);
```

- `status = "pending"` → checkpoint/resume on crash
- `batch_id` groups related checks
- Persists forever (security log)

### 5. Background worker with priority queue

```
ContradictionQueue:
  HIGH priority (user writes) → process immediately, 1-at-a-time
  NORMAL priority (agent writes) → batch up to 10, process when idle
  BACKGROUND (scheduled) → every 5 min, cluster all memories by embedding,
    check cluster-internal pairs, add edges
```

Worker loop:
```python
def _worker_loop(self):
    while True:
        task = self._queue.get()
        if task is None:
            break
        # Load checkpoint from audit log
        # Process pair
        # Update audit log: status = "completed"
        # If crash → next startup queries WHERE status = "pending"
```

### 6. Wire into `_apply_memory_event()` in `client.py`

Current flow (line 467):
```python
meta = MetaStabilityService()
if meta.check_contradiction(state, delta):
    delta["contradiction_detected"] = True
```

New flow:
```python
meta = MetaStabilityService()
if meta.check_contradiction(state, delta):
    delta["contradiction_detected"] = True
    # Tier 1 found something — create edge immediately
else:
    # Tier 1 didn't find it — schedule semantic check
    contradiction_queue.put({
        "priority": "high" if source == "user" else "normal",
        "entity_id": entity_id,
        "new_content": delta.get("content", ""),
        "existing_content": state.current_value.get("content", ""),
    })
```

## Build Order

| Step | What | Why first |
|------|------|-----------|
| 1 | `embed_text()` — lightweight embedding model + ANN index | Gatekeeper for all semantic checks |
| 2 | `ContradictionClassifier` with API provider | Simplest route to a demoable result |
| 3 | Edge creation + audit log schema | The core data model |
| 4 | Wire into `_apply()` in `GraphEngine` | Contradiction edges become first-class graph citizens |
| 5 | Background worker with priority queue + checkpoint | Production-grade reliability |
| 6 | Local NLI classifier | Offline fallback (no API key needed) |

## Testing

- Extend `test_contradiction_accuracy.py` with semantic cases (LoRA example)
- Test edge creation: assert `graph.are_adjacent(a, b)` after detection
- Test audit log: assert `WHERE status = "pending"` resume after simulated crash
- Test namespace isolation: contradictions stay within namespace
