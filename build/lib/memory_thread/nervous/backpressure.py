import time
from typing import Dict
from memory_thread.nervous.persistence_scheduler import PersistenceScheduler
from memory_thread.nervous.spillover_buffer import SpilloverBuffer

class BackpressureController:
    """
    Monitors system health and calculates a 'Pressure Score' (0.0 - 1.0).
    """
    def __init__(self, scheduler: PersistenceScheduler, spillover: SpilloverBuffer):
        self.scheduler = scheduler
        self.spillover = spillover
        self.current_pressure = 0.0

    def update(self) -> float:
        stats = self.spillover.get_stats()
        disk_items = stats['disk_count']
        mem_items = stats['memory_count']

        # Pressure Logic
        # 1. Spillover Usage (High Weight): If disk has items, we are lagging.
        disk_pressure = min(1.0, disk_items / 5000.0) # 5k items on disk = 100% pressure

        # 2. Memory Usage (Medium Weight)
        mem_pressure = min(1.0, mem_items / 1000.0)

        # Max of factors
        self.current_pressure = max(disk_pressure, mem_pressure * 0.5)

        return self.current_pressure

    def get_throttle_delay(self) -> float:
        """
        Returns suggested sleep time for producers in seconds.
        """
        if self.current_pressure < 0.5:
            return 0.0
        elif self.current_pressure < 0.8:
            return 0.01 # 10ms
        else:
            return 0.1 # 100ms braking
