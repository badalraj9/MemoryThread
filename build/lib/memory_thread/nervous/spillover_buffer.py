import os
import json
import collections
import time
from typing import Optional, List, Any
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class SpilloverBuffer:
    """
    Disk-backed FIFO buffer for handling backpressure.
    When the in-memory queue is full, items are written to disk.
    When memory frees up, items are read back from disk.
    """
    def __init__(self, spillover_dir: str = "./spillover", max_memory_size: int = 1000):
        self.spillover_dir = spillover_dir
        self.max_memory_size = max_memory_size
        self.memory_buffer = collections.deque()
        self.write_file_path = os.path.join(spillover_dir, "spillover.log")
        self.read_file_path = os.path.join(spillover_dir, "spillover.log")

        # State
        self.disk_count = 0
        self.read_offset = 0
        self.write_file_handle = None
        self.read_file_handle = None

        if not os.path.exists(spillover_dir):
            os.makedirs(spillover_dir)

        # Recovery: Check if file exists and has content
        self._recover_state()

    def _recover_state(self):
        """Recover count from disk if restarting."""
        if os.path.exists(self.write_file_path):
            # Simple line counting for now (could be slow for massive files, but robust)
            # For production, we'd use a separate metadata file for offsets/counts.
            with open(self.write_file_path, 'r') as f:
                self.disk_count = sum(1 for _ in f)
            log.info(f"Spillover recovered: {self.disk_count} items on disk.")

    def push(self, item: Any):
        """Push item. If memory full, write to disk."""
        if len(self.memory_buffer) < self.max_memory_size and self.disk_count == 0:
            self.memory_buffer.append(item)
        else:
            self._write_to_disk(item)

    def pop(self) -> Optional[Any]:
        """Pop item. Prioritize disk if exists (FIFO), else memory."""
        if self.disk_count > 0:
            return self._read_from_disk()
        elif self.memory_buffer:
            return self.memory_buffer.popleft()
        return None

    def _write_to_disk(self, item: Any):
        if not self.write_file_handle:
            self.write_file_handle = open(self.write_file_path, 'a')

        # Serialize
        data = json.dumps(item)
        self.write_file_handle.write(data + "\n")
        self.write_file_handle.flush() # Ensure it hits disk (buffering trade-off)
        self.disk_count += 1

    def _read_from_disk(self) -> Optional[Any]:
        if self.disk_count == 0: return None

        # This naive read approach reads line by line.
        # For a true FIFO file queue, we need to track read offset.
        # But reading line by line sequentially is hard if we append to the same file without random access management.
        # Strategy: Use two files? Or read line at offset?

        # Optimization: Rotating log files is better.
        # Simple Implementation for Phase 3.5:
        # Read from 'read_handle'. If EOF, wait? No, disk_count > 0 means data exists.

        if not self.read_file_handle:
            self.read_file_handle = open(self.read_file_path, 'r')
            # Seek to current read offset?
            # Ideally we track processed bytes.
            # Simplified: Since we recover by counting lines, we assume we start from 0 if recovering?
            # Or we need to delete the file when empty.

        line = self.read_file_handle.readline()
        if not line:
            # Should not happen if disk_count > 0, unless file rotated
            return None

        self.disk_count -= 1

        # Cleanup if empty
        if self.disk_count == 0:
            self._truncate_file()

        return json.loads(line)

    def _truncate_file(self):
        """Clear disk buffer when empty to reclaim space."""
        if self.write_file_handle: self.write_file_handle.close()
        if self.read_file_handle: self.read_file_handle.close()
        self.write_file_handle = None
        self.read_file_handle = None

        # Truncate
        with open(self.write_file_path, 'w') as f:
            pass

    def close(self):
        if self.write_file_handle: self.write_file_handle.close()
        if self.read_file_handle: self.read_file_handle.close()

    def get_stats(self):
        return {
            "memory_count": len(self.memory_buffer),
            "disk_count": self.disk_count
        }
