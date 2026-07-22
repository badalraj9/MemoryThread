"""Tests for SSE event bus."""

import json
import queue
import pytest
from memory_thread.services.event_bus import event_bus


class TestEventBus:
    def setup_method(self):
        event_bus._subscribers.clear()

    def test_subscribe_and_publish(self):
        q = event_bus.subscribe()
        assert event_bus.subscriber_count == 1

        event_bus.publish_sync("test_event", {"key": "value"})
        msg = q.get(timeout=1)
        parsed = json.loads(msg)
        assert parsed["type"] == "test_event"
        assert parsed["data"]["key"] == "value"

    def test_multiple_subscribers(self):
        q1 = event_bus.subscribe()
        q2 = event_bus.subscribe()
        assert event_bus.subscriber_count == 2

        event_bus.publish_sync("multi", {"n": 1})
        m1 = json.loads(q1.get(timeout=1))
        m2 = json.loads(q2.get(timeout=1))
        assert m1["type"] == "multi"
        assert m1 == m2

    def test_unsubscribed_queue_not_receiving(self):
        q = event_bus.subscribe()
        event_bus.unsubscribe(q)
        event_bus.publish_sync("after_unsub", {})

        with pytest.raises(queue.Empty):
            q.get(timeout=0.5)

    def test_event_bus_singleton(self):
        from memory_thread.services.event_bus import event_bus as eb2

        assert eb2 is event_bus

    def test_full_queue_doesnt_block_publisher(self):
        small_q = event_bus.subscribe()
        for _ in range(257):
            event_bus.publish_sync("fill", {})
        small_q.get(timeout=0.1)
