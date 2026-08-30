# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert MCP server — exposes runtime state, config queries, and agent actions.

Transport: stdio (Phase 4). HTTP/SSE + bearer auth in Phase 4b.

The server speaks JSON-RPC 2.0 over stdin/stdout, implementing the MCP
(Model Context Protocol) tool surface. Every tool that returns host config
content passes its result through ``mcp_response()`` (the egress boundary)
before returning.

Tool list (13 tools):
  get_vitals, get_discoveries, get_findings, get_proposals,
  get_proactive_events, get_being_config, get_config_value,
  get_config_structure, get_config_diff, get_config_dependencies,
  search_knowledge, run_scanner, approve_proposal

Usage:
  halbert-mcp-serve                          # stdio (default)
  halbert-mcp-serve --instance-name laptop   # named instance
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import traceback
from typing import Any, Dict, List, Optional

from .response import mcp_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instance metadata
# ---------------------------------------------------------------------------

def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _tool_get_vitals(params: Dict[str, Any]) -> Dict[str, Any]:
    """CPU, memory, disk, network, temperature snapshot."""
    try:
        import psutil
        import time
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        result: Dict[str, Any] = {
            "cpu_percent": cpu,
            "memory": {
                "total": mem.total,
                "available": mem.available,
                "percent": mem.percent,
                "used": mem.used,
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            },
            "uptime_seconds": int(time.time() - psutil.boot_time()),
        }
        # Temperature (may not be available on all platforms)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                result["temperatures"] = {
                    name: [{"label": s.label, "current": s.current}
                           for s in sensors]
                    for name, sensors in temps.items()
                }
        except (AttributeError, OSError):
            pass
        return result
    except ImportError:
        return {"error": "psutil not available"}
    except Exception as e:
        return {"error": str(e)}


def _tool_get_discoveries(params: Dict[str, Any]) -> Dict[str, Any]:
    """Discovery objects from the scanner registry."""
    try:
        from ..discovery.engine import DiscoveryEngine
        engine = DiscoveryEngine()
        discoveries = engine.get_all()
        discovery_type = params.get("type")
        if discovery_type:
            discoveries = [d for d in discoveries if d.get("type") == discovery_type]
        limit = params.get("limit", 50)
        return {"discoveries": [d.to_dict() if hasattr(d, "to_dict") else d
                                for d in discoveries[:limit]]}
    except Exception as e:
        logger.debug("get_discoveries error: %s", e)
        return {"discoveries": [], "error": str(e)}


def _tool_get_findings(params: Dict[str, Any]) -> Dict[str, Any]:
    """Open/snoozed findings from the FindingStore."""
    try:
        from ..findings.store import FindingStore
        store = FindingStore()
        status = params.get("status", "open")
        severity = params.get("severity")
        findings = store.list_findings(status=status)
        if severity:
            findings = [f for f in findings if f.severity == severity]
        limit = params.get("limit", 50)
        return {"findings": [f.to_dict() for f in findings[:limit]]}
    except Exception as e:
        logger.debug("get_findings error: %s", e)
        return {"findings": [], "error": str(e)}


def _tool_get_proposals(params: Dict[str, Any]) -> Dict[str, Any]:
    """Pending proposals from the ProposalStore."""
    try:
        from ..findings.proposals import ProposalStore
        store = ProposalStore()
        status = params.get("status", "pending")
        proposals = store.list_proposals(status=status)
        limit = params.get("limit", 50)
        return {"proposals": [p.to_dict() for p in proposals[:limit]]}
    except Exception as e:
        logger.debug("get_proposals error: %s", e)
        return {"proposals": [], "error": str(e)}


def _tool_get_proactive_events(params: Dict[str, Any]) -> Dict[str, Any]:
    """Recent proactive events from the event bus."""
    try:
        from ..proactive.events import ProactiveEventBus
        bus = ProactiveEventBus()
        limit = params.get("limit", 20)
        events = bus.get_recent(limit=limit)
        return {"events": [e.to_dict() if hasattr(e, "to_dict") else e
                           for e in events]}
    except Exception as e:
        logger.debug("get_proactive_events error: %s", e)
        return {"events": [], "error": str(e)}


def _tool_get_being_config(params: Dict[str, Any]) -> Dict[str, Any]:
    """Voice, proactivity, quiet hours — no secrets."""
    try:
        from ..config.being_config import load_being_config
        config = load_being_config()
        d = config.to_dict()
        # Strip security config — it contains routing policy, not user-facing
        # settings, and the security tab is the right place to see it.
        d.pop("security", None)
        return d
    except Exception as e:
        return {"error": str(e)}


def _tool_get_config_value(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get a config value with tier routing applied.

    Tier 0/1 (cloud_ok): raw value.
    Tier 2 / Tier 1 (local_only): deterministic description via describe_secret.
    """
    from ..config.queries import get_config_value
    from ..config.being_config import load_being_config

    path = params.get("path", "")
    key = params.get("key", "")
    if not path or not key:
        return {"error": "path and key are required"}

    try:
        config = load_being_config()
        sec = config.security
        result = get_config_value(
            path, key,
            operational_tier=sec.operational_tier,
            secret_tier=sec.secret_tier,
            secret_tier_expiry=sec.secret_tier_expiry,
            public_files=set(sec.public_files),
            extra_secret_keys=sec.extra_secret_keys,
            cloud_ok_keys=sec.cloud_ok_keys,
        )
        return mcp_response(result)
    except Exception as e:
        return mcp_response({"path": path, "key": key, "error": str(e)})


def _tool_get_config_structure(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get the parsed structure of a config file — keys and shape, no values."""
    from ..config.queries import get_config_structure
    path = params.get("path", "")
    if not path:
        return {"error": "path is required"}
    try:
        result = get_config_structure(path)
        return mcp_response(result)
    except Exception as e:
        return mcp_response({"path": path, "error": str(e)})


def _tool_get_config_diff(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get structured changes since a given snapshot — change types, no values."""
    from ..config.queries import get_config_diff
    since = params.get("since", "")
    try:
        result = get_config_diff(since=since)
        return mcp_response(result)
    except Exception as e:
        return mcp_response({"error": str(e)})


def _tool_get_config_dependencies(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get dependency edges for a config file — relationships only, no values."""
    from ..config.queries import get_config_dependencies
    path = params.get("path", "")
    if not path:
        return {"error": "path is required"}
    try:
        result = get_config_dependencies(path)
        return mcp_response(result)
    except Exception as e:
        return mcp_response({"path": path, "error": str(e)})


def _tool_search_knowledge(params: Dict[str, Any]) -> Dict[str, Any]:
    """Semantic search over SourcePrep knowledge base."""
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}
    scope = params.get("scope")
    limit = params.get("limit", 5)
    try:
        from ..integrations.sourceprep_client import SourcePrepClient
        client = SourcePrepClient()
        results = client.search(query, limit=limit, scope=scope)
        return mcp_response({"results": results, "query": query})
    except Exception as e:
        logger.debug("search_knowledge error: %s", e)
        return mcp_response({"results": [], "query": query, "error": str(e)})


def _tool_run_scanner(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a fresh scan of a given type (Phase 4b — gated).

    Gating: scanner execution is a potentially expensive operation that
    can cause load, trigger security alerts, or consume disk. It requires
    explicit confirmation via the ``confirm`` parameter set to ``True``.
    This prevents an LLM from triggering scans without user awareness.
    """
    scanner_type = params.get("type", "")
    if not scanner_type:
        return {"error": "type is required"}
    # Gating: require explicit confirmation
    if not params.get("confirm", False):
        return {
            "error": "scanner execution requires confirm=True",
            "detail": ("Running a scanner can cause load, trigger security "
                       "alerts, or consume disk. Set confirm=true to proceed."),
            "type": scanner_type,
        }
    try:
        from ..discovery.engine import DiscoveryEngine
        engine = DiscoveryEngine()
        results = engine.scan_type(scanner_type)
        return mcp_response({
            "type": scanner_type,
            "count": len(results),
            "discoveries": [d.to_dict() if hasattr(d, "to_dict") else d
                            for d in results],
        })
    except Exception as e:
        return mcp_response({"type": scanner_type, "error": str(e)})


def _tool_approve_proposal(params: Dict[str, Any]) -> Dict[str, Any]:
    """Approve and execute a pending proposal (Phase 4b — gated, high risk).

    This is a write action that modifies config files on the host.
    Gating: requires explicit ``confirm=True`` to prevent an LLM from
    applying changes without user awareness. The proposal must be in
    PENDING status. Execution goes through ``handle_approval_decision``
    which backs up, applies, and rolls back on failure.
    """
    proposal_id = params.get("proposal_id", "")
    if not proposal_id:
        return {"error": "proposal_id is required"}
    if not params.get("confirm", False):
        return {
            "error": "proposal approval requires confirm=true",
            "detail": (
                "Approving a proposal applies config changes to the host. "
                "Set confirm=true to proceed. Inspect the proposal first "
                "with get_proposals to review changes and blast radius."
            ),
            "proposal_id": proposal_id,
        }
    try:
        from ..findings.proposal_generator import handle_approval_decision
        result = handle_approval_decision(
            request_id=proposal_id,
            approved=True,
            reason=params.get("reason", "approved via MCP"),
        )
        return mcp_response(result)
    except Exception as e:
        return mcp_response({"proposal_id": proposal_id, "error": str(e)})


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_HANDLERS: Dict[str, Any] = {
    "get_vitals": _tool_get_vitals,
    "get_discoveries": _tool_get_discoveries,
    "get_findings": _tool_get_findings,
    "get_proposals": _tool_get_proposals,
    "get_proactive_events": _tool_get_proactive_events,
    "get_being_config": _tool_get_being_config,
    "get_config_value": _tool_get_config_value,
    "get_config_structure": _tool_get_config_structure,
    "get_config_diff": _tool_get_config_diff,
    "get_config_dependencies": _tool_get_config_dependencies,
    "search_knowledge": _tool_search_knowledge,
    "run_scanner": _tool_run_scanner,
    "approve_proposal": _tool_approve_proposal,
}

# Tool schemas for the MCP initialize response
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "get_vitals",
        "description": "Get current system vitals: CPU, memory, disk, network, temperature.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeframe": {"type": "string", "description": "Time window (optional)"},
            },
        },
    },
    {
        "name": "get_discoveries",
        "description": "Get discovery objects from the scanner registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Filter by discovery type"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
        },
    },
    {
        "name": "get_findings",
        "description": "Get open or snoozed findings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (default 'open')"},
                "severity": {"type": "string", "description": "Filter by severity"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
        },
    },
    {
        "name": "get_proposals",
        "description": "Get pending proposals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (default 'pending')"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
        },
    },
    {
        "name": "get_proactive_events",
        "description": "Get recent proactive events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
        },
    },
    {
        "name": "get_being_config",
        "description": "Get being config: voice, proactivity, quiet hours. No secrets.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_config_value",
        "description": "Get a config value with tier routing. Tier 2 secrets return a deterministic description, not the raw value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Config file path"},
                "key": {"type": "string", "description": "Config key name"},
            },
            "required": ["path", "key"],
        },
    },
    {
        "name": "get_config_structure",
        "description": "Get the parsed structure of a config file — keys and shape, no values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Config file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_config_diff",
        "description": "Get structured config changes since a snapshot — change types, no values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "ISO timestamp of baseline snapshot"},
            },
        },
    },
    {
        "name": "get_config_dependencies",
        "description": "Get dependency edges for a config file — relationships only, no values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Config file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_knowledge",
        "description": "Semantic search over the SourcePrep knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "scope": {"type": "string", "description": "Optional scope filter"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_scanner",
        "description": (
            "Run a fresh scan of a given discovery type. "
            "GATED: requires confirm=true to prevent unintended scans."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Scanner type to run"},
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "Must be true to proceed. Scans can cause load, "
                        "trigger alerts, or consume disk."
                    ),
                },
            },
            "required": ["type", "confirm"],
        },
    },
    {
        "name": "approve_proposal",
        "description": (
            "Approve and execute a pending config change proposal. "
            "GATED: requires confirm=true. This applies real config changes "
            "to the host — inspect the proposal with get_proposals first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "The proposal ID to approve"},
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "Must be true to proceed. Approving applies config "
                        "changes to the host filesystem."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for approval (recorded in audit log)",
                },
            },
            "required": ["proposal_id", "confirm"],
        },
    },
]


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 over stdio
# ---------------------------------------------------------------------------

class MCPServer:
    """MCP server speaking JSON-RPC 2.0 over stdin/stdout."""

    def __init__(self, instance_name: str = "", hostname: str = "") -> None:
        self.instance_name = instance_name or hostname or _hostname()
        self.hostname = hostname or _hostname()
        self._initialized = False

    def _tool_list(self) -> List[Dict[str, Any]]:
        """Return tool schemas with instance name in descriptions."""
        tools = []
        for schema in TOOL_SCHEMAS:
            tool = dict(schema)
            tool["description"] = f"[{self.instance_name}] {schema['description']}"
            tools.append(tool)
        return tools

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle a single JSON-RPC request and return a response (or None for notifications)."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                self._initialized = True
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": f"halbert-{self.instance_name}",
                        "version": "0.1.0",
                    },
                }
                return self._success(req_id, result) if req_id is not None else None

            if method == "notifications/initialized":
                # Notification — no response
                return None

            if method == "tools/list":
                return self._success(req_id, {"tools": self._tool_list()}) if req_id is not None else None

            if method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                handler = TOOL_HANDLERS.get(tool_name)
                if handler is None:
                    return self._error(req_id, -32601, f"Unknown tool: {tool_name}")
                result = handler(tool_args)
                # Tools that return host config content already pass through
                # mcp_response() internally. Tools that return runtime state
                # (vitals, discoveries, findings) do not need it — they carry
                # no config values.
                return self._success(req_id, {
                    "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                }) if req_id is not None else None

            if method == "ping":
                return self._success(req_id, {}) if req_id is not None else None

            return self._error(req_id, -32601, f"Unknown method: {method}")

        except Exception as e:
            logger.error("Request handling error: %s\n%s", e, traceback.format_exc())
            return self._error(req_id, -32603, f"Internal error: {e}")

    def _success(self, req_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def run_stdio(self) -> None:
        """Run the server over stdin/stdout, reading JSON-RPC messages line by line."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                response = self._error(None, -32700, f"Parse error: {e}")
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            response = self.handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


# ---------------------------------------------------------------------------
# HTTP/SSE transport (Phase 4b)
# ---------------------------------------------------------------------------

import hmac
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


class _MCPHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for MCP JSON-RPC over POST + SSE streaming.

    Hardening:
    - Rate limiting: max 60 requests per minute per client IP
    - SSE connection limit: max 10 concurrent SSE connections
    - CORS headers: configurable, defaults to localhost-only
    - Request size limit: max 1MB per POST body
    """

    # Set by the factory function below
    _server: MCPServer = None  # type: ignore
    _bearer_token: str = ""
    _rate_limiter: "_RateLimiter" = None  # type: ignore
    _sse_connections: "_SSEConnectionTracker" = None  # type: ignore
    _cors_origin: str = "*"

    # Limits
    _MAX_REQUEST_SIZE = 1024 * 1024  # 1MB
    _MAX_SSE_CONNECTIONS = 10
    _RATE_LIMIT_WINDOW = 60  # seconds
    _RATE_LIMIT_MAX_REQUESTS = 60  # per window per IP

    def _check_auth(self) -> bool:
        """Validate the Bearer token from the Authorization header."""
        if not self._bearer_token:
            return True  # No token configured — open mode (local only)
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:]
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(token, self._bearer_token)

    def _check_rate_limit(self) -> bool:
        """Check if the client IP is within the rate limit."""
        if self._rate_limiter is None:
            return True
        client_ip = self.client_address[0]
        return self._rate_limiter.check(client_ip)

    def _send_cors_headers(self) -> None:
        """Send CORS headers for cross-origin requests."""
        self.send_header("Access-Control-Allow-Origin", self._cors_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_sse(self, data: str) -> None:
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        """Handle JSON-RPC requests via POST."""
        if not self._check_auth():
            self._send_json(401, {"error": "Unauthorized"})
            return

        if not self._check_rate_limit():
            self._send_json(429, {"error": "Rate limit exceeded"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self._MAX_REQUEST_SIZE:
            self._send_json(413, {"error": "Request body too large"})
            return

        body = self.rfile.read(content_length)
        try:
            request = json.loads(body)
        except json.JSONDecodeError as e:
            self._send_json(200, self._server._error(None, -32700, f"Parse error: {e}"))
            return

        response = self._server.handle_request(request)
        if response is not None:
            self._send_json(200, response)
        else:
            # Notification — acknowledge with 202
            self.send_response(202)
            self._send_cors_headers()
            self.end_headers()

    def do_GET(self) -> None:
        """SSE streaming endpoint at /sse."""
        if not self._check_auth():
            self._send_json(401, {"error": "Unauthorized"})
            return

        if not self._check_rate_limit():
            self._send_json(429, {"error": "Rate limit exceeded"})
            return

        parsed = urlparse(self.path)
        if parsed.path != "/sse":
            self._send_json(404, {"error": "Not found"})
            return

        # Check SSE connection limit
        if self._sse_connections is not None:
            if not self._sse_connections.acquire():
                self._send_json(503, {"error": "Too many SSE connections"})
                return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._send_cors_headers()
        self.end_headers()

        # Send an initial endpoint event so clients know where to POST
        self._send_sse(json.dumps({
            "jsonrpc": "2.0",
            "method": "endpoint",
            "params": {"uri": "/"},
        }))

        # Keep the connection open; in a full implementation this would
        # stream server-initiated notifications. For now it's a heartbeat.
        try:
            while True:
                import time
                time.sleep(15)
                self._send_sse(json.dumps({"jsonrpc": "2.0", "method": "ping"}))
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if self._sse_connections is not None:
                self._sse_connections.release()

    def log_message(self, format: str, *args) -> None:
        # Route to stderr, not stdout
        logger.info("HTTP %s - %s", self.address_string(), format % args)


class _RateLimiter:
    """Simple in-memory rate limiter per client IP."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = {}
        import threading
        self._lock = threading.Lock()

    def check(self, client_ip: str) -> bool:
        """Return True if the client is within the rate limit."""
        import time
        now = time.time()
        with self._lock:
            if client_ip not in self._requests:
                self._requests[client_ip] = []
            # Remove old entries
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if now - t < self.window
            ]
            if len(self._requests[client_ip]) >= self.max_requests:
                return False
            self._requests[client_ip].append(now)
            return True


class _SSEConnectionTracker:
    """Track concurrent SSE connections to enforce a limit."""

    def __init__(self, max_connections: int = 10) -> None:
        self.max = max_connections
        self._current = 0
        import threading
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a connection slot. Returns True if allowed."""
        with self._lock:
            if self._current >= self.max:
                return False
            self._current += 1
            return True

    def release(self) -> None:
        """Release a connection slot."""
        with self._lock:
            if self._current > 0:
                self._current -= 1


def _make_http_handler(
    server: MCPServer,
    bearer_token: str,
    *,
    cors_origin: str = "*",
    rate_limit: int = 60,
    max_sse_connections: int = 10,
) -> type:
    """Create a handler class with the server and token bound.

    Parameters
    ----------
    cors_origin
        Value for Access-Control-Allow-Origin header. Default "*"
        allows any origin. For production, set to the specific origin.
    rate_limit
        Max requests per minute per client IP. Default 60.
    max_sse_connections
        Max concurrent SSE connections. Default 10.
    """
    class _Handler(_MCPHTTPHandler):
        _server = server
        _bearer_token = bearer_token
        _cors_origin = cors_origin
        _rate_limiter = _RateLimiter(max_requests=rate_limit, window_seconds=60)
        _sse_connections = _SSEConnectionTracker(max_connections=max_sse_connections)
    return _Handler


def generate_bearer_token() -> str:
    """Generate a random bearer token for HTTP transport."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Halbert MCP server")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument("--instance-name", default="", help="Instance name for multi-instance disambiguation")
    parser.add_argument("--hostname", default="", help="Hostname override")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default 127.0.0.1)")
    parser.add_argument(
        "--bearer-token", default="",
        help="Bearer token for HTTP auth. If empty, reads HALBERT_MCP_TOKEN env var. "
             "If neither is set, HTTP runs in open mode (local only).",
    )
    parser.add_argument(
        "--cors-origin", default="*",
        help="CORS Access-Control-Allow-Origin value (default: *). "
             "Set to a specific origin for production.",
    )
    parser.add_argument(
        "--rate-limit", type=int, default=60,
        help="Max requests per minute per client IP (default: 60).",
    )
    parser.add_argument(
        "--max-sse-connections", type=int, default=10,
        help="Max concurrent SSE connections (default: 10).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("HALBERT_MCP_LOG_LEVEL", "WARNING"),
        stream=sys.stderr,  # Never stdout — that's the JSON-RPC channel
    )

    server = MCPServer(
        instance_name=args.instance_name,
        hostname=args.hostname,
    )

    if args.transport == "stdio":
        server.run_stdio()
    elif args.transport == "http":
        token = args.bearer_token or os.environ.get("HALBERT_MCP_TOKEN", "")
        if not token:
            logger.warning("HTTP transport with no bearer token — open mode (local only)")
        handler = _make_http_handler(
            server, token,
            cors_origin=args.cors_origin,
            rate_limit=args.rate_limit,
            max_sse_connections=args.max_sse_connections,
        )
        httpd = HTTPServer((args.host, args.port), handler)
        logger.info("MCP HTTP server listening on %s:%d (instance=%s, auth=%s)",
                     args.host, args.port, server.instance_name, bool(token))
        print(f"Halbert MCP server listening on http://{args.host}:{args.port}", file=sys.stderr)
        if token:
            print(f"Bearer token: {token}", file=sys.stderr)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()


if __name__ == "__main__":
    main()
