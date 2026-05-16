"""
Memory Thread SDK

Usage:
    from memory_thread.sdk import MemoryClient

    mt = MemoryClient()
    mt.remember("User prefers dark mode")
    memories = mt.recall("user preferences")
"""

from memory_thread.sdk.client import MemoryClient
from memory_thread.sdk.models import Memory, RecallResult, WritePathMetric, ConnectionConfig

__all__ = ["MemoryClient", "Memory", "RecallResult", "WritePathMetric", "ConnectionConfig"]


def create_memory_client(namespace: str = "default", use_db: bool = True) -> MemoryClient:
    """Create a new MemoryClient instance."""
    return MemoryClient(namespace=namespace, use_db=use_db)
