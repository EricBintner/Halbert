# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Unit tests for Phase 6 HACS integration and Assist API tools."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAssistToolsHandler:
    @pytest.mark.asyncio
    async def test_empty_text(self):
        from halbert_core.integrations.home_assistant.ha_assist_tools import _ha_assist_process_handler
        result = await _ha_assist_process_handler({"text": ""})
        assert "No command" in result

    @pytest.mark.asyncio
    async def test_ha_not_configured(self):
        from halbert_core.integrations.home_assistant.ha_assist_tools import _ha_assist_process_handler

        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = False
            mock_load.return_value = mock_config
            result = await _ha_assist_process_handler({"text": "turn on the lights"})
        assert "not configured" in result

    @pytest.mark.asyncio
    async def test_successful_assist_call(self):
        from halbert_core.integrations.home_assistant.ha_assist_tools import _ha_assist_process_handler

        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = True
            mock_config.url = "http://ha.local:8123"
            mock_config.token = "test-token"
            mock_config.verify_ssl = True
            mock_load.return_value = mock_config

            with patch("halbert_core.integrations.home_assistant.ha_assist_tools._call_assist_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {
                    "conversation_id": "conv-123",
                    "response": {
                        "speech": {"plain": {"speech": "Turned on 2 lights"}},
                        "response_type": "action_done",
                    },
                }
                result = await _ha_assist_process_handler({"text": "turn on the lights"})
        assert "Turned on 2 lights" in result

    @pytest.mark.asyncio
    async def test_assist_call_error(self):
        from halbert_core.integrations.home_assistant.ha_assist_tools import _ha_assist_process_handler

        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = True
            mock_config.url = "http://ha.local:8123"
            mock_config.token = "test-token"
            mock_config.verify_ssl = True
            mock_load.return_value = mock_config

            with patch("halbert_core.integrations.home_assistant.ha_assist_tools._call_assist_api", new_callable=AsyncMock) as mock_api:
                mock_api.side_effect = Exception("Connection refused")
                result = await _ha_assist_process_handler({"text": "turn on the lights"})
        assert "Failed" in result

    @pytest.mark.asyncio
    async def test_assist_with_conversation_id(self):
        from halbert_core.integrations.home_assistant.ha_assist_tools import _ha_assist_process_handler

        with patch("halbert_core.integrations.home_assistant.ha_config.load_ha_config") as mock_load:
            mock_config = MagicMock()
            mock_config.is_configured.return_value = True
            mock_config.url = "http://ha.local:8123"
            mock_config.token = "test-token"
            mock_config.verify_ssl = True
            mock_load.return_value = mock_config

            with patch("halbert_core.integrations.home_assistant.ha_assist_tools._call_assist_api", new_callable=AsyncMock) as mock_api:
                mock_api.return_value = {
                    "response": {
                        "speech": {"plain": {"speech": "The temperature is 72"}},
                        "response_type": "query_answer",
                    },
                }
                result = await _ha_assist_process_handler({
                    "text": "what's the temperature",
                    "conversation_id": "conv-456",
                    "language": "en",
                })
        assert "72" in result
        call_kwargs = mock_api.call_args.kwargs
        assert call_kwargs["conversation_id"] == "conv-456"
        assert call_kwargs["language"] == "en"


class TestAssistToolsRegistration:
    def test_registration(self):
        from halbert_core.integrations.home_assistant.ha_assist_tools import register_assist_tools

        executor = MagicMock()
        register_assist_tools(executor)

        assert executor.register.call_count == 1
        call = executor.register.call_args
        assert call.kwargs["name"] == "ha_assist_process"


class TestHACSManifest:
    def test_manifest_json_valid(self):
        """Test that the HACS manifest.json is valid and has required fields."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).resolve().parents[2] / "custom_components" / "halbert" / "manifest.json"
        if not manifest_path.exists():
            pytest.skip("manifest.json not found (may be in worktree)")

        manifest = json.loads(manifest_path.read_text())

        assert manifest["domain"] == "halbert"
        assert manifest["name"] == "Halbert"
        assert manifest["version"] == "0.1.0"
        assert manifest["integration_type"] == "service"
        assert manifest["config_flow"] is True
        assert "codeowners" in manifest
        assert "documentation" in manifest
        assert "issue_tracker" in manifest

    def test_hacs_json_valid(self):
        """Test that hacs.json exists and is valid."""
        import json
        from pathlib import Path

        hacs_path = Path(__file__).resolve().parents[2] / "hacs.json"
        if not hacs_path.exists():
            pytest.skip("hacs.json not found (may be in worktree)")

        hacs = json.loads(hacs_path.read_text())
        assert hacs["name"] == "Halbert"
