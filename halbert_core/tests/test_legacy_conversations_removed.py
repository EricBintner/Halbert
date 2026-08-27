# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A deletions (spec §8): the JSON conversation surfaces are gone.

The timeline (/api/agent/timeline) is the only history API; the two JSON
stores, the /api/conversations router, the /api/agent/conversations
endpoints and the dead agents/handlers package must not come back.
"""

import importlib.util

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.dashboard.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # No `with`: startup hooks (migration, background starters) must not run here.
    return TestClient(create_app())


def test_conversations_router_is_gone(client):
    assert client.get("/api/conversations").status_code == 404
    assert client.post("/api/conversations", json={"name": "x"}).status_code == 404
    assert client.get("/api/conversations/some-id").status_code == 404


def test_agent_conversations_endpoints_are_gone(client):
    assert client.get("/api/agent/conversations").status_code == 404
    assert client.get("/api/agent/conversations/some-id").status_code == 404
    assert client.delete("/api/agent/conversations/some-id").status_code == 404


def test_conversations_route_module_is_gone():
    import halbert_core.dashboard.routes  # noqa: F401  (parent package must import)
    assert importlib.util.find_spec("halbert_core.dashboard.routes.conversations") is None
