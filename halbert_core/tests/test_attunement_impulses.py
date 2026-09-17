# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Classifying Halbert's proactive events into the engine's impulse classes
with a warrant and a citation (presence spec v2 §14)."""

import pytest

engine = pytest.importorskip("haloysius.attunement.types")

from halbert_core.attunement.impulses import PRODUCED_CLASSES, classify  # noqa: E402
from halbert_core.proactive.events import ProactiveEvent  # noqa: E402

C, W = engine.ImpulseClass, engine.Warrant


def ev(data=None, affected_paths=None, **kw):
    base = dict(type="finding", severity="warning", title="t", body="b")
    base.update(kw)
    e = ProactiveEvent.create(**base)   # the same constructor the gate tests use
    if data is not None:
        e.data = data
    if affected_paths is not None:
        e.affected_paths = list(affected_paths)
    return e


def test_critical_severity_is_critical_introspected_with_a_citation():
    cls, warrant, ref = classify(ev(severity="critical", finding_id="f1"))
    assert (cls, warrant, ref) == (C.CRITICAL, W.INTROSPECTED, "finding:f1")


def test_warning_severity_is_warning():
    assert classify(ev(severity="warning"))[0] is C.WARNING


def test_morning_report_and_guest_session_are_scheduled():
    assert classify(ev(type="morning_report", severity="info"))[0] is C.SCHEDULED
    assert classify(ev(type="guest_session", severity="info"))[0] is C.SCHEDULED


def test_approval_request_is_a_warning_about_the_machines_own_action():
    assert classify(ev(type="approval_request", severity="info"))[0] is C.WARNING


def test_a_recurring_finding_is_recurrence_observed():
    cls, warrant, _ = classify(ev(severity="info", data={"recurrence_count": 3}))
    assert (cls, warrant) == (C.RECURRENCE, W.OBSERVED)


def test_an_info_finding_touching_the_current_subject_is_subject_linked():
    cls, warrant, _ = classify(ev(severity="info", affected_paths=["/etc/ssh/sshd_config"]),
                               current_subject_paths=["/etc/ssh/sshd_config"])
    assert (cls, warrant) == (C.SUBJECT_LINKED, W.OBSERVED)


def test_an_unlinked_info_finding_is_an_observed_association():
    cls, warrant, ref = classify(ev(severity="info", finding_id="f9"))
    assert (cls, warrant, ref) == (C.ASSOCIATION, W.OBSERVED, "finding:f9")


def test_an_unlinked_info_event_with_no_citation_falls_to_inferred():
    e = ev(severity="info")
    e.id = ""
    assert classify(e)[1] is W.INFERRED


def test_confirmed_acoustic_anomaly_is_life_safety():
    e = ev(severity="info", category="acoustic", data={"anomaly_severity": 2})
    assert classify(e)[0] is C.LIFE_SAFETY


def test_produced_classes_is_what_classify_can_return():
    assert PRODUCED_CLASSES == {C.LIFE_SAFETY, C.CRITICAL, C.WARNING, C.SCHEDULED,
                                C.RECURRENCE, C.SUBJECT_LINKED, C.ASSOCIATION}
