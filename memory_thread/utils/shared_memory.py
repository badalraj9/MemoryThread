import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import ctypes
from typing import List, Optional

# Slab states (kept for compatibility, though we rely on stack for availability)
FREE = 0
RESERVED = 1
WRITTEN = 2
READ = 3
RELEASED = 4

class AlignedSharedMemory:
    """
    A utility class to create a shared memory block with a cache-line-aligned
    memoryview, preventing false sharing between CPU cores.
    """
    def __init__(self, size: int, alignment: int = 64, create=True, name=None):
        self._alignment = alignment
        self._shm = SharedMemory(create=create, size=size + alignment, name=name)

        # Get the address of the underlying buffer
        # We assume _shm.buf is an mmap-backed memoryview
        # Using ctypes to get the address safely
        buf = self._shm.buf
        address = ctypes.addressof(ctypes.c_char.from_buffer(buf))

        # Calculate aligned offset
        aligned_address = (address + alignment - 1) & -alignment
        offset = aligned_address - address

        self.memory = self._shm.buf[offset:offset + size]

    @property
    def name(self):
        return self._shm.name

    def close(self):
        try:
            self.memory.release()
        except Exception:
            pass
        self._shm.close()

    def unlink(self):
        self._shm.unlink()

class SlabHandle:
    def __init__(self, slab_id, memoryview):
        self.slab_id = slab_id
        self.memory = memoryview

class SlabAllocator:
    def __init__(self, num_slabs: int, slab_size: int):
        self.num_slabs = num_slabs
        self.slab_size = slab_size

        # 1. Data Slabs
        self.data_shm = AlignedSharedMemory(size=num_slabs * slab_size)

        # 2. Metadata (State flags)
        self.metadata_shm = AlignedSharedMemory(size=num_slabs * ctypes.sizeof(ctypes.c_int))
        self.metadata = (ctypes.c_int * num_slabs).from_buffer(self.metadata_shm.memory)
        for i in range(num_slabs):
            self.metadata[i] = FREE

        # 3. Free List Stack (New Optimization)
        # Stores IDs of free slabs. Initialized with 0..N-1
        self.stack_shm = AlignedSharedMemory(size=num_slabs * ctypes.sizeof(ctypes.c_int))
        self.free_stack = (ctypes.c_int * num_slabs).from_buffer(self.stack_shm.memory)
        for i in range(num_slabs):
            self.free_stack[i] = i

        # Stack Pointer (points to next available slot index)
        # Full stack: top = num_slabs. Empty stack: top = 0.
        # We pop from top-1.
        self.stack_top = mp.Value(ctypes.c_int, num_slabs)

        # 4. Synchronization
        self.free_list_semaphore = mp.Semaphore(num_slabs)
        self.lock = mp.Lock() # Protects stack_top and free_stack operations

        # 5. Reader Optimization
        # A simple FIFO queue for WRITTEN slabs would be ideal, but requires complex shared queue.
        # We stick to a cursor scan for written items, but optimize it.
        self.next_read_slab = mp.Value(ctypes.c_int, 0)

    def reserve_slab(self, timeout: float = None) -> SlabHandle:
        # Wait for a free slab
        if not self.free_list_semaphore.acquire(timeout=timeout):
             raise TimeoutError("Slab allocation timed out (Buffer Full)")

        with self.lock:
            # O(1) Pop from stack
            top = self.stack_top.value
            if top <= 0:
                raise Exception("Semaphore passed but stack empty (Invariant Violation)")

            self.stack_top.value = top - 1
            slab_id = self.free_stack[top - 1]

            # Update metadata
            self.metadata[slab_id] = RESERVED

            offset = slab_id * self.slab_size
            slab_memory = self.data_shm.memory[offset:offset + self.slab_size]
            return SlabHandle(slab_id, slab_memory)

    def reserve_slabs_batch(self, count: int) -> List[SlabHandle]:
        # Batch acquire semaphore (loop is unavoidable for Semaphore, but stack op is fast)
        for _ in range(count):
            self.free_list_semaphore.acquire()

        handles = []
        with self.lock:
            top = self.stack_top.value
            if top < count:
                 raise Exception(f"Semaphore passed but stack has {top} < {count} (Invariant Violation)")

            new_top = top - count
            self.stack_top.value = new_top

            for i in range(count):
                slab_id = self.free_stack[new_top + i]
                self.metadata[slab_id] = RESERVED

                offset = slab_id * self.slab_size
                slab_memory = self.data_shm.memory[offset:offset + self.slab_size]
                handles.append(SlabHandle(slab_id, slab_memory))

        return handles

    def mark_as_written(self, slab_id: int):
        self.metadata[slab_id] = WRITTEN

    def release_slab(self, slab_id: int):
        with self.lock:
            # O(1) Push to stack
            top = self.stack_top.value
            if top >= self.num_slabs:
                 raise Exception("Stack overflow on release (Invariant Violation)")

            self.free_stack[top] = slab_id
            self.stack_top.value = top + 1
            self.metadata[slab_id] = FREE

        self.free_list_semaphore.release()

    def release_slabs_batch(self, slab_ids: List[int]):
        count = len(slab_ids)
        with self.lock:
            top = self.stack_top.value
            if top + count > self.num_slabs:
                 raise Exception("Stack overflow on batch release")

            for i, slab_id in enumerate(slab_ids):
                self.free_stack[top + i] = slab_id
                self.metadata[slab_id] = FREE

            self.stack_top.value = top + count

        for _ in range(count):
            self.free_list_semaphore.release()

    def get_written_slab(self) -> Optional[SlabHandle]:
        # Reader still scans, but we can make it smarter or just fast-scan
        # No change here for now, scanning 'WRITTEN' state is decoupled from free-list stack
        with self.lock:
            start_idx = self.next_read_slab.value
            # Limit scan to avoid infinite loop if logic buggy
            for i in range(self.num_slabs):
                slab_id = (start_idx + i) % self.num_slabs
                if self.metadata[slab_id] == WRITTEN:
                    self.metadata[slab_id] = READ
                    self.next_read_slab.value = (slab_id + 1) % self.num_slabs

                    offset = slab_id * self.slab_size
                    slab_memory = self.data_shm.memory[offset:offset + self.slab_size]
                    return SlabHandle(slab_id, slab_memory)
        return None

    def get_written_slabs_batch(self, max_count: int) -> List[SlabHandle]:
        handles = []
        with self.lock:
            start_idx = self.next_read_slab.value
            for i in range(self.num_slabs):
                if len(handles) >= max_count: break
                slab_id = (start_idx + i) % self.num_slabs

                if self.metadata[slab_id] == WRITTEN:
                    self.metadata[slab_id] = READ
                    offset = slab_id * self.slab_size
                    slab_memory = self.data_shm.memory[offset:offset + self.slab_size]
                    handles.append(SlabHandle(slab_id, slab_memory))

            if handles:
                self.next_read_slab.value = (handles[-1].slab_id + 1) % self.num_slabs

        return handles

    def get_allocator_stats(self):
        stats = {
            "FREE": 0, "RESERVED": 0, "WRITTEN": 0, "READ": 0, "RELEASED": 0,
            "semaphore_value": self.free_list_semaphore.get_value(),
            "stack_top": self.stack_top.value
        }
        with self.lock:
            for i in range(self.num_slabs):
                state = self.metadata[i]
                if state == FREE: stats["FREE"] += 1
                elif state == RESERVED: stats["RESERVED"] += 1
                elif state == WRITTEN: stats["WRITTEN"] += 1
                elif state == READ: stats["READ"] += 1
                elif state == RELEASED: stats["RELEASED"] += 1
        return stats

    def validate_invariants(self):
        stats = self.get_allocator_stats()
        # Invariant: FREE count should match semaphore (approx) and stack_top
        # Stack stores FREE slabs. So stack_top (count of items) == FREE
        if stats["stack_top"] != stats["FREE"]:
             raise RuntimeError(f"Stack vs Metadata Mismatch: Stack({stats['stack_top']}) != FREE({stats['FREE']})")

        # Semaphore might be slightly off due to race in reading value vs lock, but should be close.
        # Strictly: semaphore value == stack_top
        if stats["semaphore_value"] != stats["stack_top"]:
             raise RuntimeError(f"Semaphore vs Stack Mismatch: Sem({stats['semaphore_value']}) != Stack({stats['stack_top']})")

        return True

    def close(self):
        for attr in ("metadata", "free_stack"):
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except Exception:
                    pass
        self.data_shm.close()
        self.metadata_shm.close()
        self.stack_shm.close()

    def unlink(self):
        self.data_shm.unlink()
        self.metadata_shm.unlink()
        self.stack_shm.unlink()
