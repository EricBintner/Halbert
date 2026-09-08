# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP server health monitoring (Workstream B4).

A crashed stdio server or a dropped HTTP connection should be detected
and recovered without agent intervention. B1's client already recovers
on demand (a call to a dead server relaunches it); this monitor makes
that PROACTIVE, and adds the two things on-demand recovery cannot do:

  * periodic detection — every :data:`DEFAULT_INTERVAL_SECONDS` a sweep
    checks each configured server (the MCP-native ``ping`` for a live
    transport, the transport ``alive`` flag for a crashed one) and
    records the answer for the dashboard;
  * backoff-capped reconnection — a down server is retried on an
    exponential schedule (start 5 s, ×2, CAP 5 min), so a permanently
    down server costs one bounded attempt per backoff window, never a
    reconnection storm. The counter resets on the first success.

Lifecycle: one monitor per process, started where the MCP client is
created (``dashboard/routes/agent.py``, inside the CAP_MCP_CLIENT gate
— the mcp package stays unimported when the capability is off). The
monitor is an asyncio task on the SAME loop the handlers run on (the
bridge's loop rule — an ``MCPClient``'s locks and subprocess readers
must never cross loops); a sync context starts no task at all.
``start_mcp_health_monitor`` SUPERSEDES any previous monitor (agent
re-init must not leak the old tick), and ``stop_mcp_health_monitor``
is wired into the dashboard's shutdown event next to the thread-tick
heartbeat — it cancels the sweep, cancels in-flight reconnects and
disconnects the client (reaping its stdio subprocesses).

Probe mechanics, honestly bounded:

  * a crashed stdio process shows in ``connected_servers()`` (the
    transport's ``alive`` is false) — detected at the very next tick,
    which is the "within 30 seconds" acceptance;
  * an alive-but-hung server needs a request: ``client.ping`` wrapped
    in a :data:`DEFAULT_PROBE_TIMEOUT` wait. Timing out the wait does
    NOT cancel an HTTP POST's worker thread (B1 note) — the
    ``requests`` timeout still bounds it; the monitor only treats the
    timeout as the answer it needs ("unresponsive") and never assumes
    the thread died;
  * a server that answers ping with a JSON-RPC error (a server that
    predates ping) is still HEALTHY — an error object is an answer
    over a live transport, which is the thing being probed;
  * stderr is deliberately still DEVNULL'd (B1): capturing it would
    buy log text at the price of the undrained-pipe hazard DEVNULL
    exists to avoid. Not taken.

Reconnection goes through the client's existing machinery
(``reconnect`` = disconnect + rebuild from CURRENT config), so the
monitor adds no connection logic of its own — it schedules what B1
already knows how to do, on a backoff. A reconnect that "succeeds" has
answered the initialize handshake, which IS a probe: the record goes
healthy immediately, and the next tick's ping confirms.

Config-refresh re-registration (the B3 residual closures): each sweep
cheaply stats ``mcp_config.yml``; when its file identity changed (the
same identity the config memo keys on), the monitor re-runs the
bridge's discovery/registration from CURRENT config — that is what
closes the collider-displacement residual (a colliding entry inserted
ahead of a fenced server no longer leaves the displaced server's tools
registered under the surviving entry: the refresh drops every
registration whose server the current config does not carry). A
RECOVERED server also triggers one refresh (its tools may never have
been registered if it was down at init). No unconditional periodic
re-registration: the mtime check is the cadence, so an unchanged
config costs one stat per tick.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .client import MCPClientError, MCPProtocolError
from .config import load_config, redact

logger = logging.getLogger("halbert.mcp.health")

#: Health tick cadence. The plan's number; tests pass a smaller one.
DEFAULT_INTERVAL_SECONDS = 30.0

#: Reconnection backoff: first retry 5 s after the first failure, then
#: ×2 each further failure, capped so a permanently-down server is
#: retried at most every 5 minutes — a reconnection storm is a crashed
#: server's worst side effect on the machine (plan risk note).
DEFAULT_BACKOFF_START_SECONDS = 5.0
DEFAULT_BACKOFF_CAP_SECONDS = 300.0

#: How long a ping may take before the server counts as unresponsive.
#: Deliberately shorter than a full per-server timeout (30 s default):
#: detection latency is interval + probe, and crash-free hung servers
#: should not add a whole per-server timeout to the sweep.
DEFAULT_PROBE_TIMEOUT_SECONDS = 10.0

#: Health states (the strings the status endpoint serves).
HEALTHY = "healthy"
UNRESPONSIVE = "unresponsive"
DOWN = "down"
UNKNOWN = "unknown"


@dataclass
class ServerHealth:
    """One server's health record, as the dashboard consumes it.

    ``health`` is the last probe's verdict; ``last_error`` is the
    redacted failure detail; the backoff fields describe the
    reconnection schedule (``next_retry_at`` is a ``time.monotonic``
    stamp — ``next_retry_in`` is derived for display, never stored).
    """
    name: str
    configured: bool = False
    connected: bool = False
    health: str = UNKNOWN
    last_error: str = ""
    last_probe_at: Optional[float] = None       # wall clock, display only
    reconnect_attempts: int = 0
    backoff_seconds: Optional[float] = None     # the delay now in force
    next_retry_at: float = 0.0                  # time.monotonic() timeline

    def as_dict(self) -> Dict[str, Any]:
        """The endpoint-facing view of this record (a copy — the record
        is the monitor's live state)."""
        retry_in = self.next_retry_at - time.monotonic()
        return {
            "connected": self.connected,
            "health": self.health,
            "last_error": self.last_error,
            "last_probe_at": self.last_probe_at,
            "reconnect_attempts": self.reconnect_attempts,
            "backoff_seconds": self.backoff_seconds,
            "next_retry_in": round(retry_in, 3) if retry_in > 0 else None,
        }


class MCPHealthMonitor:
    """Periodic health sweep + backoff-capped reconnection for one
    MCPClient, with a config-refresh re-registration piggyback."""

    def __init__(
        self,
        client,
        tool_executor=None,
        *,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        backoff_start: float = DEFAULT_BACKOFF_START_SECONDS,
        backoff_cap: float = DEFAULT_BACKOFF_CAP_SECONDS,
        probe_timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    ) -> None:
        if interval <= 0:
            raise ValueError("MCP health monitor interval must be positive")
        if backoff_start <= 0 or backoff_cap < backoff_start:
            raise ValueError(
                "MCP health monitor backoff needs 0 < start <= cap")
        self._client = client
        self._tool_executor = tool_executor
        self.interval = float(interval)
        self._backoff_start = float(backoff_start)
        self._backoff_cap = float(backoff_cap)
        self._probe_timeout = float(probe_timeout)
        self._health: Dict[str, ServerHealth] = {}
        #: The tick's wake signal. stop() SETS this instead of relying on
        #: task cancellation alone: on 3.10, a cancel() that lands exactly
        #: as the probe's ``wait_for`` completes can be swallowed by the
        #: wait_for race (the outer CancelledError is eaten and the task
        #: carries on), which would leave ``stop()`` awaiting a task that
        #: never dies. An event set BEFORE the task's next wait completes
        #: without any race — the flag check at the loop top is the
        #: guarantee cancellation only supplements.
        self._wake: asyncio.Event = asyncio.Event()
        self._task: Optional["asyncio.Task"] = None
        self._reconnect_tasks: Dict[str, "asyncio.Task"] = {}
        #: The config file identity at monitor start — the baseline the
        #: per-tick refresh check diffs against (None means "no file").
        self._last_config_identity: tuple = self._config_identity()
        self._needs_refresh = False
        self._stopping = False

    # -- clock (tests patch _now to drive backoff without sleeping) ----

    def _now(self) -> float:
        return time.monotonic()

    def _config_identity(self) -> tuple:
        """The config file's stat identity — the same shape the config
        memo keys on, so the refresh cadence and the memo always agree
        about what "the file changed" means."""
        from .config import _config_identity, config_path
        return _config_identity(config_path())

    def _record(self, name: str) -> ServerHealth:
        record = self._health.get(name)
        if record is None:
            record = ServerHealth(name=name)
            self._health[name] = record
        return record

    def health_record(self, name: str) -> Optional[ServerHealth]:
        """One server's live record (or None — never probed). The
        endpoint treats it as read-only."""
        return self._health.get(name)

    def known_servers(self) -> List[str]:
        """Every server this monitor has any state for."""
        return sorted(self._health)

    def tool_count(self, server_name: str) -> Optional[int]:
        """How many ``mcp__`` tools this server has REGISTERED on the
        executor, live at call time — what the dashboard wants, not a
        cached count. None when the monitor has no executor (a monitor
        started for status-only)."""
        if self._tool_executor is None:
            return None
        from .registry import parse_qualified_tool_name, sanitize_component
        component = sanitize_component(server_name).lower()
        count = 0
        for name in self._tool_executor.tools:
            parsed = parse_qualified_tool_name(name)
            if parsed is not None and parsed[0].lower() == component:
                count += 1
        return count

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> Optional["asyncio.Task"]:
        """Start the sweep task on the running loop (or do nothing —
        cleanly — when there is none: a sync context has no loop to
        park a task on, and the agent-init caller may be sync)."""
        if self.running:
            return self._task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        self._stopping = False
        self._task = loop.create_task(
            self._run(), name="mcp-health-monitor")
        return self._task

    async def _run(self) -> None:
        while not self._stopping:
            await self.check_once()
            if self._stopping:
                return
            # The wake event, not a bare sleep: stop() sets it, so the
            # tick exits promptly even where cancellation delivery is
            # swallowed (see the attribute comment above).
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(),
                                       timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        """Cancel the sweep and every in-flight reconnect, then
        disconnect the client (reaping its stdio subprocesses). Never
        raises; idempotent; safe against a task whose loop already
        closed (a superseded monitor from a torn-down test loop)."""
        self._stopping = True
        self._wake.set()
        task, self._task = self._task, None
        if task is not None and not task.get_loop().is_closed():
            task.cancel()
            # Bounded: the wake event is the primary stop signal (the task
            # exits at its next loop-top flag check); cancellation only
            # interrupts an in-flight sweep faster. Neither is awaited
            # unboundedly — a stop must never hang the shutdown.
            bound = self._probe_timeout + 5.0
            pending = await asyncio.wait({task}, timeout=bound)
            if task in pending:
                # The bound is not sweep-aware: an in-flight multi-server
                # discovery sweep can outlive it. stop() still returns —
                # the task exits at its next loop-top flag check (residual
                # task lifetime, not a hang).
                logger.warning(
                    "MCP health monitor did not stop within %ss; leaving "
                    "it to its loop", bound)
        reconnects = list(self._reconnect_tasks.values())
        self._reconnect_tasks.clear()
        for task in reconnects:
            if not task.get_loop().is_closed():
                task.cancel()
        live = [t for t in reconnects if not t.get_loop().is_closed()]
        if live:
            await asyncio.wait(live, timeout=self._probe_timeout + 5.0)
        try:
            await self._client.disconnect()
        except Exception as e:
            logger.debug(
                "MCP client disconnect during monitor stop failed: %s", e)

    # -- the sweep ---------------------------------------------------------

    async def check_once(self) -> None:
        """One health sweep. Never raises — a broken client, an
        unreadable config, or a garbage probe costs the sweep nothing
        but a log line; the loop carries on (the heartbeat pattern)."""
        try:
            await self._check_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("MCP health check failed (non-fatal): %s", e)

    async def _check_once(self) -> None:
        try:
            config = load_config()
            configured = [s.name for s in config.servers]
        except Exception as e:
            # load_config never raises by design; the defensive net keeps
            # a sweep from dying on the unexpected. The previous records
            # stand: a probe that cannot know the config must not wipe
            # the dashboard's view of it.
            logger.warning(
                "MCP health check: config unreadable (%s); records stand", e)
            config = None
            configured = []

        now = self._now()
        connected: Set[str] = set()
        try:
            connected = set(self._client.connected_servers())
        except Exception as e:
            logger.warning(
                "MCP health check: could not list connected servers: %s", e)

        # A server with a live connection the current config does not
        # name: configured-away (the client tears it down on its next
        # call; this record keeps the dashboard honest in between).
        for name in sorted(connected):
            if name in configured:
                continue
            record = self._record(name)
            record.configured = False
            record.connected = True
            record.health = UNKNOWN

        for name in configured:
            record = self._record(name)
            record.configured = True
            if name in connected:
                record.connected = True
                await self._probe(name, record)
            else:
                # Down (or its reconnect is mid-flight): the tools this
                # server had registered stay registered — "mark
                # unavailable" is the status surface plus re-registration
                # from current config, not a tool-level kill switch —
                # and calls through them recover on demand (B1).
                record.connected = False
                if record.health in (HEALTHY, UNKNOWN):
                    record.health = DOWN
                if now >= record.next_retry_at:
                    self._schedule_reconnect(name, record)

        # Piggybacked refresh: config changed on disk, or a server just
        # recovered (its tools may never have been registered). Both are
        # "re-bridge from current config" moments; the bridge's diff
        # decides what is dropped and what is kept.
        identity = self._config_identity()
        if identity != self._last_config_identity:
            self._last_config_identity = identity
            self._needs_refresh = True
        if self._needs_refresh:
            self._needs_refresh = False
            if self._tool_executor is not None:
                from .bridge import discover_and_register
                await discover_and_register(self._tool_executor, self._client)

    async def _probe(self, name: str, record: ServerHealth) -> None:
        """Ping one live connection. An answer of ANY kind — a result,
        or even a JSON-RPC method-not-found from a server that predates
        ping — is health; the failure modes are timeout and disconnect.
        A probe failure arms the backoff like any other failure."""
        try:
            await asyncio.wait_for(
                self._client.ping(name), timeout=self._probe_timeout)
        except MCPProtocolError as e:
            # The server ANSWERED (it just does not implement ping):
            # transport responsive.
            self._probe_succeeded(record)
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # MCPClientError subclasses + the wait_for TimeoutError +
            # anything unexpected: all mean "did not answer".
            self._probe_failed(name, record, e)
            return
        self._probe_succeeded(record)

    def _probe_succeeded(self, record: ServerHealth) -> None:
        was = record.health
        record.health = HEALTHY
        record.connected = True
        record.last_error = ""
        record.last_probe_at = time.time()
        if record.reconnect_attempts or record.backoff_seconds is not None:
            logger.info(
                "MCP server '%s' is healthy again (backoff reset after %d "
                "failed attempt(s))", record.name, record.reconnect_attempts)
        record.reconnect_attempts = 0
        record.backoff_seconds = None
        record.next_retry_at = 0.0

    def _probe_failed(
        self, name: str, record: ServerHealth, error: Exception,
    ) -> None:
        """Mark unresponsive and let the backoff decide when the
        recovery reconnect runs. The probe failure itself does not
        advance the backoff — the RECONNECT failure is the counted
        attempt — so a hung server is retried every time its backoff
        window elapses (the tick interval is the floor, the cap is the
        ceiling), and an answered handshake resets everything."""
        record.health = UNRESPONSIVE
        record.connected = True   # transport alive; it just won't answer
        record.last_error = redact(str(error))
        record.last_probe_at = time.time()
        if self._now() >= record.next_retry_at:
            self._schedule_reconnect(name, record)

    # -- reconnection ------------------------------------------------------

    def _delay_for(self, attempt: int) -> float:
        """The delay AFTER the *attempt*-th failure: start, then ×2,
        capped. 1 → start, 2 → 2×start, ... capped at ``backoff_cap`` —
        the cap is what makes a permanently-down server cost one
        bounded attempt per cap interval, never a storm."""
        return min(self._backoff_start * (2 ** (attempt - 1)),
                   self._backoff_cap)

    def _arm_backoff(self, record: ServerHealth) -> None:
        attempt = record.reconnect_attempts + 1
        delay = self._delay_for(attempt)
        record.reconnect_attempts = attempt
        record.backoff_seconds = delay
        record.next_retry_at = self._now() + delay

    def _schedule_reconnect(self, name: str, record: ServerHealth) -> None:
        """One reconnect per server at a time — a second tick that finds
        the first attempt still running waits for its backoff instead of
        piling a second subprocess launch onto the same server."""
        if name in self._reconnect_tasks:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - check_once runs on a loop
            return
        task = loop.create_task(
            self._reconnect(name, record), name=f"mcp-reconnect-{name}")
        self._reconnect_tasks[name] = task
        task.add_done_callback(lambda t, _n=name: self._reconnect_tasks.pop(_n, None))

    async def _reconnect(self, name: str, record: ServerHealth) -> None:
        """One reconnection attempt through the client's own machinery
        (disconnect + rebuild from CURRENT config). Records its own
        outcome, so a tick that finds the task done just reads the
        record. Never raises past the nets below."""
        logger.info("MCP server '%s': attempting reconnect", name)
        try:
            await self._client.reconnect(name)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._arm_backoff(record)
            record.connected = False
            record.health = DOWN
            record.last_error = redact(str(e))
            logger.warning(
                "MCP server '%s': reconnect failed (attempt %d, next "
                "retry in %gs): %s", name, record.reconnect_attempts,
                record.backoff_seconds, record.last_error)
            return
        # The answered initialize handshake IS a probe.
        record.connected = True
        record.health = HEALTHY
        record.last_probe_at = time.time()
        record.last_error = ""
        attempts = record.reconnect_attempts
        record.reconnect_attempts = 0
        record.backoff_seconds = None
        record.next_retry_at = 0.0
        # A server that was down at registration time has NO tools on
        # the executor — recovery is the moment to (re-)register them.
        self._needs_refresh = True
        logger.info(
            "MCP server '%s' reconnected%s", name,
            f" (backoff reset after {attempts} failed attempt(s))"
            if attempts else "")

    async def drain(self) -> None:
        """Await every in-flight reconnect task (tests drive the sweep
        directly and need the attempts settled before asserting)."""
        tasks = [t for t in list(self._reconnect_tasks.values())
                 if not t.get_loop().is_closed()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Module-level ownership (the agent-init flow owns the client; this owns
# the tick that client instance got, plus the endpoint's way in)
# ---------------------------------------------------------------------------

#: The monitor the current agent init started (process-global, like
#: ``_agent_instance``). Superseded — never accumulated — by each
#: ``start_mcp_health_monitor`` call, so an agent re-init cannot leak
#: the previous tick.
_ACTIVE: Optional[MCPHealthMonitor] = None

#: References to supersede-stop tasks (weak-loop bookkeeping, same
#: reason the bridge keeps ``_PENDING_DISCOVERY_TASKS``).
_PENDING_STOPS: Set["asyncio.Task"] = set()


def get_active_monitor() -> Optional[MCPHealthMonitor]:
    return _ACTIVE


async def _quietly_stop(monitor: MCPHealthMonitor) -> None:
    await monitor.stop()


def start_mcp_health_monitor(
    client, tool_executor=None, **overrides: Any,
) -> Optional[MCPHealthMonitor]:
    """Create (and, on a running loop, start) the health monitor for
    *client*, parking it as the process-active monitor. A previous
    active monitor is stopped — its client is being replaced by this
    init, so its tick must not outlive it. Returns the monitor (with
    ``running`` False when no loop was running — a sync caller gets a
    dormant monitor rather than a task on a loop that will die).

    Never raises on the client's account: the monitor touches the
    client only inside the sweep, and the sweep is netted.
    """
    global _ACTIVE
    previous = _ACTIVE
    monitor = MCPHealthMonitor(client, tool_executor=tool_executor,
                               **overrides)
    _ACTIVE = monitor
    if previous is not None and previous.running:
        try:
            stop_task = asyncio.get_running_loop().create_task(
                _quietly_stop(previous), name="mcp-health-supersede")
            _PENDING_STOPS.add(stop_task)
            stop_task.add_done_callback(_PENDING_STOPS.discard)
        except RuntimeError:
            # No loop here: the previous monitor has no live task on
            # this thread's loop to stop (its loop died with its init).
            pass
    if monitor.start() is None:
        logger.debug(
            "MCP health monitor not started (no running loop in this "
            "context; it stays dormant)")
    return monitor


async def stop_mcp_health_monitor() -> None:
    """Stop the active monitor (the dashboard's shutdown event). A
    no-op when nothing is running."""
    global _ACTIVE
    monitor, _ACTIVE = _ACTIVE, None
    if monitor is None:
        return
    await monitor.stop()


def mcp_status_snapshot() -> Dict[str, Any]:
    """The payload ``GET /api/mcp/status`` serves (B4; B5 renders it).

    Config-facing fields come from the same fresh (memoized) config
    classification reads; connection/health fields come from the active
    monitor's records, with tool counts read live off the executor. No
    active monitor (agent not initialized yet, or a dormant one) means
    config-only rows with ``health: "unknown"`` — the endpoint answers
    honestly about what it knows instead of erroring.
    """
    try:
        config = load_config()
        servers_cfg = list(config.servers)
        skipped = list(config.skipped_servers)
        load_error = config.load_error
    except Exception:
        servers_cfg, skipped, load_error = [], [], ""

    try:
        from ..tools.mcp_safety import mcp_risk_summary
        risk = mcp_risk_summary()
    except Exception:
        risk = {"default": "medium", "servers": {}}

    monitor = _ACTIVE
    entries: List[Dict[str, Any]] = []
    named = set()
    for server in servers_cfg:
        named.add(server.name)
        record = monitor.health_record(server.name) if monitor else None
        entry: Dict[str, Any] = {
            "name": server.name,
            "transport": server.transport,
            "configured": True,
            "connected": record.connected if record else False,
            "health": record.health if record else UNKNOWN,
            "last_error": record.last_error if record else "",
            "last_probe_at": record.last_probe_at if record else None,
            "tool_count": (
                monitor.tool_count(server.name) if monitor else None),
            "reconnect_attempts": (
                record.reconnect_attempts if record else 0),
            "backoff_seconds": (
                record.backoff_seconds if record else None),
            "next_retry_in": (
                record.as_dict()["next_retry_in"] if record else None),
            "risk_override": (
                server.risk_override.value
                if server.risk_override is not None else None),
            "tool_risk": {
                tool: level.value
                for tool, level in server.tool_risk.items()},
        }
        entries.append(entry)

    # Servers the monitor knows but the current config does not name —
    # a removed server still tearing down, or one that never came back
    # after a rename. Shown honestly as unconfigured.
    if monitor is not None:
        for name in monitor.known_servers():
            if name in named:
                continue
            record = monitor.health_record(name)
            entry = record.as_dict()
            entry.update({
                "name": name,
                "transport": None,
                "configured": False,
                "risk_override": None,
                "tool_risk": {},
            })
            entries.append(entry)

    entries.sort(key=lambda e: e["name"])
    return {
        "enabled": True,
        "monitor_running": bool(monitor is not None and monitor.running),
        "interval_seconds": monitor.interval if monitor else None,
        "default_risk": risk.get("default", "medium"),
        "servers": entries,
        "skipped_servers": skipped,
        "load_error": load_error,
    }