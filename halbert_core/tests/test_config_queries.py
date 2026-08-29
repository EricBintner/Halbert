# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the deterministic config query layer."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.queries import (
    get_config_value,
    get_config_structure,
    get_config_diff,
    get_config_dependencies,
)
from halbert_core.config.parser import parse as parse_config
from halbert_core.config.snapshot import snapshot, CANON_DIR, SNAP_DIR


@pytest.fixture
def temp_config_env(tmp_path, monkeypatch):
    """Create a temp config environment with a canon DB.

    Writes a small ini file, snapshots it, and patches the canon/snapshot
    directories to point at the temp location.
    """
    # Create a test config file
    config_file = tmp_path / "test.conf"
    config_file.write_text(
        "[Service]\n"
        "ExecStart=/usr/bin/myapp\n"
        "Port=2222\n"
        "Password=hunter2\n"
        "Enabled=true\n"
    )

    # Create a manifest
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(
        f"include:\n  - '{config_file}'\n"
        "exclude: []\n"
        "parsers: {}\n"
    )

    # Patch the canon/snapshot dirs to use tmp_path
    canon_dir = tmp_path / "canon"
    snap_dir = tmp_path / "snapshots"
    canon_dir.mkdir()
    snap_dir.mkdir()

    monkeypatch.setattr("halbert_core.config.snapshot.CANON_DIR", str(canon_dir))
    monkeypatch.setattr("halbert_core.config.snapshot.SNAP_DIR", str(snap_dir))
    monkeypatch.setattr("halbert_core.config.queries.CANON_DIR", str(canon_dir))
    monkeypatch.setattr("halbert_core.config.queries.SNAP_DIR", str(snap_dir))
    # drift.py also has its own CANON_DIR
    monkeypatch.setattr("halbert_core.config.drift.CANON_DIR", str(canon_dir))

    # Run the snapshot (unredacted so canon has real values)
    snapshot(str(manifest), redact=False)

    return {
        "config_file": str(config_file),
        "canon_dir": str(canon_dir),
        "snap_dir": str(snap_dir),
    }


class TestGetConfigValue:
    """get_config_value with tier routing."""

    def test_tier0_boolean(self, temp_config_env):
        """Enabled=true is a boolean → Tier 0 → raw value."""
        result = get_config_value(temp_config_env["config_file"], "Enabled")
        assert result["tier"] == 0
        assert result["value"] is True

    def test_tier1_port_cloud_ok(self, temp_config_env):
        """Port=2222 is Tier 1, cloud_ok → raw value."""
        result = get_config_value(temp_config_env["config_file"], "Port",
                                   operational_tier="cloud_ok")
        assert result["tier"] == 1
        assert result["value"] == 2222  # parser normalizes to int

    def test_tier1_port_local_only(self, temp_config_env):
        """Port=2222 is Tier 1, local_only → description."""
        result = get_config_value(temp_config_env["config_file"], "Port",
                                   operational_tier="local_only")
        assert result["tier"] == 1
        assert "value" not in result
        assert result["redacted"] is True
        assert "description" in result

    def test_tier1_port_redact(self, temp_config_env):
        """Port=2222 is Tier 1, redact → no value."""
        result = get_config_value(temp_config_env["config_file"], "Port",
                                   operational_tier="redact")
        assert result["tier"] == 1
        assert "value" not in result
        assert result["redacted"] is True

    def test_tier2_password_local_only(self, temp_config_env):
        """Password=hunter2 is Tier 2, local_only → description."""
        result = get_config_value(temp_config_env["config_file"], "Password",
                                   secret_tier="local_only")
        assert result["tier"] == 2
        assert "value" not in result
        assert result["redacted"] is True
        assert "description" in result
        # The secret must not appear in the result
        assert "hunter2" not in str(result)

    def test_tier2_password_cloud_ok_acknowledged(self, temp_config_env):
        """Password=hunter2 is Tier 2, cloud_ok_acknowledged → raw value."""
        result = get_config_value(temp_config_env["config_file"], "Password",
                                   secret_tier="cloud_ok_acknowledged")
        assert result["tier"] == 2
        assert result["value"] == "hunter2"
        assert result["acknowledged"] is True

    def test_key_not_found(self, temp_config_env):
        result = get_config_value(temp_config_env["config_file"], "NonExistent")
        assert "error" in result
        assert "not found" in result["error"]

    def test_file_not_found(self, tmp_path):
        result = get_config_value(str(tmp_path / "nonexistent.conf"), "Port")
        assert "error" in result

    def test_staleness_reparse(self, temp_config_env, tmp_path):
        """If the live file changes, the query re-parses and gets the new value."""
        config_file = temp_config_env["config_file"]
        # Modify the file
        with open(config_file, "w") as f:
            f.write("[Service]\nExecStart=/usr/bin/myapp\nPort=3333\n")
        result = get_config_value(config_file, "Port")
        assert result["tier"] == 1
        assert result["value"] == 3333


class TestGetConfigStructure:
    """get_config_structure returns shape, no values."""

    def test_ini_structure(self, temp_config_env):
        result = get_config_structure(temp_config_env["config_file"])
        assert result["kind"] == "ini"
        assert "sections" in result
        assert "Service" in result["sections"]
        # Values should be type names, not actual values.
        # configparser lowercases keys by default.
        assert result["sections"]["Service"]["port"] == "int"
        assert result["sections"]["Service"]["password"] == "str"
        assert result["sections"]["Service"]["enabled"] == "bool"

    def test_file_not_found(self, tmp_path):
        result = get_config_structure(str(tmp_path / "nonexistent.conf"))
        assert "error" in result


class TestGetConfigDiff:
    """get_config_diff returns change types, no values."""

    def test_no_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.setattr("halbert_core.config.queries.SNAP_DIR", str(tmp_path))
        result = get_config_diff()
        assert "changes" in result

    def test_with_snapshots(self, temp_config_env):
        result = get_config_diff()
        # With only one snapshot, there's nothing to diff
        assert "changes" in result


class TestGetConfigDependencies:
    """get_config_dependencies returns edges, no values."""

    def test_no_dependencies(self, temp_config_env):
        result = get_config_dependencies(temp_config_env["config_file"])
        assert result["path"] == temp_config_env["config_file"]
        assert result["dependencies"] == []

    def test_file_not_in_canon(self, tmp_path):
        result = get_config_dependencies(str(tmp_path / "nonexistent.conf"))
        assert result["dependencies"] == []


class TestYamlConfig:
    """Test queries against YAML config files."""

    def test_yaml_value_extraction(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(
            "server:\n"
            "  port: 8080\n"
            "  host: localhost\n"
            "  password: secretpass\n"
        )

        canon_dir = tmp_path / "canon"
        snap_dir = tmp_path / "snapshots"
        canon_dir.mkdir()
        snap_dir.mkdir()

        manifest = tmp_path / "manifest.yml"
        manifest.write_text(
            f"include:\n  - '{yaml_file}'\n"
            "exclude: []\n"
            "parsers: {}\n"
        )

        monkeypatch.setattr("halbert_core.config.snapshot.CANON_DIR", str(canon_dir))
        monkeypatch.setattr("halbert_core.config.snapshot.SNAP_DIR", str(snap_dir))
        monkeypatch.setattr("halbert_core.config.queries.CANON_DIR", str(canon_dir))
        monkeypatch.setattr("halbert_core.config.queries.SNAP_DIR", str(snap_dir))
        monkeypatch.setattr("halbert_core.config.drift.CANON_DIR", str(canon_dir))

        snapshot(str(manifest), redact=False)

        # Top-level key
        result = get_config_value(str(yaml_file), "server")
        assert result["key"] == "server"
        # 'server' is not a secret key, and its value (a dict) when stringified
        # contains 'password: secretpass' which redact_text would change
        # → Tier 2 by content
        assert result["tier"] == 2
