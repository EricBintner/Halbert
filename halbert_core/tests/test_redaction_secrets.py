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


def test_launchd_plist_identifier_keys_are_exempt():
    """Two false positives observed in real staged output on this host.

    `SHAuthorizationRight` names an *authorization right* -- its value is a
    well-known identifier like `system.preferences`, the same string Apple
    documents. `SecureSocketWithKey` names the *environment variable* launchd
    should publish a socket under, so its value is an env-var name such as
    `DISPLAY`. Both were `[redacted]`: `authorization` and `key` are tier-1
    substrings, and they fired on a right name and a variable name.
    """
    for text in (
        "<key>SHAuthorizationRight</key>\n<string>system.preferences</string>\n",
        "<key>SecureSocketWithKey</key>\n<string>DISPLAY</string>\n",
        "SHAuthorizationRight = system.preferences\n",
        "SecureSocketWithKey = DISPLAY\n",
    ):
        assert redact_text(text) == text, f"redacted {text!r}"


def test_a_secret_neighbour_in_the_same_plist_still_redacts():
    """The exemption is per-key, not a hole in the file."""
    p = (
        "<dict>\n"
        "  <key>SHAuthorizationRight</key>\n"
        "  <string>system.preferences</string>\n"
        "  <key>Sockets</key>\n"
        "  <dict>\n"
        "    <key>SecureSocketWithKey</key>\n"
        "    <string>DISPLAY</string>\n"
        "  </dict>\n"
        "  <key>APIToken</key>\n"
        "  <string>sk-live-shouldnotsurvive</string>\n"
        "</dict>\n"
    )
    out = redact_text(p)
    assert "sk-live-shouldnotsurvive" not in out
    assert "system.preferences" in out
    assert "<string>DISPLAY</string>" in out
    assert out.count("\n") == p.count("\n")


def test_the_exemption_is_whole_key_not_substring():
    """A longer name that merely contains an exempt one must still redact."""
    out = redact_text("<key>SecureSocketWithKeySecret</key>\n<string>hunter2</string>\n")
    assert "hunter2" not in out


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


# --- Structure that must survive being near a credential ------------------


def test_json_object_value_is_redacted_as_a_unit():
    """A secret-named object must not be half-eaten.

    Ending the value at the first delimiter left `"bob"` orphaned outside any
    key -- the secret was gone but the record was destroyed, which is the same
    failure mode as the fstab and quoted-mapping cases.
    """
    line = '  "auth": {"username": "bob", "password": "hunter2secret"},\n'
    out = redact_text(line)
    assert "hunter2secret" not in out
    assert '"bob"' not in out
    assert out == "  <secret>,\n"


def test_json_array_value_is_redacted_as_a_unit():
    out = redact_text('"api_key": ["AKIAIOSFODNN7SECRET"]\n')
    assert "AKIAIOSFODNN7SECRET" not in out


def test_multiline_json_members_are_classified_individually():
    """A container that opens at end of line is left for its members.

    Redacting to end of line there would leave an unbalanced brace and
    orphan every member, so the members are judged on their own names.
    """
    j = '{\n  "auth": {\n    "username": "bob",\n    "password": "hunter2secret"\n  }\n}\n'
    out = redact_text(j)
    assert "hunter2secret" not in out
    assert '"username": "bob"' in out
    assert out.count("\n") == j.count("\n")


def test_head_noun_rule_spares_qualified_non_secret_keys():
    """`auth-alg=open` is an algorithm, not a credential.

    NetworkManager and wpa_supplicant both write it, and postfix writes
    `smtpd_sasl_auth_enable`. Matching `auth` as any word of the key redacted
    all three; matching it as the key's last word does not.
    """
    for text in (
        "auth-alg=open\n",
        "auth_alg=OPEN\n",
        "smtpd_sasl_auth_enable = yes\n",
        "pin_length=4\n",
    ):
        assert redact_text(text) == text
    # ...while the head-noun spellings are still caught.
    assert "hunter2secret" not in redact_text("db_pass=hunter2secret\n")
    assert "hunter2secret" not in redact_text("wifi-pwd=hunter2secret\n")


def test_unterminated_plist_string_does_not_eat_the_next_entry():
    """A truncated plist must lose its credential, not the record around it.

    The unclosed `<string>` search used to run on to the next `</string>` in
    the file and blank every `<key>` in between.
    """
    p = (
        "<key>Password</key>\n"
        "<string>hunter2secret\n"
        "<key>Label</key>\n"
        "<string>keepme</string>\n"
    )
    out = redact_text(p)
    assert "hunter2secret" not in out
    assert "<key>Label</key>" in out
    assert "keepme" in out
    assert out.count("\n") == p.count("\n")


def test_plist_array_and_dict_under_a_secret_key_are_redacted():
    """A container named by a secret key has its whole subtree redacted.

    Its `<key>` elements survive, so which settings exist is still visible;
    only the values go. Siblings after the container are untouched.
    """
    p = (
        "<key>Passwords</key>\n"
        "<array>\n"
        "  <string>s3cretone</string>\n"
        "  <string>s3crettwo</string>\n"
        "</array>\n"
        "<key>Label</key>\n"
        "<string>keepme</string>\n"
    )
    out = redact_text(p)
    assert "s3cretone" not in out
    assert "s3crettwo" not in out
    assert "keepme" in out
    assert out.count("\n") == p.count("\n")


def test_plist_value_tag_attributes_are_preserved():
    out = redact_text(
        '<key>Password</key>\n<string xml:space="preserve">hunter2secret</string>\n'
    )
    assert "hunter2secret" not in out
    assert 'xml:space="preserve"' in out


# --- Addresses: non-routable is operational data, not a secret ------------
#
# Halbert administers the machine it runs on, so its own loopback and private
# addressing is core operational data. A *public* address can identify the
# host or a remote peer to an outside observer, and harvested config reaches
# an LLM that may be cloud-hosted, so those still go.


def test_loopback_addresses_survive():
    """Blanket IPv4 redaction gutted /etc/hosts: `127.0.0.1 localhost`."""
    assert redact_text("127.0.0.1 localhost\n") == "127.0.0.1 localhost\n"
    assert redact_text("127.0.1.1 myhost\n") == "127.0.1.1 myhost\n"
    # systemd-resolved's stub listener — a real, frequently-asked-about value.
    assert "127.0.0.53" in redact_text("nameserver 127.0.0.53\n")


def test_rfc1918_addresses_survive():
    for addr in ("10.0.0.1", "10.255.255.254", "172.16.0.1", "172.31.255.255",
                 "192.168.1.1", "192.168.0.254"):
        line = f"Address = {addr}/24\n"
        assert redact_text(line) == line, f"redacted private {addr}"


def test_link_local_and_unspecified_and_broadcast_survive():
    assert redact_text("169.254.1.1 self\n") == "169.254.1.1 self\n"
    # `#ListenAddress 0.0.0.0` is a stock sshd_config line.
    assert redact_text("#ListenAddress 0.0.0.0\n") == "#ListenAddress 0.0.0.0\n"
    assert redact_text("255.255.255.255 broadcasthost\n") == (
        "255.255.255.255 broadcasthost\n"
    )


def test_ipv6_loopback_and_link_local_survive():
    assert redact_text("::1 localhost\n") == "::1 localhost\n"
    assert redact_text("fe80::1%lo0 router\n") == "fe80::1%lo0 router\n"


def test_ipv6_unique_local_addresses_survive():
    """fc00::/7 (RFC 4193) is the IPv6 analogue of RFC1918.

    A ULA is not globally routable and cannot identify this host to an
    outside observer, so under the same rule that keeps 192.168.1.42 it is
    operational data rather than a secret. Real hosts number their internal
    IPv6 out of fd00::/8, so redacting it blanked the addressing half of
    every dual-stack network file.
    """
    for addr in ("fd00::1", "fc00::1", "fd12:3456:789a:1::1", "fdff::ffff"):
        line = f"peer {addr}\n"
        assert redact_text(line) == line, f"redacted unique-local {addr}"


def test_ula_exemption_does_not_reach_the_neighbouring_public_prefixes():
    """fc00::/7 covers fc00–fdff only; fb.. and fe.. below fe80 are not ULA.

    fec0::/10 in particular is site-local, which an existing test already
    requires to be redacted -- the exemption must not creep into it.
    """
    for addr in ("fbff::1", "fe00::1", "fec0::1"):
        assert addr not in redact_text(f"peer {addr}\n"), f"leaked {addr}"


# --- Netmasks: configuration, not an address ------------------------------
#
# A subnet mask identifies nothing. It is drawn from a 33-element set that is
# the same on every machine on earth, so it carries no bits that could point
# at this host or a peer -- the only thing address redaction protects.


def test_netmasks_survive_redaction():
    """`NETMASK=255.255.255.0` became `NETMASK=<ip>` on every ifcfg-* file."""
    for mask in (
        "255.255.255.0",
        "255.255.0.0",
        "255.0.0.0",
        "255.255.255.128",
        "255.255.255.252",
        "255.255.254.0",
        "128.0.0.0",
    ):
        line = f"NETMASK={mask}\n"
        assert redact_text(line) == line, f"redacted netmask {mask}"


def test_netmask_survives_whatever_the_key_is_called():
    """The mask is recognised by shape, so no keyword vocabulary to maintain.

    Four real spellings from four different files: RHEL/SUSE ifcfg,
    Debian /etc/network/interfaces, ISC dhcpd, and rsyncd's addr/mask form
    where the mask has no key in front of it at all.
    """
    for line in (
        "NETMASK=255.255.255.0\n",
        "    netmask 255.255.255.0\n",
        "option subnet-mask 255.255.255.0;\n",
        "hosts allow = 192.168.1.0/255.255.255.0\n",
    ):
        assert redact_text(line) == line, f"redacted the mask in {line!r}"


def test_a_dotted_quad_that_is_not_a_valid_mask_is_still_redacted():
    """Contiguous leading ones is the defining property; 255.0.255.0 has a
    hole, so it is an address that merely looks mask-ish."""
    for not_a_mask in ("255.0.255.0", "255.255.0.255", "0.0.0.255", "255.255.1.0"):
        out = redact_text(f"peer {not_a_mask}\n")
        assert not_a_mask not in out, f"exempted non-mask {not_a_mask}"
        assert "<ip>" in out


def test_ifcfg_eth0_keeps_its_netmask_and_loses_its_public_addresses():
    """The file shape this fix exists for, whole.

    A public IPADDR/GATEWAY must still go: exempting the mask must not be a
    back door into exempting the addresses beside it.
    """
    ifcfg = (
        "DEVICE=eth0\n"
        "BOOTPROTO=static\n"
        "IPADDR=203.0.113.42\n"
        "NETMASK=255.255.255.0\n"
        "GATEWAY=203.0.113.1\n"
        "ONBOOT=yes\n"
    )
    out = redact_text(ifcfg)
    assert "NETMASK=255.255.255.0" in out
    assert "203.0.113.42" not in out, "public IPADDR leaked"
    assert "203.0.113.1" not in out, "public GATEWAY leaked"
    assert "IPADDR=<ip>" in out
    assert "DEVICE=eth0" in out


def test_a_private_ifcfg_now_round_trips_unchanged():
    """The common case on a LAN host: nothing in the file is redactable."""
    ifcfg = (
        "DEVICE=eth0\n"
        "BOOTPROTO=static\n"
        "IPADDR=192.168.1.50\n"
        "NETMASK=255.255.255.0\n"
        "GATEWAY=192.168.1.1\n"
        "ONBOOT=yes\n"
    )
    assert redact_text(ifcfg) == ifcfg


def test_public_ipv4_is_still_redacted():
    for addr in ("8.8.8.8", "203.0.113.5", "1.1.1.1"):
        out = redact_text(f"nameserver {addr}\n")
        assert addr not in out, f"leaked public {addr}"
        assert "<ip>" in out


def test_addresses_just_outside_the_private_ranges_are_redacted():
    """172.16/12 ends at 172.31; 172.32.0.1 is public."""
    for addr in ("172.32.0.1", "172.15.0.1", "11.0.0.1", "193.168.1.1"):
        assert addr not in redact_text(f"peer {addr}\n"), f"leaked {addr}"


def test_documentation_ranges_are_redacted_despite_is_private():
    """`ipaddress.is_private` is True for TEST-NET and 2001:db8::/32.

    Verified on this interpreter: 203.0.113.5, 192.0.2.1, 198.51.100.5 and
    2001:db8::1 all report `is_private == True`, because Python's list is
    "not globally routable" rather than "RFC1918". Exempting on `is_private`
    alone would therefore have exempted addresses this fix must still redact.
    """
    for addr in ("203.0.113.5", "192.0.2.1", "198.51.100.5"):
        assert addr not in redact_text(f"peer {addr}\n"), f"leaked {addr}"
    assert "2001:db8" not in redact_text("peer 2001:db8::8a2e:370:7334\n")


def test_public_ipv6_is_still_redacted():
    out = redact_text("nameserver 2606:4700:4700::1111\n")
    assert "2606:4700" not in out
    assert "<ip6>" in out

    out = redact_text("peer 2001:0db8:85a3:0000:0000:8a2e:0370:7334\n")
    assert "8a2e" not in out
    assert "<ip6>" in out


def test_etc_hosts_round_trips_unchanged():
    """The file that motivated this fix. Every line is non-routable."""
    hosts = (
        "##\n"
        "# Host Database\n"
        "#\n"
        "# localhost is used to configure the loopback interface\n"
        "# when the system is booting.  Do not change this entry.\n"
        "##\n"
        "127.0.0.1\tlocalhost\n"
        "255.255.255.255\tbroadcasthost\n"
        "::1             localhost\n"
        "127.0.0.1       kubernetes.docker.internal\n"
        "192.168.1.42    nas.local nas\n"
        "fe80::1%en0     router.local\n"
    )
    assert redact_text(hosts) == hosts


# --- IPv6: a colon-separated numeric triple is not an address -------------


def test_sshd_maxstartups_is_not_an_ipv6_address():
    """`MaxStartups 10:30:100` is a real sshd tunable, not an address."""
    assert redact_text("MaxStartups 10:30:100\n") == "MaxStartups 10:30:100\n"


def test_timestamp_inside_an_rcs_id_survives():
    """/etc/ssh/sshd_config ships with an OpenBSD RCS ID carrying a clock."""
    line = "# $OpenBSD: sshd_config,v 1.104 2021/07/02 05:11:21 dtucker Exp $\n"
    assert redact_text(line) == line


def test_short_colon_separated_versions_survive():
    for line in ("version 1:2:3\n", "ratio 4:3\n", "elapsed 00:00:07\n"):
        assert redact_text(line) == line


def test_genuine_ipv6_forms_are_still_classified_as_ipv6():
    """Tightening must not cost recognition of real addresses.

    Exempt ones survive by exemption, not by failing to be recognised, so the
    positive control is the public forms: each must become `<ip6>`.
    """
    for addr in (
        "2001:db8::8a2e:370:7334",
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "2606:4700:4700::1111",
        "fec0::1",
    ):
        out = redact_text(f"peer {addr}\n")
        assert out == "peer <ip6>\n", f"{addr} not recognised as IPv6: {out!r}"


def test_apt_style_double_colon_keys_are_not_addresses():
    """apt writes `Acquire::http::Proxy`; dropping \\b must not catch it."""
    line = 'Acquire::http::Proxy "http://proxy.local:3142";\n'
    assert "Acquire::http::Proxy" in redact_text(line)


def test_mac_addresses_are_still_redacted_before_ipv6_sees_them():
    out = redact_text("permanent-mac-address=00:1A:2B:3C:4D:5E\n")
    assert "1A:2B" not in out
    assert "<mac>" in out


def test_redaction_is_idempotent():
    """Re-redacting already-redacted text must not degrade it further."""
    for text in (
        "psk=hunter2secret\n",
        "<key>Password</key>\n<string>hunter2secret</string>\n",
        '{"api_key":"AKIAIOSFODNN7SECRET"}\n',
        "//srv/s /mnt cifs username=bob,password=hunter2,uid=1000 0 0\n",
        "password: |\n  linesecret\n",
    ):
        once = redact_text(text)
        assert redact_text(once) == once, f"not idempotent: {text!r}"


# --- Separators inside a credential are not sibling directives -------------
#
# `_iter_pairs` offers a candidate pair for every `=`/`:` on the line,
# including the ones that sit *inside* a value. Counting those as directives
# flipped a single-directive line out of whole-line mode, and the value then
# ended at the first space -- so every credential containing a `:` or an `=`
# leaked from its second word onwards.


def test_secret_with_a_colon_in_it_is_redacted_whole():
    out = redact_text("psk=my:pass phrase\n")
    assert "phrase" not in out
    assert out == "<secret>\n"


def test_secret_with_an_equals_in_it_is_redacted_whole():
    out = redact_text("psk=a=b more words\n")
    assert "more words" not in out
    assert out == "<secret>\n"


def test_colon_separated_directive_with_a_colon_in_the_value():
    out = redact_text("password: my:pass phrase here\n")
    assert "phrase here" not in out
    assert out == "<secret>\n"


def test_spaced_separator_with_a_colon_in_the_value():
    out = redact_text("password = correct:horse battery\n")
    assert "battery" not in out
    assert out == "<secret>\n"


def test_base64_secret_ending_in_padding_is_redacted_whole():
    """WireGuard keys are base64 and routinely end in `=` or `==`."""
    out = redact_text("PrivateKey = aB3+xY/zQ== more\n")
    assert "more" not in out
    assert out == "<secret>\n"


def test_value_with_several_separators_is_redacted_whole():
    out = redact_text("psk=a:b=c:d more\n")
    assert "more" not in out
    assert "a:b=c:d" not in out
    assert out == "<secret>\n"


def test_quoted_value_containing_a_separator_ends_at_its_quote():
    """The quote is the boundary: what follows it is not part of the value."""
    out = redact_text('password = "correct:horse battery" trailing\n')
    assert "correct:horse" not in out
    assert out == "<secret> trailing\n"


def test_secret_without_a_separator_in_it_still_redacts_whole():
    """Control: the single-directive shape this must keep working."""
    assert redact_text("psk=my pass phrase\n") == "<secret>\n"


def test_a_comma_delimited_sibling_is_still_a_sibling():
    """Control for the fix: in fstab the next key follows a comma that is
    *outside* the previous value, so it is a genuine second directive and the
    option list must survive."""
    line = "//srv/share /mnt cifs username=alice,password=x,uid=1000,gid=1000 0 0\n"
    out = redact_text(line)
    assert out == "//srv/share /mnt cifs username=alice,<secret>,uid=1000,gid=1000 0 0\n"


def test_networkmanager_keyfile_psk_with_punctuation_does_not_leak():
    """End-to-end shape: this is what staging writes for a real WiFi profile."""
    nm = (
        "[wifi-security]\n"
        "key-mgmt=wpa-psk\n"
        "psk=hunter2 LEAKME\n"
        "psk=hunter2:LEAKME extra\n"
    )
    out = redact_text(nm)
    assert "LEAKME" not in out
    assert "hunter2" not in out
    assert "key-mgmt=wpa-psk" in out


def test_a_secret_key_inside_another_value_is_still_redacted():
    """Demoting a phantom pair must not demote the redaction with it: a
    systemd `Environment=` line carries its own `KEY=VALUE` inside quotes."""
    out = redact_text('Environment="DB_PASS=hunter2" "OTHER=y"\n')
    assert "hunter2" not in out
    assert "OTHER=y" in out


# --- Credentials with no `key<sep>value` shape at all ----------------------
#
# `_iter_pairs` needs an `=` or a `:` and TOKEN_RE requires one too, so three
# real shapes in harvested files had nothing looking at them: a space-
# separated directive, a command-line flag, and a credential inside a URL.


def test_ifupdown_space_separated_wpa_credentials_are_redacted():
    """W1: /etc/network/interfaces (network.yml). Debian ifupdown takes WPA
    credentials inline, space-separated, with no `=` anywhere on the line."""
    ifaces = (
        "auto wlan0\n"
        "iface wlan0 inet dhcp\n"
        "    wpa-ssid HomeNet\n"
        "    wpa-psk hunter2\n"
        "    wpa-passphrase correcthorse\n"
        "    wireless-key s3cr3t\n"
    )
    out = redact_text(ifaces)
    assert "hunter2" not in out
    assert "correcthorse" not in out
    assert "s3cr3t" not in out
    # The directive names and the non-secret siblings stay legible.
    assert "wpa-psk <secret>" in out
    assert "wpa-ssid HomeNet" in out
    assert "iface wlan0 inet dhcp" in out


def test_space_separated_keyword_must_be_the_whole_first_token():
    """Over-redaction guard. sshd_config is staged in the flat host tree and
    every one of these directives contains a credential keyword as a
    substring while being ordinary, non-secret configuration."""
    sshd = (
        "PasswordAuthentication no\n"
        "PubkeyAuthentication yes\n"
        "KbdInteractiveAuthentication no\n"
        "HostKey /etc/ssh/ssh_host_ed25519_key\n"
        "AuthorizedKeysFile\t.ssh/authorized_keys\n"
        "PermitRootLogin prohibit-password\n"
    )
    assert redact_text(sshd) == sshd


def test_a_comment_is_not_a_space_separated_directive():
    line = "# password rotation is handled by the vault agent\n"
    assert redact_text(line) == line


def test_initd_command_line_password_flag_is_redacted():
    """W2: /etc/init.d/* (service.yml). The `=` forms on the surrounding lines
    were already caught; only the space-separated flag leaked."""
    initd = (
        "#!/bin/sh\n"
        'DB_PASSWORD="hunter2"\n'
        "export API_TOKEN=abc123\n"
        "exec /usr/bin/myd --password SUPERSECRET --user alice\n"
    )
    out = redact_text(initd)
    assert "SUPERSECRET" not in out
    assert "hunter2" not in out
    assert "abc123" not in out
    # The flag name and the neighbouring non-credential flag survive.
    assert "--password <secret>" in out
    assert "--user alice" in out


def test_credential_flag_must_be_the_whole_flag_name():
    """Over-redaction guard: these flags take a port, a descriptor and a
    path, and all three contain or resemble a credential keyword."""
    line = "exec /usr/bin/myd -p 5432 --pass-fd 3 --key /etc/ssl/myd.pem\n"
    assert redact_text(line) == line


def test_equals_form_of_a_credential_flag_still_works():
    """Control: `--password=x` was already covered by the inline pass."""
    out = redact_text("exec /usr/bin/myd --password=SUPERSECRET --user alice\n")
    assert "SUPERSECRET" not in out
    assert "--user alice" in out


def test_plist_program_arguments_credential_is_redacted():
    """A launchd ProgramArguments array member has no `<key>` naming it, so
    the credential is a bare array element that nothing was looking at."""
    plist = (
        "<key>ProgramArguments</key>\n"
        "<array>\n"
        "\t<string>/usr/bin/myd</string>\n"
        "\t<string>--token</string>\n"
        "\t<string>hunter2secret</string>\n"
        "\t<string>--verbose</string>\n"
        "</array>\n"
    )
    out = redact_text(plist)
    assert "hunter2secret" not in out
    # The XML stays well formed and the rest of the argv is intact.
    assert out.count("<string>") == out.count("</string>") == 4
    assert "<string>/usr/bin/myd</string>" in out
    assert "<string>--token</string>" in out
    assert "<string>--verbose</string>" in out


def test_plist_program_arguments_without_credentials_survive():
    """Over-redaction guard: an ordinary argv must round-trip unchanged."""
    plist = (
        "<key>ProgramArguments</key>\n"
        "<array>\n"
        "\t<string>/usr/sbin/cupsd</string>\n"
        "\t<string>-l</string>\n"
        "\t<string>-c</string>\n"
        "\t<string>/etc/cups/cupsd.conf</string>\n"
        "</array>\n"
    )
    assert redact_text(plist) == plist


def test_a_flag_followed_by_another_flag_has_no_value_to_redact():
    plist = (
        "<array>\n"
        "\t<string>--token</string>\n"
        "\t<string>--verbose</string>\n"
        "</array>\n"
    )
    assert redact_text(plist) == plist


def test_plist_inline_shell_flag_uses_the_xml_safe_marker():
    """`<secret>` reads as an element inside XML; plists get the text marker."""
    out = redact_text("\t<string>/bin/sh -c 'myd --password hunter2'</string>\n")
    assert "hunter2" not in out
    assert "<secret>" not in out
    assert "[redacted]" in out
    assert out.count("<string>") == out.count("</string>") == 1


def test_plist_inline_pair_keeps_its_closing_tag():
    """`--token=abc123` inside a `<string>` is an inline pair, not an argv
    member, so `_redact_inline` owns it -- and it bounded the value on
    whitespace, which ran straight through `</string>` and took the closing
    tag with it. The document came out malformed.
    """
    out = redact_text("<string>--token=abc123secret</string>\n")
    assert "abc123secret" not in out
    assert out == "<string>[redacted]</string>\n"


def test_plist_inline_pair_uses_the_xml_safe_marker():
    """A bare `<secret>` inside a plist reads as an unknown element.

    `_placeholder_for` exists for exactly this and the inline pass was the
    one path that did not ask it.
    """
    out = redact_text("<string>api_key=AKIA123SECRET</string>\n")
    assert "AKIA123SECRET" not in out
    assert "<secret>" not in out
    assert out == "<string>[redacted]</string>\n"


def test_a_redacted_plist_document_still_parses():
    """Well-formedness is the point of the XML-safe marker; assert it with a
    parser rather than by counting tags."""
    import plistlib

    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "\t<key>Label</key>\n"
        "\t<string>com.example.myd</string>\n"
        "\t<key>ProgramArguments</key>\n"
        "\t<array>\n"
        "\t\t<string>/usr/bin/myd</string>\n"
        "\t\t<string>--token=abc123secret</string>\n"
        "\t\t<string>api_key=AKIA123SECRET</string>\n"
        "\t</array>\n"
        "</dict>\n"
        "</plist>\n"
    )
    out = redact_text(doc)
    assert "abc123secret" not in out
    assert "AKIA123SECRET" not in out

    parsed = plistlib.loads(out.encode("utf-8"))
    assert parsed["Label"] == "com.example.myd"
    assert parsed["ProgramArguments"] == [
        "/usr/bin/myd",
        "[redacted]",
        "[redacted]",
    ]


def test_a_non_credential_inline_pair_in_a_plist_string_survives():
    """Over-redaction guard: only a credential key loses its value."""
    plist = "\t<string>--config=/etc/cups/cupsd.conf</string>\n"
    assert redact_text(plist) == plist


def test_an_angle_bracket_bounds_a_value_only_inside_xml():
    """`<` ends a value on an XML line and nowhere else.

    Inside an XML text node a literal `<` must be written `&lt;`, so an
    unescaped one is markup and cannot be part of the value. Off such a line
    `<` is ordinary text, and bounding on it would leave everything after the
    bracket in plaintext -- which for a passphrase is most of it. The fstab
    shape below is the one that has to keep working: several directives on a
    line, so the value is bounded by the comma rather than by end of line.
    """
    out = redact_text("username=alice,password=hun<ter2secret,uid=1000\n")
    assert "hun<ter2secret" not in out
    assert "ter2secret" not in out
    assert "uid=1000" in out


def test_auto_master_url_credentials_are_redacted():
    """W3: /etc/auto_master (storage.yml) carries smbfs URLs with inline
    credentials and no key/value shape at all."""
    auto = "/net\t\t\t-hosts\n/-\t\t\tauto_smb\n:smbfs://alice:hunter2@fileserver/share\n"
    out = redact_text(auto)
    assert "hunter2" not in out
    # Scheme, user and host stay: the mount stays legible.
    assert "smbfs://alice:<secret>@fileserver/share" in out


def test_proxy_url_credentials_are_redacted_without_eating_the_host():
    """/etc/environment. EMAIL_RE used to swallow `pass@proxy.example.com`
    whole, which hid the leak but destroyed the proxy host with it."""
    out = redact_text("http_proxy=http://bob:proxypass@proxy.example.com:3128/\n")
    assert "proxypass" not in out
    assert "http://bob:<secret>@proxy.example.com:3128/" in out


def test_a_url_without_credentials_is_untouched():
    for line in (
        "http_proxy=http://proxy.example.com:3128/\n",
        "url=https://api.example.com/v1/things\n",
        "server=ldap://ldap.example.com:389\n",
    ):
        assert redact_text(line) == line


def test_pam_management_group_is_not_a_credential_directive():
    """Over-redaction guard, found by running the whole of /etc through this
    module: every rule in /etc/pam.d/* opens with its management group, and
    one of the four groups is literally `password`. The value position holds
    a PAM control word or a bracketed control field, never a secret."""
    pam = (
        "auth       optional       pam_krb5.so use_kcminit\n"
        "account    required       pam_opendirectory.so\n"
        "password   required       pam_opendirectory.so\n"
        "password   sufficient     pam_unix.so\n"
        "password   [success=1 default=ignore] pam_unix.so obscure\n"
        "session    required       pam_launchd.so\n"
    )
    assert redact_text(pam) == pam


# --- /etc/nsswitch.conf: `passwd` names a database, not a credential -------


def test_nsswitch_database_lines_survive():
    """N4: /etc/nsswitch.conf is in network.yml. `passwd` is a tier-1
    substring and the line is single-directive, so it became `<secret>` while
    `group:` and `hosts:` survived -- a half-destroyed file that misreports
    NSS configuration. `publickey:` was destroyed the same way, by `key`."""
    nsswitch = (
        "# /etc/nsswitch.conf\n"
        "passwd:         files systemd\n"
        "group:          files systemd\n"
        "shadow:         files\n"
        "hosts:          files mdns4_minimal [NOTFOUND=return] dns myhostname\n"
        "publickey:      nisplus\n"
        "netgroup:       nis\n"
        "services:       db files\n"
        "protocols:      db files\n"
    )
    assert redact_text(nsswitch) == nsswitch


def test_a_genuine_passwd_assignment_is_still_redacted():
    """The exemption must not reach an assignment. /etc/default/* is staged
    in the flat host tree and `PASSWD=hunter2` there is a real credential."""
    assert redact_text("passwd=secret\n") == "<secret>\n"
    for line in (
        "passwd=hunter2secret\n",
        "PASSWD=hunter2secret\n",
        "Passwd = hunter2secret\n",
        "passwd: hunter2secret\n",
        "db_passwd=hunter2secret\n",
        "passwd_file=hunter2secret\n",
    ):
        assert "hunter2secret" not in redact_text(line), line


def test_the_nsswitch_exemption_needs_every_token_to_be_a_source():
    """A single non-source token means this is not an NSS database line."""
    assert "hunter2secret" not in redact_text("passwd: files hunter2secret\n")
    assert "hunter2secret" not in redact_text("publickey: hunter2secret\n")


# --- Log messages are prose, not config -----------------------------------


def test_log_prose_is_not_read_as_a_space_separated_directive():
    """`redact_event` feeds this module log messages, which are prose rather
    than config -- the distinction the module already draws when it explains
    why TOKEN_RE is kept. The whole-line directive rule is a config rule, and
    applied to prose it ate the auth messages a sysadmin assistant most needs
    to read. Its only callers are ingestion/runner.py and ingestion/
    service.py, both telemetry; config staging calls redact_text directly.
    """
    from halbert_core.ingestion.redaction import redact_event

    for msg in (
        "password changed for user alice",
        "password expired; forcing reset",
        "passphrase prompt cancelled by user",
        "psk mismatch on wlan0",
        "secret sauce recipe loaded",
    ):
        assert redact_event({"message": msg})["message"] == msg, msg


def test_prose_still_loses_every_other_credential_shape():
    """Standing one config rule down must not open the log path up."""
    from halbert_core.ingestion.redaction import redact_event

    for msg in (
        "psk=hunter2secret applied",
        "ran myd --password hunter2secret --user alice",
        "fetching smb://alice:hunter2secret@fileserver/share",
        "api_key: hunter2secret",
    ):
        assert "hunter2secret" not in redact_event({"message": msg})["message"], msg


def test_config_text_still_gets_the_directive_rule():
    """The staging path is unaffected: it calls redact_text."""
    assert redact_text("    wpa-psk hunter2\n") == "    wpa-psk <secret>\n"
    assert redact_text("password changed\n") == "password <secret>\n"
