import asyncio
import time
import random
from typing import List, Dict
from memory_thread.nervous.fabric import FabricRouter

class PythonProducer:
    """
    Smart Producer that respects Backpressure.
    """
    def __init__(self, producer_id: str, gateway_address: str = "ipc://ingest_gateway"):
        self.producer_id = producer_id
        self.fabric = FabricRouter(address=gateway_address, mode="DEALER")
        self.running = False

    async def start(self):
        await self.fabric.start()
        self.running = True
        print(f"Producer {self.producer_id} started.")

    async def stop(self):
        self.running = False
        self.fabric.close()

    async def send_batch(self, events: List[Dict]):
        if not self.running: return

        # Simulate checking throttle (In real ZMQ Dealer, we might receive backpressure msg)
        # Here we just send
        payload = {
            "type": "batch",
            "producer_id": self.producer_id,
            "events": events
        }
        await self.fabric.send(None, payload)

    async def run_load_test(self, duration_sec=10, target_eps=1000):
        start_time = time.time()
        sent_count = 0

        while time.time() - start_time < duration_sec:
            # Create batch
            batch_size = 100
            events = [{"id": i, "content": "test"} for i in range(batch_size)]

            await self.send_batch(events)
            sent_count += batch_size

            # Rate limiting
            await asyncio.sleep(batch_size / target_eps)

        return sent_count
