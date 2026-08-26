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
    for slot in ("orchestrator", "specialist", "vision"):
        assert raw[slot]["model"] == ""
    assert raw["specialist"]["endpoint"] == "http://localhost:11434"
    assert raw["vision"]["endpoint"] == "http://localhost:11434"


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
