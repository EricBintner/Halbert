# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shadow mode proper: the engine decides, the row records it, nothing acts
on it (plan §4.6 stage 1; Haloysius handoff 2026-09-10 §2.1).

The suppression log recorded the gate's binary verdict with `margin` pinned
at 0.0 and one reason key. That is right for the shadow comparison and
fatal for Phase C, which is defined over `decision.margin` (the exploration
arm is "prefer ASK_FIRST over HOLD *near a threshold*") and over the six
outcomes (a HOLD later released and engaged with warmly is evidence the
hold was wrong; a SILENT carries no such possibility).

So the row now carries both verdicts and says which is which — and a
`margin` of None, never 0.0, when no engine decision produced one.
"""

import pytest

from halbert_core.attunement.shadow import (
    ShadowDecider,
    SuppressionRecorder,
)
from halbert_core.attunement.store import AttunementStore
from halbert_core.config.being_config import BeingConfig
from halbert_core.proactive.events import ProactiveEvent
from halbert_core.proactive.gate import ProactiveGate

engine = pytest.importorskip("haloysius.attunement.types")


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


def _config(**kw):
    cfg = BeingConfig()
    cfg.quiet_hours = None
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _event(severity="warning", **kw):
    return ProactiveEvent.create(type="finding", severity=severity,
                                 title="t", body="b", **kw)


def _recorder(store, cfg):
    return SuppressionRecorder(store=store, decider=ShadowDecider(store, cfg))


def _row(store):
    rows = store.list_outcomes_raw("halbert")
    assert len(rows) == 1
    return rows[0]


# --- the three losses the handoff named ------------------------------------

def test_the_row_carries_a_real_margin(store):
    """A-HB-26's exploration arm is "prefer ASK_FIRST over HOLD where the
    policy is near a threshold". With every margin at 0.0 no case is ever
    near one and the cheap source of positive counterfactuals is gone."""
    cfg = _config(proactivity="balanced")
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event())

    row = _row(store)
    assert row["decision_source"] == "engine"
    assert isinstance(row["margin"], float)


def test_the_outcome_is_the_engines_six_valued_one(store):
    """`speak`/`silent` merges a HOLD — which can be released and engaged
    with, and so labelled wrong — into a SILENT, which cannot."""
    cfg = _config(proactivity="balanced")
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event())

    outcome = _row(store)["outcome"]
    assert outcome in {o.value for o in engine.EngagementOutcome}


def test_the_full_reason_tuple_is_recorded(store):
    cfg = _config(proactivity="off")
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event())

    row = _row(store)
    assert row["reasons"]
    assert all(isinstance(r, str) for r in row["reasons"])


# --- and the gate's verdict is still legible beside it ---------------------

def test_both_verdicts_land_on_one_row(store):
    cfg = _config(proactivity="quiet")
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(
        _event(severity="info")
    )

    row = _row(store)
    assert row["gate_outcome"] == "silent"
    assert row["gate_reasons"] == ["dial:quiet"]
    assert row["decision_source"] == "engine"
    assert row["outcome"] in {o.value for o in engine.EngagementOutcome}


def test_disagreement_is_recorded_as_a_flag_not_inferred_later(store):
    """Shadow mode's whole product is the disagreement. A reader should not
    have to re-derive which engine outcomes count as speech."""
    cfg = _config(proactivity="off")
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event())

    row = _row(store)
    assert row["shadow_agrees"] is True  # both hold it at an off dial


def test_shadow_mode_changes_no_behaviour(store):
    """Stage one decides, logs, and acts on nothing."""
    cases = [
        (_config(proactivity="quiet"), _event(severity="info")),
        (_config(proactivity="quiet"), _event(severity="critical")),
        (_config(proactivity="balanced"), _event(severity="warning")),
        (_config(proactivity="off"), _event(severity="critical")),
    ]
    for cfg, event in cases:
        bare = ProactiveGate(cfg).should_notify(event)
        shadowed = ProactiveGate(
            cfg, recorder=_recorder(store, cfg)
        ).should_notify(event)
        assert bare == shadowed


# --- the null margin -------------------------------------------------------

def test_no_engine_decision_writes_a_null_margin_not_a_zero(store):
    """0.0 must mean "the engine computed a margin and it landed on the
    threshold". Anything else makes the Phase C reader's filter a lie."""
    cfg = _config(proactivity="quiet")
    ProactiveGate(
        cfg, recorder=SuppressionRecorder(store=store)
    ).should_notify(_event(severity="info"))

    row = _row(store)
    assert row["decision_source"] == "gate"
    assert row["margin"] is None
    assert row["shadow_agrees"] is None


def test_a_broken_shadow_falls_back_to_the_gates_verdict(store):
    class Exploding(ShadowDecider):
        def decide(self, *a, **kw):
            raise RuntimeError("policy on fire")

    cfg = _config(proactivity="quiet")
    rec = SuppressionRecorder(store=store, decider=Exploding(store, cfg))
    allowed, _ = ProactiveGate(cfg, recorder=rec).should_notify(
        _event(severity="info")
    )

    assert allowed is False
    row = _row(store)
    assert row["decision_source"] == "gate"
    assert row["gate_outcome"] == "silent"


# --- the row is still an OutcomeEntry --------------------------------------

def test_the_row_still_loads_as_the_engines_outcome_entry(store):
    cfg = _config(proactivity="balanced")
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event())

    entry = store.list_outcomes("halbert")[0]
    assert isinstance(entry, engine.OutcomeEntry)
    assert isinstance(entry.outcome, engine.EngagementOutcome)
    assert entry.reasons


def test_what_havent_you_told_me_reads_the_gate_not_the_engine(store):
    """The engine's opinion is not acted on, so it cannot be the answer to
    a question about what the product withheld."""
    cfg = _config(proactivity="assertive")
    rec = _recorder(store, cfg)
    ProactiveGate(cfg, recorder=rec).should_notify(_event(severity="critical"))

    row = _row(store)
    assert row["gate_outcome"] == "speak"
    assert rec.recent_suppressions() == []


# --- Halbert's own ceilings ------------------------------------------------

def test_halbert_is_not_muted_for_its_first_week():
    """The engine's new-relationship mute is a companion's. A fresh install
    is when a machine-minder has the most to say."""
    from halbert_core.attunement.context import halbert_config

    attachment = halbert_config().attachment
    assert attachment.new_relationship_sessions == 0
    assert attachment.new_relationship_days == 0
    assert attachment.persona_may_solicit_invitation is False


def test_the_daily_cap_is_a_runaway_guard_not_a_ration():
    from halbert_core.attunement.context import halbert_config

    assert halbert_config().attachment.max_proactive_per_day == 24


def test_a_null_margin_survives_the_round_trip_to_the_engines_dataclass(store):
    """The whole point of None-not-0.0 is that a Phase C reader can filter on
    it. That only works if it arrives intact."""
    cfg = _config(proactivity="quiet")
    ProactiveGate(
        cfg, recorder=SuppressionRecorder(store=store)
    ).should_notify(_event(severity="info"))

    entry = store.list_outcomes("halbert")[0]
    assert entry.margin is None
    assert entry.outcome is engine.EngagementOutcome.SILENT
    assert entry.reasons == ("dial:quiet",)
