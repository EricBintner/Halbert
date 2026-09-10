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
from typing import Any, Optional, Sequence

from ..policy import AskPolicy, PolicyPair, SecurityLevel, merge_policies
from .affordance import AffordanceTable, EMPTY_AFFORDANCE, affords
from .ceiling import CapabilityCeiling, EMPTY_CEILING
from .consent import (
    ASK_EVERY_USE,
    ASK_OFF,
    ConsentDecision,
    ConsentRecord,
    consent_state,
    latest_for,
)
from ..claims import ClaimStrength, meets_floor
from .halt import HaltState
from .os_grant import DEFAULT_OS_GRANTS, OsGrantState, OsGrantTable, is_os_grant_affirmative

# Axis names — the decisive_axis vocabulary.
AXIS_HALT = "halt"
AXIS_CEILING = "ceiling"
AXIS_AFFORDANCE = "affordance"
AXIS_OS_GRANT = "os_grant"
AXIS_CONSENT = "consent"
AXIS_SCOPE = "scope"
#: A12-G2: the identity claim the turn carries. Its own axis rather than
#: a threshold buried in a caller -- ``meets_floor`` existed and had no
#: consumer, and the one place a claim was compared used a hard-coded
#: number, so a capability could not state its own floor.
AXIS_CLAIM = "claim"

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
#: A11-G2: the grant's own scope could not be read. Not "out of scope"
#: -- the check never ran -- and not an exception either: a refusal the
#: permission system cannot explain is still a refusal it must TYPE.
REASON_SCOPE_UNREADABLE = "SCOPE_UNREADABLE"
#: A12-G2: the claim strength each capability requires of the speaker.
#: Absent means the capability takes any claim, including none -- the
#: ladder caps what a weak claim may reach; it never demands one where
#: the design does not.
CLAIM_FLOORS = {
    "reach.privileged": ClaimStrength.ASSERTED,
    "reach.config.write": ClaimStrength.ASSERTED,
    "reach.package": ClaimStrength.ASSERTED,
    "reach.service": ClaimStrength.ASSERTED,
    "auto.act": ClaimStrength.ASSERTED,
    "sensor.voiceprint": ClaimStrength.ASSERTED,
}

#: A11-G1: the grant stands, and this use has not been approved yet.
#: Distinct from NOT_GRANTED (nothing was ever granted) because the
#: remedy is different: one is "grant it", the other is "answer the
#: confirmation you were shown".
REASON_NEEDS_APPROVAL = "NEEDS_APPROVAL"


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
    #: A11-G1: the ask disposition of the grant this decision folded.
    #: Carried on the decision because ``axis_floor`` is the only place
    #: the ask reaches the lattice, and it has nothing else to read --
    #: it used to be a constant OFF, which is what "recorded, never
    #: enforced" meant in practice.
    ask: str = "off"


#: A11 bug 6: the sentinel that makes ``halt`` required without breaking
#: every keyword call site. ``halt=None`` used to read as "not halted",
#: so a wiring site that simply omitted the argument never observed Stop
#: -- the axis the design puts FIRST, and the one that is supposed to
#: win over everything. An omitted halt is now no halt EVIDENCE, which
#: denies like every other unwired axis. Passing ``halt=None``
#: explicitly means the same thing: the evaluator cannot tell the two
#: apart, and neither can vouch for the machine not being stopped.
_HALT_REQUIRED = object()


def effective_capability(
    capability: str,
    *,
    ceiling: CapabilityCeiling = EMPTY_CEILING,
    affordance: AffordanceTable = EMPTY_AFFORDANCE,
    os_grants: OsGrantTable = DEFAULT_OS_GRANTS,
    consent_records: Sequence[ConsentRecord] = (),
    halt: Any = _HALT_REQUIRED,
    scope_ok: Optional[bool] = None,
    registry: Optional[object] = None,
    now: Optional[str] = None,
    turn_bound: Optional[bool] = None,
    claim: Optional[object] = None,
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
    if halt is _HALT_REQUIRED or halt is None:
        # No halt evidence. Deny on the axis the design checks first,
        # rather than assume the machine is running (A11 bug 6).
        return EffectiveDecision(
            capability=capability,
            allowed=False,
            decisive_axis=AXIS_HALT,
            reason_code=REASON_HALTED,
            observations=(
                AxisObservation(
                    AXIS_HALT, False,
                    "no halt state was passed; the evaluator cannot vouch "
                    "for the machine not being stopped",
                ),
            ),
        )
    halted = halt.is_halted()
    halt_detail = halt.reason_code
    ceiling_ok = ceiling.permits(capability)
    affordance_ok = affords(capability, affordance, registry=registry)
    # A11 bug 3: ONE clock. This used to fold the consent state on wall
    # time while require() resolved the granted scope through an injected
    # ``now`` -- so an injected ``now`` past expires_at with wall time
    # before it produced ALLOWED with granted_scope=None: no scope check,
    # and no redaction check either.
    consent = consent_state(consent_records, capability, now=now)
    consent_ok = consent is ConsentDecision.GRANTED
    os_state = os_grants.state_for(capability)
    os_ok = is_os_grant_affirmative(os_state)
    scope_ok_flag = scope_ok is not False
    # A11-G7 (FD-7): "it is whether anyone asked". A turn-scoped grant is
    # permission to act WITHIN a turn, so with no live turn bound there
    # is nothing it is permission for. The reason code existed and was
    # computed by nothing. ``turn_bound=None`` means the caller has no
    # opinion -- the pre-FD-7 behaviour, unchanged.
    granted_record = latest_for(consent_records, capability)
    turn_scoped = bool(
        granted_record is not None
        and (granted_record.scope or {}).get("turn_scoped")
    )
    quiet = turn_scoped and turn_bound is False
    # A12-G2: the claim axis. ``meets_floor`` was dead vocabulary beside
    # a single hard-coded threshold, so a capability could not state what
    # identity it needs and an unverified speaker's claim never reached
    # the evaluator at all.
    # Tri-state, like ``scope_ok``: ``claim=None`` means the caller bound
    # no claim axis, which is the typed dashboard turn -- its identity
    # rides the session and it records no claim at all (the 04-A2 rule).
    # A claim that IS bound and falls below the capability's floor is
    # what denies; an absent one changes nothing.
    claim_floor = CLAIM_FLOORS.get(capability)
    claim_ok = True
    claim_detail = "no claim bound"
    strength = getattr(claim, "strength", None)
    if claim_floor is not None and strength is not None:
        claim_ok = meets_floor(strength, claim_floor)
        claim_detail = ClaimStrength(strength).name.lower()
    elif claim_floor is None:
        claim_detail = "no floor"

    observations = (
        AxisObservation(AXIS_HALT, not halted, halt_detail),
        AxisObservation(AXIS_CEILING, ceiling_ok, f"{len(ceiling)} ids"),
        AxisObservation(AXIS_AFFORDANCE, affordance_ok, "present" if affordance_ok else "unavailable"),
        AxisObservation(AXIS_CONSENT, consent_ok, consent.value),
        AxisObservation(AXIS_OS_GRANT, os_ok, os_state.value),
        AxisObservation(AXIS_SCOPE, scope_ok_flag, "granted-scope" if scope_ok_flag else "outside-grant"),
        AxisObservation(AXIS_CLAIM, claim_ok, claim_detail),
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
    if not claim_ok:
        return EffectiveDecision(capability, False, AXIS_CLAIM, REASON_NOT_GRANTED, observations)
    if quiet:
        return EffectiveDecision(capability, False, AXIS_CONSENT, REASON_QUIET, observations)
    # A11-G1: the ask disposition of the grant that just affirmed, so
    # ``axis_floor`` has something to read. It never changes the boolean
    # -- an ask-every-use grant IS granted; whether this particular use
    # may proceed is ``require()``'s question, one layer up.
    ask = (
        getattr(granted_record, "ask", ASK_OFF)
        if granted_record is not None else ASK_OFF
    )
    return EffectiveDecision(
        capability, True, "", REASON_ALLOWED, observations, ask=ask)


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
        # A11-G1: an ask-every-use grant contributes ALWAYS. This was a
        # constant OFF, so the ask axis could never reach a caller even
        # once the ledger carried it -- "Recorded, never enforced", in
        # role_gate.py's own words.
        return PolicyPair(
            security=SecurityLevel.FULL,
            ask=(
                AskPolicy.ALWAYS if decision.ask == ASK_EVERY_USE
                else AskPolicy.OFF
            ),
        )
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