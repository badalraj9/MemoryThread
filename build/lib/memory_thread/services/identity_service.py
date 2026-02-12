import uuid
import json
import logging
from typing import List, Optional, Dict
from datetime import datetime

from memory_thread.models.entity import Entity, MergeProposal, EntityMergeLog
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.db.qdrant_client import QdrantClientWrapper
from memory_thread.utils.embeddings import generate_embeddings
from memory_thread.config.settings import settings
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

log = logging.getLogger(__name__)

class IdentityService:
    def __init__(self):
        self.pg = PostgresClient()
        self.qdrant = QdrantClientWrapper()
        # Ensure Qdrant collection for entities exists
        self.collection_name = "entities"
        self._ensure_collection()

    def _ensure_collection(self):
        # This should ideally be in a setup script, but for now we check lazily
        try:
            self.qdrant.client.get_collection(self.collection_name)
        except Exception:
            log.info(f"Collection {self.collection_name} not found, creating...")
            self.qdrant.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "size": settings.EMBEDDING_DIMENSION, 
                    "distance": settings.EMBEDDING_DISTANCE
                }
            )

    def create_entity(self, name: str, entity_type: str, attributes: Dict = {}) -> Entity:
        """
        Creates a new entity in Postgres and indexes it in Qdrant.
        """
        entity = Entity(
            name=name,
            entity_type=entity_type,
            attributes=attributes
        )

        # 1. Postgres Insert
        with self.pg.get_cursor() as cur:
            cur.execute("""
                INSERT INTO entities (id, namespace, entity_type, name, attributes, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(entity.id), entity.namespace, entity.entity_type, entity.name,
                json.dumps(entity.attributes), entity.created_at, entity.updated_at
            ))

        # 2. Embedding & Qdrant Upsert
        # We embed "name: type attributes" for identification
        text_representation = f"{entity.name}: {entity.entity_type} {json.dumps(entity.attributes)}"
        embedding = generate_embeddings(tuple([text_representation]))[0]

        self.qdrant.client.upsert(
            collection_name=self.collection_name,
            points=[{
                "id": str(entity.id),
                "vector": embedding,
                "payload": {
                    "entity_type": entity.entity_type,
                    "name": entity.name,
                    "namespace": entity.namespace
                }
            }]
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
                id=row[0], namespace=row[1], entity_type=row[2], name=row[3],
                attributes=row[4], created_at=row[5], updated_at=row[6], merged_into=row[7]
            )
            for row in rows
        ]

    def get_entity(self, entity_id: uuid.UUID) -> Optional[Entity]:
        with self.pg.get_cursor() as cur:
            cur.execute("SELECT id, namespace, entity_type, name, attributes, created_at, updated_at, merged_into FROM entities WHERE id = %s", (str(entity_id),))
            row = cur.fetchone()

        if not row:
            return None

        return Entity(
            id=row[0], namespace=row[1], entity_type=row[2], name=row[3],
            attributes=row[4], created_at=row[5], updated_at=row[6], merged_into=row[7]
        )

    def scan_duplicates(self, entity_type: str, threshold: float = 0.95) -> List[MergeProposal]:
        """
        Scans active entities of a given type for duplicates using vector similarity.
        """
        entities = self.list_entities(entity_type)
        proposals = []
        processed_ids = set()

        for entity in entities:
            if entity.id in processed_ids:
                continue

            # Retrieve embedding from Qdrant (or re-compute if missing, but let's assume sync)
            # Efficient way: search in Qdrant for nearest neighbors of THIS entity's vector
            # But we don't have the vector locally. We can get it from Qdrant by ID.

            try:
                points = self.qdrant.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[str(entity.id)],
                    with_vectors=True
                )
                if not points:
                    continue
                vector = points[0].vector
            except Exception as e:
                log.error(f"Failed to retrieve vector for {entity.id}: {e}")
                continue

            # Search for similar
            search_result = self.qdrant.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="entity_type", match=MatchValue(value=entity_type)),
                        # Ideally filter out self, but Qdrant returns self.
                    ]
                ),
                score_threshold=threshold,
                limit=5
            )

            for hit in search_result:
                target_id = uuid.UUID(hit.id)
                if target_id == entity.id:
                    continue

                if target_id in processed_ids:
                    continue

                # Found a potential duplicate
                target_entity = self.get_entity(target_id)
                if not target_entity or target_entity.merged_into:
                    continue # Already merged or missing

                # Fuzzy string check as secondary signal (simple contains/Levenshtein could go here)
                # For now, rely on vector score + string match boost

                reason = f"Vector similarity {hit.score:.4f}"
                if entity.name.lower() == target_entity.name.lower():
                    reason += " + Exact name match"

                # Determine which to keep (Source -> Target).
                # Policy: Keep the older one (Target), merge newer (Source) into it.
                # Unless explicitly handled, let's just pick one consistently.
                if entity.created_at > target_entity.created_at:
                    src, tgt = entity, target_entity
                else:
                    src, tgt = target_entity, entity

                proposal = MergeProposal(
                    source_entity=src,
                    target_entity=tgt,
                    confidence=hit.score,
                    reason=reason
                )
                proposals.append(proposal)
                processed_ids.add(src.id)
                processed_ids.add(tgt.id) # Mark both as processed for this pass to avoid duplicate pairs

        return proposals

    def execute_merge(self, proposal: MergeProposal):
        """
        Executes the merge: marks source as merged_into target, logs the merge.
        Does NOT delete source.
        """
        # 1. Update Source Entity
        with self.pg.get_cursor() as cur:
            cur.execute("""
                UPDATE entities
                SET merged_into = %s, updated_at = NOW()
                WHERE id = %s
            """, (str(proposal.target_entity.id), str(proposal.source_entity.id)))

            # 2. Log Merge
            cur.execute("""
                INSERT INTO entity_merges (source_entity_id, target_entity_id, confidence, reason)
                VALUES (%s, %s, %s, %s)
            """, (
                str(proposal.source_entity.id),
                str(proposal.target_entity.id),
                proposal.confidence,
                proposal.reason
            ))

        # 3. Update Qdrant?
        # We might want to remove the source from search results or mark it.
        # Simplest: Delete source from Qdrant 'entities' collection so it's not found in future scans.
        self.qdrant.client.delete(
            collection_name=self.collection_name,
            points_selector=[str(proposal.source_entity.id)]
        )

        log.info(f"Merged {proposal.source_entity.name} into {proposal.target_entity.name}")
