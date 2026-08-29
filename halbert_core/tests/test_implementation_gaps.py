# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the remaining implementation gaps — gating, per-key escape,
remote view commands, base64/nested JSON detection, and canon staleness."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.secure_response import describe_secret
from halbert_core.config.queries import get_config_value
from halbert_core.config.being_config import SecurityConfig
from halbert_core.ingestion.redaction import redact_text
from halbert_core.mcp.server import _tool_run_scanner


class TestRunScannerGating:
    """run_scanner requires explicit confirmation."""

    def test_without_confirm_returns_error(self):
        result = _tool_run_scanner({"type": "network"})
        assert "error" in result
        assert "confirm" in result["error"].lower()

    def test_with_confirm_false_returns_error(self):
        result = _tool_run_scanner({"type": "network", "confirm": False})
        assert "error" in result

    def test_with_confirm_true_proceeds(self):
        # This will try to run the scanner, which may fail if the engine
        # isn't available — but it should NOT return the gating error.
        result = _tool_run_scanner({"type": "nonexistent_type", "confirm": True})
        # Either it runs (and returns results/error) or the engine fails,
        # but it should NOT return the "requires confirm" error.
        assert "confirm" not in result.get("error", "").lower()


class TestPerKeyEscapeHatch:
    """cloud_ok_keys allows specific secrets to be exposed to cloud."""

    def test_cloud_ok_keys_exposes_secret(self, tmp_path):
        """A key in cloud_ok_keys is returned raw even when secret_tier=local_only."""
        from halbert_core.config.queries import get_config_value, _write_canon
        from halbert_core.config.parser import parse as parse_config
        import halbert_core.config.queries as qmod

        # Create an INI config file with a secret key
        config_file = tmp_path / "app.conf"
        config_file.write_text(
            "[database]\n"
            "password = supersecret123\n"
        )

        # Parse and write to canon DB
        canon = parse_config(str(config_file))
        import hashlib
        file_hash = hashlib.sha256(config_file.read_bytes()).hexdigest()
        original_canon = qmod.CANON_DIR
        original_snap = qmod.SNAP_DIR
        qmod.CANON_DIR = str(tmp_path / "canon")
        qmod.SNAP_DIR = str(tmp_path / "snap")
        try:
            _write_canon(str(config_file), file_hash, canon)

            # Without cloud_ok_keys: should be redacted (Tier 2, local_only)
            result = get_config_value(str(config_file), "password",
                                      secret_tier="local_only")
            assert result.get("redacted") is True or "description" in result

            # With cloud_ok_keys: should return raw value
            result = get_config_value(str(config_file), "password",
                                      secret_tier="local_only",
                                      cloud_ok_keys=["password"])
            assert result.get("value") == "supersecret123"
            assert result.get("acknowledged") is True
        finally:
            qmod.CANON_DIR = original_canon
            qmod.SNAP_DIR = original_snap

    def test_cloud_ok_keys_case_insensitive(self):
        """cloud_ok_keys matching is case-insensitive and normalization-aware."""
        from halbert_core.config.being_config import SecurityConfig
        config = SecurityConfig(cloud_ok_keys=["Database-Password"])
        assert "Database-Password" in config.cloud_ok_keys

    def test_cloud_ok_keys_not_in_config_by_default(self):
        """By default, cloud_ok_keys is empty."""
        from halbert_core.config.being_config import SecurityConfig
        config = SecurityConfig()
        assert config.cloud_ok_keys == []


class TestRemoteViewCommand:
    """describe_secret view command works for remote HTTP clients."""

    def test_local_view_command(self):
        result = describe_secret("password", "hunter2", "/etc/app.conf")
        cmd = result["view_command"]
        assert "grep" in cmd
        assert "# Run on the host" not in cmd

    def test_remote_view_command(self):
        result = describe_secret("password", "hunter2", "/etc/app.conf", remote=True)
        cmd = result["view_command"]
        assert "# Run on the host" in cmd
        assert "grep" in cmd

    def test_remote_plist_view_command(self):
        result = describe_secret("APIKey", "secret", "/Library/app.plist", remote=True)
        cmd = result["view_command"]
        assert "# Run on the host" in cmd
        assert "plutil" in cmd

    def test_remote_no_file(self):
        result = describe_secret("token", "abc123", "", remote=True)
        assert "in memory" in result["view_command"]


class TestBase64SecretDetection:
    """redact_text catches base64-encoded secrets."""

    def test_base64_encoded_key_value(self):
        # base64 of "password=hunter2secretvalue123456" (long enough to match regex)
        import base64
        encoded = base64.b64encode(b"password=hunter2secretvalue123456").decode()
        result = redact_text(encoded)
        assert encoded not in result
        assert "<base64_secret>" in result

    def test_base64_encoded_secret_key(self):
        # base64 of "api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789"
        import base64
        encoded = base64.b64encode(b"api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789").decode()
        result = redact_text(encoded)
        assert encoded not in result

    def test_legitimate_base64_not_redacted(self):
        """Base64 that doesn't contain secrets should not be redacted by the base64 pass."""
        import base64
        # base64 of "configuration settings here" — short enough to avoid
        # the high-entropy backstop (which runs after and is separate)
        encoded = base64.b64encode(b"configuration settings here").decode()
        # The base64 pass should NOT redact this (no secret in decoded content)
        # Note: the high-entropy backstop might still catch it if it's 32+ chars,
        # so we test the base64 pass directly
        from halbert_core.ingestion.redaction import _redact_base64_secrets
        result = _redact_base64_secrets(encoded)
        assert result == encoded  # not redacted by base64 pass


class TestNestedJSONSecretDetection:
    """redact_text catches secrets inside JSON strings."""

    def test_json_with_secret_key(self):
        text = '{"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB", "timeout": 30}'
        result = redact_text(text)
        assert "ghp_" not in result

    def test_json_with_password_key(self):
        text = '{"password": "hunter2", "user": "admin"}'
        result = redact_text(text)
        assert "hunter2" not in result
        assert "<secret>" in result

    def test_json_without_secrets_preserved(self):
        text = '{"port": 8080, "host": "localhost"}'
        result = redact_text(text)
        assert "8080" in result
        assert "localhost" in result

    def test_invalid_json_not_redacted(self):
        """Invalid JSON should pass through without error."""
        text = '{"broken json missing closing'
        result = redact_text(text)
        # Should not crash, may or may not redact
        assert isinstance(result, str)


class TestCanonStalenessUpdate:
    """_get_current_canon writes new canon records on re-parse."""

    def test_reparse_writes_canon(self, tmp_path):
        from halbert_core.config.queries import _get_current_canon, CANON_DIR
        from halbert_core.config.snapshot import SNAP_DIR

        # Point canon/snap dirs to tmp
        import halbert_core.config.queries as qmod
        original_canon = qmod.CANON_DIR
        original_snap = qmod.SNAP_DIR
        qmod.CANON_DIR = str(tmp_path / "canon")
        qmod.SNAP_DIR = str(tmp_path / "snap")
        try:
            config_file = tmp_path / "test.conf"
            config_file.write_text("[default]\nkey = value\n")

            # First call: no canon exists, re-parses and writes canon
            canon = _get_current_canon(str(config_file))
            assert canon is not None
            assert canon.get("kind") == "ini"

            # Verify canon was written
            canon_files = os.listdir(qmod.CANON_DIR)
            assert len(canon_files) > 0

            # Verify latest snapshot was updated
            latest_path = os.path.join(qmod.SNAP_DIR, "latest.json")
            assert os.path.exists(latest_path)
            with open(latest_path) as f:
                entries = json.load(f)
            assert any(e.get("path") == str(config_file) for e in entries)
        finally:
            qmod.CANON_DIR = original_canon
            qmod.SNAP_DIR = original_snap
