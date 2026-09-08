# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Bridge MCP server tools into Halbert's ToolExecutor (Workstream B2).

Each tool a connected MCP server answers ``tools/list`` with becomes a
native agent tool under the namespaced key ``mcp__{server}__{tool}``
(B1's :class:`~halbert_core.mcp.registry.MCPToolRegistry` produces and
deconflicts the names). The agent never knows the difference: the schema
is Halbert's own ``{name, description, parameters}`` shape and the
handler is an ordinary async ``handler(args) -> result`` like every
other registered tool.

Shape of the flow (all of it inside :func:`discover_and_register`, the
single funnel every MCP tool flows through):

  ``connect()`` every configured server (failures logged by the client,
  never raised — a server that is down contributes NO tools, which is
  the graceful-absence rule) → per connected server, ``tools/list`` →
  ``MCPToolRegistry.register`` for namespacing → schema conversion →
  ``tool_executor.register(name, handler, schema)``.

Sync entry point: :func:`register_mcp_tools`. Discovery is async, but
agent init (``dashboard/routes/agent.py``) is sync and never awaits the
scheduled task, so the never-raise contract is enforced twice: the
discovery coroutine carries a top-level net (log with the server names,
return 0) and every scheduled task gets an exception-logging done
callback — an escaping exception would otherwise be an unretrieved-task
GC warning with the agent silently at zero MCP tools. The entry point
detects its threading context:

  * no running loop (CLI, tests, worker threads) — ``asyncio.run`` the
    discovery and block until it finishes;
  * a running loop (the dashboard's async routes) — schedule it on that
    loop and return the task. Discovery then lands microseconds later,
    on the SAME loop the tool handlers will later run on: an
    ``MCPClient``'s per-server locks and subprocess readers must never
    be shared across two event loops, so the bridge never moves a
    client between loops (no worker-thread discovery).

Failure model: ``MCPClient.call_tool`` raises typed
:class:`~halbert_core.mcp.client.MCPClientError` subclasses with clean,
redacted messages; the handler lets them propagate and the executor's
existing catch-all turns them into a failed :class:`ExecutionResult`
(the same route ``read_file``'s ``FileNotFoundError`` takes). Every
failure mode — server down, tool error (``isError``), timeout,
disconnect, protocol garbage — is a clean result message, never a
crash and never a hang (every client operation is timeout-bounded).

Registration timing is refresh-based since B4: tools are discovered at
agent init, and the health monitor (mcp/health.py) re-runs this bridge
from CURRENT config whenever ``mcp_config.yml``'s file identity changes
(plus after a server recovers), so a server added to (or removed from)
the config shows up within one health tick, no restart. Re-running the
bridge on a live executor is safe and diff-based: tools of servers the
current config does not name are dropped (their classifier would
fail-closed block them anyway), while a server that is configured but
DOWN at refresh time KEEPS its previous registrations — a failed
connect must not zero the working set (the B2 residual, fixed here).
The client's per-call config reload stays B1's connection behavior.

Context bloat: a server exposing a huge tool list bloats every agent
turn's tool schema block. Above :data:`MANY_TOOLS_WARNING` the bridge
logs a warning; above :data:`MAX_TOOLS_PER_SERVER` it truncates (a
per-server ``max_tools`` config knob can replace the constant if the
cap ever needs tuning — deliberately not built until asked).

Guests: MCP tool names are dynamic (they come from remote servers), so
they cannot be enumerated on ``persona/guest_tools.py``'s allowlist —
which is exactly why they are structurally denied: the allowlist IS the
rule, and no ``mcp__`` name is on it. What the OWNER's turns may do
with these tools is decided by B3's risk classification — which lives in
the PER-CALL path (``tools/mcp_safety.py``, routed from
``ToolSafetyFramework._classify_builtin``), NOT in this bridge: tool
registration happens once at agent init, but classification must be
re-evaluated against the current ``mcp_config.yml`` on every call, so a
``risk_override`` flip gates the next tool call with no restart. Nothing
below intercepts or gates; the executor's existing chain (CRITICAL
block, HIGH confirmation, RoleGate) enforces. One pre-existing route
reaches past this bridge's guarantees: an UNREGISTERED ``mcp__`` name
can be peer-proxied (the executor's ``peer_tool_proxy``) before
classification ever runs locally — there, the PEER's own safety chain
governs execution; locally, without a peer, such a name is simply an
unknown tool.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from .client import join_text_content
from .registry import (
    MCP_TOOL_PREFIX,
    MCPToolRegistry,
    parse_qualified_tool_name,
    sanitize_component,
)

logger = logging.getLogger("halbert.mcp.bridge")

#: Hard cap on tools registered from one server. A server beyond the cap
#: contributes only its first MAX tools (in tools/list order); the rest
#: are dropped with a warning naming the server and the counts.
MAX_TOOLS_PER_SERVER = 64

#: A server exposing more tools than this is legal but noteworthy: each
#: registered schema rides in EVERY agent turn's tool block, so a fat
#: server costs context on every turn. Warn without truncating.
MANY_TOOLS_WARNING = 32

#: References to discovery tasks scheduled on a running loop. The event
#: loop holds only weak references to tasks, so an unreferenced task can
#: be garbage-collected mid-discovery; this set keeps them alive until
#: they finish. Not a client singleton — the agent-init flow owns the
#: client instance; this is only bookkeeping for the init it started.
_PENDING_DISCOVERY_TASKS: Set["asyncio.Task"] = set()


# ---------------------------------------------------------------------------
# Schema conversion
# ---------------------------------------------------------------------------

def convert_schema(
    qualified_name: str,
    tool_schema: Dict[str, Any],
    server_name: str,
    tool_name: str,
) -> Dict[str, Any]:
    """Convert one ``tools/list`` entry into Halbert's tool schema shape.

    Halbert's schemas (see ``tools/executor.py``'s builtin registrations)
    are ``{name, description, parameters}`` where ``parameters`` is a
    JSON-Schema object — the same shape MCP calls ``inputSchema`` (``{type:
    "object", properties, required}``), so the mapping is a rename plus
    defensive defaults. A server that omits or garbles its inputSchema
    still gets a callable tool with an empty object schema rather than
    being dropped: the model can call it with no arguments.
    """
    input_schema = tool_schema.get("inputSchema")
    if not isinstance(input_schema, dict) or not input_schema:
        input_schema = {"type": "object", "properties": {}}

    description = tool_schema.get("description")
    if not isinstance(description, str) or not description.strip():
        description = f"MCP tool '{tool_name}' from MCP server '{server_name}'"

    return {
        "name": qualified_name,
        "description": description,
        "parameters": input_schema,
    }


def format_tool_result(result: Any) -> str:
    """Convert a raw ``tools/call`` result into what the model sees.

    Text content items are joined (the same join rule the client uses
    for ``MCPToolError.text``). A result with non-text content (images,
    embedded resources) or no content at all is JSON-dumped so nothing
    the server produced is silently discarded.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if "content" in result:
            text = join_text_content(result.get("content"))
            if text:
                return text
        return _json_dump(result)
    if result is None:
        return "(no output)"
    return _json_dump(result)


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Handler construction
# ---------------------------------------------------------------------------

def make_tool_handler(mcp_client, server_name: str, tool_name: str):
    """Build the async handler the executor registers for one MCP tool.

    The handler takes only its args dict (the executor's contract) and
    calls through the client, which owns reconnection, config reload and
    timeouts. Errors are deliberately RAISED, not returned: the client's
    typed errors carry clean redacted messages, and the executor's
    existing catch-all converts any exception into a failed
    :class:`~halbert_core.tools.executor.ExecutionResult` — the same
    path every native tool's exceptions take. Nothing intercepts the
    result here: B3's risk classification runs in the executor's
    per-call classify step (tools/mcp_safety.py) BEFORE this handler is
    reached, and the executor enforces it.
    """

    async def handler(args: Dict[str, Any]) -> Any:
        raw = await mcp_client.call_tool(server_name, tool_name, args or {})
        return format_tool_result(raw)

    return handler


# ---------------------------------------------------------------------------
# Discovery and registration
# ---------------------------------------------------------------------------

async def _collect_server_tools(
    mcp_client, server_name: str,
) -> List[Dict[str, Any]]:
    """One server's ``tools/list`` answer, all pages, as a list of dicts.

    Once "THE B3 SEAM": every MCP tool schema flows through this one
    function before registration. B3 chose NOT to wrap it — registration
    is a bad moment to classify, because it happens once at agent init
    and a classification captured here would be a snapshot a config flip
    cannot reach (the freshness requirement is per call). Risk
    classification lives in tools/mcp_safety.py, in the per-call
    executor path; the seam remains a plain fetch, kept as its own
    function because pagination (when it lands) still belongs here.
    """
    schemas = await mcp_client.list_tools(server_name)
    if not isinstance(schemas, list):
        return []
    return [s for s in schemas if isinstance(s, dict)]


def _warn_unmatched_tool_risk_keys(
    server_name: str,
    tool_schemas: List[Dict[str, Any]],
) -> None:
    """B3: warn per ``tool_risk`` key that matches no advertised tool.

    A per-tool override key that matches nothing is almost certainly a
    typo, and the failure direction is the worst one — a CRITICAL fence
    silently degrades to the per-server level or auto-execute MEDIUM.
    The config itself cannot know the server's tool list, so this is
    said HERE, the one place both sides are in hand at once. Matching is
    the classifier's own rule (sanitized, case-insensitive), so a key
    this check accepts is a key classification will apply.

    Never raises (the bridge's contract); a config that cannot be read
    simply skips the check — classification's absent-server fail-closed
    covers that state.
    """
    try:
        from .config import load_config
        from .registry import components_match

        server = load_config().server(server_name)
        if server is None or not server.tool_risk:
            return
        advertised = [
            s.get("name") for s in tool_schemas
            if isinstance(s, dict) and s.get("name")
        ]
        for key in server.tool_risk:
            # The shared matcher (registry.components_match) — the same
            # rule classification uses — so a key this warning accepts
            # is a key classification will apply. Never a drifted copy.
            if not any(components_match(name, key) for name in advertised):
                logger.warning(
                    "MCP config: server '%s' tool_risk key '%s' matches "
                    "no advertised tool (advertised: %s) — the override "
                    "applies to nothing; if this is a typo, the tool "
                    "classifies on its per-server or default path",
                    server_name, key,
                    ", ".join(sorted(str(n) for n in advertised)) or "(none)")
    except Exception as e:
        logger.debug(
            "MCP tool_risk unmatched-key check skipped for server '%s': %s",
            server_name, e)


def _register_server_tools(
    tool_executor,
    mcp_client,
    registry: MCPToolRegistry,
    server_name: str,
    tool_schemas: List[Dict[str, Any]],
) -> int:
    """Namespace, convert and register one server's tools. Returns how
    many landed on the executor."""
    _warn_unmatched_tool_risk_keys(server_name, tool_schemas)
    count = len(tool_schemas)
    if count > MAX_TOOLS_PER_SERVER:
        logger.warning(
            "MCP server '%s' exposes %d tools; registering only the first "
            "%d (context bloat cap)", server_name, count, MAX_TOOLS_PER_SERVER)
        tool_schemas = tool_schemas[:MAX_TOOLS_PER_SERVER]
    elif count > MANY_TOOLS_WARNING:
        logger.warning(
            "MCP server '%s' exposes %d tools — a large tool list rides in "
            "every agent turn's context", server_name, count)

    # B1's registry sanitizes names and resolves collisions with
    # deterministic suffixes; re-registering a server replaces its
    # previous entries wholesale.
    qualified_names = registry.register(server_name, tool_schemas)
    for qualified in qualified_names:
        ref = registry.get(qualified)
        if ref is None:
            # register() just produced this name, so this is unreachable
            # today — but a plain guard rather than an assert, so a future
            # registry edit degrades to a skipped tool, never a crash
            # under ``python -O``.
            logger.warning(
                "MCP registry lost tool '%s' between register and lookup, "
                "skipping", qualified)
            continue
        tool_executor.register(
            qualified,
            make_tool_handler(mcp_client, ref.server, ref.tool),
            convert_schema(qualified, ref.schema, ref.server, ref.tool),
        )
    return len(qualified_names)


def _drop_tools_for_server(tool_executor, server_name: str) -> int:
    """Drop every executor registration belonging to one server (its
    sanitized component in the qualified names; *server_name* is the raw
    config name the client connected, so it is sanitized before the
    comparison). Returns how many landed. The registry's per-server
    ``register`` replaces its OWN entries, but the executor's older keys
    would linger when a server's tool list SHRANK between discoveries —
    this is the executor-side half of the replace."""
    component = sanitize_component(server_name).lower()
    dropped = 0
    for name in list(tool_executor.tools):
        if not name.startswith(MCP_TOOL_PREFIX):
            continue
        parsed = parse_qualified_tool_name(name)
        if parsed is None:
            continue
        if parsed[0].lower() == component:
            tool_executor.tools.pop(name, None)
            tool_executor.schemas.pop(name, None)
            dropped += 1
    return dropped


def _drop_unconfigured_server_tools(
    tool_executor, configured_names: List[str],
) -> List[str]:
    """B4's DIFF drop — the stale-drop ordering fix the bridge docstring
    used to defer. Only the tools of servers the CURRENT config does not
    name are dropped, BEFORE anything is registered; the rest of the old
    set survives until its own server is (re-)registered.

    Three cases fall out of one rule (a registered tool exists only if
    its server was configured at registration time):

      * server REMOVED/RENAMED/DROPPED-BY-VALIDATION since → its tools
        are dropped outright (B3's classifier would fail-closed block
        them anyway; keeping them would only list dead names);
      * server still configured but DOWN at this refresh (its connect
        failed) → its tools are KEPT — the B2 residual this fixes: the
        old drop ran before ``connect()``, so a re-registration whose
        connect failed totally yielded ZERO MCP tools instead of keeping
        the previous, still-working set. The client relaunches a down
        server on the next call, and the monitor keeps retrying;
      * server connected now → its executor entries are replaced just
        before its fresh registration (``_drop_tools_for_server``), so a
        SHRUNK tool list leaves no stale names behind.

    Returns the raw names of the servers whose tools were dropped (for
    the log). A blind spot, stated honestly: a kept (down) server's
    tools may still classify under a surviving colliding config entry —
    the collider-displacement closure is complete once the server
    connects again and the refresh re-registers its tools.
    """
    configured_sanitized = {
        sanitize_component(name).lower() for name in configured_names}
    dropped_servers: List[str] = []
    for name in list(tool_executor.tools):
        if not name.startswith(MCP_TOOL_PREFIX):
            continue
        parsed = parse_qualified_tool_name(name)
        if parsed is None:
            continue
        if parsed[0].lower() not in configured_sanitized:
            tool_executor.tools.pop(name, None)
            tool_executor.schemas.pop(name, None)
            server = parsed[0]
            if server not in dropped_servers:
                dropped_servers.append(server)
    if dropped_servers:
        logger.debug(
            "Dropped stale MCP tool registration(s) for server(s): %s",
            ", ".join(dropped_servers))
    return dropped_servers


async def discover_and_register(tool_executor, mcp_client) -> int:
    """Connect every configured server and bridge its tools. Returns the
    number of tools registered. NEVER raises — a broken client, a dead
    server, a garbage tools/list, or a B3 wrapper blowing up mid-discovery
    is zero tools (logged, with the server names), not a dead agent.
    """
    try:
        return await _discover_and_register(tool_executor, mcp_client)
    except Exception as e:
        # The last-ditch net. Every step below already handles its own
        # expected failures; this catches the unexpected — including an
        # exception escaping a B3 wrapper around _collect_server_tools.
        # Production fire-and-forgets the discovery task (agent init
        # never awaits it), so anything raised here would surface as an
        # unretrieved-task GC warning with the agent silently at zero
        # MCP tools. Log it loudly instead.
        connected: List[str] = []
        try:
            connected = list(mcp_client.connected_servers())
        except Exception:
            pass
        logger.error(
            "MCP discovery failed (connected server(s): %s): %s",
            ", ".join(connected) or "(none)", e, exc_info=e)
        return 0


async def _discover_and_register(tool_executor, mcp_client) -> int:
    """The discovery body, run under discover_and_register's net.

    B4 ordering: the stale drop no longer runs before ``connect()``.
    The diff runs AFTER it (see ``_drop_unconfigured_server_tools``), so
    a refresh whose connects all fail keeps the previous registrations
    instead of zeroing the MCP tool set, while a server the current
    config no longer names still loses its tools.
    """
    try:
        # Connect every configured server. The client logs each failure
        # and collects it — a server that is down is simply absent from
        # connected_servers() below.
        await mcp_client.connect()
    except Exception as e:
        # The real client's connect() never raises MCPClientError (it
        # logs and collects per-server failures); this catches the
        # unexpected. B4: total failure KEEPS the prior registrations —
        # dropping them here would be the pre-B4 zeroing bug again.
        logger.warning("MCP discovery: connect failed: %s", e)
        return 0

    try:
        servers = mcp_client.connected_servers()
    except Exception as e:
        logger.warning("MCP discovery: could not list connected servers: %s", e)
        return 0

    # The configured names, for the diff. A config the bridge cannot
    # read leaves the diff blind — drop NOTHING (the classifier's
    # absent-server fail-closed path gates whatever is stale; a
    # mis-timed drop must not amplify a read failure into a tool loss).
    try:
        from .config import load_config
        configured_names = [s.name for s in load_config().servers]
    except Exception as e:
        logger.warning(
            "MCP discovery: config unreadable (%s); keeping every "
            "existing MCP registration", e)
        configured_names = None
    if configured_names is not None:
        _drop_unconfigured_server_tools(tool_executor, configured_names)

    registry = MCPToolRegistry()
    registered = 0
    for server_name in servers:
        try:
            # Collect FIRST: a server whose tools/list fails KEEPS its
            # previous registrations (same rule as a failed connect —
            # B4's ordering), instead of having been dropped up front.
            tool_schemas = await _collect_server_tools(mcp_client, server_name)
            _drop_tools_for_server(tool_executor, server_name)
            # Registration is inside the same try: a conversion or
            # registry failure costs THIS server's tools, not the rest
            # of the loop.
            registered += _register_server_tools(
                tool_executor, mcp_client, registry, server_name, tool_schemas)
        except Exception as e:
            logger.warning(
                "MCP server '%s': tools unavailable, skipping: %s",
                server_name, e)
            continue

    if registered:
        logger.info(
            "Registered %d MCP tool(s) from %d server(s)",
            registered, len(servers))
    return registered


def _task_finished(task: "asyncio.Task") -> None:
    """Done callback for a scheduled discovery task: release the
    bookkeeping reference and log any exception the task is carrying.

    Production fire-and-forgets the task (agent init never awaits it),
    so an exception escaping :func:`discover_and_register` would
    otherwise surface only as an unretrieved-task GC warning with no
    log naming the cause. This callback is that log — and the
    completion hook B4's health monitoring / B5 can hook into.
    """
    _PENDING_DISCOVERY_TASKS.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("MCP discovery task failed: %s", exc, exc_info=exc)


def register_mcp_tools(tool_executor, mcp_client) -> Optional["asyncio.Task"]:
    """Bridge every configured MCP server's tools onto *tool_executor*.

    The sync entry point agent init calls. Runs the async discovery to
    completion when no event loop is running (blocking agent start by at
    most the per-server timeouts), or schedules it on the running loop
    and returns the task (callers on a loop get their agent immediately;
    discovery lands a tick later on the same loop the handlers use).

    The no-loop path is single-shot: ``asyncio.run`` binds stdio
    transports to an ephemeral loop that CLOSES when it returns, so
    registration and tool use must share one loop lifetime — a caller
    that discovers on one loop and executes on another pays a
    relaunch-per-call (the transports read as dead). Every production
    callsite (dashboard routes, wyoming) runs on the loop that executes
    tools, which is why the bridge never moves a client between loops.

    Either way a server that is down, misbehaving, or absent contributes
    no tools and no error — graceful absence is the whole point.
    """
    coro = discover_and_register(tool_executor, mcp_client)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return None
    task = loop.create_task(coro)
    _PENDING_DISCOVERY_TASKS.add(task)
    task.add_done_callback(_task_finished)
    return task
