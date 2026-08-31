# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for Apple Intelligence auto-provisioning."""
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from halbert_core.model import llm_config as store
from halbert_core.model.auto_provision import auto_provision_apple_intelligence
from halbert_core.model.hardware_detector import HardwareCapabilities, HardwareProfile


def _write_config(user: Path, data: dict) -> Path:
    p = user / "models.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(data))
    return p


def _empty_config() -> dict:
    return {
        "llm_config": {
            "chat_model": {"enabled": False, "model": "", "endpoint_id": ""},
            "specialist_model": {"enabled": False, "model": "", "endpoint_id": ""},
            "vision_model": {"enabled": False, "model": "", "endpoint_id": ""},
            "secure_model": {"enabled": False, "model": "", "endpoint_id": ""},
            "saved_endpoints": [],
        }
    }


def _hw(
    ai_available: bool = True,
    unified_mem_gb: int = 128,
    bridge_running: bool = False,
) -> HardwareCapabilities:
    return HardwareCapabilities(
        total_ram_gb=128,
        available_ram_gb=100.0,
        cpu_count=20,
        platform="darwin",
        platform_friendly="mlx",
        is_apple_silicon=True,
        unified_memory_gb=unified_mem_gb,
        metal_gpu={"metal_version": "spdisplays_metal4", "gpu_name": "Apple M1 Ultra"},
        apple_intelligence_available=ai_available,
        apple_intelligence_bridge_running=bridge_running,
        profile=HardwareProfile.MAC_STUDIO_128GB,
    )


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    _write_config(tmp_path, _empty_config())
    return tmp_path


class TestAutoProvisionAppleIntelligence:
    def test_provisions_secure_model_on_eligible_host(self, config_dir):
        hw = _hw(ai_available=True, unified_mem_gb=128)
        changed = auto_provision_apple_intelligence(hw)
        assert changed is True

        cfg = store.load_global(use_cache=False)
        secure = cfg["secure_model"]
        assert secure["model"] == store.APPLE_FOUNDATION_MODEL
        assert secure["enabled"] is True

        eps = [e for e in cfg["saved_endpoints"] if e["provider"] == "apple-foundation"]
        assert len(eps) == 1
        assert eps[0]["url"] == store.APPLE_FOUNDATION_URL

    def test_does_not_assign_chat_model_on_32gb_plus(self, config_dir):
        """On 32GB+ Macs chat_model is left for the user to configure."""
        hw = _hw(ai_available=True, unified_mem_gb=128)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == ""
        assert cfg["chat_model"]["enabled"] is False

    def test_assigns_chat_model_on_16_to_24gb(self, config_dir):
        """On 16-24GB Macs the single local model rule applies."""
        hw = _hw(ai_available=True, unified_mem_gb=16)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == store.APPLE_FOUNDATION_MODEL
        assert cfg["chat_model"]["enabled"] is True

    def test_assigns_chat_model_on_24gb_boundary(self, config_dir):
        hw = _hw(ai_available=True, unified_mem_gb=24)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == store.APPLE_FOUNDATION_MODEL

    def test_does_not_assign_chat_model_on_25gb(self, config_dir):
        hw = _hw(ai_available=True, unified_mem_gb=25)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == ""

    def test_idempotent_when_endpoint_exists(self, config_dir):
        """Second call does nothing when the endpoint is already registered."""
        hw = _hw(ai_available=True, unified_mem_gb=128)
        assert auto_provision_apple_intelligence(hw) is True
        # Second call: endpoint already exists, should return False
        assert auto_provision_apple_intelligence(hw) is False

    def test_does_not_overwrite_existing_secure_model(self, config_dir):
        """A user's existing secure_model assignment is preserved."""
        cfg = _empty_config()
        cfg["llm_config"]["secure_model"] = {
            "enabled": True, "model": "my-ollama-model", "endpoint_id": "ep_1",
        }
        cfg["llm_config"]["saved_endpoints"] = [
            {"id": "ep_1", "name": "Local Ollama", "provider": "ollama", "url": "http://localhost:11434"},
        ]
        _write_config(Path(config_dir), cfg)

        hw = _hw(ai_available=True, unified_mem_gb=128)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["model"] == "my-ollama-model"

    def test_does_not_overwrite_existing_chat_model(self, config_dir):
        """A user's existing chat_model assignment is preserved."""
        cfg = _empty_config()
        cfg["llm_config"]["chat_model"] = {
            "enabled": True, "model": "my-chat-model", "endpoint_id": "ep_1",
        }
        cfg["llm_config"]["saved_endpoints"] = [
            {"id": "ep_1", "name": "Local Ollama", "provider": "ollama", "url": "http://localhost:11434"},
        ]
        _write_config(Path(config_dir), cfg)

        hw = _hw(ai_available=True, unified_mem_gb=16)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == "my-chat-model"

    def test_no_provisioning_when_not_eligible(self, config_dir):
        hw = _hw(ai_available=False)
        changed = auto_provision_apple_intelligence(hw)
        assert changed is False

        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["model"] == ""
        eps = [e for e in cfg["saved_endpoints"] if e["provider"] == "apple-foundation"]
        assert len(eps) == 0


class TestHomeVariantGate:
    """home never configure secure_model (S1): an HA variant's
    LLM reaches the house through tool calls that abstract credentials
    away, so Apple Intelligence is not provisioned for them at all."""

    @pytest.fixture(params=["home"])
    def home_variant(self, request, monkeypatch, capability_registry):
        from halbert_core.integrations import cognition_wiring
        monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: request.param)
        # F5: provisioning is capability-gated (CAP_SECURE_MODEL); the
        # home preset carries no secure_model, which is what this pins.
        capability_registry.set_variant(request.param)

    def test_home_variant_skips_provisioning_entirely(self, home_variant, config_dir):
        """16GB host: both secure_model and chat_model would be assigned —
        on a home automation variant neither is."""
        hw = _hw(ai_available=True, unified_mem_gb=16)
        assert auto_provision_apple_intelligence(hw) is False

        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["model"] == ""
        assert cfg["secure_model"]["enabled"] is False
        assert cfg["chat_model"]["model"] == ""
        eps = [e for e in cfg["saved_endpoints"] if e["provider"] == "apple-foundation"]
        assert len(eps) == 0

    def test_sysadmin_variant_provisions_as_before(self, config_dir, monkeypatch,
                                                    capability_registry):
        from halbert_core.integrations import cognition_wiring
        monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: "sysadmin")
        # F5: pin the capability explicitly rather than inheriting this
        # machine's real secure-model probe result.
        capability_registry.set_capability("secure_model", True)
        hw = _hw(ai_available=True, unified_mem_gb=128)
        assert auto_provision_apple_intelligence(hw) is True

        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["model"] == store.APPLE_FOUNDATION_MODEL
