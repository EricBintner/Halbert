# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The conjunction — all five axes, one explainable decision.

PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.2:

    effective = ceiling ∧ affordance ∧ os_grant ∧ consent ∧ ¬halted

Every axis fails closed, so the defaults of this module deny everything:
an empty ceiling, a missing affordance, an empty OS-grant table, an absent
consent record and a halt each close the capability. Nothing is permitted
until every axis is affirmatively wired — the deny-all posture the wiring
packets (D3-P5) lift, capability by capability.

**Decisive-axis naming follows §1.7's typed-denial order, not the formula's
listing order**: ``HALTED → NO_CEILING → NO_AFFORDANCE → NOT_GRANTED →
OS_DENIED / OS_UNKNOWN → OUT_OF_SCOPE``. The boolean result is identical
(∧ commutes); the order only decides which refusal a denial *names*, and
"you never granted this" (consent) is the more fundamental answer than
"macOS hasn't agreed" (OS) — asking the OS about a capability the owner
never consented to is the prompt nobody should receive.

The decision is an explainable record in the ``admission.py`` discipline
(named decisive gate + reason code, full observations retained for the
audit line), so a refusal can always be answered with "denied on axis X,
reason Y" — never "no".

**Composition with the policy lattice** (packet 02's mechanism layer): the
decision maps onto a ``PolicyPair`` floor — denial → ``SecurityLevel.DENY``
/ ``AskPolicy.OFF`` (a hard fact is not a consultation question), allow →
``SecurityLevel.FULL`` / ``OFF`` (the axes contribute nothing to
consultation; the lattice's layers own ``ask``) — folded through
``merge_policies`` and nothing else. So an axis denial forces ``DENY``
against any layer generosity, and a lattice ``DENY`` still holds when every
axis affirms: the axes compose with the lattice; they never replace it.

``QUIET`` (§1.7's autonomy-only denial) is reserved in the reason-code
vocabulary and computed nowhere here — it belongs to the profiles packet
(D3-P4).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..policy import AskPolicy, PolicyPair, SecurityLevel, merge_policies
from .affordance import AffordanceTable, EMPTY_AFFORDANCE, affords
from .ceiling import CapabilityCeiling, EMPTY_CEILING
from .consent import ConsentDecision, ConsentRecord, consent_state
from .halt import HaltState
from .os_grant import DEFAULT_OS_GRANTS, OsGrantState, OsGrantTable, is_os_grant_affirmative

# Axis names — the decisive_axis vocabulary.
AXIS_HALT = "halt"
AXIS_CEILING = "ceiling"
AXIS_AFFORDANCE = "affordance"
AXIS_OS_GRANT = "os_grant"
AXIS_CONSENT = "consent"
AXIS_SCOPE = "scope"

# Reason codes — §1.7's typed outcomes, first-denial-wins in the order
# the design states them.
REASON_ALLOWED = "ALLOWED"
REASON_HALTED = "HALTED"
REASON_NO_CEILING = "NO_CEILING"
REASON_NO_AFFORDANCE = "NO_AFFORDANCE"
REASON_NOT_GRANTED = "NOT_GRANTED"
REASON_OS_DENIED = "OS_DENIED"
REASON_OS_UNKNOWN = "OS_UNKNOWN"
REASON_OUT_OF_SCOPE = "OUT_OF_SCOPE"
#: Autonomy-only (§1.7's QUIET). Reserved; computed by the profiles packet.
REASON_QUIET = "QUIET"


@dataclass(frozen=True)
class AxisObservation:
    """One axis's reading at evaluation time — retained for the audit line."""

    axis: str
    affirmative: bool
    detail: str


@dataclass(frozen=True)
class EffectiveDecision:
    """The gate's answer: the boolean, the decisive axis, the reason.

    In the IngressDecision discipline (persona/admission.py): a denial
    always names the axis that refused and why, and the full axis evidence
    rides along so any refusal can be explained after the fact. D3-P2's
    ``Denied`` exception and D3-P3's ``require()`` are built on this record;
    it never collapses to a bare boolean at the seam.
    """

    capability: str
    allowed: bool
    decisive_axis: str
    reason_code: str
    observations: tuple


def effective_capability(
    capability: str,
    *,
    ceiling: CapabilityCeiling = EMPTY_CEILING,
    affordance: AffordanceTable = EMPTY_AFFORDANCE,
    os_grants: OsGrantTable = DEFAULT_OS_GRANTS,
    consent_records: Sequence[ConsentRecord] = (),
    halt: Optional[HaltState] = None,
    scope_ok: Optional[bool] = None,
    registry: Optional[object] = None,
) -> EffectiveDecision:
    """Evaluate one capability against all five axes.

    Every default denies: an unwired axis is a closed axis. ``halt=None``
    reads as *not halted* — the pure evaluator has no halt evidence either
    way; the wiring always passes the live ``HaltState`` (and Phase-0 boot
    reads the persisted halt before anything starts, D3-P6).

    ``scope_ok`` is tri-state: ``None`` (the default) means no scope was
    requested and the scope axis is vacuously affirmative; ``False`` means
    the requested target is outside the grant's scope (OUT_OF_SCOPE);
    ``True`` means the scope check ran and passed.
    """
    halted = halt.is_halted() if halt is not None else False
    halt_detail = halt.reason_code if halt is not None else ""
    ceiling_ok = ceiling.permits(capability)
    affordance_ok = affords(capability, affordance, registry=registry)
    consent = consent_state(consent_records, capability)
    consent_ok = consent is ConsentDecision.GRANTED
    os_state = os_grants.state_for(capability)
    os_ok = is_os_grant_affirmative(os_state)
    scope_ok_flag = scope_ok is not False

    observations = (
        AxisObservation(AXIS_HALT, not halted, halt_detail),
        AxisObservation(AXIS_CEILING, ceiling_ok, f"{len(ceiling)} ids"),
        AxisObservation(AXIS_AFFORDANCE, affordance_ok, "present" if affordance_ok else "unavailable"),
        AxisObservation(AXIS_CONSENT, consent_ok, consent.value),
        AxisObservation(AXIS_OS_GRANT, os_ok, os_state.value),
        AxisObservation(AXIS_SCOPE, scope_ok_flag, "granted-scope" if scope_ok_flag else "outside-grant"),
    )

    # First denial wins, in §1.7's order. Halt is checked first and beats
    # every other reading; consent names itself before the OS does.
    if halted:
        return EffectiveDecision(capability, False, AXIS_HALT, REASON_HALTED, observations)
    if not ceiling_ok:
        return EffectiveDecision(capability, False, AXIS_CEILING, REASON_NO_CEILING, observations)
    if not affordance_ok:
        return EffectiveDecision(capability, False, AXIS_AFFORDANCE, REASON_NO_AFFORDANCE, observations)
    if not consent_ok:
        return EffectiveDecision(capability, False, AXIS_CONSENT, REASON_NOT_GRANTED, observations)
    if os_state is OsGrantState.DENIED:
        return EffectiveDecision(capability, False, AXIS_OS_GRANT, REASON_OS_DENIED, observations)
    if not os_ok:
        # UNDETERMINED and UNQUERYABLE are both "can't tell", and a
        # capability the OS cannot be recorded as agreeing to is closed.
        return EffectiveDecision(capability, False, AXIS_OS_GRANT, REASON_OS_UNKNOWN, observations)
    if not scope_ok_flag:
        return EffectiveDecision(capability, False, AXIS_SCOPE, REASON_OUT_OF_SCOPE, observations)
    return EffectiveDecision(capability, True, "", REASON_ALLOWED, observations)


def axis_floor(decision: EffectiveDecision) -> PolicyPair:
    """The lattice contribution of a five-axis decision.

    A denial is a hard capability fact: ``SecurityLevel.DENY`` with
    ``AskPolicy.OFF`` — there is nothing to consult the owner about; the
    answer is no, and folding it through ``merge_policies`` makes that deny
    stick against every other layer's generosity. An allow contributes
    ``FULL``/``OFF`` — the axes never speak to consultation; the lattice's
    own layers own the ``ask`` axis entirely.
    """
    if decision.allowed:
        return PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.OFF)
    return PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.OFF)


def effective_policy_with_axes(
    lattice_layers,
    decision: EffectiveDecision,
) -> PolicyPair:
    """Fold the axis floor through the lattice — the only composition path.

    ``effective_policy_with_axes([role_floor, plane, session], decision)``
    is the complete per-call policy view: the lattice layers' say, min-folded
    with what the five axes determined. A ``DENY`` from either side survives
    the merge; neither layer can loosen the other.
    """
    return merge_policies(list(lattice_layers) + [axis_floor(decision)])