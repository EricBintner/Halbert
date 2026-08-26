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

from .states import AgentState, StateContext, CRAGAction, ToolCall, PlanStep, ConversationStatus
from .events import StreamEvent

if TYPE_CHECKING:
    from ..tools.safety import ToolSafetyFramework
    from ..tools.executor import ToolExecutor

logger = logging.getLogger('halbert.agents.state_machine')


# Subagent lifecycle statuses that end waiting (D1d)
_SUBAGENT_TERMINAL = {"completed", "failed", "cancelled"}


def _subagent_terminal(status: str) -> bool:
    return status in _SUBAGENT_TERMINAL


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
            AgentState.RESPONDING, AgentState.ERROR
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
    ) -> AsyncIterator[StreamEvent]:
        """
        Process a user query through the state machine.
        
        Yields StreamEvents for real-time frontend updates.
        
        Args:
            query: User's question/request
            session_id: Optional session ID (generated if not provided)
            user_id: Optional user ID
            conversation_history: Previous messages in conversation
            
        Yields:
            StreamEvent objects for each state change, tool call, etc.
        """
        session_id = session_id or str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        # Initialize context
        self.ctx = StateContext(
            session_id=session_id,
            request_id=request_id,
            user_query=query,
            user_id=user_id,
            conversation_history=conversation_history or [],
            max_loops=self.max_loops,
            images=images,
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
        
        # Start processing
        yield await self._transition(AgentState.PLANNING)
        
        try:
            # Main loop
            while self.current_state != AgentState.IDLE:
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

        finally:
            # Cleanup — but keep a paused (awaiting-confirmation) session so
            # confirm_action() can find it.
            if (session_id in self.active_sessions
                    and self.current_state != AgentState.AWAITING_CONFIRMATION):
                del self.active_sessions[session_id]
    
    async def confirm_action(
        self,
        session_id: str,
        action_id: str,
        confirmed: bool
    ) -> AsyncIterator[StreamEvent]:
        """
        Handle user confirmation for high-risk actions.
        
        Args:
            session_id: Session ID
            action_id: Action execution ID
            confirmed: Whether user confirmed the action
            
        Yields:
            StreamEvent objects
        """
        if session_id not in self.active_sessions:
            yield StreamEvent.error(session_id, "Session not found", recoverable=False)
            return
        
        self.ctx = self.active_sessions[session_id]
        
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

                # Continue processing
                async for event in self._handle_executing():
                    yield event
            else:
                # User rejected - go back to planning
                self.ctx.pending_confirmation = None
                self.ctx.add_observation("User rejected the action")
                # Rejection resumes the conversation (the agent re-plans and still
                # responds), so this is IN_PROGRESS, not a terminal CANCELLED.
                # True cancellation is cancel_session() below. (A2c)
                yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)
                yield await self._transition(AgentState.PLANNING)
        finally:
            # The paused session was kept in active_sessions only so this
            # method could find it. Evict it now unless the machine paused
            # again on another confirmation.
            if (session_id in self.active_sessions
                    and self.current_state != AgentState.AWAITING_CONFIRMATION):
                del self.active_sessions[session_id]
    
    def cancel_session(self, session_id: str) -> bool:
        """Cancel an active session."""
        if session_id in self.active_sessions:
            ctx = self.active_sessions[session_id]
            # User-facing status: cancelled (A2c). Guard against an already-
            # terminal conversation (e.g. already SUCCESS/ERROR).
            if not ctx.conversation_status.is_terminal():
                try:
                    ctx.conversation_status.transition(ConversationStatus.CANCELLED)
                except ValueError:
                    pass
            del self.active_sessions[session_id]
            self.current_state = AgentState.IDLE
            return True
        return False
    
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
        )
        try:
            from ..proactive.events import ProactiveEvent, get_event_bus
            pe = ProactiveEvent.create(
                type="somatic_block",
                severity="info",
                title=f"Block {event.data['block_type']}: {event.data['status']}",
                body=f"session={block.session_id} block={block.id}",
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
                conversation=self.ctx.conversation_history,
                observations=self.ctx.observations,
                intake=self.ctx.intake,
            )
            context_content = assembled.content
            yield StreamEvent.context_loaded(
                self.ctx.session_id,
                "assembled",
                len(assembled.sources),
                assembled.total_tokens
            )
        
        # Build prompt
        if self.prompts:
            prompt = self.prompts.build_planning_prompt(
                query=self.ctx.user_query,
                context=context_content,
                plan=[p.to_dict() for p in self.ctx.plan]
            )
        else:
            prompt = self._build_simple_planning_prompt(context_content)
        
        # Call LLM
        tool_schemas = self.tools.get_schemas() if self.tools else []
        
        response = await self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=tool_schemas,
            intake_result=self.ctx.intake if self.ctx else None,
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
        if self.crag and self.ctx.retrieved_context:
            crag_result = await self.crag.evaluate(
                self.ctx.user_query,
                self.ctx.retrieved_context,
                self.ctx.observations
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
            tc = ToolCall(
                id=str(uuid.uuid4())[:8],
                name=tool_call.function.name,
                args=tool_call.function.arguments
            )
            self.ctx.add_tool_call(tc)
            
            # Route based on tool type
            tool_name = tool_call.function.name
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
            
            result = await self.tools.execute(
                tool_name,
                tool_args,
                session_id=self.ctx.session_id,
                confirmed=confirmed
            )
            
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
                self.ctx.add_observation(f"Executed {tool_name}: success")
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
        if self.crag and self.ctx.retrieved_context:
            crag_result = await self.crag.evaluate(
                self.ctx.user_query,
                self.ctx.retrieved_context,
                self.ctx.observations
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
            if self.ctx.retrieved_context:
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
        
        # Build response prompt
        if self.prompts:
            prompt = self.prompts.build_response_prompt(
                query=self.ctx.user_query,
                context=self.ctx.retrieved_context,
                observations=self.ctx.observations
            )
            logger.info("Using AgentPromptBuilder for response prompt")
        else:
            prompt = self._build_simple_response_prompt()
            logger.info("Using simple response prompt (no prompt builder)")
        
        # DEBUG: Log the prompt to verify markdown instructions are included
        logger.debug(f"Response prompt (first 500 chars): {prompt[:500]}")
        
        # Stream response
        if hasattr(self.llm, 'stream'):
            logger.info(f"Starting LLM stream for session {self.ctx.session_id}")
            chunk_count = 0
            async for chunk in self.llm.stream(
                messages=[{"role": "user", "content": prompt}],
                intake_result=self.ctx.intake if self.ctx else None,
                images=self.ctx.images if self.ctx else None,
            ):
                chunk_count += 1
                logger.debug(f"Chunk {chunk_count}: {repr(chunk[:50])}...")
                self.ctx.response_chunks.append(chunk)
                yield StreamEvent.response_chunk(self.ctx.session_id, chunk)
            logger.info(f"LLM stream complete: {chunk_count} chunks")
        else:
            # Non-streaming fallback
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                intake_result=self.ctx.intake if self.ctx else None,
                images=self.ctx.images if self.ctx else None,
            )
            content = response.content if hasattr(response, 'content') else str(response)
            self.ctx.response_chunks.append(content)
            yield StreamEvent.response_chunk(self.ctx.session_id, content)
        
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

        # Store interaction in memory (clean text, no invocation JSON)
        if self.memory:
            await self.memory.store_interaction(
                query=self.ctx.user_query,
                response=clean_response,
                session_id=self.ctx.session_id
            )

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
        parts = [
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
        for ctx in self.ctx.retrieved_context[:5]:
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

    def _build_simple_response_prompt(self) -> str:
        """Build a simple response prompt when no prompt builder available."""
        context_text = "\n".join([
            f"[{c.get('source', 'unknown')}]: {c.get('content', '')[:500]}"
            for c in self.ctx.retrieved_context[:5]
        ])
        
        obs_text = "\n".join([f"- {obs}" for obs in self.ctx.observations])
        
        return f"""Answer this question: {self.ctx.user_query}

Available Information:
{context_text}

What I've done:
{obs_text}

Instructions:
- Provide a helpful, accurate response
- Use **markdown formatting**: headers (##), bullet points (-), **bold**, `code`, code blocks (```bash)
- Cite sources when possible
- Be concise but complete

Your response (use markdown formatting):"""
