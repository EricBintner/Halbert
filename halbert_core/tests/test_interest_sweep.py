# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""MEM-04: two clocks, and the asymmetry between them.

An inferred interest was a guess; when the evidence stops, the guess stops.
A stated interest was a person's own words, and nothing about the passage of
time makes those less true. A machine that quietly forgot what it was told
would be worse than one that never listened.

The tests that matter most here are the negative ones: a stated interest
left untouched for years, and a lapse that stays reversible.
"""

import time

import pytest

from halbert_core.continuity.interest_sweep import (
    CANDIDATE_EXPIRY_DAYS,
    INFERRED_LAPSE_DAYS,
    sweep_interests,
)
from halbert_core.continuity.interests import Interest, InterestStatus, Origin

DAY = 24 * 3600
NOW = 1_780_000_000.0


def _at(days_ago):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(NOW - days_ago * DAY, tz=timezone.utc).isoformat()


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.observation_store import ObservationStore
    from haloysius.memory_v2.store import PersonaMemoryStore

    return PersonaMemoryStore("sweep"), ObservationStore("sweep")


def _add(memory, interest):
    _op, _r, memory_id = memory.smart_add(interest.to_persona_memory("sweep"))
    return memory_id


def _status(memory, memory_id):
    return Interest.from_persona_memory(memory.get(memory_id)).status


def _stated(topic="vintage thinkpads", days_ago=400):
    return Interest(
        topic=topic, origin=Origin.STATED, actor="user",
        reason=f"remember that I collect {topic}",
        first_seen_at=_at(days_ago), last_evidenced_at=_at(days_ago),
    )


def _confirmed(topic="zfs", days_ago=100):
    return Interest(
        topic=topic, origin=Origin.INFERRED_CONFIRMED, actor="user",
        reason="appeared on 4 days in 30 across 5 threads",
        first_seen_at=_at(days_ago + 30), last_evidenced_at=_at(days_ago),
        last_confirmed_at=_at(days_ago),
    )


def _candidate(topic="samba", days_ago=40):
    return Interest(
        topic=topic, origin=Origin.INFERRED, status=InterestStatus.CANDIDATE,
        reason="appeared on 3 days in 30 across 3 threads",
        first_seen_at=_at(days_ago), last_evidenced_at=_at(days_ago),
    )


class TestAStatedInterestNeverLapses:
    """The one a timer must never reach."""

    def test_not_after_four_hundred_days(self, stores):
        memory, obs = stores
        mid = _add(memory, _stated(days_ago=400))
        report = sweep_interests(memory, obs, now=NOW)
        assert report["lapsed"] == 0
        assert _status(memory, mid) is InterestStatus.ACTIVE

    def test_not_after_ten_years(self, stores):
        memory, obs = stores
        mid = _add(memory, _stated(days_ago=3650))
        sweep_interests(memory, obs, now=NOW)
        assert _status(memory, mid) is InterestStatus.ACTIVE

    def test_even_with_no_evidence_dates_at_all(self, stores):
        memory, obs = stores
        interest = Interest(topic="sailing", origin=Origin.STATED, actor="user",
                            reason="remember that I sail")
        mid = _add(memory, interest)
        sweep_interests(memory, obs, now=NOW + 10 * 365 * DAY)
        assert _status(memory, mid) is InterestStatus.ACTIVE


class TestAnInferredInterestLapses:

    def test_after_ninety_days_without_evidence(self, stores):
        memory, obs = stores
        mid = _add(memory, _confirmed(days_ago=INFERRED_LAPSE_DAYS + 1))
        report = sweep_interests(memory, obs, now=NOW)
        assert report["lapsed"] == 1
        assert _status(memory, mid) is InterestStatus.LAPSED

    def test_not_a_day_before(self, stores):
        memory, obs = stores
        mid = _add(memory, _confirmed(days_ago=INFERRED_LAPSE_DAYS - 1))
        assert sweep_interests(memory, obs, now=NOW)["lapsed"] == 0
        assert _status(memory, mid) is InterestStatus.ACTIVE

    def test_recent_evidence_keeps_it_alive(self, stores):
        # last_evidenced_at is newer than first_seen_at: the interest is old
        # but the evidence is not, which is the case the rule is about.
        memory, obs = stores
        interest = _confirmed(days_ago=2)
        interest.first_seen_at = _at(900)
        mid = _add(memory, interest)
        assert sweep_interests(memory, obs, now=NOW)["lapsed"] == 0
        assert _status(memory, mid) is InterestStatus.ACTIVE

    def test_it_stops_colouring_turns(self, stores):
        from halbert_core.continuity.recall_interest import select_interest

        class _Signals:
            entities = {"zfs"}
            detected_domains = []
            intent = "question"
            is_troubleshooting = False
            has_error_indicators = False

        memory, obs = stores
        _add(memory, _confirmed(days_ago=INFERRED_LAPSE_DAYS + 1))
        rows = [Interest.from_persona_memory(m) for m in memory.list_memories()]
        assert select_interest(rows, _Signals()) is not None
        sweep_interests(memory, obs, now=NOW)
        rows = [Interest.from_persona_memory(m) for m in memory.list_memories()]
        assert select_interest(rows, _Signals()) is None


class TestACandidateExpires:

    def test_after_thirty_days_unanswered(self, stores):
        memory, obs = stores
        mid = _add(memory, _candidate(days_ago=CANDIDATE_EXPIRY_DAYS + 1))
        report = sweep_interests(memory, obs, now=NOW)
        assert report["expired"] == 1
        assert _status(memory, mid) is InterestStatus.LAPSED

    def test_not_before(self, stores):
        memory, obs = stores
        mid = _add(memory, _candidate(days_ago=CANDIDATE_EXPIRY_DAYS - 1))
        assert sweep_interests(memory, obs, now=NOW)["expired"] == 0
        assert _status(memory, mid) is InterestStatus.CANDIDATE

    def test_a_candidate_expires_sooner_than_a_confirmed_one_lapses(self, stores):
        """An unanswered question ages faster than an agreed fact."""
        memory, obs = stores
        cand = _add(memory, _candidate(days_ago=45))
        conf = _add(memory, _confirmed(days_ago=45))
        sweep_interests(memory, obs, now=NOW)
        assert _status(memory, cand) is InterestStatus.LAPSED
        assert _status(memory, conf) is InterestStatus.ACTIVE


class TestNothingIsErased:

    def test_a_lapse_is_reversible(self, stores):
        """The machine losing interest must not be less reversible than the
        person asking it to stop."""
        from halbert_core.continuity.forget_interest import resume_interest

        memory, obs = stores
        mid = _add(memory, _confirmed(days_ago=200))
        sweep_interests(memory, obs, now=NOW)
        assert _status(memory, mid) is InterestStatus.LAPSED

        row = Interest.from_persona_memory(memory.get(mid))
        assert resume_interest(row, mid, memory_store=memory)["complete"] is True
        assert _status(memory, mid) is InterestStatus.ACTIVE

    def test_the_row_is_still_there(self, stores):
        memory, obs = stores
        _add(memory, _confirmed(days_ago=200))
        sweep_interests(memory, obs, now=NOW)
        assert len(memory.list_memories(include_deleted=True)) == 1

    def test_it_shows_under_show_forgotten(self, stores):
        from halbert_core.continuity.about_you import list_remembered

        memory, obs = stores
        _add(memory, _confirmed(days_ago=200))
        sweep_interests(memory, obs, now=NOW)
        assert list_remembered(memory) == []
        shown = list_remembered(memory, include_forgotten=True)
        assert [r["topic"] for r in shown] == ["zfs"]

    def test_the_mirror_says_a_machine_did_it(self, stores):
        """`lapsed:` is a different claim from `forgotten_by_user:`, and the
        audit trail has to tell them apart."""
        memory, obs = stores
        interest = _confirmed(days_ago=200)
        mid = _add(memory, interest)
        obs.save(category="preference", content=interest.content,
                 source_memory_id=mid)
        sweep_interests(memory, obs, now=NOW)
        rows = obs.search("zfs", limit=5, include_stale=True)
        assert rows and rows[0].is_stale
        assert rows[0].stale_reason.startswith("lapsed:")


class TestItNeverRaises:

    def test_no_stores_at_all(self, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw

        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: None)
        assert sweep_interests()["errors"]

    def test_an_unreadable_date_is_not_treated_as_very_old(self, stores):
        # A parse failure must not sweep a row on the strength of the failure.
        memory, obs = stores
        interest = _confirmed(days_ago=200)
        interest.first_seen_at = "not-a-date"
        interest.last_evidenced_at = "also-not"
        interest.last_confirmed_at = ""
        mid = _add(memory, interest)
        assert sweep_interests(memory, obs, now=NOW)["lapsed"] == 0
        assert _status(memory, mid) is InterestStatus.ACTIVE

    def test_a_mirror_that_throws_still_retires_the_record(self, stores):
        class _Broken:
            def mark_stale_by_memory(self, *a, **kw):
                raise RuntimeError("gone")

        memory, _obs = stores
        mid = _add(memory, _confirmed(days_ago=200))
        report = sweep_interests(memory, _Broken(), now=NOW)
        assert report["lapsed"] == 1
        assert report["errors"]
        assert _status(memory, mid) is InterestStatus.LAPSED
