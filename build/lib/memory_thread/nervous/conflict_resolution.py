"""
Conflict Resolution for Galaxy Architecture.

Detects and resolves contradictions between agent beliefs.
"""
from typing import List, Dict, Any, Optional
import networkx as nx


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
            belief['id'],
            agent=belief.get('agent_id'),
            content=belief.get('content'),
            confidence=belief.get('confidence', 0.5),
            authority=belief.get('authority', 0.5)
        )

    def add_relationship(self, belief_a_id, belief_b_id, rel_type, weight):
        self.graph.add_edge(
            belief_a_id,
            belief_b_id,
            type=rel_type,
            weight=weight
        )

    def find_conflicts(self) -> List[List[str]]:
        """Find groups (clusters) of contradictory beliefs."""
        conflict_edges = [
            (u, v) for u, v, d in self.graph.edges(data=True)
            if d.get('type') == 'contradicts'
        ]
        undirected_conflict_graph = nx.Graph()
        undirected_conflict_graph.add_edges_from(conflict_edges)
        return list(nx.connected_components(undirected_conflict_graph))


class ConflictResolver:
    """
    Resolves contradictions using Authority, Consensus, or Recency.
    """

    def __init__(self):
        self._conflicts: List[Dict] = []

    def detect_conflicts(self, universes: Dict, agent_registry: Dict) -> List[Dict]:
        """
        Detect conflicts across agent universes.
        
        Args:
            universes: Dict of agent_id -> AgentMemorySpace
            agent_registry: Dict of agent_id -> authority score
            
        Returns:
            List of conflict dicts with fact_id, beliefs, severity
        """
        # For now, return cached conflicts (real implementation would query Qdrant)
        # This is a stub that can be enhanced later
        return self._conflicts
    
    def add_conflict(self, fact_id: str, beliefs: List[Dict], severity: str = "LOW"):
        """Manually add a conflict for tracking."""
        self._conflicts.append({
            "fact_id": fact_id,
            "beliefs": beliefs,
            "severity": severity
        })

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
        else:  # consensus
            winner = max(beliefs, key=lambda x: x.get("authority", 0.5))
        
        return {
            "winner": winner,
            "strategy": strategy,
            "fact_id": conflict.get("fact_id")
        }

    def resolve_cluster(self, cluster_ids: List[str], strategy: str = "authority") -> Optional[str]:
        """Resolve a cluster of conflicting belief IDs."""
        beliefs = [{"id": bid, "authority": 0.5, "confidence": 0.8, "timestamp": 0} for bid in cluster_ids]
        
        if not beliefs:
            return None

        if strategy == "authority":
            winner = max(beliefs, key=lambda x: x["authority"] * x["confidence"])
            return winner["id"]
        if strategy == "consensus":
            return self.resolve_cluster(cluster_ids, "authority")
        if strategy == "temporal":
            return max(beliefs, key=lambda x: x["timestamp"])["id"]

        raise ValueError(f"Unknown strategy: {strategy}")
