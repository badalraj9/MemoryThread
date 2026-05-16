# Architecture

Memory Thread is organized around a direct SDK write path, optional persistence backends, and asynchronous enrichment.

## Main Components

| Component | Role |
| --- | --- |
| `MemoryClient` | Public SDK entry point for `remember()`, `recall()`, `flush()`, and `close()` |
| WAL | Application-level write-ahead log for crash recovery |
| TMS/Event Model | Truth-vector events and derived entity state |
| In-memory state cache | Fast local state for direct SDK operation |
| PostgreSQL/SQLite | Optional durable state/event storage |
| Qdrant | Optional vector retrieval backend |
| Async enrichment queue | Qdrant indexing, entity extraction, and relation inference outside the synchronous write path |

## Direct Write Path

The optimized direct `remember()` path is:

1. normalize metadata
2. apply event/state update in memory
3. persist required state if a DB backend is active
4. append WAL record according to durability mode
5. schedule optional enrichment
6. return entity ID

Optional enrichment does not block direct writes:

- Qdrant indexing
- embedding generation
- user entity extraction
- relation inference

## Durability Modes

| Mode | Return Boundary | Durable Boundary |
| --- | --- | --- |
| `sync` | after WAL append and commit are flushed | each `remember()` |
| `batched` | after WAL append and commit are accepted into memory buffer | `flush()` or `close()` |

`batched` mode is the high-throughput mode. It is not durable-at-return.

## Recall Path

Recall uses Qdrant when available and falls back to keyword/in-memory retrieval when Qdrant is unavailable. Results are ranked using truth-aware scoring, not raw vector similarity alone.

## Current Bottleneck

The direct SDK now reaches 2.7K-4.8K EPS locally. Remaining write throughput limits are likely:

- shared WAL contention
- single namespace hot path
- event/state object overhead
- Python threading limits

Reaching 9K EPS on direct SDK writes likely requires WAL sharding or per-thread WAL files.
