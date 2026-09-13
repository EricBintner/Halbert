# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The snapshot engine produces consistent, verifiable copies."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from halbert_core.replica.snapshot import (
    SnapshotTarget,
    create_snapshot,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_db(path: Path, rows: int = 3) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"r{i}",) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()
    return path


def test_file_copy_snapshot_matches_source(tmp_path):
    src = tmp_path / "memories.json"
    payload = {"version": 2, "memories": [{"id": "m1"}]}
    src.write_text(json.dumps(payload))

    result = create_snapshot([SnapshotTarget(src, "file_copy", "memories.json")])

    snap = result.staging_dir / "memories.json"
    assert snap.read_bytes() == src.read_bytes()
    assert result.manifest["memories.json"]["sha256"] == _sha256(snap)


def test_sqlite_backup_passes_integrity_check(tmp_path):
    db = _make_db(tmp_path / "conversations.db")
    result = create_snapshot([SnapshotTarget(db, "sqlite_backup", "conversations.db")])

    snap = result.staging_dir / "conversations.db"
    conn = sqlite3.connect(str(snap))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3
    finally:
        conn.close()


def test_sqlite_backup_excludes_uncommitted_writes(tmp_path):
    db = _make_db(tmp_path / "conversations.db", rows=2)

    writer = sqlite3.connect(str(db))
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO t (v) VALUES ('uncommitted')")

        result = create_snapshot([SnapshotTarget(db, "sqlite_backup", "conversations.db")])
        snap = result.staging_dir / "conversations.db"
        conn = sqlite3.connect(str(snap))
        try:
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
        finally:
            conn.close()
    finally:
        writer.rollback()
        writer.close()


def test_snapshot_works_when_source_missing(tmp_path):
    absent = tmp_path / "memories.json"
    result = create_snapshot([SnapshotTarget(absent, "file_copy", "memories.json")])

    assert result.manifest == {}
    assert result.missing == ["memories.json"]
    assert not (result.staging_dir / "memories.json").exists()


def test_snapshot_works_when_conversations_db_missing(tmp_path):
    absent = tmp_path / "conversations.db"
    result = create_snapshot([SnapshotTarget(absent, "sqlite_backup", "conversations.db")])

    assert result.missing == ["conversations.db"]
    assert result.manifest == {}


def test_manifest_records_sha256_and_size(tmp_path):
    src = tmp_path / "memories.json"
    src.write_bytes(b'{"memories": []}')

    result = create_snapshot([SnapshotTarget(src, "file_copy", "memories.json")])

    entry = result.manifest["memories.json"]
    assert entry["sha256"] == _sha256(result.staging_dir / "memories.json")
    assert entry["size"] == len(b'{"memories": []}')
    assert entry["method"] == "file_copy"


def test_snapshot_targets_are_configurable(tmp_path):
    """Phase 2's vault reuses this engine with a different list — the list
    is a parameter, not a constant."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("aaa")
    b.write_text("bbb")

    result = create_snapshot([
        SnapshotTarget(a, "file_copy", "a.txt"),
        SnapshotTarget(b, "file_copy", "b.txt"),
    ])
    assert set(result.manifest) == {"a.txt", "b.txt"}
    assert (result.staging_dir / "a.txt").read_text() == "aaa"


def test_replication_targets_point_at_real_paths():
    """The standard set: memories under the haloysius personas tree (NOT
    halbert's data_dir — a wrong guess snapshots an empty path), the
    thread store under halbert's data_dir."""
    from halbert_core.replica.snapshot import replication_targets

    targets = replication_targets()
    names = {t.name: t for t in targets}
    assert set(names) == {"memories.json", "conversations.db"}
    assert names["memories.json"].method == "file_copy"
    assert names["conversations.db"].method == "sqlite_backup"
    assert "personas" in str(names["memories.json"].source)
    assert names["memories.json"].source.name == "memories.json"
    assert names["conversations.db"].source.name == "conversations.db"
