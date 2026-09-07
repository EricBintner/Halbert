# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hermes-documented darwin fact: Apple fsync(2) guarantees neither ordering nor
platter landing, and a shutdown observed corrupting 'durable' checkpoints
(hermes_state_wal.py:93-111). On darwin: checkpoint_fullfsync=1 and
synchronous=FULL, refusing to lower below FULL.

(Packet-08 A1. Test sketch adapted to the store's real accessors: both stores
expose the connection as ``_conn``, and the tests construct over a real file
DB because both factories only set the durability PRAGMAs on a
self-opened connection — a caller-owned ``conn=`` is the caller's to tune.)
"""

import sys

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.continuity.state_store import StateStore

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="darwin-only durability"
)


def test_darwin_pragmas_set_conversation_store(tmp_path):
    store = SqliteConversationStore(str(tmp_path / "conv.db"))
    try:
        conn = store._conn
        assert conn is not None
        assert conn.execute("PRAGMA checkpoint_fullfsync").fetchone()[0] == 1
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    finally:
        store.close()


def test_darwin_pragmas_set_state_store(tmp_path):
    store = StateStore(str(tmp_path / "state.db"))
    try:
        conn = store._conn
        assert conn.execute("PRAGMA checkpoint_fullfsync").fetchone()[0] == 1
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    finally:
        store.close()