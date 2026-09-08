# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP tool risk classification (Workstream B3).

MCP tools are remote: the filesystem server can delete files, a browser
server can navigate anywhere, and the shell-command pattern classifier in
tools/safety.py cannot read what a remote server's tool does. So
classification is config-driven — ``mcp_config.yml`` per-server
``risk_override`` and per-tool ``tool_risk``, with an explicit MEDIUM
default (execute with warning) — and it is evaluated PER CALL against
the freshly re-read config, in the same executor chain (CRITICAL block,
HIGH confirmation, RoleGate) every native tool goes through.

These tests pin:

* the MEDIUM default — for a server PRESENT in the config with no
  override (a registered tool whose server is ABSENT from the config
  fails CLOSED instead, spec review Issue 1: removed, renamed, dropped
  by a typo'd override, or a deleted/corrupt config must never
  silently downgrade a live tool to auto-execute);
* per-server overrides in both directions (raise to HIGH/CRITICAL,
  lower to SAFE);
* per-tool overrides beating per-server ones, with case-insensitive
  key matching (``Delete_File`` fences the registered ``delete_file``)
  and a bridge warning for keys that match nothing (Issue 2);
* sanitized server-name collisions rejected by the loader, so
  classification is deterministic regardless of config order (Issue 3);
* per-call config freshness — flip the file mid-process, no restart, no
  re-registration, the NEXT call gates differently;
* the executor chain end-to-end: HIGH requires confirmation, CRITICAL
  blocks outright even with confirmed=True, RoleGate caps apply;
* the guest structural hold from B2 (re-pinned here against a
  ``risk_override: safe`` server: classification must never be the thing
  that saves a guest, because the allowlist is);
* fail-tight config validation (a bad level name skips the server, it
  never silently falls back to MEDIUM);
* the B5-facing risk summary.
"""
from __future__ import annotations

import logging

import pytest
import yaml

from halbert_core.mcp.bridge import discover_and_register
from halbert_core.mcp.config import load_config
from halbert_core.tools.executor import ToolExecutor
from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework


# ---------------------------------------------------------------------------
# Fixtures and doubles
# ---------------------------------------------------------------------------

@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """An isolated config directory; mcp_config.yml lives in it."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    return tmp_path


def write_config(config_dir, servers=None, raw=None):
    """Write mcp_config.yml. ``servers`` is a list of dicts (safe to
    write); ``raw`` writes literal YAML text instead."""
    path = config_dir / "mcp_config.yml"
    if raw is not None:
        path.write_text(raw)
    else:
        entries = []
        for s in servers or []:
            entry = {"name": s["name"], "transport": "stdio", "command": "npx"}
            for key in ("risk_override", "tool_risk"):
                if key in s:
                    entry[key] = s[key]
            entries.append(entry)
        path.write_text(yaml.safe_dump({"servers": entries}))
    return path


def stdio_server(name, **extra):
    """One stdio server config dict, the minimum valid shape."""
    return {"name": name, **extra}


class RecordingClient:
    """Stands in for MCPClient at the bridge boundary: two tools from one
    server, and a call log so tests can prove execution actually landed."""

    TOOLS = [
        {"name": "read_file", "description": "Read a file",
         "inputSchema": {"type": "object",
                         "properties": {"path": {"type": "string"}}}},
        {"name": "delete_file", "description": "Delete a file",
         "inputSchema": {"type": "object",
                         "properties": {"path": {"type": "string"}}}},
    ]

    def __init__(self, server="fs", tools=None):
        self.server = server
        self.tools = tools if tools is not None else self.TOOLS
        self.calls = []

    async def connect(self, server_name=None):
        pass

    async def list_tools(self, server_name):
        return self.tools

    def connected_servers(self):
        return [self.server]

    async def call_tool(self, server_name, tool_name, args):
        self.calls.append((server_name, tool_name, args))
        return {"content": [{"type": "text", "text": "ok"}]}


async def bridged_executor(client=None):
    """A real ToolExecutor with really-bridged MCP tools on it (the B2
    path: bridge → registry → qualified names → executor.register)."""
    executor = ToolExecutor(web_search=False)
    client = client or RecordingClient()
    registered = await discover_and_register(executor, client)
    assert registered >= 1
    return executor, client


# ---------------------------------------------------------------------------
# The MEDIUM default
# ---------------------------------------------------------------------------

class TestMediumDefault:

    async def test_server_with_no_override_is_medium(self, config_dir):
        write_config(config_dir, [stdio_server("fs")])
        safety = ToolSafetyFramework()
        result = safety.classify(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.allowed
        assert not result.requires_confirmation

    async def test_medium_executes_through_the_executor(self, config_dir):
        """The acceptance shape: MEDIUM executes (with the framework's
        warning semantics — the risk level rides the result and the
        audit), no confirmation interposed."""
        write_config(config_dir, [stdio_server("fs")])
        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.success
        assert result.risk_level == RiskLevel.MEDIUM
        assert not result.requires_confirmation
        assert client.calls == [("fs", "delete_file", {"path": "/tmp/x"})]


# ---------------------------------------------------------------------------
# Per-server overrides
# ---------------------------------------------------------------------------

class TestPerServerOverride:

    async def test_raise_to_high_requires_confirmation(self, config_dir):
        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert not result.success
        assert result.requires_confirmation
        assert result.risk_level == RiskLevel.HIGH
        assert result.confirmation_message
        assert client.calls == []  # nothing ran without confirmation

        confirmed = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"}, confirmed=True)
        assert confirmed.success
        assert client.calls

    async def test_lower_to_safe_executes_without_confirmation(
            self, config_dir):
        """Even a tool literally named delete_file: the operator said
        this whole server is safe, and that is the primary mechanism."""
        write_config(config_dir, [stdio_server("fs", risk_override="safe")])
        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.success
        assert result.risk_level == RiskLevel.SAFE
        assert not result.requires_confirmation

    async def test_critical_override_blocks_outright(self, config_dir):
        write_config(config_dir, [stdio_server("fs", risk_override="critical")])
        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"})
        assert not result.success
        assert not result.requires_confirmation
        assert result.risk_level == RiskLevel.CRITICAL
        assert client.calls == []

    async def test_critical_blocks_even_when_confirmed(self, config_dir):
        """allowed=False is the refusal contract: no confirmed=True path
        may override a CRITICAL classification."""
        write_config(config_dir, [stdio_server("fs", risk_override="critical")])
        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"}, confirmed=True)
        assert not result.success
        assert client.calls == []

    async def test_level_names_are_case_insensitive(self, config_dir):
        write_config(config_dir, [stdio_server("fs", risk_override="HIGH")])
        safety = ToolSafetyFramework()
        result = safety.classify("mcp__fs__read_file", {})
        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_confirmation


# ---------------------------------------------------------------------------
# Per-tool overrides
# ---------------------------------------------------------------------------

class TestPerToolOverride:

    async def test_per_tool_beats_per_server(self, config_dir):
        write_config(config_dir, [stdio_server(
            "fs", risk_override="high",
            tool_risk={"read_file": "safe", "delete_file": "critical"})])
        safety = ToolSafetyFramework()

        read = safety.classify("mcp__fs__read_file", {})
        assert read.risk_level == RiskLevel.SAFE
        assert not read.requires_confirmation

        delete = safety.classify("mcp__fs__delete_file", {})
        assert delete.risk_level == RiskLevel.CRITICAL
        assert not delete.allowed

    async def test_per_tool_raise_beats_server_safe(self, config_dir):
        write_config(config_dir, [stdio_server(
            "fs", risk_override="safe", tool_risk={"delete_file": "high"})])
        safety = ToolSafetyFramework()
        result = safety.classify("mcp__fs__delete_file", {})
        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_confirmation

    async def test_per_tool_end_to_end_through_executor(self, config_dir):
        write_config(config_dir, [stdio_server(
            "fs", risk_override="high", tool_risk={"read_file": "safe"})])
        executor, client = await bridged_executor()

        read = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"})
        assert read.success
        assert read.risk_level == RiskLevel.SAFE

        delete = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert not delete.success
        assert delete.requires_confirmation
        assert delete.risk_level == RiskLevel.HIGH

    async def test_names_match_across_sanitization(self, config_dir):
        """Config names the server ``my-fs`` and the tool ``delete-file``;
        the registry sanitizes both into the qualified name. The override
        must still find them (matching is on the sanitized form)."""
        write_config(config_dir, [stdio_server(
            "my-fs", risk_override="critical",
            tool_risk={"read-file": "safe"})])
        client = RecordingClient(server="my-fs", tools=[
            {"name": "read-file", "description": "Read",
             "inputSchema": {"type": "object"}},
            {"name": "delete-file", "description": "Delete",
             "inputSchema": {"type": "object"}},
        ])
        executor, _ = await bridged_executor(client)
        assert "mcp__my_fs__delete_file" in executor.tools

        delete = await executor.execute("mcp__my_fs__delete_file", {})
        assert not delete.success  # server-level critical
        assert delete.risk_level == RiskLevel.CRITICAL

        read = await executor.execute("mcp__my_fs__read_file", {})
        assert read.success  # per-tool safe beat the critical server


# ---------------------------------------------------------------------------
# Per-call config freshness
# ---------------------------------------------------------------------------

class TestPerCallFreshness:
    """THE design trap: tool registration happens once at agent init, but
    classification must be evaluated per call against CURRENT config. A
    config flip gates the NEXT tool call with no restart and no
    re-registration — the same executor instance throughout."""

    async def test_flip_gates_the_next_call(self, config_dir):
        executor, client = await bridged_executor()

        # 1. No override: MEDIUM, executes.
        write_config(config_dir, [stdio_server("fs")])
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.success
        assert result.risk_level == RiskLevel.MEDIUM

        # 2. Flip to high: the NEXT call requires confirmation.
        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert not result.success
        assert result.requires_confirmation

        # 3. Flip to critical: the NEXT call blocks outright.
        write_config(config_dir, [stdio_server("fs", risk_override="critical")])
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"}, confirmed=True)
        assert not result.success
        assert result.risk_level == RiskLevel.CRITICAL

        # 4. Flip back to safe: the NEXT call executes again.
        write_config(config_dir, [stdio_server("fs", risk_override="safe")])
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.success
        assert result.risk_level == RiskLevel.SAFE
        assert len(client.calls) == 2  # only the two allowed calls landed

    async def test_registration_time_snapshot_is_not_used(self, config_dir):
        """Classification must not be a snapshot taken at registration:
        register the tool while the config says high, then remove the
        override and prove the next call is MEDIUM, not high."""
        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        executor, _ = await bridged_executor()

        write_config(config_dir, [stdio_server("fs")])
        result = await executor.execute("mcp__fs__read_file", {})
        assert result.success
        assert result.risk_level == RiskLevel.MEDIUM
        assert not result.requires_confirmation


# ---------------------------------------------------------------------------
# Fail-tight config validation
# ---------------------------------------------------------------------------

class TestFailTightValidation:
    """A typo in a risk level must never silently downgrade a server the
    operator meant to fence: an invalid override skips the SERVER entry
    with a warning — the loader's existing validation shape — so the
    server contributes no tools at all in production."""

    def test_invalid_risk_override_skips_the_server(
            self, config_dir, caplog):
        write_config(config_dir, [
            stdio_server("fs", risk_override="extreme"),
            stdio_server("good"),
        ], )
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            cfg = load_config()
        assert [s.name for s in cfg.servers] == ["good"]
        assert any("fs" in r.message and "risk" in r.message
                   for r in caplog.records)

    def test_invalid_tool_risk_value_skips_the_server(
            self, config_dir, caplog):
        write_config(config_dir, [
            stdio_server("fs", tool_risk={"delete_file": "banana"}),
        ])
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            cfg = load_config()
        assert cfg.servers == []
        assert any("fs" in r.message for r in caplog.records)

    def test_tool_risk_non_mapping_skips_the_server(self, config_dir):
        write_config(config_dir, [
            stdio_server("fs", tool_risk=["delete_file"]),
        ])
        cfg = load_config()
        assert cfg.servers == []

    def test_parsed_config_carries_the_overrides(self, config_dir):
        write_config(config_dir, [stdio_server(
            "fs", risk_override="high",
            tool_risk={"read_file": "safe"})])
        cfg = load_config()
        server = cfg.server("fs")
        assert server.risk_override == RiskLevel.HIGH
        assert server.tool_risk == {"read_file": RiskLevel.SAFE}


# ---------------------------------------------------------------------------
# The confirmation message
# ---------------------------------------------------------------------------

class TestConfirmationMessage:

    def test_names_the_server_and_the_tool(self, config_dir):
        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        safety = ToolSafetyFramework()
        result = safety.classify(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        message = safety.get_confirmation_message(
            "mcp__fs__delete_file", {"path": "/tmp/x"}, result)
        assert "fs" in message
        assert "delete_file" in message
        assert "/tmp/x" in message
        assert "HIGH" in message

    def test_args_preview_is_capped(self, config_dir):
        """An MCP tool's args are what the remote server receives, and
        they can be huge; the confirmation surface must not flood."""
        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        safety = ToolSafetyFramework()
        big = {"path": "/tmp/x", "blob": "y" * 10000}
        result = safety.classify("mcp__fs__write_blob", big)
        message = safety.get_confirmation_message(
            "mcp__fs__write_blob", big, result)
        assert len(message) < 2000

    def test_non_dict_args_do_not_crash_the_message(self, config_dir):
        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        safety = ToolSafetyFramework()
        result = safety.classify("mcp__fs__odd", None)
        message = safety.get_confirmation_message("mcp__fs__odd", None, result)
        assert "fs" in message


# ---------------------------------------------------------------------------
# Absent server fails closed (spec review, Issue 1)
# ---------------------------------------------------------------------------

class TestAbsentServerFailsClosed:
    """A REGISTERED ``mcp__`` tool can only exist because its server was
    in the config at registration time. So when the same tool's server is
    ABSENT from the freshly-read config, that is never the
    never-configured case — it always means removed, renamed, or dropped
    by validation. Classification fails closed (blocked, not MEDIUM):
    per-call freshness must not turn a config accident into a silent
    downgrade of a live, registered tool to auto-execute."""

    async def _registered_under_critical(self, config_dir):
        write_config(config_dir, [stdio_server("fs", risk_override="critical")])
        return await bridged_executor()

    async def test_typo_written_mid_process_blocks(self, config_dir, caplog):
        """"critcal" drops the server from the parsed config; the live
        registered tool must not fall to MEDIUM and execute."""
        executor, client = await self._registered_under_critical(config_dir)
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"})
        assert result.success is False  # still blocked under the old config

        write_config(config_dir, [stdio_server("fs", risk_override="critcal")])
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"}, confirmed=True)
        assert not result.success
        assert result.risk_level == RiskLevel.CRITICAL
        assert "fs" in (result.error or "")
        assert "validation" in (result.error or "")
        assert client.calls == []

    async def test_deleted_config_file_blocks(self, config_dir):
        executor, client = await self._registered_under_critical(config_dir)
        (config_dir / "mcp_config.yml").unlink()
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"}, confirmed=True)
        assert not result.success
        assert "fs" in (result.error or "")
        assert client.calls == []

    async def test_corrupt_yaml_blocks(self, config_dir):
        executor, client = await self._registered_under_critical(config_dir)
        (config_dir / "mcp_config.yml").write_text(
            "servers: [ {name: fs,,\n  broken yaml {{{")
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"}, confirmed=True)
        assert not result.success
        assert "fs" in (result.error or "")
        assert client.calls == []

    async def test_server_renamed_away_blocks_the_old_tool(
            self, config_dir):
        """The server is now "my fs": its entry is valid, but the tool
        registered under the old name classifies against a server that no
        longer exists for it — blocked."""
        executor, client = await self._registered_under_critical(config_dir)
        write_config(config_dir, [stdio_server("my fs", risk_override="safe")])
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/tmp/x"}, confirmed=True)
        assert not result.success
        assert result.risk_level == RiskLevel.CRITICAL
        assert "fs" in (result.error or "")
        assert client.calls == []

    async def test_in_config_no_override_still_medium(self, config_dir):
        """The fail-closed rule must not swallow the legitimate default:
        a server PRESENT with no override still classifies MEDIUM."""
        write_config(config_dir, [stdio_server("fs")])
        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.success
        assert result.risk_level == RiskLevel.MEDIUM

    def test_absent_server_reason_names_the_state(self, config_dir):
        """The refusal is diagnosable: it names the server and what the
        config read saw (skipped entries, load failure)."""
        write_config(config_dir, [
            {"name": "fs", "transport": "stdio", "command": "x",
             "risk_override": "critcal"},
        ])
        safety = ToolSafetyFramework()
        result = safety.classify("mcp__fs__read_file", {})
        assert not result.allowed
        assert not result.requires_confirmation
        assert "fs" in result.reason
        assert "validation" in result.reason


# ---------------------------------------------------------------------------
# Override-key matching (spec review, Issue 2)
# ---------------------------------------------------------------------------

class TestOverrideKeyMatching:

    async def test_per_tool_key_matches_case_insensitively(self, config_dir):
        """sanitize_component preserves case, so a key written
        "Delete_File" would never match a registered "delete_file" if
        the comparison were case-sensitive — and a CRITICAL fence would
        silently degrade to auto-execute. Matching compares
        sanitized-lowercased on both sides."""
        write_config(config_dir, [stdio_server(
            "fs", risk_override="medium",
            tool_risk={"Delete_File": "critical"})])
        safety = ToolSafetyFramework()
        result = safety.classify("mcp__fs__delete_file", {})
        assert result.risk_level == RiskLevel.CRITICAL
        assert not result.allowed

    async def test_server_name_matches_case_insensitively(self, config_dir):
        write_config(config_dir, [stdio_server("FS", risk_override="high")])
        safety = ToolSafetyFramework()
        result = safety.classify("mcp__fs__read_file", {})
        assert result.risk_level == RiskLevel.HIGH

    async def test_typo_key_still_warns_and_degrades_visibly(
            self, config_dir, caplog):
        """A key that matches nothing (a real typo, not a case variant)
        cannot match — but the operator hears about it: the bridge warns
        per unmatched key at registration, and the tool still classifies
        on its real path (per-server / MEDIUM here)."""
        write_config(config_dir, [stdio_server(
            "fs", tool_risk={"dlete_file": "critical"})])
        tool_executor = ToolExecutor(web_search=False)
        with caplog.at_level(
                logging.WARNING, logger="halbert.mcp.bridge"):
            await discover_and_register(tool_executor, RecordingClient())
        assert any(
            "dlete_file" in r.message and "fs" in r.message
            for r in caplog.records)

        result = await tool_executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"})
        assert result.success  # MEDIUM default — the typo'd fence warned
        assert result.risk_level == RiskLevel.MEDIUM

    async def test_matched_keys_do_not_warn(self, config_dir, caplog):
        write_config(config_dir, [stdio_server(
            "fs", tool_risk={"delete_file": "critical"})])
        tool_executor = ToolExecutor(web_search=False)
        with caplog.at_level(
                logging.WARNING, logger="halbert.mcp.bridge"):
            await discover_and_register(tool_executor, RecordingClient())
        assert not any(
            "matches no advertised tool" in r.message
            for r in caplog.records)


# ---------------------------------------------------------------------------
# Sanitized server-name collisions (spec review, Issue 3)
# ---------------------------------------------------------------------------

class TestSanitizedServerCollision:
    """``my-fs`` and ``my_fs`` sanitize to the same registered namespace.
    If both were kept, classification of ``mcp__my_fs__…`` would depend on
    config order — so the loader keeps the first and rejects the later
    colliding entry, exactly like the raw duplicate-name rule."""

    def test_collision_keeps_first_and_names_both(self, config_dir, caplog):
        write_config(config_dir, [
            stdio_server("my-fs"),
            stdio_server("my_fs", risk_override="critical"),
        ])
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            cfg = load_config()
        assert [s.name for s in cfg.servers] == ["my-fs"]
        assert any(
            "my-fs" in r.message and "my_fs" in r.message
            for r in caplog.records)

    def test_case_only_collision_is_rejected_too(self, config_dir):
        """Matching is case-insensitive, so FS/fs would collide at
        classification; the loader must reject the pair for the same
        order-dependence reason."""
        write_config(config_dir, [
            stdio_server("FS"),
            stdio_server("fs", risk_override="critical"),
        ])
        cfg = load_config()
        assert [s.name for s in cfg.servers] == ["FS"]

    async def test_classification_deterministic_regardless_of_order(
            self, config_dir):
        """Whichever entry survives, the SAME config classifies the SAME
        call identically every time (no order flip mid-process)."""
        write_config(config_dir, [
            stdio_server("my-fs"),
            stdio_server("my_fs", risk_override="critical"),
        ])
        safety = ToolSafetyFramework()
        for _ in range(3):
            result = safety.classify("mcp__my_fs__delete_file", {})
            assert result.risk_level == RiskLevel.MEDIUM  # my-fs survives

        write_config(config_dir, [
            stdio_server("my_fs", risk_override="critical"),
            stdio_server("my-fs"),
        ])
        for _ in range(3):
            result = safety.classify("mcp__my_fs__delete_file", {})
            assert result.risk_level == RiskLevel.CRITICAL  # my_fs wins


# ---------------------------------------------------------------------------
# The guest hold (B2's structural pin, re-pinned against B3)
# ---------------------------------------------------------------------------

class TestGuestHoldHeld:

    @pytest.fixture(autouse=True)
    def _fresh_guest_state(self):
        from halbert_core.persona import guest
        guest.reset_for_tests()
        yield
        guest.reset_for_tests()

    async def test_guest_refused_even_on_a_safe_server(self, config_dir):
        """Classification must never be what saves a guest: the allowlist
        IS the rule (no ``mcp__`` name can be on it), so even a server
        the operator marked ``risk_override: safe`` is refused."""
        write_config(config_dir, [stdio_server("fs", risk_override="safe")])
        from halbert_core.persona import guest
        persona, _ = guest.GuestPersona.from_payload({"name": "Marnie"})
        guest.offer(persona, offered_by="h2-node", offered_by_name="H2")

        executor, client = await bridged_executor()
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/etc/hosts"})
        assert not result.success
        assert "not available while" in (result.error or "")
        assert client.calls == []


# ---------------------------------------------------------------------------
# RoleGate path (the same chain, with the gate installed)
# ---------------------------------------------------------------------------

class TestRoleGatePath:

    async def test_restricted_role_capped_below_high(self, config_dir):
        """A restricted speaker cannot run a HIGH-classified MCP tool:
        RoleGate blocks it (allowed=False), confirmation cannot save it."""
        from halbert_core.tools.role_gate import RoleGate

        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        executor, client = await bridged_executor()
        executor.role_gate = RoleGate(executor.safety)

        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"},
            speaker_role="restricted", confirmed=True)
        assert not result.success
        assert client.calls == []

    async def test_admin_role_runs_high_with_confirmation(self, config_dir):
        from halbert_core.tools.role_gate import RoleGate

        write_config(config_dir, [stdio_server("fs", risk_override="high")])
        executor, client = await bridged_executor()
        executor.role_gate = RoleGate(executor.safety)

        result = await executor.execute(
            "mcp__fs__delete_file", {"path": "/tmp/x"},
            speaker_role="admin", confirmed=True)
        assert result.success
        assert client.calls


# ---------------------------------------------------------------------------
# B5-facing risk summary
# ---------------------------------------------------------------------------

class TestRiskSummary:
    """B5 (dashboard UI) renders "filesystem: HIGH" from current config
    through this query — it must read the same fresh config as
    classification."""

    def test_reflects_current_config(self, config_dir):
        from halbert_core.tools.mcp_safety import mcp_risk_summary
        write_config(config_dir, [
            stdio_server("fs", risk_override="high",
                         tool_risk={"read_file": "safe"}),
            stdio_server("api"),
        ])
        summary = mcp_risk_summary()
        assert summary["default"] == "medium"
        assert summary["servers"]["fs"]["risk_override"] == "high"
        assert summary["servers"]["fs"]["tool_risk"]["read_file"] == "safe"
        assert summary["servers"]["api"]["risk_override"] is None

    def test_empty_config_reports_default_only(self, config_dir):
        from halbert_core.tools.mcp_safety import mcp_risk_summary
        summary = mcp_risk_summary()
        assert summary["default"] == "medium"
        assert summary["servers"] == {}

    async def test_summary_flips_with_config(self, config_dir):
        from halbert_core.tools.mcp_safety import mcp_risk_summary
        write_config(config_dir, [stdio_server("fs")])
        assert mcp_risk_summary()["servers"]["fs"]["risk_override"] is None
        write_config(config_dir, [stdio_server("fs", risk_override="critical")])
        assert mcp_risk_summary()["servers"]["fs"]["risk_override"] == "critical"