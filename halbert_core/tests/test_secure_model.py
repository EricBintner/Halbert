# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the secure_model slot and local-only enforcement."""

import pytest
from halbert_core.model.llm_config import (
    SLOTS,
    default_llm_config,
    normalise,
    _is_local_url,
    resolve_from,
    ResolvedModel,
)


class TestSecureModelSlot:
    """secure_model is a 4th slot in the SLOTS tuple and default config."""

    def test_secure_model_in_slots(self):
        assert "secure_model" in SLOTS

    def test_default_config_has_secure_model(self):
        cfg = default_llm_config()
        assert "secure_model" in cfg
        assert cfg["secure_model"] == {"enabled": False, "endpoint_id": "", "model": ""}

    def test_normalise_adds_secure_model_when_missing(self):
        cfg = normalise({"chat_model": {"enabled": False, "endpoint_id": "", "model": ""}})
        assert "secure_model" in cfg
        assert cfg["secure_model"]["enabled"] is False

    def test_normalise_preserves_enabled_secure_model(self):
        cfg = normalise({
            "saved_endpoints": [
                {"id": "ep1", "name": "Local", "provider": "ollama", "url": "http://localhost:11434", "api_key": ""},
            ],
            "secure_model": {"enabled": True, "endpoint_id": "ep1", "model": "test-model"},
        })
        assert cfg["secure_model"]["enabled"] is True
        assert cfg["secure_model"]["model"] == "test-model"


class TestLocalOnlyEnforcement:
    """secure_model endpoints must be local (loopback/unspecified)."""

    @pytest.mark.parametrize("url,expected", [
        ("http://localhost:11434", True),
        ("http://127.0.0.1:11434", True),
        ("http://0.0.0.0:11434", True),
        ("http://[::1]:11434", True),
        ("https://api.openai.com/v1", False),
        ("http://192.168.1.100:11434", False),
        ("http://attacker.com/localhost", False),
        ("http://gpu-rig.tailscale:11434", False),
        ("", False),
        ("not-a-url", False),
    ])
    def test_is_local_url(self, url, expected):
        assert _is_local_url(url) is expected

    def test_normalise_disables_secure_model_pointing_at_cloud(self):
        cfg = normalise({
            "saved_endpoints": [
                {"id": "ep_cloud", "name": "OpenAI", "provider": "openai", "url": "https://api.openai.com/v1", "api_key": "sk-x"},
            ],
            "secure_model": {"enabled": True, "endpoint_id": "ep_cloud", "model": "gpt-4o"},
        })
        assert cfg["secure_model"]["enabled"] is False

    def test_normalise_disables_secure_model_pointing_at_lan(self):
        cfg = normalise({
            "saved_endpoints": [
                {"id": "ep_lan", "name": "LAN GPU", "provider": "ollama", "url": "http://192.168.1.50:11434", "api_key": ""},
            ],
            "secure_model": {"enabled": True, "endpoint_id": "ep_lan", "model": "test"},
        })
        assert cfg["secure_model"]["enabled"] is False

    def test_normalise_keeps_secure_model_on_localhost(self):
        cfg = normalise({
            "saved_endpoints": [
                {"id": "ep_local", "name": "Local Ollama", "provider": "ollama", "url": "http://localhost:11434", "api_key": ""},
            ],
            "secure_model": {"enabled": True, "endpoint_id": "ep_local", "model": "test"},
        })
        assert cfg["secure_model"]["enabled"] is True

    def test_normalise_keeps_secure_model_on_ipv6_loopback(self):
        cfg = normalise({
            "saved_endpoints": [
                {"id": "ep_v6", "name": "Local V6", "provider": "ollama", "url": "http://[::1]:11434", "api_key": ""},
            ],
            "secure_model": {"enabled": True, "endpoint_id": "ep_v6", "model": "test"},
        })
        assert cfg["secure_model"]["enabled"] is True

    def test_other_slots_not_affected_by_local_check(self):
        """chat_model pointing at cloud should still be enabled."""
        cfg = normalise({
            "saved_endpoints": [
                {"id": "ep_cloud", "name": "OpenAI", "provider": "openai", "url": "https://api.openai.com/v1", "api_key": "sk-x"},
            ],
            "chat_model": {"enabled": True, "endpoint_id": "ep_cloud", "model": "gpt-4o"},
            "secure_model": {"enabled": True, "endpoint_id": "ep_cloud", "model": "gpt-4o"},
        })
        assert cfg["chat_model"]["enabled"] is True
        assert cfg["secure_model"]["enabled"] is False


class TestResolveSecureModel:
    """resolve_from returns ResolvedModel for enabled secure_model."""

    def test_resolve_secure_model(self):
        file_cfg = {
            "llm_config": normalise({
                "saved_endpoints": [
                    {"id": "ep1", "name": "Local", "provider": "ollama", "url": "http://localhost:11434", "api_key": ""},
                ],
                "secure_model": {"enabled": True, "endpoint_id": "ep1", "model": "test"},
            })
        }
        result = resolve_from(file_cfg, "secure_model")
        assert result is not None
        assert isinstance(result, ResolvedModel)
        assert result.model == "test"
        assert result.url == "http://localhost:11434"
        assert result.provider == "ollama"

    def test_resolve_secure_model_disabled(self):
        file_cfg = {"llm_config": default_llm_config()}
        result = resolve_from(file_cfg, "secure_model")
        assert result is None
