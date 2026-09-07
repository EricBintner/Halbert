# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hermes contract (hermes_state_fts.py:310): a corrupt derived index never
blocks canonical writes. On FTS write failure: (1) a stale breadcrumb is
persisted atomically with disarming the index sync — once the sync is absent
the index has a gap of unknown extent, so nobody may re-arm it without a full
rebuild; (2) the canonical row write still succeeds; (3) search falls back to
LIKE and keeps serving.

(Packet-08 A2. Adapted to ``SqliteConversationStore``'s real API: ``search``
returns thread ids, ``append_message`` requires the thread row to exist, and
Halbert's index sync is direct gated INSERTs rather than Hermes's triggers —
the breadcrumb/disarm pairing and the rebuild gate are the same contract.)
"""

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "conv.db"))
    yield s
    s.close()


def _seed_thread(store, thread_id="t1"):
    assert store.create_thread(thread_id, "unrelated title") is True


def test_canonical_write_survives_fts_corruption(store):
    _seed_thread(store)
    store._corrupt_fts_for_test()
    msg_id = store.append_message(thread_id="t1", role="user", content="hello world")
    assert msg_id is not None                      # canonical write succeeded
    assert store.fts_degraded is True              # breadcrumb persisted
    hits = store.search("hello")                   # LIKE fallback serves
    assert "t1" in hits


def test_rows_keep_landing_while_degraded(store):
    _seed_thread(store)
    store._corrupt_fts_for_test()
    first = store.append_message(thread_id="t1", role="user", content="first")
    second = store.append_message(thread_id="t1", role="user", content="second")
    assert first is not None and second is not None
    assert store.list_messages("t1") and len(store.list_messages("t1")) == 2


def test_triggers_not_reinstalled_over_unknown_gap(store):
    _seed_thread(store)
    store._corrupt_fts_for_test()
    assert store.append_message(thread_id="t1", role="user", content="second") is not None
    with pytest.raises(RuntimeError, match="full rebuild"):
        store._reinstall_fts_triggers()  # must refuse while degraded


def test_full_rebuild_clears_degraded(store):
    _seed_thread(store)
    store._corrupt_fts_for_test()
    assert store.append_message(thread_id="t1", role="user", content="third") is not None
    assert store.rebuild_fts() is True
    assert store.fts_degraded is False
    assert store.search("third") == ["t1"]         # FTS serving again


def test_breadcrumb_survives_reopen(tmp_path):
    store = SqliteConversationStore(str(tmp_path / "conv.db"))
    try:
        assert store.create_thread("t1", "unrelated title") is True
        store._corrupt_fts_for_test()
        assert store.append_message(thread_id="t1", role="user", content="hello") is not None
        assert store.fts_degraded is True
    finally:
        store.close()
    reopened = SqliteConversationStore(str(tmp_path / "conv.db"))
    try:
        assert reopened.fts_degraded is True       # the stale breadcrumb stands
        assert reopened.search("hello") == ["t1"]  # LIKE fallback still serves
    finally:
        reopened.close()


def test_rebuild_allowed_after_fresh_corruption_without_degradation(store):
    # A healthy store is not degraded: rebuild_fts is plain maintenance there.
    _seed_thread(store)
    assert store.fts_degraded is False
    assert store.rebuild_fts() is True
    assert store.fts_degraded is False
    assert store.search("hello") == []


def test_constraint_rejection_is_not_corruption_and_still_rolls_back(store):
    # The carve-out Hermes's predicate implies: an index copy rejecting a ROW
    # (CHECK) is not a corrupt INDEX -- that failure keeps the pre-existing
    # contract: the whole append rolls back and returns None, and no
    # breadcrumb is laid.
    _seed_thread(store)
    store._conn.execute("DROP TABLE messages_fts")
    store._conn.execute(
        "CREATE TABLE messages_fts (conversation_id TEXT, "
        "content TEXT CHECK(length(content) < 5))"
    )
    assert store.append_message("t1", "user", "hello world") is None
    assert store.fts_degraded is False
    assert store.list_messages("t1") == []