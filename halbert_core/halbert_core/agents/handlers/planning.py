"""
Planning State Handler

Handles the PLANNING state: analyze query, generate plan, decide next action.
Based on research5.md Part 6.1.

NOTE: Context assembly happens exactly once — in
``AgentStateMachine._handle_planning`` — where ``assemble(intake=...)`` lets
the intake pipeline own the token budget. This class used to duplicate that
assembly (with a hardcoded max_tokens=8000 that intake then overrode); it now
delegates to the state machine's single planning path.
"""

from __future__ import annotations
import logging
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine

from ..events import StreamEvent

logger = logging.getLogger('halbert.agents.handlers.planning')


class PlanningHandler:
    """
    Handles the PLANNING state.

    Responsibilities:
    - Build prompt with assembled context
    - Call LLM to analyze and plan
    - Parse tool calls from response
    - Evaluate context with CRAG
    - Route to appropriate next state

    The actual implementation lives on AgentStateMachine._handle_planning
    (the state machine invokes its own handlers); this class is kept as a
    thin delegate so the exported handler surface stays intact while there
    is only one planning/context-assembly code path.
    """

    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent

    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Delegate to the state machine's single planning implementation."""
        async for event in self.agent._handle_planning():
            yield event
