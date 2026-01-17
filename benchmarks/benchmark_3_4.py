import multiprocessing as mp
import time
import json
import uuid
import struct
from typing import List, Dict, Any
from faker import Faker
from memory_thread.utils.shared_memory import SlabAllocator
from memory_thread.models.events import ActionEnum

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------
NUM_ENTRIES = 1000 # Enough to measure overhead
SLAB_SIZE = 65536
NUM_SLABS = 1024
SEED = 42

# -------------------------------------------------------------------------
# MOCKING SERVICES FOR BENCHMARK
# We import actual classes but might need to monkeypatch DB calls if they are slow
# But currently they are in-memory (mocked inside the classes), so it's fine.
from memory_thread.services.tms_service import TMSService, StateDerivationService
from memory_thread.services.meta_stability_service import MetaStabilityService
from memory_thread.models.events import Event, EntityState, ActorEnum, TruthVector

# -------------------------------------------------------------------------
# DATA GENERATION
# -------------------------------------------------------------------------
def generate_tms_dataset(n=NUM_ENTRIES) -> List[Dict[str, Any]]:
    fake = Faker()
    Faker.seed(SEED)
    data = []
    print(f"Generating {n} TMS events...")

    # 40% Simple Facts (UPDATE)
    # 30% State Changes (ADD/REMOVE)
    # 30% Others

    for _ in range(n):
        r = fake.random_int(0, 100)
        if r < 40:
            action = "UPDATE"
            delta = {"fact": fake.sentence()}
        elif r < 70:
            action = "ADD" if fake.boolean() else "REMOVE"
            delta = {"tree_count": fake.random_int(1, 100)}
        else:
            action = "OBSERVE"
            delta = {"preference": "dark_mode"}

        obj = {
            "action": action,
            "object_id": str(uuid.uuid4()),
            "delta": delta,
            "content": fake.text(max_nb_chars=100) # Original text
        }
        data.append(obj)
    return data

# -------------------------------------------------------------------------
# BASELINE WORKER (PHASE 3.3 Logic - Pure Ingest)
# -------------------------------------------------------------------------
def baseline_worker(allocator_args, done: mp.Event, counter: mp.Value):
    allocator = allocator_args
    while not done.is_set():
        slab = allocator.get_written_slab()
        if slab:
            try:
                # Read 4-byte header
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]
                _ = slab.memory[4:4+msg_len].tobytes()

                # NO TMS LOGIC HERE

                with counter.get_lock():
                    counter.value += 1
                allocator.release_slab(slab.slab_id)
            except Exception:
                pass
        else:
            time.sleep(0.0001)

# -------------------------------------------------------------------------
# TMS WORKER (PHASE 3.4 Logic - Full Brain)
# -------------------------------------------------------------------------
def tms_worker(allocator_args, done: mp.Event, counter: mp.Value):
    allocator = allocator_args
    tms = TMSService()
    meta = MetaStabilityService()

    while not done.is_set():
        slab = allocator.get_written_slab()
        if slab:
            try:
                # 1. Read
                header = slab.memory[:4].tobytes()
                msg_len = struct.unpack("!I", header)[0]
                raw = slab.memory[4:4+msg_len].tobytes()
                obj = json.loads(raw)

                # 2. Meta Check
                if meta.check_drift(obj.get("content", ""), "general"):
                    pass

                # 3. TMS Pipeline
                action = ActionEnum[obj["action"]]
                delta = obj["delta"]
                object_id = uuid.UUID(obj["object_id"])

                event = tms.create_event(ActorEnum.USER, action, object_id, delta)

                current_state = EntityState(
                    entity_id=object_id,
                    namespace="user",
                    current_value={},
                    truth_vector=event.truth_vector,
                    last_event_id=uuid.uuid4()
                )

                new_state = StateDerivationService.apply_event(current_state, event)

                meta.check_integrity(new_state)

                with counter.get_lock():
                    counter.value += 1
                allocator.release_slab(slab.slab_id)
            except Exception as e:
                # print(f"TMS Error: {e}")
                pass
        else:
            time.sleep(0.0001)

# -------------------------------------------------------------------------
# RUNNER CLASS
# -------------------------------------------------------------------------
class BenchmarkRunner:
    def __init__(self, mode="BASELINE", data=[]):
        self.mode = mode
        self.data = data
        self.allocator = SlabAllocator(num_slabs=NUM_SLABS, slab_size=SLAB_SIZE)
        self.done = mp.Event()
        self.counter = mp.Value('i', 0)

        target = baseline_worker if mode == "BASELINE" else tms_worker
        self.worker = mp.Process(target=target, args=(self.allocator, self.done, self.counter))

    def run(self):
        self.worker.start()
        start = time.time()

        for item in self.data:
            b_item = json.dumps(item).encode('utf-8')
            msg_len = len(b_item)
            if msg_len + 4 > SLAB_SIZE: continue

            slab = self.allocator.reserve_slab()
            slab.memory[:4] = struct.pack("!I", msg_len)
            slab.memory[4:4+msg_len] = b_item
            self.allocator.mark_as_written(slab.slab_id)

        while self.counter.value < len(self.data):
            time.sleep(0.001)
            if time.time() - start > 30: # Timeout safety
                break

        end = time.time()
        self.done.set()
        self.worker.terminate()
        self.worker.join()
        self.allocator.unlink()

        return len(self.data) / (end - start)

# -------------------------------------------------------------------------
# PART 2 & 3 & 4 & 5 Logic (Verification)
# -------------------------------------------------------------------------
def run_logic_verification():
    print("\nRunning Logic Verification (Parts 2-5)...")
    tms = TMSService()
    meta = MetaStabilityService()

    # Part 3: Arithmetic
    eid = uuid.uuid4()
    s = EntityState(entity_id=eid, namespace="u", current_value={"count": 0}, truth_vector=TruthVector(confidence=1, authority=1, freshness=1, corroboration=0), last_event_id=uuid.uuid4())

    # +5000
    e1 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, eid, {"count": 5000})
    s = StateDerivationService.apply_event(s, e1)

    # -20
    e2 = tms.create_event(ActorEnum.USER, ActionEnum.REMOVE, eid, {"count": 20})
    s = StateDerivationService.apply_event(s, e2)

    expected = 4980
    actual = s.current_value["count"]
    print(f"Arithmetic Test: Expected {expected}, Got {actual} -> {'✅' if expected==actual else '❌'}")

    # Part 5: Meta Stability
    drift = meta.check_drift("I love video games", domain="botany")
    print(f"Drift Detection: {'✅' if drift else '❌'}")

    s_bad = EntityState(entity_id=eid, namespace="u", current_value={"tree_count": -5}, truth_vector=e1.truth_vector, last_event_id=uuid.uuid4())
    integrity = meta.check_integrity(s_bad)
    print(f"Integrity Check (-5 trees): {'✅' if not integrity else '❌'}")

# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
def main():
    print("## PHASE 3.4 TMS BENCHMARK RESULTS\n")

    data = generate_tms_dataset(NUM_ENTRIES)

    # Part 1: Overhead
    print("\n### PART 1: OVERHEAD MEASUREMENT")
    base_eps = BenchmarkRunner("BASELINE", data).run()
    print(f"Baseline (3.3): {base_eps:.2f} eps")

    tms_eps = BenchmarkRunner("TMS", data).run()
    print(f"With TMS (3.4): {tms_eps:.2f} eps")

    overhead = (base_eps - tms_eps) / base_eps * 100
    print(f"**TMS OVERHEAD: {overhead:.2f}%**")
    print(f"Target (>1000 eps): {'✅' if tms_eps > 1000 else '❌'}")

    # Logic Checks
    run_logic_verification()

if __name__ == "__main__":
    mp.set_start_method('fork')
    main()
