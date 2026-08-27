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


def test_json_stores_are_gone_from_agents_conversation():
    import halbert_core.agents.conversation as conv

    # the records stay — the SQLite store and the history path use them
    assert hasattr(conv, "Conversation")
    assert hasattr(conv, "Message")
    for name in ("ConversationStore", "SessionStore", "Session",
                 "get_conversation_store", "get_session_store"):
        assert not hasattr(conv, name), name


def test_agents_package_no_longer_reexports_deleted_symbols():
    import halbert_core.agents as agents

    for name in ("ConversationStore", "get_conversation_store",
                 "PlanningHandler", "SearchingHandler", "ReadingHandler",
                 "ExecutingHandler", "ObservingHandler", "RespondingHandler"):
        assert name not in agents.__all__, name
        assert not hasattr(agents, name), name
    assert "Conversation" in agents.__all__
    assert "Message" in agents.__all__


def test_handlers_package_is_gone():
    import halbert_core.agents  # noqa: F401
    assert importlib.util.find_spec("halbert_core.agents.handlers") is None


def test_json_migration_helper_is_gone():
    import halbert_core.agents.conversation_sqlite as cs
    assert not hasattr(cs, "migrate_json_conversations_to_sqlite")
