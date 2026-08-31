# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The config wizard never fills secure_model on home automation variants.

secure_model is a sysadmin-instance slot (handoff
HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, S1): an HA variant's LLM reaches
the house through tool calls that abstract credentials away, so there is no
sensitive-data reasoning to route to a dedicated local model. These pin the
wizard — one of the three writers that could fill the slot on an
Apple-Intelligence-eligible Mac — to sysadmin instances only:

- ``run_auto`` does not call the auto-provisioning for home/home-light
- ``_build_config`` writes the slot empty (save_config deep-merges every
  slot, so omitting it would keep a stale assignment)
- ``save_config`` clears a stale secure assignment on a home-variant rerun
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from halbert_core.model import llm_config as store
from halbert_core.model.config_wizard import ConfigWizard

OLLAMA = "http://localhost:11434"


def _wizard():
    return ConfigWizard.__new__(ConfigWizard)   # skip hardware detection in __init__


def _hardware_ai(mem_gb=16):
    """An Apple-Intelligence-eligible Mac with concrete attribute values."""
    return SimpleNamespace(
        profile=SimpleNamespace(value="apple_silicon"),
        total_ram_gb=32,
        platform="darwin",
        is_apple_silicon=True,
        apple_intelligence_available=True,
        unified_memory_gb=mem_gb,
    )


def _budget():
    budget = MagicMock()
    budget.to_dict.return_value = {"max_params_b_4bit": 14}
    return budget


@pytest.fixture
def variant(monkeypatch):
    """Controllable variant behind every consumer's resolution chain.

    Patched at cognition_wiring._get_variant — the single source backend
    gating uses (being.yml > HALBERT_VARIANT env > 'sysadmin') — so the
    wizard's lazy lookup is exercised for real.
    """
    from halbert_core.integrations import cognition_wiring
    holder = {"variant": "sysadmin"}
    monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: holder["variant"])
    return holder


# ── _build_config ──────────────────────────────────────────────────────


def test_build_config_writes_secure_model_for_sysadmin(variant):
    cfg = _wizard()._build_config("chat-a", "ollama", _budget(), _hardware_ai(),
                                  endpoint=OLLAMA)
    assert cfg["llm_config"]["secure_model"] == {
        "enabled": True,
        "endpoint_id": "ep_apple_foundation",
        "model": store.APPLE_FOUNDATION_MODEL,
    }


@pytest.mark.parametrize("ha", ["home", "home-light"])
def test_build_config_writes_secure_model_empty_for_home_variants(variant, ha):
    """The slot is written empty, not omitted — save_config deep-merges
    every slot, so an omission would keep whatever was there before."""
    variant["variant"] = ha
    cfg = _wizard()._build_config("chat-a", "ollama", _budget(), _hardware_ai(),
                                  endpoint=OLLAMA)
    assert cfg["llm_config"]["secure_model"] == {"enabled": False, "endpoint_id": "", "model": ""}


@pytest.mark.parametrize("ha", ["home", "home-light"])
def test_home_variant_keeps_the_chat_model_rule(variant, ha):
    """Only secure_model is variant-gated: on a 16-24GB Mac the single
    local model rule still assigns chat_model (the Mac's own on-device use)."""
    variant["variant"] = ha
    cfg = _wizard()._build_config(None, "ollama", _budget(), _hardware_ai(mem_gb=16),
                                  endpoint=OLLAMA)
    chat = cfg["llm_config"]["chat_model"]
    assert chat["model"] == store.APPLE_FOUNDATION_MODEL
    assert chat["enabled"] is True


# ── run_auto ───────────────────────────────────────────────────────────


def _run_auto_wizard(monkeypatch):
    """A wizard whose hardware probe and budget are stubbed out."""
    wizard = _wizard()
    monkeypatch.setattr(wizard, "detect_hardware", lambda: _hardware_ai())
    monkeypatch.setattr(wizard, "get_budget", lambda hw: _budget())
    provisioned = MagicMock()
    monkeypatch.setattr(
        "halbert_core.model.config_wizard.auto_provision_apple_intelligence",
        provisioned,
    )
    return wizard, provisioned


@pytest.mark.parametrize("ha", ["home", "home-light"])
def test_run_auto_skips_apple_provisioning_for_home_variants(variant, monkeypatch, ha):
    variant["variant"] = ha
    wizard, provisioned = _run_auto_wizard(monkeypatch)
    wizard.run_auto(model="chat-a", endpoint=OLLAMA)
    provisioned.assert_not_called()


def test_run_auto_provisions_for_sysadmin(variant, monkeypatch):
    wizard, provisioned = _run_auto_wizard(monkeypatch)
    wizard.run_auto(model="chat-a", endpoint=OLLAMA)
    provisioned.assert_called_once()


# ── save_config ─────────────────────────────────────────────────────────


def test_save_config_clears_a_stale_secure_slot_for_home_variant(variant, models_config_dir):
    """The deep-merge means the empty write must actually disable the slot:
    a secure assignment left by an earlier sysadmin-style run must not
    survive a home-variant rerun of the wizard."""
    variant["variant"] = "sysadmin"
    ep_id = store.ensure_endpoint(OLLAMA, "ollama", "Local Ollama")
    store.set_slot("secure_model", "stale-secure", ep_id)
    assert store.load()["secure_model"]["enabled"] is True

    variant["variant"] = "home"
    wizard = _wizard()
    wizard.save_config(wizard._build_config("chat-a", "ollama", _budget(), _hardware_ai(),
                                            endpoint=OLLAMA))

    assert store.load()["secure_model"] == {"enabled": False, "endpoint_id": "", "model": ""}


def test_save_config_keeps_secure_model_for_sysadmin(variant, models_config_dir):
    variant["variant"] = "sysadmin"
    wizard = _wizard()
    wizard.save_config(wizard._build_config("chat-a", "ollama", _budget(), _hardware_ai(),
                                            endpoint=OLLAMA))

    secure = store.load()["secure_model"]
    assert secure["model"] == store.APPLE_FOUNDATION_MODEL
    assert secure["enabled"] is True