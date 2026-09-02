# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The two name fields can never diverge.

preferences.yml ``ai_name`` is the source (onboarding writes it); being.yml
``name`` is its mirror (the Being tab edits it). Every writer of one keeps
the other in step, so the greeting (reads preferences), the prompt builder
(reads being.yml) and the Presence Pill (the resolver) agree (W1-01, C1-02).
"""
from __future__ import annotations

import os
import sys

import pytest
import yaml

pytest.importorskip("fastapi")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core import identity


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Settings router over an isolated config dir."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("HALBERT_DISPLAY_NAME", raising=False)
    from halbert_core.dashboard.routes import settings as settings_routes

    app = FastAPI()
    app.include_router(settings_routes.router, prefix="/api/settings")
    return TestClient(app), tmp_path


def _prefs(tmp_path):
    path = tmp_path / "preferences.yml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def _being(tmp_path):
    path = tmp_path / "being.yml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


class TestBeingTabWritesThrough:

    def test_being_name_write_updates_ai_name(self, client):
        c, tmp = client
        (tmp / "preferences.yml").write_text("ai_name: Old\nuser_name: Eric\n")
        resp = c.post("/api/settings/being", json={"name": "Macky-Mac"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["config"]["name"] == "Macky-Mac"
        assert _being(tmp)["name"] == "Macky-Mac"
        assert _prefs(tmp)["ai_name"] == "Macky-Mac"
        assert _prefs(tmp)["user_name"] == "Eric"
        assert identity.resolve_entity_name("box") == "Macky-Mac"

    def test_a_being_post_without_a_name_leaves_ai_name_alone(self, client):
        c, tmp = client
        (tmp / "preferences.yml").write_text("ai_name: Macky-Mac\n")
        resp = c.post("/api/settings/being", json={"proactivity": "quiet"})
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["ai_name"] == "Macky-Mac"


class TestOnboardingWritersMirrorToBeing:

    def test_computer_name_mirrors_into_being(self, client):
        c, tmp = client
        (tmp / "being.yml").write_text("voice: hybrid\nbody_name: desk\n")
        resp = c.post("/api/settings/computer-name", json={"ai_name": "Macky-Mac"})
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["ai_name"] == "Macky-Mac"
        being = _being(tmp)
        assert being["name"] == "Macky-Mac"
        assert being["voice"] == "hybrid"
        assert being["body_name"] == "desk"

    def test_onboarding_complete_mirrors_into_being(self, client, monkeypatch):
        c, tmp = client

        class _Profiler:
            def scan_all(self):
                return {}

            def save_profile(self):
                pass

            def get_summary(self):
                return "summary"

        monkeypatch.setattr(
            "halbert_core.discovery.scanners.system_profile.get_system_profiler",
            lambda: _Profiler())
        resp = c.post("/api/settings/onboarding/complete",
                      json={"computer_name": "Macky-Mac", "admin_name": "Eric"})
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["ai_name"] == "Macky-Mac"
        assert _being(tmp)["name"] == "Macky-Mac"
        assert identity.resolve_entity_name("box") == "Macky-Mac"
