# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The credentials_admin role scope's trust-boundary behaviors.

``roles.py`` documents why this scope exists: without it the agent reads
``~/.aws/credentials`` via a file-read tool and the secret enters context
raw, bypassing tier routing entirely. The registry's data invariants
(manifest reachability, naming, platform gating) are pinned by
``test_config_roles.py``; these tests pin the BEHAVIORS that make the
boundary real:

  1. Credential files stage only under the credentials scope — they never
     land in a general directory.
  2. Default staging redacts secret values on the way in.
  3. ``redact=False`` writes raw — deliberately, for Halbert's private
     host project; the egress boundaries (tier routing + the MCP
     dispatch choke point) are what protect it, not the staging path.
  4. Bare key material (id_rsa, *.pem) is never staged by the scope,
     under either flag.
  5. End to end: a raw-staged credential still answers through
     ``get_config_value`` with metadata only — the operational gate
     ``scripts/rebuild_sourceprep_unredacted.py`` proves live, pinned
     here so it cannot silently regress.
"""
from __future__ import annotations

import json

import pytest

from halbert_core.config import queries as queries_mod
from halbert_core.config import snapshot as snapshot_mod
from halbert_core.config.queries import get_config_value
from halbert_core.config.snapshot import snapshot
from halbert_core.tools.register_host_project import stage_role_tree

AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """A fake HOME with the credential files the real manifest matches."""
    home = tmp_path / "home" / "tester"
    (home / ".aws").mkdir(parents=True)
    (home / ".ssh").mkdir(parents=True)
    (home / ".aws" / "credentials").write_text(
        f"[default]\naws_access_key_id = {AWS_ACCESS_KEY}\n"
        f"aws_secret_access_key = {AWS_SECRET_KEY}\n"
    )
    (home / ".ssh" / "config").write_text("Host desktop\n  User tester\n")
    (home / ".ssh" / "id_rsa").write_text("-----BEGIN PRIVATE KEY-----\nxyz\n")
    monkeypatch.setenv("HOME", str(home))
    return home


def _staged_files(staging_root):
    return [p for p in staging_root.rglob("*") if p.is_file()]


class TestCredentialsScopeStaging:
    def test_credentials_stage_only_into_the_credentials_subdir(self, fake_home, tmp_path):
        root = tmp_path / "staging"
        staged = stage_role_tree("credentials_admin", root)
        assert staged >= 1
        files = _staged_files(root)
        assert all(p.relative_to(root).parts[0] == "credentials" for p in files)
        assert any(p.name == "credentials" for p in files)  # the AWS file made it

    def test_default_staging_redacts_secret_values(self, fake_home, tmp_path):
        root = tmp_path / "staging"
        stage_role_tree("credentials_admin", root)
        aws_file = next(p for p in _staged_files(root) if p.name == "credentials")
        content = aws_file.read_text()
        assert AWS_ACCESS_KEY not in content
        assert AWS_SECRET_KEY not in content

    def test_raw_staging_writes_raw_by_design(self, fake_home, tmp_path):
        """redact=False is the private-index contract: raw in, egress-protected."""
        root = tmp_path / "staging"
        stage_role_tree("credentials_admin", root, redact=False)
        aws_file = next(p for p in _staged_files(root) if p.name == "credentials")
        content = aws_file.read_text()
        assert AWS_ACCESS_KEY in content

    def test_key_material_is_never_staged(self, fake_home, tmp_path):
        """id_rsa has no key=value structure — excluded outright under both flags."""
        for redact in (True, False):
            root = tmp_path / f"staging-{redact}"
            stage_role_tree("credentials_admin", root, redact=redact)
            names = {p.name for p in _staged_files(root)}
            assert "id_rsa" not in names
            assert "config" in names  # ssh client config still stages

    def test_empty_home_stages_nothing(self, tmp_path, monkeypatch):
        empty_home = tmp_path / "empty-home"
        empty_home.mkdir()
        monkeypatch.setenv("HOME", str(empty_home))
        root = tmp_path / "staging"
        assert stage_role_tree("credentials_admin", root) == 0
        assert _staged_files(root) == []


class TestTierRoutingOnRawStagedContent:
    """The egress boundary on top of raw content — the operational gate."""

    @pytest.fixture
    def raw_canon(self, fake_home, tmp_path, monkeypatch):
        """Snapshot the fake host's config RAW into an isolated canon DB."""
        raw_dir, canon_dir, snap_dir = (
            tmp_path / "raw", tmp_path / "canon", tmp_path / "snap",
        )
        for d in (raw_dir, canon_dir, snap_dir):
            d.mkdir()
        # queries.py binds CANON_DIR/SNAP_DIR at import; patch both holders.
        monkeypatch.setattr(snapshot_mod, "RAW_DIR", str(raw_dir))
        monkeypatch.setattr(snapshot_mod, "CANON_DIR", str(canon_dir))
        monkeypatch.setattr(snapshot_mod, "SNAP_DIR", str(snap_dir))
        monkeypatch.setattr(queries_mod, "CANON_DIR", str(canon_dir))
        monkeypatch.setattr(queries_mod, "SNAP_DIR", str(snap_dir))
        manifest = tmp_path / "registry.yml"
        manifest.write_text(
            "include:\n  - ~/.aws/credentials\nexclude: []\nparsers: {}\n"
        )
        snapshot(str(manifest), redact=False)
        return canon_dir

    def test_raw_staged_secret_answers_metadata_only(self, fake_home, raw_canon):
        aws_path = str(fake_home / ".aws" / "credentials")
        result = get_config_value(aws_path, "aws_access_key_id")
        assert result.get("tier") >= 2
        assert "description" in result
        assert AWS_ACCESS_KEY not in json.dumps(result, default=str)

    def test_raw_staged_secret_is_described_not_returned(self, fake_home, raw_canon):
        aws_path = str(fake_home / ".aws" / "credentials")
        result = get_config_value(aws_path, "aws_secret_access_key")
        assert "value" not in result
        description = result.get("description")
        assert isinstance(description, dict)
        assert AWS_SECRET_KEY not in json.dumps(description, default=str)