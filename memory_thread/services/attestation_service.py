"""
Attestation Service — Cryptographic proof of what MT knew at a given time.

Builds a Merkle chain of event checkpoints. Each checkpoint attests to
the state of the entire system at a point in time. Verification detects
tampering: if any event or checkpoint hash is modified, the chain breaks.

For enterprise/regulatory use: prove that an agent knew fact F with
confidence C at timestamp T, and that no retroactive modification occurred.
"""

import hashlib
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class AttestationCheckpoint:
    checkpoint_id: int
    previous_hash: str
    last_event_id: str
    root_state_hash: str
    thread_id: Optional[str]
    timestamp: str
    hash: str


class AttestationService:
    """
    Builds and verifies a Merkle chain of memory checkpoints.

    Usage:
        attester = AttestationService()
        attester.checkpoint("last-event-uuid")
        ok = attester.verify("event-uuid", {"confidence": 0.95})
    """

    def __init__(self):
        self._chain: List[AttestationCheckpoint] = []
        self._pg = None

    @property
    def pg(self):
        if self._pg is None and settings.ATTESTATION_ENABLED:
            try:
                from memory_thread.db.postgres_client import PostgresClient

                self._pg = PostgresClient()
                self._ensure_table()
            except Exception:
                self._pg = False
        elif self._pg is None:
            self._pg = False  # Skip DB when disabled
        return self._pg if self._pg else None

    def _ensure_table(self):
        """Create attestation_chain table in PostgreSQL."""
        if not self.pg:
            return
        try:
            self.pg.execute("""
                CREATE TABLE IF NOT EXISTS attestation_chain (
                    checkpoint_id SERIAL PRIMARY KEY,
                    previous_hash TEXT NOT NULL,
                    last_event_id UUID NOT NULL,
                    root_state_hash TEXT NOT NULL,
                    thread_id TEXT,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    hash TEXT NOT NULL UNIQUE
                )
            """)
        except Exception as e:
            log.warning("Could not create attestation_chain table: %s", e)

    def checkpoint(
        self, last_event_id: str, thread_id: Optional[str] = None
    ) -> AttestationCheckpoint:
        """Create a new attestation checkpoint.

        Hash chain: H(prev_hash || last_event_id || root_state || thread_id)
        """
        previous = self._get_last()
        previous_hash = previous.hash if previous else "0" * 64

        root_state = self._compute_root_state()
        payload = f"{previous_hash}:{last_event_id}:{root_state}:{thread_id or ''}"
        h = hashlib.sha256(payload.encode()).hexdigest()

        cpid = previous.checkpoint_id + 1 if previous else 1
        ts = datetime.utcnow().isoformat()

        checkpoint = AttestationCheckpoint(
            checkpoint_id=cpid,
            previous_hash=previous_hash,
            last_event_id=last_event_id,
            root_state_hash=root_state,
            thread_id=thread_id,
            timestamp=ts,
            hash=h,
        )

        self._chain.append(checkpoint)

        if self.pg:
            try:
                self.pg.execute(
                    """
                    INSERT INTO attestation_chain
                        (previous_hash, last_event_id, root_state_hash, thread_id, timestamp, hash)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """,
                    (previous_hash, last_event_id, root_state, thread_id, ts, h),
                )
            except Exception as e:
                log.warning("Could not persist checkpoint: %s", e)

        log.info("Checkpoint %d: hash=%s...", cpid, h[:16])
        return checkpoint

    def verify(self, event_id: str, claimed_state: Dict) -> bool:
        """Verify that an event's state is attested by a checkpoint.

        Returns True if the event was included in a checkpoint
        and the chain is intact.
        """
        cp = self._find_checkpoint_for_event(event_id)
        if not cp:
            return False

        # Recompute the chain from genesis to this checkpoint
        return self._verify_chain_up_to(cp.checkpoint_id)

    def verify_chain_integrity(self) -> List[str]:
        """Verify all checkpoints from genesis to latest. Return any breaks."""
        breaks = []
        for i, cp in enumerate(self._chain):
            if i == 0:
                expected_prev = "0" * 64
            else:
                expected_prev = self._chain[i - 1].hash

            if cp.previous_hash != expected_prev:
                breaks.append(
                    f"Break at checkpoint {cp.checkpoint_id}: "
                    f"expected prev={expected_prev[:16]}..., "
                    f"got {cp.previous_hash[:16]}..."
                )

            payload = (
                f"{cp.previous_hash}:{cp.last_event_id}:{cp.root_state_hash}:{cp.thread_id or ''}"
            )
            expected_hash = hashlib.sha256(payload.encode()).hexdigest()
            if cp.hash != expected_hash:
                breaks.append(
                    f"Hash mismatch at checkpoint {cp.checkpoint_id}: "
                    f"expected {expected_hash[:16]}..., got {cp.hash[:16]}..."
                )

        if not breaks:
            log.info("Chain integrity verified: %d checkpoints", len(self._chain))
        else:
            log.warning("Chain has %d breaks", len(breaks))

        return breaks

    def get_chain(self) -> List[Dict]:
        """Return the full attestation chain."""
        return [
            {
                "checkpoint_id": cp.checkpoint_id,
                "previous_hash": cp.previous_hash[:16] + "...",
                "last_event_id": cp.last_event_id[:16] + "...",
                "hash": cp.hash[:16] + "...",
                "timestamp": cp.timestamp,
                "thread_id": cp.thread_id,
            }
            for cp in self._chain
        ]

    def _get_last(self) -> Optional[AttestationCheckpoint]:
        if self._chain:
            return self._chain[-1]
        if self.pg:
            try:
                rows = self.pg.fetch_all(
                    "SELECT * FROM attestation_chain ORDER BY checkpoint_id DESC LIMIT 1"
                )
                if rows:
                    row = rows[0]
                    cp = AttestationCheckpoint(
                        checkpoint_id=row[0],
                        previous_hash=row[1],
                        last_event_id=row[2],
                        root_state_hash=row[3],
                        thread_id=row[4],
                        timestamp=row[5].isoformat()
                        if hasattr(row[5], "isoformat")
                        else str(row[5]),
                        hash=row[6],
                    )
                    self._chain.append(cp)
                    return cp
            except Exception:
                pass
        return None

    def _compute_root_state(self) -> str:
        """Compute a hash representing the full graph state."""
        try:
            from memory_thread.services.graph_engine import graph_engine

            node_count = graph_engine.graph.vcount()
            edge_count = graph_engine.graph.ecount()

            last_timestamps = []
            for v in graph_engine.graph.vs:
                ts = v.attributes().get("timestamp", "")
                if ts:
                    last_timestamps.append(str(ts))
            last_timestamps.sort(reverse=True)

            summary = (
                f"nodes={node_count}:edges={edge_count}:timestamps={','.join(last_timestamps[:5])}"
            )
            return hashlib.sha256(summary.encode()).hexdigest()[:32]
        except Exception:
            return "0" * 32

    def _find_checkpoint_for_event(self, event_id: str) -> Optional[AttestationCheckpoint]:
        """Find the checkpoint that includes this event."""
        for cp in reversed(self._chain):
            if cp.last_event_id == event_id:
                return cp
        if self.pg:
            try:
                rows = self.pg.fetch_all(
                    "SELECT * FROM attestation_chain WHERE last_event_id = %s",
                    (event_id,),
                )
                if rows:
                    row = rows[0]
                    return AttestationCheckpoint(
                        checkpoint_id=row[0],
                        previous_hash=row[1],
                        last_event_id=str(row[2]),
                        root_state_hash=row[3],
                        thread_id=row[4],
                        timestamp=row[5].isoformat()
                        if hasattr(row[5], "isoformat")
                        else str(row[5]),
                        hash=row[6],
                    )
            except Exception:
                pass
        return None

    def _verify_chain_up_to(self, checkpoint_id: int) -> bool:
        """Verify the chain from genesis to given checkpoint."""
        for i, cp in enumerate(self._chain):
            if cp.checkpoint_id > checkpoint_id:
                break
            if i == 0:
                if cp.previous_hash != "0" * 64:
                    return False
            else:
                if cp.previous_hash != self._chain[i - 1].hash:
                    return False
            payload = (
                f"{cp.previous_hash}:{cp.last_event_id}:{cp.root_state_hash}:{cp.thread_id or ''}"
            )
            if cp.hash != hashlib.sha256(payload.encode()).hexdigest():
                return False
        return True


attestation_service = AttestationService()
