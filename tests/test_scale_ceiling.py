import pytest
import time


def _percentile(values, pct):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * pct))))
    return ordered[index]


@pytest.mark.slow
@pytest.mark.benchmark
def test_scale_ceiling(memory_client_factory, perf_enabled):
    if not perf_enabled:
        pytest.skip("Set MT_RUN_PERF=1 to run scale ceiling profiling")

    client = memory_client_factory("scale", use_db=False)
    query_latencies = {}
    write_eps = {}

    for target_count in [1000, 2000, 4000, 8000, 16000, 32000, 64000]:
        while client.get_stats()["total_memories"] < target_count:
            index = client.get_stats()["total_memories"]
            client.remember(
                f"scale memory {index} retrieval profile semantic token",
                source="agent",
            )

        write_start = time.perf_counter()
        for i in range(100):
            client.remember(f"incremental write {target_count}-{i} semantic token", source="agent")
        write_eps[target_count] = 100 / max(time.perf_counter() - write_start, 1e-9)

        latencies = []
        for _ in range(100):
            started = time.perf_counter()
            client.recall("semantic token", top_k=5, min_truth_score=0.0)
            latencies.append((time.perf_counter() - started) * 1000)

        query_latencies[target_count] = {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        }

    inflection = next(
        (count for count, metrics in query_latencies.items() if metrics["p99"] > 500),
        None,
    )

    for target_count in [1000, 2000, 4000, 8000, 16000]:
        assert query_latencies[target_count]["p50"] < 100

    assert all(eps > 0 for eps in write_eps.values())
    assert inflection is None or inflection >= 1000
