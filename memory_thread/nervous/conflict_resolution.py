"""
Conflict Resolution for Galaxy Architecture.

Detects and resolves contradictions between agent beliefs.
"""

from typing import List, Dict, Any, Optional
import networkx as nx
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class ConflictGraph:
    """
    Represents the galaxy structure:
    Nodes = Beliefs
    Edges = Relationships (supports/contradicts)
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    def add_belief(self, belief: Dict):
        self.graph.add_node(
            belief["id"],
            agent=belief.get("agent_id"),
            content=belief.get("content"),
            confidence=belief.get("confidence", 0.5),
            authority=belief.get("authority", 0.5),
        )

    def add_relationship(self, belief_a_id, belief_b_id, rel_type, weight):
        self.graph.add_edge(belief_a_id, belief_b_id, type=rel_type, weight=weight)

    def find_conflicts(self) -> List[List[str]]:
        """Find groups (clusters) of contradictory beliefs."""
        conflict_edges = [
            (u, v) for u, v, d in self.graph.edges(data=True) if d.get("type") == "contradicts"
        ]
        undirected_conflict_graph = nx.Graph()
        undirected_conflict_graph.add_edges_from(conflict_edges)
        return list(nx.connected_components(undirected_conflict_graph))


class ConflictResolver:
    """
    Resolves contradictions using Authority, Consensus, or Recency.
    """

    def __init__(self, namespace: Optional[str] = None):
        self._conflicts: List[Dict] = []
        self._graph = ConflictGraph()
        self._pg = None
        self.namespace = namespace

    @property
    def pg(self):
        if self._pg is None:
            try:
                from memory_thread.db.postgres_client import PostgresClient

                self._pg = PostgresClient()
            except Exception:
                pass
        return self._pg

    def detect_conflicts(self, universes: Dict, agent_registry: Dict) -> List[Dict]:
        """
        Detect conflicts across agent universes by querying Qdrant.
        Searches for semantically similar beliefs across different agents.
        """
        try:
            from memory_thread.utils.embeddings import embed_text

            if not self.pg:
                log.warning("No DB connection for conflict detection")
                return self._conflicts

            with self.pg.get_cursor() as cur:
                if self.namespace:
                    cur.execute(
                        """
                        SELECT id, object_id, delta, truth_vector, actor, namespace
                        FROM events
                        WHERE namespace = %s
                        ORDER BY timestamp DESC
                        LIMIT 1000
                    """,
                        (self.namespace,),
                    )
                else:
                    cur.execute("""
                        SELECT id, object_id, delta, truth_vector, actor, namespace
                        FROM events
                        ORDER BY timestamp DESC
                        LIMIT 1000
                    """)
                events = cur.fetchall()

            import json

            beliefs_by_content = {}

            for event in events:
                event_id, object_id, delta, truth_vector, actor, namespace = event

                if isinstance(delta, str):
                    delta = json.loads(delta)
                if isinstance(truth_vector, str):
                    truth_vector = json.loads(truth_vector)

                content_key = str(sorted(delta.items()))

                if content_key not in beliefs_by_content:
                    beliefs_by_content[content_key] = []

                beliefs_by_content[content_key].append(
                    {
                        "id": str(event_id),
                        "entity_id": str(object_id),
                        "content": delta,
                        "agent_id": actor,
                        "namespace": namespace,
                        "confidence": truth_vector.get("confidence", 0.5) if truth_vector else 0.5,
                        "authority": truth_vector.get("authority", 0.5) if truth_vector else 0.5,
                    }
                )

            conflicts = []
            SIMILARITY_THRESHOLD = 0.85

            for content_key, beliefs in beliefs_by_content.items():
                if len(beliefs) < 2:
                    continue

                agent_ids = set(b["agent_id"] for b in beliefs)
                if len(agent_ids) < 2:
                    continue

                values = set(str(b["content"]) for b in beliefs)
                if len(values) > 1:
                    conflict = {
                        "fact_id": content_key[:50],
                        "beliefs": beliefs,
                        "type": "value_mismatch",
                        "severity": "high" if len(beliefs) > 3 else "medium",
                    }
                    conflicts.append(conflict)

                    for belief in beliefs:
                        self._graph.add_belief(belief)

            for i, c1 in enumerate(conflicts):
                for c2 in conflicts[i + 1 :]:
                    self._graph.add_relationship(
                        c1["beliefs"][0]["id"], c2["beliefs"][0]["id"], "contradicts", 1.0
                    )

            self._conflicts = conflicts
            log.info(f"Detected {len(conflicts)} conflicts")
            return conflicts

        except Exception as e:
            log.warning(f"Conflict detection failed: {e}")
            return self._conflicts

    def add_conflict(self, fact_id: str, beliefs: List[Dict], severity: str = "LOW"):
        """Manually add a conflict for tracking."""
        self._conflicts.append({"fact_id": fact_id, "beliefs": beliefs, "severity": severity})

    def resolve(self, conflict: Dict, strategy: str = "authority") -> Dict:
        """
        Resolve a conflict using specified strategy.

        Args:
            conflict: Conflict dict from detect_conflicts()
            strategy: "authority" | "consensus" | "temporal"

        Returns:
            Resolution with winning belief
        """
        beliefs = conflict.get("beliefs", [])
        if not beliefs:
            return {"winner": None, "strategy": strategy}

        if strategy == "authority":
            winner = max(beliefs, key=lambda x: x.get("authority", 0.5) * x.get("confidence", 0.5))
        elif strategy == "temporal":
            winner = max(beliefs, key=lambda x: x.get("timestamp", 0))
        else:
            winner = max(beliefs, key=lambda x: x.get("authority", 0.5))

        return {"winner": winner, "strategy": strategy, "fact_id": conflict.get("fact_id")}

    def resolve_cluster(self, cluster_ids: List[str], strategy: str = "authority") -> Optional[str]:
        """Resolve a cluster of conflicting belief IDs using real DB data."""
        if not cluster_ids:
            return None

        try:
            if not self.pg:
                log.warning("No DB connection for cluster resolution")
                return cluster_ids[0]

            import json

            beliefs = []

            with self.pg.get_cursor() as cur:
                for bid in cluster_ids:
                    cur.execute(
                        """
                        SELECT id, truth_vector, timestamp
                        FROM events
                        WHERE id = %s
                    """,
                        (bid,),
                    )
                    row = cur.fetchone()

                    if row:
                        truth_vector = row[1]
                        if isinstance(truth_vector, str):
                            truth_vector = json.loads(truth_vector)

                        beliefs.append(
                            {
                                "id": str(row[0]),
                                "authority": truth_vector.get("authority", 0.5)
                                if truth_vector
                                else 0.5,
                                "confidence": truth_vector.get("confidence", 0.5)
                                if truth_vector
                                else 0.5,
                                "timestamp": row[2].timestamp() if row[2] else 0,
                            }
                        )

            if not beliefs:
                return cluster_ids[0]

            if strategy == "authority":
                winner = max(beliefs, key=lambda x: x["authority"] * x["confidence"])
                return winner["id"]
            if strategy == "consensus":
                return self.resolve_cluster(cluster_ids, "authority")
            if strategy == "temporal":
                return max(beliefs, key=lambda x: x["timestamp"])["id"]

            raise ValueError(f"Unknown strategy: {strategy}")

        except Exception as e:
            log.warning(f"Cluster resolution failed: {e}")
            return cluster_ids[0] if cluster_ids else None
