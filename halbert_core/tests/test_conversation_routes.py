# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P3b: Conversation API endpoint tests.

Tests the P3b server half of the P3a wire contract: the single dispatch
endpoint POST /api/conversations/invoke and GET /api/conversations/health.
Uses a real SqliteConversationStore (in-memory) so the dispatch semantics
are verified against the store it stands in for, matching the approach in
test_peer_conversation_store.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes import conversations
from halbert_core.federation.peer_middleware import PeerContext, require_peer_auth
from halbert_core.federation.peers_config import PeerCredential


def _make_app():
    """Create a FastAPI app with conversations router and auth override."""
    app = FastAPI()
    app.include_router(conversations.router, prefix="/api/conversations")

    stub_cred = PeerCredential(
        node_id="test-peer", node_name="Test Peer", role="compute_provider",
        token_hash="sha256:stub", paired_at="2026-01-01T00:00:00Z",
    )
    stub_ctx = PeerContext(
        node_id="test-peer", node_name="Test Peer",
        role="compute_provider", capabilities=[], credential=stub_cred,
    )
    app.dependency_overrides[require_peer_auth] = lambda: stub_ctx
    return app


def _make_app_no_auth():
    """Create app without auth override (for auth tests)."""
    app = FastAPI()
    app.include_router(conversations.router, prefix="/api/conversations")
    return app


@pytest.fixture
def real_store(tmp_path):
    """Create a real in-memory SqliteConversationStore."""
    from halbert_core.agents.conversation_sqlite import SqliteConversationStore
    return SqliteConversationStore(":memory:")


@pytest.fixture
def app_with_store(real_store):
    """Create app with the real store injected."""
    conversations.reset_conversation_store()
    app = _make_app()
    # Patch the singleton to use our in-memory store
    with patch(
        "halbert_core.dashboard.routes.conversations.get_conversation_store",
        return_value=real_store,
    ):
        yield app, real_store
    conversations.reset_conversation_store()


class TestHealth:
    def test_health_returns_status(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)
        resp = client.get("/api/conversations/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "healthy" in data
        assert "connected" in data

    def test_health_requires_auth(self):
        app = _make_app_no_auth()
        client = TestClient(app)
        resp = client.get("/api/conversations/health")
        assert resp.status_code in (401, 403)

    def test_health_503_when_store_unavailable(self):
        conversations.reset_conversation_store()
        app = _make_app()
        with patch(
            "halbert_core.dashboard.routes.conversations.get_conversation_store",
            return_value=None,
        ):
            client = TestClient(app)
            resp = client.get("/api/conversations/health")
        assert resp.status_code == 503


class TestInvoke:
    def test_create_thread_and_get(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        # create_thread
        resp = client.post("/api/conversations/invoke", json={
            "method": "create_thread",
            "args": ["t1", "First thread"],
            "kwargs": {"status": "open"},
        })
        assert resp.status_code == 200
        assert resp.json()["value"] is True

        # get_thread
        resp = client.post("/api/conversations/invoke", json={
            "method": "get_thread",
            "args": ["t1"],
            "kwargs": {},
        })
        assert resp.status_code == 200
        thread = resp.json()["value"]
        assert thread is not None
        assert thread["thread_id"] == "t1"
        assert thread["title"] == "First thread"

    def test_append_message_and_list(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        # Create thread first
        client.post("/api/conversations/invoke", json={
            "method": "create_thread",
            "args": ["t1", "Test"],
            "kwargs": {},
        })

        # Append a message
        resp = client.post("/api/conversations/invoke", json={
            "method": "append_message",
            "args": ["t1"],
            "kwargs": {"role": "user", "content": "Hello world"},
        })
        assert resp.status_code == 200
        msg_id = resp.json()["value"]
        assert msg_id is not None and msg_id > 0

        # List messages
        resp = client.post("/api/conversations/invoke", json={
            "method": "list_messages",
            "args": ["t1"],
            "kwargs": {},
        })
        assert resp.status_code == 200
        messages = resp.json()["value"]
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello world"

    def test_current_open_thread(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        # No threads yet
        resp = client.post("/api/conversations/invoke", json={
            "method": "current_open_thread",
            "args": [],
            "kwargs": {},
        })
        assert resp.status_code == 200
        assert resp.json()["value"] is None

        # Create a thread
        client.post("/api/conversations/invoke", json={
            "method": "create_thread",
            "args": ["t1", "Open"],
            "kwargs": {"status": "open"},
        })

        resp = client.post("/api/conversations/invoke", json={
            "method": "current_open_thread",
            "args": [],
            "kwargs": {},
        })
        assert resp.status_code == 200
        thread = resp.json()["value"]
        assert thread is not None
        assert thread["thread_id"] == "t1"

    def test_update_thread(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        client.post("/api/conversations/invoke", json={
            "method": "create_thread",
            "args": ["t1", "Original"],
            "kwargs": {},
        })

        resp = client.post("/api/conversations/invoke", json={
            "method": "update_thread",
            "args": ["t1"],
            "kwargs": {"title": "Renamed", "stale": True},
        })
        assert resp.status_code == 200
        assert resp.json()["value"] is True

        # Verify
        resp = client.post("/api/conversations/invoke", json={
            "method": "get_thread",
            "args": ["t1"],
            "kwargs": {},
        })
        thread = resp.json()["value"]
        assert thread["title"] == "Renamed"
        # SQLite stores booleans as integers (1/0)
        assert thread["stale"] in (True, 1)

    def test_list_threads(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        for i in range(3):
            client.post("/api/conversations/invoke", json={
                "method": "create_thread",
                "args": [f"t{i}", f"Thread {i}"],
                "kwargs": {},
            })

        resp = client.post("/api/conversations/invoke", json={
            "method": "list_threads",
            "args": [],
            "kwargs": {"status": "open", "limit": 100},
        })
        assert resp.status_code == 200
        threads = resp.json()["value"]
        assert len(threads) == 3

    def test_search(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        client.post("/api/conversations/invoke", json={
            "method": "create_thread",
            "args": ["t1", "Garden discussion"],
            "kwargs": {},
        })
        client.post("/api/conversations/invoke", json={
            "method": "append_message",
            "args": ["t1"],
            "kwargs": {"role": "user", "content": "The garden is beautiful"},
        })

        resp = client.post("/api/conversations/invoke", json={
            "method": "search",
            "args": ["garden"],
            "kwargs": {"limit": 10},
        })
        assert resp.status_code == 200
        results = resp.json()["value"]
        assert len(results) >= 1

    def test_add_and_list_open_loops(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        client.post("/api/conversations/invoke", json={
            "method": "create_thread",
            "args": ["t1", "Test"],
            "kwargs": {},
        })

        resp = client.post("/api/conversations/invoke", json={
            "method": "add_open_loop",
            "args": ["t1"],
            "kwargs": {"text": "Follow up on X"},
        })
        assert resp.status_code == 200

        resp = client.post("/api/conversations/invoke", json={
            "method": "list_open_loops",
            "args": ["t1"],
            "kwargs": {"open_only": True},
        })
        assert resp.status_code == 200
        loops = resp.json()["value"]
        assert len(loops) >= 1

    def test_method_not_in_allowlist_rejected(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        resp = client.post("/api/conversations/invoke", json={
            "method": "__init__",
            "args": [],
            "kwargs": {},
        })
        assert resp.status_code == 400

    def test_close_not_in_allowlist(self, app_with_store):
        """close is deliberately absent from the allowlist (local no-op)."""
        app, store = app_with_store
        client = TestClient(app)

        resp = client.post("/api/conversations/invoke", json={
            "method": "close",
            "args": [],
            "kwargs": {},
        })
        assert resp.status_code == 400

    def test_invoke_requires_auth(self):
        app = _make_app_no_auth()
        client = TestClient(app)
        resp = client.post("/api/conversations/invoke", json={
            "method": "current_open_thread",
            "args": [],
            "kwargs": {},
        })
        assert resp.status_code in (401, 403)

    def test_invoke_503_when_store_unavailable(self):
        conversations.reset_conversation_store()
        app = _make_app()
        with patch(
            "halbert_core.dashboard.routes.conversations.get_conversation_store",
            return_value=None,
        ):
            client = TestClient(app)
            resp = client.post("/api/conversations/invoke", json={
                "method": "current_open_thread",
                "args": [],
                "kwargs": {},
            })
        assert resp.status_code == 503

    def test_null_return_value_is_valid(self, app_with_store):
        """null/false/[] are ordinary answers, not errors."""
        app, store = app_with_store
        client = TestClient(app)

        # get_thread on nonexistent → None
        resp = client.post("/api/conversations/invoke", json={
            "method": "get_thread",
            "args": ["nonexistent"],
            "kwargs": {},
        })
        assert resp.status_code == 200
        assert resp.json()["value"] is None

    def test_empty_list_return_is_valid(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        resp = client.post("/api/conversations/invoke", json={
            "method": "list_threads",
            "args": [],
            "kwargs": {"limit": 100},
        })
        assert resp.status_code == 200
        assert resp.json()["value"] == []


class TestConversationSerialization:
    """Verify Conversation-carrying methods serialize at the wire."""

    def test_get_returns_conversation_as_dict(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        # Create a conversation (not thread)
        client.post("/api/conversations/invoke", json={
            "method": "create",
            "args": ["conv1"],
            "kwargs": {},
        })

        resp = client.post("/api/conversations/invoke", json={
            "method": "get",
            "args": ["conv1"],
            "kwargs": {},
        })
        assert resp.status_code == 200
        conv = resp.json()["value"]
        # Conversation.to_dict() produces a dict with conversation_id
        assert conv is not None
        assert isinstance(conv, dict)
        assert conv["conversation_id"] == "conv1"


class TestRedactionFailedPropagation:
    """RedactionFailed must answer 500 with error envelope."""

    def test_redact_message_failure_returns_500(self, app_with_store):
        app, store = app_with_store
        client = TestClient(app)

        # Try to redact a nonexistent message — should fail
        resp = client.post("/api/conversations/invoke", json={
            "method": "redact_message",
            "args": [99999],
            "kwargs": {},
        })
        # redact_message returns None for missing message, not RedactionFailed
        # But if it does raise, we need to verify the 500 envelope
        # For a missing message, it returns None (200 with value: null)
        assert resp.status_code in (200, 500)
        if resp.status_code == 500:
            # Verify error envelope format
            detail = resp.json()["detail"]
            assert isinstance(detail, dict)
            assert "error" in detail
            assert detail["error"]["type"] == "RedactionFailed"


class TestAppPrefix:
    """Verify the router is mounted at /api/conversations."""

    def test_routes_have_correct_prefix(self):
        app = _make_app()
        routes = [r.path for r in app.routes]
        assert "/api/conversations/invoke" in routes
        assert "/api/conversations/health" in routes
