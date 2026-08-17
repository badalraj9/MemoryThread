import os
import sys
from pathlib import Path

import pytest

# Skip the blocking AsyncGraphWorker.flush() during lifespan so API tests
# don't hang against a large live DB. Safe: the worker still starts its
# background poll thread; only the initial full-replay is bypassed.
os.environ.setdefault("MT_SKIP_GRAPH_FLUSH", "1")
# Force server-side MemoryClient to use_db=False so API tests run fully
# in-memory without needing a live Postgres connection per request.
os.environ.setdefault("MT_USE_DB_FALSE", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_thread.sdk import MemoryClient


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running performance test")
    config.addinivalue_line("markers", "integration: uses optional services or subprocesses")
    config.addinivalue_line("markers", "benchmark: performance-oriented benchmark-style check")


@pytest.fixture(scope="module")
def pg_graph_worker():
    """Start AsyncGraphWorker with an initial flush for PG integration tests.

    Mirrors what server.py lifespan does: flush() drains any backlog from PG
    synchronously so tests that read graph state immediately after writing see
    a fully consistent graph. Worker is stopped after the test module exits.

    Skipped silently if Postgres is not available (worker will raise on init).
    """
    try:
        from memory_thread.db.postgres_client import PostgresClient
        from memory_thread.nervous.graph_worker import AsyncGraphWorker

        pg = PostgresClient()
        worker = AsyncGraphWorker(pg)
        worker.flush()
        worker.start()
        yield worker
        worker.stop()
    except Exception:
        yield None  # PG unavailable — tests guarded by requires_postgres will skip




@pytest.fixture
def isolated_namespace(monkeypatch):
    monkeypatch.setattr(MemoryClient, "_get_global_namespace", lambda self: self.namespace)
    return f"test_ns_{os.getpid()}"


@pytest.fixture
def memory_client_factory(monkeypatch, isolated_namespace):
    monkeypatch.setattr(MemoryClient, "_get_global_namespace", lambda self: self.namespace)

    def factory(suffix: str = "default", **kwargs):
        namespace = kwargs.pop("namespace", f"{isolated_namespace}_{suffix}")
        return MemoryClient(namespace=namespace, **kwargs)

    return factory


@pytest.fixture
def wal_dir(tmp_path, monkeypatch):
    import memory_thread.services.wal as wal_module

    target = tmp_path / "wal"
    wal_module.close_all_wals()
    monkeypatch.setattr(wal_module, "WAL_DIR", target)
    wal_module._wal_instances.clear()
    yield target
    wal_module.close_all_wals()
    wal_module._wal_instances.clear()


@pytest.fixture(autouse=True)
def _isolated_wal(tmp_path, monkeypatch):
    import memory_thread.services.wal as wal_module

    target = tmp_path / "autouse_wal"
    wal_module.close_all_wals()
    monkeypatch.setattr(wal_module, "WAL_DIR", target)
    wal_module._wal_instances.clear()
    yield
    wal_module.close_all_wals()
    wal_module._wal_instances.clear()


@pytest.fixture
def sqlite_db_path(tmp_path, monkeypatch):
    import memory_thread.db.sqlite_client as sqlite_module

    db_path = tmp_path / "mt.sqlite3"
    monkeypatch.setattr(sqlite_module, "DEFAULT_DB_PATH", str(db_path))
    sqlite_module._client = None
    yield db_path
    sqlite_module._client = None


@pytest.fixture
def perf_enabled():
    return os.environ.get("MT_RUN_PERF") == "1"


@pytest.fixture
def repo_root():
    return ROOT
