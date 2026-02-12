"""
Belief Store - Layer 1 of Galaxy Schema.

Manages belief dimensions (agent interpretations of facts).
Falls back to single-agent mode if multi-agent fails.
"""
import os
import json
import uuid
import math
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, asdict

from memory_thread.utils.logger import get_logger
from memory_thread.utils.embeddings import get_embedding

log = get_logger(__name__)

# File fallback
BELIEFS_DIR = Path(os.path.expanduser("~/.mt/beliefs"))


@dataclass
class Belief:
    """A belief (interpretation) derived from a fact."""
    belief_id: str
    fact_id: str
    agent_id: str
    content: str
    confidence: float
    authority: float
    freshness: float
    created_at: str
    derived_from: str  # Provenance
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @property
    def truth_score(self) -> float:
        """Composite truth score."""
        return (
            0.35 * self.confidence +
            0.30 * self.authority +
            0.25 * self.freshness +
            0.10 * math.log(1 + self.metadata.get("corroboration", 0))
        )


class BeliefStore:
    """
    Multi-dimensional belief storage.
    
    Each belief:
    - Links to a fact via derived_from
    - Belongs to an agent (dimension)
    - Has confidence, authority, freshness
    
    Fallback: Single-agent mode if DB fails
    """
    
    DEFAULT_AGENT = "default"
    
    def __init__(self):
        self._pg = None
        self._qdrant = None
        self._use_db = True
        self._ensure_fallback_dir()
    
    def _ensure_fallback_dir(self):
        BELIEFS_DIR.mkdir(parents=True, exist_ok=True)
    
    @property
    def pg(self):
        if self._pg is None:
            try:
                from memory_thread.db.postgres_client import PostgresClient
                self._pg = PostgresClient()
            except Exception as e:
                log.warning(f"Postgres unavailable for beliefs: {e}")
                self._use_db = False
        return self._pg
    
    @property
    def qdrant(self):
        if self._qdrant is None:
            try:
                from memory_thread.db.qdrant_client import QdrantClientWrapper
                self._qdrant = QdrantClientWrapper()
            except Exception as e:
                log.warning(f"Qdrant unavailable for beliefs: {e}")
        return self._qdrant
    
    def derive(
        self,
        fact_id: str,
        belief_content: str,
        agent_id: str = None,
        confidence: float = 0.8,
        authority: float = 0.5,
        metadata: Dict = None
    ) -> str:
        """
        Derive a belief from a fact.
        
        Args:
            fact_id: The fact this belief interprets
            belief_content: The interpretation/belief text
            agent_id: Which agent holds this belief
            confidence: How confident (0-1)
            authority: Agent's authority in this domain (0-1)
            metadata: Additional metadata
            
        Returns:
            belief_id
        """
        agent_id = agent_id or self.DEFAULT_AGENT
        belief_id = f"blf_{uuid.uuid4().hex[:12]}"
        
        belief = Belief(
            belief_id=belief_id,
            fact_id=fact_id,
            agent_id=agent_id,
            content=belief_content,
            confidence=min(1.0, max(0.0, confidence)),
            authority=min(1.0, max(0.0, authority)),
            freshness=1.0,  # Fresh when created
            created_at=datetime.utcnow().isoformat(),
            derived_from=f"fact:{fact_id}",
            metadata=metadata or {}
        )
        
        # Try DB first
        if self._use_db and self.pg:
            try:
                self._store_db(belief)
            except Exception as e:
                log.warning(f"DB store failed for belief: {e}")
                self._store_file(belief)
        else:
            self._store_file(belief)
        
        # Index in Qdrant for semantic search
        self._index_belief(belief)
        
        log.info(f"Derived belief: {belief_id} from fact:{fact_id} by {agent_id}")
        return belief_id
    
    def _store_db(self, belief: Belief):
        """Store belief in Postgres."""
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO beliefs (belief_id, fact_id, agent_id, content, confidence, authority, freshness, derived_from, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                belief.belief_id,
                belief.fact_id,
                belief.agent_id,
                belief.content,
                belief.confidence,
                belief.authority,
                belief.freshness,
                belief.derived_from,
                json.dumps(belief.metadata),
                belief.created_at
            ))
    
    def _store_file(self, belief: Belief):
        """Store belief as JSON file."""
        agent_dir = BELIEFS_DIR / belief.agent_id
        agent_dir.mkdir(exist_ok=True)
        path = agent_dir / f"{belief.belief_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(belief.to_dict(), f, indent=2)
    
    def _index_belief(self, belief: Belief):
        """Index belief in Qdrant for semantic search."""
        if not self.qdrant:
            return
        
        try:
            embedding = get_embedding(belief.content)
            self.qdrant.upsert(
                collection="beliefs",
                points=[{
                    "id": belief.belief_id,
                    "vector": embedding,
                    "payload": belief.to_dict()
                }]
            )
        except Exception as e:
            log.debug(f"Belief indexing failed: {e}")
    
    def get_beliefs(
        self,
        fact_id: str = None,
        agent_id: str = None,
        min_confidence: float = 0.0
    ) -> List[Belief]:
        """
        Get beliefs, optionally filtered.
        
        Args:
            fact_id: Filter by source fact
            agent_id: Filter by agent (dimension)
            min_confidence: Minimum confidence threshold
        """
        beliefs = []
        
        # Get from files (always available)
        for agent_dir in BELIEFS_DIR.iterdir():
            if agent_dir.is_dir():
                if agent_id and agent_dir.name != agent_id:
                    continue
                
                for f in agent_dir.glob("*.json"):
                    try:
                        with open(f, 'r') as file:
                            data = json.load(file)
                            belief = Belief(**data)
                            
                            if fact_id and belief.fact_id != fact_id:
                                continue
                            if belief.confidence < min_confidence:
                                continue
                            
                            beliefs.append(belief)
                    except Exception:
                        pass
        
        return sorted(beliefs, key=lambda b: b.truth_score, reverse=True)
    
    def get_belief(self, belief_id: str) -> Optional[Belief]:
        """Get a single belief by ID."""
        # Search in files
        for agent_dir in BELIEFS_DIR.iterdir():
            if agent_dir.is_dir():
                path = agent_dir / f"{belief_id}.json"
                if path.exists():
                    with open(path, 'r') as f:
                        return Belief(**json.load(f))
        return None
    
    def decay_all(self, rate: float = 0.01) -> int:
        """
        Apply decay to all beliefs.
        
        Returns:
            Number of beliefs decayed
        """
        count = 0
        
        for agent_dir in BELIEFS_DIR.iterdir():
            if agent_dir.is_dir():
                for f in agent_dir.glob("*.json"):
                    try:
                        with open(f, 'r') as file:
                            data = json.load(file)
                        
                        # Decay freshness
                        data["freshness"] = max(0.01, data.get("freshness", 1.0) * (1 - rate))
                        
                        with open(f, 'w') as file:
                            json.dump(data, file, indent=2)
                        
                        count += 1
                    except Exception:
                        pass
        
        log.info(f"Decayed {count} beliefs at rate {rate}")
        return count
    
    def search_beliefs(
        self,
        query: str,
        agent_id: str = None,
        top_k: int = 10
    ) -> List[Belief]:
        """Semantic search across beliefs."""
        if not self.qdrant:
            # Fallback to simple text search
            return self._text_search(query, agent_id, top_k)
        
        try:
            embedding = get_embedding(query)
            results = self.qdrant.search(
                collection="beliefs",
                query_vector=embedding,
                limit=top_k
            )
            
            beliefs = []
            for r in results:
                if agent_id and r.payload.get("agent_id") != agent_id:
                    continue
                beliefs.append(Belief(**r.payload))
            
            return beliefs
        except Exception as e:
            log.warning(f"Belief search failed: {e}")
            return self._text_search(query, agent_id, top_k)
    
    def _text_search(self, query: str, agent_id: str, top_k: int) -> List[Belief]:
        """Simple text-based fallback search."""
        query_lower = query.lower()
        matches = []
        
        for belief in self.get_beliefs(agent_id=agent_id):
            if query_lower in belief.content.lower():
                matches.append(belief)
                if len(matches) >= top_k:
                    break
        
        return matches
    
    def get_stats(self) -> Dict:
        """Get belief store statistics."""
        total = 0
        by_agent = {}
        
        for agent_dir in BELIEFS_DIR.iterdir():
            if agent_dir.is_dir():
                count = len(list(agent_dir.glob("*.json")))
                by_agent[agent_dir.name] = count
                total += count
        
        return {
            "total_beliefs": total,
            "by_agent": by_agent,
            "agents_count": len(by_agent),
        }


# Singleton
belief_store = BeliefStore()
