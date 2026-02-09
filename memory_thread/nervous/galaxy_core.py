"""
Galaxy Core - Multi-Agent Cognitive Architecture.

Orchestrates agent universes, fact/belief management, and conflict resolution.
"""
import uuid
import time
from typing import Dict, Any, List, Optional, Tuple

# Use wrapper classes
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.db.qdrant_client import QdrantClientWrapper
from memory_thread.utils.embeddings import get_embedding
from memory_thread.nervous.conflict_resolution import ConflictResolver


class AgentMemorySpace:
    """
    Manages a specific agent's 'universe' of facts and beliefs.
    Each agent has their own collection namespace in Qdrant.
    """
    def __init__(self, agent_id: str, qdrant_client: QdrantClientWrapper, embedding_fn):
        self.agent_id = agent_id
        self.qdrant = qdrant_client
        self.embedding_fn = embedding_fn
        self.fact_collection = f"facts_{agent_id}"
        self.belief_collection = f"beliefs_{agent_id}"
        self._init_collections()

    def _init_collections(self):
        """Create Qdrant collections for this agent."""
        try:
            self.qdrant.create_collection_if_not_exists(self.fact_collection, vector_size=384)
            self.qdrant.create_collection_if_not_exists(self.belief_collection, vector_size=384)
        except Exception as e:
            print(f"Warning: Could not init collections for {self.agent_id}: {e}")

    def store_fact(self, fact: Dict[str, Any]):
        """Store a fact in this agent's fact collection."""
        if not fact.get("embedding"):
            content = fact.get("content", "")
            fact["embedding"] = self.embedding_fn(content)
        
        point = {
            "id": str(fact.get("id", uuid.uuid4())),
            "vector": fact["embedding"],
            "payload": {
                "content": fact.get("content", ""),
                "metadata": fact.get("metadata", {}),
                "agent_id": self.agent_id,
                "timestamp": fact.get("timestamp", time.time()),
                "type": "fact"
            }
        }
        self.qdrant.upsert(collection_name=self.fact_collection, points=[point])

    def store_belief(self, belief: Dict[str, Any]):
        """Store a belief in this agent's belief collection."""
        if not belief.get("embedding"):
            content = belief.get("content", "")
            belief["embedding"] = self.embedding_fn(content)
        
        point = {
            "id": str(belief.get("id", uuid.uuid4())),
            "vector": belief["embedding"],
            "payload": {
                "fact_id": str(belief.get("fact_id")),
                "content": belief.get("content"),
                "confidence": belief.get("confidence", 0.5),
                "authority": belief.get("authority", 0.5),
                "agent_id": self.agent_id,
                "timestamp": belief.get("timestamp", time.time()),
                "type": "belief"
            }
        }
        self.qdrant.upsert(collection_name=self.belief_collection, points=[point])

    def query(self, query_text: str, top_k: int = 5):
        """Query this agent's beliefs."""
        query_vector = self.embedding_fn(query_text)
        return self.qdrant.search(
            collection_name=self.belief_collection,
            query_vector=query_vector,
            limit=top_k
        )


class GalaxyBridge:
    """
    Tracks relationships between agent universes (The Constellation).
    Uses Postgres to store explicit links.
    """
    def __init__(self, pg_client: PostgresClient):
        self.pg = pg_client
        self._ensure_table()

    def _ensure_table(self):
        """Create table if not exists."""
        query = """
        CREATE TABLE IF NOT EXISTS belief_bridges (
            id SERIAL PRIMARY KEY,
            belief_a_id UUID NOT NULL,
            belief_b_id UUID NOT NULL,
            agent_a_id VARCHAR(255) NOT NULL,
            agent_b_id VARCHAR(255) NOT NULL,
            relationship VARCHAR(50),
            confidence FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_belief_bridges_a ON belief_bridges(belief_a_id);
        CREATE INDEX IF NOT EXISTS idx_belief_bridges_b ON belief_bridges(belief_b_id);
        """
        try:
            self.pg.execute(query)
        except Exception as e:
            print(f"Warning: Could not create belief_bridges table: {e}")

    def link_beliefs(self, belief_a: Dict, belief_b: Dict, relationship: str, confidence: float):
        """Create explicit link between beliefs from different agents."""
        query = """
            INSERT INTO belief_bridges (
                belief_a_id, belief_b_id, agent_a_id, agent_b_id, relationship, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """
        self.pg.execute(query, (
            belief_a['id'], belief_b['id'],
            belief_a['agent_id'], belief_b['agent_id'],
            relationship, confidence
        ))

    def get_bridges_for_belief(self, belief_id: str) -> List[Dict]:
        """Get all bridges connected to a belief."""
        query = """SELECT * FROM belief_bridges WHERE belief_a_id = %s OR belief_b_id = %s"""
        return self.pg.fetch_all(query, (belief_id, belief_id))

    def get_galaxy_view(self, fact_id: str) -> Dict[str, Any]:
        """Get multi-perspective view for a fact."""
        return {"fact_id": fact_id, "perspectives": [], "bridges": []}


class GalaxyCore:
    """
    Core Galaxy Architecture.
    Orchestrates Multi-Agent Universes.
    """
    def __init__(self, pg_client: PostgresClient = None, qdrant_client: QdrantClientWrapper = None):
        self.pg = pg_client or PostgresClient()
        self.qdrant = qdrant_client or QdrantClientWrapper()
        self.embedding_fn = get_embedding
        self.universes: Dict[str, AgentMemorySpace] = {}
        self.agent_registry: Dict[str, float] = {}
        self.bridge = GalaxyBridge(self.pg)
        self.conflict_resolver = ConflictResolver()
        self._ensure_agents_table()

    def _ensure_agents_table(self):
        """Create agents table if not exists."""
        query = """
        CREATE TABLE IF NOT EXISTS agents (
            agent_id VARCHAR(255) PRIMARY KEY,
            authority FLOAT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            self.pg.execute(query)
        except Exception as e:
            print(f"Warning: Could not create agents table: {e}")

    def register_agent(self, agent_id: str, authority: float = 0.5):
        """Register an agent with authority score."""
        if agent_id not in self.universes:
            self.universes[agent_id] = AgentMemorySpace(agent_id, self.qdrant, self.embedding_fn)
            self.agent_registry[agent_id] = authority
            
            query = """
                INSERT INTO agents (agent_id, authority, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (agent_id) DO UPDATE SET authority = EXCLUDED.authority, updated_at = NOW()
            """
            try:
                self.pg.execute(query, (agent_id, authority))
            except Exception as e:
                print(f"Warning: Could not store agent {agent_id}: {e}")
    
    def get_agent_authority(self, agent_id: str) -> float:
        """Get authority score for an agent."""
        return self.agent_registry.get(agent_id, 0.5)
    
    def ingest(self, agent_id: str, raw_observation: Dict[str, Any]) -> Tuple[Dict, Dict]:
        """Agent forms a belief about an observation. Returns (fact, belief) tuple."""
        if agent_id not in self.universes:
            self.register_agent(agent_id, authority=0.5)
        
        universe = self.universes[agent_id]
        authority = self.agent_registry[agent_id]

        # Fact (immutable observation)
        fact_id = uuid.uuid4()
        fact = {
            "id": str(fact_id),
            "content": raw_observation.get("content", ""),
            "metadata": raw_observation.get("metadata", {}),
            "timestamp": raw_observation.get("timestamp", time.time()),
            "embedding": raw_observation.get("embedding")
        }
        universe.store_fact(fact)

        # Belief (agent's interpretation)
        belief_id = uuid.uuid4()
        belief = {
            "id": str(belief_id),
            "fact_id": str(fact_id),
            "agent_id": agent_id,
            "authority": authority,
            "content": raw_observation.get("interpretation", raw_observation.get("content", "")),
            "confidence": raw_observation.get("confidence", 0.8),
            "timestamp": time.time(),
            "embedding": raw_observation.get("embedding")
        }
        universe.store_belief(belief)

        return fact, belief
    
    def query_galaxy(self, query: str, requesting_agent: Optional[str] = None):
        """Query across all agent universes."""
        results = {"primary": [], "secondary": []}

        if requesting_agent and requesting_agent in self.universes:
            results["primary"] = self.universes[requesting_agent].query(query)

        for aid, universe in self.universes.items():
            if aid != requesting_agent:
                sub_res = universe.query(query)
                for item in sub_res:
                    if hasattr(item, 'payload'):
                        item.payload['source_agent'] = aid
                results["secondary"].extend(sub_res)

        return results
    
    def get_active_conflicts(self) -> List[Dict]:
        """Detect conflicts across agent universes."""
        return self.conflict_resolver.detect_conflicts(self.universes, self.agent_registry)
    
    def resolve_conflict(self, conflict: Dict, strategy: str = "authority") -> Dict:
        """Resolve a conflict using specified strategy."""
        return self.conflict_resolver.resolve(conflict, strategy)