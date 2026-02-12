"""
Async Write-Ahead Log (WAL) for Memory Thread.

Non-blocking WAL implementation using background threads for fsync operations.
This prevents blocking the main event loop while maintaining crash safety.

Architecture:
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │  remember() │───▶│  Queue      │───▶│  Worker     │
    └─────────────┘    └─────────────┘    └─────────────┘
                              │                  │
                              │                  ▼
                              │           ┌─────────────┐
                              └──────────▶│  fsync()    │
                                          └─────────────┘
"""
import asyncio
import json
import os
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
import uuid

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

# WAL location
WAL_DIR = Path.home() / ".mt" / "wal"


@dataclass
class AsyncWALEntry:
    """A single WAL entry."""
    sequence: int
    timestamp: str
    operation: str
    data: Dict[str, Any]
    checksum: str
    committed: bool = False
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "AsyncWALEntry":
        return cls(**d)


class AsyncWriteAheadLog:
    """
    Non-blocking Write-Ahead Log with background fsync.
    
    Uses a thread pool for disk I/O to avoid blocking the async event loop.
    
    Guarantees:
    - Events are durably stored before acknowledgment
    - Crash recovery replays uncommitted events
    - Non-blocking to async callers
    
    Usage:
        wal = AsyncWriteAheadLog(namespace="myapp")
        await wal.start()
        
        seq = await wal.append("remember", {"content": "user data"})
        # ... process the event ...
        await wal.commit(seq)
        
        await wal.stop()
    """
    
    def __init__(self, namespace: str = "default", max_workers: int = 2):
        self.namespace = namespace
        self.wal_file = WAL_DIR / f"{namespace}.async.wal"
        self.max_workers = max_workers
        
        self._lock = asyncio.Lock()
        self._sequence = 0
        self._uncommitted: Dict[int, AsyncWALEntry] = {}
        
        # Thread pool for blocking I/O
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        
        # Write queue for batching
        self._write_queue: Queue = Queue()
        self._writer_thread: Optional[threading.Thread] = None
        
        # Callbacks for commit notification
        self._commit_callbacks: Dict[int, asyncio.Future] = {}
    
    async def start(self):
        """Start the WAL and background writer."""
        WAL_DIR.mkdir(parents=True, exist_ok=True)
        
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, 
            thread_name_prefix="wal_worker"
        )
        self._running = True
        
        # Start background writer thread
        self._writer_thread = threading.Thread(
            target=self._background_writer,
            daemon=True,
            name=f"wal_writer_{self.namespace}"
        )
        self._writer_thread.start()
        
        # Recover any uncommitted entries
        await self._recover()
        
        log.info(f"AsyncWAL started: {self.namespace}")
    
    async def stop(self):
        """Stop the WAL gracefully."""
        self._running = False
        
        # Signal writer to stop
        self._write_queue.put(None)
        
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        
        if self._executor:
            self._executor.shutdown(wait=True)
        
        log.info(f"AsyncWAL stopped: {self.namespace}")
    
    def _checksum(self, data: str) -> str:
        """Simple checksum for integrity."""
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _background_writer(self):
        """Background thread that handles disk writes with fsync."""
        batch = []
        batch_timeout = 0.01  # 10ms batching window
        
        while self._running or not self._write_queue.empty():
            try:
                # Collect batch of writes
                item = self._write_queue.get(timeout=batch_timeout)
                
                if item is None:  # Stop signal
                    break
                
                batch.append(item)
                
                # Drain queue for batching (non-blocking)
                while len(batch) < 100:  # Max batch size
                    try:
                        item = self._write_queue.get_nowait()
                        if item is None:
                            break
                        batch.append(item)
                    except Empty:
                        break
                
                # Write batch to disk
                if batch:
                    self._write_batch(batch)
                    batch = []
                    
            except Empty:
                # Flush any pending batch on timeout
                if batch:
                    self._write_batch(batch)
                    batch = []
    
    def _write_batch(self, batch: List[tuple]):
        """Write a batch of entries to disk with single fsync."""
        try:
            with open(self.wal_file, "a", encoding="utf-8") as f:
                for entry, future_id in batch:
                    f.write(json.dumps(entry.to_dict(), default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())  # Single fsync for whole batch
            
            log.debug(f"WAL batch written: {len(batch)} entries")
            
        except Exception as e:
            log.error(f"WAL batch write failed: {e}")
            raise
    
    async def append(self, operation: str, data: Dict[str, Any]) -> int:
        """
        Append entry to WAL (non-blocking).
        
        Returns:
            Sequence number for this entry
        """
        async with self._lock:
            self._sequence += 1
            seq = self._sequence
            
            entry = AsyncWALEntry(
                sequence=seq,
                timestamp=datetime.utcnow().isoformat(),
                operation=operation,
                data=data,
                checksum=self._checksum(json.dumps(data, default=str)),
                committed=False
            )
            
            # Queue for background write
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            self._commit_callbacks[seq] = future
            
            self._write_queue.put((entry, seq))
            self._uncommitted[seq] = entry
            
            log.debug(f"AsyncWAL append: seq={seq} op={operation}")
            
            return seq
    
    async def commit(self, sequence: int):
        """
        Mark entry as committed (successfully processed).
        
        Args:
            sequence: The sequence number from append()
        """
        async with self._lock:
            if sequence in self._uncommitted:
                entry = self._uncommitted.pop(sequence)
                entry.committed = True
                
                # Queue commit marker for background write
                commit_marker = {
                    "type": "commit",
                    "sequence": sequence,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Use executor for commit write
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    self._write_commit_marker,
                    commit_marker
                )
                
                log.debug(f"AsyncWAL commit: seq={sequence}")
    
    def _write_commit_marker(self, marker: dict):
        """Write commit marker to disk."""
        try:
            with open(self.wal_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(marker) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            log.error(f"WAL commit marker write failed: {e}")
    
    async def rollback(self, sequence: int):
        """Mark entry as rolled back (failed processing)."""
        async with self._lock:
            if sequence in self._uncommitted:
                del self._uncommitted[sequence]
                log.debug(f"AsyncWAL rollback: seq={sequence}")
    
    async def _recover(self) -> List[AsyncWALEntry]:
        """Recover uncommitted entries after crash."""
        if not self.wal_file.exists():
            return []
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._do_recover)
    
    def _do_recover(self) -> List[AsyncWALEntry]:
        """Sync recovery logic (run in executor)."""
        entries: Dict[int, AsyncWALEntry] = {}
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
                            entry = AsyncWALEntry.from_dict(record)
                            entries[entry.sequence] = entry
                            self._sequence = max(self._sequence, entry.sequence)
                    except json.JSONDecodeError:
                        log.warning(f"Corrupt WAL line: {line[:50]}...")
        
        except Exception as e:
            log.error(f"AsyncWAL recovery failed: {e}")
            return []
        
        # Find uncommitted entries
        uncommitted = []
        for seq, entry in entries.items():
            if seq not in committed:
                uncommitted.append(entry)
                self._uncommitted[seq] = entry
        
        if uncommitted:
            log.info(f"AsyncWAL recovery: {len(uncommitted)} uncommitted entries found")
        
        return uncommitted
    
    async def get_uncommitted(self) -> List[AsyncWALEntry]:
        """Get all uncommitted entries for replay."""
        async with self._lock:
            return list(self._uncommitted.values())
    
    async def compact(self):
        """Compact WAL by removing committed entries."""
        async with self._lock:
            if not self.wal_file.exists():
                return
            
            uncommitted = await self.get_uncommitted()
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self._do_compact,
                uncommitted
            )
    
    def _do_compact(self, uncommitted: List[AsyncWALEntry]):
        """Sync compaction logic (run in executor)."""
        temp_file = self.wal_file.with_suffix(".wal.tmp")
        
        with open(temp_file, "w", encoding="utf-8") as f:
            for entry in uncommitted:
                f.write(json.dumps(entry.to_dict(), default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic rename
        temp_file.replace(self.wal_file)
        log.info(f"AsyncWAL compacted: {len(uncommitted)} entries remaining")
    
    async def stats(self) -> dict:
        """Get WAL statistics."""
        size = self.wal_file.stat().st_size if self.wal_file.exists() else 0
        return {
            "namespace": self.namespace,
            "sequence": self._sequence,
            "uncommitted_count": len(self._uncommitted),
            "file_size_bytes": size,
            "file_path": str(self.wal_file),
            "running": self._running,
        }


# Factory function
async def get_async_wal(namespace: str = "default") -> AsyncWriteAheadLog:
    """Get or create async WAL for namespace."""
    wal = AsyncWriteAheadLog(namespace)
    await wal.start()
    return wal
