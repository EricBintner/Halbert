# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agent State Definitions

Defines the state machine states and context for the agentic workflow.
Based on research5.md Part 2.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
import time

from .blocks import TextBlock, ToolUseBlock, ToolResultBlock

if TYPE_CHECKING:
    from ..intake import MessageIntake
    from .conversation_status import ConversationStatusMachine


def _new_conversation_status() -> "ConversationStatusMachine":
    """Lazy factory for the conversation status machine (avoids a circular
    import: conversation_status.py imports ConversationStatus from states)."""
    from .conversation_status import ConversationStatusMachine
    return ConversationStatusMachine()


class AgentState(Enum):
    """Possible states for the agent state machine."""
    IDLE = "idle"
    PLANNING = "planning"
    SEARCHING = "searching"
    READING = "reading"
    EXECUTING = "executing"
    OBSERVING = "observing"
    REFLECTING = "reflecting"  # Phase D: cognitive tick (advance_turn)
    RESPONDING = "responding"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ERROR = "error"


class CRAGAction(Enum):
    """CRAG evaluator actions."""
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    AMBIGUOUS = "AMBIGUOUS"
    PENDING = "PENDING"


class ConversationStatus(Enum):
    """User-facing conversation status (A2a).

    Separate from the internal ``AgentState`` machine. This is the status the
    UI shows the user. Terminal states are SUCCESS, ERROR, CANCELLED; all
    others are non-terminal and the conversation can resume from them.
    """
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    ERROR = "error"
    TRANSIENT_ERROR = "transient_error"   # API failure, will retry
    CANCELLED = "cancelled"
    BLOCKED = "blocked"                    # Waiting for user approval
    WAITING_FOR_EVENTS = "waiting_for_events"  # Waiting for subagent

    @classmethod
    def terminal(cls) -> tuple:
        """Return the terminal statuses (no further transitions)."""
        return (cls.SUCCESS, cls.ERROR, cls.CANCELLED)

    def is_terminal(self) -> bool:
        return self in self.terminal()


@dataclass
class PlanStep:
    """A single step in the agent's plan."""
    step: str
    tool: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed, failed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "tool": self.tool,
            "status": self.status
        }


@dataclass
class ToolCall:
    """Record of a tool call."""
    id: str
    name: str
    args: Dict[str, Any]
    status: str = "pending"  # pending, running, success, error
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "args": self.args,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "duration_ms": int((self.completed_at - self.started_at) * 1000) 
                if self.completed_at and self.started_at else None
        }


@dataclass
class StateContext:
    """
    Context maintained throughout a request lifecycle.
    
    This is the "scratchpad" that accumulates information
    as the agent processes a request through multiple states.
    """
    session_id: str
    request_id: str
    user_query: str
    user_id: Optional[str] = None
    
    # Conversation
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)

    # User-facing conversation status (A2c), separate from AgentState
    conversation_status: "ConversationStatusMachine" = field(
        default_factory=_new_conversation_status
    )

    # Somatic block currently active for this turn (C1d); None when no somatic
    # cycle is in progress.
    current_somatic_block_id: Optional[str] = None

    # Subagent currently being awaited (D1d); None when no subagent is pending.
    current_subagent_handle_id: Optional[str] = None
    
    # Planning
    plan: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    
    # Retrieval
    retrieved_context: List[Dict[str, Any]] = field(default_factory=list)
    
    # Execution
    tool_calls: List[ToolCall] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    
    # Pending confirmation (for high-risk actions)
    pending_confirmation: Optional[Dict[str, Any]] = None
    
    # Pending diffs (Cascade-style file change proposals)
    pending_diffs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Pending tool for state continuation
    pending_tool: Optional[Dict[str, Any]] = None
    
    # Evaluation
    confidence: float = 0.0
    crag_action: CRAGAction = CRAGAction.PENDING
    
    # Control
    loop_count: int = 0
    max_loops: int = 5
    state_history: List[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    error_recovery_attempts: int = 0
    
    # Error
    error: Optional[str] = None
    
    # Output
    response_chunks: List[str] = field(default_factory=list)
    
    # Phase D: Persona cognition (Haloysius cognitive state)
    persona_cognition: Optional[Any] = None  # PersonaCognition instance
    persona_id: str = "halbert"
    # Set once the Haloysius cognitive tick has run for this turn, so the
    # REFLECTING and RESPONDING seams never double-tick (B1).
    cognition_ticked: bool = False

    # Phase 3: Intake pipeline result (message analysis before cognitive tick)
    intake: Optional[MessageIntake] = None

    # Phase 4: Vision/image attachments (base64-encoded)
    images: Optional[List[str]] = None

    # Plan A: hidden threads (spec §4, §7). session_id stays per turn;
    # thread_id is the hidden working buffer this turn's rows belong to.
    thread_id: Optional[str] = None
    continuity_hint: str = ""
    thread_switched: bool = False
    thread_manager: Optional[Any] = None
    recalled_threads: List[Dict[str, Any]] = field(default_factory=list)
    # Terminal sessions this turn's tools spawned (spawn payloads seen on the
    # terminal bridge); persisted on the assistant row at end_turn.
    terminal_session_ids: List[str] = field(default_factory=list)
    # The ThreadManager.TurnContext for this turn (None when no manager is
    # wired); end_turn needs it back.
    turn_context: Optional[Any] = None

    def add_observation(self, observation: str):
        """Add an observation from tool execution."""
        self.observations.append(observation)
    
    def add_tool_call(self, tool_call: ToolCall):
        """Add a tool call record."""
        self.tool_calls.append(tool_call)
    
    def add_context(self, source: str, content: str, metadata: Dict = None):
        """Add retrieved context."""
        self.retrieved_context.append({
            "source": source,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time()
        })

    # -------------------------------------------------------------------------
    # Block-typed conversation history (A1)
    # -------------------------------------------------------------------------

    def add_text_block(self, role: str, text: str) -> None:
        """Append a message whose content is a single text block.

        ``role`` is ``"user"`` or ``"assistant"``.
        """
        self.conversation_history.append(
            {"role": role, "content": [TextBlock(text=text)]}
        )

    def add_tool_use_block(
        self, tool_id: str, name: str, args: Dict[str, Any]
    ) -> None:
        """Record a model-emitted tool call as a block on the assistant turn.

        If the last message is an assistant turn already carrying block-typed
        content, the tool-use block is appended to it; otherwise a new
        assistant message is started. This mirrors the Anthropic API, where a
        single assistant turn may contain text + one or more tool_use blocks.
        """
        if (
            self.conversation_history
            and self.conversation_history[-1].get("role") == "assistant"
            and isinstance(self.conversation_history[-1].get("content"), list)
        ):
            self.conversation_history[-1]["content"].append(
                ToolUseBlock(id=tool_id, name=name, input=args or {})
            )
        else:
            self.conversation_history.append({
                "role": "assistant",
                "content": [ToolUseBlock(id=tool_id, name=name, input=args or {})],
            })

    def add_tool_result_block(
        self, tool_use_id: str, result: Any, is_error: bool = False
    ) -> None:
        """Append a user message carrying a tool_result block.

        Tool results are role ``"user"`` per the Anthropic API convention.
        ``result`` is coerced to a string.
        """
        self.conversation_history.append({
            "role": "user",
            "content": [
                ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=result if isinstance(result, str) else str(result),
                    is_error=is_error,
                )
            ],
        })
    
    def get_current_plan_step(self) -> Optional[PlanStep]:
        """Get the current plan step."""
        if 0 <= self.current_step < len(self.plan):
            return self.plan[self.current_step]
        return None
    
    def advance_plan(self):
        """Mark current step complete and advance."""
        if self.get_current_plan_step():
            self.plan[self.current_step].status = "completed"
        self.current_step += 1
    
    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds."""
        return int((time.time() - self.started_at) * 1000)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        result = {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "user_query": self.user_query,
            "plan": [p.to_dict() for p in self.plan],
            "current_step": self.current_step,
            "loop_count": self.loop_count,
            "confidence": self.confidence,
            "crag_action": self.crag_action.value,
            "state_history": self.state_history,
            "elapsed_ms": self.elapsed_ms(),
            "error": self.error
        }
        if self.persona_cognition is not None:
            try:
                result["persona_cognition"] = self.persona_cognition.get_full_context()
            except Exception:
                result["persona_cognition"] = {"persona_id": self.persona_id}
        return result
