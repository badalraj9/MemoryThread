"""
Thread Service — groups events into conversation sessions.

Threads are nodes in the graph connected to their events via
'contains' edges. This enables session-aware recall, where
an agent can retrieve full discussion context, not just
individual events.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from memory_thread.services.graph_engine import graph_engine
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Thread:
    thread_id: str
    title: str
    created_by: str
    started_at: str
    status: str  # "active" | "archived"
    event_count: int = 0
    parent_thread_id: Optional[str] = None


@dataclass
class ThreadResult:
    thread: Thread
    events: List[Dict]
    child_threads: List[Thread]


class ThreadService:
    """Creates, queries, and manages conversation threads in the graph."""

    def __init__(self):
        self._pg = None

    @property
    def pg(self):
        if self._pg is None:
            from memory_thread.db.postgres_client import PostgresClient

            self._pg = PostgresClient()
        return self._pg

    def create_thread(
        self, title: str, created_by: str = "USER", parent_thread_id: Optional[str] = None
    ) -> Thread:
        """Create a new thread node in the graph."""
        thread_id = str(uuid.uuid4())

        if thread_id not in {v["name"] for v in graph_engine.graph.vs}:
            graph_engine.graph.add_vertex(
                thread_id,
                type="thread",
                title=title,
                created_by=created_by,
                started_at=datetime.utcnow().isoformat(),
                status="active",
            )

        if parent_thread_id:
            parent = str(parent_thread_id)
            if parent in {v["name"] for v in graph_engine.graph.vs}:
                if not graph_engine.graph.are_adjacent(parent, thread_id):
                    graph_engine.graph.add_edge(parent, thread_id, type="contains")
            thread_result = Thread(
                thread_id=thread_id,
                title=title,
                created_by=created_by,
                started_at=datetime.utcnow().isoformat(),
                status="active",
                parent_thread_id=parent_thread_id,
            )
        else:
            thread_result = Thread(
                thread_id=thread_id,
                title=title,
                created_by=created_by,
                started_at=datetime.utcnow().isoformat(),
                status="active",
            )

        try:
            self.pg.execute(
                """INSERT INTO threads (thread_id, title, created_by, started_at, status, parent_thread_id, session_metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, '{}')
                   ON CONFLICT (thread_id) DO NOTHING""",
                (
                    thread_id,
                    title,
                    created_by,
                    datetime.utcnow().isoformat(),
                    "active",
                    parent_thread_id,
                ),
            )
        except Exception as e:
            log.warning("Failed to persist thread to Postgres: %s", e)

        log.info("Created thread %s: %s", thread_id[:8], title)
        return thread_result

    def get_thread(self, thread_id: str) -> Optional[ThreadResult]:
        """Retrieve a thread with all its events, in order."""
        if not graph_engine._vertex_exists(thread_id):
            return None

        try:
            v = graph_engine.graph.vs.find(name=thread_id)
            vattrs = v.attributes()
            if vattrs.get("type") != "thread":
                return None
        except (ValueError, KeyError):
            return None

        events = []
        child_threads = []
        try:
            vidx = graph_engine.graph.vs.find(name=thread_id).index
            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "contains" and e.source == vidx:
                    target = graph_engine.graph.vs[e.target]
                    tattrs = target.attributes()
                    if tattrs.get("type") == "thread":
                        child_threads.append(
                            Thread(
                                thread_id=target["name"],
                                title=tattrs.get("title", ""),
                                created_by=tattrs.get("created_by", ""),
                                started_at=tattrs.get("started_at", ""),
                                status=tattrs.get("status", "active"),
                                parent_thread_id=thread_id,
                            )
                        )
                    else:
                        events.append(
                            {
                                "event_id": target["name"],
                                "timestamp": tattrs.get("timestamp", ""),
                                "actor": tattrs.get("actor", ""),
                                "action": tattrs.get("action", ""),
                                "content": tattrs.get("content", ""),
                                "truth_confidence": tattrs.get("truth_confidence", 0.5),
                                "truth_authority": tattrs.get("truth_authority", 0.5),
                                "truth_freshness": tattrs.get("truth_freshness", 1.0),
                            }
                        )
            events.sort(key=lambda x: x.get("timestamp", ""))
        except (ValueError, KeyError):
            pass

        child_threads = []
        try:
            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "contains" and e.source == vidx:
                    target = graph_engine.graph.vs[e.target]
                    tattrs = target.attributes()
                    if tattrs.get("type") == "thread":
                        child_threads.append(
                            Thread(
                                thread_id=target["name"],
                                title=tattrs.get("title", ""),
                                created_by=tattrs.get("created_by", ""),
                                started_at=tattrs.get("started_at", ""),
                                status=tattrs.get("status", "active"),
                                parent_thread_id=thread_id,
                            )
                        )
        except (ValueError, KeyError):
            pass

        thread = Thread(
            thread_id=thread_id,
            title=vattrs.get("title", ""),
            created_by=vattrs.get("created_by", ""),
            started_at=vattrs.get("started_at", ""),
            status=vattrs.get("status", "active"),
            event_count=len(events),
        )

        return ThreadResult(thread=thread, events=events, child_threads=child_threads)

    def search_threads(self, query: str) -> List[Thread]:
        """Search threads by title or event content."""
        results = []

        # 1. Title match
        for v in graph_engine.graph.vs:
            vattrs = v.attributes()
            if vattrs.get("type") == "thread":
                title = vattrs.get("title", "")
                if query.lower() in title.lower():
                    results.append(
                        Thread(
                            thread_id=v["name"],
                            title=title,
                            created_by=vattrs.get("created_by", ""),
                            started_at=vattrs.get("started_at", ""),
                            status=vattrs.get("status", "active"),
                        )
                    )

        # 2. Content match (events within threads)
        try:
            for v in graph_engine.graph.vs:
                vattrs = v.attributes()
                if vattrs.get("type") == "thread":
                    thread_id = v["name"]
                    vidx = v.index
                    for e in graph_engine.graph.es:
                        eattrs = e.attributes()
                        if eattrs.get("type") == "contains" and e.source == vidx:
                            target = graph_engine.graph.vs[e.target]
                            content = target.attributes().get("content", "")
                            if query.lower() in str(content).lower():
                                if not any(t.thread_id == thread_id for t in results):
                                    results.append(
                                        Thread(
                                            thread_id=thread_id,
                                            title=vattrs.get("title", ""),
                                            created_by=vattrs.get("created_by", ""),
                                            started_at=vattrs.get("started_at", ""),
                                            status=vattrs.get("status", "active"),
                                        )
                                    )
                                break
        except (ValueError, KeyError):
            pass

        return results[:20]

    def archive_thread(self, thread_id: str) -> bool:
        """Mark a thread as archived."""
        try:
            v = graph_engine.graph.vs.find(name=thread_id)
            v["status"] = "archived"
            return True
        except (ValueError, KeyError):
            return False

    def get_thread_context(self, event_id: str, window: int = 5) -> List[Dict]:
        """Get sibling events around a given event within its thread."""
        try:
            ev = graph_engine.graph.vs.find(name=event_id)
        except (ValueError, KeyError):
            return []

        # Find which thread contains this event
        for e in graph_engine.graph.es:
            eattrs = e.attributes()
            if eattrs.get("type") == "contains" and e.target == ev.index:
                thread_id = graph_engine.graph.vs[e.source]["name"]
                thread = self.get_thread(thread_id)
                if not thread:
                    return []
                evts = thread.events
                for i, evt in enumerate(evts):
                    if evt.get("event_id") == event_id:
                        start = max(0, i - window)
                        end = min(len(evts), i + window + 1)
                        return evts[start:end]
        return []


thread_service = ThreadService()
