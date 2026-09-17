# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""POST /api/settings/being carries the presence level and overrides."""

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Nothing under test may touch the developer's real being.yml: the route
    # resolves it through get_config_dir(), which honours HALBERT_CONFIG_DIR
    # (the pattern test_entity_name_write_through.py uses).
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.app import create_app
    return TestClient(create_app())


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
