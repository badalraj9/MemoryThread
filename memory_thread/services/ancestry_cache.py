import uuid
import hashlib
import json
from typing import List, Dict, Optional, Set
from memory_thread.models.events import Event
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class AncestryCache:
    """
    Caches causal chains (Ancestry Fingerprints) to speed up provenance queries.
    Stores fingerprints in an in-memory dictionary (simulating Redis).
    """
    def __init__(self):
        # In-memory cache: fingerprint_hash -> List[event_ids]
        self.fingerprints: Dict[str, List[str]] = {}
        # Entity -> Latest fingerprint
        self.entity_fingerprints: Dict[str, str] = {}
        self.pg = PostgresClient()

    def _compute_fingerprint(self, event_ids: List[str]) -> str:
        """Computes a deterministic hash of a list of event IDs."""
        sorted_ids = sorted(event_ids)
        serialized = ",".join(sorted_ids)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def update_ancestry(self, event: Event):
        """
        Updates the ancestry cache for a new event.
        Logic: Ancestry(E) = Ancestry(Parent) + {Parent}
        """
        # For simple linear chains (Phase 3/4 model): Parent is the previous event on this object.
        # We need to find the parent.
        # Check 'antecedents' field.

        parent_ids = [str(uid) for uid in event.antecedents]
        new_ancestry_ids = set(parent_ids)

        # Resolve parent ancestries from cache
        for pid in parent_ids:
            # This requires looking up the fingerprint of the parent event
            # We don't track event->fingerprint map globally in this simple dict.
            # We might need to query DB if not in cache.
            pass

        # Simplified for Prototype:
        # Load full history for entity, compute chain.
        # This is what we are trying to avoid, but for "Update" we might need it once.
        # Or: maintain "Current Tip Ancestry" for entity.

        entity_id = str(event.object_id)
        current_fp = self.entity_fingerprints.get(entity_id)

        current_chain = []
        if current_fp and current_fp in self.fingerprints:
            current_chain = self.fingerprints[current_fp]

        # Append new event
        new_chain = current_chain + [str(event.id)]
        new_fp = self._compute_fingerprint(new_chain)

        self.fingerprints[new_fp] = new_chain
        self.entity_fingerprints[entity_id] = new_fp

        # log.debug(f"Updated ancestry for {entity_id}: {new_fp[:8]} ({len(new_chain)} events)")

    def get_ancestry(self, entity_id: uuid.UUID) -> List[str]:
        """Returns the full list of event IDs leading to the current state."""
        eid = str(entity_id)
        fp = self.entity_fingerprints.get(eid)
        if fp:
            return self.fingerprints.get(fp, [])
        return []

    def rebuild_cache(self, entity_id: uuid.UUID):
        """
        Rebuilds the ancestry cache from DB for an entity.
        """
        with self.pg.get_cursor() as cur:
            cur.execute("""
                SELECT id FROM events WHERE object_id = %s ORDER BY timestamp ASC
            """, (str(entity_id),))
            rows = cur.fetchall()

        chain = [str(r['id']) for r in rows]
        fp = self._compute_fingerprint(chain)

        self.fingerprints[fp] = chain
        self.entity_fingerprints[str(entity_id)] = fp
        log.info(f"Rebuilt ancestry cache for {entity_id}: {len(chain)} events")
