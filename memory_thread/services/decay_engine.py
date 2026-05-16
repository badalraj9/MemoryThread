import logging
import math
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from memory_thread.config.settings import settings
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


def _get_topology_factor(entity_id: str) -> float:
    """Hub/bridge nodes get slower decay rates."""
    try:
        from memory_thread.services.graph_engine import graph_engine

        if not graph_engine.is_built:
            return 0.0
        centrality = graph_engine.centrality(entity_id)
        bridge = graph_engine.bridge_score(entity_id)
        return min(1.0, (centrality * 2 + bridge * 3) / 5)
    except Exception:
        return 0.0


# Decay Rates (Lambda) per type
RATES = {
    "fact": 0.001,  # Very slow
    "preference": 0.01,  # Medium
    "event": 0.1,  # Fast
    "prediction": 0.5,  # Very fast
    "identity": 0.0,  # Never decay
}


class DecayEngine:
    def __init__(self):
        self.pg = PostgresClient()

    def calculate_freshness(
        self,
        current_freshness: float,
        days_elapsed: float,
        memory_type: str,
        entity_id: Optional[str] = None,
    ) -> float:
        """
        freshness(t) = freshness_0 * e^(-lambda * t)
        When DECAY_USE_TOPOLOGY=True, hub/bridge nodes decay slower
        (lambda reduced by up to DECAY_TOPOLOGY_SLOW_FACTOR).
        """
        rate = RATES.get(memory_type, 0.02)

        if settings.DECAY_USE_TOPOLOGY and entity_id and rate > 0:
            topology_factor = _get_topology_factor(entity_id)
            rate = rate * (1 - topology_factor * settings.DECAY_TOPOLOGY_SLOW_FACTOR)
            rate = max(rate, 0.0001)

        if rate == 0:
            return 1.0

        return max(0.01, current_freshness * math.exp(-rate * days_elapsed))

    def update_freshness(self, simulate: bool = False):
        """
        Updates freshness for all entities based on time since last update.
        If simulate is True, returns stats but doesn't commit.
        """
        stats = {"updated": 0, "stale": 0}

        # We need to process in batches to avoid locking everything
        # For simplicity in this implementation, we fetch all active states
        # Ideally, we should add a 'last_decay_update' column to avoid re-decaying same day.
        # But let's assume this runs once a day.

        # We need memory type. It's in 'entities' table, but 'entity_state' doesn't have it directly.
        # We need a JOIN.

        query = """
            SELECT es.entity_id, es.truth_vector, e.entity_type, es.updated_at
            FROM entity_state es
            JOIN entities e ON es.entity_id = e.id
            WHERE es.status = 'active'
        """

        updates = []

        with self.pg.get_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

            now = datetime.now()

            for row in rows:
                entity_id = row[0]
                tv = row[1]
                m_type = row[2] or "other"
                last_update = row[3]  # This is when state was updated.
                # Ideally decay is based on time since last 'reinforcement'.
                # Let's use last_update as proxy for now.

                if isinstance(last_update, str):
                    last_update = datetime.fromisoformat(last_update)
                if last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=None)

                days_elapsed = (now - last_update).total_seconds() / 86400.0

                if days_elapsed < 1.0:
                    continue  # Skip if less than a day

                current_freshness = tv.get("freshness", 1.0)
                new_freshness = self.calculate_freshness(current_freshness, days_elapsed, m_type)

                if abs(new_freshness - current_freshness) < 0.01:
                    continue  # Optimization: skip negligible changes

                tv["freshness"] = round(new_freshness, 4)

                # Recalculate generic score if needed, but TV is the source.

                updates.append((json.dumps(tv), str(entity_id)))
                stats["updated"] += 1
                if new_freshness < 0.1:
                    stats["stale"] += 1

            if not simulate and updates:
                from psycopg2.extras import execute_batch

                execute_batch(
                    cur,
                    """
                    UPDATE entity_state
                    SET truth_vector = %s::jsonb
                    WHERE entity_id = %s
                """,
                    updates,
                )

        return stats
