# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shared-thread tests for singular entity mode (P3d).

Two bodies, one autobiography: the HA server owns the canonical thread
database (a real ``SqliteConversationStore`` on a WAL file — not
``:memory:``, because WAL is exactly what multi-writer sharing exercises),
its own ``ThreadManager`` talks to that store directly, and workstation
``ThreadManager``s reach the same store through ``PeerConversationStore``
over the (faked) peer link.

Covered (the P3d acceptance):
- a thread started on the workstation is visible on the HA server and
  vice versa — same thread id, same rows, no copy lag
- a reply written by one body is read back as history by the other
- concurrent turns from several bodies do not corrupt the store: every
  message lands exactly once, ids stay unique, the store stays healthy
- two separate store *instances* on the same file (the two-process shape
  WAL was built for) interleave writes without corruption
- the known check-then-create race in concurrent ``begin_turn`` produces
  at worst two open threads, never a lost or mangled row
"""
from __future__ import annotations

import threading

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.peer_conversation_store import PeerConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import MessageSignals

# The fake server is the executable P3a/P3b wire contract, and is shared
# with test_peer_conversation_store.py so the two files cannot disagree
# about what the HA server answers.
from test_peer_conversation_store import TOKEN, FakeConversationServer


class SharedEntityHarness:
    """One HA server + N bodies, all against one canonical thread DB."""

    def __init__(self, db_path):
        # The HA server's store: the one canonical database.
        self.server_store = SqliteConversationStore(str(db_path))
        # The HA server's own ThreadManager, on the store directly.
        self.ha_manager = ThreadManager(self.server_store)
        # The peer link (faked HTTP) fronting the same store.
        self.server = FakeConversationServer(self.server_store)
        self._patchers = self.server.patch()
        # Workstation-side bodies, each with its own manager over the proxy.
        self.bodies = {}

    def add_body(self, name: str) -> ThreadManager:
        proxy = PeerConversationStore(
            peer_url="http://ha-server.lan:8000", bearer_token=TOKEN, timeout=5.0)
        mgr = ThreadManager(proxy)
        self.bodies[name] = mgr
        return mgr

    def __enter__(self) -> "SharedEntityHarness":
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *exc) -> None:
        for p in self._patchers:
            p.stop()
        self.server_store.close()


@pytest.fixture
def harness(tmp_path):
    with SharedEntityHarness(tmp_path / "conversations.db") as h:
        yield h


def _turn(mgr: ThreadManager, query: str, session: str, reply: str = "done"):
    """One full turn through a manager; returns the thread id."""
    ctx = mgr.begin_turn(query, MessageSignals(), session)
    mgr.end_turn(ctx, assistant_text=reply, blocks=[], terminal_block_ids=[],
                 diff_proposals=[])
    return ctx.thread_id


# ---------------------------------------------------------------------------
# Cross-node visibility
# ---------------------------------------------------------------------------

class TestCrossNodeVisibility:
    def test_thread_started_on_workstation_visible_on_ha(self, harness):
        ws = harness.add_body("workstation")
        thread_id = _turn(ws, "why is the resilver slow?", "ws-sess")

        # The HA server's OWN manager sees it, on the same thread id,
        # without any copy/sync step — it is the same database.
        assert harness.ha_manager.current()["thread_id"] == thread_id
        rows = harness.server_store.list_messages(thread_id)
        assert [m["role"] for m in rows] == ["user", "assistant"]

    def test_ha_reply_visible_on_workstation(self, harness):
        ws = harness.add_body("workstation")
        thread_id = _turn(ws, "why is the resilver slow?", "ws-sess")

        # The HA server's agent replies into the same thread directly.
        ha = harness.ha_manager
        ctx = ha.begin_turn("and the SMART errors?", MessageSignals(), "ha-sess")
        assert ctx.thread_id == thread_id
        ha.end_turn(ctx, assistant_text="disk 5 is the noisy one", blocks=[],
                    terminal_block_ids=[], diff_proposals=[])

        # The workstation reads the whole exchange back through the proxy.
        recent = ws.store.recent_messages(thread_id, limit=10)
        contents = [m["content"] for m in recent]
        assert "why is the resilver slow?" in contents
        assert "disk 5 is the noisy one" in contents

    def test_receipt_written_by_one_body_is_recallable_by_the_other(self, harness):
        ws = harness.add_body("workstation")
        thread_id = _turn(ws, "resilver the array tonight", "ws-sess")
        other = harness.add_body("laptop")
        hits = other.store.search_receipts("resilver")
        assert hits and hits[0]["thread_id"] == thread_id


# ---------------------------------------------------------------------------
# Concurrent access — no corruption
# ---------------------------------------------------------------------------

class TestConcurrentAccess:
    def test_concurrent_turns_from_several_bodies(self, harness):
        """Four bodies turning at once through the peer link, plus the HA
        server's own manager: every message lands exactly once."""
        managers = [("direct", harness.ha_manager)] + [
            (f"body{i}", harness.add_body(f"body{i}")) for i in range(4)
        ]
        errors = []
        threads_per_body = 5

        def run(name, mgr):
            try:
                for i in range(threads_per_body):
                    _turn(mgr, f"{name} asks about subject {i}", f"sess-{name}")
            except Exception as e:  # noqa: BLE001 — recorded, asserted below
                errors.append((name, e))

        threads = [
            threading.Thread(target=run, args=(name, mgr), name=name)
            for name, mgr in managers
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads)
        assert errors == []

        store = harness.server_store
        assert store.healthy is True
        # 5 bodies x 5 turns x (user + assistant) rows, none lost, none doubled.
        all_rows = []
        for t in store.list_threads(limit=1000):
            all_rows.extend(store.list_messages(t["thread_id"]))
        assert len(all_rows) == 5 * threads_per_body * 2
        # Message ids are unique — a doubled write would show as a duplicate id.
        ids = [m["message_id"] for m in all_rows]
        assert len(ids) == len(set(ids))

    def test_two_store_instances_on_one_file(self, tmp_path):
        """The two-process shape WAL exists for: two direct store instances
        on the same database file, interleaving writes from threads."""
        db = tmp_path / "two-process.db"
        store_a = SqliteConversationStore(str(db))
        store_b = SqliteConversationStore(str(db))
        store_a.create_thread("t1", "Shared")
        store_b.create_thread("t2", "Shared")

        errors = []
        per_thread_writes, threads_per_store = 10, 4

        def hammer(store, thread_id, tag):
            try:
                for i in range(per_thread_writes):
                    assert store.append_message(
                        thread_id, "user", f"{tag}-{i}") is not None
            except Exception as e:  # noqa: BLE001
                errors.append((tag, e))

        # 4 threads hammering t1 via instance A, 4 hammering t2 via
        # instance B — two instances of the same file written concurrently.
        threads = [
            threading.Thread(target=hammer, args=(store_a, "t1", f"a-{n}"))
            for n in range(threads_per_store)
        ] + [
            threading.Thread(target=hammer, args=(store_b, "t2", f"b-{n}"))
            for n in range(threads_per_store)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert not any(t.is_alive() for t in threads)
        assert errors == []
        assert store_a.healthy and store_b.healthy
        assert len(store_a.list_messages("t1")) == threads_per_store * per_thread_writes
        assert len(store_b.list_messages("t2")) == threads_per_store * per_thread_writes
        store_a.close()
        store_b.close()

    def test_concurrent_begin_turn_never_loses_a_row(self, harness):
        """Known race, bounded damage: two bodies beginning a turn at the
        same instant can both see 'no open thread' and each open one — the
        check (current_open_thread) and the create (create_thread) are two
        wire calls, not one atomic step. What must NEVER happen is a lost
        or mangled row: both turns persist fully, and at most two open
        threads exist afterwards. (Collapsing the race needs a server-side
        atomic get-or-open; out of scope for P3d, noted for P3c.)"""
        ws_a = harness.add_body("workstation-a")
        ws_b = harness.add_body("workstation-b")
        barrier = threading.Barrier(2)
        results = []

        def begin(mgr, query):
            barrier.wait()
            ctx = mgr.begin_turn(query, MessageSignals(), "sess")
            mgr.end_turn(ctx, assistant_text="ok", blocks=[],
                         terminal_block_ids=[], diff_proposals=[])
            results.append(ctx.thread_id)

        t1 = threading.Thread(target=begin, args=(ws_a, "query from a"))
        t2 = threading.Thread(target=begin, args=(ws_b, "query from b"))
        t1.start(); t2.start()
        t1.join(timeout=30); t2.join(timeout=30)
        assert not (t1.is_alive() or t2.is_alive())

        store = harness.server_store
        open_threads = store.list_threads(status="open", limit=10)
        assert len(open_threads) <= 2
        for thread_id in results:
            rows = store.list_messages(thread_id)
            assert [m["role"] for m in rows] == ["user", "assistant"]
        # Both turns' rows survived regardless of how the race resolved.
        total = sum(len(store.list_messages(t["thread_id"]))
                    for t in store.list_threads(limit=10))
        assert total == len(results) * 2