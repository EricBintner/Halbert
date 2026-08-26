# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the precedence resolution engine."""

import os
import tempfile
import shutil

import pytest

from halbert_core.findings.precedence import (
    PrecedenceEngine,
    SYSTEMD_ADDITIVE_KEYS,
)


@pytest.fixture
def config_dir():
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


@pytest.fixture
def systemd_fixture(config_dir):
    """Base unit + drop-in with additive and override directives."""
    base = os.path.join(config_dir, "systemd", "system", "mysvc.service")
    _write(base, (
        "[Unit]\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Environment=FOO=1\n"
        "ExecStartPre=/bin/a\n"
        "MemoryMax=2G\n"
        "ExecStart=/bin/run\n"
    ))
    dropin_dir = os.path.join(config_dir, "systemd", "system", "mysvc.service.d")
    _write(os.path.join(dropin_dir, "10-extra.conf"), (
        "[Unit]\n"
        "After=remote-fs.target\n"
        "\n"
        "[Service]\n"
        "Environment=BAR=2\n"
        "ExecStartPre=/bin/b\n"
        "MemoryMax=1G\n"
    ))
    return config_dir


class TestSystemdAdditiveDirectives:
    def test_additive_keys_accumulate_without_conflicts(self, systemd_fixture):
        engine = PrecedenceEngine(config_dir=systemd_fixture)
        result = engine.resolve_systemd_unit("mysvc")

        conflict_keys = {c["key"] for c in result["conflicts"]}
        # Additive directives must NOT be flagged despite differing values
        assert "unit/after" not in conflict_keys
        assert "service/environment" not in conflict_keys
        assert "service/execstartpre" not in conflict_keys

    def test_additive_values_merge_into_lists(self, systemd_fixture):
        engine = PrecedenceEngine(config_dir=systemd_fixture)
        result = engine.resolve_systemd_unit("mysvc")

        assert result["effective"]["unit/after"] == [
            "network.target", "remote-fs.target"
        ]
        assert result["effective"]["service/environment"] == ["FOO=1", "BAR=2"]
        assert result["effective"]["service/execstartpre"] == ["/bin/a", "/bin/b"]

    def test_override_directive_differing_is_conflict(self, systemd_fixture):
        engine = PrecedenceEngine(config_dir=systemd_fixture)
        result = engine.resolve_systemd_unit("mysvc")

        conflicts = {c["key"]: c for c in result["conflicts"]}
        # MemoryMax is override-capable — differing values are a conflict
        assert "service/memorymax" in conflicts
        assert conflicts["service/memorymax"]["effective"] == "1G"

    def test_matching_values_no_conflict(self, config_dir):
        base = os.path.join(config_dir, "systemd", "system", "svc.service")
        _write(base, "[Service]\nEnvironment=FOO=1\nMemoryMax=1G\n")
        dropin = os.path.join(config_dir, "systemd", "system", "svc.service.d")
        _write(os.path.join(dropin, "10.conf"), "[Service]\nEnvironment=FOO=1\nMemoryMax=1G\n")

        engine = PrecedenceEngine(config_dir=config_dir)
        result = engine.resolve_systemd_unit("svc")
        assert result["conflicts"] == []
        assert result["effective"]["service/environment"] == ["FOO=1", "FOO=1"]

    def test_allowlist_contents(self):
        assert "service/environment" in SYSTEMD_ADDITIVE_KEYS
        assert "unit/after" in SYSTEMD_ADDITIVE_KEYS
        assert "socket/listenstream" in SYSTEMD_ADDITIVE_KEYS
        assert "service/memorymax" not in SYSTEMD_ADDITIVE_KEYS


class TestSshdResolution:
    def test_include_at_top_dropin_wins(self, config_dir):
        _write(os.path.join(config_dir, "ssh", "sshd_config"), (
            f"Include {config_dir}/ssh/sshd_config.d/*.conf\n"
            "Port 22\n"
            "PasswordAuthentication yes\n"
        ))
        _write(os.path.join(config_dir, "ssh", "sshd_config.d", "10.conf"), (
            "Port 2222\n"
        ))

        engine = PrecedenceEngine(config_dir=config_dir)
        result = engine.resolve_sshd()
        # First match wins; Include at top means the drop-in is read first
        assert result["effective"]["port"] == "2222"
        assert result["effective"]["passwordauthentication"] == "yes"
        assert result["include_aware"] is True

    def test_include_at_bottom_base_wins(self, config_dir):
        _write(os.path.join(config_dir, "ssh", "sshd_config"), (
            "PasswordAuthentication yes\n"
            f"Include {config_dir}/ssh/sshd_config.d/*.conf\n"
        ))
        _write(os.path.join(config_dir, "ssh", "sshd_config.d", "10.conf"), (
            "PasswordAuthentication no\n"
        ))

        engine = PrecedenceEngine(config_dir=config_dir)
        result = engine.resolve_sshd()
        # First match wins: base file's value was read before the Include
        assert result["effective"]["passwordauthentication"] == "yes"
        # Differing values are still reported as a conflict
        keys = {c["key"] for c in result["conflicts"]}
        assert "passwordauthentication" in keys

    def test_no_include_falls_back_to_last_wins(self, config_dir):
        # No Include directive anywhere — legacy behavior is preserved:
        # drop-ins are appended after the base, last match wins.
        _write(os.path.join(config_dir, "ssh", "sshd_config"), (
            "PasswordAuthentication yes\n"
        ))
        _write(os.path.join(config_dir, "ssh", "sshd_config.d", "10.conf"), (
            "PasswordAuthentication no\n"
        ))

        engine = PrecedenceEngine(config_dir=config_dir)
        result = engine.resolve_sshd()
        assert result["include_aware"] is False
        assert result["effective"]["passwordauthentication"] == "no"

    def test_conflict_still_reported_first_match(self, config_dir):
        _write(os.path.join(config_dir, "ssh", "sshd_config"), (
            f"Include {config_dir}/ssh/sshd_config.d/*.conf\n"
            "Port 22\n"
        ))
        _write(os.path.join(config_dir, "ssh", "sshd_config.d", "10.conf"), "Port 2222\n")

        engine = PrecedenceEngine(config_dir=config_dir)
        result = engine.resolve_sshd()
        conflicts = {c["key"]: c for c in result["conflicts"]}
        assert "port" in conflicts
        assert conflicts["port"]["effective"] == "2222"
