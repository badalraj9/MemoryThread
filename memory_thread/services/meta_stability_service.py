import uuid
import json
import math
from typing import Dict, Any, List, Optional
from memory_thread.models.events import EntityState, ActionEnum
from memory_thread.utils.logger import get_logger
from memory_thread.config.settings import settings

log = get_logger(__name__)

ANTONYM_PAIRS = {
    "likes": "hates",
    "prefers": "avoids",
    "loves": "dislikes",
    "happy": "sad",
    "positive": "negative",
    "agrees": "disagrees",
    "supports": "opposes",
    "true": "false",
    "yes": "no",
    "enable": "disable",
    "accept": "reject",
    "trusts": "distrusts",
    "believes": "doubts",
    "accepts": "rejects",
    "approves": "disapproves",
}


class MetaStabilityService:
    def __init__(self):
        self.domain_centroids: Dict[str, List[float]] = {}
        self.drift_threshold = getattr(settings, "DRIFT_THRESHOLD", 0.3)
        self._pg = None

    @property
    def pg(self):
        if self._pg is None:
            from memory_thread.db.postgres_client import PostgresClient

            self._pg = PostgresClient()
        return self._pg

    def _cosine_distance(self, a: List[float], b: List[float]) -> float:
        """Compute cosine distance between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 1.0
        similarity = dot / (norm_a * norm_b)
        return 1.0 - similarity

    def check_drift(self, content: str, domain: str = "general") -> bool:
        """
        Detects semantic drift using cosine distance.
        On first call per domain, stores content embedding as centroid.
        On subsequent calls, computes distance to stored centroid.
        Uses rolling average (0.9 * old + 0.1 * new) to update centroid.
        Returns True when cosine similarity below 0.7 (distance above 0.3).
        """
        from memory_thread.utils.embeddings import embed_text

        embedding = embed_text(content)

        if domain not in self.domain_centroids:
            self.domain_centroids[domain] = embedding
            log.debug(f"Stored centroid for domain: {domain}")
            return False

        centroid = self.domain_centroids[domain]
        distance = self._cosine_distance(embedding, centroid)

        # Rolling average update: 0.9 * old + 0.1 * new
        updated_centroid = [0.9 * c + 0.1 * e for c, e in zip(centroid, embedding)]
        self.domain_centroids[domain] = updated_centroid

        if distance > self.drift_threshold:
            log.warning(
                f"Drift Detected in domain '{domain}': distance={distance:.3f} > threshold={self.drift_threshold}"
            )
            return True

        return False

    def _is_sign_conflict(self, old_val: Any, new_val: Any) -> bool:
        """Check for numeric sign conflict (positive vs negative)."""
        if not isinstance(old_val, (int, float)) or not isinstance(new_val, (int, float)):
            return False
        return (old_val > 0 and new_val < 0) or (old_val < 0 and new_val > 0)

    def _is_semantic_opposite(self, key: str, old_val: Any, new_val: Any) -> bool:
        """Check if key represents semantic opposites based on antonym dict."""
        key_lower = key.lower()
        if key_lower in ANTONYM_PAIRS:
            opposite = ANTONYM_PAIRS[key_lower]
            if isinstance(old_val, str) and isinstance(new_val, str):
                return old_val.lower() == opposite or new_val.lower() == opposite
        for pair_key, pair_val in ANTONYM_PAIRS.items():
            if key_lower == pair_val and isinstance(old_val, str) and isinstance(new_val, str):
                return old_val.lower() == pair_key or new_val.lower() == pair_key
        return False

    def check_contradiction(self, current_state: EntityState, new_delta: Dict[str, Any]) -> bool:
        """
        Checks if the new update logically contradicts the current state.
        Three cases:
        1. Boolean flip (already there)
        2. Numeric sign conflict - positive value replacing negative or vice versa
        3. Semantic opposites - antonym pairs
        """
        for k, v in new_delta.items():
            if k in current_state.current_value:
                curr_val = current_state.current_value[k]

                if isinstance(curr_val, bool) and isinstance(v, bool) and curr_val != v:
                    log.warning(
                        f"Contradiction Detected (boolean flip): {k} changed from {curr_val} to {v}"
                    )
                    return True

                if self._is_sign_conflict(curr_val, v):
                    log.warning(
                        f"Contradiction Detected (sign conflict): {k} changed from {curr_val} to {v}"
                    )
                    return True

                if self._is_semantic_opposite(k, curr_val, v):
                    log.warning(
                        f"Contradiction Detected (semantic opposite): {k} changed from {curr_val} to {v}"
                    )
                    return True
        return False

    def check_integrity(self, state: EntityState) -> bool:
        """
        Validates internal consistency of the state using configurable rules.
        """
        from memory_thread.config.settings import settings

        integrity_rules = getattr(
            settings,
            "INTEGRITY_RULES",
            {
                "tree_count": {"min": 0},
                "age": {"min": 0, "max": 150},
                "confidence": {"min": 0.0, "max": 1.0},
            },
        )

        for field, rules in integrity_rules.items():
            if field in state.current_value:
                value = state.current_value[field]
                if not isinstance(value, (int, float)):
                    continue
                if "min" in rules and value < rules["min"]:
                    log.error(f"Integrity Failure: {field} ({value}) below min ({rules['min']})")
                    return False
                if "max" in rules and value > rules["max"]:
                    log.error(f"Integrity Failure: {field} ({value}) above max ({rules['max']})")
                    return False

        return True

    def check_event_anomaly(self, event_count: int, duration_sec: float) -> bool:
        """
        Rate limiting / Burst detection.
        """
        if duration_sec > 0:
            rate = event_count / duration_sec
            if rate > 5000:
                log.warning(f"Anomaly: Burst rate {rate:.2f} eps detected.")
                return True
        return False

    def update_health_metrics(self, drift_detected: bool, contradiction_detected: bool):
        """
        Updates the singleton tms_health table.
        Creates table if it doesn't exist, then does upsert.
        """
        try:
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tms_health (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        drift_count INTEGER DEFAULT 0,
                        contradiction_count INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT NOW()
                    )
                """)

                cur.execute(
                    """
                    INSERT INTO tms_health (id, drift_count, contradiction_count, last_updated)
                    VALUES (1, 0, 0, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        drift_count = tms_health.drift_count + EXCLUDED.drift_count,
                        contradiction_count = tms_health.contradiction_count + EXCLUDED.contradiction_count,
                        last_updated = NOW()
                """,
                    (1 if drift_detected else 0, 1 if contradiction_detected else 0),
                )

                if drift_detected:
                    log.debug("Updated tms_health: drift_count incremented")
                if contradiction_detected:
                    log.debug("Updated tms_health: contradiction_count incremented")

        except Exception as e:
            log.error(f"Error updating health metrics: {e}")
