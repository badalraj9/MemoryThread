"""
Memory Thread MCP Server.

Exposes MT's core memory operations as MCP tools for AI agents.
Supports stdio (default) and SSE transports.

Usage:
    # stdio — for MCP clients (Claude Code, Cursor, etc.)
    python -m memory_thread.mcp_server

    # SSE — for HTTP-based MCP clients
    python -m memory_thread.mcp_server --transport sse --port 8001
"""

import os
import sys
import uuid
import secrets
from typing import Optional

from mcp.server.fastmcp import FastMCP


# ==============================================================================
# Client factory (same pattern as api/server.py)
# ==============================================================================


_client_cache: dict = {}


def _get_client(namespace: str = "default"):
    if namespace not in _client_cache:
        from memory_thread.sdk import MemoryClient

        _client_cache[namespace] = MemoryClient(
            namespace=namespace, use_db=True, default_authority=0.5
        )
    return _client_cache[namespace]


def _verify_api_key(api_key: Optional[str]) -> Optional[str]:
    expected = os.environ.get("MT_API_KEY", "")
    if not expected:
        return None
    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise ValueError("Invalid API key")
    return api_key


# ==============================================================================
# FastMCP app
# ==============================================================================

mcp = FastMCP(
    "Memory Thread",
    instructions="Truth-preserving cognitive memory for AI agents. Store and recall memories with graph-based retrieval and contradiction detection.",
)


# ---------------------------------------------------------------------------
# Core: remember
# ---------------------------------------------------------------------------


@mcp.tool(
    name="remember",
    description="Store a piece of information into memory. MT will extract entities and relations automatically.",
)
def remember(
    content: str,
    source: str = "agent",
    confidence: float = 0.8,
    memory_type: str = "fact",
    namespace: str = "default",
    api_key: Optional[str] = None,
) -> str:
    _verify_api_key(api_key)
    client = _get_client(namespace)
    entity_id = client.remember(
        content=content,
        source=source,
        confidence=confidence,
        memory_type=memory_type,
    )
    return str(entity_id)


# ---------------------------------------------------------------------------
# Core: recall
# ---------------------------------------------------------------------------


@mcp.tool(
    name="recall",
    description="Search memories using graph-based spreading activation with keyword fallback. Returns relevant memories with truth scores.",
)
def recall(
    query: str,
    top_k: int = 5,
    min_truth_score: float = 0.3,
    namespace: str = "default",
    api_key: Optional[str] = None,
) -> str:
    _verify_api_key(api_key)
    client = _get_client(namespace)
    result = client.recall(query, top_k=top_k, min_truth_score=min_truth_score)
    if not result.memories:
        return "No relevant memories found."
    lines = [f"Found {result.total_found} memories (showing top {len(result.memories)}):"]
    for m in result.memories:
        lines.append(
            f"- [{m.truth_score:.0%}] {m.content} "
            f"(confidence={m.confidence:.2f}, freshness={m.freshness:.2f})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Check contradiction
# ---------------------------------------------------------------------------


@mcp.tool(
    name="check_contradiction",
    description="Check if a statement contradicts any existing memory. Uses key-based and antonym detection (not semantic).",
)
def check_contradiction(
    content: str,
    namespace: str = "default",
    api_key: Optional[str] = None,
) -> str:
    _verify_api_key(api_key)
    client = _get_client(namespace)
    result = client.check_contradiction(content)
    if result.get("has_contradiction"):
        return (
            f"Contradiction detected: '{content}' conflicts with "
            f"'{result.get('conflicting_memory', '')}' "
            f"(entity: {result.get('entity_id', 'unknown')})"
        )
    return "No contradiction detected."


# ---------------------------------------------------------------------------
# Golden Thread
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_golden_thread",
    description="Trace the complete causal history of a memory entity. Shows every event that shaped it, current truth score, and consistency status.",
)
def get_golden_thread(
    entity_id: str,
    namespace: str = "default",
    api_key: Optional[str] = None,
) -> str:
    _verify_api_key(api_key)
    client = _get_client(namespace)
    try:
        eid = uuid.UUID(entity_id)
    except ValueError:
        return f"Invalid entity_id: {entity_id}"
    result = client.get_golden_thread(eid)
    lines = [
        f"Entity: {result['entity_id']}",
        f"Consistent: {result['is_consistent']}",
        f"Current truth: {result['current_truth']:.2f}",
        f"",
        f"Narrative:",
        result["narrative"],
    ]
    if result.get("related_paths"):
        lines.append("")
        lines.append("Related paths:")
        for path in result["related_paths"][:5]:
            lines.append(f"  - {path}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_stats",
    description="Get memory system statistics — total memories, events, average truth score, and DB type.",
)
def get_stats(
    namespace: str = "default",
    api_key: Optional[str] = None,
) -> str:
    _verify_api_key(api_key)
    client = _get_client(namespace)
    stats = client.get_stats()
    lines = [
        f"Total memories: {stats.get('total_memories', 0)}",
        f"Total events: {stats.get('total_events', 0)}",
        f"Average truth score: {stats.get('avg_truth_score', 0):.2%}",
        f"Database: {stats.get('db_type', 'unknown')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_health",
    description="Check the health of the MT system — Postgres connectivity and memory health score.",
)
def get_health(
    namespace: str = "default",
    api_key: Optional[str] = None,
) -> str:
    _verify_api_key(api_key)
    client = _get_client(namespace)
    health = client.get_health()
    postgres_connected = False
    try:
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute("SELECT 1")
        postgres_connected = True
    except Exception:
        pass
    lines = [
        f"Status: {'healthy' if postgres_connected else 'degraded'}",
        f"PostgreSQL: {'connected' if postgres_connected else 'unavailable'}",
        f"Health score: {health.get('health_score', 1.0):.0%}",
        f"Low truth memories: {health.get('low_truth_memories', 0)}",
        f"Stale memories: {health.get('stale_memories', 0)}",
    ]
    return "\n".join(lines)


# ==============================================================================
# Entry point
# ==============================================================================


def run():
    transport = os.environ.get("MT_MCP_TRANSPORT", "stdio")
    if transport == "sse":
        port = int(os.environ.get("MT_MCP_PORT", "8001"))
        host = os.environ.get("MT_MCP_HOST", "0.0.0.0")
        print(f"MCP SSE server starting on {host}:{port}", file=sys.stderr)
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
