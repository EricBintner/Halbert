# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The vault engine gathers the whole entity into one encrypted tar."""
import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest

from halbert_core.backup.encrypt import (
    CryptoUnavailable,
    decrypt_file,
    derive_key,
)
from halbert_core.backup.manifest import BackupManifest
from halbert_core.backup.vault import (
    ARCHIVE_SUFFIX,
    create_backup,
    list_backups,
)


@pytest.fixture
def entity_tree(tmp_path, monkeypatch):
    """A minimal entity on disk: config files, memories, a thread store,
    and a signer that exports."""
    config = tmp_path / "config"
    data = tmp_path / "data"
    halo = tmp_path / "halo"
    for d in (config, data, halo):
        d.mkdir(parents=True)

    (config / "being.yml").write_text("voice: null\n")
    (config / "peers.json").write_text('{"peers": []}')
    (config / "models.yml").write_text("chat_model: local\n")

    (halo / "personas" / "halbert").mkdir(parents=True)
    (halo / "personas" / "halbert" / "memories.json").write_text(json.dumps({
        "version": 2, "persona_id": "halbert",
        "memories": [{"id": "m1", "persona_id": "halbert",
                      "content": "x", "memory_type": "episodic"}],
    }))
    conn = sqlite3.connect(str(data / "conversations.db"))
    conn.execute("CREATE TABLE conversations (id TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "halbert_core.utils.platform.get_config_dir", lambda: config)
    monkeypatch.setenv("HALBERT_DATA_DIR", str(data))
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(halo))

    class FakeSigner:
        custody = "file"
        did = "did:key:zTest"
        def private_bytes(self):
            return b"PRIVATEKEYBYTES32______________"

    monkeypatch.setattr(
        "halbert_core.crypto.storage.resolve_signer",
        lambda *a, **kw: FakeSigner())
    return tmp_path


def _members(archive: Path):
    with tarfile.open(archive, "r:*") as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers()
                if m.isfile()}


def test_backup_writes_archive_with_manifest(entity_tree, tmp_path):
    archive = create_backup("pw", tmp_path / "out")
    assert archive.name.endswith(ARCHIVE_SUFFIX)
    members = _members(archive)
    manifest = BackupManifest.from_json(members["manifest.json"].decode())
    assert manifest.schema_version == 1
    assert manifest.entity_name
    assert manifest.kdf_iterations == 600_000
    assert manifest.key_exported is True


def test_archive_contains_all_expected_files(entity_tree, tmp_path):
    archive = create_backup("pw", tmp_path / "out")
    names = set(_members(archive))
    assert "identity/body.key.enc" in names
    assert "identity/did.txt" in names
    assert "config/being.yml.enc" in names
    assert "config/peers.json.enc" in names
    assert "databases/memories.json.enc" in names
    assert "databases/conversations.db.enc" in names
    assert "model-manifest.json" in names


def test_each_enc_file_decrypts_with_passphrase(entity_tree, tmp_path):
    archive = create_backup("pw", tmp_path / "out")
    members = _members(archive)
    manifest = BackupManifest.from_json(members["manifest.json"].decode())
    key = derive_key("pw", bytes.fromhex(manifest.kdf_salt),
                     manifest.kdf_iterations)
    for name, entry in manifest.files.items():
        if entry["encrypted"]:
            pt = decrypt_file(members[name], key, name)
            assert pt  # every .enc member decrypts


def test_encrypted_payload_is_not_plaintext(entity_tree, tmp_path):
    archive = create_backup("pw", tmp_path / "out")
    members = _members(archive)
    assert b"PRIVATEKEYBYTES" not in members["identity/body.key.enc"]
    key = derive_key("pw", bytes.fromhex(
        BackupManifest.from_json(members["manifest.json"].decode()).kdf_salt))
    # decrypt needs iterations too — pull them properly:
    manifest = BackupManifest.from_json(members["manifest.json"].decode())
    key = derive_key("pw", bytes.fromhex(manifest.kdf_salt),
                     manifest.kdf_iterations)
    assert decrypt_file(
        members["identity/body.key.enc"], key,
        "identity/body.key.enc") == b"PRIVATEKEYBYTES32______________"


def test_model_manifest_is_plaintext(entity_tree, tmp_path):
    archive = create_backup("pw", tmp_path / "out")
    members = _members(archive)
    models = json.loads(members["model-manifest.json"].decode())
    assert models.get("chat_model") == "local"


def test_backup_fresh_install_no_databases(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "being.yml").write_text("voice: null\n")
    monkeypatch.setattr(
        "halbert_core.utils.platform.get_config_dir", lambda: config)
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path / "halo"))
    monkeypatch.setattr(
        "halbert_core.crypto.storage.resolve_signer", lambda *a, **kw: None)

    archive = create_backup("pw", tmp_path / "out")
    members = _members(archive)
    manifest = BackupManifest.from_json(members["manifest.json"].decode())
    assert manifest.key_exported is False
    # A fresh install still archives its config.
    assert "config/being.yml.enc" in members


def test_backup_write_is_atomic(entity_tree, tmp_path):
    out = tmp_path / "out"
    archive = create_backup("pw", out)
    assert archive.is_file()
    # No temp file left behind.
    assert not list(out.glob("*.tmp"))


def test_list_backups_reads_manifests(entity_tree, tmp_path):
    out = tmp_path / "out"
    a = create_backup("pw", out)
    found = list_backups(out)
    assert len(found) == 1
    assert found[0].key_exported is True


def test_backup_fails_without_crypto(entity_tree, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "halbert_core.backup.vault.check_crypto_available", lambda: False)
    with pytest.raises(CryptoUnavailable):
        create_backup("pw", tmp_path / "out")
