# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Agent API Routes

Provides endpoints for the state machine agent with SSE streaming.
Based on research5.md Part 7.
"""

from __future__ import annotations
import logging
import asyncio
from contextlib import aclosing
from typing import Optional, Dict, Any, List

try:
    from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    StreamingResponse = object

logger = logging.getLogger('halbert.dashboard.routes.agent')

if FASTAPI_AVAILABLE:
    router = APIRouter(prefix="/api/agent", tags=["agent"])
else:
    router = None


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    """Request to send a message to the agent."""
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID (auto-generated if not provided)")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for history")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    # Phase 4: Vision/image support (ported from chat.py)
    images: Optional[List[str]] = Field(None, description="Base64-encoded images for vision model")
    # Performance tweaks - sent from frontend Settings > AI > Performance Tweaks
    max_tokens: Optional[int] = Field(8192, description="Max tokens for LLM response")
    temperature: Optional[float] = Field(0.7, description="LLM temperature (0.0-1.0)")


class ConfirmActionRequest(BaseModel):
    """Request to confirm or reject a high-risk action."""
    action_id: str = Field(..., description="Action execution ID")
    confirmed: bool = Field(..., description="Whether to confirm the action")


class AgentStateResponse(BaseModel):
    """Response with current agent state."""
    session_id: str
    state: str
    plan: list = []
    current_step: int = 0
    loop_count: int = 0
    confidence: float = 0.0
    crag_action: str = "PENDING"


class IntakeRequest(BaseModel):
    """Request to run the intake pipeline on a message without executing the agent.

    Used by the boot-gate smoke and operational checks to verify intake routing
    (guide vs specialist vs vision) independently of a full agent round-trip.
    """
    message: str = Field(..., description="User message to classify")


# -----------------------------------------------------------------------------
# Agent Instance Management
# -----------------------------------------------------------------------------

_agent_instance = None


def get_agent():
    """Get or create the agent instance."""
    global _agent_instance

    if _agent_instance is not None:
        return _agent_instance

    try:
        from ...agents import AgentStateMachine
        from ...tools import ToolSafetyFramework, ToolExecutor
        from ...eval.crag import CRAGEvaluator
        from ...context import create_wired_context_assembler, MemoryServiceAdapter
        from ...context.adapters import SourcePrepAdapter
        from ...prompts import AgentPromptBuilder, PromptBuilder, ContextInjector

        # Initialize components
        safety = ToolSafetyFramework()
        tool_executor = ToolExecutor(safety=safety)

        # Create wired context assembler (connects to RAG, discovery, memory)
        context_assembler = create_wired_context_assembler()

        # SEARCHING state retrieval: SourcePrep (RAGServiceAdapter is deprecated on the chat path)
        rag_service = SourcePrepAdapter()
        memory_service = MemoryServiceAdapter()

        # Wire PromptBuilder + ContextInjector into AgentPromptBuilder
        # for rich system prompts with model-specific overrides
        from ...prompts.loader import PromptLoader
        from pathlib import Path as _Path
        try:
            from ...utils.platform import get_config_dir
            prompts_dir = get_config_dir().parent / "config" / "prompts"
            if not prompts_dir.exists():
                prompts_dir = _Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts"
            prompt_loader = PromptLoader(prompts_dir)
            prompt_builder = PromptBuilder(prompt_loader)
        except Exception as e:
            logger.warning(f"Failed to init PromptBuilder: {e}, using None")
            prompt_builder = None
        context_injector = ContextInjector()

        # Load voice setting from BeingConfig (Phase 6)
        try:
            from ...config.being_config import load_being_config
            being_cfg = load_being_config()
            voice = being_cfg.voice
        except Exception:
            voice = "first_person"

        prompt_builder = AgentPromptBuilder(
            base_builder=prompt_builder,
            context_injector=context_injector,
            voice=voice,
        )

        # Create LLM client
        llm_client = _get_llm_client()

        # Create CRAG evaluator (optional, uses LLM for completeness check)
        crag_evaluator = CRAGEvaluator(llm_client=llm_client)

        # Phase D: Wire cognitive tick (Haloysius advance_turn)
        cognition_tick = None
        event_mapper = None
        try:
            from ...integrations.cognition_wiring import get_cognition_tick, get_event_mapper
            cognition_tick = get_cognition_tick()
            event_mapper = get_event_mapper()
            logger.info("Cognitive tick and event mapper wired")
        except Exception as e:
            logger.warning(f"Cognitive tick not available (non-fatal): {e}")

        # Phase 3: Wire intake pipeline
        intake_pipeline = None
        try:
            from ...intake import IntakePipeline, ComplexityRouter, get_context_budget
            from ...model.client import get_configured_model, get_ollama_endpoint

            model_config = _load_model_config()
            guide_model = get_configured_model()
            guide_endpoint = get_ollama_endpoint()

            # Create complexity router with the guide model
            complexity_router = ComplexityRouter(
                llm_caller=_make_llm_caller(),
                guide_model=guide_model,
                endpoint=guide_endpoint,
            )

            intake_pipeline = IntakePipeline(
                complexity_router=complexity_router,
                budget_fn=get_context_budget,
                model_config=model_config,
            )
            logger.info("Intake pipeline wired")
        except Exception as e:
            logger.warning(f"Intake pipeline not available (non-fatal): {e}")

        # Create agent
        _agent_instance = AgentStateMachine(
            llm_client=llm_client,
            tool_executor=tool_executor,
            crag_evaluator=crag_evaluator,
            context_assembler=context_assembler,
            prompt_builder=prompt_builder,
            rag_service=rag_service,
            memory_service=memory_service,
            max_loops=5,
            crag_threshold=0.7,
            cognition_tick=cognition_tick,
            event_mapper=event_mapper,
            intake_pipeline=intake_pipeline,
        )

        logger.info("Agent state machine initialized with wired services")
        return _agent_instance

    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise


def _get_llm_client():
    """Get LLM client - directly uses chat infrastructure for reliability."""
    try:
        # Just return the adapter - it calls chat functions directly
        return LLMClientAdapter()
    except Exception as e:
        logger.warning(f"Could not create LLM client: {e}, using mock")
        return MockLLMClient()


def _load_model_config():
    """Load model config from models.yml for the intake pipeline.

    Returns a dict with keys matching the IntakePipeline's expected
    model_config shape: orchestrator.model, specialist.model/enabled,
    routing.complexity_threshold.
    """
    try:
        from ...model.config_locator import find_models_config
        import yaml

        config_path = find_models_config(include_repo=False)
        if config_path is not None:
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}
    except Exception as e:
        logger.warning(f"Could not load model config: {e}")
        return {}


def _make_llm_caller():
    """Create a callable for ComplexityRouter that wraps call_llm_chat.

    The returned callable has signature:
        caller(endpoint, model, messages, options) -> dict
    """
    from ...model.client import call_llm_chat

    def caller(endpoint, model, messages, options):
        return call_llm_chat(
            endpoint=endpoint,
            model=model,
            messages=messages,
            provider="ollama",
            stream=False,
            timeout=30,
            options=options,
        )

    return caller


class LLMClientAdapter:
    """Adapter that uses same routing logic as Chat (guide vs specialist)."""
    
    def __init__(self):
        """Initialize adapter - calls chat functions directly, no router needed."""
        # Performance tweaks - can be set per-request from frontend settings
        self.max_tokens = 8192
        self.temperature = 0.7
    
    async def chat(self, messages, tools=None, intake_result=None, images=None):
        """Call LLM with messages, routing to specialist for complex queries.

        Tool schemas are forwarded to the model and any tool calls come back on
        ``LLMResponse.tool_calls``. That is what makes EXECUTING / READING /
        AWAITING_CONFIRMATION reachable: PLANNING routes on ``tool_calls``, so
        while this adapter dropped ``tools`` on the floor those three states
        could never be entered from the API, and the approval flow with them.

        The vision path deliberately does not forward tools — vision models
        here are captioners, and mixing the two loses the image.

        Args:
            messages: LLM message list.
            tools: Optional OpenAI-style tool schemas.
            intake_result: Optional Phase 3 MessageIntake for model routing.
            images: Optional list of base64-encoded images for vision model.
        """
        from ...model.client import (
            get_specialist_model, get_configured_model, get_ollama_endpoint,
            score_query_complexity, call_llm_chat, get_vision_model
        )

        # Get the prompt from messages
        prompt = messages[-1].get("content", "") if messages else ""
        system = messages[0].get("content", "") if messages and messages[0].get("role") == "system" else ""

        # Phase 4: Vision model routing when images are present or intake recommends it
        use_vision = bool(images) or (intake_result is not None and intake_result.recommended_model == "vision")
        if use_vision:
            vision_model, vision_endpoint = get_vision_model()
            if vision_model:
                logger.info(f"Agent using vision model: {vision_model}")
                # Add images to the last user message
                llm_messages = []
                if system:
                    llm_messages.append({"role": "system", "content": system})
                for msg in messages:
                    if msg.get("role") != "system":
                        m = dict(msg)
                        if msg.get("role") == "user" and images:
                            m["images"] = images
                        llm_messages.append(m)
                try:
                    result = call_llm_chat(
                        endpoint=vision_endpoint,
                        model=vision_model,
                        messages=llm_messages,
                        provider="ollama",
                        stream=False,
                        timeout=300,
                        options={"num_predict": 2048, "temperature": 0.7},
                    )
                    return LLMResponse(content=result.get("content", ""))
                except Exception as e:
                    logger.error(f"Vision model call failed: {e}, falling back to text")

        # Route based on complexity
        model = get_configured_model()
        if not model:
            raise HTTPException(400, "No model configured — choose one in Settings → AI Models (models.yml)")
        endpoint = get_ollama_endpoint()
        provider = "ollama"

        specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
        if specialist_model:
            if intake_result is not None:
                # Phase 3: Use intake's recommended_model
                use_specialist = intake_result.recommended_model == "specialist"
                logger.info(f"Agent using intake routing: {intake_result.recommended_model}")
            else:
                # Fallback: legacy complexity scoring
                complexity_score = score_query_complexity(prompt)
                use_specialist = complexity_score >= 0.5
                logger.info(f"Agent using legacy routing (complexity: {complexity_score:.2f})")

            if use_specialist:
                model = specialist_model
                endpoint = specialist_endpoint
                provider = specialist_provider or "ollama"
        
        # Build messages for LLM
        llm_messages = []
        if system:
            llm_messages.append({"role": "system", "content": system})
        for msg in messages:
            if msg.get("role") != "system":
                llm_messages.append(msg)
        
        try:
            # Call LLM using shared model client
            result = call_llm_chat(
                endpoint=endpoint,
                model=model,
                messages=llm_messages,
                provider=provider,
                stream=False,
                timeout=300,
                options={"num_predict": 2048, "temperature": 0.7},
                tools=tools,
            )
            return LLMResponse(
                content=result.get("content", ""),
                tool_calls=_as_tool_calls(result.get("tool_calls")),
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Fallback to guide model
            if specialist_model and model == specialist_model:
                logger.info("Falling back to guide model")
                guide_model = get_configured_model()
                if not guide_model:
                    raise HTTPException(400, "No model configured — choose one in Settings → AI Models (models.yml)")
                guide_endpoint = get_ollama_endpoint()
                result = call_llm_chat(
                    endpoint=guide_endpoint,
                    model=guide_model,
                    messages=llm_messages,
                    provider="ollama",
                    stream=False,
                    timeout=180,
                    tools=tools,
                )
                return LLMResponse(
                    content=result.get("content", ""),
                    tool_calls=_as_tool_calls(result.get("tool_calls")),
                )
            raise
    
    async def stream(self, messages, intake_result=None, images=None):
        """Stream response from LLM with true incremental streaming.
        
        Uses aiohttp for async streaming. Filters out <think> blocks in real-time.
        Uses self.max_tokens and self.temperature from instance (set per-request).
        """
        import aiohttp
        import re
        from ...model.client import (
            get_specialist_model, get_configured_model, get_ollama_endpoint,
            score_query_complexity, get_vision_model
        )
        
        # Use instance variables for performance tweaks
        max_tokens = self.max_tokens
        temperature = self.temperature
        logger.info(f"LLM streaming with max_tokens={max_tokens}, temperature={temperature}")
        
        # Get the prompt from messages
        prompt = messages[-1].get("content", "") if messages else ""

        # Phase 4: Vision model routing when images are present or intake recommends it
        use_vision = bool(images) or (intake_result is not None and intake_result.recommended_model == "vision")
        if use_vision:
            vision_model, vision_endpoint = get_vision_model()
            if vision_model:
                logger.info(f"Agent stream using vision model: {vision_model}")
                model = vision_model
                endpoint = vision_endpoint
                provider = "ollama"
                # Add images to the last user message
                if images:
                    for msg in messages:
                        if msg.get("role") == "user":
                            msg["images"] = images
                            break

        # Route based on complexity (skipped if vision model already selected)
        if not use_vision or not vision_model:
            model = get_configured_model()
            if not model:
                raise HTTPException(400, "No model configured — choose one in Settings → AI Models (models.yml)")
            endpoint = get_ollama_endpoint()
            provider = "ollama"
        
        specialist_model, specialist_endpoint, specialist_provider = get_specialist_model()
        if specialist_model:
            if intake_result is not None:
                use_specialist = intake_result.recommended_model == "specialist"
                logger.info(f"Agent stream using intake routing: {intake_result.recommended_model}")
            else:
                complexity_score = score_query_complexity(prompt)
                use_specialist = complexity_score >= 0.5
                logger.info(f"Agent stream using legacy routing (complexity: {complexity_score:.2f})")

            if use_specialist:
                model = specialist_model
                endpoint = specialist_endpoint
                provider = specialist_provider or "ollama"
        
        # State for filtering <think> blocks
        in_think_block = False
        buffer = ""
        
        try:
            timeout = aiohttp.ClientTimeout(total=600)  # 10 minute timeout
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if provider == "openai":
                    url = f"{endpoint}/v1/chat/completions"
                    payload = {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                else:
                    url = f"{endpoint}/api/chat"
                    payload = {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "options": {"num_predict": max_tokens, "temperature": temperature}
                    }
                
                logger.info(f"Streaming from {url} model={model}")
                
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"LLM API error: {resp.status} - {error_text}")
                        yield f"Error: API returned {resp.status}"
                        return
                    
                    async for line in resp.content:
                        if not line:
                            continue
                        
                        line_text = line.decode('utf-8').strip()
                        if not line_text:
                            continue
                        
                        # Parse SSE or JSON response
                        content = ""
                        if provider == "openai":
                            # OpenAI SSE format: data: {...}
                            if line_text.startswith("data: "):
                                data_str = line_text[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    import json
                                    data = json.loads(data_str)
                                    delta = data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                except:
                                    continue
                        else:
                            # Ollama JSON format
                            try:
                                import json
                                data = json.loads(line_text)
                                content = data.get("message", {}).get("content", "")
                                if data.get("done"):
                                    break
                            except:
                                continue
                        
                        if not content:
                            continue
                        
                        # DEBUG: Log all chunks to trace newlines
                        logger.debug(f"LLM raw chunk: {repr(content)}")
                        
                        # Filter <think> blocks in real-time
                        buffer += content
                        
                        # Check for think block boundaries
                        while True:
                            if not in_think_block:
                                # Look for <think> start
                                think_start = buffer.find("<think>")
                                if think_start != -1:
                                    # Yield content before <think>
                                    if think_start > 0:
                                        yield buffer[:think_start]
                                    buffer = buffer[think_start + 7:]  # Skip <think>
                                    in_think_block = True
                                else:
                                    # No <think> found - yield safe content
                                    # Keep last 7 chars in case "<think>" spans chunks
                                    if len(buffer) > 7:
                                        to_yield = buffer[:-7]
                                        logger.debug(f"Yielding chunk: {repr(to_yield)}")
                                        yield to_yield
                                        buffer = buffer[-7:]
                                    break
                            else:
                                # Inside think block - look for </think>
                                think_end = buffer.find("</think>")
                                if think_end != -1:
                                    buffer = buffer[think_end + 8:]  # Skip </think>
                                    in_think_block = False
                                else:
                                    # Still in think block - discard and keep searching
                                    if len(buffer) > 8:
                                        buffer = buffer[-8:]  # Keep last 8 for </think>
                                    break
                        
                # Yield any remaining buffer (if not in think block)
                if buffer and not in_think_block:
                    # Final check for incomplete <think> tag
                    if "<think" not in buffer:
                        yield buffer
                
        except asyncio.TimeoutError:
            logger.error("LLM streaming timed out")
            yield "\n\n[Response timed out]"
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            yield f"\n\n[Error: {e}]"


class LLMResponse:
    """Simple response wrapper."""
    def __init__(self, content="", tool_calls=None, plan=None):
        self.content = content
        self.tool_calls = tool_calls
        self.plan = plan


class _ToolCallFunction:
    """The ``.function`` half of a tool call (name + decoded arguments)."""
    __slots__ = ("name", "arguments")

    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments


class AdaptedToolCall:
    """A tool call in the shape the state machine reads.

    PLANNING accesses ``tool_call.function.name`` / ``.function.arguments``
    (the OpenAI SDK object shape), so the flat dicts the model client
    normalises to are wrapped rather than passed through.
    """
    __slots__ = ("id", "function")

    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = _ToolCallFunction(name, arguments)


def _as_tool_calls(raw_calls):
    """Wrap normalised ``{id, name, arguments}`` dicts as AdaptedToolCall.

    Returns None (not []) when there are none: PLANNING tests truthiness, and
    None keeps "no tool calls" distinguishable from "tools were never asked
    for" in logs.
    """
    if not raw_calls:
        return None
    return [
        AdaptedToolCall(c.get("id") or f"call_{i}", c["name"], c.get("arguments") or {})
        for i, c in enumerate(raw_calls)
        if c.get("name")
    ] or None


class MockLLMClient:
    """Mock LLM client for testing."""
    
    async def chat(self, messages, tools=None):
        return LLMResponse(content="I'm a mock response for testing.")
    
    async def stream(self, messages):
        yield "I'm a mock response for testing."


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

if FASTAPI_AVAILABLE:
    
    @router.post("/message")
    async def send_message(request: SendMessageRequest, req: Request):
        """
        Send message to agent with SSE streaming response.
        
        Returns Server-Sent Events with state changes, tool executions, and response chunks.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent initialization failed: {e}")
        
        session_id = request.session_id
        
        # Handle concurrent requests: if session exists and not IDLE, force reset
        from ...agents.states import AgentState
        if session_id and session_id in agent.active_sessions:
            if agent.current_state != AgentState.IDLE:
                logger.warning(f"Session {session_id} still active (state={agent.current_state}), forcing reset")
                # Mark as cancelled
                agent.cancelled[session_id] = True
                # Force state to IDLE
                agent.current_state = AgentState.IDLE
                # Brief wait for any in-flight processing
                await asyncio.sleep(0.05)
                # Clear cancellation flag for new request
                agent.cancelled[session_id] = False
        
        # Set performance tweaks from request (from frontend Settings > AI > Performance Tweaks)
        if hasattr(agent.llm, 'max_tokens'):
            agent.llm.max_tokens = request.max_tokens or 8192
            agent.llm.temperature = request.temperature or 0.7
            logger.info(f"Set LLM tweaks: max_tokens={agent.llm.max_tokens}, temperature={agent.llm.temperature}")
        
        async def event_stream():
            """Generate SSE events from agent processing with heartbeat."""
            from ...agents.events import StreamEvent
            import time
            
            last_event_time = time.time()
            heartbeat_interval = 15  # Send heartbeat every 15 seconds
            
            try:
                # aclosing, not a bare `async for`: this loop abandons the
                # generator on the cancel path below (and Starlette drops it
                # when the client disconnects), and process() holds the
                # agent's turn lock across every yield. Closing it explicitly
                # runs its finally — releasing the lock and settling the
                # machine — instead of leaving that to the event loop's
                # async-generator finalizer.
                async with aclosing(agent.process(
                    query=request.message,
                    session_id=session_id,
                    images=request.images,
                )) as stream:
                    async for event in stream:
                        # Check if cancelled mid-stream
                        if session_id and agent.cancelled.get(session_id):
                            yield StreamEvent.cancelled(session_id).to_sse()
                            return

                        # Yield the event
                        yield event.to_sse()
                        last_event_time = time.time()

                        # Check if we need to send heartbeats during long gaps
                        # (This is mainly for between-state gaps, not during streaming)

            except Exception as e:
                logger.error(f"Agent processing error: {e}")
                yield StreamEvent.error(
                    session_id or "unknown",
                    str(e),
                    recoverable=False
                ).to_sse()
            finally:
                # Ensure we signal completion
                logger.info(f"Event stream completed for session {session_id}")
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            }
        )
    
    @router.post("/confirm/{session_id}")
    async def confirm_action(
        session_id: str,
        request: ConfirmActionRequest,
        req: Request
    ):
        """
        Confirm or reject a high-risk action.
        
        Returns SSE stream of continued processing.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent not available: {e}")
        
        if session_id not in agent.active_sessions:
            raise HTTPException(404, "Session not found")
        
        async def event_stream():
            try:
                # See send_message: confirm_action also holds the turn lock
                # across its yields, so the generator is closed explicitly.
                async with aclosing(agent.confirm_action(
                    session_id,
                    request.action_id,
                    request.confirmed
                )) as stream:
                    async for event in stream:
                        yield event.to_sse()
            except Exception as e:
                logger.error(f"Confirmation error: {e}")
                from ...agents.events import StreamEvent
                yield StreamEvent.error(session_id, str(e)).to_sse()
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream"
        )
    
    @router.get("/state/{session_id}")
    async def get_state(session_id: str, req: Request) -> AgentStateResponse:
        """Get current state of an agent session."""
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent not available: {e}")
        
        if session_id not in agent.active_sessions:
            raise HTTPException(404, "Session not found")
        
        ctx = agent.active_sessions[session_id]
        
        return AgentStateResponse(
            session_id=session_id,
            state=agent.current_state.value,
            plan=[p.to_dict() for p in ctx.plan],
            current_step=ctx.current_step,
            loop_count=ctx.loop_count,
            confidence=ctx.confidence,
            crag_action=ctx.crag_action.value
        )
    
    @router.post("/cancel/{session_id}")
    async def cancel_session(session_id: str, req: Request):
        """Cancel an ongoing agent session."""
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent not available: {e}")
        
        if agent.cancel_session(session_id):
            return {"cancelled": True, "session_id": session_id}
        
        raise HTTPException(404, "Session not found")
    
    @router.get("/health")
    async def health():
        """Health check for agent service."""
        try:
            agent = get_agent()
            return {
                "status": "healthy",
                "active_sessions": len(agent.active_sessions),
                "current_state": agent.current_state.value
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    @router.post("/intake")
    def run_intake(request: IntakeRequest):
        """Run the intake pipeline on a message and return routing classification.

        Read-only: classifies the message (guide / specialist / vision) without
        executing the agent. Used by the boot-gate smoke to verify intake routing
        deterministically. Sync handler so the (potentially blocking) complexity
        LLM call runs off the event loop in FastAPI's threadpool.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent initialization failed: {e}")

        pipeline = agent.intake_pipeline
        if pipeline is None:
            raise HTTPException(
                503,
                "Intake pipeline not available (configured without Phase 3 intake)",
            )

        result = pipeline.analyze(request.message)
        specialist_enabled = bool(
            _load_model_config().get("specialist", {}).get("enabled", False)
        )
        return {
            "recommended_model": result.recommended_model,
            "complexity_score": result.complexity_score,
            "complexity_level": result.complexity_level,
            "intent": result.intent,
            "is_greeting": result.is_greeting,
            "is_troubleshooting": result.is_troubleshooting,
            "specialist_enabled": specialist_enabled,
        }

    @router.get("/sessions")
    async def list_sessions():
        """List active agent sessions."""
        try:
            agent = get_agent()
            return {
                "sessions": [
                    {
                        "session_id": sid,
                        "query": ctx.user_query[:100],
                        "state": ctx.state_history[-1] if ctx.state_history else "idle",
                        "loop_count": ctx.loop_count,
                        "elapsed_ms": ctx.elapsed_ms()
                    }
                    for sid, ctx in agent.active_sessions.items()
                ]
            }
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.get("/metrics")
    async def get_metrics():
        """Get agent metrics and statistics."""
        try:
            from ...agents import get_metrics_collector
            metrics = get_metrics_collector()
            return metrics.get_summary()
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.get("/metrics/sessions")
    async def get_recent_sessions(limit: int = 10):
        """Get recent completed sessions."""
        try:
            from ...agents import get_metrics_collector
            metrics = get_metrics_collector()
            return {"sessions": metrics.get_recent_sessions(limit)}
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.get("/conversations")
    async def list_conversations(user_id: str = None, limit: int = 50):
        """List conversations."""
        try:
            from ...agents.conversation import get_conversation_store
            store = get_conversation_store()
            return {"conversations": store.list_conversations(user_id, limit)}
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str):
        """Get a specific conversation."""
        try:
            from ...agents.conversation import get_conversation_store
            store = get_conversation_store()
            conv = store.get(conversation_id)
            if conv is None:
                raise HTTPException(404, "Conversation not found")
            return conv.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str):
        """Delete a conversation."""
        try:
            from ...agents.conversation import get_conversation_store
            store = get_conversation_store()
            if store.delete(conversation_id):
                return {"deleted": True}
            raise HTTPException(404, "Conversation not found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
    
    # -------------------------------------------------------------------------
    # Diff Apply/Reject Endpoints (Cascade-style)
    # -------------------------------------------------------------------------
    
    @router.post("/diff/{session_id}/{diff_id}/apply")
    async def apply_diff(session_id: str, diff_id: str):
        """
        Apply a proposed file change.
        
        Writes the proposed content to disk and emits diff_applied event.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent not available: {e}")
        
        if session_id not in agent.active_sessions:
            raise HTTPException(404, "Session not found")
        
        ctx = agent.active_sessions[session_id]
        
        # Find the diff proposal in pending_diffs
        if not hasattr(ctx, 'pending_diffs') or diff_id not in ctx.pending_diffs:
            raise HTTPException(404, "Diff not found")
        
        diff = ctx.pending_diffs[diff_id]
        
        try:
            # Write file to disk
            import os
            file_path = diff.get('file_path')
            new_content = diff.get('new_content')
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w') as f:
                f.write(new_content)
            
            # Mark as applied
            diff['status'] = 'applied'
            
            logger.info(f"Applied diff {diff_id} to {file_path}")
            return {"applied": True, "diff_id": diff_id, "file_path": file_path}
            
        except Exception as e:
            logger.error(f"Failed to apply diff: {e}")
            raise HTTPException(500, f"Failed to apply diff: {e}")
    
    @router.post("/diff/{session_id}/{diff_id}/reject")
    async def reject_diff(session_id: str, diff_id: str):
        """
        Reject a proposed file change.
        
        Marks the diff as rejected without writing to disk.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent not available: {e}")
        
        if session_id not in agent.active_sessions:
            raise HTTPException(404, "Session not found")
        
        ctx = agent.active_sessions[session_id]
        
        # Find the diff proposal
        if not hasattr(ctx, 'pending_diffs') or diff_id not in ctx.pending_diffs:
            raise HTTPException(404, "Diff not found")
        
        # Mark as rejected
        ctx.pending_diffs[diff_id]['status'] = 'rejected'
        
        logger.info(f"Rejected diff {diff_id}")
        return {"rejected": True, "diff_id": diff_id}
