"""
Galaxy Query - Layer 2 of Galaxy Schema.

OLAP-style query operations across the cognitive galaxy.
Optional layer - degrades gracefully if unavailable.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from memory_thread.services.fact_store import fact_store
from memory_thread.services.belief_store import belief_store, Belief
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class GalaxyQueryResult:
    """Result from a galaxy query."""
    beliefs: List[Belief]
    facts_referenced: int
    agents_involved: List[str]
    query_type: str
    filters_applied: Dict


class GalaxyQuery:
    """
    OLAP-style queries across the cognitive galaxy.
    
    Operations:
    - SLICE: Filter by source
    - DICE: Filter by multiple dimensions
    - DRILL DOWN: Navigate to source facts
    - ROLL UP: Aggregate beliefs
    """
    
    def __init__(self):
        self.fact_store = fact_store
        self.belief_store = belief_store
    
    def slice(
        self,
        source_uri: str = None,
        fact_id: str = None
    ) -> GalaxyQueryResult:
        """
        SLICE: Get all beliefs derived from a specific source.
        
        "Show me all beliefs about auth_service.py"
        """
        beliefs = []
        
        if fact_id:
            beliefs = self.belief_store.get_beliefs(fact_id=fact_id)
        elif source_uri:
            # Find facts from this source
            facts = self.fact_store.list_facts()
            for fact in facts:
                if fact.get("source_uri") == source_uri:
                    beliefs.extend(self.belief_store.get_beliefs(fact_id=fact["fact_id"]))
        
        agents = list(set(b.agent_id for b in beliefs))
        
        return GalaxyQueryResult(
            beliefs=beliefs,
            facts_referenced=len(set(b.fact_id for b in beliefs)),
            agents_involved=agents,
            query_type="SLICE",
            filters_applied={"source_uri": source_uri, "fact_id": fact_id}
        )
    
    def dice(
        self,
        agent_id: str = None,
        min_authority: float = None,
        min_confidence: float = None,
        content_type: str = None
    ) -> GalaxyQueryResult:
        """
        DICE: Multi-dimensional filter.
        
        "Show me beliefs from Security agents with authority > 0.8"
        """
        beliefs = self.belief_store.get_beliefs(
            agent_id=agent_id,
            min_confidence=min_confidence or 0.0
        )
        
        # Apply additional filters
        if min_authority:
            beliefs = [b for b in beliefs if b.authority >= min_authority]
        
        agents = list(set(b.agent_id for b in beliefs))
        
        return GalaxyQueryResult(
            beliefs=beliefs,
            facts_referenced=len(set(b.fact_id for b in beliefs)),
            agents_involved=agents,
            query_type="DICE",
            filters_applied={
                "agent_id": agent_id,
                "min_authority": min_authority,
                "min_confidence": min_confidence
            }
        )
    
    def drill_down(self, belief_id: str) -> Dict[str, Any]:
        """
        DRILL DOWN: Navigate from belief to source fact.
        
        "Show me the raw event that led to this belief"
        """
        belief = self.belief_store.get_belief(belief_id)
        if not belief:
            return {"error": f"Belief not found: {belief_id}"}
        
        fact = self.fact_store.get(belief.fact_id)
        
        return {
            "belief": belief.to_dict() if belief else None,
            "source_fact": fact,
            "provenance": belief.derived_from if belief else None
        }
    
    def roll_up(
        self,
        entity_query: str = None,
        agent_id: str = None
    ) -> Dict[str, Any]:
        """
        ROLL UP: Aggregate beliefs into summary.
        
        "Summarize all high-confidence beliefs about authentication"
        """
        # Search for relevant beliefs
        beliefs = self.belief_store.search_beliefs(
            query=entity_query or "",
            agent_id=agent_id,
            top_k=20
        )
        
        if not beliefs:
            return {
                "summary": "No beliefs found",
                "belief_count": 0,
                "avg_confidence": 0,
                "agents": []
            }
        
        avg_confidence = sum(b.confidence for b in beliefs) / len(beliefs)
        avg_authority = sum(b.authority for b in beliefs) / len(beliefs)
        agents = list(set(b.agent_id for b in beliefs))
        
        # Generate summary (could use LLM in future)
        top_beliefs = sorted(beliefs, key=lambda b: b.truth_score, reverse=True)[:5]
        summary_points = [b.content[:80] for b in top_beliefs]
        
        return {
            "summary": "; ".join(summary_points),
            "belief_count": len(beliefs),
            "avg_confidence": round(avg_confidence, 3),
            "avg_authority": round(avg_authority, 3),
            "agents": agents,
            "top_beliefs": [b.to_dict() for b in top_beliefs]
        }
    
    def query(
        self,
        operation: str,
        **kwargs
    ) -> Any:
        """
        Generic query dispatcher.
        
        Args:
            operation: SLICE, DICE, DRILL_DOWN, ROLL_UP
            **kwargs: Operation-specific parameters
        """
        ops = {
            "SLICE": self.slice,
            "DICE": self.dice,
            "DRILL_DOWN": self.drill_down,
            "ROLL_UP": self.roll_up,
        }
        
        handler = ops.get(operation.upper())
        if not handler:
            return {"error": f"Unknown operation: {operation}"}
        
        try:
            return handler(**kwargs)
        except Exception as e:
            log.error(f"Galaxy query failed: {e}")
            return {"error": str(e)}
    
    def semantic_search(
        self,
        query: str,
        agent_id: str = None,
        top_k: int = 10
    ) -> GalaxyQueryResult:
        """
        Semantic search across all beliefs.
        """
        beliefs = self.belief_store.search_beliefs(
            query=query,
            agent_id=agent_id,
            top_k=top_k
        )
        
        return GalaxyQueryResult(
            beliefs=beliefs,
            facts_referenced=len(set(b.fact_id for b in beliefs)),
            agents_involved=list(set(b.agent_id for b in beliefs)),
            query_type="SEMANTIC_SEARCH",
            filters_applied={"query": query, "agent_id": agent_id}
        )
    
    def get_conflicts(self) -> List[Dict]:
        """
        Find conflicting beliefs across agents.
        
        Returns beliefs about the same fact with contradicting content.
        """
        conflicts = []
        facts_with_beliefs = {}
        
        # Group beliefs by fact
        all_beliefs = self.belief_store.get_beliefs()
        for belief in all_beliefs:
            if belief.fact_id not in facts_with_beliefs:
                facts_with_beliefs[belief.fact_id] = []
            facts_with_beliefs[belief.fact_id].append(belief)
        
        # Find facts with multiple agents having different beliefs
        for fact_id, beliefs in facts_with_beliefs.items():
            if len(beliefs) < 2:
                continue
            
            agents = set(b.agent_id for b in beliefs)
            if len(agents) < 2:
                continue
            
            # Check for potential conflicts (simple: different agents, different content)
            conflicts.append({
                "fact_id": fact_id,
                "beliefs": [b.to_dict() for b in beliefs],
                "agents": list(agents),
                "severity": "potential"  # Would need NLP to determine actual conflict
            })
        
        return conflicts


# Singleton
galaxy_query = GalaxyQuery()
