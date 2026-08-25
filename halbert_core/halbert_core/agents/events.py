"""
Stream Event Definitions

Events emitted during agent processing for real-time frontend updates.
Based on research5.md Part 2.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
import time
import json


@dataclass
class StreamEvent:
    """
    Event emitted during agent processing.
    
    These events are sent via SSE to the frontend to provide
    real-time updates on agent state, tool execution, and responses.
    """
    type: str
    session_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "type": self.type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            **self.data
        }
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        payload = self.to_dict()
        return f"data: {json.dumps(payload)}\n\n"
    
    # -------------------------------------------------------------------------
    # Factory methods for common event types
    # -------------------------------------------------------------------------
    
    @classmethod
    def state_change(
        cls,
        session_id: str,
        new_state: str,
        previous_state: str = None
    ) -> 'StreamEvent':
        """Emit when agent state changes."""
        return cls(
            type="state_change",
            session_id=session_id,
            data={
                "state": new_state,
                "previous_state": previous_state
            }
        )
    
    @classmethod
    def plan(cls, session_id: str, steps: List[Dict]) -> 'StreamEvent':
        """Emit when plan is created or updated."""
        return cls(
            type="plan",
            session_id=session_id,
            data={"steps": steps}
        )
    
    @classmethod
    def plan_step_update(
        cls,
        session_id: str,
        step_index: int,
        status: str
    ) -> 'StreamEvent':
        """Emit when a plan step status changes."""
        return cls(
            type="plan_step_update",
            session_id=session_id,
            data={
                "step_index": step_index,
                "status": status
            }
        )
    
    @classmethod
    def confidence_update(
        cls,
        session_id: str,
        confidence: float,
        crag_action: str
    ) -> 'StreamEvent':
        """Emit when CRAG evaluation completes."""
        return cls(
            type="confidence_update",
            session_id=session_id,
            data={
                "confidence": confidence,
                "crag_action": crag_action
            }
        )
    
    @classmethod
    def context_loaded(
        cls,
        session_id: str,
        source: str,
        count: int,
        tokens: int = 0,
        label: str = None
    ) -> 'StreamEvent':
        """Emit when context is loaded from a source."""
        return cls(
            type="context_loaded",
            session_id=session_id,
            data={
                "source": source,
                "count": count,
                "tokens": tokens,
                "label": label or source
            }
        )
    
    @classmethod
    def scan_start(
        cls,
        session_id: str,
        source: str,
        query: str = None,
        file_count: int = None
    ) -> 'StreamEvent':
        """Emit when agent starts scanning/searching a source."""
        data = {"source": source}
        if query:
            data["query"] = query
        if file_count is not None:
            data["file_count"] = file_count
        return cls(
            type="scan_start",
            session_id=session_id,
            data=data
        )
    
    @classmethod
    def scan_complete(
        cls,
        session_id: str,
        source: str,
        results: int = 0
    ) -> 'StreamEvent':
        """Emit when scan/search completes."""
        return cls(
            type="scan_complete",
            session_id=session_id,
            data={
                "source": source,
                "results": results
            }
        )
    
    @classmethod
    def tool_start(
        cls,
        session_id: str,
        tool: str,
        args: Dict,
        execution_id: str
    ) -> 'StreamEvent':
        """Emit when tool execution starts."""
        return cls(
            type="tool_start",
            session_id=session_id,
            data={
                "tool": tool,
                "args": args,
                "execution_id": execution_id
            }
        )
    
    @classmethod
    def tool_complete(
        cls,
        session_id: str,
        execution_id: str,
        success: bool,
        result: Any = None,
        error: str = None
    ) -> 'StreamEvent':
        """Emit when tool execution completes."""
        return cls(
            type="tool_complete",
            session_id=session_id,
            data={
                "execution_id": execution_id,
                "success": success,
                "result": result,
                "error": error
            }
        )
    
    @classmethod
    def tool_confirmation_required(
        cls,
        session_id: str,
        execution_id: str,
        tool: str,
        description: str,
        risk_level: str
    ) -> 'StreamEvent':
        """Emit when tool requires user confirmation."""
        return cls(
            type="tool_confirmation_required",
            session_id=session_id,
            data={
                "execution_id": execution_id,
                "tool": tool,
                "description": description,
                "risk_level": risk_level
            }
        )
    
    @classmethod
    def response_chunk(cls, session_id: str, content: str) -> 'StreamEvent':
        """Emit a chunk of the streaming response."""
        return cls(
            type="response_chunk",
            session_id=session_id,
            data={"content": content}
        )
    
    @classmethod
    def response_complete(cls, session_id: str) -> 'StreamEvent':
        """Emit when response is complete."""
        return cls(
            type="response_complete",
            session_id=session_id,
            data={}
        )

    @classmethod
    def response_provenance(
        cls, session_id: str, provenance: list
    ) -> 'StreamEvent':
        """Emit provenance refs for the response (Phase 8)."""
        return cls(
            type="response_provenance",
            session_id=session_id,
            data={"provenance": provenance}
        )

    @classmethod
    def module_invoke(
        cls, session_id: str, module: str, props: dict
    ) -> 'StreamEvent':
        """Emit a module invocation event (Phase 8).

        The frontend receives this and renders the module in the
        context region alongside the conversation.
        """
        return cls(
            type="module_invoke",
            session_id=session_id,
            data={"module": module, "props": props}
        )
    
    @classmethod
    def thinking(cls, session_id: str, content: str) -> 'StreamEvent':
        """Emit thinking/reasoning content."""
        return cls(
            type="thinking",
            session_id=session_id,
            data={"content": content}
        )
    
    @classmethod
    def error(cls, session_id: str, message: str, recoverable: bool = True) -> 'StreamEvent':
        """Emit an error event."""
        return cls(
            type="error",
            session_id=session_id,
            data={
                "message": message,
                "recoverable": recoverable
            }
        )
    
    @classmethod
    def loop_warning(
        cls,
        session_id: str,
        loop_count: int,
        max_loops: int
    ) -> 'StreamEvent':
        """Emit warning about loop count."""
        return cls(
            type="loop_warning",
            session_id=session_id,
            data={
                "loop_count": loop_count,
                "max_loops": max_loops
            }
        )
    
    @classmethod
    def session_started(cls, session_id: str, request_id: str) -> 'StreamEvent':
        """Emit when session starts."""
        return cls(
            type="session_started",
            session_id=session_id,
            data={"request_id": request_id}
        )
    
    @classmethod
    def session_ended(
        cls,
        session_id: str,
        duration_ms: int,
        loop_count: int
    ) -> 'StreamEvent':
        """Emit when session ends."""
        return cls(
            type="session_ended",
            session_id=session_id,
            data={
                "duration_ms": duration_ms,
                "loop_count": loop_count
            }
        )
    
    # -------------------------------------------------------------------------
    # Diff/File Change Events (Cascade-style)
    # -------------------------------------------------------------------------
    
    @classmethod
    def diff_proposal(
        cls,
        session_id: str,
        diff_id: str,
        file_path: str,
        new_content: str,
        old_content: str = None,
        additions: int = 0,
        deletions: int = 0
    ) -> 'StreamEvent':
        """Emit when agent proposes a file change."""
        return cls(
            type="diff_proposal",
            session_id=session_id,
            data={
                "diff_id": diff_id,
                "file_path": file_path,
                "new_content": new_content,
                "old_content": old_content,
                "additions": additions,
                "deletions": deletions
            }
        )
    
    @classmethod
    def diff_applied(cls, session_id: str, diff_id: str) -> 'StreamEvent':
        """Emit when user applies a diff."""
        return cls(
            type="diff_applied",
            session_id=session_id,
            data={"diff_id": diff_id}
        )
    
    @classmethod
    def diff_rejected(cls, session_id: str, diff_id: str) -> 'StreamEvent':
        """Emit when user rejects a diff."""
        return cls(
            type="diff_rejected",
            session_id=session_id,
            data={"diff_id": diff_id}
        )
    
    @classmethod
    def cancelled(cls, session_id: str) -> 'StreamEvent':
        """Emit when session is cancelled."""
        return cls(
            type="cancelled",
            session_id=session_id,
            data={"message": "Session cancelled"}
        )

    @classmethod
    def conversation_status(
        cls,
        session_id: str,
        status: Any,
        blocked_action: Optional[Dict[str, Any]] = None,
        waiting_for: Optional[str] = None,
    ) -> 'StreamEvent':
        """Emit a user-facing conversation status change (A2c).

        ``status`` may be a ``ConversationStatus`` enum or its string value.
        Drives the UI's conversation status badge (in_progress / blocked /
        waiting / success / error / cancelled).
        """
        sval = status.value if hasattr(status, "value") else str(status)
        return cls(
            type="conversation_status",
            session_id=session_id,
            data={
                "status": sval,
                "blocked_action": blocked_action,
                "waiting_for": waiting_for,
            },
        )

    @classmethod
    def somatic_block(
        cls,
        session_id: str,
        block_type: str,
        block_id: str,
        status: str,
        **kwargs: Any,
    ) -> 'StreamEvent':
        """Emit a somatic block phase/status change (C1d).

        Drives the UI's somatic-block timeline. Extra fields (finding_id,
        proposal_id, approval_request_id, action_id, reflection_id) are
        passed through as kwargs.
        """
        data = {"block_type": block_type, "block_id": block_id, "status": status}
        data.update(kwargs)
        return cls(type="somatic_block", session_id=session_id, data=data)
    
    @classmethod
    def heartbeat(cls, session_id: str = "system") -> 'StreamEvent':
        """Emit periodic heartbeat to keep connection alive.

        ``session_id`` defaults to ``"system"`` so background heartbeat loops
        (e.g. ``EventEmitter._heartbeat_loop``) can call this with no args.
        """
        return cls(
            type="heartbeat",
            session_id=session_id,
            data={"time": int(time.time())}
        )
