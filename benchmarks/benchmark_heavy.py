import multiprocessing as mp
import time
import queue
import os
import ctypes
import json
import struct
from typing import List, Dict, Any
from faker import Faker
import statistics

from memory_thread.utils.shared_memory import SlabAllocator, WRITTEN

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------
NUM_ENTRIES = 500
SLAB_SIZE = 65536 # 64KB Safety
NUM_SLABS = 1024
SEED = 42

# -------------------------------------------------------------------------
# DATA
# -------------------------------------------------------------------------
def generate_light_dataset(n=NUM_ENTRIES) -> List[str]:
    fake = Faker()
    Faker.seed(SEED)
    return [fake.text(max_nb_chars=100) for _ in range(n)]

def generate_heavy_dataset(n=NUM_ENTRIES) -> List[Dict[str, Any]]:
    fake = Faker()
    Faker.seed(SEED)
    data = []
    print(f"Generating {n} heavy entries...")
    for _ in range(n):
        obj = {
            "content": fake.text(max_nb_chars=1000),
            "created_at": time.time(),
            "metadata": {
                "source": "user",
                "importance": 0.8,
                "tags": [fake.word() for _ in range(10)],
                "nested": {
                    "a": fake.text(max_nb_chars=200),
                    "b": [fake.random_int() for _ in range(50)]
                }
            },
            "entities": [{"name": fake.name(), "label": "PERSON", "info": fake.text()} for _ in range(5)],
            "history": [{"event": fake.word(), "timestamp": time.time()} for _ in range(5)]
        }
        data.append(obj)
    return data

# -------------------------------------------------------------------------
# RUNNERS
# -------------------------------------------------------------------------
def old_worker(input_queue: mp.Queue, done: mp.Event, counter: mp.Value, work_delay: float):
    while not done.is_set():
        try:
            item = input_queue.get(timeout=0.01)
            if item == "STOP": break

            if isinstance(item, dict): _ = item.get("content")
            if work_delay > 0: time.sleep(work_delay)
            with counter.get_lock():
                counter.value += 1
        except queue.Empty:
            continue

class OldSystemRunner:
    def __init__(self, data: List[Any], work_delay: float = 0):
        self.data = data
        self.work_delay = work_delay
        self.queue = mp.Queue()
        self.done = mp.Event()
        self.counter = mp.Value('i', 0)
        self.worker = mp.Process(target=old_worker, args=(self.queue, self.done, self.counter, work_delay))

    def run(self):
        self.worker.start()
        start = time.time()
        for item in self.data:
            self.queue.put(item)
        self.queue.put("STOP")

        self.worker.join()

        end = time.time()
        self.done.set()
        return len(self.data) / (end - start)

def new_worker(allocator_args, done: mp.Event, counter: mp.Value, work_delay: float):
    allocator = allocator_args
    while not done.is_set():
        slab = allocator.get_written_slab()
        if slab:
            try:
                # Read Header (4 bytes length)
                # Need to act on memoryview carefully
                # We can cast or just read bytes
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]

                # Read Body
                raw = slab.memory[4:4+msg_len].tobytes()

                if raw == b"STOP":
                    allocator.release_slab(slab.slab_id)
                    break

                if raw.startswith(b'{'):
                    obj = json.loads(raw)
                    _ = obj.get("content")

                if work_delay > 0: time.sleep(work_delay)
                with counter.get_lock():
                    counter.value += 1
                allocator.release_slab(slab.slab_id)
            except Exception as e:
                # print(f"WORKER ERROR: {e}")
                pass
        else:
            time.sleep(0.0001)

class NewSystemRunner:
    def __init__(self, data: List[Any], work_delay: float = 0):
        self.data = data
        self.work_delay = work_delay
        self.allocator = SlabAllocator(num_slabs=NUM_SLABS, slab_size=SLAB_SIZE)
        self.done = mp.Event()
        self.counter = mp.Value('i', 0)
        self.worker = mp.Process(target=new_worker, args=(self.allocator, self.done, self.counter, work_delay))

    def run(self):
        self.worker.start()
        start = time.time()

        count = 0
        for item in self.data:
            b_item = json.dumps(item).encode('utf-8')
            msg_len = len(b_item)
            if msg_len + 4 > SLAB_SIZE:
                print("SKIPPED ITEM TOO LARGE")
                continue

            slab = self.allocator.reserve_slab()
            # Write Header
            slab.memory[:4] = struct.pack("!I", msg_len)
            # Write Body
            slab.memory[4:4+msg_len] = b_item

            self.allocator.mark_as_written(slab.slab_id)
            count += 1

        # Send STOP
        slab = self.allocator.reserve_slab()
        b_stop = b"STOP"
        slab.memory[:4] = struct.pack("!I", len(b_stop))
        slab.memory[4:4+len(b_stop)] = b_stop
        self.allocator.mark_as_written(slab.slab_id)

        self.worker.join()
        end = time.time()
        self.done.set()
        self.allocator.unlink()
        return count / (end - start)

def main():
    print("## COMPREHENSIVE BENCHMARK: QUEUE vs SLAB")

    light_data = generate_light_dataset(NUM_ENTRIES)
    heavy_data = generate_heavy_dataset(NUM_ENTRIES)

    results = []

    # SCENARIO A: Light
    print("\n--- A) LIGHT PAYLOAD ---")
    res_old = OldSystemRunner(light_data, work_delay=0).run()
    res_new = NewSystemRunner(light_data, work_delay=0).run()
    print(f"Old: {res_old:.2f} eps | New: {res_new:.2f} eps | Imp: {res_new/res_old:.2f}x")
    results.append(("Light", res_old, res_new))

    # SCENARIO B: Heavy
    print("\n--- B) HEAVY PAYLOAD ---")
    res_old = OldSystemRunner(heavy_data, work_delay=0).run()
    res_new = NewSystemRunner(heavy_data, work_delay=0).run()
    print(f"Old: {res_old:.2f} eps | New: {res_new:.2f} eps | Imp: {res_new/res_old:.2f}x")
    results.append(("Heavy", res_old, res_new))

    # SCENARIO C: Heavy + Work
    print("\n--- C) HEAVY + SIMULATED WORK (5ms) ---")
    res_old = OldSystemRunner(heavy_data, work_delay=0.005).run()
    res_new = NewSystemRunner(heavy_data, work_delay=0.005).run()
    print(f"Old: {res_old:.2f} eps | New: {res_new:.2f} eps | Imp: {res_new/res_old:.2f}x")
    results.append(("Heavy+Work", res_old, res_new))

    print("\n### FINAL COMPARISON TABLE")
    print("| Scenario | Old (Queue) | New (Slab) | Improvement |")
    print("|---|---|---|---|")
    for name, o, n in results:
        print(f"| {name} | {o:.2f} | {n:.2f} | {n/o:.2f}x |")

if __name__ == "__main__":
    mp.set_start_method('fork')
    main()
