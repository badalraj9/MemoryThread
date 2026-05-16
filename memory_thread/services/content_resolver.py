"""Shared content resolver — single source of truth for entity content resolution.

Entity nodes in iGraph don't store content directly (events do).
This utility finds the latest event that modified an entity and returns its content.
"""

from typing import Optional


def resolve_content(node_id: str) -> str:
    """Get content for a node. Entity nodes resolve from the latest modifying event."""
    from memory_thread.services.graph_engine import graph_engine

    try:
        v = graph_engine.graph.vs.find(name=node_id)
    except (ValueError, KeyError):
        return ""
    vattrs = v.attributes()
    content = vattrs.get("content") or ""
    if vattrs.get("type") == "entity" and not content:
        try:
            vidx = graph_engine.graph.vs.find(name=node_id).index
            best, best_ts = "", ""
            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "modifies" and e.target == vidx:
                    ev = graph_engine.graph.vs[e.source]
                    ev_content = ev.attributes().get("content")
                    if not ev_content:
                        continue
                    ets = str(ev.attributes().get("timestamp", ""))
                    if ets >= best_ts:
                        best = str(ev_content)
                        best_ts = ets
            if best:
                return best
        except (ValueError, KeyError):
            pass
    return str(content) if content else ""
