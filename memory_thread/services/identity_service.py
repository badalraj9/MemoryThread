import uuid
import json
import logging
from typing import List, Optional, Dict
from datetime import datetime

from memory_thread.models.entity import Entity, MergeProposal, EntityMergeLog
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.config.settings import settings

log = logging.getLogger(__name__)


class IdentityService:
    def __init__(self):
        self.pg = PostgresClient()

    def create_entity(self, name: str, entity_type: str, attributes: Dict = {}) -> Entity:
        entity = Entity(name=name, entity_type=entity_type, attributes=attributes)

        with self.pg.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO entities (id, namespace, entity_type, name, attributes, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    str(entity.id),
                    entity.namespace,
                    entity.entity_type,
                    entity.name,
                    json.dumps(entity.attributes),
                    entity.created_at,
                    entity.updated_at,
                ),
            )

        return entity

    def list_entities(self, entity_type: Optional[str] = None) -> List[Entity]:
        query = "SELECT id, namespace, entity_type, name, attributes, created_at, updated_at, merged_into FROM entities WHERE merged_into IS NULL"
        params = []
        if entity_type:
            query += " AND entity_type = %s"
            params.append(entity_type)

        with self.pg.get_cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [
            Entity(
                id=row[0],
                namespace=row[1],
                entity_type=row[2],
                name=row[3],
                attributes=row[4],
                created_at=row[5],
                updated_at=row[6],
                merged_into=row[7],
            )
            for row in rows
        ]

    def get_entity(self, entity_id: uuid.UUID) -> Optional[Entity]:
        with self.pg.get_cursor() as cur:
            cur.execute(
                "SELECT id, namespace, entity_type, name, attributes, created_at, updated_at, merged_into FROM entities WHERE id = %s",
                (str(entity_id),),
            )
            row = cur.fetchone()

        if not row:
            return None

        return Entity(
            id=row[0],
            namespace=row[1],
            entity_type=row[2],
            name=row[3],
            attributes=row[4],
            created_at=row[5],
            updated_at=row[6],
            merged_into=row[7],
        )

    def scan_duplicates(self, entity_type: str, threshold: float = 0.95) -> List[MergeProposal]:
        """
        Scans active entities of a given type for duplicates using name matching.
        Note: Vector similarity has been removed. Uses exact name match only.
        """
        entities = self.list_entities(entity_type)
        proposals = []
        processed_ids = set()

        for entity in entities:
            if entity.id in processed_ids:
                continue

            # Check for exact name duplicates
            for other in entities:
                if other.id == entity.id or other.id in processed_ids:
                    continue
                if entity.name.lower() == other.name.lower():
                    # Determine which to keep (Source -> Target).
                    if entity.created_at > other.created_at:
                        src, tgt = entity, other
                    else:
                        src, tgt = other, entity

                    proposal = MergeProposal(
                        source_entity=src,
                        target_entity=tgt,
                        confidence=1.0,
                        reason="Exact name match",
                    )
                    proposals.append(proposal)
                    processed_ids.add(src.id)
                    processed_ids.add(tgt.id)
                    break  # Only match each entity once

        return proposals

    def execute_merge(self, proposal: MergeProposal):
        """
        Executes the merge: marks source as merged_into target, logs the merge.
        Does NOT delete source.
        """
        # 1. Update Source Entity
        with self.pg.get_cursor() as cur:
            cur.execute(
                """
                UPDATE entities
                SET merged_into = %s, updated_at = NOW()
                WHERE id = %s
            """,
                (str(proposal.target_entity.id), str(proposal.source_entity.id)),
            )

            # 2. Log Merge
            cur.execute(
                """
                INSERT INTO entity_merges (source_entity_id, target_entity_id, confidence, reason)
                VALUES (%s, %s, %s, %s)
            """,
                (
                    str(proposal.source_entity.id),
                    str(proposal.target_entity.id),
                    proposal.confidence,
                    proposal.reason,
                ),
            )

        log.info(f"Merged {proposal.source_entity.name} into {proposal.target_entity.name}")
