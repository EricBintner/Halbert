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

    def test_wrong_phrase_403_does_not_echo_the_phrase(self, client):
        """REV-01 F2: the 403 must not teach the challenge's answer.

        The phrase is rendered in the modal for the human — that is its
        purpose. Repeating it in the error body hands an agent driving
        the API the answer to its own challenge.
        """
        for phrase in (None, "let me in", "EXPOSE"):
            resp = client.post("/api/settings/being",
                               json=_unlock_body(phrase=phrase))
            assert resp.status_code == 403
            assert "EXPOSE SECRETS" not in resp.json()["detail"]
            assert resp.json()["detail"]  # still says why, generically

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
        """Bounding an already-unlocked tier with a timestamp is not an
        extension — the unlock itself was the gated act (see the
        extension tests above for the gated direction)."""
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


class TestExposureIncreaseGating:
    """REV-01 F2: the phrase gates every exposure-INCREASING change.

    The fresh ``local_only → cloud_ok_acknowledged`` transition is only
    one of the ways egress can widen. Hatch additions and expiry
    extensions expose the same values an unlock does — they must clear
    the same bar. Locking down stays frictionless.
    """

    def _unlock(self, client, **extra):
        body = _unlock_body(phrase="EXPOSE SECRETS")
        body["security"].update(extra)
        resp = client.post("/api/settings/being", json=body)
        assert resp.status_code == 200

    # -- hatch additions (cloud_ok_keys) --

    def test_hatch_addition_requires_phrase(self, client):
        resp = client.post("/api/settings/being",
                           json={"security": {"cloud_ok_keys": ["serial"]}})
        assert resp.status_code == 403
        assert "EXPOSE SECRETS" not in resp.json()["detail"]

    def test_hatch_addition_with_phrase_accepted(self, client):
        resp = client.post(
            "/api/settings/being",
            json={"security": {"cloud_ok_keys": ["serial"],
                               "phrase": "EXPOSE SECRETS"}})
        assert resp.status_code == 200
        assert resp.json()["config"]["security"]["cloud_ok_keys"] == ["serial"]

    def test_hatch_addition_to_existing_hatch_requires_phrase(self, client):
        self._unlock(client, cloud_ok_keys=["serial"])
        resp = client.post(
            "/api/settings/being",
            json={"security": {"cloud_ok_keys": ["serial", "location"]}})
        assert resp.status_code == 403

    def test_hatch_removal_needs_no_phrase(self, client):
        """Locking down: dropping keys from the hatch stays frictionless."""
        self._unlock(client, cloud_ok_keys=["serial", "location"])
        resp = client.post(
            "/api/settings/being",
            json={"security": {"cloud_ok_keys": ["serial"]}})
        assert resp.status_code == 200

    def test_unchanged_hatch_needs_no_phrase(self, client):
        """A save riding the identical hatch list is not a hatch change."""
        self._unlock(client, cloud_ok_keys=["serial"])
        resp = client.post(
            "/api/settings/being",
            json={"security": {"cloud_ok_keys": ["serial"],
                               "public_files": ["/etc/hosts"]}})
        assert resp.status_code == 200

    # -- expiry extension while unlocked --

    def test_expiry_extension_requires_phrase(self, client):
        expiry = "2030-01-01T00:00:00+00:00"
        self._unlock(client, secret_tier_expiry="2027-01-01T00:00:00+00:00")
        resp = client.post("/api/settings/being", json=_unlock_body(
            secret_tier_expiry=expiry))
        assert resp.status_code == 403
        assert "EXPOSE SECRETS" not in resp.json()["detail"]

    def test_expiry_extension_with_phrase_accepted(self, client):
        self._unlock(client, secret_tier_expiry="2027-01-01T00:00:00+00:00")
        body = _unlock_body(phrase="EXPOSE SECRETS",
                            secret_tier_expiry="2030-01-01T00:00:00+00:00")
        resp = client.post("/api/settings/being", json=body)
        assert resp.status_code == 200
        assert resp.json()["config"]["security"]["secret_tier_expiry"] == \
            "2030-01-01T00:00:00+00:00"

    def test_making_unlock_permanent_requires_phrase(self, client):
        """expiry=None while unlocked means permanent — an extension."""
        self._unlock(client, secret_tier_expiry="2027-01-01T00:00:00+00:00")
        resp = client.post("/api/settings/being", json=_unlock_body(
            secret_tier_expiry=None))
        assert resp.status_code == 403

    def test_expiry_shortening_needs_no_phrase(self, client):
        """Locking down: a nearer expiry stays frictionless."""
        self._unlock(client, secret_tier_expiry="2030-01-01T00:00:00+00:00")
        resp = client.post("/api/settings/being", json=_unlock_body(
            secret_tier_expiry="2027-01-01T00:00:00+00:00"))
        assert resp.status_code == 200

    def test_bounding_a_permanent_unlock_needs_no_phrase(self, client):
        """expiry None → a timestamp is a shortening, not an extension."""
        self._unlock(client)  # permanent (no expiry)
        resp = client.post("/api/settings/being", json=_unlock_body(
            secret_tier_expiry="2027-01-01T00:00:00+00:00"))
        assert resp.status_code == 200


class TestPhraseSingleSource:
    def test_phrase_lives_in_shared_config_module(self):
        """REV-01 F2: one definition point, imported by the dashboard route.

        The MCP path and the dashboard route must never drift apart.
        """
        from halbert_core.config.security_constants import UNLOCK_PHRASE
        from halbert_core.dashboard.routes import settings as settings_routes
        assert settings_routes.UNLOCK_PHRASE is UNLOCK_PHRASE
        assert UNLOCK_PHRASE == "EXPOSE SECRETS"
