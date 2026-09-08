# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""T1 of the session-tree migration (D-1 design, 2026-09-07, §6 row "T1 —
schema (additive)"): the additive tree columns land through packet 08's
declarative column reconciliation, ``move_leaf`` ships as the unwired
transaction primitive (§1.2), and ``update_thread`` gains the title CAS
ladder (§1.4). Zero reader change, zero writer change for every existing
caller.

The one-leaf partial unique index (§1.2) is deliberately NOT here: landing
it as speced conflicts with merged reality (the P3d shared-store race and
the A6b-era duplicate rows), so it is held for the founder's Q3 answer
rather than improvised around -- see the T1 report.

Test shapes are the packet-08 patterns the design §6 test strategy names:
old-shape upgrade in place with zero data loss, reference-decl pins,
reconciliation idempotence, never-rename/never-downgrade, and
crash-injection atomicity.
"""

import sqlite3

import pytest

from halbert_core.agents import conversation_sqlite as cs


# ---------------------------------------------------------------------------
# Old-shape helpers (the packet-08 `_drop_message_column` pattern, widened
# to the three tables T1 touches)
# ---------------------------------------------------------------------------

def _drop_column(db_path: str, table: str, victim: str) -> None:
    """Rebuild ``table`` without one column -- an old-shape store."""
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    assert victim in cols
    keep = [c for c in cols if c != victim]
    conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
    conn.execute(f"CREATE TABLE {table} AS SELECT {', '.join(keep)} FROM {table}_old")
    conn.execute(f"DROP TABLE {table}_old")
    conn.commit()
    conn.close()


def _columns_of(db_path: str, table: str):
    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    conn.close()
    return cols


def _decl_of(db_path: str, table: str, column: str):
    """(name, type, notnull, dflt) as PRAGMA table_info reports them."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    conn.close()
    row = next(r for r in rows if r[1] == column)
    return row[2], row[3], row[4]


#: The columns T1 adds, per the design's M1 SQL blocks (§1.1, §1.3, §2.2,
#: §3.4, §5.1) -- table -> column -> (type, notnull, default).
T1_COLUMNS = {
    "conversations": {
        # §1.1: typed edge column, not Hermes's JSON markers.
        "edge_kind": ("TEXT", 1, "'root'"),
        # §5.1: guest thread rows carry no stable persona marker today
        # (guest provenance lives per-message in metadata), so the column
        # lands reserved for the Q3/T4 scope decision.
        "persona": ("TEXT", 0, None),
        # §3.4: persisted anti-thrash counters, on the row so a crash or
        # restart resumes the same cooldown.
        "compact_streak": ("INTEGER", 1, "0"),
        "compact_cooldown_until": ("REAL", 0, None),
        "compact_last_at": ("REAL", 0, None),
    },
    "messages": {
        # §2.2: the context half of the display/context split;
        # ``visible_in_timeline`` is the display half and already exists.
        "context_included": ("INTEGER", 1, "1"),
    },
    "compact_boundaries": {
        # §1.3: the rotation ledger's writer columns. The table still has
        # NO writers in T1 -- rotation is T3, default off.
        "coverage_end_id": ("INTEGER", 0, None),
        "generation": ("INTEGER", 1, "1"),
        "unresolved_request": ("TEXT", 1, "''"),
        "trigger_detail": ("TEXT", 1, "''"),
    },
}


# ---------------------------------------------------------------------------
# Old-shape upgrade (design §6: "a Plan-A-era DB (schema_version 4, no tree
# columns) opens, reconciles, inserts turn rows, and current_open_thread()
# returns the same answer before and after")
# ---------------------------------------------------------------------------

class TestOldShapeUpgrade:
    def test_plan_a_era_db_upgrades_in_place_with_zero_data_loss(self, tmp_path):
        db = str(tmp_path / "conv.db")
        store = cs.SqliteConversationStore(db)
        assert store.create_thread("leafy", "Samba share") is True
        assert store.create_thread("old", "NAS swap") is True
        assert store.update_thread("old", status="paused", paused_at=1.0) is True
        a = store.append_message(thread_id="leafy", role="user", content="survivor")
        b = store.append_message(thread_id="old", role="user", content="also survives")
        assert a is not None and b is not None
        store._conn.execute(
            "INSERT INTO compact_boundaries (thread_id, trigger, created_at) "
            "VALUES ('old', 'manual', 1.0)"
        )
        store._conn.commit()
        answer_before = store.current_open_thread()["thread_id"]
        store.close()

        # Simulate the Plan-A-era shape: strip every T1 column.
        for table, columns in T1_COLUMNS.items():
            for column in columns:
                _drop_column(db, table, column)

        store2 = cs.SqliteConversationStore(db)
        try:
            # Every T1 column is back, and each carries the reference decl
            # (the Hermes trap: no silent NULLs where the DDL states a
            # DEFAULT).
            for table, columns in T1_COLUMNS.items():
                present = _columns_of(db, table)
                for column, (type_, notnull, dflt) in columns.items():
                    assert column in present, f"{table}.{column} not reconciled"
                    assert _decl_of(db, table, column) == (type_, notnull, dflt)
            # Zero data loss: both threads, both messages, the boundary row.
            assert sorted(m["content"] for m in store2.list_messages("leafy")) == ["survivor"]
            assert sorted(m["content"] for m in store2.list_messages("old")) == ["also survives"]
            assert store2._conn.execute(
                "SELECT COUNT(*) FROM compact_boundaries"
            ).fetchone()[0] == 1
            # Reconciled rows read the reference defaults, not blanks.
            assert store2.get_thread("leafy")["edge_kind"] == "root"
            assert store2.get_thread("leafy")["compact_streak"] == 0
            row = store2._conn.execute(
                "SELECT context_included FROM messages WHERE id = ?", (a,)
            ).fetchone()
            assert row[0] == 1
            boundary = store2._conn.execute(
                "SELECT generation, unresolved_request, trigger_detail FROM compact_boundaries"
            ).fetchone()
            assert tuple(boundary) == (1, "", "")
            # The same open thread answers before and after.
            assert store2.current_open_thread()["thread_id"] == answer_before
            # And the upgraded store still takes writes.
            assert store2.append_message("leafy", "user", "post-upgrade write") is not None
        finally:
            store2.close()

    def test_tree_reconciliation_idempotent_on_reopen(self, tmp_path):
        db = str(tmp_path / "conv.db")
        store = cs.SqliteConversationStore(db)
        store.close()
        _drop_column(db, "conversations", "edge_kind")
        _drop_column(db, "messages", "context_included")
        cs.SqliteConversationStore(db).close()
        after_first = _columns_of(db, "conversations"), _columns_of(db, "messages")
        cs.SqliteConversationStore(db).close()
        after_second = _columns_of(db, "conversations"), _columns_of(db, "messages")
        assert after_first == after_second
        assert "edge_kind" in after_second[0]
        assert "context_included" in after_second[1]

    def test_extra_columns_survive_reconciliation_untouched(self, tmp_path):
        """Extends packet 08's never-rename/never-downgrade pin to the two
        tables T1 widens beyond messages: a column the reference schema does
        not know about must survive, and none of T1's columns may ever be
        dropped by a later open."""
        db = str(tmp_path / "conv.db")
        store = cs.SqliteConversationStore(db)
        store.close()
        conn = sqlite3.connect(db)
        conn.execute("ALTER TABLE conversations ADD COLUMN legacy_thing TEXT NOT NULL DEFAULT 'kept'")
        conn.execute("ALTER TABLE compact_boundaries ADD COLUMN legacy_mark TEXT")
        conn.commit()
        conn.close()
        store2 = cs.SqliteConversationStore(db)
        store2.close()
        conn = sqlite3.connect(db)
        conv = conn.execute("PRAGMA table_info(conversations)").fetchall()
        bounds = conn.execute("PRAGMA table_info(compact_boundaries)").fetchall()
        conn.close()
        row = next(r for r in conv if r[1] == "legacy_thing")
        assert (row[2], row[3], row[4]) == ("TEXT", 1, "'kept'")
        assert any(r[1] == "legacy_mark" for r in bounds)
        # T1's columns are still there too -- reconciliation only ever ADDs.
        names = {r[1] for r in conv}
        assert {"edge_kind", "persona", "compact_streak",
                "compact_cooldown_until", "compact_last_at"} <= names


# ---------------------------------------------------------------------------
# move_leaf (design §1.2): one transaction, statuses + the departure edge
# stamped on the child. T1 ships the primitive unwired; branch-summary
# minting (§2.3) is T2's addition inside it.
# ---------------------------------------------------------------------------

class TestMoveLeaf:
    @pytest.fixture
    def pair(self, tmp_path):
        store = cs.SqliteConversationStore(":memory:")
        store.create_thread("old", "Samba share")
        store.update_thread("old", status="open")
        store.create_thread("new", "Scanner share")
        store.update_thread("new", status="paused", paused_at=5.0)
        yield store
        store.close()

    def test_leaf_move_swaps_status_and_stamps_edge(self, pair):
        assert pair.move_leaf("old", "new", "branch", now=100.0) is True
        old = pair.get_thread("old")
        new = pair.get_thread("new")
        assert old["status"] == "paused"
        assert old["paused_at"] == 100.0
        assert (new["status"], new["paused_at"], new["turns_since_pause"]) == ("open", None, 0)
        assert new["parent_thread_id"] == "old"
        assert new["edge_kind"] == "branch"
        assert new["updated_at"] == 100.0

    def test_every_documented_edge_kind_is_stampable(self, pair):
        for edge in ("continuation", "branch", "delegate", "merged"):
            # reset both sides between rounds
            pair.update_thread("new", status="paused", paused_at=5.0)
            pair.update_thread("old", status="open")
            assert pair.move_leaf("old", "new", edge) is True
            assert pair.get_thread("new")["edge_kind"] == edge
            # restore for the next round: swap roles back via raw status
            pair._conn.execute("UPDATE conversations SET parent_thread_id = NULL, edge_kind = 'root'")
            pair._conn.commit()

    def test_move_leaf_refuses_root_self_unknown_and_non_open_old(self, pair):
        assert pair.move_leaf("old", "new", "root") is False
        assert pair.move_leaf("old", "old", "branch") is False
        assert pair.move_leaf("nope", "new", "branch") is False
        assert pair.move_leaf("old", "nope", "branch") is False
        assert pair.move_leaf("old", "new", "sideways") is False
        # 'old' is open, so that one is refused for the edge/ids above only;
        # pause it and the move is refused for the leaf reason.
        pair.update_thread("old", status="paused")
        assert pair.move_leaf("old", "new", "branch") is False
        # and a merged target never becomes the leaf (merged_into is a
        # terminal supersession edge, design §1.2)
        pair._conn.execute(
            "UPDATE conversations SET status = 'merged', merged_into = 'old' WHERE id = 'new'"
        )
        pair._conn.commit()
        assert pair.move_leaf("new", "old", "branch") is False

    def test_move_leaf_never_reparents(self, pair):
        """Design §0: "the leaf moves, rows never re-parent". A child that
        already records its provenance keeps it; the move only swaps
        statuses."""
        pair._conn.execute(
            "UPDATE conversations SET parent_thread_id = 'founder', edge_kind = 'continuation' "
            "WHERE id = 'new'"
        )
        pair._conn.commit()
        assert pair.move_leaf("old", "new", "branch") is True
        new = pair.get_thread("new")
        assert new["parent_thread_id"] == "founder"
        assert new["edge_kind"] == "continuation"
        assert new["status"] == "open"

    def test_move_leaf_is_atomic_under_an_injected_crash(self, pair, monkeypatch):
        """Design §6 crash-injection pattern, applied to the T1 primitive:
        a failure between the two status writes must leave no half-moved
        leaf after the rollback. (sqlite3.Connection attributes are
        read-only, so the crash is injected by swapping the store's
        connection for a delegating wrapper that raises on the first status
        write -- the transaction discipline under test is move_leaf's own
        ``with self._conn:`` block, not the wrapper.)"""
        real_conn = pair._conn

        class _CrashingConn:
            def __init__(self, real):
                self._real = real

            def execute(self, sql, *args, **kwargs):
                if sql.startswith("UPDATE conversations SET status = 'paused'"):
                    raise sqlite3.OperationalError(
                        "injected crash between the two writes"
                    )
                return self._real.execute(sql, *args, **kwargs)

            def __enter__(self):
                return self._real.__enter__()

            def __exit__(self, *exc):
                return self._real.__exit__(*exc)

            def __getattr__(self, name):
                return getattr(self._real, name)

        monkeypatch.setattr(pair, "_conn", _CrashingConn(real_conn))
        assert pair.move_leaf("old", "new", "branch", now=100.0) is False
        monkeypatch.undo()
        # No half-rotated state: the old row is still the open leaf, the
        # new row is still paused with no edge stamped.
        assert pair.get_thread("old")["status"] == "open"
        new = pair.get_thread("new")
        assert new["status"] == "paused"
        assert new["parent_thread_id"] is None
        # and the store still works afterwards
        assert pair.move_leaf("old", "new", "branch", now=101.0) is True


# ---------------------------------------------------------------------------
# Title CAS (design §1.4): "an LLM-refined title never clobbers a
# founder-typed one". The ladder covers the repo's real vocabulary --
# 'receipt' is the refined rank threads.py writes, 'model' the model-given
# provisional -- plus the design's reserved 'refined'/'user' names.
# 'redacted'/'forgotten' are terminal: nothing may re-title a redacted or
# forgotten thread through this path.
# ---------------------------------------------------------------------------

class TestTitleCas:
    @pytest.fixture
    def store(self, tmp_path):
        s = cs.SqliteConversationStore(":memory:")
        s.create_thread("t", "add a samba share")
        yield s
        s.close()

    def test_refined_over_provisional_lands(self, store):
        """The one ranking caller that exists today (threads.py
        ``_refined_title_fields``) refines a provisional title; it must be
        unaffected by the CAS."""
        assert store.update_thread(
            "t", title="Add samba", title_source="receipt", status="paused"
        ) is True
        t = store.get_thread("t")
        assert (t["title"], t["title_source"]) == ("Add samba", "receipt")

    def test_bare_rename_over_provisional_lands(self, store):
        """The peer wire's rename (P3a contract) carries no title_source; a
        bare title update is a refinement and must keep landing, and must
        not silently re-stamp the source column."""
        assert store.update_thread("t", title="Renamed", stale=True) is True
        t = store.get_thread("t")
        assert (t["title"], t["title_source"], t["stale"]) == ("Renamed", "provisional", 1)

    def test_user_rank_outranks_refined(self, store):
        assert store.update_thread("t", title="Add samba", title_source="receipt") is True
        assert store.update_thread("t", title="My thread", title_source="user") is True
        assert store.get_thread("t")["title"] == "My thread"
        # and the demotion back is refused
        assert store.update_thread("t", title="Add samba", title_source="receipt") is False
        t = store.get_thread("t")
        assert (t["title"], t["title_source"]) == ("My thread", "user")

    def test_cas_refusal_writes_nothing(self, store):
        """A refused title update must not land the rest of the fields
        either: one UPDATE, gated as a unit."""
        assert store.update_thread("t", title="My thread", title_source="user") is True
        assert store.update_thread(
            "t", title="clobber", title_source="receipt", status="paused", stale=True
        ) is False
        t = store.get_thread("t")
        assert (t["title"], t["title_source"], t["status"], t["stale"]) == (
            "My thread", "user", "open", 0
        )

    def test_redacted_and_forgotten_titles_are_terminal(self, store):
        for source in ("redacted", "forgotten"):
            s = cs.SqliteConversationStore(":memory:")
            s.create_thread("t", "add a samba share")
            s._conn.execute(
                "UPDATE conversations SET title_source = ? WHERE id = 't'", (source,)
            )
            s._conn.commit()
            assert s.update_thread("t", title="re-derived", title_source="receipt") is False
            assert s.get_thread("t")["title"] == "add a samba share"
            s.close()

    def test_equal_rank_restamp_is_allowed(self, store):
        """migrations.py stamps ``title_source='provisional'`` back onto a
        thread that already carries it; the CAS forbids demotions, not
        idempotent re-stamps."""
        assert store.update_thread("t", title_source="provisional", status="closed") is True
        t = store.get_thread("t")
        assert (t["title_source"], t["status"]) == ("provisional", "closed")

    def test_unknown_title_source_is_refused(self, store):
        assert store.update_thread("t", title="x", title_source="mystery") is False
        assert store.get_thread("t")["title"] == "add a samba share"