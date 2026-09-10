# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Typed denials — the gate never answers with a bare False.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.7: ``require()`` never
returns a bare ``False`` and has no default return path. It raises
``Denied`` carrying one of the seven typed outcomes (first-denial-wins,
in the §1.7 order P1 pinned) plus ``QUIET`` (autonomy only, reserved for
the profiles packet). If the store cannot be read it raises
``ConsentUnavailable`` and enters Stop; it never falls back to a value.
"""
from __future__ import annotations

import pytest

from halbert_core.consent.denials import (
    CLOSED_REASONS,
    ConsentUnavailable,
    Denied,
    denial_copy,
)
from halbert_core.persona.permission import (
    AffordanceTable,
    CapabilityCeiling,
    ConsentDecision,
    ConsentRecord,
    HaltState,
    OsGrantState,
    OsGrantTable,
    Principal,
    effective_capability,
)

# Every §1.7 outcome, verbatim.
ALL_SECTION_17_OUTCOMES = {
    "HALTED",
    "NO_CEILING",
    "NO_AFFORDANCE",
    "NOT_GRANTED",
    "OS_DENIED",
    "OS_UNKNOWN",
    "OUT_OF_SCOPE",
    "QUIET",
}

# Added since, deliberately and with its own reason to exist (R-08,
# A11-G2): SCOPE_UNREADABLE is what a grant whose scope the code cannot
# parse denies with. It is not OUT_OF_SCOPE -- the scope check never ran
# -- and it must not be an exception either, because a refusal the
# permission system cannot explain is still a refusal it has to TYPE.
# Before it existed, 24 of the 47 shipped profile rows raised a bare
# ValueError out of require() on the first call after acceptance.
#
# NEEDS_APPROVAL (R-08, A11-G1/G9 under FD-6) is the second: a grant
# recorded ``ask: every_use`` is a standing permission, not a standing
# authorisation. It is not NOT_GRANTED, because the remedy is different
# -- answer the confirmation you were shown, do not grant again.
ADDED_OUTCOMES = {"SCOPE_UNREADABLE", "NEEDS_APPROVAL"}


# ---------------------------------------------------------------------------
# The closed vocabulary.
# ---------------------------------------------------------------------------


def test_the_denied_vocabulary_is_the_section_17_outcomes_plus_the_recorded_additions():
    assert CLOSED_REASONS == frozenset(ALL_SECTION_17_OUTCOMES | ADDED_OUTCOMES)


def test_every_section_17_outcome_is_still_carried():
    """The additions extend the vocabulary; they never replace it."""
    assert frozenset(ALL_SECTION_17_OUTCOMES) <= CLOSED_REASONS


@pytest.mark.parametrize("reason_code", sorted(ALL_SECTION_17_OUTCOMES))
def test_every_outcome_is_constructible(reason_code):
    denied = Denied("sensor.screen", reason_code)
    assert denied.reason_code == reason_code


@pytest.mark.parametrize(
    "bad", ["ALLOWED", "", "denied", "NOT_A_THING", "halted"]
)
def test_a_reason_outside_the_closed_set_is_refused(bad):
    """Fail-closed vocabulary, the ceiling discipline: a typo in a reason
    code must never mint a new refusal outcome silently."""
    with pytest.raises(ValueError):
        Denied("sensor.screen", bad)


def test_allow_is_not_a_denial_outcome():
    assert "ALLOWED" not in CLOSED_REASONS


# ---------------------------------------------------------------------------
# Raised from P1's EffectiveDecision.
# ---------------------------------------------------------------------------


def _records(capability="sensor.screen"):
    owner = Principal(kind="owner", id="local:501", authn="os_reauth:touchid", at_machine=True)
    return (ConsentRecord(
        capability=capability, decision=ConsentDecision.GRANTED,
        ts="2026-09-06T14:12:03Z", principal=owner,
        surface="desktop-app/first-run", text_shown_sha256="9f2c" + "0" * 60,
    ),)


def _granted_capability(capability="sensor.screen"):
    """All five axes affirmative — the only state in which a denial is NOT
    expected, so every denial below names its own isolated cause."""
    return effective_capability(
        capability,
        ceiling=CapabilityCeiling(frozenset({capability})),
        affordance=AffordanceTable(present=frozenset({capability})),
        os_grants=OsGrantTable({capability: OsGrantState.GRANTED}),
        consent_records=_records(capability),
        halt=HaltState(),
        scope_ok=True,
    )


def test_an_allowed_decision_has_no_denial():
    with pytest.raises(ValueError):
        Denied.from_decision(_granted_capability())


def _decision_leading_to(reason_code):
    capability = "sensor.screen"
    if reason_code == "HALTED":
        halt = HaltState()
        halt.halt("owner_stop")
        return effective_capability(capability, halt=halt)
    # R-08 Phase A (A11 bug 6): every branch below passes a live, NOT
    # halted state. Omitting it used to read as "not halted"; it now
    # reads as no halt evidence and denies HALTED, which would make
    # every row of this matrix answer the same thing.
    if reason_code == "NO_CEILING":
        return effective_capability(capability, halt=HaltState())
    if reason_code == "NO_AFFORDANCE":
        return effective_capability(
            capability, ceiling=CapabilityCeiling(frozenset({capability})),
            halt=HaltState(),
        )
    if reason_code == "NOT_GRANTED":
        return effective_capability(
            capability,
            ceiling=CapabilityCeiling(frozenset({capability})),
            affordance=AffordanceTable(present=frozenset({capability})),
            halt=HaltState(),
        )
    if reason_code == "OS_DENIED":
        return effective_capability(
            capability,
            ceiling=CapabilityCeiling(frozenset({capability})),
            affordance=AffordanceTable(present=frozenset({capability})),
            consent_records=_records(capability),
            os_grants=OsGrantTable({capability: OsGrantState.DENIED}),
            halt=HaltState(),
        )
    if reason_code == "OS_UNKNOWN":
        return effective_capability(
            capability,
            ceiling=CapabilityCeiling(frozenset({capability})),
            affordance=AffordanceTable(present=frozenset({capability})),
            consent_records=_records(capability),
            halt=HaltState(),
        )
    if reason_code == "OUT_OF_SCOPE":
        return effective_capability(
            capability,
            ceiling=CapabilityCeiling(frozenset({capability})),
            affordance=AffordanceTable(present=frozenset({capability})),
            consent_records=_records(capability),
            os_grants=OsGrantTable({capability: OsGrantState.GRANTED}),
            halt=HaltState(),
            scope_ok=False,
        )
    raise AssertionError(f"no denial matrix entry for {reason_code}")


@pytest.mark.parametrize(
    "reason_code",
    ["HALTED", "NO_CEILING", "NO_AFFORDANCE", "NOT_GRANTED",
     "OS_DENIED", "OS_UNKNOWN", "OUT_OF_SCOPE"],
)
def test_each_axis_failure_raises_its_typed_outcome(reason_code):
    decision = _decision_leading_to(reason_code)

    with pytest.raises(Denied) as caught:
        raise Denied.from_decision(decision)

    denied = caught.value
    assert denied.reason_code == reason_code
    assert denied.capability == "sensor.screen"
    assert denied.decisive_axis == decision.decisive_axis
    # The full axis evidence rides along for the audit line.
    assert denied.decision is decision
    assert denied.decision.observations == decision.observations


def test_the_denial_names_itself_for_the_audit_line():
    denied = Denied.from_decision(_decision_leading_to("NOT_GRANTED"))

    text = str(denied)
    assert "sensor.screen" in text
    assert "NOT_GRANTED" in text


def test_each_outcome_has_deterministic_copy():
    """§1.7: both the UI and the machine's own voice can explain a refusal.
    The copy is shipped deterministic text, never generated."""
    for reason_code in CLOSED_REASONS:
        assert denial_copy(reason_code).strip()


def test_denial_copy_names_the_right_outcome():
    assert "stopped" in denial_copy("HALTED").lower()
    assert "never granted" in denial_copy("NOT_GRANTED").lower()


def test_denial_copy_for_a_bogus_code_is_refused():
    with pytest.raises(ValueError):
        denial_copy("NOT_A_THING")


# ---------------------------------------------------------------------------
# ConsentUnavailable — a Stop, never a fallback value.
# ---------------------------------------------------------------------------


def test_consent_unavailable_is_a_runtime_error_with_a_halt_reason():
    exc = ConsentUnavailable("the ledger cannot be read")

    assert isinstance(exc, RuntimeError)
    # The default halt reason is unreadable — the wiring writes it into
    # P1's HaltState and the machine says which one stopped it.
    assert exc.halt_reason == "consent_unreadable"


def test_consent_unavailable_names_its_halt_reason():
    exc = ConsentUnavailable(
        "integrity primitive missing", halt_reason="integrity_missing"
    )

    assert exc.halt_reason == "integrity_missing"