# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
CORS tests for the dashboard app: the Tauri webview origin (tauri://localhost
on macOS/Linux, http://tauri.localhost on Windows) must be allowed, plus any
extra origins from HALBERT_CORS_ORIGINS. Unknown origins get no CORS header.
"""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard.app import create_app  # noqa: E402

ROUTE = "/api/settings/onboarding/status"


@pytest.fixture
def client():
    return TestClient(create_app())


def test_cors_allows_tauri_origin(client):
    resp = client.get(ROUTE, headers={"Origin": "tauri://localhost"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "tauri://localhost"


def test_cors_allows_windows_tauri_origin(client):
    resp = client.get(ROUTE, headers={"Origin": "http://tauri.localhost"})
    assert resp.headers["access-control-allow-origin"] == "http://tauri.localhost"


def test_cors_preflight_tauri(client):
    resp = client.options(
        ROUTE,
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "tauri://localhost"


def test_cors_rejects_unknown_origin(client):
    resp = client.get(ROUTE, headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_extra_origins_from_env(monkeypatch):
    monkeypatch.setenv("HALBERT_CORS_ORIGINS", "http://127.0.0.1:9123,http://extra.example")
    client = TestClient(create_app())
    resp = client.get(ROUTE, headers={"Origin": "http://extra.example"})
    assert resp.headers["access-control-allow-origin"] == "http://extra.example"


def test_cors_wildcard_env_entry_is_rejected(monkeypatch, caplog):
    """'*' must never reach allow_origins: with allow_credentials=True a wildcard
    would let any site make credentialed cross-origin requests."""
    monkeypatch.setenv("HALBERT_CORS_ORIGINS", "*")
    import logging

    with caplog.at_level(logging.WARNING):
        client = TestClient(create_app())
    resp = client.get(ROUTE, headers={"Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
    assert any("HALBERT_CORS_ORIGINS" in r.getMessage() for r in caplog.records)


def test_cors_wildcard_mixed_with_valid_origins(monkeypatch):
    """Whitespace-only and '*' entries are dropped; real origins still work."""
    monkeypatch.setenv("HALBERT_CORS_ORIGINS", " , *, http://extra.example ,  ")
    client = TestClient(create_app())
    assert "access-control-allow-origin" not in client.get(
        ROUTE, headers={"Origin": "http://evil.example"}
    ).headers
    assert client.get(ROUTE, headers={"Origin": "http://extra.example"}).headers[
        "access-control-allow-origin"
    ] == "http://extra.example"
