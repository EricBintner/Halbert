# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Mock-server tests for PeerConversationStore (singular entity, P3a).

The fake server here is the executable form of the P3a wire contract (see
``peer_conversation_store.py``'s module docstring): every ``requests.post``
the proxy makes is dispatched into a REAL ``SqliteConversationStore`` so the
proxy's semantics are tested against the store it stands in for, not against
canned responses. ``routes/conversations.py`` (P3b) must answer the same
envelope — this file is its reference implementation.

Covered:
- every public method round-trips through the proxy
- ``Conversation``-carrying methods (get/create/get_or_create/save) serialize
- ``RedactionFailed`` propagates (the one deliberate raise in the interface)
- connection errors and 401 raise ``PeerConversationUnavailable``
- ``healthy``/``connected`` degrade to False when the peer is down
- the method allowlist stays in parity with both classes' public interfaces
- ``ThreadManager`` accepts the proxy as a drop-in store
"""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import requests as _requests

from halbert_core.agents.conversation import Conversation
from halbert_core.agents.conversation_sqlite import (
    RedactionFailed,
    SqliteConversationStore,
)
from halbert_core.agents.peer_conversation_store import (
    PEER_CONVERSATION_METHODS,
    PeerConversationStore,
    PeerConversationUnavailable,
)
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import MessageSignals

TOKEN = "peer-token-1"


def _response(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    resp.text = json.dumps(payload or {})
    return resp


class FakeConversationServer:
    """In-process stand-in for the HA server's conversation API (P3b).

    Dispatches the proxy's invoke envelope into a real SQLite store, so a
    green test here means the proxy and the store agree on semantics.
    """

    def __init__(self, store: SqliteConversationStore, *, token: str = TOKEN):
        self.store = store
        self.token = token
        self.requests: list = []  # (verb, url, kwargs) of every call seen

    # -- the two transports the proxy uses -------------------------------

    def post(self, url, json=None, headers=None, timeout=None, **kw):
        self.requests.append(("POST", url, {"json": json, "headers": headers}))
        auth = (headers or {}).get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return _response(401, {"detail": "Missing or invalid bearer token"})
        body = json or {}
        method, args, kwargs = body.get("method"), body.get("args", []), body.get("kwargs", {})
        if method not in PEER_CONVERSATION_METHODS:
            return _response(400, {"detail": f"method not allowed: {method!r}"})
        # Conversation-carrying arg: rebuild the dataclass server-side.
        if method == "save":
            args = [Conversation.from_dict(args[0])]
        try:
            result = getattr(self.store, method)(*args, **kwargs)
        except RedactionFailed as e:
            return _response(500, {"error": {"type": "RedactionFailed",
                                             "message": str(e)}})
        if isinstance(result, Conversation):
            result = result.to_dict()
        return _response(200, {"value": result})

    def get(self, url, headers=None, timeout=None, **kw):
        self.requests.append(("GET", url, {"headers": headers}))
        auth = (headers or {}).get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return _response(401, {"detail": "Missing or invalid bearer token"})
        if url.endswith("/api/conversations/health"):
            return _response(200, {"healthy": self.store.healthy,
                                   "connected": self.store.connected})
        return _response(404, {"detail": "not found"})

    # -- patching helpers -------------------------------------------------

    def patch(self):
        return [patch("requests.post", new=self.post),
                patch("requests.get", new=self.get)]


@pytest.fixture
def server():
    return FakeConversationServer(SqliteConversationStore(":memory:"))


@pytest.fixture
def store(server):
    return PeerConversationStore(
        peer_url="http://ha-server.lan:8000",
        bearer_token=TOKEN,
        timeout=5.0,
    )


@pytest.fixture
def wired(server, store):
    """Proxy + fake server with the HTTP layer patched in."""
    with server.patch()[0], server.patch()[1]:
        yield server, store


# ---------------------------------------------------------------------------
# Public-interface round-trips (the P3a acceptance: every public method)
# ---------------------------------------------------------------------------

class TestRoundTrips:
    def test_thread_lifecycle(self, wired):
        server, store = wired
        assert store.create_thread("t1", "First thread", status="open") is True
        thread = store.get_thread("t1")
        assert thread is not None and thread["thread_id"] == "t1"
        assert thread["status"] == "open"
        assert store.create_thread("t1", "again") is False  # duplicate id
        assert store.update_thread("t1", title="Renamed", stale=True) is True
        assert store.get_thread("t1")["title"] == "Renamed"
        assert store.current_open_thread()["thread_id"] == "t1"
        listed = store.list_threads(status="open")
        assert [t["thread_id"] for t in listed] == ["t1"]

    def test_messages(self, wired):
        server, store = wired
        store.create_thread("t1", "First thread")
        mid = store.append_message(
            "t1", "user", "hello world", origin="human", turn_id="turn-1",
        )
        assert isinstance(mid, int)
        store.append_message("t1", "assistant", "hi there", turn_id="turn-1")
        msgs = store.list_messages("t1")
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["turn_id"] == "turn-1"
        assert store.recent_messages("t1")[-1]["content"] == "hi there"
        assert store.last_turn_id("t1") == "turn-1"
        assert store.update_message(mid, status="complete") is True
        assert store.mark_in_progress_interrupted() == 0

    def test_append_to_missing_thread_returns_none(self, wired):
        server, store = wired
        assert store.append_message("nope", "user", "x") is None

    def test_turns_and_receipts(self, wired):
        server, store = wired
        store.create_thread("t1", "Resilver thread")
        store.append_message("t1", "user", "check the resilver", turn_id="turn-1")
        store.append_message("t1", "assistant", "it is fine", turn_id="turn-1")
        turns = store.list_turns()
        assert len(turns) == 1 and turns[0]["turn_id"] == "turn-1"
        assert store.list_turns(before_turn_id="turn-1") == []
        assert store.upsert_receipt("t1", "Resilver thread", "resilver checked and fine") is True
        hits = store.search_receipts("resilver")
        assert hits and hits[0]["thread_id"] == "t1"
        snips = store.search_snippets("t1", "resilver")
        assert snips and "resilver" in snips[0]
        assert store.search("resilver") == ["t1"]

    def test_pending_notes(self, wired):
        server, store = wired
        store.create_thread("t1", "T")
        store.append_message("t1", "user", "q")
        store.append_message("t1", "system", "note one", origin="system",
                             visible_in_timeline=False)
        store.append_message("t1", "system", "note two", origin="system",
                             visible_in_timeline=False)
        assert store.pending_notes("t1") == ["note one", "note two"]
        assert store.pending_notes("t1", limit=1) == ["note one"]

    def test_redact_and_merge(self, wired):
        server, store = wired
        store.create_thread("t1", "Secrets")
        store.create_thread("t2", "Other")
        mid = store.append_message("t1", "user", "/srv/clients/acmecorp-payroll.kdbx")
        assert store.redact_message(mid) == "t1"
        assert store.list_messages("t1")[0]["content"] == store.REDACTED
        assert store.merge_thread("t1", "t2") == 1
        assert store.get_thread("t1")["status"] == "merged"
        # One row moved: t2 never had messages of its own in this test.
        assert len(store.list_messages("t2")) == 1

    def test_open_loops(self, wired):
        server, store = wired
        store.create_thread("t1", "T")
        loop_id = store.add_open_loop("t1", "follow up on resilver", domain="systems")
        assert isinstance(loop_id, int)
        loops = store.list_open_loops("t1")
        assert loops[0]["text"] == "follow up on resilver"
        assert store.close_open_loop(loop_id) is True
        assert store.list_open_loops("t1") == []
        assert store.list_open_loops("t1", open_only=False)

    def test_somatic_blocks(self, wired):
        server, store = wired
        assert store.add_somatic_block("s1", "b1", "heartbeat", "ok") is True
        blocks = store.list_somatic_blocks("s1")
        assert blocks[0]["block_id"] == "b1"
        assert store.remove_somatic_block("s1", "b1") is True
        assert store.list_somatic_blocks("s1") == []

    def test_terminal_blocks_and_sessions(self, wired):
        server, store = wired
        assert store.insert_terminal_session({
            "session_id": "sess1", "kind": "user", "owner": "human",
            "watched": 1, "spawned_at": time.time(), "last_state": "running",
        }) is True
        assert store.get_terminal_session("sess1")["kind"] == "user"
        assert store.list_terminal_sessions(kind="user")[0]["session_id"] == "sess1"
        assert store.update_terminal_session("sess1", last_state="exited") is True

        assert store.insert_terminal_block({
            "block_id": "blk1", "session_id": "sess1", "command": "ls",
            "started_at": time.time(), "output_head": "a\nb", "output_tail": "b",
        }) is True
        assert store.get_terminal_block("blk1")["command"] == "ls"
        assert store.list_terminal_blocks(session_id="sess1")[0]["block_id"] == "blk1"
        assert store.update_terminal_block("blk1", exit_code=0, last_state="exited") is True
        assert store.get_terminal_block("blk1")["exit_code"] == 0

    def test_conversation_dataclass_methods(self, wired):
        server, store = wired
        conv = store.create("c1", user_id="eric")
        assert isinstance(conv, Conversation) and conv.conversation_id == "c1"
        # save() upserts the thread row only — messages go through
        # append_message (the store's own contract), so get() reads back an
        # empty history until a message row exists.
        conv.add_message("user", "hello there")
        assert store.save(conv) is True
        assert store.get("c1").messages == []
        store.append_message("c1", "user", "hello there")
        loaded = store.get("c1")
        assert isinstance(loaded, Conversation)
        assert loaded.messages[0].content == "hello there"
        again = store.get_or_create("c1")
        assert again.conversation_id == "c1"
        assert store.delete("c1") is True
        assert store.get("c1") is None
        store.save(store.create("c2"))
        assert store.list_conversations()[0]["conversation_id"] == "c2"

    def test_migration_and_close(self, wired):
        server, store = wired
        assert store.migrate_terminal_block_ids_to_blocks() == 0
        store.close()  # no-op on the proxy; must not raise


# ---------------------------------------------------------------------------
# Failure semantics
# ---------------------------------------------------------------------------

class TestFailures:
    def test_redaction_failed_propagates(self, server, store):
        """The one deliberate raise in the store interface must survive the
        network hop: a privacy failure is reported as a failure."""
        def raise_failed(message_id):
            raise RedactionFailed("redaction did not land")
        server.store.redact_message = raise_failed
        with server.patch()[0], server.patch()[1]:
            with pytest.raises(RedactionFailed):
                store.redact_message(1)

    def test_connection_error_raises_unavailable(self, store):
        with patch("requests.post", side_effect=_requests.ConnectionError("refused")):
            with pytest.raises(PeerConversationUnavailable):
                store.get_thread("t1")

    def test_timeout_raises_unavailable(self, store):
        with patch("requests.post", side_effect=_requests.Timeout("timed out")):
            with pytest.raises(PeerConversationUnavailable):
                store.get_thread("t1")

    def test_401_raises_unavailable(self, server, store):
        bad = PeerConversationStore("http://ha-server.lan:8000", bearer_token="wrong")
        with server.patch()[0], server.patch()[1]:
            with pytest.raises(PeerConversationUnavailable, match="401"):
                bad.get_thread("t1")

    def test_server_error_raises_unavailable(self, store):
        with patch("requests.post", return_value=_response(500, {"detail": "boom"})):
            with pytest.raises(PeerConversationUnavailable, match="500"):
                store.get_thread("t1")

    def test_invalid_json_raises_unavailable(self, store):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = json.JSONDecodeError("no json", "", 0)
        with patch("requests.post", return_value=resp):
            with pytest.raises(PeerConversationUnavailable, match="JSON"):
                store.get_thread("t1")

    def test_health_degrades_to_false(self, store):
        with patch("requests.get", side_effect=_requests.ConnectionError("refused")):
            assert store.healthy is False
            assert store.connected is False

    def test_health_reads_peer_flags(self, server, store):
        with server.patch()[1]:
            assert store.healthy is True
            assert store.connected is True


# ---------------------------------------------------------------------------
# Contract: bearer header + allowlist parity
# ---------------------------------------------------------------------------

class TestContract:
    def test_bearer_header_on_every_request(self, server, store):
        with server.patch()[0], server.patch()[1]:
            store.get_thread("t1")
            store.healthy
        for verb, url, kwargs in server.requests:
            assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}", url

    def test_allowlist_matches_proxy_public_interface(self):
        """Every public method of the proxy is allowlisted and vice versa —
        an unlisted method would be dead code, an unimplemented listed one
        a silent hole in the drop-in claim."""
        public = {
            name for name in dir(PeerConversationStore)
            if not name.startswith("_") and callable(getattr(PeerConversationStore, name))
        }
        public -= {"close"}  # proxied as a local no-op, never sent over the wire
        assert public == set(PEER_CONVERSATION_METHODS)

    def test_allowlist_subset_of_sqlite_store(self):
        """The allowlist may only name methods the real store actually has —
        the server side dispatches into that store."""
        sqlite_public = {
            name for name in dir(SqliteConversationStore)
            if not name.startswith("_") and callable(getattr(SqliteConversationStore, name))
        }
        assert set(PEER_CONVERSATION_METHODS) <= sqlite_public

    def test_invoke_refuses_unlisted_method(self, store):
        with pytest.raises(PeerConversationUnavailable, match="not allowed"):
            store._invoke("execute_sql", [], {})


# ---------------------------------------------------------------------------
# Drop-in for ThreadManager
# ---------------------------------------------------------------------------

class TestThreadManagerDropIn:
    def test_begin_turn_through_proxy(self, wired):
        server, store = wired
        mgr = ThreadManager(store)
        ctx = mgr.begin_turn("why is the resilver slow?", MessageSignals(), "sess-1")
        assert ctx.thread_id
        # The user row landed in the SERVER-side store through the proxy.
        msgs = store.list_messages(ctx.thread_id)
        assert msgs and msgs[0]["role"] == "user"
        assert store.current_open_thread()["thread_id"] == ctx.thread_id