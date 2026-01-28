"""
Agent State Definitions

Defines the state machine states and context for the agentic workflow.
Based on research5.md Part 2.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time


class AgentState(Enum):
    """Possible states for the agent state machine."""
    IDLE = "idle"
    PLANNING = "planning"
    SEARCHING = "searching"
    READING = "reading"
    EXECUTING = "executing"
    OBSERVING = "observing"
    RESPONDING = "responding"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ERROR = "error"


class CRAGAction(Enum):
    """CRAG evaluator actions."""
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    AMBIGUOUS = "AMBIGUOUS"
    PENDING = "PENDING"


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
        return {
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
