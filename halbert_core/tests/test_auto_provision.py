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
        hw = _hw(ai_available=True, unified_mem_gb=128, bridge_running=True)
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
        hw = _hw(ai_available=True, unified_mem_gb=128, bridge_running=True)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == ""
        assert cfg["chat_model"]["enabled"] is False

    def test_assigns_chat_model_on_16_to_24gb(self, config_dir):
        """On 16-24GB Macs the single local model rule applies."""
        hw = _hw(ai_available=True, unified_mem_gb=16, bridge_running=True)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == store.APPLE_FOUNDATION_MODEL
        assert cfg["chat_model"]["enabled"] is True

    def test_assigns_chat_model_on_24gb_boundary(self, config_dir):
        hw = _hw(ai_available=True, unified_mem_gb=24, bridge_running=True)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == store.APPLE_FOUNDATION_MODEL

    def test_does_not_assign_chat_model_on_25gb(self, config_dir):
        hw = _hw(ai_available=True, unified_mem_gb=25, bridge_running=True)
        auto_provision_apple_intelligence(hw)

        cfg = store.load_global(use_cache=False)
        assert cfg["chat_model"]["model"] == ""

    def test_idempotent_when_endpoint_exists(self, config_dir):
        """Second call does nothing when the endpoint is already registered."""
        hw = _hw(ai_available=True, unified_mem_gb=128, bridge_running=True)
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

        hw = _hw(ai_available=True, unified_mem_gb=128, bridge_running=True)
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

        hw = _hw(ai_available=True, unified_mem_gb=16, bridge_running=True)
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

    def test_no_provisioning_when_eligible_but_bridge_not_running(self, config_dir):
        """Eligible hardware with the FoundationModels sidecar not started
        yet is a valid state (R05-F2/U4-20): the endpoint would be inert,
        so it is not registered at all — nothing to hide from the picker."""
        hw = _hw(ai_available=True, unified_mem_gb=128, bridge_running=False)
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
        # F5: provisioning is capability-gated (CAP_SECURE_MODEL_ALLOWED);
        # the home preset carries no secure_model_allowed, which is what
        # this pins.
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
        # machine's real secure-model-allowed preset resolution.
        capability_registry.set_capability("secure_model_allowed", True)
        hw = _hw(ai_available=True, unified_mem_gb=128, bridge_running=True)
        assert auto_provision_apple_intelligence(hw) is True

        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["model"] == store.APPLE_FOUNDATION_MODEL


class TestReconcileWhenTheBridgeIsDown:
    """APPLE-1: the endpoint was registered at a boot where the probe passed,
    and nothing ever looked again.

    The FoundationModels sidecar was never built, so the probe now fails --
    but ``secure_model`` still points at ``127.0.0.1:11435``, and the boot
    path skips provisioning entirely once the endpoint exists, so the dead
    assignment is never revisited. Every secure turn then tries a port with
    nothing on it and falls back to the guide, which is what exposed SEC-21.

    Reconciling is the symmetric operation to provisioning: provisioning
    wrote the slot when the bridge answered, so this clears it when the
    bridge does not, at WARNING, naming the slot. The endpoint itself stays
    registered -- the host is still eligible and the picker should still
    list it -- only the *assignment* to a dead endpoint goes.
    """

    def _provision_then_kill_bridge(self):
        auto_provision_apple_intelligence(_hw(bridge_running=True))
        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["model"] == store.APPLE_FOUNDATION_MODEL
        return cfg["secure_model"]["endpoint_id"]

    def test_a_dead_bridge_disables_the_secure_slot(self, config_dir, caplog):
        import logging
        from halbert_core.model.auto_provision import reconcile_apple_intelligence

        ep_id = self._provision_then_kill_bridge()
        with caplog.at_level(logging.WARNING):
            cleared = reconcile_apple_intelligence(_hw(bridge_running=False))

        assert cleared == ["secure_model"]
        cfg = store.load_global(use_cache=False)
        assert cfg["secure_model"]["enabled"] is False
        assert any("secure_model" in r.message and "bridge" in r.message.lower()
                   for r in caplog.records), "clearing a configured slot must be said out loud"
        # The endpoint stays: eligibility has not changed, only reachability.
        assert any(e["id"] == ep_id for e in cfg["saved_endpoints"])

    def test_a_live_bridge_leaves_the_slot_alone(self, config_dir):
        from halbert_core.model.auto_provision import reconcile_apple_intelligence

        self._provision_then_kill_bridge()
        assert reconcile_apple_intelligence(_hw(bridge_running=True)) == []
        assert store.load_global(use_cache=False)["secure_model"]["enabled"] is True

    def test_it_only_touches_slots_that_point_at_the_apple_endpoint(self, config_dir):
        from halbert_core.model.auto_provision import reconcile_apple_intelligence

        self._provision_then_kill_bridge()
        # A local Ollama secure model the user chose deliberately must survive
        # a dead Apple bridge untouched.
        ollama_id = store.ensure_endpoint("http://localhost:11434", "ollama", "Local Ollama")
        store.set_slot("secure_model", "qwen3:8b", ollama_id)
        assert reconcile_apple_intelligence(_hw(bridge_running=False)) == []
        assert store.load_global(use_cache=False)["secure_model"]["model"] == "qwen3:8b"

    def test_no_apple_endpoint_is_a_no_op(self, config_dir):
        from halbert_core.model.auto_provision import reconcile_apple_intelligence
        assert reconcile_apple_intelligence(_hw(bridge_running=False)) == []

    def test_a_dead_bridge_also_clears_a_chat_slot_it_provisioned(self, config_dir):
        # On a 16-24GB Mac provisioning also fills chat_model. A dead bridge
        # would otherwise leave the *chat* model pointing at nothing, which
        # is a worse user experience than an empty slot.
        from halbert_core.model.auto_provision import reconcile_apple_intelligence

        auto_provision_apple_intelligence(_hw(unified_mem_gb=16, bridge_running=True))
        cleared = reconcile_apple_intelligence(_hw(unified_mem_gb=16, bridge_running=False))
        assert set(cleared) == {"secure_model", "chat_model"}
