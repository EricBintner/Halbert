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
