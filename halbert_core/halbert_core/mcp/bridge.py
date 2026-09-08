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
single funnel every MCP tool flows through — the seam B3's per-server
risk classification wraps):

  ``connect()`` every configured server (failures logged by the client,
  never raised — a server that is down contributes NO tools, which is
  the graceful-absence rule) → per connected server, ``tools/list`` →
  ``MCPToolRegistry.register`` for namespacing → schema conversion →
  ``tool_executor.register(name, handler, schema)``.

Sync entry point: :func:`register_mcp_tools`. Discovery is async, but
agent init (``dashboard/routes/agent.py``) is sync, so the entry point
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

Registration timing is restart-based: tools are discovered at agent
init, so a server added to (or removed from) ``mcp_config.yml`` shows
up after the next agent start. Re-running the bridge on a live executor
(a future B4 health refresh) is also supported: it first drops every
stale ``mcp__`` registration, so a removed server's tools do not
linger. The client's per-call config reload stays B1's connection
behavior.

Context bloat: a server exposing a huge tool list bloats every agent
turn's tool schema block. Above :data:`MANY_TOOLS_WARNING` the bridge
logs a warning; above :data:`MAX_TOOLS_PER_SERVER` it truncates (a
per-server ``max_tools`` config knob can replace the constant if the
cap ever needs tuning — deliberately not built until asked).

Guests: MCP tool names are dynamic (they come from remote servers), so
they cannot be enumerated on ``persona/guest_tools.py``'s allowlist —
which is exactly why they are structurally denied: the allowlist IS the
rule, and no ``mcp__`` name is on it. Per-server risk classification
(B3) will decide what the OWNER's turns may do with these tools.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from .client import _join_text_content
from .registry import MCPToolRegistry

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
            text = _join_text_content(result.get("content"))
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
    path every native tool's exceptions take. B3 will intercept the
    result/error on its way to the model.
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

    THE B3 SEAM: every MCP tool schema flows through this one function
    before registration, so per-server risk classification (B3) can wrap
    or filter it without touching the rest of the bridge.
    """
    schemas = await mcp_client.list_tools(server_name)
    if not isinstance(schemas, list):
        return []
    return [s for s in schemas if isinstance(s, dict)]


def _register_server_tools(
    tool_executor,
    mcp_client,
    registry: MCPToolRegistry,
    server_name: str,
    tool_schemas: List[Dict[str, Any]],
) -> int:
    """Namespace, convert and register one server's tools. Returns how
    many landed on the executor."""
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
        assert ref is not None  # register() just produced it
        tool_executor.register(
            qualified,
            make_tool_handler(mcp_client, ref.server, ref.tool),
            convert_schema(qualified, ref.schema, ref.server, ref.tool),
        )
    return len(qualified_names)


def _unregister_stale_mcp_tools(tool_executor) -> None:
    """Drop every previously bridged tool before a fresh discovery, so a
    server that vanished from the config does not leave its tools behind
    (the executor has no unregister of its own). The ``mcp__`` prefix is
    exclusively the bridge's — no native tool carries it."""
    stale = [name for name in tool_executor.tools if name.startswith("mcp__")]
    for name in stale:
        tool_executor.tools.pop(name, None)
        tool_executor.schemas.pop(name, None)
    if stale:
        logger.debug("Dropped %d stale MCP tool registration(s)", len(stale))


async def discover_and_register(tool_executor, mcp_client) -> int:
    """Connect every configured server and bridge its tools. Returns the
    number of tools registered. NEVER raises — a broken client, a dead
    server, or a garbage tools/list is zero tools, not a dead agent.
    """
    _unregister_stale_mcp_tools(tool_executor)

    try:
        # Connect every configured server. The client logs each failure
        # and collects it — a server that is down is simply absent from
        # connected_servers() below.
        await mcp_client.connect()
    except Exception as e:
        logger.warning(
            "MCP discovery: connect failed, no tools registered: %s", e)
        return 0

    try:
        servers = mcp_client.connected_servers()
    except Exception as e:
        logger.warning("MCP discovery: could not list connected servers: %s", e)
        return 0

    registry = MCPToolRegistry()
    registered = 0
    for server_name in servers:
        try:
            tool_schemas = await _collect_server_tools(mcp_client, server_name)
        except Exception as e:
            logger.warning(
                "MCP server '%s': tools unavailable, skipping: %s",
                server_name, e)
            continue
        registered += _register_server_tools(
            tool_executor, mcp_client, registry, server_name, tool_schemas)

    if registered:
        logger.info(
            "Registered %d MCP tool(s) from %d server(s)",
            registered, len(servers))
    return registered


def register_mcp_tools(tool_executor, mcp_client) -> Optional["asyncio.Task"]:
    """Bridge every configured MCP server's tools onto *tool_executor*.

    The sync entry point agent init calls. Runs the async discovery to
    completion when no event loop is running (blocking agent start by at
    most the per-server timeouts), or schedules it on the running loop
    and returns the task (callers on a loop get their agent immediately;
    discovery lands a tick later on the same loop the handlers use).

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
    task.add_done_callback(_PENDING_DISCOVERY_TASKS.discard)
    return task