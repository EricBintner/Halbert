# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""ProactiveGate records what it decides (A-HB-25, plan §4.6 stage 1).

Shadow mode's first stage changes no behaviour: the gate decides exactly as
it does today and writes down what it did. These tests pin both halves —
that the row appears, and that nothing about the decision moved.
"""

import pytest

from halbert_core.attunement.shadow import SuppressionRecorder
from halbert_core.attunement.store import AttunementStore
from halbert_core.config.being_config import BeingConfig
from halbert_core.proactive.events import ProactiveEvent
from halbert_core.proactive.gate import ProactiveGate


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


def _event(severity="info", **kw):
    return ProactiveEvent.create(type="finding", severity=severity,
                                 title="t", body="b", **kw)


def _config(**kw):
    cfg = BeingConfig()
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_a_suppressed_event_lands_in_the_log(store):
    gate = ProactiveGate(
        _config(proactivity="quiet", quiet_hours=None),
        recorder=SuppressionRecorder(store=store),
    )
    allowed, reason = gate.should_notify(_event(severity="info"))

    assert allowed is False
    rows = store.list_outcomes_raw("halbert")
    assert len(rows) == 1
    assert rows[0]["outcome"] == "silent"
    assert rows[0]["reasons"] == ["dial:quiet"]


def test_an_allowed_event_lands_in_the_log(store):
    gate = ProactiveGate(
        _config(proactivity="assertive", quiet_hours=None),
        recorder=SuppressionRecorder(store=store),
    )
    allowed, _ = gate.should_notify(_event(severity="info"))

    assert allowed is True
    assert store.list_outcomes_raw("halbert")[0]["outcome"] == "speak"


def test_the_decision_is_unchanged_with_and_without_a_recorder(store):
    """Stage one of the rollout must be behaviour-preserving."""
    cases = [
        (_config(proactivity="quiet", quiet_hours=None), _event(severity="info")),
        (_config(proactivity="quiet", quiet_hours=None), _event(severity="critical")),
        (_config(proactivity="balanced", quiet_hours=None), _event(severity="warning")),
        (_config(proactivity="off", quiet_hours=None), _event(severity="critical")),
    ]
    for cfg, event in cases:
        bare = ProactiveGate(cfg).should_notify(event)
        watched = ProactiveGate(
            cfg, recorder=SuppressionRecorder(store=store)
        ).should_notify(event)
        assert bare == watched


def test_a_broken_recorder_does_not_break_the_gate():
    class Exploding:
        def record(self, *a, **kw):
            raise RuntimeError("nope")

    gate = ProactiveGate(_config(proactivity="quiet", quiet_hours=None),
                         recorder=Exploding())
    assert gate.should_notify(_event(severity="info")) == (
        False, "proactivity dial is 'quiet' (requires severity >= 2)"
    )


def test_no_recorder_is_the_default():
    gate = ProactiveGate(_config(quiet_hours=None))
    assert gate.recorder is None
    assert gate.should_notify(_event(severity="critical"))[0] is True
