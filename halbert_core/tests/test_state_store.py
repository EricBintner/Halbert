# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's own machine-state ledger (handoff R1).

Replaces the Haloysius TemporalStateLedger per founder direction D1. Same
semantics — recording a value closes the previous one's valid_to — plus a
thread_id Haloysius could not express, because it has no idea what a thread is.
"""

import sqlite3

import pytest

from halbert_core.continuity import StateStore


@pytest.fixture
def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "state.db"))
    yield s
    s.close()


def _cur(store):
    return {(t.subject, t.predicate): t.object for t in store.current_state()}


class TestRecordAndRead:
    def test_record_then_current(self, store):
        store.record_state("service:nginx", "service_status", "running", "state_tracker")
        assert _cur(store) == {("service:nginx", "service_status"): "running"}

    def test_new_value_supersedes_the_old(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        store.record_state("service:nginx", "service_status", "stopped", "t")
        cur = store.current_state()
        assert len(cur) == 1 and cur[0].object == "stopped"
        assert cur[0].valid_to is None

    def test_history_keeps_both_with_closed_intervals(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        store.record_state("service:nginx", "service_status", "stopped", "t")
        hist = store.state_history("service:nginx", "service_status")
        assert [h.object for h in hist] == ["running", "stopped"]
        assert hist[0].valid_to is not None
        assert hist[1].valid_to is None
        assert hist[0].valid_to == pytest.approx(hist[1].valid_from)

    def test_distinct_subjects_are_independent(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        store.record_state("service:smbd", "service_status", "stopped", "t")
        store.record_state("system", "cpu_load", "42%", "t")
        assert len(store.current_state()) == 3

    def test_recording_the_same_value_is_a_noop(self, store):
        """A tracker resyncing unchanged state must not churn the history."""
        store.record_state("system", "cpu_load", "42%", "t")
        store.record_state("system", "cpu_load", "42%", "t")
        assert len(store.state_history("system", "cpu_load")) == 1

    def test_current_state_can_filter(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        store.record_state("system", "cpu_load", "42%", "t")
        assert len(store.current_state(subject="system")) == 1
        assert len(store.current_state(predicate="service_status")) == 1


class TestProvenance:
    def test_source_is_kept(self, store):
        store.record_state("disk:/dev/sda1", "disk_health", "healthy", "state_tracker:disk")
        assert store.current_state()[0].source == "state_tracker:disk"

    def test_thread_id_is_kept(self, store):
        """The gain over the Haloysius ledger: which conversation caused this."""
        store.record_state("service:smbd", "service_status", "running", "thread",
                           thread_id="t-42")
        assert store.current_state()[0].thread_id == "t-42"

    def test_confidence_defaults_to_one(self, store):
        store.record_state("system", "cpu_load", "42%", "t")
        assert store.current_state()[0].confidence == 1.0


class TestInvalidate:
    def test_invalidate_closes_the_open_triple(self, store):
        store.record_state("service:nginx", "service_status", "running", "t")
        assert store.invalidate_state("service:nginx", "service_status") == 1
        assert store.current_state() == []
        assert len(store.state_history("service:nginx", "service_status")) == 1

    def test_invalidate_unknown_is_zero(self, store):
        assert store.invalidate_state("nope", "nope") == 0


class TestAttachToAnExistingConnection:
    def test_accepts_a_caller_owned_connection(self, tmp_path):
        """So the table can fold into the Plan A thread db with no data move."""
        conn = sqlite3.connect(str(tmp_path / "threads.db"))
        conn.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY)")
        s = StateStore(conn=conn)
        s.record_state("system", "cpu_load", "42%", "t")
        assert _cur(s) == {("system", "cpu_load"): "42%"}
        # the caller's own tables are untouched and still usable
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"conversations", "state_triples"} <= names

    def test_does_not_close_a_borrowed_connection(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "threads.db"))
        s = StateStore(conn=conn)
        s.record_state("system", "cpu_load", "42%", "t")
        s.close()
        conn.execute("SELECT 1").fetchone()   # must not raise


class TestFailSoft:
    def test_a_broken_connection_never_raises(self, store, caplog):
        store.close()
        assert store.record_state("system", "cpu_load", "1%", "t") is None
        assert store.current_state() == []
