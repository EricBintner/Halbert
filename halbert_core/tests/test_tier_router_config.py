# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""TierRouter config discovery via config_locator."""
from pathlib import Path

import pytest

from halbert_core.model.config_locator import ENV_VAR, repo_root
from halbert_core.model.tier_router import TierRouter


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


def test_find_config_uses_repo_when_no_user_config(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "halbert_core.model.config_locator.get_config_dir", lambda: tmp_path / "empty"
    )
    r = TierRouter()
    assert r.config_path == repo_root() / "config" / "models.yml"
    # The repo file is a neutral template: every model slot is empty, and the
    # legacy parser skips slots whose model is empty, so nothing is registered
    # until the user picks a model in Settings.
    assert r.config.models == {}


def test_find_config_prefers_user_config(monkeypatch, tmp_path):
    u = tmp_path / "u"
    u.mkdir()
    (u / "models.yml").write_text("orchestrator: {model: test-model}\n")
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: u)
    r = TierRouter()
    assert r.config_path == u / "models.yml"
    assert r.config.models["guide-model"].model_id == "test-model"


def test_find_config_none(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "halbert_core.model.config_locator.get_config_dir", lambda: tmp_path / "none"
    )
    monkeypatch.setattr(
        "halbert_core.model.config_locator.repo_root", lambda: tmp_path / "norepo"
    )
    r = TierRouter()
    assert r.config.models == {}
    assert r.config_path == tmp_path / "none" / "models.yml"


def test_repo_template_has_empty_model_slots():
    """The checked-in config/models.yml must not ship model ids or private endpoints."""
    import yaml

    raw = yaml.safe_load((repo_root() / "config" / "models.yml").read_text())
    llm = raw["llm_config"]
    for slot in ("chat_model", "specialist_model", "vision_model", "secure_model"):
        assert llm[slot]["model"] == ""
        assert llm[slot]["enabled"] is False
    for ep in llm["saved_endpoints"]:
        assert ep["url"] == "http://localhost:11434"
        assert ep["api_key"] == ""


def test_legacy_config_skips_empty_model_slots(tmp_path):
    p = tmp_path / "models.yml"
    p.write_text(
        "orchestrator: {model: ''}\n"
        "specialist: {enabled: true, model: ''}\n"
        "vision: {model: ''}\n"
    )
    r = TierRouter(p)
    assert r.config.models == {}


def test_legacy_config_parses_populated_slots(tmp_path):
    p = tmp_path / "models.yml"
    p.write_text(
        "orchestrator: {model: 'example-guide:8b', provider: ollama}\n"
        "specialist: {enabled: true, model: 'example-specialist:70b', endpoint: 'http://localhost:11435'}\n"
        "vision: {model: 'example-vision:8b', endpoint: 'http://localhost:11435'}\n"
    )
    r = TierRouter(Path(p))
    assert set(r.config.models) == {"guide-model", "specialist-model", "vision-model"}
    assert r.config.models["guide-model"].model_id == "example-guide:8b"
    assert r.config.models["specialist-model"].endpoint == "http://localhost:11435"
    assert r.config.specialist.fallback == ["guide-model"]


class _SlotReadSpy(dict):
    """dict that records which keys were read through .get()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_keys = set()

    def get(self, key, default=None):
        self.read_keys.add(key)
        return super().get(key, default)


def _llm_config_spy():
    return _SlotReadSpy({
        "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "guide-a"},
        "specialist_model": {"enabled": False, "endpoint_id": "", "model": ""},
        "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
        "secure_model": {"enabled": True, "endpoint_id": "e1", "model": "secure-a"},
        "saved_endpoints": [
            {"id": "e1", "provider": "ollama", "url": "http://localhost:11434"},
        ],
    })


@pytest.mark.parametrize("ha", ["home"])
def test_home_variant_does_not_read_the_secure_slot(monkeypatch, ha):
    """home never configure secure_model, so from_legacy_config
    does not read the slot for them — even a stale value left behind by a
    sysadmin-style config cannot reach the router."""
    from halbert_core.integrations import cognition_wiring
    from halbert_core.model import tier_router

    monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: ha)
    spy = _llm_config_spy()
    cfg = tier_router.TierRouterConfig.from_legacy_config({"llm_config": spy})
    assert "secure_model" not in spy.read_keys
    assert cfg.models["guide-model"].model_id == "guide-a"


def test_sysadmin_variant_reads_the_secure_slot(monkeypatch):
    from halbert_core.integrations import cognition_wiring
    from halbert_core.model import tier_router

    monkeypatch.setattr(cognition_wiring, "_get_variant", lambda: "sysadmin")
    spy = _llm_config_spy()
    tier_router.TierRouterConfig.from_legacy_config({"llm_config": spy})
    assert "secure_model" in spy.read_keys
