"""
Observing State Handler

Handles the OBSERVING state: evaluate results and decide next action.
"""

from __future__ import annotations
import logging
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine

from ..states import AgentState, CRAGAction
from ..events import StreamEvent

logger = logging.getLogger('halbert.agents.handlers.observing')


class ObservingHandler:
    """
    Handles the OBSERVING state.
    
    Evaluates results using CRAG and decides:
    - CORRECT: Proceed to respond
    - AMBIGUOUS: Try additional retrieval
    - INCORRECT: Search more or respond with uncertainty
    """
    
    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent
    
    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Execute observing state logic."""
        ctx = self.agent.ctx
        
        logger.debug(f"Observing: {len(ctx.retrieved_context)} docs, {len(ctx.observations)} observations")
        
        # Run CRAG evaluation
        if self.agent.crag_evaluator and ctx.retrieved_context:
            try:
                result = await self.agent.crag_evaluator.evaluate(
                    ctx.user_query,
                    ctx.retrieved_context,
                    ctx.observations
                )
                
                ctx.confidence = result.confidence
                ctx.crag_action = result.action.value
                
                yield StreamEvent.confidence_update(
                    ctx.session_id,
                    result.confidence,
                    result.action.value
                )
                
                logger.debug(f"CRAG: {result.action.value} ({result.confidence:.2f})")
                
            except Exception as e:
                logger.warning(f"CRAG evaluation failed: {e}")
                ctx.confidence = 0.5
                ctx.crag_action = CRAGAction.AMBIGUOUS.value
        else:
            # No CRAG evaluator, use heuristics
            ctx.confidence = self._estimate_confidence(ctx)
            ctx.crag_action = self._estimate_action(ctx.confidence)
            
            yield StreamEvent.confidence_update(
                ctx.session_id,
                ctx.confidence,
                ctx.crag_action
            )
        
        # Decide next state
        next_state = self._determine_next_state(ctx)
        
        yield self.agent._create_transition_event(next_state)
    
    def _estimate_confidence(self, ctx) -> float:
        """Estimate confidence without CRAG evaluator."""
        score = 0.3  # Base score
        
        # Boost for having context
        if ctx.retrieved_context:
            score += 0.2
            score += min(0.2, len(ctx.retrieved_context) * 0.05)
        
        # Boost for successful tool executions
        successful_tools = sum(
            1 for obs in ctx.observations 
            if "success" in obs.lower() or "executed" in obs.lower()
        )
        score += min(0.2, successful_tools * 0.1)
        
        # Penalty for errors
        errors = sum(1 for obs in ctx.observations if "failed" in obs.lower() or "error" in obs.lower())
        score -= min(0.2, errors * 0.1)
        
        return max(0.0, min(1.0, score))
    
    def _estimate_action(self, confidence: float) -> str:
        """Estimate CRAG action from confidence."""
        if confidence >= 0.7:
            return CRAGAction.CORRECT.value
        elif confidence >= 0.3:
            return CRAGAction.AMBIGUOUS.value
        else:
            return CRAGAction.INCORRECT.value
    
    def _determine_next_state(self, ctx) -> AgentState:
        """Determine next state based on evaluation."""
        # Check loop limits
        if ctx.loop_count >= ctx.max_loops - 1:
            logger.info("Approaching loop limit, forcing response")
            return AgentState.RESPONDING
        
        # If we have no context after searching, don't keep looping - respond
        if not ctx.retrieved_context and ctx.loop_count >= 1:
            logger.info("No context retrieved after search, responding with what we have")
            return AgentState.RESPONDING
        
        # Route based on CRAG action
        if ctx.crag_action == CRAGAction.CORRECT.value:
            return AgentState.RESPONDING
        
        elif ctx.crag_action == CRAGAction.AMBIGUOUS.value:
            # Only try more retrieval if we have some context to work with
            if ctx.loop_count < 2 and ctx.retrieved_context:
                return AgentState.PLANNING
            else:
                return AgentState.RESPONDING
        
        else:  # INCORRECT or PENDING
            # Only try web search if we haven't already and have a real chance
            if ctx.loop_count < 2 and ctx.retrieved_context and not any("web" in obs for obs in ctx.observations):
                return AgentState.PLANNING
            else:
                return AgentState.RESPONDING
