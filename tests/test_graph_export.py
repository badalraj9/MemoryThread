"""Tests for GraphEngine.export_graph_json()."""

import pytest
from memory_thread.services.graph_engine import GraphEngine


@pytest.fixture
def engine():
    ge = GraphEngine()
    ge.graph.add_vertex(
        "a",
        type="entity",
        namespace="user",
        content="memory a",
        truth_confidence=0.9,
        truth_authority=0.5,
        truth_freshness=1.0,
    )
    ge.graph.add_vertex(
        "b",
        type="entity",
        namespace="user",
        content="memory b",
        truth_confidence=0.7,
        truth_authority=0.6,
        truth_freshness=0.8,
    )
    ge.graph.add_vertex(
        "c",
        type="entity",
        namespace="other",
        content="memory c",
        truth_confidence=0.5,
        truth_authority=0.4,
        truth_freshness=0.6,
    )
    ge.graph.add_edge("a", "b", type="relates", relation_type="supports", confidence=0.9)
    ge.graph.add_edge("b", "c", type="relates", relation_type="contradicts", confidence=0.8)
    return ge


class TestGraphExport:
    def test_export_full(self, engine):
        result = engine.export_graph_json()
        assert "nodes" in result
        assert "edges" in result
        assert "metadata" in result
        assert result["metadata"]["node_count"] == 3
        assert result["metadata"]["edge_count"] == 2
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2

    def test_export_filtered_by_namespace(self, engine):
        result = engine.export_graph_json(namespace="user")
        assert result["metadata"]["node_count"] == 2
        node_ids = {n["id"] for n in result["nodes"]}
        assert node_ids == {"a", "b"}

    def test_export_node_fields(self, engine):
        result = engine.export_graph_json()
        node_a = next(n for n in result["nodes"] if n["id"] == "a")
        assert node_a["truth_confidence"] == 0.9
        assert node_a["truth_authority"] == 0.5
        assert node_a["truth_freshness"] == 1.0
        assert isinstance(node_a["x"], float)
        assert isinstance(node_a["y"], float)
        assert isinstance(node_a["centrality"], float)
        assert isinstance(node_a["pagerank"], float)
        assert isinstance(node_a["community_id"], int)

    def test_export_edge_fields(self, engine):
        result = engine.export_graph_json()
        edge = result["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "type" in edge
        assert "relation_type" in edge
        assert "confidence" in edge

    def test_export_empty_graph(self):
        ge = GraphEngine()
        result = ge.export_graph_json()
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["metadata"]["node_count"] == 0
