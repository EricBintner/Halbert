# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for cross-file secret correlation."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.secret_correlation import (
    _secret_hash,
    _extract_secrets_from_canon,
    build_correlation_index,
    save_correlation_index,
    load_correlation_index,
    find_correlated_secrets,
    describe_with_correlations,
)


class TestSecretHash:
    """_secret_hash produces stable, one-way hashes."""

    def test_stable(self):
        assert _secret_hash("hunter2") == _secret_hash("hunter2")

    def test_different_values(self):
        assert _secret_hash("hunter2") != _secret_hash("hunter3")

    def test_truncated_to_16(self):
        assert len(_secret_hash("test")) == 16


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
