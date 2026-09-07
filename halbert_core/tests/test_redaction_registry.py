# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the secret variant registry (Packet 05 Phase A).

Lifted from OpenClaw src/logging/secret-redaction-registry.ts: when a secret
value becomes known, register its exact value PLUS url-encoded and
json-escaped forms — those are the leak forms that evade plain-value
redaction.
"""
import json
import os
import sys
import urllib.parse

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.ingestion import redaction_registry as _rr
from halbert_core.ingestion.redaction_registry import (
    REDACTION_PLACEHOLDER,
    SecretVariantRegistry,
)


@pytest.fixture(autouse=True)
def _fresh_global_registry():
    """Isolate the process-global registry around every test here.

    Tests in this file deliberately populate the global registry (an acked
    value registered at the egress path must not leak into other test
    modules' expectations about redaction output).
    """
    saved = _rr._GLOBAL
    _rr._GLOBAL = None
    try:
        yield
    finally:
        _rr._GLOBAL = saved


def _reg():
    return SecretVariantRegistry(max_entries=64)


def test_plain_form_is_registered():
    reg = _reg()
    reg.register("hunter2")
    assert "hunter2" in reg
    assert reg.redact_text("password is hunter2 ok") == (
        f"password is {REDACTION_PLACEHOLDER} ok"
    )


def test_urlencoded_form_is_caught():
    reg = _reg()
    reg.register("p@ss w/rd")
    encoded = urllib.parse.quote("p@ss w/rd")
    assert reg.redact_text(f"see {encoded} in url") == (
        f"see {REDACTION_PLACEHOLDER} in url"
    )


def test_json_escaped_form_is_caught():
    reg = _reg()
    secret = 'say "hi"\\now'
    # the inner escaped form as it appears when embedded in JSON text
    escaped = json.dumps(secret)[1:-1]
    reg.register(secret)
    assert reg.redact_text(f"payload {escaped} end") == (
        f"payload {REDACTION_PLACEHOLDER} end"
    )


def test_bounded_and_fifo():
    reg = SecretVariantRegistry(max_entries=4)
    for i in range(6):
        reg.register(f"secret-{i}")
    assert "secret-0" not in reg  # oldest evicted
    assert "secret-5" in reg


def test_empty_and_short_values_ignored():
    reg = _reg()
    reg.register("")
    # too short to redact safely — would blank out ordinary text
    reg.register("ab")
    assert len(reg) == 0


# ---------------------------------------------------------------------------
# A2 integration: registration at the acknowledged-egress path
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_config_env(tmp_path, monkeypatch):
    """Real config env (same shape as test_config_queries.py's fixture):
    a small ini file snapshotted unredacted into a temp canon DB."""
    from halbert_core.config.snapshot import snapshot

    config_file = tmp_path / "test.conf"
    config_file.write_text(
        "[Service]\n"
        "ExecStart=/usr/bin/myapp\n"
        "Port=2222\n"
        "Password=hunter2\n"
        "Enabled=true\n"
    )
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(
        f"include:\n  - '{config_file}'\n" "exclude: []\n" "parsers: {}\n"
    )
    canon_dir = tmp_path / "canon"
    snap_dir = tmp_path / "snapshots"
    canon_dir.mkdir()
    snap_dir.mkdir()
    monkeypatch.setattr("halbert_core.config.snapshot.CANON_DIR", str(canon_dir))
    monkeypatch.setattr("halbert_core.config.snapshot.SNAP_DIR", str(snap_dir))
    monkeypatch.setattr("halbert_core.config.queries.CANON_DIR", str(canon_dir))
    monkeypatch.setattr("halbert_core.config.queries.SNAP_DIR", str(snap_dir))
    monkeypatch.setattr("halbert_core.config.drift.CANON_DIR", str(canon_dir))
    snapshot(str(manifest), redact=False)
    return str(config_file)


def test_egress_acked_value_is_registered(temp_config_env):
    """A config value that crosses via the ack path is registered, and is
    subsequently redacted from arbitrary text even when URL-encoded.

    A2's rule: the moment a secret is deliberately egressed, every encoded
    form of it becomes known-dangerous everywhere else.
    """
    import urllib.parse

    from halbert_core.config.queries import get_config_value

    reg = _rr.get_global_registry()
    assert len(reg) == 0

    result = get_config_value(
        temp_config_env, "Password", secret_tier="cloud_ok_acknowledged"
    )
    assert result["_egress_ack"] is True  # the ack path, not the locked path
    assert "hunter2" in reg

    # raw form
    assert reg.redact_text("the value is hunter2 here") == (
        f"the value is {REDACTION_PLACEHOLDER} here"
    )
    # url-encoded form
    encoded = urllib.parse.quote("hunter2")
    assert reg.redact_text(f"see {encoded} in url") == (
        f"see {REDACTION_PLACEHOLDER} in url"
    )


def test_non_ack_paths_do_not_register(temp_config_env):
    """Tier 0/1 raw values and locked Tier 2 descriptions never feed the
    registry — only the acknowledged-egress path does (the packet rule:
    registration happens where EGRESS_ACK_FIELD is set)."""
    from halbert_core.config.queries import get_config_value

    reg = _rr.get_global_registry()

    locked = get_config_value(temp_config_env, "Password", secret_tier="local_only")
    assert locked["redacted"] is True
    tier0 = get_config_value(temp_config_env, "Enabled")
    tier1 = get_config_value(temp_config_env, "Port", operational_tier="cloud_ok")
    assert tier0["tier"] == 0 and tier1["tier"] == 1
    assert len(reg) == 0


# ---------------------------------------------------------------------------
# A3 integration: the MCP response boundary consults the registry
# (added in the A3 commit; kept out of the A2 commit)
# ---------------------------------------------------------------------------