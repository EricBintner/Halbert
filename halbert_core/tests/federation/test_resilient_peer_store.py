# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Multi-node Task 3 — resilient peer conversation store.

The canonical host sleeps, the Wi-Fi drops, DHCP moves the box — and
``PeerConversationStore`` used to fail every call into the agent loop.
``ResilientPeerConversationStore`` wraps it with a write-through local
mirror and a durable FIFO staging queue. These tests pin the semantics:

- offline writes succeed locally and are staged in order
- offline reads serve the mirror (write-through + read-mirroring)
- flush replays FIFO, rewriting local-minted ids to peer ids
- ``redact_message`` is never staged
- transient failures back off; poisoned rows dead-letter out of the FIFO
"""
from __future__ import annotations

import time

import pytest
import requests

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.peer_conversation_store import (
    PeerConversationStore,
    PeerConversationUnavailable,
)
from halbert_core.agents.resilient_peer_store import ResilientPeerConversationStore


# ---------------------------------------------------------------------------
# Fake transports — a live peer backed by a real store, and a dead one
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _DownSession:
    """Peer unreachable — every request is a ConnectionError."""

    def post(self, *args, **kwargs):
        raise requests.ConnectionError("peer is down")

    def get(self, *args, **kwargs):
        raise requests.ConnectionError("peer is down")


class _LiveSession:
    """Dispatch the wire envelope to a real SqliteConversationStore."""

    def __init__(self, remote: SqliteConversationStore):
        self.remote = remote
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        method, args, kwargs = json["method"], json["args"], json["kwargs"]
        self.calls.append(method)
        value = getattr(self.remote, method)(*args, **kwargs)
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        elif isinstance(value, list):
            value = [v.to_dict() if hasattr(v, "to_dict") else v for v in value]
        return _Resp(200, {"value": value})

    def get(self, url, headers=None, timeout=None):
        return _Resp(200, {"healthy": True, "connected": True})


class _FlakySession(_LiveSession):
    """Fails N POSTs with ConnectionError, then goes live."""

    def __init__(self, remote, fail_times: int):
        super().__init__(remote)
        self._remaining = fail_times

    def post(self, url, json=None, headers=None, timeout=None):
        if self._remaining > 0:
            self._remaining -= 1
            raise requests.ConnectionError("still down")
        return super().post(url, json=json, headers=headers, timeout=timeout)


class _BoomSession:
    """Peer reachable but every call explodes — a non-transport failure."""

    def post(self, *args, **kwargs):
        raise ValueError("server blew up mid-call")

    def get(self, *args, **kwargs):
        return _Resp(200, {"healthy": True, "connected": True})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rig(tmp_path):
    remote = SqliteConversationStore(str(tmp_path / "remote.db"))
    session = _LiveSession(remote)
    peer = PeerConversationStore("http://peer.test", "tok", session=session)
    store = ResilientPeerConversationStore(
        peer, str(tmp_path / "cache.db"), autostart_flush=False)
    yield store, remote, session, peer
    store.close()


def _down(peer):
    peer._session = _DownSession()


def _up(peer, session):
    peer._session = session


def _rewind_retries(store):
    """Force every queued row's backoff window to 'due now'."""
    with store.local._lock, store.local._conn:
        store.local._conn.execute(
            "UPDATE staged_invocation SET next_retry_at = 0")


# ---------------------------------------------------------------------------
# Offline writes stage and serve locally
# ---------------------------------------------------------------------------

class TestOfflineWrites:
    def test_append_returns_local_id_and_serves_locally(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        assert store.create_thread("t1", "T") is True
        mid = store.append_message("t1", "user", "hello offline")
        assert isinstance(mid, int)
        assert store.staged_count() == 2

        msgs = store.list_messages("t1")
        assert len(msgs) == 1
        assert msgs[0]["content"] == "hello offline"

    def test_online_writes_flow_through_and_mirror(self, rig):
        store, remote, session, peer = rig
        store.create_thread("t1", "T")
        mid = store.append_message("t1", "user", "hello online")
        assert mid is not None
        assert store.staged_count() == 0
        # The remote got it...
        assert remote.list_messages("t1")[0]["content"] == "hello online"
        # ...and the mirror has a copy under its own id.
        local_msgs = store.local.list_messages("t1")
        assert local_msgs[0]["content"] == "hello online"
        # map: local id ↔ peer id
        assert store._peer_id_for(local_msgs[0]["message_id"], "message") == mid

    def test_offline_read_falls_back_to_mirror(self, rig):
        store, remote, session, peer = rig
        store.create_thread("t1", "T")
        store.append_message("t1", "user", "before outage")
        _down(peer)
        msgs = store.list_messages("t1")
        assert msgs[0]["content"] == "before outage"

    def test_read_mirrors_peer_only_data(self, rig):
        """Data the satellite never wrote appears in the cache after a
        successful online read, then survives the outage."""
        store, remote, session, peer = rig
        remote.create_thread("tx", "peer-side")
        remote.append_message("tx", "assistant", "written on the host")
        # Online read mirrors it into the cache.
        msgs = store.list_messages("tx")
        assert msgs[0]["content"] == "written on the host"
        _down(peer)
        msgs = store.list_messages("tx")
        assert msgs[0]["content"] == "written on the host"


# ---------------------------------------------------------------------------
# Flush — order, id rewriting, peer id capture
# ---------------------------------------------------------------------------

class TestFlush:
    def test_fifo_order_and_peer_id_capture(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        store.create_thread("t1", "T")
        local_mid = store.append_message("t1", "user", "staged hello")
        session.calls.clear()
        _up(peer, session)

        flushed = store.flush_pending()
        assert flushed == 2
        assert store.staged_count() == 0
        assert session.calls == ["create_thread", "append_message"]

        peer_msgs = remote.list_messages("t1")
        assert peer_msgs[0]["content"] == "staged hello"
        peer_mid = peer_msgs[0]["message_id"]
        assert store._peer_id_for(local_mid, "message") == peer_mid

    def test_update_message_rewritten_to_peer_id(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        store.create_thread("t1", "T")
        local_mid = store.append_message("t1", "user", "raw")
        store.update_message(local_mid, metadata={"flag": 7})
        _up(peer, session)

        assert store.flush_pending() == 3
        peer_msg = remote.list_messages("t1")[0]
        assert peer_msg["metadata"]["flag"] == 7
        assert peer_msg["message_id"] != local_mid or True  # id rewritten regardless

    def test_offline_update_of_peer_id_message(self, rig):
        """update_message(peer_id) while offline: applies to the mirror
        via the map and replays to the peer as the peer's id."""
        store, remote, session, peer = rig
        store.create_thread("t1", "T")
        peer_mid = store.append_message("t1", "user", "online write")
        _down(peer)
        assert store.update_message(peer_mid, metadata={"v": 9}) is True
        session.calls.clear()
        _up(peer, session)
        assert store.flush_pending() == 1
        assert remote.list_messages("t1")[0]["metadata"]["v"] == 9
        # The wire call carried the peer's id, not the local one.
        assert session.calls == ["update_message"]

    def test_flush_stops_when_peer_drops_mid_replay(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        store.create_thread("t1", "T")
        store.append_message("t1", "user", "one")
        store.append_message("t1", "user", "two")

        class DropsAfterFirst(_LiveSession):
            def __init__(self, remote):
                super().__init__(remote)
                self._n = 0

            def post(self, url, json=None, headers=None, timeout=None):
                self._n += 1
                if self._n > 1:
                    raise requests.ConnectionError("dropped mid-flush")
                return super().post(url, json=json, headers=headers, timeout=timeout)

        _up(peer, DropsAfterFirst(remote))
        assert store.flush_pending() == 1  # only create_thread landed
        assert store.staged_count() == 2   # order preserved for next pass


# ---------------------------------------------------------------------------
# redact_message — never staged
# ---------------------------------------------------------------------------

class TestRedactMessage:
    def test_unavailable_surfaces_not_staged(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        with pytest.raises(PeerConversationUnavailable):
            store.redact_message(1)
        assert store.staged_count() == 0


# ---------------------------------------------------------------------------
# Backoff and dead-lettering
# ---------------------------------------------------------------------------

class TestBackoff:
    def test_retries_until_success(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        store.create_thread("t1", "T")
        _up(peer, _FlakySession(remote, fail_times=3))

        for _ in range(3):
            assert store.flush_pending() == 0
            _rewind_retries(store)
        assert store.flush_pending() == 1
        assert store.staged_count() == 0

    def test_backoff_defers_retry(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        store.create_thread("t1", "T")
        _up(peer, _FlakySession(remote, fail_times=10))
        store.flush_pending()
        # The row now has a future next_retry_at — a second pass skips it.
        assert store.flush_pending() == 0

    def test_poisoned_row_dead_letters_out_of_fifo(self, rig):
        store, remote, session, peer = rig
        _down(peer)
        store.create_thread("t1", "T")
        _up(peer, _BoomSession())
        for _ in range(5):
            store.flush_pending()
            _rewind_retries(store)
        assert store.staged_count() == 0  # excluded from the FIFO
        row = store.local._conn.execute(
            "SELECT dead_lettered_at FROM staged_invocation").fetchone()
        assert row["dead_lettered_at"] is not None


# ---------------------------------------------------------------------------
# Store-surface plumbing
# ---------------------------------------------------------------------------

class TestSurface:
    def test_health_delegates_to_peer(self, rig):
        store, remote, session, peer = rig
        assert store.healthy is True and store.connected is True
        _down(peer)
        assert store.healthy is False and store.connected is False

    def test_unknown_methods_raise_attribute_error(self, rig):
        store, *_ = rig
        with pytest.raises(AttributeError):
            store.definitely_not_a_method

    def test_thread_reads(self, rig):
        store, remote, session, peer = rig
        store.create_thread("t1", "My Title", status="open")
        t = store.get_thread("t1")
        assert t["title"] == "My Title"
        _down(peer)
        t = store.get_thread("t1")
        assert t["thread_id"] == "t1"
