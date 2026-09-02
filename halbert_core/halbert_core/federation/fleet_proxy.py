# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Fleet proxy — Desktop as MCP client of satellite (no bespoke inspect API).

Implements finding C5 from the federated multi-node review.

C5 — Fleet Cockpit inspection reuses the MCP server, not a parallel API
-----------------------------------------------------------------------
Pillar 4 / Phase 3 of the handoff proposes the Desktop AI inspecting
"remote Pi systemd configs, cron jobs, HA error logs."  Building a
bespoke ``/api/fleet/inspect`` endpoint on every satellite means every
satellite runs a second API surface with its own auth, its own
redaction, and its own tool set.

The MCP server already solves this:
- It exposes config queries with ``mcp_response()`` redaction
- It has a tool allowlist (Tier 0/1/2 sensitivity)
- It uses bearer token auth (shared with peer auth via C1)

The Desktop should be an MCP *client* of the satellite, not a consumer
of a parallel API.  This module proxies MCP tool calls from the Desktop
to the satellite over the peer link.

Data flow
---------
::

    Desktop (Fleet Cockpit UI)
    ┌──────────────────────┐         ┌────────────────────────┐
    │ fleet.py route       │         │ Satellite              │
    │   /api/fleet/        │── MCP ─►│ mcp/server.py          │
    │     {node_id}/       │  call   │   (17 tools, redacted) │
    │     inspect          │         │   mcp_response()       │
    └──────────────────────┘         └────────────────────────┘

The Desktop's fleet route receives a tool name + params from the UI,
calls ``fleet_proxy.call_satellite_tool()``, which sends an MCP
JSON-RPC request to the satellite's MCP server.  The satellite applies
``mcp_response()`` redaction on its end.  The Desktop applies
``mcp_response()`` again as defense-in-depth (in case the satellite
is running an older version without redaction).

Why defense-in-depth?
---------------------
The satellite is a separate Halbert instance that may be running a
different version.  If the satellite's MCP server has a redaction bug
(or is running a pre-redaction version), the Desktop's second
``mcp_response()`` pass catches it.  This is the "trust but verify"
pattern — the satellite is trusted to redact, but the Desktop verifies.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP JSON-RPC over HTTP
# ---------------------------------------------------------------------------

class FleetProxy:
    """Proxy MCP tool calls from the Desktop to a satellite node.

    The Desktop acts as an MCP client, sending JSON-RPC 2.0 requests to
    the satellite's MCP HTTP/SSE endpoint (Phase 4b).  The satellite's
    MCP server handles the tool execution and applies ``mcp_response()``
    redaction.  This class applies ``mcp_response()`` again on the
    Desktop side as defense-in-depth.

    TODO(federation-9.9): Implement using ``requests`` (the one allowed
    hard dependency) to send JSON-RPC over HTTP.
    """

    def __init__(
        self,
        satellite_endpoint: str,
        peer_token: str,
        timeout: float = 10.0,
    ):
        """
        Args:
            satellite_endpoint: The satellite's base URL
                (e.g., "http://living-room-pi.local:8000").
            peer_token: Bearer token for authenticating to the satellite.
            timeout: HTTP timeout for MCP calls (seconds).
        """
        self.satellite_endpoint = satellite_endpoint.rstrip("/")
        self.peer_token = peer_token
        self.timeout = timeout

    def call_tool(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call an MCP tool on the satellite.

        Sends a JSON-RPC 2.0 ``tools/call`` request to the satellite's
        MCP HTTP endpoint.  The satellite executes the tool and returns
        the result (already redacted by the satellite's mcp_response()).

        This method applies ``mcp_response()`` again on the result as
        defense-in-depth (C5).

        TODO(federation-9.9): Implement using requests.post:
        1. Build JSON-RPC 2.0 request: {"jsonrpc": "2.0", "method": "tools/call",
           "params": {"name": tool_name, "arguments": params}, "id": 1}
        2. POST to {satellite_endpoint}/api/mcp/v1 (Phase 4b HTTP transport)
        3. Parse JSON-RPC response
        4. Apply mcp_response() on the result (defense-in-depth)
        5. Return the redacted result
        """
        raise NotImplementedError("FleetProxy.call_tool() — TODO(federation-9.9)")

    def list_tools(self) -> list:
        """List available MCP tools on the satellite.

        TODO(federation-9.9): Send JSON-RPC ``tools/list`` request.
        The Desktop uses this to populate the Fleet Cockpit's tool
        picker (which diagnostic tools are available on this satellite).
        """
        raise NotImplementedError("FleetProxy.list_tools() — TODO(federation-9.9)")

    def get_satellite_info(self) -> Dict[str, Any]:
        """Get the satellite's instance info (persona, role, features).

        This is a plain REST call to ``GET /api/instance/info``, not an
        MCP call.  It's used to populate the Fleet Cockpit's node card.

        TODO(federation-9.9): Implement using requests.get.
        """
        raise NotImplementedError("FleetProxy.get_satellite_info() — TODO(federation-9.9)")

    def stream_logs(self, follow: bool = True):
        """Stream logs from the satellite via SSE.

        TODO(federation-9.9): Connect to the satellite's log SSE
        endpoint and yield log lines.  Used by the Fleet Cockpit's
        real-time log viewer.
        """
        raise NotImplementedError("FleetProxy.stream_logs() — TODO(federation-9.9)")


# ---------------------------------------------------------------------------
# Convenience — get a proxy for a paired satellite
# ---------------------------------------------------------------------------

def get_fleet_proxy(node_id: str) -> Optional[FleetProxy]:
    """Get a FleetProxy for a paired satellite by node_id.

    Looks up the peer's endpoint and token from PeersConfig and
    constructs a FleetProxy.  Returns None if the peer is not found or
    is revoked.

    TODO(federation-9.4): the spec above is UNIMPLEMENTABLE as written.
    PeersConfig deliberately persists only ``sha256:<hex>`` token hashes
    (M14: the raw token is never persisted to disk), so the raw peer
    token the C5 "Desktop as MCP client of satellite" flow needs cannot
    be recovered from PeersConfig. Before federation-9.9 is implemented,
    a token-custody design is required: peer pairing is bidirectional
    (each side holds a raw token for the *other*), so the Desktop's
    OUTBOUND satellite credentials need their own store — a separate
    credentials file or an OS keychain/keyring reference — with
    ``token_hash`` kept for inbound verification. They must NEVER be
    stored as plaintext in peers.json; silently downgrading M14 is the
    failure mode this note exists to prevent.

    TODO(federation-9.9): Implement (after the custody design lands):
    1. Get PeersConfig singleton
    2. Look up peer by node_id
    3. If not found or revoked, return None
    4. Construct FleetProxy(satellite_endpoint, peer_token)
    5. Return the proxy
    """
    # None, not NotImplementedError: None is this function's documented
    # answer for "no proxy is available for that peer", and the callers all
    # handle it. Raising turned every Fleet Cockpit route into a 500 —
    # reporting a crash where the truth is that the outbound-token custody
    # design above has not been made yet (FED-01 / R10-F10, and the R2-F6
    # decision this note describes).
    logger.debug(
        "Fleet proxy unavailable for %s: outbound peer-token custody is not "
        "designed yet (federation-9.4)", node_id,
    )
    return None
