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
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        self.wal_file = WAL_DIR / f"{namespace}.wal"
        self.lock = threading.Lock()
        self._sequence = 0
        self._uncommitted: Dict[int, WALEntry] = {}
        
        self._ensure_dir()
        self._recover()
    
    def _ensure_dir(self):
        """Create WAL directory if needed."""
        WAL_DIR.mkdir(parents=True, exist_ok=True)
    
    def _checksum(self, data: str) -> str:
        """Simple checksum for integrity."""
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def append(self, operation: str, data: Dict[str, Any]) -> int:
        """
        Append entry to WAL and sync to disk.
        
        Returns:
            Sequence number for this entry
        """
        with self.lock:
            self._sequence += 1
            seq = self._sequence
            
            entry = WALEntry(
                sequence=seq,
                timestamp=datetime.utcnow().isoformat(),
                operation=operation,
                data=data,
                checksum=self._checksum(json.dumps(data, default=str)),
                committed=False
            )
            
            # Write to disk with fsync (crash-safe)
            try:
                with open(self.wal_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), default=str) + "\n")
                    f.flush()
                    os.fsync(f.fileno())  # Force to disk
            except Exception as e:
                log.error(f"WAL write failed: {e}")
                raise RuntimeError(f"WAL write failed: {e}")
            
            self._uncommitted[seq] = entry
            log.debug(f"WAL append: seq={seq} op={operation}")
            
            return seq
    
    def commit(self, sequence: int):
        """
        Mark entry as committed (successfully processed).
        
        Args:
            sequence: The sequence number from append()
        """
        with self.lock:
            if sequence in self._uncommitted:
                entry = self._uncommitted.pop(sequence)
                entry.committed = True
                
                # Append commit marker
                try:
                    with open(self.wal_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "type": "commit",
                            "sequence": sequence,
                            "timestamp": datetime.utcnow().isoformat()
                        }) + "\n")
                        f.flush()
                        os.fsync(f.fileno())
                except Exception as e:
                    log.error(f"WAL commit write failed: {e}")
                
                log.debug(f"WAL commit: seq={sequence}")
    
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
        Compact WAL by removing committed entries.
        
        Call periodically to prevent unbounded growth.
        """
        with self.lock:
            if not self.wal_file.exists():
                return
            
            # Read all, keep only uncommitted
            uncommitted = self.get_uncommitted()
            
            # Rewrite WAL with only uncommitted
            temp_file = self.wal_file.with_suffix(".wal.tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                for entry in uncommitted:
                    f.write(json.dumps(entry.to_dict(), default=str) + "\n")
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic rename
            temp_file.replace(self.wal_file)
            log.info(f"WAL compacted: {len(uncommitted)} entries remaining")
    
    def stats(self) -> dict:
        """Get WAL statistics."""
        size = self.wal_file.stat().st_size if self.wal_file.exists() else 0
        return {
            "namespace": self.namespace,
            "sequence": self._sequence,
            "uncommitted_count": len(self._uncommitted),
            "file_size_bytes": size,
            "file_path": str(self.wal_file),
        }


# Singleton per namespace
_wal_instances: Dict[str, WriteAheadLog] = {}
_wal_lock = threading.Lock()


def get_wal(namespace: str = "default") -> WriteAheadLog:
    """Get or create WAL for namespace."""
    with _wal_lock:
        if namespace not in _wal_instances:
            _wal_instances[namespace] = WriteAheadLog(namespace)
        return _wal_instances[namespace]
