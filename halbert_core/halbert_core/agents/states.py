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
    from ..persona.claims import IdentifierClaim
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

    # Model reasoning (thinking) surfaced alongside the response (Phase 2).
    # The text stream carries it tagged ('thinking', text) so the state machine
    # routes it to StreamEvent.thinking rather than response_chunk; it is a
    # streaming affordance, not part of the committed answer, and is not
    # persisted (see the chat-UI design note).
    thinking_chunks: List[str] = field(default_factory=list)
    # monotonic() stamp of the first thinking chunk, for the "Thought for
    # {elapsed}" duration emitted on thinking_complete.
    thinking_started_at: Optional[float] = None
    
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

    # Per-turn model selection from the in-chat picker. These ride on the
    # context — never on the shared LLM adapter — because one adapter instance
    # is shared by every concurrent request, so anything stored on it leaks
    # between sessions.
    #   model_override: an exact model name; bypasses the complexity router
    #                   entirely (Locked Mode).
    #   tier_override:  "guide" | "specialist" | "vision"; forces a tier but
    #                   still resolves the concrete model from models.yml.
    model_override: Optional[str] = None
    tier_override: Optional[str] = None

    # Plan A: hidden threads (spec §4, §7). session_id stays per turn;
    # thread_id is the hidden working buffer this turn's rows belong to.
    thread_id: Optional[str] = None
    continuity_hint: str = ""
    thread_switched: bool = False
    thread_manager: Optional[Any] = None
    recalled_threads: List[Dict[str, Any]] = field(default_factory=list)
    # How many times an inline thread meta-tool has re-entered PLANNING this
    # turn (A9b). Inline meta-tools deliberately do not raise loop_count, so
    # max_loops cannot end a PLANNING→PLANNING chain; this counter does.
    meta_tool_reentries: int = 0
    # Terminal block ids this turn's tools spawned (spawn payloads seen on the
    # terminal bridge); persisted on the assistant row at end_turn. Renamed from
    # terminal_session_ids in Plan B (B21) — the values are now block_ids, not
    # session_ids, but the field name on the store column remains
    # terminal_block_ids.
    terminal_block_ids: List[str] = field(default_factory=list)
    #: block id -> the tool call that ran it. Recorded as the spawn payloads
    #: arrive, because the drain is the one place both ids are in scope, and
    #: handed to end_turn so the stored row can carry the join the timeline
    #: needs after a reload. Only real block ids appear here: a spawn with no
    #: block id falls back to a SESSION id above, which has no row to stamp.
    block_executions: Dict[str, str] = field(default_factory=dict)
    # The ThreadManager.TurnContext for this turn (None when no manager is
    # wired); end_turn needs it back.
    turn_context: Optional[Any] = None

    # Merge-only: the seam between routes/agent.py, _begin_turn and
    # _build_messages. Both are read off the context so the state machine
    # never has to import route or conversation-store code to work them out.
    #   history_budget:       conversation-bucket tokens for this turn,
    #                         resolved by routes/agent.py::_history_budget
    #                         from the answering model and passed through
    #                         process()/confirm_action().
    #   thread_receipt_block: the fitted "## Earlier in this subject" block,
    #                         rendered once in _begin_turn from the receipt
    #                         row ThreadManager prefixed to the thread rows,
    #                         and folded into messages[0].
    history_budget: int = 0
    thread_receipt_block: str = ""

    # Per-turn retrieval scope override. When set, the ContextAssembler uses
    # this scope for SourcePrep retrieval when no active skill provides one.
    # This is how the "Analyze" button hardwires retrieval to a silo's KB
    # scope without defining a full skill.
    retrieval_scope: Optional[str] = None

    # Trust boundary: True once this turn's assembled context was flagged by
    # detect_secure_content (secret content or sensitive provenance). Latched
    # in PLANNING — once True it stays True for the whole turn. The LLM
    # adapter resolves secure turns to a local model only and fails closed
    # when none is configured.
    secure_context: bool = False

    # Auditory cortex: the verified speaker role for this turn. Voice turns
    # set this from speaker_id verification (admin/member/guest/restricted/
    # unknown). Text/chat turns default to "admin" — text chat is already
    # authenticated via the dashboard session. The RoleGate in tools/role_gate
    # uses this to tighten (never loosen) the base safety classification.
    speaker_role: str = "admin"

    # Packet 04 A1 (typed voice ingress): the ingress modality and the
    # speaker CLAIM, not a role grant. A voice turn arrives through the
    # same /api/agent/message door as a typed one, so without these the
    # turn was indistinguishable from dashboard chat and speaker_role
    # silently defaulted to "admin" — RoleGate then treated every spoken
    # command as the owner's. modality is ingress ("text" | "voice" |
    # "terminal" — C5: a turn typed at the machine's terminal surface),
    # defaulting by the same rule as speaker_role: explicit wins, text
    # turns keep today's behavior exactly, voice turns with no identified
    # speaker are "unknown" — never a silent admin default — and terminal
    # turns are admin via the channel's own declaration.
    modality: str = "text"
    # Who the audio pipeline says is speaking (CAM++ match name, "" when
    # unmatched). A name to display and a claim to record — identification
    # failing or absent changes the claim strength, never the role itself.
    speaker_name: Optional[str] = None
    # Where the speaker claim came from ("voice_speaker_verification" for a
    # biometric match, "free_text_name" for a spoken self-identification,
    # None when unverified). Recording only in this packet — mapping to
    # claim strengths and RoleGate enforcement is the permission-system
    # deep pass (PACKET-02 Phase B / A2).
    claim_source: Optional[str] = None
    # Packet 04 A2 / D-6: the derived identifier claim (PACKET-02 strength
    # ladder) for a voice turn — claim_source mapped to a ClaimStrength
    # (voice_speaker_verification→ASSERTED, free_text_name→MUTABLE,
    # unknown/absent→UNVERIFIED), the raw speaker name hashed, never
    # stored. Recorded on the context AND bound for the tool executor
    # (current_turn_claim), which caps the effective role RoleGate hears
    # for a claim below ASSERTED at member-class — the D-6 enforcement.
    # Typed turns leave it None (their identity rides the dashboard
    # session, and the packet's gate is that absent fields change
    # nothing).
    identifier_claim: Optional["IdentifierClaim"] = None

    # Packet 04 B1: the per-turn mutation digest — the rollup of this
    # turn's successful write-plane effects, (tool, redacted target)
    # pairs only, never raw args. Created by process(), read at turn
    # finalize; a voice turn speaks it as a tail and the audit log
    # carries the same line. None only before process() runs.
    turn_digest: Optional[Any] = None

    # Phase 2 modality wiring: the user query with <speech>/<text>/
    # <modality_context> control tags stripped (spec 5.11), resolved in
    # RESPONDING and consumed by _build_messages. It lives here, on the
    # per-turn context, and NOT on the state machine: one machine instance
    # serves every concurrent session, so a defanged query stored on it
    # outlived its turn and was read by the NEXT turn's PLANNING — which then
    # planned against the previous question (REV-06 F1). Same reasoning as
    # model_override/tier_override above.
    defanged_query: Optional[str] = None

    # R-01 Phase D (A07-G10): the turn's own liveness clock. Monotonic,
    # touched at handler entry, at each tool start and completion and on
    # each stream chunk; the turn-liveness watchdog reads it and nothing
    # else. It is the one progress clock for a turn -- a second derived
    # clock is how "stalled" and "working" start disagreeing.
    #
    # The note says WHAT last moved it, which is what a diagnostic line
    # needs: "planning" and "tool:run_command" are different kinds of
    # quiet.
    last_activity: float = field(default_factory=time.monotonic)
    last_activity_note: str = "turn started"

    def touch(self, note: str) -> None:
        """Record that the turn made progress."""
        self.last_activity = time.monotonic()
        self.last_activity_note = note

    def idle_seconds(self) -> float:
        """How long since this turn last made progress."""
        return time.monotonic() - self.last_activity

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
