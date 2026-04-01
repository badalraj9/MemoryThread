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
import struct
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import (
    TMSService,
    TruthVectorService,
    StateDerivationService,
)
from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger
from urllib.parse import urlparse, parse_qs
import os

log = get_logger(__name__)


class _SlabIngestPipeline:
    """Single-process slab-backed ingest path with background draining."""

    def __init__(self, owner: "MemoryClient", num_slabs: int = 512, slab_size: int = 65536):
        from memory_thread.utils.shared_memory import SlabAllocator

        self.owner = owner
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._drain_loop,
            name=f"mt-slab-ingest-{owner.namespace}",
            daemon=True,
        )
        self._accepted_count = 0
        self._processed_count = 0
        self._lock = threading.Lock()
        self._thread.start()

    def enqueue(self, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        msg_len = len(encoded)
        if msg_len + 4 > self.allocator.slab_size:
            raise ValueError("Slab payload exceeds slab size")

        slab = self.allocator.reserve_slab(timeout=1.0)
        slab.memory[:4] = struct.pack("!I", msg_len)
        slab.memory[4 : 4 + msg_len] = encoded
        self.allocator.mark_as_written(slab.slab_id)

        with self._lock:
            self._accepted_count += 1

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "accepted_count": self._accepted_count,
                "processed_count": self._processed_count,
            }

    def close(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.allocator.close()
        self.allocator.unlink()

    def _drain_loop(self) -> None:
        while not self._stop_event.is_set():
            slab = self.allocator.get_written_slab()
            if not slab:
                time.sleep(0.001)
                continue

            try:
                msg_len = struct.unpack("!I", slab.memory[:4].tobytes())[0]
                payload = json.loads(slab.memory[4 : 4 + msg_len].tobytes())
                process_hook = getattr(self.owner, "_slab_process_hook", None)
                if process_hook:
                    process_hook(payload["content"])
                self.owner._remember_direct(
                    content=payload["content"],
                    source=payload["source"],
                    confidence=payload["confidence"],
                    authority=payload["authority"],
                    memory_type=payload["memory_type"],
                    entity_id=uuid.UUID(payload["entity_id"]),
                )
                with self._lock:
                    self._processed_count += 1
            finally:
                self.allocator.release_slab(slab.slab_id)


@dataclass
class ConnectionConfig:
    """Parsed connection configuration from MT_URL."""

    host: str
    port: int
    namespace: str
    api_key: Optional[str] = None
    use_db: bool = True


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

    @classmethod
    def connect(
        cls, url: str, use_db: bool = True, default_authority: float = 0.5
    ) -> "MemoryClient":
        """
        Connect to Memory Thread using a connection string.

        Args:
            url: Connection string in format mt://host:port/namespace?api_key=xxx
                 Examples:
                   - mt://localhost:8000/my-project
                   - mt://api.memorythread.io/org/project?api_key=sk-xxx
                   - mt://localhost:8000/default
            use_db: If True, use Postgres/Qdrant. If False, in-memory only.
            default_authority: Default authority score for memories (0.0-1.0)

        Returns:
            Configured MemoryClient instance
        """
        parsed = urlparse(url)

        if parsed.scheme != "mt":
            raise ValueError(f"Invalid scheme: {parsed.scheme}. Expected 'mt'.")

        host = parsed.hostname or "localhost"
        port = parsed.port or 8000

        path = parsed.path.strip("/")
        namespace = path if path else "default"

        query_params = parse_qs(parsed.query)
        api_key = query_params.get("api_key", [None])[0]

        if api_key:
            os.environ["MT_API_KEY"] = api_key

        client = cls(namespace=namespace, use_db=use_db, default_authority=default_authority)
        log.info(f"Connected to Memory Thread at {host}:{port}/{namespace}")
        return client

    @classmethod
    def connect_from_env(cls) -> "MemoryClient":
        """
        Connect using MT_URL environment variable.

        Returns:
            Configured MemoryClient instance
        """
        mt_url = os.environ.get("MT_URL")
        if not mt_url:
            raise ValueError("MT_URL environment variable not set")

        return cls.connect(mt_url)

    def __init__(
        self,
        namespace: Optional[str] = None,
        use_db: bool = False,
        default_authority: float = 0.5,
        use_slab_ingest: bool = False,
    ):
        """
        Initialize the Memory Client.

        Args:
            namespace: Logical grouping for memories. If None, auto-resolves from .mt/ config.
            use_db: If True, use Postgres/Qdrant (slower init). If False, in-memory only (faster).
            default_authority: Default authority score for memories (0.0-1.0)
        """
        # Auto-resolve namespace if not provided
        if namespace is None:
            namespace = self._resolve_namespace()

        self.namespace = namespace
        self.tms = TMSService()
        self.use_db = use_db
        self.default_authority = min(1.0, max(0.0, default_authority))
        self.use_slab_ingest = use_slab_ingest

        # In-memory cache (always available)
        self._memories: Dict[uuid.UUID, EntityState] = {}
        self._global_memories: Dict[uuid.UUID, EntityState] = {}
        self._event_log: List[Event] = []

        # DB clients (lazy init)
        self._pg = None
        self._qdrant = None
        self._collection_name = "memories"

        if use_db:
            self._init_db_clients()

        self._slab_ingest = _SlabIngestPipeline(self) if use_slab_ingest else None
        self._slab_process_hook = None

    def _resolve_namespace(self) -> str:
        """Resolve namespace by checking .mt/ config, walking up directories, or falling back to global."""
        import os
        import json
        from pathlib import Path
        from memory_thread.config.settings import settings

        # First check .mt/ in current directory
        mt_config_path = Path(".") / settings.MT_PROJECT_DIR / "config.json"
        if mt_config_path.exists():
            try:
                with open(mt_config_path) as f:
                    config = json.load(f)
                    if config.get("namespace"):
                        return config["namespace"]
            except Exception:
                pass

        # Walk up directories like git
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            mt_dir = parent / ".mt"
            if mt_dir.exists():
                config_path = mt_dir / "config.json"
                if config_path.exists():
                    try:
                        with open(config_path) as f:
                            config = json.load(f)
                            if config.get("namespace"):
                                return config["namespace"]
                    except Exception:
                        pass

            if parent == parent.parent:
                break

        # Fall back to global namespace
        return self._get_global_namespace()

    def _get_global_namespace(self) -> str:
        """Get or create global namespace from ~/.mt/config.json."""
        import os
        import json
        from pathlib import Path
        from memory_thread.config.settings import settings

        global_dir = Path(settings.MT_GLOBAL_DIR)
        global_dir.mkdir(parents=True, exist_ok=True)
        config_path = global_dir / "config.json"

        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    return config.get("namespace", "global")
            except Exception:
                pass

        namespace = os.environ.get("MT_USER", "global")
        config = {"namespace": namespace, "type": "global"}
        with open(config_path, "w") as f:
            json.dump(config, f)

        return namespace

    def _init_db_clients(self):
        """Initialize database clients with graceful fallback."""
        # Try PostgreSQL first
        try:
            from memory_thread.db.postgres_client import PostgresClient

            self._pg = PostgresClient()
            self._db_type = "postgres"
            log.info("PostgreSQL connected")
        except Exception as e:
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
                    "distance": settings.EMBEDDING_DISTANCE,
                },
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
                    relations.append(
                        {
                            "type": "HAS_NAME",
                            "target": ent["value"],
                            "target_type": "PERSON",
                            "confidence": 0.95,
                        }
                    )

        # Pattern: "I work at X" or "I'm at X"
        if any(
            p in text_lower for p in ["work at", "work for", "working at", "employed at", "job at"]
        ):
            for ent in entities:
                if ent.get("entity") in ["ORG", "ORGANIZATION"]:
                    relations.append(
                        {
                            "type": "WORKS_AT",
                            "target": ent["value"],
                            "target_type": "ORG",
                            "confidence": 0.9,
                        }
                    )

        # Pattern: "I live in X" or "I'm from X"
        if any(p in text_lower for p in ["live in", "from ", "based in", "located in"]):
            for ent in entities:
                if ent.get("entity") in ["GPE", "LOC", "LOCATION"]:
                    relations.append(
                        {
                            "type": "LOCATED_IN",
                            "target": ent["value"],
                            "target_type": "LOCATION",
                            "confidence": 0.85,
                        }
                    )

        # Pattern: "I like X" or "I prefer X"
        if any(p in text_lower for p in ["i like", "i prefer", "i love", "i enjoy"]):
            # Extract what comes after the preference keyword
            for keyword in ["like", "prefer", "love", "enjoy"]:
                if keyword in text_lower:
                    # Simple extraction: take rest of sentence
                    idx = text_lower.find(keyword)
                    preference = text[idx + len(keyword) :].strip()
                    if preference and len(preference) < 50:
                        relations.append(
                            {
                                "type": "PREFERS",
                                "target": preference.rstrip(".!"),
                                "target_type": "PREFERENCE",
                                "confidence": 0.9,
                            }
                        )
                    break

        return relations

    def remember(
        self,
        content: str,
        source: str = "agent",
        confidence: float = 0.8,
        authority: float = 0.5,
        memory_type: str = "fact",
        entity_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        if self._slab_ingest is not None:
            if entity_id is None:
                entity_id = uuid.uuid4()
            self._slab_ingest.enqueue(
                {
                    "entity_id": str(entity_id),
                    "content": content,
                    "source": source,
                    "confidence": confidence,
                    "authority": authority,
                    "memory_type": memory_type,
                }
            )
            return entity_id

        return self._remember_direct(
            content=content,
            source=source,
            confidence=confidence,
            authority=authority,
            memory_type=memory_type,
            entity_id=entity_id,
        )

    def _remember_direct(
        self,
        content: str,
        source: str = "agent",
        confidence: float = 0.8,
        authority: float = 0.5,
        memory_type: str = "fact",
        entity_id: Optional[uuid.UUID] = None,
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
            wal_seq = wal.append(
                "remember",
                {
                    "entity_id": str(entity_id),
                    "content": content,
                    "source": source,
                    "confidence": confidence,
                    "authority": authority,
                    "memory_type": memory_type,
                },
            )
        except Exception as e:
            log.warning(f"WAL unavailable: {e}")
        # =============================================

        # Adjust authority based on source
        if source == "user":
            authority = max(authority, 0.9)  # User input is high authority

        # Create truth vector
        truth_vector = TruthVector(
            confidence=confidence, authority=authority, freshness=1.0, corroboration=0
        )

        # Create event
        actor = ActorEnum.USER if source == "user" else ActorEnum.AGENT
        event = self.tms.create_event(
            actor=actor,
            action=ActionEnum.ADD if entity_id not in self._memories else ActionEnum.UPDATE,
            object_id=entity_id,
            delta={"content": content, "type": memory_type, "namespace": self.namespace},
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
                truth_vector=TruthVector(
                    confidence=0.5, authority=0.5, freshness=1.0, corroboration=0
                ),
                last_event_id=event.id,
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
                                "source_memory_id": str(entity_id),
                            },
                            truth_vector=TruthVector(
                                confidence=ent.get("confidence", 0.9),
                                authority=0.9,
                                freshness=1.0,
                                corroboration=0,
                            ),
                            last_event_id=event.id,
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
                            "source_memory_id": str(entity_id),
                        },
                        truth_vector=TruthVector(
                            confidence=rel.get("confidence", 0.9),
                            authority=0.9,
                            freshness=1.0,
                            corroboration=0,
                        ),
                        last_event_id=event.id,
                    )

                if extracted_entities or extracted_relations:
                    log.info(
                        f"Extracted {len(extracted_entities)} entities, {len(extracted_relations)} relations"
                    )

            except Exception as e:
                log.debug(f"Entity extraction skipped: {e}")

        # Persist to Postgres
        if self._pg:
            try:
                self._persist_to_postgres(entity_id, content, memory_type, state, event)
            except Exception as e:
                log.warning(f"Postgres persist failed: {e}")
        # Fallback to SQLite
        elif hasattr(self, "_sqlite") and self._sqlite:
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

    def _persist_to_postgres(
        self, entity_id: uuid.UUID, content: str, memory_type: str, state: EntityState, event: Event
    ):
        """Persist memory to PostgreSQL - event first (for FK), then state."""
        with self._pg.get_cursor() as cur:
            # First: Persist the event (required for FK constraint)
            cur.execute(
                """
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    str(event.id),
                    event.namespace,
                    event.timestamp,
                    event.actor.value,
                    event.action.value,
                    str(event.object_id),
                    json.dumps(event.delta),
                    [str(uid) for uid in event.antecedents],
                    json.dumps(
                        {
                            "confidence": event.truth_vector.confidence,
                            "authority": event.truth_vector.authority,
                            "freshness": event.truth_vector.freshness,
                            "corroboration": event.truth_vector.corroboration,
                        }
                    ),
                ),
            )

            # Second: Persist entity state (references event via last_event_id FK)
            cur.execute(
                """
                INSERT INTO entity_state (entity_id, namespace, current_value, truth_vector, last_event_id, updated_at, version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    current_value = EXCLUDED.current_value,
                    truth_vector = EXCLUDED.truth_vector,
                    last_event_id = EXCLUDED.last_event_id,
                    updated_at = EXCLUDED.updated_at,
                    version = entity_state.version + 1
            """,
                (
                    str(entity_id),
                    self.namespace,
                    json.dumps(state.current_value),
                    json.dumps(
                        {
                            "confidence": state.truth_vector.confidence,
                            "authority": state.truth_vector.authority,
                            "freshness": state.truth_vector.freshness,
                            "corroboration": state.truth_vector.corroboration,
                        }
                    ),
                    str(event.id),
                    datetime.utcnow(),
                    state.version if hasattr(state, "version") else 1,
                ),
            )

    def _persist_to_sqlite(
        self, entity_id: uuid.UUID, content: str, memory_type: str, state: EntityState, event: Event
    ):
        """Persist memory to SQLite."""
        self._sqlite.save_state(
            entity_id=str(entity_id),
            namespace=self.namespace,
            current_value=state.current_value,
            truth_vector={
                "confidence": state.truth_vector.confidence,
                "authority": state.truth_vector.authority,
                "freshness": state.truth_vector.freshness,
                "corroboration": state.truth_vector.corroboration,
            },
            last_event_id=str(event.id),
        )

    def _index_in_qdrant(
        self, entity_id: uuid.UUID, content: str, memory_type: str, state: EntityState
    ):
        """Index memory in Qdrant for semantic search."""
        from qdrant_client.models import PointStruct

        embedding = self._generate_embedding(content)

        self._qdrant.client.upsert(
            collection_name=self._collection_name,
            points=[
                PointStruct(
                    id=str(entity_id),
                    vector=embedding,
                    payload={
                        "content": content,
                        "type": memory_type,
                        "namespace": self.namespace,
                        "confidence": state.truth_vector.confidence,
                        "authority": state.truth_vector.authority,
                        "freshness": state.truth_vector.freshness,
                    },
                )
            ],
        )

    def recall(
        self,
        query: str,
        top_k: int = 5,
        min_truth_score: float = 0.3,
        project: Optional[str] = None,
    ) -> RecallResult:
        """
        Recall memories relevant to a query.

        Uses Qdrant semantic search if available, falls back to keyword.
        Searches both current project namespace AND global namespace simultaneously,
        merging results with project namespace getting higher authority weight.

        Args:
            query: What to search for
            top_k: Maximum memories to return
            min_truth_score: Minimum truth score threshold
            project: Optional specific project namespace to search (isolated, no global)

        Returns:
            RecallResult with ranked memories
        """
        # If specific project requested, search only that namespace
        if project:
            original_namespace = self.namespace
            self.namespace = project
            result = self._recall_impl(query, top_k, min_truth_score)
            self.namespace = original_namespace
            return result

        # Otherwise search both project and global namespaces
        global_namespace = self._get_global_namespace()

        # Search project namespace
        project_result = self._recall_impl(query, top_k, min_truth_score)

        # Search global namespace if different
        if global_namespace != self.namespace:
            self.namespace = global_namespace
            global_result = self._recall_impl(query, top_k, min_truth_score)
            self.namespace = self.namespace  # Restore

            # Merge results with project namespace getting higher authority
            return self._merge_results(project_result, global_result, top_k)

        return project_result

    def _recall_impl(self, query: str, top_k: int, min_truth_score: float) -> RecallResult:
        """Internal recall implementation."""
        # Try Qdrant semantic search first
        if self._qdrant:
            try:
                return self._recall_from_qdrant(query, top_k, min_truth_score)
            except Exception as e:
                log.warning(f"Qdrant search failed: {e}, falling back to keyword")

        # Fallback to keyword search
        return self._recall_keyword(query, top_k, min_truth_score)

    def _merge_results(
        self, project_result: RecallResult, global_result: RecallResult, top_k: int
    ) -> RecallResult:
        """Merge project and global results, with project getting higher authority."""
        from memory_thread.config.settings import settings

        global_weight = getattr(settings, "GLOBAL_AUTHORITY_WEIGHT", 0.8)

        # Adjust authority for global memories
        adjusted_global = []
        for mem in global_result.memories:
            adjusted_mem = Memory(
                content=mem.content,
                entity_id=mem.entity_id,
                truth_score=mem.truth_score * global_weight,
                confidence=mem.confidence,
                authority=mem.authority * global_weight,
                freshness=mem.freshness,
                corroboration=mem.corroboration,
                timestamp=mem.timestamp,
                source=mem.source,
                memory_type=mem.memory_type,
            )
            adjusted_global.append(adjusted_mem)

        # Combine and sort
        all_memories = project_result.memories + adjusted_global
        all_memories.sort(key=lambda m: m.truth_score, reverse=True)

        return RecallResult(
            memories=all_memories[:top_k], query=project_result.query, total_found=len(all_memories)
        )

    def _include_shared_memories(self, memories: List[Memory]) -> List[Memory]:
        """Include shared memories from .mt/ folder with adjusted authority."""
        from memory_thread.config.settings import settings

        shared_authority = 0.9

        for entity_id, state in self._global_memories.items():
            mem = Memory(
                content=state.current_value.get("content", ""),
                entity_id=entity_id,
                truth_score=TruthVectorService.calculate_score(state.truth_vector),
                confidence=state.truth_vector.confidence,
                authority=state.truth_vector.authority * shared_authority,
                freshness=state.truth_vector.freshness,
                corroboration=state.truth_vector.corroboration,
                timestamp=state.updated_at,
                source="shared",
                memory_type=state.current_value.get("type", "fact"),
            )
            memories.append(mem)

        return memories

    def _recall_from_qdrant(self, query: str, top_k: int, min_truth_score: float) -> RecallResult:
        """Semantic search using Qdrant."""
        query_embedding = self._generate_embedding(query)

        try:
            results = self._qdrant.client.query_points(
                collection_name=self._collection_name,
                query=query_embedding,
                limit=top_k * 2,
                query_filter={"must": [{"key": "namespace", "match": {"value": self.namespace}}]}
                if self.namespace != "default"
                else None,
            )
            results = results.points
        except Exception as e:
            log.warning(f"Qdrant search failed: {e}")
            return RecallResult(memories=[], query=query, total_found=0)

        memories = []
        for hit in results:
            payload = hit.payload

            truth_vector = TruthVector(
                confidence=payload.get("confidence", 0.5),
                authority=payload.get("authority", 0.5),
                freshness=payload.get("freshness", 1.0),
                corroboration=hit.score,
            )

            truth_score = TruthVectorService.calculate_score(truth_vector)

            if truth_score >= min_truth_score:
                memories.append(
                    Memory(
                        content=payload.get("content", ""),
                        entity_id=uuid.UUID(hit.id) if isinstance(hit.id, str) else hit.id,
                        truth_score=truth_score,
                        confidence=truth_vector.confidence,
                        authority=truth_vector.authority,
                        freshness=truth_vector.freshness,
                        corroboration=truth_vector.corroboration,
                        timestamp=datetime.utcnow(),
                        source="recall",
                        memory_type=payload.get("type", "fact"),
                    )
                )

        memories.sort(key=lambda m: m.truth_score, reverse=True)

        return RecallResult(memories=memories[:top_k], query=query, total_found=len(memories))

    def _recall_keyword(self, query: str, top_k: int, min_truth_score: float) -> RecallResult:
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
            final_score = truth_score * 0.6 + relevance * 0.4

            if final_score >= min_truth_score:
                scored_memories.append(
                    (
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
                            memory_type=state.current_value.get("type", "fact"),
                        ),
                        final_score,
                    )
                )

        scored_memories.sort(key=lambda x: x[1], reverse=True)
        top_memories = [m for m, _ in scored_memories[:top_k]]

        return RecallResult(memories=top_memories, query=query, total_found=len(scored_memories))

    def get_context_for_llm(
        self, query: str, max_tokens: int = 500, include_scores: bool = True
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

            if self._qdrant:
                try:
                    self._qdrant.client.delete(
                        collection_name=self._collection_name, points_selector=[str(entity_id)]
                    )
                except Exception:
                    pass

            if self._pg:
                try:
                    with self._pg.get_cursor() as cur:
                        cur.execute(
                            "DELETE FROM entity_state WHERE entity_id = %s", (str(entity_id),)
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
                cur.execute(
                    """
                    SELECT entity_id, namespace, current_value, truth_vector
                    FROM entity_state
                    WHERE namespace = %s
                """,
                    (self.namespace,),
                )

                for row in cur.fetchall():
                    entity_id = uuid.UUID(row[0])
                    current_value = row[2] if isinstance(row[2], dict) else json.loads(row[2])
                    tv_data = row[3] if isinstance(row[3], dict) else json.loads(row[3])

                    state = EntityState(
                        entity_id=entity_id,
                        namespace=row[1],
                        current_value=current_value,
                        truth_vector=TruthVector(**tv_data),
                        last_event_id=uuid.uuid4(),
                    )
                    self._memories[entity_id] = state
                    count += 1

        except Exception as e:
            log.warning(f"Failed to load from DB: {e}")

        # Load shared project memories from .mt/ folder if it exists
        self._load_shared_memories()

        return count

    def _load_shared_memories(self) -> int:
        """Load shared project memories from .mt/ folder in git repo root."""
        from pathlib import Path
        from memory_thread.config.settings import settings

        # Find git repo root
        current = Path.cwd()
        git_root = None
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                git_root = parent
                break
            if parent == parent.parent:
                break

        if not git_root:
            return 0

        # Check for .mt/ folder in git root
        mt_dir = git_root / settings.MT_PROJECT_DIR
        shared_memories_file = mt_dir / "shared_memories.json"

        if not shared_memories_file.exists():
            return 0

        count = 0
        try:
            with open(shared_memories_file) as f:
                shared_data = json.load(f)

            from memory_thread.config.settings import settings

            for mem_data in shared_data.get("memories", []):
                entity_id = uuid.UUID(mem_data["entity_id"])
                current_value = mem_data.get("current_value", {})
                tv_data = mem_data.get("truth_vector", {})

                # Apply authority weight for shared memories
                source_authority = tv_data.get("authority", 0.5)
                tv_data["authority"] = source_authority * 0.9

                state = EntityState(
                    entity_id=entity_id,
                    namespace="shared",
                    current_value=current_value,
                    truth_vector=TruthVector(**tv_data),
                    last_event_id=uuid.uuid4(),
                )
                self._global_memories[entity_id] = state
                count += 1

            log.info(f"Loaded {count} shared memories from {shared_memories_file}")

        except Exception as e:
            log.warning(f"Failed to load shared memories: {e}")

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total = len(self._memories)
        if total == 0:
            stats = {"total_memories": 0, "avg_truth_score": 0}
            if hasattr(self, "_db_type"):
                stats["db_type"] = self._db_type
            stats["qdrant_connected"] = self._qdrant is not None
            if self._slab_ingest is not None:
                stats.update(self._slab_ingest.stats())
            return stats

        scores = [
            TruthVectorService.calculate_score(s.truth_vector) for s in self._memories.values()
        ]

        stats = {
            "total_memories": total,
            "total_events": len(self._event_log),
            "avg_truth_score": sum(scores) / len(scores),
            "namespace": self.namespace,
            "db_type": getattr(self, "_db_type", "memory"),
            "qdrant_connected": self._qdrant is not None,
        }
        if self._slab_ingest is not None:
            stats.update(self._slab_ingest.stats())
        return stats

    def close(self) -> None:
        """Release background resources owned by this client."""
        if self._slab_ingest is not None:
            self._slab_ingest.close()
            self._slab_ingest = None

    def clear(self):
        """Clear all memories."""
        self._memories.clear()
        self._event_log.clear()

    # =========================================================================
    # COGNITIVE FEATURES
    # =========================================================================

    def check_contradiction(
        self, content: str, entity_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Check if new content contradicts existing memories.
        Delegates to MetaStabilityService.check_contradiction.

        Returns:
            Dict with 'has_contradiction', 'conflicting_memory', 'explanation'
        """
        try:
            from memory_thread.services.meta_stability_service import MetaStabilityService

            meta = MetaStabilityService()

            if entity_id and entity_id in self._memories:
                state = self._memories[entity_id]
                new_delta = {"content": content}
                has_conflict = meta.check_contradiction(state, new_delta)

                if has_conflict:
                    return {
                        "has_contradiction": True,
                        "conflicting_memory": state.current_value.get("content", ""),
                        "entity_id": str(entity_id),
                        "explanation": "Direct value conflict detected",
                    }

            for eid, state in self._memories.items():
                new_delta = {"content": content}
                if meta.check_contradiction(state, new_delta):
                    return {
                        "has_contradiction": True,
                        "conflicting_memory": state.current_value.get("content", ""),
                        "entity_id": str(eid),
                        "explanation": "Contradiction detected via MetaStabilityService",
                    }

            return {"has_contradiction": False}

        except Exception as e:
            log.warning(f"Contradiction check failed: {e}")
            return {"has_contradiction": False, "error": str(e)}

    def apply_decay(self, decay_rate: float = 0.01) -> int:
        """
        Apply decay to all memories using TruthVectorService.decay_freshness.

        Returns number of memories affected.
        """
        try:
            from memory_thread.services.tms_service import TruthVectorService

            affected = 0
            for entity_id, state in self._memories.items():
                memory_type = state.current_value.get("type", "fact")
                event_time = state.updated_at
                state.truth_vector.freshness = TruthVectorService.decay_freshness(
                    state.truth_vector, event_time, memory_type
                )
                affected += 1

            log.info(f"Decay applied to {affected} memories")
            return affected

        except Exception as e:
            log.warning(f"Decay failed: {e}")
            for state in self._memories.values():
                state.truth_vector.freshness *= 1 - decay_rate
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
        confidence: float = 0.9,
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
        self, entity_a: uuid.UUID, entity_b: uuid.UUID, max_hops: int = 3
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
                if self._memories:
                    best_entity = max(
                        self._memories.values(),
                        key=lambda s: TruthVectorService.calculate_score(s.truth_vector),
                    )
                    return service.take_snapshot(best_entity)
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
                "final_state": final_state.current_value if final_state else None,
            }
        except Exception as e:
            log.warning(f"Replay failed: {e}")
            return None

    def get_golden_thread(self, entity_id: uuid.UUID) -> Dict:
        """
        Get the complete causal chain for an entity.
        Returns full narrative of how this memory came to be.
        """
        from memory_thread.services.golden_thread import GoldenThreadService

        service = GoldenThreadService()
        result = service.trace(entity_id)
        return {
            "entity_id": str(entity_id),
            "narrative": result.narrative,
            "events": [e.__dict__ for e in result.events],
            "current_truth": result.current_truth,
            "is_consistent": result.is_consistent,
            "related_paths": result.related_paths,
        }

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
        low_truth = sum(
            1
            for s in self._memories.values()
            if TruthVectorService.calculate_score(s.truth_vector) < 0.3
        )
        stale = sum(1 for s in self._memories.values() if s.truth_vector.freshness < 0.2)

        stats.update(
            {
                "low_truth_memories": low_truth,
                "stale_memories": stale,
                "health_score": 1.0 - (low_truth + stale) / max(len(self._memories), 1),
            }
        )

        return stats

    # =========================================================================
    # LLM INTEGRATION
    # =========================================================================

    def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        use_local: bool = True,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Chat with memory-augmented LLM.

        Uses Qdrant semantic recall to find relevant memories/code chunks.

        Args:
            user_message: User's input
            system_prompt: Optional system prompt
            use_local: If True, use local SmolLM. If False, use cloud API.
            provider: Explicit provider ('ollama', 'groq', 'openrouter', etc.)
            model: Specific model to use (e.g. 'deepseek-r1')

        Returns:
            LLM response with memory context
        """
        # 1. Check for contradictions first
        contradiction = self.check_contradiction(user_message)
        contradiction_note = ""
        if contradiction.get("has_contradiction"):
            contradiction_note = (
                f"\n[Note: User previously said: {contradiction.get('conflicting_memory', '')}]"
            )

        # 2. Semantic recall from Qdrant — finds relevant code chunks, facts, etc.
        context = self.get_context_for_llm(
            query=user_message,
            max_tokens=1000,  # ~4000 chars — enough for code context
            include_scores=True,
        )

        # 3. Store the message only after confirming it's worth storing
        if not contradiction.get("has_contradiction"):
            self.remember(user_message, source="user")

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

        # 5. Generate response
        # Priority: provider argument > use_local flag
        if provider == "ollama":
            response = self._generate_ollama(full_prompt, model=model)
        elif use_local and not provider:
            response = self._generate_local(full_prompt)
        else:
            # Pass provider/model down to cloud generator if applicable
            response = self._generate_cloud(full_prompt, provider=provider or "auto")

        # 6. Remember agent response (lower authority)
        self.remember(response, source="agent", confidence=0.7, authority=0.5)

        return response

    def _generate_local(self, prompt: str) -> str:
        """Generate response using local SmolLM."""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            # Lazy load model
            if not hasattr(self, "_llm_model"):
                log.info("Loading SmolLM-135M...")
                self._llm_tokenizer = AutoTokenizer.from_pretrained(
                    "HuggingFaceTB/SmolLM-135M-Instruct"
                )
                self._llm_model = AutoModelForCausalLM.from_pretrained(
                    "HuggingFaceTB/SmolLM-135M-Instruct", torch_dtype=torch.float32
                )
                log.info("SmolLM loaded")

            inputs = self._llm_tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=512
            )

            with torch.no_grad():
                outputs = self._llm_model.generate(
                    **inputs,
                    max_new_tokens=150,
                    do_sample=True,
                    temperature=0.7,
                    pad_token_id=self._llm_tokenizer.eos_token_id,
                )

            response = self._llm_tokenizer.decode(outputs[0], skip_special_tokens=True)
            # Extract only the assistant's response
            if "Assistant:" in response:
                response = response.split("Assistant:")[-1].strip()

            return response

        except Exception as e:
            log.error(f"Local generation failed: {e}")
            return (
                f"[Memory context retrieved, but local LLM unavailable. Context: {prompt[:200]}...]"
            )

    def _generate_cloud(self, prompt: str, provider: str = "auto") -> str:
        """
        Generate response using cloud API.

        Providers:
            - "groq": Uses GROQ_MODEL (default: llama-3.1-70b-versatile)
            - "openrouter": Uses OPENROUTER_MODEL (default: meta-llama/llama-3.1-405b-instruct)
            - "auto": Try Groq first, then OpenRouter, then local

        Set via environment variables:
            - GROQ_API_KEY, GROQ_MODEL
            - OPENROUTER_API_KEY, OPENROUTER_MODEL
        """
        try:
            import os
            import requests

            groq_key = os.environ.get("GROQ_API_KEY")
            groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            openrouter_key = os.environ.get("OPENROUTER_API_KEY")
            openrouter_model = os.environ.get(
                "OPENROUTER_MODEL", "meta-llama/llama-3.1-405b-instruct"
            )

            # Provider selection
            if provider == "groq" or (provider == "auto" and groq_key):
                if groq_key:
                    log.info(f"Using Groq ({groq_model})")
                    response = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        json={
                            "model": groq_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 500,
                            "temperature": 0.7,
                        },
                        timeout=30,
                    )
                    if response.ok:
                        return response.json()["choices"][0]["message"]["content"]
                    else:
                        log.warning(f"Groq error: {response.status_code} - {response.text[:100]}")

            # Try OpenRouter
            if provider == "openrouter" or (provider == "auto" and openrouter_key):
                if openrouter_key:
                    log.info(f"Using OpenRouter ({openrouter_model})")
                    response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "HTTP-Referer": "https://github.com/badalraj9/MemoryThread",
                            "X-Title": "MemoryThread",
                        },
                        json={
                            "model": openrouter_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 500,
                            "temperature": 0.7,
                        },
                        timeout=60,
                    )
                    if response.ok:
                        return response.json()["choices"][0]["message"]["content"]
                    else:
                        log.warning(
                            f"OpenRouter error: {response.status_code} - {response.text[:100]}"
                        )

            # Fallback to local
            log.warning("No cloud API available, falling back to local model")
            return self._generate_local(prompt)

        except Exception as e:
            log.error(f"Cloud generation failed: {e}")
            return self._generate_local(prompt)

    def list_ollama_models(self) -> List[str]:
        """
        Fetch available models from local Ollama instance.

        Returns:
            List of model names (e.g. ['deepseek-r1:latest', 'llama3:latest'])
        """
        import os
        import requests

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        try:
            response = requests.get(f"{host}/api/tags", timeout=5)
            if response.ok:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
            return []
        except Exception as e:
            log.warning(f"Failed to list Ollama models: {e}")
            return []

    def _generate_ollama(self, prompt: str, model: str = None) -> str:
        """
        Generate response using local Ollama instance.
        """
        import os
        import requests
        import json

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        # Default to deepseek-r1 if not specified, or fallback to environment variable
        model = model or os.environ.get("OLLAMA_MODEL", "deepseek-r1")

        try:
            log.info(f"Using Ollama ({model})")

            # Streaming is supported but for SDK simple usage we use non-streaming
            response = requests.post(
                f"{host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_ctx": 4096},
                },
                timeout=120,
            )

            if response.ok:
                return response.json().get("response", "").strip()
            else:
                log.warning(f"Ollama error: {response.status_code} - {response.text[:100]}")
                return f"[Error: Ollama generation failed using {model}]"

        except Exception as e:
            log.error(f"Ollama generation failed: {e}")
            return f"[Error: Could not connect to Ollama at {host}]"

    # ========== GALAXY SCHEMA METHODS (Layer 3) ==========

    def ingest_fact(
        self,
        content: str,
        source_uri: str = None,
        content_type: str = "text",
        metadata: dict = None,
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
                content=content, source_uri=source_uri, content_type=content_type, metadata=metadata
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
        metadata: dict = None,
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
                metadata=metadata,
            )
        except Exception as e:
            log.error(f"Belief derivation failed: {e}")
            # Fallback: just remember the belief
            entity_id = self.remember(belief, source="agent", memory_type="belief")
            return str(entity_id)

    def query_galaxy(self, operation: str, **kwargs):
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
                    top_k=kwargs.get("top_k", 10),
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
