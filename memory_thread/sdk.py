"""
Memory Thread SDK - Production Version

Wired to:
- PostgreSQL for event/state persistence
- Qdrant for semantic vector search

Usage:
    from memory_thread.sdk import MemoryClient
    
    mt = MemoryClient()
    mt.remember("User prefers dark mode")
    memories = mt.recall("user preferences")  # Semantic search!
"""
import uuid
import json
import os
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import TMSService, TruthVectorService, StateDerivationService
from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger
from memory_thread.nervous.vault import vault

log = get_logger(__name__)


@dataclass
class Memory:
    """A single memory with truth metadata."""
    content: str
    entity_id: uuid.UUID
    truth_score: float
    confidence: float
    authority: float
    freshness: float
    corroboration: int
    timestamp: datetime
    source: str
    memory_type: str = "fact"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "entity_id": str(self.entity_id),
            "truth_score": self.truth_score,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RecallResult:
    """Result of a recall operation."""
    memories: List[Memory]
    query: str
    total_found: int
    
    def to_context(self, max_chars: int = 2000) -> str:
        """Format memories as context for an LLM."""
        if not self.memories:
            return "No relevant memories found."
        
        lines = ["Relevant memories:"]
        char_count = len(lines[0])
        
        for i, mem in enumerate(self.memories, 1):
            line = f"{i}. [{mem.truth_score:.0%} confidence] {mem.content}"
            if char_count + len(line) > max_chars:
                break
            lines.append(line)
            char_count += len(line)
        
        return "\n".join(lines)


class MemoryClient:
    """
    Production SDK for Memory Thread.
    
    Persists to PostgreSQL, searches via Qdrant.
    Falls back to in-memory if DB unavailable.
    """
    
    def __init__(self, namespace: str = "default", use_db: bool = True, default_authority: float = 0.5):
        """
        Initialize the Memory Client.
        
        Args:
            namespace: Logical grouping for memories
            use_db: If True, use Postgres/Qdrant. If False, in-memory only.
            default_authority: Default authority score for memories (0.0-1.0)
        """
        self.namespace = namespace
        self.tms = TMSService()
        self.use_db = use_db
        self.default_authority = min(1.0, max(0.0, default_authority))
        
        # In-memory cache (always available)
        self._memories: Dict[uuid.UUID, EntityState] = {}
        self._event_log: List[Event] = []
        
        # DB clients (lazy init)
        self._pg = None
        self._qdrant = None
        self._collection_name = "memories"
        
        if use_db:
            self._init_db_clients()
    
    def _init_db_clients(self):
        """Initialize database clients with graceful fallback."""
        # Try PostgreSQL first
        try:
            from memory_thread.db.postgres_client import PostgresClient
            self._pg = PostgresClient()
            self._db_type = "postgres"
            log.info("PostgreSQL connected")
        except Exception as e:
            # Clean logging: only warn in file, not console (unless debug)
            log.warning(f"PostgreSQL unavailable: {e}. Trying SQLite...")
            self._pg = None
            
            # Fallback to SQLite
            try:
                from memory_thread.db.sqlite_client import SQLiteClient
                self._sqlite = SQLiteClient()
                self._db_type = "sqlite"
                log.info("SQLite connected (fallback mode)")
            except Exception as e2:
                log.warning(f"SQLite also failed: {e2}. Using in-memory only.")
                self._sqlite = None
                self._db_type = "memory"
        
        # Try Qdrant for semantic search
        try:
            from memory_thread.db.qdrant_client import QdrantClientWrapper
            self._qdrant = QdrantClientWrapper()
            self._ensure_collection()
            log.info("Qdrant connected")
        except Exception as e:
            # Clean logging
            log.warning(f"Qdrant unavailable: {e}. Using keyword search.")
            self._qdrant = None
    
    def _ensure_collection(self):
        """Ensure Qdrant collection exists."""
        if not self._qdrant:
            return
        try:
            self._qdrant.client.get_collection(self._collection_name)
        except Exception:
            log.info(f"Creating Qdrant collection: {self._collection_name}")
            self._qdrant.client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    "size": settings.EMBEDDING_DIMENSION,
                    "distance": settings.EMBEDDING_DISTANCE
                }
            )
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        try:
            from memory_thread.utils.embeddings import generate_embeddings
            return generate_embeddings(tuple([text]))[0]
        except Exception:
            # Return zeros if embedding fails
            return [0.0] * settings.EMBEDDING_DIMENSION
    
    def _extract_entities(self, text: str) -> List[Dict]:
        """
        Extract named entities from text using hybrid NER.
        
        Returns list of: {"entity": "PERSON", "value": "Badal", "confidence": 0.95}
        """
        try:
            from memory_thread.services.hybrid_ner_service import extract_entities
            return extract_entities(text)
        except ImportError:
            log.warning("hybrid_ner_service not available, skipping entity extraction")
            return []
        except Exception as e:
            log.warning(f"Entity extraction failed: {e}")
            return []
    
    def _infer_user_relations(self, text: str, entities: List[Dict]) -> List[Dict]:
        """
        Infer relationships from text patterns.
        
        Patterns like "My name is X" → (USER, HAS_NAME, X)
        """
        relations = []
        text_lower = text.lower()
        
        # Pattern: "My name is X" or "I am X"
        if any(p in text_lower for p in ["my name is", "i am ", "i'm ", "call me "]):
            for ent in entities:
                if ent.get("entity") == "PERSON":
                    relations.append({
                        "type": "HAS_NAME",
                        "target": ent["value"],
                        "target_type": "PERSON",
                        "confidence": 0.95
                    })
        
        # Pattern: "I work at X" or "I'm at X"
        if any(p in text_lower for p in ["work at", "work for", "working at", "employed at", "job at"]):
            for ent in entities:
                if ent.get("entity") in ["ORG", "ORGANIZATION"]:
                    relations.append({
                        "type": "WORKS_AT",
                        "target": ent["value"],
                        "target_type": "ORG",
                        "confidence": 0.9
                    })
        
        # Pattern: "I live in X" or "I'm from X"
        if any(p in text_lower for p in ["live in", "from ", "based in", "located in"]):
            for ent in entities:
                if ent.get("entity") in ["GPE", "LOC", "LOCATION"]:
                    relations.append({
                        "type": "LOCATED_IN",
                        "target": ent["value"],
                        "target_type": "LOCATION",
                        "confidence": 0.85
                    })
        
        # Pattern: "I like X" or "I prefer X"
        if any(p in text_lower for p in ["i like", "i prefer", "i love", "i enjoy"]):
            # Extract what comes after the preference keyword
            for keyword in ["like", "prefer", "love", "enjoy"]:
                if keyword in text_lower:
                    # Simple extraction: take rest of sentence
                    idx = text_lower.find(keyword)
                    preference = text[idx + len(keyword):].strip()
                    if preference and len(preference) < 50:
                        relations.append({
                            "type": "PREFERS",
                            "target": preference.rstrip('.!'),
                            "target_type": "PREFERENCE",
                            "confidence": 0.9
                        })
                    break
        
        return relations
    
    def remember(
        self,
        content: str,
        source: str = "agent",
        confidence: float = 0.8,
        authority: float = 0.5,
        memory_type: str = "fact",
        entity_id: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """
        Store a memory with truth tracking.
        
        Args:
            content: The fact/memory to store
            source: Who provided this ("user", "agent", "system")
            confidence: How confident in this fact (0.0-1.0)
            authority: Source authority level (0.0-1.0)
            memory_type: Type ("fact", "event", "preference", "identity")
            entity_id: Optional existing entity to update
        
        Returns:
            The entity ID for this memory
        """
        # Create entity ID
        if entity_id is None:
            entity_id = uuid.uuid4()
        
        # ====== WAL: Pre-write for crash safety ======
        wal_seq = None
        try:
            from memory_thread.services.wal import get_wal
            wal = get_wal(self.namespace)
            wal_seq = wal.append("remember", {
                "entity_id": str(entity_id),
                "content": content,
                "source": source,
                "confidence": confidence,
                "authority": authority,
                "memory_type": memory_type,
            })
        except Exception as e:
            log.warning(f"WAL unavailable: {e}")
        # =============================================
        
        # Adjust authority based on source
        if source == "user":
            authority = max(authority, 0.9)  # User input is high authority
        
        # Create truth vector
        truth_vector = TruthVector(
            confidence=confidence,
            authority=authority,
            freshness=1.0,
            corroboration=0
        )
        
        # Create event
        actor = ActorEnum.USER if source == "user" else ActorEnum.AGENT
        event = self.tms.create_event(
            actor=actor,
            action=ActionEnum.ADD if entity_id not in self._memories else ActionEnum.UPDATE,
            object_id=entity_id,
            delta={"content": content, "type": memory_type, "namespace": self.namespace}
        )
        event.truth_vector = truth_vector
        
        # Store in memory cache
        self._event_log.append(event)
        
        # Create or update state
        if entity_id in self._memories:
            state = self._memories[entity_id]
        else:
            state = EntityState(
                entity_id=entity_id,
                namespace=self.namespace,
                current_value={"content": "", "type": memory_type},
                truth_vector=TruthVector(confidence=0.5, authority=0.5, freshness=1.0, corroboration=0),
                last_event_id=event.id
            )
        
        # Apply event to state
        state = StateDerivationService.apply_event(state, event)
        state.current_value["content"] = content
        state.current_value["type"] = memory_type
        self._memories[entity_id] = state
        
        # Extract entities and relationships (Smart MT!)
        extracted_entities = []
        extracted_relations = []
        if source == "user":  # Only parse user input for entities
            try:
                extracted_entities = self._extract_entities(content)
                extracted_relations = self._infer_user_relations(content, extracted_entities)
                
                # Store extracted entities as separate memories
                for ent in extracted_entities:
                    ent_type = ent.get("entity", "UNKNOWN")
                    ent_value = ent.get("value", "")
                    if ent_value and ent_type in ["PERSON", "ORG", "GPE", "PRODUCT"]:
                        ent_id = uuid.uuid4()
                        self._memories[ent_id] = EntityState(
                            entity_id=ent_id,
                            namespace=self.namespace,
                            current_value={
                                "content": ent_value,
                                "type": "entity",
                                "entity_type": ent_type,
                                "source_memory_id": str(entity_id)
                            },
                            truth_vector=TruthVector(
                                confidence=ent.get("confidence", 0.9),
                                authority=0.9,
                                freshness=1.0,
                                corroboration=0
                            ),
                            last_event_id=event.id
                        )
                
                # Store extracted relations
                for rel in extracted_relations:
                    rel_id = uuid.uuid4()
                    self._memories[rel_id] = EntityState(
                        entity_id=rel_id,
                        namespace=self.namespace,
                        current_value={
                            "content": f"USER {rel['type']} {rel['target']}",
                            "type": "relation",
                            "relation_type": rel["type"],
                            "target": rel["target"],
                            "target_type": rel["target_type"],
                            "source_memory_id": str(entity_id)
                        },
                        truth_vector=TruthVector(
                            confidence=rel.get("confidence", 0.9),
                            authority=0.9,
                            freshness=1.0,
                            corroboration=0
                        ),
                        last_event_id=event.id
                    )
                
                if extracted_entities or extracted_relations:
                    log.info(f"Extracted {len(extracted_entities)} entities, {len(extracted_relations)} relations")
                    
            except Exception as e:
                log.debug(f"Entity extraction skipped: {e}")
        
        # Persist to Postgres
        if self._pg:
            try:
                self._persist_to_postgres(entity_id, content, memory_type, state, event)
            except Exception as e:
                log.warning(f"Postgres persist failed: {e}")
        # Fallback to SQLite
        elif hasattr(self, '_sqlite') and self._sqlite:
            try:
                self._persist_to_sqlite(entity_id, content, memory_type, state, event)
            except Exception as e:
                log.warning(f"SQLite persist failed: {e}")
        
        # Index in Qdrant
        if self._qdrant:
            try:
                self._index_in_qdrant(entity_id, content, memory_type, state)
            except Exception as e:
                log.warning(f"Qdrant index failed: {e}")
        
        # ====== WAL: Commit after successful processing ======
        if wal_seq is not None:
            try:
                from memory_thread.services.wal import get_wal
                wal = get_wal(self.namespace)
                wal.commit(wal_seq)
            except Exception as e:
                log.warning(f"WAL commit failed: {e}")
        # =====================================================
        
        return entity_id
    
    def _persist_to_postgres(self, entity_id: uuid.UUID, content: str, 
                              memory_type: str, state: EntityState, event: Event):
        """Persist memory to PostgreSQL."""
        with self._pg.get_cursor() as cur:
            # Upsert into memories table (or entity_state)
            cur.execute("""
                INSERT INTO entity_state (entity_id, namespace, current_value, truth_vector, last_event_id, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    current_value = EXCLUDED.current_value,
                    truth_vector = EXCLUDED.truth_vector,
                    last_event_id = EXCLUDED.last_event_id,
                    updated_at = EXCLUDED.updated_at
            """, (
                str(entity_id),
                self.namespace,
                json.dumps(state.current_value),
                json.dumps({
                    "confidence": state.truth_vector.confidence,
                    "authority": state.truth_vector.authority,
                    "freshness": state.truth_vector.freshness,
                    "corroboration": state.truth_vector.corroboration
                }),
                str(event.id),
                datetime.utcnow()
            ))
    
    def _persist_to_sqlite(self, entity_id: uuid.UUID, content: str,
                            memory_type: str, state: EntityState, event: Event):
        """Persist memory to SQLite."""
        self._sqlite.save_state(
            entity_id=str(entity_id),
            namespace=self.namespace,
            current_value=state.current_value,
            truth_vector={
                "confidence": state.truth_vector.confidence,
                "authority": state.truth_vector.authority,
                "freshness": state.truth_vector.freshness,
                "corroboration": state.truth_vector.corroboration
            },
            last_event_id=str(event.id)
        )
    
    def _index_in_qdrant(self, entity_id: uuid.UUID, content: str,
                          memory_type: str, state: EntityState):
        """Index memory in Qdrant for semantic search."""
        embedding = self._generate_embedding(content)
        
        self._qdrant.client.upsert(
            collection_name=self._collection_name,
            points=[{
                "id": str(entity_id),
                "vector": embedding,
                "payload": {
                    "content": content,
                    "type": memory_type,
                    "namespace": self.namespace,
                    "confidence": state.truth_vector.confidence,
                    "authority": state.truth_vector.authority,
                    "freshness": state.truth_vector.freshness,
                }
            }]
        )
    
    def recall(
        self,
        query: str,
        top_k: int = 5,
        min_truth_score: float = 0.3
    ) -> RecallResult:
        """
        Recall memories relevant to a query.
        
        Uses Qdrant semantic search if available, falls back to keyword.
        
        Args:
            query: What to search for
            top_k: Maximum memories to return
            min_truth_score: Minimum truth score threshold
        
        Returns:
            RecallResult with ranked memories
        """
        # Try Qdrant semantic search first
        if self._qdrant:
            try:
                return self._recall_from_qdrant(query, top_k, min_truth_score)
            except Exception as e:
                log.warning(f"Qdrant search failed: {e}, falling back to keyword")
        
        # Fallback to keyword search
        return self._recall_keyword(query, top_k, min_truth_score)
    
    def _recall_from_qdrant(self, query: str, top_k: int, 
                             min_truth_score: float) -> RecallResult:
        """Semantic search using Qdrant."""
        query_embedding = self._generate_embedding(query)
        
        results = self._qdrant.client.search(
            collection_name=self._collection_name,
            query_vector=query_embedding,
            limit=top_k * 2,  # Get extra for filtering
            query_filter={
                "must": [
                    {"key": "namespace", "match": {"value": self.namespace}}
                ]
            } if self.namespace != "default" else None
        )
        
        memories = []
        for hit in results:
            payload = hit.payload
            truth_score = (
                payload.get("confidence", 0.5) * 0.4 +
                payload.get("authority", 0.5) * 0.3 +
                payload.get("freshness", 1.0) * 0.2 +
                hit.score * 0.1  # Semantic similarity
            )
            
            if truth_score >= min_truth_score:
                memories.append(Memory(
                    content=payload.get("content", ""),
                    entity_id=uuid.UUID(hit.id) if isinstance(hit.id, str) else hit.id,
                    truth_score=truth_score,
                    confidence=payload.get("confidence", 0.5),
                    authority=payload.get("authority", 0.5),
                    freshness=payload.get("freshness", 1.0),
                    corroboration=0,
                    timestamp=datetime.utcnow(),
                    source="recall",
                    memory_type=payload.get("type", "fact")
                ))
        
        # Sort by truth score
        memories.sort(key=lambda m: m.truth_score, reverse=True)
        
        return RecallResult(
            memories=memories[:top_k],
            query=query,
            total_found=len(memories)
        )
    
    def _recall_keyword(self, query: str, top_k: int, 
                         min_truth_score: float) -> RecallResult:
        """Keyword-based search fallback."""
        query_words = set(query.lower().split())
        scored_memories = []
        
        for entity_id, state in self._memories.items():
            content = state.current_value.get("content", "")
            content_words = set(content.lower().split())
            
            overlap = len(query_words & content_words)
            if overlap == 0:
                continue
            
            relevance = overlap / max(len(query_words), 1)
            truth_score = TruthVectorService.calculate_score(state.truth_vector)
            final_score = (truth_score * 0.6 + relevance * 0.4)
            
            if final_score >= min_truth_score:
                scored_memories.append((
                    Memory(
                        content=content,
                        entity_id=entity_id,
                        truth_score=final_score,
                        confidence=state.truth_vector.confidence,
                        authority=state.truth_vector.authority,
                        freshness=state.truth_vector.freshness,
                        corroboration=int(state.truth_vector.corroboration),
                        timestamp=datetime.utcnow(),
                        source=state.current_value.get("type", "fact"),
                        memory_type=state.current_value.get("type", "fact")
                    ),
                    final_score
                ))
        
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        top_memories = [m for m, _ in scored_memories[:top_k]]
        
        return RecallResult(
            memories=top_memories,
            query=query,
            total_found=len(scored_memories)
        )
    
    def get_context_for_llm(
        self,
        query: str,
        max_tokens: int = 500,
        include_scores: bool = True
    ) -> str:
        """
        Get formatted context for LLM prompt injection.
        
        Args:
            query: The user's question/query
            max_tokens: Approximate token limit
            include_scores: Whether to include confidence scores
        
        Returns:
            Formatted context string ready for LLM
        """
        result = self.recall(query, top_k=10)
        
        if not result.memories:
            return "No relevant memories found."
        
        max_chars = max_tokens * 4
        
        if include_scores:
            return result.to_context(max_chars)
        else:
            lines = []
            char_count = 0
            for mem in result.memories:
                if char_count + len(mem.content) > max_chars:
                    break
                lines.append(f"- {mem.content}")
                char_count += len(mem.content)
            return "\n".join(lines) if lines else "No relevant memories."
    
    def forget(self, entity_id: uuid.UUID) -> bool:
        """Mark a memory as forgotten (soft delete)."""
        if entity_id in self._memories:
            state = self._memories[entity_id]
            state.truth_vector.freshness = 0.0
            
            # Update in Qdrant
            if self._qdrant:
                try:
                    self._qdrant.client.delete(
                        collection_name=self._collection_name,
                        points_selector=[str(entity_id)]
                    )
                except Exception:
                    pass
            
            return True
        return False
    
    def load_from_db(self) -> int:
        """Load memories from database into cache."""
        if not self._pg:
            return 0
        
        count = 0
        try:
            with self._pg.get_cursor() as cur:
                cur.execute("""
                    SELECT entity_id, namespace, current_value, truth_vector
                    FROM entity_state
                    WHERE namespace = %s
                """, (self.namespace,))
                
                for row in cur.fetchall():
                    entity_id = uuid.UUID(row[0])
                    current_value = row[2] if isinstance(row[2], dict) else json.loads(row[2])
                    tv_data = row[3] if isinstance(row[3], dict) else json.loads(row[3])
                    
                    state = EntityState(
                        entity_id=entity_id,
                        namespace=row[1],
                        current_value=current_value,
                        truth_vector=TruthVector(**tv_data),
                        last_event_id=uuid.uuid4()
                    )
                    self._memories[entity_id] = state
                    count += 1
                    
        except Exception as e:
            log.warning(f"Failed to load from DB: {e}")
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total = len(self._memories)
        if total == 0:
            return {"total_memories": 0, "avg_truth_score": 0}
        
        scores = [
            TruthVectorService.calculate_score(s.truth_vector)
            for s in self._memories.values()
        ]
        
        return {
            "total_memories": total,
            "total_events": len(self._event_log),
            "avg_truth_score": sum(scores) / len(scores),
            "namespace": self.namespace,
            "db_type": getattr(self, '_db_type', 'memory'),
            "qdrant_connected": self._qdrant is not None,
        }
    
    def clear(self):
        """Clear all memories."""
        self._memories.clear()
        self._event_log.clear()
    
    # =========================================================================
    # COGNITIVE FEATURES
    # =========================================================================
    
    def check_contradiction(self, content: str, entity_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """
        Check if new content contradicts existing memories.
        
        Returns:
            Dict with 'has_contradiction', 'conflicting_memory', 'explanation'
        """
        try:
            from memory_thread.services.meta_stability_service import MetaStabilityService
            meta = MetaStabilityService()
            
            # If entity_id provided, check specific entity
            if entity_id and entity_id in self._memories:
                state = self._memories[entity_id]
                # Extract key-value pairs from content
                new_delta = {"content": content}
                has_conflict = meta.check_contradiction(state, new_delta)
                
                if has_conflict:
                    return {
                        "has_contradiction": True,
                        "conflicting_memory": state.current_value.get("content", ""),
                        "entity_id": str(entity_id),
                        "explanation": "Direct value conflict detected"
                    }
            
            # Check all memories for semantic contradiction
            # Simple approach: look for opposite sentiments
            content_lower = content.lower()
            for eid, state in self._memories.items():
                existing = state.current_value.get("content", "").lower()
                
                # Simple contradiction patterns
                if "not " in content_lower or "don't" in content_lower or "hate" in content_lower:
                    # Check if existing says opposite
                    for neg, pos in [("hate", "like"), ("don't", ""), ("not", "")]:
                        if neg in content_lower:
                            positive_version = content_lower.replace(neg, pos).strip()
                            if positive_version in existing or existing in positive_version:
                                return {
                                    "has_contradiction": True,
                                    "conflicting_memory": state.current_value.get("content", ""),
                                    "entity_id": str(eid),
                                    "explanation": f"Sentiment conflict: '{content}' vs '{existing}'"
                                }
            
            return {"has_contradiction": False}
            
        except Exception as e:
            log.warning(f"Contradiction check failed: {e}")
            return {"has_contradiction": False, "error": str(e)}
    
    def apply_decay(self, decay_rate: float = 0.01) -> int:
        """
        Apply decay to all memories (reduce freshness over time).
        
        Returns number of memories affected.
        """
        try:
            from memory_thread.services.decay_engine import DecayEngine
            engine = DecayEngine()
            
            affected = 0
            for entity_id, state in self._memories.items():
                old_freshness = state.truth_vector.freshness
                # Exponential decay
                state.truth_vector.freshness *= (1 - decay_rate)
                affected += 1
            
            log.info(f"Decay applied to {affected} memories")
            return affected
            
        except Exception as e:
            log.warning(f"Decay failed: {e}")
            # Fallback: simple decay
            for state in self._memories.values():
                state.truth_vector.freshness *= (1 - decay_rate)
            return len(self._memories)
    
    def get_truth_score(self, entity_id: uuid.UUID) -> Optional[float]:
        """Get the current truth score for an entity."""
        if entity_id in self._memories:
            return TruthVectorService.calculate_score(self._memories[entity_id].truth_vector)
        return None
    
    # =========================================================================
    # GRAPH & REASONING FEATURES
    # =========================================================================
    
    def add_relation(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation_type: str,
        confidence: float = 0.9
    ) -> bool:
        """
        Add an explicit relationship between two entities.
        
        Example: add_relation(user_id, company_id, "WORKS_AT")
        """
        try:
            from memory_thread.services.graph_service import GraphService
            graph = GraphService()
            graph.add_relation(source_id, target_id, relation_type, confidence)
            log.info(f"Relation added: {source_id} -[{relation_type}]-> {target_id}")
            return True
        except Exception as e:
            log.warning(f"Failed to add relation: {e}")
            return False
    
    def find_path(
        self,
        entity_a: uuid.UUID,
        entity_b: uuid.UUID,
        max_hops: int = 3
    ) -> Optional[List[Dict]]:
        """
        Find how two entities are connected (multi-hop query).
        
        Returns list of relations forming the path, or None if not connected.
        """
        try:
            from memory_thread.services.reasoning.query_engine import QueryEngine
            engine = QueryEngine()
            return engine.find_path(entity_a, entity_b, max_hops)
        except Exception as e:
            log.warning(f"Path finding failed: {e}")
            return None
    
    def get_related(self, entity_id: uuid.UUID, depth: int = 1) -> List[Dict]:
        """Get entities related to the given entity."""
        try:
            from memory_thread.services.graph_service import GraphService
            graph = GraphService()
            return graph.get_relations(entity_id, direction="both")
        except Exception as e:
            log.warning(f"Failed to get related: {e}")
            return []
    
    def infer_relations(self, entity_id: Optional[uuid.UUID] = None) -> int:
        """
        Run inference engine to auto-deduce transitive relations.
        
        Example: If A works_at B and B located_in C → infer A affiliated_with C
        
        Returns number of new relations inferred.
        """
        try:
            from memory_thread.services.reasoning.inference_engine import InferenceEngine
            engine = InferenceEngine()
            
            if entity_id:
                engine.infer_transitive_relations(entity_id)
                return 1
            else:
                # Infer for all entities
                count = 0
                for eid in list(self._memories.keys()):
                    engine.infer_transitive_relations(eid)
                    count += 1
                return count
                
        except Exception as e:
            log.warning(f"Inference failed: {e}")
            return 0
    
    # =========================================================================
    # HYBRID RETRIEVAL
    # =========================================================================
    
    def hybrid_search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        Advanced hybrid search: vector + keyword + graph + truth scoring.
        
        This is the most comprehensive retrieval method.
        """
        try:
            from memory_thread.services.retrieval_service import retrieve_memories
            return retrieve_memories(query, top_k)
        except Exception as e:
            log.warning(f"Hybrid search failed: {e}, falling back to recall")
            result = self.recall(query, top_k)
            return [m.to_dict() for m in result.memories]
    
    # =========================================================================
    # RELIABILITY FEATURES
    # =========================================================================
    
    def take_snapshot(self, entity_id: Optional[uuid.UUID] = None) -> Optional[str]:
        """
        Create a checkpoint/snapshot of current state.
        
        Returns snapshot hash if successful.
        """
        try:
            from memory_thread.services.snapshot_service import SnapshotService
            service = SnapshotService()
            
            if entity_id and entity_id in self._memories:
                return service.take_snapshot(self._memories[entity_id])
            elif not entity_id:
                # Snapshot most important entity
                if self._memories:
                    first_entity = next(iter(self._memories.values()))
                    return service.take_snapshot(first_entity)
            return None
            
        except Exception as e:
            log.warning(f"Snapshot failed: {e}")
            return None
    
    def get_provenance(self, entity_id: uuid.UUID) -> List[str]:
        """
        Get full event history (provenance chain) for an entity.
        
        Returns list of event IDs that contributed to current state.
        """
        try:
            from memory_thread.services.ancestry_cache import AncestryCache
            cache = AncestryCache()
            return cache.get_ancestry(entity_id)
        except Exception as e:
            log.warning(f"Provenance lookup failed: {e}")
            # Fallback: return events from log
            return [str(e.id) for e in self._event_log if e.object_id == entity_id]
    
    def replay_entity(self, entity_id: uuid.UUID) -> Optional[Dict]:
        """
        Replay all events for an entity to verify state consistency.
        
        Returns replay result with success status and any differences.
        """
        try:
            from memory_thread.services.replay_service import ReplayService
            service = ReplayService()
            trace = service.capture_trace(entity_id)
            success, diffs, final_state = service.replay_trace(trace)
            
            return {
                "success": success,
                "differences": diffs,
                "final_state": final_state.current_value if final_state else None
            }
        except Exception as e:
            log.warning(f"Replay failed: {e}")
            return None
    
    # =========================================================================
    # MAINTENANCE FEATURES
    # =========================================================================
    
    def consolidate(self, entity_id: Optional[uuid.UUID] = None, window_days: int = 30) -> int:
        """
        Consolidate/assimilate repetitive events into summaries.
        
        Returns number of events consolidated.
        """
        try:
            from memory_thread.services.assimilator import AssimilatorService
            service = AssimilatorService()
            
            total = 0
            target_ids = [entity_id] if entity_id else list(self._memories.keys())
            
            for eid in target_ids:
                groups = service.detect_patterns(eid, window_days)
                for group in groups:
                    summary = service.consolidate_events(group)
                    if summary:
                        service.execute_consolidation(summary, group)
                        total += len(group)
            
            log.info(f"Consolidated {total} events")
            return total
            
        except Exception as e:
            log.warning(f"Consolidation failed: {e}")
            return 0
    
    def prune(self, threshold: float = 0.3) -> int:
        """
        Remove low-value memories (truth score below threshold).
        
        Returns number of memories pruned.
        """
        try:
            from memory_thread.services.pruner import PrunerService
            service = PrunerService()
            
            pruned = 0
            to_remove = []
            
            for entity_id, state in self._memories.items():
                score = TruthVectorService.calculate_score(state.truth_vector)
                if score < threshold:
                    to_remove.append(entity_id)
            
            for eid in to_remove:
                del self._memories[eid]
                pruned += 1
            
            log.info(f"Pruned {pruned} low-value memories")
            return pruned
            
        except Exception as e:
            log.warning(f"Pruning failed: {e}")
            return 0
    
    def get_health(self) -> Dict[str, Any]:
        """Get comprehensive system health metrics."""
        stats = self.get_stats()
        
        # Add health-specific metrics
        low_truth = sum(1 for s in self._memories.values() 
                       if TruthVectorService.calculate_score(s.truth_vector) < 0.3)
        stale = sum(1 for s in self._memories.values() 
                   if s.truth_vector.freshness < 0.2)
        
        stats.update({
            "low_truth_memories": low_truth,
            "stale_memories": stale,
            "health_score": 1.0 - (low_truth + stale) / max(len(self._memories), 1)
        })
        
        return stats
    
    # =========================================================================
    # LLM INTEGRATION
    # =========================================================================
    
    def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        use_local: bool = True
    ) -> str:
        """
        Chat with memory-augmented LLM.
        
        Uses Qdrant semantic recall to find relevant memories/code chunks.
        
        Args:
            user_message: User's input
            system_prompt: Optional system prompt
            use_local: If True, prefer local models (Ollama/SmolLM).
        
        Returns:
            LLM response with memory context
        """
        # 1. Auto-extract and store from user message
        self.remember(user_message, source="user")
        
        # 2. Check for contradictions
        contradiction = self.check_contradiction(user_message)
        contradiction_note = ""
        if contradiction.get("has_contradiction"):
            contradiction_note = f"\n[Note: User previously said: {contradiction.get('conflicting_memory', '')}]"
        
        # 3. Semantic recall from Qdrant — finds relevant code chunks, facts, etc.
        context = self.get_context_for_llm(
            query=user_message, 
            max_tokens=1000,  # ~4000 chars — enough for code context
            include_scores=True
        )
        
        # 4. Build prompt
        default_system = """You are a helpful assistant with deep memory about the user's codebase and documents.
Use the recalled memory context below to give accurate, specific answers.
When answering about code, reference file names, classes, and functions from the context.
If the context doesn't contain relevant information, say so honestly."""
        
        full_prompt = f"""{system_prompt or default_system}

RECALLED MEMORY CONTEXT:
{context}{contradiction_note}

User: {user_message}
Assistant:"""
        
        # 5. Determine Provider via Vault
        # Priority:
        # 1. Env vars (legacy overrides)
        # 2. Vault active provider
        # 3. Default fallback (SmolLM)

        user_id = os.environ.get("MT_USER", "user")

        # Check explicit env override first
        env_provider = os.environ.get("MT_PROVIDER")
        if env_provider:
            active_provider = env_provider.lower()
        else:
            active_provider = vault.get_active_provider(user_id)

        log.debug(f"Chat request - Provider: {active_provider}, User: {user_id}")

        # Retrieve full configuration for the active provider
        provider_config = vault.get_provider(active_provider, user_id)
        
        # Determine generation method based on config or name
        is_ollama = active_provider == "ollama"
        if provider_config and "localhost:11434" in (provider_config.get("base_url") or ""):
            is_ollama = True

        log.debug(f"Chat request - Provider: {active_provider}, User: {user_id}, Config: {bool(provider_config)}")

        if is_ollama:
            # Get configured model for ollama, or default
            creds = vault.get_provider("ollama", user_id) 
            # If using a custom provider name pointing to Ollama, use its model
            if active_provider != "ollama" and provider_config:
                 creds = provider_config
            
            model = creds.get("model") if creds else "llama3"
            log.debug(f"Calling Ollama with model: {model}")
            response = self._generate_ollama(full_prompt, model=model)

        elif active_provider in ["groq", "openrouter", "openai"] or (provider_config and provider_config.get("api_key")):
            # If it has an API key, try cloud generation (generic or specific)
            response = self._generate_cloud(full_prompt, provider=active_provider)

        else:
            # Fallback to SmolLM (local transformers)
            # If active_provider was 'local' or unknown, we land here.
            log.debug(f"Falling back to local SmolLM (provider={active_provider})")
            response = self._generate_smollm(full_prompt)
        
        # 6. Remember agent response (lower authority)
        self.remember(response, source="agent", confidence=0.7, authority=0.5)
        
        return response
    
    def _generate_ollama(self, prompt: str, model: str = "llama3") -> str:
        """Generate response using local Ollama instance via Chat API."""
        try:
            # Use /api/chat which is better for chat models than /api/generate
            url = "http://localhost:11434/api/chat"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                # Keep context window reasonable for 4GB VRAM
                "options": {
                    "num_ctx": 2048
                }
            }

            resp = requests.post(url, json=payload, stream=True, timeout=300)

            if resp.status_code == 200:
                full_content = []
                print("", end="", flush=True) # Start line
                
                for line in resp.iter_lines():
                    if line:
                        try:
                            # Parse streaming JSON
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                print(content, end="", flush=True)
                                full_content.append(content)
                        except json.JSONDecodeError:
                            pass
                
                print() # Newline at end
                return "".join(full_content)
                
            elif resp.status_code == 404:
                # Fallback to generate if chat endpoint missing (old versions) or model not found
                log.warning(f"Ollama chat endpoint/model failed (404). Trying /api/generate...")
                return self._generate_ollama_legacy(prompt, model)
            else:
                log.warning(f"Ollama error {resp.status_code}: {resp.text}")
                return f"[Ollama error ({resp.status_code}). Check logs.]"

        except requests.exceptions.ConnectionError:
            log.warning("Ollama unreachable at localhost:11434")
            return "[Ollama unreachable. Is 'ollama serve' running?]"
        except Exception as e:
            log.warning(f"Ollama connection failed: {e}")
            return f"[Ollama error: {e}]"

    def _generate_ollama_legacy(self, prompt: str, model: str) -> str:
        """Fallback for older Ollama versions or completion models."""
        try:
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return f"[Ollama legacy failed ({resp.status_code})]"
        except Exception:
            return "[Ollama legacy failed]"

    def _generate_smollm(self, prompt: str) -> str:
        """Generate response using local SmolLM (Transformers)."""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            
            # Lazy load model
            if not hasattr(self, '_llm_model'):
                log.info("Loading SmolLM-135M...")
                self._llm_tokenizer = AutoTokenizer.from_pretrained("HuggingFaceTB/SmolLM-135M-Instruct")
                self._llm_model = AutoModelForCausalLM.from_pretrained(
                    "HuggingFaceTB/SmolLM-135M-Instruct",
                    torch_dtype=torch.float32
                )
                log.info("SmolLM loaded")
            
            inputs = self._llm_tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            
            with torch.no_grad():
                outputs = self._llm_model.generate(
                    **inputs,
                    max_new_tokens=150,
                    do_sample=True,
                    temperature=0.7,
                    pad_token_id=self._llm_tokenizer.eos_token_id
                )
            
            response = self._llm_tokenizer.decode(outputs[0], skip_special_tokens=True)
            # Extract only the assistant's response
            if "Assistant:" in response:
                response = response.split("Assistant:")[-1].strip()
            
            return response
            
        except Exception as e:
            log.error(f"Local generation failed: {e}")
            return f"[Memory context retrieved, but local LLM unavailable. Context: {prompt[:200]}...]"
    
    def _generate_cloud(self, prompt: str, provider: str = "auto") -> str:
        """
        Generate response using cloud API.
        Checks Vault for credentials first, then Env Vars.
        """
        try:
            import requests
            
            user_id = os.environ.get("MT_USER", "default")
            
            # Groq
            if provider == "groq" or provider == "auto":
                creds = vault.get_provider("groq", user_id)
                key = creds.get("api_key") if creds else os.environ.get("GROQ_API_KEY")
                model = creds.get("model") if creds else os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

                if key:
                    log.info(f"Using Groq ({model})")
                    response = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 500,
                            "temperature": 0.7
                        },
                        timeout=30
                    )
                    if response.ok:
                        return response.json()["choices"][0]["message"]["content"]
                    else:
                        log.warning(f"Groq error: {response.status_code}")

            # OpenRouter
            if provider == "openrouter" or provider == "auto":
                creds = vault.get_provider("openrouter", user_id)
                key = creds.get("api_key") if creds else os.environ.get("OPENROUTER_API_KEY")
                model = creds.get("model") if creds else os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.1-405b-instruct")

                if key:
                    log.info(f"Using OpenRouter ({model})")
                    response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "https://github.com/badalraj9/MemoryThread",
                            "X-Title": "MemoryThread"
                        },
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 500,
                            "temperature": 0.7
                        },
                        timeout=60
                    )
                    if response.ok:
                        return response.json()["choices"][0]["message"]["content"]
                    else:
                        log.warning(f"OpenRouter error: {response.status_code}")

            # Fallback to local
            log.warning("No cloud API available/configured, falling back to local model")
            return self._generate_smollm(prompt)
            
        except Exception as e:
            log.error(f"Cloud generation failed: {e}")
            return self._generate_smollm(prompt)
    
    def ingest_fact(
        self,
        content: str,
        source_uri: str = None,
        content_type: str = "text",
        metadata: dict = None
    ) -> str:
        """
        Ingest a fact into the Galaxy Schema.
        
        Facts are:
        - Immutable (stored once)
        - Content-addressed (deduped by hash)
        - The foundation for all beliefs
        
        Args:
            content: Raw content (code, text, log)
            source_uri: Origin (file path, URL)
            content_type: Type (text, code, log, document)
            metadata: Additional metadata
            
        Returns:
            fact_id (content hash)
        """
        try:
            from memory_thread.services.fact_store import fact_store
            return fact_store.store(
                content=content,
                source_uri=source_uri,
                content_type=content_type,
                metadata=metadata
            )
        except Exception as e:
            log.error(f"Fact ingestion failed: {e}")
            # Fallback: use regular remember
            entity_id = self.remember(content, source="fact", memory_type="fact")
            return str(entity_id)
    
    def derive_belief(
        self,
        fact_id: str,
        belief: str,
        agent_id: str = None,
        confidence: float = 0.8,
        authority: float = 0.5,
        metadata: dict = None
    ) -> str:
        """
        Derive a belief from a fact.
        
        Beliefs are:
        - Agent-specific interpretations
        - Linked to source facts
        - Subject to decay and truth scoring
        
        Args:
            fact_id: The source fact hash
            belief: The interpretation/belief text
            agent_id: Which agent holds this belief (default: namespace)
            confidence: Confidence level (0-1)
            authority: Agent authority in this domain (0-1)
            metadata: Additional metadata
            
        Returns:
            belief_id
        """
        try:
            from memory_thread.services.belief_store import belief_store
            return belief_store.derive(
                fact_id=fact_id,
                belief_content=belief,
                agent_id=agent_id or self.namespace,
                confidence=confidence,
                authority=authority,
                metadata=metadata
            )
        except Exception as e:
            log.error(f"Belief derivation failed: {e}")
            # Fallback: just remember the belief
            entity_id = self.remember(belief, source="agent", memory_type="belief")
            return str(entity_id)
    
    def query_galaxy(
        self,
        operation: str,
        **kwargs
    ):
        """
        Query the cognitive galaxy using OLAP-style operations.
        
        Operations:
        - SLICE: Filter by source ("beliefs from auth.py")
        - DICE: Multi-filter ("beliefs from SecurityBot with authority > 0.8")
        - DRILL_DOWN: Get source fact for a belief
        - ROLL_UP: Aggregate beliefs into summary
        - SEARCH: Semantic search across beliefs
        
        Args:
            operation: SLICE, DICE, DRILL_DOWN, ROLL_UP, SEARCH
            **kwargs: Operation-specific filters
            
        Returns:
            GalaxyQueryResult or dict
        """
        try:
            from memory_thread.services.galaxy_query import galaxy_query
            
            if operation.upper() == "SEARCH":
                return galaxy_query.semantic_search(
                    query=kwargs.get("query", ""),
                    agent_id=kwargs.get("agent_id"),
                    top_k=kwargs.get("top_k", 10)
                )
            
            return galaxy_query.query(operation, **kwargs)
        except Exception as e:
            log.error(f"Galaxy query failed: {e}")
            # Fallback: use regular recall
            return self.recall(kwargs.get("query", ""), top_k=kwargs.get("top_k", 10))
    
    def get_galaxy_conflicts(self) -> list:
        """
        Get conflicts across agent dimensions.
        
        Returns beliefs about the same fact with different interpretations.
        """
        try:
            from memory_thread.services.galaxy_query import galaxy_query
            return galaxy_query.get_conflicts()
        except Exception as e:
            log.error(f"Conflict detection failed: {e}")
            return []
    
    def galaxy_stats(self) -> dict:
        """Get statistics from the Galaxy Schema stores."""
        stats = {"layer": "galaxy"}
        
        try:
            from memory_thread.services.fact_store import fact_store
            stats["facts"] = fact_store.get_stats()
        except Exception:
            stats["facts"] = {"error": "unavailable"}
        
        try:
            from memory_thread.services.belief_store import belief_store
            stats["beliefs"] = belief_store.get_stats()
        except Exception:
            stats["beliefs"] = {"error": "unavailable"}
        
        return stats


# Convenience function
def create_memory_client(namespace: str = "default", use_db: bool = True) -> MemoryClient:
    """Create a new MemoryClient instance."""
    return MemoryClient(namespace=namespace, use_db=use_db)
