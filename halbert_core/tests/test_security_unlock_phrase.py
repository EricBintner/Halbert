# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Server-side enforcement of the Tier 2 escape-hatch phrase.

The Security tab modal checks the phrase in the browser, but that is UX
friction — the boundary must hold against a bare HTTP client. These tests
drive POST /api/settings/being directly.
"""
from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("fastapi")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Settings router over an isolated config dir."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from halbert_core.dashboard.routes import settings as settings_routes

    app = FastAPI()
    app.include_router(settings_routes.router, prefix="/api/settings")
    return TestClient(app)


def _unlock_body(**extra):
    security = {"secret_tier": "cloud_ok_acknowledged"}
    security.update(extra)
    return {"security": security}


class TestUnlockPhraseEnforcement:
    def test_unlock_without_phrase_rejected(self, client):
        resp = client.post("/api/settings/being", json=_unlock_body())
        assert resp.status_code == 403
        assert "EXPOSE SECRETS" in resp.json()["detail"]

    def test_unlock_with_wrong_phrase_rejected(self, client):
        resp = client.post(
            "/api/settings/being", json=_unlock_body(phrase="let me in"))
        assert resp.status_code == 403

    def test_unlock_with_phrase_accepted(self, client):
        resp = client.post(
            "/api/settings/being", json=_unlock_body(phrase="EXPOSE SECRETS"))
        assert resp.status_code == 200
        assert resp.json()["config"]["security"]["secret_tier"] == \
            "cloud_ok_acknowledged"

    def test_phrase_is_whitespace_and_case_normalised(self, client):
        resp = client.post(
            "/api/settings/being",
            json=_unlock_body(phrase="  expose   secrets  "))
        assert resp.status_code == 200

    def test_relock_needs_no_phrase(self, client):
        # Unlock first (with phrase)
        resp = client.post(
            "/api/settings/being", json=_unlock_body(phrase="EXPOSE SECRETS"))
        assert resp.status_code == 200
        # Relock without phrase
        resp = client.post("/api/settings/being",
                           json={"security": {"secret_tier": "local_only"}})
        assert resp.status_code == 200
        assert resp.json()["config"]["security"]["secret_tier"] == "local_only"

    def test_ttl_change_while_unlocked_needs_no_new_phrase(self, client):
        """Adjusting the expiry of an already-unlocked tier is not a new
        transition — the unlock itself was the gated act."""
        resp = client.post(
            "/api/settings/being", json=_unlock_body(phrase="EXPOSE SECRETS"))
        assert resp.status_code == 200
        resp = client.post("/api/settings/being", json=_unlock_body(
            secret_tier_expiry="2099-01-01T00:00:00+00:00"))
        assert resp.status_code == 200

    def test_phrase_is_not_persisted(self, client, tmp_path):
        """The phrase is enforcement metadata — it must not land in being.yml."""
        client.post("/api/settings/being",
                    json=_unlock_body(phrase="EXPOSE SECRETS"))
        being_yml = tmp_path / "being.yml"
        assert being_yml.exists()
        assert "phrase" not in being_yml.read_text().lower()

    def test_unlock_survives_next_load_in_same_process(self, client):
        """Regression (volatile guard): a 1h unlock must still be in effect
        on the very next read — load_being_config runs per request."""
        import datetime
        expiry = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(hours=1)).isoformat()
        resp = client.post("/api/settings/being", json=_unlock_body(
            phrase="EXPOSE SECRETS", secret_tier_expiry=expiry))
        assert resp.status_code == 200
        resp = client.get("/api/settings/being")
        assert resp.status_code == 200
        assert resp.json()["config"]["security"]["secret_tier"] == \
            "cloud_ok_acknowledged"
