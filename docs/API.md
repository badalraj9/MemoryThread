# API Reference — How to Use It

Practical reference for the Python SDK, REST API, CLI, and proxy. Covers usage, durability modes, configuration, and patterns.

See [SUMMARY.md](SUMMARY.md) for problem/benchmarks. See [ARCHITECTURE.md](ARCHITECTURE.md) for data flow and service internals.

---

## Installation

```bash
pip install -e ".[full]"        # API + DB + CLI + NLP
pip install -e ".[api,db,cli]"  # Production minimal
```

---

## Python SDK

### Getting a Client

```python
from memory_thread.sdk import MemoryClient

client = MemoryClient(
    namespace="my_app",            # Isolates memory — cross-namespace reads blocked
    use_db=True,                   # False = in-memory only (lost on restart)
    durability_mode="batched",     # "sync" = ~277 EPS, "batched" = ~4,780 EPS
    enable_write_metrics=True,     # ~5% overhead, useful for debugging
    auto_flush_interval=50.0,      # ms — batched auto-flush period
    wal_batch_size=100,            # Records per WAL batch
)
```

### `remember()` — Store a Memory

```python
entity_id = client.remember(
    content="User prefers dark mode with blue accents",
    source="user",              # "user" | "agent" | "system" → auto-maps to authority
    confidence=0.95,            # [0, 1] certainty in the content
    authority=0.9,              # Source trust (USER=1.0, AGENT=0.5, auto if omitted)
    memory_type="preference",   # "fact" | "preference" | "event" | "prediction" | "identity"
    thread_id="thread-uuid",    # Optional: group related memories
    metadata={"source": "chat", "session_id": "abc123"},
)
```

**Returns:** `str` — entity UUID. Multiple `remember()` calls for the same concept update the same entity (dedup by content hash).

### `recall()` — Retrieve Memories

```python
result = client.recall(
    query="dark mode",
    top_k=10,
    min_truth_score=0.0,        # Filter out low-confidence memories
    mode="hybrid",              # "graph" | "keyword" | "hybrid"
    max_graph_depth=3,
    graph_decay=0.5,
)

result.results      # List[Memory]
result.format()     # Pretty table
result.to_dict()    # Raw data
```

Each result includes: `entity_id`, `content`, `score` (√(activation × truth_score)), `activation`, `truth_score`, `memory_type`, `truth_vector`.

### `flush()` — Durability for Batched Mode

```python
client.flush()
```

Call at logical checkpoints: end of user session, every N records in batch, before shutdown. Without it, uncommitted writes are lost on crash.

### `close()` — Clean Shutdown

```python
client.close()
```

Drains enrichment, flushes WAL, compacts if threshold reached, closes DB connections. Always call in `finally`.

### Graph Operations

```python
# Create typed relation
client.add_relation(
    source_id="uuid-1",
    target_id="uuid-2",
    relation_type="works_with",   # any string
    confidence=0.9,
    metadata={"since": "2024-01-15"},
)

# Remove relation
client.remove_relation(
    source_id="uuid-1",
    target_id="uuid-2",
    relation_type="works_with",   # None = remove ALL between these
)

# Merge duplicate entities
client.merge_entities(
    source_id="uuid-1",           # merged INTO target
    target_id="uuid-2",           # survives
    strategy="authority",         # "authority" | "temporal"
)
```

All three create LINK/UNLINK/MERGE events and go through the same WAL + GraphEngine path as `remember()`.

### SecureMemoryClient — For Untrusted Code

```python
from memory_thread.sdk import SecureMemoryClient
client = SecureMemoryClient(
    namespace="sandbox",
    allowed_methods=["remember", "recall", "flush", "close"],
)
```

---

## REST API

Base: `http://localhost:8000`
Auth: `Authorization: Bearer <MT_API_KEY>` (optional)

### Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/memory/remember` | Store memory |
| POST | `/api/memory/recall` | Graph-primary recall |
| GET | `/api/memory/{id}` | Get entity |
| GET | `/api/memory/{id}/golden-thread` | Causal chain |
| POST | `/api/memory/relations` | Add relation |
| DELETE | `/api/memory/relations` | Remove relation |
| POST | `/api/memory/merge` | Merge entities |
| GET | `/api/graph` | Full graph snapshot |
| GET | `/api/graph/stats` | Node/edge counts |
| GET | `/api/events/stream` | SSE real-time deltas |
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness (DB + graph loaded) |
| GET | `/api/version` | Version |

### Example: Remember

```bash
curl -X POST http://localhost:8000/api/memory/remember \
  -H "Content-Type: application/json" \
  -d '{"content": "User prefers dark mode", "source": "user", "confidence": 0.95}'
# → {"entity_id": "uuid", "truth_score": 0.92}
```

### Example: Recall

```bash
curl -X POST http://localhost:8000/api/memory/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "dark mode", "top_k": 5}'
# → {"results": [...], "seed_count": 3, "graph_nodes_activated": 47}
```

### Example: SSE Stream

```bash
curl -N http://localhost:8000/api/events/stream
# data: {"type": "delta", "seq": 142, "changes": {...}}
```

Delta payload: `{nodes_added, nodes_removed, nodes_updated, edges_added, edges_removed}`.

---

## CLI

```bash
mt --help
mt ask "What does the user prefer?"      # Chat with memory
mt search "dark mode"                    # Search
mt whoami                                 # Identity + role
mt status                                 # Health

# Providers (encrypted at rest)
mt provider list
mt provider create groq --key gsk_xxx
mt provider set-default groq

# API keys
mt client-admin create                    # Shows key ONCE
mt client-admin list
mt client-admin revoke <key_id>

# Multi-agent
mt galaxy list --depth 2
mt galaxy diff --ns1 alpha --ns2 beta
```

---

## Proxy (`mt-serve`)

OpenAI-compatible proxy with automatic memory injection.

```bash
mt-serve                                    # Ollama (default)
mt-serve --backend https://api.openai.com/v1
mt-serve --backend https://openrouter.ai/api/v1
mt-serve --port 8080
```

**What it does:** Intercepts `/v1/chat/completions`, extracts user message → `recall()` → injects relevant memories into system prompt → redacts secrets (API keys, SSNs, tokens) → forwards to backend LLM → streams response.

Point any OpenAI-compatible client to `http://localhost:8000/v1`.

---

## Durability Modes

| Mode | Return Guarantee | Data Safe After | Throughput | When to Use |
|---|---|---|---|---|
| `sync` | WAL flushed to disk | Each `remember()` | ~277 EPS | Critical data, financial, legal |
| `batched` | WAL accepted to memory | `flush()` or `close()` | ~4,780 EPS | Ingestion, analytics, bulk |

**Batched is NOT durable-at-return.** Use patterns:

```python
# Batch with checkpoints
client = MemoryClient(durability_mode="batched")
try:
    for i, doc in enumerate(documents):
        client.remember(doc.text, source="system", confidence=0.8, memory_type="fact")
        if i % 500 == 0:
            client.flush()
finally:
    client.close()
```

---

## Configuration (Environment Variables)

```bash
# Database
MT_DATABASE_URL=postgresql://user:pass@localhost:5432/memory_thread
MT_USE_SQLITE=false

# API
MT_API_KEY=your-secret-key
MT_ALLOWED_ORIGINS=http://localhost:5173

# WAL
WAL_DURABILITY_MODE=batched
WAL_BATCH_SIZE=100
WAL_FLUSH_INTERVAL_MS=50
WAL_COMPACTION_THRESHOLD=10000

# Recall
MT_RECALL_MODE=hybrid
RECALL_GRAPH_MAX_DEPTH=3
RECALL_GRAPH_DECAY=0.5
RECALL_FTS_FALLBACK=true

# Vault (Fernet encryption)
MT_SECRET_KEY=base64-32-byte-key
```

Generate Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## Error Handling

```python
from memory_thread.exceptions import MemoryThreadError, ValidationError, DurabilityError, NamespaceIsolationError

try:
    client.remember("content")
except NamespaceIsolationError:
    print("Cross-namespace access blocked — check your namespace")
except MemoryThreadError as e:
    print(f"[{e.code}] {e.message}")
```

HTTP codes: 200=success, 400=bad request, 401=unauthorized, 404=not found, 500=internal, 503=unavailable.

---

## Common Patterns

### Threaded conversation

```python
thread_id = client.remember("User: Hello", source="user")
client.remember("Agent: Hi!", source="agent", thread_id=thread_id)
client.remember("User: I like dark mode", source="user", thread_id=thread_id)
```

### Namespace isolation

```python
# Completely separate
a = MemoryClient(namespace="team-a")
b = MemoryClient(namespace="team-b")
a.remember("secret")        # team-a only
b.recall("secret")          # empty — blocked at SDK level
```

### Truth score filtering

```python
# Default min_truth_score=0.0 returns everything
# Raise it to filter low-confidence
results = client.recall("query", min_truth_score=0.5)
```

---

## Debugging

| Symptom | Check |
|---|---|
| Slow recall | `GET /api/graph/stats` — graph size; reduce `max_graph_depth` |
| Missing memories | `GET /health/ready` — GraphEngine loaded? PostgreSQL connected? |
| Batched data lost | Did you call `flush()` and `close()`? |
| Proxy not injecting | `MT_PROXY_BACKEND` reachable? Check proxy logs |
| SSE not connecting | CORS (`MT_ALLOWED_ORIGINS`), firewall, proxy buffering |

---

## Version Compatibility

SDK 1.0.x → API v1 → Python 3.9+. Breaking changes on major version bump only.