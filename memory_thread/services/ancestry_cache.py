import uuid
import hashlib
import json
from typing import List, Dict, Optional, Set
from datetime import datetime

from memory_thread.models.events import Event
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class AncestryCache:
    """
    Caches causal chains (Ancestry Fingerprints) to speed up provenance queries.
    Stores fingerprints in Postgres for persistence, with in-memory dict as warm cache.
    """

    def __init__(self):
        self.fingerprints: Dict[str, List[str]] = {}
        self.entity_fingerprints: Dict[str, str] = {}
        self.event_to_entity: Dict[str, str] = {}
        self.pg = PostgresClient()
        self._load_from_db()

    def _load_from_db(self):
        """Load existing fingerprints from DB into memory dict as warm cache."""
        try:
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    SELECT entity_id, fingerprint_hash, event_chain
                    FROM ancestry_cache
                """)
                rows = cur.fetchall()

            for row in rows:
                entity_id = row["entity_id"]
                fingerprint_hash = row["fingerprint_hash"]
                event_chain = row["event_chain"]

                if isinstance(event_chain, str):
                    event_chain = json.loads(event_chain)

                self.fingerprints[fingerprint_hash] = event_chain
                self.entity_fingerprints[str(entity_id)] = fingerprint_hash

                for event_id in event_chain:
                    self.event_to_entity[event_id] = str(entity_id)

            log.info(f"Loaded {len(self.entity_fingerprints)} ancestry caches from database")
        except Exception as e:
            log.warning(f"Could not load ancestry cache from DB: {e}")

    def _compute_fingerprint(self, event_ids: List[str]) -> str:
        """Computes a deterministic hash of a list of event IDs."""
        sorted_ids = sorted(event_ids)
        serialized = ",".join(sorted_ids)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _persist_to_db(self, entity_id: str, fingerprint_hash: str, event_chain: List[str]):
        """Persist ancestry cache to Postgres."""
        try:
            with self.pg.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ancestry_cache (entity_id, fingerprint_hash, event_chain, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (entity_id) DO UPDATE SET
                        fingerprint_hash = EXCLUDED.fingerprint_hash,
                        event_chain = EXCLUDED.event_chain,
                        updated_at = EXCLUDED.updated_at
                """,
                    (entity_id, fingerprint_hash, json.dumps(event_chain), datetime.utcnow()),
                )
        except Exception as e:
            log.warning(f"Could not persist ancestry cache to DB: {e}")

    def update_ancestry(self, event: Event):
        """
        Updates the ancestry cache for a new event.
        Logic: Ancestry(E) = Ancestry(Parent) + {Parent}
        """
        parent_ids = [str(uid) for uid in event.antecedents]
        entity_id = str(event.object_id)

        resolved_ancestry: List[str] = []

        for pid in parent_ids:
            parent_entity = self.event_to_entity.get(pid)
            if parent_entity:
                parent_fp = self.entity_fingerprints.get(parent_entity)
                if parent_fp and parent_fp in self.fingerprints:
                    resolved_ancestry.extend(self.fingerprints[parent_fp])

        current_chain = resolved_ancestry.copy()

        existing_fp = self.entity_fingerprints.get(entity_id)
        if existing_fp and existing_fp in self.fingerprints:
            current_chain = self.fingerprints[existing_fp]

        new_chain = current_chain + [str(event.id)]
        new_fp = self._compute_fingerprint(new_chain)

        self.fingerprints[new_fp] = new_chain
        self.entity_fingerprints[entity_id] = new_fp
        self.event_to_entity[str(event.id)] = entity_id

        self._persist_to_db(entity_id, new_fp, new_chain)

        log.debug(f"Updated ancestry for {entity_id}: {new_fp[:8]} ({len(new_chain)} events)")

    def get_ancestry(self, entity_id: uuid.UUID) -> List[str]:
        """Returns the full list of event IDs leading to the current state."""
        eid = str(entity_id)
        fp = self.entity_fingerprints.get(eid)
        if fp:
            return self.fingerprints.get(fp, [])
        return []

    def rebuild_cache(self, entity_id: uuid.UUID):
        """Rebuilds the ancestry cache from DB for an entity."""
        with self.pg.get_cursor() as cur:
            cur.execute(
                """
                SELECT id FROM events WHERE object_id = %s ORDER BY timestamp ASC
            """,
                (str(entity_id),),
            )
            rows = cur.fetchall()

        chain = [str(r["id"]) for r in rows]
        fp = self._compute_fingerprint(chain)

        self.fingerprints[fp] = chain
        self.entity_fingerprints[str(entity_id)] = fp

        for event_id in chain:
            self.event_to_entity[event_id] = str(entity_id)

        self._persist_to_db(str(entity_id), fp, chain)

        log.info(f"Rebuilt ancestry cache for {entity_id}: {len(chain)} events")

    def get_fingerprint(self, entity_id: uuid.UUID) -> Optional[str]:
        """Get the current fingerprint for an entity."""
        return self.entity_fingerprints.get(str(entity_id))

    def get_event_chain(self, entity_id: uuid.UUID) -> List[str]:
        """Get the full event chain for an entity."""
        return self.get_ancestry(entity_id)


ancestry_cache = AncestryCache()
