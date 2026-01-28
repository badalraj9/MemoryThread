import multiprocessing as mp
import time
import struct
import json
import uuid
import datetime
from typing import List, Union, Dict, Any
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.services.hybrid_ner_service import extract_entities
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.models.events import Event, EntityState, ActorEnum, ActionEnum
from memory_thread.services.classify_service import classify_memory
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.utils.logger import get_logger
from memory_thread.utils.shared_cache import result_cache
from memory_thread.nervous.persistence_engine import PersistenceEngine

log = get_logger(__name__)

# Function to handle JSON serialization for non-standard types
def json_serial(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, "dict"): # Pydantic models
        return obj.dict()
    raise TypeError(f"Type {type(obj)} not serializable")

def worker_process(allocator: SlabAllocator, persistence_engine: Any): # Note: passing engine requires proxy or pickling strategy, using direct ZMQ push if possible
    # Actually, passing PersistenceEngine object to process might be tricky if it has open sockets/files.
    # Ideally, worker just needs the ZMQ socket or a Queue wrapper that writes to ZMQ.
    # Here, we will reconstruct a QueueManager producer in the worker.

    from memory_thread.nervous.queue_manager import QueueManager
    qm = QueueManager(address="ipc://persistence_pipe")
    qm.setup_producer()

    log.info("Worker process started.")

    tms_service = TMSService()
    meta_service = MetaStabilityService()

    while True:
        slab = allocator.get_written_slab()
        if slab:
            try:
                # 1. READ (Length-Header Protocol)
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]
                raw_data = slab.memory[4:4+msg_len].tobytes()

                content_obj = {}
                text = ""

                if raw_data.startswith(b'{'):
                    try:
                        content_obj = json.loads(raw_data)
                        text = content_obj.get("content", "")
                    except json.JSONDecodeError:
                        text = raw_data.decode('utf-8')
                else:
                    text = raw_data.decode('utf-8')

                # 2. META-STABILITY CHECK (Layer 0)
                if meta_service.check_drift(text, domain="general"):
                    log.warning("Drift detected, quarantining event.")

                # 3. TMS PIPELINE (Layer 1 -> Layer 2)
                if "action" in content_obj and "delta" in content_obj:
                    action = ActionEnum[content_obj.get("action", "UPDATE")]
                    delta = content_obj.get("delta", {})
                    object_id_str = content_obj.get("object_id")
                    object_id = uuid.UUID(object_id_str) if object_id_str else uuid.uuid4()
                else:
                    action = ActionEnum.UPDATE
                    delta = {"content": text}
                    object_id = uuid.uuid4()

                event = tms_service.create_event(
                    actor=ActorEnum.USER,
                    action=action,
                    object_id=object_id,
                    delta=delta
                )

                current_state = EntityState(
                    entity_id=object_id,
                    namespace="user",
                    current_value={},
                    truth_vector=event.truth_vector,
                    last_event_id=uuid.uuid4()
                )

                new_state = StateDerivationService.apply_event(current_state, event)

                if not meta_service.check_integrity(new_state):
                    log.error("State integrity check failed!")

                # 4. OUTPUT TO ZMQ (Q2 -> Q3)
                output_payload = {
                    "event": event.dict(),
                    "state": new_state.dict(),
                    "original_text": text
                }

                # Serialize properly for ZMQ
                qm.send(json.loads(json.dumps(output_payload, default=json_serial)))

                allocator.release_slab(slab.slab_id)
            except Exception as e:
                log.error(
                    f"Error processing slab {slab.slab_id}: {e}",
                    exc_info=True,
                    extra={
                        "slab_id": slab.slab_id,
                        "error_type": type(e).__name__
                    }
                )
                # Track for potential retry/dead-letter handling
                # In production: implement retry queue or DLQ persistence
                allocator.release_slab(slab.slab_id)
        else:
            time.sleep(0.001)

    qm.close()

class IngestionService:
    def __init__(self, num_slabs=128, slab_size=65536):
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self.workers = []
        # Phase 3.5: Use Persistence Engine instead of mp.Queue writer
        self.persistence_engine = PersistenceEngine()

    def start(self):
        self.persistence_engine.start()

        for p in self.workers:
            if p.is_alive(): p.terminate()
        self.workers = []

        for _ in range(max(1, mp.cpu_count() - 2)):
            # Workers self-initialize ZMQ producers
            p = mp.Process(target=worker_process, args=(self.allocator, None))
            p.start()
            self.workers.append(p)
        log.info(f"Started {len(self.workers)} worker processes.")

    def ingest_texts(self, texts: List[Union[str, Dict]]):
        import hashlib
        for item in texts:
            if isinstance(item, dict):
                text_content = str(item)
                encoded_data = json.dumps(item, default=json_serial).encode('utf-8')
            else:
                text_content = item
                encoded_data = item.encode('utf-8')

            text_hash = hashlib.sha256(text_content.encode()).hexdigest()

            msg_len = len(encoded_data)
            if msg_len + 4 > self.allocator.slab_size:
                continue

            slab = self.allocator.reserve_slab()
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4:4+msg_len] = encoded_data
            self.allocator.mark_as_written(slab.slab_id)

    def shutdown(self):
        log.info("Shutdown initiated...")

        # 1. Stop accepting new requests (implicitly done by stopping app logic calling ingest)

        # 2. Flush workers
        # Wait for workers to finish current slabs?
        # Slabs are guarded by semaphores.

        # 3. Stop Persistence Engine (It will finish its buffer)
        self.persistence_engine.stop()

        for p in self.workers:
            p.terminate()
            p.join()

        self.allocator.unlink()
        log.info("Ingestion Service Shutdown Complete.")

# Global instance
ingestion_service = IngestionService()
