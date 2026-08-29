# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Fleet Cockpit REST endpoints — node aggregation and remote inspection.

Implements finding C5 from the federated multi-node review.

C5 — Fleet Cockpit reuses the MCP server, not a bespoke inspect API
-------------------------------------------------------------------
The Desktop's Fleet Cockpit inspects remote satellites by proxying MCP
tool calls through ``fleet_proxy.py``.  Each satellite runs the MCP
server (Phase 4b) with its own ``mcp_response()`` redaction boundary.
The Desktop connects as an MCP client.

This route module provides the REST endpoints that the Fleet Cockpit
UI calls.  It does NOT implement a parallel inspection API — it
delegates to ``FleetProxy`` which speaks MCP JSON-RPC to the satellite.

Endpoints
---------
  GET  /api/fleet/nodes               — list all paired satellites with status
  GET  /api/fleet/{node_id}/info      — satellite's instance info (via REST)
  GET  /api/fleet/{node_id}/telemetry — latest telemetry for a satellite
  POST /api/fleet/{node_id}/inspect   — proxy an MCP tool call to a satellite
  GET  /api/fleet/{node_id}/logs      — SSE stream of satellite logs
  GET  /api/fleet/{node_id}/discoveries — satellite's discovery snapshot

The ``inspect`` endpoint is the key one — it takes a tool name and
params, proxies them to the satellite's MCP server, and returns the
redacted result.  The satellite applies ``mcp_response()`` on its end;
the Desktop applies ``mcp_response()`` again as defense-in-depth (C5).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...federation.peer_middleware import get_peers_config
from ...federation.fleet_proxy import get_fleet_proxy, FleetProxy

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class FleetVitals(BaseModel):
    """Live vitals for a fleet node (matches the frontend FleetNodeStatus.vitals shape)."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_available_mb: float = 0.0
    temperature_c: Optional[float] = None
    uptime_seconds: float = 0.0
    load_average_1m: Optional[float] = None
    disk_percent: float = 0.0


class FleetNodeStatus(BaseModel):
    """Status of a single satellite node in the fleet."""
    node_id: str
    node_name: str
    role: str
    endpoint: Optional[str] = None
    online: bool = False
    last_seen: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    # Telemetry is populated lazily (only for online nodes)
    vitals: Optional[FleetVitals] = None
    discovery_count: Optional[int] = None


class InspectRequest(BaseModel):
    """A request to inspect a satellite via MCP tool call.

    The tool_name must be one of the MCP server's 17 tools.  The
    satellite applies its own tool allowlist and redaction — the
    Desktop does not filter here (the satellite is the authority on
    what it exposes).
    """
    tool_name: str = Field(..., description="MCP tool name (e.g., 'get_config_structure')")
    params: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")


class InspectResponse(BaseModel):
    """The result of an MCP tool call proxied to a satellite."""
    node_id: str
    tool_name: str
    result: Any
    redacted: bool = True  # Always True — mcp_response() is applied on both ends


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/fleet/nodes", response_model=List[FleetNodeStatus])
async def list_fleet_nodes() -> List[FleetNodeStatus]:
    """List all paired satellite nodes with their current status.

    TODO(federation-9.9): For each paired peer:
    1. Construct a FleetProxy
    2. Call get_satellite_info() to check if online
    3. If online, fetch latest telemetry
    4. Build FleetNodeStatus
    """
    config = get_peers_config()
    nodes: List[FleetNodeStatus] = []

    for peer in config.list_peers():
        nodes.append(FleetNodeStatus(
            node_id=peer.node_id,
            node_name=peer.node_name,
            role=peer.role,
            endpoint=peer.endpoint,
            online=False,  # TODO(federation-9.9): probe via FleetProxy
            last_seen=peer.last_seen,
            capabilities=peer.capabilities,
        ))

    return nodes


@router.get("/api/fleet/{node_id}/info")
async def get_node_info(node_id: str) -> Dict[str, Any]:
    """Get a satellite's instance info (persona, role, features).

    This is a plain REST call to the satellite's ``GET /api/instance/info``,
    proxied through FleetProxy.  No MCP involved — this is just the
    satellite's identity card.

    TODO(federation-9.9): Implement via FleetProxy.get_satellite_info().
    """
    proxy = get_fleet_proxy(node_id)
    if proxy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Peer {node_id} not found or revoked")
    # TODO(federation-9.9): return await proxy.get_satellite_info()
    raise NotImplementedError("get_node_info — TODO(federation-9.9)")


@router.get("/api/fleet/{node_id}/telemetry")
async def get_node_telemetry(node_id: str) -> Dict[str, Any]:
    """Get the latest telemetry for a satellite.

    TODO(federation-9.9): Either:
    a) Fetch from a local cache (if the satellite pushes telemetry via
       TelemetryAgent), or
    b) Pull from the satellite via an MCP tool call or REST endpoint.
    """
    raise NotImplementedError("get_node_telemetry — TODO(federation-9.9)")


@router.post("/api/fleet/{node_id}/inspect", response_model=InspectResponse)
async def inspect_node(node_id: str, req: InspectRequest) -> InspectResponse:
    """Proxy an MCP tool call to a satellite (C5 — no bespoke inspect API).

    This is the core of the Fleet Cockpit's remote inspection capability.
    The Desktop sends an MCP tool call to the satellite via FleetProxy.
    The satellite executes the tool and applies ``mcp_response()``
    redaction.  The Desktop applies ``mcp_response()`` again as
    defense-in-depth.

    TODO(federation-9.9): Implement via FleetProxy.call_tool().
    """
    proxy = get_fleet_proxy(node_id)
    if proxy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Peer {node_id} not found or revoked")

    # TODO(federation-9.9):
    # result = proxy.call_tool(req.tool_name, req.params)
    # return InspectResponse(node_id=node_id, tool_name=req.tool_name, result=result)
    raise NotImplementedError("inspect_node — TODO(federation-9.9)")


@router.get("/api/fleet/{node_id}/logs")
async def stream_node_logs(node_id: str):
    """SSE stream of a satellite's logs.

    TODO(federation-9.9): Connect to the satellite's log SSE endpoint
    via FleetProxy.stream_logs() and proxy the events to the client.
    """
    raise NotImplementedError("stream_node_logs — TODO(federation-9.9)")


@router.get("/api/fleet/{node_id}/discoveries")
async def get_node_discoveries(node_id: str) -> Dict[str, Any]:
    """Get a satellite's discovery snapshot via MCP.

    This calls the satellite's MCP ``get_discoveries`` tool (or a REST
    equivalent) and returns the structured discovery list.  The
    satellite applies ``mcp_response()`` redaction on the result.

    TODO(federation-9.9): Implement via FleetProxy.call_tool("get_discoveries", {}).
    """
    raise NotImplementedError("get_node_discoveries — TODO(federation-9.9)")
