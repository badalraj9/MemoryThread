"""Retrieval service — graph-primary and vector fallback paths."""

import logging
from typing import List, Dict, Optional

from memory_thread.config.settings import settings
from memory_thread.services.content_resolver import resolve_content as _resolve_content

log = logging.getLogger(__name__)


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
) -> List[Dict]:
    """Graph-primary retrieval via spreading activation."""
    from memory_thread.services.graph_engine import graph_engine

    activated = graph_engine.activation(
        seeds=seeds,
        max_depth=max_depth,
        decay_per_hop=decay,
        truth_threshold=truth_threshold,
    )
    scored = []
    for node_id, activation_score in activated.items():
        if node_id not in {v["name"] for v in graph_engine.graph.vs}:
            continue
        node = graph_engine.graph.vs.find(name=node_id)
        vattrs = node.attributes()
        if vattrs.get("type") not in ("entity",):
            continue

        truth_confidence = _safe_float(vattrs.get("truth_confidence"), 0.5)
        truth_authority = _safe_float(vattrs.get("truth_authority"), 0.5)
        truth_freshness = _safe_float(vattrs.get("truth_freshness"), 1.0)
        truth_score = (truth_confidence * 0.4) + (truth_authority * 0.35) + (truth_freshness * 0.25)
        final_score = (activation_score * truth_score) ** 0.5
        scored.append(
            {
                "id": node_id,
                "content": _resolve_content(node_id),
                "score": final_score,
                "activation": activation_score,
                "truth_score": truth_score,
                "source": "graph",
            }
        )
    return sorted(scored, key=lambda x: -x["score"])[:top_k]
