# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Conversation Status Machine (A2a)

Tracks the user-facing conversation status, separate from the internal
``AgentState`` state machine. The UI consumes this to show the user whether
their request is in progress, blocked on approval, waiting on a subagent,
transiently errored (retrying), or finished.

This is a thin tracker — it does NOT drive the agent loop. The agent state
machine calls ``transition()`` at the appropriate seams (approval needed,
subagent spawned, API failure, response complete). See OPUS-HANDOFF §A2a.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from .states import ConversationStatus

logger = logging.getLogger("halbert.agents.conversation_status")

# Allowed transitions: {from_status: {to_status, ...}}
_TRANSITIONS: Dict[ConversationStatus, frozenset] = {
    ConversationStatus.IN_PROGRESS: frozenset({
        ConversationStatus.TRANSIENT_ERROR,
        ConversationStatus.BLOCKED,
        ConversationStatus.WAITING_FOR_EVENTS,
        ConversationStatus.SUCCESS,
        ConversationStatus.CANCELLED,
        ConversationStatus.ERROR,
    }),
    ConversationStatus.TRANSIENT_ERROR: frozenset({
        ConversationStatus.IN_PROGRESS,  # retry
        ConversationStatus.ERROR,        # max retries exhausted
        ConversationStatus.CANCELLED,
    }),
    ConversationStatus.BLOCKED: frozenset({
        ConversationStatus.IN_PROGRESS,   # approval granted
        ConversationStatus.CANCELLED,    # rejected
    }),
    ConversationStatus.WAITING_FOR_EVENTS: frozenset({
        ConversationStatus.IN_PROGRESS,   # subagent completed
        ConversationStatus.CANCELLED,
        ConversationStatus.ERROR,
    }),
    # Terminal states have no outbound transitions
    ConversationStatus.SUCCESS: frozenset(),
    ConversationStatus.ERROR: frozenset(),
    ConversationStatus.CANCELLED: frozenset(),
}


class ConversationStatusMachine:
    """Tracks user-facing conversation status. Separate from AgentStateMachine.

    Holds optional context for the non-terminal waiting states:
    - ``blocked_action``: the action awaiting approval (when BLOCKED)
    - ``waiting_for``: the subagent id being waited on (when WAITING_FOR_EVENTS)
    """

    def __init__(self, initial: ConversationStatus = ConversationStatus.IN_PROGRESS):
        self._status: ConversationStatus = initial
        self._blocked_action: Optional[Dict[str, Any]] = None
        self._waiting_for: Optional[str] = None
        self._retry_count: int = 0

    # ------------------------------------------------------------------
    # Read accessors
    # ------------------------------------------------------------------

    def current(self) -> ConversationStatus:
        """Current conversation status."""
        return self._status

    def blocked_action(self) -> Optional[Dict[str, Any]]:
        """The action awaiting user approval, if BLOCKED; else None."""
        return self._blocked_action

    def waiting_for(self) -> Optional[str]:
        """The subagent id being waited on, if WAITING_FOR_EVENTS; else None."""
        return self._waiting_for

    @property
    def retry_count(self) -> int:
        """Number of transient errors seen so far."""
        return self._retry_count

    def is_terminal(self) -> bool:
        return self._status.is_terminal()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for SSE/UI consumption."""
        return {
            "status": self._status.value,
            "blocked_action": self._blocked_action,
            "waiting_for": self._waiting_for,
            "retry_count": self._retry_count,
            "terminal": self.is_terminal(),
        }

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        new_status: ConversationStatus,
        *,
        blocked_action: Optional[Dict[str, Any]] = None,
        waiting_for: Optional[str] = None,
    ) -> ConversationStatus:
        """Transition to ``new_status`` with optional context.

        Args:
            new_status: Target status.
            blocked_action: The action dict awaiting approval (required
                semantics when entering BLOCKED; cleared on exit).
            waiting_for: The subagent id being awaited (required semantics
                when entering WAITING_FOR_EVENTS; cleared on exit).

        Returns:
            The new status.

        Raises:
            ValueError: If the transition is not allowed from the current
                status (terminal states cannot transition, and only the
                edges in ``_TRANSITIONS`` are valid).
        """
        if new_status == self._status:
            # Idempotent no-op (e.g. IN_PROGRESS → IN_PROGRESS)
            return self._status

        allowed = _TRANSITIONS.get(self._status, frozenset())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid conversation status transition: "
                f"{self._status.value} → {new_status.value}"
            )

        old = self._status
        self._status = new_status

        # Track transient retries (historical count; not reset on recovery)
        if new_status == ConversationStatus.TRANSIENT_ERROR:
            self._retry_count += 1

        # Manage waiting-state context
        if new_status == ConversationStatus.BLOCKED:
            self._blocked_action = blocked_action
        else:
            self._blocked_action = None

        if new_status == ConversationStatus.WAITING_FOR_EVENTS:
            self._waiting_for = waiting_for
        else:
            self._waiting_for = None

        logger.debug(
            f"Conversation status: {old.value} → {new_status.value} "
            f"(blocked_action={self._blocked_action is not None}, "
            f"waiting_for={self._waiting_for})"
        )
        return self._status

    def reset(self) -> None:
        """Reset to IN_PROGRESS and clear all context (new turn)."""
        self._status = ConversationStatus.IN_PROGRESS
        self._blocked_action = None
        self._waiting_for = None
        self._retry_count = 0
