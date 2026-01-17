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
            item = qm.receive(timeout_ms=10)

            # 2. Buffer (Spillover Logic)
            if item:
                spill.push(item)

            # 3. Process from Buffer (Q3) -> DB
            # We fetch from spillover to maintain order
            next_item = spill.pop()
            if next_item:
                if sched.add(next_item):
                    # Batch Ready
                    batch = sched.get_batch()
                    self._write_batch(batch, sched)
            else:
                time.sleep(0.01) # Idle

        qm.close()
        spill.close()

    def _write_batch(self, batch, sched):
        start = time.time()
        # Mock DB Write (Simulated 1000 eps limit = 1ms per item)
        # Batch size 100 -> 100ms
        delay = len(batch) * 0.001
        time.sleep(delay)

        duration = time.time() - start
        # log.info(f"Persisted batch of {len(batch)} in {duration:.4f}s")

        # Update Scheduler Regulation
        # We don't have queue size easily from ZMQ, but spillover has it
        # q_size = 0 # Need shared memory or query
        # sched.update_pressure(q_size, duration)
