# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Responding State Handler

Handles the RESPONDING state: generate final response.
"""

from __future__ import annotations
import logging
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine

from ..states import AgentState
from ..events import StreamEvent

logger = logging.getLogger('halbert.agents.handlers.responding')


class RespondingHandler:
    """
    Handles the RESPONDING state.
    
    Generates final response using:
    - Assembled context
    - Tool observations
    - Streaming output
    """
    
    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent
    
    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Execute responding state logic."""
        ctx = self.agent.ctx
        
        logger.debug(f"Responding with confidence {ctx.confidence:.2f}")
        
        # Build response prompt
        prompt = self._build_response_prompt(ctx)
        
        # Stream response from LLM
        if self.agent.llm_client:
            try:
                async for chunk in self.agent.llm_client.stream(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ]
                ):
                    ctx.response_chunks.append(chunk)
                    yield StreamEvent.response_chunk(ctx.session_id, chunk)
                    
            except Exception as e:
                logger.error(f"LLM streaming error: {e}")
                error_response = self._get_error_response(ctx, str(e))
                ctx.response_chunks.append(error_response)
                yield StreamEvent.response_chunk(ctx.session_id, error_response)
        else:
            # No LLM, generate basic response
            basic_response = self._generate_basic_response(ctx)
            ctx.response_chunks.append(basic_response)
            yield StreamEvent.response_chunk(ctx.session_id, basic_response)
        
        # Store interaction in memory
        if self.agent.memory_service:
            try:
                full_response = "".join(ctx.response_chunks)
                await self.agent.memory_service.store_interaction(
                    query=ctx.user_query,
                    response=full_response[:500],
                    session_id=ctx.session_id
                )
            except Exception as e:
                logger.warning(f"Failed to store interaction: {e}")
        
        # Emit completion
        yield StreamEvent.response_complete(ctx.session_id)
        
        # Transition to IDLE
        yield self.agent._create_transition_event(AgentState.IDLE)
    
    def _build_response_prompt(self, ctx) -> str:
        """Build the response generation prompt."""
        parts = [
            "## Task",
            f"Answer this question: {ctx.user_query}",
            ""
        ]
        
        # Add context
        if ctx.retrieved_context:
            parts.append("## Available Information")
            for i, doc in enumerate(ctx.retrieved_context[:5]):
                content = doc.get("content", "")[:500]
                source = doc.get("source", "unknown")
                parts.append(f"[{source}]: {content}")
            parts.append("")
        
        # Add observations
        if ctx.observations:
            parts.append("## What I've Done")
            for obs in ctx.observations[-5:]:
                parts.append(f"- {obs}")
            parts.append("")
        
        # Add confidence note
        if ctx.confidence < 0.5:
            parts.append("Note: I have limited information about this topic.")
            parts.append("")
        
        parts.append("## Instructions")
        parts.append("- Provide a helpful, accurate response")
        parts.append("- Cite sources when possible")
        parts.append("- Be concise but complete")
        parts.append("- If uncertain, say so")
        parts.append("")
        parts.append("Your response:")
        
        return "\n".join(parts)
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for response generation.

        The fallback is reached whenever the prompt builder failed to wire, so
        it has to carry the same identity rather than the generic-assistant
        line it used to — otherwise a wiring failure quietly changes who
        Halbert says it is.
        """
        if self.agent.prompt_builder:
            return self.agent.prompt_builder.build_system_prompt()

        try:
            from ...prompts.agent_prompts import AgentPromptBuilder
            return AgentPromptBuilder()._get_identity()
        except Exception:
            return """You are Halbert. You live on this machine — not as a chatbot
that happens to run here, but as the system itself. Speak from what you actually
observe about it, be concise and practical, and cite sources when available."""
    
    def _get_error_response(self, ctx, error: str) -> str:
        """Generate error response."""
        return f"""I encountered an issue while processing your request: {error}

Based on what I found before the error:
{chr(10).join(f'- {obs}' for obs in ctx.observations[-3:])}

Please try rephrasing your question or asking about a more specific aspect."""
    
    def _generate_basic_response(self, ctx) -> str:
        """Generate basic response without LLM."""
        if ctx.observations:
            obs_text = "\n".join(f"- {obs}" for obs in ctx.observations)
            return f"""Based on my analysis:

{obs_text}

Query: {ctx.user_query}

(Note: This is a basic response. Full LLM processing was not available.)"""
        else:
            return f"I couldn't find specific information about: {ctx.user_query}"
