# API And SDK Usage

## Create A Client

```python
from memory_thread.sdk import MemoryClient

client = MemoryClient(namespace="project", use_db=False)
```

For high-throughput local writes:

```python
client = MemoryClient(
    namespace="project",
    use_db=False,
    durability_mode="batched",
)
```

For strict per-call durability:

```python
client = MemoryClient(
    namespace="project",
    use_db=False,
    durability_mode="sync",
)
```

## Remember

```python
entity_id = client.remember(
    "User prefers dark mode",
    source="user",
    confidence=0.95,
    authority=0.9,
    memory_type="preference",
)
```

## Flush And Close

In `batched` mode, call `flush()` when you need accepted writes to become durable:

```python
client.flush()
```

Call `close()` during shutdown:

```python
client.close()
```

`close()` drains enrichment work, flushes WAL records, and compacts committed WAL records when configured.

## Recall

```python
result = client.recall("dark mode", top_k=5, min_truth_score=0.0)
print(result.format())
```

Recall uses graph spreading activation with Postgres FTS for seed resolution. Falls back to keyword/in-memory search when the graph or database is unavailable.

## Write Stats

```python
stats = client.get_write_stats()
```

Useful fields:

- `durability_mode`
- `durable_append_count`
- `durable_commit_count`
- `buffered_record_count`
- `file_size_bytes`
- `compacted_count`

## Write Metrics

Write-path timing can be enabled or disabled:

```python
client = MemoryClient(enable_write_metrics=False)
```

Disable metrics for maximum throughput. Enable metrics when diagnosing bottlenecks.
