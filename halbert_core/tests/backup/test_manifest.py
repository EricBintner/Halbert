# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The manifest is the archive's table of contents and trust anchor."""
import pytest

from halbert_core.backup.manifest import (
    BACKUP_SCHEMA_VERSION,
    BackupManifest,
    ManifestError,
)


def _manifest() -> BackupManifest:
    return BackupManifest(
        schema_version=BACKUP_SCHEMA_VERSION,
        node_id="halbert-mac",
        entity_name="halbert",
        created_at="2026-09-13T12:00:00+00:00",
        kdf_salt="ab" * 16,
        kdf_iterations=600_000,
        files={"databases/memories.json.enc": {
            "sha256": "0" * 64, "size": 100, "encrypted": True}},
        key_custody="file",
        key_exported=True,
    )


def test_manifest_roundtrips_through_json():
    m = _manifest()
    back = BackupManifest.from_json(m.to_json())
    assert back.node_id == "halbert-mac"
    assert back.entity_name == "halbert"
    assert back.kdf_iterations == 600_000
    assert back.key_custody == "file"
    assert back.key_exported is True
    assert back.files["databases/memories.json.enc"]["sha256"] == "0" * 64


def test_manifest_records_schema_version():
    m = BackupManifest.from_json(_manifest().to_json())
    assert m.schema_version == BACKUP_SCHEMA_VERSION


def test_manifest_validates_required_fields():
    import json
    broken = json.loads(_manifest().to_json())
    del broken["files"]
    with pytest.raises(ManifestError):
        BackupManifest.from_dict(broken)
    del broken["node_id"]
    with pytest.raises(ManifestError):
        BackupManifest.from_dict(broken)


def test_manifest_not_json_fails_clearly():
    with pytest.raises(ManifestError):
        BackupManifest.from_json("{not json")


def test_manifest_defaults_are_safe():
    """A minimal manifest still parses — forward-compat readers get
    defaults, not crashes."""
    import json
    minimal = {"schema_version": 1, "node_id": "n",
               "created_at": "t", "files": {}}
    m = BackupManifest.from_dict(minimal)
    assert m.key_exported is False
    assert m.model_manifest is None
