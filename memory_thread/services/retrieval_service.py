"""Retrieval service — graph-primary and vector fallback paths."""

import logging
import time
from typing import List, Dict, Optional, Tuple

from memory_thread.config.settings import settings
from memory_thread.models.events import TruthVector
from memory_thread.services.content_resolver import resolve_content as _resolve_content

log = logging.getLogger(__name__)

# ── Read-time influence trust map ──────────────────────────────────────

_TRUST_MAP_CACHE: Dict[str, Tuple[float, Tuple]] = {}
_TRUST_MAP_TTL = 60.0


def _load_namespace_trust_map(requesting_namespace: str) -> Optional[Dict[str, float]]:
    """Fetch cross-namespace trust weights from galaxy_influence_matrix.

    Only queries PG if the connection pool was already initialized (by a
    previous PersistenceService.connect() call). Falls back to self-trust
    when PG is unavailable. Cached for _TRUST_MAP_TTL seconds.
    """
    now = time.monotonic()
    cached = _TRUST_MAP_CACHE.get(requesting_namespace)
    if cached and (now - cached[0]) < _TRUST_MAP_TTL:
        return dict(cached[1])

    trust_map: Dict[str, float] = {requesting_namespace: 1.0}
    try:
        from memory_thread.db import postgres_client

        # Only attempt PG query if pool was already initialized
        if postgres_client._pool is not None:
            pg = postgres_client.PostgresClient()
            with pg.get_cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT observed_namespace, trust_weight
                        FROM galaxy_influence_matrix
                        WHERE requesting_namespace = %s
                        """,
                        (requesting_namespace,),
                    )
                    for row in cur.fetchall():
                        trust_map[row["observed_namespace"]] = row["trust_weight"]
                except Exception:
                    pass
    except Exception:
        pass

    _TRUST_MAP_CACHE[requesting_namespace] = (time.monotonic(), tuple(sorted(trust_map.items())))
    return trust_map


def _safe_float(val, default: float = 0.5) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def retrieve_memories(query: str, top_k: int = 10) -> list:
    log.warning(
        "retrieve_memories() is deprecated and uses vector-only scoring. "
        "Phase 3 of graph-core will replace this with graph-primary activation. "
        "See docs/GRAPH_CORE_ARCHITECTURE.md"
    )
    return []


def retrieve_by_activation(
    seeds: List[str],
    top_k: int = 10,
    max_depth: int = 3,
    decay: float = 0.5,
    truth_threshold: float = 0.0,
    namespace: Optional[str] = None,
) -> List[Dict]:
    """Graph-primary retrieval via spreading activation, optionally scoped to a namespace.

    When namespace is provided, cross-namespace trust weights from
    galaxy_influence_matrix are loaded and applied as read-time influence
    scaling during BFS traversal (no write-path involvement).
    """
    from memory_thread.services.graph_engine import graph_engine

    trust_map = _load_namespace_trust_map(namespace) if namespace else None

    activated = graph_engine.activation(
        seeds=seeds,
        max_depth=max_depth,
        decay_per_hop=decay,
        truth_threshold=truth_threshold,
        namespace_filter=namespace,
        trust_map=trust_map,
    )
    # Fix #2: build the vertex name set once before the loop (was O(K·V), now O(V+K))
    all_vertex_names = (
        set(graph_engine.graph.vs["name"]) if graph_engine.graph.vcount() > 0 else set()
    )
    scored = []
    for node_id, activation_score in activated.items():
        if node_id not in all_vertex_names:
            continue
        nidx = graph_engine._vidx(node_id)
        if nidx is None:
            continue
        node = graph_engine.graph.vs[nidx]
        vattrs = node.attributes()
        if vattrs.get("type") not in ("entity",):
            continue

        truth_confidence = _safe_float(vattrs.get("truth_confidence"), 0.5)
        truth_authority = _safe_float(vattrs.get("truth_authority"), 0.5)
        truth_freshness = _safe_float(vattrs.get("truth_freshness"), 1.0)
        tv = TruthVector(
            confidence=truth_confidence,
            authority=truth_authority,
            freshness=truth_freshness,
            corroboration=0.0,
        )
        truth_score = tv.truth_score
        final_score = (activation_score * truth_score) ** 0.5
        scored.append(
            {
                "id": node_id,
                "content": _resolve_content(node_id),
                "score": final_score,
                "activation": activation_score,
                "truth_score": truth_score,
                "namespace": vattrs.get("namespace"),
                "source": "graph",
            }
        )
    return sorted(scored, key=lambda x: -x["score"])[:top_k]
