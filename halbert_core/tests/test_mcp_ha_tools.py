# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for MCP HA tools — ha_get_entities, ha_call_service, autonomy level."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from halbert_core.mcp.server import (
    _tool_ha_get_entities,
    _tool_ha_get_entity_state,
    _tool_ha_call_service,
    _tool_get_autonomy_level,
    _tool_set_autonomy_level,
    TOOL_HANDLERS,
    TOOL_SCHEMAS,
)


class TestMCPSchemas:
    """Verify the new tools are registered."""

    def test_ha_tools_in_handlers(self):
        assert "ha_get_entities" in TOOL_HANDLERS
        assert "ha_get_entity_state" in TOOL_HANDLERS
        assert "ha_call_service" in TOOL_HANDLERS
        assert "get_autonomy_level" in TOOL_HANDLERS
        assert "set_autonomy_level" in TOOL_HANDLERS

    def test_ha_tools_in_schemas(self):
        names = [s["name"] for s in TOOL_SCHEMAS]
        assert "ha_get_entities" in names
        assert "ha_get_entity_state" in names
        assert "ha_call_service" in names
        assert "get_autonomy_level" in names
        assert "set_autonomy_level" in names

    def test_total_tool_count(self):
        assert len(TOOL_SCHEMAS) == 18
        assert len(TOOL_HANDLERS) == 18


class TestHAGetEntities:
    """Test ha_get_entities tool."""

    def test_returns_error_when_ha_not_configured(self):
        with patch("halbert_core.mcp.server._get_ha_client", return_value=None):
            result = _tool_ha_get_entities({})
            assert "error" in result

    def test_returns_entities_when_configured(self):
        mock_client = MagicMock()
        mock_client.get_states = AsyncMock(return_value=[
            {"entity_id": "light.living_room", "state": "on", "attributes": {"friendly_name": "Living Room"}},
            {"entity_id": "light.bedroom", "state": "off", "attributes": {"friendly_name": "Bedroom"}},
        ])
        mock_client.close = AsyncMock()
        with patch("halbert_core.mcp.server._get_ha_client", return_value=mock_client):
            result = _tool_ha_get_entities({})
            assert result["count"] == 2
            assert len(result["entities"]) == 2

    def test_domain_filter(self):
        mock_client = MagicMock()
        mock_client.get_states = AsyncMock(return_value=[
            {"entity_id": "light.living_room", "state": "on", "attributes": {}},
            {"entity_id": "climate.thermostat", "state": "heat", "attributes": {}},
        ])
        mock_client.close = AsyncMock()
        with patch("halbert_core.mcp.server._get_ha_client", return_value=mock_client):
            result = _tool_ha_get_entities({"domain": "light"})
            assert result["count"] == 1
            assert result["entities"][0]["entity_id"] == "light.living_room"


class TestHACallService:
    """Test ha_call_service tool with autonomy gate."""

    def test_observe_blocks_action(self):
        mock_gate = MagicMock()
        mock_gate.evaluate.return_value = MagicMock(
            allowed=False,
            auto_execute=False,
            requires_proposal=False,
            cancel_window_seconds=0,
            governance_level=0,
            reason="Autonomy level is 'observe'",
        )
        with patch("halbert_core.mcp.server._get_autonomy_gate", return_value=mock_gate):
            result = _tool_ha_call_service({
                "domain": "light",
                "service": "turn_on",
                "entity_id": "light.living_room",
            })
            assert result["executed"] is False
            assert "observe" in result["reason"]

    def test_act_executes_level_0(self):
        mock_gate = MagicMock()
        mock_gate.evaluate.return_value = MagicMock(
            allowed=True,
            auto_execute=True,
            requires_proposal=False,
            cancel_window_seconds=0,
            governance_level=0,
            reason="Auto-executed",
        )
        mock_client = MagicMock()
        mock_client.call_service = AsyncMock(return_value={})
        mock_client.close = AsyncMock()
        with patch("halbert_core.mcp.server._get_autonomy_gate", return_value=mock_gate), \
             patch("halbert_core.mcp.server._get_ha_client", return_value=mock_client):
            result = _tool_ha_call_service({
                "domain": "light",
                "service": "turn_on",
                "entity_id": "light.living_room",
            })
            assert result["executed"] is True

    def test_suggest_creates_proposal(self):
        mock_gate = MagicMock()
        mock_gate.evaluate.return_value = MagicMock(
            allowed=True,
            auto_execute=False,
            requires_proposal=True,
            cancel_window_seconds=0,
            governance_level=2,
            reason="Requires proposal",
        )
        with patch("halbert_core.mcp.server._get_autonomy_gate", return_value=mock_gate):
            result = _tool_ha_call_service({
                "domain": "lock",
                "service": "unlock",
                "entity_id": "lock.front_door",
            })
            assert result["executed"] is False
            assert result["requires_proposal"] is True

    def test_missing_domain_returns_error(self):
        result = _tool_ha_call_service({"service": "turn_on"})
        assert "error" in result

    def test_missing_service_returns_error(self):
        result = _tool_ha_call_service({"domain": "light"})
        assert "error" in result


class TestAutonomyLevel:
    """Test get/set autonomy level tools."""

    def test_get_autonomy_level(self):
        mock_cfg = MagicMock()
        mock_cfg.autonomy_level = "act"
        mock_cfg.autonomy_overrides = {"lock": "suggest"}
        mock_cfg.variant = "home"
        with patch("halbert_core.config.being_config.load_being_config", return_value=mock_cfg):
            result = _tool_get_autonomy_level({})
            assert result["autonomy_level"] == "act"
            assert result["variant"] == "home"

    def test_set_autonomy_level_requires_confirm(self):
        result = _tool_set_autonomy_level({"level": "act", "confirm": False})
        assert "error" in result
        assert "confirm" in result["error"]

    def test_set_autonomy_level_missing_level(self):
        result = _tool_set_autonomy_level({"confirm": True})
        assert "error" in result
