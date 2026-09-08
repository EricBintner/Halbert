# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP server health monitoring (Workstream B4).

The monitor (mcp/health.py) owns the three B4 jobs:

* detection — a periodic sweep that probes each configured server
  (``ping`` for a live transport, the transport ``alive`` flag for a
  crashed one) and records the verdict for the dashboard;
* recovery — backoff-capped reconnection (start, ×2, cap; reset on
  success — a reconnection storm is what the cap exists to prevent);
* the config-refresh re-registration piggyback — re-bridging from
  CURRENT config whenever mcp_config.yml's file identity changes (which
  closes B3's collider-displacement residual) or a server recovers
  (its tools may never have been registered while it was down).

Plus the two residuals folded in here:

* the bridge's stale-drop ordering fix — a refresh whose connect fails
  KEEPS the prior registrations (TestStaleDropOrdering, bridge-level);
* the config memo (config.py, identity-keyed) — freshness without
  re-parsing the same file twice per call (TestConfigMemo).

The monitor is tested against a fake client at the same boundary the
bridge tests use, plus real-client integration tests against the
in-process fake stdio server imported from test_mcp_client — one fake
server, the same one the client's own tests speak to.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp.client import (  # noqa: E402
    MCPClientError,
    MCPConnectionError,
    MCPDisconnectedError,
    MCPProtocolError,
)
from halbert_core.mcp.bridge import discover_and_register  # noqa: E402
from halbert_core.mcp.config import (  # noqa: E402
    MCPClientConfig,
    load_config,
)
from halbert_core.tools.executor import ToolExecutor  # noqa: E402
from halbert_core.tools.safety import ToolSafetyFramework  # noqa: E402
from test_mcp_client import FAKE_SERVER  # noqa: E402
from test_mcp_bridge import (  # noqa: E402
    FAKE_STDIO_SERVER,
    _mcp_tools,
    _tool_schema,
)


# ---------------------------------------------------------------------------
# Fixtures and doubles
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mcp_env(tmp_path, monkeypatch):
    """An isolated config dir (every test writes its own mcp_config.yml)
    plus a cleared config memo and monitor slot — no test inherits
    another's parsed config or a leaked monitor tick."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from halbert_core.mcp import config as config_mod
    from halbert_core.mcp import health as health_mod

    config_mod.reset_config_memo()
    yield
    # Belt: a test that failed mid-flight must not leave a live tick.
    # Tests stop their own monitors in finally blocks; this is the net.
    monitor = health_mod._ACTIVE
    if monitor is not None:
        task = monitor._task
        health_mod._ACTIVE = None
        if task is not None and not task.done():
            task.cancel()


def write_config(tmp_path, servers, risk=None):
    """Write mcp_config.yml. ``servers`` is a list of raw names; ``risk``
    optionally maps a name to a risk_override level."""
    entries = []
    for name in servers:
        entry = {"name": name, "transport": "stdio", "command": "x"}
        if risk and name in risk:
            entry["risk_override"] = risk[name]
        entries.append(entry)
    (tmp_path / "mcp_config.yml").write_text(yaml.safe_dump({"servers": entries}))


FS_TOOLS = [
    _tool_schema("read_file", "Read a file from disk",
                 properties={"path": {"type": "string"}},
                 required=["path"]),
    _tool_schema("delete_file", "Delete a file",
                 properties={"path": {"type": "string"}}),
]

CALC_TOOLS = [
    _tool_schema("add", "Add two numbers",
                 properties={"a": {"type": "integer"},
                             "b": {"type": "integer"}},
                 required=["a", "b"]),
]


class FakeClient:
    """Duck-typed MCPClient covering BOTH boundaries the monitor
    touches: the bridge's (connect / list_tools / connected_servers /
    call_tool — the discovery-refresh path) and its own (reconnect /
    ping / disconnect). ``tools`` is the per-server tools/list answer;
    ``_connected`` stands in for the client's live transports (removing
    a name is how a test fakes a crash — exactly what a real
    transport's ``alive`` flip looks like from outside).
    """

    def __init__(self, tools=None, fail_connect=(), fail_reconnect=(),
                 hung=(), ping_protocol_error=(), connected=None):
        self.tools = dict(tools or {})
        self.fail_connect = set(fail_connect)
        self.fail_reconnect = set(fail_reconnect)
        self.hung = set(hung)
        self.ping_protocol_error = set(ping_protocol_error)
        self._connected = (set(connected) if connected is not None
                           else set(self.tools) - self.fail_connect)
        self.reconnect_calls: list = []
        self.disconnect_calls: list = []
        self.connect_calls = 0

    # -- bridge boundary ---------------------------------------------------

    async def connect(self, server_name=None):
        self.connect_calls += 1
        names = ([server_name] if server_name is not None
                 else sorted(self.tools))
        for name in names:
            if name in self.fail_connect:
                self._connected.discard(name)
                continue
            self._connected.add(name)

    async def list_tools(self, server_name):
        if server_name not in self._connected:
            raise MCPConnectionError(
                f"MCP server '{server_name}': not connected")
        return list(self.tools.get(server_name, []))

    async def call_tool(self, server_name, tool_name, arguments=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    def connected_servers(self):
        return sorted(self._connected)

    # -- monitor boundary --------------------------------------------------

    async def reconnect(self, server_name):
        self.reconnect_calls.append(server_name)
        if server_name in self.fail_reconnect:
            self._connected.discard(server_name)
            raise MCPConnectionError(
                f"MCP server '{server_name}': failed to launch '/bin/false'")
        self._connected.add(server_name)

    async def ping(self, server_name):
        if server_name not in self._connected:
            raise MCPDisconnectedError(
                f"MCP server '{server_name}' is not connected")
        if server_name in self.ping_protocol_error:
            # A server that predates ping: an ANSWER, just an error one.
            raise MCPProtocolError(
                f"MCP server '{server_name}' rejected 'ping': "
                f"[-32601] Unknown method")
        if server_name in self.hung:
            # Bounded by the monitor's probe wait_for, not by this sleep.
            await asyncio.sleep(60)

    async def disconnect(self, server_name=None):
        self.disconnect_calls.append(server_name)
        if server_name is None:
            self._connected.clear()
        else:
            self._connected.discard(server_name)


class Clock:
    """A controllable ``time.monotonic`` stand-in: tests advance it
    instead of sleeping out the backoff."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_monitor(client, executor=None, **overrides):
    """A monitor with the test knobs wired: a patched clock (parked on
    the monitor as ``.clock`` so tests can advance time) and a short
    probe timeout unless a test asks otherwise."""
    from halbert_core.mcp.health import MCPHealthMonitor

    overrides.setdefault("probe_timeout", 0.1)
    monitor = MCPHealthMonitor(client, tool_executor=executor, **overrides)
    clock = Clock()
    monitor._now = clock
    monitor.clock = clock
    return monitor


async def sweep(monitor):
    """One sweep plus its reconnection attempts, settled."""
    await monitor.check_once()
    await monitor.drain()


def _health(monitor, name):
    record = monitor.health_record(name)
    assert record is not None
    return record


# =============================================================================
# The config memo (B4 charter: freshness without the double parse)
# =============================================================================

class TestConfigMemo:

    def test_same_identity_serves_the_cached_object(self, tmp_path):
        write_config(tmp_path, ["fs"])
        first = load_config()
        second = load_config()
        assert first is second

    def test_file_flip_is_seen_by_the_next_call(self, tmp_path):
        write_config(tmp_path, ["fs"])
        assert load_config().server("fs") is not None
        write_config(tmp_path, ["calc"])
        fresh = load_config()
        assert fresh.server("fs") is None
        assert fresh.server("calc") is not None

    def test_same_mtime_and_size_is_cached(self, tmp_path):
        """The identity, not the content, decides: content rewritten to
        the same byte size with the mtime PINNED to the old value serves
        the cached parse — and a real mtime change re-reads. (A pinned
        same-mtime rewrite is not a normal write; this test exists to
        prove the KEY is what the memo keys on, so nothing subtler —
        wall-clock time, a call counter — can leak in.)"""
        path = tmp_path / "mcp_config.yml"
        write_config(tmp_path, ["one"])
        first = load_config()
        old_stat = path.stat()
        # Rewrite to a different server of the SAME byte length, then
        # force the mtime back to the pinned value.
        write_config(tmp_path, ["two"])
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        assert path.stat().st_mtime_ns == old_stat.st_mtime_ns
        assert load_config() is first  # cached: identical identity
        assert load_config().server("one") is not None

        # A genuinely new mtime (any write) is a fresh read.
        os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1))
        fresh = load_config()
        assert fresh is not first
        assert fresh.server("two") is not None

    def test_corrupt_then_fixed_cycle(self, tmp_path, caplog):
        path = tmp_path / "mcp_config.yml"
        path.write_text("servers: [oops-not-a-list")
        first = load_config()
        assert first.load_error
        assert first.server("fs") is None
        # Memoized: the same broken file parses to the same cached object
        # (and the load warning fired once, not once per call).
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            second = load_config()
            load_config()
        assert second is first
        warnings = [r for r in caplog.records
                    if "failed to load" in r.message]
        assert len(warnings) == 1

        write_config(tmp_path, ["fs"])
        fixed = load_config()
        assert fixed.load_error == ""
        assert fixed.server("fs") is not None

    def test_missing_then_created_then_missing(self, tmp_path):
        missing = load_config()
        assert missing.load_error == "config file missing"
        assert load_config() is missing  # a missing file is memoizable

        write_config(tmp_path, ["fs"])
        assert load_config().server("fs") is not None

        (tmp_path / "mcp_config.yml").unlink()
        again = load_config()
        assert again.load_error == "config file missing"
        assert again is not missing  # identity (None) vs server-ful slot

    def test_distinct_config_paths_have_distinct_slots(
            self, tmp_path, monkeypatch):
        """Multi-instance: two config paths in one process must not
        serve each other's parse (the slot is keyed by path)."""
        write_config(tmp_path, ["fs"])
        first = load_config()
        other = tmp_path / "other"
        other.mkdir()
        with monkeypatch.context() as ctx:
            ctx.setenv("HALBERT_CONFIG_DIR", str(other))
            # A different path is a different slot: not the cached object.
            assert load_config() is not first
        assert load_config() is first


# =============================================================================
# client.ping (the probe the monitor rides on)
# =============================================================================

class TestClientPing:
    """Real MCPClient against the in-process fake stdio server."""

    def _fake_server_path(self, tmp_path):
        script = tmp_path / "fake_mcp_server.py"
        script.write_text(FAKE_SERVER)
        return str(script)

    async def test_ping_a_live_server(self, tmp_path):
        client = _real_client(self._fake_server_path(tmp_path), "normal")
        try:
            await client.ping("fakesrv")  # the spec's empty result
            assert client.connected_servers() == ["fakesrv"]
        finally:
            await client.disconnect()

    async def test_ping_a_server_that_predates_ping_is_still_an_answer(
            self, tmp_path):
        """The bridge fake answers unknown methods with a JSON-RPC
        error — an error object is an ANSWER over a live transport, so
        it surfaces as MCPProtocolError (the monitor's healthy case),
        not a timeout."""
        script = tmp_path / "bridge_fake_server.py"
        script.write_text(FAKE_STDIO_SERVER)
        client = _bridge_client(str(script))
        try:
            with pytest.raises(MCPProtocolError):
                await client.ping("fakesrv")
        finally:
            await client.disconnect()

    async def test_ping_a_crashed_server_is_not_connected(self, tmp_path):
        client = _real_client(self._fake_server_path(tmp_path), "crash")
        try:
            with pytest.raises(MCPClientError, match="not connected"):
                await client.ping("fakesrv")
        finally:
            await client.disconnect()

    async def test_ping_an_unconfigured_server(self, tmp_path):
        from halbert_core.mcp.client import MCPClient
        client = MCPClient(config_loader=MCPClientConfig)
        with pytest.raises(MCPClientError, match="not configured"):
            await client.ping("ghost")

    async def test_a_disconnected_servers_tool_call_is_a_clear_error(self):
        """The B4 acceptance phrase: an agent call to a disconnected
        server's tool returns a clear error naming it, not a hang and
        not a bare traceback."""
        from halbert_core.mcp.client import MCPClient
        from halbert_core.mcp.config import MCPServerConfig
        client = MCPClient(config_loader=lambda: MCPClientConfig(servers=[
            MCPServerConfig(name="filesystem", transport="stdio",
                            command="/nonexistent/definitely-not-here")]))
        with pytest.raises(MCPDisconnectedError) as excinfo:
            await client.call_tool("filesystem", "read_file", {"path": "/x"})
        message = str(excinfo.value)
        assert "MCP server 'filesystem' is not connected" in message
        # The transport's own (redacted) detail is preserved inside it.
        assert "definitely-not-here" in message


def _cfg(server_path, mode, timeout=3.0):
    from halbert_core.mcp.config import MCPServerConfig
    return MCPServerConfig(
        name="fakesrv", transport="stdio",
        command=sys.executable, args=[server_path],
        env={"FAKE_MODE": mode}, timeout_seconds=timeout)


def _real_client(server_path, mode, timeout=3.0):
    from halbert_core.mcp.client import MCPClient
    return MCPClient(config_loader=lambda: MCPClientConfig(
        servers=[_cfg(server_path, mode, timeout)]))


def _bridge_client(server_path, timeout=3.0):
    """A client pointed at the BRIDGE fake (FAKE_STDIO_SERVER), which
    answers unknown methods with a JSON-RPC error — the predates-ping
    shape."""
    from halbert_core.mcp.client import MCPClient
    from halbert_core.mcp.config import MCPServerConfig
    return MCPClient(config_loader=lambda: MCPClientConfig(servers=[
        MCPServerConfig(name="fakesrv", transport="stdio",
                        command=sys.executable, args=[server_path],
                        timeout_seconds=timeout)]))


# =============================================================================
# Detection
# =============================================================================

class TestDetection:

    async def test_connected_server_probes_healthy(self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        monitor = make_monitor(client)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.health == "healthy"
        assert record.connected is True
        assert record.last_error == ""

    async def test_crash_is_detected_within_the_tick(self, tmp_path):
        """A crash is the transport's ``alive`` flip — visible in
        connected_servers() with no request at all: detected at the very
        next sweep, and recovery is scheduled with it."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        monitor = make_monitor(client)
        await sweep(monitor)
        assert _health(monitor, "fs").health == "healthy"

        client._connected.discard("fs")  # the subprocess died
        await monitor.check_once()  # no drain yet: the record first
        record = _health(monitor, "fs")
        assert record.health == "down"
        assert record.connected is False
        assert record.last_error == ""  # nothing failed yet — it is just gone

        # The reconnect completes on the same schedule and recovery
        # lands healthy.
        await monitor.drain()
        record = _health(monitor, "fs")
        assert record.connected is True
        assert record.health == "healthy"

    async def test_unresponsive_ping_marks_unresponsive_then_recovers(
            self, tmp_path):
        """An alive-but-hung server needs a request to detect: the probe
        times out (bounded — the probe timeout, never a whole per-server
        timeout), the record says unresponsive, and the scheduled
        reconnect (kill + relaunch) recovers it."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS}, hung={"fs"})
        monitor = make_monitor(client, probe_timeout=0.05)
        await monitor.check_once()  # probe times out; reconnect scheduled
        record = _health(monitor, "fs")
        assert record.health == "unresponsive"
        assert record.connected is True
        await monitor.drain()
        record = _health(monitor, "fs")
        assert record.connected is True  # the relaunch re-established it
        assert record.health == "healthy"

    async def test_a_ping_error_answer_is_still_healthy(self, tmp_path):
        """A server that predates ping answers a JSON-RPC error — an
        error object is an answer over a live transport: HEALTHY."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            ping_protocol_error={"fs"})
        monitor = make_monitor(client)
        await sweep(monitor)
        assert _health(monitor, "fs").health == "healthy"

    async def test_a_server_down_at_start_is_down_with_a_record(
            self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        monitor = make_monitor(client)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.configured is True
        assert record.connected is False
        assert record.health == "down"
        assert "failed to launch" in record.last_error

    async def test_a_removed_server_is_recorded_unconfigured(self, tmp_path):
        """A live connection the current config no longer names: shown
        honestly as unconfigured (the client tears it down on its next
        call; the record keeps the dashboard honest in between)."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        monitor = make_monitor(client)
        await sweep(monitor)

        write_config(tmp_path, ["calc"])  # fs removed entirely
        client._connected.add("calc")  # still connected, not configured
        await sweep(monitor)
        # calc: connected, live, and CONFIGURED (the config names it now).
        record = _health(monitor, "calc")
        assert record.configured is True
        assert record.connected is True
        # And a server only ever KNOWN through the config that dropped it:
        # its record is kept, shown honestly as unconfigured (the client
        # tears it down on its next call; the monitor's refresh may have
        # already reconnected it, which the record also shows).
        fs_record = _health(monitor, "fs")
        assert fs_record.configured is False


# =============================================================================
# Backoff and reconnection
# =============================================================================

class TestBackoff:

    async def test_backoff_sequence_and_cap(self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        monitor = make_monitor(client, backoff_start=0.01, backoff_cap=0.04)
        clock = monitor.clock

        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.reconnect_attempts == 1
        assert record.backoff_seconds == pytest.approx(0.01)

        clock.advance(1.0)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.reconnect_attempts == 2
        assert record.backoff_seconds == pytest.approx(0.02)

        clock.advance(1.0)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.reconnect_attempts == 3
        assert record.backoff_seconds == pytest.approx(0.04)

        clock.advance(1.0)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.reconnect_attempts == 4
        assert record.backoff_seconds == pytest.approx(0.04)  # capped

    async def test_backoff_is_capped_not_storming(self, tmp_path):
        """A permanently-down server is retried at most once per backoff
        window: with a clock that never advances past the window, N
        sweeps produce ONE attempt. That is the cap that prevents a
        reconnection storm on a permanently-down server."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        monitor = make_monitor(client, backoff_start=100.0, backoff_cap=100.0)
        clock = monitor.clock

        for _ in range(6):
            await sweep(monitor)
        record = _health(monitor, "fs")
        assert client.reconnect_calls == ["fs"]  # exactly one attempt
        assert record.reconnect_attempts == 1

        # Past the (capped) window, exactly one more.
        clock.advance(150.0)
        for _ in range(6):
            await sweep(monitor)
        assert client.reconnect_calls == ["fs", "fs"]
        assert _health(monitor, "fs").reconnect_attempts == 2

    async def test_backoff_resets_on_success(self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        monitor = make_monitor(client, backoff_start=0.01, backoff_cap=0.04)
        clock = monitor.clock

        # Two failed attempts to build up a backoff…
        await sweep(monitor)
        clock.advance(1.0)
        await sweep(monitor)
        assert _health(monitor, "fs").reconnect_attempts == 2
        assert _health(monitor, "fs").backoff_seconds == pytest.approx(0.02)

        # …then the server comes back.
        client.fail_reconnect.clear()
        clock.advance(1.0)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.health == "healthy"
        assert record.reconnect_attempts == 0
        assert record.backoff_seconds is None
        assert record.last_error == ""

        # And the next failure starts the sequence over, not at ×2^2.
        client.fail_reconnect.add("fs")
        client._connected.discard("fs")
        clock.advance(1.0)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.reconnect_attempts == 1
        assert record.backoff_seconds == pytest.approx(0.01)

    async def test_the_record_carries_a_displayable_retry_schedule(
            self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        monitor = make_monitor(client)
        await sweep(monitor)
        record = _health(monitor, "fs")
        assert record.reconnect_attempts == 1
        assert record.next_retry_at > monitor.clock()
        # The status view derives a next_retry_in from it (a real-clock
        # derivation; with the patched clock this test asserts the stored
        # schedule above instead).


class TestReconnectionScheduling:

    async def test_one_reconnect_at_a_time_per_server(self, tmp_path):
        """A second sweep while the first reconnect is still in flight
        waits — it must not pile a second launch onto the same server."""
        write_config(tmp_path, ["fs"])

        class SlowReconnect(FakeClient):
            started = 0

            async def reconnect(self, server_name):
                type(self).started += 1
                await asyncio.sleep(0.05)
                await super().reconnect(server_name)

        client = SlowReconnect(tools={"fs": FS_TOOLS})
        client._connected.clear()
        monitor = make_monitor(client)
        await monitor.check_once()  # schedules the one reconnect
        await asyncio.sleep(0.02)  # let its first step begin the slow wait
        await monitor.check_once()  # must not schedule another
        assert len(monitor._reconnect_tasks) == 1
        assert client.started == 1
        await monitor.drain()
        assert _health(monitor, "fs").health == "healthy"


# =============================================================================
# Config-refresh re-registration (the piggybacked bridge)
# =============================================================================

class TestRefreshCadence:

    async def test_unchanged_config_costs_no_re_registration(self, tmp_path):
        """The refresh cadence is the mtime check: an unchanged config
        costs one stat per sweep, no second discovery."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        executor = ToolExecutor(web_search=False)
        registered = await discover_and_register(executor, client)
        assert registered == 2
        assert client.connect_calls == 1  # the initial discovery

        monitor = make_monitor(client, executor)  # baselines the identity
        await sweep(monitor)
        assert client.connect_calls == 1  # no piggybacked re-bridge
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

    async def test_config_edit_triggers_re_registration(self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        executor = ToolExecutor(web_search=False)
        await discover_and_register(executor, client)
        monitor = make_monitor(client, executor)

        write_config(tmp_path, ["fs", "calc"])
        client.tools["calc"] = CALC_TOOLS
        await sweep(monitor)
        assert client.connect_calls == 2
        assert _mcp_tools(executor) == [
            "mcp__calc__add", "mcp__fs__delete_file", "mcp__fs__read_file"]

    async def test_a_recovered_server_registers_its_tools(self, tmp_path):
        """A server down at init contributed no tools; its recovery is
        the moment to register them — no config edit, no restart."""
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        executor = ToolExecutor(web_search=False)
        await discover_and_register(executor, client)
        assert _mcp_tools(executor) == []  # down at init: no tools

        monitor = make_monitor(client, executor)
        await sweep(monitor)  # detects down, reconnects… and fails
        assert _health(monitor, "fs").health == "down"

        client.fail_connect.clear()
        client.fail_reconnect.clear()  # the server comes back
        monitor.clock.advance(10.0)  # past the armed backoff window
        await sweep(monitor)  # reconnect succeeds → flags the refresh…
        await sweep(monitor)  # …which piggybacks on the next sweep
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]


class TestColliderDisplacementClosed:
    """B3's disclosed residual: a colliding entry inserted BEFORE a
    fenced server displaces the fence at load, and tools registered
    from the displaced server classify under the surviving entry. The
    load-time check cannot close that — the monitor's refresh (re-bridge
    from CURRENT config) is what does."""

    async def _bridged_fenced_server(self, tmp_path):
        write_config(tmp_path, ["my-fs"], risk={"my-fs": "critical"})
        client = FakeClient(tools={"my-fs": FS_TOOLS})
        executor = ToolExecutor(web_search=False)
        await discover_and_register(executor, client)
        assert _mcp_tools(executor) == [
            "mcp__my_fs__delete_file", "mcp__my_fs__read_file"]
        # The fence: every tool from my-fs classifies CRITICAL.
        safety = ToolSafetyFramework()
        assert safety.classify(
            "mcp__my_fs__delete_file", {}).risk_level.value == "critical"
        return client, executor, safety

    async def test_displaced_fence_resolves_on_the_refresh(self, tmp_path):
        client, executor, safety = await self._bridged_fenced_server(tmp_path)
        monitor = make_monitor(client, executor)

        # The colliding entry is INSERTED BEFORE the fenced server: the
        # loader keeps "my_fs" (no override) and drops "my-fs" (critical).
        write_config(tmp_path, ["my_fs", "my-fs"], risk={"my-fs": "critical"})
        client.tools = {"my_fs": [FS_TOOLS[0]]}  # a different server's tools
        client._connected = {"my_fs"}

        await sweep(monitor)
        # The displaced server's tools are GONE — the surviving entry's
        # own tool list is what is registered now.
        assert _mcp_tools(executor) == ["mcp__my_fs__read_file"]
        # The fenced tool call is not silently MEDIUM any more: the tool
        # is gone (the executor refuses it before classification runs).
        result = await executor.execute(
            "mcp__my_fs__delete_file", {"path": "/x"})
        assert result.success is False
        # And the surviving entry's own tool classifies under ITS config —
        # the surviving entry's truth, not the displaced fence and not an
        # inherited override.
        assert safety.classify(
            "mcp__my_fs__read_file", {}).risk_level.value == "medium"

    async def test_the_closure_is_per_refresh_not_one_shot(self, tmp_path):
        """Flip the collision the OTHER way and the refreshed executor
        follows the config's surviving entry again — the mechanism, not
        hand-edited registration state, restores the fence."""
        client, executor, _safety = await self._bridged_fenced_server(tmp_path)
        monitor = make_monitor(client, executor)

        # Displace: my_fs first, my-fs dropped by the collision rule.
        write_config(tmp_path, ["my_fs", "my-fs"])
        client.tools = {"my_fs": [FS_TOOLS[0]]}
        client._connected = {"my_fs"}
        await sweep(monitor)
        assert _mcp_tools(executor) == ["mcp__my_fs__read_file"]

        # And back: my-fs first again — the fence is restored by the
        # same mechanism.
        write_config(tmp_path, ["my-fs"], risk={"my-fs": "critical"})
        client.tools = {"my-fs": FS_TOOLS}
        client._connected = {"my-fs"}
        await sweep(monitor)
        assert _mcp_tools(executor) == [
            "mcp__my_fs__delete_file", "mcp__my_fs__read_file"]
        safety = ToolSafetyFramework()
        check = safety.classify("mcp__my_fs__delete_file", {})
        assert check.risk_level.value == "critical"
        assert check.allowed is False


# =============================================================================
# The stale-drop ordering fix (B2 residual, bridge-level)
# =============================================================================

class TestStaleDropOrdering:

    async def test_a_failed_connect_keeps_the_prior_tools(self, tmp_path):
        """THE residual: the old drop ran before connect(), so a
        re-registration whose connect failed totally left ZERO MCP
        tools. Now: configured-but-down keeps the working set."""
        write_config(tmp_path, ["fs", "calc"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS, "calc": CALC_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__calc__add", "mcp__fs__delete_file", "mcp__fs__read_file"]

        # Refresh with calc DOWN (config unchanged — both still configured).
        down_client = FakeClient(
            tools={"fs": FS_TOOLS, "calc": CALC_TOOLS},
            fail_connect={"calc"})
        await discover_and_register(executor, down_client)
        assert _mcp_tools(executor) == [
            "mcp__calc__add", "mcp__fs__delete_file", "mcp__fs__read_file"]

    async def test_a_removed_servers_tools_are_still_dropped(self, tmp_path):
        write_config(tmp_path, ["fs", "calc"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS, "calc": CALC_TOOLS}))

        write_config(tmp_path, ["fs"])
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

    async def test_a_shrunken_tool_list_leaves_no_stale_names(
            self, tmp_path):
        write_config(tmp_path, ["fs"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))

        slim = FakeClient(tools={"fs": [FS_TOOLS[0]]})
        await discover_and_register(executor, slim)
        assert _mcp_tools(executor) == ["mcp__fs__read_file"]

    async def test_a_failed_tools_list_keeps_the_prior_tools(
            self, tmp_path):
        """Same rule at the next seam down: a server that connected but
        whose tools/list failed KEEPS its previous registrations."""
        write_config(tmp_path, ["fs"])

        class ListBroken(FakeClient):
            async def list_tools(self, server_name):
                raise MCPConnectionError("went away mid-list")

        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))
        await discover_and_register(
            executor, ListBroken(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

    async def test_an_unreadable_config_keeps_everything(self, tmp_path,
                                                         monkeypatch):
        """A config the diff cannot read leaves the bridge blind: drop
        NOTHING (a mis-timed drop must not amplify a read failure into
        a tool loss; the classifier's fail-closed path gates staleness)."""
        from halbert_core.mcp import config as config_mod

        write_config(tmp_path, ["fs"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))

        def _boom():
            raise RuntimeError("config exploded")

        monkeypatch.setattr(config_mod, "load_config", _boom)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

    @pytest.mark.parametrize("raw", [
        "servers: [oops-not-yaml",      # unparseable YAML
        "just_a_string",                # not a mapping
        "servers: 42",                  # 'servers' is not a list
    ])
    async def test_a_real_corrupt_config_keeps_everything(
            self, tmp_path, raw):
        """The NON-RAISING corrupt shapes — what load_config actually
        returns for a file that exists but cannot be read (it degrades to
        a load_error, never raises). Every such shape leaves the diff
        blind: the tools are KEPT, not dropped."""
        from halbert_core.mcp import config as config_mod

        write_config(tmp_path, ["fs"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

        (tmp_path / "mcp_config.yml").write_text(raw)
        config_mod.reset_config_memo()
        assert load_config().load_error  # genuinely unreadable

        # The refresh runs (the file identity changed) — and drops nothing.
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

    async def test_a_missing_config_drops_everything(self, tmp_path):
        """The OPPOSITE shape: a MISSING file is a legitimate removal —
        every server is gone, so the diff proceeds with the empty list
        and the tools are dropped (the opposite side of "unparseable")."""
        write_config(tmp_path, ["fs"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]

        (tmp_path / "mcp_config.yml").unlink()
        # A real client tears down the removed server at its next call
        # (_ensure: "not configured") and connects nothing — the fake
        # mirrors that by having nothing connected.
        # (tools is empty too: the real client connects only what the
        # config names, and the config now names nothing.)
        down_client = FakeClient(tools={}, connected=set())
        await discover_and_register(executor, down_client)
        assert _mcp_tools(executor) == []

    async def test_a_total_connect_failure_keeps_everything(self, tmp_path):
        write_config(tmp_path, ["fs"])
        executor = ToolExecutor(web_search=False)
        await discover_and_register(
            executor, FakeClient(tools={"fs": FS_TOOLS}))

        class ExplodingConnect(FakeClient):
            async def connect(self, server_name=None):
                raise RuntimeError("not even an MCPClientError")

        await discover_and_register(executor, ExplodingConnect())
        assert _mcp_tools(executor) == [
            "mcp__fs__delete_file", "mcp__fs__read_file"]


# =============================================================================
# Lifecycle: start/stop, supersession, shutdown
# =============================================================================

class TestLifecycle:

    def test_start_without_a_loop_is_dormant(self):
        from halbert_core.mcp.health import start_mcp_health_monitor
        monitor = start_mcp_health_monitor(FakeClient())
        assert monitor is not None
        assert monitor.running is False

    async def test_start_and_stop_cleanly(self):
        from halbert_core.mcp.health import start_mcp_health_monitor
        client = FakeClient(tools={"fs": FS_TOOLS})
        monitor = start_mcp_health_monitor(client)
        assert monitor.running is True
        await monitor.stop()
        assert monitor.running is False
        assert monitor._task is None
        assert monitor._reconnect_tasks == {}
        assert client.disconnect_calls == [None]  # subprocesses reaped
        # No leaked task on this loop.
        leftover = [t for t in asyncio.all_tasks()
                    if "mcp-health" in (t.get_name() or "")]
        assert leftover == []

    async def test_stop_is_idempotent_and_tolerates_no_active(self):
        from halbert_core.mcp.health import stop_mcp_health_monitor
        await stop_mcp_health_monitor()  # nothing active: a no-op

        monitor = make_monitor(FakeClient())
        monitor.start()
        await monitor.stop()
        await monitor.stop()  # second stop: a no-op
        assert monitor.running is False

    async def test_supersession_stops_the_previous_monitor(self):
        from halbert_core.mcp import health as health_mod
        from halbert_core.mcp.health import (
            get_active_monitor, start_mcp_health_monitor,
            stop_mcp_health_monitor,
        )

        first_client = FakeClient(tools={"fs": FS_TOOLS})
        first = start_mcp_health_monitor(first_client)
        assert first.running is True

        second = start_mcp_health_monitor(FakeClient())
        assert get_active_monitor() is second
        # The supersede-stop is scheduled on this loop: let it land.
        for task in list(health_mod._PENDING_STOPS):
            await task
        assert first.running is False
        assert first_client.disconnect_calls == [None]
        assert second.running is True
        await stop_mcp_health_monitor()
        assert second.running is False

    async def test_stop_mcp_health_monitor_stops_the_active_one(self):
        from halbert_core.mcp import health as health_mod
        from halbert_core.mcp.health import (
            get_active_monitor, start_mcp_health_monitor,
            stop_mcp_health_monitor,
        )

        client = FakeClient(tools={"fs": FS_TOOLS})
        start_mcp_health_monitor(client)
        monitor = get_active_monitor()
        assert monitor is not None
        await stop_mcp_health_monitor()
        assert monitor.running is False
        assert client.disconnect_calls == [None]
        assert health_mod.get_active_monitor() is None

    async def test_agent_init_starts_the_monitor(
            self, monkeypatch, capability_registry):
        """The agent-init wiring: capability on → a monitor exists for
        the client this init created (and it starts on the running
        loop)."""
        from halbert_core.mcp import health as health_mod
        from halbert_core.dashboard.routes import agent as agent_routes

        capability_registry.set_capability("mcp_client", True)
        monkeypatch.setattr(agent_routes, "_agent_instance", None)
        monkeypatch.setattr(agent_routes, "_get_llm_client",
                            lambda: MagicMock())
        monkeypatch.setattr(
            "halbert_core.integrations.cognition_wiring.get_cognition_tick",
            lambda: None)
        monkeypatch.setattr(
            "halbert_core.integrations.cognition_wiring.get_event_mapper",
            lambda: None)
        fake_client = FakeClient(tools={"fs": FS_TOOLS})
        monkeypatch.setattr(
            "halbert_core.mcp.client.MCPClient", lambda: fake_client)

        try:
            agent = agent_routes.get_agent()
            # Let the scheduled discovery land (it completes a tick later
            # in production; here, before the asserts).
            await asyncio.sleep(0)
            monitor = health_mod.get_active_monitor()
            assert monitor is not None
            assert monitor.running is True
            assert monitor._client is fake_client
            assert agent is not None
        finally:
            await health_mod.stop_mcp_health_monitor()
            monkeypatch.setattr(agent_routes, "_agent_instance", None)

    async def test_agent_init_failure_leaves_no_monitor(
            self, monkeypatch, capability_registry):
        from halbert_core.mcp import health as health_mod
        from halbert_core.dashboard.routes import agent as agent_routes

        capability_registry.set_capability("mcp_client", True)
        monkeypatch.setattr(agent_routes, "_agent_instance", None)
        monkeypatch.setattr(agent_routes, "_get_llm_client",
                            lambda: MagicMock())
        monkeypatch.setattr(
            "halbert_core.integrations.cognition_wiring.get_cognition_tick",
            lambda: None)
        monkeypatch.setattr(
            "halbert_core.integrations.cognition_wiring.get_event_mapper",
            lambda: None)

        def _boom():
            raise RuntimeError("MCP blew up during init")

        monkeypatch.setattr("halbert_core.mcp.client.MCPClient", _boom)
        agent = agent_routes.get_agent()  # must not raise
        try:
            assert agent is not None
            assert health_mod.get_active_monitor() is None
        finally:
            monkeypatch.setattr(agent_routes, "_agent_instance", None)


# =============================================================================
# The /api/mcp/status endpoint
# =============================================================================

@pytest.fixture
def status_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.routes.mcp import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestStatusEndpoint:

    def test_capability_off_is_an_honest_empty_state(
            self, status_client, capability_registry):
        capability_registry.set_capability("mcp_client", False)
        r = status_client.get("/api/mcp/status")
        assert r.status_code == 200
        payload = r.json()
        assert payload["enabled"] is False
        assert payload["servers"] == []

    def test_capability_on_without_a_monitor_serves_config_rows(
            self, tmp_path, status_client, capability_registry):
        capability_registry.set_capability("mcp_client", True)
        write_config(tmp_path, ["fs"], risk={"fs": "high"})
        r = status_client.get("/api/mcp/status")
        assert r.status_code == 200
        payload = r.json()
        assert payload["enabled"] is True
        assert payload["monitor_running"] is False
        assert payload["skipped_servers"] == []
        assert payload["load_error"] == ""
        [row] = payload["servers"]
        assert row["name"] == "fs"
        assert row["configured"] is True
        assert row["connected"] is False
        assert row["health"] == "unknown"  # never probed
        assert row["tool_count"] is None
        assert row["risk_override"] == "high"
        assert row["transport"] == "stdio"

    async def test_monitor_rows_reflect_health_and_tool_counts(self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        executor = ToolExecutor(web_search=False)
        from halbert_core.mcp import health as health_mod
        from halbert_core.mcp.bridge import discover_and_register
        from halbert_core.dashboard.routes.mcp import mcp_status

        await discover_and_register(executor, client)
        monitor = health_mod.start_mcp_health_monitor(
            client, tool_executor=executor)
        try:
            await monitor.check_once()
            payload = await mcp_status()
            assert payload["enabled"] is True
            assert payload["monitor_running"] is True
            [row] = payload["servers"]
            assert row["connected"] is True
            assert row["health"] == "healthy"
            assert row["tool_count"] == 2
            assert row["reconnect_attempts"] == 0
            assert row["last_error"] == ""
            assert row["risk_override"] is None
        finally:
            await health_mod.stop_mcp_health_monitor()

    async def test_a_down_server_shows_its_backoff(self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS},
                            fail_connect={"fs"}, fail_reconnect={"fs"})
        from halbert_core.mcp import health as health_mod
        from halbert_core.dashboard.routes.mcp import mcp_status

        monitor = health_mod.start_mcp_health_monitor(
            client, backoff_start=0.01, backoff_cap=0.5)
        try:
            await monitor.check_once()
            await monitor.drain()
            payload = await mcp_status()
            [row] = payload["servers"]
            assert row["connected"] is False
            assert row["health"] == "down"
            assert row["reconnect_attempts"] == 1
            assert row["backoff_seconds"] == pytest.approx(0.01)
            assert "failed to launch" in row["last_error"]
        finally:
            await health_mod.stop_mcp_health_monitor()

    async def test_last_error_is_redacted(
            self, tmp_path, monkeypatch):
        """last_error is config-written-adjacent text interpolated into a
        dashboard payload: it passes the config module's redactor."""
        from halbert_core.mcp import health as health_mod
        from halbert_core.dashboard.routes.mcp import mcp_status

        write_config(tmp_path, ["fs"])

        class LeakyReconnect(FakeClient):
            async def reconnect(self, server_name):
                raise MCPConnectionError(
                    f"MCP server '{server_name}': failed to launch "
                    f"'npx --token=hunter2'")

        client = LeakyReconnect(tools={"fs": FS_TOOLS})
        client._connected.discard("fs")
        monitor = health_mod.start_mcp_health_monitor(client)
        monkeypatch.setattr(health_mod, "redact",
                            lambda text: str(text).replace("hunter2",
                                                           "<redacted>"))
        try:
            await monitor.check_once()
            await monitor.drain()
            payload = await mcp_status()
            [row] = payload["servers"]
            assert "hunter2" not in row["last_error"]
            assert "<redacted>" in row["last_error"]
        finally:
            await health_mod.stop_mcp_health_monitor()

    async def test_a_monitor_known_but_unconfigured_server_is_shown(
            self, tmp_path):
        write_config(tmp_path, ["fs"])
        client = FakeClient(tools={"fs": FS_TOOLS})
        executor = ToolExecutor(web_search=False)
        from halbert_core.mcp import health as health_mod
        from halbert_core.dashboard.routes.mcp import mcp_status

        monitor = health_mod.start_mcp_health_monitor(
            client, tool_executor=executor)
        try:
            await sweep(monitor)
            write_config(tmp_path, ["calc"])  # fs removed entirely
            client._connected.add("calc")
            await sweep(monitor)
            payload = await mcp_status()
            by_name = {row["name"]: row for row in payload["servers"]}
            assert by_name["fs"]["configured"] is False
            assert by_name["calc"]["configured"] is True
        finally:
            await health_mod.stop_mcp_health_monitor()


# =============================================================================
# Real-client integration (the fake stdio server from test_mcp_client)
# =============================================================================

class TestRealClientIntegration:

    def _fake_server_path(self, tmp_path):
        script = tmp_path / "fake_mcp_server.py"
        script.write_text(FAKE_SERVER)
        return str(script)

    async def test_crash_detected_and_recovered(self, tmp_path):
        """The full B4 cycle against real machinery: connect → probe
        healthy → crash the subprocess → detected within a sweep →
        reconnect (relaunch) → healthy again, tools intact, and a call
        through the executor works after the recovery."""
        from halbert_core.mcp.health import MCPHealthMonitor

        write_config(tmp_path, ["fakesrv"])  # the monitor sweeps by config
        client = _real_client(self._fake_server_path(tmp_path), "normal")
        executor = ToolExecutor(web_search=False)
        try:
            await discover_and_register(executor, client)
            assert _mcp_tools(executor) == [
                "mcp__fakesrv__add", "mcp__fakesrv__echo"]

            monitor = MCPHealthMonitor(
                client, tool_executor=executor,
                interval=0.01, backoff_start=0.01, backoff_cap=0.05,
                probe_timeout=1.0)
            clock = Clock()
            monitor._now = clock
            await sweep(monitor)
            record = monitor.health_record("fakesrv")
            assert record.health == "healthy"
            assert record.connected is True

            # CRASH: kill the subprocess the way a server crash happens.
            transport = client._connections["fakesrv"].transport
            transport._proc.kill()
            await transport._proc.wait()

            await monitor.check_once()  # detected, reconnect scheduled
            record = monitor.health_record("fakesrv")
            assert record.connected is False
            assert record.health == "down"

            # The reconnect machinery recovers it (the fake relaunches).
            await monitor.drain()
            record = monitor.health_record("fakesrv")
            assert record.connected is True
            assert record.health == "healthy"
            assert _mcp_tools(executor) == [
                "mcp__fakesrv__add", "mcp__fakesrv__echo"]
            result = await executor.execute(
                "mcp__fakesrv__echo", {"text": "hello"})
            assert result.success is True
            assert result.result == '{"text": "hello"}'
        finally:
            await client.disconnect()

    async def test_a_permanently_crashing_server_arms_the_backoff(
            self, tmp_path):
        """FAKE_MODE=crash: the process exits before the handshake, so
        every reconnect fails — the record shows the backoff growing,
        never a launch storm."""
        from halbert_core.mcp.health import MCPHealthMonitor

        write_config(tmp_path, ["fakesrv"])  # the monitor sweeps by config
        client = _real_client(self._fake_server_path(tmp_path), "crash")
        try:
            monitor = MCPHealthMonitor(
                client, interval=0.01,
                backoff_start=0.01, backoff_cap=0.03, probe_timeout=0.5)
            clock = Clock()
            monitor._now = clock
            await sweep(monitor)
            record = monitor.health_record("fakesrv")
            assert record.health == "down"
            assert record.reconnect_attempts == 1
            assert record.backoff_seconds == pytest.approx(0.01)
            assert "not connected" in record.last_error

            clock.advance(1.0)
            await sweep(monitor)
            record = monitor.health_record("fakesrv")
            assert record.reconnect_attempts == 2
            assert record.backoff_seconds == pytest.approx(0.02)

            clock.advance(1.0)
            await sweep(monitor)
            record = monitor.health_record("fakesrv")
            assert record.reconnect_attempts == 3
            assert record.backoff_seconds == pytest.approx(0.03)  # capped
        finally:
            await client.disconnect()

    async def test_a_hung_server_is_detected_unresponsive(self, tmp_path):
        """hang_after: handshakes (the transport reads alive), then never
        answers — only a request can detect it. The probe timeout bounds
        the detection; the reconnect relaunch recovers the transport."""
        from halbert_core.mcp.health import MCPHealthMonitor

        write_config(tmp_path, ["fakesrv"])  # the monitor sweeps by config
        client = _real_client(self._fake_server_path(tmp_path),
                              "hang_after", timeout=2.0)
        try:
            await client.connect()
            assert client.connected_servers() == ["fakesrv"]

            monitor = MCPHealthMonitor(
                client, interval=0.01,
                backoff_start=0.01, backoff_cap=0.5, probe_timeout=0.3)
            clock = Clock()
            monitor._now = clock
            await monitor.check_once()  # ping: no answer in 0.3 s
            record = monitor.health_record("fakesrv")
            assert record.health == "unresponsive"
            assert record.connected is True

            # The scheduled reconnect (kill + relaunch) re-establishes a
            # transport whose handshake answers.
            await monitor.drain()
            record = monitor.health_record("fakesrv")
            assert record.connected is True
            assert record.health == "healthy"
        finally:
            await client.disconnect()

    async def test_config_refresh_re_registration_mid_process(self, tmp_path):
        """A config edit is picked up by the refresh within one sweep:
        a server added to the config shows up with tools, no restart."""
        from halbert_core.mcp.client import MCPClient
        from halbert_core.mcp.health import MCPHealthMonitor

        server_path = self._fake_server_path(tmp_path)
        config_path = tmp_path / "mcp_config.yml"

        def write_real_config(names):
            entries = [
                {"name": name, "transport": "stdio",
                 "command": sys.executable, "args": [server_path],
                 "env": {"FAKE_MODE": "limited"}}
                for name in names]
            config_path.write_text(yaml.safe_dump({"servers": entries}))

        write_real_config(["fakesrv"])
        client = MCPClient(config_loader=load_config)
        executor = ToolExecutor(web_search=False)
        try:
            await discover_and_register(executor, client)
            assert _mcp_tools(executor) == ["mcp__fakesrv__echo"]

            monitor = MCPHealthMonitor(
                client, tool_executor=executor,
                interval=0.01, probe_timeout=1.0)
            clock = Clock()
            monitor._now = clock
            await sweep(monitor)
            assert _mcp_tools(executor) == ["mcp__fakesrv__echo"]

            # A second server joins the config (same fake script).
            write_real_config(["fakesrv", "fakesrv2"])
            await sweep(monitor)
            assert "mcp__fakesrv2__echo" in _mcp_tools(executor)
            assert monitor.tool_count("fakesrv2") == 1
        finally:
            await client.disconnect()


# =============================================================================
# The status route is mounted on the real app (B5's door exists)
# =============================================================================

def test_route_is_mounted_on_the_real_app():
    """The B4 endpoint is registered through mount_api like every other
    router — which is also what keeps it behind the dashboard's auth.

    (The walked path carries no /api prefix: this FastAPI keeps include-
    time prefixes out of ``route.path`` — the census's shape — and the
    /api prefix lives on the mount, so the served URL is /api/mcp/status
    while the walked leaf is /mcp/status, exactly like /api/devices.)"""
    from halbert_core.dashboard.app import create_app, SPA_ROUTES

    app = create_app()
    # This FastAPI does not flatten an included router into app.routes:
    # it appends an _IncludedRouter wrapper (the census's lesson). Walk it.
    stack = list(app.routes)
    paths = set()
    while stack:
        route = stack.pop()
        if type(route).__name__ == "_IncludedRouter":
            original = getattr(route, "original_router", None)
            if original is not None:
                stack.extend(original.routes)
            continue
        children = getattr(route, "routes", None)
        if children and not isinstance(children, (str, bytes)):
            stack.extend(children)
            continue
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    assert "/mcp/status" in paths
    # And it is not on the public allowlist: it sits behind the door.
    assert "/mcp/status" not in (set(SPA_ROUTES) if SPA_ROUTES else set())