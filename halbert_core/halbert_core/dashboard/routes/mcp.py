# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP status API routes (Workstream B4; B5 renders the payload).

``GET /api/mcp/status`` — one JSON view of the MCP client's world for
the dashboard: which servers are configured, which are connected, each
server's health and tool count, its B3 risk classification, and the
reconnection schedule the health monitor is holding a down server to.
The whole payload is assembled in :func:`halbert_core.mcp.health.
mcp_status_snapshot` so the route stays a thin, capability-gated wrap.

The endpoint never 500s on a disabled capability: CAP_MCP_CLIENT off is
an honest empty state (the same shape the frontend renders as "MCP is
off"), not an error. The mcp package is imported only inside the
capability check — the subtractive contract (a capability-off body
never pays for it) — and every mcp-written string in the payload was
redacted where it was produced (config.redact / the client's scrubbing),
and the route's own fallback message is redacted at serve time.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from fastapi import APIRouter
    FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - fastapi is a hard dep in prod
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("halbert.dashboard.routes.mcp")

if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/mcp", tags=["mcp"])
else:
    router = None


@router.get("/status")
async def mcp_status() -> Dict[str, Any]:
    """Connected MCP servers, their health and tool counts.

    Shape (see mcp/health.py's snapshot docstring): ``enabled``,
    ``monitor_running``, per-server ``name``/``transport``/``configured``
    /``connected``/``health``/``last_error`` (redacted)/``tool_count``
    /``reconnect_attempts``/``backoff_seconds``/``next_retry_in``/risk
    fields, plus the B3 fail-closed context (``skipped_servers``,
    ``load_error``, ``default_risk``).
    """
    from ...capabilities import CAP_MCP_CLIENT, has_capability
    if not has_capability(CAP_MCP_CLIENT):
        return {
            "enabled": False,
            "monitor_running": False,
            "servers": [],
            "skipped_servers": [],
            "load_error": "",
        }
    try:
        from ...mcp.health import mcp_status_snapshot
        return mcp_status_snapshot()
    except Exception as e:
        # The status page must not become the thing that breaks: a
        # broken snapshot is an honest "unknown" payload, not a 500. The
        # detail is redacted WHERE SERVED (an exception message can carry
        # paths or credential-bearing URLs) and kept in the log.
        from ...mcp.config import redact
        logger.warning("MCP status snapshot failed: %s", e)
        return {
            "enabled": True,
            "monitor_running": False,
            "servers": [],
            "skipped_servers": [],
            "load_error": f"status snapshot failed: {redact(str(e))}",
        }