# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The inferred half of RQ-3: recurrence proposes, a person decides.

The rule is arithmetic and nothing else. No model reads a conversation and
decides what someone is into -- that write is what this entire design exists
to refuse, and it is the one Haloysius's own `update_user_knowledge` makes.

Deliberately **not** the consolidator's existing 7-day / 3-thread rule.
Three threads about samba in one evening is a job, not an interest. Distinct
days are the chat analogue of "that grey van, three times this week".

And what it writes is a candidate, which is not a belief: nothing derived
from it reaches a prompt or the observation index until a person says yes.
"""

import time

import pytest

from halbert_core.continuity.consolidation import (
    CANDIDATE_MIN_DAYS,
    CANDIDATE_MIN_THREADS,
    CANDIDATE_MIN_TURNS,
    CANDIDATE_WINDOW_DAYS,
    Consolidator,
)
from halbert_core.continuity.interests import Interest, InterestStatus, Origin

DAY = 24 * 3600
NOW = 1_780_000_000.0


def _thread(tid, *, days_ago, entities=(), domains=(), turns=4):
    return {
        "thread_id": tid,
        "updated_at": NOW - days_ago * DAY,
        "entities_json": list(entities),
        "topic_domains": list(domains),
        "turn_count": turns,
        "status": "closed",
    }


class _Threads:
    def __init__(self, threads):
        self._threads = threads

    def list_threads(self, status=None, limit=50):
        return list(self._threads)[:limit]


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setenv("HALOYSIUS_DATA_HOME", str(tmp_path))
    from haloysius.memory_v2.store import PersonaMemoryStore

    return PersonaMemoryStore("candidates")


def _run(threads, memory, now=NOW):
    return Consolidator(_Threads(threads), None, memory).propose_interests(now=now)


def _interests(memory):
    return [
        i for i in (Interest.from_persona_memory(m) for m in memory.list_memories())
        if i is not None
    ]


def _qualifying(topic="zfs"):
    """Three distinct days, three threads, all non-ephemeral."""
    return [
        _thread("t1", days_ago=1, entities=[topic]),
        _thread("t2", days_ago=5, entities=[topic]),
        _thread("t3", days_ago=9, entities=[topic]),
    ]


class TestTheBar:

    def test_recurrence_across_days_proposes_a_candidate(self, memory):
        assert _run(_qualifying(), memory) == 1
        assert [i.topic for i in _interests(memory)] == ["zfs"]

    def test_the_same_evening_is_not_an_interest(self, memory):
        # Three threads about samba in one evening is a job. This is the
        # single most important line in the rule.
        same_day = [
            _thread("t1", days_ago=1, entities=["samba"]),
            _thread("t2", days_ago=1, entities=["samba"]),
            _thread("t3", days_ago=1, entities=["samba"]),
        ]
        assert _run(same_day, memory) == 0
        assert _interests(memory) == []

    def test_too_few_days(self, memory):
        two_days = [
            _thread("t1", days_ago=1, entities=["zfs"]),
            _thread("t2", days_ago=1, entities=["zfs"]),
            _thread("t3", days_ago=4, entities=["zfs"]),
        ]
        assert _run(two_days, memory) == 0

    def test_too_few_threads(self, memory):
        # Three days but only two threads: one long-running strand of work
        # revisited, not a recurring subject.
        two_threads = [
            _thread("t1", days_ago=1, entities=["zfs"]),
            _thread("t1", days_ago=5, entities=["zfs"]),
            _thread("t2", days_ago=9, entities=["zfs"]),
        ]
        assert _run(two_threads, memory) == 0

    def test_single_turn_threads_do_not_count(self, memory):
        # Three one-line asks on three days would otherwise manufacture an
        # interest nobody has.
        ephemeral = [
            _thread(f"t{n}", days_ago=n * 3, entities=["zfs"], turns=1)
            for n in (1, 2, 3)
        ]
        assert _run(ephemeral, memory) == 0

    def test_outside_the_window_does_not_count(self, memory):
        stale = [
            _thread("t1", days_ago=1, entities=["zfs"]),
            _thread("t2", days_ago=5, entities=["zfs"]),
            _thread("t3", days_ago=CANDIDATE_WINDOW_DAYS + 3, entities=["zfs"]),
        ]
        assert _run(stale, memory) == 0

    def test_a_domain_qualifies_as_well_as_an_entity(self, memory):
        by_domain = [
            _thread(f"t{n}", days_ago=n * 3, domains=["storage"]) for n in (1, 2, 3)
        ]
        assert _run(by_domain, memory) == 1
        assert [i.topic for i in _interests(memory)] == ["storage"]

    def test_the_thresholds_are_the_constants(self):
        # If someone loosens these, the test names above stop describing
        # what the code does. Pin them where a reader will see it.
        assert (CANDIDATE_MIN_DAYS, CANDIDATE_MIN_THREADS, CANDIDATE_MIN_TURNS) == (3, 3, 2)
        assert CANDIDATE_WINDOW_DAYS == 30


class TestWhatItWrites:

    def test_it_is_a_candidate_and_not_a_belief(self, memory):
        _run(_qualifying(), memory)
        row = _interests(memory)[0]
        assert row.status is InterestStatus.CANDIDATE
        assert row.origin is Origin.INFERRED

    def test_a_candidate_is_never_mirrored(self, memory):
        # should_mirror is what keeps a guess out of the index recall reads.
        _run(_qualifying(), memory)
        assert _interests(memory)[0].should_mirror is False

    def test_a_candidate_never_reaches_a_prompt(self, memory):
        from halbert_core.continuity.recall_interest import select_interest

        class _Signals:
            entities = {"zfs"}
            detected_domains = []
            intent = "question"
            is_troubleshooting = False
            has_error_indicators = False

        _run(_qualifying(), memory)
        assert select_interest(_interests(memory), _Signals()) is None

    def test_the_reason_names_itself(self, memory):
        # MEM-06 takes a human utterance or a self-naming rule, and nothing
        # else. A sentence a model composed about why someone might like
        # something is exactly what it forbids.
        _run(_qualifying(), memory)
        assert _interests(memory)[0].reason == "appeared on 3 days in 30 across 3 threads"

    def test_the_evidence_is_the_threads_it_counted(self, memory):
        _run(_qualifying(), memory)
        evidence = _interests(memory)[0].evidence
        assert sorted(evidence["threads"]) == ["t1", "t2", "t3"]
        assert evidence["days"] == 3
        assert evidence["window_days"] == 30

    def test_it_is_not_listed_as_something_remembered(self, memory):
        # Nobody confirmed it, so presenting it as "something I remember
        # about you" would claim more than the system is entitled to.
        from halbert_core.continuity.about_you import list_remembered

        _run(_qualifying(), memory)
        assert list_remembered(memory) == []
        assert list_remembered(memory, include_forgotten=True) == []


class TestItDoesNotTalkOverThePerson:

    def _stated(self, memory, topic="zfs"):
        interest = Interest(topic=topic, origin=Origin.STATED, actor="user",
                            reason=f"remember that I work on {topic}")
        memory.smart_add(interest.to_persona_memory("candidates"))

    def test_it_does_not_propose_what_is_already_active(self, memory):
        self._stated(memory)
        assert _run(_qualifying(), memory) == 0
        assert len(_interests(memory)) == 1

    def test_it_does_not_re_propose_what_was_retracted(self, memory):
        """The one that matters. Re-proposing something a person stopped
        using walks their retraction back through the side door."""
        from halbert_core.continuity.forget_interest import stop_using_interest

        self._stated(memory)
        memory_id = memory.list_memories()[0].id
        stop_using_interest(_interests(memory)[0], memory_id,
                            turn="t1", memory_store=memory)
        assert _interests(memory)[0].status is InterestStatus.FORGET_REQUESTED

        assert _run(_qualifying(), memory) == 0
        assert _interests(memory)[0].status is InterestStatus.FORGET_REQUESTED

    def test_running_twice_proposes_once(self, memory):
        assert _run(_qualifying(), memory) == 1
        assert _run(_qualifying(), memory) == 0
        assert len(_interests(memory)) == 1


class TestItNeverRaises:

    def test_no_memory_store(self, memory, monkeypatch):
        import halbert_core.integrations.cognition_wiring as cw

        monkeypatch.setattr(cw, "get_persona_memory_store", lambda: None)
        assert Consolidator(_Threads(_qualifying()), None).propose_interests(now=NOW) == 0

    def test_a_thread_store_that_throws(self, memory):
        class _Broken:
            def list_threads(self, **kw):
                raise RuntimeError("gone")

        assert Consolidator(_Broken(), None, memory).propose_interests(now=NOW) == 0

    def test_malformed_thread_rows_are_skipped_not_fatal(self, memory):
        rows = _qualifying() + [
            {"thread_id": "bad", "updated_at": "not-a-number", "turn_count": 4},
            {"thread_id": "worse", "entities_json": None, "topic_domains": None},
        ]
        assert _run(rows, memory) == 1
