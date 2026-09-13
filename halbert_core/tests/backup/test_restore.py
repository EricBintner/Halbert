# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Restore: everything verifies in memory before a byte is written."""
import json
import sqlite3
import stat
import tarfile
import io
from pathlib import Path

import pytest

from halbert_core.backup.restore import (
    RestoreError,
    restore_backup,
)
from halbert_core.backup.vault import create_backup


class Tree:
    """One machine's on-disk tree."""
    def __init__(self, root: Path):
        self.config = root / "config"
        self.data = root / "data"
        self.halo = root / "halo"
        self.state = root / "state"
        for d in (self.config, self.data, self.halo, self.state):
            d.mkdir(parents=True)

    def activate(self, monkeypatch):
        """Point every path resolver at this tree."""
        monkeypatch.setattr(
            "halbert_core.utils.platform.get_config_dir", lambda: self.config)
        monkeypatch.setattr(
            "halbert_core.utils.paths.state_dir", lambda: str(self.state))
        monkeypatch.setenv("HALBERT_DATA_DIR", str(self.data))
        monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(self.halo))


def _populate(tree: Tree, monkeypatch):
    """A source entity: config + memories + threads + an exported key."""
    (tree.config / "being.yml").write_text("voice: null\n")
    (tree.config / "peers.json").write_text('{"peers": []}')
    (tree.config / "models.yml").write_text("chat_model: local\n")
    (tree.halo / "personas" / "halbert").mkdir(parents=True)
    (tree.halo / "personas" / "halbert" / "memories.json").write_text(json.dumps({
        "version": 2, "persona_id": "halbert",
        "memories": [{"id": "m1", "persona_id": "halbert",
                      "content": "x", "memory_type": "episodic"}],
    }))
    conn = sqlite3.connect(str(tree.data / "conversations.db"))
    conn.execute("CREATE TABLE conversations (id TEXT)")
    conn.executemany("INSERT INTO conversations VALUES (?)", [("c1",), ("c2",)])
    conn.commit()
    conn.close()

    class FakeSigner:
        custody = "file"
        did = "did:key:zTest"
        def private_bytes(self):
            return b"K" * 32

    monkeypatch.setattr(
        "halbert_core.crypto.storage.resolve_signer",
        lambda *a, **kw: FakeSigner())


@pytest.fixture
def machines(tmp_path, monkeypatch):
    src = Tree(tmp_path / "src")
    dst = Tree(tmp_path / "dst")
    src.activate(monkeypatch)
    _populate(src, monkeypatch)
    archive_dir = tmp_path / "out"
    archive_dir.mkdir()
    archive = create_backup("pw", archive_dir, entity_name="halbert")
    # From here the "destination" is live.
    dst.activate(monkeypatch)
    return src, dst, archive


def test_restore_unpacks_all_files(machines):
    src, dst, archive = machines
    report = restore_backup(archive, "pw")
    assert (dst.config / "being.yml").is_file()
    assert (dst.config / "peers.json").is_file()
    assert (dst.data / "conversations.db").is_file()
    assert (dst.halo / "personas" / "halbert" / "memories.json").is_file()
    assert report.thread_count == 2
    assert report.memory_count == 1
    # The key went through the file keystore, owner-only.
    key = dst.state / "keys" / "body.key"
    assert key.is_file()
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_wrong_passphrase_writes_nothing(machines):
    src, dst, archive = machines
    with pytest.raises(RestoreError):
        restore_backup(archive, "wrong")
    assert not (dst.config / "being.yml").exists()
    assert not (dst.data / "conversations.db").exists()


def test_entity_name_drift_warns(machines, monkeypatch):
    src, dst, archive = machines
    monkeypatch.setattr(
        "halbert_core.identity.resolve_entity_name", lambda: "other")
    report = restore_backup(archive, "pw")
    assert any("other" in w for w in report.warnings)
    assert (dst.data / "conversations.db").is_file()  # warned, still restored


def test_tampered_member_fails_nothing_written(machines, tmp_path):
    src, dst, archive = machines
    with tarfile.open(archive, "r:*") as tar:
        members = {m.name: tar.extractfile(m).read()
                   for m in tar.getmembers() if m.isfile()}
    blob = bytearray(members["config/being.yml.enc"])
    blob[-1] ^= 0xFF
    members["config/being.yml.enc"] = bytes(blob)
    tampered = tmp_path / "tampered.halbert-backup"
    with tarfile.open(tampered, "w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    with pytest.raises(RestoreError):
        restore_backup(tampered, "pw")
    assert not (dst.config / "being.yml").exists()


def test_restore_is_idempotent(machines):
    src, dst, archive = machines
    restore_backup(archive, "pw")
    second = restore_backup(archive, "pw")
    assert (dst.data / "conversations.db").is_file()
    # Identical content — nothing quarantined the second time.
    assert second.quarantined == []


def test_files_not_in_archive_survive(machines):
    src, dst, archive = machines
    sentinel = dst.config / "unrelated.conf"
    sentinel.write_text("keep me")
    restore_backup(archive, "pw")
    assert sentinel.read_text() == "keep me"


def test_divergent_existing_state_quarantined(machines):
    src, dst, archive = machines
    (dst.config / "being.yml").write_text("voice: different\n")
    report = restore_backup(archive, "pw")
    assert len(report.quarantined) == 1
    assert (dst.config / "being.yml").read_text() == "voice: null\n"
    assert Path(report.quarantined[0]).read_text() == "voice: different\n"
