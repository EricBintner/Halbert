# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for Phase 3 HA config SourcePrep bridge and tools."""

import os
from unittest.mock import MagicMock, patch

import pytest

from halbert_core.integrations.home_assistant.ha_config_bridge import (
    HAConfigSourcePrep,
    check_sourceprep_status,
    search_ha_config,
    search_ha_automations,
    push_automation_edges,
)


class TestHAConfigSourcePrep:
    def test_from_env_defaults(self):
        config = HAConfigSourcePrep.from_env()
        assert config.project_id == "ha-config"
        assert config.sourceprep_url == "http://localhost:8400"
        assert config.ha_config_path == "/config"
        assert config.enabled is True

    def test_from_env_custom(self):
        with patch.dict(os.environ, {
            "HA_SOURCEPREP_PROJECT_ID": "my-ha",
            "SOURCEPREP_URL": "http://sp:9000",
            "HA_CONFIG_PATH": "/homeassistant/config",
            "HA_SOURCEPREP_ENABLED": "false",
        }):
            config = HAConfigSourcePrep.from_env()
            assert config.project_id == "my-ha"
            assert config.sourceprep_url == "http://sp:9000"
            assert config.ha_config_path == "/homeassistant/config"
            assert config.enabled is False


class TestCheckSourcePrepStatus:
    def test_disabled_returns_error(self):
        config = HAConfigSourcePrep(enabled=False)
        status = check_sourceprep_status(config)
        assert status["daemon_reachable"] is False
        assert "disabled" in status["error"]

    def test_daemon_not_reachable(self):
        config = HAConfigSourcePrep(enabled=True, sourceprep_url="http://localhost:9999")
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            client.health.return_value = False
            mock_get.return_value = client
            status = check_sourceprep_status(config)
        assert status["daemon_reachable"] is False
        assert "not reachable" in status["error"]

    def test_daemon_reachable_not_indexed(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            client.health.return_value = True
            client.search.side_effect = Exception("project not found")
            mock_get.return_value = client
            status = check_sourceprep_status(config)
        assert status["daemon_reachable"] is True
        assert status["indexed"] is False

    def test_daemon_reachable_and_indexed(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            client.health.return_value = True
            client.search.return_value = {"chunks": [{"content": "test"}]}
            mock_get.return_value = client
            status = check_sourceprep_status(config)
        assert status["daemon_reachable"] is True
        assert status["indexed"] is True
        assert status["error"] is None


class TestSearchHAConfig:
    def test_disabled_returns_empty(self):
        config = HAConfigSourcePrep(enabled=False)
        results = search_ha_config("test", config=config)
        assert results == []

    def test_search_returns_chunks(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            client.get_context.return_value = {
                "chunks": [
                    {"file_path": "/config/automations.yaml", "content": "test automation", "score": 0.85},
                ]
            }
            mock_get.return_value = client
            results = search_ha_config("front door", config=config)
        assert len(results) == 1
        assert results[0]["file_path"] == "/config/automations.yaml"

    def test_search_handles_error(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            client.get_context.side_effect = Exception("connection failed")
            mock_get.return_value = client
            results = search_ha_config("test", config=config)
        assert results == []


class TestSearchHAAutomations:
    def test_filters_to_automation_files(self):
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.search_ha_config") as mock_search:
            mock_search.return_value = [
                {"file_path": "/config/automations.yaml", "content": "auto 1"},
                {"file_path": "/config/configuration.yaml", "content": "config"},
                {"file_path": "/config/scripts.yaml", "content": "script 1"},
            ]
            results = search_ha_automations("door lock")
        assert len(results) == 2
        assert all("automation" in r["file_path"] or "script" in r["file_path"] for r in results)

    def test_returns_all_if_no_automation_matches(self):
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.search_ha_config") as mock_search:
            mock_search.return_value = [
                {"file_path": "/config/configuration.yaml", "content": "config"},
                {"file_path": "/config/sensors.yaml", "content": "sensors"},
            ]
            results = search_ha_automations("test")
        assert len(results) == 2  # Returns all when none match filter


class TestPushAutomationEdges:
    def test_disabled_returns_false(self):
        config = HAConfigSourcePrep(enabled=False)
        result = push_automation_edges([], config=config)
        assert result is False

    def test_empty_automations_returns_true(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client
            result = push_automation_edges([], config=config)
        assert result is True
        client.push_external_edges.assert_not_called()

    def test_pushes_edges(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client
            result = push_automation_edges([
                {
                    "id": "auto_front_door",
                    "file_path": "/config/automations/front_door.yaml",
                    "triggers": ["lock.front_door", "binary_sensor.front_door"],
                    "actions": ["light.front_porch", "notify.mobile_app"],
                },
            ], config=config)
        assert result is True
        client.push_external_edges.assert_called_once()
        call_args = client.push_external_edges.call_args
        edges = call_args[0][0]
        assert len(edges) == 4  # 2 triggers + 2 actions
        assert call_args.kwargs.get("replace_origin") == "ha-config"

    def test_handles_push_error(self):
        config = HAConfigSourcePrep(enabled=True)
        with patch("halbert_core.integrations.home_assistant.ha_config_bridge.get_client") as mock_get:
            client = MagicMock()
            client.push_external_edges.side_effect = Exception("push failed")
            mock_get.return_value = client
            result = push_automation_edges([
                {"id": "test", "file_path": "/test.yaml", "triggers": ["a"], "actions": ["b"]},
            ], config=config)
        assert result is False


# --- Tool handler tests ---

class TestHAConfigToolHandlers:
    @pytest.mark.asyncio
    async def test_search_config_handler_returns_results(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import _ha_search_config_handler

        with patch("halbert_core.integrations.home_assistant.ha_config_tools.search_ha_config") as mock_search:
            mock_search.return_value = [
                {"file_path": "/config/automations.yaml", "content": "test auto", "score": 0.9},
            ]
            result = await _ha_search_config_handler({"query": "front door automations"})
        assert "Found 1 config result" in result
        assert "/config/automations.yaml" in result

    @pytest.mark.asyncio
    async def test_search_config_handler_no_results(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import _ha_search_config_handler

        with patch("halbert_core.integrations.home_assistant.ha_config_tools.search_ha_config") as mock_search:
            mock_search.return_value = []
            result = await _ha_search_config_handler({"query": "test"})
        assert "No HA config results found" in result

    @pytest.mark.asyncio
    async def test_search_config_handler_empty_query(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import _ha_search_config_handler

        result = await _ha_search_config_handler({"query": ""})
        assert "No query provided" in result

    @pytest.mark.asyncio
    async def test_config_status_handler_healthy(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import _ha_config_status_handler

        with patch("halbert_core.integrations.home_assistant.ha_config_tools.check_sourceprep_status") as mock_status:
            mock_status.return_value = {
                "daemon_reachable": True,
                "project_id": "ha-config",
                "config_path": "/config",
                "indexed": True,
                "error": None,
            }
            result = await _ha_config_status_handler({})
        assert "running" in result
        assert "indexed" in result

    @pytest.mark.asyncio
    async def test_config_status_handler_not_reachable(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import _ha_config_status_handler

        with patch("halbert_core.integrations.home_assistant.ha_config_tools.check_sourceprep_status") as mock_status:
            mock_status.return_value = {
                "daemon_reachable": False,
                "project_id": "ha-config",
                "config_path": "/config",
                "indexed": False,
                "error": "Connection refused",
            }
            result = await _ha_config_status_handler({})
        assert "not reachable" in result

    @pytest.mark.asyncio
    async def test_config_status_handler_not_indexed(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import _ha_config_status_handler

        with patch("halbert_core.integrations.home_assistant.ha_config_tools.check_sourceprep_status") as mock_status:
            mock_status.return_value = {
                "daemon_reachable": True,
                "project_id": "ha-config",
                "config_path": "/config",
                "indexed": False,
                "error": None,
            }
            result = await _ha_config_status_handler({})
        assert "not indexed" in result


class TestRegisterHAConfigTools:
    def test_registration(self):
        from halbert_core.integrations.home_assistant.ha_config_tools import register_ha_config_tools

        executor = MagicMock()
        register_ha_config_tools(executor)

        assert executor.register.call_count == 2
        registered_names = [call.kwargs["name"] for call in executor.register.call_args_list]
        assert "ha_search_config" in registered_names
        assert "ha_config_status" in registered_names
