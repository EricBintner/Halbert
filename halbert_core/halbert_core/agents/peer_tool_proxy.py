# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""PeerToolProxy — route tool calls to a paired peer's MCP server.

In singular entity mode, the HA server's agent may need workstation
capabilities (config editing, SourcePrep documentation, terminal commands).
This module routes those tool calls to the workstation's MCP server over
the peer HTTP link.

This is NOT the compute-offload path (which sends arbitrary prompts to the
peer's GPU with a restricted toolset). This is a specific, structured tool
call — the workstation applies its own safety gating (agent state machine,
proposal approval, mcp_response redaction) before executing.

Security model:
- The HA server sends a tool name + params, not an arbitrary prompt.
- The workstation's MCP server executes the tool with the same safety
  gating as a local call (proposal approval for write actions, etc.).
- mcp_response() redaction is applied by the workstation at the egress
  boundary — this IS external egress (the response crosses the network),
  unlike memory/thread federation which is internal.
- Bearer token authenticates the HA server as a trusted peer.
- The PeerToolProxy only routes tools that the peer actually has
  (verified via tools/list on the peer's MCP server).

Direction: HA server → workstation (reversed from fleet_proxy.py, which
is workstation → satellite for fleet cockpit inspection).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PeerToolUnavailable(Exception):
    """Raised when the peer's MCP server is unreachable or the tool is not available."""


class PeerToolProxy:
    """Route tool calls to a paired peer's MCP server.

    Usage:
        proxy = PeerToolProxy(
            peer_url="http://mac-studio.lan:8000",
            bearer_token="...",
        )
        # Check if the peer has a tool
        if proxy.has_tool("search_knowledge"):
            result = proxy.call_tool("search_knowledge", {"query": "..."})
    """

    def __init__(
        self,
        peer_url: str,
        bearer_token: str = "",
        timeout: float = 30.0,
    ):
        """
        Args:
            peer_url: The peer's base URL (e.g., "http://mac-studio.lan:8000").
                The MCP HTTP endpoint is at {peer_url}/ (POST for JSON-RPC).
            bearer_token: Bearer token for peer authentication.
            timeout: HTTP timeout for tool calls (seconds). Longer than the
                memory/thread proxies because tool execution can be slow.
        """
        self.peer_url = peer_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self._available_tools: Optional[Set[str]] = None

    @property
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _mcp_call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC 2.0 request to the peer's MCP HTTP endpoint.

        Returns the result dict from the JSON-RPC response.
        Raises PeerToolUnavailable on connection or protocol errors.
        """
        import requests

        url = f"{self.peer_url}/"
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }
        try:
            resp = requests.post(
                url,
                json=body,
                headers=self._headers,
                timeout=self.timeout,
            )
        except requests.ConnectionError as e:
            raise PeerToolUnavailable(
                f"Cannot reach peer MCP server at {url}: {e}"
            ) from e
        except requests.Timeout as e:
            raise PeerToolUnavailable(
                f"Peer MCP server timed out at {url}: {e}"
            ) from e

        if resp.status_code == 401:
            raise PeerToolUnavailable(
                f"Peer MCP server rejected bearer token (401) at {url}"
            )
        if resp.status_code >= 400:
            raise PeerToolUnavailable(
                f"Peer MCP server returned {resp.status_code}: {resp.text[:200]}"
            )

        try:
            rpc_response = resp.json()
        except json.JSONDecodeError as e:
            raise PeerToolUnavailable(
                f"Peer MCP server returned invalid JSON: {e}"
            ) from e

        if "error" in rpc_response:
            error = rpc_response["error"]
            raise PeerToolUnavailable(
                f"Peer MCP error {error.get('code')}: {error.get('message')}"
            )

        return rpc_response.get("result", {})

    def list_tools(self) -> List[str]:
        """List available tools on the peer's MCP server.

        Returns a list of tool names. Cached after first call.
        Raises PeerToolUnavailable on connection errors.
        """
        if self._available_tools is not None:
            return sorted(self._available_tools)

        result = self._mcp_call("tools/list")
        tools = result.get("tools", [])
        self._available_tools = {t["name"] for t in tools if "name" in t}
        logger.info(
            "Peer %s has %d tools: %s",
            self.peer_url, len(self._available_tools),
            sorted(self._available_tools),
        )
        return sorted(self._available_tools)

    def has_tool(self, tool_name: str) -> bool:
        """Check if the peer has a specific tool.

        Returns False on connection errors (peer is unreachable).
        """
        try:
            return tool_name in self.list_tools()
        except PeerToolUnavailable:
            return False

    def call_tool(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Call a tool on the peer's MCP server.

        The peer executes the tool with its own safety gating (agent state
        machine, proposal approval, mcp_response redaction). The result is
        returned as a dict (the tool's return value, already redacted by
        the peer's mcp_response egress boundary).

        Args:
            tool_name: Name of the tool to call
            params: Tool arguments

        Returns:
            The tool result dict (already redacted by the peer)

        Raises:
            PeerToolUnavailable: If the peer is unreachable, the tool
                doesn't exist on the peer, or the peer rejects the call.
        """
        # Verify the tool exists on the peer before calling
        if not self.has_tool(tool_name):
            raise PeerToolUnavailable(
                f"Peer at {self.peer_url} does not have tool '{tool_name}'"
            )

        result = self._mcp_call("tools/call", {
            "name": tool_name,
            "arguments": params or {},
        })

        # MCP tools/call returns {"content": [{"type": "text", "text": "..."}]}
        # where text is the JSON-encoded tool result.
        content = result.get("content", [])
        if not content:
            return {}

        text = content[0].get("text", "{}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def refresh_tools(self) -> List[str]:
        """Force-refresh the cached tool list from the peer.

        Called when the peer's capabilities may have changed (e.g., after
        a peer software update or variant change).
        """
        self._available_tools = None
        return self.list_tools()
