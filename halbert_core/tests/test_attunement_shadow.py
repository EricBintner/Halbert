# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The suppression log (A-HB-25, plan O1) and shadow mode (plan §4.6).

`why now` has a shadow the product cannot currently answer: *why did I not
hear about this?* Eleven mechanisms can eat a proactive event, all of them
silent by construction, and a warning lost to an interaction of two is
indistinguishable from a warning never generated.

This lands before the engine does, recording the legacy gate's own decisions
with stable reason keys. When `decide()` arrives, the same rows gain the
engine's opinion alongside — which is shadow mode.
"""

import pytest

from halbert_core.attunement.shadow import (
    SuppressionRecorder,
    reason_key_for,
)
from halbert_core.attunement.store import AttunementStore
from halbert_core.proactive.events import ProactiveEvent


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


def _event(**kw):
    kw.setdefault("type", "finding")
    kw.setdefault("severity", "warning")
    kw.setdefault("title", "Disk nearly full")
    kw.setdefault("body", "…")
    return ProactiveEvent.create(**kw)


@pytest.mark.parametrize(
    "prose,expected",
    [
        ("proactivity dial is 'quiet' (requires severity >= 2)", "dial:quiet"),
        ("proactivity dial is 'off' (requires severity >= 99)", "dial:off"),
        ("quiet hours active (non-critical suppressed)", "quiet_hours"),
        ("safe mode active (non-critical suppressed)", "incident:safe_mode"),
        ("finding snoozed until 2026-09-09T00:00:00+00:00",
         "standing:defer_topic:snoozed"),
        ("finding dismissed: not relevant", "standing:defer_topic:dismissed"),
    ],
)
def test_legacy_reasons_map_to_stable_keys(prose, expected):
    """Reasons reach the user as *why not*. Prose cannot be localised,
    grouped or counted; keys can."""
    assert reason_key_for(prose) == expected


def test_the_guest_reason_has_a_key_rather_than_a_name_bearing_slug():
    """The prose carries the guest's chosen name. Without a pattern it fell
    through to `unmapped:<slug>` and put that name in a durable row that is
    meant to hold "enums, ids, numbers and timestamps only — never text"."""
    key = reason_key_for(
        "a guest persona is fronting (Aurelius) — "
        "Halbert does not interrupt in someone else's voice"
    )

    assert key == "guest:fronting"
    assert "aurelius" not in key.lower()


def test_an_unrecognised_reason_is_keyed_not_dropped():
    key = reason_key_for("something new nobody mapped")
    assert key.startswith("unmapped:")


def test_empty_reason_on_an_allowed_event_is_no_key():
    assert reason_key_for("") == ""


def test_a_suppressed_event_is_recorded_with_its_reason(store):
    rec = SuppressionRecorder(store=store, persona_id="halbert")
    rec.record(_event(), allowed=False,
               reason="proactivity dial is 'quiet' (requires severity >= 2)")

    rows = store.list_outcomes_raw("halbert")
    assert len(rows) == 1
    assert rows[0]["outcome"] == "silent"
    assert rows[0]["reasons"] == ["dial:quiet"]
    assert rows[0]["severity"] == "warning"
    assert rows[0]["source"] == "finding"


def test_an_allowed_event_is_recorded_too(store):
    """A-HB-25 records every decision, or the log answers only half the
    question and the learning loop sees only one arm."""
    rec = SuppressionRecorder(store=store, persona_id="halbert")
    rec.record(_event(), allowed=True, reason="")

    rows = store.list_outcomes_raw("halbert")
    assert rows[0]["outcome"] == "speak"
    assert rows[0]["reasons"] == []


def test_the_channel_class_of_a_finding_is_push(store):
    rec = SuppressionRecorder(store=store, persona_id="halbert")
    rec.record(_event(), allowed=False, reason="safe mode active (non-critical suppressed)")
    assert store.list_outcomes_raw("halbert")[0]["channel_class"] == "push"


def test_the_finding_id_is_carried_as_the_correlation_key(store):
    rec = SuppressionRecorder(store=store, persona_id="halbert")
    rec.record(_event(finding_id="f-42"), allowed=False, reason="finding dismissed: no")
    assert store.list_outcomes_raw("halbert")[0]["context_key"] == "f-42"


def test_recording_never_breaks_the_caller(store):
    """The gate must not start failing because a log write did. A suppression
    system that crashes the thing it observes is worse than no log."""

    class Exploding:
        def record_outcome_raw(self, entry):
            raise RuntimeError("disk on fire")

    rec = SuppressionRecorder(store=Exploding(), persona_id="halbert")
    rec.record(_event(), allowed=False, reason="quiet hours active")  # must not raise


def test_no_store_means_no_recording_and_no_error():
    rec = SuppressionRecorder(store=None, persona_id="halbert")
    assert rec.record(_event(), allowed=True, reason="") is None


def test_recent_suppressions_answer_what_havent_you_told_me(store):
    rec = SuppressionRecorder(store=store, persona_id="halbert")
    rec.record(_event(title="A"), allowed=False, reason="quiet hours active")
    rec.record(_event(title="B"), allowed=True, reason="")
    rec.record(_event(title="C"), allowed=False, reason="finding dismissed: no")

    held = rec.recent_suppressions()

    assert len(held) == 2
    assert {r["outcome"] for r in held} == {"silent"}
