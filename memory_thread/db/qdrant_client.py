"""
Qdrant Client Wrapper for Memory Thread.

Provides a unified interface for Qdrant operations with graceful fallbacks.
"""
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient as BaseQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from memory_thread.config.settings import settings


def get_qdrant_client() -> BaseQdrantClient:
    """Get a Qdrant client instance."""
    return BaseQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


class QdrantClientWrapper:
    """Wrapper around Qdrant client with convenience methods."""
    
    def __init__(self):
        self.client = get_qdrant_client()
    
    def create_collection_if_not_exists(self, collection_name: str, vector_size: int = 384):
        """Create a collection if it doesn't exist."""
        try:
            self.client.get_collection(collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
    
    def upsert(self, collection_name: str, points: List[Dict[str, Any]]):
        """Upsert points into a collection."""
        qdrant_points = []
        for p in points:
            qdrant_points.append(PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {})
            ))
        self.client.upsert(collection_name=collection_name, points=qdrant_points)
    
    def search(self, collection_name: str, query_vector: List[float], limit: int = 5) -> List[Any]:
        """Search for similar vectors."""
        try:
            return self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit
            )
        except Exception:
            return []


# Alias for backward compatibility
QdrantClient = QdrantClientWrapper
