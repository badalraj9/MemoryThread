import multiprocessing as mp
import time
import zmq
from memory_thread.nervous.queue_manager import QueueManager
from memory_thread.nervous.spillover_buffer import SpilloverBuffer
from memory_thread.nervous.persistence_scheduler import PersistenceScheduler
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class PersistenceEngine:
    def __init__(self):
        self.zm_ctx = zmq.Context()
        self.queue_manager = QueueManager(self.zm_ctx)
        self.spillover = SpilloverBuffer()
        self.scheduler = PersistenceScheduler()
        self.running = mp.Value('b', True)
        self.consumer_process = mp.Process(target=self._consumer_loop)

    def start(self):
        # Ingestion calls setup_producer(), Consumer calls setup_consumer()
        # But we spawn consumer process here.
        self.consumer_process.start()
        # Allow time for bind
        time.sleep(0.1)
        self.queue_manager.setup_producer()

    def push(self, item):
        self.queue_manager.send(item)

    def stop(self):
        self.running.value = False
        self.queue_manager.close()
        self.consumer_process.join()
        self.spillover.close()

    def _consumer_loop(self):
        # Re-init for process safety
        qm = QueueManager(address="ipc://persistence_pipe")
        qm.setup_consumer()
        spill = SpilloverBuffer()
        sched = PersistenceScheduler()

        log.info("Persistence Engine Consumer Started")

        last_stat_time = time.time()

        while self.running.value:
            # Stats Logging
            if time.time() - last_stat_time > 1.0:
                stats = spill.get_stats()
                if stats['disk_count'] > 0:
                    log.warning(f"Persistence Backpressure: {stats['disk_count']} items on disk, {stats['memory_count']} in memory")
                last_stat_time = time.time()

            # 1. Pull from ZMQ (Q2)
            # Try to drain ZMQ buffer into spillover first
            for _ in range(100): # Limit loop to avoid starvation of write
                 item = qm.receive(timeout_ms=0)
                 if item: spill.push(item)
                 else: break

            # 2. Process from Buffer (Q3) -> DB (Batched)
            # We fetch from spillover to maintain order and fill batch
            while True:
                next_item = spill.pop()
                if next_item:
                    ready = sched.add(next_item)
                    if ready:
                        batch = sched.get_batch()
                        self._write_batch(batch, sched)
                        break # Process one batch per loop cycle to check ZMQ again
                else:
                    # No more items, force flush if timeout
                    if sched.should_flush_time():
                        batch = sched.get_batch()
                        if batch: self._write_batch(batch, sched)
                    break

            time.sleep(0.001) # Brief yield

        qm.close()
        spill.close()

    def _write_batch(self, batch, sched):
        if not batch: return
        start = time.time()

        # REAL BATCHING LOGIC (Even if DB is mocked, structure must be real)
        # In production: self.pg.executemany(...)

        # Simulate Network Latency (1 round trip per batch, not per item!)
        # 10ms fixed latency + 0.1ms processing per item
        network_latency = 0.010
        processing_time = len(batch) * 0.0001
        time.sleep(network_latency + processing_time)

        duration = time.time() - start
        if len(batch) > 50:
             log.info(f"Persisted batch of {len(batch)} items in {duration:.4f}s")
