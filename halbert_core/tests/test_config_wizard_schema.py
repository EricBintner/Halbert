# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The CLI wizard writes the llm_config schema, never the legacy keys."""
from unittest.mock import MagicMock, patch

import pytest

from halbert_core.model import llm_config as store
from halbert_core.model.config_wizard import ConfigWizard

OLLAMA = "http://localhost:11434"


def _wizard():
    return ConfigWizard.__new__(ConfigWizard)   # skip hardware detection in __init__


def _hardware():
    # Explicit numeric/bool attrs: _build_config does arithmetic on
    # unified_memory_gb (`mem <= 24`), which a bare MagicMock fails with
    # TypeError. Apple Intelligence off keeps these tests about the schema,
    # not the AI branch.
    return MagicMock(profile=MagicMock(value="apple_silicon"), total_ram_gb=32,
                     platform="darwin", is_apple_silicon=True,
                     unified_memory_gb=32, apple_intelligence_available=False,
                     apple_intelligence_bridge_running=False)


def _budget():
    budget = MagicMock()
    budget.to_dict.return_value = {"max_params_b_4bit": 14}
    return budget


def test_build_config_uses_llm_config_schema():
    cfg = _wizard()._build_config("chat-a", "ollama", _budget(), _hardware(), endpoint="http://localhost:11434")
    assert "orchestrator" not in cfg and "specialist" not in cfg
    llm = store.normalise(cfg["llm_config"])
    assert llm["chat_model"] == {"enabled": True, "endpoint_id": "ep_local_ollama", "model": "chat-a"}
    assert llm["saved_endpoints"] == [{"id": "ep_local_ollama", "name": "Local Ollama", "provider": "ollama",
                                       "url": "http://localhost:11434", "api_key": ""}]
    assert cfg["routing"]["strategy"] == "auto"


def test_build_config_without_model_leaves_chat_unset():
    cfg = _wizard()._build_config(None, "ollama", _budget(), _hardware())
    assert store.normalise(cfg["llm_config"])["chat_model"]["enabled"] is False


# ── U6 S1/W2: the wizard's secure_model write is sysadmin-only ──────────


def _ai_hardware():
    """Apple-Intelligence-eligible host (32GB Mac: AI takes secure, not chat)."""
    return MagicMock(profile=MagicMock(value="apple_silicon"), total_ram_gb=32,
                     platform="darwin", is_apple_silicon=True,
                     unified_memory_gb=32, apple_intelligence_available=True,
                     apple_intelligence_bridge_running=True)


def _ai_budget():
    budget = MagicMock()
    budget.to_dict.return_value = {"max_params_b_4bit": 14}
    return budget


@pytest.mark.parametrize("variant", ["home"])
def test_build_config_home_variants_write_empty_secure_slot(variant):
    """home carry no secure_model — and the slot must be written
    EMPTY, not omitted, because save_config deep-merges all slots."""
    with patch("halbert_core.model.config_wizard._is_home_variant",
               return_value=True), \
         patch("halbert_core.model.auto_provision._is_home_variant",
               return_value=True):
        cfg = _wizard()._build_config(None, "ollama", _ai_budget(), _ai_hardware())
    secure = cfg["llm_config"]["secure_model"]
    assert secure == {"enabled": False, "endpoint_id": "", "model": ""}
    # The apple-foundation endpoint still registers — chat/specialist may
    # use it until the compute-peer setting lands (U6 S3).
    eps = [e for e in cfg["llm_config"]["saved_endpoints"]
           if e["provider"] == "apple-foundation"]
    assert len(eps) == 1


def test_build_config_sysadmin_writes_ai_secure_slot():
    with patch("halbert_core.model.config_wizard._is_home_variant",
               return_value=False), \
         patch("halbert_core.model.auto_provision._is_home_variant",
               return_value=False):
        cfg = _wizard()._build_config(None, "ollama", _ai_budget(), _ai_hardware())
    secure = cfg["llm_config"]["secure_model"]
    assert secure["enabled"] is True
    assert secure["model"] == store.APPLE_FOUNDATION_MODEL
    assert secure["endpoint_id"] == "ep_apple_foundation"


def test_validate_config_requires_llm_config(tmp_path):
    p = tmp_path / "models.yml"
    p.write_text("orchestrator: {model: x}\nrouting: {}\nhandoff: {}\n")
    assert _wizard().validate_config(p) is False
    p.write_text(
        "llm_config:\n"
        "  chat_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "  specialist_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "  vision_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "  secure_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "routing: {}\nhandoff: {}\n"
    )
    assert _wizard().validate_config(p) is True


# ── The wizard persists through the store, never over it ──


def test_save_config_round_trips_through_the_store(models_config_dir):
    wizard = _wizard()
    cfg = wizard._build_config("model-a", "ollama", _budget(), _hardware(), endpoint=OLLAMA)
    assert wizard.save_config(cfg) == models_config_dir / "models.yml"

    llm = store.load()
    ep_id = llm["chat_model"]["endpoint_id"]
    assert llm["chat_model"] == {"enabled": True, "endpoint_id": ep_id, "model": "model-a"}
    assert ep_id != "ep_local_ollama"          # the store mints the id, not the wizard
    assert [(e["id"], e["url"]) for e in llm["saved_endpoints"]] == [(ep_id, OLLAMA)]
    assert store.load_file()["routing"]["strategy"] == "auto"


def test_save_config_keeps_the_keys_the_wizard_does_not_build(models_config_dir):
    """Dumping the file in place deleted every sibling key, saved API keys included."""
    store.save({"saved_endpoints": [{"id": "cloud", "name": "Cloud", "provider": "openai",
                                     "url": "https://api.example.com/v1", "api_key": "sk-x"}]})
    store.set_top_level("compression", {"backend": "semantic", "enabled": True})

    wizard = _wizard()
    wizard.save_config(wizard._build_config("model-a", "ollama", _budget(), _hardware(), endpoint=OLLAMA))

    on_disk = store.load_file()
    assert on_disk["compression"] == {"backend": "semantic", "enabled": True}
    cloud = next(e for e in on_disk["llm_config"]["saved_endpoints"] if e["id"] == "cloud")
    assert cloud["api_key"] == "sk-x"


def test_save_config_writes_a_private_file(models_config_dir):
    import os
    wizard = _wizard()
    wizard.save_config(wizard._build_config("model-a", "ollama", _budget(), _hardware(), endpoint=OLLAMA))
    assert os.stat(models_config_dir / "models.yml").st_mode & 0o777 == 0o600


def test_save_config_without_a_model_leaves_the_slot_unset(models_config_dir):
    wizard = _wizard()
    wizard.save_config(wizard._build_config(None, "ollama", _budget(), _hardware(), endpoint=OLLAMA))
    llm = store.load()
    assert llm["chat_model"] == {"enabled": False, "endpoint_id": "", "model": ""}
    assert llm["saved_endpoints"] == []


def test_save_config_of_nothing_writes_nothing(models_config_dir):
    assert _wizard().save_config({}) is None
    assert not (models_config_dir / "models.yml").exists()


def test_validate_config_with_no_path_reads_the_store_file(models_config_dir):
    assert _wizard().validate_config() is False        # nothing written yet
    wizard = _wizard()
    wizard.save_config(wizard._build_config("model-a", "ollama", _budget(), _hardware(), endpoint=OLLAMA))
    assert wizard.validate_config() is True
