# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the MCP server — JSON-RPC protocol and tool dispatch."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.mcp.server import MCPServer, TOOL_HANDLERS, TOOL_SCHEMAS


@pytest.fixture
def server():
    return MCPServer(instance_name="test", hostname="test-host")


class TestProtocol:
    """JSON-RPC 2.0 protocol handling."""

    def test_initialize(self, server):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        resp = server.handle_request(req)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        assert "protocolVersion" in resp["result"]
        assert "serverInfo" in resp["result"]
        assert "halbert-test" in resp["result"]["serverInfo"]["name"]

    def test_ping(self, server):
        req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
        resp = server.handle_request(req)
        assert resp["id"] == 2
        assert "result" in resp

    def test_notification_no_response(self, server):
        """Notifications (no id) should return None."""
        req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = server.handle_request(req)
        assert resp is None

    def test_unknown_method(self, server):
        req = {"jsonrpc": "2.0", "id": 3, "method": "bogus"}
        resp = server.handle_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_tools_list(self, server):
        req = {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
        resp = server.handle_request(req)
        assert "result" in resp
        tools = resp["result"]["tools"]
        assert len(tools) == 12
        # Instance name should be in descriptions
        assert "[test]" in tools[0]["description"]

    def test_tools_list_has_all_expected(self, server):
        req = {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}
        resp = server.handle_request(req)
        tool_names = {t["name"] for t in resp["result"]["tools"]}
        expected = {
            "get_vitals", "get_discoveries", "get_findings", "get_proposals",
            "get_proactive_events", "get_being_config", "get_config_value",
            "get_config_structure", "get_config_diff", "get_config_dependencies",
            "search_knowledge", "run_scanner",
        }
        assert tool_names == expected


class TestToolCall:
    """Tool dispatch via tools/call."""

    def _call(self, server, tool_name, args=None):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool_name, "arguments": args or {}},
        }
        resp = server.handle_request(req)
        assert "result" in resp
        content = resp["result"]["content"][0]["text"]
        return json.loads(content)

    def test_unknown_tool(self, server):
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "bogus", "arguments": {}},
        }
        resp = server.handle_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_get_vitals(self, server):
        result = self._call(server, "get_vitals")
        # psutil may or may not be available
        assert "error" in result or "cpu_percent" in result

    def test_get_being_config(self, server):
        result = self._call(server, "get_being_config")
        # Should have voice, proactivity fields
        assert "voice" in result or "error" in result
        # Security config should be stripped
        assert "security" not in result

    def test_get_config_value_missing_params(self, server):
        result = self._call(server, "get_config_value")
        assert "error" in result

    def test_get_config_value_not_found(self, server):
        result = self._call(server, "get_config_value", {
            "path": "/nonexistent/path.conf", "key": "Port"
        })
        assert "error" in result

    def test_get_config_structure_missing_path(self, server):
        result = self._call(server, "get_config_structure")
        assert "error" in result

    def test_get_config_diff(self, server):
        result = self._call(server, "get_config_diff")
        assert "changes" in result

    def test_get_config_dependencies_missing_path(self, server):
        result = self._call(server, "get_config_dependencies")
        assert "error" in result

    def test_search_knowledge_missing_query(self, server):
        result = self._call(server, "search_knowledge")
        assert "error" in result

    def test_run_scanner_missing_type(self, server):
        result = self._call(server, "run_scanner")
        assert "error" in result


class TestTierRouting:
    """Config value tier routing through the MCP server."""

    def test_password_is_redacted(self, server, tmp_path, monkeypatch):
        """A password value should come back redacted, not raw."""
        # Create a config file with a password
        config_file = tmp_path / "test.conf"
        config_file.write_text("[Service]\nPassword=hunter2\n")

        # Patch being config to use defaults (local_only for secrets)
        from halbert_core.config.being_config import BeingConfig, SecurityConfig
        from halbert_core.config import being_config as bc_module

        # Patch load_being_config to return a config with local_only
        def mock_load():
            bc = BeingConfig()
            bc.security = SecurityConfig(secret_tier="local_only")
            return bc

        monkeypatch.setattr("halbert_core.config.being_config.load_being_config", mock_load)

        # Patch the canon DB to have our file
        from halbert_core.config import queries as q_module
        from halbert_core.config.parser import parse as parse_config

        def mock_get_current_canon(path):
            if str(config_file) in path:
                return parse_config(str(config_file))
            return None

        monkeypatch.setattr(q_module, "_get_current_canon", mock_get_current_canon)

        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_config_value",
                       "arguments": {"path": str(config_file), "key": "Password"}},
        }
        resp = server.handle_request(req)
        content = json.loads(resp["result"]["content"][0]["text"])

        assert content["tier"] == 2
        assert "value" not in content
        assert content.get("redacted") is True
        assert "hunter2" not in json.dumps(content)


class TestEgressBoundary:
    """mcp_response() is applied to config tools."""

    def test_config_value_passes_through_mcp_response(self, server, tmp_path, monkeypatch):
        """The MCP response boundary should redact secrets in tool output."""
        config_file = tmp_path / "test.conf"
        config_file.write_text("[Service]\nPassword=hunter2\nPort=2222\n")

        from halbert_core.config import queries as q_module
        from halbert_core.config.parser import parse as parse_config

        def mock_get_current_canon(path):
            if str(config_file) in path:
                return parse_config(str(config_file))
            return None

        monkeypatch.setattr(q_module, "_get_current_canon", mock_get_current_canon)

        # Request with cloud_ok_acknowledged to get the raw value
        from halbert_core.config.being_config import BeingConfig, SecurityConfig
        def mock_load():
            bc = BeingConfig()
            bc.security = SecurityConfig(secret_tier="cloud_ok_acknowledged")
            return bc
        monkeypatch.setattr("halbert_core.config.being_config.load_being_config", mock_load)

        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_config_value",
                       "arguments": {"path": str(config_file), "key": "Password"}},
        }
        resp = server.handle_request(req)
        content_text = resp["result"]["content"][0]["text"]
        # Even with cloud_ok_acknowledged, the mcp_response boundary
        # should redact the password value in the output
        assert "hunter2" not in content_text
