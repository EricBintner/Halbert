# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-09 Phase C: what happens around a server, not inside one message.

- **A17-G10** -- a stdio server was spawned without its own session, and
  ``close()`` killed only the direct child. ``npx`` spawns ``npm`` spawns
  ``node``: the grandchildren outlived Halbert's own teardown.
- **A17-G11** -- ``notifications/tools/list_changed`` was dropped ("server
  notifications are dropped", the read loop's own docstring), so a server
  that gained or lost a tool kept its stale registration until a config
  change happened to trigger a refresh.
- **A17-G12** -- two tools from the SAME server whose names sanitize to
  the same component both registered, the second with a ``_2`` suffix.
  Neither can be fenced by a per-tool risk override, because the override
  matches the sanitized component and now names two tools.
- **A17-G13** -- nothing consulted a breaker in the CALL path: a dead
  server cost a full timeout per call, every call, with an error string
  that told the model nothing about whether to retry.
- **A17-G14** -- the reconnect budget was zeroed by any successful probe.
  A server that handshakes and then dies looks healthy at the instant of
  the reset, so the budget never charges and it is relaunched forever.
"""

import asyncio

import pytest


# ---------------------------------------------------------------------------
# A17-G10: the child gets its own process group
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_stdio_server_is_spawned_in_its_own_session(monkeypatch):
    from halbert_core.mcp import client as client_mod

    seen = {}

    async def _fake_exec(*args, **kwargs):
        seen.update(kwargs)
        raise OSError("not really launching")

    monkeypatch.setattr(client_mod.asyncio, "create_subprocess_exec", _fake_exec)
    transport = client_mod.StdioTransport(name="x", command="npx")
    with pytest.raises(client_mod.MCPConnectionError):
        await transport.connect()
    assert seen.get("start_new_session") is True


@pytest.mark.asyncio
async def test_close_escalates_to_the_process_group():
    from halbert_core.mcp.client import StdioTransport

    killed = []

    class _Proc:
        pid = 4242
        returncode = None
        stdin = None
        stdout = None

        def kill(self):
            killed.append("child")

        async def wait(self):
            self.returncode = -9
            return -9

    transport = StdioTransport(name="x", command="npx")
    transport._proc = _Proc()
    transport._pgid = 4242

    calls = []
    import halbert_core.mcp.client as client_mod
    client_mod._killpg = lambda pgid, sig: calls.append((pgid, sig))

    await transport.close()
    assert calls, "close() must signal the process group, not only the child"
    assert calls[0][0] == 4242


# ---------------------------------------------------------------------------
# A17-G12: an intra-server name collision excludes, it does not suffix
# ---------------------------------------------------------------------------

def test_two_same_server_tools_with_one_sanitized_name_are_excluded():
    from halbert_core.mcp.registry import MCPToolRegistry

    registry = MCPToolRegistry()
    names = registry.register("fs", [
        {"name": "read-file"},
        {"name": "read_file"},     # same sanitized component
    ])
    assert names == ["mcp__fs__read_file"]
    assert "mcp__fs__read_file_2" not in registry


def test_a_cross_server_collision_still_suffixes():
    """Two servers may legitimately both offer "read_file"."""
    from halbert_core.mcp.registry import MCPToolRegistry

    registry = MCPToolRegistry()
    registry.register("a", [{"name": "read_file"}])
    names = registry.register("b", [{"name": "read_file"}])
    assert names == ["mcp__b__read_file"]


# ---------------------------------------------------------------------------
# A17-G8: an annotation raises risk, an override still wins
# ---------------------------------------------------------------------------

def _configured_fs(monkeypatch, **overrides):
    """A config naming server "fs", so the classifier does not take the
    absent-server fail-closed branch (which is its own test's subject)."""
    from types import SimpleNamespace
    import halbert_core.tools.mcp_safety as mcp_safety

    server = SimpleNamespace(
        name="fs", tool_risk=overrides.get("tool_risk", {}),
        risk_override=overrides.get("risk_override"),
    )
    monkeypatch.setattr(
        mcp_safety, "_current_config",
        lambda: SimpleNamespace(servers=[server]),
    )


def test_a_destructive_annotation_classifies_high(monkeypatch):
    from halbert_core.mcp.registry import get_tool_registry
    from halbert_core.tools.mcp_safety import classify_mcp_tool
    from halbert_core.tools.safety import RiskLevel

    _configured_fs(monkeypatch)
    registry = get_tool_registry()
    registry.register("fs", [
        {"name": "delete_file", "annotations": {"destructiveHint": True}},
    ])
    try:
        result = classify_mcp_tool("mcp__fs__delete_file", {})
        assert result.risk_level is RiskLevel.HIGH
    finally:
        registry.unregister_server("fs")


def test_a_read_only_annotation_stays_medium(monkeypatch):
    from halbert_core.mcp.registry import get_tool_registry
    from halbert_core.tools.mcp_safety import classify_mcp_tool
    from halbert_core.tools.safety import RiskLevel

    _configured_fs(monkeypatch)
    registry = get_tool_registry()
    registry.register("fs", [
        {"name": "read_file", "annotations": {"readOnlyHint": True}},
    ])
    try:
        result = classify_mcp_tool("mcp__fs__read_file", {})
        assert result.risk_level is RiskLevel.MEDIUM
    finally:
        registry.unregister_server("fs")


def test_an_operator_override_still_beats_the_annotation(monkeypatch):
    """A hint may tighten; the operator's word is still the top."""
    from halbert_core.mcp.registry import get_tool_registry
    from halbert_core.tools.mcp_safety import classify_mcp_tool
    from halbert_core.tools.safety import RiskLevel

    _configured_fs(monkeypatch, tool_risk={"delete_file": RiskLevel.LOW})
    registry = get_tool_registry()
    registry.register("fs", [
        {"name": "delete_file", "annotations": {"destructiveHint": True}},
    ])
    try:
        assert classify_mcp_tool(
            "mcp__fs__delete_file", {}).risk_level is RiskLevel.LOW
    finally:
        registry.unregister_server("fs")


# ---------------------------------------------------------------------------
# A17-G13: the call path consults a breaker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_down_server_fails_fast_with_retry_guidance(monkeypatch):
    from halbert_core.mcp import health as health_mod
    from halbert_core.mcp.bridge import make_tool_handler
    from halbert_core.mcp.client import MCPDisconnectedError

    class _Record:
        health = "down"
        connected = False
        next_retry_at = 0.0
        last_error = "launch failed"

    class _Monitor:
        def health_record(self, name):
            return _Record()

        def _now(self):
            return 0.0

    monkeypatch.setattr(health_mod, "get_active_monitor", lambda: _Monitor())

    called = []

    class _Client:
        async def call_tool(self, server, tool, args):
            called.append((server, tool))
            await asyncio.sleep(30)

    handler = make_tool_handler(_Client(), "fs", "read_file")
    with pytest.raises(MCPDisconnectedError) as excinfo:
        await asyncio.wait_for(handler({}), timeout=2)
    message = str(excinfo.value)
    assert "not a timeout" in message.lower() or "never reached" in message.lower()
    assert "retry" in message.lower()
    assert called == [], "a down server must not be dialled"


@pytest.mark.asyncio
async def test_a_healthy_server_is_dialled_normally(monkeypatch):
    from halbert_core.mcp import health as health_mod
    from halbert_core.mcp.bridge import make_tool_handler

    monkeypatch.setattr(health_mod, "get_active_monitor", lambda: None)

    class _Client:
        async def call_tool(self, server, tool, args):
            return {"content": [{"type": "text", "text": "ok"}]}

    handler = make_tool_handler(_Client(), "fs", "read_file")
    assert "ok" in await handler({})


# ---------------------------------------------------------------------------
# A17-G14: only a proven session clears the budget
# ---------------------------------------------------------------------------

def test_a_session_that_dies_right_after_the_handshake_still_owes_the_budget():
    from halbert_core.mcp.health import MCPHealthMonitor, ServerHealth

    monitor = MCPHealthMonitor(client=None)
    record = ServerHealth(name="flaky")
    record.reconnect_attempts = 3
    record.connected_at = 100.0
    monitor._now = lambda: 100.5      # well inside the probe interval

    monitor._probe_succeeded(record)
    assert record.reconnect_attempts == 3, "an unproven session clears nothing"
    assert record.proven is False


def test_a_session_that_survives_a_probe_interval_clears_the_budget():
    from halbert_core.mcp.health import MCPHealthMonitor, ServerHealth

    monitor = MCPHealthMonitor(client=None)
    record = ServerHealth(name="steady")
    record.reconnect_attempts = 3
    record.connected_at = 100.0
    monitor._now = lambda: 100.0 + monitor.interval + 1

    monitor._probe_succeeded(record)
    assert record.proven is True
    assert record.reconnect_attempts == 0


# ---------------------------------------------------------------------------
# A17-G11: list_changed refreshes off the read loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_list_changed_notification_sets_the_flag_not_a_refresh():
    """The read loop must not re-run discovery inline: that wedges the
    stdio stream while a request is in flight."""
    from halbert_core.mcp.client import StdioTransport

    transport = StdioTransport(name="fs", command="/bin/true")
    line = b'{"jsonrpc":"2.0","method":"notifications/tools/list_changed"}\n'

    class _Reader:
        def __init__(self):
            self.lines = [line]

        async def readline(self):
            return self.lines.pop(0) if self.lines else b""

    class _Proc:
        returncode = None
        stdout = _Reader()
        stdin = None

    transport._proc = _Proc()
    await transport._read_loop()
    assert transport.tools_changed is True


def test_the_monitor_consumes_the_flag_once():
    from types import SimpleNamespace

    from halbert_core.mcp.health import MCPHealthMonitor

    transport = SimpleNamespace(tools_changed=True)
    client = SimpleNamespace(
        _connections={"fs": SimpleNamespace(transport=transport)}
    )
    monitor = MCPHealthMonitor(client=client)
    assert monitor._consume_tools_changed() is True
    assert transport.tools_changed is False
    assert monitor._consume_tools_changed() is False
