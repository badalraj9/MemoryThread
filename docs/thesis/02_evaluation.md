# Evaluation

Latest benchmark artifact:

- `reports/throughput_benchmark_2026-04-17_final_batch.json`

## Direct SDK Batched Throughput

| Scenario | EPS |
| --- | ---: |
| 1 producer, no cognitive work | 4,780.7 |
| 4 producers, no cognitive work | 3,164.8 |
| 4 producers, cognitive work | 2,719.0 |

## Sync Versus Batched

| Scenario | Speedup |
| --- | ---: |
| 1 producer, no cognitive work | 17.25x |
| 4 producers, no cognitive work | 11.85x |
| 4 producers, cognitive work | 12.20x |

## Correctness Verification

Latest focused test command:

```bash
pytest tests/test_memory_client_durability_modes.py tests/test_truth_retrieval_quality.py tests/test_qdrant_dimension_guard.py tests/test_wal_recovery.py -q
```

Result:

```text
14 passed, 1 warning
```

Verified areas:

- WAL recovery
- sync durability boundary
- batched `flush()` and `close()` durability boundaries
- WAL compaction
- async indexing drain
- Qdrant dimension guard
- truth-weighted recall ranking

## Limitations

The direct SDK does not reach 9K EPS. Current results support a 2.7K-4.8K EPS claim for local direct SDK batched writes. Reaching 9K likely requires WAL sharding or a different persistence design.
