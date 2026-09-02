# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The Tier 2 architectural guarantee at the MCP dispatch choke point.

The merged security-review fix (06e113cc) moved the egress boundary from
individual tool handlers to the JSON-RPC dispatcher: every ``tools/call``
result passes through ``mcp_response()`` whether or not the handler
remembered to call it. These tests pin that guarantee architecturally:

  1. A handler that returns raw secrets is still redacted by the choke point.
  2. Every tools/call result that gets a response goes through
     ``mcp_response``, exactly once, with the handler's raw result. A
     notification (no ``id``) is the one exception — R2-P3 rejects it
     before dispatch, so neither the handler nor the choke point runs
     for it at all (see test_notification_tools_call_never_dispatches).
  3. The exception path cannot smuggle a secret out in an error message.

The value-level guarantee (``describe_secret`` makes no network calls and
emits only metadata) is pinned by test_secure_response.py; this file covers
the dispatch layer above it.
"""
from __future__ import annotations

import json

import pytest

from halbert_core.mcp import server as server_module
from halbert_core.mcp.server import MCPServer, TOOL_HANDLERS


@pytest.fixture
def srv():
    return MCPServer(instance_name="test", hostname="test-host")


def _tools_call(srv, name, arguments):
    return srv.handle_request({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })


class TestDispatchChokePoint:
    """A handler that forgets mcp_response is still redacted at dispatch."""

    def test_leaky_handler_is_redacted(self, srv, monkeypatch):
        raw_secret = "hunter2-bare-secret-value"

        def leaky(args):
            # Every shape a forgetful handler might return.
            return {
                "path": "/etc/app.conf",
                "key": "password",
                "value": raw_secret,
                "inline": f"password={raw_secret}",
                "nested": {"api_key": raw_secret},
            }

        monkeypatch.setitem(TOOL_HANDLERS, "leaky", leaky)
        resp = _tools_call(srv, "leaky", {})
        body = resp["result"]["content"][0]["text"]
        assert raw_secret not in body
        assert "<secret>" in body

    def test_every_tools_call_result_passes_through_mcp_response(self, srv, monkeypatch):
        """The wrap is at dispatch, not left to the handler — spy on it."""
        calls = []
        real = server_module.mcp_response

        def spy(payload):
            calls.append(payload)
            return real(payload)

        monkeypatch.setattr(server_module, "mcp_response", spy)
        resp = _tools_call(srv, "get_vitals", {})
        assert resp["result"] is not None
        assert len(calls) == 1
        # The spy saw the handler's raw (unwrapped) result.
        assert isinstance(calls[0], dict)

    def test_notification_tools_call_never_dispatches(self, srv, monkeypatch):
        """A notification tools/call is rejected before dispatch (R2-P3).

        Superseded guarantee, kept for the historical record: this used to
        assert the choke point still ran for a notification (handler runs,
        response is merely discarded). That let a notification execute a
        side-effecting tool (run_scanner, approve_proposal) whose caller
        would never even learn the result — the bug R2-P3 fixed. A
        notification must now never reach the handler OR the choke point.
        """
        calls = []
        real = server_module.mcp_response

        def spy(payload):
            calls.append(payload)
            return real(payload)

        monkeypatch.setattr(server_module, "mcp_response", spy)
        resp = srv.handle_request({
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": "get_vitals", "arguments": {}},
        })
        assert resp is None  # notification — no response
        assert len(calls) == 0  # and no dispatch happened at all

    def test_exception_message_cannot_smuggle_a_secret(self, srv, monkeypatch):
        """A handler that embeds a secret in an exception must not leak it.

        The dispatcher's catch-all formats the exception into the JSON-RPC
        error message. If that message is not redacted, a handler crashing
        mid-secret-handling (``ValueError(f"bad key: {value}")``) carries the
        secret straight past the choke point in the error response.
        """
        raw_secret = "sk-live-abcdef1234567890abcdef"

        def crashing(args):
            raise ValueError(f"cannot parse credential: {raw_secret}")

        monkeypatch.setitem(TOOL_HANDLERS, "crashing", crashing)
        resp = _tools_call(srv, "crashing", {})
        body = json.dumps(resp)
        assert raw_secret not in body
        assert resp["error"]["code"] == -32603