# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for Home Assistant integration (Phase 1)."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from halbert_core.integrations.home_assistant.ha_config import (
    HAConfig,
    load_ha_config,
    save_ha_config,
)
from halbert_core.integrations.home_assistant.ha_client import HAClient


# --- HAConfig tests ---

class TestHAConfig:
    def test_defaults(self):
        config = HAConfig()
        assert not config.is_configured()
        assert config.url == ""
        assert config.token == ""
        assert config.verify_ssl is True
        assert "light" in config.visible_domains

    def test_is_configured(self):
        config = HAConfig(url="http://ha.local:8123", token="abc123")
        assert config.is_configured()

    def test_to_dict_masks_token(self):
        config = HAConfig(url="http://ha.local:8123", token="verylongtoken123")
        d = config.to_dict()
        assert "verylongtoken123" not in d["token"]
        assert d["token"].endswith("...")
        assert d["url"] == "http://ha.local:8123"

    def test_to_dict_short_token(self):
        config = HAConfig(url="http://ha.local:8123", token="ab")
        d = config.to_dict()
        assert d["token"] == "***"


# --- Config load/save round-trip ---

class TestConfigPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path))
        config = HAConfig(
            url="http://homeassistant.local:8123",
            token="test_token_12345",
            verify_ssl=False,
        )
        save_ha_config(config)

        loaded = load_ha_config()
        assert loaded.url == "http://homeassistant.local:8123"
        assert loaded.token == "test_token_12345"
        assert loaded.verify_ssl is False

    def test_load_missing_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "nonexistent"))
        config = load_ha_config()
        assert not config.is_configured()
        assert config.url == ""


# --- HAClient tests (mocked aiohttp) ---

class TestHAClient:
    def test_headers(self):
        config = HAConfig(url="http://ha.local:8123", token="test123")
        client = HAClient(config)
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test123"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_get_status_connected(self):
        config = HAConfig(url="http://ha.local:8123", token="test")
        client = HAClient(config)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content_type = "application/json"
        mock_resp.json = AsyncMock(return_value={"message": "API running."})
        mock_resp.raise_for_status = MagicMock()

        mock_session = AsyncMock()
        mock_session.request.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.closed = False
        client._session = mock_session

        result = await client.get_status()
        assert result["connected"] is True

    @pytest.mark.asyncio
    async def test_get_status_connection_failed(self):
        config = HAConfig(url="http://ha.local:8123", token="test")
        client = HAClient(config)

        mock_session = AsyncMock()
        mock_session.request.side_effect = Exception("Connection refused")
        mock_session.closed = False
        client._session = mock_session

        result = await client.get_status()
        assert result["connected"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_service(self):
        config = HAConfig(url="http://ha.local:8123", token="test")
        client = HAClient(config)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content_type = "application/json"
        mock_resp.json = AsyncMock(return_value=[{"entity_id": "light.living_room", "state": "on"}])
        mock_resp.raise_for_status = MagicMock()

        mock_session = AsyncMock()
        mock_session.request.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.closed = False
        client._session = mock_session

        result = await client.call_service("light", "turn_on", {"entity_id": "light.living_room"})
        assert result["success"] is True
        assert len(result["entities"]) == 1

    @pytest.mark.asyncio
    async def test_get_entities_by_domain(self):
        config = HAConfig(url="http://ha.local:8123", token="test")
        client = HAClient(config)

        states = [
            {"entity_id": "light.living_room", "state": "on"},
            {"entity_id": "light.bedroom", "state": "off"},
            {"entity_id": "switch.fan", "state": "on"},
        ]

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content_type = "application/json"
        mock_resp.json = AsyncMock(return_value=states)
        mock_resp.raise_for_status = MagicMock()

        mock_session = AsyncMock()
        mock_session.request.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session.closed = False
        client._session = mock_session

        lights = await client.get_entities_by_domain("light")
        assert len(lights) == 2
        assert all(e["entity_id"].startswith("light.") for e in lights)


# --- Home archetypes tests ---

class TestHomeArchetypes:
    def test_list_returns_four(self):
        from halbert_core.persona.home_archetypes import list_home_archetypes
        archetypes = list_home_archetypes()
        # If Haloysius not installed, returns empty — that's OK
        if len(archetypes) == 0:
            pytest.skip("Haloysius not installed")
        assert len(archetypes) == 4

    def test_expected_ids(self):
        from halbert_core.persona.home_archetypes import list_home_archetypes
        archetypes = list_home_archetypes()
        if len(archetypes) == 0:
            pytest.skip("Haloysius not installed")
        ids = {a["id"] for a in archetypes}
        assert ids == {"steward", "companion", "guardian", "concierge"}

    def test_get_by_id(self):
        from halbert_core.persona.home_archetypes import get_home_archetype
        archetype = get_home_archetype("steward")
        if archetype is None:
            pytest.skip("Haloysius not installed")
        assert archetype.id == "steward"
        assert archetype.name == "The Steward"


# --- Cognition wiring parameterization tests ---

class TestCognitionWiringParameterization:
    def test_default_persona_id(self):
        from halbert_core.integrations.cognition_wiring import _get_persona_id
        # Ensure env is not set
        old = os.environ.pop("HALBERT_PERSONA_ID", None)
        try:
            assert _get_persona_id() == "halbert"
        finally:
            if old is not None:
                os.environ["HALBERT_PERSONA_ID"] = old

    def test_env_persona_id(self):
        from halbert_core.integrations.cognition_wiring import _get_persona_id
        old = os.environ.get("HALBERT_PERSONA_ID")
        os.environ["HALBERT_PERSONA_ID"] = "home"
        try:
            assert _get_persona_id() == "home"
        finally:
            if old is None:
                os.environ.pop("HALBERT_PERSONA_ID", None)
            else:
                os.environ["HALBERT_PERSONA_ID"] = old

    def test_env_scene_context(self):
        from halbert_core.integrations.cognition_wiring import _get_scene_context
        old = os.environ.get("HALBERT_SCENE_CONTEXT")
        os.environ["HALBERT_SCENE_CONTEXT"] = "smart home automation"
        try:
            assert _get_scene_context() == "smart home automation"
        finally:
            if old is None:
                os.environ.pop("HALBERT_SCENE_CONTEXT", None)
            else:
                os.environ["HALBERT_SCENE_CONTEXT"] = old

    def test_scene_context_falls_back_to_platform(self):
        from halbert_core.integrations.cognition_wiring import _get_scene_context
        old = os.environ.pop("HALBERT_SCENE_CONTEXT", None)
        try:
            ctx = _get_scene_context()
            assert "administration" in ctx
        finally:
            if old is not None:
                os.environ["HALBERT_SCENE_CONTEXT"] = old


# --- HA tool registration tests ---

class TestHAToolRegistration:
    def test_register_ha_tools(self):
        """Test that register_ha_tools adds both tools to a mock executor."""
        from halbert_core.integrations.home_assistant.ha_tool import register_ha_tools

        class MockExecutor:
            def __init__(self):
                self.tools = {}
                self.schemas = {}

            def register(self, name, handler, schema):
                self.tools[name] = handler
                self.schemas[name] = schema

        executor = MockExecutor()
        register_ha_tools(executor)

        assert "ha_call_service" in executor.tools
        assert "ha_get_entity_state" in executor.tools
        assert executor.schemas["ha_call_service"]["name"] == "ha_call_service"
        assert executor.schemas["ha_get_entity_state"]["name"] == "ha_get_entity_state"
        # Verify required fields
        assert "domain" in executor.schemas["ha_call_service"]["parameters"]["properties"]
        assert "entity_id" in executor.schemas["ha_get_entity_state"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_call_service_handler_not_configured(self, monkeypatch):
        """Handler returns error message when HA is not configured."""
        from halbert_core.integrations.home_assistant import ha_tool
        from halbert_core.integrations.home_assistant.ha_config import HAConfig

        # Reset client with unconfigured config
        await ha_tool.close_client()
        monkeypatch.setattr(
            "halbert_core.integrations.home_assistant.ha_tool.load_ha_config",
            lambda: HAConfig(),
        )

        result = await ha_tool._ha_call_service_handler({
            "domain": "light",
            "service": "turn_on",
            "entity_id": "light.test",
        })
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_get_entity_state_handler_not_configured(self, monkeypatch):
        """Handler returns error message when HA is not configured."""
        from halbert_core.integrations.home_assistant import ha_tool
        from halbert_core.integrations.home_assistant.ha_config import HAConfig

        await ha_tool.close_client()
        monkeypatch.setattr(
            "halbert_core.integrations.home_assistant.ha_tool.load_ha_config",
            lambda: HAConfig(),
        )

        result = await ha_tool._ha_get_entity_state_handler({
            "entity_id": "light.test",
        })
        assert "not configured" in result.lower()
