# Durability And Performance

Latest benchmark artifact:

- `reports/throughput_benchmark_2026-04-17_final_batch.json`

Benchmark command:

```bash
python benchmarks/benchmark_throughput.py --duration 10 --output reports/throughput_benchmark_2026-04-17_final_batch.json
```

## Latest Direct SDK Results

| Scenario | Direct SDK Batched |
| --- | ---: |
| 1 producer, no cognitive work | 4,780.7 EPS |
| 4 producers, no cognitive work | 3,164.8 EPS |
| 4 producers, cognitive work | 2,719.0 EPS |

## Sync Vs Batched

| Scenario | Sync Direct SDK | Batched Direct SDK | Speedup |
| --- | ---: | ---: | ---: |
| 1 producer, no cognitive work | 277.2 EPS | 4,780.7 EPS | 17.25x |
| 4 producers, no cognitive work | 267.0 EPS | 3,164.8 EPS | 11.85x |
| 4 producers, cognitive work | 222.9 EPS | 2,719.0 EPS | 12.20x |

## Full Benchmark Snapshot

| Scenario | System | Accepted EPS | Processed EPS |
| --- | --- | ---: | ---: |
| 1 producer | `sdk_direct_sync` | 277.2 | 277.2 |
| 1 producer | `sdk_direct_batched` | 4,780.7 | 4,780.7 |
| 1 producer | `memory_thread batched WAL` | 7,845.2 | 7,845.2 |
| 4 producers | `sdk_direct_sync` | 267.0 | 267.0 |
| 4 producers | `sdk_direct_batched` | 3,164.8 | 3,164.8 |
| 4 producers | `memory_thread batched WAL` | 4,885.7 | 4,885.7 |
| 4 producers + cognitive | `sdk_direct_sync` | 222.9 | 222.9 |
| 4 producers + cognitive | `sdk_direct_batched` | 2,719.0 | 2,719.0 |
| 4 producers + cognitive | `memory_thread batched WAL` | 3,991.7 | 3,991.7 |

## Durability Contract

`sync` mode:

- WAL append is flushed before return.
- WAL commit is flushed before return.
- Lowest throughput, strongest per-call durability.

`batched` mode:

- WAL append and commit are accepted into an in-memory WAL buffer before return.
- `flush()` makes pending records durable.
- `close()` drains enrichment and flushes pending WAL records.
- Higher throughput, explicit durability boundary.

## Verified Tests

```bash
pytest tests/test_memory_client_durability_modes.py tests/test_truth_retrieval_quality.py tests/test_qdrant_dimension_guard.py tests/test_wal_recovery.py -q
```

Result:

```text
14 passed, 1 warning
```

## Known Limit

Direct SDK writes did not reach 9K EPS. The current range is 2.7K-4.8K EPS. A 9K target likely needs WAL sharding, per-thread WAL files, or another persistence layout.
