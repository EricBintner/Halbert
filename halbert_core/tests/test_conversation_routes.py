# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P3b: Conversation API endpoint tests.

Tests the peer conversation routes that expose the local
SqliteConversationStore over HTTP for paired peer nodes. Uses mocked
store since we don't want to hit a real SQLite DB.
"""

from unittest.mock import patch, MagicMock

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


def _mock_store():
    return MagicMock()


def _patch_store(store):
    return patch(
        "halbert_core.dashboard.routes.conversations.get_conversation_store",
        return_value=store,
    )


class TestThreadEndpoints:
    def test_current_open_thread(self):
        app = _make_app()
        store = _mock_store()
        store.current_open_thread.return_value = {"thread_id": "t1", "title": "Test"}
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/current-open-thread")
        assert resp.status_code == 200
        assert resp.json()["thread"]["thread_id"] == "t1"

    def test_current_open_thread_none(self):
        app = _make_app()
        store = _mock_store()
        store.current_open_thread.return_value = None
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/current-open-thread")
        assert resp.status_code == 200
        assert resp.json()["thread"] is None

    def test_get_thread_found(self):
        app = _make_app()
        store = _mock_store()
        store.get_thread.return_value = {"thread_id": "t1", "title": "Test"}
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/threads/t1")
        assert resp.status_code == 200

    def test_get_thread_not_found(self):
        app = _make_app()
        store = _mock_store()
        store.get_thread.return_value = None
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/threads/nonexistent")
        assert resp.status_code == 404

    def test_create_thread(self):
        app = _make_app()
        store = _mock_store()
        store.create_thread.return_value = {"thread_id": "new-t", "title": "New"}
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/threads", json={
                "thread_id": "new-t", "title": "New",
            })
        assert resp.status_code == 200
        assert resp.json()["thread"]["thread_id"] == "new-t"

    def test_update_thread(self):
        app = _make_app()
        store = _mock_store()
        store.update_thread.return_value = True
        with _patch_store(store):
            client = TestClient(app)
            resp = client.put("/api/conversations/threads/t1", json={
                "fields": {"status": "paused"},
            })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_list_threads(self):
        app = _make_app()
        store = _mock_store()
        store.list_threads.return_value = [{"thread_id": "t1"}, {"thread_id": "t2"}]
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/threads?status=open&limit=10")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2


class TestMessageEndpoints:
    def test_append_message(self):
        app = _make_app()
        store = _mock_store()
        store.append_message.return_value = 42
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/messages", json={
                "thread_id": "t1", "role": "user", "content": "Hello",
            })
        assert resp.status_code == 200
        assert resp.json()["message_id"] == 42

    def test_update_message(self):
        app = _make_app()
        store = _mock_store()
        store.update_message.return_value = True
        with _patch_store(store):
            client = TestClient(app)
            resp = client.put("/api/conversations/messages/42", json={
                "fields": {"content": "updated"},
            })
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_list_messages(self):
        app = _make_app()
        store = _mock_store()
        store.list_messages.return_value = [{"message_id": 1}, {"message_id": 2}]
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/threads/t1/messages?limit=10")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_recent_messages(self):
        app = _make_app()
        store = _mock_store()
        store.recent_messages.return_value = [{"message_id": 1}]
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/threads/t1/recent-messages?limit=5")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestOpenLoops:
    def test_add_open_loop(self):
        app = _make_app()
        store = _mock_store()
        store.add_open_loop.return_value = "loop-1"
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/open-loops", json={
                "thread_id": "t1", "description": "Follow up on X",
            })
        assert resp.status_code == 200
        assert resp.json()["loop_id"] == "loop-1"

    def test_list_open_loops(self):
        app = _make_app()
        store = _mock_store()
        store.list_open_loops.return_value = [{"id": "loop-1"}]
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/threads/t1/open-loops?open_only=true")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestSearch:
    def test_search(self):
        app = _make_app()
        store = _mock_store()
        store.search.return_value = [{"thread_id": "t1", "snippet": "match"}]
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/search?q=test&limit=5")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_search_receipts(self):
        app = _make_app()
        store = _mock_store()
        store.search_receipts.return_value = [{"thread_id": "t1"}]
        with _patch_store(store):
            client = TestClient(app)
            resp = client.get("/api/conversations/search-receipts?q=install")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestRecovery:
    def test_mark_in_progress_interrupted(self):
        app = _make_app()
        store = _mock_store()
        store.mark_in_progress_interrupted.return_value = 3
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/mark-in-progress-interrupted")
        assert resp.status_code == 200
        assert resp.json()["marked"] == 3

    def test_redact_message_success(self):
        app = _make_app()
        store = _mock_store()
        store.redact_message.return_value = "redacted"
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/messages/42/redact")
        assert resp.status_code == 200

    def test_redact_message_failure(self):
        app = _make_app()
        store = _mock_store()
        store.redact_message.side_effect = Exception("RedactionFailed")
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/messages/42/redact")
        assert resp.status_code == 500

    def test_merge_thread(self):
        app = _make_app()
        store = _mock_store()
        store.merge_thread.return_value = {"merged": True}
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/merge-thread", json={
                "new_thread_id": "t2", "prev_thread_id": "t1",
            })
        assert resp.status_code == 200

    def test_merge_thread_not_found(self):
        app = _make_app()
        store = _mock_store()
        store.merge_thread.return_value = None
        with _patch_store(store):
            client = TestClient(app)
            resp = client.post("/api/conversations/merge-thread", json={
                "new_thread_id": "t2", "prev_thread_id": "t1",
            })
        assert resp.status_code == 404


class TestAuthRequired:
    def test_current_open_thread_requires_auth(self):
        app = _make_app_no_auth()
        client = TestClient(app)
        resp = client.get("/api/conversations/current-open-thread")
        assert resp.status_code in (401, 403)

    def test_append_message_requires_auth(self):
        app = _make_app_no_auth()
        client = TestClient(app)
        resp = client.post("/api/conversations/messages", json={
            "thread_id": "t1", "role": "user", "content": "test",
        })
        assert resp.status_code in (401, 403)

    def test_search_requires_auth(self):
        app = _make_app_no_auth()
        client = TestClient(app)
        resp = client.get("/api/conversations/search?q=test")
        assert resp.status_code in (401, 403)


class TestStoreUnavailable:
    def test_503_when_store_none(self):
        app = _make_app()
        with patch(
            "halbert_core.dashboard.routes.conversations.get_conversation_store",
            return_value=None,
        ):
            client = TestClient(app)
            resp = client.get("/api/conversations/current-open-thread")
        assert resp.status_code == 503
