# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for the Phase 3 HA config SourcePrep bridge.

S2 (handoff HOME-AUTOMATION-SIMPLIFICATION-2026-08-30): home variants run
without SourcePrep, so this bridge is default-disabled and the
/home/config-search endpoints plus the ha_search_config LLM tools are
retired (see test_ha_sourceprep_variants.py for the variant gating).
These tests pin the bridge's opt-in behaviour for an operator who
explicitly sets HA_SOURCEPREP_ENABLED=1.
"""

import os
from unittest.mock import MagicMock, patch

from halbert_core.integrations.home_assistant.ha_config_bridge import (
    HAConfigSourcePrep,
    check_sourceprep_status,
    search_ha_config,
    search_ha_automations,
    push_automation_edges,
)


class TestHAConfigSourcePrep:
    def test_from_env_defaults(self):
        """S2: the bridge is default-disabled — HA variants have no
        SourcePrep, so nothing short of an explicit opt-in turns it on."""
        config = HAConfigSourcePrep.from_env()
        assert config.project_id == "ha-config"
        assert config.sourceprep_url == "http://localhost:8400"
        assert config.ha_config_path == "/config"
        assert config.enabled is False

    def test_from_env_explicit_opt_in(self):
        with patch.dict(os.environ, {"HA_SOURCEPREP_ENABLED": "1"}):
            config = HAConfigSourcePrep.from_env()
        assert config.enabled is True

    def test_from_env_custom(self):
        with patch.dict(os.environ, {
            "HA_SOURCEPREP_PROJECT_ID": "my-ha",
            "SOURCEPREP_URL": "http://sp:9000",
            "HA_CONFIG_PATH": "/homeassistant/config",
            "HA_SOURCEPREP_ENABLED": "true",
        }):
            config = HAConfigSourcePrep.from_env()
            assert config.project_id == "my-ha"
            assert config.sourceprep_url == "http://sp:9000"
            assert config.ha_config_path == "/homeassistant/config"
            assert config.enabled is True

    def test_default_disabled_env_search_is_a_no_op(self):
        """With the S2 default, search_ha_config() must not touch the
        network at all — from_env() yields enabled=False and the bridge
        returns [] before a client is ever built."""
        with patch(
            "halbert_core.integrations.home_assistant.ha_config_bridge.get_client"
        ) as mock_get:
            results = search_ha_config("automations for the front door")
        assert results == []
        mock_get.assert_not_called()


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
