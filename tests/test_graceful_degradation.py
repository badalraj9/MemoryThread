from contextlib import contextmanager

from memory_thread.sdk import MemoryClient


class _WorkingCursor:
    def execute(self, query, params=None):
        return None

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _WorkingPostgresClient:
    @contextmanager
    def get_cursor(self):
        yield _WorkingCursor()


class _WorkingQdrantWrapper:
    def __init__(self):
        self.client = self

    def get_collection(self, collection_name):
        return {"name": collection_name}

    def create_collection(self, collection_name, vectors_config):
        return None

    def upsert(self, collection_name, points):
        return None

    def query_points(self, collection_name, query, limit, query_filter=None):
        return type("Result", (), {"points": []})()

    def delete(self, collection_name, points_selector):
        return None


def test_graceful_degradation_across_dependency_failures_and_recovery(monkeypatch, sqlite_db_path):
    import memory_thread.db.postgres_client as postgres_module
    import memory_thread.db.qdrant_client as qdrant_module
    import memory_thread.db.sqlite_client as sqlite_module

    monkeypatch.setattr(MemoryClient, "_get_global_namespace", lambda self: self.namespace)
    original_sqlite = sqlite_module.SQLiteClient

    monkeypatch.setattr(postgres_module, "PostgresClient", _WorkingPostgresClient)
    monkeypatch.setattr(qdrant_module, "QdrantClientWrapper", _WorkingQdrantWrapper)
    monkeypatch.setattr(sqlite_module, "SQLiteClient", lambda: original_sqlite(str(sqlite_db_path)))

    healthy = MemoryClient(namespace="healthy", use_db=True)
    assert getattr(healthy, "_db_type", None) == "postgres"
    assert healthy._qdrant is not None

    monkeypatch.setattr(
        qdrant_module,
        "QdrantClientWrapper",
        lambda: (_ for _ in ()).throw(RuntimeError("qdrant down")),
    )
    qdrant_down = MemoryClient(namespace="qdrant_down", use_db=True)
    qdrant_down.remember("fallback keyword memory", source="agent")
    qdrant_results = qdrant_down.recall("fallback keyword", top_k=5, min_truth_score=0.0)

    assert qdrant_down._qdrant is None
    assert qdrant_results.total_found > 0

    monkeypatch.setattr(
        postgres_module,
        "PostgresClient",
        lambda: (_ for _ in ()).throw(RuntimeError("postgres down")),
    )
    monkeypatch.setattr(qdrant_module, "QdrantClientWrapper", _WorkingQdrantWrapper)
    postgres_down = MemoryClient(namespace="postgres_down", use_db=True)
    sqlite_entity_id = postgres_down.remember("sqlite fallback memory", source="agent")
    sqlite_state = postgres_down._sqlite.get_state(str(sqlite_entity_id))

    assert postgres_down.get_stats()["db_type"] == "sqlite"
    assert sqlite_state["current_value"]["content"] == "sqlite fallback memory"

    monkeypatch.setattr(
        qdrant_module,
        "QdrantClientWrapper",
        lambda: (_ for _ in ()).throw(RuntimeError("qdrant down")),
    )
    monkeypatch.setattr(
        sqlite_module,
        "SQLiteClient",
        lambda: (_ for _ in ()).throw(RuntimeError("sqlite down")),
    )
    fully_degraded = MemoryClient(namespace="fully_degraded", use_db=True)
    fully_degraded.remember("memory only fallback", source="agent")
    degraded_results = fully_degraded.recall("memory only", top_k=5, min_truth_score=0.0)

    assert fully_degraded.get_stats()["db_type"] == "memory"
    assert fully_degraded._qdrant is None
    assert degraded_results.total_found > 0

    monkeypatch.setattr(postgres_module, "PostgresClient", _WorkingPostgresClient)
    monkeypatch.setattr(qdrant_module, "QdrantClientWrapper", _WorkingQdrantWrapper)
    monkeypatch.setattr(sqlite_module, "SQLiteClient", lambda: original_sqlite(str(sqlite_db_path)))

    restored = MemoryClient(namespace="restored", use_db=True)
    restored.remember("restored dependencies memory", source="agent")

    assert restored.get_stats()["db_type"] == "postgres"
    assert restored._qdrant is not None
