# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Hermes _reconcile_columns (hermes_state_schema.py:641): the reference
schema DDL is the single source of truth; column additions need no
version-gated migration and a reordering can never skip a column. Also the
Hermes trap: a reconciler-added column without its DEFAULT/NOT NULL clause
hid whole histories until an unconditional backfill ran -- so reconciled
columns carry the reference decl and existing rows get the reference
default at the same open.

(Packet-08 A3. Sketch adapted: the dropped-column victim is a
DEFAULT-carrying additive column, so the upgrade can run on a POPULATED
table -- the packet's own gate demands a pre-inserted row survive
reconciliation, which an empty-table sketch never exercises.)
"""

import sqlite3

import pytest

from halbert_core.agents import conversation_sqlite as cs


def _drop_message_column(db_path: str, victim: str) -> None:
    """Rebuild ``messages`` without one column -- an old-shape store."""
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    assert victim in cols
    keep = [c for c in cols if c != victim]
    conn.execute("ALTER TABLE messages RENAME TO messages_old")
    conn.execute(f"CREATE TABLE messages AS SELECT {', '.join(keep)} FROM messages_old")
    conn.execute("DROP TABLE messages_old")
    conn.commit()
    conn.close()


def _columns_of(db_path: str, table: str):
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    conn.close()
    return cols


def test_old_shape_db_upgrades_in_place_with_zero_data_loss(tmp_path):
    db = str(tmp_path / "conv.db")
    store = cs.SqliteConversationStore(db)
    assert store.create_thread("t1", "old shape") is True
    assert store.append_message(thread_id="t1", role="user", content="survivor") is not None
    store.close()

    _drop_message_column(db, "status")
    # A row written by the OLD shape, before this open's reconciliation.
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO messages(conversation_id, role, content, timestamp, metadata) "
        "VALUES ('t1', 'user', 'pre-reconciliation words', 100.0, '{}')"
    )
    conn.commit()
    conn.close()

    store2 = cs.SqliteConversationStore(db)  # reconciliation on open
    try:
        assert "status" in _columns_of(db, "messages")
        rows = store2.list_messages("t1")
        # both rows survive, nothing blanked (order is incidental: the
        # simulated old shape lost its rowid-alias PK, so the raw row's id
        # is NULL and sorts first)
        assert sorted(r["content"] for r in rows) == [
            "pre-reconciliation words", "survivor",
        ]
        # and the Hermes silent-blank trap: the reconciled column reads the
        # reference default, not NULL/''
        assert rows[0]["status"] == "complete"
        assert rows[1]["status"] == "complete"
    finally:
        store2.close()


def test_reconciled_column_carries_reference_decl(tmp_path):
    db = str(tmp_path / "conv.db")
    store = cs.SqliteConversationStore(db)
    store.close()
    _drop_message_column(db, "status")

    cs.SqliteConversationStore(db).close()

    conn = sqlite3.connect(db)
    cols = conn.execute("PRAGMA table_info(messages)").fetchall()
    conn.close()
    # (cid, name, type, notnull, dflt_value, pk)
    row = next(r for r in cols if r[1] == "status")
    assert row is not None
    _, _, type_, notnull, dflt, pk = row
    assert type_ == "TEXT"
    assert notnull == 1
    assert dflt == "'complete'"


def test_reconciled_nullable_column_backfilled_not_blanked(tmp_path):
    db = str(tmp_path / "conv.db")
    store = cs.SqliteConversationStore(db)
    store.close()
    _drop_message_column(db, "origin")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO messages(conversation_id, role, content, timestamp, metadata) "
        "VALUES ('t1', 'user', 'history words', 100.0, '{}')"
    )
    conn.commit()
    conn.close()
    store2 = cs.SqliteConversationStore(db)
    try:
        rows = store2.list_messages("t1")
        assert len(rows) == 1
        assert rows[0]["origin"] == "human"  # reference default, not NULL
    finally:
        store2.close()


def test_reconciliation_idempotent_on_reopen(tmp_path):
    db = str(tmp_path / "conv.db")
    store = cs.SqliteConversationStore(db)
    store.close()
    _drop_message_column(db, "turn_id")
    store2 = cs.SqliteConversationStore(db)
    store2.close()
    after_first = _columns_of(db, "messages")
    store3 = cs.SqliteConversationStore(db)
    store3.close()
    after_second = _columns_of(db, "messages")
    assert after_first == after_second
    assert "turn_id" in after_second


def test_never_downgrades_or_renames_extra_columns(tmp_path):
    # A column the reference schema does not know about must survive
    # reconciliation untouched -- the reconciler only ever ADDs.
    db = str(tmp_path / "conv.db")
    store = cs.SqliteConversationStore(db)
    store.close()
    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE messages ADD COLUMN legacy_thing TEXT NOT NULL DEFAULT 'kept'")
    conn.commit()
    conn.close()
    store2 = cs.SqliteConversationStore(db)
    store2.close()
    conn = sqlite3.connect(db)
    cols = conn.execute("PRAGMA table_info(messages)").fetchall()
    conn.close()
    row = next(r for r in cols if r[1] == "legacy_thing")
    assert (row[2], row[3], row[4]) == ("TEXT", 1, "'kept'")


def test_additive_lists_agree_with_reference_schema():
    """The update-allowlists (_THREAD_COLUMNS/_MESSAGE_COLUMNS/
    _TERMINAL_BLOCK_ADDITIVE) and the reconciliation reference must never
    drift apart: every allowlisted additive column exists in the reference
    DDL with the exact same declaration."""
    for table, columns in (
        ("conversations", cs._THREAD_COLUMNS),
        ("messages", cs._MESSAGE_COLUMNS),
        ("terminal_blocks", cs._TERMINAL_BLOCK_ADDITIVE),
    ):
        reference = cs._reference_columns(table)
        for name, decl in columns:
            assert name in reference, f"{table}.{name} missing from the reference schema"
            assert reference[name] == decl, (
                f"{table}.{name}: reference {reference[name]!r} != allowlist {decl!r}"
            )


def test_reference_schema_is_the_only_column_source(tmp_path):
    """Fresh DB: reconciling an already-current DB must be a no-op that adds
    nothing -- every reference column already present."""
    db = str(tmp_path / "conv.db")
    store = cs.SqliteConversationStore(db)
    try:
        for table in cs._REFERENCE_SCHEMA:
            reference = set(cs._reference_columns(table))
            existing = {
                r[1] for r in store._conn.execute(f"PRAGMA table_info({table})")
            }
            assert existing >= reference, f"{table} missing {reference - existing}"
    finally:
        store.close()