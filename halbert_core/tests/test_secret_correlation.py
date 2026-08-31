# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for cross-file secret correlation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config import secret_correlation as sc
from halbert_core.config.secret_correlation import (
    _secret_hash,
    _extract_secrets_from_canon,
    build_correlation_index,
    save_correlation_index,
    load_correlation_index,
    find_correlated_secrets,
    describe_with_correlations,
)


@pytest.fixture(autouse=True)
def _tmp_correlation_env(tmp_path, monkeypatch):
    """Keep every test's pepper and index inside its own tmp dir.

    The pepper path is derived from _CORRELATION_FILE, so redirecting the
    index to tmp_path also redirects the pepper — no test may touch the
    real ~/.local/share/halbert/config/.
    """
    path = str(tmp_path / "correlations.json")
    monkeypatch.setattr(sc, "_CORRELATION_FILE", path)
    sc._PEPPER_CACHE.clear()
    yield
    sc._PEPPER_CACHE.clear()


class TestSecretHash:
    """_secret_hash produces stable, one-way, pepper-keyed hashes."""

    def test_stable(self):
        assert _secret_hash("hunter2") == _secret_hash("hunter2")

    def test_different_values(self):
        assert _secret_hash("hunter2") != _secret_hash("hunter3")

    def test_truncated_to_16(self):
        assert len(_secret_hash("test")) == 16


class TestPepperedHash:
    """REV-01 F5: the index hash is HMAC-keyed by a separate pepper.

    A bare sha256(secret)[:16] does not slow a dictionary attack on human
    passwords — any candidate is hashed and compared — and the index file
    enumerates where every secret on the machine lives. Keying the hash
    with a locally-generated pepper (stored 0600 in a SEPARATE file from
    the index) means an exfiltrated index alone verifies nothing.
    """

    def _pepper_file(self):
        return os.path.join(
            os.path.dirname(sc._CORRELATION_FILE), sc._PEPPER_FILENAME
        )

    def test_not_plain_sha256(self):
        """A candidate hashed offline (no pepper) never matches the index."""
        stored = _secret_hash("hunter2")
        for candidate in ("hunter2", "password", "correcthorse"):
            plain = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16]
            assert stored != plain

    @pytest.mark.skipif(os.name != "posix", reason="0600 is a POSIX mode")
    def test_pepper_file_beside_index_mode_0600(self):
        """The pepper is a separate 0600 file, created on first use."""
        _secret_hash("hunter2")
        pepper = self._pepper_file()
        assert os.path.exists(pepper)
        assert pepper != sc._CORRELATION_FILE
        assert os.stat(pepper).st_mode & 0o777 == 0o600

    def test_pepper_generated_once_and_reused(self):
        """Repeated calls reuse the stored pepper — it is not regenerated."""
        h1 = _secret_hash("hunter2")
        pepper = self._pepper_file()
        with open(pepper, "rb") as f:
            first = f.read()
        h2 = _secret_hash("hunter2")
        with open(pepper, "rb") as f:
            assert f.read() == first
        assert h1 == h2

    def test_fresh_installs_get_distinct_peppers(self, tmp_path):
        """Two machines (fresh pepper each) never produce matching hashes."""
        monkey = pytest.MonkeyPatch()
        try:
            monkey.setattr(
                sc, "_CORRELATION_FILE", str(tmp_path / "a" / "correlations.json")
            )
            h1 = _secret_hash("hunter2")
            monkey.setattr(
                sc, "_CORRELATION_FILE", str(tmp_path / "b" / "correlations.json")
            )
            h2 = _secret_hash("hunter2")
        finally:
            monkey.undo()
        assert h1 != h2

    def test_exfiltrated_index_alone_verifies_nothing(self, tmp_path):
        """The index copied without its pepper matches no candidate value."""
        entries = [
            {
                "path": "/etc/app1.conf",
                "canon": {"kind": "ini", "sections": {"default": {"password": "samepass"}}},
            },
            {
                "path": "/etc/app2.conf",
                "canon": {"kind": "ini", "sections": {"default": {"pass": "samepass"}}},
            },
        ]
        save_correlation_index(build_correlation_index(entries))
        assert len(find_correlated_secrets("password", "samepass", "/etc/app1.conf")) == 1

        # Attacker exfiltrates only the index file...
        stolen = tmp_path / "stolen"
        stolen.mkdir()
        shutil.copy(sc._CORRELATION_FILE, stolen / "correlations.json")
        monkey = pytest.MonkeyPatch()
        try:
            monkey.setattr(sc, "_CORRELATION_FILE", str(stolen / "correlations.json"))
            sc._PEPPER_CACHE.clear()
            # ...their machine generates its own pepper → nothing verifies
            assert find_correlated_secrets("password", "samepass", "/etc/app1.conf") == []
        finally:
            monkey.undo()
            sc._PEPPER_CACHE.clear()
        # and the stolen file still contains no raw value to work on
        with open(stolen / "correlations.json") as f:
            assert "samepass" not in f.read()

    def test_missing_pepper_fails_closed(self):
        """An index whose pepper is lost yields no matches — never a false hit."""
        entries = [
            {
                "path": "/etc/app2.conf",
                "canon": {"kind": "ini", "sections": {"default": {"pass": "samepass"}}},
            },
        ]
        save_correlation_index(build_correlation_index(entries))
        assert len(find_correlated_secrets("password", "samepass", "/etc/app1.conf")) == 1

        os.remove(self._pepper_file())
        sc._PEPPER_CACHE.clear()
        assert find_correlated_secrets("password", "samepass", "/etc/app1.conf") == []

    def test_build_save_find_roundtrip_with_pepper(self):
        """build, save, and find all use the same pepper end to end."""
        entries = [
            {
                "path": "/etc/postfix/sasl_passwd",
                "canon": {"kind": "ini", "sections": {"default": {"password": "samepass"}}},
            },
            {
                "path": "/etc/msmtprc",
                "canon": {"kind": "ini", "sections": {"default": {"pass": "samepass"}}},
            },
        ]
        save_correlation_index(build_correlation_index(entries))
        results = find_correlated_secrets("password", "samepass", "/etc/postfix/sasl_passwd")
        assert len(results) == 1
        assert results[0]["path"] == "/etc/msmtprc"


class TestExtractSecrets:
    """_extract_secrets_from_canon finds secrets in parsed config."""

    def test_ini_secret_key(self):
        canon = {
            "kind": "ini",
            "sections": {
                "default": {
                    "password": "hunter2",
                    "user": "admin",
                }
            }
        }
        secrets = _extract_secrets_from_canon(canon, "/etc/app.conf")
        assert len(secrets) == 1
        assert secrets[0][0] == "password"
        assert secrets[0][1] == "hunter2"

    def test_ini_secret_value(self):
        """A value that triggers redact_text but has a neutral key."""
        canon = {
            "kind": "ini",
            "sections": {
                "default": {
                    "config": "api_key=sk-abcdefghijklmnopqrstuvwxyz0123456789",
                }
            }
        }
        secrets = _extract_secrets_from_canon(canon, "/etc/app.conf")
        assert len(secrets) == 1

    def test_yaml_nested_secret(self):
        canon = {
            "kind": "yaml",
            "tree": {
                "database": {
                    "password": "secretpass",
                    "host": "localhost",
                },
                "api": {
                    "key": "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB",
                },
            }
        }
        secrets = _extract_secrets_from_canon(canon, "/etc/app.yaml")
        assert len(secrets) == 2
        keys = [s[0] for s in secrets]
        assert "database.password" in keys
        assert "api.key" in keys

    def test_no_secrets(self):
        canon = {
            "kind": "ini",
            "sections": {
                "default": {
                    "port": "8080",
                    "host": "localhost",
                }
            }
        }
        secrets = _extract_secrets_from_canon(canon, "/etc/app.conf")
        assert len(secrets) == 0


class TestCorrelationIndex:
    """build_correlation_index groups secrets by value hash."""

    def test_same_secret_grouped(self):
        entries = [
            {
                "path": "/etc/postfix/sasl_passwd",
                "canon": {
                    "kind": "ini",
                    "sections": {"default": {"password": "samepass"}},
                },
            },
            {
                "path": "/etc/msmtprc",
                "canon": {
                    "kind": "ini",
                    "sections": {"default": {"pass": "samepass"}},
                },
            },
        ]
        index = build_correlation_index(entries)
        # Both entries have the same value "samepass" → 1 hash with 2 locations
        assert len(index) == 1
        hash_key = list(index.keys())[0]
        assert len(index[hash_key]) == 2

    def test_different_secrets_separate(self):
        entries = [
            {
                "path": "/etc/app1.conf",
                "canon": {
                    "kind": "ini",
                    "sections": {"default": {"password": "pass1"}},
                },
            },
            {
                "path": "/etc/app2.conf",
                "canon": {
                    "kind": "ini",
                    "sections": {"default": {"password": "pass2"}},
                },
            },
        ]
        index = build_correlation_index(entries)
        assert len(index) == 2

    def test_empty_entries(self):
        index = build_correlation_index([])
        assert index == {}


class TestSaveLoadIndex:
    """save/load correlation index round-trip."""

    def test_save_and_load(self, tmp_path, monkeypatch):
        path = str(tmp_path / "correlations.json")
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            path,
        )
        index = {"abc123": [{"path": "/etc/app", "key": "password", "section": "default"}]}
        save_correlation_index(index)
        loaded = load_correlation_index()
        assert loaded == index

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            str(tmp_path / "nonexistent.json"),
        )
        assert load_correlation_index() == {}


class TestFindCorrelated:
    """find_correlated_secrets locates the same secret in other files."""

    def test_finds_correlation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            str(tmp_path / "correlations.json"),
        )
        index = {
            _secret_hash("samepass"): [
                {"path": "/etc/app1.conf", "key": "password", "section": "default"},
                {"path": "/etc/app2.conf", "key": "pass", "section": "default"},
                {"path": "/etc/app3.conf", "key": "password", "section": "default"},
            ]
        }
        save_correlation_index(index)

        # Find correlations from app1 — should return app2 and app3
        results = find_correlated_secrets("password", "samepass", "/etc/app1.conf")
        assert len(results) == 2
        paths = [r["path"] for r in results]
        assert "/etc/app2.conf" in paths
        assert "/etc/app3.conf" in paths

    def test_no_correlation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            str(tmp_path / "correlations.json"),
        )
        save_correlation_index({})
        results = find_correlated_secrets("password", "uniquepass", "/etc/app.conf")
        assert results == []

    def test_excludes_current_location(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            str(tmp_path / "correlations.json"),
        )
        h = _secret_hash("samepass")
        index = {
            h: [
                {"path": "/etc/app.conf", "key": "password", "section": "default"},
            ]
        }
        save_correlation_index(index)
        results = find_correlated_secrets("password", "samepass", "/etc/app.conf")
        assert results == []  # same location excluded


class TestDescribeWithCorrelations:
    """describe_with_correlations adds correlation info to describe_secret."""

    def test_with_correlation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            str(tmp_path / "correlations.json"),
        )
        h = _secret_hash("samepass")
        index = {
            h: [
                {"path": "/etc/app1.conf", "key": "password", "section": "default"},
                {"path": "/etc/app2.conf", "key": "pass", "section": "default"},
            ]
        }
        save_correlation_index(index)

        result = describe_with_correlations("password", "samepass", "/etc/app1.conf")
        assert "correlations" in result
        assert result["correlation_count"] == 1
        assert result["correlations"][0]["path"] == "/etc/app2.conf"
        # The raw value must NOT appear
        assert "samepass" not in str(result)

    def test_without_correlation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.config.secret_correlation._CORRELATION_FILE",
            str(tmp_path / "correlations.json"),
        )
        save_correlation_index({})

        result = describe_with_correlations("password", "uniquepass", "/etc/app.conf")
        assert "correlations" not in result
        assert "correlation_count" not in result
        assert result["redacted"] is True
