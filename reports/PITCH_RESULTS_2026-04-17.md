# Memory Thread Final Pitch Results

Generated: 2026-04-17T02:44:05+05:30

Branch: `mt-optimized`

Primary benchmark artifact:

- `reports/throughput_benchmark_2026-04-17_final_batch.json`

Benchmark command:

```bash
python benchmarks/benchmark_throughput.py --duration 10 --output reports/throughput_benchmark_2026-04-17_final_batch.json
```

## Latest Direct SDK Batched Results

| Scenario | Latest EPS |
| --- | ---: |
| 1 producer, no cognitive work | 4,780.7 EPS |
| 4 producers, no cognitive work | 3,164.8 EPS |
| 4 producers, cognitive work | 2,719.0 EPS |

## Speedup Over Sync Direct SDK

| Scenario | Sync Direct SDK | Batched Direct SDK | Speedup |
| --- | ---: | ---: | ---: |
| 1 producer, no cognitive work | 277.2 EPS | 4,780.7 EPS | 17.25x |
| 4 producers, no cognitive work | 267.0 EPS | 3,164.8 EPS | 11.85x |
| 4 producers, cognitive work | 222.9 EPS | 2,719.0 EPS | 12.20x |

Safe claim:

> Direct SDK batched writes now reach 2.7K-4.8K EPS locally, with 11.85x-17.25x speedup over sync direct SDK in the same benchmark.

## Durability Contract

| Mode | Return Semantics | Durable Boundary |
| --- | --- | --- |
| `sync` | returns after WAL append and commit are flushed | every `remember()` |
| `batched` | returns after WAL append and commit are accepted into the WAL buffer | `flush()` or `close()` |

Batched mode is not durable-at-return.

## Full Benchmark Snapshot

| Scenario | System | Accepted EPS | Processed EPS |
| --- | --- | ---: | ---: |
| 1 producer | `sdk_direct_sync` | 277.2 | 277.2 |
| 1 producer | `sdk_direct_batched` | 4,780.7 | 4,780.7 |
| 1 producer | `memory_thread batched WAL` | 7,845.2 | 7,845.2 |
| 1 producer | `baseline` | 12,687.4 | 12,687.4 |
| 4 producers | `sdk_direct_sync` | 267.0 | 267.0 |
| 4 producers | `sdk_direct_batched` | 3,164.8 | 3,164.8 |
| 4 producers | `memory_thread batched WAL` | 4,885.7 | 4,885.7 |
| 4 producers | `baseline` | 9,495.8 | 9,495.8 |
| 4 producers + cognitive | `sdk_direct_sync` | 222.9 | 222.9 |
| 4 producers + cognitive | `sdk_direct_batched` | 2,719.0 | 2,719.0 |
| 4 producers + cognitive | `memory_thread batched WAL` | 3,991.7 | 3,991.7 |
| 4 producers + cognitive | `baseline` | 8,677.2 | 8,677.2 |

## Verification

```bash
pytest tests/test_memory_client_durability_modes.py tests/test_truth_retrieval_quality.py tests/test_qdrant_dimension_guard.py tests/test_wal_recovery.py -q
```

Result:

```text
14 passed, 1 warning
```

## Claims To Avoid

- Do not claim 19.21x over baseline.
- Do not claim batched mode is durable at return.
- Do not claim direct SDK reaches 9K EPS.
