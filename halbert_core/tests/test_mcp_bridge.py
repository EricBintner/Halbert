# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the MCP tool registration bridge (Workstream B2).

The bridge turns MCP server tools into native agent tools: namespaced
``mcp__{server}__{tool}`` names, converted schemas, and async handlers
that call through ``MCPClient`` and map every failure mode to a clean
result. Tests mock at the MCPClient boundary (a fake with canned
tools/calls/results) plus one integration path through a real
``ToolExecutor`` and the agent-init wiring in ``dashboard/routes/agent.py``.

B1 residual coverage (folded into B2 by authorization): the concurrent
always-expire retype lives in test_mcp_client.py, next to the other
session-expiry tests.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp.client import (
    MCPConnectionError,
    MCPDisconnectedError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPToolError,
)
from halbert_core.tools.executor import ToolExecutor


# =============================================================================
# Test doubles
# =============================================================================

#: A minimal real stdio MCP server (the B1 pattern): initialize →
#: tools/list → tools/call, line-delimited JSON-RPC on stdin/stdout.
FAKE_STDIO_SERVER = r'''
import json, sys

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

TOOLS = [{"name": "add", "description": "Add two integers.",
          "inputSchema": {"type": "object",
                          "properties": {"a": {"type": "integer"},
                                         "b": {"type": "integer"}},
                          "required": ["a", "b"]}}]

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        req = json.loads(line)
    except Exception:
        continue
    if "id" not in req:
        continue  # notification: no response, per spec
    method = req.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": req["id"], "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "bridge-fake", "version": "0"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": req["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        args = (req.get("params") or {}).get("arguments") or {}
        total = int(args.get("a", 0)) + int(args.get("b", 0))
        send({"jsonrpc": "2.0", "id": req["id"], "result": {
            "content": [{"type": "text", "text": str(total)}]}})
    else:
        send({"jsonrpc": "2.0", "id": req["id"], "error": {
            "code": -32601, "message": "Unknown method"}})
'''

def _tool_schema(name, description="A tool", properties=None, required=None):
    """A canned tools/list entry, the wire shape MCP servers answer with."""
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


def _text_result(text):
    """A canned tools/call result with text content."""
    return {"content": [{"type": "text", "text": text}]}


class FakeMCPClient:
    """Stands in for MCPClient at the boundary B2 depends on.

    ``tools`` maps server name -> tools/list answer. ``results`` maps
    (server, tool) -> the tools/call return value, or an Exception
    instance to raise. ``connect_failures`` names servers that cannot be
    reached (a down server connects to nothing, like the real client's
    logged-and-collected failure path). ``list_failures`` maps server ->
    Exception to raise from list_tools (a server that connected but
    cannot answer tools/list).
    """

    def __init__(self, tools=None, results=None, connect_failures=(),
                 list_failures=None):
        self.tools = dict(tools or {})
        self.results = dict(results or {})
        self.connect_failures = set(connect_failures)
        self.list_failures = dict(list_failures or {})
        self.connected = []
        self.tool_calls = []

    async def connect(self, server_name=None):
        names = ([server_name] if server_name is not None
                 else sorted(self.tools))
        for name in names:
            if name in self.connect_failures:
                continue  # logged by the real client, never raised
            self.connected.append(name)

    async def list_tools(self, server_name):
        if server_name in self.list_failures:
            raise self.list_failures[server_name]
        if server_name not in self.connected:
            raise MCPConnectionError(
                f"MCP server '{server_name}': not connected")
        return list(self.tools.get(server_name, []))

    async def call_tool(self, server_name, tool_name, arguments=None):
        self.tool_calls.append((server_name, tool_name, dict(arguments or {})))
        value = self.results.get((server_name, tool_name))
        if isinstance(value, Exception):
            raise value
        if value is None:
            return _text_result("ok")
        return value

    def connected_servers(self):
        return sorted(set(self.connected))


FS_TOOLS = [
    _tool_schema("read_file", "Read a file from disk",
                 properties={"path": {"type": "string"}},
                 required=["path"]),
    _tool_schema("list_dir", "List a directory",
                 properties={"path": {"type": "string"}}),
]

CALC_TOOLS = [
    _tool_schema("add", "Add two numbers",
                 properties={"a": {"type": "integer"},
                             "b": {"type": "integer"}},
                 required=["a", "b"]),
]


def _mcp_tools(executor):
    return sorted(name for name in executor.tools if name.startswith("mcp__"))


# =============================================================================
# Registration and namespacing
# =============================================================================

class TestRegistration:

    def test_tools_registered_with_namespaced_names(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(tools={"fs": FS_TOOLS})
        register_mcp_tools(executor, client)
        assert _mcp_tools(executor) == [
            "mcp__fs__list_dir", "mcp__fs__read_file"]

    def test_schemas_convert_mcp_inputschema_to_parameters(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(tools={"fs": FS_TOOLS})
        register_mcp_tools(executor, client)
        schema = executor.schemas["mcp__fs__read_file"]
        # Halbert's tool schema shape: name + description + parameters,
        # where parameters is the JSON-Schema object MCP calls inputSchema.
        assert schema["name"] == "mcp__fs__read_file"
        assert schema["description"] == "Read a file from disk"
        assert schema["parameters"] == {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        # And the model-facing wrapper get_schemas() produces is intact.
        offered = {s["function"]["name"]: s
                   for s in executor.get_schemas()}
        assert "mcp__fs__read_file" in offered
        assert offered["mcp__fs__read_file"]["type"] == "function"

    def test_missing_inputschema_defaults_to_empty_object_schema(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": [{"name": "bare", "description": "No schema"}]})
        register_mcp_tools(executor, client)
        schema = executor.schemas["mcp__fs__bare"]
        assert schema["parameters"] == {"type": "object", "properties": {}}

    def test_missing_description_falls_back(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(tools={"fs": [{"name": "bare"}]})
        register_mcp_tools(executor, client)
        schema = executor.schemas["mcp__fs__bare"]
        assert "fs" in schema["description"]
        assert "bare" in schema["description"]

    def test_tool_without_a_name_is_skipped(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": [{"description": "nameless"}, {"name": "ok"}]})
        register_mcp_tools(executor, client)
        assert _mcp_tools(executor) == ["mcp__fs__ok"]

    def test_tools_from_multiple_servers(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(tools={"fs": FS_TOOLS, "calc": CALC_TOOLS})
        register_mcp_tools(executor, client)
        assert _mcp_tools(executor) == [
            "mcp__calc__add", "mcp__fs__list_dir", "mcp__fs__read_file"]

    def test_colliding_names_get_deterministic_suffixes(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(tools={
            "fs": [_tool_schema("read-file"), _tool_schema("read_file")],
        })
        register_mcp_tools(executor, client)
        # Both sanitize to mcp__fs__read_file; the first keeps the bare
        # name, the second gets a suffix (B1's registry rule).
        assert _mcp_tools(executor) == [
            "mcp__fs__read_file", "mcp__fs__read_file_2"]


class TestGracefulAbsence:

    def test_server_down_at_init_contributes_no_tools(self, caplog):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": FS_TOOLS, "calc": CALC_TOOLS},
            connect_failures={"fs"})
        with caplog.at_level(logging.WARNING):
            register_mcp_tools(executor, client)
        assert _mcp_tools(executor) == ["mcp__calc__add"]
        assert not client.connected or "fs" not in client.connected

    def test_list_tools_failure_skips_that_server(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": FS_TOOLS, "calc": CALC_TOOLS},
            list_failures={"calc": MCPConnectionError("went away mid-list")})
        register_mcp_tools(executor, client)
        assert _mcp_tools(executor) == [
            "mcp__fs__list_dir", "mcp__fs__read_file"]

    def test_no_configured_servers_registers_nothing(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        register_mcp_tools(executor, FakeMCPClient())
        assert _mcp_tools(executor) == []

    async def test_discovery_never_raises_even_on_garbage(self):
        from halbert_core.mcp.bridge import discover_and_register

        class GarbageClient:
            async def connect(self, server_name=None):
                raise RuntimeError("not even an MCPClientError")

            def connected_servers(self):
                raise RuntimeError("completely broken")

        executor = ToolExecutor()
        # Returns a count; a broken client is zero tools, not a crash.
        registered = await discover_and_register(executor, GarbageClient())
        assert registered == 0
        assert _mcp_tools(executor) == []


class TestRestartAndRefresh:
    """The acceptance criteria are restart-based: config edit + agent
    restart. A fresh executor is a restart; re-registration on the same
    executor is the bridge's refresh path (a stale mcp__ registration
    from a previous config must not survive it)."""

    def test_restart_adds_a_new_servers_tools(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        before = ToolExecutor()
        register_mcp_tools(before, FakeMCPClient(tools={"fs": FS_TOOLS}))
        assert "mcp__fs__read_file" in before.tools

        # Restart with a config that adds calc and drops nothing.
        after = ToolExecutor()
        register_mcp_tools(
            after, FakeMCPClient(tools={"fs": FS_TOOLS, "calc": CALC_TOOLS}))
        assert _mcp_tools(after) == [
            "mcp__calc__add", "mcp__fs__list_dir", "mcp__fs__read_file"]

    def test_restart_removes_a_removed_servers_tools(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        before = ToolExecutor()
        register_mcp_tools(
            before, FakeMCPClient(tools={"fs": FS_TOOLS, "calc": CALC_TOOLS}))
        assert "mcp__calc__add" in before.tools

        after = ToolExecutor()
        register_mcp_tools(after, FakeMCPClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(after) == ["mcp__fs__list_dir", "mcp__fs__read_file"]

    def test_refresh_on_same_executor_drops_removed_servers(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        register_mcp_tools(
            executor, FakeMCPClient(tools={"fs": FS_TOOLS, "calc": CALC_TOOLS}))
        assert "mcp__calc__add" in executor.tools
        # Config edit: calc removed, fs kept — re-register on the SAME
        # executor (what a B4 health refresh would do).
        register_mcp_tools(executor, FakeMCPClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__list_dir", "mcp__fs__read_file"]

    def test_re_registration_does_not_duplicate(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(tools={"fs": FS_TOOLS})
        register_mcp_tools(executor, client)
        register_mcp_tools(executor, FakeMCPClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__list_dir", "mcp__fs__read_file"]


class TestToolCountCaps:

    def test_over_cap_truncates_and_warns(self, caplog):
        from halbert_core.mcp.bridge import MAX_TOOLS_PER_SERVER, register_mcp_tools

        assert MAX_TOOLS_PER_SERVER >= 1
        tools = [_tool_schema(f"t{i}") for i in range(MAX_TOOLS_PER_SERVER + 40)]
        executor = ToolExecutor()
        with caplog.at_level(logging.WARNING):
            register_mcp_tools(executor, FakeMCPClient(tools={"big": tools}))
        assert len(_mcp_tools(executor)) == MAX_TOOLS_PER_SERVER
        assert any("big" in r.message for r in caplog.records
                   if r.levelno >= logging.WARNING)

    def test_many_tools_under_cap_warns_but_keeps_all(self, caplog):
        from halbert_core.mcp.bridge import (
            MANY_TOOLS_WARNING, MAX_TOOLS_PER_SERVER, register_mcp_tools,
        )

        assert MANY_TOOLS_WARNING < MAX_TOOLS_PER_SERVER
        tools = [_tool_schema(f"t{i}") for i in range(MANY_TOOLS_WARNING + 1)]
        executor = ToolExecutor()
        with caplog.at_level(logging.WARNING):
            register_mcp_tools(executor, FakeMCPClient(tools={"big": tools}))
        assert len(_mcp_tools(executor)) == len(tools)
        assert any("big" in r.message for r in caplog.records
                   if r.levelno >= logging.WARNING)


# =============================================================================
# Calling MCP tools through a real ToolExecutor
# =============================================================================

class TestCalling:

    async def test_call_passes_args_and_returns_text(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": FS_TOOLS},
            results={("fs", "read_file"): _text_result("file body")})
        task = register_mcp_tools(executor, client)
        await task  # discovery is scheduled, not run, until awaited

        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/etc/hosts"})
        assert result.success is True
        assert result.result == "file body"
        assert client.tool_calls == [("fs", "read_file", {"path": "/etc/hosts"})]

    async def test_multi_part_text_content_is_joined(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": FS_TOOLS},
            results={("fs", "read_file"): {"content": [
                {"type": "text", "text": "line one"},
                {"type": "text", "text": "line two"},
            ]}})
        task = register_mcp_tools(executor, client)
        await task
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/x"})
        assert result.success is True
        assert result.result == "line one\nline two"

    async def test_non_text_result_is_json(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": FS_TOOLS},
            results={("fs", "read_file"): {"content": [
                {"type": "image", "data": "base64bytes"}]}})
        task = register_mcp_tools(executor, client)
        await task
        result = await executor.execute("mcp__fs__read_file", {"path": "/x"})
        assert result.success is True
        assert "base64bytes" in result.result

    @pytest.mark.parametrize("exc,fragment", [
        (MCPToolError(
            "MCP server 'fs' tool 'read_file' reported an error: boom detail",
            result={"isError": True}, text="boom detail"),
         "boom detail"),
        (MCPTimeoutError("MCP server 'fs': no response within 30s"),
         "MCP server 'fs'"),
        (MCPConnectionError("MCP server 'fs': failed to launch"),
         "failed to launch"),
        (MCPDisconnectedError("MCP server 'fs': connection closed"),
         "connection closed"),
        (MCPProtocolError("MCP server 'fs' rejected 'tools/call': [-1] bad"),
         "bad"),
        (RuntimeError("something unexpected"),
         "something unexpected"),
    ])
    async def test_every_failure_mode_is_a_clean_failed_result(
            self, exc, fragment):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        client = FakeMCPClient(
            tools={"fs": FS_TOOLS},
            results={("fs", "read_file"): exc})
        task = register_mcp_tools(executor, client)
        await task
        # Must not raise out of execute — the agent turn survives.
        result = await executor.execute(
            "mcp__fs__read_file", {"path": "/x"})
        assert result.success is False
        assert fragment in result.error


# =============================================================================
# Sync entry: loop detection
# =============================================================================

class TestSyncEntry:

    def test_sync_context_runs_discovery_to_completion(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        returned = register_mcp_tools(
            executor, FakeMCPClient(tools={"fs": FS_TOOLS}))
        assert returned is None  # nothing pending: discovery already ran
        assert _mcp_tools(executor) == [
            "mcp__fs__list_dir", "mcp__fs__read_file"]

    async def test_running_loop_schedules_and_returns_the_task(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        executor = ToolExecutor()
        task = register_mcp_tools(
            executor, FakeMCPClient(tools={"fs": FS_TOOLS}))
        assert isinstance(task, asyncio.Task)
        await task
        assert _mcp_tools(executor) == [
            "mcp__fs__list_dir", "mcp__fs__read_file"]

    async def test_scheduled_task_absorbs_its_own_failures(self):
        from halbert_core.mcp.bridge import register_mcp_tools

        class GarbageClient:
            async def connect(self, server_name=None):
                raise RuntimeError("boom")

            def connected_servers(self):
                return []

        executor = ToolExecutor()
        task = register_mcp_tools(executor, GarbageClient())
        await task  # must not raise
        assert _mcp_tools(executor) == []


# =============================================================================
# End-to-end: a real MCPClient against a real (in-process) stdio server
# =============================================================================

class TestEndToEnd:

    async def test_real_stdio_server_bridges_and_executes(self, tmp_path):
        """The full chain: subprocess MCP server → real MCPClient →
        bridge → real ToolExecutor → a tool call that returns '5'."""
        from halbert_core.mcp.bridge import register_mcp_tools
        from halbert_core.mcp.client import MCPClient
        from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

        script = tmp_path / "fake_mcp_server.py"
        script.write_text(FAKE_STDIO_SERVER)
        client = MCPClient(config_loader=lambda: MCPClientConfig(servers=[
            MCPServerConfig(name="fakesrv", transport="stdio",
                            command=sys.executable, args=[str(script)],
                            timeout_seconds=5.0),
        ]))
        executor = ToolExecutor()
        try:
            task = register_mcp_tools(executor, client)
            await task
            assert _mcp_tools(executor) == ["mcp__fakesrv__add"]
            assert executor.schemas["mcp__fakesrv__add"]["parameters"][
                "required"] == ["a", "b"]
            result = await executor.execute(
                "mcp__fakesrv__add", {"a": 2, "b": 3})
            assert result.success is True
            assert result.result == "5"
        finally:
            await client.disconnect()

    async def test_unlaunchable_server_contributes_no_tools(self):
        """A server whose command cannot even launch is graceful absence:
        no tools, no crash, agent init unaffected."""
        from halbert_core.mcp.bridge import register_mcp_tools
        from halbert_core.mcp.client import MCPClient
        from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

        client = MCPClient(config_loader=lambda: MCPClientConfig(servers=[
            MCPServerConfig(name="ghost", transport="stdio",
                            command="/nonexistent/definitely-not-here",
                            args=[]),
        ]))
        executor = ToolExecutor()
        task = register_mcp_tools(executor, client)
        await task  # must not raise
        assert _mcp_tools(executor) == []


# =============================================================================
# Capability + guest surface
# =============================================================================

class TestCapabilityAndGuests:

    def test_capability_constant_is_registered(self):
        from halbert_core.capabilities import (
            ALL_CAPABILITIES, CAP_MCP_CLIENT, _PRESET_HOME, _PRESET_SYSADMIN,
            _PROBES,
        )
        assert CAP_MCP_CLIENT == "mcp_client"
        assert CAP_MCP_CLIENT in ALL_CAPABILITIES
        assert _PRESET_SYSADMIN[CAP_MCP_CLIENT] is True
        assert _PRESET_HOME[CAP_MCP_CLIENT] is False
        # Config-driven, not runtime-detected: no probe.
        assert CAP_MCP_CLIENT not in _PROBES

    def test_mcp_tools_are_denied_to_guests(self):
        from halbert_core.persona.guest_tools import (
            GUEST_ALLOWED_TOOLS, is_tool_allowed_for_guest,
        )
        assert "mcp__fs__read_file" not in GUEST_ALLOWED_TOOLS
        assert is_tool_allowed_for_guest("mcp__fs__read_file") is False
        # And the structural rule holds for every name a server could
        # produce: the allowlist is the whole rule, and no mcp__ name is
        # on it.
        assert not any(name.startswith("mcp__") for name in GUEST_ALLOWED_TOOLS)


# =============================================================================
# Agent init wiring (dashboard/routes/agent.py get_agent)
# =============================================================================

def _prepare_agent_routes(monkeypatch):
    """get_agent() scaffolding, same pattern as the existing wiring tests."""
    import halbert_core.dashboard.routes.agent as agent_routes
    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    monkeypatch.setattr(agent_routes, "_get_llm_client", lambda: MagicMock())
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring.get_cognition_tick",
        lambda: None)
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring.get_event_mapper",
        lambda: None)
    return agent_routes


class TestAgentInit:

    def test_capability_off_registers_nothing_and_imports_no_mcp(
            self, monkeypatch, capability_registry):
        capability_registry.set_capability("mcp_client", False)
        agent_routes = _prepare_agent_routes(monkeypatch)
        mcp_before = {m for m in sys.modules
                      if m.startswith("halbert_core.mcp")}

        agent = agent_routes.get_agent()
        try:
            assert not any(name.startswith("mcp__")
                           for name in agent.tools.tools)
            mcp_after = {m for m in sys.modules
                         if m.startswith("halbert_core.mcp")}
            assert mcp_after == mcp_before
        finally:
            monkeypatch.setattr(agent_routes, "_agent_instance", None)

    def test_capability_on_registers_mcp_tools(
            self, monkeypatch, capability_registry):
        capability_registry.set_capability("mcp_client", True)
        agent_routes = _prepare_agent_routes(monkeypatch)
        fake_client = FakeMCPClient(tools={"fs": FS_TOOLS})
        monkeypatch.setattr(
            "halbert_core.mcp.client.MCPClient", lambda: fake_client)

        agent = agent_routes.get_agent()
        try:
            assert "mcp__fs__read_file" in agent.tools.tools
            schema = agent.tools.schemas["mcp__fs__read_file"]
            assert schema["name"] == "mcp__fs__read_file"
        finally:
            monkeypatch.setattr(agent_routes, "_agent_instance", None)

    def test_mcp_failure_does_not_break_the_agent(
            self, monkeypatch, capability_registry):
        capability_registry.set_capability("mcp_client", True)
        agent_routes = _prepare_agent_routes(monkeypatch)

        def _boom():
            raise RuntimeError("MCP blew up during init")

        monkeypatch.setattr("halbert_core.mcp.client.MCPClient", _boom)

        agent = agent_routes.get_agent()  # must not raise
        try:
            assert agent is not None
            assert not any(name.startswith("mcp__")
                           for name in agent.tools.tools)
        finally:
            monkeypatch.setattr(agent_routes, "_agent_instance", None)