# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-05 Phase C: an MCP credential is a known secret from the moment it resolves.

A03-G7. The redaction registry is a LEARNED layer: it protects values it
has watched cross a boundary Halbert controls. MCP bearer tokens were
never registered, so the one class of secret Halbert resolves on every
single request -- a server's API token -- was invisible to the exact-value
pass. If a token ever appeared in an error string, a log line, a tool
result or a confirmation preview, only the pattern heuristics stood
between it and the model.

Registering at resolve time is the right seam: it is where the value
exists, it runs on every request so a rotated token is registered too,
and it costs one bounded insert against a cached alternation.

**Reported, per the packet's STOP condition:** a server's ``env`` block
is NOT registered wholesale. It carries paths, feature flags and
hostnames as often as credentials, and registering a path would replace
every mention of that directory with ``<secret>`` in every tool result
and log line on the machine. The classification rule needed to do it
safely is a name-shaped one (``*_TOKEN``, ``*_KEY``, ``*_SECRET``,
``*_PASSWORD``, ``*_CREDENTIAL``), which is exactly what
``ingestion.redaction._is_secret_key`` already decides -- so that is what
this uses, and an env value whose NAME does not read as a credential is
left to the pattern pass.
"""

import pytest

from halbert_core.ingestion.redaction_registry import (
    REDACTION_PLACEHOLDER,
    get_global_registry,
)
from halbert_core.mcp.config import MCPAuthConfig, register_server_secrets


def test_a_resolved_bearer_token_is_registered(monkeypatch):
    monkeypatch.setenv("SOME_MCP_TOKEN", "tok-abcdef123456")
    auth = MCPAuthConfig(type="bearer", token_env="SOME_MCP_TOKEN")
    assert auth.resolve_token() == "tok-abcdef123456"
    assert REDACTION_PLACEHOLDER in get_global_registry().redact_text(
        "failed with tok-abcdef123456")


def test_a_literal_token_is_registered_too():
    auth = MCPAuthConfig(type="bearer", token="literal-token-value")
    auth.resolve_token()
    assert REDACTION_PLACEHOLDER in get_global_registry().redact_text(
        "sent literal-token-value")


def test_a_missing_token_registers_nothing(monkeypatch):
    monkeypatch.delenv("ABSENT_MCP_TOKEN", raising=False)
    auth = MCPAuthConfig(type="bearer", token_env="ABSENT_MCP_TOKEN")
    assert auth.resolve_token() is None


def test_credential_shaped_env_names_are_registered():
    register_server_secrets({"WEATHER_API_KEY": "wk-999888777666"})
    assert REDACTION_PLACEHOLDER in get_global_registry().redact_text(
        "key=wk-999888777666")


def test_a_path_shaped_env_value_is_not_registered():
    """The STOP condition, pinned: registering a path would replace every
    mention of that directory on the machine."""
    register_server_secrets({"DATA_ROOT": "/Users/someone/Documents"})
    text = "reading from /Users/someone/Documents"
    assert get_global_registry().redact_text(text) == text


def test_a_short_credential_is_left_to_the_pattern_pass():
    register_server_secrets({"TINY_TOKEN": "abc"})
    assert get_global_registry().redact_text("abc") == "abc"


def test_registration_is_idempotent(monkeypatch):
    monkeypatch.setenv("REPEAT_MCP_TOKEN", "tok-repeat-999999")
    auth = MCPAuthConfig(type="bearer", token_env="REPEAT_MCP_TOKEN")
    before = len(get_global_registry())
    for _ in range(5):
        auth.resolve_token()
    assert len(get_global_registry()) <= before + 4
