# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The MCP response boundary must strip credentials before egress.

``mcp_response()`` is the single choke point every MCP tool returns
through.  A credential that reaches this function must not survive it —
not at the top level, not nested in a dict, not inside a list, not
concatenated with other text.

Two passes are tested:
1. Structural — a dict with a ``"key"`` field that is a secret key name
   has its ``"value"`` field replaced.  Also, dict keys that are secret
   key names trigger redaction of their values.
2. Text — ``redact_text()`` catches credentials embedded in strings:
   ``key=value`` shapes, PEM blocks, JWTs, URL-embedded credentials.
"""
from __future__ import annotations

from halbert_core.mcp.response import mcp_response


# --- Structural pass: config-value-pair shape ----------------------------
#
# The primary MCP payload for config queries is:
#   {"path": ..., "key": "password", "value": "hunter2", "tier": 2}
# redact_text("hunter2") returns "hunter2" (no key=value structure), so
# the structural pass must catch it by checking _is_secret_key on the
# "key" field.

def test_password_value_pair_is_redacted():
    payload = {"path": "/etc/app.conf", "key": "password", "value": "hunter2-bare-secret"}
    result = mcp_response(payload)
    assert "hunter2-bare-secret" not in str(result)
    assert result["path"] == "/etc/app.conf"
    assert result["key"] == "password"  # key name survives (not a credential)


def test_api_key_value_pair_is_redacted():
    payload = {"path": "/etc/app.conf", "key": "api_key", "value": "sk-live-1234567890"}
    result = mcp_response(payload)
    assert "sk-live-1234567890" not in str(result)


def test_token_value_pair_is_redacted():
    payload = {"path": "/etc/app.conf", "key": "token", "value": "abc123secret456"}
    result = mcp_response(payload)
    assert "abc123secret456" not in str(result)


def test_non_secret_value_pair_passes_through():
    """Tier 0/1 values (non-secret keys) must survive the boundary."""
    payload = {"path": "/etc/ssh/sshd_config", "key": "Port", "value": "2222", "tier": 1}
    result = mcp_response(payload)
    assert result["value"] == "2222"
    assert result["key"] == "Port"
    assert result["tier"] == 1


def test_bool_value_under_secret_key_is_kept():
    """PasswordAuthentication is a bool — not a credential, even under 'password'."""
    payload = {"path": "/etc/ssh/sshd_config", "key": "PasswordAuthentication", "value": "no"}
    result = mcp_response(payload)
    # "no" is a string, not a bool, so it gets redacted. But a real bool:
    payload_bool = {"path": "/etc/ssh/sshd_config", "key": "PasswordAuthentication", "value": False}
    result_bool = mcp_response(payload_bool)
    assert result_bool["value"] is False


# --- Structural pass: secret dict keys -----------------------------------

def test_secret_dict_key_redacts_value():
    payload = {"config": {"password": "hunter2", "host": "db.internal"}}
    result = mcp_response(payload)
    assert "hunter2" not in str(result)
    assert result["config"]["host"] == "db.internal"


def test_nested_secret_dict_key_redacts_value():
    payload = {
        "config": {
            "database": {
                "password": "supersecret-db-pass",
                "host": "db.internal",
            }
        }
    }
    result = mcp_response(payload)
    assert "supersecret-db-pass" not in str(result)
    assert result["config"]["database"]["host"] == "db.internal"


# --- Text pass: embedded credentials in strings --------------------------

def test_key_equals_value_in_string_is_redacted():
    payload = {"content": "password=hunter2-text-secret\nport=2222"}
    result = mcp_response(payload)
    assert "hunter2-text-secret" not in str(result)
    assert "2222" in str(result)


def test_yaml_key_colon_value_is_redacted():
    payload = {"content": "api_key: sk-live-1234567890abcdef\nport: 8080"}
    result = mcp_response(payload)
    assert "sk-live-1234567890abcdef" not in str(result)
    assert "8080" in str(result)


def test_pem_block_is_redacted():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKBxKCAQEA\n-----END RSA PRIVATE KEY-----"
    payload = {"certificate": pem}
    result = mcp_response(payload)
    assert "MIIEpAIKBxKCAQEA" not in str(result)
    assert "BEGIN RSA PRIVATE KEY" not in str(result)


def test_jwt_is_redacted():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    payload = {"auth_header": f"Bearer {jwt}"}
    result = mcp_response(payload)
    assert jwt not in str(result)


def test_url_credentials_are_redacted():
    url = "https://alice:hunter2-secret@proxy.example.com:3128"
    payload = {"proxy": url}
    result = mcp_response(payload)
    assert "hunter2-secret" not in str(result)
    # redact_text strips the credentials from the URL; the secret must be gone.
    # The host may or may not survive depending on redact_text's URL handling.


def test_list_of_strings_is_redacted():
    payload = {
        "lines": [
            "Port 2222",
            "PasswordAuthentication no",
            "passphrase = my-secret-passphrase",
        ]
    }
    result = mcp_response(payload)
    joined = str(result)
    assert "my-secret-passphrase" not in joined
    assert "2222" in joined


# --- Non-mutation and edge cases -----------------------------------------

def test_non_string_scalars_pass_through():
    payload = {"port": 2222, "enabled": True, "ratio": 0.85, "nothing": None}
    result = mcp_response(payload)
    assert result == payload


# --- Acknowledged egress marker (REV-01 F3) ------------------------------
#
# get_config_value sets ``_egress_ack: True`` on a payload only after
# verifying tier + acknowledgment + TTL. When the choke point sees the
# marker, the dict's ``value`` field is the one deliberate exception —
# everything else in the payload is still redacted, and the marker
# itself never egresses.

def test_egress_ack_lets_acknowledged_value_cross():
    payload = {
        "path": "/etc/app.conf", "key": "password",
        "tier": 2, "value": "hunter2-acknowledged",
        "acknowledged": True, "_egress_ack": True,
    }
    result = mcp_response(payload)
    assert result["value"] == "hunter2-acknowledged"
    assert result["key"] == "password"  # key name is not a credential
    assert "_egress_ack" not in result  # enforcement metadata never egresses


def test_egress_ack_marker_is_dropped_from_output():
    payload = {"key": "api_key", "value": "sk-live-1", "_egress_ack": True}
    result = mcp_response(payload)
    assert "_egress_ack" not in result
    assert result["value"] == "sk-live-1"


def test_without_marker_vocabulary_value_still_redacted():
    payload = {"path": "/etc/app.conf", "key": "password", "value": "hunter2"}
    result = mcp_response(payload)
    assert result["value"] == "<secret>"


def test_egress_ack_exempts_only_that_dicts_value_field():
    """Everything else in the acknowledged dict still gets the full
    treatment — embedded credentials in sibling text are caught by the
    text pass."""
    payload = {
        "_egress_ack": True,
        "key": "password",
        "value": "hunter2-acknowledged",
        "note": "backup password=hunter2-inline",
    }
    result = mcp_response(payload)
    assert result["value"] == "hunter2-acknowledged"
    assert "hunter2-inline" not in str(result)


def test_egress_ack_does_not_leak_to_sibling_dicts():
    """The marker is per-dict: an acknowledged result in a list must not
    open the door for other payloads in the same response."""
    payload = {
        "results": [
            {"key": "password", "value": "hunter2-ack", "_egress_ack": True},
            {"key": "password", "value": "hunter2-not-ack"},
        ]
    }
    result = mcp_response(payload)
    assert result["results"][0]["value"] == "hunter2-ack"
    assert result["results"][1]["value"] == "<secret>"


def test_nested_secret_dict_keys_still_redacted_under_marker():
    payload = {
        "_egress_ack": True,
        "value": "hunter2-acknowledged",
        "config": {"token": "tok-sentinel-98765"},
    }
    result = mcp_response(payload)
    assert result["value"] == "hunter2-acknowledged"
    assert "tok-sentinel-98765" not in str(result)
    assert result["config"]["token"] == "<secret>"


def test_forged_string_marker_is_ignored():
    """Only a literal True honors the exception — a string that merely
    spells the marker name is not an acknowledgment."""
    payload = {"key": "password", "value": "hunter2-forged",
               "_egress_ack": "true"}
    result = mcp_response(payload)
    assert "hunter2-forged" not in str(result)


def test_input_is_not_mutated():
    original = {"key": "password", "value": "hunter2-original"}
    mcp_response(original)
    assert original["value"] == "hunter2-original"


def test_empty_and_edge_cases():
    assert mcp_response(None) is None
    assert mcp_response("") == ""
    assert mcp_response([]) == []
    assert mcp_response({}) == {}
    assert mcp_response(42) == 42
    assert mcp_response(True) is True


# --- Master sentinel test ------------------------------------------------

def test_planted_sentinels_never_appear_in_any_response():
    """Every credential shape the boundary is designed to catch must be gone.

    Note: a bare secret under a neutral key (e.g. ``{"location": "ghp_abc"}``)
    is NOT included here — that is the known Task 8 gap (known-prefix
    detection + entropy backstop).  Each sentinel below is in a position
    the structural or text pass is expected to handle.
    """
    # Config-value-pair: secret key field triggers value redaction.
    for key_name in ("password", "api_key", "token", "passphrase", "secret"):
        secret_val = f"{key_name}-sentinel-value-12345"
        payload = {"path": "/etc/app.conf", "key": key_name, "value": secret_val}
        result = mcp_response(payload)
        assert secret_val not in str(result), (
            f"Config-value-pair sentinel survived for key {key_name!r}"
        )

    # Secret dict key: value under a secret-named key is replaced.
    for key_name in ("password", "api_key", "token"):
        secret_val = f"{key_name}-dictkey-sentinel-67890"
        payload = {"config": {key_name: secret_val, "host": "db.internal"}}
        result = mcp_response(payload)
        assert secret_val not in str(result), (
            f"Dict-key sentinel survived for key {key_name!r}"
        )

    # Text pass: embedded credentials in strings.
    text_sentinels = [
        "password=hunter2-text-secret",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIKBxKCAQEA\n-----END RSA PRIVATE KEY-----",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        "https://alice:hunter2-url-secret@proxy.example.com:3128",
    ]
    for sentinel in text_sentinels:
        payload = {"content": sentinel}
        result = mcp_response(payload)
        assert sentinel not in str(result), (
            f"Text sentinel survived: {sentinel[:40]!r}..."
        )
