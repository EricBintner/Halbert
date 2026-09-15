# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Onboarding machine roles — probe, completion, and the Being-tab write
path.

The roles replace the dead ``user_type`` single-select: they are stored in
preferences.yml and the system profile, read by the prompt builder and the
nav feature flags, and editable after onboarding through
/api/settings/machine-roles.
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


class _Profiler:
    def scan_all(self):
        return {}

    def save_profile(self):
        pass

    def get_summary(self):
        return "summary"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Settings router over an isolated config dir, scan stubbed out."""
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("HALBERT_DISPLAY_NAME", raising=False)
    monkeypatch.setattr(
        "halbert_core.discovery.scanners.system_profile.get_system_profiler",
        lambda: _Profiler())
    from halbert_core.dashboard.routes import settings as settings_routes

    app = FastAPI()
    app.include_router(settings_routes.router, prefix="/api/settings")
    return TestClient(app), tmp_path


def _prefs(tmp_path):
    path = tmp_path / "preferences.yml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


class TestOnboardingComplete:
    def test_roles_are_stored_and_returned(self, client):
        c, tmp = client
        resp = c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "admin_name": "Eric",
            "roles": ["workstation", "home_automation_hub"],
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["roles"] == ["workstation", "home_automation_hub"]
        assert _prefs(tmp)["roles"] == ["workstation", "home_automation_hub"]

    def test_no_roles_defaults_to_workstation(self, client):
        c, tmp = client
        resp = c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
        })
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["roles"] == ["workstation"]

    def test_invalid_roles_are_filtered_and_fall_back(self, client):
        c, tmp = client
        resp = c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "roles": ["it_admin", "server"],  # it_admin is not a role
        })
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["roles"] == ["server"]

        resp = c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "roles": ["it_admin", "casual"],
        })
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["roles"] == ["workstation"]

    def test_marker_file_carries_no_roles(self, client):
        c, tmp = client
        c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "admin_name": "Eric",
            "roles": ["server"],
        })
        marker = (tmp / "onboarding_complete").read_text()
        assert marker.splitlines() == ["Macky-Mac", "Eric"]

    def test_notes_become_the_being_purpose(self, client):
        c, tmp = client
        c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "roles": ["server"],
            "notes": "it also serves media to the house",
        })
        being = yaml.safe_load((tmp / "being.yml").read_text())
        assert being["purpose"] == "it also serves media to the house"

    def test_empty_notes_leave_purpose_alone(self, client):
        c, tmp = client
        c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "roles": ["server"],
        })
        being_path = tmp / "being.yml"
        purpose = yaml.safe_load(being_path.read_text()).get("purpose", "") \
            if being_path.exists() else ""
        assert not purpose

    def test_roles_reach_the_identity_resolver(self, client):
        c, tmp = client
        c.post("/api/settings/onboarding/complete", json={
            "computer_name": "Macky-Mac",
            "roles": ["server", "home_automation_hub"],
        })
        assert identity.resolve_machine_roles() == [
            "server", "home_automation_hub"]


class TestMachineRolesEndpoints:
    def test_get_is_empty_before_onboarding(self, client):
        c, _ = client
        resp = c.get("/api/settings/machine-roles")
        assert resp.status_code == 200
        assert resp.json()["roles"] == []
        assert "workstation" in resp.json()["valid"]

    def test_post_writes_preferences(self, client):
        c, tmp = client
        resp = c.post("/api/settings/machine-roles",
                      json={"roles": ["home_automation_hub"]})
        assert resp.status_code == 200, resp.text
        assert _prefs(tmp)["roles"] == ["home_automation_hub"]
        assert identity.resolve_machine_roles() == ["home_automation_hub"]

    def test_post_rejects_an_empty_set(self, client):
        c, tmp = client
        resp = c.post("/api/settings/machine-roles", json={"roles": []})
        assert resp.status_code == 200, resp.text
        assert resp.json()["roles"] == ["workstation"]


class TestProbe:
    def test_probe_returns_signals_and_suggestion(self, client, monkeypatch):
        c, _ = client
        monkeypatch.setattr(
            "halbert_core.discovery.role_inference.collect_probe_signals",
            lambda: {"has_display": True, "session_type": "gui",
                     "ram_gb": 64, "cpu_cores": 24})
        resp = c.get("/api/settings/onboarding/probe")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signals"]["has_display"] is True
        assert body["suggestion"]["roles"] == ["workstation"]

    def test_probe_never_writes_a_profile(self, client, monkeypatch, tmp_path):
        c, tmp = client
        monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp / "data"))
        monkeypatch.setattr(
            "halbert_core.discovery.role_inference.collect_probe_signals",
            lambda: {})
        resp = c.get("/api/settings/onboarding/probe")
        assert resp.status_code == 200
        assert not (tmp / "data" / "system_profile.json").exists()


class TestResolveMachineRoles:
    def test_filters_stale_values(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
        (tmp_path / "preferences.yml").write_text(
            "roles: [workstation, it_admin]\n")
        assert identity.resolve_machine_roles() == ["workstation"]

    def test_absent_preferences_means_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
        assert identity.resolve_machine_roles() == []
