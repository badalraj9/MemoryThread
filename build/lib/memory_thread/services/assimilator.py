import uuid
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict

from memory_thread.models.events import Event, ActionEnum, ActorEnum
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class AssimilatorService:
    def __init__(self):
        self.pg = PostgresClient()

    def detect_patterns(self, entity_id: uuid.UUID, window_days: int = 30) -> List[List[Event]]:
        """
        Finds groups of events that are candidates for consolidation.
        Strategy: Group by (actor, action) within the time window.
        """
        cutoff_date = datetime.now() - timedelta(days=window_days)

        with self.pg.get_cursor() as cur:
            # Fetch active events (not yet consolidated) for the entity
            cur.execute("""
                SELECT id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector
                FROM events
                WHERE object_id = %s
                  AND timestamp > %s
                  AND consolidated_into IS NULL
                ORDER BY timestamp ASC
            """, (str(entity_id), cutoff_date))

            rows = cur.fetchall()

        events = [
            Event(
                id=row[0], namespace=row[1], timestamp=row[2], actor=row[3],
                action=row[4], object_id=row[5], delta=row[6],
                antecedents=row[7], truth_vector=row[8]
            )
            for row in rows
        ]

        # Grouping logic
        # Simple heuristic: Group sequential events of same (actor, action)
        groups = []
        if not events:
            return groups

        current_group = [events[0]]

        for i in range(1, len(events)):
            prev = current_group[-1]
            curr = events[i]

            # Rules for grouping:
            # 1. Same Actor
            # 2. Same Action
            # 3. Same Keys in Delta (structural similarity)
            # 4. Time proximity? (Optional, but "daily" is in requirements)

            is_same_structure = (
                prev.actor == curr.actor and
                prev.action == curr.action and
                set(prev.delta.keys()) == set(curr.delta.keys())
            )

            if is_same_structure:
                current_group.append(curr)
            else:
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [curr]

        if len(current_group) > 1:
            groups.append(current_group)

        return groups

    def consolidate_events(self, events: List[Event]) -> Optional[Event]:
        """
        Merges a list of events into a single summary event.
        """
        if not events:
            return None

        first = events[0]
        last = events[-1]

        # 1. Aggregate Delta
        # Strategy:
        # - Numeric: Sum
        # - Strings: Keep Last? Or List?
        # - Lists: Extend?

        consolidated_delta = {}
        for key, val in first.delta.items():
            values = [e.delta.get(key) for e in events]

            if all(isinstance(v, (int, float)) for v in values):
                consolidated_delta[key] = sum(values)
            elif all(isinstance(v, str) for v in values):
                # For strings, if they are identical, keep one. If diff, maybe "various"?
                # But requirement says "State changes: Keep only final state"
                consolidated_delta[key] = values[-1]
            else:
                # Fallback to last value (State update logic)
                consolidated_delta[key] = values[-1]

        # 2. Create Summary Event
        # Provenance: All source IDs go into 'antecedents'
        source_ids = [e.id for e in events]

        # Action might change? "ADD" x 10 -> "ADD" (sum)
        # If action was UPDATE, it remains UPDATE.

        summary_event = Event(
            id=uuid.uuid4(),
            namespace=first.namespace,
            timestamp=datetime.now(), # Consolidated at NOW
            actor=ActorEnum.SYSTEM, # System performed the consolidation
            action=first.action, # Keep original action type? Or make specific CONSOLIDATE action?
                                 # Keeping original allows replay to work similarly (e.g. adding 100 instead of 10x10)
            object_id=first.object_id,
            delta=consolidated_delta,
            antecedents=source_ids,
            truth_vector=first.truth_vector # Inherit from first? Or average?
                                            # Requirement: "Repeated facts: Merge... with increased corroboration"
                                            # For now, simplistic: take the first one's truth.
        )

        # Add metadata about consolidation
        # Since 'delta' is the payload, we shouldn't pollute it with metadata if it breaks schema.
        # But we don't have a separate metadata field on Event model in code (schema has it? No, schema has delta).
        # We can add a specialized field in delta or rely on the fact that actor=SYSTEM implies maintenance.

        return summary_event

    def execute_consolidation(self, summary_event: Event, source_events: List[Event]):
        """
        Writes the summary event and marks source events as consolidated.
        """
        with self.pg.get_cursor() as cur:
            # 1. Insert Summary Event
            cur.execute("""
                INSERT INTO events (id, namespace, timestamp, actor, action, object_id, delta, antecedents, truth_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(summary_event.id), summary_event.namespace, summary_event.timestamp,
                summary_event.actor.value, summary_event.action.value, str(summary_event.object_id),
                json.dumps(summary_event.delta),
                [str(uid) for uid in summary_event.antecedents], # Postgres array of UUIDs
                summary_event.truth_vector.model_dump_json()
            ))

            # 2. Update Source Events
            source_ids = [str(e.id) for e in source_events]
            cur.execute("""
                UPDATE events
                SET consolidated_into = %s
                WHERE id = ANY(%s)
            """, (str(summary_event.id), source_ids))

        log.info(f"Consolidated {len(source_events)} events into {summary_event.id}")
