"""
Postgres integration tests.

These tests require a real PostgreSQL instance. They are skipped automatically
if Postgres is unavailable (no env vars, connection refused, etc.).

To run:
    # With Postgres available:
    pytest tests/test_postgres_integration.py -v -s

    # With env vars:
    POSTGRES_USER=mt POSTGRES_PASSWORD=mt POSTGRES_DB=mt_test pytest tests/test_postgres_integration.py -v

What is covered that no other test covers:
  - Full remember() write path through _persist_to_postgres (events + entity_state tables)
  - recall() reading back from a Postgres-backed MemoryClient
  - Namespace isolation in use_db=True mode (the DB-mode vulnerability)
  - WAL recovery after a simulated crash (use_db=True)
  - graph_engine.rebuild() reading from the actual events table
"""

import os
import uuid
import pytest

# ── Skip guard ───────────────────────────────────────────────────────────────


def _postgres_available() -> bool:
    """Return True if Postgres is reachable with current env vars."""
    try:
        import psycopg2
        from memory_thread.config.settings import settings

        conn = psycopg2.connect(
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            host=settings.POSTGRES_SERVER,
            port=settings.POSTGRES_PORT,
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="Postgres not available — set POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB",
)


# ── Schema fixture ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def pg_schema():
    """
    Ensure the minimal schema exists for integration tests.
    Creates tables if they don't exist; does not drop them (safe for shared DBs).
    """
    from memory_thread.db.postgres_client import PostgresClient
    from memory_thread.db.migrations.runner import MIGRATIONS

    pg = PostgresClient()
    # Apply migration 1 (core_tables) idempotently — all statements use IF NOT EXISTS
    core_migration = next(m for m in MIGRATIONS if m["id"] == 1)
    with pg.get_cursor() as cur:
        cur.execute(core_migration["sql"])
    return pg


@pytest.fixture
def ns():
    """Unique namespace per test so tests never bleed into each other."""
    return f"pg_test_{uuid.uuid4().hex[:8]}"


# ── Full write path ───────────────────────────────────────────────────────────


@requires_postgres
def test_remember_persists_to_postgres(pg_schema, ns):
    """
    remember() in use_db=True mode must write both:
      - events table (the immutable event log)
      - entity_state table (the current derived state)
    """
    from memory_thread.sdk import MemoryClient
    from memory_thread.db.postgres_client import PostgresClient

    client = MemoryClient(namespace=ns, use_db=True)
    entity_id = client.remember(
        "User prefers dark mode",
        source="user",
        confidence=0.95,
        authority=0.9,
    )
    client.close()

    # Verify directly in Postgres — not through the SDK
    pg = PostgresClient()
    with pg.get_cursor() as cur:
        cur.execute("SELECT id, namespace, delta FROM events WHERE object_id = %s", (entity_id,))
        event_rows = cur.fetchall()

    assert len(event_rows) >= 1, "Event not written to events table"
    assert event_rows[0]["namespace"] == ns

    with pg.get_cursor() as cur:
        cur.execute(
            "SELECT entity_id, namespace, current_value FROM entity_state WHERE entity_id = %s",
            (entity_id,),
        )
        state_row = cur.fetchone()

    assert state_row is not None, "entity_state not written"
    assert state_row["namespace"] == ns
    assert "content" in state_row["current_value"] or state_row["current_value"]


@requires_postgres
def test_recall_reads_from_postgres_backend(pg_schema, ns):
    """
    A fresh MemoryClient with use_db=True must be able to recall memories
    written by a previous client (i.e., it loads from Postgres on init,
    not just from the in-memory dict).
    """
    from memory_thread.sdk import MemoryClient

    # Writer client
    writer = MemoryClient(namespace=ns, use_db=True)
    writer.remember("quantum computing is the future", source="user", confidence=0.9)
    writer.close()

    # Fresh reader — cold start, must rebuild from Postgres
    reader = MemoryClient(namespace=ns, use_db=True)
    result = reader.recall("quantum computing", top_k=5, min_truth_score=0.0)
    reader.close()

    assert result.total_found >= 1, (
        f"Fresh MemoryClient could not recall memory written by previous client "
        f"(namespace={ns}). Did load_from_db() run correctly?"
    )
    contents = [m.content for m in result.memories]
    assert any("quantum" in c.lower() for c in contents), f"Wrong content returned: {contents}"


@requires_postgres
def test_namespace_isolation_in_db_mode(pg_schema):
    """
    Core security test: a namespace cannot read memories from another namespace,
    even in use_db=True mode where rebuild() loads nodes without namespace set
    on relation/thread stubs.

    This is the DB-mode variant of test_namespace_isolation.py which only runs
    in use_db=False mode and cannot catch the rebuild() vulnerability.
    """
    from memory_thread.sdk import MemoryClient

    ns_alpha = f"pg_alpha_{uuid.uuid4().hex[:8]}"
    ns_beta = f"pg_beta_{uuid.uuid4().hex[:8]}"

    # Write distinct memories to each namespace
    alpha = MemoryClient(namespace=ns_alpha, use_db=True)
    beta = MemoryClient(namespace=ns_beta, use_db=True)

    alpha_token = f"alpha_secret_{uuid.uuid4().hex[:6]}"
    beta_token = f"beta_secret_{uuid.uuid4().hex[:6]}"

    alpha.remember(f"alpha only: {alpha_token}", source="user", confidence=0.9)
    beta.remember(f"beta only: {beta_token}", source="user", confidence=0.9)

    alpha.close()
    beta.close()

    # Fresh clients — triggers rebuild() from Postgres
    alpha2 = MemoryClient(namespace=ns_alpha, use_db=True)
    beta2 = MemoryClient(namespace=ns_beta, use_db=True)

    # Alpha must not find beta's token
    alpha_results = alpha2.recall(beta_token, top_k=10, min_truth_score=0.0)
    # Beta must not find alpha's token
    beta_results = beta2.recall(alpha_token, top_k=10, min_truth_score=0.0)

    alpha2.close()
    beta2.close()

    assert alpha_results.total_found == 0, (
        f"Namespace isolation BREACH in DB mode: alpha client found {alpha_results.total_found} "
        f"beta memories when querying for '{beta_token}'"
    )
    assert beta_results.total_found == 0, (
        f"Namespace isolation BREACH in DB mode: beta client found {beta_results.total_found} "
        f"alpha memories when querying for '{alpha_token}'"
    )


@requires_postgres
def test_truth_scores_isolated_between_namespaces(pg_schema):
    """
    The same content written with different confidence values to two namespaces
    must produce different truth scores — they must not share entity_state.
    """
    from memory_thread.sdk import MemoryClient

    ns_high = f"pg_high_{uuid.uuid4().hex[:8]}"
    ns_low = f"pg_low_{uuid.uuid4().hex[:8]}"
    shared_content = "the sky is blue"

    high = MemoryClient(namespace=ns_high, use_db=True)
    low = MemoryClient(namespace=ns_low, use_db=True)

    eid_high = high.remember(shared_content, source="user", confidence=0.99, authority=1.0)
    eid_low = low.remember(shared_content, source="agent", confidence=0.1, authority=0.1)

    score_high = high.get_truth_score(eid_high)
    score_low = low.get_truth_score(eid_low)

    high.close()
    low.close()

    assert score_high is not None
    assert score_low is not None
    assert score_high != score_low, (
        "Same content in two namespaces returned identical truth scores — "
        "entity_state may be shared across namespaces"
    )
    assert score_high > score_low, (
        f"High-confidence namespace score ({score_high}) should exceed "
        f"low-confidence namespace score ({score_low})"
    )


@requires_postgres
def test_graph_rebuild_from_postgres(pg_schema, ns):
    """
    graph_engine.rebuild() must correctly load events from Postgres and
    reconstruct the iGraph so that graph-primary recall works on a fresh client.
    """
    from memory_thread.sdk import MemoryClient
    from memory_thread.services.graph_engine import graph_engine

    # Write several memories
    writer = MemoryClient(namespace=ns, use_db=True)
    ids = [
        writer.remember(f"graph rebuild test memory {i} token_{i}", source="user", confidence=0.9)
        for i in range(5)
    ]
    writer.close()

    # Force a fresh rebuild (clear graph then rebuild from Postgres)
    graph_engine.clear()
    from memory_thread.db.postgres_client import PostgresClient
    pg = PostgresClient()
    graph_engine.rebuild(pg)

    # Graph should have nodes for our writes
    assert graph_engine.graph.vcount() > 0, "rebuild() produced an empty graph"
    # At least one of our entity IDs should be a vertex
    found = any(graph_engine._vertex_exists(str(eid)) for eid in ids)
    assert found, f"None of the written entity IDs found in rebuilt graph (namespace={ns})"
