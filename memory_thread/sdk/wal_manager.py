"""WalManager — Write-Ahead Log lifecycle for MemoryClient."""

import time
import logging
from typing import Optional

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class WalManager:
    """WAL lifecycle: prewrite, append-committed, commit, replay, close."""

    def __init__(
        self, namespace: str, durability_mode: str, flush_batch_size: int, flush_interval_ms: int
    ):
        from memory_thread.services.wal import get_wal

        self.namespace = namespace
        self.durability_mode = durability_mode
        self._wal = get_wal(
            namespace,
            flush_batch_size=flush_batch_size,
            flush_interval_ms=flush_interval_ms,
            async_flush=durability_mode == "batched",
        )

    # ── Write path ─────────────────────────────────────────────────────

    def _publish(self, event_type: str, **data):
        try:
            from memory_thread.services.event_bus import event_bus

            event_bus.publish_sync(event_type, data)
        except Exception:
            pass

    def prewrite(
        self,
        entity_id,
        event_id,
        content,
        source,
        confidence,
        authority,
        memory_type,
        wal_seq,
        wal_prewritten,
        record_metric=None,
    ):
        if wal_prewritten:
            return wal_seq

        started = time.perf_counter()
        wal_seq = None
        try:
            wal_seq = self._wal.append(
                "remember",
                {
                    "entity_id": str(entity_id),
                    "event_id": str(event_id),
                    "content": content,
                    "source": source,
                    "confidence": confidence,
                    "authority": authority,
                    "memory_type": memory_type,
                },
            )
            self._publish(
                "wal_append",
                operation="remember",
                sequence=wal_seq,
                entity_id=str(entity_id),
                namespace=self.namespace,
            )
        except Exception as e:
            log.warning(f"WAL unavailable: {e}")
        finally:
            if record_metric:
                record_metric("remember.wal_prewrite", started)
        return wal_seq

    def append_committed(
        self, entity_id, content, source, confidence, authority, memory_type, record_metric=None
    ):
        started = time.perf_counter()
        wal_seq = None
        try:
            wal_seq = self._wal.append_committed(
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
            if wal_seq is not None:
                self._publish(
                    "wal_append_committed",
                    operation="remember",
                    sequence=wal_seq,
                    entity_id=str(entity_id),
                    namespace=self.namespace,
                )
        except Exception as e:
            log.warning(f"WAL append committed failed: {e}")
        finally:
            if record_metric:
                record_metric("remember.wal_append_committed", started)
        return wal_seq

    def commit(self, wal_seq, wal_prewritten, record_metric=None):
        if wal_seq is None or wal_prewritten:
            return
        started = time.perf_counter()
        try:
            self._wal.commit(wal_seq)
            self._publish(
                "wal_commit",
                sequence=wal_seq,
                namespace=self.namespace,
            )
        except Exception as e:
            log.warning(f"WAL commit failed: {e}")
        finally:
            if record_metric:
                record_metric("remember.wal_commit", started)

    # ── Replay path ────────────────────────────────────────────────────

    def get_uncommitted(self) -> list:
        if self._wal is None:
            return []
        return self._wal.get_uncommitted()

    def commit_sequence(self, sequence: int) -> None:
        if self._wal is not None:
            self._wal.commit(sequence)
            self._publish(
                "wal_commit",
                sequence=sequence,
                namespace=self.namespace,
            )

    # ── Lifecycle ──────────────────────────────────────────────────────

    def flush(self):
        if self._wal is not None:
            self._wal.flush()

    def compact(self):
        if self._wal is not None:
            self._wal.compact()

    def close(self, compact: bool = False):
        if self._wal is not None:
            from memory_thread.services.wal import close_wal

            close_wal(self.namespace, compact=compact)
            self._wal = None

    def get_stats(self) -> dict:
        if self._wal is not None:
            return self._wal.stats()
        return {}
