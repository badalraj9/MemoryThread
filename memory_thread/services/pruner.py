import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

from memory_thread.db.postgres_client import PostgresClient
from memory_thread.models.events import EntityState
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class PrunerService:
    def __init__(self):
        self.pg = PostgresClient()

    def calculate_pruning_score(self, state: Dict) -> float:
        """
        Calculates a score between 0.0 (prune immediately) and 1.0 (keep forever).
        Factors: Recency, Frequency, Importance (from truth vector).
        """
        now = datetime.now()
        last_accessed = state.get('last_accessed') or now
        access_count = state.get('access_count', 0)

        # Calculate days since last access
        if isinstance(last_accessed, str):
            try:
                last_accessed = datetime.fromisoformat(last_accessed)
            except ValueError:
                last_accessed = now # Fallback

        # If naive datetime, assume local/utc consistent
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=None) # Ensure compatibility with 'now'

        days_idle = (now - last_accessed).days

        # 1. Recency Score (Decays over 90 days)
        recency_score = max(0.0, 1.0 - (days_idle / 90.0))

        # 2. Frequency Score (Logarithmic boost)
        # 0 visits -> 0.0, 10 visits -> 0.5, 100 visits -> 1.0
        import math
        freq_score = min(1.0, math.log(access_count + 1) / math.log(100))

        # 3. Importance (Truth Vector)
        # Using authority or confidence as proxy for importance
        truth_vector = state.get('truth_vector', {})
        importance = truth_vector.get('authority', 0.5)

        # Weighted Sum
        # Recency is king (0.5), Importance (0.3), Frequency (0.2)
        score = (recency_score * 0.5) + (importance * 0.3) + (freq_score * 0.2)

        return score

    def scan_for_pruning(self, threshold: float = 0.3) -> List[Dict]:
        """
        Scans for active states with score below threshold.
        """
        candidates = []
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT entity_id, namespace, current_value, truth_vector, last_event_id, updated_at, status, last_accessed, access_count
                FROM entity_state
                WHERE status = 'active'
            """)
            rows = cur.fetchall()

        for row in rows:
            state = {
                "entity_id": row[0],
                "namespace": row[1],
                "current_value": row[2],
                "truth_vector": row[3],
                "last_accessed": row[7],
                "access_count": row[8]
            }

            score = self.calculate_pruning_score(state)

            if score < threshold:
                state['pruning_score'] = score
                candidates.append(state)

        return candidates

    def prune_states(self, entity_ids: List[str]):
        """
        Marks states as inactive.
        """
        if not entity_ids:
            return

        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entity_state
                SET status = 'inactive'
                WHERE entity_id = ANY(%s)
            """, (entity_ids,))

        log.info(f"Pruned {len(entity_ids)} states.")

    def recover_state(self, entity_id: str):
        """
        Restores a pruned state to active.
        """
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entity_state
                SET status = 'active', last_accessed = NOW()
                WHERE entity_id = %s
            """, (entity_id,))

        log.info(f"Recovered state for {entity_id}")
