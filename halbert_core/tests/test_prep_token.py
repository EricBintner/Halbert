# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for PREP_DAEMON_TOKEN management."""
from __future__ import annotations

import os
import stat

from halbert_core.integrations.prep_token import (
    auth_headers,
    ensure_token,
    get_token,
    _token_path,
)


def test_ensure_token_generates_and_persists(tmp_path, monkeypatch):
    """ensure_token creates a token file when none exists."""
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("PREP_DAEMON_TOKEN", raising=False)

    token = ensure_token()
    assert len(token) == 64  # 32 bytes hex = 64 chars
    assert token.isalnum()

    # File exists with 0600 permissions
    path = _token_path()
    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_ensure_token_returns_existing(tmp_path, monkeypatch):
    """ensure_token returns the existing token without regenerating."""
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("PREP_DAEMON_TOKEN", raising=False)

    token1 = ensure_token()
    token2 = ensure_token()
    assert token1 == token2


def test_env_var_takes_precedence(tmp_path, monkeypatch):
    """PREP_DAEMON_TOKEN env var is returned without reading the file."""
    monkeypatch.setenv("PREP_DAEMON_TOKEN", "env-token-12345")
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(tmp_path))

    assert get_token() == "env-token-12345"
    assert ensure_token() == "env-token-12345"
    # File should NOT be written when env var is set
    assert not _token_path().exists()


def test_auth_headers_with_token(tmp_path, monkeypatch):
    """auth_headers returns Authorization: Bearer when token exists."""
    monkeypatch.setenv("PREP_DAEMON_TOKEN", "test-token-abc")
    headers = auth_headers()
    assert headers == {"Authorization": "Bearer test-token-abc"}


def test_auth_headers_without_token(tmp_path, monkeypatch):
    """auth_headers returns empty dict when no token is configured."""
    monkeypatch.delenv("PREP_DAEMON_TOKEN", raising=False)
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(tmp_path / "nonexistent"))
    headers = auth_headers()
    assert headers == {}


def test_get_token_returns_none_when_nothing_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("PREP_DAEMON_TOKEN", raising=False)
    monkeypatch.setenv("Halbert_CONFIG_DIR", str(tmp_path / "nonexistent"))
    assert get_token() is None
