"""
Memory Thread SDK - MemoryClient

Usage:
    from memory_thread.sdk import MemoryClient

    mt = MemoryClient()
    mt.remember("User prefers dark mode")
    memories = mt.recall("user preferences")
"""

import uuid
import json
import threading
import time
import queue
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs
import os

from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.services.tms_service import (
    TMSService,
    TruthVectorService,
    StateDerivationService,
)
from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger
from memory_thread.sdk.models import Memory, RecallResult, WritePathMetric, ConnectionConfig
from memory_thread.sdk.wal_manager import WalManager
from memory_thread.sdk.persistence import PersistenceService
from memory_thread.sdk.enrichment import EnrichmentPipeline

log = get_logger(__name__)


def _get_write_path_metric_buffer(thread_local, buffers, lock):
    buffer = getattr(thread_local, "buffer", None)
    if buffer is None:
        buffer = {}
        thread_local.buffer = buffer
        with lock:
            buffers.append(buffer)
    return buffer


def _aggregate_write_path_metrics(buffers, lock):
    aggregated = {}
    with lock:
        buffers_copy = list(buffers)
    for buffer in buffers_copy:
        for stage, metric in buffer.items():
            target = aggregated.setdefault(stage, WritePathMetric())
            target.calls += metric.calls
            target.total_ms += metric.total_ms
            target.max_ms = max(target.max_ms, metric.max_ms)
    return aggregated


class MemoryClient:
    """Production SDK for Memory Thread."""

    @classmethod
    def connect(
        cls, url: str, use_db: bool = True, default_authority: float = 0.5
    ) -> "MemoryClient":
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
        mt_url = os.environ.get("MT_URL")
        if not mt_url:
            raise ValueError("MT_URL environment variable not set")
        return cls.connect(mt_url)

    def __init__(
        self,
        namespace: Optional[str] = None,
        use_db: bool = False,
        default_authority: float = 0.5,
        durability_mode: Optional[str] = None,
        wal_flush_batch_size: Optional[int] = None,
        wal_flush_interval_ms: Optional[int] = None,
        enable_write_metrics: Optional[bool] = None,
    ):
        if namespace is None:
            namespace = self._resolve_namespace()

        self.namespace = namespace
        self.tms = TMSService()
        self.use_db = use_db
        self.default_authority = min(1.0, max(0.0, default_authority))
        self.durability_mode = durability_mode or settings.WAL_DURABILITY_MODE
        if self.durability_mode not in {"sync", "batched"}:
            raise ValueError("durability_mode must be 'sync' or 'batched'")
        self.wal_flush_batch_size = wal_flush_batch_size or settings.WAL_FLUSH_BATCH_SIZE
        self.wal_flush_interval_ms = wal_flush_interval_ms or settings.WAL_FLUSH_INTERVAL_MS
        self.enable_write_metrics = (
            settings.WRITE_PATH_METRICS_ENABLED
            if enable_write_metrics is None
            else enable_write_metrics
        )
        self.event_log_max = max(0, settings.MEMORY_CLIENT_EVENT_LOG_MAX)

        self._memories: Dict[uuid.UUID, EntityState] = {}
        self._global_memories: Dict[uuid.UUID, EntityState] = {}
        self._event_log: List[Event] = []
        self._write_path_metrics: Dict[str, WritePathMetric] = {}
        self._write_path_metric_buffers: List[Dict[str, WritePathMetric]] = [
            self._write_path_metrics
        ]
        self._write_path_metrics_lock = threading.Lock()
        self._write_path_metrics_local = threading.local()

        self._persistence = PersistenceService(self.namespace)
        self._wal_manager = WalManager(
            self.namespace,
            self.durability_mode,
            self.wal_flush_batch_size,
            self.wal_flush_interval_ms,
        )
        self._enrichment = EnrichmentPipeline(
            self.namespace,
            self._memories,
            self._persistence,
        )
        self._enrichment.start()

        from memory_thread.nervous.contradiction_worker import ContradictionWorker

        self._contradiction_worker = ContradictionWorker(self.namespace)
        self._contradiction_worker.start()

        self._pg = None
        self._sqlite = None
        self._recall_graph_fallback_count = 0

        if use_db:
            self._init_db_clients()
            self.load_from_db()

        self._replay_uncommitted()
        self._replay_pending_contradictions()

    def _replay_pending_contradictions(self):
        """Re-queue any contradiction checks that were pending at last crash."""
        if not hasattr(self, "_contradiction_worker"):
            return
        replayed = self._contradiction_worker.replay_pending()
        if replayed:
            log.info("Re-queued %d pending contradiction checks from audit log", replayed)

    def _resolve_namespace(self) -> str:
        import json
        from pathlib import Path

        mt_config_path = Path(".") / settings.MT_PROJECT_DIR / "config.json"
        if mt_config_path.exists():
            try:
                with open(mt_config_path) as f:
                    config = json.load(f)
                    if config.get("namespace"):
                        return config["namespace"]
            except Exception:
                pass

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

        return self._get_global_namespace()

    def _get_global_namespace(self) -> str:
        import json
        from pathlib import Path

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

    def _replay_uncommitted(self):
        entries = self._wal_manager.get_uncommitted()
        if not entries:
            return
        log.info("Replaying %d uncommitted WAL entries on startup", len(entries))
        from memory_thread.services.graph_engine import graph_engine

        for entry in entries:
            try:
                data = entry.data
                replay_entity_id = uuid.UUID(data["entity_id"])
                replay_event_id = (
                    uuid.UUID(data["event_id"]) if data.get("event_id") else uuid.uuid4()
                )
                replay_content = data.get("content", "")
                replay_source = data.get("source", "agent")
                replay_confidence = float(data.get("confidence", 0.8))
                replay_authority = float(data.get("authority", 0.5))
                replay_memory_type = data.get("memory_type", "fact")

                replay_event, replay_state = self._apply_memory_event(
                    entity_id=replay_entity_id,
                    content=replay_content,
                    source=replay_source,
                    confidence=replay_confidence,
                    authority=replay_authority,
                    memory_type=replay_memory_type,
                    event_id=replay_event_id,
                )
                self._persistence.save(
                    replay_entity_id,
                    replay_content,
                    replay_memory_type,
                    replay_state,
                    replay_event,
                )
                graph_engine.apply_event(replay_event)
                self._wal_manager.commit_sequence(entry.sequence)
                log.info("Replayed WAL entry %d for entity %s", entry.sequence, replay_entity_id)
            except Exception as e:
                log.error("Failed to replay WAL entry %d: %s", entry.sequence, e)

    def _init_db_clients(self):
        self._persistence.connect()
        self._pg = self._persistence.pg
        self._sqlite = self._persistence.sqlite
        self._db_type = self._persistence.db_type

        if self._pg:
            from memory_thread.services.graph_engine import graph_engine

            if not graph_engine.load_snapshot(settings.GRAPH_SNAPSHOT_PATH):
                graph_engine.rebuild(self._pg)

    def remember(
        self,
        content: str,
        source: str = "agent",
        confidence: float = 0.8,
        authority: float = 0.5,
        memory_type: str = "fact",
        entity_id: Optional[uuid.UUID] = None,
        thread_id: Optional[str] = None,
        antecedents: Optional[List[uuid.UUID]] = None,
        action: Optional[str] = None,
    ) -> uuid.UUID:
        return self._remember_direct(
            content=content,
            source=source,
            confidence=confidence,
            authority=authority,
            memory_type=memory_type,
            entity_id=entity_id,
            thread_id=thread_id,
            antecedents=antecedents or [],
            action=action,
        )

    def _remember_direct(
        self,
        content: str,
        source: str = "agent",
        confidence: float = 0.8,
        authority: float = 0.5,
        memory_type: str = "fact",
        entity_id: Optional[uuid.UUID] = None,
        wal_seq: Optional[int] = None,
        wal_prewritten: bool = False,
        thread_id: Optional[str] = None,
        antecedents: Optional[List[uuid.UUID]] = None,
        action: Optional[str] = None,
        event_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        overall_started = time.perf_counter()
        entity_id = entity_id or uuid.uuid4()
        event_id = event_id or uuid.uuid4()

        authority = self._normalize_authority(source, authority)
        if self.durability_mode != "batched" or wal_prewritten:
            wal_seq = self._wal_manager.prewrite(
                entity_id=entity_id,
                event_id=event_id,
                content=content,
                source=source,
                confidence=confidence,
                authority=authority,
                memory_type=memory_type,
                wal_seq=wal_seq,
                wal_prewritten=wal_prewritten,
                record_metric=self._record_write_path_metric,
            )

        event, state = self._apply_memory_event(
            entity_id=entity_id,
            content=content,
            source=source,
            confidence=confidence,
            authority=authority,
            memory_type=memory_type,
            thread_id=thread_id,
            antecedents=antecedents or [],
            action=action,
            event_id=event_id,
        )
        self._persistence.save(entity_id, content, memory_type, state, event)
        from memory_thread.services.graph_engine import graph_engine

        graph_engine.apply_event(event)

        if self.durability_mode == "batched" and not wal_prewritten:
            self._wal_manager.append_committed(
                entity_id=entity_id,
                content=content,
                source=source,
                confidence=confidence,
                authority=authority,
                memory_type=memory_type,
                record_metric=self._record_write_path_metric,
            )
        else:
            self._wal_manager.commit(
                wal_seq, wal_prewritten, record_metric=self._record_write_path_metric
            )
        self._enrichment.schedule(source, content, entity_id, event.id, memory_type, state)
        self._record_write_path_metric("remember.total", overall_started)

        return entity_id

    def _record_write_path_metric(self, stage: str, started_at: float) -> None:
        if not self.enable_write_metrics:
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        buffer = _get_write_path_metric_buffer(
            self._write_path_metrics_local,
            self._write_path_metric_buffers,
            self._write_path_metrics_lock,
        )
        metric = buffer.setdefault(stage, WritePathMetric())
        metric.calls += 1
        metric.total_ms += elapsed_ms
        metric.max_ms = max(metric.max_ms, elapsed_ms)

    def get_write_path_metrics(self) -> Dict[str, Dict[str, float]]:
        aggregated = _aggregate_write_path_metrics(
            self._write_path_metric_buffers,
            self._write_path_metrics_lock,
        )
        return {
            stage: {
                "calls": metric.calls,
                "total_ms": round(metric.total_ms, 3),
                "avg_ms": round(metric.total_ms / metric.calls, 3) if metric.calls else 0.0,
                "max_ms": round(metric.max_ms, 3),
            }
            for stage, metric in aggregated.items()
        }

    def reset_write_path_metrics(self) -> None:
        with self._write_path_metrics_lock:
            for buffer in self._write_path_metric_buffers:
                buffer.clear()

    def get_write_stats(self) -> Dict[str, Any]:
        stats = {
            "durability_mode": self.durability_mode,
            "wal_flush_batch_size": self.wal_flush_batch_size,
            "wal_flush_interval_ms": self.wal_flush_interval_ms,
            "write_metrics_enabled": self.enable_write_metrics,
        }
        stats.update(self._wal_manager.get_stats())
        return stats

    def flush(self) -> None:
        self._wal_manager.flush()

    def compact_wal(self) -> None:
        self._wal_manager.compact()

    def _normalize_authority(self, source: str, authority: float) -> float:
        started = time.perf_counter()
        if source == "user":
            authority = max(authority, 0.9)
        self._record_write_path_metric("remember.normalize_authority", started)
        return authority

    def _apply_memory_event(
        self,
        entity_id,
        content,
        source,
        confidence,
        authority,
        memory_type,
        thread_id=None,
        antecedents=None,
        action=None,
        event_id=None,
    ):
        started = time.perf_counter()
        truth_vector = TruthVector.model_construct(
            confidence=confidence, authority=authority, freshness=1.0, corroboration=0
        )
        actor = ActorEnum.USER if source == "user" else ActorEnum.AGENT
        event_id = event_id or uuid.uuid4()
        if action is None:
            action = ActionEnum.ADD if entity_id not in self._memories else ActionEnum.UPDATE
        elif isinstance(action, str):
            action = ActionEnum(action)
        delta = {"content": content, "type": memory_type, "namespace": self.namespace}
        tid = uuid.UUID(thread_id) if thread_id else None
        event = Event.model_construct(
            id=event_id,
            namespace=self.namespace,
            timestamp=datetime.utcnow(),
            actor=actor,
            action=action,
            object_id=entity_id,
            delta=delta,
            antecedents=antecedents or [],
            truth_vector=truth_vector,
            thread_id=tid,
        )
        self._event_log.append(event)
        if self.event_log_max and len(self._event_log) > self.event_log_max:
            del self._event_log[: max(1, self.event_log_max // 10)]

        state = self._memories.get(entity_id)
        if state is None:
            state = EntityState.model_construct(
                entity_id=entity_id,
                namespace=self.namespace,
                current_value=delta.copy(),
                truth_vector=TruthVector.model_construct(
                    confidence=0.5, authority=0.5, freshness=1.0, corroboration=0
                ),
                version=0,
                last_event_id=event_id,
                updated_at=datetime.utcnow(),
            )
        else:
            from memory_thread.services.meta_stability_service import MetaStabilityService

            meta = MetaStabilityService()
            has_conflict = meta.check_contradiction(state, delta)
            if has_conflict:
                delta["contradiction_detected"] = True
                log.info("Contradiction detected (tier 1 key-based) for entity %s", entity_id)

            self._contradiction_worker.schedule(
                entity_id=str(entity_id),
                event_id=str(event.id),
                existing_content=state.current_value.get("content", ""),
                new_content=content,
                source=source,
            )

            state.current_value.update(delta)

        previous_vector = state.truth_vector
        total_authority = previous_vector.authority + truth_vector.authority
        if total_authority == 0:
            previous_weight = 0.5
            event_weight = 0.5
        else:
            previous_weight = previous_vector.authority / total_authority
            event_weight = truth_vector.authority / total_authority

        state.truth_vector = TruthVector.model_construct(
            confidence=(
                previous_weight * previous_vector.confidence
                + event_weight * truth_vector.confidence
            ),
            authority=max(previous_vector.authority, truth_vector.authority),
            freshness=max(previous_vector.freshness, truth_vector.freshness),
            corroboration=previous_vector.corroboration + truth_vector.corroboration + 1,
        )
        state.version += 1
        state.last_event_id = event_id
        state.updated_at = datetime.utcnow()
        self._memories[entity_id] = state
        self._record_write_path_metric("remember.derive_state", started)
        return event, state

    def remember_in_thread(
        self,
        content,
        thread_id,
        source="agent",
        confidence=0.8,
        authority=0.5,
        memory_type="fact",
        entity_id=None,
    ):
        from memory_thread.services.graph_engine import graph_engine as ge

        if not ge._vertex_exists(thread_id):
            raise ValueError(f"Thread {thread_id} does not exist")

        entity_id = entity_id or uuid.uuid4()
        tv = TruthVector(
            confidence=confidence, authority=authority, freshness=1.0, corroboration=0.0
        )
        event = Event(
            actor=ActorEnum.USER if source == "user" else ActorEnum.AGENT,
            action=ActionEnum.ADD,
            object_id=entity_id,
            delta={"content": content, "type": memory_type, "source": source},
            truth_vector=tv,
            thread_id=uuid.UUID(thread_id) if isinstance(thread_id, str) else thread_id,
        )
        self._event_log.append(event)
        ge.apply_event(event)
        return entity_id

    def recall(
        self,
        query: str,
        top_k: int = 5,
        min_truth_score: float = 0.3,
        project: Optional[str] = None,
    ) -> RecallResult:
        if project:
            original_namespace = self.namespace
            self.namespace = project
            result = self._recall_impl(query, top_k, min_truth_score)
            self.namespace = original_namespace
            return result

        global_namespace = self._get_global_namespace()
        project_result = self._recall_impl(query, top_k, min_truth_score)

        if global_namespace != self.namespace:
            original_namespace = self.namespace
            self.namespace = global_namespace
            global_result = self._recall_impl(query, top_k, min_truth_score)
            self.namespace = original_namespace
            return self._merge_results(project_result, global_result, top_k)

        return project_result

    def create_thread(self, title: str, parent_thread_id: Optional[str] = None) -> str:
        from memory_thread.services.thread_service import thread_service

        thread = thread_service.create_thread(
            title, created_by=self.namespace, parent_thread_id=parent_thread_id
        )
        return thread.thread_id

    def get_thread(self, thread_id: str) -> Optional[Dict]:
        from memory_thread.services.thread_service import thread_service

        result = thread_service.get_thread(thread_id)
        if not result:
            return None
        return {
            "thread_id": result.thread.thread_id,
            "title": result.thread.title,
            "created_by": result.thread.created_by,
            "started_at": result.thread.started_at,
            "status": result.thread.status,
            "event_count": result.thread.event_count,
            "events": result.events,
            "child_threads": [
                {"thread_id": ct.thread_id, "title": ct.title, "created_by": ct.created_by}
                for ct in result.child_threads
            ],
        }

    def search_threads(self, query: str) -> List[Dict]:
        from memory_thread.services.thread_service import thread_service

        results = thread_service.search_threads(query)
        return [
            {
                "thread_id": t.thread_id,
                "title": t.title,
                "created_by": t.created_by,
                "started_at": t.started_at,
                "status": t.status,
            }
            for t in results
        ]

    def _recall_graph_primary(self, query, top_k=5, min_truth_score=0.3, max_depth=3, decay=0.5):
        """Graph-primary retrieval with keyword fallback. No global namespace merge."""
        from memory_thread.services.graph_engine import graph_engine
        from memory_thread.services.retrieval_service import retrieve_by_activation

        if graph_engine.graph.vcount() == 0:
            self._recall_graph_fallback_count += 1
            log.info("Graph recall fallback: graph empty")
            return self._recall_keyword(query, top_k, min_truth_score)

        seeds = self._resolve_seeds(query)
        if not seeds:
            self._recall_graph_fallback_count += 1
            log.info("Graph recall fallback: no seed nodes for '%s'", query)
            return self._recall_keyword(query, top_k, min_truth_score)

        activated = retrieve_by_activation(
            seeds=seeds,
            top_k=top_k,
            max_depth=max_depth,
            decay=decay,
            truth_threshold=min_truth_score,
        )

        memories = []
        for item in activated:
            memories.append(
                Memory(
                    content=item.get("content", item.get("id", "")),
                    entity_id=uuid.UUID(item["id"]) if isinstance(item["id"], str) else item["id"],
                    truth_score=item["score"],
                    confidence=item.get("truth_score", min_truth_score),
                    authority=item.get("truth_score", min_truth_score) * 0.9,
                    freshness=1.0,
                    corroboration=0,
                    timestamp=datetime.utcnow(),
                    source="graph",
                    memory_type="fact",
                )
            )

        if len(memories) < top_k:
            keyword_result = self._recall_keyword(
                query, top_k=top_k - len(memories), min_truth_score=min_truth_score
            )
            seen_ids = {str(m.entity_id) for m in memories}
            for mem in keyword_result.memories:
                if str(mem.entity_id) not in seen_ids:
                    memories.append(mem)
                    seen_ids.add(str(mem.entity_id))

        memories.sort(key=lambda m: (m.truth_score, m.authority), reverse=True)
        return RecallResult(memories=memories[:top_k], query=query, total_found=len(memories))

    def recall_graph(
        self, query, top_k=5, min_truth_score=0.3, max_depth=3, decay=0.5, project=None
    ):
        if project:
            original_namespace = self.namespace
            self.namespace = project
            result = self._recall_graph_primary(query, top_k, min_truth_score, max_depth, decay)
            self.namespace = original_namespace
            return result

        global_namespace = self._get_global_namespace()
        project_result = self._recall_graph_primary(query, top_k, min_truth_score, max_depth, decay)

        if global_namespace != self.namespace:
            original_namespace = self.namespace
            self.namespace = global_namespace
            global_result = self._recall_graph_primary(
                query, top_k, min_truth_score, max_depth, decay
            )
            self.namespace = original_namespace
            return self._merge_results(project_result, global_result, top_k)

        return project_result

    def _resolve_seeds(self, query: str) -> List[str]:
        from memory_thread.services.graph_engine import graph_engine

        seeds = []

        try:
            uid = uuid.UUID(query.strip())
            node = str(uid)
            if graph_engine._vertex_exists(node):
                seeds.append(node)
        except (ValueError, AttributeError):
            pass

        # Collect generous initial matches — filtering by namespace below
        matches = graph_engine.search_nodes(query, attr="content")
        seeds.extend(matches)

        name_matches = graph_engine.search_nodes(query, attr="name")
        seeds.extend(n for n in name_matches if n not in seeds)

        if not seeds and self._pg:
            try:
                rows = self._pg.search_events_fts(query, limit=5)
                for row in rows:
                    node = str(row["object_id"])
                    if graph_engine._vertex_exists(node):
                        seeds.append(node)
            except Exception:
                pass

        # Filter to current namespace — graph is shared, seeds must not leak across namespaces
        filtered = []
        for name in seeds:
            try:
                v = graph_engine.graph.vs.find(name=name)
                v_ns = v.attributes().get("namespace")
                if v_ns == self.namespace:
                    filtered.append(name)
            except (ValueError, KeyError):
                filtered.append(name)

        return list(set(filtered))[: settings.RECALL_GRAPH_MIN_SEEDS]

    def _recall_impl(self, query: str, top_k: int, min_truth_score: float) -> RecallResult:
        return self._recall_graph_primary(query, top_k, min_truth_score)

    def _merge_results(self, project_result, global_result, top_k):
        from memory_thread.config.settings import settings

        global_weight = getattr(settings, "GLOBAL_AUTHORITY_WEIGHT", 0.8)

        adjusted_global = []
        for mem in global_result.memories:
            adjusted_global.append(
                Memory(
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
            )

        all_memories = project_result.memories + adjusted_global
        all_memories.sort(key=lambda m: (m.truth_score, m.authority), reverse=True)

        return RecallResult(
            memories=all_memories[:top_k],
            query=project_result.query,
            total_found=len(all_memories),
        )

    def _include_shared_memories(self, memories: List[Memory]) -> List[Memory]:
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

    def _recall_keyword(self, query: str, top_k: int, min_truth_score: float) -> RecallResult:
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

        scored_memories.sort(key=lambda x: (x[1], x[0].authority), reverse=True)
        top_memories = [m for m, _ in scored_memories[:top_k]]
        return RecallResult(memories=top_memories, query=query, total_found=len(scored_memories))

    def forget(self, entity_id: uuid.UUID) -> bool:
        if entity_id in self._memories:
            state = self._memories[entity_id]
            state.truth_vector.freshness = 0.0
            self._persistence.delete(entity_id)
            return True
        return False

    def load_from_db(self) -> int:
        loaded = self._persistence.load_all(self.namespace)
        self._memories.update(loaded)
        count = len(loaded)
        self._load_shared_memories()
        return count

    def _load_shared_memories(self) -> int:
        from pathlib import Path

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

        mt_dir = git_root / settings.MT_PROJECT_DIR
        shared_memories_file = mt_dir / "shared_memories.json"

        if not shared_memories_file.exists():
            return 0

        count = 0
        try:
            with open(shared_memories_file) as f:
                shared_data = json.load(f)

            for mem_data in shared_data.get("memories", []):
                entity_id = uuid.UUID(mem_data["entity_id"])
                current_value = mem_data.get("current_value", {})
                tv_data = mem_data.get("truth_vector", {})
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
        total = len(self._memories)
        if total == 0:
            stats = {"total_memories": 0, "avg_truth_score": 0}
            if hasattr(self, "_db_type"):
                stats["db_type"] = self._db_type
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
        }
        return stats

    def close(self) -> None:
        self._enrichment.shutdown()
        self._contradiction_worker.shutdown()
        self._wal_manager.close(compact=settings.WAL_COMPACT_ON_CLOSE)

        from memory_thread.services.graph_engine import graph_engine

        graph_engine.snapshot(settings.GRAPH_SNAPSHOT_PATH)

    def clear(self):
        self._memories.clear()
        self._event_log.clear()

    def check_contradiction(self, content, entity_id=None):
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
        try:
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
        if entity_id in self._memories:
            return TruthVectorService.calculate_score(self._memories[entity_id].truth_vector)
        return None

    def add_relation(self, source_id, target_id, relation_type, confidence=0.9):
        try:
            from memory_thread.services.graph_service import GraphService

            graph = GraphService()
            graph.add_relation(source_id, target_id, relation_type, confidence)
            log.info(f"Relation added: {source_id} -[{relation_type}]-> {target_id}")
            return True
        except Exception as e:
            log.warning(f"Failed to add relation: {e}")
            return False

    def find_path(self, entity_a, entity_b, max_hops=3):
        try:
            from memory_thread.services.reasoning.query_engine import QueryEngine

            engine = QueryEngine()
            return engine.find_path(entity_a, entity_b, max_hops)
        except Exception as e:
            log.warning(f"Path finding failed: {e}")
            return None

    def get_related(self, entity_id, depth=1):
        try:
            from memory_thread.services.graph_service import GraphService

            graph = GraphService()
            return graph.get_relations(entity_id, direction="both")
        except Exception as e:
            log.warning(f"Failed to get related: {e}")
            return []

    def infer_relations(self, entity_id=None):
        try:
            from memory_thread.services.reasoning.inference_engine import InferenceEngine

            engine = InferenceEngine()

            if entity_id:
                engine.infer_transitive_relations(entity_id)
                return 1
            else:
                count = 0
                for eid in list(self._memories.keys()):
                    engine.infer_transitive_relations(eid)
                    count += 1
                return count
        except Exception as e:
            log.warning(f"Inference failed: {e}")
            return 0

    def hybrid_search(self, query: str, top_k: int = 10) -> List[Dict]:
        try:
            from memory_thread.services.retrieval_service import retrieve_memories

            return retrieve_memories(query, top_k)
        except Exception as e:
            log.warning(f"Hybrid search failed: {e}, falling back to recall")
            result = self.recall(query, top_k)
            return [m.to_dict() for m in result.memories]

    def take_snapshot(self, entity_id=None):
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
        try:
            from memory_thread.services.ancestry_cache import AncestryCache

            cache = AncestryCache()
            return cache.get_ancestry(entity_id)
        except Exception as e:
            log.warning(f"Provenance lookup failed: {e}")
            return [str(e.id) for e in self._event_log if e.object_id == entity_id]

    def replay_entity(self, entity_id: uuid.UUID) -> Optional[Dict]:
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

    def consolidate(self, entity_id=None, window_days=30):
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
        stats = self.get_stats()
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

    def ingest_fact(self, content, source_uri=None, content_type="text", metadata=None):
        try:
            from memory_thread.services.fact_store import fact_store

            return fact_store.store(
                content=content, source_uri=source_uri, content_type=content_type, metadata=metadata
            )
        except Exception as e:
            log.error(f"Fact ingestion failed: {e}")
            entity_id = self.remember(content, source="fact", memory_type="fact")
            return str(entity_id)

    def derive_belief(
        self, fact_id, belief, agent_id=None, confidence=0.8, authority=0.5, metadata=None
    ):
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
            entity_id = self.remember(belief, source="agent", memory_type="belief")
            return str(entity_id)

    def query_galaxy(self, operation: str, **kwargs):
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
            return self.recall(kwargs.get("query", ""), top_k=kwargs.get("top_k", 10))

    def get_galaxy_conflicts(self) -> list:
        try:
            from memory_thread.services.galaxy_query import galaxy_query

            return galaxy_query.get_conflicts()
        except Exception as e:
            log.error(f"Conflict detection failed: {e}")
            return []

    def galaxy_stats(self) -> dict:
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
