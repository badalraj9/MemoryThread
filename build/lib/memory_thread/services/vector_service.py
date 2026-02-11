import logging
import os
from typing import List
from qdrant_client import QdrantClient, models
from memory_thread.models.memory_object import MemoryObject
from memory_thread.db.qdrant_client import get_qdrant_client
from memory_thread.db.qdrant_setup import COLLECTION_NAME

log = logging.getLogger(__name__)

def store_vectors(memory_objects: List[MemoryObject]):
    client = get_qdrant_client()
    points = [
        models.PointStruct(
            id=str(obj.id),
            vector=obj.embedding,
            payload={
                "memory_type": obj.memory_type, "importance": obj.importance,
                "entities": obj.entities, "topics": obj.topics,
                "metadata": obj.metadata.dict()
            }
        ) for obj in memory_objects if obj.embedding
    ]
    if not points: return
    client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
    log.info(f"Stored batch of {len(points)} vectors in Qdrant.")

def search_vectors(embedding: List[float], top_k: int = 20):
    client = get_qdrant_client()
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        limit=top_k,
        with_payload=True,
        with_vectors=False
    )

    return [(hit.id, hit.score) for hit in results.points]
