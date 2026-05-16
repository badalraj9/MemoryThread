# Roadmap

## Current Status

The mt-optimized work is complete for the current direct SDK write path.

Done:

- async enrichment outside synchronous writes
- sync and batched durability modes
- direct SDK batched write path
- WAL compaction controls
- write stats and optional write metrics
- final benchmark report
- focused tests for durability, recovery, tsvector migration, async enrichment drain, and truth-weighted recall

## Remaining Work

### 1. Persistence Architecture For 9K EPS

Direct SDK currently reaches 2.7K-4.8K EPS. To chase 9K EPS:

- shard WAL by thread or writer
- evaluate per-thread WAL files
- reduce namespace-wide lock contention
- benchmark long-running writes with compaction enabled

### 2. FTS + Graph Recall Benchmarks

Current recall validation uses focused tests. Add:

- FTS seed resolution latency and precision benchmark
- graph activation recall quality benchmark
- hybrid (graph + FTS) vs graph-only recall comparison
- cold-start (empty graph → pure FTS) latency benchmark

### 3. Production Shutdown

Add integration coverage for:

- SIGTERM/SIGINT shutdown
- `close()` under pending enrichment load
- WAL flush and compaction at shutdown

### 4. Documentation And Paper

Keep all public claims tied to current benchmark artifacts. Do not reintroduce stale phase claims.
