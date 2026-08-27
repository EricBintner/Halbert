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


# --- Inline values owned by the line pass ---------------------------------
# The line pass classifies EVERY line, inline values included. Before this,
# it bailed on an inline value and handed a format-aware decision back to a
# format-blind regex; each test below is a leak that boundary error caused.


def test_plist_password_string_is_redacted():
    """L1: launchd/SystemConfiguration plists put the value in the next tag."""
    p = "<key>Password</key>\n<string>hunter2secret</string>\n"
    out = redact_text(p)
    assert "hunter2secret" not in out
    # The marker must keep the XML well-formed: a literal `<secret>` would
    # read as an unknown element, so it goes inside the text node.
    assert "<string>[redacted]</string>" in out
    assert "<key>Password</key>" in out


def test_plist_nested_dict_token_is_redacted():
    """L1: launchd EnvironmentVariables nest the secret key one level down."""
    p = (
        "<key>EnvironmentVariables</key>\n"
        "<dict>\n"
        "  <key>API_TOKEN</key>\n"
        "  <string>sk-live-abcdef123456</string>\n"
        "</dict>\n"
    )
    out = redact_text(p)
    assert "sk-live-abcdef123456" not in out
    assert "<key>API_TOKEN</key>" in out
    assert out.count("\n") == p.count("\n")


def test_plist_data_blob_is_redacted():
    """L1: a `<data>` base64 blob under a secret key is still a credential."""
    p = "<key>SecretData</key>\n<data>aGVsbG8xMjM0NQ==</data>\n"
    out = redact_text(p)
    assert "aGVsbG8xMjM0NQ==" not in out
    assert "<data>[redacted]</data>" in out


def test_plist_same_line_key_and_value_is_redacted():
    """Both tags on one line is equally valid plist XML."""
    out = redact_text("<key>Password</key><string>hunter2secret</string>\n")
    assert "hunter2secret" not in out


def test_plist_non_secret_key_is_untouched():
    """The plist rule must not fire on ordinary keys."""
    p = "<key>NetBIOSName</key>\n<string>WORKSTATION</string>\n"
    assert redact_text(p) == p


def test_json_quoted_key_is_redacted():
    """L2: a quoted key put the keyword out of the regex's reach."""
    j = '{\n  "password": "hunter2secret"\n}\n'
    out = redact_text(j)
    assert "hunter2secret" not in out
    assert out.count("\n") == j.count("\n")


def test_json_single_line_object_is_redacted():
    """L2: one-line JSON, no whitespace around the separator."""
    out = redact_text('{"api_key":"AKIAIOSFODNN7SECRET"}\n')
    assert "AKIAIOSFODNN7SECRET" not in out


def test_bare_quoted_key_forms_are_redacted():
    """L2: quoted YAML/JSON keys, both quote styles."""
    assert "hunter2secret" not in redact_text('"password": "hunter2secret"\n')
    assert "hunter2secret" not in redact_text("'password': 'hunter2secret'\n")


def test_value_with_spaces_is_redacted_to_end_of_line():
    """L5: a passphrase with spaces leaked everything after the first word."""
    out = redact_text("psk=correct horse battery staple\n")
    assert "horse" not in out
    assert "battery" not in out
    assert "staple" not in out


def test_quoted_value_with_spaces_is_fully_redacted():
    """L5: the quoted form leaked the tail and the closing quote."""
    out = redact_text('password = "correct horse battery"\n')
    assert "correct" not in out
    assert "horse battery" not in out


def test_keyword_adjacency_is_not_required():
    """L6: real NetworkManager/wpa_supplicant keys are not bare keywords."""
    assert "A1B2C3D4E5" not in redact_text("wep-key0=A1B2C3D4E5\n")
    assert "A1B2C3D4E5" not in redact_text('wep_key0="A1B2C3D4E5"\n')
    assert "$6$salt$hash" not in redact_text("password_hash = $6$salt$hash\n")
    assert "topsecretvalue" not in redact_text("secret_value = topsecretvalue\n")


def test_fstab_option_list_keeps_non_secret_siblings():
    """O1: /etc/fstab is the first entry in the storage manifest.

    A comma-separated option list is its own shape: the secret ends at the
    delimiter, so uid/gid survive.
    """
    line = "//srv/share /mnt cifs username=bob,password=hunter2,uid=1000,gid=1000 0 0\n"
    out = redact_text(line)
    assert "hunter2" not in out
    assert "uid=1000" in out
    assert "gid=1000" in out
    assert "username=bob" in out


def test_option_list_without_sibling_keys_is_redacted_whole():
    """A comma inside a value is only a delimiter when a sibling key follows.

    Without that evidence the value runs to end of line (the L5 rule), so a
    passphrase that happens to contain a comma is not half-leaked.
    """
    out = redact_text("psk=correct,horse,battery\n")
    assert "horse" not in out
    assert "battery" not in out
