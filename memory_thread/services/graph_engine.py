"""
GraphEngine — In-memory materialized cognitive graph.

Rebuilds the entire cognitive graph from the event log on startup.
Provides traversal (spreading activation), topological analytics
(centrality, community, PageRank), and incremental updates.

Backed by iGraph for performance and thread-safe reads.
"""

from __future__ import annotations

import uuid
import math
import logging
import threading
from typing import List, Dict, Optional, Set, Tuple, Any, Union
from datetime import datetime

try:
    import igraph as ig

    _HAS_IGRAPH = True
except ImportError:
    ig = None  # type: ignore
    _HAS_IGRAPH = False

from memory_thread.models.events import Event, ActionEnum, TruthVector
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


def _ea(edge: ig.Edge, attr: str, default: Any = None) -> Any:
    """Safe attribute access for iGraph edges."""
    attrs = edge.attributes()
    return attrs.get(attr, default)


def _va(vertex: ig.Vertex, attr: str, default: Any = None) -> Any:
    """Safe attribute access for iGraph vertices."""
    attrs = vertex.attributes()
    return attrs.get(attr, default)


class GraphEngine:
    """
    In-memory materialized cognitive graph.

    Thread-safe for concurrent reads (iGraph C core).
    Writes serialized via _write_lock.

    Usage:
        engine = GraphEngine()
        engine.rebuild(pg_client)           # startup: load all events
        engine.apply_event(event)           # incremental: on each remember()
        activated = engine.activation(seeds) # retrieval: spreading activation
    """

    def __init__(self):
        if not _HAS_IGRAPH:
            raise RuntimeError(
                "python-igraph is required but not installed. "
                "Install it with: pip install python-igraph"
            )
        self.graph: ig.Graph = ig.Graph(directed=True)
        self.node_index: Dict[str, str] = {}
        self._write_lock = threading.Lock()
        self._built = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_antecedents(raw: Any) -> list:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw in ("{}", ""):
                return []
            if raw.startswith("{") and raw.endswith("}"):
                inner = raw[1:-1]
                parts = [p.strip().strip('"') for p in inner.split(",") if p.strip()]
                return parts
            return [raw]
        return []

    def rebuild(self, pg) -> None:
        """Full rebuild from PostgreSQL events table. Called once on startup."""
        self.clear()
        try:
            rows = pg.fetch_all("SELECT * FROM events ORDER BY timestamp")
        except Exception as e:
            log.warning("Could not rebuild graph from events: %s. Starting empty.", e)
            return

        count = 0
        for row in rows:
            try:
                raw_ants = row.get("antecedents")
                antecedents = self._parse_antecedents(raw_ants)
                delta = row.get("delta") or {}
                event = Event(
                    id=row.get("id"),
                    namespace=row.get("namespace", "user"),
                    timestamp=row.get("timestamp"),
                    actor=row.get("actor"),
                    action=row.get("action"),
                    object_id=row.get("object_id"),
                    delta=delta,
                    antecedents=antecedents,
                    truth_vector=TruthVector(
                        confidence=0.5, authority=0.5, freshness=1.0, corroboration=0.0
                    ),
                )
                if isinstance(row.get("truth_vector"), dict):
                    tv = row["truth_vector"]
                    event.truth_vector = TruthVector(
                        confidence=tv.get("confidence", 0.5),
                        authority=tv.get("authority", 0.5),
                        freshness=tv.get("freshness", 1.0),
                        corroboration=tv.get("corroboration", 0.0),
                    )
                self._apply(event)
                count += 1
            except Exception as e:
                log.debug("Skipping event row during rebuild: %s", e)

        try:
            rels = pg.fetch_all("SELECT * FROM relations")
            for rel in rels:
                src = str(rel.get("source_entity_id"))
                tgt = str(rel.get("target_entity_id"))
                self._ensure_node(src, type="entity")
                self._ensure_node(tgt, type="entity")
                if self.graph.are_adjacent(src, tgt):
                    continue
                self.graph.add_edge(
                    src,
                    tgt,
                    type="relates",
                    relation_type=str(rel.get("relation_type", "")),
                    confidence=float(rel.get("confidence", 1.0)),
                    is_inferred=bool(rel.get("is_inferred", False)),
                )
        except Exception as e:
            log.debug("Could not load relations table: %s", e)

        try:
            bridges = pg.fetch_all("SELECT * FROM belief_bridges")
            for bridge in bridges:
                a = str(bridge.get("belief_a_id"))
                b = str(bridge.get("belief_b_id"))
                rel = bridge.get("relationship")
                self._ensure_node(a, type="belief")
                self._ensure_node(b, type="belief")
                if self.graph.are_adjacent(a, b):
                    continue
                self.graph.add_edge(
                    a,
                    b,
                    type=rel,
                    confidence=float(bridge.get("confidence", 1.0)),
                )
        except Exception as e:
            log.debug("Could not load belief_bridges: %s", e)

        try:
            thread_rows = pg.fetch_all("SELECT * FROM threads")
            for row in thread_rows:
                tid = str(row["thread_id"])
                if tid not in {v["name"] for v in self.graph.vs}:
                    self.graph.add_vertex(
                        tid,
                        type="thread",
                        title=row.get("title", ""),
                        created_by=row.get("created_by", "USER"),
                        started_at=str(row.get("started_at", "")),
                        status=row.get("status", "active"),
                    )
                if row.get("parent_thread_id"):
                    parent_tid = str(row["parent_thread_id"])
                    if parent_tid in {v["name"] for v in self.graph.vs}:
                        if not self.graph.are_adjacent(parent_tid, tid):
                            self.graph.add_edge(parent_tid, tid, type="contains")
        except Exception as e:
            log.debug("Could not load threads from Postgres: %s", e)

        self._built = True
        log.info(
            "GraphEngine rebuilt: %d vertices, %d edges", self.graph.vcount(), self.graph.ecount()
        )

    def apply_event(self, event: Event) -> None:
        """Apply one event to the in-memory graph. Called on every remember()."""
        with self._write_lock:
            self._apply(event)

    def clear(self) -> None:
        """Reset graph to empty state."""
        with self._write_lock:
            self.graph = ig.Graph(directed=True)
            self.node_index = {}
            self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    # ── Traversal ──────────────────────────────────────────────────────

    def activation(
        self,
        seeds: List[str],
        max_depth: int = 3,
        decay_per_hop: float = 0.5,
        truth_threshold: float = 0.0,
        edge_types: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Spreading activation from seed nodes.

        BFS-based: each hop propagates activation attenuated by
        edge_confidence and decay_per_hop. Multiple paths to same
        node keep the MAX activation.

        Returns {node_id: activation_score}.
        """
        if self.graph.vcount() == 0:
            return {}

        resolved = [s for s in seeds if self._vertex_exists(s)]
        if not resolved:
            return {}

        activation_map: Dict[str, float] = {s: 1.0 for s in resolved}
        frontier: Set[str] = set(resolved)
        visited: Set[str] = set(resolved)

        for _ in range(max_depth):
            next_frontier: Set[str] = set()
            for node in frontier:
                current_act = activation_map.get(node, 0.0)
                try:
                    vidx = self.graph.vs.find(name=node).index
                except (ValueError, KeyError):
                    continue
                incident = self.graph.incident(vidx, mode="out")
                for eidx in incident:
                    e = self.graph.es[eidx]
                    etype = _ea(e, "type", "")
                    if edge_types and etype not in edge_types:
                        continue
                    target_name = self.graph.vs[e.target]["name"]
                    eattrs = e.attributes()
                    raw_conf = eattrs.get("confidence")
                    edge_conf = float(raw_conf) if raw_conf is not None else 1.0
                    propagated = current_act * edge_conf * decay_per_hop
                    if propagated < truth_threshold:
                        continue
                    if propagated > activation_map.get(target_name, 0.0):
                        activation_map[target_name] = propagated
                    if target_name not in visited:
                        next_frontier.add(target_name)
                        visited.add(target_name)
            frontier = next_frontier
            if not frontier:
                break

        return activation_map

    def get_neighbors(
        self,
        node_id: str,
        direction: str = "both",
        edge_types: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Get immediate neighbors with edge attributes."""
        if not self._vertex_exists(node_id):
            return []
        try:
            vidx = self.graph.vs.find(name=node_id).index
        except (ValueError, KeyError):
            return []

        results = []
        for mode in ("out", "in"):
            if direction not in (mode, "both"):
                continue
            direction_label = mode
            for eidx in self.graph.incident(vidx, mode=mode):
                e = self.graph.es[eidx]
                eattrs = e.attributes()
                etype = eattrs.get("type", "")
                if edge_types and etype not in edge_types:
                    continue
                partner = self.graph.vs[e.target if mode == "out" else e.source]
                entry = {
                    "id": partner["name"],
                    "direction": direction_label,
                    "relation_type": eattrs.get("relation_type", eattrs.get("type", "")),
                    "confidence": float(eattrs.get("confidence", 1.0))
                    if "confidence" in eattrs
                    else 1.0,
                }
                for k, v in eattrs.items():
                    if k not in ("type", "confidence", "relation_type"):
                        entry[k] = v
                results.append(entry)

        return results

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        weight: Optional[str] = None,
    ) -> List[str]:
        """Shortest path between two nodes. Returns list of node names."""
        if not self._vertex_exists(source_id) or not self._vertex_exists(target_id):
            return []
        try:
            s = self.graph.vs.find(name=source_id).index
            t = self.graph.vs.find(name=target_id).index
        except (ValueError, KeyError):
            return []
        try:
            path = self.graph.get_shortest_paths(s, t, weights=weight, output="vpath")[0]
            return [self.graph.vs[i]["name"] for i in path]
        except Exception:
            return []

    # ── Topological Analytics ──────────────────────────────────────────

    def centrality(self, node_id: str) -> float:
        """Degree centrality (0.0 to 1.0)."""
        if not self._vertex_exists(node_id) or self.graph.vcount() < 2:
            return 0.0
        try:
            vidx = self.graph.vs.find(name=node_id).index
            return self.graph.degree(vidx, mode="all") / (self.graph.vcount() - 1)
        except (ValueError, KeyError):
            return 0.0

    def bridge_score(self, node_id: str) -> float:
        """Betweenness centrality — how many shortest paths pass through this node."""
        if not self._vertex_exists(node_id) or self.graph.vcount() < 3:
            return 0.0
        try:
            vidx = self.graph.vs.find(name=node_id).index
            n = self.graph.vcount()
            max_betweenness = (n - 1) * (n - 2) / 2
            if max_betweenness == 0:
                return 0.0
            return self.graph.betweenness(vidx) / max_betweenness
        except (ValueError, KeyError):
            return 0.0

    def pagerank(self, personalized: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """PageRank scores for all nodes. Optional personalization vector."""
        if self.graph.vcount() == 0:
            return {}
        try:
            if personalized:
                vertices = self.graph.vs["name"]
                total = sum(personalized.get(v, 0.0) for v in vertices)
                weights = (
                    [personalized.get(v, 0.0) / total for v in vertices] if total > 0 else None
                )
            else:
                weights = None
            scores = self.graph.pagerank(weights=weights, directed=True)
            return {self.graph.vs[i]["name"]: scores[i] for i in range(len(scores))}
        except Exception:
            return {}

    def community(self) -> List[List[str]]:
        """Leiden community detection. Returns groups of node names."""
        if self.graph.vcount() < 2:
            return []
        try:
            simple = ig.Graph.simplify(self.graph, combine_edges=None)
            if simple.vcount() < 2:
                return []
            vc = simple.community_leiden(objective_function="modularity")
            groups = {}
            for i, mem in enumerate(vc.membership):
                groups.setdefault(mem, []).append(simple.vs[i]["name"])
            return list(groups.values())
        except Exception:
            return []

    def contradiction_cycles(self) -> List[List[str]]:
        """Find connected components formed by 'contradicts' edges."""
        contradict_nodes = set()
        contradict_edges = []
        for e in self.graph.es:
            eattrs = e.attributes()
            if eattrs.get("type", "") == "contradicts":
                src = self.graph.vs[e.source]["name"]
                tgt = self.graph.vs[e.target]["name"]
                contradict_nodes.add(src)
                contradict_nodes.add(tgt)
                contradict_edges.append((src, tgt))
        if not contradict_edges:
            return []
        sub = ig.Graph(directed=False)
        name_map = {}
        for n in contradict_nodes:
            name_map[n] = sub.vcount()
            sub.add_vertex(n)
        for s, t in contradict_edges:
            if s in name_map and t in name_map:
                sub.add_edge(name_map[s], name_map[t])
        comps = sub.connected_components()
        return [list(comp) for comp in comps]

    def _community_map(self) -> Dict[str, int]:
        """Flatten community() into {node_id: community_id}."""
        if self.graph.vcount() < 2:
            return {}
        try:
            simple = ig.Graph.simplify(self.graph, combine_edges=None)
            if simple.vcount() < 2:
                return {}
            vc = simple.community_leiden(objective_function="modularity")
            return {simple.vs[i]["name"]: mem for i, mem in enumerate(vc.membership)}
        except Exception:
            return {}

    def export_graph_json(self, namespace: Optional[str] = None) -> Dict:
        """Export full graph as JSON-serializable dict for the frontend."""
        if self.graph.vcount() == 0:
            return {
                "nodes": [],
                "edges": [],
                "metadata": {"node_count": 0, "edge_count": 0, "community_count": 0},
            }

        community_map = self._community_map()
        pr_scores = self.pagerank()
        vcount = self.graph.vcount()

        try:
            layout = self.graph.layout_fruchterman_reingold()
        except Exception:
            import random

            random.seed(42)
            layout = [(random.uniform(-1, 1), random.uniform(-1, 1)) for _ in range(vcount)]

        nodes = []
        for i, v in enumerate(self.graph.vs):
            attrs = v.attributes()
            if namespace and attrs.get("namespace") not in (namespace, None):
                continue
            vname = attrs.get("name", "")
            deg = self.graph.degree(i, mode="all")
            centrality = deg / (vcount - 1) if vcount > 1 else 0.0
            nodes.append(
                {
                    "id": vname,
                    "type": attrs.get("type", ""),
                    "memory_type": attrs.get("memory_type", attrs.get("type", "")),
                    "namespace": attrs.get("namespace", ""),
                    "content": attrs.get("content", ""),
                    "truth_confidence": attrs.get("truth_confidence", 0.5),
                    "truth_authority": attrs.get("truth_authority", 0.5),
                    "truth_freshness": attrs.get("truth_freshness", 1.0),
                    "truth_corroboration": attrs.get("truth_corroboration", 0.0),
                    "centrality": centrality,
                    "pagerank": pr_scores.get(vname, 0.0),
                    "community_id": community_map.get(vname, -1),
                    "x": float(layout[i][0]),
                    "y": float(layout[i][1]),
                }
            )

        edges = []
        for e in self.graph.es:
            eattrs = e.attributes()
            edges.append(
                {
                    "source": self.graph.vs[e.source]["name"],
                    "target": self.graph.vs[e.target]["name"],
                    "type": eattrs.get("type", ""),
                    "relation_type": eattrs.get("relation_type", ""),
                    "confidence": float(eattrs.get("confidence", 1.0)),
                    "timestamp": eattrs.get("timestamp", ""),
                }
            )

        community_ids = set(community_map.values())
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "community_count": len(community_ids),
            },
        }

    # ── Persistence ────────────────────────────────────────────────────

    def snapshot(self, path: str) -> None:
        """Persist graph + node_index to disk. Faster restarts than full rebuild."""
        import pickle, os

        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with self._write_lock:
                with open(path, "wb") as f:
                    pickle.dump(
                        {"graph": self.graph, "node_index": self.node_index},
                        f,
                        protocol=pickle.HIGHEST_PROTOCOL,
                    )
            log.info(
                "Graph snapshot saved to %s (%d v, %d e)",
                path,
                self.graph.vcount(),
                self.graph.ecount(),
            )
        except Exception as e:
            log.warning("Could not save graph snapshot: %s", e)

    def load_snapshot(self, path: str) -> bool:
        """Load graph + node_index from snapshot. Returns False if missing or corrupt."""
        import pickle

        try:
            open(path, "rb").close()
        except FileNotFoundError:
            return False
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            with self._write_lock:
                self.graph = data["graph"]
                self.node_index = data["node_index"]
                self._built = True
            log.info(
                "Graph snapshot loaded from %s (%d v, %d e)",
                path,
                self.graph.vcount(),
                self.graph.ecount(),
            )
            return True
        except Exception as e:
            log.warning("Snapshot load failed (%s) — rebuilding from Postgres", e)
            return False

    # ── Query Helpers ──────────────────────────────────────────────────

    def find_nodes(self, attr: str, value: Any) -> List[str]:
        """Find all vertex names with matching attribute value."""
        return [v["name"] for v in self.graph.vs if _va(v, attr) == value]

    def search_nodes(self, text: str, attr: str = "content") -> List[str]:
        """Search nodes by word-overlap match on an attribute."""
        query_words = set(text.lower().split())
        return [
            v["name"]
            for v in self.graph.vs
            if isinstance(_va(v, attr), str)
            and (query_words & set(str(_va(v, attr, "")).lower().split()))
        ]

    # ── Internal ───────────────────────────────────────────────────────

    def _apply(self, event: Event) -> None:
        entity_id = str(event.object_id)
        event_id = str(event.id)

        self._ensure_node(entity_id, type="entity", namespace=event.namespace)

        import json as _json

        event_attrs = {
            "type": "event",
            "action": event.action.value,
            "actor": event.actor.value,
            "namespace": event.namespace,
            "timestamp": event.timestamp.isoformat()
            if isinstance(event.timestamp, datetime)
            else str(event.timestamp),
            "truth_confidence": event.truth_vector.confidence,
            "truth_authority": event.truth_vector.authority,
            "truth_freshness": event.truth_vector.freshness,
            "object_id": entity_id,
            "content": event.delta.get("content", ""),
            "delta_json": _json.dumps(event.delta),
        }
        if event_id not in {v["name"] for v in self.graph.vs}:
            self.graph.add_vertex(event_id, **event_attrs)

        if not self.graph.are_adjacent(event_id, entity_id):
            self.graph.add_edge(event_id, entity_id, type="modifies", action=event.action.value)

        if event.delta.get("contradiction_detected"):
            self.graph.add_edge(
                event_id,
                entity_id,
                type="contradicts",
                direction="event_to_entity",
                detector="tier1_key_based",
                confidence=event.truth_vector.confidence,
                timestamp=event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else str(event.timestamp),
            )

        if event.thread_id:
            thread_id = str(event.thread_id)
            if thread_id not in {v["name"] for v in self.graph.vs}:
                self.graph.add_vertex(
                    thread_id, type="thread", title="", created_by=event.actor.value
                )
            if not self.graph.are_adjacent(thread_id, event_id):
                self.graph.add_edge(thread_id, event_id, type="contains")

        for ant in event.antecedents:
            ant_id = str(ant)
            if self._vertex_exists(ant_id) and not self.graph.are_adjacent(ant_id, event_id):
                self.graph.add_edge(ant_id, event_id, type="causes")

        if event.action == ActionEnum.LINK:
            target_id = event.delta.get("target_id")
            if target_id:
                target_id = str(target_id)
                rel_type = event.delta.get("relation_type", "related_to")
                self._ensure_node(target_id, type="entity")
                if not self.graph.are_adjacent(entity_id, target_id):
                    self.graph.add_edge(
                        entity_id,
                        target_id,
                        type="relates",
                        relation_type=rel_type,
                        confidence=event.truth_vector.confidence,
                        is_inferred=event.delta.get("is_inferred", False),
                        metadata=str(event.delta.get("metadata", {})),
                    )

        if event.action == ActionEnum.UNLINK:
            target_id = event.delta.get("target_id")
            if target_id:
                target_id = str(target_id)
                rel_type = event.delta.get("relation_type")
                to_remove = []
                for e in self.graph.es:
                    eattrs = e.attributes()
                    src_name = self.graph.vs[e.source]["name"]
                    tgt_name = self.graph.vs[e.target]["name"]
                    if (
                        src_name == entity_id
                        and tgt_name == target_id
                        and eattrs.get("type") == "relates"
                        and (rel_type is None or eattrs.get("relation_type") == rel_type)
                    ):
                        to_remove.append(e.index)
                for idx in sorted(to_remove, reverse=True):
                    self.graph.delete_edges(idx)

        if event.action == ActionEnum.MERGE:
            target_id = event.delta.get("target_id")
            if target_id:
                target_id = str(target_id)
                self._ensure_node(target_id, type="entity")
                self._merge_nodes(entity_id, target_id)

        from memory_thread.services.event_bus import event_bus

        event_bus.publish_sync(
            "graph_mutation",
            {
                "event_id": event_id,
                "object_id": entity_id,
                "action": event.action.value,
                "namespace": event.namespace,
                "contradiction": event.delta.get("contradiction_detected", False),
            },
        )

    def _ensure_node(self, name: str, **attrs) -> str:
        if name not in {v["name"] for v in self.graph.vs}:
            self.graph.add_vertex(name, **attrs)
            if attrs.get("type") == "entity":
                self.node_index[name] = name
        return name

    def _vertex_exists(self, name: str) -> bool:
        try:
            self.graph.vs.find(name=name)
            return True
        except (ValueError, KeyError):
            return False

    def _merge_nodes(self, source: str, target: str) -> None:
        """Rewire all edges from source to target, then remove source."""
        if source == target:
            return
        try:
            sidx = self.graph.vs.find(name=source).index
            tidx = self.graph.vs.find(name=target).index
        except (ValueError, KeyError):
            return

        edges_to_add = []
        for e in self.graph.es:
            if e.source == sidx and e.target != tidx:
                edges_to_add.append((target, self.graph.vs[e.target]["name"], dict(e.attributes())))
            elif e.target == sidx and e.source != tidx:
                edges_to_add.append((self.graph.vs[e.source]["name"], target, dict(e.attributes())))

        for src, tgt, attrs in edges_to_add:
            if not self.graph.are_adjacent(src, tgt):
                self.graph.add_edge(src, tgt, **attrs)

        self.graph.delete_vertices(sidx)
        self.node_index.pop(source, None)


# Module-level singleton
graph_engine = GraphEngine()
