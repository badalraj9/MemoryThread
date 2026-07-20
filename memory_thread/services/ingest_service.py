import multiprocessing as mp
import time
import struct
import json
import uuid
import datetime
from typing import List, Union, Dict, Any
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.models.events import Event, EntityState, ActorEnum, ActionEnum
from memory_thread.services.classify_service import classify_memory, get_decay_rate
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.utils.logger import get_logger
from memory_thread.utils.shared_cache import result_cache
from memory_thread.nervous.persistence_engine import PersistenceEngine

log = get_logger(__name__)


def json_serial(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Type {type(obj)} not serializable")


def _resolve_namespace() -> str:
    """Resolve namespace from environment or project config."""
    import os
    from pathlib import Path

    mt_namespace = os.environ.get("MT_NAMESPACE")
    if mt_namespace:
        return mt_namespace

    config_path = Path(".mt") / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
                return config.get("namespace", "default")
        except Exception:
            pass

    return "default"


def worker_process(allocator: SlabAllocator, persistence_engine: Any):
    from memory_thread.nervous.queue_manager import QueueManager

    qm = QueueManager(address="ipc://persistence_pipe")
    qm.setup_producer()

    log.info("Worker process started.")

    tms_service = TMSService()
    meta_service = MetaStabilityService()
    current_namespace = _resolve_namespace()

    while True:
        slab = allocator.get_written_slab()
        if slab:
            try:
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]
                raw_data = slab.memory[4 : 4 + msg_len].tobytes()

                content_obj = {}
                text = ""

                if raw_data.startswith(b"{"):
                    try:
                        content_obj = json.loads(raw_data)
                        text = content_obj.get("content", "")
                    except json.JSONDecodeError:
                        text = raw_data.decode("utf-8")
                else:
                    text = raw_data.decode("utf-8")

                memory_type, confidence, has_negation = classify_memory(text)
                decay_rate = get_decay_rate(memory_type)

                if "action" in content_obj and "delta" in content_obj:
                    action = ActionEnum[content_obj.get("action", "UPDATE")]
                    delta = content_obj.get("delta", {})
                    object_id_str = content_obj.get("object_id")
                    object_id = uuid.UUID(object_id_str) if object_id_str else uuid.uuid4()
                else:
                    action = ActionEnum.UPDATE
                    delta = {"content": text, "type": memory_type}
                    object_id = uuid.uuid4()

                existing_state = tms_service.get_current_state(object_id)

                if existing_state:
                    current_state = existing_state
                else:
                    current_state = EntityState(
                        entity_id=object_id,
                        namespace=current_namespace,
                        current_value={},
                        last_event_id=uuid.uuid4(),
                    )

                if meta_service.check_contradiction(current_state, delta):
                    log.warning(f"Contradiction detected for entity {object_id}")
                    _log_contradiction(current_namespace, object_id, delta)

                event = tms_service.create_event(
                    actor=ActorEnum.USER,
                    action=action,
                    object_id=object_id,
                    delta=delta,
                    namespace=current_namespace,
                    confidence=confidence,
                    authority=0.8,
                )

                new_state = StateDerivationService.apply_event(current_state, event)

                if not meta_service.check_integrity(new_state):
                    log.error("State integrity check failed!")

                output_payload = {
                    "event": event.dict(),
                    "state": new_state.dict(),
                    "original_text": text,
                    "memory_type": memory_type,
                    "decay_rate": decay_rate,
                }

                qm.send(json.loads(json.dumps(output_payload, default=json_serial)))

                allocator.release_slab(slab.slab_id)
            except Exception as e:
                log.error(
                    f"Error processing slab {slab.slab_id}: {e}",
                    exc_info=True,
                    extra={"slab_id": slab.slab_id, "error_type": type(e).__name__},
                )
                _log_failed_ingestion(slab, str(e), current_namespace)
                allocator.release_slab(slab.slab_id)
        else:
            time.sleep(0.001)

    qm.close()


def _log_contradiction(namespace: str, object_id: uuid.UUID, delta: Dict):
    """Log contradiction to database."""
    try:
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS contradictions (
                    id SERIAL PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    object_id UUID NOT NULL,
                    delta JSONB NOT NULL,
                    logged_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute(
                """
                INSERT INTO contradictions (namespace, object_id, delta)
                VALUES (%s, %s, %s)
            """,
                (namespace, str(object_id), json.dumps(delta)),
            )
    except Exception as e:
        log.warning(f"Failed to log contradiction: {e}")


def _log_failed_ingestion(slab, error: str, namespace: str):
    """Log failed ingestion to database for debugging."""
    try:
        from memory_thread.db.postgres_client import PostgresClient

        pg = PostgresClient()
        with pg.get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS failed_ingestions (
                    id SERIAL PRIMARY KEY,
                    namespace TEXT,
                    slab_id INTEGER,
                    error TEXT,
                    content BYTEA,
                    logged_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute(
                """
                INSERT INTO failed_ingestions (namespace, slab_id, error, content)
                VALUES (%s, %s, %s, %s)
            """,
                (
                    namespace,
                    getattr(slab, "slab_id", None),
                    error,
                    slab.memory.tobytes() if hasattr(slab, "memory") else None,
                ),
            )
    except Exception as e:
        log.warning(f"Failed to log failed ingestion: {e}")


class IngestionService:
    def __init__(self, num_slabs=128, slab_size=65536):
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.workers = []
        self.persistence_engine = PersistenceEngine()

    def start(self):
        self.persistence_engine.start()

        for p in self.workers:
            if p.is_alive():
                p.terminate()
        self.workers = []

        for _ in range(max(1, mp.cpu_count() - 2)):
            p = mp.Process(target=worker_process, args=(self.allocator, None))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_texts(self, texts: List[Union[str, Dict]]):
        import hashlib

        for item in texts:
            if isinstance(item, dict):
                text_content = str(item)
                encoded_data = json.dumps(item, default=json_serial).encode("utf-8")
            else:
                text_content = item
                encoded_data = item.encode("utf-8")

            text_hash = hashlib.sha256(text_content.encode()).hexdigest()

            msg_len = len(encoded_data)
            if msg_len + 4 > self.allocator.slab_size:
                continue

            slab = self.allocator.reserve_slab()
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4 : 4 + msg_len] = encoded_data
            self.allocator.mark_as_written(slab.slab_id)

    def shutdown(self):
        log.info("Shutdown initiated...")

        self.persistence_engine.stop()

        for p in self.workers:
            p.terminate()
            p.join()

        self.allocator.unlink()
        log.info("Ingestion Service Shutdown Complete.")


ingestion_service = IngestionService()
