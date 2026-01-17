import multiprocessing as mp
import time
import json
import uuid
import struct
import os
import shutil
from typing import List, Dict, Any
from faker import Faker
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.services.ingest_service import IngestionService
from memory_thread.nervous.persistence_engine import PersistenceEngine

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------
NUM_ENTRIES = 10000
SLAB_SIZE = 65536
NUM_SLABS = 1024
SEED = 42

# -------------------------------------------------------------------------
# DATA GENERATION
# -------------------------------------------------------------------------
def generate_dataset(n=NUM_ENTRIES) -> List[Dict[str, Any]]:
    fake = Faker()
    Faker.seed(SEED)
    data = []
    print(f"Generating {n} events...")
    for _ in range(n):
        obj = {
            "action": "ADD",
            "object_id": str(uuid.uuid4()),
            "delta": {"tree_count": fake.random_int(1, 100)},
            "content": fake.text(max_nb_chars=100)
        }
        data.append(obj)
    return data

# -------------------------------------------------------------------------
# BENCHMARK RUNNER
# -------------------------------------------------------------------------
def run_benchmark():
    print("## PHASE 3.5 NERVOUS SYSTEM BENCHMARK")

    # Cleanup spillover
    if os.path.exists("./spillover"):
        shutil.rmtree("./spillover")
    os.makedirs("./spillover")

    service = IngestionService(num_slabs=NUM_SLABS, slab_size=SLAB_SIZE)
    service.start()

    data = generate_dataset(NUM_ENTRIES)

    print("\n--- Starting Ingestion Burst (50k eps target) ---")
    start_time = time.time()

    # Ingest all at once (simulating burst)
    # The IngestionService uses the SlabAllocator which is blocking if full,
    # but since we have 1024 slabs and workers consume fast, it should flow.
    # Actually, ingest_texts handles batching internally? No, loop.

    service.ingest_texts(data)

    ingest_duration = time.time() - start_time
    ingest_eps = NUM_ENTRIES / ingest_duration
    print(f"Ingestion Throughput: {ingest_eps:.2f} eps")

    # Wait for Persistence (Lag Drain)
    # Since we can't easily query the internal queue size without shared metrics,
    # we will wait for a timeout or check spillover file size.
    print("Waiting for persistence pipeline to drain...")
    time.sleep(5) # Give it some time

    # Check Spillover Status
    spill_files = os.listdir("./spillover")
    spill_size = sum(os.path.getsize(os.path.join("./spillover", f)) for f in spill_files)
    print(f"Spillover Size on Disk: {spill_size} bytes")

    if spill_size > 0:
        print("✅ Spillover Activated (Backpressure handled)")
    else:
        print("⚠️ Spillover Empty (Maybe load wasn't high enough or everything processed in memory)")

    service.shutdown()

    print("\n--- Metrics ---")
    print(f"Items: {NUM_ENTRIES}")
    print(f"Ingest Time: {ingest_duration:.4f}s")
    print(f"Ingest Speed: {ingest_eps:.2f} eps")

    return ingest_eps

if __name__ == "__main__":
    # mp.set_start_method('fork') # Already set by default or imports
    run_benchmark()
