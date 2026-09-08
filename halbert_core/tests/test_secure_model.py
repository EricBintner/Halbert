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


class TestNormaliseRefusesCloudTaggedSecureModel:
    """SEC-21, at config-write time.

    ``normalise`` already disables a ``secure_model`` whose endpoint URL is
    not loopback. It did not look at the model, so ``glm-5.3:cloud`` on
    ``localhost:11434`` saved as an enabled secure model -- and the turn-time
    gate, which trusted the slot, never checked it either. Refusing it here
    means the misconfiguration cannot be saved in the first place, which is
    earlier and louder than failing a turn.
    """

    def _cfg(self, model):
        return {
            "saved_endpoints": [{
                "id": "ep_local", "name": "Local Ollama",
                "provider": "ollama", "url": "http://localhost:11434", "api_key": "",
            }],
            "secure_model": {"enabled": True, "endpoint_id": "ep_local", "model": model},
        }

    def test_a_cloud_tagged_secure_model_is_disabled(self):
        cfg = normalise(self._cfg("glm-5.3:cloud"))
        assert cfg["secure_model"]["enabled"] is False

    def test_the_model_name_is_kept_so_the_ui_can_say_why(self):
        # Disabled, not erased: the picker should show what was configured
        # and why it will not be used, not a blank slot.
        cfg = normalise(self._cfg("glm-5.3:cloud"))
        assert cfg["secure_model"]["model"] == "glm-5.3:cloud"

    def test_a_local_secure_model_on_the_same_endpoint_stays_enabled(self):
        cfg = normalise(self._cfg("qwen3:8b"))
        assert cfg["secure_model"]["enabled"] is True

    def test_other_slots_may_still_hold_cloud_tags(self):
        # The rule is the secure slot's rule. chat_model on a :cloud tag is a
        # choice the user is allowed to make; the secure gate keeps secrets
        # away from it per turn.
        cfg = self._cfg("qwen3:8b")
        cfg["chat_model"] = {"enabled": True, "endpoint_id": "ep_local",
                             "model": "deepseek-v4-flash:cloud"}
        out = normalise(cfg)
        assert out["chat_model"]["enabled"] is True
