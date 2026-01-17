import time
from typing import List, Any
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class PersistenceScheduler:
    """
    Manages batching and pressure regulation for DB writes.
    """
    def __init__(self, batch_size=100, max_latency_ms=1000):
        self.batch_size = batch_size
        self.max_latency_ms = max_latency_ms
        self.current_batch = []
        self.last_flush_time = time.time()

        # Pressure Metrics
        self.pressure_score = 0.0 # 0.0 to 1.0 (1.0 = choked)

    def add(self, item: Any) -> bool:
        """Add item. Returns True if batch is ready."""
        self.current_batch.append(item)
        if len(self.current_batch) >= self.batch_size:
            return True
        if (time.time() - self.last_flush_time) * 1000 > self.max_latency_ms:
            return True
        return False

    def get_batch(self) -> List[Any]:
        batch = self.current_batch
        self.current_batch = []
        self.last_flush_time = time.time()
        return batch

    def update_pressure(self, queue_size: int, processing_time: float):
        """
        Calculate pressure based on queue lag and DB write time.
        """
        # Simple heuristic: If queue > 1000 or write time > 100ms, pressure rises
        lag_factor = min(1.0, queue_size / 5000.0)
        write_factor = min(1.0, processing_time / 0.1) # Target 100ms
        self.pressure_score = max(lag_factor, write_factor)

        if self.pressure_score > 0.8:
            log.warning(f"High Pressure: {self.pressure_score:.2f} (Lag: {queue_size})")

    def should_throttle(self) -> bool:
        return self.pressure_score > 0.9
