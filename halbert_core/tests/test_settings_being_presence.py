# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""POST /api/settings/being carries the presence level and overrides."""

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The settings router alone over an isolated config dir.

    Nothing under test may touch the developer's real being.yml: the route
    resolves it through get_config_dir(), which honours HALBERT_CONFIG_DIR
    (test_entity_name_write_through.py's pattern). And the POST's hot-reload
    branch calls get_agent(), which would boot the whole agent and open the
    developer's real ChromaDB; a stub singleton makes that branch a no-op
    (test_agent_interrupt_routes.py's pattern).
    """
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from halbert_core.dashboard.routes import agent as agent_routes
    from halbert_core.dashboard.routes import settings as settings_routes
    monkeypatch.setattr(agent_routes, "_agent_instance", SimpleNamespace(prompt_builder=None))
    app = FastAPI()
    app.include_router(settings_routes.router, prefix="/api/settings")
    return TestClient(app)


def test_presence_round_trips(client):
    r = client.post("/api/settings/being", json={"presence": 6, "presence_overrides": {"warning": 2}})
    assert r.status_code == 200, r.text
    cfg = client.get("/api/settings/being").json()["config"]
    assert cfg["presence"] == 6 and cfg["presence_overrides"] == {"warning": 2}


def test_out_of_range_presence_is_rejected(client):
    r = client.post("/api/settings/being", json={"presence": 11})
    assert r.status_code == 400
    r = client.post("/api/settings/being", json={"presence_overrides": {"critical": 0}})
    assert r.status_code == 400


def test_the_old_dial_field_still_saves_in_slice_one(client):
    assert client.post("/api/settings/being", json={"proactivity": "quiet"}).status_code == 200
    assert client.get("/api/settings/being").json()["config"]["proactivity"] == "quiet"


@pytest.mark.parametrize("bad", [True, "6", 6.5])
def test_a_wrong_type_is_refused_before_it_can_be_laundered(client, bad):
    # Pydantic's lax int would read true as 1; StrictInt makes a wrong type a 422
    # and leaves the range check to validate()'s 400.
    assert client.post("/api/settings/being", json={"presence": bad}).status_code == 422
    assert client.get("/api/settings/being").json()["config"]["presence"] == 3
