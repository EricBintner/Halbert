# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Phase 4b — HTTP/SSE transport + bearer auth."""
from __future__ import annotations

import http.client
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp.server import MCPServer, generate_bearer_token, _make_http_handler
from http.server import HTTPServer


@pytest.fixture
def http_server_factory():
    """Factory that starts an HTTP server on a free port and returns its URL + token."""
    servers = []

    def _start(token: str = "", host: str = "127.0.0.1", cors_origin: str = ""):
        mcp = MCPServer(instance_name="test", hostname="test-host")
        handler = _make_http_handler(mcp, token, cors_origin=cors_origin)
        # Port 0 = OS picks a free port
        httpd = HTTPServer((host, 0), handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        servers.append((httpd, thread))
        return f"http://{host}:{port}", token

    yield _start

    for httpd, thread in servers:
        httpd.shutdown()
        thread.join(timeout=2)


def _post(url: str, body: dict, token: str = "") -> tuple[int, dict | None]:
    """POST a JSON-RPC request and return (status_code, response_json or None)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            if raw:
                return resp.status, json.loads(raw)
            return resp.status, None
    except urllib.error.HTTPError as e:
        raw = e.read()
        if raw:
            return e.code, json.loads(raw)
        return e.code, None


class TestBearerTokenGeneration:
    def test_generate_bearer_token_returns_string(self):
        token = generate_bearer_token()
        assert isinstance(token, str)
        assert len(token) >= 32

    def test_generate_bearer_token_unique(self):
        t1 = generate_bearer_token()
        t2 = generate_bearer_token()
        assert t1 != t2


class TestHTTPTransport:
    """HTTP JSON-RPC transport."""

    def test_initialize_no_auth(self, http_server_factory):
        """Open mode (no token) should accept requests."""
        url, _ = http_server_factory(token="")
        status, resp = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert status == 200
        assert resp["id"] == 1
        assert "result" in resp

    def test_initialize_with_valid_token(self, http_server_factory):
        """Valid bearer token should accept requests."""
        token = generate_bearer_token()
        url, _ = http_server_factory(token=token)
        status, resp = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token=token)
        assert status == 200
        assert "result" in resp

    def test_rejected_without_token(self, http_server_factory):
        """Missing Authorization header should return 401."""
        token = generate_bearer_token()
        url, _ = http_server_factory(token=token)
        status, resp = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert status == 401

    def test_rejected_with_wrong_token(self, http_server_factory):
        """Wrong bearer token should return 401."""
        token = generate_bearer_token()
        url, _ = http_server_factory(token=token)
        status, resp = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token="wrong")
        assert status == 401

    def test_tools_list_over_http(self, http_server_factory):
        """tools/list should work over HTTP."""
        url, _ = http_server_factory(token="")
        status, resp = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert status == 200
        tools = resp["result"]["tools"]
        assert len(tools) == 18

    def test_tool_call_over_http(self, http_server_factory):
        """tools/call should work over HTTP."""
        url, _ = http_server_factory(token="")
        status, resp = _post(url, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "get_vitals", "arguments": {}},
        })
        assert status == 200
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "error" in content or "cpu_percent" in content

    def test_notification_returns_202(self, http_server_factory):
        """Notifications (no id) should return 202."""
        url, _ = http_server_factory(token="")
        status, resp = _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert status == 202
        assert resp is None  # no body for 202

    def test_unknown_method_over_http(self, http_server_factory):
        """Unknown method should return error."""
        url, _ = http_server_factory(token="")
        status, resp = _post(url, {"jsonrpc": "2.0", "id": 4, "method": "bogus"})
        assert status == 200
        assert "error" in resp
        assert resp["error"]["code"] == -32601


class TestMultiInstance:
    """Multiple instances with different tokens."""

    def test_two_instances_separate_tokens(self, http_server_factory):
        """Two instances with different tokens should be isolated."""
        token1 = generate_bearer_token()
        token2 = generate_bearer_token()
        url1, _ = http_server_factory(token=token1)
        url2, _ = http_server_factory(token=token2)

        # Token1 works on instance1, fails on instance2
        s1, _ = _post(url1, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token=token1)
        assert s1 == 200

        s2, _ = _post(url2, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token=token1)
        assert s2 == 401

        # Token2 works on instance2, fails on instance1
        s3, _ = _post(url2, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token=token2)
        assert s3 == 200

        s4, _ = _post(url1, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, token=token2)
        assert s4 == 401


class TestRateLimiting:
    """Rate limiting prevents abuse from a single client IP."""

    def test_rate_limit_returns_429(self, http_server_factory):
        """After exceeding the rate limit, returns 429."""
        # Start with a low rate limit
        mcp = MCPServer(instance_name="test")
        handler = _make_http_handler(mcp, "", rate_limit=3)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{port}"
        try:
            # First 3 requests should succeed
            for _ in range(3):
                status, _ = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
                assert status == 200
            # 4th should be rate limited
            status, resp = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
            assert status == 429
        finally:
            httpd.shutdown()
            thread.join(timeout=2)


class TestCORS:
    """CORS is default-deny; an explicit origin is echoed with Vary."""

    def test_cors_default_deny_on_post(self, http_server_factory):
        """With no origin configured, POST responses carry no CORS headers."""
        url, _ = http_server_factory(token="")
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") is None

    def test_cors_explicit_origin_on_post(self, http_server_factory):
        """An explicit origin is echoed, with Vary: Origin."""
        url, _ = http_server_factory(token="", cors_origin="http://localhost:5173")
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
            assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")
            assert resp.headers.get("Vary") == "Origin"

    def test_options_preflight_default_deny(self, http_server_factory):
        """OPTIONS preflight returns 204 but no Allow-Origin by default."""
        url, _ = http_server_factory(token="")
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 204
            assert resp.headers.get("Access-Control-Allow-Origin") is None

    def test_options_preflight_explicit_origin(self, http_server_factory):
        """OPTIONS preflight echoes the configured origin."""
        url, _ = http_server_factory(token="", cors_origin="http://localhost:5173")
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 204
            assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


class TestRequestSizeLimit:
    """Request body size is limited."""

    def test_oversized_request_rejected(self, http_server_factory):
        """POST bodies larger than 1MB are rejected with 413."""
        url, _ = http_server_factory(token="")
        # Create a body larger than 1MB
        big_data = "x" * (1024 * 1024 + 100)
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"x": big_data}}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "Should have raised an error"
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            # HTTPError: server responded with 413 before reading body
            # URLError: broken pipe because server closed connection before
            #   the client finished sending the oversized body
            # Both are acceptable — the server rejected the request
            if isinstance(e, urllib.error.HTTPError):
                assert e.code == 413


def _raw_post(url: str, headers: dict, timeout: int = 5) -> http.client.HTTPResponse:
    """POST with hand-rolled headers (Content-Length: -1 etc.) that
    urllib refuses to send. Returns the response; the caller reads it."""
    p = urllib.parse.urlparse(url)
    conn = http.client.HTTPConnection(p.hostname, p.port, timeout=timeout)
    conn.putrequest("POST", "/")
    for name, value in headers.items():
        conn.putheader(name, value)
    conn.endheaders()
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp


class TestContentLengthHardening:
    """REV-02 F2 / REV-01 F6 — Content-Length is validated before reading.

    A negative value reaches rfile.read(-1) = read-until-EOF and pins a
    handler thread indefinitely; a non-integer raises unhandled.
    """

    def test_negative_content_length_rejected_413(self, http_server_factory):
        url, _ = http_server_factory(token="")
        resp = _raw_post(url, {
            "Content-Type": "application/json",
            "Content-Length": "-1",
        })
        assert resp.status == 413

    def test_non_integer_content_length_rejected_400(self, http_server_factory):
        url, _ = http_server_factory(token="")
        resp = _raw_post(url, {
            "Content-Type": "application/json",
            "Content-Length": "abc",
        })
        assert resp.status == 400


class TestRateLimitBeforeAuth:
    """REV-02 F3 — rate limiting runs before bearer auth.

    The 401 path (including token guessing) must consume rate-limit
    allowance; otherwise the unauthenticated surface is unthrottled.
    """

    def test_unauthenticated_flood_is_rate_limited(self):
        token = generate_bearer_token()
        mcp = MCPServer(instance_name="test")
        handler = _make_http_handler(mcp, token, rate_limit=3)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{port}"
        try:
            statuses = []
            for _ in range(4):
                status, _ = _post(
                    url, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                    token="wrong-token-that-is-long-enough-1234567890")
                statuses.append(status)
            # First three: auth fails (401) but the bucket fills; the
            # fourth is throttled before auth is even consulted.
            assert statuses == [401, 401, 401, 429]
        finally:
            httpd.shutdown()
            thread.join(timeout=2)


class TestNonASCIIBearerToken:
    """REV-02 F5 — a non-ASCII Authorization header fails closed (401).

    hmac.compare_digest raises TypeError on non-ASCII str; BaseHTTPRequestHandler
    decodes headers latin-1, so raw non-ASCII bytes survive into the token.
    The request thread must not crash.
    """

    def test_non_ascii_token_returns_401_not_crash(self, http_server_factory):
        token = generate_bearer_token()
        url, _ = http_server_factory(token=token)
        resp = _raw_post(url, {
            "Content-Type": "application/json",
            "Content-Length": "0",
            # "tëst" carries U+00EB — latin-1 encodable, non-ASCII.
            "Authorization": "Bearer tëst-tëst-tëst-tëst-tëst",
        })
        assert resp.status == 401


class TestSSESlotRelease:
    """REV-02 F4 — the SSE slot is released on every path.

    The old code wrote response headers outside the try/finally that
    released the slot, so a client that RST during the header write
    (BrokenPipeError before end of headers) leaked one of the 10 slots
    per race.
    """

    def _make_handler_obj(self, handler_cls):
        """A handler instance with just enough state for do_GET's early
        path (no real socket machinery — the write calls are patched)."""
        obj = object.__new__(handler_cls)
        obj.path = "/sse"
        obj.client_address = ("127.0.0.1", 0)
        obj.headers = {}
        return obj

    def test_header_write_failure_releases_slot(self, monkeypatch):
        mcp = MCPServer(instance_name="test")
        handler_cls = _make_http_handler(mcp, "", rate_limit=100)
        tracker = handler_cls._sse_connections

        def _raise(*args, **kwargs):
            raise BrokenPipeError("client reset during header write")

        monkeypatch.setattr(handler_cls, "send_response", _raise)
        monkeypatch.setattr(handler_cls, "send_header", _raise)
        monkeypatch.setattr(handler_cls, "end_headers", _raise)
        monkeypatch.setattr(handler_cls, "_send_sse", _raise)

        # More races than the 10-slot cap: with the leak, the 11th call
        # would return a 503 path and the cap would be gone forever.
        for _ in range(12):
            obj = self._make_handler_obj(handler_cls)
            obj.do_GET()  # must not raise

        assert tracker._current == 0
        # A fresh SSE connection can still acquire a slot.
        assert tracker.acquire() is True
        tracker.release()
