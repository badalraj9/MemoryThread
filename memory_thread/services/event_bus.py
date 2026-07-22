"""
Event Bus — sync publish / sync subscribe for real-time graph events.

Simple threading.Queue-based fan-out. The SSE endpoint runs in a
FastAPI thread pool and blocks on queue.get() with a 30s keepalive.
No asyncio bridge needed.
"""

import json
import time
import queue
import threading
from typing import Dict, Any, Set

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class EventBus:
    """Sync-publish / sync-subscribe event bus. FastAPI runs the subscriber in a thread pool."""

    def __init__(self):
        self._subscribers: Set[queue.Queue] = set()
        self._lock = threading.Lock()

    def publish_sync(self, event_type: str, data: Dict[str, Any]):
        payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
        dead: list[queue.Queue] = []
        with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(payload)
                except Exception:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.add(q)
        log.debug("SSE subscriber added (%d total)", len(self._subscribers))
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._subscribers.discard(q)
        log.debug("SSE subscriber removed (%d remaining)", len(self._subscribers))

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton
event_bus = EventBus()
