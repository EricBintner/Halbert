# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Secret-redaction coverage for config formats staged into SourcePrep.

Every pattern here corresponds to a real file the role manifests harvest.
A regression in any of these ships plaintext credentials into a searchable
knowledge scope.
"""
from __future__ import annotations

from halbert_core.ingestion.redaction import redact_text


def test_networkmanager_psk_is_redacted():
    """NetworkManager stores WiFi passwords as a bare psk= line."""
    nm = "[wifi-security]\nkey-mgmt=wpa-psk\npsk=hunter2supersecret\n"
    out = redact_text(nm)
    assert "hunter2supersecret" not in out
    assert "<secret>" in out


def test_wireguard_private_key_with_spaces_is_redacted():
    """Standard WireGuard formatting puts spaces around the separator."""
    wg = "[Interface]\nPrivateKey = aGVsbG93b3JsZGJhc2U2NHNlY3JldA=\nListenPort = 51820\n"
    out = redact_text(wg)
    assert "aGVsbG93b3JsZGJhc2U2NHNlY3JldA=" not in out
    assert "<secret>" in out


def test_wireguard_preshared_key_is_redacted():
    wg = "[Peer]\nPresharedKey = c2hhcmVkc2VjcmV0dmFsdWU=\n"
    out = redact_text(wg)
    assert "c2hhcmVkc2VjcmV0dmFsdWU=" not in out


def test_existing_token_patterns_still_redacted():
    """Guard against the widened regex breaking what already worked."""
    assert "abc123" not in redact_text("api_key=abc123")
    assert "s3cret" not in redact_text("password:s3cret")


def test_listen_port_is_not_redacted():
    """The widened regex must not swallow ordinary non-secret directives."""
    out = redact_text("[Interface]\nListenPort = 51820\n")
    assert "51820" in out
