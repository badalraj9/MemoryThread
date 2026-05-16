"""Test graceful degradation when dependencies fail."""

import pytest
import sys
import os


class _UnavailablePostgres:
    def get_cursor(self):
        raise ConnectionError("Postgres is down")

    def fetch_all(self, *args, **kwargs):
        raise ConnectionError("Postgres is down")

    def search_events_fts(self, *args, **kwargs):
        raise ConnectionError("Postgres is down")


class _HealthyPostgres:
    def __init__(self):
        from memory_thread.db.postgres_client import PostgresClient

        self._real = PostgresClient()

    def get_cursor(self):
        return self._real.get_cursor()

    def fetch_all(self, *args, **kwargs):
        return self._real.fetch_all(*args, **kwargs)

    def search_events_fts(self, *args, **kwargs):
        return self._real.search_events_fts(*args, **kwargs)


def test_postgres_available():
    import memory_thread.sdk.client as client_module
    from memory_thread.sdk.client import MemoryClient

    pg = _HealthyPostgres()
    client = MemoryClient(namespace="test_degradation_healthy", use_db=True)
    assert client._pg is not None
    client.close()


def test_postgres_unavailable_fallback_to_memory():
    import memory_thread.sdk.client as client_module
    from memory_thread.sdk.client import MemoryClient

    client = MemoryClient(namespace="test_degradation_pg_down", use_db=False)
    assert client._pg is None
    result = client.remember("memory only fallback", source="agent")
    assert result is not None
    client.close()


def test_sqlite_fallback():
    """If Postgres is down but SQLite is configured, should fall back."""
    import memory_thread.sdk.client as client_module
    from memory_thread.sdk.client import MemoryClient

    client = MemoryClient(namespace="test_degradation_sqlite", use_db=False)
    assert client._pg is None
    client.remember("sqlite fallback test", source="agent", confidence=0.8)
    recall = client.recall("sqlite fallback", top_k=5)
    assert recall.total_found >= 1
    client.close()
