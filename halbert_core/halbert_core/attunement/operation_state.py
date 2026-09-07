# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""What the machine is doing with the user right now (A-HB-1, HB-N1).

The engine's receptivity table scores a person in a room: arriving, doing
chores, on a call. For a sysadmin persona the dominant interruption cost is
not environmental at all — it is *self-inflicted*. A person alone at a desk,
arrived twenty minutes ago, scores well on every environmental term while
being two seconds from confirming ``mkfs`` on the wrong device because we
asked.

This is the same predicate the observation-lenses suppression gate (B4)
needs. It is computed once, here, so the two cannot drift.

The function is pure: callers pass resolved primitives, not live objects, so
it is cheap enough for the always-on path and testable without an agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

#: Risk levels at which a turn counts as destructive. Mirrors
#: ``tools.safety.RiskLevel``; compared by value so callers may pass either
#: the enum or the string that reaches the streaming layer.
_DESTRUCTIVE_RISK = frozenset({"high", "critical"})

#: Agent states in which a turn is in flight on the user's behalf. IDLE and
#: ERROR are not; AWAITING_CONFIRMATION is, but carries its own stronger flag.
_IN_FLIGHT_STATES = frozenset(
    {"planning", "searching", "reading", "executing", "observing",
     "reflecting", "responding", "awaiting_confirmation"}
)


@dataclass(frozen=True)
class OperationState:
    """What the persona is in the middle of, from the user's point of view."""

    awaiting_user_confirmation: bool = False
    """A turn is paused holding a confirmation. The most interruption-hostile
    state this product has: the user is reading a question we asked."""

    operation_in_progress: bool = False
    """A turn is in flight on the user's behalf."""

    destructive_turn: bool = False
    """This turn classified at HIGH or CRITICAL tool risk."""

    incident_active: bool = False
    """Safe mode, or an open critical finding."""

    reasons: Tuple[str, ...] = field(default_factory=tuple)
    """Stable keys, never prose — they reach the engine's decision reasons and
    from there the user-facing *why*."""

    def any_active(self) -> bool:
        """True when any operation-shaped condition holds."""
        return (
            self.awaiting_user_confirmation
            or self.operation_in_progress
            or self.destructive_turn
            or self.incident_active
        )


def _risk_value(turn_risk: Any) -> Optional[str]:
    """Normalise a RiskLevel, a bare string, or None to a comparable value."""
    if turn_risk is None:
        return None
    value = getattr(turn_risk, "value", turn_risk)
    return str(value).lower()


def _state_value(agent_state: Any) -> Optional[str]:
    if agent_state is None:
        return None
    value = getattr(agent_state, "value", agent_state)
    return str(value).lower()


def operation_state(
    *,
    agent_state: Any = None,
    turn_risk: Any = None,
    safe_mode_active: bool = False,
    open_critical_findings: int = 0,
) -> OperationState:
    """Classify the persona's current operational posture.

    Args:
        agent_state: ``AgentState`` or its value; None when no turn is running.
        turn_risk: ``RiskLevel`` or its value for the highest-risk tool call
            classified this turn.
        safe_mode_active: ``GuardrailEnforcer.safe_mode_active``.
        open_critical_findings: count from ``FindingStore``.

    An unrecognised state is treated as *clear*, not as busy. Failing open on
    a signal is right; the policy fails quiet on the decision, which is where
    that conservatism belongs.
    """
    reasons: list[str] = []

    state = _state_value(agent_state)
    awaiting = state == "awaiting_confirmation"
    in_flight = state in _IN_FLIGHT_STATES

    if awaiting:
        reasons.append("operation:awaiting_confirmation")
    if in_flight:
        reasons.append("operation:in_flight")

    risk = _risk_value(turn_risk)
    destructive = risk in _DESTRUCTIVE_RISK
    if destructive:
        reasons.append("operation:destructive_turn")

    incident = False
    if safe_mode_active:
        incident = True
        reasons.append("operation:incident:safe_mode")
    if open_critical_findings > 0:
        incident = True
        reasons.append("operation:incident:critical_finding")

    return OperationState(
        awaiting_user_confirmation=awaiting,
        operation_in_progress=in_flight,
        destructive_turn=destructive,
        incident_active=incident,
        reasons=tuple(reasons),
    )
