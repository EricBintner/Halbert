"""
Executing State Handler

Handles the EXECUTING state: execute tool calls with safety checks.
Supports Cascade-style diff proposals for file write operations.
"""

from __future__ import annotations
import uuid
import logging
import os
from typing import AsyncIterator, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state_machine import AgentStateMachine

from ..states import AgentState
from ..events import StreamEvent

logger = logging.getLogger('halbert.agents.handlers.executing')

# Tools that write files and should emit diff proposals
FILE_WRITE_TOOLS = {'write_file', 'edit_file', 'create_file', 'patch_file'}


class ExecutingHandler:
    """
    Handles the EXECUTING state.
    
    Executes tool calls with:
    - Safety classification
    - Confirmation for high-risk operations
    - Timeout handling
    - Result capture
    """
    
    def __init__(self, agent: 'AgentStateMachine'):
        self.agent = agent
    
    async def handle(self) -> AsyncIterator[StreamEvent]:
        """Execute executing state logic."""
        ctx = self.agent.ctx
        ctx.loop_count += 1
        
        # Get pending tool
        if not ctx.pending_tool:
            logger.warning("Executing state without pending tool")
            yield self.agent._create_transition_event(AgentState.OBSERVING)
            return
        
        tool_name = ctx.pending_tool.get("name", "")
        tool_args = ctx.pending_tool.get("args", {})
        
        logger.debug(f"Executing tool: {tool_name}")
        
        # Generate execution ID
        exec_id = str(uuid.uuid4())[:8]
        
        yield StreamEvent.tool_start(
            ctx.session_id,
            tool_name,
            tool_args,
            exec_id
        )
        
        # Check if this is a file write tool - emit diff proposal instead of executing
        if tool_name in FILE_WRITE_TOOLS:
            async for event in self._handle_file_write(ctx, tool_name, tool_args, exec_id):
                yield event
            return
        
        # Check if already confirmed
        confirmed = ctx.pending_tool.get("confirmed", False)
        
        # Execute tool
        result = None
        if self.agent.tool_executor:
            try:
                result = await self.agent.tool_executor.execute(
                    tool_name,
                    tool_args,
                    session_id=ctx.session_id,
                    confirmed=confirmed
                )
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                result = type('Result', (), {
                    'success': False,
                    'error': str(e),
                    'result': None,
                    'requires_confirmation': False,
                    'risk_level': None
                })()
        
        # Check if confirmation required
        if result and result.requires_confirmation:
            ctx.pending_confirmation = {
                "action_id": exec_id,
                "tool": tool_name,
                "args": tool_args,
                "description": getattr(result, 'confirmation_message', f"Execute {tool_name}"),
                "risk_level": result.risk_level.value if result.risk_level else "medium"
            }
            
            yield StreamEvent.confirmation_required(
                ctx.session_id,
                exec_id,
                tool_name,
                ctx.pending_confirmation["description"],
                ctx.pending_confirmation["risk_level"]
            )
            
            yield self.agent._create_transition_event(AgentState.AWAITING_CONFIRMATION)
            return
        
        # Emit completion event
        yield StreamEvent.tool_complete(
            ctx.session_id,
            exec_id,
            result.success if result else False,
            result.result if result and result.success else None,
            result.error if result and not result.success else None
        )
        
        # Record observation
        if result and result.success:
            result_preview = str(result.result)[:200] if result.result else "completed"
            ctx.observations.append(f"Executed {tool_name}: {result_preview}")
        else:
            error_msg = result.error if result else "Unknown error"
            ctx.observations.append(f"Failed {tool_name}: {error_msg}")
        
        # Clear pending tool
        ctx.pending_tool = None
        
        # Transition to OBSERVING
        yield self.agent._create_transition_event(AgentState.OBSERVING)
    
    async def _handle_file_write(self, ctx, tool_name: str, tool_args: dict, exec_id: str) -> AsyncIterator[StreamEvent]:
        """
        Handle file write tools by emitting diff proposals instead of immediate execution.
        
        This implements Cascade-style "I have prepared this change. May I write it?"
        """
        file_path = tool_args.get('path') or tool_args.get('file_path') or tool_args.get('filename', '')
        new_content = tool_args.get('content', '')
        
        # Try to read existing content for diff
        old_content = None
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    old_content = f.read()
            except Exception as e:
                logger.debug(f"Could not read existing file: {e}")
        
        # Calculate additions/deletions
        old_lines = old_content.split('\n') if old_content else []
        new_lines = new_content.split('\n') if new_content else []
        additions = max(0, len(new_lines) - len(old_lines))
        deletions = max(0, len(old_lines) - len(new_lines))
        
        # Generate diff ID
        diff_id = f"diff-{exec_id}"
        
        # Store in pending_diffs
        ctx.pending_diffs[diff_id] = {
            'file_path': file_path,
            'old_content': old_content,
            'new_content': new_content,
            'additions': additions,
            'deletions': deletions,
            'status': 'pending',
            'tool_name': tool_name,
            'exec_id': exec_id
        }
        
        # Emit diff proposal event
        yield StreamEvent.diff_proposal(
            ctx.session_id,
            diff_id,
            file_path,
            new_content,
            old_content,
            additions,
            deletions
        )
        
        # Mark tool as complete (diff proposed, waiting for user action)
        yield StreamEvent.tool_complete(
            ctx.session_id,
            exec_id,
            True,
            f"Diff proposed for {file_path}",
            None
        )
        
        # Add observation
        ctx.observations.append(f"Proposed file change: {file_path} (+{additions}/-{deletions})")
        
        # Clear pending tool
        ctx.pending_tool = None
        
        # Transition to OBSERVING
        yield self.agent._create_transition_event(AgentState.OBSERVING)
