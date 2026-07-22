"""Tests for contradiction → graph edge creation."""

import pytest
import uuid
from unittest.mock import patch
from memory_thread.sdk.client import MemoryClient
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.models.events import TruthVector, EntityState
from datetime import datetime


@pytest.fixture(autouse=True)
def clear_graph():
    """Clear the singleton graph engine between tests so edges don't leak."""
    from memory_thread.services.graph_engine import graph_engine

    graph_engine.clear()
    yield


class TestContradictionEdge:
    def test_tier1_antonym_detection(self):
        """MetaStabilityService detects antonym key flips (exact word match on values)."""
        meta = MetaStabilityService()
        state = EntityState(
            entity_id=uuid.uuid4(),
            namespace="test",
            current_value={"likes": "hates"},
            truth_vector=TruthVector(confidence=0.8, authority=0.5, freshness=1.0, corroboration=1),
            version=1,
            last_event_id=uuid.uuid4(),
            updated_at=datetime.utcnow(),
        )
        assert meta.check_contradiction(state, {"likes": "likes"}), "likes→hates should trigger"

    def test_tier1_sign_conflict(self):
        meta = MetaStabilityService()
        state = EntityState(
            entity_id=uuid.uuid4(),
            namespace="test",
            current_value={"score": 5},
            truth_vector=TruthVector(confidence=0.8, authority=0.5, freshness=1.0, corroboration=1),
            version=1,
            last_event_id=uuid.uuid4(),
            updated_at=datetime.utcnow(),
        )
        assert meta.check_contradiction(state, {"score": -3})

    def test_tier1_bool_flip(self):
        meta = MetaStabilityService()
        state = EntityState(
            entity_id=uuid.uuid4(),
            namespace="test",
            current_value={"enabled": True},
            truth_vector=TruthVector(confidence=0.8, authority=0.5, freshness=1.0, corroboration=1),
            version=1,
            last_event_id=uuid.uuid4(),
            updated_at=datetime.utcnow(),
        )
        assert meta.check_contradiction(state, {"enabled": False})

    def test_tier1_no_false_positive(self):
        meta = MetaStabilityService()
        # Same value should not trigger
        state = EntityState(
            entity_id=uuid.uuid4(),
            namespace="test",
            current_value={"likes": "pizza"},
            truth_vector=TruthVector(confidence=0.8, authority=0.5, freshness=1.0, corroboration=1),
            version=1,
            last_event_id=uuid.uuid4(),
            updated_at=datetime.utcnow(),
        )
        assert not meta.check_contradiction(state, {"likes": "pizza"})
        # Unrelated key change should not trigger
        assert not meta.check_contradiction(state, {"age": 30})

    def test_contradiction_edge_created_when_flag_set(self):
        """_remember_direct creates 'contradicts' edge when delta has contradiction_detected=True."""
        mt = MemoryClient(use_db=False, namespace="test_contradiction_edge")

        eid = uuid.uuid4()
        mt.remember("first", source="user", memory_type="fact", entity_id=eid)

        with patch.object(MetaStabilityService, "check_contradiction", return_value=True):
            mt.remember("second", source="user", memory_type="fact", entity_id=eid)

        from memory_thread.services.graph_engine import graph_engine

        contradict_edges = [
            e for e in graph_engine.graph.es if e.attributes().get("type") == "contradicts"
        ]
        assert len(contradict_edges) >= 1

        edge = contradict_edges[-1]
        attrs = edge.attributes()
        assert attrs["detector"] == "tier1_key_based"

    def test_edge_survives_rebuild(self):
        """Contradiction edges are recreated on graph rebuild from persisted delta flag."""
        from memory_thread.services.graph_engine import graph_engine

        mt = MemoryClient(use_db=False, namespace="test_contradiction_rebuild")

        eid = uuid.uuid4()
        mt.remember("first", source="user", memory_type="fact", entity_id=eid)

        with patch.object(MetaStabilityService, "check_contradiction", return_value=True):
            mt.remember("second", source="user", memory_type="fact", entity_id=eid)

        edges_before = [
            e for e in graph_engine.graph.es if e.attributes().get("type") == "contradicts"
        ]
        assert len(edges_before) >= 1

        # Simulate rebuild by serializing events and replaying
        events = list(mt._event_log)
        graph_engine.clear()

        for event in events:
            graph_engine.apply_event(event)

        edges_after = [
            e for e in graph_engine.graph.es if e.attributes().get("type") == "contradicts"
        ]
        assert len(edges_after) >= 1
        assert edges_after[0].attributes()["detector"] == "tier1_key_based"

    def test_no_contradiction_no_edge(self):
        """Normal writes without contradiction should NOT create 'contradicts' edges."""
        mt = MemoryClient(use_db=False, namespace="test_no_contradiction_edge")

        mt.remember("User likes cats", source="user", memory_type="preference")
        mt.remember("User likes dogs", source="user", memory_type="preference")

        from memory_thread.services.graph_engine import graph_engine

        contradict_edges = [
            e
            for e in graph_engine.graph.es
            if e.attributes().get("type") == "contradicts"
            and e.attributes().get("detector") == "tier1_key_based"
        ]
        assert len(contradict_edges) == 0
