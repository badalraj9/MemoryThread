"""
API layer tests — FastAPI TestClient coverage for server.py endpoints.

Tests the HTTP contract: routing, auth, request/response serialisation, and
error handling. The SDK is not mocked — these use MemoryClient(use_db=False)
which runs in-memory so no Postgres is needed.
"""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_api_key(monkeypatch):
    """Ensure MT_API_KEY is unset by default so auth is open unless a test sets it."""
    monkeypatch.delenv("MT_API_KEY", raising=False)


@pytest.fixture
def client():
    # Import inside fixture so monkeypatching of env vars takes effect first
    from memory_thread.api.server import app, _client_cache

    _client_cache.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    _client_cache.clear()


# ── Health ──────────────────────────────────────────────────────────────────


def test_root_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Memory Thread" in resp.json()["message"]


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "timestamp" in data
    assert "version" in data


# ── Remember ────────────────────────────────────────────────────────────────


def test_remember_stores_memory(client):
    resp = client.post(
        "/memory/remember",
        json={
            "content": "User prefers dark mode",
            "source": "user",
            "confidence": 0.95,
            "namespace": "test_api_remember",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "entity_id" in data
    assert data["message"] == "Memory stored successfully"


def test_remember_requires_content(client):
    resp = client.post(
        "/memory/remember",
        json={"source": "agent"},  # missing required 'content'
    )
    assert resp.status_code == 422  # Pydantic validation error


def test_remember_rejects_out_of_range_confidence(client):
    resp = client.post(
        "/memory/remember",
        json={"content": "test", "confidence": 1.5},  # > 1.0
    )
    assert resp.status_code == 422


# ── Recall ───────────────────────────────────────────────────────────────────


def test_recall_returns_results(client):
    # Write first
    client.post(
        "/memory/remember",
        json={"content": "dark mode is preferred", "namespace": "test_api_recall"},
    )
    # Then recall — correct endpoint is POST /memory/recall
    resp = client.post(
        "/memory/recall",
        json={"query": "dark mode", "namespace": "test_api_recall", "min_truth_score": 0.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "query" in data
    assert "total_found" in data
    assert "memories" in data
    assert isinstance(data["memories"], list)


def test_recall_empty_namespace_returns_empty(client):
    resp = client.post(
        "/memory/recall",
        json={"query": "anything", "namespace": "test_api_empty_ns_xyz", "min_truth_score": 0.0},
    )
    assert resp.status_code == 200
    assert resp.json()["total_found"] == 0


def test_recall_requires_query(client):
    resp = client.post("/memory/recall", json={"namespace": "ns"})
    assert resp.status_code == 422


# ── Auth ─────────────────────────────────────────────────────────────────────


def test_no_auth_required_when_key_not_set(client):
    """With MT_API_KEY unset, all endpoints are open."""
    resp = client.post(
        "/memory/remember",
        json={"content": "open access test", "namespace": "test_api_auth"},
    )
    assert resp.status_code == 200


def test_auth_required_when_key_set(monkeypatch):
    """With MT_API_KEY set, requests without a token get 403."""
    monkeypatch.setenv("MT_API_KEY", "test-secret-key")
    # Re-import to pick up the patched env
    from memory_thread.api import server as srv
    import importlib

    importlib.reload(srv)
    from memory_thread.api.server import app, _client_cache

    _client_cache.clear()

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/memory/remember",
            json={"content": "auth test", "namespace": "test_api_auth"},
        )
        # Expecting 401 (no token) or 403 (forbidden)
        assert resp.status_code in (401, 403), resp.text


def test_auth_passes_with_correct_bearer_token(monkeypatch):
    """Correct bearer token is accepted."""
    monkeypatch.setenv("MT_API_KEY", "test-secret-key")
    from memory_thread.api import server as srv
    import importlib

    importlib.reload(srv)
    from memory_thread.api.server import app, _client_cache

    _client_cache.clear()

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/memory/remember",
            json={"content": "authed write", "namespace": "test_api_auth"},
            headers={"Authorization": "Bearer test-secret-key"},
        )
        assert resp.status_code == 200, resp.text


# ── Health is always open ────────────────────────────────────────────────────


def test_health_open_even_with_key_set(monkeypatch):
    """Health endpoint has no auth dependency — always accessible."""
    monkeypatch.setenv("MT_API_KEY", "test-secret-key")
    from memory_thread.api import server as srv
    import importlib

    importlib.reload(srv)
    from memory_thread.api.server import app

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/health")
        assert resp.status_code == 200


# ── Rate Limiting ────────────────────────────────────────────────────────────


def test_rate_limiter_allows_normal_traffic(client):
    """Normal traffic well below 100 RPM is never rate-limited."""
    for _ in range(5):
        resp = client.post(
            "/memory/remember",
            json={"content": "rate test", "namespace": "test_api_rate"},
        )
        assert resp.status_code == 200


# ── Graph Endpoints ──────────────────────────────────────────────────────────


def test_get_graph_returns_empty(client):
    resp = client.get("/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "metadata" in data


def test_get_graph_after_remember(client):
    client.post("/memory/remember", json={"content": "graph test node", "namespace": "test_graph"})
    resp = client.get("/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["node_count"] >= 1


def test_get_graph_stats(client):
    client.post("/memory/remember", json={"content": "stats test", "namespace": "test_graph"})
    resp = client.get("/graph/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "node_count" in data
    assert "edge_count" in data
    assert "density" in data


def test_search_graph(client):
    client.post(
        "/memory/remember", json={"content": "unique search term xkcd", "namespace": "test_graph"}
    )
    resp = client.post("/graph/search", json={"query": "unique search", "attr": "content"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("unique search term xkcd" in r["content"] for r in data["results"])


def test_graph_paths_empty(client):
    import uuid

    fake_a = str(uuid.uuid4())
    fake_b = str(uuid.uuid4())
    resp = client.post("/graph/paths", json={"source": fake_a, "target": fake_b})
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False


def test_activation_requires_seeds(client):
    resp = client.post("/graph/activation", json={"seeds": []})
    assert resp.status_code == 422


def test_activation_returns_empty_for_missing_seeds(client):
    import uuid

    resp = client.post(
        "/graph/activation",
        json={"seeds": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_activated"] == 0
    assert data["activation_map"] == {}


def test_activation_returns_nodes_after_remember(client):
    # Write a memory so a node exists
    client.post(
        "/memory/remember",
        json={"content": "activation target node", "namespace": "test_activation"},
    )
    # Recall via graph to get a node ID, then activate from it
    from memory_thread.services.graph_engine import graph_engine

    nodes = graph_engine.find_nodes("namespace", "test_activation")
    assert len(nodes) >= 1
    resp = client.post(
        "/graph/activation",
        json={
            "seeds": nodes[:1],
            "max_depth": 2,
            "decay_per_hop": 0.5,
            "truth_threshold": 0.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_activated"] >= 1
    assert nodes[0] in data["activation_map"]


# ── SSE Events ──────────────────────────────────────────────────────────────


def test_graph_engine_publishes_on_remember():
    """graph_engine._apply() publishes graph_mutation events on remember()."""
    from memory_thread.services.graph_engine import graph_engine
    from memory_thread.services.event_bus import event_bus
    import queue
    import json

    graph_engine.clear()
    event_bus._subscribers.clear()

    q = event_bus.subscribe()
    from memory_thread.sdk.client import MemoryClient

    mt = MemoryClient(use_db=False, namespace="test_sse_unit")
    mt.remember("sse publish test", source="user")

    # WAL events fire before graph_mutation; consume until we find it
    msg = None
    for _ in range(10):
        raw = q.get(timeout=2)
        parsed = json.loads(raw)
        if parsed["type"] == "graph_mutation":
            msg = parsed
            break

    assert msg is not None, "graph_mutation event not received"
    assert msg["type"] == "graph_mutation"
    assert "object_id" in msg["data"]
    assert msg["data"]["action"] in ("ADD", "UPDATE")
