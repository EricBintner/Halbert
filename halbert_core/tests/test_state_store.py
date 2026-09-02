# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's own machine-state ledger (handoff R1, provenance per LEDGER-1).

Replaces the Haloysius TemporalStateLedger per founder direction D1. Same
semantics — recording a value closes the previous one's valid_to — plus a
thread_id Haloysius could not express, because it has no idea what a thread is,
and the provenance columns that make "I remember why" answerable.
"""

import sqlite3

import pytest

from halbert_core.continuity import StateStore
from halbert_core.continuity.state_store import (
    ACTOR_AGENT,
    ACTOR_SYSTEM,
    ACTOR_USER,
    UNRECORDED,
)


@pytest.fixture
def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "state.db"))
    yield s
    s.close()


def _rec(store, subject, predicate, obj, source="t", **kw):
    """Record with provenance defaulted, for tests that are about something else.

    Production call sites cannot do this — ``reason`` and ``actor`` are
    keyword-only with no default. See TestReasonIsMandatory.
    """
    kw.setdefault("reason", "test: fixture write")
    kw.setdefault("actor", ACTOR_SYSTEM)
    return store.record_state(subject, predicate, obj, source, **kw)


def _cur(store):
    return {(t.subject, t.predicate): t.object for t in store.current_state()}


class TestRecordAndRead:
    def test_record_then_current(self, store):
        _rec(store, "service:nginx", "service_status", "running", "state_tracker")
        assert _cur(store) == {("service:nginx", "service_status"): "running"}

    def test_new_value_supersedes_the_old(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        _rec(store, "service:nginx", "service_status", "stopped")
        cur = store.current_state()
        assert len(cur) == 1 and cur[0].object == "stopped"
        assert cur[0].valid_to is None

    def test_history_keeps_both_with_closed_intervals(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        _rec(store, "service:nginx", "service_status", "stopped")
        hist = store.state_history("service:nginx", "service_status")
        assert [h.object for h in hist] == ["running", "stopped"]
        assert hist[0].valid_to is not None
        assert hist[1].valid_to is None
        assert hist[0].valid_to == pytest.approx(hist[1].valid_from)

    def test_distinct_subjects_are_independent(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        _rec(store, "service:smbd", "service_status", "stopped")
        _rec(store, "system", "cpu_load", "42%")
        assert len(store.current_state()) == 3

    def test_recording_the_same_value_is_a_noop(self, store):
        """A tracker resyncing unchanged state must not churn the history."""
        _rec(store, "system", "cpu_load", "42%")
        _rec(store, "system", "cpu_load", "42%")
        assert len(store.state_history("system", "cpu_load")) == 1

    def test_a_noop_does_not_overwrite_the_original_reason(self, store):
        """Nothing changed, so the first write's reason still explains the value."""
        _rec(store, "system", "cpu_load", "42%", reason="tracker: first sample")
        _rec(store, "system", "cpu_load", "42%", reason="tracker: later sample")
        assert store.current_state()[0].reason == "tracker: first sample"

    def test_current_state_can_filter(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        _rec(store, "system", "cpu_load", "42%")
        assert len(store.current_state(subject="system")) == 1
        assert len(store.current_state(predicate="service_status")) == 1


class TestReasonIsMandatory:
    """The column exists to be trustworthy; a default would make it optional.

    A reason exists exactly once, at the write. These tests are the guard that
    stops a future call site omitting it and a later pass inventing one.
    """

    def test_omitting_reason_is_a_type_error(self, store):
        with pytest.raises(TypeError):
            store.record_state("system", "cpu_load", "42%", "t", actor=ACTOR_SYSTEM)

    def test_omitting_actor_is_a_type_error(self, store):
        with pytest.raises(TypeError):
            store.record_state("system", "cpu_load", "42%", "t", reason="because")

    def test_reason_and_actor_are_keyword_only(self, store):
        """They cannot be passed positionally, so they cannot be swapped."""
        with pytest.raises(TypeError):
            store.record_state("system", "cpu_load", "42%", "t", "because", "user")

    @pytest.mark.parametrize("bad", ["", "   ", None, 7])
    def test_an_empty_reason_is_refused(self, store, bad):
        with pytest.raises(ValueError):
            store.record_state("system", "cpu_load", "42%", "t",
                               reason=bad, actor=ACTOR_SYSTEM)

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_an_empty_actor_is_refused(self, store, bad):
        with pytest.raises(ValueError):
            store.record_state("system", "cpu_load", "42%", "t",
                               reason="because", actor=bad)

    def test_the_unrecorded_sentinel_is_accepted(self, store):
        """A blank we admit to is legitimate; a fabrication is not."""
        _rec(store, "system", "cpu_load", "42%", reason=UNRECORDED)
        assert store.current_state()[0].reason == UNRECORDED

    def test_invalidate_also_requires_a_reason(self, store):
        """Closing a fact is a change, so it is explained too."""
        _rec(store, "service:nginx", "service_status", "running")
        with pytest.raises(TypeError):
            store.invalidate_state("service:nginx", "service_status")

    def test_provenance_is_stripped(self, store):
        _rec(store, "system", "cpu_load", "42%", reason="  spaced  ", actor=" user ")
        t = store.current_state()[0]
        assert t.reason == "spaced" and t.actor == "user"


class TestProvenance:
    def test_source_is_kept(self, store):
        _rec(store, "disk:/dev/sda1", "disk_health", "healthy", "state_tracker:disk")
        assert store.current_state()[0].source == "state_tracker:disk"

    def test_thread_id_is_kept(self, store):
        """The gain over the Haloysius ledger: which conversation caused this."""
        _rec(store, "service:smbd", "service_status", "running", "thread",
             thread_id="t-42")
        assert store.current_state()[0].thread_id == "t-42"

    def test_confidence_defaults_to_one(self, store):
        _rec(store, "system", "cpu_load", "42%")
        assert store.current_state()[0].confidence == 1.0

    def test_reason_and_actor_round_trip(self, store):
        _rec(store, "config:/etc/nginx.conf", "worker_processes", "4",
             "editor_save", reason="user asked for more workers", actor=ACTOR_USER)
        t = store.current_state()[0]
        assert t.reason == "user asked for more workers"
        assert t.actor == ACTOR_USER

    def test_to_dict_carries_provenance(self, store):
        _rec(store, "system", "cpu_load", "42%", reason="why", actor=ACTOR_AGENT,
             request_id="req-1")
        d = store.current_state()[0].to_dict()
        assert d["reason"] == "why"
        assert d["actor"] == ACTOR_AGENT
        assert d["request_id"] == "req-1"

    def test_supersession_explains_the_close(self, store):
        """The predecessor closed because of this write, so it says so."""
        _rec(store, "service:nginx", "service_status", "running",
             reason="tracker: first sweep")
        _rec(store, "service:nginx", "service_status", "stopped",
             reason="user stopped it during maintenance", actor=ACTOR_USER)
        old = store.state_history("service:nginx", "service_status")[0]
        assert old.closed_reason == "superseded: user stopped it during maintenance"
        assert old.closed_by == ACTOR_USER

    def test_invalidate_records_why_it_closed(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        store.invalidate_state("service:nginx", "service_status",
                               reason="service was removed", actor=ACTOR_USER)
        closed = store.state_history("service:nginx", "service_status")[0]
        assert closed.closed_reason == "service was removed"
        assert closed.closed_by == ACTOR_USER


class TestWhy:
    """LEDGER-1's definition of done: what is true, since when, who, and why."""

    def test_why_returns_current_and_what_it_replaced(self, store):
        _rec(store, "config:/etc/ssh/sshd_config", "PermitRootLogin", "yes",
             reason="shipped default", actor=ACTOR_SYSTEM)
        _rec(store, "config:/etc/ssh/sshd_config", "PermitRootLogin", "no",
             reason="hardening pass after the audit finding", actor=ACTOR_AGENT)

        w = store.why("config:/etc/ssh/sshd_config", "PermitRootLogin")
        assert w.found
        assert w.current.object == "no"
        assert w.current.reason == "hardening pass after the audit finding"
        assert w.current.actor == ACTOR_AGENT
        assert w.superseded.object == "yes"          # the before value, free
        assert w.superseded.valid_to is not None

    def test_why_with_no_history_has_no_predecessor(self, store):
        _rec(store, "system", "cpu_load", "42%")
        w = store.why("system", "cpu_load")
        assert w.found and w.current is not None and w.superseded is None

    def test_why_abstains_on_an_unknown_key(self, store):
        """The ledger resolves or says nothing. It never guesses."""
        w = store.why("nope", "nope")
        assert not w.found
        assert w.current is None and w.superseded is None

    def test_why_after_invalidate_keeps_the_last_value(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        store.invalidate_state("service:nginx", "service_status",
                               reason="host decommissioned", actor=ACTOR_USER)
        w = store.why("service:nginx", "service_status")
        assert w.current is None
        assert w.superseded.object == "running"
        assert w.superseded.closed_reason == "host decommissioned"

    def test_why_to_dict_is_json_shaped(self, store):
        _rec(store, "system", "cpu_load", "42%")
        d = store.why("system", "cpu_load").to_dict()
        assert d["subject"] == "system" and d["predicate"] == "cpu_load"
        assert d["current"]["object"] == "42%"
        assert d["superseded"] is None


class TestRequestJoin:
    """request_id is the join key to the audit log — never an event seq."""

    def test_by_request_returns_every_triple_for_one_request(self, store):
        _rec(store, "config:/etc/a.conf", "x", "1", request_id="req-1")
        _rec(store, "config:/etc/b.conf", "y", "2", request_id="req-1")
        _rec(store, "config:/etc/c.conf", "z", "3", request_id="req-2")
        assert len(store.by_request("req-1")) == 2
        assert len(store.by_request("req-2")) == 1

    def test_by_request_unknown_is_empty(self, store):
        assert store.by_request("nope") == []

    def test_request_id_is_optional(self, store):
        _rec(store, "system", "cpu_load", "42%")
        assert store.current_state()[0].request_id is None


class TestPreProvenanceDatabase:
    """No users, so nothing migrates — and nothing is deleted either."""

    def _legacy_db(self, path):
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE state_triples ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL,"
            " predicate TEXT NOT NULL, object TEXT NOT NULL, source TEXT NOT NULL,"
            " confidence REAL NOT NULL DEFAULT 1.0, valid_from REAL NOT NULL,"
            " valid_to REAL, thread_id TEXT)"
        )
        conn.execute(
            "INSERT INTO state_triples"
            " (subject, predicate, object, source, confidence, valid_from)"
            " VALUES ('system', 'cpu_load', '99%', 'old', 1.0, 1.0)"
        )
        conn.commit()
        conn.close()

    def test_an_old_database_still_opens_and_writes(self, tmp_path):
        db = tmp_path / "old.db"
        self._legacy_db(db)
        s = StateStore(db_path=str(db))
        assert _rec(s, "system", "cpu_load", "42%") is not None
        assert _cur(s) == {("system", "cpu_load"): "42%"}
        s.close()

    def test_old_rows_are_set_aside_not_read(self, tmp_path):
        db = tmp_path / "old.db"
        self._legacy_db(db)
        s = StateStore(db_path=str(db))
        # the pre-provenance value must not surface as current state
        assert "99%" not in {t.object for t in s.current_state()}
        s.close()

    def test_old_rows_are_not_deleted(self, tmp_path):
        """They cannot answer *why*, but they are still real history."""
        db = tmp_path / "old.db"
        self._legacy_db(db)
        StateStore(db_path=str(db)).close()
        conn = sqlite3.connect(str(db))
        kept = conn.execute(
            "SELECT object FROM state_triples_pre_provenance").fetchall()
        assert [r[0] for r in kept] == ["99%"]
        conn.close()

    def test_reopening_a_current_database_is_a_noop(self, tmp_path):
        db = tmp_path / "new.db"
        s = StateStore(db_path=str(db))
        _rec(s, "system", "cpu_load", "42%")
        s.close()
        s2 = StateStore(db_path=str(db))
        assert _cur(s2) == {("system", "cpu_load"): "42%"}
        names = {r[0] for r in s2._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "state_triples_pre_provenance" not in names
        s2.close()


class TestInvalidate:
    def test_invalidate_closes_the_open_triple(self, store):
        _rec(store, "service:nginx", "service_status", "running")
        assert store.invalidate_state("service:nginx", "service_status",
                                      reason="stopped by hand",
                                      actor=ACTOR_USER) == 1
        assert store.current_state() == []
        assert len(store.state_history("service:nginx", "service_status")) == 1

    def test_invalidate_unknown_is_zero(self, store):
        assert store.invalidate_state("nope", "nope", reason="none",
                                      actor=ACTOR_SYSTEM) == 0


class TestAttachToAnExistingConnection:
    def test_accepts_a_caller_owned_connection(self, tmp_path):
        """So the table can fold into the Plan A thread db with no data move."""
        conn = sqlite3.connect(str(tmp_path / "threads.db"))
        conn.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
        s = StateStore(conn=conn)
        _rec(s, "system", "cpu_load", "42%")
        assert _cur(s) == {("system", "cpu_load"): "42%"}
        # the caller's own tables are untouched and still usable
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"conversations", "state_triples"} <= names

    def test_does_not_close_a_borrowed_connection(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "threads.db"))
        s = StateStore(conn=conn)
        _rec(s, "system", "cpu_load", "42%")
        s.close()
        conn.execute("SELECT 1").fetchone()   # must not raise


class TestFailSoft:
    def test_a_broken_connection_never_raises(self, store, caplog):
        store.close()
        assert _rec(store, "system", "cpu_load", "1%") is None
        assert store.current_state() == []

    def test_a_broken_connection_never_raises_from_why(self, store):
        store.close()
        w = store.why("system", "cpu_load")
        assert not w.found

    def test_a_missing_reason_still_raises_on_a_broken_store(self, store):
        """Fail-soft covers the database, not the caller's contract."""
        store.close()
        with pytest.raises(TypeError):
            store.record_state("system", "cpu_load", "1%", "t")


class TestAdditiveMigration:
    """A column added to _SCHEMA alone never appears on an existing database.

    Every CREATE in _SCHEMA is IF NOT EXISTS, so on a real ledger the
    statement is a no-op, _row() then raises on the missing key, and each
    read method's fail-soft except turns that into an empty list. The ledger
    would read blank with nothing raising anywhere. These tests build a
    database from the PREVIOUS schema on purpose -- a tmp-dir database
    created by the current code gets the column for free and proves nothing.
    """

    #: The schema as it shipped before closed_by_request.
    _PREVIOUS = (
        "CREATE TABLE state_triples ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL,"
        " predicate TEXT NOT NULL, object TEXT NOT NULL, source TEXT NOT NULL,"
        " confidence REAL NOT NULL DEFAULT 1.0, valid_from REAL NOT NULL,"
        " valid_to REAL, thread_id TEXT, reason TEXT NOT NULL,"
        " actor TEXT NOT NULL, request_id TEXT, closed_reason TEXT,"
        " closed_by TEXT)"
    )

    def _previous_schema_db(self, path):
        conn = sqlite3.connect(str(path))
        conn.execute(self._PREVIOUS)
        conn.execute(
            "INSERT INTO state_triples"
            " (subject, predicate, object, source, confidence, valid_from,"
            "  reason, actor)"
            " VALUES ('system', 'cpu_load', '42%', 'tracker', 1.0, 1.0,"
            "         'a real reason', 'user')"
        )
        conn.commit()
        conn.close()

    def test_an_existing_ledger_still_reads_after_the_upgrade(self, tmp_path):
        """The failure this guards is silent: blank reads, no exception."""
        db = tmp_path / "live.db"
        self._previous_schema_db(db)

        s = StateStore(db_path=str(db))
        rows = s.current_state()
        assert len(rows) == 1, "the ledger read blank after adding a column"
        assert rows[0].object == "42%"
        assert rows[0].reason == "a real reason"
        assert rows[0].closed_by_request is None
        s.close()

    def test_the_column_is_actually_added(self, tmp_path):
        db = tmp_path / "live.db"
        self._previous_schema_db(db)
        StateStore(db_path=str(db)).close()

        conn = sqlite3.connect(str(db))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(state_triples)")}
        assert "closed_by_request" in cols
        conn.close()

    def test_the_existing_table_is_not_set_aside(self, tmp_path):
        """A later column must not trip the pre-provenance guard.

        Putting it in _PROVENANCE_COLUMNS would rename the live table away
        and orphan every row -- a worse outcome dressed as the fix.
        """
        db = tmp_path / "live.db"
        self._previous_schema_db(db)
        s = StateStore(db_path=str(db))
        names = {r[0] for r in s._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "state_triples_pre_provenance" not in names
        s.close()

    def test_reopening_is_idempotent(self, tmp_path):
        db = tmp_path / "live.db"
        self._previous_schema_db(db)
        StateStore(db_path=str(db)).close()
        s = StateStore(db_path=str(db))
        assert len(s.current_state()) == 1
        s.close()


class TestRedactRequest:
    """The ledger's half of "forget that": remove the words, keep the facts."""

    def test_it_clears_the_reason_on_rows_the_request_wrote(self, store):
        _rec(store, "file:/etc/a.conf", "content_sha256", "aaa",
             reason="a private explanation", actor=ACTOR_USER, request_id="req-1")
        assert store.redact_request("req-1", actor=ACTOR_USER) == 1
        assert store.current_state()[0].reason == UNRECORDED

    def test_it_also_clears_the_copy_on_the_row_it_closed(self, store):
        """The leak: a predecessor holds the reason under a DIFFERENT request_id.

        by_request() would never return that row, so a request-keyed
        redaction that only looked there would leave the words standing.
        """
        _rec(store, "file:/etc/a.conf", "content_sha256", "aaa",
             reason="first", actor=ACTOR_USER, request_id="req-1")
        _rec(store, "file:/etc/a.conf", "content_sha256", "bbb",
             reason="a private explanation", actor=ACTOR_USER, request_id="req-2")

        old = store.state_history("file:/etc/a.conf", "content_sha256")[0]
        assert old.closed_reason == "superseded: a private explanation"
        assert old.request_id == "req-1" and old.closed_by_request == "req-2"

        store.redact_request("req-2", actor=ACTOR_USER)
        old = store.state_history("file:/etc/a.conf", "content_sha256")[0]
        assert "private" not in (old.closed_reason or "")
        assert old.closed_reason == UNRECORDED

    def test_the_facts_and_their_timeline_survive(self, store):
        """What was true and when is not the thing being forgotten."""
        _rec(store, "file:/etc/a.conf", "content_sha256", "aaa",
             reason="first", actor=ACTOR_USER, request_id="req-1")
        _rec(store, "file:/etc/a.conf", "content_sha256", "bbb",
             reason="second", actor=ACTOR_USER, request_id="req-2")
        store.redact_request("req-2", actor=ACTOR_USER)

        hist = store.state_history("file:/etc/a.conf", "content_sha256")
        assert [h.object for h in hist] == ["aaa", "bbb"]
        assert hist[0].valid_to is not None and hist[1].valid_to is None

    def test_a_second_call_is_a_no_op_not_a_failure(self, store):
        _rec(store, "system", "cpu_load", "42%", reason="why", request_id="req-1")
        assert store.redact_request("req-1", actor=ACTOR_USER) == 1
        assert store.redact_request("req-1", actor=ACTOR_USER) == 0

    def test_an_unknown_request_is_zero(self, store):
        assert store.redact_request("nope", actor=ACTOR_USER) == 0

    def test_other_requests_are_untouched(self, store):
        _rec(store, "file:/etc/a.conf", "content_sha256", "aaa",
             reason="keep me", actor=ACTOR_USER, request_id="req-1")
        _rec(store, "file:/etc/b.conf", "content_sha256", "bbb",
             reason="forget me", actor=ACTOR_USER, request_id="req-2")
        store.redact_request("req-2", actor=ACTOR_USER)

        kept = store.current_state(subject="file:/etc/a.conf")[0]
        assert kept.reason == "keep me"

    def test_it_requires_an_actor(self, store):
        with pytest.raises(TypeError):
            store.redact_request("req-1")
