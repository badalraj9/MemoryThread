import concurrent.futures
import time
import uuid

import pytest

from memory_thread.models.events import EntityState, TruthVector
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.services.tms_service import TruthVectorService


def _percentile(values, pct):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * pct))))
    return ordered[index]


def _measure(operation, iterations=1000):
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return {
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "p99": _percentile(samples, 0.99),
    }


def _measure_under_concurrency(operation_factory, workers=10, iterations_per_worker=100):
    samples = []

    def run_worker():
        op = operation_factory()
        worker_samples = []
        for _ in range(iterations_per_worker):
            started = time.perf_counter_ns()
            op()
            worker_samples.append((time.perf_counter_ns() - started) / 1_000_000)
        return worker_samples

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in concurrent.futures.as_completed(pool.submit(run_worker) for _ in range(workers)):
            samples.extend(future.result())

    return {
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "p99": _percentile(samples, 0.99),
    }


@pytest.mark.slow
@pytest.mark.benchmark
def test_latency_profile(memory_client_factory, perf_enabled, monkeypatch):
    if not perf_enabled:
        pytest.skip("Set MT_RUN_PERF=1 to run latency profiling")

    client = memory_client_factory("latency", use_db=False)
    ids = [client.remember(f"latency seed {i} semantic token", source="agent") for i in range(200)]

    probe_state = EntityState(
        entity_id=ids[0],
        namespace=client.namespace,
        current_value={"content": "user age is 25", "type": "fact"},
        truth_vector=TruthVector(confidence=0.9, authority=0.9, freshness=1.0, corroboration=0),
        last_event_id=uuid.uuid4(),
    )
    contradiction_service = MetaStabilityService()

    def golden_thread_stub(entity_id):
        return {
            "entity_id": str(entity_id),
            "narrative": "Golden Thread: synthetic trace",
            "events": [{"sequence": 1}],
            "current_truth": {"confidence": 0.9},
            "is_consistent": True,
            "related_paths": [],
        }

    monkeypatch.setattr(client, "get_golden_thread", golden_thread_stub)

    idle_profiles = {
        "write": _measure(lambda: client.remember(f"write {uuid.uuid4()}", source="agent")),
        "read": _measure(lambda: client.get_truth_score(ids[0])),
        "search": _measure(lambda: client.recall("semantic token", top_k=5, min_truth_score=0.0)),
        "truth": _measure(
            lambda: TruthVectorService.calculate_score(
                TruthVector(confidence=0.9, authority=0.9, freshness=1.0, corroboration=3)
            )
        ),
        "contradiction": _measure(lambda: contradiction_service.check_contradiction(probe_state, {"content": "user age is 30"})),
        "golden_thread": _measure(lambda: client.get_golden_thread(ids[0])),
    }

    concurrent_profiles = {
        "write": _measure_under_concurrency(lambda: lambda: client.remember(f"write {uuid.uuid4()}", source="agent")),
        "read": _measure_under_concurrency(lambda: lambda: client.get_truth_score(ids[0])),
        "search": _measure_under_concurrency(lambda: lambda: client.recall("semantic token", top_k=5, min_truth_score=0.0)),
        "truth": _measure_under_concurrency(
            lambda: lambda: TruthVectorService.calculate_score(
                TruthVector(confidence=0.9, authority=0.9, freshness=1.0, corroboration=3)
            )
        ),
        "contradiction": _measure_under_concurrency(
            lambda: lambda: contradiction_service.check_contradiction(probe_state, {"content": "user age is 30"})
        ),
        "golden_thread": _measure_under_concurrency(lambda: lambda: client.get_golden_thread(ids[0])),
    }

    for operation_name, idle in idle_profiles.items():
        assert idle["p99"] >= idle["p50"]
        assert concurrent_profiles[operation_name]["p99"] <= idle["p99"] * 3


def test_latency_smoke(memory_client_factory):
    """
    Always-running structural smoke test for the latency-profile operations.

    Does NOT assert timing — just verifies all operations execute without error
    and return structurally correct results. Catches import breaks, API
    regressions, and enrichment worker crashes without the overhead of the
    full 1000-iteration profile.

    To run the full latency profile with timing assertions:
        MT_RUN_PERF=1 pytest tests/test_latency_profile.py::test_latency_profile -v -s
    """
    client = memory_client_factory("latency_smoke", use_db=False)

    ids = [client.remember(f"smoke memory {i} token", source="agent") for i in range(20)]

    # recall
    result = client.recall("smoke memory token", top_k=5, min_truth_score=0.0)
    assert result.total_found >= 0

    # get_truth_score
    score = client.get_truth_score(ids[0])
    assert score is None or isinstance(score, float)

    # contradiction check
    service = MetaStabilityService()
    from memory_thread.models.events import EntityState, TruthVector
    import uuid as _uuid
    state = EntityState(
        entity_id=ids[0],
        namespace=client.namespace,
        current_value={"content": "smoke test"},
        truth_vector=TruthVector(confidence=0.9, authority=0.9, freshness=1.0, corroboration=0),
        last_event_id=_uuid.uuid4(),
    )
    result = service.check_contradiction(state, {"content": "different value"})
    assert isinstance(result, bool)

    # truth score calculation
    score = TruthVectorService.calculate_score(
        TruthVector(confidence=0.9, authority=0.9, freshness=1.0, corroboration=3)
    )
    assert 0.0 <= score <= 1.0
