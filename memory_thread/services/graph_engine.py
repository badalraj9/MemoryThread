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
import time
import logging
import threading
from collections import defaultdict, deque
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
        # Fix #1 + A: name -> igraph vertex index for O(1) lookups.
        # A plain Set only gave O(1) existence; the index map also removes
        # the O(V) vs.find scans on the recall hot path.
        self._vertex_index: Dict[str, int] = {}
        self._index_generation: int = 0
        # Bumped only on index-shifting ops (delete_vertices, load_snapshot).
        # add_vertex APPENDS and leaves existing indices stable, so it needs
        # no bump. Lookups self-detect staleness via generation mismatch.
        self._graph_generation: int = 0
        self._write_lock = threading.RLock()
        self._built = False
        # ── Namespace-scoped graph tiering (enterprise RAM bounding) ──────
        # The graph is a materialized hot-tier of Postgres. By default the
        # whole graph lives in RAM (backward compatible). When an LRU budget
        # is set, inactive namespaces are evicted from RAM and lazily
        # re-materialized from Postgres on demand. budget==0 => unlimited.
        self._ns_access: Dict[str, float] = {}
        self._namespace_budget: int = 0
        self.watermark: Optional[tuple] = (
            None  # (timestamp_epoch, event_id_str) for incremental rebuild
        )

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

    @staticmethod
    def _row_to_event(row: dict) -> Event:
        """Convert a DB row dict to an Event object for graph application."""
        raw_ants = row.get("antecedents")
        ants = GraphEngine._parse_antecedents(raw_ants)
        delta = row.get("delta") or {}
        event = Event(
            id=row.get("id"),
            namespace=row.get("namespace", "user"),
            timestamp=row.get("timestamp"),
            actor=row.get("actor"),
            action=row.get("action"),
            object_id=row.get("object_id"),
            delta=delta,
            antecedents=ants,
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
        return event

    def rebuild(self, pg, watermark: Optional[tuple] = None) -> None:
        """
        Rebuild graph from PostgreSQL events table.

        Args:
            pg: PostgresClient instance.
            watermark: Optional (timestamp_epoch, event_id_str) cursor.
                       If provided, only events after this cursor are fetched
                       and applied (incremental catch-up after snapshot load).
                       If None, a full rebuild from all events is performed.
        """
        if watermark:
            # ── Incremental: preserve snapshot data, fetch only new events ──
            wm_ts_epoch, wm_id = watermark
            log.info("Incremental rebuild from watermark (ts_epoch=%s, id=%s)", wm_ts_epoch, wm_id)
            try:
                rows = pg.fetch_all(
                    """SELECT * FROM events
                       WHERE timestamp > to_timestamp(%s)
                          OR (timestamp >= to_timestamp(%s) AND id::text > %s)
                       ORDER BY timestamp, id""",
                    (wm_ts_epoch, wm_ts_epoch, wm_id),
                )
            except Exception as e:
                log.warning("Incremental rebuild query failed: %s", e)
                return

            if not rows:
                log.info("No new events since watermark — graph is current")
                self._built = True
                return

            count = 0
            for row in rows:
                try:
                    event = self._row_to_event(row)
                    self._apply(event)
                    count += 1
                except Exception as e:
                    log.debug("Skipping event row during incremental rebuild: %s", e)

            log.info(
                "GraphEngine incremental rebuild: %d new events applied, now %d v, %d e",
                count,
                self.graph.vcount(),
                self.graph.ecount(),
            )
            self._built = True
            return

        # ── Full rebuild from all events ──
        self.clear()
        try:
            log.info("Full rebuild from all events")
            rows = pg.fetch_all("SELECT * FROM events ORDER BY timestamp")
        except Exception as e:
            log.warning("Could not rebuild graph from events: %s. Starting empty.", e)
            return

        # Topological sort: process antecedents before dependents
        event_by_id: Dict[str, dict] = {}
        in_degree: Dict[str, int] = {}
        dep_graph: Dict[str, List[str]] = defaultdict(list)

        for row in rows:
            eid = str(row.get("id"))
            event_by_id[eid] = row
            raw_ants = row.get("antecedents")
            ants = self._parse_antecedents(raw_ants)
            for ant in ants:
                ant_str = str(ant)
                dep_graph[ant_str].append(eid)
                in_degree[eid] = in_degree.get(eid, 0) + 1
            if eid not in in_degree:
                in_degree[eid] = 0

        # Kahn's algorithm
        queue = deque([eid for eid, deg in in_degree.items() if deg == 0])
        topo_sorted: List[dict] = []
        while queue:
            eid = queue.popleft()
            topo_sorted.append(event_by_id[eid])
            for neighbor in dep_graph.get(eid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Append events not reached (cycle or missing ant) preserving timestamp order
        seen = {str(r.get("id")) for r in topo_sorted}
        for row in rows:
            if str(row.get("id")) not in seen:
                topo_sorted.append(row)

        count = 0
        for row in topo_sorted:
            try:
                event = self._row_to_event(row)
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
                if tid not in self._vertex_index:  # A: O(1) existence
                    v = self.graph.add_vertex(
                        tid,
                        type="thread",
                        title=row.get("title", ""),
                        created_by=row.get("created_by", "USER"),
                        started_at=str(row.get("started_at", "")),
                        status=row.get("status", "active"),
                    )
                    self._register(tid, v.index)  # A
                if row.get("parent_thread_id"):
                    parent_tid = str(row["parent_thread_id"])
                    if parent_tid in self._vertex_index:  # A: O(1) existence
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
        # Touch the namespace so an active workspace is never the LRU victim.
        self._touch_ns(event.namespace)

    # ── Namespace-scoped graph tiering ──────────────────────────────────
    # Enables enterprise RAM bounding: only active workspaces' subgraphs
    # stay in RAM; inactive ones are evicted and re-materialized on demand.

    def _touch_ns(self, ns: Optional[str]) -> None:
        if ns:
            self._ns_access[ns] = time.monotonic()

    def _present_namespaces(self) -> Set[str]:
        seen: Set[str] = set()
        for v in self.graph.vs:
            ns = v.attributes().get("namespace")
            if ns:
                seen.add(ns)
        return seen

    def namespace_loaded(self, ns: Optional[str]) -> bool:
        if not ns:
            return True
        return ns in self._present_namespaces()

    def set_namespace_budget(self, max_namespaces: int) -> None:
        """Set the max number of namespaces held in RAM. 0 = unlimited."""
        self._namespace_budget = max(0, max_namespaces)

    def evict_namespace(self, ns: Optional[str]) -> int:
        """Remove a namespace's subgraph from RAM (generation-safe).

        Returns the number of vertices evicted. Cross-namespace edges incident
        to evicted vertices are removed by igraph. Does not touch Postgres —
        the data is re-materialized via ensure_namespace_loaded() on next use.
        """
        if not ns:
            return 0
        with self._write_lock:
            to_remove = [
                (v.index, v["name"]) for v in self.graph.vs if v.attributes().get("namespace") == ns
            ]
            if not to_remove:
                self._ns_access.pop(ns, None)
                return 0
            for _, name in to_remove:
                self._vertex_index.pop(name, None)
            idxs = [i for i, _ in to_remove]
            self.graph.delete_vertices(idxs)
            self._graph_generation += 1
            self._ns_access.pop(ns, None)
            log.info("Evicted namespace '%s' from graph RAM (%d vertices)", ns, len(to_remove))
            return len(to_remove)

    def ensure_namespace_loaded(self, ns: Optional[str], pg=None) -> bool:
        """Lazily re-materialize a namespace's subgraph from Postgres.

        No-op if already present. Returns True if the namespace is now loaded.
        This is the "reactivate from DB" path that keeps RAM bounded: an
        evicted workspace comes back only when actually referenced.
        """
        if not ns:
            return True
        self._touch_ns(ns)
        if self.namespace_loaded(ns):
            return True
        if pg is None:
            return False
        try:
            rows = pg.fetch_all(
                "SELECT * FROM events WHERE namespace = %s ORDER BY timestamp, id", (ns,)
            )
            for row in rows:
                try:
                    ev = self._row_to_event(row)
                    self._apply(ev)
                except Exception as e:  # skip malformed rows
                    log.debug("Skipping event on namespace reload: %s", e)
            self._touch_ns(ns)
        except Exception as e:
            log.warning("Failed to reload namespace '%s' from Postgres: %s", ns, e)
            return False
        return self.namespace_loaded(ns)

    def enforce_namespace_budget(self) -> None:
        """Evict least-recently-used namespaces beyond the configured budget."""
        if self._namespace_budget <= 0:
            return
        present = self._present_namespaces()
        if len(present) <= self._namespace_budget:
            return
        ranked = sorted(present, key=lambda n: self._ns_access.get(n, 0.0))
        for ns in ranked[: len(present) - self._namespace_budget]:
            self.evict_namespace(ns)

    def clear(self) -> None:
        """Reset graph to empty state."""
        with self._write_lock:
            self.graph = ig.Graph(directed=True)
            self.node_index = {}
            self._vertex_index = {}  # A: reset index
            self._index_generation = self._graph_generation  # empty matches
            self.watermark = None
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
        namespace_filter: Optional[str] = None,
        trust_map: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Spreading activation from seed nodes.

        BFS-based: each hop propagates activation attenuated by
        edge_confidence and decay_per_hop. Multiple paths to same
        node keep the MAX activation.

        If namespace_filter is set and trust_map is None, only nodes
        belonging to that namespace are traversed (strict isolation).

        If trust_map is provided, the namespace_filter gate is relaxed
        and cross-namespace traversal energy is scaled by the trust
        weight of the neighbor's namespace — enabling read-time
        multi-agent influence weighting.

        Returns {node_id: activation_score}.
        """
        if namespace_filter:
            self._touch_ns(namespace_filter)
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
                vidx = self._vidx(node)
                if vidx is None:
                    continue
                incident = self.graph.incident(vidx, mode="out")
                for eidx in incident:
                    e = self.graph.es[eidx]
                    etype = _ea(e, "type", "")
                    if edge_types and etype not in edge_types:
                        continue
                    tgt = self.graph.vs[e.target]
                    target_name = tgt["name"]

                    tgt_ns = tgt.attributes().get("namespace")

                    # Namespace gate: strict isolation when no trust_map
                    if namespace_filter and trust_map is None:
                        if tgt_ns and tgt_ns != namespace_filter:
                            continue

                    eattrs = e.attributes()
                    raw_conf = eattrs.get("confidence")
                    edge_conf = float(raw_conf) if raw_conf is not None else 1.0
                    lookup_ns = tgt_ns if tgt_ns is not None else namespace_filter
                    influence_scale = trust_map.get(lookup_ns, 0.1) if trust_map else 1.0
                    propagated = current_act * edge_conf * decay_per_hop * influence_scale
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
        vidx = self._vidx(node_id)
        if vidx is None:
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
        s = self._vidx(source_id)
        t = self._vidx(target_id)
        if s is None or t is None:
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
        vidx = self._vidx(node_id)
        if vidx is None:
            return 0.0
        return self.graph.degree(vidx, mode="all") / (self.graph.vcount() - 1)

    def bridge_score(self, node_id: str) -> float:
        """Betweenness centrality — how many shortest paths pass through this node."""
        if not self._vertex_exists(node_id) or self.graph.vcount() < 3:
            return 0.0
        vidx = self._vidx(node_id)
        if vidx is None:
            return 0.0
        n = self.graph.vcount()
        max_betweenness = (n - 1) * (n - 2) / 2
        if max_betweenness == 0:
            return 0.0
        return self.graph.betweenness(vidx) / max_betweenness

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
        """Persist graph + node_index + watermark to disk. Faster restarts than full rebuild."""
        import pickle, os

        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with self._write_lock:
                with open(path, "wb") as f:
                    pickle.dump(
                        {
                            "graph": self.graph,
                            "node_index": self.node_index,
                            "watermark": self.watermark,
                        },
                        f,
                        protocol=pickle.HIGHEST_PROTOCOL,
                    )
            log.info(
                "Graph snapshot saved to %s (%d v, %d e, watermark=%s)",
                path,
                self.graph.vcount(),
                self.graph.ecount(),
                self.watermark,
            )
        except Exception as e:
            log.warning("Could not save graph snapshot: %s", e)

    def load_snapshot(self, path: str) -> bool:
        """Load graph + node_index + watermark from snapshot. Returns False if missing or corrupt."""
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
                self.watermark = data.get("watermark")  # None if old snapshot
                # A: graph replaced -> indices shifted; bump + rebuild lazily.
                self._graph_generation += 1
                self._rebuild_vertex_index()
                self._built = True
                # B: backfill cached_content on old snapshots that lack it.
                self._backfill_entity_content()
            log.info(
                "Graph snapshot loaded from %s (%d v, %d e, watermark=%s)",
                path,
                self.graph.vcount(),
                self.graph.ecount(),
                self.watermark,
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
        if event_id not in self._vertex_index:
            v = self.graph.add_vertex(event_id, **event_attrs)
            self._register(event_id, v.index)  # A

        if not self.graph.are_adjacent(event_id, entity_id):
            self.graph.add_edge(event_id, entity_id, type="modifies", action=event.action.value)

        # Fix #3/B: cache latest content directly on the entity vertex so
        # resolve_content is O(1) instead of an O(E) edge scan. Every event
        # modifies its entity, so the entity always holds the newest content.
        eidx = self._vidx(entity_id)
        if eidx is not None:
            entity_v = self.graph.vs[eidx]
            entity_v["cached_content"] = event_attrs["content"]
            entity_v["last_event_id"] = event_id
            entity_v["last_event_ts"] = event_attrs["timestamp"]

        if event.delta.get("contradiction_detected"):
            # Determine if this is a cross-namespace contradiction
            is_cross_ns = False
            eidx = self._vidx(entity_id)
            if eidx is not None:
                entity_v = self.graph.vs[eidx]
                entity_ns = entity_v.attributes().get("namespace")
                is_cross_ns = entity_ns and entity_ns != event.namespace

            if is_cross_ns:
                # Cross-namespace: link event→event instead of event→entity
                # Find the previous event that last modified this entity
                prev_event_id = None
                eidx = self._vidx(entity_id)
                if eidx is not None:
                    for e in self.graph.es:
                        eattrs_ = e.attributes()
                        if eattrs_.get("type") == "modifies" and e.target == eidx:
                            src = self.graph.vs[e.source]["name"]
                            if src != event_id:
                                prev_event_id = src
                                break

                if prev_event_id and self._vertex_exists(prev_event_id):
                    self.graph.add_edge(
                        event_id,
                        prev_event_id,
                        type="contradicts",
                        direction="cross_namespace",
                        detector="tier1_key_based",
                        confidence=event.truth_vector.confidence,
                        timestamp=event.timestamp.isoformat()
                        if isinstance(event.timestamp, datetime)
                        else str(event.timestamp),
                    )
                else:
                    # Fallback to event→entity if no prior event found
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
            else:
                # Same-namespace: existing event→entity behavior
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
            if thread_id not in self._vertex_index:
                v = self.graph.add_vertex(
                    thread_id, type="thread", title="", created_by=event.actor.value
                )
                self._register(thread_id, v.index)  # A
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

        # Update watermark for incremental rebuild cursor
        ts = event.timestamp
        if ts.tzinfo is not None:
            wm_epoch = ts.timestamp()
        else:
            # timezone-naive — assumed UTC (from datetime.utcnow())
            wm_epoch = (ts - datetime(1970, 1, 1)).total_seconds()
        self.watermark = (wm_epoch, str(event.id))

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

    def _rebuild_vertex_index(self) -> None:
        """Rebuild name->index map from the current graph (O(V), lazy)."""
        self._vertex_index = {v["name"]: v.index for v in self.graph.vs}
        self._index_generation = self._graph_generation

    def _backfill_entity_content(self) -> None:
        """B: one-time O(E) pass to populate cached_content on existing graphs.

        Only runs when an entity vertex actually lacks cached_content, so
        already-cached snapshots pay nothing. Content lives on the modifying
        EVENT vertex (source of the `modifies` edge), not on the edge itself.
        """
        if self.graph.vcount() == 0:
            return
        needs_backfill = any(
            v.attributes().get("type") == "entity" and "cached_content" not in v.attributes()
            for v in self.graph.vs
        )
        if not needs_backfill:
            return
        for v in self.graph.vs:
            vattrs = v.attributes()
            if vattrs.get("type") != "entity" or "cached_content" in vattrs:
                continue
            best_content = ""
            best_ts = ""
            for e in self.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "modifies" and e.target == v.index:
                    src = self.graph.vs[e.source]
                    content = src.attributes().get("content")
                    if not content:
                        continue
                    ts = str(src.attributes().get("timestamp", ""))
                    if ts >= best_ts:
                        best_content = str(content)
                        best_ts = ts
            if best_content:
                v["cached_content"] = best_content

    def _vidx(self, name: str) -> Optional[int]:
        """O(1) name->igraph index lookup. Self-detects staleness via generation."""
        if self._index_generation != self._graph_generation:
            self._rebuild_vertex_index()
        return self._vertex_index.get(name)

    def _register(self, name: str, idx: Optional[int] = None) -> None:
        """A: Register a vertex in the O(1) name->index map."""
        if idx is None:
            idx = self.graph.vs.find(name).index  # fallback; callers pass idx
        self._vertex_index[name] = idx

    def _unregister(self, name: str) -> None:
        """A: Remove a vertex from the name->index map."""
        self._vertex_index.pop(name, None)

    def _ensure_node(self, name: str, **attrs) -> str:
        if not self._vertex_exists(name):
            v = self.graph.add_vertex(name, **attrs)
            self._register(name, v.index)  # A
            if attrs.get("type") == "entity":
                self.node_index[name] = name
        return name

    def _vertex_exists(self, name: str) -> bool:
        """A: O(1) existence check via the maintained name->index map."""
        return name in self._vertex_index

    def _merge_nodes(self, source: str, target: str) -> None:
        """Rewire all edges from source to target, then remove source."""
        if source == target:
            return
        sidx = self._vidx(source)
        tidx = self._vidx(target)
        if sidx is None or tidx is None:
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
        self._unregister(source)
        self.node_index.pop(source, None)
        # A: deletion shifts every index > sidx — invalidate lazily; the next
        # _vidx call rebuilds once. No eager O(V) per merge.
        self._graph_generation += 1


# Module-level singleton
graph_engine = GraphEngine()
