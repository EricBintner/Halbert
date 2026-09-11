# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Somebody labels the attempts (Haloysius handoff 2026-09-10 §2.2).

`update_reaction` existed and nothing called it, so no proactive attempt
had ever been labelled and Phase C's learning loop had one arm and no other.
The engine's warning is specific: a loop that sees its speaking decisions
punished and its silences never evaluated ratchets toward silence, and a
quiet assistant looks well-behaved while getting worse.

Three of the four arms are signals the product already has — a dismissal, a
snooze, and acting on a finding. The fourth, IGNORED, is a sweep rather
than an event, and it is the one that must never touch a suppressed
attempt: an attempt nobody saw cannot have been ignored, and labelling it
so would poison the very arm it looks like it fills.
"""

from datetime import datetime, timedelta, timezone

import pytest

from halbert_core.attunement.reactions import ReactionRecorder
from halbert_core.attunement.store import AttunementStore


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


def _attempt(store, attempt_id, *, finding_id="f1", gate_outcome="speak",
             ts=None, reaction=None):
    store.record_outcome_raw({
        "attempt_id": attempt_id,
        "persona_id": "halbert",
        "subject_id": "primary",
        "source": "finding",
        "severity": "warning",
        "channel_class": "push",
        "outcome": "speak",
        "reasons": [],
        "margin": 0.1,
        "context_key": finding_id,
        "gate_outcome": gate_outcome,
        "gate_reasons": [],
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "reaction": reaction,
    })


def _reaction(store, attempt_id):
    rows = store.list_outcomes_raw("halbert")
    return next(r["reaction"] for r in rows if r["attempt_id"] == attempt_id)


# --- the join ---------------------------------------------------------------

def test_the_finding_id_finds_its_attempt(store):
    _attempt(store, "a1", finding_id="f-42")

    assert store.latest_attempt_for_context("f-42", persona_id="halbert") == "a1"


def test_the_most_recent_attempt_wins(store):
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _attempt(store, "old", finding_id="f-42", ts=old)
    _attempt(store, "new", finding_id="f-42")

    assert store.latest_attempt_for_context("f-42", persona_id="halbert") == "new"


def test_an_unknown_finding_has_no_attempt(store):
    assert store.latest_attempt_for_context("nope", persona_id="halbert") is None


def test_an_empty_context_key_never_matches(store):
    """Most rows have no context key. A blank lookup must not pick one of
    them at random and label it."""
    _attempt(store, "a1", finding_id=None)

    assert store.latest_attempt_for_context("", persona_id="halbert") is None
    assert store.latest_attempt_for_context(None, persona_id="halbert") is None


# --- the arms ---------------------------------------------------------------

def test_dismissing_a_finding_labels_its_attempt(store):
    _attempt(store, "a1", finding_id="f-1")

    assert ReactionRecorder(store).on_dismissed("f-1") is True
    assert _reaction(store, "a1") == "dismissed"


def test_snoozing_a_finding_is_not_now_not_a_dismissal(store):
    """"Not now" and "no" are different evidence, and a loop that merges
    them learns the wrong thing from a postponement."""
    _attempt(store, "a1", finding_id="f-1")

    assert ReactionRecorder(store).on_snoozed("f-1") is True
    assert _reaction(store, "a1") == "not_now"


def test_acting_on_a_finding_is_the_positive_arm(store):
    _attempt(store, "a1", finding_id="f-1")

    assert ReactionRecorder(store).on_engaged("f-1") is True
    assert _reaction(store, "a1") == "engaged"


def test_a_finding_nobody_was_told_about_labels_nothing(store):
    """No attempt, no reaction — and no row invented to hold one."""
    assert ReactionRecorder(store).on_dismissed("never-pushed") is False
    assert store.list_outcomes_raw("halbert") == []


def test_a_broken_store_never_reaches_the_caller(store):
    class Exploding:
        def latest_attempt_for_context(self, *a, **kw):
            raise RuntimeError("disk gone")

    assert ReactionRecorder(Exploding()).on_dismissed("f-1") is False


# --- the sweep --------------------------------------------------------------

def test_an_unanswered_attempt_becomes_ignored(store):
    stale = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    _attempt(store, "a1", ts=stale)

    assert ReactionRecorder(store).sweep_ignored(after_s=3600) == 1
    assert _reaction(store, "a1") == "ignored"


def test_a_recent_attempt_is_still_open(store):
    _attempt(store, "a1")

    assert ReactionRecorder(store).sweep_ignored(after_s=3600) == 0
    assert _reaction(store, "a1") is None


def test_a_suppressed_attempt_is_never_called_ignored(store):
    """Nobody saw it. Calling that "ignored" manufactures a negative
    label out of the product's own silence — which is exactly the arm
    Phase C cannot learn from."""
    stale = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    _attempt(store, "a1", ts=stale, gate_outcome="silent")

    assert ReactionRecorder(store).sweep_ignored(after_s=3600) == 0
    assert _reaction(store, "a1") is None


def test_an_already_labelled_attempt_is_left_alone(store):
    stale = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    _attempt(store, "a1", ts=stale, reaction="engaged")

    assert ReactionRecorder(store).sweep_ignored(after_s=3600) == 0
    assert _reaction(store, "a1") == "engaged"


# --- the arms must not reach an attempt nobody received ---------------------

def test_dismissing_a_finding_whose_push_was_suppressed_labels_nothing(store):
    """The routine path, not an edge case: the dial is quiet, the push is
    suppressed, the finding is still written and still listed, the person
    meets it on the Findings page and dismisses it there.

    Labelling that row pairs a real "no" with an outcome the person never
    saw — and with a shadow attached that outcome is often the engine's
    `speak`, so the row reads "the engine would have spoken and they said
    no". That is the ratchet this module's docstring quotes the engine
    warning about, arriving through the arm it claims to protect.
    """
    _attempt(store, "a1", finding_id="f-1", gate_outcome="silent")

    assert ReactionRecorder(store).on_dismissed("f-1") is False
    assert _reaction(store, "a1") is None


def test_snoozing_and_engaging_are_held_to_the_same_rule(store):
    _attempt(store, "a1", finding_id="f-1", gate_outcome="silent")
    recorder = ReactionRecorder(store)

    assert recorder.on_snoozed("f-1") is False
    assert recorder.on_engaged("f-1") is False
    assert _reaction(store, "a1") is None


def test_a_spoken_attempt_is_still_found_past_a_suppressed_one(store):
    """The suppressed row is newer. The join must skip it rather than stop
    at it, or a real reaction is lost every time a dial change straddles
    one finding."""
    older = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    _attempt(store, "spoke", finding_id="f-1", ts=older)
    _attempt(store, "held", finding_id="f-1", gate_outcome="silent")

    assert ReactionRecorder(store).on_dismissed("f-1") is True
    assert _reaction(store, "spoke") == "dismissed"
    assert _reaction(store, "held") is None


def test_the_sweep_filters_before_the_limit_not_after(store):
    """Suppressed rows are never labelled, so they stay unanswered forever.
    Filtered in Python after SQLite applied the LIMIT, enough of them at the
    head of a newest-first window hide every spoken row behind them."""
    stale = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    older = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    for i in range(5):
        _attempt(store, f"held-{i}", finding_id=f"f-{i}",
                 gate_outcome="silent", ts=stale)
    _attempt(store, "spoke", finding_id="f-x", ts=older)

    rows = store.unanswered_attempts("halbert", before_ts=stale, limit=3)

    assert [r["attempt_id"] for r in rows] == ["spoke"]


# --- the counter the margin is measured against ----------------------------

def test_engaging_advances_the_counter_the_policy_reads(store):
    """`record_reaction` is not a wrapper around `update_reaction`: it also
    calls `note_accepted`. While that counter is below the engine's
    quiet-period threshold every decision carries a fixed extra cost, so a
    wiring that writes the reaction and never advances the counter pins
    that cost on forever and depresses every margin it records."""
    pytest.importorskip("haloysius.attunement.ledger")
    from haloysius.attunement.ledger import StandingRequestLedger

    from halbert_core.attunement.context import halbert_config

    _attempt(store, "a1", finding_id="f-1")
    ledger = StandingRequestLedger(store, "halbert", halbert_config())
    assert ledger.state("primary").accepted_interactions == 0

    ReactionRecorder(store).on_engaged("f-1")

    assert ledger.state("primary").accepted_interactions == 1


def test_a_negative_reaction_does_not_advance_it(store):
    pytest.importorskip("haloysius.attunement.ledger")
    from haloysius.attunement.ledger import StandingRequestLedger

    from halbert_core.attunement.context import halbert_config

    _attempt(store, "a1", finding_id="f-1")
    ReactionRecorder(store).on_dismissed("f-1")

    ledger = StandingRequestLedger(store, "halbert", halbert_config())
    assert ledger.state("primary").accepted_interactions == 0
