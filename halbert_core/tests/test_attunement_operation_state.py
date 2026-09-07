# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Assistant-side operation state (A-HB-1, HB-N1).

The engine's receptivity table models a person in a room. This product's
dominant interruption cost is a person mid-operation *with the persona
itself*: every environmental signal can read "great moment" two seconds
before a mistaken confirmation on ``mkfs``.

The same predicate is what the observation-lenses suppression gate (B4)
needs, so it is computed once here rather than twice.
"""

import pytest

from halbert_core.agents.states import AgentState
from halbert_core.tools.safety import RiskLevel
from halbert_core.attunement.operation_state import (
    OperationState,
    operation_state,
)


def test_idle_agent_with_nothing_open_is_clear():
    s = operation_state(agent_state=AgentState.IDLE)
    assert s.any_active() is False
    assert s.awaiting_user_confirmation is False
    assert s.operation_in_progress is False


def test_awaiting_confirmation_is_the_strongest_signal():
    """A paused turn holding a confirmation is the most interruption-hostile
    state Halbert has."""
    s = operation_state(agent_state=AgentState.AWAITING_CONFIRMATION)
    assert s.awaiting_user_confirmation is True
    assert s.any_active() is True
    assert "operation:awaiting_confirmation" in s.reasons


@pytest.mark.parametrize(
    "state",
    [
        AgentState.PLANNING,
        AgentState.SEARCHING,
        AgentState.READING,
        AgentState.EXECUTING,
        AgentState.OBSERVING,
        AgentState.RESPONDING,
    ],
)
def test_a_turn_in_flight_is_an_operation_in_progress(state):
    s = operation_state(agent_state=state)
    assert s.operation_in_progress is True
    assert "operation:in_flight" in s.reasons


def test_idle_and_error_are_not_operations_in_progress():
    for state in (AgentState.IDLE, AgentState.ERROR):
        assert operation_state(agent_state=state).operation_in_progress is False


@pytest.mark.parametrize("risk", [RiskLevel.HIGH, RiskLevel.CRITICAL])
def test_high_and_critical_tool_risk_make_the_turn_destructive(risk):
    s = operation_state(agent_state=AgentState.EXECUTING, turn_risk=risk)
    assert s.destructive_turn is True
    assert "operation:destructive_turn" in s.reasons


@pytest.mark.parametrize("risk", [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM])
def test_ordinary_tool_risk_is_not_destructive(risk):
    s = operation_state(agent_state=AgentState.EXECUTING, turn_risk=risk)
    assert s.destructive_turn is False


def test_risk_may_be_given_as_its_string_value():
    """Callers on the streaming path carry the value, not the enum."""
    assert operation_state(turn_risk="critical").destructive_turn is True
    assert operation_state(turn_risk="low").destructive_turn is False


def test_safe_mode_is_an_incident():
    s = operation_state(safe_mode_active=True)
    assert s.incident_active is True
    assert "operation:incident:safe_mode" in s.reasons


def test_an_open_critical_finding_is_an_incident():
    s = operation_state(open_critical_findings=1)
    assert s.incident_active is True
    assert "operation:incident:critical_finding" in s.reasons


def test_unknown_agent_state_is_treated_as_clear_not_as_busy():
    """Fail open on the *signal*, not on the decision: an unrecognised state
    must not silently suppress everything. The policy fails quiet on its own."""
    s = operation_state(agent_state=None)
    assert s.operation_in_progress is False
    assert s.any_active() is False


def test_reasons_are_stable_keys_never_prose():
    s = operation_state(
        agent_state=AgentState.AWAITING_CONFIRMATION,
        safe_mode_active=True,
        turn_risk=RiskLevel.HIGH,
    )
    for reason in s.reasons:
        assert reason.startswith("operation:")
        assert " " not in reason


def test_state_is_frozen():
    s = operation_state(agent_state=AgentState.IDLE)
    with pytest.raises(Exception):
        s.operation_in_progress = True  # type: ignore[misc]
