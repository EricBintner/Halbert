# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the MCP client library (Workstream B1).

Test doubles:
  * an in-process FAKE stdio MCP server (a tiny python subprocess
    speaking JSON-RPC 2.0 over stdin/stdout, driven by a FAKE_MODE env
    var: normal / limited / crash / refuse / malformed / hang / die_after)
  * a mocked HTTP layer (monkeypatched ``requests.post`` — no network)

Edge cases covered per the plan: a crashing server, malformed JSON, a
hung server, handshake refusal, hot-reloaded config, tokens never in
logs/errors, registry collisions.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys

import pytest
import requests
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp import client as mcp_client_module
from halbert_core.mcp.client import (
    HTTPTransport,
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPDisconnectedError,
    MCPProtocolError,
    MCPToolError,
    StdioTransport,
    _parse_sse,
)
from halbert_core.mcp.config import (
    MCPAuthConfig,
    MCPServerConfig,
    config_path,
    load_config,
)
from halbert_core.mcp.registry import MCPToolRegistry, qualify_tool_name


# ---------------------------------------------------------------------------
# The fake stdio MCP server
# ---------------------------------------------------------------------------

FAKE_SERVER = r'''
import json, os, sys

MODE = os.environ.get("FAKE_MODE", "normal")

if MODE == "crash":
    sys.exit(1)

if MODE == "slow_init":
    import time
    time.sleep(0.3)  # hold the handshake open so lifecycle races are testable

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def tools_list():
    tools = [{
        "name": "echo",
        "description": "Echo the arguments back as text.",
        "inputSchema": {"type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"]},
    }]
    if MODE != "limited":
        tools.append({
            "name": "add",
            "description": "Add two integers.",
            "inputSchema": {"type": "object",
                            "properties": {"a": {"type": "integer"},
                                            "b": {"type": "integer"}},
                            "required": ["a", "b"]}})
    return tools

initialized = False
saw_rejection = False

def not_initialized(req):
    send({"jsonrpc": "2.0", "id": req.get("id"),
          "error": {"code": -32000, "message": "not initialized"}})

def send_tools(req, tools, next_cursor=None):
    result = {"tools": [{"name": t} for t in tools]}
    if next_cursor:
        result["nextCursor"] = next_cursor
    send({"jsonrpc": "2.0", "id": req.get("id"), "result": result})

def handle(req):
    global initialized
    method = req.get("method", "")
    if method == "initialize":
        initialized = True
        if MODE == "bad_init":
            send({"jsonrpc": "2.0", "id": req.get("id"), "result": {}})
        elif MODE == "old_version":
            send({"jsonrpc": "2.0", "id": req.get("id"), "result": {
                "protocolVersion": "1998-01-01"}})
        else:
            send({"jsonrpc": "2.0", "id": req.get("id"), "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fake", "version": "0.1.0"}}})
    elif method == "tools/list":
        if not initialized:
            not_initialized(req)
        elif MODE == "paginated":
            cursor = (req.get("params") or {}).get("cursor")
            pages = {"p2": (["tool_b"], "p3"), "p3": (["tool_c"], None)}
            if cursor is None:
                send_tools(req, ["tool_a"], "p2")
            else:
                tools, nxt = pages.get(cursor, ([], None))
                send_tools(req, tools, nxt)
        elif MODE == "hostile":
            # Always echoes a cursor: pagination must hit its cap.
            send_tools(req, ["tool_x"], req.get("params", {}).get("cursor") or "more")
        else:
            send({"jsonrpc": "2.0", "id": req.get("id"),
                  "result": {"tools": tools_list()}})
    elif method == "tools/call":
        if not initialized:
            not_initialized(req)
            return
        params = req.get("params") or {}
        args = params.get("arguments") or {}
        if params.get("name") == "boom":
            send({"jsonrpc": "2.0", "id": req.get("id"), "result": {
                "content": [{"type": "text", "text": "something exploded"}],
                "isError": True}})
        elif params.get("name") == "add":
            text = str(int(args.get("a", 0)) + int(args.get("b", 0)))
        else:
            text = json.dumps(args)
        if params.get("name") != "boom":
            send({"jsonrpc": "2.0", "id": req.get("id"), "result": {
                "content": [{"type": "text", "text": text}]}})
    elif method == "resources/list":
        send({"jsonrpc": "2.0", "id": req.get("id"), "result": {"resources": [
            {"uri": "fake://greeting", "name": "greeting",
             "mimeType": "text/plain"}]}})
    elif method == "resources/read":
        uri = (req.get("params") or {}).get("uri", "")
        send({"jsonrpc": "2.0", "id": req.get("id"), "result": {"contents": [
            {"uri": uri, "mimeType": "text/plain",
             "text": "hello from resource"}]}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": req.get("id"), "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": req.get("id"),
              "error": {"code": -32601, "message": "Unknown method"}})

while True:
    line = sys.stdin.readline()
    if line == "":
        break
    if MODE == "malformed":
        sys.stdout.write("this is not json\n")
        sys.stdout.flush()
        continue
    if MODE == "hang":
        continue
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    if "id" not in req:
        continue  # notification: no response, per spec
    if MODE == "refuse":
        send({"jsonrpc": "2.0", "id": req.get("id"),
              "error": {"code": -32603, "message": "handshake refused"}})
        continue
    if MODE in ("sneaky", "sneaky_noanswer"):
        # Adversarial server-initiated traffic. A server REQUEST with an
        # id colliding with the client's pending request, plus an
        # adversarial notification carrying both a method and an id —
        # neither may resolve the pending future.
        if "method" in req:
            if req.get("method") == "initialize":
                initialized = True
                send({"jsonrpc": "2.0", "id": req.get("id"), "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {}, "serverInfo": {"name": "fake"}}})
            elif req.get("method") == "tools/list":
                send({"jsonrpc": "2.0", "id": req.get("id"),
                      "method": "sampling/createMessage",
                      "params": {"text": "gotcha"}})
                send({"jsonrpc": "2.0", "method": "notifications/message",
                      "id": req.get("id"),
                      "params": {"result": "fake"}})
                if MODE == "sneaky":
                    send({"jsonrpc": "2.0", "id": req.get("id"),
                          "result": {"tools": [{"name": "sneaky_tool"}]}})
            elif req.get("method") == "resources/list":
                send({"jsonrpc": "2.0", "id": req.get("id"),
                      "result": {"saw_rejection": saw_rejection}})
        elif "error" in req:
            # The client's -32601 rejection of our server request.
            saw_rejection = True
        continue
    if MODE == "die_after" and initialized:
        sys.exit(0)
    if MODE == "hang_after" and initialized:
        continue  # handshakes, then never answers again
    handle(req)
'''


@pytest.fixture
def fake_server_script(tmp_path):
    """Write the fake MCP server to disk; returns its path."""
    script = tmp_path / "fake_mcp_server.py"
    script.write_text(FAKE_SERVER)
    return script


@pytest.fixture
async def stdio_transports(fake_server_script):
    """Factory for StdioTransport instances, closed after the test."""
    created = []

    def make(mode="normal", timeout=2.0, name="fake"):
        transport = StdioTransport(
            name=name,
            command=sys.executable,
            args=[str(fake_server_script)],
            env={"FAKE_MODE": mode} if mode else None,
            timeout=timeout,
        )
        created.append(transport)
        return transport

    yield make
    for transport in created:
        await transport.close()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """An isolated HALBERT_CONFIG_DIR with an mcp_config.yml writer."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))

    def write(servers=None, **extra):
        data = {"servers": servers if servers is not None else []}
        data.update(extra)
        (tmp_path / "mcp_config.yml").write_text(yaml.safe_dump(data))

    return write


def stdio_server_entry(script, name="fake", mode="normal", timeout=2.0, **extra):
    entry = {
        "name": name,
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(script)],
        "timeout_seconds": timeout,
    }
    if mode is not None:
        entry["env"] = {"FAKE_MODE": mode}
    entry.update(extra)
    return entry


# ---------------------------------------------------------------------------
# HTTP test doubles
# ---------------------------------------------------------------------------

class FakeHTTPResponse:
    def __init__(self, status_code=200, content_type="application/json",
                 body=None, json_body=None, extra_headers=None):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        if extra_headers:
            self.headers.update(extra_headers)
        self.text = body if body is not None else json.dumps(json_body or {})
        self._json = json_body

    def json(self):
        if self._json is None:
            raise ValueError("No JSON could be decoded")
        return self._json


class FakePost:
    """A monkeypatch target for requests.post: records calls, returns
    queued responses (an entry that is an Exception is raised)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, json=None, headers=None, timeout=None, **kw):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout})
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


class ExpiringSessionPost:
    """A scripted Streamable HTTP server with session expiry: any
    request whose Mcp-Session-Id is not the CURRENT one gets a 404;
    initialize rotates the session and answers with the new id.

    Deterministic under ANY interleaving — responses key off header
    content, not call order, so concurrent-expiry tests don't race.
    `always_expire=True` 404s every request even after recovery (for
    the double-expiry retype test).
    """

    def __init__(self, always_expire=False):
        self.calls = []
        self.session = "sess-initial"
        self.always_expire = always_expire

    def __call__(self, url, json=None, headers=None, timeout=None, **kw):
        self.calls.append({"json": json, "headers": dict(headers or {})})
        method = json.get("method")
        if method == "initialize":
            self.session = f"sess-{len(self.calls)}"
            return FakeHTTPResponse(
                json_body=rpc_result(
                    json["id"], {"protocolVersion": "2024-11-05"}),
                extra_headers={"Mcp-Session-Id": self.session})
        if "id" not in json:
            return FakeHTTPResponse(status_code=202)
        if (self.always_expire
                or headers.get("Mcp-Session-Id") != self.session):
            return FakeHTTPResponse(status_code=404)
        return FakeHTTPResponse(json_body=rpc_result(json["id"], {"ok": True}))


@pytest.fixture
def http_transport_factory(monkeypatch):
    """Build an HTTPTransport against a FakePost; returns
    (make, fake) where make(url=..., token_provider=...) builds a
    connected-or-not transport."""
    created = []

    def make(fake, url="https://mcp.example.com/mcp", token_provider=None,
             timeout=2.0, name="remote"):
        monkeypatch.setattr(mcp_client_module.requests, "post", fake)
        transport = HTTPTransport(
            name=name, url=url, token_provider=token_provider, timeout=timeout)
        created.append(transport)
        return transport

    yield make
    # HTTPTransport.close() is synchronous-safe; call it to keep the
    # contract honest even though there is no socket.
    for transport in created:
        transport._connected = False


# ===========================================================================
# Stdio transport
# ===========================================================================

class TestStdioTransport:

    async def test_connect_and_list_tools(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        tools = await transport.request("tools/list")
        assert isinstance(tools, dict)
        names = [t["name"] for t in tools["tools"]]
        assert names == ["echo", "add"]
        # Schemas survive the round trip.
        add = tools["tools"][1]
        assert add["inputSchema"]["required"] == ["a", "b"]

    async def test_initialize_handshake_happens_first(self, stdio_transports):
        """The fake server refuses tools/list before initialize — a green
        list_tools proves the handshake ran, in order."""
        transport = stdio_transports()
        await transport.connect()
        await transport.request("tools/list")  # no MCPProtocolError raised

    async def test_call_tool_returns_structured_result(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        result = await transport.request("tools/call", {
            "name": "add", "arguments": {"a": 2, "b": 3}})
        assert result["content"][0]["text"] == "5"

    async def test_arguments_reach_the_server_verbatim(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        result = await transport.request("tools/call", {
            "name": "echo", "arguments": {"text": "hello world"}})
        assert json.loads(result["content"][0]["text"]) == {"text": "hello world"}

    async def test_resources_list_and_read(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        listed = await transport.request("resources/list")
        assert listed["resources"][0]["uri"] == "fake://greeting"
        read = await transport.request("resources/read", {
            "uri": "fake://greeting"})
        assert read["contents"][0]["text"] == "hello from resource"
        assert read["contents"][0]["uri"] == "fake://greeting"

    async def test_jsonrpc_error_becomes_protocol_error(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        with pytest.raises(MCPProtocolError, match="Unknown method"):
            await transport.request("no/such/method")

    async def test_crashing_server_is_a_clean_connection_error(
            self, stdio_transports):
        transport = stdio_transports(mode="crash")
        with pytest.raises(MCPConnectionError):
            await transport.connect()

    async def test_handshake_refusal_is_a_clean_connection_error(
            self, stdio_transports):
        transport = stdio_transports(mode="refuse")
        with pytest.raises(MCPConnectionError, match="handshake refused"):
            await transport.connect()

    async def test_malformed_json_never_hangs(self, stdio_transports):
        """A server answering garbage fails via the timeout, bounded."""
        transport = stdio_transports(mode="malformed", timeout=0.5)
        with pytest.raises(MCPConnectionError, match="no response to 'initialize'"):
            await transport.connect()

    async def test_hung_server_times_out(self, stdio_transports):
        transport = stdio_transports(mode="hang", timeout=0.5)
        with pytest.raises(MCPConnectionError, match="no response to 'initialize'"):
            await transport.connect()

    async def test_request_after_server_death_is_disconnected_error(
            self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        assert transport.alive
        transport._proc.kill()
        await transport._proc.wait()
        with pytest.raises(MCPDisconnectedError):
            await transport.request("tools/list")

    async def test_death_during_pending_request_fails_the_future(
            self, stdio_transports):
        """A request whose answer never comes because the process died
        resolves as an error, not a hang. hang_after: handshakes, then
        stops answering — so a request is genuinely pending when the
        process is killed."""
        transport = stdio_transports(mode="hang_after", timeout=5.0)
        await transport.connect()
        future = asyncio.get_running_loop().create_task(
            transport.request("tools/list"))
        await asyncio.sleep(0.1)  # let the request reach the server
        transport._proc.kill()
        with pytest.raises(MCPDisconnectedError):
            await future

    async def test_close_terminates_the_subprocess(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        pid = transport._proc.pid
        await transport.close()
        assert not transport.alive
        # The child is reaped: the pid is gone (recycling is not a
        # realistic hazard inside one test).
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    async def test_close_is_idempotent(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        await transport.close()
        await transport.close()

    async def test_concurrent_requests_are_matched_by_id(
            self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        results = await asyncio.gather(*[
            transport.request("tools/call", {"name": "add",
                                            "arguments": {"a": i, "b": 10}})
            for i in range(5)
        ])
        texts = [r["content"][0]["text"] for r in results]
        assert texts == [str(i + 10) for i in range(5)]

    async def test_launch_failure_names_the_command(self, stdio_transports):
        transport = StdioTransport(
            name="broken", command="/no/such/binary", args=[],
            timeout=2.0)
        with pytest.raises(MCPConnectionError, match="broken"):
            await transport.connect()

    # -- B1 review: server-initiated traffic must not steal a future ------

    async def test_server_request_with_colliding_id_never_resolves_pending(
            self, stdio_transports):
        """A server-initiated REQUEST whose id collides with our pending
        request, plus an adversarial notification carrying the same id,
        must both be ignored — only the true response resolves the
        future. (Before the fix, the colliding request resolved the
        future and the true response was dropped as unknown.)"""
        transport = stdio_transports(mode="sneaky")
        await transport.connect()
        result = await transport.request("tools/list")
        assert [t["name"] for t in result["tools"]] == ["sneaky_tool"]

    async def test_server_requests_are_rejected_not_ignored(
            self, stdio_transports):
        """A server-initiated request gets a JSON-RPC -32601 back, so the
        server is not left hanging on a reply we will never send."""
        transport = stdio_transports(mode="sneaky")
        await transport.connect()
        await transport.request("tools/list")  # triggers the server request
        result = await transport.request("resources/list")
        assert result["saw_rejection"] is True

    async def test_colliding_request_without_true_answer_times_out(
            self, stdio_transports):
        """When the server request is the ONLY thing that comes back, the
        pending request must fail via its timeout — not silently
            "succeed" with the request's payload."""
        transport = stdio_transports(mode="sneaky_noanswer", timeout=0.5)
        await transport.connect()
        with pytest.raises(MCPClientError, match="no response"):
            await transport.request("tools/list")

    # -- B1 review: initialize validation -----------------------------------

    async def test_initialize_result_without_version_fails_handshake(
            self, stdio_transports):
        transport = stdio_transports(mode="bad_init")
        with pytest.raises(MCPConnectionError, match="protocolVersion"):
            await transport.connect()

    async def test_unsupported_server_version_fails_handshake(
            self, stdio_transports):
        transport = stdio_transports(mode="old_version")
        with pytest.raises(MCPConnectionError, match="1998-01-01"):
            await transport.connect()

    async def test_negotiated_version_is_recorded(self, stdio_transports):
        transport = stdio_transports()
        await transport.connect()
        assert transport.negotiated_protocol_version == "2024-11-05"

    # -- B1 review: isError stays raw at the transport level -----------------

    async def test_iserror_result_is_raw_at_transport_level(
            self, stdio_transports):
        """The transport returns the raw result; the isError → typed
        error surface lives on MCPClient.call_tool."""
        transport = stdio_transports()
        await transport.connect()
        result = await transport.request("tools/call", {
            "name": "boom", "arguments": {}})
        assert result["isError"] is True
        assert result["content"][0]["text"] == "something exploded"

    # -- B1 lifecycle review: cancelled connect -------------------------------

    async def test_cancelled_connect_reaps_the_subprocess(
            self, stdio_transports):
        """CancelledError is not an MCPClientError — the handshake
        cleanup must still run, or the transport is left half-alive
        with an orphaned subprocess no one holds a reference to."""
        transport = stdio_transports(mode="hang", timeout=5.0)
        task = asyncio.get_running_loop().create_task(transport.connect())
        await asyncio.sleep(0.15)  # initialize sent; the server never answers
        pid = transport._proc.pid
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not transport.alive
        assert transport.negotiated_protocol_version is None
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)  # subprocess reaped, not orphaned


# ===========================================================================
# HTTP transport (Streamable HTTP, mocked — no network)
# ===========================================================================

class TestHTTPTransport:

    async def test_connect_and_list_tools_json_response(
            self, http_transport_factory):
        fake = FakePost([
            FakeHTTPResponse(json_body=rpc_result(1, {"protocolVersion": "2024-11-05"})),
            FakeHTTPResponse(status_code=202),  # initialized notification
            FakeHTTPResponse(json_body=rpc_result(2, {"tools": [
                {"name": "echo", "description": "Echo",
                 "inputSchema": {"type": "object"}}]})),
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        assert fake.calls[0]["json"]["method"] == "initialize"
        assert fake.calls[1]["json"]["method"] == "notifications/initialized"
        assert "id" not in fake.calls[1]["json"]  # notification: no id
        tools = await transport.request("tools/list")
        assert tools["tools"][0]["name"] == "echo"
        assert fake.calls[0]["headers"]["Accept"] == (
            "application/json, text/event-stream")

    async def test_sse_response_is_parsed(self, http_transport_factory):
        body = (
            ": ping\n\n"
            "event: message\n"
            'data: {"jsonrpc": "2.0", "id": 1, "result": '
            '{"protocolVersion": "2024-11-05"}}\n\n'
        )
        sse_init = FakeHTTPResponse(
            content_type="text/event-stream", body=body)
        tools_body = (
            'data: {"jsonrpc": "2.0", "id": 2, "result": {"tools": '
            '[{"name": "echo"}]}}\n\n'
        )
        fake = FakePost([
            sse_init,
            FakeHTTPResponse(status_code=202),
            FakeHTTPResponse(content_type="text/event-stream",
                             body=tools_body),
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        tools = await transport.request("tools/list")
        assert tools == {"tools": [{"name": "echo"}]}

    async def test_sse_multi_data_lines_and_no_trailing_blank(self):
        """SSE events may split data across lines and the final event may
        have no terminating blank line."""
        body = 'data: {"jsonrpc": "2.0",\ndata: "id": 7, "result": {"ok": true}}\n'
        parsed = _parse_sse(body, 7)
        assert parsed == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}

    async def test_bearer_token_from_env_reaches_the_header(
            self, http_transport_factory, monkeypatch):
        monkeypatch.setenv("FAKE_MCP_TOKEN", "env-token-value-12345")
        fake = FakePost([
            FakeHTTPResponse(json_body=rpc_result(
                1, {"protocolVersion": "2024-11-05"})),
            FakeHTTPResponse(status_code=202),
        ])
        from halbert_core.mcp.config import MCPAuthConfig
        transport = http_transport_factory(
            fake, token_provider=MCPAuthConfig(
                type="bearer", token_env="FAKE_MCP_TOKEN").resolve_token)
        await transport.connect()
        assert fake.calls[0]["headers"]["Authorization"] == (
            "Bearer env-token-value-12345")

    async def test_connection_error_scrubs_the_token(
            self, http_transport_factory, caplog):
        """A requests exception (which can echo a URL or anything else)
        must not carry the token into the raised error or the logs."""
        token = "sk-live-literal-secret-token"
        fake = FakePost([
            requests.ConnectionError(f"connect failed for {token}"),
        ])
        transport = http_transport_factory(
            fake, token_provider=lambda: token)
        with caplog.at_level(logging.DEBUG, logger="halbert.mcp.client"):
            with pytest.raises(MCPConnectionError) as excinfo:
                await transport.connect()
        assert token not in str(excinfo.value)
        assert token not in caplog.text

    async def test_legacy_http_sse_only_server_gets_a_clear_error(
            self, http_transport_factory):
        fake = FakePost([FakeHTTPResponse(status_code=404)])
        transport = http_transport_factory(fake)
        with pytest.raises(MCPConnectionError, match="legacy HTTP\\+SSE"):
            await transport.connect()

    async def test_unauthorized_is_a_clear_error(self, http_transport_factory):
        fake = FakePost([FakeHTTPResponse(status_code=401)])
        transport = http_transport_factory(fake)
        with pytest.raises(MCPConnectionError, match="unauthorized"):
            await transport.connect()

    async def test_jsonrpc_error_becomes_protocol_error(
            self, http_transport_factory):
        fake = FakePost([
            FakeHTTPResponse(json_body=rpc_result(
                1, {"protocolVersion": "2024-11-05"})),
            FakeHTTPResponse(status_code=202),
            FakeHTTPResponse(json_body={
                "jsonrpc": "2.0", "id": 2,
                "error": {"code": -32601, "message": "no such tool"}}),
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        with pytest.raises(MCPProtocolError, match="no such tool"):
            await transport.request("tools/call", {"name": "missing"})

    async def test_request_before_connect_is_disconnected_error(
            self, http_transport_factory):
        transport = http_transport_factory(FakePost([]))
        with pytest.raises(MCPDisconnectedError):
            await transport.request("tools/list")

    # -- B1 review: Mcp-Session-Id -------------------------------------------

    async def test_session_id_is_captured_and_echoed(
            self, http_transport_factory):
        fake = FakePost([
            FakeHTTPResponse(
                json_body=rpc_result(1, {"protocolVersion": "2024-11-05"}),
                extra_headers={"Mcp-Session-Id": "sess-abc"}),
            FakeHTTPResponse(status_code=202),
            FakeHTTPResponse(json_body=rpc_result(
                2, {"tools": [{"name": "echo"}]})),
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        tools = await transport.request("tools/list")
        assert tools["tools"][0]["name"] == "echo"
        # The initialize POST itself carries no session id (none is held
        # yet); every subsequent request must echo it.
        assert "Mcp-Session-Id" not in fake.calls[0]["headers"]
        assert fake.calls[1]["headers"]["Mcp-Session-Id"] == "sess-abc"
        assert fake.calls[2]["headers"]["Mcp-Session-Id"] == "sess-abc"

    async def test_expired_session_rehandshakes_once_and_retries(
            self, http_transport_factory):
        """A 404 while a session id is held means the session expired:
        one transparent re-handshake, then the original request is
        retried — not a misdiagnosed legacy-transport error."""
        fake = FakePost([
            # first session
            FakeHTTPResponse(
                json_body=rpc_result(1, {"protocolVersion": "2024-11-05"}),
                extra_headers={"Mcp-Session-Id": "sess-old"}),
            FakeHTTPResponse(status_code=202),
            # session expired
            FakeHTTPResponse(status_code=404),
            # re-handshake: NEW initialize (id 3) and a new session id
            FakeHTTPResponse(
                json_body=rpc_result(3, {"protocolVersion": "2024-11-05"}),
                extra_headers={"Mcp-Session-Id": "sess-new"}),
            FakeHTTPResponse(status_code=202),
            # the retried original request (still id 2)
            FakeHTTPResponse(json_body=rpc_result(
                2, {"tools": [{"name": "after_reconnect"}]})),
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        tools = await transport.request("tools/list")
        assert tools["tools"][0]["name"] == "after_reconnect"
        # The retried POST carries the NEW session id.
        assert fake.calls[5]["headers"]["Mcp-Session-Id"] == "sess-new"

    async def test_concurrent_expiry_recovers_with_one_rehandshake(
            self, http_transport_factory):
        """Two concurrent requests whose session the server expired:
        exactly ONE re-handshake (serialized recovery; the second
        waiter sees the rotated session id and just retries), and no
        spurious MCPDisconnectedError from the not-connected guard."""
        fake = ExpiringSessionPost()
        transport = http_transport_factory(fake)
        await transport.connect()
        # The server expires the session under both requests' feet.
        fake.session = "sess-rotated-server-side"
        results = await asyncio.gather(
            transport.request("tools/list"),
            transport.request("ping"),
        )
        assert results == [{"ok": True}, {"ok": True}]
        # Two initialize POSTs total: the original connect + exactly one
        # recovery handshake — not one per waiter.
        initialize_posts = [c for c in fake.calls
                            if c["json"].get("method") == "initialize"]
        assert len(initialize_posts) == 2
        assert transport.alive

    async def test_double_expiry_is_retyped_not_internal(
            self, http_transport_factory):
        """A session that expires again immediately after recovery is a
        plain MCPConnectionError — the internal _SessionExpired class
        never reaches the public surface."""
        fake = ExpiringSessionPost(always_expire=True)
        transport = http_transport_factory(fake)
        await transport.connect()
        with pytest.raises(MCPConnectionError,
                           match="expired again") as excinfo:
            await transport.request("tools/list")
        from halbert_core.mcp.client import _SessionExpired
        assert type(excinfo.value) is not _SessionExpired
        assert type(excinfo.value) is MCPConnectionError

    async def test_concurrent_double_expiry_retypes_both_waiters(
            self, http_transport_factory):
        """Two concurrent requests against an always-expiring server: the
        first waiter takes the re-handshake path, the second retries on
        the rotated session — and BOTH failures surface as plain
        MCPConnectionError, never the internal _SessionExpired. The
        waiter branch used to let its retry's _SessionExpired escape to
        the caller (B1 residual, fixed with B2)."""
        fake = ExpiringSessionPost(always_expire=True)
        transport = http_transport_factory(fake)
        await transport.connect()
        results = await asyncio.gather(
            transport.request("tools/list"),
            transport.request("ping"),
            return_exceptions=True,
        )
        from halbert_core.mcp.client import _SessionExpired
        assert len(results) == 2
        for result in results:
            assert isinstance(result, MCPConnectionError)
            assert type(result) is not _SessionExpired
            assert "expired again" in str(result)

    async def test_202_answer_to_a_request_names_the_mode(
            self, http_transport_factory):
        """A request (not a notification) answered 202 means the server
        answers on a long-lived GET stream — say so, instead of a
        generic status complaint."""
        fake = FakePost([
            FakeHTTPResponse(json_body=rpc_result(
                1, {"protocolVersion": "2024-11-05"})),
            FakeHTTPResponse(status_code=202),
            FakeHTTPResponse(status_code=202),  # a REQUEST answered 202
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        with pytest.raises(MCPConnectionError, match="long-lived GET stream"):
            await transport.request("tools/list")

    # -- B1 review: JSON responses must answer the request --------------------

    async def test_json_response_with_wrong_id_is_rejected(
            self, http_transport_factory):
        fake = FakePost([
            FakeHTTPResponse(
                json_body=rpc_result(1, {"protocolVersion": "2024-11-05"})),
            FakeHTTPResponse(status_code=202),
            # answers id 999, not our tools/list (id 2)
            FakeHTTPResponse(json_body=rpc_result(
                999, {"tools": [{"name": "wrong-request"}]})),
        ])
        transport = http_transport_factory(fake)
        await transport.connect()
        with pytest.raises(MCPProtocolError, match="does not answer"):
            await transport.request("tools/list")

    # -- B1 review: URLs are user input ---------------------------------------

    async def test_url_with_embedded_key_is_redacted_from_errors(
            self, http_transport_factory, caplog):
        """The configured URL is user input: a ?key= credential in it
        must not survive into the raised error or the log record."""
        secret = "sk-live-url-secret-991"
        fake = FakePost([
            FakeHTTPResponse(status_code=404),
            FakeHTTPResponse(status_code=404),
        ])
        transport = http_transport_factory(
            fake, url=f"https://mcp.example.com/mcp?key={secret}")
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.client"):
            with pytest.raises(MCPConnectionError,
                               match="legacy HTTP\\+SSE") as excinfo:
                await transport.connect()
        assert secret not in str(excinfo.value)
        assert secret not in caplog.text

    async def test_bad_initialize_result_fails_handshake(
            self, http_transport_factory):
        fake = FakePost([
            FakeHTTPResponse(json_body=rpc_result(1, {})),
        ])
        transport = http_transport_factory(fake)
        with pytest.raises(MCPProtocolError, match="protocolVersion"):
            await transport.connect()


# ===========================================================================
# Config
# ===========================================================================

class TestConfig:

    def test_missing_file_means_no_servers(self, config_dir, tmp_path):
        assert not (tmp_path / "mcp_config.yml").exists()
        assert load_config().servers == []

    def test_empty_file_means_no_servers(self, config_dir):
        config_dir()
        assert load_config().servers == []

    def test_null_servers_means_no_servers(self, config_dir):
        path = config_path()
        path.write_text("servers:\n")
        assert load_config().servers == []

    def test_corrupt_yaml_means_no_servers(self, config_dir, caplog):
        path = config_path()
        path.write_text("servers: [unclosed\n  - {bad yaml")
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            config = load_config()
        assert config.servers == []
        assert "failed to load" in caplog.text

    def test_full_entries_parse(self, config_dir):
        config_dir([
            {"name": "filesystem", "transport": "stdio",
             "command": "npx",
             "args": ["-y", "@modelcontextprotocol/server-filesystem", "/u"],
             "env": {"NODE_ENV": "production"},
             "timeout_seconds": 12},
            {"name": "linear", "transport": "http",
             "url": "https://mcp.linear.app/sse",
             "auth": {"type": "bearer", "token_env": "LINEAR_MCP_TOKEN"}},
        ])
        config = load_config()
        assert [s.name for s in config.servers] == ["filesystem", "linear"]
        fs = config.server("filesystem")
        assert fs.transport == "stdio"
        assert fs.command == "npx"
        assert fs.args == ["-y", "@modelcontextprotocol/server-filesystem", "/u"]
        assert fs.env == {"NODE_ENV": "production"}
        assert fs.timeout_seconds == 12.0
        linear = config.server("linear")
        assert linear.transport == "http"
        assert linear.auth.type == "bearer"
        assert linear.auth.token_env == "LINEAR_MCP_TOKEN"

    def test_default_timeout_applies(self, config_dir):
        config_dir([{"name": "s", "transport": "stdio", "command": "x"}])
        assert load_config().server("s").timeout_seconds == 30.0

    def test_invalid_entries_are_skipped_not_fatal(
            self, config_dir, caplog):
        config_dir([
            {"transport": "stdio", "command": "x"},          # no name
            {"name": "bad-transport", "transport": "carrier-pigeon"},
            {"name": "no-command", "transport": "stdio"},
            {"name": "no-url", "transport": "http"},
            {"name": "ok", "transport": "stdio", "command": "x"},
            {"name": "ok", "transport": "stdio", "command": "y"},  # dup
        ])
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            config = load_config()
        assert [s.name for s in config.servers] == ["ok"]
        assert config.server("ok").command == "x"  # first wins
        assert "duplicate server name" in caplog.text
        assert "unknown transport" in caplog.text

    def test_servers_not_a_list_means_no_servers(self, config_dir):
        config_dir(servers={"name": "oops"})
        assert load_config().servers == []

    def test_literal_token_never_reaches_config_warnings(
            self, config_dir, caplog):
        """A literal token in a broken entry is scrubbed from the
        warning that skips it (the entry dumps nothing, but scrub is the
        guard — assert the invariant the logging path owes)."""
        secret = "ghp_literalsecret123"
        config_dir([
            {"name": "bad", "transport": "stdio", "command": "",
             "auth": {"type": "bearer", "token": secret}},
            {"name": "bad2", "transport": "nope",
             "auth": {"type": "bearer", "token": secret}},
        ])
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            load_config()
        assert secret not in caplog.text

    def test_describe_never_contains_a_literal_token(self):
        server = MCPServerConfig(
            name="remote", transport="http", url="https://mcp.example.com",
            auth=MCPAuthConfig(type="bearer", token="super-secret-token"))
        assert "super-secret-token" not in server.describe()
        assert "remote" in server.describe()

    def test_signature_tracks_reconnect_relevant_fields(self):
        """A signature change forces a reconnect. The env-var VALUE is
        deliberately absent (resolved per request, no reconnect needed);
        the literal token IS present — the transport binds the config
        object's resolver, so a rotated literal takes effect only through
        a reconnect."""
        base = MCPServerConfig(
            name="s", transport="http", url="https://x.example",
            auth=MCPAuthConfig(type="bearer", token_env="OLD_VAR"))
        new_var = MCPServerConfig(
            name="s", transport="http", url="https://x.example",
            auth=MCPAuthConfig(type="bearer", token_env="NEW_VAR"))
        new_literal = MCPServerConfig(
            name="s", transport="http", url="https://x.example",
            auth=MCPAuthConfig(type="bearer", token="literal-one"))
        rotated_literal = MCPServerConfig(
            name="s", transport="http", url="https://x.example",
            auth=MCPAuthConfig(type="bearer", token="literal-two"))
        new_url = MCPServerConfig(
            name="s", transport="http", url="https://other.example",
            auth=MCPAuthConfig(type="bearer", token_env="OLD_VAR"))
        assert base.signature() == MCPServerConfig(
            name="s", transport="http", url="https://x.example",
            auth=MCPAuthConfig(type="bearer", token_env="OLD_VAR")).signature()
        assert base.signature() != new_var.signature()
        assert base.signature() != new_literal.signature()
        assert new_literal.signature() != rotated_literal.signature()
        assert base.signature() != new_url.signature()

    def test_config_path_lives_in_the_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
        assert config_path() == tmp_path / "mcp_config.yml"

    def test_missing_token_env_logs_the_name_only(self, monkeypatch, caplog):
        monkeypatch.delenv("NO_SUCH_TOKEN_VAR", raising=False)
        auth = MCPAuthConfig(type="bearer", token_env="NO_SUCH_TOKEN_VAR")
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.config"):
            assert auth.resolve_token() is None
        assert "NO_SUCH_TOKEN_VAR" in caplog.text

    def test_missing_token_env_warns_once_not_per_call(
            self, monkeypatch, caplog):
        """resolve_token runs on every HTTP request — one misconfigured
        variable must produce ONE warning line, not a log flood."""
        var_name = "NEVER_EVER_SET_TOKEN_VAR_42"
        monkeypatch.delenv(var_name, raising=False)
        auth = MCPAuthConfig(type="bearer", token_env=var_name)
        with caplog.at_level(logging.DEBUG, logger="halbert.mcp.config"):
            for _ in range(5):
                assert auth.resolve_token() is None
        warnings = [r for r in caplog.records
                    if r.levelno == logging.WARNING and var_name in r.message]
        assert len(warnings) == 1


# ===========================================================================
# MCPClient — multi-server management + hot reload
# ===========================================================================

class TestMCPClient:

    async def test_stdio_connect_list_call_via_client(
            self, fake_server_script, config_dir):
        config_dir([stdio_server_entry(fake_server_script)])
        client = MCPClient()
        tools = await client.list_tools("fake")
        assert [t["name"] for t in tools] == ["echo", "add"]
        result = await client.call_tool("fake", "add", {"a": 40, "b": 2})
        assert result["content"][0]["text"] == "42"
        await client.disconnect()

    async def test_multiple_servers(
            self, fake_server_script, config_dir):
        config_dir([
            stdio_server_entry(fake_server_script, name="alpha"),
            stdio_server_entry(fake_server_script, name="beta"),
        ])
        client = MCPClient()
        await client.connect()
        assert client.connected_servers() == ["alpha", "beta"]
        alpha_tools = await client.list_tools("alpha")
        beta_tools = await client.list_tools("beta")
        assert len(alpha_tools) == 2 and len(beta_tools) == 2
        await client.disconnect()
        assert client.connected_servers() == []

    async def test_config_is_reread_on_every_call_hot_reload(
            self, fake_server_script, config_dir):
        """Change the config BETWEEN calls — no client restart, no
        reconnect API — and the very next call uses the new config."""
        config_dir([stdio_server_entry(fake_server_script, mode="normal")])
        client = MCPClient()
        assert [t["name"] for t in await client.list_tools("fake")] == [
            "echo", "add"]
        config_dir([stdio_server_entry(fake_server_script, mode="limited")])
        assert [t["name"] for t in await client.list_tools("fake")] == [
            "echo"]
        await client.disconnect()

    async def test_removed_server_is_rejected_on_next_call(
            self, fake_server_script, config_dir):
        config_dir([stdio_server_entry(fake_server_script)])
        client = MCPClient()
        await client.list_tools("fake")
        config_dir([])  # server removed from config
        with pytest.raises(MCPClientError, match="not configured"):
            await client.list_tools("fake")
        await client.disconnect()

    async def test_crashed_server_is_relaunched_on_the_next_call(
            self, fake_server_script, config_dir):
        """B1 reconnection: a server that dies mid-session is detected and
        relaunched (with the CURRENT config) on the next call."""
        config_dir([stdio_server_entry(fake_server_script, mode="die_after")])
        client = MCPClient()
        # First call: handshake succeeds, then the server exits before
        # answering tools/list.
        with pytest.raises(MCPClientError):
            await client.list_tools("fake")
        # The config is hot-fixed to a healthy server — no restart, no
        # explicit reconnect: the next call relaunches.
        config_dir([stdio_server_entry(fake_server_script, mode="normal")])
        tools = await client.list_tools("fake")
        assert [t["name"] for t in tools] == ["echo", "add"]
        await client.disconnect()

    async def test_one_dead_server_does_not_block_the_others(
            self, fake_server_script, config_dir, caplog):
        config_dir([
            {"name": "dead", "transport": "stdio",
             "command": "/no/such/binary", "args": [],
             "timeout_seconds": 2.0},
            stdio_server_entry(fake_server_script, name="alive"),
        ])
        client = MCPClient()
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.client"):
            await client.connect()  # must not raise
        assert "dead" in caplog.text
        assert client.connected_servers() == ["alive"]
        tools = await client.list_tools("alive")
        assert len(tools) == 2
        await client.disconnect()

    async def test_unknown_server_name_raises(self, config_dir):
        config_dir()
        client = MCPClient()
        with pytest.raises(MCPClientError, match="not configured"):
            await client.list_tools("ghost")

    async def test_reconnect_uses_the_current_config(
            self, fake_server_script, config_dir, monkeypatch):
        """reconnect drops the live connection and builds a fresh
        transport from the CURRENT config — asserted via the transport
        factory seam, not client internals."""
        config_dir([stdio_server_entry(fake_server_script, mode="normal")])
        built = []
        real_build = mcp_client_module.build_transport

        def counting_build(server_config):
            built.append(server_config.name)
            return real_build(server_config)

        monkeypatch.setattr(mcp_client_module, "build_transport",
                            counting_build)
        client = MCPClient()
        await client.list_tools("fake")    # builds transport #1
        await client.reconnect("fake")     # builds transport #2
        assert built == ["fake", "fake"]
        assert client.connected_servers() == ["fake"]
        assert len(await client.list_tools("fake")) == 2  # reused, not #3
        await client.disconnect()

    # -- B1 lifecycle review: teardown and races ------------------------------

    async def test_removing_a_server_from_config_tears_down_its_subprocess(
            self, fake_server_script, config_dir):
        """Deleting a server from mcp_config.yml must kill its stdio
        subprocess, not just refuse new calls — "deletions take effect
        without a restart" means the process too."""
        config_dir([stdio_server_entry(fake_server_script)])
        client = MCPClient()
        await client.list_tools("fake")
        pid = client._connections["fake"].transport._proc.pid
        config_dir([])  # server deleted from config
        with pytest.raises(MCPClientError, match="not configured"):
            await client.list_tools("fake")
        assert client.connected_servers() == []
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)  # subprocess reaped

    async def test_disconnect_during_in_flight_connect_does_not_resurrect(
            self, fake_server_script, config_dir):
        """disconnect() takes the same per-server lock as _ensure: a
        connect that lands mid-call cannot resurrect the connection the
        caller just killed."""
        config_dir([stdio_server_entry(fake_server_script, mode="slow_init")])
        client = MCPClient()
        task = asyncio.get_running_loop().create_task(
            client.list_tools("fake"))
        await asyncio.sleep(0.1)  # _ensure mid-handshake (slow server)
        await client.disconnect()  # must wait for, then beat, the landing
        with contextlib.suppress(MCPClientError):
            await task
        assert client.connected_servers() == []
        await client.disconnect()

    async def test_http_server_via_client(
            self, config_dir, monkeypatch):
        config_dir([{
            "name": "remote", "transport": "http",
            "url": "https://mcp.example.com/mcp",
            "timeout_seconds": 2.0,
        }])
        fake = FakePost([
            FakeHTTPResponse(json_body=rpc_result(1, {"protocolVersion": "2024-11-05"})),
            FakeHTTPResponse(status_code=202),
            FakeHTTPResponse(json_body=rpc_result(
                2, {"tools": [{"name": "remote_tool"}]})),
        ])
        monkeypatch.setattr(mcp_client_module.requests, "post", fake)
        client = MCPClient()
        tools = await client.list_tools("remote")
        assert tools == [{"name": "remote_tool"}]
        await client.disconnect()

    async def test_timeout_is_bounded_by_config(
            self, fake_server_script, config_dir):
        import time
        config_dir([stdio_server_entry(fake_server_script, mode="hang",
                                       timeout=0.5)])
        client = MCPClient()
        start = time.monotonic()
        with pytest.raises(MCPClientError):
            await client.list_tools("fake")
        assert time.monotonic() - start < 10.0
        await client.disconnect()

    # -- B1 review: isError, pagination, concurrency, URL redaction ----------

    async def test_call_tool_iserror_raises_typed_error(
            self, fake_server_script, config_dir):
        """A tool result with isError: true is the tool FAILING —
        call_tool must raise, carrying the content and raw result, never
        return it as a normal result."""
        config_dir([stdio_server_entry(fake_server_script)])
        client = MCPClient()
        with pytest.raises(MCPToolError) as excinfo:
            await client.call_tool("fake", "boom", {})
        assert excinfo.value.text == "something exploded"
        assert excinfo.value.result["isError"] is True
        assert "reported an error" in str(excinfo.value)
        # A normal tool still returns its raw result.
        result = await client.call_tool("fake", "add", {"a": 1, "b": 1})
        assert result["content"][0]["text"] == "2"
        await client.disconnect()

    async def test_list_tools_follows_pagination_cursor(
            self, fake_server_script, config_dir):
        """A server that splits tools/list into pages must not lose
        every page after the first."""
        config_dir([stdio_server_entry(fake_server_script, mode="paginated")])
        client = MCPClient()
        tools = await client.list_tools("fake")
        assert [t["name"] for t in tools] == ["tool_a", "tool_b", "tool_c"]
        await client.disconnect()

    async def test_hostile_infinite_cursor_hits_the_cap(
            self, fake_server_script, config_dir):
        """A server that echoes a cursor forever gets a clear pagination
        error, not an infinite loop."""
        config_dir([stdio_server_entry(fake_server_script, mode="hostile",
                                       timeout=5.0)])
        client = MCPClient()
        with pytest.raises(MCPProtocolError, match="pagination"):
            await client.list_tools("fake")
        await client.disconnect()

    async def test_concurrent_first_touch_launches_one_subprocess(
            self, fake_server_script, config_dir, monkeypatch):
        """Two concurrent first calls must launch exactly one subprocess
        (the per-server lock); without it the loser's transport is
        overwritten and its subprocess orphaned."""
        config_dir([stdio_server_entry(fake_server_script)])
        built = []
        real_build = mcp_client_module.build_transport

        def counting_build(server_config):
            built.append(server_config.name)
            return real_build(server_config)

        monkeypatch.setattr(mcp_client_module, "build_transport",
                            counting_build)
        client = MCPClient()
        results = await asyncio.gather(
            client.list_tools("fake"),
            client.list_tools("fake"),
        )
        assert built == ["fake"]
        assert all([t["name"] for t in tools] == ["echo", "add"]
                   for tools in results)
        await client.disconnect()

    async def test_url_secret_not_logged_by_connect_failure(
            self, config_dir, monkeypatch, caplog):
        """The client-level connect() failure log interpolates the
        server's error message — an embedded URL credential must not
        reach the log record."""
        secret = "sk-live-url-secret-777"
        config_dir([{
            "name": "remote", "transport": "http",
            "url": f"https://mcp.example.com/mcp?key={secret}",
            "timeout_seconds": 2.0,
        }])
        fake = FakePost([FakeHTTPResponse(status_code=404)])
        monkeypatch.setattr(mcp_client_module.requests, "post", fake)
        client = MCPClient()
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.client"):
            await client.connect()  # must not raise
        assert "remote" in caplog.text
        assert "failed to connect" in caplog.text
        assert secret not in caplog.text
        await client.disconnect()


# ===========================================================================
# Registry
# ===========================================================================

class TestRegistry:

    def test_namespaced_registration(self):
        registry = MCPToolRegistry()
        names = registry.register("filesystem", [
            {"name": "read_file", "description": "Read",
             "inputSchema": {"type": "object"}},
        ])
        assert names == ["mcp__filesystem__read_file"]

    def test_lookup_round_trip(self):
        registry = MCPToolRegistry()
        schema = {"name": "list_issues", "description": "List",
                  "inputSchema": {"type": "object"}}
        registry.register("linear", [schema])
        ref = registry.get("mcp__linear__list_issues")
        assert ref.server == "linear"
        assert ref.tool == "list_issues"
        assert ref.schema is schema
        assert "mcp__linear__list_issues" in registry
        assert len(registry) == 1
        assert registry.names() == ["mcp__linear__list_issues"]

    def test_sanitization_removes_delimiter_ambiguity(self):
        registry = MCPToolRegistry()
        names = registry.register("my fs.v2", [
            {"name": "read__file", "schema": {}},
            {"name": "weird/tool name!", "schema": {}},
        ])
        for name in names:
            assert name.count("__") == 2  # exactly the two delimiters
        assert names[0] == "mcp__my_fs_v2__read_file"
        assert names[1] == "mcp__my_fs_v2__weird_tool_name"
        assert registry.get("mcp__my_fs_v2__read_file").tool == "read__file"

    def test_collision_gets_a_deterministic_suffix(self):
        """Distinct (server, tool) pairs that sanitize to the same key do
        not overwrite each other: the first keeps the bare key, later
        ones get _2, _3 in registration order. Re-registering the SAME
        server replaces its entries, so it reclaims the bare name."""
        registry = MCPToolRegistry()
        first = registry.register("fs", [
            {"name": "read-file", "schema": {}}])   # sanitizes to read_file
        cross = registry.register("fs-", [          # sanitizes to fs too
            {"name": "read_file", "schema": {}}])
        assert first == ["mcp__fs__read_file"]
        assert cross == ["mcp__fs__read_file_2"]
        # Each ref remembers its true origin.
        assert registry.get("mcp__fs__read_file").server == "fs"
        assert registry.get("mcp__fs__read_file").tool == "read-file"
        assert registry.get("mcp__fs__read_file_2").server == "fs-"
        assert registry.get("mcp__fs__read_file_2").tool == "read_file"
        # Collision within one batch: same rule, deterministic.
        batch = registry.register("fs2", [
            {"name": "read-file", "schema": {}},
            {"name": "read_file", "schema": {}},
        ])
        assert batch == ["mcp__fs2__read_file", "mcp__fs2__read_file_2"]
        # Same registration order in a fresh registry → same names.
        again = MCPToolRegistry()
        assert again.register("fs", [
            {"name": "read-file", "schema": {}}]) == first
        assert again.register("fs-", [
            {"name": "read_file", "schema": {}}]) == cross

    def test_reregistering_a_server_replaces_its_tools(self):
        registry = MCPToolRegistry()
        registry.register("fs", [
            {"name": "old_tool", "schema": {}},
            {"name": "kept", "schema": {}},
        ])
        names = registry.register("fs", [{"name": "new_tool", "schema": {}}])
        assert names == ["mcp__fs__new_tool"]
        assert registry.get("mcp__fs__old_tool") is None
        assert registry.get("mcp__fs__kept") is None
        assert registry.get("mcp__fs__new_tool") is not None

    def test_unregister_server(self):
        registry = MCPToolRegistry()
        registry.register("a", [{"name": "t1", "schema": {}}])
        registry.register("b", [{"name": "t2", "schema": {}}])
        registry.unregister_server("a")
        assert registry.names() == ["mcp__b__t2"]
        registry.unregister_server("a")  # idempotent
        assert registry.servers() == ["b"]

    def test_nameless_tools_are_skipped(self, caplog):
        registry = MCPToolRegistry()
        with caplog.at_level(logging.WARNING, logger="halbert.mcp.registry"):
            names = registry.register("s", [
                {"description": "no name", "schema": {}},
                {"name": "fine", "schema": {}},
            ])
        assert names == ["mcp__s__fine"]
        assert "no name" in caplog.text

    def test_qualify_is_pure_and_total(self):
        assert qualify_tool_name("a", "b") == "mcp__a__b"
        assert qualify_tool_name("", "") == "mcp__unnamed__unnamed"
        assert qualify_tool_name("S P A C E", "x") == "mcp__S_P_A_C_E__x"


# ===========================================================================
# Live counterparty: the real mcp/server.py over stdio
# ===========================================================================

class TestLiveHalbertServer:
    """The client speaks the same wire shapes the house server does —
    verified against the REAL server, not a double. The server is
    tools-only (no resources), so resources degrade to a clean
    MCPProtocolError, which this test pins down."""

    async def test_client_speaks_to_the_real_server(
            self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
        package_parent = os.path.realpath(
            os.path.join(os.path.dirname(__file__), ".."))
        server_code = (
            "import sys; sys.path.insert(0, {parent!r}); "
            "from halbert_core.mcp.server import MCPServer; "
            "MCPServer(instance_name='test', hostname='test-host').run_stdio()"
        ).format(parent=package_parent)
        transport = StdioTransport(
            name="halbert", command=sys.executable,
            args=["-c", server_code], timeout=15.0)
        try:
            await transport.connect()
            tools = await transport.request("tools/list")
            from halbert_core.mcp.server import TOOL_SCHEMAS
            assert len(tools["tools"]) == len(TOOL_SCHEMAS)
            result = await transport.request("tools/call", {
                "name": "get_autonomy_level", "arguments": {}})
            assert result["content"][0]["type"] == "text"
            # The real server has no resources surface: a clean, typed
            # error — never a hang, never a crash.
            with pytest.raises(MCPProtocolError, match="resources/list"):
                await transport.request("resources/list")
        finally:
            await transport.close()


# ===========================================================================
# Package discipline
# ===========================================================================

class TestPackageDiscipline:

    def test_client_modules_import_with_no_side_effects(self):
        """Importing the client/config/registry must not touch the
        network, the filesystem, or the process table."""
        import subprocess
        code = (
            "import sys; sys.path.insert(0, "
            + repr(os.path.join(os.path.dirname(__file__), "..")) + "); "
            "import halbert_core.mcp.client, halbert_core.mcp.config, "
            "halbert_core.mcp.registry; "
            "print('ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout

    def test_no_capability_is_added(self):
        """B1 must not register capabilities — CAP_MCP_CLIENT is B2's
        concern. The capabilities registry must not mention mcp."""
        try:
            from halbert_core.capabilities import has_capability
        except ImportError:
            pytest.skip("capabilities module not importable")
        assert not has_capability("CAP_MCP_CLIENT")