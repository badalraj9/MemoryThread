import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import memory_thread.services.wal as wal_module
from memory_thread.db.sqlite_client import SQLiteClient
from memory_thread.services.wal import get_wal


def _crash_writer_script(repo_root: Path, wal_dir: Path, db_path: Path, namespace: str, committed: int):
    return f"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, r"{repo_root}")

import memory_thread.services.wal as wal_module
wal_module.WAL_DIR = Path(r"{wal_dir}")
wal_module._wal_instances.clear()

from memory_thread.db.sqlite_client import SQLiteClient
from memory_thread.services.wal import get_wal

wal = get_wal("{namespace}")
db = SQLiteClient(r"{db_path}")

for i in range(100):
    content = f"memory-{{i:03d}}"
    entity_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))
    seq = wal.append("remember", {{
        "entity_id": entity_id,
        "content": content,
        "source": "test",
        "confidence": 0.9,
        "authority": 0.9,
        "memory_type": "fact",
    }})
    if i < {committed}:
        db.save_state(
            entity_id=entity_id,
            namespace="{namespace}",
            current_value={{"content": content, "type": "fact"}},
            truth_vector={{"confidence": 0.9, "authority": 0.9, "freshness": 1.0, "corroboration": 0.0}},
            last_event_id=str(uuid.uuid4()),
        )
        wal.commit(seq)

os._exit(1)
"""


def _replay_entries(namespace: str, db_path: Path):
    wal = get_wal(namespace)
    db = SQLiteClient(str(db_path))
    for entry in wal.get_uncommitted():
        data = entry.data
        db.save_state(
            entity_id=data["entity_id"],
            namespace=namespace,
            current_value={"content": data["content"], "type": data.get("memory_type", "fact")},
            truth_vector={
                "confidence": data.get("confidence", 0.8),
                "authority": data.get("authority", 0.5),
                "freshness": 1.0,
                "corroboration": 0.0,
            },
            last_event_id=str(uuid.uuid4()),
        )
        wal.commit(entry.sequence)


@pytest.mark.integration
@pytest.mark.parametrize("crash_percent", [10, 30, 50, 70, 90])
def test_wal_recovery_replays_all_uncommitted_entries(tmp_path, repo_root, monkeypatch, crash_percent):
    wal_dir = tmp_path / "wal"
    db_path = tmp_path / "recovery.sqlite3"
    namespace = f"wal_recovery_{crash_percent}"
    committed = crash_percent

    subprocess.run(
        [sys.executable, "-c", _crash_writer_script(repo_root, wal_dir, db_path, namespace, committed)],
        check=False,
        cwd=repo_root,
    )

    monkeypatch.setattr(wal_module, "WAL_DIR", wal_dir)
    wal_module._wal_instances.clear()

    db = SQLiteClient(str(db_path))
    assert db.count_states(namespace) == committed

    _replay_entries(namespace, db_path)

    states = db.get_states_by_namespace(namespace)
    recovered_contents = {state["current_value"]["content"] for state in states}
    expected_contents = {f"memory-{i:03d}" for i in range(100)}

    assert len(states) == 100
    assert recovered_contents == expected_contents
