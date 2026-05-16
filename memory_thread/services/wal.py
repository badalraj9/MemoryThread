"""
Write-Ahead Log (WAL) for Memory Thread.

Provides crash-proof persistence by writing events to disk
BEFORE they're processed. On recovery, replays uncommitted events.

Architecture:
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │  remember() │───▶│  WAL.append │───▶│  fsync()    │
    └─────────────┘    └─────────────┘    └─────────────┘
                              │
                              ▼
                       ┌─────────────┐
                       │  .wal file  │  (crash-safe)
                       └─────────────┘
"""

import json
import os
import time
import threading
import atexit
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import uuid

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# WAL location
WAL_DIR = Path.home() / ".mt" / "wal"


@dataclass
class WALEntry:
    """A single WAL entry."""

    sequence: int
    timestamp: str
    operation: str  # "remember", "forget", "update"
    data: Dict[str, Any]
    checksum: str
    committed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WALEntry":
        return cls(**d)


class WriteAheadLog:
    """
    Append-only, crash-safe Write-Ahead Log.

    Guarantees:
    - Events are durably stored before acknowledgment
    - Crash recovery replays uncommitted events
    - No data loss on process crash

    Usage:
        wal = WriteAheadLog(namespace="myapp")
        seq = wal.append("remember", {"content": "user data"})
        # ... process the event ...
        wal.commit(seq)
    """

    def __init__(
        self,
        namespace: str = "default",
        flush_batch_size: int = 10,
        flush_interval_ms: int = 5,
        async_flush: bool = False,
    ):
        self.namespace = namespace
        self.wal_file = WAL_DIR / f"{namespace}.wal"
        self.lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._sequence = 0
        self._uncommitted: Dict[int, WALEntry] = {}
        self._active_buffer: List[str] = []
        self._flush_buffer: List[str] = []
        self._flush_batch_size = max(1, flush_batch_size)
        self._flush_interval_sec = max(0.001, flush_interval_ms / 1000.0)
        self._last_flush_at = time.perf_counter()
        self._stop_event = threading.Event()
        self._flush_event = threading.Event()
        self._async_flush = async_flush
        self._durable_append_count = 0
        self._durable_commit_count = 0
        self._compacted_count = 0

        self._ensure_dir()
        self._recover()
        if self._async_flush:
            self._flusher = threading.Thread(
                target=self._flush_loop,
                name=f"mt-wal-flusher-{namespace}",
                daemon=True,
            )
            self._flusher.start()

    def _ensure_dir(self):
        """Create WAL directory if needed."""
        WAL_DIR.mkdir(parents=True, exist_ok=True)

    def _checksum(self, data: str) -> str:
        """Simple checksum for integrity."""
        import hashlib

        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _entry_line(
        self,
        sequence: int,
        timestamp: str,
        operation: str,
        data: Dict[str, Any],
        checksum: str,
    ) -> str:
        return json.dumps(
            {
                "sequence": sequence,
                "timestamp": timestamp,
                "operation": operation,
                "data": data,
                "checksum": checksum,
                "committed": False,
            },
            default=str,
            separators=(",", ":"),
        )

    def _enqueue_line(self, line: str):
        self._enqueue_lines([line])

    def _enqueue_lines(self, lines: List[str]):
        if not lines:
            return

        with self.lock:
            self._active_buffer.extend(lines)
            buffered = len(self._active_buffer)
            last_flush_age = time.perf_counter() - self._last_flush_at

        if not self._async_flush:
            self.flush()
        elif buffered >= self._flush_batch_size or last_flush_age >= self._flush_interval_sec:
            self._flush_event.set()

    def _write_batch(self, lines: List[str]):
        if not lines:
            return

        try:
            with open(self.wal_file, "a", encoding="utf-8") as f:
                for line in lines:
                    f.write(line)
                    f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            log.error(f"WAL batch write failed: {e}")
            raise RuntimeError(f"WAL batch write failed: {e}")

    def _flush_loop(self):
        while not self._stop_event.is_set():
            self._flush_event.wait(self._flush_interval_sec)
            self._flush_event.clear()
            try:
                self.flush()
            except Exception:
                # Keep the flusher alive; foreground callers will surface errors.
                pass

    def flush(self):
        """Synchronously flush buffered WAL lines to disk as a single batch."""
        wait_for_inflight_only = False
        with self.lock:
            if not self._active_buffer and not self._flush_buffer:
                self._last_flush_at = time.perf_counter()
                wait_for_inflight_only = True

            if not wait_for_inflight_only and self._active_buffer:
                self._active_buffer, self._flush_buffer = self._flush_buffer, self._active_buffer
            lines = [] if wait_for_inflight_only else self._flush_buffer
            if not wait_for_inflight_only:
                self._flush_buffer = []

            append_lines = 0
            commit_lines = 0
            for line in lines:
                if '"type":"commit"' in line or '"type": "commit"' in line:
                    commit_lines += 1
                else:
                    append_lines += 1

        with self._io_lock:
            self._write_batch(lines)

        with self.lock:
            self._durable_append_count += append_lines
            self._durable_commit_count += commit_lines
            self._last_flush_at = time.perf_counter()

    def append(self, operation: str, data: Dict[str, Any]) -> int:
        """
        Append entry to WAL and sync to disk.

        Returns:
            Sequence number for this entry
        """
        with self.lock:
            self._sequence += 1
            seq = self._sequence
            timestamp = datetime.utcnow().isoformat()
            data_json = json.dumps(data, default=str, separators=(",", ":"))
            checksum = self._checksum(data_json)

            self._uncommitted[seq] = WALEntry(
                sequence=seq,
                timestamp=timestamp,
                operation=operation,
                data=data,
                checksum=checksum,
                committed=False,
            )
            log.debug(f"WAL append: seq={seq} op={operation}")

        self._enqueue_line(self._entry_line(seq, timestamp, operation, data, checksum))
        return seq

    def append_many(self, operation: str, payloads: List[Dict[str, Any]]) -> List[int]:
        """
        Append multiple entries and durably flush them as a single batch.

        Returns:
            Sequence numbers in the same order as payloads
        """
        if not payloads:
            return []

        sequences: List[int] = []
        lines: List[str] = []
        with self.lock:
            for data in payloads:
                self._sequence += 1
                seq = self._sequence
                timestamp = datetime.utcnow().isoformat()
                data_json = json.dumps(data, default=str, separators=(",", ":"))
                checksum = self._checksum(data_json)
                self._uncommitted[seq] = WALEntry(
                    sequence=seq,
                    timestamp=timestamp,
                    operation=operation,
                    data=data,
                    checksum=checksum,
                    committed=False,
                )
                sequences.append(seq)
                lines.append(self._entry_line(seq, timestamp, operation, data, checksum))

        self._enqueue_lines(lines)
        return sequences

    def append_committed(self, operation: str, data: Dict[str, Any]) -> int:
        """
        Append an entry and its commit marker into the same WAL buffer batch.

        This is intended for accepted-before-durable write paths where processing
        has already succeeded before the WAL batch is made durable.
        """
        with self.lock:
            self._sequence += 1
            seq = self._sequence
            timestamp = datetime.utcnow().isoformat()
            data_json = json.dumps(data, default=str, separators=(",", ":"))
            checksum = self._checksum(data_json)
            entry_line = self._entry_line(seq, timestamp, operation, data, checksum)
            commit_line = json.dumps(
                {
                    "type": "commit",
                    "sequence": seq,
                    "timestamp": timestamp,
                },
                separators=(",", ":"),
            )
            log.debug(f"WAL append committed: seq={seq} op={operation}")

        self._enqueue_lines([entry_line, commit_line])
        return seq

    def commit(self, sequence: int):
        """
        Mark entry as committed (successfully processed).

        Args:
            sequence: The sequence number from append()
        """
        commit_line = None
        with self.lock:
            if sequence in self._uncommitted:
                entry = self._uncommitted.pop(sequence)
                entry.committed = True

                log.debug(f"WAL commit: seq={sequence}")
                commit_line = json.dumps(
                    {
                        "type": "commit",
                        "sequence": sequence,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    separators=(",", ":"),
                )
        if commit_line is not None:
            self._enqueue_line(commit_line)

    def commit_many(self, sequences: List[int]):
        """Mark multiple entries as committed as a single durable batch."""
        if not sequences:
            return

        timestamp = datetime.utcnow().isoformat()
        commit_lines: List[str] = []
        with self.lock:
            for sequence in sequences:
                if sequence in self._uncommitted:
                    entry = self._uncommitted.pop(sequence)
                    entry.committed = True
                    log.debug(f"WAL commit: seq={sequence}")
                    commit_lines.append(
                        json.dumps(
                            {
                                "type": "commit",
                                "sequence": sequence,
                                "timestamp": timestamp,
                            },
                            separators=(",", ":"),
                        )
                    )
        if commit_lines:
            self._enqueue_lines(commit_lines)

    def rollback(self, sequence: int):
        """Mark entry as rolled back (failed processing)."""
        with self.lock:
            if sequence in self._uncommitted:
                del self._uncommitted[sequence]
                log.debug(f"WAL rollback: seq={sequence}")

    def _recover(self) -> List[WALEntry]:
        """
        Recover uncommitted entries after crash.

        Returns:
            List of uncommitted entries to replay
        """
        if not self.wal_file.exists():
            return []

        entries: Dict[int, WALEntry] = {}
        committed: set = set()

        try:
            with open(self.wal_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)

                        if record.get("type") == "commit":
                            committed.add(record["sequence"])
                        else:
                            entry = WALEntry.from_dict(record)
                            entries[entry.sequence] = entry
                            self._sequence = max(self._sequence, entry.sequence)
                    except json.JSONDecodeError:
                        log.warning(f"Corrupt WAL line: {line[:50]}...")

        except Exception as e:
            log.error(f"WAL recovery failed: {e}")
            return []

        # Find uncommitted entries
        uncommitted = []
        for seq, entry in entries.items():
            if seq not in committed:
                uncommitted.append(entry)
                self._uncommitted[seq] = entry

        if uncommitted:
            log.info(f"WAL recovery: {len(uncommitted)} uncommitted entries found")

        return uncommitted

    def get_uncommitted(self) -> List[WALEntry]:
        """Get all uncommitted entries for replay."""
        with self.lock:
            return list(self._uncommitted.values())

    def compact(self):
        """
        Compact WAL: copy all entries (committed + uncommitted) to a fresh file
        using an atomic temp-file swap. The compacted file preserves every entry
        so recovery can still see the full history.
        """
        import tempfile

        self.flush()
        with self.lock:
            if not self.wal_file.exists():
                return

            all_entries = list(self._uncommitted.values())

        dir_ = self.wal_file.parent
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".wal.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for entry in all_entries:
                    f.write(json.dumps(entry.to_dict(), default=str, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.wal_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        with self.lock:
            self._compacted_count += 1
        log.debug(f"WAL compacted: {len(all_entries)} entries remaining")

    def stats(self) -> dict:
        """Get WAL statistics."""
        size = self.wal_file.stat().st_size if self.wal_file.exists() else 0
        with self.lock:
            buffered_records = len(self._active_buffer) + len(self._flush_buffer)
            durable_append_count = self._durable_append_count
            durable_commit_count = self._durable_commit_count
            compacted_count = self._compacted_count
        return {
            "namespace": self.namespace,
            "sequence": self._sequence,
            "uncommitted_count": len(self._uncommitted),
            "buffered_record_count": buffered_records,
            "durable_append_count": durable_append_count,
            "durable_commit_count": durable_commit_count,
            "compacted_count": compacted_count,
            "file_size_bytes": size,
            "file_path": str(self.wal_file),
        }

    def close(self, compact: bool = False):
        """Stop background flushing and durably flush remaining buffered records."""
        self._stop_event.set()
        self._flush_event.set()
        if hasattr(self, "_flusher") and self._flusher.is_alive():
            self._flusher.join(timeout=1.0)
        self.flush()
        if compact:
            self.compact()


# Singleton per namespace
_wal_instances: Dict[str, WriteAheadLog] = {}
_wal_namespace_locks: Dict[str, threading.Lock] = {}
_wal_lock = threading.Lock()


def get_wal(
    namespace: str = "default",
    flush_batch_size: int = 10,
    flush_interval_ms: int = 5,
    async_flush: bool = False,
) -> WriteAheadLog:
    """Get or create WAL for namespace."""
    with _wal_lock:
        if namespace not in _wal_namespace_locks:
            _wal_namespace_locks[namespace] = threading.Lock()
        namespace_lock = _wal_namespace_locks[namespace]

    with namespace_lock:
        if namespace not in _wal_instances:
            _wal_instances[namespace] = WriteAheadLog(
                namespace=namespace,
                flush_batch_size=flush_batch_size,
                flush_interval_ms=flush_interval_ms,
                async_flush=async_flush,
            )
        return _wal_instances[namespace]


def close_all_wals(compact: bool = False):
    with _wal_lock:
        instances = list(_wal_instances.values())
        _wal_instances.clear()
        _wal_namespace_locks.clear()
    for wal in instances:
        try:
            wal.close()
            if compact:
                wal.compact()
        except Exception:
            pass


def close_wal(namespace: str, compact: bool = False):
    with _wal_lock:
        wal = _wal_instances.pop(namespace, None)
        _wal_namespace_locks.pop(namespace, None)
    if wal is not None:
        wal.close(compact=compact)


atexit.register(close_all_wals)
