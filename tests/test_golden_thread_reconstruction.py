"""
Golden Thread reconstruction tests using GraphEngine.
"""

import time
import uuid

import pytest

from memory_thread.services.graph_engine import graph_engine
from memory_thread.models.events import Event, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.golden_thread import GoldenThreadService
from datetime import datetime


def _build_graph(entity_id: uuid.UUID, depth: int):
    """Build a chain of events in the GraphEngine."""
    graph_engine.clear()
    events = []

    for index in range(depth):
        if index == 0:
            action = ActionEnum.ADD
            content = "initial memory"
        elif index > 0 and index % 10 == 0:
            action = ActionEnum.UPDATE
            content = f"contradiction event {index}"
        elif index > 0 and index % 3 == 0:
            action = ActionEnum.OBSERVE
            content = f"corroboration event {index}"
        else:
            action = ActionEnum.UPDATE
            content = f"update event {index}"

        delta = {"content": content, "step": index}
        if index > 0 and index % 10 == 0:
            delta["contradiction_detected"] = True
            delta["conflicting_content"] = f"previous state {index - 1}"

        evt = Event(
            id=uuid.uuid4(),
            namespace="golden",
            actor=ActorEnum.USER if index % 2 == 0 else ActorEnum.AGENT,
            action=action,
            object_id=entity_id,
            delta=delta,
            antecedents=[events[-1].id] if events else [],
            truth_vector=TruthVector(
                confidence=0.8,
                authority=0.9,
                freshness=max(0.1, 1.0 - (index * 0.01)),
                corroboration=float(index),
            ),
        )
        evt.timestamp = datetime(2026, 1, 1, 0, 0, index)
        events.append(evt)

    for evt in events:
        graph_engine.apply_event(evt)


@pytest.mark.integration
def test_golden_thread_reconstructs_complete_causal_chain():
    gts = GoldenThreadService()
    timings = {}

    for depth in [1, 5, 10, 25, 50]:
        entity_id = uuid.uuid4()
        _build_graph(entity_id, depth)

        started = time.perf_counter()
        result = gts.trace(entity_id)
        timings[depth] = time.perf_counter() - started

        assert len(result.events) == depth
        assert [event.sequence for event in result.events] == list(range(1, depth + 1))
        assert result.narrative.strip()
        assert "Golden Thread:" in result.narrative
        assert "Current State:" in result.narrative
        assert "Consistency:" in result.narrative

    assert timings[50] < timings[5] * 10
