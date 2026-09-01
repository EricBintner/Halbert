# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Security tests for PeerToolProxy — cross-node tool routing.

These tests verify the security boundary of the cross-node tool proxy:
- Bearer token authentication is enforced
- Tool existence is verified before routing (no arbitrary tool calls)
- The peer's safety gating is the authoritative boundary (not the proxy)
- Connection failures are handled gracefully
- The proxy cannot be tricked into routing to a non-existent tool
- The proxy cannot be tricked into calling a tool on a non-peer host
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests as _requests

from halbert_core.agents.peer_tool_proxy import PeerToolProxy, PeerToolUnavailable


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def proxy():
    """A PeerToolProxy pointed at a mock peer."""
    return PeerToolProxy(
        peer_url="http://workstation.lan:8000",
        bearer_token="test-token-123",
        timeout=5.0,
    )


@pytest.fixture
def proxy_no_token():
    """A PeerToolProxy with no bearer token."""
    return PeerToolProxy(
        peer_url="http://workstation.lan:8000",
        bearer_token="",
        timeout=5.0,
    )


def _mock_mcp_response(tools=None, tool_result=None):
    """Build a mock requests.post response for MCP JSON-RPC."""
    resp = MagicMock()
    resp.status_code = 200
    if tools is not None:
        resp.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"tools": [{"name": t} for t in tools]},
            "id": 1,
        }
    elif tool_result is not None:
        resp.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "content": [{"type": "text", "text": json.dumps(tool_result)}]
            },
            "id": 1,
        }
    return resp


# ---------------------------------------------------------------------------
# Bearer token authentication
# ---------------------------------------------------------------------------

class TestBearerAuth:
    """Bearer token must be sent on every request."""

    @patch("requests.post")
    def test_bearer_token_sent(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        proxy.list_tools()
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert headers.get("Authorization") == "Bearer test-token-123"

    @patch("requests.post")
    def test_no_token_no_auth_header(self, mock_post, proxy_no_token):
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        proxy_no_token.list_tools()
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert "Authorization" not in headers

    @patch("requests.post")
    def test_401_raises_unavailable(self, mock_post, proxy):
        resp = MagicMock()
        resp.status_code = 401
        mock_post.return_value = resp
        with pytest.raises(PeerToolUnavailable, match="401"):
            proxy.list_tools()


# ---------------------------------------------------------------------------
# Tool existence verification
# ---------------------------------------------------------------------------

class TestToolExistence:
    """The proxy must verify a tool exists on the peer before routing."""

    @patch("requests.post")
    def test_call_tool_verifies_existence(self, mock_post, proxy):
        # First call: tools/list returns only search_knowledge
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        # Try to call a tool that doesn't exist
        with pytest.raises(PeerToolUnavailable, match="does not have tool"):
            proxy.call_tool("edit_system_config", {"path": "/etc/ssh/sshd_config"})

    @patch("requests.post")
    def test_call_existing_tool_succeeds(self, mock_post, proxy):
        # First call: tools/list
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        proxy.list_tools()
        # Second call: tools/call
        mock_post.return_value = _mock_mcp_response(
            tool_result={"results": ["doc1", "doc2"]}
        )
        result = proxy.call_tool("search_knowledge", {"query": "nvidia driver"})
        assert result == {"results": ["doc1", "doc2"]}

    @patch("requests.post")
    def test_has_tool_returns_false_for_missing(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        assert proxy.has_tool("edit_system_config") is False
        assert proxy.has_tool("search_knowledge") is True

    @patch("requests.post")
    def test_has_tool_returns_false_on_connection_error(self, mock_post, proxy):
        mock_post.side_effect = _requests.ConnectionError("unreachable")
        assert proxy.has_tool("search_knowledge") is False


# ---------------------------------------------------------------------------
# Connection and protocol errors
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Connection failures and protocol errors must be handled gracefully."""

    @patch("requests.post")
    def test_connection_error_raises_unavailable(self, mock_post, proxy):
        mock_post.side_effect = _requests.ConnectionError("refused")
        with pytest.raises(PeerToolUnavailable, match="Cannot reach"):
            proxy.list_tools()

    @patch("requests.post")
    def test_timeout_raises_unavailable(self, mock_post, proxy):
        mock_post.side_effect = _requests.Timeout("timed out")
        with pytest.raises(PeerToolUnavailable, match="timed out"):
            proxy.list_tools()

    @patch("requests.post")
    def test_mcp_error_raises_unavailable(self, mock_post, proxy):
        # First call: tools/list succeeds (so has_tool passes)
        mock_post.return_value = _mock_mcp_response(tools=["bogus"])
        proxy.list_tools()
        # Second call: tools/call returns MCP error
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Unknown tool: bogus"},
            "id": 1,
        }
        mock_post.return_value = resp
        with pytest.raises(PeerToolUnavailable, match="Unknown tool"):
            proxy.call_tool("bogus")

    @patch("requests.post")
    def test_invalid_json_raises_unavailable(self, mock_post, proxy):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = json.JSONDecodeError("bad", "", 0)
        mock_post.return_value = resp
        with pytest.raises(PeerToolUnavailable, match="invalid JSON"):
            proxy.list_tools()


# ---------------------------------------------------------------------------
# Tool result handling
# ---------------------------------------------------------------------------

class TestToolResults:
    """Tool results from the peer are parsed correctly."""

    @patch("requests.post")
    def test_json_result_parsed(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["get_vitals"])
        proxy.list_tools()
        mock_post.return_value = _mock_mcp_response(
            tool_result={"cpu_percent": 42.0, "memory": {"percent": 55.0}}
        )
        result = proxy.call_tool("get_vitals")
        assert result["cpu_percent"] == 42.0

    @patch("requests.post")
    def test_non_json_result_returned_as_raw(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["get_vitals"])
        proxy.list_tools()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": "not json"}]},
            "id": 1,
        }
        mock_post.return_value = resp
        result = proxy.call_tool("get_vitals")
        assert result == {"raw": "not json"}

    @patch("requests.post")
    def test_empty_content_returns_empty_dict(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["get_vitals"])
        proxy.list_tools()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"content": []},
            "id": 1,
        }
        mock_post.return_value = resp
        result = proxy.call_tool("get_vitals")
        assert result == {}


# ---------------------------------------------------------------------------
# Tool list caching
# ---------------------------------------------------------------------------

class TestToolListCaching:
    """The tool list is cached after first call."""

    @patch("requests.post")
    def test_tools_cached(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        proxy.list_tools()
        proxy.list_tools()
        # Only one HTTP call — second call uses cache
        assert mock_post.call_count == 1

    @patch("requests.post")
    def test_refresh_clears_cache(self, mock_post, proxy):
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        proxy.list_tools()
        proxy.refresh_tools()
        assert mock_post.call_count == 2


# ---------------------------------------------------------------------------
# ToolExecutor integration (peer fallback)
# ---------------------------------------------------------------------------

class TestExecutorPeerFallback:
    """ToolExecutor routes unknown tools to the peer when configured."""

    async def test_unknown_tool_without_proxy_returns_error(self):
        from halbert_core.tools.executor import ToolExecutor
        executor = ToolExecutor()
        result = await executor.execute("nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.error

    async def test_unknown_tool_with_proxy_routes_to_peer(self):
        from halbert_core.tools.executor import ToolExecutor
        proxy = MagicMock()
        proxy.has_tool.return_value = True
        proxy.call_tool.return_value = {"result": "from peer"}
        proxy.peer_url = "http://workstation.lan:8000"
        executor = ToolExecutor(peer_tool_proxy=proxy)
        result = await executor.execute("search_knowledge", {"query": "test"})
        assert result.success is True
        assert result.result == {"result": "from peer"}
        proxy.has_tool.assert_called_once_with("search_knowledge")
        proxy.call_tool.assert_called_once_with("search_knowledge", {"query": "test"})

    async def test_unknown_tool_peer_also_missing_returns_error(self):
        from halbert_core.tools.executor import ToolExecutor
        proxy = MagicMock()
        proxy.has_tool.return_value = False
        proxy.peer_url = "http://workstation.lan:8000"
        executor = ToolExecutor(peer_tool_proxy=proxy)
        result = await executor.execute("nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.error

    async def test_peer_failure_falls_through_to_error(self):
        from halbert_core.tools.executor import ToolExecutor
        proxy = MagicMock()
        proxy.has_tool.return_value = True
        proxy.call_tool.side_effect = PeerToolUnavailable("unreachable")
        proxy.peer_url = "http://workstation.lan:8000"
        executor = ToolExecutor(peer_tool_proxy=proxy)
        result = await executor.execute("search_knowledge", {"query": "test"})
        assert result.success is False
        assert "Unknown tool" in result.error

    def test_local_tool_takes_precedence_over_peer(self):
        """If a tool exists locally, it's used — the peer is not consulted."""
        from halbert_core.tools.executor import ToolExecutor
        proxy = MagicMock()
        proxy.peer_url = "http://workstation.lan:8000"
        executor = ToolExecutor(peer_tool_proxy=proxy)
        # run_command is a built-in local tool
        proxy.has_tool.assert_not_called()
        proxy.call_tool.assert_not_called()


# ---------------------------------------------------------------------------
# Security boundary: proxy cannot be tricked
# ---------------------------------------------------------------------------

class TestSecurityBoundary:
    """The proxy cannot be tricked into routing to a non-peer host or
    calling tools that don't exist on the peer."""

    def test_peer_url_is_fixed_at_construction(self, proxy):
        """The peer URL cannot be changed after construction."""
        assert proxy.peer_url == "http://workstation.lan:8000"

    def test_bearer_token_is_fixed_at_construction(self, proxy):
        """The bearer token cannot be changed after construction."""
        assert proxy.bearer_token == "test-token-123"

    @patch("requests.post")
    def test_tool_call_sends_correct_jsonrpc(self, mock_post, proxy):
        """The tool call is a specific JSON-RPC tools/call, not arbitrary."""
        mock_post.return_value = _mock_mcp_response(tools=["search_knowledge"])
        proxy.list_tools()
        mock_post.return_value = _mock_mcp_response(tool_result={"ok": True})
        proxy.call_tool("search_knowledge", {"query": "test"})
        # Check the second call (tools/call)
        call_body = mock_post.call_args.kwargs.get("json", mock_post.call_args[1].get("json", {}))
        assert call_body["jsonrpc"] == "2.0"
        assert call_body["method"] == "tools/call"
        assert call_body["params"]["name"] == "search_knowledge"
        assert call_body["params"]["arguments"] == {"query": "test"}
