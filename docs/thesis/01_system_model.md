# System Model

Memory Thread models memory as truth-bearing state derived from events.

## Memory Unit

A memory contains:

- content
- namespace
- memory type
- source
- truth vector
- provenance through the latest event ID

## Truth Vector

The truth vector is:

```text
T = confidence, authority, freshness, corroboration
```

These dimensions let retrieval rank not only by relevance, but also by reliability.

## Event And State

Each write produces an event. Entity state is derived from the latest event and prior state. This design supports replay, recovery, provenance tracking, and future Golden Thread analysis.

## Durability

Memory Thread uses an application-level write-ahead log.

In `sync` mode, a write returns after WAL append and commit are flushed.

In `batched` mode, a write returns after WAL records are accepted into the WAL buffer. Durability is established by `flush()` or `close()`.

## Enrichment

The optimized system treats Qdrant indexing, embeddings, entity extraction, and relation inference as enrichment. These tasks run asynchronously and do not block the direct write path.
