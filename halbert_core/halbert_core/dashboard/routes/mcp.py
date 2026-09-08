# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MCP API routes (Workstream B4 status; B5 config-edit endpoints).

``GET /api/mcp/status`` — one JSON view of the MCP client's world for
the dashboard: which servers are configured, which are connected, each
server's health and tool count, its B3 risk classification, and the
reconnection schedule the health monitor is holding a down server to.
The whole payload is assembled in :func:`halbert_core.mcp.health.
mcp_status_snapshot` so the route stays a thin, capability-gated wrap.

The config-edit endpoints (B5) — ``POST /api/mcp/servers``,
``DELETE /api/mcp/servers/{name}``, ``PUT /api/mcp/servers/{name}/risk``
— land every UI edit through the write path in :mod:`halbert_core.mcp.
config`, which validates with the SAME loader the agent reads, round-
trips the serialization before the atomic replace, and refuses to
introduce a literal token (the API carries an env var NAME, never a
value). Every error message is redacted before it is served.

The endpoints never 500s on a disabled capability: CAP_MCP_CLIENT off is
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
    from fastapi import APIRouter, HTTPException, Request
    FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - fastapi is a hard dep in prod
    FASTAPI_AVAILABLE = False
    APIRouter = object
    HTTPException = Exception
    Request = object

logger = logging.getLogger("halbert.dashboard.routes.mcp")

if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/mcp", tags=["mcp"])
else:
    router = None


def _capability_off_payload() -> Dict[str, Any]:
    """The honest empty state CAP_MCP_CLIENT-off serves (B4 status)."""
    return {
        "enabled": False,
        "monitor_running": False,
        "servers": [],
        "skipped_servers": [],
        "load_error": "",
    }


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
        return _capability_off_payload()
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


# ---------------------------------------------------------------------------
# B5: config-edit endpoints. Every edit lands in the write path
# (mcp.config), which validates with the loader the agent reads, round-
# trips the serialization before the atomic replace, and refuses to
# introduce a literal token. The route is a thin, capability-gated wrap
# that maps the write path's exceptions to 4xx with redacted detail.
#
# A config edit while CAP_MCP_CLIENT is off is a 409, not a silent
# success: the capability gate is the user's intent that MCP is inert,
# and writing servers behind that gate would surprise the next reader.
# ---------------------------------------------------------------------------

def _require_mcp() -> None:
    """Raise 409 when MCP is off, 503 when the mcp package is broken."""
    from ...capabilities import CAP_MCP_CLIENT, has_capability
    if not has_capability(CAP_MCP_CLIENT):
        raise HTTPException(
            status_code=409,
            detail="MCP client capability is disabled (CAP_MCP_CLIENT)")


def _serve_write_error(e: Exception) -> None:
    """Map a write-path exception to a 400 with a redacted detail.

    ``ConfigWriteError`` and ``ValueError`` are the write path's
    "nothing was written" signals (validation refusal, duplicate name,
    missing server, invalid risk level). Any other exception is a 500
    we did not intend to raise from the write path — logged, never
    surfaced raw.
    """
    from ...mcp.config import ConfigWriteError, redact
    if isinstance(e, (ConfigWriteError, ValueError)):
        raise HTTPException(status_code=400, detail=redact(str(e)))
    logger.error("MCP config write failed unexpectedly: %s", e, exc_info=True)
    raise HTTPException(status_code=500, detail="config write failed")


@router.post("/servers")
async def mcp_add_server(request: Request) -> Dict[str, Any]:
    """Add one MCP server to ``mcp_config.yml``.

    Body: a single server entry (the shape ``mcp_config.yml``'s
    ``servers:`` list stores). The write path validates it with the
    loader, serializes the canonical form, round-trips it, and atomically
    replaces the file. A name that duplicates an existing one (exactly
    or after sanitization) is a 400. A literal ``auth.token`` in the
    body is a 400 — the API carries ``auth.token_env`` (an env var
    NAME), never a token value, so a secret typed into a web form is
    not persisted to disk in the first place.

    Returns the fresh ``mcp_status_snapshot`` so the dashboard updates
    in one round-trip (the write changed the file identity; the snapshot
    re-reads it).
    """
    _require_mcp()
    try:
        from ...mcp.config import add_server_entry
        body = await request.json()
    except Exception as e:  # malformed JSON
        raise HTTPException(status_code=400, detail="request body is not valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="server entry must be a JSON object")
    # Refuse to introduce a literal token through the API — the
    # token_env flow exists so a secret typed into a web form is not
    # persisted to disk in the first place.
    _reject_literal_token(body)
    try:
        add_server_entry(body)
    except Exception as e:
        _serve_write_error(e)
    return _snapshot_or_empty()


@router.delete("/servers/{name}")
async def mcp_remove_server(name: str) -> Dict[str, Any]:
    """Remove every server written as *name* from ``mcp_config.yml``.

    The loader keeps the first of a duplicate pair, so removing by exact
    raw name is the operator's own intent. A name that is not configured
    is a 400 (never a silent no-op). Returns the fresh status snapshot.
    """
    _require_mcp()
    try:
        from ...mcp.config import remove_server_entry
        remove_server_entry(name)
    except Exception as e:
        _serve_write_error(e)
    return _snapshot_or_empty()


@router.put("/servers/{name}/risk")
async def mcp_set_risk(name: str, request: Request) -> Dict[str, Any]:
    """Set (or clear, with null) one server's B3 risk override keys.

    Body: ``{"risk_override": "high" | null, "tool_risk":
    {"tool": "critical"} | null}``. Every other key of the entry —
    including a literal ``auth.token`` the user hand-wrote — is
    preserved untouched. An invalid level name is a 400; a server that
    is not configured is a 400. Returns the fresh status snapshot.
    """
    _require_mcp()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="request body is not valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="risk body must be a JSON object")
    risk_override = body.get("risk_override", None)
    tool_risk = body.get("tool_risk", None)
    if risk_override is not None and not isinstance(risk_override, str):
        raise HTTPException(status_code=400, detail="risk_override must be a string or null")
    if tool_risk is not None and not isinstance(tool_risk, dict):
        raise HTTPException(status_code=400, detail="tool_risk must be a mapping or null")
    if tool_risk is not None:
        for tool, level in tool_risk.items():
            if not isinstance(tool, str) or not isinstance(level, str):
                raise HTTPException(
                    status_code=400,
                    detail="tool_risk keys and values must be strings")
    try:
        from ...mcp.config import set_risk_overrides
        set_risk_overrides(name, risk_override, tool_risk)
    except Exception as e:
        _serve_write_error(e)
    return _snapshot_or_empty()


def _reject_literal_token(body: Dict[str, Any]) -> None:
    """Refuse a body that would introduce a literal ``auth.token``.

    The dashboard API carries an env var NAME (``token_env``), never a
    token value. A literal ``token`` the user hand-wrote into an
    existing file is PRESERVED on an unrelated edit (it stays in the
    file it was already in), but a write that would INTRODUCE one
    through the API is refused — the token_env flow exists so a secret
    typed into a web form is not persisted to disk in the first place.
    """
    auth = body.get("auth")
    if isinstance(auth, dict) and auth.get("token"):
        raise HTTPException(
            status_code=400,
            detail="a literal auth.token is not accepted; use auth.token_env "
                   "(an environment variable name) instead")


def _snapshot_or_empty() -> Dict[str, Any]:
    """The fresh status snapshot after a successful write, or an honest
    empty payload if the snapshot itself broke (the write still landed)."""
    try:
        from ...mcp.health import mcp_status_snapshot
        return mcp_status_snapshot()
    except Exception as e:
        from ...mcp.config import redact
        logger.warning("MCP status snapshot after write failed: %s", e)
        payload = _capability_off_payload()
        payload["enabled"] = True
        payload["load_error"] = f"status snapshot failed: {redact(str(e))}"
        return payload
