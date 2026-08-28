# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agent State Machine

Core orchestration using a state machine pattern with CRAG evaluation.
Based on research5.md Part 6.
"""

from __future__ import annotations
import asyncio
import logging
import re
import time
import uuid
from typing import AsyncIterator, Dict, List, Optional, Callable, Any, TYPE_CHECKING

from .blocks import content_to_text
from .states import AgentState, StateContext, CRAGAction, ToolCall, PlanStep, ConversationStatus
from .events import StreamEvent
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
            logger.info(f"Session {session_id} waiting for the current turn to finish")
            yield StreamEvent.conversation_status(
                session_id, "waiting", waiting_for="previous turn"
            )

        # One turn at a time (spec §12). Everything below, including the
        # finally, runs under the lock; asyncio.Lock is not task-bound, so
        # releasing it from the generator's cleanup is fine whichever task
        # drives the last step. The wait is bounded (TURN_LOCK_TIMEOUT_S) so
        # a wedged turn surfaces as an error the user can retry instead of
        # queueing every later message behind a badge that never changes.
        if not await self._acquire_turn_lock(session_id):
            for event in self._turn_lock_timeout_events(session_id):
                yield event
            return

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

            # Phase D: Inject persona cognition if tick is wired
            if self.cognition_tick is not None:
                try:
                    from ..integrations.cognition_wiring import get_cognition
                    self.ctx.persona_cognition = get_cognition()
                except Exception as e:
                    logger.warning(f"Could not inject persona cognition: {e}")

            # Track active session
            self.active_sessions[session_id] = self.ctx

            logger.info(f"Starting agent processing: session={session_id}, query={query[:100]}")

            yield StreamEvent.session_started(session_id, request_id)

            # Plan A: persist the user row and resolve the thread before any
            # model call (spec §4.1-§4.4), under the lock so thread
            # resolve/open/pause never races another turn.
            async for event in self._begin_turn():
                yield event

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
                async for event in self._drive():
                    yield event
            finally:
                # end_turn before the state reset: the status is derived
                # from where the machine stopped (spec §4.7, §12).
                self._end_turn(self._turn_status(session_id))
                self._settle_turn(session_id)
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
        self.active_sessions.pop(session_id, None)
        self.cancelled.pop(session_id, None)

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
                diff_proposals=diffs,
                status=status,
                thread_id_override=ctx.thread_id if ctx.thread_switched else None,
            )
        except Exception as e:
            logger.warning(f"end_turn failed (non-fatal): {e}")

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
        if session_id not in self.active_sessions:
            return False
        ctx = self.active_sessions[session_id]
        self.cancelled[session_id] = True
        # User-facing status: cancelled (A2c). Guard against an already-
        # terminal conversation (e.g. already SUCCESS/ERROR).
        if not ctx.conversation_status.is_terminal():
            try:
                ctx.conversation_status.transition(ConversationStatus.CANCELLED)
            except ValueError:
                pass
        paused = self.current_state == AgentState.AWAITING_CONFIRMATION
        if paused or not self._turn_in_flight():
            self._record_superseded_turn(ctx)
            del self.active_sessions[session_id]
            self.current_state = AgentState.IDLE
        return True

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
    
    def _build_messages(self, prompt: str, tail: str = "") -> List[Dict[str, Any]]:
        """Instructions, then the prior turns, then the new question.

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
        messages: List[Dict[str, Any]] = [{"role": "system", "content": prompt}]
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
        query = self.ctx.user_query
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

    async def _handle_planning(self) -> AsyncIterator[StreamEvent]:
        """
        PLANNING state: Analyze query, create plan, decide next action.
        """
        logger.info(f"PLANNING: {self.ctx.user_query[:50]}...")
        
        # Assemble context if we have context assembler.
        # NOTE: this is the single context-assembly call site for planning —
        # intake.context_budget controls the token budget, so max_tokens is
        # intentionally not passed (the intake assembler overrides it anyway).
        context_content = ""
        if self.context:
            assembled = await self.context.assemble(
                query=self.ctx.user_query,
                observations=self.ctx.observations,
                intake=self.ctx.intake,
                session_id=self.ctx.session_id,
            )
            context_content = assembled.content
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
        response = await self.llm.chat(
            messages=self._build_messages(prompt, tail=self._continuity_tail()),
            tools=tool_schemas,
            intake_result=self.ctx.intake if self.ctx else None,
            images=self.ctx.images if self.ctx else None,
            model_override=self.ctx.model_override if self.ctx else None,
            tier_override=self.ctx.tier_override if self.ctx else None,
            # What the complexity router scores. The final message is the
            # question with the continuity hint glued to its front (D1), and
            # routing on that picked the specialist for "hi".
            routing_prompt=self.ctx.user_query if self.ctx else "",
        )
        
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
            if tool_name in ["search", "search_discoveries", "recall_memory", "web_search"]:
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
        
        if tool_call and tool_call.name in ["search", "web_search"]:
            search_query = tool_call.args.get("query", self.ctx.user_query)
        else:
            search_query = self.ctx.user_query
        
        # Execute searches in parallel
        tasks = []
        
        if self.rag:
            tasks.append(("rag", self.rag.search(search_query, limit=5)))
        
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
        
        self.ctx.add_observation(
            f"Retrieved {len(self.ctx.retrieved_context)} context items"
        )
        
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
        
        if self.tools:
            result = await self.tools.execute("read_file", {"path": file_path})
            
            yield StreamEvent.tool_complete(
                self.ctx.session_id,
                exec_id,
                result.success,
                result.result[:500] if result.result else None,
                result.error
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
    def _terminal_event(session_id: str, payload: Dict[str, Any]) -> Optional[StreamEvent]:
        """Convert a terminal-bridge payload into its SSE event."""
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
            return StreamEvent.terminal_complete(
                session_id,
                terminal_id,
                int(exit_code) if exit_code is not None else -1,
            )
        return None

    def _note_terminal_payload(self, payload: Dict[str, Any]) -> None:
        """Remember every terminal this turn spawned (persisted at end_turn)."""
        if payload.get("kind") != "spawn":
            return
        terminal_id = str(payload.get("terminal_session_id", ""))
        block_id = str(payload.get("block_id", ""))
        # Plan B: track block_id when present, fall back to session_id
        track_id = block_id or terminal_id
        if track_id and track_id not in self.ctx.terminal_block_ids:
            self.ctx.terminal_block_ids.append(track_id)

    async def _run_tool_streaming(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmed: bool,
        sink: List[Any],
    ) -> AsyncIterator[StreamEvent]:
        """Execute a tool, yielding terminal events while it runs.

        The tool executor publishes terminal lifecycle payloads onto the
        terminal bridge (streaming/terminal_bridge) for the current agent
        session. Draining that bus concurrently with the tool task is what
        makes a running command visible in the conversation *as it runs*;
        awaiting the tool first would only ever produce a finished transcript.

        The ExecutionResult is appended to ``sink`` — an async generator
        cannot return a value.
        """
        bus = get_terminal_event_bus()
        queue = bus.subscribe(self.ctx.session_id)
        task = asyncio.ensure_future(self.tools.execute(
            tool_name,
            tool_args,
            session_id=self.ctx.session_id,
            confirmed=confirmed,
        ))
        try:
            while True:
                getter = asyncio.ensure_future(queue.get())
                done, _pending = await asyncio.wait(
                    {task, getter}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    payload = getter.result()
                    self._note_terminal_payload(payload)
                    event = self._terminal_event(self.ctx.session_id, payload)
                    if event is not None:
                        yield event
                    continue
                # Tool finished with nothing queued: stop waiting on the queue.
                getter.cancel()
                break

            # Flush whatever the tool published on its way out.
            while not queue.empty():
                payload = queue.get_nowait()
                self._note_terminal_payload(payload)
                event = self._terminal_event(self.ctx.session_id, payload)
                if event is not None:
                    yield event

            sink.append(await task)
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
                tool_name, tool_args, confirmed, sink
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
            
            if result.success:
                tool_call.status = "success"
                tool_call.result = result.result
                # The observation has to carry the *output*, not just "success".
                # Observations are the only channel by which a tool result
                # reaches the next PLANNING pass; recording bare success left
                # the model blind to what it had just learnt, so it re-issued
                # the same call until max_loops cut the turn off.
                self.ctx.add_observation(
                    _format_tool_observation(tool_name, tool_args, result.result)
                )
            else:
                tool_call.status = "error"
                tool_call.error = result.error
                self.ctx.add_observation(f"Executed {tool_name}: {result.error}")
            
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

    async def _handle_responding(self) -> AsyncIterator[StreamEvent]:
        """
        RESPONDING state: Generate final response.
        """
        logger.info(f"RESPONDING: confidence={self.ctx.confidence:.2f}")
        
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
            prompt = self.prompts.build_response_prompt(
                query=self.ctx.user_query,
                context=self.ctx.retrieved_context,
                observations=self.ctx.observations,
                tools_supported=getattr(self.llm, "tools_supported", None),
            )
            logger.info("Using AgentPromptBuilder for response prompt")
        else:
            prompt = self._build_simple_response_prompt()
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
            async for chunk in self.llm.stream(
                messages=self._build_messages(prompt, tail=tail),
                intake_result=self.ctx.intake if self.ctx else None,
                images=self.ctx.images if self.ctx else None,
                model_override=self.ctx.model_override if self.ctx else None,
                tier_override=self.ctx.tier_override if self.ctx else None,
                on_model_selected=selected.append,
                # The question, not the hint that rides in front of it (D1).
                routing_prompt=self.ctx.user_query if self.ctx else "",
            ):
                if selected and not announced:
                    announced = True
                    yield StreamEvent.model_selected(
                        self.ctx.session_id, **selected[-1]
                    )
                chunk_count += 1
                logger.debug(f"Chunk {chunk_count}: {repr(chunk[:50])}...")
                self.ctx.response_chunks.append(chunk)
                yield StreamEvent.response_chunk(self.ctx.session_id, chunk)
            logger.info(f"LLM stream complete: {chunk_count} chunks")
        else:
            # Non-streaming fallback
            response = await self.llm.chat(
                messages=self._build_messages(prompt, tail=tail),
                intake_result=self.ctx.intake if self.ctx else None,
                images=self.ctx.images if self.ctx else None,
                model_override=self.ctx.model_override if self.ctx else None,
                tier_override=self.ctx.tier_override if self.ctx else None,
                on_model_selected=selected.append,
                # The question, not the hint that rides in front of it (D1).
                routing_prompt=self.ctx.user_query if self.ctx else "",
            )
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

        # Commit the stripped text as the session's final response text
        self.ctx.response_chunks.clear()
        self.ctx.response_chunks.append(clean_response)

        # B1: the cognitive tick must run exactly once per turn. Turns that
        # reach RESPONDING without passing REFLECTING (max-loop / oscillation
        # guards, ERROR give-up) tick here, with the real reply — the closest
        # match to advance_turn's assistant_response.
        async for event in self._run_cognition_tick(clean_response):
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

    def _build_simple_response_prompt(self) -> str:
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

        return f"""{self._fallback_identity()}

Answer this question: {self.ctx.user_query}

{receipt_block}Available Information:
{context_text}

What I've done:
{obs_text}

Instructions:
- Provide a helpful, accurate response
- Use **markdown formatting**: headers (##), bullet points (-), **bold**, `code`, code blocks (```bash)
- Cite sources when possible
- Be concise but complete

Your response (use markdown formatting):"""
