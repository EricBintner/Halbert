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


def test_lkdc_realm_hash_is_redacted():
    """com.apple.smb.server.plist carries an LKDC Kerberos realm hash."""
    smb = (
        "<key>LocalKerberosRealm</key>\n"
        "<string>LKDC:SHA1.9F2C4E1A7B3D5F8E0C6A2B4D9E1F3A5C7B8D0E2F</string>\n"
    )
    out = redact_text(smb)
    assert "9F2C4E1A7B3D5F8E0C6A2B4D9E1F3A5C7B8D0E2F" not in out
    assert "<lkdc_realm>" in out


def test_plain_text_without_lkdc_is_untouched():
    text = "<key>NetBIOSName</key>\n<string>WORKSTATION</string>\n"
    assert redact_text(text) == "<key>NetBIOSName</key>\n<string>WORKSTATION</string>\n"


def test_redaction_does_not_span_newlines():
    """`\\s*` would match \\n and swallow the next line's first token.

    /etc/netplan/*.yaml is harvested by the network role manifest, so a
    key-like mapping at end-of-line must not consume the following line.
    """
    out = redact_text("api:\n  - foo\n")
    assert "foo" in out
    assert "- foo" in out


def test_netplan_wifi_redacts_value_without_eating_structure():
    """Real netplan carries `password:` under access-points:.

    The secret value must go, but the surrounding YAML structure must
    survive — a newline-spanning separator would consume the next line's
    first token and corrupt the file. /etc/netplan/*.yaml is harvested by
    the network role manifest, so this is the production case.
    """
    netplan = (
        "network:\n"
        "  version: 2\n"
        "  wifis:\n"
        "    wlan0:\n"
        "      access-points:\n"
        '        "HomeNet":\n'
        '          password: "sup3rs3cretwifi"\n'
        "      dhcp4: true\n"
    )
    out = redact_text(netplan)

    # The secret is gone.
    assert "sup3rs3cretwifi" not in out
    # But every structural line around it survives intact.
    assert "dhcp4: true" in out
    assert "access-points:" in out
    assert '"HomeNet":' in out
    # And the line following the secret was not swallowed.
    assert out.count("\n") == netplan.count("\n")


def test_secret_with_horizontal_whitespace_still_redacted():
    """The WireGuard case that motivated the change must keep working."""
    assert "abc123def" not in redact_text("PrivateKey = abc123def\n")
    assert "xyz789" not in redact_text("psk\t=\txyz789\n")
