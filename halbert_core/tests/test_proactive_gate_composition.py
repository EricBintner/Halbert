# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""An event eaten by two mechanisms must name both (plan P1, §4.5).

The suppression log exists because eleven mechanisms can eat a proactive
event and every one of them is silent by construction. A log that records
only the first gate that fired answers "why not" less completely than it
looks like it does: a warning lost to an interaction of two reads exactly
like a warning lost to one.

These tests pin the composition, and pin that composing it changed neither
the gate's verdict nor the prose it returns.
"""

import pytest

from halbert_core.attunement.shadow import SuppressionRecorder
from halbert_core.attunement.store import AttunementStore
from halbert_core.config.being_config import BeingConfig
from halbert_core.findings.store import Finding, FindingStore
from halbert_core.proactive.events import ProactiveEvent
from halbert_core.proactive.gate import ProactiveGate


@pytest.fixture
def store(tmp_path):
    return AttunementStore(db_path=str(tmp_path / "attunement.db"))


@pytest.fixture
def findings(tmp_path):
    return FindingStore(db_path=str(tmp_path / "findings.db"))


def _config(**kw):
    cfg = BeingConfig()
    cfg.quiet_hours = None
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _event(severity="info", **kw):
    return ProactiveEvent.create(type="finding", severity=severity,
                                 title="t", body="b", **kw)


def _dismissed_finding(findings) -> str:
    fid = findings.add(Finding(
        id="", detector="d", severity="info", title="t", description="d",
        why_now="n", why_care="c", why_so="s",
    ))
    findings.dismiss(fid, "not relevant")
    return fid


class _SafeMode:
    """Stands in for a GuardrailEnforcer in safe mode; the gate reads one
    attribute off it and nothing else."""

    safe_mode_active = True


def test_two_mechanisms_both_reach_the_log(store, findings):
    """The dial and a dismissal both ate this event. Both are named."""
    fid = _dismissed_finding(findings)
    gate = ProactiveGate(
        _config(proactivity="quiet"),
        finding_store=findings,
        recorder=SuppressionRecorder(store=store),
    )

    allowed, _ = gate.should_notify(_event(severity="info", finding_id=fid))

    assert allowed is False
    row = store.list_outcomes_raw("halbert")[0]
    assert row["gate_reasons"] == ["dial:quiet", "standing:defer_topic:dismissed"]


def test_three_mechanisms_all_reach_the_log(store, findings):
    fid = _dismissed_finding(findings)
    gate = ProactiveGate(
        _config(proactivity="quiet"),
        guardrail_enforcer=_SafeMode(),
        finding_store=findings,
        recorder=SuppressionRecorder(store=store),
    )

    gate.should_notify(_event(severity="info", finding_id=fid))

    assert store.list_outcomes_raw("halbert")[0]["gate_reasons"] == [
        "dial:quiet", "incident:safe_mode", "standing:defer_topic:dismissed",
    ]


def test_the_prose_is_still_the_first_mechanism_that_fired(findings):
    """The gate's `(bool, str)` contract is read by callers. Composing the
    log must not change a single one of those strings."""
    fid = _dismissed_finding(findings)
    gate = ProactiveGate(_config(proactivity="quiet"), finding_store=findings)

    allowed, reason = gate.should_notify(_event(severity="info", finding_id=fid))

    assert allowed is False
    assert reason == "proactivity dial is 'quiet' (requires severity >= 2)"


def test_an_allowed_event_names_no_mechanism(store):
    gate = ProactiveGate(
        _config(proactivity="assertive"),
        recorder=SuppressionRecorder(store=store),
    )

    assert gate.should_notify(_event(severity="info"))[0] is True
    assert store.list_outcomes_raw("halbert")[0]["gate_reasons"] == []


def test_a_guest_persona_does_not_leak_a_name_into_the_log(store, monkeypatch):
    """`OutcomeEntry` is "enums, ids, numbers and timestamps only — never
    text". The guest suppression's prose carries a person's chosen name, so
    it needs a key of its own rather than the unmapped slug."""
    class _Persona:
        name = "Aurelius"

    class _Live:
        persona = _Persona()

    import halbert_core.persona.guest as guest_mod
    monkeypatch.setattr(guest_mod, "current_guest", lambda: _Live(), raising=False)

    gate = ProactiveGate(
        _config(proactivity="assertive"),
        recorder=SuppressionRecorder(store=store),
    )
    allowed, reason = gate.should_notify(_event(severity="warning"))

    assert allowed is False
    keys = store.list_outcomes_raw("halbert")[0]["gate_reasons"]
    assert keys == ["guest:fronting"]
    assert not any("aurelius" in k.lower() for k in keys)


def test_a_findings_store_that_raises_suppresses_one_event_not_a_sweep(store):
    """Composing the reasons means this read is reached for events that
    previously returned at the dial or quiet hours. In the detector sweep it
    sits under one broad try covering the whole per-detector loop, so an
    unguarded error here would now abandon that detector's remaining
    findings rather than cost a single event its dismissal check."""
    class _Exploding:
        def get(self, finding_id):
            raise RuntimeError("database is locked")

    gate = ProactiveGate(
        _config(proactivity="quiet"),
        finding_store=_Exploding(),
        recorder=SuppressionRecorder(store=store),
    )

    allowed, reason = gate.should_notify(_event(severity="info", finding_id="f-1"))

    assert allowed is False
    assert reason == "proactivity dial is 'quiet' (requires severity >= 2)"
    assert store.list_outcomes_raw("halbert")[0]["gate_reasons"] == ["dial:quiet"]


def test_the_gate_has_one_verdict_path():
    """`_decide` was a second single-answer view over `_evaluate` with no
    caller. A second verdict path is the drift CLAUDE.md's one-choke-point
    rule exists to stop."""
    assert not hasattr(ProactiveGate, "_decide")
