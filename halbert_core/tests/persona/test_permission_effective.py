# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The conjunction: effective = ceiling ∧ affordance ∧ os_grant ∧ consent ∧ ¬halted.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2 (the formula) and §1.7
(the typed denials and their first-denial-wins order). The decisive axis is
named in every record — the IngressDecision discipline from admission.py —
and the decision composes with the policy lattice: an axis denial is a
SecurityLevel.DENY floor no other layer's generosity can lift.
"""
from __future__ import annotations

import dataclasses

import pytest

from halbert_core.persona.permission.affordance import AffordanceTable, EMPTY_AFFORDANCE
from halbert_core.persona.permission.ceiling import EMPTY_CEILING, ceiling_from_ids
from halbert_core.persona.permission.consent import ConsentDecision, ConsentRecord, Principal
from halbert_core.persona.permission.effective import (
    AXIS_AFFORDANCE,
    AXIS_CEILING,
    AXIS_CLAIM,
    AXIS_CONSENT,
    AXIS_HALT,
    AXIS_OS_GRANT,
    AXIS_SCOPE,
    REASON_ALLOWED,
    REASON_HALTED,
    REASON_NO_AFFORDANCE,
    REASON_NO_CEILING,
    REASON_NOT_GRANTED,
    REASON_OS_DENIED,
    REASON_OS_UNKNOWN,
    REASON_OUT_OF_SCOPE,
    REASON_QUIET,
    EffectiveDecision,
    axis_floor,
    effective_capability,
    effective_policy_with_axes,
)
from halbert_core.persona.permission.halt import HaltReason, HaltState
from halbert_core.persona.permission.os_grant import OsGrantState, OsGrantTable
from halbert_core.persona.policy import (
    AskPolicy,
    GUEST_WRITE_PLANE_FLOOR,
    OWNER_DEFAULT,
    PolicyPair,
    SecurityLevel,
    merge_policies,
)

CAP = "sensor.screen"


class _FakeRegistry:
    def __init__(self, present: set[str]):
        self._present = set(present)

    def has(self, name: str) -> bool:
        return name in self._present


def _grant_record(capability: str = CAP) -> ConsentRecord:
    return ConsentRecord(
        capability=capability,
        decision=ConsentDecision.GRANTED,
        ts="2026-09-06T14:12:03Z",
        principal=Principal(kind="owner", authn="os_reauth:touchid", at_machine=True),
        surface="desktop-app/first-run",
        text_shown_sha256="9f2c" + "0" * 60,
    )


def _all_yes(**overrides):
    """A context in which every axis is affirmative."""
    kwargs = dict(
        capability=CAP,
        ceiling=ceiling_from_ids({CAP, "reach.terminal", "sys.local_llm"}),
        affordance=AffordanceTable(present=frozenset({CAP, "reach.terminal"})),
        os_grants=OsGrantTable({CAP: OsGrantState.GRANTED, "reach.terminal": OsGrantState.GRANTED}),
        consent_records=(_grant_record(),),
        halt=HaltState(),
        registry=_FakeRegistry({"local_llm"}),
    )
    kwargs.update(overrides)
    return kwargs


def test_all_five_affirmative_allows():
    decision = effective_capability(**_all_yes())
    assert decision.allowed is True
    assert decision.reason_code == REASON_ALLOWED
    assert decision.capability == CAP
    # the full axis evidence is retained for the audit line
    axes = {obs.axis for obs in decision.observations}
    # AXIS_CLAIM joined in R-08 Phase E (A12-G2): the identity claim is
    # its own axis now rather than a threshold buried in a caller.
    assert axes == {
        AXIS_HALT, AXIS_CEILING, AXIS_AFFORDANCE, AXIS_CONSENT,
        AXIS_OS_GRANT, AXIS_SCOPE, AXIS_CLAIM,
    }
    assert all(obs.affirmative for obs in decision.observations)


def test_the_decision_is_frozen():
    decision = effective_capability(**_all_yes())
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.allowed = False


def test_halt_wins_over_everything():
    halted = HaltState()
    halted.halt(HaltReason.OWNER_STOP, by="owner", surface="tray")
    decision = effective_capability(**_all_yes(halt=halted))
    assert decision.allowed is False
    assert decision.reason_code == REASON_HALTED
    assert decision.decisive_axis == AXIS_HALT
    # a halt denial is explained by the halt, not by any axis the grants affirm


def test_no_ceiling_denies_and_names_the_axis():
    decision = effective_capability(**_all_yes(ceiling=EMPTY_CEILING))
    assert decision.allowed is False
    assert decision.reason_code == REASON_NO_CEILING
    assert decision.decisive_axis == AXIS_CEILING


def test_unknown_capability_id_denies_via_the_ceiling():
    decision = effective_capability(**_all_yes(capability="sensor.screenshot"))
    assert decision.allowed is False
    assert decision.reason_code == REASON_NO_CEILING


def test_missing_affordance_denies():
    decision = effective_capability(**_all_yes(affordance=EMPTY_AFFORDANCE))
    assert decision.allowed is False
    assert decision.reason_code == REASON_NO_AFFORDANCE
    assert decision.decisive_axis == AXIS_AFFORDANCE


def test_absent_consent_denies_because_never_asked():
    decision = effective_capability(**_all_yes(consent_records=()))
    assert decision.allowed is False
    assert decision.reason_code == REASON_NOT_GRANTED
    assert decision.decisive_axis == AXIS_CONSENT


def test_first_denial_wins_consent_before_os_per_section_1_7():
    # §1.7's precedence puts NOT_GRANTED before OS_DENIED — "you never
    # granted this" is the more fundamental answer than "macOS hasn't
    # agreed", even though the §1.2 formula lists os_grant before consent
    decision = effective_capability(
        **_all_yes(
            consent_records=(),
            os_grants=OsGrantTable({CAP: OsGrantState.DENIED}),
        )
    )
    assert decision.reason_code == REASON_NOT_GRANTED
    assert decision.decisive_axis == AXIS_CONSENT


def test_os_denied_with_consent_granted():
    decision = effective_capability(**_all_yes(os_grants=OsGrantTable({CAP: OsGrantState.DENIED})))
    assert decision.allowed is False
    assert decision.reason_code == REASON_OS_DENIED
    assert decision.decisive_axis == AXIS_OS_GRANT


def test_the_two_cant_tell_states_are_os_unknown():
    for state in (OsGrantState.UNDETERMINED, OsGrantState.UNQUERYABLE):
        decision = effective_capability(**_all_yes(os_grants=OsGrantTable({CAP: state})))
        assert decision.allowed is False, state
        assert decision.reason_code == REASON_OS_UNKNOWN, state


def test_out_of_scope_after_every_axis_affirms():
    decision = effective_capability(**_all_yes(scope_ok=False))
    assert decision.allowed is False
    assert decision.reason_code == REASON_OUT_OF_SCOPE
    assert decision.decisive_axis == AXIS_SCOPE


def test_halt_beats_all_other_denials_at_once():
    halted = HaltState()
    halted.halt(HaltReason.INTEGRITY_MISSING, by="system", surface="boot")
    decision = effective_capability(
        capability=CAP,
        ceiling=EMPTY_CEILING,
        affordance=EMPTY_AFFORDANCE,
        consent_records=(),
        os_grants=OsGrantTable({}),
        halt=halted,
    )
    assert decision.reason_code == REASON_HALTED


def test_registry_backed_affordance_flows_through_the_conjunction():
    # sys.local_llm is presence-probed via the injected registry
    decision = effective_capability(
        capability="sys.local_llm",
        ceiling=ceiling_from_ids({"sys.local_llm"}),
        affordance=EMPTY_AFFORDANCE,
        os_grants=OsGrantTable({"sys.local_llm": OsGrantState.GRANTED}),
        consent_records=(),
        halt=HaltState(),
        registry=_FakeRegistry({"local_llm"}),
    )
    # affordance affirmed by the probe; consent is absent → denied there
    affordance_obs = next(o for o in decision.observations if o.axis == AXIS_AFFORDANCE)
    assert affordance_obs.affirmative is True
    assert decision.reason_code == REASON_NOT_GRANTED


def test_every_default_is_fail_closed():
    """R-08 Phase A (A11 bug 6): halt is now the first unwired axis.

    ``halt=None`` used to read as "not halted" -- so with NOTHING wired
    the evaluator vouched for the machine not being stopped and denied on
    the ceiling instead. An omitted halt is no halt evidence, and the
    axis the design checks first is the one that answers.
    """
    decision = effective_capability(capability=CAP)  # nothing wired at all
    assert decision.allowed is False
    assert decision.reason_code == REASON_HALTED


def test_the_ceiling_answers_once_halt_evidence_exists():
    """The old pin, with the halt axis wired: unwired ceiling denies."""
    from halbert_core.persona.permission.halt import HaltState

    decision = effective_capability(capability=CAP, halt=HaltState())
    assert decision.allowed is False
    assert decision.reason_code == REASON_NO_CEILING


# ---------------------------------------------------------------------------
# Lattice composition: effective security = min(lattice security, axis floor)
# ---------------------------------------------------------------------------

def _allowed_decision() -> EffectiveDecision:
    return effective_capability(**_all_yes())


def _denied_decision() -> EffectiveDecision:
    return effective_capability(**_all_yes(ceiling=EMPTY_CEILING))


def test_axis_floor_of_a_denial_is_deny_and_not_a_question():
    floor = axis_floor(_denied_decision())
    assert floor.security is SecurityLevel.DENY
    # ask OFF: a hard fact is not a consultation question — there is nothing
    # to ask the owner; the answer is no
    assert floor.ask is AskPolicy.OFF


def test_axis_floor_of_an_allow_contributes_nothing():
    floor = axis_floor(_allowed_decision())
    assert floor.security is SecurityLevel.FULL
    assert floor.ask is AskPolicy.OFF  # other layers own consultation


def test_axis_denial_forces_deny_against_any_generosity():
    # the A1 invariant at the permission seam: three generous layers cannot
    # lift what the axes refuse
    generous = [PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.OFF)] * 3
    merged = effective_policy_with_axes(generous, _denied_decision())
    assert merged.security is SecurityLevel.DENY


def test_axis_allow_preserves_the_lattice_say():
    merged = effective_policy_with_axes([OWNER_DEFAULT], _allowed_decision())
    assert merged.security is SecurityLevel.FULL
    assert merged.ask is AskPolicy.ON_MISS  # the lattice's ask survives


def test_guest_write_plane_floor_still_holds_with_axes_on_top():
    merged = effective_policy_with_axes(
        [GUEST_WRITE_PLANE_FLOOR, OWNER_DEFAULT], _allowed_decision()
    )
    assert merged.security is SecurityLevel.DENY
    # max-ask: the owner default's ON_MISS survives a DENY-security floor —
    # consultation is the most-prompting layer's call, never the axes'
    assert merged.ask is AskPolicy.ON_MISS


def test_lattice_deny_still_holds_when_the_axes_allow():
    # the axes never REPLACE the lattice: a lattice DENY stays DENY even when
    # every axis affirms
    merged = effective_policy_with_axes([GUEST_WRITE_PLANE_FLOOR], _allowed_decision())
    assert merged.security is SecurityLevel.DENY


def test_merge_policies_composition_is_the_only_path():
    # axis_floor feeds merge_policies; there is no other way the axes touch
    # the lattice (no direct security assignment anywhere in the module)
    floor = axis_floor(_denied_decision())
    assert merge_policies([OWNER_DEFAULT, floor]).security is SecurityLevel.DENY


def test_quiet_reason_code_exists_but_is_not_computed_here():
    # §1.7's QUIET is the autonomy-only denial; it belongs to the D3-P4
    # profiles work. The code is reserved so the vocabulary stays closed.
    assert REASON_QUIET == "QUIET"