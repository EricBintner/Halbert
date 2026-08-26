# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Reading State Handler

Handles the READING state: read specific files.
"""

from __future__ import annotations
import uuid
import logging
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine

from ..states import AgentState
from ..events import StreamEvent

logger = logging.getLogger('halbert.agents.handlers.reading')


class ReadingHandler:
    """
    Handles the READING state.
    
    Reads files requested by the LLM and adds content to context.
    """
    
    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent
    
    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Execute reading state logic."""
        ctx = self.agent.ctx
        ctx.loop_count += 1
        
        # Get file path from pending tool
        if not ctx.pending_tool or ctx.pending_tool.get("name") != "read_file":
            logger.warning("Reading state without read_file tool")
            yield self.agent._create_transition_event(AgentState.OBSERVING)
            return
        
        file_path = ctx.pending_tool.get("args", {}).get("path", "")
        
        if not file_path:
            ctx.observations.append("No file path provided for reading")
            ctx.pending_tool = None
            yield self.agent._create_transition_event(AgentState.OBSERVING)
            return
        
        logger.debug(f"Reading file: {file_path}")
        
        # Generate execution ID
        exec_id = str(uuid.uuid4())[:8]
        
        yield StreamEvent.tool_start(
            ctx.session_id,
            "read_file",
            {"path": file_path},
            exec_id
        )
        
        # Execute file read
        result = None
        if self.agent.tool_executor:
            try:
                result = await self.agent.tool_executor.execute(
                    "read_file",
                    {"path": file_path},
                    session_id=ctx.session_id
                )
            except Exception as e:
                logger.error(f"File read error: {e}")
                result = type('Result', (), {'success': False, 'error': str(e), 'result': None})()
        
        # Emit completion event
        yield StreamEvent.tool_complete(
            ctx.session_id,
            exec_id,
            result.success if result else False,
            result.result if result and result.success else None,
            result.error if result and not result.success else None
        )
        
        # Process result
        if result and result.success:
            content = result.result
            
            # Truncate if too long
            if len(content) > 10000:
                content = content[:10000] + "\n... [truncated]"
            
            ctx.observations.append(f"Read {file_path}: {len(content)} chars")
            ctx.retrieved_context.append({
                "source": "file",
                "path": file_path,
                "content": content
            })
        else:
            error_msg = result.error if result else "Unknown error"
            ctx.observations.append(f"Failed to read {file_path}: {error_msg}")
        
        # Clear pending tool
        ctx.pending_tool = None
        
        # Transition to OBSERVING
        yield self.agent._create_transition_event(AgentState.OBSERVING)
