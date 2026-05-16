"""Qdrant has been removed — replaced by Postgres FTS + spaCy for seed resolution."""

import pytest


def test_memory_client_initializes_without_qdrant():
    from memory_thread.sdk.client import MemoryClient

    client = MemoryClient(namespace="test_no_qdrant", use_db=False)
    assert client is not None
    assert not hasattr(client, "_qdrant")
    client.close()


def test_memory_client_recall_fallback_to_keyword():
    from memory_thread.sdk.client import MemoryClient

    client = MemoryClient(namespace="test_no_qdrant_fallback", use_db=False)
    client.remember("test memory for recall fallback", source="agent", confidence=0.8)
    result = client.recall("test memory", top_k=5)
    assert result is not None
    assert result.query == "test memory"
    client.close()
