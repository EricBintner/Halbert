# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Registry of MCP-discovered tools — which tools came from which server.

Halbert's tool namespace for MCP tools is ``mcp__{server}__{tool}``
(e.g. ``mcp__filesystem__read_file``), matching the convention external
MCP clients use for Halbert's own server. The registry owns the mapping
in both directions:

  * ``register(server, tool_schemas)`` → the namespaced keys (and
    nothing else — B2 decides what the agent does with them)
  * ``get(name)`` → ``MCPToolRef`` carrying the origin server, the
    server-side tool name to send in ``tools/call``, and the schema

Names come from config and from remote servers — never trusted to be
clean. Sanitization collapses every run of non-alphanumerics (including
``_``) to a single underscore and trims edges, so no component can
contain ``__`` and the two delimiters in a qualified name are the ONLY
double underscores: ``mcp__a__b`` parses unambiguously into server ``a``,
tool ``b``.

Collisions: two distinct (server, tool) pairs that sanitize to the same
key (``fs``/``read-file`` vs ``fs``/``read_file``) do not overwrite each
other. The first registration keeps the bare key; later ones get a
deterministic numeric suffix (``..._2``, ``..._3``) in registration
order. Re-registering a server replaces that server's previous entries
wholesale (hot-reload: a server whose tool list changed drops its old
names), so suffixes are stable for any given registration order.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("halbert.mcp.registry")

#: Runs of anything that is not a letter or digit — ``_``, ``-``,
#: whitespace, unicode punctuation — collapse to one underscore, so a
#: sanitized component can never contain the ``__`` delimiter.
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


#: The prefix every bridged MCP tool name carries. Exclusively the
#: bridge's — no native tool starts with it, which is what lets the
#: safety classifier (tools/mcp_safety.py) route on the prefix and what
#: lets _unregister_stale_mcp_tools drop exactly the bridged set.
MCP_TOOL_PREFIX = "mcp__"


def _sanitize_component(raw: Any) -> str:
    part = _NON_ALNUM.sub("_", str(raw)).strip("_")
    return part or "unnamed"


#: Public alias: B3's classifier and B5's display both need to reduce a
#: config-written name (server or tool) to the sanitized form the
#: qualified name carries, so an override written against ``my-fs`` /
#: ``delete-file`` still matches the registered ``mcp__my_fs__delete_file``.
sanitize_component = _sanitize_component


def components_match(config_written: Any, registered: str) -> bool:
    """Does a config-written name (server or tool) refer to the
    registered component of a qualified tool name?

    THE one matcher for every override decision: B3's classifier
    (tools/mcp_safety.py), the registration-time unmatched-key warning
    (mcp/bridge.py) and the loader's collision rejection (mcp/config.py)
    all import this, so "a key the registration warning accepts is a key
    classification will apply" is enforced by code, not convention —
    if this gains a rule, every consumer gains it together.

    Sanitized on both sides (the registry collapsed ``my-fs`` →
    ``my_fs``), and CASE-INSENSITIVELY: ``sanitize_component`` preserves
    case, so a fence written ``Delete_File`` must still match a
    registered ``delete_file`` rather than silently missing it and
    auto-executing. Registered names keep their case — only the
    comparison lowers it.
    """
    return sanitize_component(config_written).lower() == str(registered).lower()


def qualify_tool_name(server_name: str, tool_name: str) -> str:
    """The namespaced tool key: ``mcp__{server}__{tool}``."""
    return f"{MCP_TOOL_PREFIX}{_sanitize_component(server_name)}__{_sanitize_component(tool_name)}"  # noqa: E501


def parse_qualified_tool_name(qualified_name: str) -> Optional[tuple]:
    """The inverse of :func:`qualify_tool_name`: split a qualified tool
    name back into its ``(server_component, tool_component)`` pair, both
    in sanitized form.

    Returns None for anything that is not a well-formed qualified name —
    no ``mcp__`` prefix, wrong component count, or an empty component.
    Sanitization guarantees a component can never contain the ``__``
    delimiter (so the split is unambiguous), with one honest limit: a
    deterministic collision suffix (``mcp__fs__tool_2``) is part of the
    tool component and is NOT stripped — a tool that only exists under a
    suffixed name cannot be individually classified per-tool and rides
    its server's override or the MEDIUM default.
    """
    if not isinstance(qualified_name, str):
        return None
    if not qualified_name.startswith(MCP_TOOL_PREFIX):
        return None
    rest = qualified_name[len(MCP_TOOL_PREFIX):]
    parts = rest.split("__")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


@dataclass(frozen=True)
class MCPToolRef:
    """One namespaced MCP tool: where it came from and how to call it."""
    server: str          # configured server name (MCPClient call target)
    tool: str           # tool name as the SERVER knows it
    schema: Dict[str, Any]   # the tools/list schema (name, description, inputSchema)


class MCPToolRegistry:
    """Tracks which tools come from which MCP server."""

    def __init__(self) -> None:
        self._by_name: Dict[str, MCPToolRef] = {}
        self._by_server: Dict[str, List[str]] = {}

    # -- registration --------------------------------------------------------

    def register(
        self, server_name: str, tool_schemas: List[Dict[str, Any]]
    ) -> List[str]:
        """Register a server's discovered tools; returns the qualified
        names, in ``tool_schemas`` order.

        Replaces any previous registration for *server_name* first, so a
        re-discovery (server restarted, tools changed, config reloaded)
        never leaves stale names behind.
        """
        self.unregister_server(server_name)
        names: List[str] = []
        for schema in tool_schemas:
            if not isinstance(schema, dict):
                continue
            tool_name = schema.get("name")
            if not tool_name or not isinstance(tool_name, str):
                logger.warning(
                    "MCP registry: server '%s' advertised a tool with no "
                    "name, skipping", server_name)
                continue
            base = qualify_tool_name(server_name, tool_name)
            qualified = base
            counter = 1
            # Deterministic collision suffix: bare name to the first
            # registrant, then _2, _3, ... in registration order.
            while qualified in self._by_name:
                counter += 1
                qualified = f"{base}_{counter}"
            if qualified != base:
                logger.warning(
                    "MCP registry: tool name collision — server '%s' tool "
                    "'%s' registered as '%s'", server_name, tool_name,
                    qualified)
            self._by_name[qualified] = MCPToolRef(
                server=server_name, tool=tool_name, schema=schema)
            names.append(qualified)
        self._by_server[server_name] = names
        return names

    def unregister_server(self, server_name: str) -> None:
        """Drop every tool registered for *server_name*."""
        for qualified in self._by_server.pop(server_name, []):
            self._by_name.pop(qualified, None)

    # -- lookup ---------------------------------------------------------------

    def get(self, qualified_name: str) -> Optional[MCPToolRef]:
        """Look up one namespaced tool."""
        return self._by_name.get(qualified_name)

    def names(self) -> List[str]:
        """All registered tool names, sorted (deterministic ordering)."""
        return sorted(self._by_name)

    def servers(self) -> List[str]:
        """Server names with at least one registered tool."""
        return sorted(
            server for server, tools in self._by_server.items() if tools)

    def __contains__(self, qualified_name: object) -> bool:
        return qualified_name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)