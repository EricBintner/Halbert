# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""W3-S09: every client-side route in App.tsx is served by the dashboard.

The SPA route table in dashboard/app.py is explicit rather than a catch-all
(so a mistyped API URL still 404s). The cost is that a route added on the
frontend and not here is a 404 under the systemd deployment — which is how
the kiosk deep link ``chromium --kiosk http://127.0.0.1:8001/voice`` came
to serve nothing. This file keeps the two lists in step.
"""

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard import app as dashboard_app  # noqa: E402

APP_TSX = Path(dashboard_app.__file__).parent / "frontend" / "src" / "App.tsx"


def _frontend_paths():
    return sorted(set(re.findall(r'<Route\s+path="([^"]+)"', APP_TSX.read_text())))


def test_app_tsx_routes_are_parsed():
    # Guard the regex: if App.tsx changes shape and this matches nothing,
    # the parity test below would pass vacuously.
    paths = _frontend_paths()
    assert "/" in paths
    assert "/voice" in paths
    assert len(paths) >= 10


def test_every_frontend_route_is_served_by_the_spa_table():
    served = set(dashboard_app.SPA_ROUTES) | {"/"}
    missing = [p for p in _frontend_paths() if p not in served]
    assert not missing, (
        "routes in frontend/src/App.tsx with no entry in dashboard.app.SPA_ROUTES "
        f"(they 404 as deep links under the systemd deployment): {missing}"
    )


def test_voice_routes_are_in_the_table():
    assert "/voice" in dashboard_app.SPA_ROUTES
    assert "/voice-hud" in dashboard_app.SPA_ROUTES


@pytest.fixture
def client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa-marker</title>")
    app = FastAPI()
    dashboard_app.mount_frontend(app, dist)
    return TestClient(app)


def test_spa_routes_serve_index_html(client):
    for path in ("/voice", "/voice-hud", "/findings", "/terminal"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "spa-marker" in resp.text, path
        assert resp.headers["cache-control"].startswith("no-cache"), path


def test_spa_table_is_not_a_catch_all(client):
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/not-a-route").status_code == 404


def test_root_serves_index_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "spa-marker" in resp.text
