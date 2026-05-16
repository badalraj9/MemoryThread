# Thesis Reference

## Abstract

Memory Thread is a cognitive memory layer for AI agents that attaches truth metadata and provenance to every memory. It combines event-sourced memory updates, truth-vector scoring, write-ahead logging, graceful degradation, and truth-aware recall. The current implementation validates correctness and durability properties while providing a measured high-throughput batched direct SDK mode.

## Problem

AI systems often retrieve memories as if all stored information is equally reliable. Vector databases provide semantic similarity, but they do not natively model confidence, source authority, temporal freshness, corroboration, or causal provenance.

Memory Thread addresses this by treating memory as an evolving state derived from events, where each event carries a truth vector and provenance context.

## Core Model

### Truth Vector

Each memory has:

- `confidence`: certainty in the content
- `authority`: trust level of the source
- `freshness`: temporal relevance
- `corroboration`: support from other observations

### Event Sourcing

Writes create events. Entity state is derived from those events. This supports replay, auditability, and Golden Thread-style provenance reconstruction.

### Durability

Memory Thread uses an application-level WAL because a memory write may span multiple storage systems. The WAL protects accepted operations even when PostgreSQL, SQLite, or Qdrant behavior differs.

## Current Architecture

The optimized direct write path keeps required state mutation in the foreground and moves optional enrichment to the background. Qdrant indexing, embeddings, entity extraction, and relation inference do not block `remember()` in the optimized path.

## Evaluation

Latest local benchmark:

| Scenario | Direct SDK Batched |
| --- | ---: |
| 1 producer | 4,780.7 EPS |
| 4 producers | 3,164.8 EPS |
| 4 producers + cognitive work | 2,719.0 EPS |

Latest focused verification:

```text
14 passed, 1 warning
```

Validated behavior includes WAL recovery, batched durability boundaries, Qdrant dimension guard behavior, async indexing drain on close, and truth-weighted recall ranking.

## Claims To Use

- Memory Thread tracks confidence, authority, freshness, corroboration, and provenance.
- Batched direct SDK writes reach 2.7K-4.8K EPS locally.
- Batched direct SDK is 11.85x-17.25x faster than sync direct SDK in the latest benchmark.
- Durability in batched mode is explicit through `flush()` and `close()`.

## Claims To Avoid

- Do not claim 19.21x over baseline.
- Do not claim batched mode is durable at return.
- Do not claim direct SDK reaches 9K EPS.

## Future Work

- WAL sharding or per-thread WAL files for higher direct SDK throughput
- broader recall/indexing benchmarks with real Qdrant
- long-running compaction policy validation
- formal crash-recovery semantics for batched mode
