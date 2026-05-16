# Memory Thread: Truth-Preserving Memory For AI Agents

## Abstract

Memory Thread is a cognitive memory layer for AI systems that stores information with explicit reliability metadata and provenance. Instead of treating every retrieved vector as equally valid, Memory Thread attaches a truth vector to each memory: confidence, authority, freshness, and corroboration. The system combines event-sourced state derivation, application-level write-ahead logging, graceful backend degradation, and truth-aware recall. The current `mt-optimized` implementation validates durability and recovery behavior and reaches 2.7K-4.8K events per second in direct SDK batched writes on the latest local benchmark.

## 1. Problem

AI agents need memory, but most memory systems optimize for semantic similarity rather than epistemic quality. A vector hit can be recent or stale, authoritative or speculative, corroborated or isolated. Without explicit truth metadata and provenance, agents can retrieve plausible but unreliable information.

Memory Thread addresses this by making memory reliability a first-class data model concern.

## 2. Contributions

Memory Thread provides:

1. **Truth vectors:** confidence, authority, freshness, and corroboration attached to memories.
2. **Event-sourced memory:** writes create events, and entity state is derived from those events.
3. **Application-level WAL:** durability spans in-memory state, optional SQL storage, and optional SQL persistence.
4. **Graceful degradation:** the system continues operating when PostgreSQL is unavailable.
5. **Optimized direct SDK writes:** batched mode gives high-throughput local writes with explicit `flush()` and `close()` durability boundaries.

## 3. Architecture

The public interface is `MemoryClient`. The key operations are:

- `remember()`: store a memory with truth metadata
- `recall()`: retrieve truth-ranked memories
- `flush()`: make pending batched WAL records durable
- `close()`: drain enrichment, flush WAL, and release resources

The optimized write path separates required state mutation from optional enrichment. Entity extraction and relation inference are scheduled asynchronously rather than blocking `remember()`.

## 4. Durability Model

Memory Thread supports two direct SDK durability modes.

| Mode | Return Semantics | Durable Boundary |
| --- | --- | --- |
| `sync` | returns after append and commit are flushed | each `remember()` |
| `batched` | returns after append and commit are accepted into the WAL buffer | `flush()` or `close()` |

Batched mode is a high-throughput accepted-write mode. It should not be described as durable-at-return.

## 5. Evaluation

Latest artifact:

- `reports/throughput_benchmark_2026-04-17_final_batch.json`

Latest direct SDK batched write results:

| Scenario | Throughput |
| --- | ---: |
| 1 producer, no cognitive work | 4,780.7 EPS |
| 4 producers, no cognitive work | 3,164.8 EPS |
| 4 producers, cognitive work | 2,719.0 EPS |

Compared with sync direct SDK in the same benchmark:

| Scenario | Speedup |
| --- | ---: |
| 1 producer, no cognitive work | 17.25x |
| 4 producers, no cognitive work | 11.85x |
| 4 producers, cognitive work | 12.20x |

Focused verification:

```text
14 passed, 1 warning
```

The verification covers WAL recovery, sync and batched durability boundaries, WAL compaction, Postgres FTS search, async enrichment drain on close, and truth-weighted retrieval ranking.

## 6. Limitations

Memory Thread does not currently reach 9K EPS on direct SDK writes. The measured range is 2.7K-4.8K EPS. Reaching 9K likely requires a deeper persistence design, such as WAL sharding, per-thread WAL files, or a different persistence layout.

The old 19.21x throughput claim is unsupported by the current benchmark harness and should not be used.

## 7. Conclusion

Memory Thread demonstrates a practical path for truth-preserving AI memory: reliability metadata, event provenance, recovery semantics, and optimized write throughput can coexist. The current implementation is correctness-validated and performance-improved, with remaining work concentrated around deeper WAL architecture and real-backend recall benchmarking.
