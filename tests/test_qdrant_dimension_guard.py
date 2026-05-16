from contextlib import contextmanager

from memory_thread.config.settings import settings
from memory_thread.sdk import MemoryClient


class _WorkingCursor:
    def execute(self, query, params=None):
        return None


class _WorkingPostgresClient:
    @contextmanager
    def get_cursor(self):
        yield _WorkingCursor()


class _DimensionMismatchQdrantWrapper:
    def __init__(self):
        self.client = self
        self.deleted = []
        self.created = []

    def get_collection(self, collection_name):
        return {"config": {"params": {"vectors": {"size": 1536}}}}

    def create_collection(self, collection_name, vectors_config):
        self.created.append((collection_name, vectors_config))

    def delete_collection(self, collection_name):
        self.deleted.append(collection_name)


def test_qdrant_dimension_mismatch_disables_qdrant_by_default(monkeypatch):
    import memory_thread.db.postgres_client as postgres_module
    import memory_thread.db.qdrant_client as qdrant_module

    monkeypatch.setattr(postgres_module, "PostgresClient", _WorkingPostgresClient)
    monkeypatch.setattr(qdrant_module, "QdrantClientWrapper", _DimensionMismatchQdrantWrapper)
    monkeypatch.setattr(
        settings, "QDRANT_AUTO_RECREATE_COLLECTION_ON_DIMENSION_MISMATCH", False
    )

    client = MemoryClient(namespace="qdrant-dimension-disable", use_db=True)

    assert client._qdrant is None


def test_qdrant_dimension_mismatch_can_recreate_collection(monkeypatch):
    import memory_thread.db.postgres_client as postgres_module
    import memory_thread.db.qdrant_client as qdrant_module

    monkeypatch.setattr(postgres_module, "PostgresClient", _WorkingPostgresClient)
    monkeypatch.setattr(qdrant_module, "QdrantClientWrapper", _DimensionMismatchQdrantWrapper)
    monkeypatch.setattr(settings, "QDRANT_AUTO_RECREATE_COLLECTION_ON_DIMENSION_MISMATCH", True)

    client = MemoryClient(namespace="qdrant-dimension-recreate", use_db=True)

    assert client._qdrant is not None
    assert client._qdrant.deleted == ["memories"]
    assert client._qdrant.created
