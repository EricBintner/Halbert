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
    assert set(r.config.models) == {"guide-model", "specialist-model", "vision-model"}
    assert r.config.models["guide-model"].model_id == "qwen2.5:14b-instruct-q4_0"


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


def test_legacy_config_parses_repo_file():
    r = TierRouter(Path(repo_root() / "config" / "models.yml"))
    assert r.config.models["specialist-model"].endpoint == "http://100.74.58.17:11434"
    assert r.config.specialist.fallback == ["guide-model"]
