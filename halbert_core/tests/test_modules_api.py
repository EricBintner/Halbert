# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Module API hardening tests.

Covers:
- File-access allowlist rejection (arbitrary outside-root path → 403)
- Unknown module name → clean 404
- drive-health payload self-describes its telemetry source
"""

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes.modules import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_unknown_module_returns_404(client):
    resp = client.get("/api/modules/no-such-module/data")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_config_diff_path_outside_allowlist_returns_403(client):
    # $HOME/.ssh/id_rsa is outside every allowed root (/etc, ~/.config,
    # host-config staging) — must be rejected whether or not it exists.
    ssh_key = str(Path.home() / ".ssh" / "id_rsa")
    resp = client.get("/api/modules/config-diff/data", params={"path": ssh_key})
    assert resp.status_code == 403


def test_config_diff_missing_path_param_returns_400(client):
    resp = client.get("/api/modules/config-diff/data")
    assert resp.status_code == 400


def test_config_diff_missing_file_returns_404(client):
    resp = client.get(
        "/api/modules/config-diff/data",
        params={"path": "/etc/halbert-definitely-does-not-exist-xyz.conf"},
    )
    assert resp.status_code == 404


def test_evidence_file_source_outside_allowlist_returns_403(client):
    resp = client.get(
        "/api/modules/evidence/data",
        params={"source": f"file:{Path.home()}/.bash_history"},
    )
    assert resp.status_code == 403


def test_list_modules_includes_registry_defaults(client):
    resp = client.get("/api/modules")
    assert resp.status_code == 200
    names = {m["name"] for m in resp.json()["modules"]}
    assert {"config-diff", "vitals", "drive-health", "evidence"} <= names


def test_drive_health_payload_self_describes_telemetry(client):
    resp = client.get("/api/modules/drive-health/data")
    assert resp.status_code == 200
    body = resp.json()
    # Partition-usage telemetry only — never SMART/temperature.
    assert body.get("telemetry_source") == "psutil-partitions"
    for drive in body.get("drives", []):
        assert "smart" not in drive
        assert "temperature" not in drive
