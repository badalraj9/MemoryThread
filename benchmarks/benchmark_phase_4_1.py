import asyncio
import multiprocessing as mp
import time
import sys
from memory_thread.producers.python_producer import PythonProducer
from memory_thread.nervous.fabric import FabricRouter

# -------------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------------
TARGET_EPS = 50000
DURATION_SEC = 5
NUM_PRODUCERS = 4
ADDRESS = "tcp://127.0.0.1:5555"

# -------------------------------------------------------------------------
# SERVER
# -------------------------------------------------------------------------
def run_gateway_server(stop_event, shared_count):
    async def server_loop():
        router = FabricRouter(address=ADDRESS, mode="ROUTER")
        await router.start()

        count = 0
        print("[Server] Ready.", flush=True)

        while not stop_event.is_set():
            # Use small timeout to check stop_event
            # ZMQ poll is cleaner but basic receive loops
            try:
                # We need non-blocking receive or timeout
                # FabricRouter.receive() doesn't expose timeout in async mode easily
                # unless we modify it or wrap in wait_for.
                # Assuming traffic is high, it won't block long.
                msg = await asyncio.wait_for(router.receive(), timeout=0.1)
                if msg:
                    _, payload = msg
                    batch_len = len(payload.get("events", []))
                    count += batch_len
                    with shared_count.get_lock():
                        shared_count.value = count
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        router.close()

    asyncio.run(server_loop())

# -------------------------------------------------------------------------
# PRODUCER
# -------------------------------------------------------------------------
def run_producer(pid):
    async def producer_loop():
        p = PythonProducer(f"prod-{pid}", gateway_address=ADDRESS)
        await p.start()

        # Blast events for DURATION_SEC
        count = await p.run_load_test(duration_sec=DURATION_SEC, target_eps=TARGET_EPS // NUM_PRODUCERS)

        await p.stop()

    asyncio.run(producer_loop())

# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
def run_benchmark():
    print(f"## PHASE 4.1 SCALING BENCHMARK ({TARGET_EPS} eps target)", flush=True)

    stop_event = mp.Event()
    shared_count = mp.Value('i', 0)
    server = mp.Process(target=run_gateway_server, args=(stop_event, shared_count))
    server.start()

    time.sleep(2) # Warmup

    start_time = time.time()
    producers = []
    for i in range(NUM_PRODUCERS):
        p = mp.Process(target=run_producer, args=(i,))
        p.start()
        producers.append(p)

    for p in producers:
        p.join()

    # Producers finished in DURATION_SEC (approx)
    duration = time.time() - start_time

    stop_event.set()
    time.sleep(1) # Allow server to read final items

    final_count = shared_count.value
    eps = final_count / duration if duration > 0 else 0

    print(f"\n[Result] Processed: {final_count}")
    print(f"[Result] Duration: {duration:.2f}s")
    print(f"[Result] Aggregate EPS: {eps:.2f}")

    if eps > 10000:
        print("✅ Target Met (>10k)")
    else:
        print("❌ Target Missed")

    server.terminate()
    server.join()

if __name__ == "__main__":
    run_benchmark()
