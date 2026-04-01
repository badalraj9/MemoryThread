import time
import uuid

import pytest

import memory_thread.services.golden_thread as golden_thread_module


def _build_trace(entity_id, depth):
    events = []
    for index in range(depth):
        if index == 0:
            action = "ADD"
            delta = {"content": "initial memory", "step": index}
        elif index % 10 == 0:
            action = "UPDATE"
            delta = {
                "content": f"contradiction event {index}",
                "step": index,
                "contradiction_detected": True,
                "conflicting_content": f"previous state {index - 1}",
            }
        elif index % 3 == 0:
            action = "OBSERVE"
            delta = {"content": f"corroboration event {index}", "step": index, "corroborated": True}
        else:
            action = "UPDATE"
            delta = {"content": f"update event {index}", "step": index}

        events.append(
            {
                "id": str(uuid.uuid4()),
                "namespace": "golden",
                "timestamp": f"2026-01-01T00:00:{index:02d}",
                "actor": "USER" if index % 2 == 0 else "AGENT",
                "action": action,
                "object_id": str(entity_id),
                "delta": delta,
                "antecedents": [str(entity_id)],
                "truth_vector": {
                    "confidence": 0.8,
                    "authority": 0.9,
                    "freshness": max(0.1, 1.0 - (index * 0.01)),
                    "corroboration": index,
                },
            }
        )

    final_state = {
        "entity_id": str(entity_id),
        "namespace": "golden",
        "current_value": {"content": f"final state depth {depth}", "step": depth - 1},
        "truth_vector": events[-1]["truth_vector"],
        "version": depth,
        "last_event_id": events[-1]["id"],
        "updated_at": "2026-01-01T00:01:00",
    }
    return {"entity_id": str(entity_id), "events": events, "final_state": final_state}


class _FakeReplayService:
    def __init__(self, depth):
        self.depth = depth

    def capture_trace(self, entity_id):
        return _build_trace(entity_id, self.depth)

    def replay_trace(self, trace):
        return True, [], trace["final_state"]


class _FakeAncestryCache:
    def rebuild_cache(self, entity_id):
        return None


class _FakeQueryEngine:
    pass


class _FakePostgresClient:
    pass


@pytest.mark.integration
def test_golden_thread_reconstructs_complete_causal_chain(monkeypatch):
    timings = {}

    for depth in [1, 5, 10, 25, 50]:
        monkeypatch.setattr(golden_thread_module, "ReplayService", lambda d=depth: _FakeReplayService(d))
        monkeypatch.setattr(golden_thread_module, "AncestryCache", _FakeAncestryCache)
        monkeypatch.setattr(golden_thread_module, "QueryEngine", _FakeQueryEngine)
        monkeypatch.setattr(golden_thread_module, "PostgresClient", _FakePostgresClient)

        service = golden_thread_module.GoldenThreadService()
        entity_id = uuid.uuid4()

        started = time.perf_counter()
        result = service.trace(entity_id)
        timings[depth] = time.perf_counter() - started

        assert len(result.events) == depth
        assert [event.sequence for event in result.events] == list(range(1, depth + 1))
        assert [event.delta["step"] for event in result.events] == list(range(depth))
        assert all(str(entity_id) in event.related_entities for event in result.events)
        assert result.narrative.strip()
        assert "Golden Thread:" in result.narrative
        assert "Current State:" in result.narrative
        assert "Consistency:" in result.narrative
        assert "error" not in result.narrative.lower()

    assert timings[50] < timings[5] * 10
