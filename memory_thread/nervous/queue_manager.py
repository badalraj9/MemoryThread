import zmq
import multiprocessing as mp
from typing import Optional, Any
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class QueueManager:
    """
    Manages ZeroMQ PUSH/PULL sockets for the persistence pipeline.
    """
    def __init__(self, context=None, address="ipc://persistence_pipe"):
        self.context = context or zmq.Context()
        self.address = address
        self.socket = None
        self.type = None

    def setup_producer(self):
        """Setup PUSH socket (Output from TMS)."""
        self.socket = self.context.socket(zmq.PUSH)
        self.socket.bind(self.address)
        self.type = "PUSH"
        log.info(f"ZMQ PUSH bound to {self.address}")

    def setup_consumer(self):
        """Setup PULL socket (Input to DB Writer)."""
        self.socket = self.context.socket(zmq.PULL)
        self.socket.connect(self.address)
        self.type = "PULL"
        log.info(f"ZMQ PULL connected to {self.address}")

    def send(self, item: Any):
        if self.type != "PUSH": raise RuntimeError("Socket not configured as PUSH")
        self.socket.send_json(item)

    def receive(self, timeout_ms: int = 100) -> Optional[Any]:
        if self.type != "PULL": raise RuntimeError("Socket not configured as PULL")
        if self.socket.poll(timeout_ms):
            return self.socket.recv_json()
        return None

    def close(self):
        if self.socket:
            self.socket.close()
