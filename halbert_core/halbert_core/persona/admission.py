# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Named-gate admission decisions.

Lifted from OpenClaw src/channels/message-access/decision.ts: every inbound request
walks an ordered list of named gates; the decision is an explainable record carrying
the decisive gate and reason code plus the full gate graph, so any deny can be
answered after the fact with "dropped at gate X, reason Y" — never "no".

Shared second-instance shape: DebateHaus's warrant module
(backend/ai-moderator/orchestrator/warrant.js, branch feat/moderator-warrant)
already returns denial reason codes (mandate:malformed, mandate:disabled:<type>,
holder:maxInterventionRate:<n>, ...) in exactly this reason_code shape and is
adopting the same gate_graph record (their R-DH-3). Two concrete instances make
this a module candidate for a future engine lift — generalize from both, and
keep the layers separate: this record gates ADMISSION (capability), while the
warrant gates LEGITIMACY (by whose rule the voice acts) and must not be chained
behind claim strength.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


class GateEffect:
    ALLOW = "allow"
    SKIP = "skip"
    BLOCK = "block"
    OBSERVE = "observe"


ADMISSION_DISPATCH = "dispatch"
ADMISSION_DROP = "drop"
ADMISSION_SKIP = "skip"
ADMISSION_OBSERVE = "observe"


@dataclass(frozen=True)
class Gate:
    id: str
    phase: str
    effect: str
    allowed: bool
    reason_code: str
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngressDecision:
    admission: str
    decisive_gate: str
    reason_code: str
    gate_graph: tuple[Gate, ...]


def decide_ingress(gates) -> IngressDecision:
    """First blocking gate wins; the decision records which gate and why."""
    if not gates:
        return IngressDecision(ADMISSION_DROP, "", "no_gates_evaluated", ())
    decisive = None
    for gate in gates:
        if gate.effect == GateEffect.BLOCK:
            decisive = gate
            break
    if decisive is None:
        decisive = gates[-1]
        return IngressDecision(ADMISSION_DISPATCH, decisive.id, decisive.reason_code, tuple(gates))
    return IngressDecision(ADMISSION_DROP, decisive.id, decisive.reason_code, tuple(gates))


#: Human words for the machine-readable codes; the payload carries both.
#:
#: R-01 Phase E (A12-G6): this registry and the three helpers below used
#: to live in ``dashboard/routes/guest.py``, and ``agents/channels.py``
#: hand-copied the payload shape with a comment saying it "mirrors
#: guest.py's ``_deny_payload``". A comment is not a shared function, and
#: a hand copy drifts -- the talk door, the one door every typed and
#: spoken turn arrives at, was the copy. One registry, one deny shape.
REASON_TEXT: dict[str, str] = {
    # Guest routes (the original set).
    "not_local_admin": "This control is available only from the machine it configures.",
    "peer_token_missing": "A pairing token is required for this route.",
    "guest_already_fronting": "Another persona is already fronting here.",
    "no_such_session": "No live guest session with that id.",
    "session_owned_by_other_peer": "That session was offered by another peer.",
    "no_guest_fronting": "No guest persona is fronting.",
    "no_session_to_forget": "No guest is fronting; say which session to forget.",
    "no_gate_list_configured": "This route has no admission policy configured.",
    # The talk door.
    "no_channel_configured": "No channel is configured for that ingress.",
    "below_turn_role_floor": (
        "That turn was started by someone with more authority than this "
        "arrival carries."
    ),
    "empty_arrival": "An empty message is not an instruction.",
    "turn_already_stopped": "That turn was stopped; send this as a new message.",
    "answer_already_committed": (
        "That turn has already answered; send this as a new message."
    ),
}


def allow(gate_id: str, phase: str, reason: str = "ok", **facts) -> Gate:
    """A gate that lets the request through."""
    return Gate(
        id=gate_id, phase=phase, effect=GateEffect.ALLOW,
        allowed=True, reason_code=reason, facts=facts,
    )


def block(
    gate_id: str, phase: str, reason: str, http_status: int, **facts
) -> Gate:
    """A gate that stops the walk. The first one wins."""
    return Gate(
        id=gate_id, phase=phase, effect=GateEffect.BLOCK,
        allowed=False, reason_code=reason,
        facts={"http_status": http_status, **facts},
    )


def deny_payload(decisive_gate: str, reason_code: str) -> dict[str, Any]:
    """The one denial body: which gate, why, and what to say about it."""
    return {
        "reason_code": reason_code,
        "decisive_gate": decisive_gate,
        "message": REASON_TEXT.get(reason_code, reason_code),
    }


def admit(gates) -> IngressDecision:
    """Walk an already-evaluated gate list. Alias of ``decide_ingress``.

    Named for the caller's verb: the guest routes' ``_admit`` builds its
    gates asynchronously and then decides; a synchronous door (the talk
    door) has its gates in hand and only needs the decision.
    """
    return decide_ingress(gates)
