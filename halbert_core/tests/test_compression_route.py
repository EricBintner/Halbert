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
    """PICK-02: going through the store (llm_config.load_file/set_top_level)
    means a legacy key like ``orchestrator`` is migrated into ``llm_config``
    the same way every other write path already migrates it, rather than
    being copied through verbatim by a bare yaml.safe_dump."""
    c, tmp = client
    (tmp / "models.yml").write_text("orchestrator:\n  model: example-model:latest\ncompression:\n  enabled: true\n")
    r = c.post("/api/compression/config", json={"threshold": 1234})
    assert r.status_code == 200, r.text
    cfg = yaml.safe_load((tmp / "models.yml").read_text())
    assert "orchestrator" not in cfg
    assert cfg["llm_config"]["chat_model"]["model"] == "example-model:latest"
    assert cfg["compression"] == {"enabled": True, "threshold": 1234}


def test_post_never_writes_repo_config(monkeypatch, tmp_path):
    """PICK-02: with only the repo config present, POST must create the user
    file and leave the repo file untouched — and, unlike the old
    yaml.safe_dump-the-whole-dict implementation, must NOT copy the repo
    template's other sections (routing, handoff, its placeholder
    llm_config) into the user's file. The store's own read path
    (find_models_config(include_repo=False)) never considers the
    git-tracked repo file a config source at all — the picker's GET
    /llm/config has never seeded from it either, so this endpoint is now
    consistent with the rest of the system rather than a second, buggier
    seeding path."""
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
    # NOT seeded from the repo template: no routing/handoff sections, and
    # the user file's own llm_config stays the normalised empty scaffold.
    assert "routing" not in cfg
    assert "handoff" not in cfg
    assert cfg["llm_config"]["chat_model"]["model"] == ""
    assert cfg["llm_config"]["saved_endpoints"] == []
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
    # /etc/halbert/models.yml is a real system layer (unlike the repo
    # template) and still seeds the user file; its legacy orchestrator
    # key is migrated into llm_config like any other write path does.
    assert "orchestrator" not in cfg
    assert cfg["llm_config"]["chat_model"]["model"] == "sys"
    assert cfg["compression"] == {"enabled": True, "backend": "lingua"}


def test_post_writes_0600_and_atomically(client):
    """PICK-02: the old implementation wrote with a bare open()+yaml.safe_dump
    (no atomic rename, no 0600). Going through set_top_level gets both for
    free — this pins that the file this route creates actually has them."""
    import os
    import stat

    c, tmp = client
    r = c.post("/api/compression/config", json={"backend": "lingua"})
    assert r.status_code == 200, r.text
    path = tmp / "models.yml"
    assert path.exists()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_post_strips_a_stray_default_routing_block_once(client):
    """PICK-02: a routing: block byte-identical to the repo template is a
    remnant of the old bug (which copied the whole repo dict, routing
    included, into the user file) and is removed as a one-shot repair."""
    c, tmp = client
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "models.yml").write_text(
        "routing:\n"
        "  strategy: auto\n"
        "  prefer_specialist_for: [code_generation, code_analysis, reasoning, system_command]\n"
        "  complexity_threshold: 0.5\n"
        "compression:\n"
        "  enabled: true\n"
    )
    r = c.post("/api/compression/config", json={"backend": "lingua"})
    assert r.status_code == 200, r.text
    cfg = yaml.safe_load((tmp / "models.yml").read_text())
    assert "routing" not in cfg
    assert cfg["compression"]["backend"] == "lingua"


def test_post_keeps_a_customised_routing_block(client):
    """A routing: block that does NOT match the template default is a real
    customisation, not a copy artifact, and must survive untouched."""
    c, tmp = client
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "models.yml").write_text(
        "routing:\n"
        "  strategy: auto\n"
        "  prefer_specialist_for: [code_generation, code_analysis, reasoning, system_command]\n"
        "  complexity_threshold: 0.9\n"
        "compression:\n"
        "  enabled: true\n"
    )
    r = c.post("/api/compression/config", json={"backend": "lingua"})
    assert r.status_code == 200, r.text
    cfg = yaml.safe_load((tmp / "models.yml").read_text())
    assert cfg["routing"]["complexity_threshold"] == 0.9


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
