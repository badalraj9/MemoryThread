"""
Async Qdrant Client Wrapper for Memory Thread.

Provides an async-first interface for Qdrant operations with:
- AsyncQdrantClient for non-blocking vector operations
- Automatic retry with exponential backoff
- Graceful fallbacks on connection failure
- Health check capabilities

Usage:
    client = AsyncQdrantClientWrapper()
    await client.connect()
    
    await client.create_collection_if_not_exists("memories", vector_size=384)
    await client.upsert("memories", points)
    results = await client.search("memories", query_vector, limit=5)
    
    await client.close()
"""
import asyncio
from typing import List, Dict, Any, Optional
import functools

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from memory_thread.config.settings import settings
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


def retry_on_connection_error(max_attempts: int = 3, wait_seconds: float = 1.0):
    """
    Decorator for retrying async Qdrant operations on transient failures.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except (ConnectionError, TimeoutError, OSError) as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = min(wait_seconds * (2 ** (attempt - 1)), 10.0)
                        log.warning(
                            f"Qdrant operation failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        log.error(f"Qdrant operation failed after {max_attempts} attempts: {e}")
                        raise
                except Exception:
                    # Non-retryable error
                    raise
                    
            raise last_exception
        return wrapper
    return decorator


class AsyncQdrantClientWrapper:
    """
    Async wrapper around Qdrant client with convenience methods.
    
    Usage:
        client = AsyncQdrantClientWrapper()
        await client.connect()
        
        await client.upsert("collection", points)
        results = await client.search("collection", vector)
        
        await client.close()
    """
    
    def __init__(self, host: str = None, port: int = None):
        """Initialize client. Connection is created lazily."""
        self.host = host or settings.QDRANT_HOST
        self.port = port or settings.QDRANT_PORT
        self._client: Optional[AsyncQdrantClient] = None
        self._connected = False
    
    async def connect(self):
        """Initialize the async Qdrant client."""
        if not self._connected:
            try:
                self._client = AsyncQdrantClient(host=self.host, port=self.port)
                self._connected = True
                log.info(f"Async Qdrant client connected to {self.host}:{self.port}")
            except Exception as e:
                log.error(f"Failed to connect to Qdrant: {e}")
                raise
    
    async def close(self):
        """Close the Qdrant client."""
        if self._client is not None:
            try:
                await self._client.close()
                log.info("Async Qdrant client closed")
            except Exception as e:
                log.warning(f"Error closing Qdrant client: {e}")
            finally:
                self._client = None
                self._connected = False
    
    async def _ensure_connected(self):
        """Ensure client is connected."""
        if not self._connected:
            await self.connect()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Qdrant health status."""
        result = {
            "status": "unknown",
            "error": None,
            "collections": []
        }
        
        try:
            await self._ensure_connected()
            collections = await self._client.get_collections()
            result.update({
                "status": "healthy",
                "collections": [c.name for c in collections.collections]
            })
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
        
        return result
    
    @retry_on_connection_error()
    async def create_collection_if_not_exists(
        self, 
        collection_name: str, 
        vector_size: int = 384,
        distance: Distance = Distance.COSINE
    ):
        """Create a collection if it doesn't exist."""
        await self._ensure_connected()
        
        try:
            await self._client.get_collection(collection_name)
            log.debug(f"Collection '{collection_name}' already exists")
        except Exception:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance)
            )
            log.info(f"Created collection '{collection_name}' (size={vector_size})")
    
    @retry_on_connection_error()
    async def upsert(self, collection_name: str, points: List[Dict[str, Any]]):
        """
        Upsert points into a collection.
        
        Args:
            collection_name: Target collection
            points: List of dicts with 'id', 'vector', 'payload'
        """
        await self._ensure_connected()
        
        qdrant_points = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {})
            )
            for p in points
        ]
        
        await self._client.upsert(
            collection_name=collection_name, 
            points=qdrant_points
        )
    
    @retry_on_connection_error()
    async def search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        limit: int = 5,
        score_threshold: float = None,
        filter_conditions: Dict = None
    ) -> List[Any]:
        """
        Search for similar vectors.
        
        Args:
            collection_name: Collection to search
            query_vector: Query embedding
            limit: Max results
            score_threshold: Minimum similarity score
            filter_conditions: Qdrant filter conditions
            
        Returns:
            List of search results with scores
        """
        await self._ensure_connected()
        
        try:
            results = await self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=filter_conditions
            )
            return results
        except Exception as e:
            log.warning(f"Qdrant search failed: {e}")
            return []
    
    @retry_on_connection_error()
    async def delete(self, collection_name: str, ids: List[str]):
        """Delete points by IDs."""
        await self._ensure_connected()
        await self._client.delete(
            collection_name=collection_name,
            points_selector=ids
        )
    
    @retry_on_connection_error()
    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Get collection statistics."""
        await self._ensure_connected()
        
        try:
            info = await self._client.get_collection(collection_name)
            return {
                "name": collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value if info.status else "unknown"
            }
        except Exception as e:
            return {"name": collection_name, "error": str(e)}


# Singleton instance
_async_qdrant_instance: Optional[AsyncQdrantClientWrapper] = None


async def get_async_qdrant() -> AsyncQdrantClientWrapper:
    """Get or create the async Qdrant client singleton."""
    global _async_qdrant_instance
    
    if _async_qdrant_instance is None:
        _async_qdrant_instance = AsyncQdrantClientWrapper()
        await _async_qdrant_instance.connect()
    
    return _async_qdrant_instance
