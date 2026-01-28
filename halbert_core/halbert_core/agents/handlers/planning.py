"""
Planning State Handler

Handles the PLANNING state: analyze query, generate plan, decide next action.
Based on research5.md Part 6.1.
"""

from __future__ import annotations
import logging
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine
    from ..states import StateContext

from ..states import AgentState
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
    """
    
    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent
    
    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Execute planning state logic."""
        ctx = self.agent.ctx
        
        logger.debug(f"Planning for: {ctx.user_query[:50]}...")
        
        # Build context
        assembled = None
        if self.agent.context_assembler:
            try:
                assembled = await self.agent.context_assembler.assemble(
                    query=ctx.user_query,
                    conversation=ctx.conversation_history,
                    observations=ctx.observations,
                    max_tokens=8000
                )
                
                yield StreamEvent.context_loaded(
                    ctx.session_id,
                    "assembled",
                    len(assembled.sources) if assembled else 0,
                    assembled.total_tokens if assembled else 0
                )
            except Exception as e:
                logger.warning(f"Context assembly failed: {e}")
        
        # Build planning prompt
        prompt = self._build_planning_prompt(ctx, assembled)
        
        # Call LLM
        response = None
        if self.agent.llm_client:
            try:
                tools = self.agent.tool_executor.get_schemas() if self.agent.tool_executor else None
                response = await self.agent.llm_client.chat(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    tools=tools
                )
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                ctx.error = str(e)
                yield self.agent._create_transition_event(AgentState.ERROR)
                return
        
        # Parse plan from response
        if response and response.plan:
            ctx.plan = response.plan
            yield StreamEvent.plan(ctx.session_id, response.plan)
        
        # CRAG evaluation if we have context
        if ctx.retrieved_context and self.agent.crag_evaluator:
            try:
                crag_result = await self.agent.crag_evaluator.evaluate(
                    ctx.user_query,
                    ctx.retrieved_context,
                    ctx.observations
                )
                ctx.confidence = crag_result.confidence
                ctx.crag_action = crag_result.action.value
                
                yield StreamEvent.confidence_update(
                    ctx.session_id,
                    crag_result.confidence,
                    crag_result.action.value
                )
            except Exception as e:
                logger.warning(f"CRAG evaluation failed: {e}")
        
        # Route based on tool calls or CRAG action
        next_state = self._determine_next_state(response, ctx)
        
        # Store pending tool call if any
        if response and response.tool_calls:
            tool = response.tool_calls[0]
            ctx.pending_tool = {
                "name": tool.function.name,
                "args": tool.function.arguments
            }
            ctx.tool_calls.append(ctx.pending_tool)
        
        yield self.agent._create_transition_event(next_state)
    
    def _build_planning_prompt(self, ctx: 'StateContext', assembled) -> str:
        """Build the planning prompt."""
        parts = [
            "## Current Task",
            f"User request: {ctx.user_query}",
            ""
        ]
        
        # Add assembled context
        if assembled and assembled.content:
            parts.append(assembled.content)
            parts.append("")
        
        # Add previous observations
        if ctx.observations:
            parts.append("## Previous Observations")
            for obs in ctx.observations[-5:]:  # Last 5
                parts.append(f"- {obs}")
            parts.append("")
        
        # Add current plan status
        if ctx.plan:
            parts.append("## Current Plan")
            for i, step in enumerate(ctx.plan):
                status = step.get("status", "pending")
                marker = "✓" if status == "completed" else "○"
                parts.append(f"{marker} {i+1}. {step.get('step', '')}")
            parts.append("")
        
        parts.append("## Instructions")
        parts.append("1. Analyze what information is needed to answer the request")
        parts.append("2. Check if the context already contains the answer")
        parts.append("3. If more information needed, use appropriate tools")
        parts.append("4. If ready to answer, proceed to respond")
        
        return "\n".join(parts)
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for planning."""
        if self.agent.prompt_builder:
            return self.agent.prompt_builder.build_system_prompt()
        
        return """You are Halbert, an AI assistant for Linux system administration.
Analyze the user's request and decide on the best approach.
Use tools when you need more information.
Be helpful, accurate, and concise."""
    
    def _determine_next_state(self, response, ctx: 'StateContext') -> AgentState:
        """Determine next state based on response."""
        # Check for tool calls
        if response and response.tool_calls:
            tool_name = response.tool_calls[0].function.name
            
            if tool_name in ["search", "recall_memory", "web_search"]:
                return AgentState.SEARCHING
            elif tool_name in ["read_file"]:
                return AgentState.READING
            else:
                return AgentState.EXECUTING
        
        # If we've already looped and have no context, just respond
        if ctx.loop_count >= 1 and not ctx.retrieved_context:
            logger.info("No context after loop, responding directly")
            return AgentState.RESPONDING
        
        # Check CRAG action (compare against string values)
        crag_value = ctx.crag_action.value if hasattr(ctx.crag_action, 'value') else ctx.crag_action
        if crag_value == "CORRECT":
            return AgentState.RESPONDING
        elif crag_value == "INCORRECT" and ctx.loop_count < 1:
            # Only search on first iteration
            return AgentState.SEARCHING
        
        # Default: respond with what we have
        return AgentState.RESPONDING
