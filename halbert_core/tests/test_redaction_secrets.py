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
    """The URL structure must survive *under a secret-keyword parent*.

    The previous version of this test fed a line with no secret keyword in
    it, so nothing could ever have touched it -- it asserted the absence of
    a code path rather than its behaviour. `api:` is the keyword-bearing
    parent from the discrimination example in redaction.py, and it is the
    side of that example that was never actually exercised.
    """
    assert redact_text("api:\n  endpoint: https://x\n") == "api:\n  endpoint: https://x\n"
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


# --- Comments, mapping discrimination, and line endings -------------------


def test_comment_between_key_and_value_does_not_terminate_it():
    """L3: PyYAML reads this as {'password': 'realsecret'}.

    A blank line already did not terminate a deferred value; a comment does
    not either, but it used to `break` the scan and leave the value below it
    in plaintext.
    """
    y = "password:\n  # comment\n  realsecret\n"
    out = redact_text(y)
    assert "realsecret" not in out
    assert "# comment" in out
    assert out.count("\n") == y.count("\n")


def test_comment_only_inline_value_still_defers():
    """PyYAML reads `password: # note` + indented line as the value."""
    out = redact_text("password: # note\n  realsecret\n")
    assert "realsecret" not in out


def test_comment_does_not_terminate_a_non_secret_mapping():
    """The comment skip must not turn a nested mapping into a value."""
    y = "api:\n  # comment\n  timeout: 30\n"
    out = redact_text(y)
    assert "timeout: 30" in out


def test_comment_inside_a_block_scalar_is_body_not_comment():
    """Inside `|` a `#` is literal text, so it is part of the credential."""
    y = "password: |\n  # notacomment\n  linesecret\n"
    out = redact_text(y)
    assert "notacomment" not in out
    assert "linesecret" not in out


def test_block_header_with_trailing_comment_is_recognised():
    """L4: YAML permits `password: | # note`.

    The anchored header pattern did not match it, so TOKEN_RE ate the `|`
    and orphaned the whole block body in plaintext -- the exact failure the
    pass ordering exists to prevent.
    """
    y = "password: | # inline comment\n  realsecret\n  secondline\n"
    out = redact_text(y)
    assert "realsecret" not in out
    assert "secondline" not in out
    assert out.count("\n") == y.count("\n")


def test_unquoted_scalar_containing_colon_is_redacted():
    """L8: `pa55:word:here` is a scalar, not a mapping.

    Ground truth, not folklore: yaml.safe_load('password:\\n  pa55:word:here\\n')
    returns {'password': 'pa55:word:here'}. YAML opens a mapping only when a
    colon is followed by whitespace or end of line.
    """
    y = "password:\n  pa55:word:here\n"
    out = redact_text(y)
    assert "pa55:word:here" not in out
    assert out.count("\n") == y.count("\n")


def test_mapping_discrimination_still_spares_real_structure():
    """The narrowed mapping rule must not start eating nested mappings."""
    assert redact_text("api:\n  endpoint: https://x\n") == "api:\n  endpoint: https://x\n"
    assert "timeout: 30" in redact_text("api:\n  timeout: 30\n")
    assert "- foo" in redact_text("api:\n  - foo\n")


def test_quoted_mapping_keys_are_not_eaten():
    """O2: a leading quote is not proof of a scalar.

    netplan writes SSIDs as quoted mapping keys (`"HomeNet":`), and the old
    rule ate the first child of `keys:` while leaving the rest -- a
    half-destroyed mapping.
    """
    y = 'keys:\n  "primary": /etc/ssl/a.pem\n  "backup": /etc/ssl/b.pem\n'
    out = redact_text(y)
    assert '"primary": /etc/ssl/a.pem' in out
    assert '"backup": /etc/ssl/b.pem' in out


def test_crlf_line_endings_are_preserved():
    """O4: rewriting a line must not leave the file with mixed endings."""
    y = "password:\r\n  hunter2secret\r\n  keepme\r\n"
    out = redact_text(y)
    assert "hunter2secret" not in out
    assert out == "password:\r\n  <secret>\r\n  keepme\r\n"
    assert "\n" not in out.replace("\r\n", "")


def test_crlf_inline_value_keeps_its_ending():
    out = redact_text("psk=hunter2secret\r\nkeep=me\r\n")
    assert "hunter2secret" not in out
    assert out == "<secret>\r\nkeep=me\r\n"


def test_tab_indentation_is_not_read_as_a_dedent():
    """A tab is one character but eight columns; comparing raw lengths made
    it look like a dedent from four spaces and ended the value early."""
    y = "    password:\n\tdeepsecret\n"
    out = redact_text(y)
    assert "deepsecret" not in out


# --- Keyword coverage -----------------------------------------------------


def test_short_and_alternate_secret_keywords_are_covered():
    """L7: real config files do not spell it `password` every time."""
    cases = {
        "passphrase=hunter2secret\n": "hunter2secret",
        "pass=hunter2secret\n": "hunter2secret",
        "passwd=hunter2secret\n": "hunter2secret",
        "credential=hunter2secret\n": "hunter2secret",
        "auth=hunter2secret\n": "hunter2secret",
        "Authorization: Bearer abcdefghijklmnop\n": "abcdefghijklmnop",
        "pin=987654\n": "987654",
        "seed=hunter2secret\n": "hunter2secret",
        "pwd=hunter2secret\n": "hunter2secret",
        "client_secret=hunter2secret\n": "hunter2secret",
        "access_token: hunter2secret\n": "hunter2secret",
    }
    for text, leaked in cases.items():
        assert leaked not in redact_text(text), f"leaked from {text!r}"


def test_borgmatic_encryption_passphrase_is_redacted():
    """/etc/borgmatic.d/*.yaml is a harvested path and this is its literal key."""
    y = (
        "location:\n"
        "  source_directories:\n"
        "    - /home/user\n"
        "storage:\n"
        "  encryption_passphrase: hunter2secret\n"
    )
    out = redact_text(y)
    assert "hunter2secret" not in out
    assert "source_directories:" in out


def test_short_keywords_do_not_match_inside_unrelated_words():
    """The short spellings are whole-word only: `pin` lives inside `mapping`,
    `pass` inside `bypass`, `seed` inside `seeded`."""
    for text in ("mapping=identity\n", "bypass=true\n", "compass=north\n"):
        assert redact_text(text) == text


def test_known_non_secret_keys_are_exempt():
    """Keys that contain a secret substring but are not credentials."""
    for text in (
        "key-mgmt=wpa-psk\n",
        "key_mgmt=WPA-PSK\n",
        "KEYMAP=us\n",
        "apiVersion: v1\n",
    ):
        assert redact_text(text) == text


# --- Cost -----------------------------------------------------------------


def test_long_single_line_does_not_stall_the_redactor():
    """EMAIL_RE backtracked quadratically over an unbroken word run.

    Measured before the fix: 35 ms at 5,000 characters, 569 ms at 20,000,
    5,111 ms at 60,000 -- a clean 4x per doubling. Line breaks used to bound
    it; whole-file staging removes that bound, and a one-line base64 blob or
    a long JSON token is ordinary input. The threshold is deliberately loose:
    the point is linear-vs-quadratic, not a microbenchmark.
    """
    import time

    blob = "a" * 60000
    start = time.perf_counter()
    redact_text(blob)
    assert time.perf_counter() - start < 1.0
