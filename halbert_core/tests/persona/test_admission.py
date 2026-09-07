# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
from halbert_core.persona.admission import (
    Gate, GateEffect, decide_ingress, IngressDecision, ADMISSION_DISPATCH, ADMISSION_DROP,
)

def _gate(id, effect=GateEffect.ALLOW, reason="ok", **facts):
    return Gate(id=id, phase="test", effect=effect, allowed=effect is not GateEffect.BLOCK, reason_code=reason, facts=facts)

def test_first_blocker_is_decisive_and_recorded():
    gates = [_gate("identity"), _gate("persona", effect=GateEffect.BLOCK, reason="persona_execute_deny")]
    decision = decide_ingress(gates)
    assert decision.admission == ADMISSION_DROP
    assert decision.decisive_gate == "persona"
    assert decision.reason_code == "persona_execute_deny"
    assert len(decision.gate_graph) == 2  # full graph retained for the audit trail

def test_all_allow_dispatches():
    decision = decide_ingress([_gate("identity"), _gate("persona"), _gate("session")])
    assert decision.admission == ADMISSION_DISPATCH
    assert decision.decisive_gate == "session"  # last gate evaluated

def test_empty_gate_list_fails_closed():
    decision = decide_ingress([])
    assert decision.admission == ADMISSION_DROP
    assert decision.reason_code == "no_gates_evaluated"