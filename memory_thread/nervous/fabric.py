import zmq
import zmq.asyncio
import json
import asyncio
from typing import Dict, Any, Optional, Tuple
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class FabricRouter:
    """
    ZMQ Router/Dealer Fabric for distributed ingestion.
    Replaces PUSH/PULL to allow bidirectional backpressure control.
    """
    def __init__(self, context=None, address="ipc://fabric_router", mode="ROUTER"):
        self.context = context or zmq.asyncio.Context()
        self.address = address
        self.mode = mode
        self.socket = None
        self.running = False

    async def start(self):
        if self.mode == "ROUTER":
            self.socket = self.context.socket(zmq.ROUTER)
            self.socket.bind(self.address)
            log.info(f"Fabric ROUTER bound to {self.address}")
        elif self.mode == "DEALER":
            self.socket = self.context.socket(zmq.DEALER)
            self.socket.connect(self.address)
            log.info(f"Fabric DEALER connected to {self.address}")
        else:
            raise ValueError("Invalid mode. Use ROUTER or DEALER.")
        self.running = True

    async def send(self, identity: bytes, message: Dict[str, Any]):
        """Send message to specific identity (ROUTER) or to server (DEALER)."""
        if not self.running: return
        try:
            msg_bytes = json.dumps(message).encode('utf-8')
            if self.mode == "ROUTER":
                await self.socket.send_multipart([identity, b"", msg_bytes])
            else:
                await self.socket.send(msg_bytes)
        except Exception as e:
            log.error(f"Fabric Send Error: {e}")

    async def receive(self) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """
        Returns (identity, message_dict).
        If DEALER, identity is None.
        """
        if not self.running: return None
        try:
            if self.mode == "ROUTER":
                frames = await self.socket.recv_multipart()
                # ROUTER usually receives [identity, message] from DEALER
                # Or [identity, empty, message] if REQ/REP pattern emulation
                if len(frames) == 2:
                    identity, msg_bytes = frames
                elif len(frames) == 3:
                    identity, _, msg_bytes = frames
                else:
                    log.error(f"Unexpected ZMQ frames: {len(frames)}")
                    return None
                return identity, json.loads(msg_bytes)
            else:
                msg_bytes = await self.socket.recv()
                return None, json.loads(msg_bytes)
        except Exception as e:
            log.error(f"Fabric Receive Error: {e}")
            return None

    def close(self):
        self.running = False
        if self.socket:
            self.socket.close()

class KafkaMirror:
    """
    Async Kafka Producer to mirror all events for durability.
    Mocks behavior if no broker available.
    """
    def __init__(self, bootstrap_servers="localhost:9092", topic="memory_events"):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer = None
        self.mock_mode = False

    async def start(self):
        try:
            from aiokafka import AIOKafkaProducer
            self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
            await self.producer.start()
            log.info(f"Kafka Mirror connected to {self.bootstrap_servers}")
        except Exception as e:
            log.warning(
                f"Kafka connection failed ({e}). Switching to MOCK mode. "
                f"WARNING: Events will NOT be durably persisted to Kafka! "
                f"This is acceptable for development but NOT for production."
            )
            self.mock_mode = True

    async def mirror(self, event: Dict[str, Any]):
        if self.mock_mode:
            # log.debug("Mock Kafka Mirror: Event persisted.")
            return

        try:
            key = event.get("object_id", "default").encode('utf-8')
            value = json.dumps(event).encode('utf-8')
            await self.producer.send_and_wait(self.topic, value=value, key=key)
        except Exception as e:
            log.error(f"Kafka Mirror Error: {e}")

    async def stop(self):
        if self.producer and not self.mock_mode:
            await self.producer.stop()
