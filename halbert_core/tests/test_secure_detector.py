# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the secure content detector and model routing fallback."""
from __future__ import annotations

from halbert_core.integrations.secure_detector import detect_secure_content


# --- Provenance detector ------------------------------------------------

def test_provenance_host_scope_triggers_secure():
    assert detect_secure_content("", chunk_sources=["host/etc/ssh/sshd_config"]) is True


def test_provenance_non_host_scope_does_not_trigger():
    assert detect_secure_content("", chunk_sources=["knowledge/docs/ssh.md"]) is False


def test_provenance_mixed_sources_triggers_secure():
    sources = ["knowledge/docs/ssh.md", "host/etc/ssh/sshd_config"]
    assert detect_secure_content("", chunk_sources=sources) is True


def test_provenance_empty_sources_does_not_trigger():
    assert detect_secure_content("", chunk_sources=[]) is False


def test_provenance_none_sources_does_not_trigger():
    assert detect_secure_content("", chunk_sources=None) is False


# --- Content detector ---------------------------------------------------

def test_content_with_password_triggers_secure():
    ctx = "The sshd config has password=hunter2secret on port 2222"
    assert detect_secure_content(ctx) is True


def test_content_with_api_key_triggers_secure():
    ctx = "Configuration: api_key: sk-live-1234567890abcdef"
    assert detect_secure_content(ctx) is True


def test_content_with_pem_block_triggers_secure():
    ctx = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKBxKCAQEA\n-----END RSA PRIVATE KEY-----"
    assert detect_secure_content(ctx) is True


def test_clean_content_does_not_trigger():
    ctx = "The sshd is on port 2222 with password auth disabled. That's good."
    assert detect_secure_content(ctx) is False


def test_empty_content_does_not_trigger():
    assert detect_secure_content("") is False


def test_structural_content_does_not_trigger():
    ctx = "Port 2222\nPermitRootLogin no\nPasswordAuthentication no"
    assert detect_secure_content(ctx) is False


# --- Fail-toward-secure on exceptions -----------------------------------

def test_detector_fails_toward_secure_on_exception(monkeypatch):
    """If redact_text raises, the detector must return True."""
    from halbert_core.integrations import secure_detector as mod

    def boom(_text):
        raise RuntimeError("simulated redaction failure")

    monkeypatch.setattr(mod, "redact_text", boom)
    assert detect_secure_content("some context") is True


# --- Both parts combined ------------------------------------------------

def test_provenance_and_content_both_fire():
    ctx = "password=hunter2"
    sources = ["host/etc/app.conf"]
    assert detect_secure_content(ctx, chunk_sources=sources) is True
