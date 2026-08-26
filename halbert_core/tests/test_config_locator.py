"""Tests for halbert_core.model.config_locator (single models.yml locator)."""
from pathlib import Path

import pytest

from halbert_core.model import config_locator
from halbert_core.model.config_locator import (
    ENV_VAR,
    find_models_config,
    models_config_candidates,
    repo_root,
    write_models_config,
)


@pytest.fixture
def dirs(monkeypatch, tmp_path):
    user = tmp_path / "user"
    repo = tmp_path / "repo"
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: user)
    monkeypatch.setattr("halbert_core.model.config_locator.repo_root", lambda: repo)
    monkeypatch.delenv(ENV_VAR, raising=False)
    return user, repo


def _write(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("orchestrator: {model: x}\n")
    return p


def test_env_override_wins(dirs, monkeypatch, tmp_path):
    user, repo = dirs
    _write(user / "models.yml")
    _write(repo / "config" / "models.yml")
    env_file = _write(tmp_path / "x.yml")
    monkeypatch.setenv(ENV_VAR, str(env_file))
    assert find_models_config() == env_file
    assert models_config_candidates()[0] == env_file


def test_env_override_missing_is_skipped(dirs, monkeypatch, tmp_path):
    user, repo = dirs
    _write(user / "models.yml")
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "missing.yml"))
    assert find_models_config() == user / "models.yml"


def test_user_dir_before_repo(dirs):
    user, repo = dirs
    _write(user / "models.yml")
    _write(repo / "config" / "models.yml")
    assert find_models_config() == user / "models.yml"


def test_repo_fallback(dirs):
    user, repo = dirs
    _write(repo / "config" / "models.yml")
    assert find_models_config() == repo / "config" / "models.yml"
    assert find_models_config(include_repo=False) is None


def test_none_when_nothing_exists(dirs):
    user, repo = dirs
    assert find_models_config() is None
    assert models_config_candidates() == [
        user / "models.yml",
        repo / "config" / "models.yml",
        Path("/etc/halbert/models.yml"),
    ]
    assert models_config_candidates(include_repo=False) == [
        user / "models.yml",
        Path("/etc/halbert/models.yml"),
    ]


def test_repo_root_is_checkout():
    root = repo_root()
    assert (root / "halbert_core" / "halbert_core" / "model" / "config_locator.py").is_file()
    assert (root / "config" / "models.yml").is_file()
    assert Path(config_locator.__file__).resolve().is_relative_to(root)


def test_env_override_missing_logs_warning(dirs, monkeypatch, tmp_path, caplog):
    import logging

    user, repo = dirs
    missing = tmp_path / "missing.yml"
    monkeypatch.setenv(ENV_VAR, str(missing))
    with caplog.at_level(logging.WARNING, logger=config_locator.logger.name):
        assert find_models_config() is None
    assert any(
        ENV_VAR in r.getMessage() and str(missing) in r.getMessage()
        and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_write_target_is_user_file_even_when_only_etc_exists(dirs, monkeypatch, tmp_path):
    """System install: only /etc/halbert/models.yml exists and no user file.
    Reads may fall back to /etc, but writes must go to the user file."""
    user, repo = dirs
    etc = _write(tmp_path / "etc" / "halbert" / "models.yml")
    monkeypatch.setattr(
        config_locator, "models_config_candidates",
        lambda include_repo=True: [user / "models.yml", etc],
    )
    assert find_models_config(include_repo=False) == etc
    assert write_models_config() == user / "models.yml"


def test_write_target_honours_env_override(dirs, monkeypatch, tmp_path):
    user, repo = dirs
    env_file = tmp_path / "override.yml"
    monkeypatch.setenv(ENV_VAR, str(env_file))
    assert write_models_config() == env_file


def test_write_target_never_repo(dirs):
    user, repo = dirs
    _write(repo / "config" / "models.yml")
    assert write_models_config() == user / "models.yml"
