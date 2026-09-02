# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for scripts/rebuild_sourceprep_unredacted.py's egress check (SEC-03/04/11).

Covers the lock-aware fix to boundary 2 (the MCP dispatch choke point):
that boundary reads the REAL host's current secret tier via
``_tool_get_config_value -> load_being_config()``, unlike boundary 1 which
always probes against the hardcoded ``local_only`` default. If the host is
unlocked (``cloud_ok_acknowledged``, TTL not expired), a value crossing via
the legitimate ``_egress_ack`` escape hatch must not be reported as a leak
(SystemExit(2)) — only a leak while the host is LOCKED is a real finding.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "halbert_core"))


def _load_rebuild_script():
    path = REPO_ROOT / "scripts" / "rebuild_sourceprep_unredacted.py"
    spec = importlib.util.spec_from_file_location("rebuild_sourceprep_unredacted", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rebuild_script():
    return _load_rebuild_script()


def _stage_secret_being_yml(monkeypatch, tmp_path, unlocked: bool):
    """Point being_config at a tmp_path file, locked or unlocked."""
    from halbert_core.config import being_config as bc

    path = str(tmp_path / "being.yml")
    cfg = bc.BeingConfig()
    if unlocked:
        cfg.security.secret_tier = "cloud_ok_acknowledged"
    bc.save_being_config(cfg, path)
    monkeypatch.setattr(bc, "_default_path", lambda: Path(path))


def _stage_one_secret(monkeypatch, rebuild_script, tmp_path, config_file):
    """_first_secret_key finds exactly one secret pair, and the MCP dispatch
    handler returns it either raw (host unlocked) or described (locked) —
    both boundaries operate on the SAME live queries.config machinery, so
    fake only the snapshot manifest and let get_config_value/_tool_get_config_value
    run for real against a real staged config file."""
    from halbert_core.config import queries as q_module

    config_file.write_text("[Service]\nPassword=hunter2\n")
    monkeypatch.setattr(
        q_module, "_load_latest_snapshot",
        lambda: [{"path": str(config_file), "hash": "x"}],
    )
    from halbert_core.config.parser import parse as parse_config
    monkeypatch.setattr(
        q_module, "_get_current_canon",
        lambda p: parse_config(str(config_file)) if str(config_file) in p else None,
    )
    from halbert_core.config.queries import _load_canon
    monkeypatch.setattr(
        rebuild_script, "_first_secret_key",
        lambda probe_key: (str(config_file), "Password", "hunter2"),
    )


def test_egress_check_fails_hard_when_host_locked(
        rebuild_script, monkeypatch, tmp_path):
    """A genuine leak while the host is locked is still a hard SystemExit(2)."""
    _stage_secret_being_yml(monkeypatch, tmp_path, unlocked=False)
    config_file = tmp_path / "test.conf"
    _stage_one_secret(monkeypatch, rebuild_script, tmp_path, config_file)

    # Force boundary 2 to look leaked regardless of the real redaction —
    # this isolates the lock-aware branch logic under test, not the
    # redactor itself (that's covered by test_redact.py/test_mcp_server.py).
    # _egress_check imports MCPServer fresh via `from
    # halbert_core.mcp.server import MCPServer`, so patch the method on
    # the real class rather than an attribute on the script module (it
    # doesn't import MCPServer at module scope).
    from halbert_core.mcp.server import MCPServer

    monkeypatch.setattr(
        MCPServer, "handle_request",
        lambda self, req: {"result": {"content": [{"type": "text", "text": '{"value": "hunter2"}'}]}},
    )

    with pytest.raises(SystemExit) as exc:
        rebuild_script._egress_check(None)
    assert exc.value.code == 2


def test_egress_check_downgrades_to_note_when_host_unlocked(
        rebuild_script, monkeypatch, tmp_path):
    """The same apparent leak, with the host unlocked, is a false positive:
    the value legitimately crossed via _egress_ack — report it, don't fail."""
    _stage_secret_being_yml(monkeypatch, tmp_path, unlocked=True)
    config_file = tmp_path / "test.conf"
    _stage_one_secret(monkeypatch, rebuild_script, tmp_path, config_file)

    from halbert_core.mcp.server import MCPServer

    # _egress_ack is stripped by mcp_response before reaching the client —
    # the raw value legitimately appears with no marker.
    monkeypatch.setattr(
        MCPServer, "handle_request",
        lambda self, req: {"result": {"content": [{"type": "text", "text": '{"value": "hunter2"}'}]}},
    )

    report = rebuild_script._egress_check(None)
    assert report["mcp_dispatch"]["host_unlocked"] is True
    assert "note" in report["mcp_dispatch"]
    assert "egress_ack" in report["mcp_dispatch"]["note"] or "escape hatch" in report["mcp_dispatch"]["note"]
