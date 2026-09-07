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