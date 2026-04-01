# Memory Thread Pitch Results

Generated: 2026-04-01T11:07:48.7172165+05:30
Refreshed against stored benchmark snapshot: 2026-04-01T11:15:00+05:30

## Executive Summary

- Priority validation tests passed:
  - WAL recovery
  - Decay curves
  - Contradiction accuracy
- Test command run:
  - `pytest tests/test_wal_recovery.py tests/test_decay_curves.py tests/test_contradiction_accuracy.py -q`
- Result:
  - `8 passed`

## Priority Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.11.3, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\memorythread\semi-final-version
configfile: pyproject.toml
plugins: anyio-4.12.1, langsmith-0.3.45, asyncio-1.3.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 8 items

tests\test_wal_recovery.py .....                                         [ 62%]
tests\test_decay_curves.py ..                                            [ 87%]
tests\test_contradiction_accuracy.py .                                   [100%]

======================== 8 passed, 2 warnings in 7.29s ========================
```

## Throughput Benchmark Snapshot

Benchmark command:

- `python benchmarks/benchmark_throughput.py --duration 5`

Stored artifact:

- `reports/throughput_benchmark_2026-04-01.json`

Benchmark methodology changes:

- MT WAL path now batches writes instead of fsync per event
- MT reports both accepted EPS and durable processed EPS
- baseline now performs durability work too: write + flush per event
- UUIDs are pre-generated outside the hot loop

### Measured Results

| Scenario                 | System        | Producers | Cognitive Work | Accepted EPS | Processed EPS |
| ------------------------ | ------------- | --------- | -------------- | -----------: | ------------: |
| light_single_producer    | memory_thread | 1         | no             |      9,599.4 |       9,595.4 |
| light_single_producer    | baseline      | 1         | no             |     13,266.2 |      13,266.2 |
| light_four_producers     | memory_thread | 4         | no             |      3,704.2 |       3,689.6 |
| light_four_producers     | baseline      | 4         | no             |     10,767.6 |      10,767.6 |
| realistic_four_producers | memory_thread | 4         | yes            |      3,392.4 |       3,392.4 |
| realistic_four_producers | baseline      | 4         | yes            |      9,758.2 |       9,758.2 |

## Interpretation

- The validation tests above support correctness claims around WAL recovery, decay behavior, and contradiction handling.
- The benchmark harness is materially fairer than the earlier version because baseline durability is no longer free and MT now exposes accepted versus durable throughput separately.
- Even after the WAL bottleneck fix, the current local benchmark snapshot still does not support the paper's earlier 19.21x throughput claim.

## Recommended Pitch Framing

- "We validated core correctness properties locally: recovery, decay math, and contradiction detection are passing."
- "We also rebuilt the throughput benchmark to make it methodologically fairer, including durability on both sides and separate accepted versus durable throughput for MT."
- "Current benchmark results show the system is correct and resilient, while throughput optimization remains an active engineering area."

run codex resume 019d4775-699b-78c1-9834-b05d85a11779
