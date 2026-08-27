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


# --- Structured (line-oriented) redaction -------------------------------
# Shapes a single-line regex provably cannot handle: the value lives on a
# later line than the key. See redact_structured_values() for why.


def test_next_line_value_is_redacted():
    """YAML block style puts the value on the following line."""
    y = 'access-points:\n  password:\n    "nextlinesecret"\n  dhcp4: true\n'
    out = redact_text(y)
    assert "nextlinesecret" not in out
    assert "dhcp4: true" in out
    assert out.count("\n") == y.count("\n")


def test_next_line_redaction_preserves_indentation():
    y = "password:\n      deeplyindentedsecret\n"
    out = redact_text(y)
    assert "deeplyindentedsecret" not in out
    assert "password:" in out
    # The value line keeps its indentation, so structure is readable.
    assert "\n      " in out


def test_key_with_no_value_at_all_is_left_alone():
    """A bare key at EOF, or followed by a non-indented line, is not a secret."""
    assert redact_text("password:\n") == "password:\n"
    out = redact_text("password:\nnetwork:\n  version: 2\n")
    assert "network:" in out
    assert "version: 2" in out


def test_quoted_next_line_scalar_containing_colon_is_redacted():
    """A colon inside a quoted scalar does not make it a mapping.

    This is the case that defeated the regex approach: any pattern narrow
    enough to spare `endpoint: https://x` also spared this and leaked it.
    """
    y = 'password:\n    "pa55:word:here"\n'
    out = redact_text(y)
    assert "pa55:word:here" not in out
    assert "password:" in out
    assert out.count("\n") == y.count("\n")


def test_literal_block_scalar_body_is_redacted():
    """`|` bodies are the normal way to write a multi-line secret."""
    y = "password: |\n  linesecretone\n  linesecrettwo\n"
    out = redact_text(y)
    assert "linesecretone" not in out
    assert "linesecrettwo" not in out
    assert out.count("\n") == y.count("\n")


def test_folded_block_scalar_body_is_redacted():
    y = "password: >\n  foldedsecret\n"
    out = redact_text(y)
    assert "foldedsecret" not in out
    assert out.count("\n") == y.count("\n")


def test_block_scalar_chomping_and_indent_modifiers_are_handled():
    """`|-`, `|+`, `>-` and `|2` are all valid block scalar headers."""
    for header in ("|-", "|+", ">-", "|2", "|2-"):
        y = f"token: {header}\n  modifiersecret\n"
        out = redact_text(y)
        assert "modifiersecret" not in out, f"leaked with header {header!r}"
        assert out.count("\n") == y.count("\n")


def test_block_scalar_body_survives_deeper_nesting():
    """Body lines are those indented deeper than the key; siblings are not."""
    y = (
        "wifis:\n"
        "  wlan0:\n"
        "    password: |\n"
        "      bodysecretone\n"
        "      bodysecrettwo\n"
        "    dhcp4: true\n"
    )
    out = redact_text(y)
    assert "bodysecretone" not in out
    assert "bodysecrettwo" not in out
    # The dedented sibling is not part of the value.
    assert "dhcp4: true" in out
    assert out.count("\n") == y.count("\n")


def test_blank_line_between_key_and_value_is_redacted():
    """A blank line does not terminate the value."""
    y = "password:\n\n  blanklinesecret\n"
    out = redact_text(y)
    assert "blanklinesecret" not in out
    assert out.count("\n") == y.count("\n")


def test_sequence_child_is_structure_not_secret():
    """A `- item` child is a list, not a credential (the 2b guard)."""
    y = "api:\n  - foo\n"
    out = redact_text(y)
    assert "- foo" in out
    assert out.count("\n") == y.count("\n")


def test_mapping_child_is_structure_not_secret():
    """A `key: value` child is a nested mapping; the inline rule owns it."""
    y = "api:\n  timeout: 30\n"
    out = redact_text(y)
    assert "timeout: 30" in out
    assert out.count("\n") == y.count("\n")


def test_non_secret_inline_url_is_left_alone():
    """`endpoint:` carries no secret keyword, so the URL structure stays."""
    y = "endpoint: https://example.invalid/path\n"
    assert redact_text(y) == y
