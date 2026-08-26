# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The CLI wizard writes the llm_config schema, never the legacy keys."""
from unittest.mock import MagicMock

from halbert_core.model import llm_config as store
from halbert_core.model.config_wizard import ConfigWizard


def _wizard():
    return ConfigWizard.__new__(ConfigWizard)   # skip hardware detection in __init__


def _hardware():
    return MagicMock(profile=MagicMock(value="apple_silicon"), total_ram_gb=32,
                     platform="darwin", is_apple_silicon=True)


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


def test_validate_config_requires_llm_config(tmp_path):
    p = tmp_path / "models.yml"
    p.write_text("orchestrator: {model: x}\nrouting: {}\nhandoff: {}\n")
    assert _wizard().validate_config(p) is False
    p.write_text(
        "llm_config:\n"
        "  chat_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "  specialist_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "  vision_model: {enabled: false, endpoint_id: '', model: ''}\n"
        "routing: {}\nhandoff: {}\n"
    )
    assert _wizard().validate_config(p) is True
