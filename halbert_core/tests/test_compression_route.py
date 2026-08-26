# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""/api/compression/config reads and writes the user models.yml via config_locator."""
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes.compression import router
from halbert_core.model.config_locator import ENV_VAR


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "halbert_core.model.config_locator.repo_root", lambda: tmp_path / "norepo"
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), tmp_path


def test_get_config_defaults_when_missing(client):
    c, tmp = client
    r = c.get("/api/compression/config")
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "auto"
    assert body["threshold"] == 4000
    assert not (tmp / "models.yml").exists()


def test_post_creates_user_file(client):
    c, tmp = client
    r = c.post("/api/compression/config", json={"backend": "lingua"})
    assert r.status_code == 200, r.text
    assert r.json()["config"]["backend"] == "lingua"
    cfg = yaml.safe_load((tmp / "models.yml").read_text())
    assert cfg["compression"]["backend"] == "lingua"
    assert c.get("/api/compression/config").json()["backend"] == "lingua"


def test_post_preserves_other_keys(client):
    c, tmp = client
    (tmp / "models.yml").write_text("orchestrator:\n  model: example-model:latest\ncompression:\n  enabled: true\n")
    r = c.post("/api/compression/config", json={"threshold": 1234})
    assert r.status_code == 200, r.text
    cfg = yaml.safe_load((tmp / "models.yml").read_text())
    assert cfg["orchestrator"] == {"model": "example-model:latest"}
    assert cfg["compression"] == {"enabled": True, "threshold": 1234}


def test_post_never_writes_repo_config(monkeypatch, tmp_path):
    """Reviewer repro: with only the repo config present, POST must create the
    user file (seeded from the repo defaults) and leave the repo file untouched."""
    import shutil

    from halbert_core.model.config_locator import repo_root

    repo_copy = tmp_path / "repo"
    (repo_copy / "config").mkdir(parents=True)
    src = repo_root() / "config" / "models.yml"
    shutil.copy(src, repo_copy / "config" / "models.yml")
    before = (repo_copy / "config" / "models.yml").read_bytes()

    user_dir = tmp_path / "user"
    user_dir.mkdir()
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: user_dir)
    monkeypatch.setattr("halbert_core.model.config_locator.repo_root", lambda: repo_copy)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    r = c.post("/api/compression/config", json={"backend": "lingua"})
    assert r.status_code == 200, r.text
    assert (repo_copy / "config" / "models.yml").read_bytes() == before
    cfg = yaml.safe_load((user_dir / "models.yml").read_text())
    assert cfg["compression"]["backend"] == "lingua"
    # seeded from repo defaults, not an empty file
    repo_cfg = yaml.safe_load(before)
    for k in repo_cfg:
        assert k in cfg
    assert c.get("/api/compression/config").json()["backend"] == "lingua"


def test_post_never_writes_etc_when_no_user_file(monkeypatch, tmp_path):
    """System install: only /etc/halbert/models.yml exists. POST must seed from
    it but write the user file, leaving /etc untouched."""
    from halbert_core.model import config_locator

    etc = tmp_path / "etc" / "halbert" / "models.yml"
    etc.parent.mkdir(parents=True)
    etc.write_text("orchestrator:\n  model: sys\ncompression:\n  enabled: true\n")
    before = etc.read_bytes()
    user_dir = tmp_path / "user"

    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: user_dir)
    monkeypatch.setattr(
        config_locator, "models_config_candidates",
        lambda include_repo=True: [user_dir / "models.yml", etc],
    )
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    r = c.post("/api/compression/config", json={"backend": "lingua"})
    assert r.status_code == 200, r.text
    assert etc.read_bytes() == before
    cfg = yaml.safe_load((user_dir / "models.yml").read_text())
    assert cfg["orchestrator"] == {"model": "sys"}
    assert cfg["compression"] == {"enabled": True, "backend": "lingua"}


def test_post_writes_env_override_file(monkeypatch, tmp_path):
    env_file = tmp_path / "override.yml"
    env_file.write_text("compression:\n  enabled: true\n")
    monkeypatch.setenv(ENV_VAR, str(env_file))
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: tmp_path / "user")
    monkeypatch.setattr("halbert_core.model.config_locator.repo_root", lambda: tmp_path / "norepo")
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    r = c.post("/api/compression/config", json={"threshold": 99})
    assert r.status_code == 200, r.text
    cfg = yaml.safe_load(env_file.read_text())
    assert cfg["compression"] == {"enabled": True, "threshold": 99}
    assert not (tmp_path / "user" / "models.yml").exists()
