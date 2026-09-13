# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The satellite's replica store: verify first, swap atomically, own the dir."""
import json
import os
import sqlite3
import stat
from pathlib import Path

import pytest

from halbert_core.replica.snapshot import (
    SnapshotTarget,
    create_snapshot,
)
from halbert_core.replica.store import (
    ReplicaStore,
    ReplicaValidationError,
)


def _write_memories(path: Path, count: int = 2) -> Path:
    path.write_text(json.dumps({
        "version": 2,
        "persona_id": "halbert",
        "memories": [{"id": f"m{i}"} for i in range(count)],
    }))
    return path


def _write_db(path: Path, rows: int = 3) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE conversations (id TEXT)")
        conn.executemany("INSERT INTO conversations VALUES (?)",
                         [(f"c{i}",) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()
    return path


def _snapshot(tmp_path: Path, memories: int = 2, threads: int = 3):
    """A real snapshot staging dir + the manifest shape the endpoint sends."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    mem = _write_memories(src_dir / "memories.json", memories)
    db = _write_db(src_dir / "conversations.db", threads)
    result = create_snapshot([
        SnapshotTarget(mem, "file_copy", "memories.json"),
        SnapshotTarget(db, "sqlite_backup", "conversations.db"),
    ])
    manifest = {
        "files": result.manifest,
        "created_at": result.created_at,
        "source_node_id": "canonical-1",
    }
    return result.staging_dir, manifest


@pytest.fixture
def store(tmp_path):
    return ReplicaStore(replica_dir=tmp_path / "canonical_replica")


def test_receive_valid_snapshot_stores_and_records_meta(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    meta = store.receive(staging, manifest)

    assert meta.source_node_id == "canonical-1"
    assert meta.memory_count == 2
    assert meta.thread_count == 3
    assert store.path().joinpath("memories.json").is_file()
    assert store.meta().source_node_id == "canonical-1"


def test_replica_dir_is_owner_only(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    store.receive(staging, manifest)
    mode = stat.S_IMODE(store.path().stat().st_mode)
    assert mode == 0o700


def test_receive_corrupt_db_rejected_old_preserved(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    store.receive(staging, manifest)

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    _write_memories(bad_dir / "memories.json")
    (bad_dir / "conversations.db").write_bytes(b"not a sqlite file")
    import hashlib
    manifest["files"]["conversations.db"]["sha256"] = hashlib.sha256(
        b"not a sqlite file").hexdigest()

    with pytest.raises(ReplicaValidationError):
        store.receive(bad_dir, manifest)
    assert store.is_valid()  # the first snapshot is still the live one


def test_receive_corrupt_memories_json_rejected(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    store.receive(staging, manifest)

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "memories.json").write_text("{not json")
    _write_db(bad_dir / "conversations.db")
    import hashlib
    manifest["files"]["memories.json"]["sha256"] = hashlib.sha256(
        b"{not json").hexdigest()

    with pytest.raises(ReplicaValidationError):
        store.receive(bad_dir, manifest)
    assert store.is_valid()


def test_receive_wrong_sha256_rejected(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    manifest["files"]["memories.json"]["sha256"] = "0" * 64
    with pytest.raises(ReplicaValidationError):
        store.receive(staging, manifest)
    assert store.meta() is None


def test_unknown_payload_name_rejected(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    evil = Path(staging) / ".."
    manifest["files"]["../../etc/passwd"] = {"sha256": "0" * 64}
    with pytest.raises(ReplicaValidationError):
        store.receive(staging, manifest)


def test_meta_returns_none_when_no_replica(store):
    assert store.meta() is None
    assert store.is_valid() is False


def test_receive_replaces_old_atomically(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    store.receive(staging, manifest)
    first_meta = store.meta()

    staging2, manifest2 = _snapshot(tmp_path / "second", memories=9, threads=7)
    meta2 = store.receive(staging2, manifest2)

    assert meta2.memory_count == 9
    assert store.meta().received_at >= first_meta.received_at
    assert store.is_valid()


def test_is_valid_false_when_payload_deleted(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    store.receive(staging, manifest)
    # Simulate a damaged replica: remove a payload file out from under it.
    current = store.path() / "memories.json"
    current.unlink()
    assert store.is_valid() is False


def test_is_valid_false_when_payload_modified(store, tmp_path):
    staging, manifest = _snapshot(tmp_path)
    store.receive(staging, manifest)
    f = store.path() / "memories.json"
    f.write_text(json.dumps({"memories": []}))
    assert store.is_valid() is False
