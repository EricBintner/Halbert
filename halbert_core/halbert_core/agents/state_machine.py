# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agent State Machine

Core orchestration using a state machine pattern with CRAG evaluation.
Based on research5.md Part 6.
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from typing import AsyncIterator, Dict, List, Optional, Callable, Any, TYPE_CHECKING

from .blocks import content_to_text
from .states import AgentState, StateContext, CRAGAction, ToolCall, PlanStep, ConversationStatus
from .events import StreamEvent
from .steering import (
    STEER_MARKER,
    STEER_MARKER_CLOSE,
    Decision,
    Verdict,
    apply_steer_to_results,
    decide_midturn,
)
from .turn_activity import TurnActivity
from ..streaming.terminal_bridge import get_terminal_event_bus
from ..tools.safety import THREAD_META_TOOLS

if TYPE_CHECKING:
    from ..tools.safety import ToolSafetyFramework
    from ..tools.executor import ToolExecutor

logger = logging.getLogger('halbert.agents.state_machine')


# Subagent lifecycle statuses that end waiting (D1d)
_SUBAGENT_TERMINAL = {"completed", "failed", "cancelled"}


def _subagent_terminal(status: str) -> bool:
    return status in _SUBAGENT_TERMINAL


# Tool output is dropped into the observation list, which the context assembler
# budgets and may truncate again. This cap just stops one `cat` of a big file
# from crowding out everything else before that budgeting happens.
_TOOL_RESULT_CHARS = 2000

# Per-receipt ceiling for the recalled-subjects block appended to the PLANNING
# prompt. Tighter than RESPONDING's (which renders a receipt whole, up to
# threads.RECEIPT_ROW_MAX): the block is appended after the assembler has
# already spent its budget, so it is overspend by construction, and PLANNING
# only has to decide whether an earlier subject is worth searching or
# answering from — the whole receipt still reaches the answer prompt.
_PLANNING_RECEIPT_CHARS = 700


def _recalled_block_name() -> str:
    """The name of the prompt block the recalled receipts are rendered in.

    recall_thread's observation points the model at that block, so the name is
    read from the renderer's own header rather than typed twice: reworded on
    one side only, the sentence would send the model looking for a section
    that no longer exists — the failure this whole fix is about.
    """
    try:
        from ..prompts.agent_prompts import RECALLED_SECTION_HEADER
    except Exception:  # pragma: no cover - import cycle guard
        return "Earlier subjects recalled"
    return RECALLED_SECTION_HEADER.lstrip("#").strip()


def _merge_adjacent(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fold consecutive same-role messages into one.

    A turn that was cancelled before it answered leaves a user message with no
    assistant reply, so the next turn would send two user messages in a row —
    which some providers reject outright.
    """
    merged: List[Dict[str, Any]] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] = merged[-1]["content"] + "\n\n" + msg["content"]
            continue
        merged.append(dict(msg))
    return merged


def _defang_system_row(text: str) -> str:
    """One history row's text, neutralised for the instructions it folds into.

    ``_build_messages`` concatenates any non-user/assistant row straight into
    ``messages[0]``. That text is untrusted — a thread receipt is built from
    command stdout, file names and log lines — and in that position an
    unfenced ``</continuity>`` or a line starting ``##`` reads as a prompt
    delimiter or a section heading the admin never wrote. Plan A closed that
    hole inside ``_history_section``; the array replaced the call site, so the
    fence moves here rather than disappearing.

    The cap is the thread receipt's own producer-side ceiling
    (``threads.RECEIPT_ROW_MAX``), so the bounded scan matches the row this
    actually guards. Failure to import the builder is not a reason to send the
    text through unguarded, so the raw ``<continuity>`` tags are stripped
    inline as a floor.

    THE CAP IS APPLIED HERE, not left to the defanger. ``defang_system_text``
    clips its input to ``max(_DEFANG_SCAN_MIN, cap * _DEFANG_SCAN_FACTOR)``
    before its fixpoint loop, which bounds that loop's cost on a pathological
    row — but it is a scan bound, not a policy, and its own docstring says so:
    "A producer that stops bounding its rows needs a cap at the fold, not a
    bigger scan window here." Without one, this position inherited the scan
    bound as a silent truncation at 6000 characters.

    That matters because of where the text lands. Every other row in the array
    is spent against the conversation budget by ``build_conversation_window``;
    this one is concatenated onto ``messages[0]`` ahead of the instructions,
    outside any budget, at whatever length the store hands over. Today nothing
    reaches the ceiling — ``threads.py::_fence`` bounds the receipt and the
    soft-landing note to ``RECEIPT_ROW_MAX`` — but "bounded because every
    current producer happens to bound itself" is not a property this position
    should rely on.

    The shape is ``_fence``'s, deliberately: cut one character short and mark
    the cut, so a truncated row is distinguishable from a complete one by
    anyone reading the prompt back.
    """
    text = str(text)
    try:
        from ..prompts.agent_prompts import defang_system_text
        from .threads import RECEIPT_ROW_MAX
    except Exception:  # pragma: no cover - import cycle guard
        return re.sub(r"</?\s*continuity\s*>", " ", text, flags=re.IGNORECASE)
    fenced = defang_system_text(text, RECEIPT_ROW_MAX)
    if len(fenced) <= RECEIPT_ROW_MAX:
        return fenced
    return fenced[: RECEIPT_ROW_MAX - 1].rstrip() + "\u2026"


class TurnStopped(Exception):
    """A step abandoned itself because the turn was stopped (A07-G5).

    Raised from inside a long step -- an in-flight model request -- when
    ``self.cancelled`` goes up. ``_drive`` catches it as the stop it is
    (a ``cancelled`` event and a return), rather than the handler error
    the generic ``except Exception`` would have made of it.
    """


def _unverified_claim():
    """The claim a turn carries when the ladder could not derive one.

    R-01 Phase A (A12 bug 1). ``None`` is not "a weak claim" -- it is no
    claim at all, and no claim means the executor's voice ceiling never
    runs, so a derivation *failure* left the stated role standing
    uncapped. UNVERIFIED is the ladder's own fail-closed reading of an
    unknown source; a failure to reach the ladder gets the same answer.
    """
    from ..persona.claims import ClaimStrength, IdentifierClaim
    return IdentifierClaim(kind="speaker", strength=ClaimStrength.UNVERIFIED)


def _default_conversation_tokens() -> int:
    """The conversation bucket a turn gets when the route did not name one.

    Imported inside the function, like every other reach into ``..context``
    from this module: ``context.assembler`` imports the agent package's
    ``blocks``/``threads`` helpers, so a module-level import here closes a
    cycle for no benefit.
    """
    try:
        from ..context.assembler import DEFAULT_CONVERSATION_TOKENS
    except Exception:  # pragma: no cover - import cycle guard
        return 800
    return DEFAULT_CONVERSATION_TOKENS


def _format_tool_observation(name: str, args: Any, result: Any) -> str:
    """Render an executed tool call as an observation the model can use."""
    text = "" if result is None else str(result)
    if len(text) > _TOOL_RESULT_CHARS:
        text = text[:_TOOL_RESULT_CHARS] + f"\n… [truncated, {len(str(result))} chars total]"
    call = f"{name}({args})" if args else name
    if not text.strip():
        return f"Executed {call}: succeeded with no output"
    return f"Executed {call}:\n{text}"


# Tool names PLANNING routes to SEARCHING.
_SEARCH_ROUTED_TOOLS = ("search", "search_discoveries", "web_search")

# Of those, the ones with no implementation behind them: SEARCHING serves a
# general RAG/memory query instead. The turn is told this explicitly rather
# than being handed a plain success, so the model does not report the generic
# result as if the tool it asked for had run (R06-O2).
#: The trailing comma is load-bearing: without it this is a *string*,
#: and the ``in`` test below becomes substring containment, so a plain
#: ``search`` would be reported to the model as not implemented.
_SUBSTITUTED_BY_SEARCH = ("search_discoveries",)


class AgentStateMachine:
    """
    Core agent orchestration using a state machine pattern.
    
    Based on ReAct (research4.md Part 5) with CRAG evaluation (Part 11).
    
    States:
        IDLE -> PLANNING -> SEARCHING/READING/EXECUTING -> OBSERVING -> PLANNING/REFLECTING -> RESPONDING

    Every turn that produces a response passes through REFLECTING (the
    Haloysius cognition tick seam) except the failure exits (max-loops guard,
    oscillation guard, ERROR give-up), which go straight to RESPONDING —
    RESPONDING then ticks once itself so the tick fires exactly once per turn (B1).

    The loop continues until:
        - CRAG confidence >= threshold (CORRECT)
        - Max loops reached
        - Error that can't be recovered
    """
    
    # Valid state transitions
    TRANSITIONS: Dict[AgentState, List[AgentState]] = {
        AgentState.IDLE: [AgentState.PLANNING],
        AgentState.PLANNING: [
            AgentState.SEARCHING, AgentState.READING,
            AgentState.EXECUTING, AgentState.REFLECTING,
            AgentState.RESPONDING, AgentState.ERROR,
            # Re-entry after an inline thread meta-tool (Plan A, spec §7).
            AgentState.PLANNING,
        ],
        AgentState.SEARCHING: [AgentState.OBSERVING, AgentState.ERROR],
        AgentState.READING: [AgentState.OBSERVING, AgentState.ERROR],
        AgentState.EXECUTING: [
            AgentState.OBSERVING, AgentState.AWAITING_CONFIRMATION, AgentState.ERROR
        ],
        AgentState.OBSERVING: [
            AgentState.REFLECTING, AgentState.PLANNING, AgentState.RESPONDING, AgentState.ERROR
        ],
        AgentState.REFLECTING: [
            AgentState.RESPONDING, AgentState.PLANNING, AgentState.ERROR
        ],
        AgentState.RESPONDING: [AgentState.IDLE],
        AgentState.AWAITING_CONFIRMATION: [AgentState.EXECUTING, AgentState.PLANNING],
        AgentState.ERROR: [AgentState.PLANNING, AgentState.RESPONDING, AgentState.IDLE],
    }

    # How long a queued turn waits for ``turn_lock`` before it gives up with
    # a visible error. Spec §12 queues a second message behind the running
    # turn; it does not promise an unbounded wait. The lock is held across
    # every yield of process(), so a turn that wedges (a model call with no
    # timeout, or a release missed because a consumer was torn down without
    # closing the generator) would otherwise hang every later message
    # forever behind nothing but a "waiting" badge, recoverable only by
    # restarting the process. Generous enough for a real turn (several
    # model calls and a long command); overridable per instance in tests.
    TURN_LOCK_TIMEOUT_S: float = 600.0

    # How often a long step -- a running tool, an in-flight model request --
    # looks up to see whether the turn was stopped (R-01 Phase B, A07-G2 /
    # A07-G5). _drive polls between steps and between events; this is the
    # poll *inside* one step, and it is what makes "/stop kills a running
    # command" true rather than "the stop is honoured once the command
    # finishes". Short enough to feel immediate, long enough that a turn
    # spends no measurable time waking up.
    STOP_POLL_SECONDS: float = 0.05

    # A07-G10: how long a turn may make no progress at all before the
    # liveness watchdog ends it. TURN_LOCK_TIMEOUT_S bounds a *waiter*;
    # this bounds the *holder*, which nothing did -- a turn wedged on an
    # un-returning await held the lock for the life of the process and
    # every later message queued behind a badge that never changed.
    # Generous on purpose: a long command that prints nothing still
    # stamps at start and completion, so this is the "nothing at all
    # happened" threshold, not a step budget. A turn parked on a
    # confirmation is exempt -- waiting on a person is not wedging.
    TURN_STALL_SECONDS: float = 900.0
    #: How often the watchdog samples the turn's liveness clock.
    STALL_POLL_SECONDS: float = 5.0

    # How many times an inline thread meta-tool may re-enter PLANNING in one
    # turn. Meta-tools are handled inline and deliberately do not raise
    # loop_count, so max_loops never ends a PLANNING→PLANNING chain, and
    # _already_called only stops the *identical* call: a run of meta-tools
    # with differing arguments would otherwise keep re-planning (a model
    # round-trip each time) until the oscillation guard fired and ended the
    # turn with a user-visible error. Two is enough for a legitimate
    # sequence (recall then resume); the call after that is still handled,
    # it just answers instead of planning again.
    MAX_META_TOOL_REENTRIES: int = 2
    
    def __init__(
        self,
        llm_client,
        tool_executor: 'ToolExecutor' = None,
        crag_evaluator = None,
        context_assembler = None,
        prompt_builder = None,
        rag_service = None,
        memory_service = None,
        max_loops: int = 5,
        crag_threshold: float = 0.7,
        cognition_tick: Callable = None,
        event_mapper = None,
        intake_pipeline = None,
        somatic_lifecycle = None,
        somatic_store = None,
        subagent_manager = None,
    ):
        """
        Initialize the agent state machine.

        Args:
            llm_client: Client for LLM calls (chat, stream)
            tool_executor: Tool execution with safety checks
            crag_evaluator: CRAG evaluation for confidence scoring
            context_assembler: Context assembly from multiple sources
            prompt_builder: Prompt construction
            rag_service: RAG search service
            memory_service: Memory recall/store service
            max_loops: Maximum loop iterations
            crag_threshold: Confidence threshold for CORRECT
            cognition_tick: Haloysius advance_turn callable
            event_mapper: System event → persona emotion mapper
            intake_pipeline: Phase 3 IntakePipeline for pre-cognitive message analysis
            somatic_lifecycle: Optional SomaticLifecycle (C1d). When None, the
                somatic seams are no-ops.
            somatic_store: Optional SomaticStore backing the lifecycle.
        """
        self.llm = llm_client
        self.tools = tool_executor
        self.crag = crag_evaluator
        self.context = context_assembler
        self.prompts = prompt_builder
        self.rag = rag_service
        self.memory = memory_service
        self.intake = intake_pipeline
        self.somatic_lifecycle = somatic_lifecycle
        self.somatic_store = somatic_store
        self.subagents = subagent_manager
        
        self.max_loops = max_loops
        self.crag_threshold = crag_threshold
        
        # Phase D: Cognitive tick (Haloysius advance_turn)
        self.cognition_tick = cognition_tick
        self.event_mapper = event_mapper
        
        self.current_state = AgentState.IDLE
        self.ctx: Optional[StateContext] = None
        
        # Active sessions for multi-session support
        self.active_sessions: Dict[str, StateContext] = {}
        
        # Cancellation tracking for session interruption
        self.cancelled: Dict[str, bool] = {}
        #: Sessions waiting on the turn lock (A07-G9). A queued turn is
        #: not in ``active_sessions`` -- it has no context yet -- so this
        #: is what lets ``request_stop`` answer for one instead of
        #: declining and letting it run when the lock frees.
        self._queued_sessions: set = set()

        # Packet 07: the interrupt algebra. ``turn_activity`` carries the
        # running turn's activity generation (B1): a stop claims it, so an
        # abort that loses the race to a finishing turn declines instead of
        # double-firing. ``_turn_generation`` is the generation the running
        # turn stamped at its start — the generation a stop observes.
        # ``_pending_steer`` holds the steers waiting for a session's next
        # batch boundary (B2): a mid-turn arrival steers into that boundary
        # instead of queueing a whole second turn. It is a LIST per session
        # (A07-G6): the slot used to be replace-not-grow, so a second
        # arrival erased the first after both had been told "accepted".
        # Both are plain cross-request surfaces in ``cancel_session``'s
        # discipline: they never take the turn lock, which a mid-turn
        # arrival can never own.
        self.turn_activity = TurnActivity()
        self._turn_generation: Optional[int] = None
        self._pending_steer: Dict[str, List[str]] = {}

        # Voice mode (O3): the PiperTTS instance behind the Haloysius voice
        # backend, cached once resolved so every egress turn shares one model
        # load. None until a turn needs it (and stays None without a seam).
        self._egress_tts: Any = None
        # O3: egress failure sites already warned about (warning-once) — the
        # machine is a process singleton, so this is once per site per run.
        self._egress_warned: set = set()

        # One turn at a time (spec §12): held for the whole of process() and
        # confirm_action(), including their cleanup, so a second /message
        # during a turn waits here instead of the route force-resetting the
        # machine. Only the *slots* are initialised: the Lock itself is built
        # lazily by the ``turn_lock`` property below, against the loop that is
        # actually running. Binding a Lock to ``turn_lock`` here as well would
        # write through a read-only property and raise ``AttributeError: can't
        # set attribute 'turn_lock'`` at construction — the process could not
        # start at all.
        self._turn_lock: Optional[asyncio.Lock] = None
        self._turn_lock_loop = None

    @property
    def turn_lock(self) -> asyncio.Lock:
        """One turn at a time.

        ``self.ctx`` is a single instance attribute on a process-wide agent, so
        a second concurrent request overwrites the first turn's context
        mid-flight — the user gets the other person's plan, observations and
        answer. Callers hold this for the whole turn.

        The whole turn, deliberately, and not just the ``self.ctx`` assignment:
        every handler reads ``self.ctx`` and writes ``self.current_state``
        across its own awaits, and ``_apply_generation_params`` sets
        ``max_tokens``/``temperature`` on the one shared LLM adapter, so a lock
        released before RESPONDING finishes would let the next turn clobber all
        of it exactly as if there were no lock. Those two tweaks are applied
        here rather than in the route precisely because this lock is what makes
        writing to the shared adapter safe (merge D5). The cost is real — a slow turn blocks
        every other request until the model times out — and the fix is not a
        narrower lock but per-turn state: pass the ``StateContext`` (and the
        state, and the adapter tweaks) through the handlers instead of hanging
        them off the agent, at which point no lock is needed at all. Until
        then this stays wide, and Halbert is single-user.

        The lock is made against the running loop rather than at construction:
        the agent outlives any one loop, and a lock bound to a dead loop raises
        instead of locking.
        """
        loop = asyncio.get_running_loop()
        if self._turn_lock is None or self._turn_lock_loop is not loop:
            self._turn_lock = asyncio.Lock()
            self._turn_lock_loop = loop
        return self._turn_lock

    # Property aliases for handler compatibility
    @property
    def tool_executor(self):
        """Alias for handlers that use tool_executor."""
        return self.tools
    
    @property
    def llm_client(self):
        """Alias for handlers that use llm_client."""
        return self.llm
    
    @property
    def rag_service(self):
        """Alias for handlers that use rag_service."""
        return self.rag
    
    @property
    def memory_service(self):
        """Alias for handlers that use memory_service."""
        return self.memory

    @property
    def intake_pipeline(self):
        """Alias for the intake pipeline."""
        return self.intake
    
    async def process(
        self,
        query: str,
        session_id: str = None,
        user_id: str = None,
        conversation_history: List[Dict] = None,
        images: List[str] = None,
        thread_id: str = None,
        continuity: str = "",
        thread_manager=None,
        *,
        model_override: str = None,
        tier_override: str = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        history_budget: Optional[int] = None,
        retrieval_scope: Optional[str] = None,
        speaker_role: Optional[str] = None,
        modality: Optional[str] = None,
        speaker_name: Optional[str] = None,
        claim_source: Optional[str] = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Process a user query through the state machine.

        Yields StreamEvents for real-time frontend updates.

        Args:
            query: User's question/request
            session_id: Optional session ID (generated if not provided)
            user_id: Optional user ID
            conversation_history: Previous messages in conversation. Only a
                fallback: with a ThreadManager wired ``_begin_turn`` replaces
                it with the thread's own windowed rows.
            images: Optional base64 images for the vision model
            thread_id: Hidden thread this turn belongs to (Plan A); the
                ThreadManager overrides it when one is wired
            continuity: The <continuity> hint for this turn ("" when none)
            thread_manager: ThreadManager that persists the turn (may be None)
            model_override: Exact model name pinned for this turn; bypasses
                the complexity router
            tier_override: "guide" | "specialist" | "vision" — force a tier
                without naming a model
            max_tokens: Generation ceiling for this turn, applied to the
                shared LLM adapter once this turn owns the lock
            temperature: Sampling temperature for this turn, same placement
            history_budget: Conversation-bucket tokens this turn may spend on
                the thread receipt plus the prior turns. Resolved by the
                route from the model that will actually answer (a pinned
                turn's budget is not the default model's), so the state
                machine never has to import route or picker code to know it.
            retrieval_scope: Explicit SourcePrep scope id for retrieval this
                turn. Used when no active skill provides one — e.g. the
                "Analyze" button hardwires retrieval to the host scope.
            speaker_role: Verified role of the speaker for this turn
                (admin/member/guest/restricted/unknown). The RoleGate uses it
                to tighten tool-risk classification. Voice ingress passes
                "unknown" (the satellite protocol verifies no one); absent
                means the dashboard-chat default "admin" applies.
            modality: Ingress modality ("voice" for a spoken turn,
                "terminal" for a turn typed at the machine's terminal
                surface, C5). Absent means a typed turn — today's
                behavior, unchanged. A voice turn with no speaker_role
                defaults to "unknown", never to the "admin" a typed turn
                carries: the RoleGate must not hear the owner's voice in
                an unidentified speaker's. A terminal turn defaults to
                "admin" and carries the channel's own dashboard-token
                claim (founder ruling 2026-09-07), so the D-6 cap is a
                no-op for it.
            speaker_name: Who the audio pipeline identified as speaking
                (CAM++ match name). A claim to record, not a role grant.
            claim_source: Where the speaker claim came from
                ("voice_speaker_verification" | "free_text_name" | None).
                Ignored for a terminal turn: its claim is the channel's
                own stamp.

        Yields:
            StreamEvent objects for each state change, tool call, etc.
        """
        session_id = session_id or str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        # A second /message during a live turn queues on the lock (the
        # route no longer force-resets the machine, A11). Tell the UI it
        # is waiting before blocking (spec §12: "emits conversation_status:
        # waiting"); the status is the plain string the badge expects.
        queued = self.turn_lock.locked()
        if queued:
            self._queued_sessions.add(session_id)
            logger.info(f"Session {session_id} waiting for the current turn to finish")
            yield StreamEvent.conversation_status(
                session_id, "waiting", waiting_for="previous turn"
            )
            # C3 (busy-mode unification): the honest queued-turn event —
            # a whole turn queuing on the lock (an image arrival over
            # the dashboard door, a terminal client's first-class queue)
            # is its own observable state, not just a waiting badge. The
            # design's one addition to the dashboard's whole-turn queue
            # path (§4 table); rides alongside the status event above,
            # never replacing it.
            yield StreamEvent.turn_queued(
                session_id, waiting_for="previous turn"
            )
            # C4: the tee hears the queue too (reduced set) — the voice
            # HUD can say "answering, and another turn is waiting".
            self._tee_publish(
                "turn_queued", session_id, waiting_for="previous turn"
            )

        # One turn at a time (spec §12). Everything below, including the
        # finally, runs under the lock; asyncio.Lock is not task-bound, so
        # releasing it from the generator's cleanup is fine whichever task
        # drives the last step. The wait is bounded (TURN_LOCK_TIMEOUT_S) so
        # a wedged turn surfaces as an error the user can retry instead of
        # queueing every later message behind a badge that never changes.
        try:
            got_lock = await self._acquire_turn_lock(session_id)
        finally:
            self._queued_sessions.discard(session_id)
        if not got_lock:
            for event in self._turn_lock_timeout_events(session_id):
                yield event
            return

        # A07-G9: a stop issued while this turn was queued is read here,
        # the first thing under the lock. The turn never starts: it says
        # what it was asked to say (cancelled) and releases immediately,
        # rather than answering a question the user withdrew.
        if self.cancelled.pop(session_id, False):
            logger.info(f"Session {session_id} stopped while queued")
            self.turn_lock.release()
            yield StreamEvent.cancelled(session_id)
            return

        # Packet 07 B1: the turn's activity generation, stamped at the
        # first sync step under the lock (no await separates the acquire
        # from here, so no other request can observe the sliver). A stop
        # issued against this turn observes and claims this generation;
        # the RESPONDING finalize stamp below is what makes such a claim
        # stale once the turn's answer is committed.
        self._turn_generation = self.turn_activity.stamp()

        # Packet 04 A1: typed voice ingress. Exactly one door
        # (/api/agent/message) serves typed and spoken turns, so the turn
        # has to carry which it is. C5 adds the third ingress value:
        # "terminal", a turn typed at the machine's terminal surface
        # (founder ruling 2026-09-07 — the terminal is a talk channel,
        # ASSERTED via the dashboard token). Defaulting, in order: an
        # explicit role always wins; otherwise the resolved channel's own
        # default_role is the answer (design §1: the defaults the route,
        # the gate list, and a test can all read — typed is admin
        # (dashboard chat is session-authenticated), voice is "unknown"
        # — never a silent admin default, the security gap this closes —
        # and terminal is admin, the owner's shell on the owner's
        # machine). The modality is normalized to the three enumerated
        # ingress values so a client cannot invent a fourth; the inline
        # defaults below are only the registry's non-fatal fallback.
        #
        # A09 bug 1 (R-01 Phase A): "normalized to the three enumerated
        # values" used to mean "anything unrecognised becomes text" --
        # and text is the dashboard channel, whose default_role is
        # admin. An in-process caller passing modality='mcp' therefore
        # got an admin turn, contradicting the route's fail-closed
        # registry. Resolve through the one registry instead: an
        # unadmitted modality is refused here exactly as it is at the
        # door, in the admission module's payload shape.
        normalized_modality = str(modality or "").strip().lower()
        try:
            from .channels import ChannelRefused, resolve_channel
            turn_modality = resolve_channel(normalized_modality).id
            if turn_modality == "dashboard":
                # The registry's id for the typed door; process() has
                # always called that modality "text" on the context.
                turn_modality = "text"
        except ChannelRefused as refusal:
            logger.warning(
                "turn refused: no channel for modality %r", modality
            )
            yield StreamEvent(
                type="error",
                session_id=session_id,
                data=refusal.payload(),
            )
            return
        if speaker_role:
            turn_speaker_role = speaker_role
        else:
            try:
                from .channels import resolve_channel
                turn_speaker_role = resolve_channel(turn_modality).default_role
            except Exception:
                turn_speaker_role = (
                    "admin" if turn_modality == "text" else "unknown"
                )

        # C1 (channel layer, D-4 design §1): the turn's resolved channel,
        # derived from the same normalized modality through the one
        # registry, bound here for provenance — the ThreadManager reads
        # it when it writes the user row (metadata.channel), recording
        # how the turn arrived, never gating anything on it. Same
        # copy-down-the-task pattern as the turn digest below; reset in
        # the finally so no channel bleeds into a later turn. The route
        # already refused an unresolvable modality, and the two values
        # here always resolve, so a failure is non-fatal by the same rule
        # as the digest.
        channel_token = None
        try:
            from .channels import current_turn_channel, resolve_channel
            channel_token = current_turn_channel.set(
                resolve_channel(turn_modality)
            )
        except Exception as e:
            logger.debug(f"turn channel not bound (non-fatal): {e}")

        # Packet 04 A2: claim strength at the voice gate — recorded on the
        # turn context, and (D-6 wave 3) bound for the tool executor to
        # enforce: a claim below ASSERTED caps the effective role
        # RoleGate hears at member-class. A voice turn's claim_source maps
        # through the PACKET-02 strength ladder; a source the ladder
        # does not know — or an absent one — fails closed to UNVERIFIED,
        # never to a stronger reading. Typed turns record no claim here:
        # absent request fields must keep today's behavior exactly (the
        # packet's regression gate), and a typed turn's identity rides
        # the dashboard session. A terminal turn's claim is the channel's
        # own stamp (the branch below), which is the same dashboard-token
        # identity a typed turn rides — stated where the voice ladder can
        # read it, so the D-6 cap composes and is a no-op at ASSERTED.
        turn_identifier_claim = None
        if turn_modality == "voice":
            try:
                from ..persona.claims import claim_from_source
                turn_identifier_claim = claim_from_source(claim_source, value=speaker_name)
            except Exception as e:
                # A12 bug 1 (R-01 Phase A): this used to be non-fatal and
                # leave the claim None -- and a None claim is not a weak
                # claim, it is NO cap: the executor's voice ceiling never
                # runs and the stated role stands. Fail closed instead.
                logger.warning(f"identifier claim not derived; failing closed: {e}")
                turn_identifier_claim = _unverified_claim()
        elif turn_modality == "terminal":
            # C5 (founder ruling 2026-09-07): the terminal channel's
            # identity IS the dashboard token the door validated —
            # ASSERTED, unconditionally. Derived from the channel's own
            # stamp, never from the wire's field: an absent or forged
            # claim_source can neither raise nor weaken it (there is no
            # pre-C5 terminal turn whose bytes need preserving). The
            # recorded claim_source is normalized to the same stamp so
            # the turn's record and its derived claim agree, and the
            # D-6 cap composes as a no-op: an ASSERTED claim's ceiling
            # is admin, so the executor's effective_voice_role leaves
            # the terminal turn's admin role exactly as stated.
            try:
                from ..persona.claims import claim_from_source
                from .channels import CHANNEL_CLAIM_STAMP
                claim_source = CHANNEL_CLAIM_STAMP["terminal"]
                turn_identifier_claim = claim_from_source(claim_source)
            except Exception as e:
                logger.warning(f"identifier claim not derived; failing closed: {e}")
                turn_identifier_claim = _unverified_claim()
        claim_strength_label = (
            turn_identifier_claim.strength.name.lower()
            if turn_identifier_claim is not None else "none"
        )

        # D-6 wave 3: bind the claim where the executor consumes it. The
        # tools this turn spawns copy this context, so the RoleGate
        # consumption point in ToolExecutor.execute() sees the voice
        # turn's claim and caps the effective role (voice turns only —
        # nothing bound for a typed turn). Dies with the turn, in the
        # finally below, so no claim ever bleeds into a LATER turn.
        claim_token = None
        if turn_identifier_claim is not None:
            try:
                from ..tools.executor import current_turn_claim
                claim_token = current_turn_claim.set(turn_identifier_claim)
            except Exception as e:
                logger.debug(f"turn claim not bound (non-fatal): {e}")

        # Packet 04 B1: the per-turn mutation digest. Bound on the
        # ContextVar so a write-plane success anywhere in this turn
        # (tools execute in tasks spawned inside it, which copy the
        # context) records into the turn's own digest — and cleared in
        # the finally below so no effect ever lands in a LATER turn.
        digest_token = None
        turn_digest = None
        try:
            from ..security.turn_digest import TurnDigest, current_turn_digest
            turn_digest = TurnDigest()
            digest_token = current_turn_digest.set(turn_digest)
        except Exception as e:
            logger.debug(f"turn digest not bound (non-fatal): {e}")

        try:
            # Generation params live on the one shared LLM adapter, so they
            # are only safe to write once this turn owns it. The route used
            # to set them under its own lock for exactly that reason; the
            # machine's lock covers the whole turn, so this placement is
            # strictly tighter. (The model/tier overrides are different —
            # they ride on the StateContext below, never on the adapter.)
            self._apply_generation_params(max_tokens, temperature)

            # A stale flag from an earlier turn on the same session id would
            # otherwise cancel this one before it began.
            self.cancelled.pop(session_id, None)

            self._supersede_paused_turn(session_id)

            # Initialize context
            self.ctx = StateContext(
                session_id=session_id,
                request_id=request_id,
                user_query=query,
                user_id=user_id,
                conversation_history=conversation_history or [],
                max_loops=self.max_loops,
                images=images,
                thread_id=thread_id,
                continuity_hint=continuity or "",
                thread_manager=thread_manager,
                model_override=model_override,
                tier_override=tier_override,
                history_budget=history_budget or _default_conversation_tokens(),
                retrieval_scope=retrieval_scope,
                speaker_role=turn_speaker_role,
                modality=turn_modality,
                speaker_name=speaker_name or None,
                claim_source=claim_source or None,
                identifier_claim=turn_identifier_claim,
                turn_digest=turn_digest,
            )

            # Phase 3: Run intake pipeline before cognitive tick
            if self.intake is not None:
                try:
                    self.ctx.intake = self.intake.analyze(query)
                    logger.info(
                        f"Intake: intent={self.ctx.intake.intent}, "
                        f"complexity={self.ctx.intake.complexity_score}, "
                        f"model={self.ctx.intake.recommended_model}"
                    )
                except Exception as e:
                    logger.warning(f"Intake pipeline failed (non-fatal): {e}")

            # B3: bind the active skills' declared safety for this turn.
            # Installed here, inside the turn-locked block and after intake,
            # because this is the first point the turn's skills are known;
            # cleared in the turn's finally, because set_skill_safety is a bare
            # attribute assignment and nothing else clears it -- a skill left
            # installed would classify the *next* turn.
            self._install_skill_safety()

            # Phase D: Inject persona cognition if tick is wired
            if self.cognition_tick is not None:
                try:
                    from ..integrations.cognition_wiring import get_cognition
                    self.ctx.persona_cognition = get_cognition()
                except Exception as e:
                    logger.warning(f"Could not inject persona cognition: {e}")

            # Track active session
            self.active_sessions[session_id] = self.ctx

            # Not the query. This line put the first hundred characters of
            # whatever the user said into the log on every turn, private mode
            # and all — a copy of the words in a file the erase path does not
            # reach and the ownership layer never sees. Length is enough to
            # debug a turn; the words are in the transcript when they are
            # Halbert's to keep.
            logger.info(
                "Starting agent processing: session=%s, query_chars=%d, "
                "modality=%s, speaker_role=%s, claim_source=%s, claim_strength=%s",
                session_id, len(query or ""),
                turn_modality, turn_speaker_role, claim_source or "none",
                claim_strength_label,
            )

            yield StreamEvent.session_started(session_id, request_id)
            # C4 (turn-event tee): the reduced set's lifecycle head. The
            # channel is already bound (above), so subscribers learn
            # whose turn started — the voice HUD's reflect-vs-ignore
            # question — without any content.
            self._tee_publish("turn_started", session_id)

            # Plan A: persist the user row and resolve the thread before any
            # model call (spec §4.1-§4.4), under the lock so thread
            # resolve/open/pause never races another turn.
            async for event in self._begin_turn():
                yield event

            # SK-2 seam 2: the turn's skill activations, promoted from a
            # debug log line to the durable skill_events table. After
            # _begin_turn so the turn scope is entered and the row carries
            # the same run_id the read receipts will.
            self._record_skill_activation()

            try:
                # A queued caller was told "waiting" before it blocked, and
                # nothing else on the normal turn path clears that badge —
                # the frontend reducer just keeps the last status string, so
                # without this the turn would read "waiting" while it plans,
                # runs commands and streams, and only flip at the very end.
                if queued:
                    yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)

                # Inside the try (spec §12): an invalid transition, an
                # exception in a handler or a consumer that goes away
                # mid-turn must all reach the cleanup below, otherwise the
                # machine is stranded mid-state and the next turn cannot
                # start.
                yield await self._transition(AgentState.PLANNING)
                # A07-G10: the liveness watchdog for THIS turn, bound to
                # the generation it stamped at start. Started here rather
                # than at the top of process() so it never watches a turn
                # that is still assembling its context, and torn down in
                # the finally below so it cannot outlive the turn.
                watchdog = asyncio.ensure_future(
                    self._turn_watchdog(session_id, self._turn_generation)
                )
                try:
                    async for event in self._drive():
                        yield event
                finally:
                    watchdog.cancel()
            finally:
                # end_turn before the state reset: the status is derived
                # from where the machine stopped (spec §4.7, §12).
                self._end_turn(self._turn_status(session_id))
                self._settle_turn(session_id)
                # Skills are per-turn. Not cleared when the turn merely paused
                # on a confirmation: confirm_action() resumes into the same
                # turn's context and the rules that classified the pending call
                # must still be the ones that classify it on resume.
                if getattr(self, "current_state", None) is not (
                    AgentState.AWAITING_CONFIRMATION
                ):
                    self._clear_skill_safety()
        finally:
            # _begin_turn() runs before the inner try, so a consumer that goes
            # away while it is still yielding (stop button, disconnect) never
            # reaches the finally that ends the turn: the user row would stay
            # in_progress with no assistant row until the next turn's
            # mark_interrupted() healed it. End it here instead. This is a
            # no-op for a turn the inner finally already ended (_end_turn
            # clears ctx.turn_context) and for one merely paused on a
            # confirmation (_end_turn returns while AWAITING_CONFIRMATION).
            # The status cannot come from _turn_status: the machine is still
            # IDLE at this point, which there means "ran to the end".
            self._end_turn("interrupted")
            # Settle before releasing so the next queued turn sees a settled
            # machine. Repeating _settle_turn is idempotent and it also covers
            # the sliver between registering the session and entering the try
            # above: a consumer that goes away exactly there would otherwise
            # leave the session registered.
            self._settle_turn(session_id)
            # Packet 04 B1: the turn's digest binding dies with the turn,
            # whichever way it ended — an effect recorded after this point
            # belongs to no turn and is dropped rather than attributed to
            # the next one.
            if digest_token is not None:
                try:
                    from ..security.turn_digest import current_turn_digest
                    current_turn_digest.reset(digest_token)
                except Exception as e:
                    logger.debug(f"turn digest unbind failed (non-fatal): {e}")
            # D-6 wave 3: the voice claim binding dies with the turn, the
            # same rule as the digest — a claim read after this point
            # belongs to no turn and must not gate the next one's tools.
            if claim_token is not None:
                try:
                    from ..tools.executor import current_turn_claim
                    current_turn_claim.reset(claim_token)
                except Exception as e:
                    logger.debug(f"turn claim unbind failed (non-fatal): {e}")
            # C1: the channel binding dies with the turn, the same rule —
            # a channel read after this point belongs to no turn and must
            # not label the next one's rows.
            if channel_token is not None:
                try:
                    from .channels import current_turn_channel
                    current_turn_channel.reset(channel_token)
                except Exception as e:
                    logger.debug(f"turn channel unbind failed (non-fatal): {e}")
            self.turn_lock.release()

    def _supersede_paused_turn(self, session_id: str) -> None:
        """A new message while a turn waits on a confirmation abandons it.

        The route used to force-reset the machine (routes/agent.py); now the
        machine settles itself. The staged HIGH-risk action is never run;
        when the paused turn was persisted (it carries a TurnContext) it is
        ended as ``cancelled`` with one block recording the action as
        "not run — superseded" so the receipt's Commands line carries it
        (spec §5). Any session left in active_sessions by a previous turn
        is evicted with it.
        """
        if self.current_state == AgentState.IDLE and not self.active_sessions:
            return
        for sid in list(self.active_sessions):
            old_ctx = self.active_sessions.pop(sid, None)
            if sid != session_id:
                logger.info(
                    f"Superseding session {sid} left in "
                    f"{self.current_state.value} by a new message"
                )
            self._record_superseded_turn(old_ctx)
        self.current_state = AgentState.IDLE

    def _record_superseded_turn(self, old_ctx: Optional[StateContext]) -> None:
        """End a superseded, persisted turn so its receipt records what the
        turn did and the action it never ran (spec §5).

        ``ThreadManager.end_turn`` is the only writer of the assistant row —
        nothing persists blocks as they happen — so everything the abandoned
        turn already did has to be written here too. A turn that ran ``ls``,
        spawned a terminal and then paused on ``systemctl restart sshd``
        keeps the ``ls``, its terminal id and any proposed diff on the
        receipt; only the staged action is recorded as "not run — superseded".

        No manager or no TurnContext: nothing to do. Never raises.
        """
        if old_ctx is None:
            return
        tm = getattr(old_ctx, "thread_manager", None)
        turn = getattr(old_ctx, "turn_context", None)
        if tm is None or turn is None:
            return
        old_ctx.turn_context = None   # ended here, never again
        pending = old_ctx.pending_confirmation or {}
        calls = list(old_ctx.tool_calls or [])
        # The staged call is the one the confirmation names; it is still
        # status="pending" because it never ran.
        staged = next((tc for tc in calls if tc.id == pending.get("action_id")), None)
        if staged is None and pending and calls:
            staged = calls[-1]
        blocks: List[Dict[str, Any]] = [
            self._tool_block(tc)
            for tc in calls
            if tc is not staged
            and tc.status not in ("pending", "running")
            and tc.name not in THREAD_META_TOOLS
        ]
        if pending:
            args = pending.get("args")
            if not isinstance(args, dict):
                args = staged.args if staged is not None and isinstance(staged.args, dict) else {}
            blocks.append({
                "tool": str(pending.get("tool", "")),
                "args": args,
                "result": "not run — superseded",
                "exit": None,
                "status": "superseded",
            })
        try:
            tm.end_turn(
                turn,
                assistant_text="".join(old_ctx.response_chunks or []),
                blocks=blocks,
                terminal_block_ids=list(old_ctx.terminal_block_ids or []),
                block_executions=dict(getattr(old_ctx, 'block_executions', {}) or {}),
                diff_proposals=[
                    {"diff_id": diff_id,
                     **(diff if isinstance(diff, dict) else {"value": diff})}
                    for diff_id, diff in (old_ctx.pending_diffs or {}).items()
                ],
                status="cancelled",
            )
        except Exception as e:
            logger.warning(f"end_turn for a superseded turn failed (non-fatal): {e}")

    def _apply_generation_params(
        self, max_tokens: Optional[int], temperature: Optional[float]
    ) -> None:
        """Write this turn's generation ceiling onto the shared LLM adapter.

        Called only from inside the turn lock. One ``LLMClientAdapter`` is
        shared by every request, so these are the two per-request tweaks that
        genuinely cannot live on the ``StateContext`` yet — everything else
        that varies per turn (the model and tier overrides) already does, and
        moving these across is a follow-up, not part of this seam.

        ``None`` means "the caller did not say", which keeps whatever the
        adapter already holds rather than resetting it to a default the
        caller never chose.
        """
        llm = self.llm
        if llm is None or not hasattr(llm, "max_tokens"):
            return
        if max_tokens is not None:
            llm.max_tokens = max_tokens
        if temperature is not None:
            llm.temperature = temperature
        logger.debug(
            f"LLM tweaks for this turn: max_tokens={getattr(llm, 'max_tokens', None)}, "
            f"temperature={getattr(llm, 'temperature', None)}"
        )

    async def _acquire_turn_lock(self, session_id: str) -> bool:
        """Take ``turn_lock`` for a turn, bounded by TURN_LOCK_TIMEOUT_S.

        True once the lock is held; the caller then owns the release. False
        when the wait timed out: the caller streams
        ``_turn_lock_timeout_events()`` and returns without touching the turn
        that is still running.

        Both entry points wait here, so both are bounded. An unbounded wait
        in either one hangs the request with no error and no stream close,
        recoverable only by restarting the process.
        """
        try:
            await asyncio.wait_for(
                self.turn_lock.acquire(), timeout=self.TURN_LOCK_TIMEOUT_S
            )
            return True
        except asyncio.TimeoutError:
            logger.error(
                f"Session {session_id} gave up waiting for the turn lock after "
                f"{self.TURN_LOCK_TIMEOUT_S:.0f}s (state={self.current_state.value})"
            )
            return False

    def _turn_lock_timeout_events(self, session_id: str) -> List[StreamEvent]:
        """The stream a caller that never got the lock sees: a terminal
        status for its own badge, a recoverable error, and a closed session.

        The status is the bare factory, deliberately not
        ``_set_conversation_status``: that one writes through ``self.ctx``,
        which here still belongs to the turn that is running and holding the
        lock. Without it the badge would stay on the "waiting" this caller
        emitted before blocking — the frontend reducer keeps the last status
        string and neither ``error`` nor ``session_ended`` touches it.
        """
        return [
            StreamEvent.conversation_status(session_id, "error"),
            StreamEvent.error(
                session_id,
                "The previous turn is still running. Try that again in a moment.",
                recoverable=True,
            ),
            StreamEvent.session_ended(session_id, 0, 0),
        ]

    def _settle_turn(self, session_id: str) -> None:
        """Cleanup shared by process() and confirm_action().

        A turn paused on AWAITING_CONFIRMATION keeps its session so
        confirm_action() can find it. Anything else is over: the machine
        returns to IDLE (also after a mid-turn exception or disconnect,
        which used to strand it in PLANNING and break the next turn) and
        the session is evicted.
        """
        if self.current_state == AgentState.AWAITING_CONFIRMATION:
            return
        self.current_state = AgentState.IDLE
        # C4: publish the turn's END once — the repeated settle calls
        # (process()'s outer finally) find the session already gone and
        # stay silent.
        ended = self.active_sessions.pop(session_id, None) is not None
        self.cancelled.pop(session_id, None)
        if ended:
            self._tee_publish("turn_ended", session_id)
        # Packet 07 B2: a steer that never found a batch boundary (the turn
        # ended, errored or was stopped first) leaves the slot here. The
        # arrival's own response already confirmed it (steer_accepted), so
        # this is bookkeeping, not a silent drop — but it is said in the
        # log so a steer the model never saw is diagnosable. Repeated by
        # process()'s outer finally, idempotently.
        leftover_steer = self._pending_steer.pop(session_id, None)
        if leftover_steer:
            logger.info(
                "Session %s ended with %d unapplied steer(s) (%d chars); the "
                "turn finished before a batch boundary could apply them",
                session_id, len(leftover_steer),
                sum(len(t) for t in leftover_steer),
            )

    async def _begin_turn(self) -> AsyncIterator[StreamEvent]:
        """Persist the user message and resolve the thread (spec §4.1-§4.4).

        Seeds ``ctx`` from the TurnContext: thread id, hint, history
        (receipt + last raw turns) and any deterministic recall, whose
        receipt goes in as ``retrieved_context[0]`` with ``source="thread"``.
        A store failure emits ``thread_store_error`` once and the turn
        carries on without persistence.

        This is also where the history is *shaped*, exactly once per turn.
        ``ThreadManager.begin_turn`` returns at most ``HISTORY_ROWS`` (12)
        rows, but that number is a bound on the store read — so a 4k-row
        thread is not materialised only to be trimmed — and not the window
        decision. The window is a token budget, not a row count: six long
        turns overflow a small local model where twenty short ones do not.
        The receipt row the manager prefixes is split off here, fitted to
        its own allowance and parked on ``ctx.thread_receipt_block`` (it is
        context *about* the conversation, so it belongs in the leading
        instructions, not mid-array); what is left of the bucket buys the
        raw turns. ``_build_messages`` does no budgeting of its own: it is
        called once per LLM call site, twice in a normal turn, and paying
        for the window twice would be both slower and inconsistent between
        the two halves of one turn.
        """
        # The Eyes rows are read once per turn (A4); this is where a turn
        # starts, so it is where the previous turn's cache stops being true.
        self._reset_world_observations()
        self._reset_interest_block()
        tm = self.ctx.thread_manager
        if tm is None:
            return
        sid = self.ctx.session_id
        try:
            from ..intake.signals import analyze_message
            signals = analyze_message(self.ctx.user_query)
            turn = tm.begin_turn(self.ctx.user_query, signals, sid)
        except Exception as e:
            logger.warning(f"begin_turn failed (non-fatal): {e}")
            yield StreamEvent.thread_store_error(sid, f"begin_turn: {e}")
            return

        self.ctx.turn_context = turn
        self._enter_turn_scope(turn.turn_id)
        self.ctx.thread_id = turn.thread_id
        self.ctx.continuity_hint = turn.hint or ""
        self.ctx.recalled_threads = list(turn.recalled or [])

        # Function-local, like every other reach into ``..context`` from this
        # module: context/assembler.py imports the agent package's blocks and
        # thread helpers, so a module-level import here would close a cycle
        # to save nothing.
        from ..context.assembler import (
            RECEIPT_HEADER,
            build_conversation_window,
            fit_receipt,
            receipt_allowance,
            split_receipt_row,
        )
        from ..context.tokens import TokenCounter

        counter = TokenCounter()
        # ``process()`` always sets a budget; a directly constructed context
        # (tests, out-of-tree callers) leaves the field at its 0 default, and
        # taking that literally would spend nothing and silently send the
        # model a turn with no history at all.
        budget = self.ctx.history_budget or _default_conversation_tokens()
        receipt, turns = split_receipt_row(list(turn.history or []))
        # Any *other* leading system row the ThreadManager wrote — today that
        # is the soft landing's '[Previous subject "X", kept for one turn
        # only; it is not the current task]' note (threads.py
        # ``_soft_landing``), which labels the six old-subject rows that
        # follow it. It cannot travel in the window: every path out of
        # ``build_conversation_window`` opens on a *user* row, so a leading
        # system row is always discarded, and the six rows it was labelling
        # then read to the model as the current subject. It goes where the
        # receipt goes — ``messages[0]`` — for the same reason: it is context
        # *about* the conversation, not a line anyone said.
        # Defanged like any other row that lands in the instructions: the
        # soft landing's own note is built from a fenced title, but this loop
        # takes whatever leading system row the store hands over.
        notes: List[str] = []
        while turns and turns[0].get("role") not in ("user", "assistant"):
            note = _defang_system_row(
                content_to_text(turns[0].get("content", ""))
            ).strip()
            if note:
                notes.append(note)
            turns = turns[1:]
        self.ctx.thread_receipt_block = ""
        if receipt:
            # The receipt and the turns share one bucket and the turns are
            # what the model is answering, so the receipt may only spend what
            # they leave — floored so a long history cannot evict it outright.
            # The −2 is the blank line the header costs once joined.
            allowance = receipt_allowance(turns, budget, counter)
            body = fit_receipt(
                receipt, allowance - counter.count(RECEIPT_HEADER) - 2, counter
            )
            if body:
                self.ctx.thread_receipt_block = RECEIPT_HEADER + body
        if notes:
            # After the receipt, never before it: the receipt block owns the
            # start of what ``_build_messages`` appends (its own '## Earlier
            # in this subject' heading), and the note is a caveat on the rows
            # that follow, not a heading of its own. Its cost comes out of the
            # same bucket, so the window below sees a smaller budget.
            self.ctx.thread_receipt_block = "\n\n".join(
                p for p in [self.ctx.thread_receipt_block, *notes] if p
            )
        self.ctx.conversation_history = build_conversation_window(
            turns,
            query=self.ctx.user_query,
            max_tokens=max(
                0, budget - counter.count(self.ctx.thread_receipt_block)
            ),
            token_counter=counter,
        )

        for r in self.ctx.recalled_threads:
            rid = str(r.get("thread_id", ""))
            rtitle = str(r.get("title", ""))
            rdate = str(r.get("date", ""))
            self.ctx.add_context(
                source="thread",
                content=str(r.get("receipt", "")),
                metadata={
                    "thread_id": rid, "title": rtitle, "date": rdate,
                    "match_terms": list(r.get("match_terms") or []),
                },
            )
            yield StreamEvent.thread_recalled(
                sid, rid, rtitle, rdate, list(r.get("match_terms") or []), mode="auto",
                last_turn_id=r.get("last_turn_id") or self._last_turn_id(rid),
                scope_crossed=r.get("scope_crossed"),
            )

        yield StreamEvent.turn_persisted(sid, turn.thread_id, turn.turn_id)

    def _turn_status(self, session_id: str) -> str:
        """``complete`` | ``cancelled`` | ``interrupted`` for the turn ending now.

        Runs before ``_settle_turn`` resets the state: IDLE *after the turn
        started* means ``_drive`` ran to the end; anything else (an
        exception, the consumer going away) is an interrupted turn.

        ``self.cancelled`` is load-bearing again, not legacy. The stop button
        reaches a running turn on a *different* request, and the only thing
        it can safely touch there is the flag: writing the turn from
        ``cancel_session`` would persist a truncated record and make this
        finally's own ``end_turn`` a no-op. ``_drive`` polls the flag between
        handler steps and between events, so the flag is what ends the turn
        and what names it here. ``ctx.conversation_status`` carries the same
        cancellation for the badge and is checked too, because a caller
        outside this machine may set only that.
        """
        cancelled = bool(self.cancelled.get(session_id))
        try:
            cancelled = cancelled or (
                self.ctx.conversation_status.current() == ConversationStatus.CANCELLED
            )
        except Exception:
            pass
        if cancelled:
            return "cancelled"
        if self.current_state == AgentState.IDLE:
            # IDLE is also the state *before* the first transition, so on
            # its own it does not mean "ran to the end". The queued
            # caller's conversation_status is yielded from inside the try
            # while the machine is still IDLE; a consumer that goes away on
            # exactly that event would otherwise persist an empty turn as
            # ``complete`` — and a row that is no longer ``in_progress`` is
            # one boot's ``mark_interrupted()`` can never heal, unlike the
            # plain abandonment this would be mistaken for. Every
            # ``_transition`` appends to ``state_history``, so it is empty
            # only for a turn that never started.
            started = bool(getattr(self.ctx, "state_history", None))
            return "complete" if started else "interrupted"
        return "interrupted"

    @staticmethod
    def _tool_block(tc: ToolCall) -> Dict[str, Any]:
        """One persisted tool block (spec §8 messages.blocks_json)."""
        result = tc.result
        if not isinstance(result, (str, int, float, bool, dict, list, type(None))):
            result = str(result)
        if isinstance(result, str) and len(result) > 4000:
            result = result[:4000] + "…"
        exit_code: Optional[int] = None
        if tc.name == "run_command":
            text = tc.result if isinstance(tc.result, str) else ""
            m = re.match(r"Exit code (-?\d+)", text)
            if m:
                exit_code = int(m.group(1))
            elif tc.status == "success":
                exit_code = 0
        return {
            "tool": tc.name,
            "args": tc.args if isinstance(tc.args, dict) else {"value": str(tc.args)},
            "result": result,
            "exit": exit_code,
            "execution_id": tc.id,
            "status": tc.status,
            "error": tc.error,
        }

    def _enter_turn_scope(self, turn_id: str) -> None:
        """Put this turn's id where a write four layers down can find it.

        ``record_file_change`` reads it from a ContextVar rather than a
        parameter, because tool handlers take only their args dict: threading
        one through every registered tool to reach the ledger would be a
        change to the whole registry for one field. See
        continuity/provenance.current_turn.
        """
        from ..continuity.provenance import current_turn, current_user_message

        self._turn_scope_token = current_turn.set(turn_id)
        # The user's own words, for the same reason and with the same
        # lifetime. ``remember`` checks a recorded reason against them; a
        # writer that cannot see them refuses rather than trusting the model.
        self._turn_message_token = current_user_message.set(
            getattr(self.ctx, "user_query", "") or ""
        )

    def _leave_turn_scope(self) -> None:
        """Restore whatever was in scope before this turn.

        Resetting through the token rather than setting None: turns nest --
        a confirmation resume ends one turn from inside another -- and
        clearing outright would drop the outer turn's id, putting every write
        after it on no turn at all. Called from an outer finally that may fire
        for a turn that never began, so a missing token is not an error.
        """
        from ..continuity.provenance import current_turn, current_user_message

        for attr, var in (("_turn_scope_token", current_turn),
                          ("_turn_message_token", current_user_message)):
            token = getattr(self, attr, None)
            if token is None:
                continue
            setattr(self, attr, None)
            try:
                var.reset(token)
            except ValueError:
                # The token belongs to another context (the turn began on a
                # different task). Nothing to restore here; leaving the value
                # set would be worse than leaving it alone.
                pass

    def _end_turn(self, status: str) -> None:
        """Hand the finished turn to the ThreadManager (spec §4.7).

        Skipped while the turn is merely paused on a confirmation (the
        TurnContext stays on ctx; confirm_action's finally ends it).
        Thread meta-tool calls are not blocks. Never raises, and calling it
        twice for one turn is a no-op (the TurnContext is cleared before the
        write), so process()'s outer finally can safely end a turn that was
        abandoned before the inner try was ever entered.
        """
        if self.current_state == AgentState.AWAITING_CONFIRMATION:
            return
        ctx = self.ctx
        if ctx is None:
            return
        tm = ctx.thread_manager
        turn = ctx.turn_context
        if tm is None or turn is None:
            return
        ctx.turn_context = None
        self._leave_turn_scope()
        blocks = [
            self._tool_block(tc) for tc in ctx.tool_calls
            if tc.name not in THREAD_META_TOOLS
        ]
        diffs = [
            {"diff_id": diff_id, **(diff if isinstance(diff, dict) else {"value": diff})}
            for diff_id, diff in ctx.pending_diffs.items()
        ]
        try:
            tm.end_turn(
                turn,
                assistant_text="".join(ctx.response_chunks),
                blocks=blocks,
                terminal_block_ids=list(ctx.terminal_block_ids),
                block_executions=dict(ctx.block_executions),
                diff_proposals=diffs,
                status=status,
                thread_id_override=ctx.thread_id if ctx.thread_switched else None,
            )
        except Exception as e:
            # Non-fatal to the stream, but the turn is GONE: the words the
            # user said and the answer they got are not written anywhere.
            # Say which turn, so this is diagnosable rather than a shrug.
            logger.warning(
                "end_turn failed for turn %s in thread %s - this turn is not "
                "persisted and will not appear in the timeline: %s",
                getattr(turn, "turn_id", "?"), getattr(turn, "thread_id", "?"), e,
            )

    async def _drive(self) -> AsyncIterator[StreamEvent]:
        """Run the state machine from ``self.current_state`` until it settles.

        The single loop shared by ``process()`` and ``confirm_action()``: a
        resumed turn has to reach RESPONDING the same way a fresh one does,
        otherwise confirming an action executes the tool and then goes quiet
        (no observation, no answer, no ``session_ended``).

        Ends on IDLE (turn finished), on AWAITING_CONFIRMATION (turn paused,
        session deliberately left in ``active_sessions``), or on the stop
        button. Caller owns session eviction.

        The cancellation poll lives here rather than in the route because
        this is the only loop that sees both seams: between handler *steps*
        (a turn stopped during a long command must not go on to plan and
        answer) and between the events one handler yields (a turn stopped
        mid-stream must stop mid-stream). The route used to poll only the
        latter, so a route that no longer wraps the turn — and a caller that
        is not a route at all — lost the stop button entirely. Returning here
        leaves the write to ``process()``'s finally, which has the text and
        blocks the turn actually finished with; ``_turn_status`` reads the
        same flag and names the turn ``cancelled``.
        """
        session_id = self.ctx.session_id

        while self.current_state != AgentState.IDLE:
            if self.cancelled.get(session_id):
                logger.info(f"Session {session_id} cancelled between steps")
                yield StreamEvent.cancelled(session_id)
                return

            # Packet 07 B2: the batch boundary. A steer queued by a
            # mid-turn arrival applies here, between handler steps, so
            # the next model call re-reads the observations with the
            # user's mid-turn text appended to the last tool result.
            self._drain_pending_steer()

            if self.current_state == AgentState.AWAITING_CONFIRMATION:
                # Blocking state: end this SSE stream and keep the session
                # in active_sessions so confirm_action() can resume it.
                # Checked BEFORE the max-loops / oscillation guards so a
                # pause on the final allowed loop is not overwritten to
                # RESPONDING.
                logger.info(f"Session {session_id} paused awaiting confirmation")
                break

            # Safety checks
            if self.ctx.loop_count >= self.ctx.max_loops:
                logger.warning(f"Max loops ({self.ctx.max_loops}) reached")
                yield StreamEvent.loop_warning(
                    session_id, self.ctx.loop_count, self.ctx.max_loops
                )
                yield StreamEvent.error(
                    session_id,
                    f"Max iterations ({self.ctx.max_loops}) reached, responding with available information"
                )
                # Fall through to the RESPONDING handler (mirrors the
                # oscillation guard). A `continue` here re-fired this guard
                # forever because loop_count never drops below max_loops.
                if self.current_state != AgentState.RESPONDING:
                    self.ctx.state_history.append(AgentState.RESPONDING.value)
                    self.current_state = AgentState.RESPONDING

            if self._detect_oscillation():
                logger.warning("State oscillation detected")
                yield StreamEvent.error(session_id, "State oscillation detected, forcing response")
                # Clear state history to break out of oscillation detection loop
                self.ctx.state_history.clear()
                self.ctx.state_history.append(AgentState.RESPONDING.value)
                self.current_state = AgentState.RESPONDING
                # Don't continue - let it execute the RESPONDING handler

            # Execute handler for current state
            handler = self._get_handler()
            if handler:
                # A07-G10: handler entry is progress.
                self._touch_activity(self.current_state.value.lower())
                try:
                    async for event in handler():
                        yield event
                        # Between events, so the stop button can cut a
                        # response that is still streaming rather than only
                        # one that has finished.
                        if self.cancelled.get(session_id):
                            logger.info(
                                f"Session {session_id} cancelled mid-{self.current_state.value}"
                            )
                            yield StreamEvent.cancelled(session_id)
                            return
                except TurnStopped:
                    # A07-G5: a long step abandoned itself because the
                    # user stopped the turn. Same ending as the poll
                    # above, reached from inside a step instead of
                    # between two.
                    logger.info(
                        f"Session {session_id} cancelled inside "
                        f"{self.current_state.value}"
                    )
                    yield StreamEvent.cancelled(session_id)
                    return
                except Exception as e:
                    logger.error(f"Handler error in {self.current_state}: {e}")
                    self.ctx.error = str(e)
                    if self.current_state == AgentState.RESPONDING:
                        # Terminal guard: a failure while producing the final
                        # response cannot be recovered by retrying — the
                        # ERROR handler's give-up path transitions back to
                        # RESPONDING, which would fail identically forever.
                        # End the session instead (non-recoverable error).
                        yield StreamEvent.error(session_id, str(e), recoverable=False)
                        # User-facing status: terminal error (A2c) —
                        # unless the give-up path already made it terminal.
                        if not self.ctx.conversation_status.is_terminal():
                            yield self._set_conversation_status(ConversationStatus.ERROR)
                        self.current_state = AgentState.IDLE
                    else:
                        yield StreamEvent.error(session_id, str(e))
                        self.current_state = AgentState.ERROR
            else:
                logger.error(f"No handler for state: {self.current_state}")
                self.current_state = AgentState.ERROR

        # Session complete (a paused session is not ended: the
        # tool_confirmation_required + conversation_status: blocked events
        # already told the client to stop and wait for confirm_action()).
        if self.current_state != AgentState.AWAITING_CONFIRMATION:
            yield StreamEvent.session_ended(
                session_id,
                self.ctx.elapsed_ms(),
                self.ctx.loop_count
            )


    async def confirm_action(
        self,
        session_id: str,
        action_id: str,
        confirmed: bool,
        *,
        model_override: str = None,
        tier_override: str = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        history_budget: Optional[int] = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Handle user confirmation for high-risk actions.

        Resumes the paused turn and runs it to completion: an approved action
        executes and the machine keeps going (OBSERVING → … → RESPONDING), a
        rejected one re-plans and still answers. Either way the caller sees a
        ``response_complete`` and ``session_ended``, exactly as on an
        unblocked turn.

        Args:
            session_id: Session ID
            action_id: Action execution ID
            confirmed: Whether user confirmed the action
            model_override: Same per-turn overrides ``process()`` takes. The
                confirmation is a separate HTTP request, so the route has to
                resolve them again and hand them back; anything left unsaid
                keeps what the paused turn already decided rather than
                silently reverting the resumed half to a default.
            tier_override: See ``model_override``
            max_tokens: Generation ceiling, applied to the shared adapter
                once this call owns the turn lock
            temperature: Sampling temperature, same placement
            history_budget: Conversation-bucket tokens; only relevant if a
                later re-plan reshapes the window

        Yields:
            StreamEvent objects
        """
        # Bounded acquire + explicit release rather than ``async with``: the
        # UI aborts the paused turn's SSE and POSTs /confirm immediately, so
        # that generator may still be closing (and holding the lock) when we
        # arrive. That is normally milliseconds, but a wedged turn must not
        # make /confirm hang forever with nothing to show for it.
        if not await self._acquire_turn_lock(session_id):
            for event in self._turn_lock_timeout_events(session_id):
                yield event
            return

        # The adapter is shared, so this waits for the lock like everything
        # else that writes to it.
        self._apply_generation_params(max_tokens, temperature)

        try:
            if session_id not in self.active_sessions:
                yield StreamEvent.error(session_id, "Session not found", recoverable=False)
                return

            self.ctx = self.active_sessions[session_id]
            # Only what the caller actually named: the resumed turn keeps the
            # model it was already answering with otherwise.
            if model_override is not None:
                self.ctx.model_override = model_override
            if tier_override is not None:
                self.ctx.tier_override = tier_override
            if history_budget:
                self.ctx.history_budget = history_budget
            # A stop pressed while the confirmation dialog was open must not
            # cancel the turn the user has just approved.
            self.cancelled.pop(session_id, None)
            # Packet 07 B1: the resumed turn is new activity — stamp it, so
            # a stop issued against the resumed turn claims this generation
            # and not the one the original half of the turn ran under.
            self._turn_generation = self.turn_activity.stamp()

            if not self.ctx.pending_confirmation:
                yield StreamEvent.error(session_id, "No pending confirmation")
                return

            if self.ctx.pending_confirmation.get("action_id") != action_id:
                yield StreamEvent.error(session_id, "Action ID mismatch")
                return

            try:
                if confirmed:
                    # Execute the confirmed action
                    self.ctx.pending_confirmation["confirmed"] = True
                    # Approval granted: resume working (A2c)
                    yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)
                    yield await self._transition(AgentState.EXECUTING)
                else:
                    # User rejected - go back to planning
                    self.ctx.pending_confirmation = None
                    # Settle the rejected call and name it in the observation.
                    # A bare "User rejected the action" told the next PLANNING pass
                    # nothing about *what* was refused, and left the call at
                    # status="pending" so _already_called() could not stop the model
                    # proposing the identical command again.
                    rejected = self.ctx.tool_calls[-1] if self.ctx.tool_calls else None
                    if rejected is not None and rejected.id == action_id:
                        rejected.status = "error"
                        rejected.error = "rejected by user"
                        self.ctx.add_observation(
                            f"The user refused to run {rejected.name}({rejected.args}). "
                            "Do not propose it again; answer without it or suggest "
                            "a different approach."
                        )
                    else:
                        self.ctx.add_observation("User rejected the action")
                    # Rejection resumes the conversation (the agent re-plans and still
                    # responds), so this is IN_PROGRESS, not a terminal CANCELLED.
                    # True cancellation is cancel_session() below. (A2c)
                    yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)
                    yield await self._transition(AgentState.PLANNING)

                # Resume the turn. Running only _handle_executing() here stopped
                # the machine dead at OBSERVING: the tool ran but the user never
                # got an answer, and the stream never closed. _drive() is the same
                # loop process() uses, so a resumed turn finishes like any other.
                async for event in self._drive():
                    yield event
            finally:
                # end_turn before the state reset: the status is derived
                # from where the machine stopped (spec §4.7, §12).
                self._end_turn(self._turn_status(session_id))
                self._settle_turn(session_id)
        finally:
            self.turn_lock.release()

    def cancel_session(self, session_id: str) -> bool:
        """Cancel an active session.

        Raising the ``cancelled`` flag is what actually stops a *running*
        turn: this runs on a different request while the turn is mid-flight,
        and ``_drive`` polls the flag between handler steps and between the
        events one handler yields. Evicting the session instead left the
        stream running to completion — the user pressed stop and the model
        kept answering — and writing the turn from here would persist a
        truncated record and make ``process()``'s own ``end_turn`` a no-op.
        So for a running turn this raises the flag and touches nothing else:
        ``process()``'s finally ends the turn ``cancelled`` and settles the
        machine, with the text, blocks and terminal ids it really finished
        with.

        A session **no turn is answering** is the other half of the rule, and
        the reason there is any teardown here at all. Nothing will ever run a
        finally for it again, so raising the flag and stopping there left the
        entry in ``active_sessions`` — which ``/api/agent/sessions`` and
        ``/health`` report as a live turn the user has just stopped — and left
        its persisted user row ``in_progress`` until some later message
        happened to supersede it. So when no turn is in flight the machine
        settles the session itself: the turn is ended as a superseded pause is
        (cancelled, keeping what it already said and recording any staged
        action as never run, spec §5), the session is evicted and the machine
        returns to IDLE.

        A turn paused on a confirmation is the best-known case of that: its
        SSE stream has already closed, ``confirm_action`` is never called for
        it, and the next message's ``_supersede_paused_turn`` can no longer
        find the session to end it. It is named explicitly below because the
        pause can be reached with the stream not yet drained — the generator
        suspended on its last event, still holding the lock — and a paused
        turn is not a running one whichever way the lock reads.

        "In flight" is the turn lock, not the state: the lock is held for the
        whole of ``process()``/``confirm_action()`` including their cleanup,
        and a turn registers its session under it (``_supersede_paused_turn``
        evicts everything else first), so a held lock means the session in
        hand is being answered right now. The state cannot answer the same
        question — IDLE is also where a turn sits while ``_begin_turn`` is
        still writing, and tearing down there is exactly the force-reset this
        method stopped doing: the answer keeps arriving while the next
        transition fights it. The private slot is read rather than the
        ``turn_lock`` property because this is a plain sync call: the property
        wants a running loop and would build a lock just to report it free.
        """
        # A07-G13 + A07 bug 2 (R-01 Phase B): one stop semantics. This
        # used to raise the flag with no generation claim while a typed
        # ``/stop`` claimed it -- two verbs for one act, and a paused turn
        # that tore down under this one and not under the other. The
        # button and the command are now the same call; everything the
        # docstring above describes still happens, in ``_stop_teardown``.
        return self.request_stop(session_id) == "stopped"

    def _stop_teardown(self, session_id: str) -> None:
        """Settle a session no turn will ever run a finally for.

        The half of the stop rule that is not "raise the flag": a paused
        turn, or one whose ``process()`` has already returned, has nobody
        left to end it, so the machine ends it here -- as a superseded
        pause is ended (cancelled, keeping what it already said and
        recording any staged action as never run, spec §5) -- evicts the
        session and returns to IDLE.
        """
        ctx = self.active_sessions.get(session_id)
        if ctx is None:
            return
        self._record_superseded_turn(ctx)
        del self.active_sessions[session_id]
        self.current_state = AgentState.IDLE

    def _flag_cancelled(self, session_id: str) -> None:
        """Raise the stop flag and name the conversation cancelled."""
        self.cancelled[session_id] = True
        ctx = self.active_sessions.get(session_id)
        # User-facing status: cancelled (A2c). Guard against an already-
        # terminal conversation (e.g. already SUCCESS/ERROR).
        if ctx is not None and not ctx.conversation_status.is_terminal():
            try:
                ctx.conversation_status.transition(ConversationStatus.CANCELLED)
            except ValueError:
                pass

    def _turn_in_flight(self) -> bool:
        """Whether a turn is running right now, lock in hand.

        Deliberately conservative: an unbuilt or free lock is "nothing is
        running", and anything else is treated as a live turn whose own
        cleanup owns the teardown. Reading the slot rather than the
        ``turn_lock`` property keeps this callable from sync code and from a
        thread with no loop of its own.
        """
        lock = self._turn_lock
        return bool(lock is not None and lock.locked())

    # ------------------------------------------------------------------
    # Packet 07: the interrupt algebra at the machine edge
    # ------------------------------------------------------------------

    def request_stop(self, session_id: str) -> str:
        """Generation-claimed stop of the running turn (Packet 07 B1).

        Returns ``"stopped"`` or ``"turn completed, stop declined"`` —
        never both, never a retry. The stop carries the generation the
        running turn stamped at its start (Hermes ``require_generation``);
        the claim executes only while that generation is still current,
        exactly once. The RESPONDING finalize stamp is the final mutation
        edge: once the turn's answer is committed the claim is stale, and a
        stop that loses that race declines instead of firing on a turn
        that already delivered.

        A turn paused on a confirmation (its stream already closed) is
        stopped through ``cancel_session``'s teardown — nothing is racing,
        no claim is needed. Like ``cancel_session``, this runs on a
        different request while the turn is mid-flight: it touches only
        the ``cancelled`` flag and the user-facing status, never the
        turn's own writes, which the turn's finally owns.
        """
        if session_id not in self.active_sessions:
            # A07-G9: a turn queued on the turn lock has not entered
            # active_sessions yet, so it used to be unstoppable -- the
            # user's stop declined and the queued turn ran anyway the
            # moment the lock freed. A queued session is stoppable: the
            # flag is raised now and process() reads it the instant it
            # takes the lock.
            if session_id in self._queued_sessions:
                self._flag_cancelled(session_id)
                return "stopped"
            return "turn completed, stop declined"
        # A07 bug 2: the paused rule was asymmetric -- cancel_session
        # tore a paused turn down whether or not the lock was held, and
        # this path only looked at the lock. A pause can be reached with
        # the generator suspended on its last event, still holding the
        # lock, so both facts have to be read here for the two verbs to
        # agree.
        paused = self.current_state == AgentState.AWAITING_CONFIRMATION
        if paused or not self._turn_in_flight():
            # Paused on a confirmation, or a turn whose finally has not
            # run yet: nothing is racing and no claim is needed.
            self._flag_cancelled(session_id)
            self._stop_teardown(session_id)
            return "stopped"
        generation = self._turn_generation
        if generation is None:
            # Defensive: a turn in flight is stamped at its first sync
            # step under the lock, so this cannot happen on the normal
            # path. Decline rather than fire a claim nobody can vouch for.
            return "turn completed, stop declined"

        def _abort() -> bool:
            # The same flag _drive polls between steps and between
            # events; the turn's own finally does the teardown and names
            # the turn cancelled. The claim's single-shot lock is what
            # keeps two stops from both firing on one turn.
            self._flag_cancelled(session_id)
            return True

        if self.turn_activity.claim(generation, _abort) is None:
            # Stale (the turn finalized between observation and claim) or
            # already claimed (another stop got there first and its flag
            # is up). Either way this caller stopped nothing new; say
            # "stopped" when the turn is already stopping, else decline.
            if self.cancelled.get(session_id):
                return "stopped"
            return "turn completed, stop declined"
        return "stopped"

    def request_steer(self, text: str) -> Dict[str, Any]:
        """Queue a steer for the running turn (Packet 07 B2).

        Never interrupts: the text rides the single replace-not-grow
        pending slot for the running session and is applied at the next
        batch boundary (``_drive``'s between-steps seam), where it is
        appended to the last tool result — or, when the turn has produced
        no tool result yet, enters the observations as its own
        ``[steered]`` line so the next model call still sees it.
        """
        if not self._turn_in_flight() or self.ctx is None:
            return {"accepted": False, "reason": "no turn in flight"}
        session_id = self.ctx.session_id
        pending = self._pending_steer.setdefault(session_id, [])
        replaced = bool(pending)
        # A07-G6: steers CONCATENATE. The slot used to be replace-not-grow,
        # so a second arrival before the boundary erased the first -- and
        # both had been answered "accepted". Every accepted steer is
        # delivered; ``replaced`` keeps its name and now means "there was
        # already one pending", which is what the surface renders.
        pending.append(text)
        return {
            "accepted": True,
            "replaced": replaced,
            "reason": "steer queued for the next batch boundary",
        }

    def _drain_pending_steer(self) -> None:
        """Apply the queued steer at the batch boundary (Packet 07 B2).

        Called from ``_drive`` between handler steps — the seam where the
        next model call will re-read the observations.
        ``apply_steer_to_results`` owns the append (steers concatenate,
        ``\\n[steered]`` marker); a turn with no tool result yet takes the
        fresh-observation fallback so the text still reaches the model
        instead of waiting for a boundary that may never come.
        """
        ctx = self.ctx
        if ctx is None:
            return
        pending = self._pending_steer.get(ctx.session_id) or []
        if not pending:
            return
        view: List[Dict[str, Any]] = []
        if ctx.observations:
            name = ctx.tool_calls[-1].name if ctx.tool_calls else "tool"
            view = [{"name": name, "output": ctx.observations[-1]}]
        for text in pending:
            applied = apply_steer_to_results(view, text)
            if applied is not None:
                # The apply fn mutated the view's copy of the last
                # observation; write the appended text back to the line
                # the context assembler actually reads.
                ctx.observations[-1] = applied
            else:
                ctx.add_observation(
                    f"{STEER_MARKER.strip()}\n{text}\n{STEER_MARKER_CLOSE.strip()}"
                )
        self._pending_steer.pop(ctx.session_id, None)

    def _arrival_below_turn_floor(
        self, speaker_role, identifier_claim, channel
    ) -> bool:
        """Does this arrival stand below the running turn's role floor?

        R-01 Phase A. Every mid-turn verb acts ON the running turn, so
        the speaker who arrives must stand at least where the speaker
        who started it stands. Both sides are read through
        ``role_gate.turn_role_order`` -- the existing role table capped
        by the existing claim ladder -- so this adds no role vocabulary
        of its own (the packet's STOP condition).

        Fail-closed defaulting: an arrival whose caller stamped no role
        reads as its channel's own ``default_role`` (voice: unknown),
        and only a caller with no channel at all -- the back-compat seam
        for embedders predating the channel layer -- reads as the
        dashboard's admin.
        """
        running = self.ctx
        if running is None:
            return False
        try:
            from ..tools.role_gate import turn_role_order
        except Exception as e:  # pragma: no cover - import-time only
            logger.warning("role floor unavailable; refusing arrival: %s", e)
            return True
        if speaker_role:
            arrival_role = speaker_role
        elif channel is not None:
            arrival_role = channel.default_role
        else:
            arrival_role = "admin"
        arrival = turn_role_order(
            arrival_role,
            identifier_claim.strength if identifier_claim is not None else None,
        )
        running_claim = getattr(running, "identifier_claim", None)
        floor = turn_role_order(
            getattr(running, "speaker_role", None) or "admin",
            running_claim.strength if running_claim is not None else None,
        )
        return arrival < floor

    def _arrival_refusal(self, text: str) -> str:
        """Why this arrival cannot act on the running turn, or "".

        A07-G3 and A07 bug 1. Each of these used to be answered
        ``steer_accepted`` and then quietly dropped -- the pending slot
        was drained at a batch boundary the turn would never reach again,
        or the text was a blank line nobody wanted. The refusal is what
        lets the surface do the right thing instead: send it as the next
        turn.
        """
        from .steering import (
            REASON_ANSWER_ALREADY_COMMITTED,
            REASON_EMPTY_ARRIVAL,
            REASON_TURN_ALREADY_STOPPED,
        )
        if not (text or "").strip():
            return REASON_EMPTY_ARRIVAL
        running = self.ctx
        if running is not None and self.cancelled.get(running.session_id):
            return REASON_TURN_ALREADY_STOPPED
        # The RESPONDING finalize stamp is the answer-commit edge: after
        # it the running generation has moved past the one the turn
        # started under, and nothing will re-read the observations.
        if (
            self._turn_generation is not None
            and self.turn_activity.generation != self._turn_generation
        ):
            return REASON_ANSWER_ALREADY_COMMITTED
        return ""

    def handle_midturn_arrival(
        self,
        session_id: str,
        text: str,
        channel=None,
        speaker_role=None,
        identifier_claim=None,
    ) -> tuple:
        """Route one arrival that reached the machine while a turn runs.

        Packet 07 B1/B2, plus C3's busy-mode unification: the verbs this
        arrival may use are the *arrival's channel's* ``busy_verbs``
        (D-4 design §4 — busy behavior is a capability of the channel,
        not a user setting). A verb the channel does not declare
        degrades before the algebra ever sees it: over the voice and
        terminal channels (``{steer}`` / ``{queue, steer}``) a ``/stop``
        is not a command — it steers, the corrective verb both declare —
        and the generation-claiming stop path is the dashboard's own
        (``{stop, steer}``). ``channel=None`` (the Wyoming seam and any
        embedder predating the channel layer) keeps the dashboard's
        verb set exactly — today's behavior.

        Returns ``(decision, events)``: ``events is None`` means
        NORMAL_TURN and the caller runs an ordinary turn; otherwise the
        events are the arrival's own observable verdict — a steer rides
        the single pending slot, a stop claims the running turn's
        activity generation, a refusal says which floor it stood below —
        so no mid-turn arrival is ever silently dropped. The running
        turn is ``self.ctx``'s (the lock serialises everything), not the
        arrival's own session id.

        ``speaker_role`` and ``identifier_claim`` are the arrival's
        STAMPED identity — what the door derived from the credential it
        validated, never what the wire said (R-01 Phase A). The talk
        door stamps them before it calls here; that ordering is the fix
        for the OSS pass's #1 finding, and this signature is what makes
        the old order impossible to restore by accident.
        """
        if not self._turn_in_flight() or self.ctx is None:
            return (
                decide_midturn(turn_active=False, is_command=False, text=text),
                None,
            )
        # The channel's declared verbs govern this arrival. An absent
        # channel is the dashboard's set (stop declared) — the
        # pre-C3 behavior every existing caller relies on.
        stop_declared = True
        if channel is not None:
            stop_declared = "stop" in (channel.busy_verbs or frozenset())
        tokens = (text or "").strip().split()
        # Only "/stop" is a machine command today: the composer's other
        # slash commands ("/model") are parsed away client-side, and an
        # unknown "/anything" is text the model should see, not a verb.
        # C3: a channel that does not declare stop never sees its
        # arrivals as commands — "/stop" spoken over the voice channel
        # is text, and text steers.
        is_command = (
            stop_declared
            and bool(tokens)
            and tokens[0].lower() == "/stop"
        )
        tool_batch_in_flight = self.current_state in (
            AgentState.EXECUTING,
            AgentState.SEARCHING,
            AgentState.READING,
        )
        decision = decide_midturn(
            turn_active=True,
            is_command=is_command,
            text=text,
            tool_batch_in_flight=tool_batch_in_flight,
            # REDIRECT awaits a cancellable provider client (the Phase B
            # verify-first finding: none of today's clients expose one),
            # so the predicate is never reported and redirect stays
            # dormant, degrading to steer by decide_midturn's rules.
            in_model_request=False,
            below_role_floor=self._arrival_below_turn_floor(
                speaker_role, identifier_claim, channel
            ),
            refusal=self._arrival_refusal(text),
        )
        if decision.verb == Verdict.REFUSED:
            # The refusal is the arrival's verdict, and the room hears
            # that one was refused — never the words that were refused.
            self._tee_publish(
                "steer_refused", session_id,
                reason_code=decision.reason_code,
                running_turn=self.ctx.session_id,
            )
            logger.warning(
                "midturn arrival refused: reason=%s arrival_session=%s "
                "running_session=%s modality=%s",
                decision.reason_code, session_id, self.ctx.session_id,
                getattr(channel, "id", None),
            )
            events = [
                StreamEvent(
                    type="steer_refused",
                    session_id=session_id,
                    data={
                        "reason_code": decision.reason_code,
                        "reason": decision.reason,
                    },
                )
            ]
            return decision, events
        if decision.verb == Verdict.STOP:
            outcome = self.request_stop(self.ctx.session_id)
            # C4: the verdict rides the tee with the arrival's session id
            # (the arrival's own stream answers its sender; the tee tells
            # the room). "stopped" is the outcome word, never the words.
            self._tee_publish(
                "stop_outcome", session_id,
                outcome=outcome, running_turn=self.ctx.session_id,
            )
            if outcome == "stopped":
                # Existing vocabulary only: the arrival's stream closes
                # the way the stopped turn's own stream closes.
                events = [
                    StreamEvent.cancelled(session_id),
                    StreamEvent.session_ended(session_id, 0, 0),
                ]
            else:
                # New event type; backend-only until a frontend consumer
                # renders it (see the packet's Phase C decisions).
                events = [
                    StreamEvent(
                        type="stop_declined",
                        session_id=session_id,
                        data={"reason": outcome},
                    )
                ]
            return decision, events
        if decision.verb in (Verdict.STEER, Verdict.REDIRECT):
            steer = self.request_steer(text)
            # C4: the steer verdict rides the tee — flags only, never the
            # steered text itself (the room does not need the words).
            self._tee_publish(
                "steer_accepted", session_id,
                running_turn=self.ctx.session_id,
                replaced=bool(steer.get("replaced")),
                demoted="interrupt_demoted_to_steer" in decision.notes,
            )
            events = [
                StreamEvent(
                    type="steer_accepted",
                    session_id=session_id,
                    data={
                        "reason": decision.reason,
                        "replaced": bool(steer.get("replaced")),
                        "demoted": "interrupt_demoted_to_steer" in decision.notes,
                    },
                )
            ]
            return decision, events
        return decision, None

    def _touch_activity(self, note: str) -> None:
        """Stamp the running turn's liveness clock (A07-G10).

        One clock, on the turn's own context: handler entry, tool start
        and completion, and every stream chunk. The watchdog reads this
        and nothing else -- a second derived clock is how "stalled" and
        "working" start disagreeing.
        """
        ctx = self.ctx
        if ctx is not None:
            ctx.touch(note)

    async def _turn_watchdog(self, session_id: str, generation: int) -> None:
        """End a turn that has stopped making progress (A07-G10).

        Bound to the generation it observed: the abort goes through the
        same single-shot ``TurnActivity`` claim a stop uses, so a sampler
        that wakes late can only ever end the turn it was watching, never
        a later one under the same session id.

        A turn paused on a confirmation is not stalled -- a person may
        take a quarter of an hour to answer, and waiting is not wedging.
        """
        while True:
            await asyncio.sleep(self.STALL_POLL_SECONDS)
            ctx = self.ctx
            if ctx is None or ctx.session_id != session_id:
                return
            if self.current_state == AgentState.AWAITING_CONFIRMATION:
                # Not stalled, and not this watchdog's turn to end: the
                # pause has its own teardown path.
                return
            if ctx.idle_seconds() < self.TURN_STALL_SECONDS:
                continue
            note = ctx.last_activity_note
            idle = ctx.idle_seconds()

            def _abort() -> bool:
                logger.error(
                    "turn liveness watchdog: session=%s idle=%.0fs "
                    "last_activity=%r -- ending the turn",
                    session_id, idle, note,
                )
                self._flag_cancelled(session_id)
                return True

            self.turn_activity.claim(generation, _abort)
            return

    async def _model_call(self, coro):
        """Await a model request, abandoning it if the turn is stopped.

        A07-G5. ``await self.llm.chat(...)`` is the longest uninterruptible
        stretch of a turn: ``_drive`` polls the stop flag between steps and
        between events, and a model call is neither -- so a stop issued
        while the model was thinking was honoured only once the model had
        finished thinking, and the user watched the answer they had just
        stopped arrive in full.

        The request runs as a task; this waits on it in
        ``STOP_POLL_SECONDS`` slices and cancels it the moment the flag is
        up. Cancelling the task is what actually reaches the provider
        client's own request (an ``aiohttp``/``httpx`` await raises
        ``CancelledError`` and closes the connection); nothing here needs
        the client to expose an abort handle of its own.
        """
        session_id = self.ctx.session_id if self.ctx is not None else None
        task = asyncio.ensure_future(coro)
        while True:
            done, _pending = await asyncio.wait(
                {task}, timeout=self.STOP_POLL_SECONDS
            )
            if task in done:
                return task.result()
            if session_id is not None and self.cancelled.get(session_id):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                logger.info(
                    "model request abandoned by stop: session=%s", session_id
                )
                raise TurnStopped("model request stopped by the user")

    async def _model_stream(self, agen):
        """Stream a model response, abandoning it if the turn is stopped.

        The streaming twin of ``_model_call`` (A07-G5). ``_drive`` polls
        the stop flag between the events a handler yields, which covers
        every chunk after the first -- but not the wait *for* the first
        chunk, which is the whole of a wedged request. Each ``__anext__``
        goes through the same poll, and the generator is closed on the
        way out so the provider connection does not outlive the turn.
        """
        try:
            while True:
                try:
                    chunk = await self._model_call(agen.__anext__())
                except StopAsyncIteration:
                    return
                yield chunk
        finally:
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass

    def _detect_oscillation(self) -> bool:
        """Detect A→B→A→B pattern indicating infinite loop."""
        h = self.ctx.state_history
        if len(h) >= 4:
            return h[-4] == h[-2] and h[-3] == h[-1]
        return False
    
    async def _transition(self, new_state: AgentState) -> StreamEvent:
        """
        Transition to a new state with validation.
        
        Args:
            new_state: Target state
            
        Returns:
            StreamEvent for the state change
            
        Raises:
            ValueError: If transition is not valid
        """
        valid_transitions = self.TRANSITIONS.get(self.current_state, [])
        if new_state not in valid_transitions:
            raise ValueError(
                f"Invalid transition: {self.current_state} → {new_state}. "
                f"Valid: {valid_transitions}"
            )
        
        old_state = self.current_state
        self.current_state = new_state
        self.ctx.state_history.append(new_state.value)

        logger.debug(f"State transition: {old_state.value} → {new_state.value}")

        # C4 (turn-event tee): the reduced set's backbone — state
        # transitions, without any content.
        self._tee_publish(
            "state_change",
            self.ctx.session_id,
            **{"from": old_state.value, "to": new_state.value},
        )

        return StreamEvent.state_change(
            self.ctx.session_id,
            new_state.value,
            old_state.value
        )

    def _set_conversation_status(
        self, new_status: ConversationStatus, **kwargs
    ) -> StreamEvent:
        """Transition the user-facing conversation status and return its SSE event.

        Validates the transition via ConversationStatusMachine and emits a
        ``conversation_status`` StreamEvent carrying the new status plus any
        blocked_action / waiting_for context (A2c).
        """
        self.ctx.conversation_status.transition(new_status, **kwargs)
        # C4 (turn-event tee): user-facing statuses are part of the
        # reduced set — the waiting/blocked/in-progress line a second
        # screen would want.
        self._tee_publish(
            "conversation_status",
            self.ctx.session_id,
            status=self.ctx.conversation_status.current(),
            waiting_for=self.ctx.conversation_status.waiting_for(),
        )
        return StreamEvent.conversation_status(
            self.ctx.session_id,
            self.ctx.conversation_status.current(),
            blocked_action=self.ctx.conversation_status.blocked_action(),
            waiting_for=self.ctx.conversation_status.waiting_for(),
        )

    async def _emit_somatic_block(self, block: Any) -> StreamEvent:
        """Build a somatic_block SSE event and also publish it to the
        ProactiveEventBus (C1d). Best-effort on the proactive side.
        """
        event = StreamEvent.somatic_block(
            self.ctx.session_id,
            block.block_type.value if hasattr(block.block_type, "value") else str(block.block_type),
            block.id,
            block.status.value if hasattr(block.status, "value") else str(block.status),
            finding_id=block.finding_id,
            proposal_id=block.proposal_id,
            approval_request_id=block.approval_request_id,
            action_id=block.action_id,
            reflection_id=block.reflection_id,
            # Somatic blocks are tagged with the hidden thread (spec §8);
            # the event's session_id stays per turn for routing. Before a
            # thread exists (no manager) the turn's session id stands in.
            thread_id=self.ctx.thread_id or self.ctx.session_id,
        )
        try:
            from ..proactive.events import ProactiveEvent, get_event_bus
            pe = ProactiveEvent.create(
                type="somatic_block",
                severity="info",
                title=f"Block {event.data['block_type']}: {event.data['status']}",
                body=(
                    f"session={block.session_id} "
                    f"thread={self.ctx.thread_id or self.ctx.session_id} block={block.id}"
                ),
            )
            await get_event_bus().publish(pe)
        except Exception as e:
            logger.debug(f"Proactive somatic publish failed (non-fatal): {e}")
        # C4 (turn-event tee): terminal-block markers are in the reduced
        # set — type and status only, never the block's content.
        self._tee_publish(
            "somatic_block",
            self.ctx.session_id,
            block_type=event.data["block_type"],
            block_id=event.data["block_id"],
            status=event.data["status"],
        )
        return event

    # ------------------------------------------------------------------
    # Subagents (D1d)
    # ------------------------------------------------------------------

    async def spawn_subagent(
        self,
        agent_type: str,
        task_goal: str,
        scoped_sources: Optional[List[str]] = None,
        agent_config: Optional[Dict] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Spawn a subagent and move the conversation to WAITING_FOR_EVENTS.

        Yields a conversation_status (WAITING_FOR_EVENTS) event and a
        subagent_event (spawned). No-op (yields nothing) if no subagent manager
        is wired. Stores the handle id on ctx for await_subagent.
        """
        if self.subagents is None:
            return
        handle = self.subagents.spawn(
            agent_type, task_goal, scoped_sources or [],
            agent_config=agent_config,
        )
        self.ctx.current_subagent_handle_id = handle.id
        yield self._set_conversation_status(
            ConversationStatus.WAITING_FOR_EVENTS, waiting_for=handle.id
        )
        yield StreamEvent.subagent_event(
            self.ctx.session_id, "spawned", handle.id,
            agent_type=agent_type, status=handle.status,
        )

    async def await_subagent_completion(
        self, timeout: float = 300.0
    ) -> AsyncIterator[StreamEvent]:
        """Wait for the current subagent to finish, then resume (IN_PROGRESS).

        Polls the handle status until terminal or ``timeout``. Yields a
        subagent_event (completed/failed) and a conversation_status (IN_PROGRESS)
        event. Clears the pending handle id from ctx.
        """
        handle_id = self.ctx.current_subagent_handle_id
        if not handle_id or self.subagents is None:
            return
        deadline = time.time() + timeout
        # Hold the handle object; its .status is mutated externally by the
        # manager's complete()/cancel() (which also remove it from the active
        # set), so we poll the object rather than re-fetching via get().
        handle = self.subagents.get(handle_id)
        while handle is not None and not _subagent_terminal(handle.status):
            if time.time() >= deadline:
                break
            await asyncio.sleep(0.1)

        self.ctx.current_subagent_handle_id = None
        if handle is not None:
            yield StreamEvent.subagent_event(
                self.ctx.session_id, handle.status, handle.id,
                agent_type=handle.agent_type, status=handle.status,
                result_block_id=handle.result_block_id,
            )
        yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)
    
    def _get_handler(self) -> Optional[Callable]:
        """Get the handler function for the current state."""
        handlers = {
            AgentState.PLANNING: self._handle_planning,
            AgentState.SEARCHING: self._handle_searching,
            AgentState.READING: self._handle_reading,
            AgentState.EXECUTING: self._handle_executing,
            AgentState.OBSERVING: self._handle_observing,
            AgentState.REFLECTING: self._handle_reflecting,
            AgentState.RESPONDING: self._handle_responding,
            AgentState.ERROR: self._handle_error,
            AgentState.AWAITING_CONFIRMATION: self._handle_awaiting_confirmation,
        }
        return handlers.get(self.current_state)
    
    # -------------------------------------------------------------------------
    # State Handlers
    # -------------------------------------------------------------------------
    
    @property
    def prompt_builder(self):
        """The builder this machine renders prompts with, under the name the
        settings and persona routes hot-reload it by.

        Both routes guard on ``hasattr(agent, 'prompt_builder')`` before
        calling ``reload_personality()``; the constructor keeps the builder as
        ``self.prompts``, so every voice or personality change made in
        Settings was a silent no-op until the next restart (alignment audit
        2026-09-02, C1-04). One object, two names.
        """
        return self.prompts

    def _identity_block(self, response_modality: str = "text") -> str:
        """Who is speaking this turn, rendered by the builder; "" without one.

        Tolerates a builder without the hook (a test double, an out-of-tree
        builder) and a hook that raises: the turn goes on without the block,
        as it did before the block existed, rather than ending with an
        error.
        """
        render = getattr(self.prompts, "build_identity_block", None) if self.prompts else None
        if not callable(render):
            return ""
        try:
            block = render(response_modality=response_modality)
        except Exception as e:
            logger.warning(f"Identity block unavailable this turn: {e}")
            return ""
        return block.strip() if isinstance(block, str) else ""

    def _install_skill_safety(self) -> None:
        """Bind the turn's composed skill safety onto the executor's framework.

        ``self.tools.safety`` and not a fresh framework: that is the instance
        ToolExecutor classifies against and the one ``RoleGate`` wraps, so both
        branches of the executor's gate see the same rules. A skill installed
        anywhere else would read as bound and enforce nothing -- which is what
        DEFECT-1's third break already was.

        Never raises: a skill whose safety cannot be composed costs the turn
        its extra rules, not its answer. The base classifier is unaffected,
        and skill safety only ever raises a risk level (invariant 6).
        """
        safety = getattr(getattr(self, "tools", None), "safety", None)
        if safety is None or not hasattr(safety, "set_skill_safety"):
            return
        try:
            intake = getattr(self.ctx, "intake", None)
            matches = getattr(intake, "active_skills", None) if intake else None
            if not matches:
                safety.set_skill_safety(None)
                return
            from ..skills.composer import compose_matches

            composed = compose_matches(matches)
            safety.set_skill_safety(composed.safety if composed else None)
            if composed:
                logger.info(
                    "Skill safety installed for this turn: %s",
                    ", ".join(m.name for m in matches),
                )
        except Exception:
            logger.warning("installing skill safety failed; continuing",
                           exc_info=True)
            try:
                safety.set_skill_safety(None)
            except Exception:
                pass

    def _clear_skill_safety(self) -> None:
        """Drop the turn's skill rules. Never raises."""
        safety = getattr(getattr(self, "tools", None), "safety", None)
        if safety is None or not hasattr(safety, "set_skill_safety"):
            return
        try:
            safety.set_skill_safety(None)
        except Exception:
            logger.warning("clearing skill safety failed", exc_info=True)

    def _record_skill_activation(self) -> None:
        """Promote the turn's skill activations to skill_events (SK-2 §6).

        Seam 2: matcher and explicit activations were invisible durable-wise
        (a debug log line); now each one is a row keyed by the skill's
        stable id — `explicit` for a `/name` invocation, `matched` for a
        trigger match — with the turn's ids so a run's rows join (the read
        receipts the executor writes carry the same run_id). Runs inside
        the turn lock, after `_begin_turn` entered the turn scope. A skill
        that never got an id writes nothing: the row keys on identity,
        never name. Never raises — telemetry is reportability, not a gate.
        """
        try:
            intake = getattr(self.ctx, "intake", None)
            matches = getattr(intake, "active_skills", None) if intake else None
            if not matches:
                return
            from ..continuity.provenance import current_turn
            from ..skills.telemetry import record_skill_event

            run_id = current_turn.get()
            session_id = getattr(self.ctx, "session_id", None)
            for match in matches:
                skill = getattr(match, "skill", None)
                skill_id = getattr(skill, "id", None)
                if not skill_id:
                    continue
                record_skill_event(
                    skill_id,
                    "explicit" if getattr(match, "explicit", False) else "matched",
                    session_id=session_id,
                    run_id=run_id,
                    detail={
                        "name": getattr(skill, "name", ""),
                        "score": getattr(match, "score", 0),
                    },
                )
        except Exception:
            logger.warning("recording skill activations failed; continuing",
                           exc_info=True)

    #: How many ledger rows the Eyes block carries, and how far back it looks.
    #: An idle day is thousands of rows, so this is a cap, not a window: the
    #: block is grounding -- what has just happened around this machine -- not
    #: a log, and a model handed two hundred lines reads none of them.
    WORLD_OBSERVATION_LIMIT = 12
    WORLD_OBSERVATION_HOURS = 24

    def _reset_world_observations(self) -> None:
        """Drop the turn's cached Eyes rows, so the next turn re-reads."""
        self._world_obs_cache = None

    def _world_observations(self) -> List[str]:
        """Recent event-ledger rows as citable prompt lines (A4).

        Computed once per turn and cached. PLANNING and RESPONDING both ask
        for this, and an event landing between them would otherwise let the
        model plan against a world that had changed by the time it answered,
        with nothing to tell it that had happened. Stale-within-a-turn is the
        correct trade: the turn is the unit the model reasons over.

        Grounding is unconditional: this is not lens-selected and not gated on
        the proactivity dial. What Halbert has just seen around it is context
        for answering, the same way vitals are -- the lens selects *remarks*,
        which is a different thing (CD-3).

        Ordered newest first and capped. Never raises: a ledger that cannot be
        read costs the turn its grounding, not its answer -- the same posture
        get_timeline_store() already takes.
        """
        cached = getattr(self, "_world_obs_cache", None)
        if cached is not None:
            return cached
        try:
            from ..integrations.cognition_wiring import get_timeline_store
            from ..continuity.timeline import as_prompt_line

            store = get_timeline_store()
            if store is None:
                self._world_obs_cache = []
                return []
            since = time.time() - self.WORLD_OBSERVATION_HOURS * 3600
            # Over-fetch, because deduplication below removes rows: a person
            # arriving writes both the state change and the occupancy event,
            # with the same title by design, and rendering both reads as two
            # arrivals.
            rows = store.query(since=since, limit=self.WORLD_OBSERVATION_LIMIT * 3)

            lines: List[str] = []
            seen: set = set()
            for row in rows:
                # Keyed on (title, second) rather than title alone: the same
                # thing happening twice an hour apart is two facts, and
                # collapsing those would hide the recurrence the ledger exists
                # to record. Only rows describing one moment collapse.
                key = ((row.get("title") or "").strip().lower(),
                       int(row.get("timestamp") or 0))
                if key in seen:
                    continue
                seen.add(key)
                lines.append(as_prompt_line(row))
                if len(lines) >= self.WORLD_OBSERVATION_LIMIT:
                    break
            self._world_obs_cache = lines
            return lines
        except Exception:
            logger.warning("reading the event ledger for the Eyes block failed; "
                           "continuing without grounding", exc_info=True)
            self._world_obs_cache = []
            return []

    #: Event type for an interest injection. It is an event -- it happened,
    #: at a time, on a thread -- so it lives in the event ledger, which is
    #: what makes the once-a-day rule survive a restart and gives the
    #: `memory_recalled` chip a row to cite.
    INTEREST_RECALL_EVENT = "interest_recalled"

    def _reset_interest_block(self) -> None:
        self._interest_cache = None

    def _interest_block(self) -> str:
        """The one remembered interest this turn may carry (RECALL-v1).

        Computed once per turn and cached: ``_build_messages`` runs at both
        LLM call sites, and a second selection could differ -- a model that
        planned with a fact and answered without it has no way to notice.

        Never raises. A recall that fails costs the turn its colour, not its
        answer.
        """
        cached = getattr(self, "_interest_cache", None)
        if cached is not None:
            return cached
        block = ""
        try:
            from ..continuity.interests import Interest
            from ..continuity.recall_interest import (
                RECALL_COOLDOWN_SECONDS,
                render_interest_block,
                select_interest,
            )
            from ..integrations.cognition_wiring import (
                get_persona_memory_store,
                get_timeline_store,
            )

            store = get_persona_memory_store()
            intake = getattr(self.ctx, "intake", None)
            if store is None or intake is None:
                self._interest_cache = ""
                return ""

            rows = [
                i for i in (
                    Interest.from_persona_memory(m)
                    for m in (getattr(store, "list_memories", list)() or [])
                ) if i is not None
            ]
            if not rows:
                self._interest_cache = ""
                return ""

            thread_id = getattr(self.ctx, "thread_id", "") or ""
            timeline = get_timeline_store()
            last_at = None
            if timeline is not None and thread_id:
                prior = timeline.query(
                    event_type=self.INTEREST_RECALL_EVENT,
                    entity_id=thread_id,
                    since=time.time() - RECALL_COOLDOWN_SECONDS,
                    limit=1,
                )
                if prior:
                    last_at = prior[0].get("timestamp")

            dial = "balanced"
            try:
                from ..config.being_config import load_being_config
                dial = getattr(load_being_config(), "proactivity", "balanced") or "balanced"
            except Exception:
                pass

            chosen = select_interest(
                rows, intake, thread_id=thread_id, dial=dial,
                last_injection_at=last_at,
            )
            if chosen is None:
                self._interest_cache = ""
                return ""

            block = render_interest_block(chosen)
            self._record_interest_recall(chosen, thread_id, timeline)
        except Exception:
            logger.warning("interest recall failed; continuing without it",
                           exc_info=True)
            block = ""
        self._interest_cache = block
        return block

    def _record_interest_recall(self, interest, thread_id: str, timeline) -> None:
        """Log the injection, so it is citable and countable.

        Recorded whether or not the model ends up using it: the person is
        entitled to know the fact was put in front of it, and a chip that only
        appears when the model happened to mention something is not
        visibility.
        """
        if timeline is None or not thread_id:
            return
        try:
            from ..continuity.timeline import TimelineEvent

            timeline.record(TimelineEvent(
                timestamp=time.time(),
                event_type=self.INTEREST_RECALL_EVENT,
                source="recall",
                entity_id=thread_id,
                title=f"Recalled: {interest.topic}",
                data={"topic": interest.topic,
                      "origin": getattr(interest.origin, "value", ""),
                      "reason": interest.reason},
            ))
        except Exception:
            logger.debug("could not record the interest recall", exc_info=True)

    def _composed_prompt_block(self) -> str:
        """The active skills' expertise text, or "" when none matched.

        Reads the same ``active_skills`` the state machine already composes
        for retrieval scoping. Never raises: a skill that cannot be composed
        costs the turn its expertise, not its answer -- the rule intake
        already applies to matching.
        """
        try:
            intake = getattr(self.ctx, "intake", None)
            matches = getattr(intake, "active_skills", None) if intake else None
            if not matches:
                return ""
            from ..skills.composer import compose_matches

            composed = compose_matches(matches)
            return (composed.prompt or "") if composed else ""
        except Exception:
            logger.warning("composing the skill prompt failed; continuing",
                           exc_info=True)
            return ""

    def _catalog_block(self) -> str:
        """The ``<available_skills>`` catalog, or "" without a registry.

        Track B disclosure (skills SK-2, design §2.1): every consultable
        skill is listed by name, description and location so the model can
        read one on demand. Rendered from the registry's structured
        snapshot -- keyed to its snapshot_version, never re-parsed from
        this prompt -- and the skills matched this turn are passed as
        protected, so the truncation ladder cuts them last. Never raises:
        a catalog that cannot render costs the turn its disclosure, not
        its answer.
        """
        try:
            pipeline = getattr(self, "intake", None)
            registry = getattr(pipeline, "skill_registry", None) if pipeline else None
            if registry is None:
                return ""
            turn = getattr(self.ctx, "intake", None)
            protected = getattr(turn, "active_skill_names", None) or ()
            from ..skills.catalog import render_available_skills

            return render_available_skills(registry, protected=protected)
        except Exception:
            logger.warning("rendering the skills catalog failed; continuing",
                           exc_info=True)
            return ""

    def _stable_head(self, identity: str, catalog: str,
                     skills_block: str) -> str:
        """The cache-stable head of messages[0], closed by the boundary.

        §2.2: identity, catalog and bound bodies are a pure function of
        versioned inputs, assembled through `build_stable_prefix` and
        followed by the literal CACHE_BOUNDARY marker; everything volatile
        -- receipt block, folded history rows, the turn prompt -- is
        appended below it by `_build_messages`. The join is sha-keyed and
        memoized; a failure here falls back to the plain join rather than
        costing the turn the head at all.
        """
        try:
            from ..prompts.agent_prompts import (
                CACHE_BOUNDARY_MARKER,
                build_stable_prefix,
            )
            stable = build_stable_prefix(identity, catalog, skills_block)
        except Exception:
            logger.warning("stable-prefix assembly failed; joining plainly",
                           exc_info=True)
            stable = "\n\n".join(p for p in (identity, catalog, skills_block) if p)
        if not stable:
            return ""
        return f"{stable}\n\n{CACHE_BOUNDARY_MARKER}"

    def _build_messages(
        self, prompt: str, tail: str = "", response_modality: str = "text",
    ) -> List[Dict[str, Any]]:
        """Identity, instructions, then the prior turns, then the new question.

        The identity block (``AgentPromptBuilder.build_identity_block``: who
        this machine is in the configured voice, which body it is at, what it
        is for) leads ``messages[0]`` on both LLM calls of a turn. It goes
        first because the head of the system message is the one position
        every provider path reads as "who you are", and because before the
        merge nothing put the identity in front of the model at all (C1-01).
        With no prompt builder nothing is prepended: RESPONDING's own fallback
        prompt already opens with ``_fallback_identity``.

        Conversation lives in this array and nowhere else: the context
        assembler is no longer handed the history, and its memory source drops
        this session's own stored interactions, because either one flattened
        into ``prompt`` would send earlier turns twice — once as prose and once
        as messages — for no extra meaning.

        ``ctx.thread_receipt_block`` — the "Earlier in this subject" summary
        of the turns this thread's window could not afford — joins the
        leading instructions rather than sitting mid-array, because it is
        context *about* the conversation and not a line anyone said, and
        because one system message at the front is the only shape every
        provider path agrees on. A ``system`` row that survives on
        ``conversation_history`` (a resumed subject's receipt, a summary from
        an older store) is folded in the same way, as a safety net — and
        defanged on the way in. That row is untrusted text (a receipt is built
        from command stdout and log lines) and it is being concatenated into
        the instructions, which is precisely the position
        ``AgentPromptBuilder._defang_continuity`` /
        ``_defang_line_markers`` exist to protect; before the merge they
        guarded it inside ``_history_section``, which this array replaced.

        ``tail`` is the continuity hint, and it is glued to the front of the
        final user message instead of being built into ``prompt``. A10 put it
        at the tail of the prose for a reason — a local model whose context
        window is too small drops the *head* of what it is sent — and array
        position now serves that purpose better than prose position: the hint
        travels with the question, which is the one thing the model must
        still see. Note the order: ``_merge_adjacent`` runs *after* the glue,
        so a stranded unanswered user turn folds in ahead of the hint. That
        is correct — the hint stays adjacent to the query it qualifies.
        """
        identity = self._identity_block(response_modality)
        # B2: the matched skills' expertise, between identity and the prompt.
        # Never PromptBuilder.build_prompt, which is dead on the chat path --
        # its one live consumer is scheduler/autonomous_tasks. This block is
        # sent on both LLM calls of a turn, so it is paid for twice; it is
        # capped in the composer for that reason.
        skills_block = self._composed_prompt_block()
        # SK-2: the <available_skills> catalog rides between identity and
        # the bound bodies, and the whole head is closed by the literal
        # CACHE_BOUNDARY marker (§2.2) -- everything above it versioned,
        # everything below it volatile.
        catalog = self._catalog_block()
        head = self._stable_head(identity, catalog, skills_block)
        # RECALL-v1: its own dated block, BELOW the cache boundary. It is a
        # per-turn selection -- a different interest, or none, on the next
        # turn -- so putting it in the stable head would invalidate the
        # cached prefix on every turn to save nothing.
        interest_block = self._interest_block()
        below = "\n\n".join(p for p in (interest_block, prompt) if p)
        content = f"{head}\n\n{below}" if head else below
        messages: List[Dict[str, Any]] = [{"role": "system", "content": content}]
        if self.ctx.thread_receipt_block:
            messages[0]["content"] += "\n\n" + self.ctx.thread_receipt_block
        for msg in (self.ctx.conversation_history or []):
            content = content_to_text(msg.get("content", ""))
            if not content.strip():
                continue
            role = msg.get("role", "user")
            if role not in ("user", "assistant"):
                messages[0]["content"] += "\n\n" + _defang_system_row(content)
                continue
            messages.append({"role": role, "content": content})
        # Phase 2: use the defanged query if modality wiring set one
        # (strips <speech>/<text>/<modality_context> control tags from
        # untrusted user input per spec 5.11). Falls back to the raw
        # query when the engine is not installed or defanging was skipped.
        # It is read off the per-turn context, never off self — see the
        # field's comment in states.py.
        query = self.ctx.defanged_query or self.ctx.user_query
        messages.append({
            "role": "user",
            "content": f"{tail}\n\n{query}" if tail else query,
        })
        return _merge_adjacent(messages)

    def _tools_supported(self) -> Optional[bool]:
        """Whether the model answering THIS turn can call tools (A9d + P3).

        ``self.llm.tools_supported`` answers for the models the adapter routes
        to *by configuration* — the guide and the specialist. A per-turn pin
        is neither: it is resolved from ``StateContext``, where every other
        per-turn override lives (E-2), and the shared adapter must not be told
        about it, because one adapter serves every concurrent request. So a
        pinned model that had rejected tool schemas still read as "unknown"
        and the preamble went on telling it to call ``recall_thread`` —
        exactly the instruction A9d exists to withhold.

        The narrowing is asked of the adapter (``tools_supported_for``), not
        computed here: which model a *tier* pin resolves to is the route's
        answer to give (D4), and a client without the hook — every test
        double, MockLLMClient — falls back to the plain property.
        """
        supported = getattr(self.llm, "tools_supported", None)
        if not self.ctx:
            return supported
        pin = self.ctx.model_override or self.ctx.tier_override
        narrow = getattr(self.llm, "tools_supported_for", None)
        if not pin or not callable(narrow):
            return supported
        try:
            return narrow(
                model_override=self.ctx.model_override,
                tier_override=self.ctx.tier_override,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Per-turn tool support unavailable: {e}")
            return supported

    def _continuity_tail(self) -> str:
        """This turn's continuity hint as the tail of the final user message.

        Empty when there is no hint or no prompt builder. The builder still
        owns the wording (voice preamble + hint, and the no-tools variant of
        the preamble when the client fell back); only where it lands changed.
        ``_continuity_section`` returns the two parts as a list, never a
        string.
        """
        if not self.prompts or not self.ctx.continuity_hint:
            return ""
        try:
            parts = self.prompts._continuity_section(
                self.ctx.continuity_hint,
                self._tools_supported(),
            )
        except Exception as e:  # pragma: no cover - builder without the hook
            logger.debug(f"Continuity section unavailable: {e}")
            return ""
        return "\n\n".join(parts) if parts else ""

    def _should_diagnostic_capture(self, tool_name: str) -> bool:
        """Only capture on failures of command-execution tools, not
        search/read/lookup tools. Avoids context pollution from
        unrelated screen state on benign failures. Gated by
        being.yml senses.vision.capture_on_error (default False).
        """
        try:
            from ..vision.config import is_screen_capture_enabled
            if not is_screen_capture_enabled():
                return False
            from ..config.being_config import load_being_config
            being_cfg = load_being_config()
            if not being_cfg.senses.vision.capture_on_error:
                return False
        except Exception:
            return False
        diagnostic_tools = {"run_command", "execute_command", "shell", "bash"}
        return tool_name in diagnostic_tools

    def _screen_is_the_machines_own(self) -> bool:
        """True when a guest fronts and the screen is not the guest's to see.

        The two automatic captures below reach ``vision_tools`` directly, so
        neither passes ``ToolExecutor.execute`` and neither is covered by the
        guest tool mask — a borrowed persona would be handed the active
        window and its OCR without ever asking for a tool. The mask's own
        list is the authority: if ``capture_active_window`` is denied to a
        guest, so is taking one on its behalf.
        """
        try:
            from ..persona.guest import current_guest
            from ..persona.guest_tools import is_tool_allowed_for_guest
        except Exception:
            return False
        if current_guest() is None:
            return False
        return not is_tool_allowed_for_guest("capture_active_window")

    async def _handle_planning(self) -> AsyncIterator[StreamEvent]:
        """
        PLANNING state: Analyze query, create plan, decide next action.
        """
        logger.info(f"PLANNING: {self.ctx.user_query[:50]}...")

        # Auto-capture: if the user's message signals visual intent but no
        # image has been captured yet, grab the active window before planning.
        # Eliminates the 2-turn round-trip where the LLM requests a screenshot
        # it obviously needs. Gated by both the system-level screen capture
        # enable (vision_config.yml) and the persona-level capture_on_intent
        # consent (being.yml senses.vision.capture_on_intent).
        if (self.ctx.intake and getattr(self.ctx.intake, 'has_vision_request', False)
                and not self.ctx.images
                and not self._screen_is_the_machines_own()):
            try:
                from ..vision.config import is_screen_capture_enabled
                if is_screen_capture_enabled():
                    from ..config.being_config import load_being_config
                    being_cfg = load_being_config()
                    if being_cfg.senses.vision.capture_on_intent:
                        from ..tools.vision_tools import capture_active_window_tool
                        result = await capture_active_window_tool({})
                        if isinstance(result, dict) and "image" in result:
                            self.ctx.images = self.ctx.images or []
                            self.ctx.images.append(result["image"])
                            if "ocr_text" in result and result["ocr_text"]:
                                self.ctx.add_observation(
                                    f"[Auto-capture] Active window OCR:\n{result['ocr_text']}"
                                )
            except Exception as e:
                logger.debug(f"Auto-capture in PLANNING skipped: {e}")

        # Assemble context if we have context assembler.
        # NOTE: this is the single context-assembly call site for planning —
        # intake.context_budget controls the token budget, so max_tokens is
        # intentionally not passed (the intake assembler overrides it anyway).
        context_content = ""
        if self.context:
            assembled = await self.context.assemble(
                query=self.ctx.user_query,
                observations=self.ctx.observations,
                world_observations=self._world_observations(),
                intake=self.ctx.intake,
                session_id=self.ctx.session_id,
                retrieval_scope=self.ctx.retrieval_scope,
            )
            context_content = assembled.content
            # Trust boundary latch: once the assembler's backstop flags this
            # turn's context as carrying secrets, every model call this turn
            # (planning, responding, re-entries) must resolve local-only.
            if getattr(assembled, "secure", False):
                if not self.ctx.secure_context:
                    logger.info(
                        "Secure content in assembled context — this turn is "
                        "restricted to local models"
                    )
                self.ctx.secure_context = True
            yield StreamEvent.context_loaded(
                self.ctx.session_id,
                "assembled",
                len(assembled.sources),
                assembled.total_tokens
            )

        # The receipts recall_thread put on the retrieved context reach
        # RESPONDING through build_response_prompt, but ContextAssembler.assemble
        # takes no parameter that carries them — so the PLANNING pass the
        # re-entry pays for saw the recalled subjects' names next to an
        # observation telling the model their receipts were "in the available
        # context", and, with no assembler wired, next to a literal
        # "Available context: (none)" (review: Plan A / A9b). Appended here,
        # after the assembled content and on both prompt paths, so that
        # sentence is true of the prompt the model actually reads.
        receipt_block = self._receipt_block(_PLANNING_RECEIPT_CHARS)
        if receipt_block:
            context_content = (
                f"{context_content}\n\n{receipt_block}" if context_content else receipt_block
            )

        # Build prompt. The continuity hint is deliberately NOT passed in:
        # it rides the last message of the array instead (see
        # _build_messages), so it is adjacent to the question rather than
        # buried in a prose block that a small context window may cut.
        if self.prompts:
            prompt = self.prompts.build_planning_prompt(
                query=self.ctx.user_query,
                context=context_content,
                plan=[p.to_dict() for p in self.ctx.plan],
                # False once the client fell back to a no-tools retry (spec
                # §7): the preamble then omits the tool instruction. Narrowed
                # to this turn's pinned model where there is one (see
                # ``_tools_supported``).
                tools_supported=self._tools_supported(),
            )
        else:
            prompt = self._build_simple_planning_prompt(context_content)

        # Call LLM
        tool_schemas = self.tools.get_schemas() if self.tools else []

        # ``images`` is threaded here as well as in RESPONDING: without it the
        # two halves of one turn resolve different models, so the planner
        # decides what to do about a picture it cannot see.
        response = await self._model_call(self.llm.chat(
            messages=self._build_messages(prompt, tail=self._continuity_tail()),
            tools=tool_schemas,
            intake_result=self.ctx.intake if self.ctx else None,
            images=self.ctx.images if self.ctx else None,
            model_override=self.ctx.model_override if self.ctx else None,
            tier_override=self.ctx.tier_override if self.ctx else None,
            secure=self.ctx.secure_context if self.ctx else False,
            # What the complexity router scores. The final message is the
            # question with the continuity hint glued to its front (D1), and
            # routing on that picked the specialist for "hi".
            routing_prompt=self.ctx.user_query if self.ctx else "",
        ))

        # Parse plan if present
        if hasattr(response, 'plan') and response.plan:
            self.ctx.plan = [
                PlanStep(step=s.get("step", ""), tool=s.get("tool"))
                for s in response.plan
            ]
            yield StreamEvent.plan(
                self.ctx.session_id,
                [p.to_dict() for p in self.ctx.plan]
            )
        
        # CRAG evaluation if we have retrieved context
        crag_documents = self._retrieval_documents()
        if self.crag and crag_documents:
            # ``crag_documents``, not ``retrieved_context``: thread receipts
            # are continuity, not retrieval, and scoring them switched CRAG
            # on for turns that had retrieved nothing. The overrides ride
            # along so the evaluator uses the same model the turn does.
            crag_result = await self.crag.evaluate(
                self.ctx.user_query,
                crag_documents,
                self.ctx.observations,
                model_override=self.ctx.model_override,
                tier_override=self.ctx.tier_override,
                secure=self.ctx.secure_context,
            )
            self.ctx.confidence = crag_result.confidence
            self.ctx.crag_action = CRAGAction(crag_result.action.value)

            yield StreamEvent.confidence_update(
                self.ctx.session_id,
                crag_result.confidence,
                crag_result.action.value
            )
        
        # Route based on tool calls or CRAG result
        if hasattr(response, 'tool_calls') and response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = tool_call.function.arguments

            if tool_name in THREAD_META_TOOLS:
                # Handled inline (spec §7): mutate the context, emit
                # thread_started / thread_recalled, run PLANNING once more
                # with the new hint. No tool card, no loop increment. The
                # identical call twice in a turn teaches the model nothing,
                # so it reflects instead; MAX_META_TOOL_REENTRIES bounds the
                # re-entries that differing calls would otherwise run up.
                if self._already_called(tool_name, tool_args):
                    logger.info(f"PLANNING: {tool_name} already handled this turn")
                    self.ctx.add_observation(
                        f"{tool_name} was already handled this turn; answer with what you have."
                    )
                    yield await self._transition(AgentState.REFLECTING)
                    return
                # _handle_meta_tool records exactly one tool call when it did
                # something. Count the records rather than reading back the
                # last one's name: a no-op new_thread leaves the *earlier*
                # new_thread record at index -1, so a name check would call
                # the no-op a success and re-plan on nothing.
                recorded_before = len(self.ctx.tool_calls)
                async for event in self._handle_meta_tool(tool_name, tool_args or {}):
                    yield event
                if len(self.ctx.tool_calls) == recorded_before:
                    # Nothing recorded: the call was a no-op (a second
                    # new_thread), so there is nothing new to plan on.
                    yield await self._transition(AgentState.REFLECTING)
                    return
                self.ctx.meta_tool_reentries += 1
                if self.ctx.meta_tool_reentries > self.MAX_META_TOOL_REENTRIES:
                    # Budget spent. The call above still took effect; we just
                    # stop paying for another PLANNING round-trip, so the turn
                    # ends on its own instead of through the oscillation guard.
                    logger.info(
                        "PLANNING: thread meta-tool re-entry budget spent "
                        f"({self.ctx.meta_tool_reentries}), reflecting"
                    )
                    self.ctx.add_observation(
                        "Enough thread bookkeeping for this turn; answer the "
                        "question with what you have."
                    )
                    yield await self._transition(AgentState.REFLECTING)
                    return
                yield await self._transition(AgentState.PLANNING)
                return

            if self._already_called(tool_name, tool_args):
                # Same tool, same arguments, already run this turn. Re-running
                # it cannot teach the model anything new — it just burns a loop
                # (and repeats the side effect, for tools that have one) until
                # max_loops ends the turn. Answer with what we have instead.
                logger.info(f"PLANNING: {tool_name} already ran this turn, not repeating")
                self.ctx.add_observation(
                    f"{tool_name} was already run this turn with the same "
                    "arguments; its result is above."
                )
                yield await self._transition(AgentState.REFLECTING)
                return

            tc = ToolCall(
                id=str(uuid.uuid4())[:8],
                name=tool_name,
                args=tool_args
            )
            self.ctx.add_tool_call(tc)

            # Route based on tool type
            if tool_name in _SEARCH_ROUTED_TOOLS:
                yield await self._transition(AgentState.SEARCHING)
            elif tool_name in ["read_file", "read_config", "cat"]:
                yield await self._transition(AgentState.READING)
            else:
                yield await self._transition(AgentState.EXECUTING)
        
        elif self.ctx.crag_action == CRAGAction.CORRECT:
            yield await self._transition(AgentState.REFLECTING)

        elif self.ctx.loop_count == 0 and self._intake_is_greeting():
            # Greeting turns have nothing to retrieve: searching only pulls in
            # unrelated host hits that leak into the reply. Still reflect so
            # the cognitive tick runs.
            logger.info("PLANNING: greeting intake, skipping SEARCHING")
            yield await self._transition(AgentState.REFLECTING)

        elif self.ctx.loop_count == 0:
            # First iteration, try searching
            yield await self._transition(AgentState.SEARCHING)

        else:
            # Default: reflect (cognitive tick) then respond with what we have
            yield await self._transition(AgentState.REFLECTING)
    
    def _already_called(self, name: str, args: Any) -> bool:
        """Has this exact tool call already finished this turn?

        Only settled calls count: a call still pending (the one being routed)
        must not match itself, and a genuine retry of a *different* invocation
        is unaffected because the arguments differ.
        """
        return any(
            tc.name == name
            and tc.args == args
            and tc.status in ("success", "error")
            for tc in self.ctx.tool_calls
        )

    def _thread_receipts(self) -> List[Dict[str, Any]]:
        """The thread receipts on the retrieved context, oldest first.

        ``source="thread"`` entries are the receipts of *other* subjects
        recall_thread (and A9c's auto-recall) pulled in this turn. They are
        rendered in their own prompt block — see ``_retrieval_documents`` for
        why they are kept out of the retrieval list.
        """
        return [
            c for c in self.ctx.retrieved_context
            if (c or {}).get("source") == "thread"
        ]

    def _retrieval_documents(self) -> List[Dict[str, Any]]:
        """The retrieved context minus the thread receipts: what this turn
        actually retrieved.

        Thread receipts are conversation continuity, not retrieval: what an
        earlier subject was about says nothing about whether the host
        knowledge needed to answer *this* question was found.

        Letting them count as retrieval broke twice over. CRAG scored them,
        which switched CRAG on for turns that had retrieved nothing, and a
        CORRECT verdict then sent PLANNING straight to REFLECTING — the turn
        answered off a thread receipt and never searched at all. And every
        prompt/provenance site slices the first five entries, while recall
        appends up to three receipts during PLANNING, *before* SEARCHING
        appends a single hit — so three of those five slots went to
        continuity and real retrieval was dropped from the answer (review:
        Plan A / A9b). The receipts still reach the prompt, in their own
        block; they just do not vote on retrieval quality or spend the
        retrieval budget.
        """
        return [
            c for c in self.ctx.retrieved_context
            if (c or {}).get("source") != "thread"
        ]

    def _receipt_block(self, max_chars: Optional[int] = None) -> str:
        """The recalled subjects' receipts as a prompt block, "" when none.

        One renderer for every prompt that shows them (RESPONDING's builder
        uses the same function), so the block's header — which recall_thread's
        observation points the model at — cannot drift between prompts.
        """
        receipts = self._thread_receipts()
        if not receipts:
            return ""
        try:
            from ..prompts.agent_prompts import render_recalled_receipts
        except Exception as e:  # pragma: no cover - import cycle guard
            logger.debug(f"receipt block unavailable (non-fatal): {e}")
            return ""
        return render_recalled_receipts(receipts, max_chars=max_chars)

    def _last_turn_id(self, thread_id: Optional[str]) -> Optional[str]:
        """The newest turn_id of ``thread_id``, for thread_recalled (spec §6:
        the chip click scrolls the timeline to it). None without a store,
        without rows, or when the store fails.

        Asks the store for that one id (``last_turn_id``, a tail read off
        ``idx_messages_conv``). Reading it with ``list_messages`` instead
        materialised the whole recalled thread — every row built, its four
        JSON columns decoded, all under the store lock — to look at one
        column of one row: ~30 ms on a 4k-row thread, paid up to three times
        per recall_thread and once per turn under A9c's auto-recall (review:
        Plan A / A9b; ``pending_notes`` records the same measurement for the
        same reason). ``list_messages(limit=N)`` is no help — its LIMIT takes
        the OLDEST N rows — so the scan below stays only as the fallback for
        a store that predates the method.
        """
        store = getattr(self.ctx.thread_manager, "store", None)
        if store is None or not thread_id:
            return None
        indexed = getattr(store, "last_turn_id", None)
        if callable(indexed):
            try:
                found = indexed(thread_id)
            except Exception as e:
                logger.debug(f"last turn lookup for {thread_id} failed (non-fatal): {e}")
                return None
            return str(found) if found else None
        try:
            rows = store.list_messages(thread_id)
        except Exception as e:
            logger.debug(f"last turn lookup for {thread_id} failed (non-fatal): {e}")
            return None
        for row in reversed(list(rows or [])):
            turn_id = row.get("turn_id") if isinstance(row, dict) else None
            if turn_id:
                return str(turn_id)
        return None

    async def _handle_meta_tool(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> AsyncIterator[StreamEvent]:
        """Handle new_thread / recall_thread / resume_thread inline (spec §7).

        Records the call on ``ctx.tool_calls`` (status success, no event) so
        PLANNING's repeat guard can see it. A ``new_thread`` after the turn
        already switched is a no-op and records nothing.
        """
        tm = self.ctx.thread_manager
        sid = self.ctx.session_id
        args = dict(tool_args or {})

        def _record() -> None:
            self.ctx.add_tool_call(ToolCall(
                id=str(uuid.uuid4())[:8], name=tool_name, args=args,
                status="success", result="handled inline",
                started_at=time.time(), completed_at=time.time(),
            ))

        if tool_name == "new_thread":
            if self.ctx.thread_switched:
                self.ctx.add_observation(
                    "new_thread was already handled this turn; continue with the current subject."
                )
                return
            title = " ".join(str(args.get("title") or "").split())[:60]
            if not title:
                title = " ".join(self.ctx.user_query.split())[:60] or "Untitled"
            reason = str(args.get("reason") or "")
            previous = self.ctx.thread_id
            new_id: Optional[str] = None
            if tm is not None:
                try:
                    new_id = tm.new_thread(title, reason, from_thread_id=previous)
                except Exception as e:
                    logger.warning(f"new_thread store failure (non-fatal): {e}")
                    yield StreamEvent.thread_store_error(sid, f"new_thread: {e}")
            if not new_id:
                # No store (or it failed): the turn still switches subject
                # in memory so the model's decision is honoured.
                new_id = str(uuid.uuid4())
            self.ctx.thread_id = new_id
            self.ctx.thread_switched = True
            self.ctx.conversation_history = []
            # …and the receipt of the subject we just left, which _begin_turn
            # fitted into the leading instructions. A new subject has no
            # "Earlier in this subject", and leaving the old one standing
            # would answer the new question out of the old thread's summary.
            self.ctx.thread_receipt_block = ""
            self.ctx.continuity_hint = (
                f'<continuity>\nThread: "{title}" · opened just now.\n</continuity>'
            )
            self.ctx.add_observation(f'Started a new subject: "{title}".')
            _record()
            yield StreamEvent.thread_started(
                sid, new_id, title, reason=reason, previous_thread_id=previous
            )
            return

        if tool_name == "recall_thread":
            query = str(args.get("query") or "").strip() or None
            thread_id = str(args.get("thread_id") or "").strip() or None
            results: List[Dict[str, Any]] = []
            if tm is not None:
                try:
                    # R4: scope as a property of the query — pass the open
                    # thread's domains so same-domain hits rank first.
                    turn_domains = list(getattr(self.ctx.turn_context, "domains", None) or [])
                    results = list(tm.recall(
                        query=query, thread_id=thread_id,
                        exclude_thread_id=self.ctx.thread_id,
                        domains=turn_domains or None,
                    ) or [])
                except Exception as e:
                    logger.warning(f"recall_thread store failure (non-fatal): {e}")
                    yield StreamEvent.thread_store_error(sid, f"recall_thread: {e}")
            _record()
            if not results:
                self.ctx.add_observation("No earlier thread matched.")
                return
            names = []
            for r in results[:3]:
                rid = str(r.get("thread_id", ""))
                rtitle = str(r.get("title", ""))
                rdate = str(r.get("date", ""))
                self.ctx.recalled_threads.append(r)
                self.ctx.add_context(
                    source="thread",
                    content=str(r.get("receipt", "")),
                    metadata={
                        "thread_id": rid, "title": rtitle, "date": rdate,
                        "match_terms": list(r.get("match_terms") or []),
                        "matching_messages": list(r.get("matching_messages") or []),
                    },
                )
                names.append(f'"{rtitle}" ({rdate})')
                yield StreamEvent.thread_recalled(
                    sid, rid, rtitle, rdate, list(r.get("match_terms") or []), mode="tool",
                    last_turn_id=r.get("last_turn_id") or self._last_turn_id(rid),
                    scope_crossed=r.get("scope_crossed"),
                )
            self.ctx.add_observation(
                "Recalled earlier subjects: " + "; ".join(names)
                + f'. Their receipts are in the available context, under '
                  f'"{_recalled_block_name()}".'
            )
            return

        if tool_name == "resume_thread":
            target = str(args.get("thread_id") or "").strip()
            ok = False
            if tm is not None and target:
                try:
                    ok = bool(tm.resume_thread(target, from_thread_id=self.ctx.thread_id))
                except Exception as e:
                    logger.warning(f"resume_thread store failure (non-fatal): {e}")
                    yield StreamEvent.thread_store_error(sid, f"resume_thread: {e}")
            if not ok:
                _record()
                self.ctx.add_observation(
                    f"Could not resume thread {target or '(none)'}; continuing with the current subject."
                )
                return
            previous = self.ctx.thread_id
            title, receipt = "", ""
            try:
                found = list(tm.recall(thread_id=target) or [])
            except Exception as e:
                logger.warning(f"recall after resume failed (non-fatal): {e}")
                found = []
            if found:
                title = str(found[0].get("title", ""))
                receipt = str(found[0].get("receipt", ""))
            self.ctx.thread_id = target
            self.ctx.thread_switched = True
            # The resumed subject's receipt IS the current subject's history,
            # so it goes in the conversation's receipt slot — the one the
            # assembler splits back off and budgets (context/assembler.py
            # `_split_receipt_row`), and the one `_history_section` renders in
            # RESPONDING. It used to be copied onto retrieved_context as well,
            # where it looked like retrieval and got rendered a second time in
            # the answer prompt (review: Plan A / A9b). One place only; a
            # `source="thread"` entry now means "a receipt of ANOTHER subject,
            # recalled this turn".
            # Fenced exactly the way threads.py `_history` fences the row it
            # writes for the same slot: same producer, same reader, so it may
            # not be the one that hands the fold an unfenced receipt. Without
            # this the receipt's own brackets and any `<continuity>` tag in it
            # survive into `messages[0]` (review: merge seam).
            from .threads import RECEIPT_ROW_MAX, RECEIPT_ROW_PREFIX, _fence
            self.ctx.conversation_history = (
                [{
                    "role": "system",
                    "content": (
                        f"{RECEIPT_ROW_PREFIX} "
                        f"{_fence(receipt, RECEIPT_ROW_MAX, keep_lines=True)}]"
                    ),
                }] if receipt else []
            )
            # The block _begin_turn rendered belongs to the subject we just
            # left. This row replaces it: _build_messages folds any non-
            # user/assistant row into the leading instructions, which is the
            # same place the block would have landed.
            self.ctx.thread_receipt_block = ""
            self.ctx.continuity_hint = (
                f'<continuity>\nThread: "{title or target}" · resumed just now.\n</continuity>'
            )
            self.ctx.add_observation(f'Resumed the earlier subject "{title or target}".')
            _record()
            yield StreamEvent.thread_started(
                sid, target, title, reason="resumed", previous_thread_id=previous
            )
            return

    # Word-count ceilings for the retrieval skip (see _intake_is_greeting).
    _GREETING_MAX_WORDS = 5            # "hey halbert, good morning!"
    _GREETING_QUESTION_MAX_WORDS = 6   # "hello, what can you do?"

    _WORD_STRIP_RE = re.compile(r"[^\w\s'-]+")

    def _intake_is_greeting(self) -> bool:
        """True only when the message is a *pure* greeting turn that has
        nothing to retrieve.

        intake/signals.py's greeting regex is a prefix match ("hi ...",
        "halbert, ..."), so is_greeting/intent=="greeting" is also true for
        "Halbert, what does PermitRootLogin accept in sshd_config?". Skipping
        retrieval on that flag alone would starve real questions. Rule:

        * the intake flagged the message as a greeting, AND
        * no troubleshooting / error signals (is_troubleshooting,
          has_error_indicators) and no detected host domains, AND
        * short: <= 5 words after stripping punctuation (computed from
          ctx.user_query), or, when the intake also flags it as a question,
          <= 6 words -- a capabilities question with no host context
          ("hello, what can you do?") is fine to answer without retrieval.

        Anything longer, or carrying host/troubleshooting context, still
        goes through SEARCHING.
        """
        intake = self.ctx.intake
        if intake is None:
            return False
        flagged = (
            getattr(intake, "is_greeting", False) is True
            or getattr(intake, "intent", None) == "greeting"
        )
        if not flagged:
            return False
        if getattr(intake, "is_troubleshooting", False) is True:
            return False
        if getattr(intake, "has_error_indicators", False) is True:
            return False
        domains = getattr(intake, "detected_domains", None)
        if isinstance(domains, (list, tuple, set)) and domains:
            return False

        words = self._WORD_STRIP_RE.sub(" ", self.ctx.user_query or "").split()
        limit = (
            self._GREETING_QUESTION_MAX_WORDS
            if getattr(intake, "is_question", False) is True
            else self._GREETING_MAX_WORDS
        )
        return len(words) <= limit
    
    async def _handle_searching(self) -> AsyncIterator[StreamEvent]:
        """
        SEARCHING state: Execute RAG and memory searches.
        """
        self.ctx.loop_count += 1
        logger.info(f"SEARCHING: loop={self.ctx.loop_count}")
        
        # Get pending tool call or use query
        tool_call = self.ctx.tool_calls[-1] if self.ctx.tool_calls else None

        # Whatever the model asked to search for, if it said. This used to be
        # read only for "search"/"web_search", so a recall_memory(query=...)
        # silently searched the user's raw question instead of the term the
        # model had picked out.
        search_query = self.ctx.user_query
        if tool_call:
            asked = tool_call.args.get("query") if tool_call.args else None
            if asked:
                search_query = asked
        
        # Narrow the search the same way PLANNING's context assembly does.
        # Routing sends every non-greeting first loop with no tool call
        # through SEARCHING, so an unscoped call here was the whole retrieval
        # for turns that had explicitly asked for a scope — the "Analyze"
        # button's retrieval_scope, or an active skill's role/scope — and it
        # searched everything instead (R06-F3).
        from ..context.assembler import resolve_retrieval_scope, scope_kwargs_for
        from ..context.assembler import ContextAssembler as _CA

        composed = _CA._composed_skills(None, self.ctx.intake)
        scope, role = resolve_retrieval_scope(composed, self.ctx.retrieval_scope)

        # Execute searches in parallel
        tasks = []

        if self.rag:
            kwargs = scope_kwargs_for(self.rag.search, scope, role)
            tasks.append(("rag", self.rag.search(search_query, limit=5, **kwargs)))

        if self.memory:
            tasks.append(("memory", self.memory.recall(search_query, limit=3)))
        
        # Execute all search tasks
        for source, task in tasks:
            try:
                results = await task
                for result in results:
                    metadata = dict(result.get("metadata") or {})
                    # Keep the retriever's similarity score: CRAG uses it as
                    # the relevance signal when no embedding service is wired.
                    if "score" not in metadata and result.get("score") is not None:
                        metadata["score"] = result.get("score")
                    self.ctx.add_context(
                        source=source,
                        content=result.get("content", str(result)),
                        metadata=metadata
                    )
                
                yield StreamEvent.context_loaded(
                    self.ctx.session_id,
                    source,
                    len(results),
                    0  # TODO: token count
                )
            except Exception as e:
                logger.error(f"Search error ({source}): {e}")
                self.ctx.add_observation(f"Search error ({source}): {e}")
        
        # Update tool call status
        if tool_call:
            tool_call.status = "success"
            tool_call.result = {"count": len(self.ctx.retrieved_context)}

        count = len(self.ctx.retrieved_context)
        if tool_call and tool_call.name in _SUBSTITUTED_BY_SEARCH:
            # Say so. A model told that search_discoveries succeeded and
            # returned nothing concludes that nothing was discovered, and
            # tells the user so — which is a claim this turn has no basis
            # for. Naming the substitution lets it answer from what the
            # search did find, and say plainly that it could not check
            # (R06-O2). ``recall_memory`` is no longer in this set: it is a
            # real tool over the change ledger and abstains in its own words.
            self.ctx.add_observation(
                f"{tool_call.name} is not implemented; a general search was "
                f"run in its place and returned {count} context items. "
                f"Do not report this as the result of {tool_call.name}."
            )
        else:
            self.ctx.add_observation(f"Retrieved {count} context items")
        
        yield await self._transition(AgentState.OBSERVING)
    
    async def _handle_reading(self) -> AsyncIterator[StreamEvent]:
        """
        READING state: Read specific files or resources.
        """
        self.ctx.loop_count += 1
        logger.info(f"READING: loop={self.ctx.loop_count}")
        
        tool_call = self.ctx.tool_calls[-1] if self.ctx.tool_calls else None
        
        if not tool_call:
            self.ctx.add_observation("No file specified to read")
            yield await self._transition(AgentState.OBSERVING)
            return
        
        file_path = tool_call.args.get("path") or tool_call.args.get("file")
        
        exec_id = tool_call.id
        yield StreamEvent.tool_start(
            self.ctx.session_id,
            "read_file",
            {"path": file_path},
            exec_id
        )
        # C4: the tool-call marker, reduced — the name, never the args
        # (args carry paths and material the tee's consumers do not
        # need).
        self._tee_publish(
            "tool_start", self.ctx.session_id,
            tool="read_file", execution_id=exec_id,
        )
        
        if self.tools:
            result = await self.tools.execute("read_file", {"path": file_path})
            
            yield StreamEvent.tool_complete(
                self.ctx.session_id,
                exec_id,
                result.success,
                result.result[:500] if result.result else None,
                result.error
            )
            # C4: the completion marker — success only, never the result.
            self._tee_publish(
                "tool_complete", self.ctx.session_id,
                execution_id=exec_id, success=result.success,
            )
            
            if result.success:
                tool_call.status = "success"
                tool_call.result = result.result
                self.ctx.add_observation(f"Read {file_path}: {len(result.result)} chars")
                self.ctx.add_context(
                    source="file",
                    content=result.result,
                    metadata={"path": file_path}
                )
            else:
                tool_call.status = "error"
                tool_call.error = result.error
                self.ctx.add_observation(f"Failed to read {file_path}: {result.error}")
        else:
            self.ctx.add_observation("Tool executor not available")
        
        yield await self._transition(AgentState.OBSERVING)
    
    # -------------------------------------------------------------------------
    # Terminal streaming bridge (E1f)
    # -------------------------------------------------------------------------

    @staticmethod
    def _terminal_event(
        session_id: str,
        payload: Dict[str, Any],
        execution_id: Optional[str] = None,
    ) -> Optional[StreamEvent]:
        """Convert a terminal-bridge payload into its SSE event.

        ``execution_id`` is the tool call the payload was drained under. Only
        block events carry it: it is what lets the conversation's tool card
        find its terminal tile without matching on a command string.
        """
        kind = payload.get("kind")
        terminal_id = str(payload.get("terminal_session_id", ""))
        if kind == "spawn":
            return StreamEvent.terminal_spawn(
                session_id,
                terminal_id,
                command=str(payload.get("command", "")),
                pid=int(payload.get("pid") or 0),
                sandboxed=bool(payload.get("sandboxed")),
                cwd=payload.get("cwd"),
                attach=str(payload.get("attach", "sse")),
                block_id=payload.get("block_id"),
                owner=str(payload.get("owner", "agent")),
            )
        if kind == "output":
            return StreamEvent.terminal_output(
                session_id, terminal_id, str(payload.get("data", ""))
            )
        if kind == "complete":
            exit_code = payload.get("exit_code")
            duration = payload.get("duration")
            return StreamEvent.terminal_complete(
                session_id,
                terminal_id,
                int(exit_code) if exit_code is not None else -1,
                block_id=payload.get("block_id"),
                duration=float(duration) if duration is not None else None,
                output_head=payload.get("output_head"),
                output_tail=payload.get("output_tail"),
                output_elided_lines=payload.get("output_elided_lines"),
                output_total_lines=payload.get("output_total_lines"),
            )
        if kind in ("block", "block_promote"):
            block_id = str(payload.get("block_id", ""))
            if not block_id:
                # A block record with no id is unaddressable: nothing could
                # promote it, complete it, or jump to the turn that ran it.
                # Dropping it beats putting a ghost in the store.
                return None
            return StreamEvent.terminal_block(
                session_id,
                block_id=block_id,
                terminal_session_id=terminal_id,
                command=str(payload.get("command", "")),
                owner=str(payload.get("owner", "agent")),
                interactive=bool(payload.get("interactive")),
                promote=(kind == "block_promote"),
                execution_id=execution_id,
            )
        return None

    def _note_terminal_payload(
        self, payload: Dict[str, Any], execution_id: Optional[str] = None
    ) -> None:
        """Remember every terminal this turn spawned (persisted at end_turn).

        Also remembers which tool call ran which block. That pairing exists
        only here -- the drain runs under one tool call and sees that call's
        payloads -- and ``end_turn`` needs it to stamp ``execution_id`` on the
        stored row, which is what lets the timeline render a stored command
        the same way the live stream did.
        """
        if payload.get("kind") != "spawn":
            return
        terminal_id = str(payload.get("terminal_session_id", ""))
        block_id = str(payload.get("block_id", ""))
        # Plan B: track block_id when present, fall back to session_id
        track_id = block_id or terminal_id
        if track_id and track_id not in self.ctx.terminal_block_ids:
            self.ctx.terminal_block_ids.append(track_id)
        # Only a real block id is paired. The session-id fallback names no
        # row, so stamping a tool call onto it would point the timeline at
        # something that can never be hydrated.
        if block_id and execution_id:
            self.ctx.block_executions[block_id] = execution_id

    async def _run_tool_streaming(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmed: bool,
        sink: List[Any],
        execution_id: Optional[str] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute a tool, yielding terminal events while it runs.

        The tool executor publishes terminal lifecycle payloads onto the
        terminal bridge (streaming/terminal_bridge) for the current agent
        session. Draining that bus concurrently with the tool task is what
        makes a running command visible in the conversation *as it runs*;
        awaiting the tool first would only ever produce a finished transcript.

        Every payload drained here belongs to *this* tool call — the bus is
        subscribed for its duration and nothing else is running under it — so
        ``execution_id`` can be stamped onto the block events on the way out.
        That is the join the frontend needs, and the reason it never has to
        match a result back to a card by tool name.

        The ExecutionResult is appended to ``sink`` — an async generator
        cannot return a value.
        """
        bus = get_terminal_event_bus()
        queue = bus.subscribe(self.ctx.session_id)
        self._touch_activity(f"tool started: {tool_name}")
        task = asyncio.ensure_future(self.tools.execute(
            tool_name,
            tool_args,
            session_id=self.ctx.session_id,
            confirmed=confirmed,
            speaker_role=self.ctx.speaker_role,
        ))
        try:
            while True:
                getter = asyncio.ensure_future(queue.get())
                done, _pending = await asyncio.wait(
                    {task, getter},
                    return_when=asyncio.FIRST_COMPLETED,
                    # A07-G2: bounded, so the loop is a place a stop can
                    # be *observed*. Without it the wait blocked until the
                    # tool finished -- so a stop raised the flag and then
                    # waited for the very command it was meant to stop,
                    # and _drive's between-steps poll only saw it after
                    # the tool had run to completion.
                    timeout=self.STOP_POLL_SECONDS,
                )
                if self.cancelled.get(self.ctx.session_id):
                    getter.cancel()
                    logger.info(
                        "tool cancelled by stop: session=%s tool=%s",
                        self.ctx.session_id, tool_name,
                    )
                    # task.cancel() raises CancelledError inside
                    # ToolExecutor.execute; run_command's own
                    # `except BaseException` kills the child and reaps it
                    # (executor.py's subprocess path), so the stop
                    # reaches the process, not just the coroutine.
                    task.cancel()
                    raise asyncio.CancelledError(
                        f"tool {tool_name} stopped by the user"
                    )
                if not done:
                    # Neither settled inside the poll window: keep waiting.
                    getter.cancel()
                    continue
                if getter in done:
                    payload = getter.result()
                    # Output from a running command is progress: a long
                    # build is not a wedged turn.
                    self._touch_activity(f"tool output: {tool_name}")
                    self._note_terminal_payload(payload, execution_id)
                    event = self._terminal_event(
                        self.ctx.session_id, payload, execution_id
                    )
                    if event is not None:
                        yield event
                    continue
                # Tool finished with nothing queued: stop waiting on the queue.
                getter.cancel()
                break

            # Flush whatever the tool published on its way out.
            while not queue.empty():
                payload = queue.get_nowait()
                self._note_terminal_payload(payload, execution_id)
                event = self._terminal_event(
                    self.ctx.session_id, payload, execution_id
                )
                if event is not None:
                    yield event

            sink.append(await task)
            self._touch_activity(f"tool completed: {tool_name}")
        finally:
            bus.unsubscribe(self.ctx.session_id, queue)
            if not task.done():
                task.cancel()

    async def _handle_executing(self) -> AsyncIterator[StreamEvent]:
        """
        EXECUTING state: Execute tool calls with safety checks.
        """
        self.ctx.loop_count += 1
        logger.info(f"EXECUTING: loop={self.ctx.loop_count}")
        
        tool_call = self.ctx.tool_calls[-1] if self.ctx.tool_calls else None
        
        if not tool_call:
            self.ctx.add_observation("No tool call to execute")
            yield await self._transition(AgentState.OBSERVING)
            return
        
        tool_name = tool_call.name
        tool_args = tool_call.args
        exec_id = tool_call.id
        
        yield StreamEvent.tool_start(
            self.ctx.session_id,
            tool_name,
            tool_args,
            exec_id
        )
        # C4: the tool-call marker, reduced — the name, never the args.
        self._tee_publish(
            "tool_start", self.ctx.session_id,
            tool=tool_name, execution_id=exec_id,
        )
        
        tool_call.started_at = __import__('time').time()
        
        if self.tools:
            # Check if already confirmed
            confirmed = (
                self.ctx.pending_confirmation and 
                self.ctx.pending_confirmation.get("confirmed", False)
            )
            
            # Run the tool while relaying anything it prints to a terminal
            # (E1f). _run_tool_streaming yields terminal_* SSE events as the
            # command produces output and leaves the ExecutionResult in `sink`,
            # so the conversation shows a live tile instead of a wall of text
            # once the command has already finished.
            sink: List[Any] = []
            async for terminal_event in self._run_tool_streaming(
                tool_name, tool_args, confirmed, sink, execution_id=exec_id
            ):
                yield terminal_event
            result = sink[0]

            tool_call.completed_at = __import__('time').time()
            
            if result.requires_confirmation:
                # Need user confirmation
                self.ctx.pending_confirmation = {
                    "action_id": exec_id,
                    "tool": tool_name,
                    "description": result.confirmation_message,
                    "risk_level": result.risk_level.value
                }
                
                yield StreamEvent.tool_confirmation_required(
                    self.ctx.session_id,
                    exec_id,
                    tool_name,
                    result.confirmation_message,
                    result.risk_level.value
                )
                
                # User-facing status: blocked on approval (A2c)
                yield self._set_conversation_status(
                    ConversationStatus.BLOCKED,
                    blocked_action=self.ctx.pending_confirmation,
                )

                yield await self._transition(AgentState.AWAITING_CONFIRMATION)
                return
            
            yield StreamEvent.tool_complete(
                self.ctx.session_id,
                exec_id,
                result.success,
                result.result,
                result.error
            )
            # C4: the completion marker — success only, never the result.
            self._tee_publish(
                "tool_complete", self.ctx.session_id,
                execution_id=exec_id, success=result.success,
            )
            
            if result.success:
                tool_call.status = "success"
                tool_call.result = result.result
                # Vision tools return a dict with an "image" key (base64
                # JPEG). Detect it and append to ctx.images so the next
                # LLM call routes through the vision model. The text
                # observation uses the "description" field, not the base64.
                #
                # capture_and_ocr returns "ocr_text" (text observation,
                # no image routing) and optionally "image" (when
                # include_image=True). The OCR text goes into the
                # observation directly — the LLM reads it as text, not
                # through the vision model, saving 5-15x tokens.
                if isinstance(result.result, dict) and "image" in result.result:
                    img_data = result.result["image"]
                    if img_data and isinstance(img_data, str):
                        if self.ctx.images is None:
                            self.ctx.images = []
                        self.ctx.images.append(img_data)
                    desc = result.result.get("description", "Image captured")
                    # If OCR text is also present, include it in the
                    # observation so the LLM gets both the text and the
                    # image routing.
                    ocr_text = result.result.get("ocr_text")
                    if ocr_text and isinstance(ocr_text, str):
                        self.ctx.add_observation(
                            f"Executed {tool_name}: {desc}\nOCR text:\n{ocr_text}"
                        )
                    else:
                        self.ctx.add_observation(
                            f"Executed {tool_name}: {desc}"
                        )
                elif isinstance(result.result, dict) and "ocr_text" in result.result:
                    # OCR-only result: text observation, no image routing.
                    # This is the 5-15x token savings path — the LLM
                    # reads the extracted text without needing the
                    # vision model at all.
                    ocr_text = result.result["ocr_text"]
                    desc = result.result.get("description", "OCR text extracted")
                    self.ctx.add_observation(
                        f"Executed {tool_name}: {desc}\n{ocr_text}"
                    )
                else:
                    # The observation has to carry the *output*, not just
                    # "success". Observations are the only channel by which
                    # a tool result reaches the next PLANNING pass; recording
                    # bare success left the model blind to what it had just
                    # learnt, so it re-issued the same call until max_loops
                    # cut the turn off.
                    self.ctx.add_observation(
                        _format_tool_observation(tool_name, tool_args, result.result)
                    )
            else:
                tool_call.status = "error"
                tool_call.error = result.error
                self.ctx.add_observation(f"Executed {tool_name}: {result.error}")

                # Opt-in diagnostic capture: OCR the screen on command
                # execution failures for diagnostic context. Gated by
                # being.yml senses.vision.capture_on_error (default False).
                # Only fires for command-execution tools, not search/read.
                # OCR text only (no image) to avoid routing the turn
                # through the more expensive vision model.
                if self._should_diagnostic_capture(tool_name) and not self._screen_is_the_machines_own():
                    try:
                        from ..tools.vision_tools import capture_and_ocr
                        screen = await capture_and_ocr({"include_image": False})
                        if isinstance(screen, dict) and "ocr_text" in screen:
                            ocr_excerpt = screen["ocr_text"][:500]
                            self.ctx.add_observation(
                                f"[Diagnostic] Screen OCR at failure:\n{ocr_excerpt}"
                            )
                    except Exception as e:
                        logger.debug(f"Diagnostic capture failed: {e}")

            # Clear pending confirmation
            self.ctx.pending_confirmation = None
        else:
            self.ctx.add_observation("Tool executor not available")
        
        yield await self._transition(AgentState.OBSERVING)
    
    async def _handle_observing(self) -> AsyncIterator[StreamEvent]:
        """
        OBSERVING state: Evaluate results, decide next action.
        """
        logger.info(f"OBSERVING: {len(self.ctx.observations)} observations")
        
        # CRAG evaluation
        crag_documents = self._retrieval_documents()
        if self.crag and crag_documents:
            # Receipts are dropped here too — see the note at PLANNING's
            # evaluation site.
            crag_result = await self.crag.evaluate(
                self.ctx.user_query,
                crag_documents,
                self.ctx.observations,
                model_override=self.ctx.model_override,
                tier_override=self.ctx.tier_override,
                secure=self.ctx.secure_context,
            )

            self.ctx.confidence = crag_result.confidence
            self.ctx.crag_action = CRAGAction(crag_result.action.value)
            
            yield StreamEvent.confidence_update(
                self.ctx.session_id,
                crag_result.confidence,
                crag_result.action.value
            )
        else:
            # No CRAG, estimate based on context
            if crag_documents:
                self.ctx.confidence = 0.6
                self.ctx.crag_action = CRAGAction.AMBIGUOUS
            else:
                self.ctx.confidence = 0.3
                self.ctx.crag_action = CRAGAction.INCORRECT
        
        # Decide next state
        if self.ctx.crag_action == CRAGAction.CORRECT:
            yield await self._transition(AgentState.REFLECTING)
        elif self.ctx.loop_count >= self.ctx.max_loops - 1:
            # Almost at limit, respond with what we have
            yield await self._transition(AgentState.REFLECTING)
        else:
            # Need more info, go back to planning
            yield await self._transition(AgentState.PLANNING)
    
    async def _forward_guest_turn(self, reply: str) -> AsyncIterator[StreamEvent]:
        """While a guest fronts, the turn goes to the guest's home; when it
        cannot, the user is told the guest will not remember it. The round
        trip runs in a worker thread and is bounded by the sibling client's
        timeout. Non-fatal on error."""
        try:
            from ..persona import sibling
            from ..persona.guest import current_guest
            session = current_guest()
        except Exception:
            return
        if session is None:
            return
        # Once per turn, like the tick: a turn that re-enters RESPONDING must
        # not become two memories at the home.
        if getattr(self.ctx, "guest_turn_forwarded", False):
            return
        self.ctx.guest_turn_forwarded = True
        ok = False
        try:
            ok = await asyncio.to_thread(sibling.forward_turn, session, self.ctx.user_query, reply)
        except Exception as e:
            logger.warning(f"Guest turn not forwarded: {e}")
        if not ok:
            why = "no memory home in this session" if session.home is None else "their home did not answer"
            yield StreamEvent.thinking(
                self.ctx.session_id,
                f"{session.persona.name} will not remember this turn: {why}.",
            )

    async def _run_cognition_tick(self, assistant_response: str) -> AsyncIterator[StreamEvent]:
        """Run the Haloysius cognitive tick at most once per turn (B1).

        Called from REFLECTING (pre-response, with observations as the
        stand-in reply) and again from RESPONDING (post-response, with the
        real reply). ``ctx.cognition_ticked`` guarantees exactly one tick per
        turn regardless of which states the loop visited. Non-fatal on error.

        The tick (``advance_turn``) is synchronous and may do file/memory
        work, so it runs in a worker thread to keep the event loop free.
        """
        if self.ctx.cognition_ticked:
            return
        # Ownership (design §4.2, R2): while a guest persona fronts, the tick
        # is the guest's. Halbert's own cognition and semantic memory must not
        # learn a guest's evenings; the turn goes to the guest's home instead
        # (``_forward_guest_turn``, from RESPONDING with the real reply).
        try:
            from ..continuity.ownership import Owner, route_write
            if route_write("cognition.tick") is not Owner.HALBERT:
                self.ctx.cognition_ticked = True
                logger.debug("Cognition tick skipped: a guest persona fronts")
                return
        except Exception as e:
            logger.debug(f"Ownership check unavailable, ticking as before: {e}")
        if self.cognition_tick is None or self.ctx.persona_cognition is None:
            logger.debug("No cognition_tick wired, skipping")
            return
        self.ctx.cognition_ticked = True
        try:
            # Populate cognition with system events before the tick
            if self.event_mapper is not None:
                self.event_mapper.populate_cognition(self.ctx.persona_cognition)

            tick_result = await asyncio.to_thread(
                self.cognition_tick,
                cognition=self.ctx.persona_cognition,
                user_message=self.ctx.user_query,
                assistant_response=assistant_response,
            )

            # Emit thought event if a thought was generated
            if tick_result and hasattr(tick_result, 'thought') and tick_result.thought:
                thought_text = tick_result.thought.content if hasattr(tick_result.thought, 'content') else str(tick_result.thought)
                logger.info(f"Cognitive tick generated thought: {thought_text[:80]}")
                yield StreamEvent.thinking(self.ctx.session_id, thought_text)

            # Check for worry intrusions that should color the response
            if hasattr(self.ctx.persona_cognition, 'worries'):
                intrusions = self.ctx.persona_cognition.worries.check_intrusions(
                    self.ctx.user_query
                )
                for intrusion in intrusions:
                    logger.info(f"Worry intrusion: {intrusion[:80]}")
                    self.ctx.add_observation(f"[worry] {intrusion}")

            logger.info("Cognitive tick complete")
        except Exception as e:
            logger.error(f"Cognitive tick error: {e}")
            # Non-fatal: the turn continues

    async def _handle_reflecting(self) -> AsyncIterator[StreamEvent]:
        """
        REFLECTING state: Run the cognitive tick (Haloysius advance_turn).

        This is the composed-loop seam where the cognitive core processes
        the turn: decay, trigger detection, thought generation, worry
        intrusion, cross-layer conflict detection. The result may inject
        a thought or worry that colors the response.

        If no cognition_tick is wired, this is a pass-through to RESPONDING.
        """
        logger.info(f"REFLECTING: cognitive tick for session {self.ctx.session_id}")

        # Build the assistant response from observations + context
        assistant_response = "\n".join(self.ctx.observations[-3:])
        if not assistant_response:
            assistant_response = "\n".join(self.ctx.response_chunks[-3:])
        async for event in self._run_cognition_tick(assistant_response):
            yield event

        # C1d: if a somatic block is active for this turn, advance it to
        # reflection and emit the block event (SSE + ProactiveEventBus).
        if (self.somatic_lifecycle is not None and self.somatic_store is not None
                and self.ctx.current_somatic_block_id):
            block = self.somatic_store.get(self.ctx.current_somatic_block_id)
            if block is not None:
                try:
                    await self.somatic_lifecycle.advance_to_reflection(block)
                    self.somatic_store.save(block)
                    yield await self._emit_somatic_block(block)
                except Exception as e:
                    logger.warning(f"Somatic reflection failed (non-fatal): {e}")

        # Always proceed to responding after reflection
        yield await self._transition(AgentState.RESPONDING)

    @staticmethod
    def _echo_guard_egress(
        text: str, *, session_id: str, request_id: Optional[str] = None
    ) -> str:
        """Echo guard at the outbound reply seam (A05-G4, R-05 Phase E).

        The body of this moved to ``security/scrub.py``: it existed twice
        -- here and in ``turn_event_tee`` -- and two copies of a security
        seam drift. Two things changed with the move, both of them the
        point of the change:

        * a PARTIAL echo is now actually redacted. This matched on a
          normalised window and then called ``registry.redact_text``,
          which replaces whole registered forms, so a reply carrying the
          first 85 characters of a 98-character acked value matched,
          changed nothing, and was delivered -- while the warning said
          ``redacted: true`` (A05-G1 + bug 1);
        * the seam fails CLOSED. It was "non-fatal by construction": any
          failure returned the text raw, on the reasoning that a guard
          failure must not cost the user their answer. A scrub that
          cannot run is not evidence that there was nothing to scrub.
        """
        from ..security.scrub import scrub_for_egress
        return scrub_for_egress(
            text, surface="reply",
            session_id=session_id, request_id=request_id or "",
        )

    def _tee_publish(self, event: str, session_id: str, **fields: Any) -> None:
        """Publish one reduced event to the turn-event tee (C4).

        The tee is observe-only fan-out: a subscriber in the room sees
        what the answer stream was cleared to show (the hub scrubs
        payload strings through the echo-guard seam itself), and a
        failing subscriber never costs the turn. Non-fatal end to end —
        the tee is an observation of this turn, never a step in it, so
        any failure here is logged at debug and forgotten. The channel
        rides from the turn's bound ``current_turn_channel`` so a second
        screen can tell whose turn it is watching (the voice HUD's
        "mine or the dashboard's" question).
        """
        try:
            from .channels import current_turn_channel
            from .turn_event_tee import get_turn_event_tee

            channel = current_turn_channel.get()
            get_turn_event_tee().publish({
                "event": event,
                "session_id": session_id,
                "channel": channel.id if channel is not None else None,
                **fields,
            })
        except Exception as e:
            logger.debug(f"tee publish skipped (non-fatal): {e}")

    async def _handle_responding(self) -> AsyncIterator[StreamEvent]:
        """
        RESPONDING state: Generate final response.
        """
        logger.info(f"RESPONDING: confidence={self.ctx.confidence:.2f}")

        # Clear any value a re-entry into RESPONDING left behind (a resumed
        # turn runs this handler again on the same context). Cross-turn
        # leakage is already impossible: the field lives on the per-turn
        # StateContext, which is rebuilt by process().
        self.ctx.defanged_query = None

        # Phase 2 modality wiring: resolve the turn's delivery modality
        # (TEXT/VOICE) from the channel capability + cognitive state, and
        # defang modality control tags from the user input (spec 5.11).
        # When the engine is not installed, this is a no-op (text-only).
        modality_ctx = None
        try:
            from ..integrations.modality_wiring import (
                build_modality_context,
                defang_user_input,
                resolve_turn_modality,
                should_speak,
            )
            modality_ctx = build_modality_context(
                user_query=self.ctx.user_query,
                speaker_role=self.ctx.speaker_role,
                ingress_modality=getattr(self.ctx, "modality", "text"),
                speaker_name=getattr(self.ctx, "speaker_name", None),
            )
            if modality_ctx is not None:
                modality_ctx = resolve_turn_modality(modality_ctx)
                # Defang the user query in conversation history (spec 5.11).
                # The original query is preserved in ctx.user_query; the
                # defanged version is applied to the messages array below.
                self.ctx.defanged_query = defang_user_input(self.ctx.user_query)
        except Exception as e:
            logger.debug(f"Modality wiring skipped (non-fatal): {e}")

        # Phase 2.5: resolve the delivery modality for the response prompt.
        # Both arms below consume it — the builder arm passes it to
        # build_response_prompt, the no-builder arm to
        # _build_simple_response_prompt — so it is resolved before the branch.
        # It used to live inside the ``if self.prompts:`` arm, which left the
        # name unbound on every turn taken by a state machine constructed
        # without a prompt builder (Wyoming voice turns, and any embedder that
        # is not the dashboard's get_agent()).
        response_modality = "text"
        if modality_ctx is not None:
            try:
                resolved_mod = getattr(modality_ctx, "recommended_modality", None)
                if resolved_mod is not None:
                    response_modality = resolved_mod.value.lower()
            except Exception:
                pass

        # Build response prompt. Neither ``history`` nor ``continuity`` is
        # passed any more:
        #   * the prior turns are the messages array (_build_messages), and
        #     rendering them into the prose as well sent every earlier turn
        #     twice — once as "## Earlier in this conversation", once as real
        #     messages — for one budget's worth of meaning;
        #   * the continuity hint rides the last user message, next to the
        #     question it qualifies.
        # The receipts of subjects recalled *this* turn are a different
        # mechanism and are untouched: build_response_prompt still renders
        # them from ``context``, and _receipt_block still feeds the
        # no-builder path below.
        if self.prompts:
            # A10-G7 + A10-G6: the model is told the spoken budget it is
            # actually working to, and whether the listener cut off the
            # last reply. Both were computed by nothing: the engine's
            # budget block was unreachable, and a barge-in stopped the
            # audio and told the model nothing at all.
            spoken_cap = None
            barge_note = ""
            try:
                from ..integrations.modality_wiring import (
                    spoken_max_words, take_barge_in_note,
                )
                if response_modality == "voice":
                    spoken_cap = spoken_max_words(modality_ctx)
                    barge_note = take_barge_in_note(self.ctx.session_id) or ""
            except Exception as e:
                logger.debug(f"spoken budget/barge-in hint skipped: {e}")
            prompt = self.prompts.build_response_prompt(
                query=self.ctx.user_query,
                context=self.ctx.retrieved_context,
                observations=self.ctx.observations,
                world_observations=self._world_observations(),
                tools_supported=getattr(self.llm, "tools_supported", None),
                response_modality=response_modality,
                spoken_max_words=spoken_cap,
                barge_in_note=barge_note,
            )
            logger.info("Using AgentPromptBuilder for response prompt")
        else:
            prompt = self._build_simple_response_prompt(
                response_modality=response_modality,
            )
            logger.info("Using simple response prompt (no prompt builder)")

        # DEBUG: Log the prompt to verify markdown instructions are included
        logger.debug(f"Response prompt (first 500 chars): {prompt[:500]}")

        tail = self._continuity_tail()

        # The turn's model is announced from here and nowhere else. PLANNING
        # resolves separately and can land on a different tier — it scores a
        # different prompt — so naming its choice would credit the answer to a
        # model that never saw the question.
        selected: List[Dict[str, Any]] = []
        announced = False

        # Stream response
        if hasattr(self.llm, 'stream'):
            logger.info(f"Starting LLM stream for session {self.ctx.session_id}")
            chunk_count = 0
            async for chunk in self._model_stream(self.llm.stream(
                messages=self._build_messages(
                    prompt, tail=tail, response_modality=response_modality,
                ),
                intake_result=self.ctx.intake if self.ctx else None,
                images=self.ctx.images if self.ctx else None,
                model_override=self.ctx.model_override if self.ctx else None,
                tier_override=self.ctx.tier_override if self.ctx else None,
                secure=self.ctx.secure_context if self.ctx else False,
                on_model_selected=selected.append,
                # The question, not the hint that rides in front of it (D1).
                routing_prompt=self.ctx.user_query if self.ctx else "",
            )):
                if selected and not announced:
                    announced = True
                    yield StreamEvent.model_selected(
                        self.ctx.session_id, **selected[-1]
                    )
                chunk_count += 1
                self._touch_activity("responding: stream chunk")
                logger.debug(f"Chunk {chunk_count}: {repr(chunk[:50])}...")
                self.ctx.response_chunks.append(chunk)
                yield StreamEvent.response_chunk(self.ctx.session_id, chunk)
            logger.info(f"LLM stream complete: {chunk_count} chunks")
        else:
            # Non-streaming fallback
            response = await self._model_call(self.llm.chat(
                messages=self._build_messages(
                    prompt, tail=tail, response_modality=response_modality,
                ),
                intake_result=self.ctx.intake if self.ctx else None,
                images=self.ctx.images if self.ctx else None,
                model_override=self.ctx.model_override if self.ctx else None,
                tier_override=self.ctx.tier_override if self.ctx else None,
                secure=self.ctx.secure_context if self.ctx else False,
                on_model_selected=selected.append,
                # The question, not the hint that rides in front of it (D1).
                routing_prompt=self.ctx.user_query if self.ctx else "",
            ))
            if selected:
                announced = True
                yield StreamEvent.model_selected(
                    self.ctx.session_id, **selected[-1]
                )
            content = response.content if hasattr(response, 'content') else str(response)
            self.ctx.response_chunks.append(content)
            yield StreamEvent.response_chunk(self.ctx.session_id, content)

        # A stream that resolved a model and then produced nothing still owes
        # the user the reason its answer is empty.
        if selected and not announced:
            yield StreamEvent.model_selected(self.ctx.session_id, **selected[-1])

        # Full (raw) streamed response text
        full_response = "".join(self.ctx.response_chunks)

        # Phase 8: Parse module invocation requests from the raw response and
        # strip them. The LLM-emitted {"action": "invoke_module", ...} JSON
        # blocks must never stay visible in the chat bubble: streaming already
        # sent them as raw chunks, so the FINAL committed state — memory store
        # and the `content` field on response_complete below — carries the
        # stripped text. module_invoke SSE events are still emitted so the
        # frontend can render the modules alongside the clean message.
        try:
            module_invocations, clean_response = self._parse_module_invocations(full_response)
        except Exception as e:
            logger.debug(f"Module invocation parsing skipped: {e}")
            module_invocations, clean_response = [], full_response

        # Not stored in memory here any more (spec §7): thread receipts, and
        # the Haloysius line written when a thread closes, replace
        # memory.store_interaction. Storing every Q/A made each turn a global
        # memory that leaked into unrelated threads.

        # Echo guard at the outbound seam (Packet 05 B2). This commit is
        # the single point the turn's final text passes on its way to every
        # user-visible surface: response_complete (the frontend adopts
        # this content as the rendered bubble), _end_turn's persisted
        # assistant row (it joins ctx.response_chunks, which from here on
        # is exactly this text), and the modality demux below (display,
        # speech, TTS egress). Redacting here covers all of them at once.
        # The live response_chunk stream above is a transient draft the
        # frontend replaces with the committed text — the guard
        # deliberately operates on the committed state, not the drafts.
        clean_response = self._echo_guard_egress(
            clean_response,
            session_id=self.ctx.session_id,
            request_id=getattr(self.ctx, "request_id", None),
        )

        # Commit the stripped text as the session's final response text
        self.ctx.response_chunks.clear()
        self.ctx.response_chunks.append(clean_response)

        # Packet 07 B1: the final mutation edge. The committed answer is
        # the turn's last mutation; from here a stop declines ("turn
        # completed, stop declined") instead of firing on a turn that
        # already delivered. Mid-stream stops still work: they claim the
        # start generation, which stays current until this stamp.
        self.turn_activity.stamp()

        # B1: the cognitive tick must run exactly once per turn. Turns that
        # reach RESPONDING without passing REFLECTING (max-loop / oscillation
        # guards, ERROR give-up) tick here, with the real reply — the closest
        # match to advance_turn's assistant_response.
        async for event in self._run_cognition_tick(clean_response):
            yield event

        # Ownership (design §4.2): a guest's turn is one memory at the guest's
        # home. Done here, with the real reply, and never from REFLECTING,
        # whose stand-in reply is Halbert's observations — machine facts that
        # must not reach a guest persona (R2).
        async for event in self._forward_guest_turn(clean_response):
            yield event

        # Phase 4: Parse config-edit blocks from response (ported from chat.py)
        try:
            from ..tools.config_editor import parse_edit_blocks
            edit_blocks = parse_edit_blocks(full_response)
            if edit_blocks:
                import uuid as _uuid
                diff_id = str(_uuid.uuid4())
                self.ctx.pending_diffs[diff_id] = {
                    "file_path": None,  # filled by frontend or tool context
                    "edit_blocks": edit_blocks,
                    "status": "pending",
                }
                yield StreamEvent(
                    type="diff_proposed",
                    data={
                        "diff_id": diff_id,
                        "block_count": len(edit_blocks),
                        # The blocks ride the event so config-editor flows can
                        # build a preview diff client-side (the agent path
                        # does not know the editor's current buffer content).
                        "edit_blocks": edit_blocks,
                        "session_id": self.ctx.session_id,
                    },
                )
                logger.info(f"Parsed {len(edit_blocks)} edit blocks from response")
        except Exception as e:
            logger.debug(f"Edit block parsing skipped: {e}")

        # Phase 8: Extract and emit provenance refs for the response
        try:
            provenance_refs = self._extract_provenance(full_response)
            if provenance_refs:
                yield StreamEvent.response_provenance(
                    self.ctx.session_id, provenance_refs
                )
                logger.info(f"Emitted {len(provenance_refs)} provenance refs")
        except Exception as e:
            logger.debug(f"Provenance extraction skipped: {e}")

        # Phase 8: Emit module invocation events (parsed + stripped above)
        for inv in module_invocations:
            yield StreamEvent.module_invoke(
                self.ctx.session_id, inv["module"], inv.get("props", {})
            )
            logger.info(f"Module invoked: {inv['module']}")

        # Phase 2 modality wiring: demux the response into a MultiStreamPayload
        # and emit modality + speech SSE events for the frontend. When the
        # engine is not installed or the modality is TEXT, this is a no-op
        # (the display_text is the clean_response, no speech segments).
        try:
            if modality_ctx is not None:
                from ..integrations.modality_wiring import (
                    apply_pronunciation,
                    demux_response,
                    get_display_text,
                    get_speech_text,
                    should_speak,
                    spoken_segment_lines,
                )
                from ..integrations.speech_summarizer import make_speech_summarizer
                from ..integrations.tts_quality import adapt_for_speech
                payload = demux_response(
                    clean_response,
                    modality_ctx,
                    session_id=self.ctx.session_id,
                    thread_id=self.ctx.thread_id or "",
                )
                if payload is not None:
                    # Emit modality decision event for the frontend.
                    modality_value = getattr(
                        getattr(modality_ctx, "recommended_modality", None),
                        "value", "text",
                    )
                    # Apply pronunciation substitutions to the speech text
                    # so TTS pronounces domain terms correctly (spec 5.14).
                    # Packet 04 C1: the spoken copy is adapted first — a
                    # code-heavy reply speaks the fallback line, prose is
                    # fence-stripped. The display text is untouched.
                    speech_text = apply_pronunciation(
                        adapt_for_speech(get_speech_text(payload))
                    )
                    yield StreamEvent(
                        type="modality_resolved",
                        session_id=self.ctx.session_id,
                        data={
                            "modality": modality_value,
                            "speech_text": speech_text,
                            "display_text": get_display_text(payload),
                        },
                    )
                    # If voice modality, emit speech segments for the audio
                    # pipeline. The frontend's useAgentStream hook routes
                    # these to the audio playback component.
                    if should_speak(modality_ctx):
                        # O3: collect the spoken segments (post-pronunciation
                        # text + rate) as they are emitted so the TTS egress
                        # hook below can synthesize the same audio the ribbon
                        # is showing. Packet 04 C1: the selection goes
                        # through spoken_segment_lines so the spoken copy is
                        # TTS-adapted (code-heavy -> one fallback line;
                        # prose -> fence-stripped) while the on-screen text
                        # is untouched. Packet 04 C2: a long spoken copy is
                        # summarized to 1-2 sentences by the utility model
                        # before synthesis (the summarizer is fail-soft and
                        # gated on length — short replies are never sent to
                        # a model, and any failure speaks the original).
                        # The speech_text above stays the full adapted
                        # spoken copy (screen-side record); only what is
                        # synthesized is summarized.
                        spoken_segments: List[tuple] = []
                        # A14-G4 (summarizer half): a secure turn's spoken
                        # copy is the same material the turn was restricted
                        # to local models for. Handing it to a cloud utility
                        # slot to be shortened would undo that in one line.
                        summarizer = make_speech_summarizer(
                            self.ctx.session_id,
                            secure=bool(getattr(self.ctx, "secure_context", False)),
                        )
                        for line in spoken_segment_lines(
                            clean_response, payload, summarizer=summarizer
                        ):
                            seg_text = apply_pronunciation(line["text"])
                            seg_rate = float(line.get("rate") or 1.0)
                            spoken_segments.append((seg_text, seg_rate))
                            yield StreamEvent(
                                type="speech_segment",
                                session_id=self.ctx.session_id,
                                data={
                                    "text": seg_text,
                                    "role": line.get("role", "persona"),
                                    "prosody": {
                                        "rate": line.get("rate", 1.0),
                                        "volume": line.get("volume", 1.0),
                                        "whisper": line.get("whisper", False),
                                    },
                                },
                            )
                        logger.info(
                            f"Emitted {len(spoken_segments)} "
                            f"speech segments for voice delivery"
                        )
                        # Packet 04 B1: the turn's mutation digest tail —
                        # accountability for what this spoken command did,
                        # spoken while the user can still hear it. Voice
                        # turns only; a typed turn's effects stay in the
                        # audit chain and the receipt. The same line is
                        # appended to the hash-chained audit log: this is a
                        # turn-scoped rollup of records the write plane
                        # already wrote, not a new audit channel.
                        try:
                            from ..security.turn_digest import spoken_tail
                            tail = spoken_tail(
                                getattr(self.ctx, "turn_digest", None),
                                getattr(self.ctx, "modality", "text"),
                            )
                        except Exception as e:
                            logger.debug(f"turn digest tail skipped (non-fatal): {e}")
                            tail = None
                        if tail:
                            spoken_segments.append((tail, 1.0))
                            yield StreamEvent(
                                type="speech_segment",
                                session_id=self.ctx.session_id,
                                data={
                                    "text": tail,
                                    "role": "persona",
                                    "prosody": {
                                        "rate": 1.0,
                                        "volume": 1.0,
                                        "whisper": False,
                                    },
                                },
                            )
                            try:
                                from ..obs.audit import write_audit
                                write_audit(
                                    tool="turn_digest",
                                    mode="rollup",
                                    request_id=self.ctx.request_id,
                                    ok=True,
                                    # A05 bug 7: the SAME scrubbed string
                                    # the tail speaks. ``tail`` already
                                    # came through the egress seam; the
                                    # rollup used to be built separately.
                                    summary=tail,
                                    reason="voice turn mutation digest",
                                )
                            except Exception as e:
                                logger.debug(f"turn digest audit rollup failed (non-fatal): {e}")
                        # Voice mode (O3): stream the same spoken segments to
                        # any browser subscribed to this session's audio on
                        # /api/audio/tts. Strictly optional — the turn is
                        # already complete for everyone else.
                        if spoken_segments:
                            try:
                                await self._speak_to_tts_egress(spoken_segments)
                            except Exception as e:
                                self._egress_log_once(
                                    "hook",
                                    f"TTS egress skipped (non-fatal): {e}",
                                )
        except Exception as e:
            logger.debug(f"Modality demux/delivery skipped (non-fatal): {e}")

        # Final committed text is the stripped response — see the stripping
        # note above. Streaming may have already shown the raw tail, so
        # response_complete carries the clean text for the final commit.
        complete_event = StreamEvent.response_complete(self.ctx.session_id)
        complete_event.data["content"] = clean_response
        yield complete_event
        # User-facing status: success (A2c). The ERROR give-up path has
        # already moved the status to the terminal ERROR before routing here;
        # a terminal status cannot transition, so leave it as-is.
        if not self.ctx.conversation_status.is_terminal():
            yield self._set_conversation_status(ConversationStatus.SUCCESS)
        yield await self._transition(AgentState.IDLE)

    # ------------------------------------------------------------------
    # Voice mode (O3): TTS egress to browser subscribers
    # ------------------------------------------------------------------

    def _voice_tts_for_egress(self) -> Any:
        """The PiperTTS instance behind the Haloysius voice backend.

        Reached through the app seam (the same backend the engine's own
        synthesis uses), so one model loads per process instead of one per
        consumer; cached on the machine. Returns None when the seam has no
        voice backend (engine absent, audio-inference extra missing) — the
        egress hook then stays silent.
        """
        if self._egress_tts is not None:
            return self._egress_tts
        try:
            from haloysius.seam import get_app_seam
            seam = get_app_seam()
            backend = seam.get_voice_backend() if seam is not None else None
            if backend is not None:
                self._egress_tts = backend.get_tts()
        except Exception:
            self._egress_tts = None
        return self._egress_tts

    async def _speak_to_tts_egress(self, segments: List[tuple]) -> None:
        """Synthesize and stream spoken segments to browser TTS subscribers.

        The hub (dashboard ``routes/tts_egress.py``, the get_event_bus-style
        module singleton — this machine holds no FastAPI app reference) is
        the only gate: no subscriber for this turn's session means no
        synthesis at all. Per segment, publish:

            {"type": "begin", "sample_rate": <model rate>, "format": "s16le"}
            <binary PCM chunks>
            {"type": "end"} or {"type": "cancelled"}

        The sample rate is the Piper model's real rate (commonly 22050, not
        the module's 16k constant) — ``PiperTTS.synthesize`` records it on
        the instance, which ``HalbertVoiceBackend`` already reads.

        Barge-in: the token comes from the audio pipeline coordinator when
        it is running (VAD barge-in then cancels browser playback too);
        otherwise a standalone BargeInToken, still checked between chunks
        and triggerable through the hub (the /api/audio/tts cancel control
        frame). A token fired before the first chunk publishes nothing —
        the browser cancels its own playback on interrupt.

        Prosody: ``rate`` maps to Piper speed exactly as
        ``HalbertVoiceBackend.synthesize`` does (the same ``_speed``
        override, restored in ``finally`` — it carries the same
        shared-instance caveat). ``volume``/``whisper`` are the browser's
        GainNode business; the speech_segment event already carried them.

        PiperTTS generates a whole clip before yielding its first chunk
        (sherpa-onnx is batch), so awaiting this inline costs one synthesis
        pass, not the clip's duration — and the speech_segment SSE events
        above have already reached the browser by then.
        """
        try:
            from ..dashboard.routes.tts_egress import get_tts_egress_hub
        except Exception as e:
            self._egress_log_once("hub_import", f"TTS egress hub unavailable: {e}")
            return
        hub = get_tts_egress_hub()
        session_id = self.ctx.session_id
        if not hub.has_subscribers(session_id):
            return
        tts = self._voice_tts_for_egress()
        if tts is None:
            # A subscriber is waiting but there is no engine to speak with —
            # the one case worth a warning (once); after that it is the
            # deployment's steady state, not news.
            self._egress_log_once(
                "tts_unavailable",
                "TTS egress: browser subscribed but no PiperTTS is available",
            )
            return

        # Wake-before-speak (P2): a turn that starts from standby must not
        # talk at a black screen — raise the panel before the first
        # ``begin`` frame reaches the browser. The display module is
        # best-effort by contract (never raises, no-ops without hardware),
        # and neither is it news when it is unavailable (every macOS dev
        # machine is), so a debug line is all a miss earns.
        try:
            from ..system import display_power
            # Off the loop thread: wake may spawn xset, and a hung X server
            # must never stall every SSE stream (and the very ``begin``
            # frame this precedes) behind a blocking subprocess.
            await asyncio.to_thread(display_power.wake)
        except Exception:
            logger.debug("wake-before-speak unavailable", exc_info=True)

        # Barge-in token: coordinator-owned when the pipeline runs, so VAD
        # barge-in (coordinator.trigger_barge_in) cancels this synthesis
        # too; standalone otherwise.
        token = None
        pipeline = getattr(hub, "pipeline", None)
        if pipeline is not None:
            try:
                token = pipeline.create_barge_in_token()
            except Exception:
                token = None
        if token is None:
            from ..audio.speech.barge_in import BargeInHandler
            token = BargeInHandler().create_token()

        hub.register_cancel_token(session_id, token)
        any_began = False
        sent_cancelled = False
        try:
            spoken_words = 0
            total_words = sum(len((t or "").split()) for t, _ in segments)
            for text, rate in segments:
                # Barge-in between segments: stop before spending a full
                # sherpa-onnx generation pass on a segment nobody will hear.
                if token is not None and token.is_set():
                    # A10-G6: record what the listener actually heard, so
                    # the NEXT turn knows it was interrupted. Barge-in
                    # stopped the audio and told the model nothing, and
                    # the commonest reason a person interrupts is that
                    # the answer had already gone wrong.
                    try:
                        from ..integrations.modality_wiring import record_barge_in
                        record_barge_in(
                            session_id,
                            spoken_words=spoken_words,
                            total_words=total_words,
                        )
                    except Exception as e:
                        logger.debug(f"barge-in note not recorded: {e}")
                    break
                if not text.strip():
                    continue
                original_speed = tts._speed
                tts._speed = rate
                began = False
                try:
                    async for chunk in tts.synthesize(text, cancel_token=token):
                        if token is not None and token.is_set():
                            break
                        if not began:
                            began = True
                            await hub.publish(session_id, {
                                "type": "begin",
                                "sample_rate": getattr(
                                    tts, "_sample_rate", None
                                ) or 16000,
                                "format": "s16le",
                            })
                        await hub.publish(session_id, chunk)
                    spoken_words += len((text or "").split())
                finally:
                    tts._speed = original_speed
                if began:
                    any_began = True
                    cancelled = token is not None and token.is_set()
                    if cancelled:
                        sent_cancelled = True
                    await hub.publish(
                        session_id,
                        {"type": "cancelled" if cancelled else "end"},
                    )
            # Barge-in in the window between one segment's end and the next
            # segment's first chunk: the loop broke before that segment's
            # ``began`` ever turned True, so nothing was published for it —
            # tell the browser anyway, or it plays the clip it already
            # scheduled to the end instead of stopping.
            if (
                not sent_cancelled
                and any_began
                and token is not None
                and token.is_set()
            ):
                await hub.publish(session_id, {"type": "cancelled"})
        finally:
            hub.clear_cancel_token(session_id)
            # Give the coordinator its slot back so it does not go stale
            # after the turn (a stale active token would eat the next VAD
            # barge-in). No-op when the active token has moved on. NOTE for
            # whoever wires VAD to the pipeline's own speak(): speak() also
            # fills _active_barge_in_token — one active token, one turn;
            # these two writers must stay mutually exclusive.
            if pipeline is not None and token is not None:
                try:
                    pipeline.release_barge_in_token(token)
                except Exception:
                    pass

    def _egress_log_once(self, site: str, message: str) -> None:
        """Warn once per egress failure site, then drop to debug.

        Voice egress is strictly optional, so a failure must never spam every
        voice turn — but the first occurrence is a real wiring/model problem
        an operator should see in the logs.
        """
        if site in self._egress_warned:
            logger.debug(message)
            return
        self._egress_warned.add(site)
        logger.warning(message)

    async def _handle_error(self) -> AsyncIterator[StreamEvent]:
        """
        ERROR state: Handle and recover from errors.
        """
        self.ctx.error_recovery_attempts += 1
        logger.warning(
            f"ERROR: attempt={self.ctx.error_recovery_attempts}, "
            f"error={self.ctx.error}"
        )
        
        if self.ctx.error_recovery_attempts >= 3:
            # Give up, respond with error context
            yield self._set_conversation_status(ConversationStatus.ERROR)
            yield await self._transition(AgentState.RESPONDING)
        else:
            # Try to recover by replanning
            self.ctx.error = None
            # Transient error → resume working (A2c)
            yield self._set_conversation_status(ConversationStatus.TRANSIENT_ERROR)
            yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)
            yield await self._transition(AgentState.PLANNING)
    
    async def _handle_awaiting_confirmation(self) -> AsyncIterator[StreamEvent]:
        """
        AWAITING_CONFIRMATION state: Wait for user to confirm/reject.
        
        This is a blocking state - processing pauses until
        confirm_action() is called.
        """
        logger.info(f"AWAITING_CONFIRMATION: {self.ctx.pending_confirmation}")
        # No events to yield - we wait for external input
        return
        yield  # Make it an async generator
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    def _build_simple_planning_prompt(self, context: str) -> str:
        """Build a simple planning prompt when no prompt builder available."""
        parts = []
        if self.ctx.continuity_hint:
            parts.extend([self.ctx.continuity_hint, ""])
        parts += [
            f"User query: {self.ctx.user_query}",
            "",
            "Available context:",
            context or "(none)",
            "",
            "Observations so far:",
            "\n".join(self.ctx.observations) or "(none)",
            "",
            "Instructions:",
            "1. Analyze what information is needed to answer the query",
            "2. If you need more information, use available tools",
            "3. If you have enough information, provide your answer",
        ]
        return "\n".join(parts)
    
    def _parse_module_invocations(self, response: str) -> tuple:
        """Parse module invocation requests from the LLM response.

        The LLM can emit structured JSON blocks to invoke modules:
        {"action": "invoke_module", "module": "vitals", "props": {"timeframe": "1h"}}

        The backend validates that the module exists in the registry
        before emitting the invocation event.

        Returns:
            (invocations, stripped_response) — valid invocation dicts plus
            the response text with every well-formed invoke_module JSON block
            removed, so the invocation markup never remains user-visible
            (it is rendered as a module SSE event instead).
        """
        import json

        from ..modules import get_module_registry
        registry = get_module_registry()

        invocations = []
        spans = []  # (start, end) character spans of invocation blocks

        # Find all JSON-like blocks in the response and try to parse them
        # Look for {"action": "invoke_module", ...} patterns
        # We use a balanced-brace approach: find the start, then match braces
        idx = 0
        while idx < len(response):
            # Find the start of a potential JSON block
            start = response.find('{"action"', idx)
            if start == -1:
                break

            # Find the matching closing brace
            depth = 0
            end = start
            for i in range(start, len(response)):
                if response[i] == '{':
                    depth += 1
                elif response[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            else:
                break  # No matching brace found

            json_str = response[start:end]
            try:
                data = json.loads(json_str)
                if data.get("action") == "invoke_module":
                    # Strip every well-formed invocation block — even ones
                    # naming unknown modules — so raw JSON never leaks into
                    # the chat bubble.
                    spans.append((start, end))
                    module_name = data.get("module", "")
                    # Validate module exists
                    module = registry.get(module_name)
                    if module:
                        invocations.append({
                            "module": module_name,
                            "props": data.get("props", {}),
                        })
                    else:
                        logger.warning(
                            f"LLM tried to invoke unknown module: {module_name}"
                        )
            except json.JSONDecodeError:
                pass  # Not valid JSON, skip

            idx = end

        # Build the stripped response (drop invocation blocks plus the
        # surrounding whitespace they leave behind)
        if spans:
            parts = []
            prev = 0
            for start, end in spans:
                parts.append(response[prev:start])
                prev = end
            parts.append(response[prev:])
            stripped = "".join(parts)
            # Collapse 3+ consecutive blank lines left by removed blocks
            import re
            stripped = re.sub(r'\n{3,}', '\n\n', stripped).strip()
        else:
            stripped = response

        return invocations, stripped

    def _extract_provenance(self, response: str) -> list:
        """Extract provenance refs from the response and retrieved context.

        Phase 8: Validates that refs point to real data before attaching.
        Uses the retrieved context and observations as evidence sources.
        """
        from ..proactive.provenance import (
            ProvenanceRef, parse_path_lines_ref, attach_provenance
        )
        import re

        refs = []

        # 1. Extract path:line references from the response text
        # Match patterns like /etc/ssh/sshd_config:42 or /path/file:10-20
        path_pattern = r'(/(?:etc|var|usr|home|tmp|opt|srv|root|Library|System)[\w/.-]+):(\d+)(?:-(\d+))?'
        for match in re.finditer(path_pattern, response):
            path = match.group(1)
            start = int(match.group(2))
            end = int(match.group(3)) if match.group(3) else None
            refs.append(parse_path_lines_ref(path, start, end))

        # 2. Create provenance from retrieved context sources.
        # ctx.retrieved_context items carry {source, content, metadata}.
        # Only emit refs that can actually validate — never fabricated ids.
        # Thread receipts are skipped before the slice, not inside the loop:
        # they can never produce a ref, so counting them against these five
        # entries only thinned the citations (see _retrieval_documents).
        for ctx in self._retrieval_documents()[:5]:
            source = ctx.get('source', '')
            content = ctx.get('content', '') or ''
            meta = ctx.get('metadata') or {}
            item_id = ctx.get('id') or meta.get('id')

            if source == 'file':
                # path_lines needs a real existing file AND an explicit line
                # spec (e.g. "path:42"); without line info no valid ref is
                # possible, so drop deliberately rather than emit a ref that
                # validation would discard anyway.
                path = meta.get('path')
                line = meta.get('line') or meta.get('line_start')
                if path and line:
                    refs.append(ProvenanceRef(
                        type='path_lines',
                        ref=f'{path}:{line}',
                        label=f"Retrieved from {path} (line {line})",
                    ))
            elif source == 'memory' and item_id:
                refs.append(ProvenanceRef(
                    type='memory_id',
                    ref=str(item_id),
                    label=f"Memory: {content[:60]}",
                ))
            elif source in ('rag', 'retrieval') and item_id:
                refs.append(ProvenanceRef(
                    type='observation_id',
                    ref=str(item_id),
                    label=f"Observation: {content[:60]}",
                ))

        # NOTE: self.ctx.observations holds plain strings with no stable id,
        # so no valid ref type can point at them — that branch was removed
        # rather than building 'observation:' log_cursors that always fail
        # validation.

        # Validate and attach — invalid refs are dropped
        packaged = attach_provenance("", refs)
        return packaged['provenance']

    def _fallback_identity(self) -> str:
        """Who the answer is from when the prompt builder failed to wire.

        This path is reached exactly when something is already wrong, and
        before the merge it answered as a generic assistant — so a wiring
        failure quietly changed who the admin was talking to. Main fixed that
        on ``handlers/responding.py``; the handlers package left with Plan A
        and took the fix and its three tests with it, so the fix moves onto
        the path that survived (P6: superseded tests are rewritten, and a
        rewrite needs something true to assert).
        """
        try:
            from ..prompts.agent_prompts import AgentPromptBuilder
            identity = AgentPromptBuilder()._get_identity()
            if identity and identity.strip():
                return identity.strip()
        except Exception as e:  # pragma: no cover - broken prompts package
            logger.warning(f"Identity unavailable for the fallback prompt: {e}")
        return (
            "You are Halbert. You live on this machine — not as a chatbot "
            "that happens to run here, but as the system itself. Speak from "
            "what you actually observe about it, be concise and practical, "
            "and cite sources when available."
        )

    def _build_simple_response_prompt(self, response_modality: str = "text") -> str:
        """Build a simple response prompt when no prompt builder available."""
        # Receipts are rendered in their own block, so continuity cannot spend
        # the five retrieval slots (see _retrieval_documents).
        context_text = "\n".join([
            f"[{c.get('source', 'unknown')}]: {c.get('content', '')[:500]}"
            for c in self._retrieval_documents()[:5]
        ])
        receipt_block = self._receipt_block()
        if receipt_block:
            receipt_block = f"{receipt_block}\n\n"

        obs_text = "\n".join([f"- {obs}" for obs in self.ctx.observations])

        # Phase 2.5: modality-conditional formatting (same logic as
        # AgentPromptBuilder.build_response_prompt).
        if response_modality == "voice":
            formatting_line = (
                "- Respond in plain text suitable for speech: short "
                "sentences, no markdown syntax, no code blocks"
            )
            response_style = "plain text, spoken naturally"
        else:
            formatting_line = (
                "- Use **markdown formatting**: headers (##), bullet "
                "points (-), **bold**, `code`, code blocks (```bash)"
            )
            response_style = "markdown formatting"

        return f"""{self._fallback_identity()}

Answer this question: {self.ctx.user_query}

{receipt_block}Available Information:
{context_text}

What I've done:
{obs_text}

Instructions:
- Provide a helpful, accurate response
{formatting_line}
- Cite sources when possible
- Be concise but complete

Your response ({response_style}):"""
