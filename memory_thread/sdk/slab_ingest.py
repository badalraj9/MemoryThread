import uuid
import json
import struct
import threading
import time
import gc
from typing import Optional, Dict, Any, Callable, List
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class SlabIngestPipeline:
    """Single-process slab-backed ingest path with batched background draining."""

    def __init__(
        self,
        remember_fn: Callable,
        namespace: str,
        slab_process_hook: Optional[Callable] = None,
        num_slabs: int = 512,
        slab_size: int = 65536,
        drain_threads: int = 4,
        drain_batch_size: int = 32,
    ):
        from memory_thread.utils.shared_memory import SlabAllocator

        self._remember_fn = remember_fn
        self._namespace = namespace
        self._slab_process_hook = slab_process_hook
        self.allocator = SlabAllocator(num_slabs=num_slabs, slab_size=slab_size)
        self._stop_event = threading.Event()
        self._drain_threads = max(1, drain_threads)
        self._drain_batch_size = max(1, drain_batch_size)
        self._threads = [
            threading.Thread(
                target=self._drain_loop,
                name=f"mt-slab-ingest-{namespace}-{index}",
                daemon=True,
            )
            for index in range(self._drain_threads)
        ]
        self._accepted_count = 0
        self._processed_count = 0
        self._lock = threading.Lock()
        for thread in self._threads:
            thread.start()

    def enqueue(self, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        msg_len = len(encoded)
        if msg_len + 4 > self.allocator.slab_size:
            raise ValueError("Slab payload exceeds slab size")

        slab = self.allocator.reserve_slab(timeout=1.0)
        try:
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4 : 4 + msg_len] = encoded
            self.allocator.mark_as_written(slab.slab_id)
        finally:
            slab.memory.release()

        with self._lock:
            self._accepted_count += 1

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "accepted_count": self._accepted_count,
                "processed_count": self._processed_count,
                "drain_threads": self._drain_threads,
                "drain_batch_size": self._drain_batch_size,
            }

    def close(self) -> Dict[str, int]:
        self._stop_event.set()
        for _ in range(self._drain_threads):
            self.allocator.written_semaphore.release()
        for thread in self._threads:
            thread.join()
        final_stats = self.stats()
        gc.collect()
        self.allocator.close()
        self.allocator.unlink()
        return final_stats

    def _drain_loop(self) -> None:
        wal = None
        try:
            from memory_thread.services.wal import get_wal

            wal = get_wal(self._namespace)
        except Exception as e:
            log.warning(f"Slab ingest WAL unavailable: {e}")

        while True:
            try:
                slabs = self.allocator.get_written_slabs_batch_blocking(
                    max_count=self._drain_batch_size,
                    timeout=0.1,
                )
            except RuntimeError:
                if self._stop_event.is_set():
                    break
                raise
            if not slabs:
                if self._stop_event.is_set():
                    break
                continue

            decoded_batch = []
            for slab in slabs:
                msg_len = struct.unpack("!I", slab.memory[:4].tobytes())[0]
                payload = json.loads(slab.memory[4 : 4 + msg_len].tobytes())
                decoded_batch.append((slab, payload))

            wal_sequences: List[Optional[int]] = [None] * len(decoded_batch)
            if wal is not None:
                try:
                    wal_payloads = [
                        {
                            "entity_id": payload["entity_id"],
                            "content": payload["content"],
                            "source": payload["source"],
                            "confidence": payload["confidence"],
                            "authority": payload["authority"],
                            "memory_type": payload["memory_type"],
                        }
                        for _, payload in decoded_batch
                    ]
                    wal_sequences = wal.append_many("remember", wal_payloads)
                except Exception as e:
                    log.warning(f"Slab ingest WAL batch append failed: {e}")
                    wal_sequences = [None] * len(decoded_batch)

            released_ids = []
            committed_sequences: List[int] = []
            try:
                for (slab, payload), wal_seq in zip(decoded_batch, wal_sequences):
                    try:
                        if self._slab_process_hook:
                            self._slab_process_hook(payload["content"])
                        self._remember_fn(
                            content=payload["content"],
                            source=payload["source"],
                            confidence=payload["confidence"],
                            authority=payload["authority"],
                            memory_type=payload["memory_type"],
                            entity_id=uuid.UUID(payload["entity_id"]),
                            wal_seq=wal_seq,
                            wal_prewritten=wal_seq is not None,
                        )
                        if wal_seq is not None:
                            committed_sequences.append(wal_seq)
                        released_ids.append(slab.slab_id)
                    except Exception as e:
                        log.warning(f"Slab ingest item processing failed: {e}")
                    finally:
                        slab.memory.release()
                if wal is not None and committed_sequences:
                    try:
                        wal.commit_many(committed_sequences)
                    except Exception as e:
                        log.warning(f"Slab ingest WAL batch commit failed: {e}")
                with self._lock:
                    self._processed_count += len(released_ids)
            finally:
                if released_ids:
                    self.allocator.release_slabs_batch(released_ids)
