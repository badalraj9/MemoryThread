import uuid

import memory_thread.services.wal as wal_module
from memory_thread.sdk import MemoryClient


def _reset_wal(tmp_path, monkeypatch):
    wal_module.close_all_wals()
    monkeypatch.setattr(wal_module, "WAL_DIR", tmp_path / "wal")


def test_sync_durability_mode_flushes_append_and_commit_per_remember(tmp_path, monkeypatch):
    _reset_wal(tmp_path, monkeypatch)
    client = MemoryClient(namespace="sync-durability", use_db=False, durability_mode="sync")

    try:
        client.remember(
            "sync durable memory",
            source="benchmark",
            entity_id=uuid.uuid4(),
        )
        stats = client.get_write_stats()

        assert stats["durability_mode"] == "sync"
        assert stats["durable_append_count"] == 1
        assert stats["durable_commit_count"] == 1
        assert stats["buffered_record_count"] == 0
    finally:
        client.close()
        wal_module.close_all_wals()


def test_batched_durability_mode_accepts_before_durable_flush(tmp_path, monkeypatch):
    _reset_wal(tmp_path, monkeypatch)
    client = MemoryClient(
        namespace="batched-accept-before-flush",
        use_db=False,
        durability_mode="batched",
        wal_flush_batch_size=1000,
        wal_flush_interval_ms=60000,
    )

    try:
        client.remember(
            "batched accepted memory",
            source="benchmark",
            entity_id=uuid.uuid4(),
        )
        stats = client.get_write_stats()

        assert stats["durability_mode"] == "batched"
        assert stats["write_metrics_enabled"] is True
        assert stats["durable_append_count"] == 0
        assert stats["durable_commit_count"] == 0
        assert stats["buffered_record_count"] == 2

        client.flush()
        stats = client.get_write_stats()

        assert stats["durable_append_count"] == 1
        assert stats["durable_commit_count"] == 1
        assert stats["buffered_record_count"] == 0
    finally:
        client.close()
        wal_module.close_all_wals()


def test_write_metrics_can_be_disabled_for_hot_path(tmp_path, monkeypatch):
    _reset_wal(tmp_path, monkeypatch)
    client = MemoryClient(
        namespace="metrics-disabled",
        use_db=False,
        durability_mode="batched",
        enable_write_metrics=False,
    )

    try:
        client.remember("metrics disabled memory", source="benchmark", entity_id=uuid.uuid4())
        client.flush()

        assert client.get_write_path_metrics() == {}
        assert client.get_write_stats()["write_metrics_enabled"] is False
    finally:
        client.close()
        wal_module.close_all_wals()


def test_enrichment_worker_drains_on_close():
    from memory_thread.sdk.client import MemoryClient

    client = MemoryClient(namespace="test_enrichment_drain", use_db=False)
    client.remember("test enrichment drain", source="user", confidence=0.8)
    client.close()


def test_batched_close_flushes_pending_wal_records(tmp_path, monkeypatch):
    _reset_wal(tmp_path, monkeypatch)
    namespace = "batched-close-flush"
    client = MemoryClient(
        namespace=namespace,
        use_db=False,
        durability_mode="batched",
        wal_flush_batch_size=1000,
        wal_flush_interval_ms=60000,
    )

    for index in range(5):
        client.remember(
            f"batched close memory {index}",
            source="benchmark",
            entity_id=uuid.uuid4(),
        )

    stats = client.get_write_stats()
    assert stats["buffered_record_count"] == 10

    client.close()

    wal_module._wal_instances.clear()
    recovered = wal_module.get_wal(namespace).get_uncommitted()

    assert recovered == []
    wal_module.close_all_wals()


def test_compact_wal_removes_committed_records_from_file(tmp_path, monkeypatch):
    _reset_wal(tmp_path, monkeypatch)
    client = MemoryClient(
        namespace="compact-committed-records",
        use_db=False,
        durability_mode="batched",
        wal_flush_batch_size=1000,
        wal_flush_interval_ms=60000,
    )

    try:
        for index in range(10):
            client.remember(
                f"compact memory {index}",
                source="benchmark",
                entity_id=uuid.uuid4(),
            )
        client.flush()
        before = client.get_write_stats()

        assert before["durable_append_count"] == 10
        assert before["durable_commit_count"] == 10
        assert before["file_size_bytes"] > 0

        client.compact_wal()
        after = client.get_write_stats()

        assert after["uncommitted_count"] == 0
        assert after["file_size_bytes"] == 0
        assert after["compacted_count"] == 1
    finally:
        client.close()
        wal_module.close_all_wals()
