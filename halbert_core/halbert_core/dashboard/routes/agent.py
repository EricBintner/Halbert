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
import uuid
from contextlib import aclosing
from typing import Any, Callable, Dict, List, NamedTuple, Optional

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
    """Request to send a message to the agent.

    There is deliberately no client-chosen conversation id. The server picks
    the thread (Plan A, spec §4): a session id names one turn, not a
    conversation, and the read-only thread id the UI needs comes back on the
    ``turn_persisted`` event and from ``GET /thread/current``. A field the
    client could set and nothing could read would be a live-looking parameter
    that silently does nothing.
    """
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID (auto-generated if not provided)")
    # Phase 4: Vision/image support (ported from chat.py)
    images: Optional[List[str]] = Field(None, description="Base64-encoded images for vision model")
    # Performance tweaks - sent from frontend Settings > AI > Performance Tweaks
    # Bounded (spec §7 follow-up): num_ctx_for_model's per-model cache is a
    # high-water mark, so an unbounded value here would let one request pin the
    # process-global num_ctx at the ceiling for that model — not forever any
    # more (the mark is released once nothing has needed more than half the
    # window for _NUM_CTX_RELEASE_SECONDS), but for every turn in between,
    # which is the whole of an ordinary session. The bound is still the right
    # place to refuse it: releasing late is a recovery, not a defence. 32768
    # matches both the cache's own default ceiling and the frontend's actual
    # maximum Performance Tweaks option (Settings.tsx), so this rejects only
    # the pathological/malicious case, not any value the UI already offers.
    max_tokens: Optional[int] = Field(8192, ge=1, le=32768, description="Max tokens for LLM response")
    temperature: Optional[float] = Field(0.7, description="LLM temperature (0.0-1.0)")
    # In-chat model picker: the pill and the /model command send these.
    model: Optional[str] = Field(None, description="Exact model pinned for this turn; bypasses the complexity router")
    tier: Optional[str] = Field(None, description="'guide' | 'specialist' | 'vision' | 'auto'")
    endpoint_id: Optional[str] = Field(None, description="Saved-endpoint id the pinned model came from; removes ambiguity when the same model name exists on two endpoints")
    scope: Optional[str] = Field(None, description="Explicit SourcePrep scope id for retrieval this turn (e.g. 'host'). Used when no active skill provides a scope.")


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
        from ...context import create_agent_context_assembler
        from ...context.adapters import SourcePrepAdapter
        from ...prompts import AgentPromptBuilder, PromptBuilder, ContextInjector

        # Initialize components
        safety = ToolSafetyFramework()
        # Wrap safety in RoleGate so speaker_role from voice turns can
        # tighten (never loosen) tool access. Text/chat turns default to
        # 'admin' (already authenticated via dashboard session).
        from ...tools.role_gate import RoleGate
        tool_executor = ToolExecutor(safety=safety, role_gate=RoleGate(safety))
        tool_executor.register_system_tools()

        # Conditional vision tool registration — only register capture
        # tools when the user has explicitly enabled screen capture or
        # webcam in vision_config.yml. Prevents the LLM from being
        # offered capture tools when the user hasn't opted in.
        from ...vision.config import is_screen_capture_enabled, is_webcam_enabled
        if is_screen_capture_enabled() or is_webcam_enabled():
            tool_executor.register_vision_tools()

        # Create agent context assembler (R9: no ChromaDB memory on agent path)
        context_assembler = create_agent_context_assembler()

        # SEARCHING state retrieval: SourcePrep (RAGServiceAdapter is
        # deprecated on the chat path).
        # S2: home variants run without SourcePrep — the HA agent answers
        # from live HA state and conversational context. rag_service stays
        # None; the SEARCHING state guards every rag call with
        # `if self.rag:`, so it simply gathers from the remaining sources.
        rag_service = None
        if not _is_home_variant():
            rag_service = SourcePrepAdapter()
        # R9: ChromaDB-backed memory fenced off the agent path.
        # memory_service is deliberately None — recall is Halbert-owned (receipts/FTS5).
        memory_service = None

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
            being_cfg = None
            voice = "first_person"

        prompt_builder = AgentPromptBuilder(
            base_builder=prompt_builder,
            context_injector=context_injector,
            voice=voice,
            being_cfg=being_cfg,
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
        try:
            from ...integrations.home_assistant.ha_tool import register_ha_tools
            register_ha_tools(tool_executor)
        except Exception as e:
            logger.warning(f"Could not register HA tools (non-fatal): {e}")

        # Frigate NVR tools — only registers if Frigate is configured
        try:
            from ...integrations.frigate.frigate_tools import register_frigate_tools
            register_frigate_tools(tool_executor)
        except Exception as e:
            logger.warning(f"Could not register Frigate tools (non-fatal): {e}")
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
    """Whole models.yml (post-migration) for the intake pipeline — see model.llm_config."""
    try:
        from ...model import llm_config as llm_store
        return llm_store.load_file()
    except Exception as e:
        logger.warning(f"Could not load model config: {e}")
        return {}


def _make_llm_caller():
    """Create a callable for ComplexityRouter that wraps call_llm_chat.

    The returned callable has signature:
        caller(endpoint, model, messages, options) -> dict
    """
    from ...model.client import call_llm_chat, provider_for

    def caller(endpoint, model, messages, options):
        # The router knows only a URL. Hardcoding "ollama" here posted every
        # cloud endpoint to {url}/api/chat.
        return call_llm_chat(
            endpoint=endpoint,
            model=model,
            messages=messages,
            provider=provider_for(endpoint),
            stream=False,
            timeout=30,
            options=options,
        )

    return caller


_NO_MODEL_MSG = "No model configured — choose one in Settings → AI Models (models.yml)"


def _attach_images(messages: List[Dict[str, Any]], images: Optional[List[str]]) -> None:
    """Hang this turn's images on the last user message, in place."""
    if not images:
        return
    for msg in reversed(messages):
        if msg.get("role") == "user":
            msg["images"] = images
            return


def _thread_manager():
    """The process-wide ThreadManager, or None when the store is unavailable.

    Module-level so tests can monkeypatch it; every thread endpoint degrades
    to an empty answer when this returns None (spec §12).
    """
    try:
        from ...agents.threads import get_thread_manager
        return get_thread_manager()
    except Exception as e:
        logger.warning(f"Thread manager unavailable (non-fatal): {e}")
        return None


def _thread_summary(thread: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{thread_id, title, status} for the timeline's current_thread."""
    if not thread:
        return None
    return {
        "thread_id": thread.get("id") or thread.get("thread_id"),
        "title": thread.get("title") or "",
        "status": thread.get("status") or "open",
    }


def _active_ctx(session_id: str):
    """The live StateContext for ``session_id``, without building the agent."""
    if _agent_instance is None:
        return None
    return _agent_instance.active_sessions.get(session_id)


def _find_stored_diff(tm, diff_id: str):
    """Locate a persisted diff proposal by id (spec §8).

    Returns ``(message_id, proposals, index)`` where ``proposals`` is the
    assistant row's full diff list, or None. Scans the newest 200 turns;
    older diffs are not actionable from the UI.
    """
    if tm is None:
        return None
    try:
        turns = tm.store.list_turns(limit=200)
    except Exception as e:
        logger.warning(f"Diff lookup failed (non-fatal): {e}")
        return None
    for turn in reversed(turns):
        proposals = list(turn.get("diff_proposals") or [])
        for index, proposal in enumerate(proposals):
            if isinstance(proposal, dict) and proposal.get("diff_id") == diff_id:
                message_id = (turn.get("assistant") or {}).get("message_id")
                return None if message_id is None else (message_id, proposals, index)
    return None


class TurnModel(NamedTuple):
    """The concrete model chosen for one turn, plus why."""
    model: str
    endpoint: str
    provider: str
    tier: str            # "guide" | "specialist" | "vision"
    pinned: bool         # user pinned it; the complexity router was bypassed
    escalated: bool      # the router chose specialist on its own
    reason: str          # human-readable, for the handoff banner and logs


def _endpoint_is_local(provider: str, endpoint: str) -> bool:
    """Locality verdict for the secure gate.

    The endpoint URL decides: a provider named "ollama" can still point at a
    remote host, so provider membership in LOCAL_GPU_PROVIDERS is not proof.
    On-device providers (MLX, Apple Foundation) have no network egress by
    construction and pass without a URL check.
    """
    from ...model.llm_config import _is_local_url
    if (provider or "") in ("mlx", "apple-foundation"):
        return True
    return _is_local_url(endpoint or "")


def _is_home_variant() -> bool:
    """True when the instance variant is home/home-light.

    secure_model is a sysadmin-instance slot (see
    ``integrations/cognition_wiring.is_home_variant``): home automation
    variants never configure it, so the dedicated secure branch is skipped
    for them and the local-guide / fail-closed chain decides instead (S1).
    HA variants also run without SourcePrep retrieval, so the
    SEARCHING-state rag_service stays None for them (S2).
    """
    try:
        from ...integrations.cognition_wiring import is_home_variant
        return is_home_variant()
    except Exception:
        return False


class _SecureContentBlocked(Exception):
    """A secure turn found no local model to answer with. Raised rather than
    routed: silently sending secrets to a cloud endpoint is the failure this
    exception exists to prevent."""


def _resolve_turn_model(
    prompt: str,
    intake_result=None,
    images=None,
    model_override: Optional[str] = None,
    tier_override: Optional[str] = None,
    endpoint_id: Optional[str] = None,
    secure: bool = False,
) -> TurnModel:
    """Pick the model for this turn.

    Precedence: an explicit model pin beats a tier pin, which beats automatic
    routing. A pin bypasses the complexity router entirely — that is the whole
    point of Locked Mode: a user who pins a local model must never discover
    afterwards that a cloud specialist answered and billed them.

    When ``secure=True`` the turn carries secrets (the context-assembly
    backstop flagged it), and the boundary beats everything, pins included:

    1. The dedicated ``secure_model`` slot answers when configured — it is
       guaranteed local-only by ``llm_config.normalise``. Home automation
       variants (home/home-light) skip this branch: secure_model is a
       sysadmin-instance slot they never configure, so resolution falls
       straight to the chain below.
    2. Otherwise the normally-resolved model answers, but only if its
       endpoint is local (loopback URL or an on-device provider).
    3. Otherwise the guide answers if the guide is local.
    4. Otherwise the turn fails closed with ``_SecureContentBlocked``.

    A false positive costs a local-model answer; a false negative ships a
    secret to a cloud vendor. Resolution is done per call from models.yml
    rather than cached on the adapter, because one adapter instance is shared
    by every concurrent request.
    """
    from ...model.client import (
        get_configured_model, get_ollama_endpoint, get_specialist_model,
        get_vision_model, provider_for, resolve_endpoint_by_id,
        score_query_complexity,
    )

    guide_model = get_configured_model()
    guide_endpoint = get_ollama_endpoint()
    guide_provider = provider_for(guide_endpoint)

    # ── 0. Persona model override (shadows the guide model) ─────────────
    # When BeingConfig has a model set, it replaces the guide model for all
    # turns. Per-turn pins and tier overrides still take precedence (checked
    # below) — the persona model just changes what "guide" means.
    try:
        from ...config.being_config import load_being_config
        being_cfg = load_being_config()
        if being_cfg.model:
            persona_endpoint = guide_endpoint
            persona_provider = guide_provider
            if being_cfg.model_endpoint_id:
                resolved = resolve_endpoint_by_id(being_cfg.model_endpoint_id)
                if resolved:
                    persona_endpoint, persona_provider, _ = resolved
            guide_model = being_cfg.model
            guide_endpoint = persona_endpoint
            guide_provider = persona_provider
    except Exception as e:
        logger.debug(f"Persona model override not applied: {e}")

    # ── 0.5. Secure gate ────────────────────────────────────────────────
    # The trust boundary beats pins and routing. Order: dedicated secure
    # slot, then the normally-resolved model if local, then a local guide,
    # then fail closed. The dedicated slot is skipped for home automation
    # variants: secure_model is a sysadmin-instance slot they never
    # configure (an HA variant's LLM reaches the house through tool calls
    # that abstract credentials away), so the gate below enforces the same
    # local-or-fail-closed boundary on the remaining chain.
    if secure and not _is_home_variant():
        from ...model.client import get_secure_model
        sec_model, sec_endpoint, sec_provider = get_secure_model()
        if sec_model:
            return TurnModel(
                sec_model, sec_endpoint, sec_provider or "ollama",
                "guide", False, False,
                "Secure content — dedicated local secure model",
            )

    def gate(turn: "TurnModel") -> "TurnModel":
        """Force a secure turn onto a local endpoint or fail closed."""
        if not secure or _endpoint_is_local(turn.provider, turn.endpoint):
            return turn
        if guide_model and _endpoint_is_local(guide_provider, guide_endpoint):
            logger.info(
                "Secure content: %s is cloud-bound (%s @ %s) — local guide answers",
                turn.model, turn.provider, turn.endpoint,
            )
            return TurnModel(
                guide_model, guide_endpoint, guide_provider, "guide",
                False, False,
                f"Secure content — {turn.model} is cloud-bound; answered locally",
            )
        raise _SecureContentBlocked(
            "This turn contains sensitive content (secrets or credentials) and "
            "no local model is configured to answer it. Configure a local guide "
            "or secure model in Settings → AI Models."
        )

    # ── 1. Explicit model pin ────────────────────────────────────────────
    if model_override:
        # An id from the picker is exact; without one, match the pinned name
        # against a configured slot, then fall back to the guide endpoint —
        # which is right for the common case of another model on the same
        # local runtime.
        resolved = resolve_endpoint_by_id(endpoint_id) if endpoint_id else None
        if resolved:
            url, provider, _ = resolved
        else:
            spec_model, spec_endpoint, spec_provider = get_specialist_model()
            vis_model, vis_endpoint, vis_provider = get_vision_model()
            if spec_model == model_override:
                url, provider = spec_endpoint, spec_provider or "ollama"
            elif vis_model == model_override:
                url, provider = vis_endpoint, vis_provider or "ollama"
            else:
                url, provider = guide_endpoint, guide_provider
        return gate(TurnModel(
            model=model_override, endpoint=url, provider=provider,
            tier="guide", pinned=True, escalated=False,
            reason=f"Pinned to {model_override}",
        ))

    # ── 2. Tier pin ──────────────────────────────────────────────────────
    if tier_override in ("guide", "specialist", "vision"):
        if tier_override == "specialist":
            model, url, provider = get_specialist_model()
            if model:
                return gate(TurnModel(model, url, provider or "ollama", "specialist",
                                      True, False, "Pinned to the specialist tier"))
            logger.info("Specialist tier pinned but not configured; using guide")
        elif tier_override == "vision":
            model, url, provider = get_vision_model()
            if model:
                return gate(TurnModel(model, url, provider or "ollama", "vision",
                                      True, False, "Pinned to the vision tier"))
            logger.info("Vision tier pinned but not configured; using guide")
        if not guide_model:
            raise HTTPException(400, _NO_MODEL_MSG)
        return gate(TurnModel(guide_model, guide_endpoint, guide_provider, "guide",
                              True, False, "Pinned to the guide tier"))

    # ── 3. Automatic routing (unchanged behaviour) ───────────────────────
    if images or (intake_result is not None
                  and intake_result.recommended_model == "vision"):
        model, url, provider = get_vision_model()
        if model:
            return gate(TurnModel(model, url, provider or "ollama", "vision",
                                  False, False, "Image attached"))

    if not guide_model:
        raise HTTPException(400, _NO_MODEL_MSG)

    spec_model, spec_endpoint, spec_provider = get_specialist_model()
    if spec_model:
        if intake_result is not None:
            use_specialist = intake_result.recommended_model == "specialist"
            reason = f"Intake routing: {intake_result.recommended_model}"
        else:
            score = score_query_complexity(prompt)
            use_specialist = score >= 0.5
            reason = f"Complexity score {score:.2f} (threshold 0.50)"
        if use_specialist:
            return gate(TurnModel(spec_model, spec_endpoint, spec_provider or "ollama",
                                  "specialist", False, True, reason))

    return gate(TurnModel(guide_model, guide_endpoint, guide_provider, "guide",
                          False, False, "Routine query"))


def _report_model(
    callback: Optional[Callable[[Dict[str, Any]], None]],
    turn: TurnModel,
    fallback_from: Optional[str] = None,
) -> None:
    """Hand the resolved turn model back to the caller, if it asked.

    A per-call callback rather than a return value because ``stream()`` is an
    async generator whose return value the ``async for`` in RESPONDING never
    sees, and rather than an attribute because one adapter serves every
    concurrent request. A caller's bookkeeping must never cost the user their
    answer, so a raising callback is swallowed.
    """
    if callback is None:
        return
    payload = {
        "model": turn.model,
        "endpoint": turn.endpoint,
        "provider": turn.provider,
        "tier": turn.tier,
        "pinned": turn.pinned,
        "escalated": turn.escalated,
        "reason": turn.reason,
    }
    if fallback_from and fallback_from != turn.model:
        payload["fallback_from"] = fallback_from
    try:
        callback(payload)
    except Exception as e:
        logger.warning(f"on_model_selected callback failed: {e}")


class _ModelUnreachable(Exception):
    """The turn's model produced nothing at all — no connection, a refusal, or
    a missing credential — while the turn can still be handed to another one."""


def _fallback_to_guide(turn: TurnModel, requested: str,
                       secure: bool = False) -> Optional[TurnModel]:
    """The guide's turn to answer in place of one that could not be reached.

    ``None`` when the guide is what already failed: asking it again is the loop
    this fallback exists to avoid. Also ``None`` on a secure turn when the
    guide endpoint is not local — a stand-in that ships the secrets the first
    model was chosen to protect is not a fallback, it is a leak.
    """
    from ...model.client import (
        get_configured_model, get_ollama_endpoint, provider_for,
    )

    guide_model = get_configured_model()
    if not guide_model or guide_model == turn.model:
        return None
    guide_endpoint = get_ollama_endpoint()
    guide_provider = provider_for(guide_endpoint)
    if secure and not _endpoint_is_local(guide_provider, guide_endpoint):
        logger.error(
            "Secure turn: %s unreachable and the guide (%s @ %s) is not local — "
            "failing closed rather than answering from a cloud endpoint",
            requested, guide_model, guide_endpoint,
        )
        return None
    # pinned/escalated are cleared: the guide answered because the choice
    # failed, not because anyone chose it, and a banner reading "pinned" over a
    # model the user never picked is worse than no banner at all.
    return turn._replace(
        model=guide_model,
        endpoint=guide_endpoint,
        provider=guide_provider,
        tier="guide",
        pinned=False,
        escalated=False,
        reason=f"{requested} was unreachable; the guide answered",
    )


class LLMClientAdapter:
    """Adapter that uses same routing logic as Chat (guide vs specialist)."""

    def __init__(self):
        """Initialize adapter - calls chat functions directly, no router needed."""
        # Performance tweaks - can be set per-request from frontend settings
        self.max_tokens = 8192
        self.temperature = 0.7

    @property
    def tools_supported(self) -> Optional[bool]:
        """False only when every model this adapter routes to has rejected tool
        schemas this process; None while any of them might still call one
        (spec §7). The state machine passes it to the prompt builder.

        Resolved per read rather than latched on ``self``: one adapter is
        shared by every concurrent request, so anything stored here leaks
        across sessions (E-2), and a model swapped in through Settings starts
        out unknown again instead of inheriting the last one's verdict.

        Deliberately not one flag either. ``chat`` routes between a guide and a
        specialist model, so a specialist that cannot call tools would
        otherwise mute the "call recall_thread / new_thread" instruction for
        every later turn, including the simple ones routed back to a guide
        model that can call them -- the continuity feature would go quietly
        uninstructed for the rest of the process (review: Plan A / A9d).
        """
        try:
            from ...model.client import (
                get_configured_model, get_specialist_model, model_supports_tools,
            )
            candidates = [
                m for m in (get_configured_model(), get_specialist_model()[0]) if m
            ]
        except Exception as e:
            logger.warning(f"Could not resolve the configured models: {e}")
            return None
        if not candidates:
            return None  # nothing configured yet: unknown
        if all(model_supports_tools(m) is False for m in candidates):
            return False
        return None

    def tools_supported_for(
        self,
        model_override: Optional[str] = None,
        tier_override: Optional[str] = None,
        endpoint_id: Optional[str] = None,
    ) -> Optional[bool]:
        """``tools_supported`` narrowed to the model ONE turn will use.

        The property above answers for the configured slots, which is the
        right answer for an unpinned turn and the wrong one for a pinned one:
        a pin bypasses routing entirely (see ``_resolve_turn_model``), so a
        pinned model that rejected tool schemas is muted by nothing — ``all()``
        over the guide and the specialist still says "unknown" and the state
        machine goes on instructing a model that cannot call a tool to call
        one (review: merge seam, P3 x A9d).

        A method rather than more state on ``self``: one adapter is shared by
        every concurrent request, so the pin arrives as an argument and leaves
        with the call. Resolution goes through ``_resolve_turn_model`` so a
        *tier* pin lands on the same model the answering turn will land on,
        fallbacks included, instead of this re-deriving it.
        """
        if not model_override and not tier_override:
            return self.tools_supported
        try:
            from ...model.client import model_supports_tools
            turn = _resolve_turn_model(
                "", None, None, model_override, tier_override, endpoint_id,
            )
        except Exception as e:
            # No model configured, a malformed models.yml: the configured
            # answer is a better guess than a wrong one.
            logger.warning(f"Could not resolve this turn's model for tools: {e}")
            return self.tools_supported
        return model_supports_tools(turn.model)

    async def chat(self, messages, tools=None, intake_result=None, images=None,
                   model_override=None, tier_override=None, endpoint_id=None,
                   on_model_selected=None, routing_prompt=None, secure=False):
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
            model_override: Exact model pinned for this turn; bypasses routing.
            tier_override: "guide" | "specialist" | "vision" for this turn.
            endpoint_id: Saved-endpoint id the pinned model came from.
            on_model_selected: Called once with the model that actually
                produced the content, after any fallback has settled.
            routing_prompt: The text the complexity router should score. The
                caller's question, not the message it ends up inside.
            secure: This turn's assembled context was flagged as containing
                secrets. The turn resolves to a local model only (secure_model
                slot, else a local guide), and fails closed when none exists.

        Every override is a parameter, never instance state: one adapter is
        shared by all concurrent requests, so anything stored on ``self``
        leaks across sessions.

        ``call_llm_chat`` is synchronous — a blocking ``requests`` call under a
        300s timeout — and this is a coroutine, so every one of the three call
        sites below goes through ``asyncio.to_thread``. Called inline it stops
        the event loop for the whole planning call: every other open SSE
        stream, every other request and every heartbeat waits behind one
        model's think time, and a slow or wedged endpoint takes the whole
        dashboard down with it rather than the one turn that asked for it.
        Nothing here needs the loop while the model works, and ``call_llm_chat``
        takes all of its inputs as arguments and serialises GPU access through
        a file lock, so it is safe to run off it. ``_report_model`` stays on
        this side of the await, in the same order as before.
        """
        from ...model.client import call_llm_chat

        # What the router scores. ``messages[-1]`` is the fallback for callers
        # that send a bare question, but it is no longer the question: since
        # D1 the continuity hint is glued to the front of the final user
        # message, and scoring that decided which model answered on ~46 words
        # the user never wrote — "hi" scored 0.00 alone and 0.70 with a hint,
        # over a 0.50 threshold. The route sizes the history budget from the
        # bare message (``_answering_model``), so this is also what keeps the
        # budget and the answering model talking about the same turn.
        prompt = routing_prompt if routing_prompt is not None else (
            messages[-1].get("content", "") if messages else ""
        )
        # Every system message, not only messages[0]: the loop below drops any
        # it does not hoist, so reading one position silently deleted the rest
        # the moment the callers started sending a real multi-turn array.
        system = "\n\n".join(
            m.get("content", "") for m in (messages or [])
            if m.get("role") == "system" and m.get("content")
        )

        turn = _resolve_turn_model(
            prompt, intake_result, images, model_override, tier_override,
            endpoint_id, secure=secure,
        )
        logger.info(
            f"Agent turn model: {turn.model} @ {turn.endpoint} "
            f"(tier={turn.tier}, provider={turn.provider}, "
            f"pinned={turn.pinned}) — {turn.reason}"
        )
        # What the turn asked for first, so a later fallback can say what the
        # user is not getting.
        requested = turn.model

        if turn.tier == "vision":
            llm_messages = []
            if system:
                llm_messages.append({"role": "system", "content": system})
            for msg in messages:
                if msg.get("role") != "system":
                    llm_messages.append(dict(msg))
            # This turn's images belong on this turn's question. Attaching them
            # to every user message re-sends them once per remembered turn;
            # attaching them to the first hangs them on an old one.
            _attach_images(llm_messages, images)
            try:
                result = await asyncio.to_thread(
                    call_llm_chat,
                    endpoint=turn.endpoint,
                    model=turn.model,
                    messages=llm_messages,
                    provider=turn.provider,
                    stream=False,
                    timeout=300,
                    options={"num_predict": 2048, "temperature": 0.7},
                )
                _report_model(on_model_selected, turn)
                return LLMResponse(content=result.get("content", ""))
            except Exception as e:
                logger.error(f"Vision model call failed: {e}, falling back to text")
                # Re-resolve without the vision path so the turn still answers.
                turn = _resolve_turn_model(
                    prompt, intake_result, None, model_override, tier_override,
                    endpoint_id, secure=secure,
                )

        model, endpoint, provider = turn.model, turn.endpoint, turn.provider

        # Build messages for LLM
        llm_messages = []
        if system:
            llm_messages.append({"role": "system", "content": system})
        for msg in messages:
            if msg.get("role") != "system":
                llm_messages.append(msg)
        
        try:
            # Call LLM using shared model client
            result = await asyncio.to_thread(
                call_llm_chat,
                endpoint=endpoint,
                model=model,
                messages=llm_messages,
                provider=provider,
                stream=False,
                timeout=300,
                # PLANNING answers are a tool call or a short plan: 1024 is
                # plenty and keeps num_ctx (and the model reload) small --
                # num_ctx is sized as prompt + 512 + num_predict, so 2048
                # inflates every planning window by a kilotoken (A10).
                options={"num_predict": 1024, "temperature": 0.7},
                tools=tools,
            )
            _report_model(on_model_selected, turn, requested)
            return LLMResponse(
                content=result.get("content", ""),
                tool_calls=_as_tool_calls(result.get("tool_calls")),
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Never strand the turn: if a specialist or a pinned model is
            # unreachable, answer with the guide and let the UI say so.
            # On a secure turn the guide must itself be local — see
            # _fallback_to_guide.
            guide = _fallback_to_guide(turn, requested, secure=secure)
            if guide is None:
                raise
            logger.warning(
                f"Model '{model}' unavailable ({e}); falling back to "
                f"guide model '{guide.model}' for this turn"
            )
            result = await asyncio.to_thread(
                call_llm_chat,
                endpoint=guide.endpoint,
                model=guide.model,
                messages=llm_messages,
                provider=guide.provider,
                stream=False,
                timeout=180,
                # Explicit rather than left to the client default, so the
                # stand-in plans in the same window as the call it replaces.
                options={"num_predict": 1024, "temperature": 0.7},
                tools=tools,
            )
            _report_model(on_model_selected, guide, requested)
            return LLMResponse(
                content=result.get("content", ""),
                tool_calls=_as_tool_calls(result.get("tool_calls")),
            )
    
    async def stream(self, messages, intake_result=None, images=None,
                     model_override=None, tier_override=None, endpoint_id=None,
                     on_model_selected=None, routing_prompt=None, secure=False):
        """Stream response from LLM with true incremental streaming.

        This — not chat() — is the production response path: the state machine
        prefers stream() whenever the client exposes it. Anything the user must
        see honoured (a pinned model, a credential) has to be handled here, not
        only in chat().

        Uses aiohttp for async streaming. Filters out <think> blocks in real-time.
        Uses self.max_tokens and self.temperature from instance (set per-request).

        A model that cannot be reached costs the user that model, never the
        answer: the guide takes the turn instead and ``on_model_selected``
        names what was lost, so the UI can say so. The guide is tried once —
        falling back to a guide that is itself down would loop.

        ``on_model_selected`` is called once, with the model whose bytes the
        user is about to read — a callback rather than a return value because
        an ``async for`` never sees a generator's return.

        ``routing_prompt`` is the text the complexity router scores: the
        caller's question, not the message it ends up inside. See ``chat``.
        """
        # Use instance variables for performance tweaks. The defaults stand
        # in for a turn that set neither (a /confirm resumes without them):
        # the num_ctx arithmetic in _stream_turn cannot take None.
        max_tokens = self.max_tokens or 8192
        temperature = self.temperature if self.temperature is not None else 0.7
        logger.info(f"LLM streaming with max_tokens={max_tokens}, temperature={temperature}")

        # The question the router scores, not the message it travels in — the
        # continuity hint rides the front of that message since D1. See chat().
        prompt = routing_prompt if routing_prompt is not None else (
            messages[-1].get("content", "") if messages else ""
        )

        turn = _resolve_turn_model(
            prompt, intake_result, images, model_override, tier_override,
            endpoint_id, secure=secure,
        )
        logger.info(
            f"Agent stream model: {turn.model} @ {turn.endpoint} "
            f"(tier={turn.tier}, provider={turn.provider}, "
            f"pinned={turn.pinned}) — {turn.reason}"
        )
        # What the turn asked for first, so a fallback can say what the user is
        # not getting.
        requested = turn.model

        if turn.tier == "vision" and images:
            _attach_images(messages, images)

        try:
            async for chunk in self._stream_turn(
                turn, messages, max_tokens, temperature,
                on_model_selected, requested,
            ):
                yield chunk
            return
        except _ModelUnreachable as unreachable:
            guide = _fallback_to_guide(turn, requested, secure=secure)
            if guide is None:
                logger.error(f"Stream failed with no guide to stand in: {unreachable}")
                yield f"\n\n[Error: {unreachable}]"
                return
            logger.warning(
                f"Model '{turn.model}' unavailable ({unreachable}); streaming "
                f"from guide model '{guide.model}' for this turn"
            )

        # Deliberately outside the handler above, so a guide that is also down
        # ends the turn with one notice instead of re-entering the fallback.
        try:
            async for chunk in self._stream_turn(
                guide, messages, max_tokens, temperature,
                on_model_selected, requested,
            ):
                yield chunk
        except _ModelUnreachable as also_unreachable:
            logger.error(f"Guide model unreachable as well: {also_unreachable}")
            yield f"\n\n[Error: {also_unreachable}]"

    async def _stream_turn(self, turn, messages, max_tokens, temperature,
                           on_model_selected, requested):
        """Stream one model's answer, reporting it once the request is good.

        The report waits for the response headers because that is the last
        moment the turn can still change hands: reported earlier it credits a
        model that never answered, reported later the "was unavailable" chip
        arrives over text already on screen. Headers land ahead of the first
        token, so a healthy turn's banner is not held back.

        For the same reason ``_ModelUnreachable`` is raised only from before
        that moment: the caller may put another model behind an unstarted turn,
        while a failure after it is told to the user in-band rather than
        restarted over text they have already read.
        """
        import aiohttp
        from ...model.client import (
            OPENAI_COMPATIBLE_PROVIDERS, _api_url, api_key_for,
            estimate_prompt_tokens, num_ctx_for_model,
        )

        model, endpoint, provider = turn.model, turn.endpoint, turn.provider

        # State for filtering <think> blocks
        in_think_block = False
        buffer = ""
        reported = False

        try:
            # The streaming path builds its own requests rather than going
            # through call_llm_chat, so it needs the same auth and provider
            # coverage — without it a BYOK endpoint authenticates for the
            # planning call and then 401s on the answer the user actually sees.
            api_key = api_key_for(endpoint)
            headers = {}
            if provider in OPENAI_COMPATIBLE_PROVIDERS:
                wire = "openai"
                url = _api_url(endpoint, "/v1/chat/completions")
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
            elif provider == "anthropic":
                wire = "anthropic"
                if not api_key:
                    raise _ModelUnreachable(
                        "no API key configured for this endpoint — add one in "
                        "Settings → AI Models"
                    )
                url = _api_url(endpoint or "https://api.anthropic.com", "/v1/messages")
                system_parts = [
                    m.get("content", "") for m in messages
                    if m.get("role") == "system" and m.get("content")
                ]
                payload = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                    "messages": [
                        {
                            "role": "assistant" if m.get("role") == "assistant" else "user",
                            "content": m.get("content") or "",
                        }
                        for m in messages
                        if m.get("role") != "system" and m.get("content")
                    ],
                }
                if system_parts:
                    payload["system"] = "\n\n".join(system_parts)
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
            else:
                wire = "ollama"
                url = f"{(endpoint or '').rstrip('/')}/api/chat"
                # A10, re-applied here on purpose: stream() builds its own
                # request rather than going through call_llm_chat, and this
                # is the production response path. Without a num_ctx sized
                # from the prompt, Ollama uses its small default window and
                # silently drops the HEAD of the prompt -- which is
                # messages[0], the instructions and the thread receipt.
                prompt_tokens = estimate_prompt_tokens(messages, None)
                # `endpoint` is the daemon this request is about to go to, and
                # it is what lets the model's real architecture window be
                # discovered instead of falling back to the ceiling: without it
                # a cold process streams the answer -- the call the user
                # actually reads -- at 32768 tokens of KV cache for a model
                # whose window may be a quarter of that.
                #
                # `on_event_loop` because this is one. Discovery is ordinary
                # blocking `requests`, and a probe taken here does not merely
                # slow this turn down: it stops the event loop, so every other
                # open SSE stream and every other request in the process stops
                # with it, for up to the probe timeout and longer if DNS hangs
                # (measured on this tree: a 3.01s probe, a 3.06s gap between
                # event-loop heartbeats). So this turn is sized from what is
                # already known -- the picker's listing, the planning call, an
                # earlier turn -- and anything still unknown is discovered on a
                # worker thread, for the turns after this one.
                num_ctx = num_ctx_for_model(
                    model, prompt_tokens, max_tokens,
                    endpoint=endpoint, on_event_loop=True,
                )
                # The reply has to fit what is left of the window after the
                # prompt (spec §7: max_tokens is subordinate to
                # num_ctx - prompt). _do_llm_call has no equivalent step
                # because it is not streaming a bounded answer back.
                num_predict = max(256, min(max_tokens, num_ctx - prompt_tokens - 512))
                if prompt_tokens + 512 > num_ctx:
                    # num_ctx was clamped (model_max, or the 32768 default
                    # ceiling) below what this prompt needs. Ollama truncates
                    # the head of the prompt with nothing logged, so say so.
                    logger.warning(
                        f"Prompt for {model} is ~{prompt_tokens} tokens "
                        f"but num_ctx={num_ctx}; Ollama will truncate "
                        "the head of the prompt."
                    )
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_predict": num_predict,
                        "temperature": temperature,
                        "num_ctx": num_ctx,
                    },
                }

            timeout = aiohttp.ClientTimeout(total=600)  # 10 minute timeout
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.info(
                    f"Streaming from {url} model={model} "
                    f"(wire: {wire}, auth: {'yes' if api_key else 'no'})"
                )

                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"LLM API error: {resp.status} - {error_text}")
                        raise _ModelUnreachable(f"API returned {resp.status}")

                    _report_model(on_model_selected, turn, requested)
                    reported = True

                    async for line in resp.content:
                        if not line:
                            continue
                        
                        line_text = line.decode('utf-8').strip()
                        if not line_text:
                            continue
                        
                        # Parse SSE or JSON response
                        content = ""
                        if wire == "openai":
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
                        elif wire == "anthropic":
                            # Anthropic SSE: named events plus a data: line. The
                            # text lives on content_block_delta.delta.text.
                            if not line_text.startswith("data: "):
                                continue
                            try:
                                import json
                                data = json.loads(line_text[6:])
                            except Exception:
                                continue
                            event_type = data.get("type")
                            if event_type == "content_block_delta":
                                content = (data.get("delta") or {}).get("text", "")
                            elif event_type == "message_stop":
                                break
                            elif event_type == "error":
                                msg = (data.get("error") or {}).get("message", "unknown")
                                logger.error(f"Anthropic stream error: {msg}")
                                yield f"Error: {msg}"
                                return
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
                
        except _ModelUnreachable:
            raise
        except asyncio.TimeoutError:
            logger.error("LLM streaming timed out")
            if not reported:
                raise _ModelUnreachable("the request timed out")
            yield "\n\n[Response timed out]"
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            if not reported:
                raise _ModelUnreachable(str(e) or type(e).__name__) from e
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
    """Mock LLM client for testing.

    Accepts **kwargs so new per-request routing parameters on the real adapter
    do not TypeError here.
    """

    async def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content="I'm a mock response for testing.")

    async def stream(self, messages, **kwargs):
        yield "I'm a mock response for testing."


# -----------------------------------------------------------------------------
# Per-turn model and budget resolution (E-3, merge decision D4)
#
# The route resolves the model that will answer and the tokens the turn may
# spend on remembered ones, and hands both to process(); the state machine
# never reaches back into route or store code to work them out. What is
# remembered, and which hidden thread it belongs to, is the ThreadManager's
# business (Plan A, spec §4) -- there is no conversation store here any more.
# -----------------------------------------------------------------------------


def _answering_model(
    prompt: str,
    model_override: Optional[str] = None,
    tier_override: Optional[str] = None,
    endpoint_id: Optional[str] = None,
    images: Optional[List[str]] = None,
) -> Optional[str]:
    """Name of the model that will answer this turn, resolved for budgeting.

    The picker's pin is not the answer: the frontend omits ``model`` unless the
    user pinned one, so budgeting off the pin sized every ordinary turn's
    history for the empty string — a constant, whatever model models.yml
    actually names. This runs the same resolution the answering path runs, so
    a small local guide gets a small window and a large one gets its own.

    One approximation remains, and it is the cheap half of the trade: intake
    has not run yet (it runs inside ``agent.process``, after the history it
    would size is already loaded), so automatic guide-vs-specialist routing
    falls back to the complexity score rather than intake's verdict. The two
    agree on ordinary turns and both sit in the same tier far more often than
    the empty string did.

    Returns ``None`` when nothing can be resolved (no model configured yet, a
    malformed models.yml), which the caller reads as "use the default": a
    mis-sized history is a bad turn, a 500 here is no turn at all.
    """
    try:
        return _resolve_turn_model(
            prompt,
            images=images,
            model_override=model_override,
            tier_override=tier_override,
            endpoint_id=endpoint_id,
        ).model
    except Exception as e:
        logger.warning(f"Could not resolve the answering model for budgeting: {e}")
        return None


def _history_budget(model_name: Optional[str]) -> int:
    """Tokens this turn may spend on remembered turns.

    Taken from the model tier's own conversation line rather than a constant:
    a small local model with a 32k window cannot afford the history a large one
    can, and a single number would either starve one or overflow the other.
    """
    from ...context.assembler import DEFAULT_CONVERSATION_TOKENS
    try:
        from ...intake import get_context_budget
        return get_context_budget(model_name or "").conversation
    except Exception as e:
        logger.warning(f"Context budget unavailable, using default: {e}")
        return DEFAULT_CONVERSATION_TOKENS


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

if FASTAPI_AVAILABLE:

    @router.post("/message")
    async def send_message(request: SendMessageRequest, req: Request):
        """
        Send message to agent with SSE streaming response.

        A second message during a live turn queues on the state machine's turn
        lock (spec §12). Nothing here takes a lock of its own and nothing here
        resets the machine any more: a route that held the lock and then called
        a ``process()`` that takes it again is a non-reentrant self-deadlock,
        and the machine's own bounded acquire supersedes a stranded turn far
        better than a force-write of the shared state ever did.

        Everything model-owned is resolved before the turn starts -- the pin,
        the model that will answer, the tokens it may spend on history -- and
        handed to ``process()`` as parameters (D4/D5). Which hidden thread the
        turn belongs to is the server's choice, made inside the state machine
        through the ThreadManager (D6); the client does not get to name one.
        """
        try:
            agent = get_agent()
        except Exception as e:
            raise HTTPException(500, f"Agent initialization failed: {e}")

        # A turn needs a stable id to be reported and cancelled under, and the
        # agent generates its own when the client sends none -- which the route
        # would never learn, so an error raised out here would carry an id no
        # client could correlate.
        session_id = request.session_id or str(uuid.uuid4())

        # In-chat model picker for this turn. "auto" means "no pin" -- it is the
        # absence of an override, not a third mode.
        tier_override = request.tier if request.tier in ("guide", "specialist", "vision") else None
        model_override = request.model or None
        if model_override or tier_override:
            logger.info(
                f"Turn override from picker: model={model_override!r} "
                f"tier={tier_override!r} endpoint_id={request.endpoint_id!r}"
            )

        # The budget belongs to the model that will actually answer, resolved
        # through the same path the answering turn takes (D4). Reading it from
        # the picker's pin meant a constant for every unpinned turn, which is
        # every turn by default.
        history_budget = _history_budget(_answering_model(
            request.message,
            model_override=model_override,
            tier_override=tier_override,
            endpoint_id=request.endpoint_id,
            images=request.images,
        ))

        # Plan A: the state machine persists the turn and resolves the hidden
        # thread itself (begin_turn under its lock); the route only hands over
        # the manager. None means "no store": the turn still runs.
        thread_manager = _thread_manager()

        async def event_stream():
            """Generate SSE events from agent processing."""
            from ...agents.events import StreamEvent

            try:
                # aclosing, not a bare `async for`: Starlette drops this
                # generator when the client disconnects, and process() holds
                # the agent's turn lock across every yield. Closing it
                # explicitly runs its finally -- releasing the lock and
                # settling the machine -- instead of leaving that to the event
                # loop's async-generator finalizer.
                async with aclosing(agent.process(
                    query=request.message,
                    session_id=session_id,
                    images=request.images,
                    thread_manager=thread_manager,
                    model_override=model_override,
                    tier_override=tier_override,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    history_budget=history_budget,
                    retrieval_scope=request.scope,
                )) as stream:
                    async for event in stream:
                        yield event.to_sse()
            except Exception as e:
                logger.error(f"Agent processing error: {e}")
                yield StreamEvent.error(session_id, str(e), recoverable=False).to_sse()
            finally:
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

        # A confirmation resumes a turn that is already half-run, so the pin and
        # the budget are read back off its context rather than re-resolved: the
        # request carries neither, and re-resolving could hand the second half
        # of a turn to a different model than answered the first. Which thread
        # it lands in is not the route's business either -- the machine holds
        # the TurnContext and ends the turn through it, so there is no
        # session-to-conversation map here to keep in step.
        ctx = agent.active_sessions[session_id]
        model_override = getattr(ctx, "model_override", None)
        tier_override = getattr(ctx, "tier_override", None)
        history_budget = getattr(ctx, "history_budget", None) or None

        async def event_stream():
            try:
                # See send_message: confirm_action also holds the turn lock
                # across its yields, so the generator is closed explicitly.
                # max_tokens / temperature are deliberately not passed -- a
                # confirmation carries no Performance Tweaks of its own, and
                # the paused turn keeps the ones it started under.
                async with aclosing(agent.confirm_action(
                    session_id,
                    request.action_id,
                    request.confirmed,
                    model_override=model_override,
                    tier_override=tier_override,
                    history_budget=history_budget,
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
            (_load_model_config().get("llm_config") or {})
            .get("specialist_model", {})
            .get("enabled", False)
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
    
    # -------------------------------------------------------------------------
    # Diff Apply/Reject Endpoints (Cascade-style)
    #
    # Live session first, then the store (messages.diff_proposals_json,
    # spec §8): active_sessions is evicted at the end of the turn, so a diff
    # proposed a moment ago is usually only on disk by the time the admin
    # clicks Apply. A turn paused on AWAITING_CONFIRMATION is the one moment
    # when both copies exist at once, so a decision always settles every copy
    # -- see _diff_copies.
    # -------------------------------------------------------------------------

    def _require_pending(diff: Dict[str, Any], diff_id: str) -> None:
        """Refuse a proposal that has already been applied or rejected.

        A stored proposal stays addressable by id for as long as it is on the
        timeline, so without this an old ``new_content`` (a whole-file
        replacement) could be written over a file the admin has edited since
        -- or a rejected change could be applied after the fact. A missing
        status counts as pending: rows written before this column existed.
        """
        status = diff.get("status") or "pending"
        if status != "pending":
            raise HTTPException(400, f"Diff {diff_id} was already {status}")

    def _diff_copies(session_id: str, diff_id: str):
        """Every copy of ``diff_id``, plus the handle that writes the store back.

        Returns ``(copies, stored)``. ``copies`` holds every dict that carries
        this proposal's status -- the live sessions' copies first (the session
        the request named leading, when it holds one), the persisted proposal
        last -- and is empty when the diff is nowhere to be found. ``stored``
        is ``(tm, message_id, proposals)`` for writing the persisted list
        back, or None when the turn is not (yet) on disk.

        The live side scans *every* active session rather than only
        ``session_id``: a diff card rendered from the timeline has no session
        id to send (the persisted turn dicts carry none), so a request can
        name a session that never held the diff while the session that does
        is still paused on AWAITING_CONFIRMATION. Diff ids are unique, so the
        scan is both cheap and unambiguous -- and it is what lets a decision
        settle the copy the request did not route to.
        """
        contexts: List[Any] = []
        if _agent_instance is not None:
            try:
                contexts = list(_agent_instance.active_sessions.values())
            except Exception as e:
                logger.warning(f"Live sessions unavailable (non-fatal): {e}")
        named = _active_ctx(session_id)
        if named is not None:
            contexts = [named] + [ctx for ctx in contexts if ctx is not named]
        copies: List[Dict[str, Any]] = []
        for ctx in contexts:
            pending = getattr(ctx, "pending_diffs", None)
            diff = pending.get(diff_id) if isinstance(pending, dict) else None
            if isinstance(diff, dict):
                copies.append(diff)
        tm = _thread_manager()
        found = _find_stored_diff(tm, diff_id)
        stored = None
        if found is not None:
            message_id, proposals, index = found
            copies.append(proposals[index])
            stored = (tm, message_id, proposals)
        return copies, stored

    def _settle_diff(copies: List[Dict[str, Any]], stored, status: str) -> bool:
        """Record the decision on every copy; False when the store refused it.

        Settling only the copy the request happened to route to leaves the
        other one reading "pending", and ``new_content`` is a whole-file
        replacement: the second decision would then silently discard whatever
        the admin edited in between.
        """
        for diff in copies:
            diff["status"] = status
        if stored is None:
            return True
        tm, message_id, proposals = stored
        try:
            tm.store.update_message(message_id, diff_proposals=proposals)
            return True
        except Exception as e:
            logger.warning(f"Could not persist diff status (non-fatal): {e}")
            return False

    def _apply_target(diff: Dict[str, Any]):
        """The ``(file_path, new_content)`` an apply would write, or a 400."""
        file_path = diff.get("file_path")
        new_content = diff.get("new_content")
        if not file_path or new_content is None:
            raise HTTPException(400, "Diff has no file path or content to apply; use the editor flow")
        return file_path, new_content

    def _write_file(file_path: str, new_content: str, diff_id: str) -> None:
        import os
        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "w") as f:
                f.write(new_content)
        except Exception as e:
            logger.error(f"Failed to apply diff {diff_id} (it stays settled as applied): {e}")
            raise HTTPException(500, f"Failed to apply diff: {e}")
        logger.info(f"Applied diff {diff_id} to {file_path}")

    @router.post("/diff/{session_id}/{diff_id}/apply")
    async def apply_diff(session_id: str, diff_id: str):
        """Apply a proposed file change (live session, else the store)."""
        copies, stored = _diff_copies(session_id, diff_id)
        if not copies:
            raise HTTPException(404, "Diff not found")
        for diff in copies:
            _require_pending(diff, diff_id)
        file_path, new_content = _apply_target(copies[0])
        # Settle before touching disk. A proposal marked applied by a write
        # that then failed costs the admin one re-ask; a write that succeeded
        # while the proposal stayed pending is replayable over their next
        # edit, and takes that edit with it.
        persisted = _settle_diff(copies, stored, "applied")
        _write_file(file_path, new_content, diff_id)
        result: Dict[str, Any] = {"applied": True, "diff_id": diff_id, "file_path": file_path}
        if not persisted:
            # The store still says "pending": tell the caller rather than
            # showing a clean tick over a decision that dies with the process.
            result["status_persisted"] = False
        return result

    @router.post("/diff/{session_id}/{diff_id}/reject")
    async def reject_diff(session_id: str, diff_id: str):
        """Reject a proposed file change without writing to disk."""
        copies, stored = _diff_copies(session_id, diff_id)
        if not copies:
            raise HTTPException(404, "Diff not found")
        for diff in copies:
            _require_pending(diff, diff_id)
        persisted = _settle_diff(copies, stored, "rejected")
        logger.info(f"Rejected diff {diff_id}")
        result: Dict[str, Any] = {"rejected": True, "diff_id": diff_id}
        if not persisted:
            result["status_persisted"] = False
        return result

    # -------------------------------------------------------------------------
    # Timeline and threads (Plan A, spec §11)
    # -------------------------------------------------------------------------

    _EMPTY_TIMELINE: Dict[str, Any] = {"turns": [], "has_more": False, "current_thread": None}

    @router.get("/timeline")
    async def get_timeline(before: Optional[str] = None, around: Optional[str] = None, limit: int = 50):
        """One page of the timeline, newest-last, grouped by turn.

        ``before`` pages backwards from a turn id; ``around`` centres on one
        (a chip click). Degrades to an empty page, never a 500 (spec §12).
        """
        tm = _thread_manager()
        if tm is None:
            return dict(_EMPTY_TIMELINE)
        try:
            page = max(1, min(int(limit), 200))
            if around and not before:
                # ``before`` still wins when both are given, as the store does.
                # ``around`` is already a centred window, so the +1/trim trick
                # below would drop the anchor itself whenever the store tops
                # the window up forwards (an anchor with nothing older than
                # it -- exactly the "jump to the start of an old thread"
                # case). Ask for the page as-is and probe for older turns.
                turns = tm.store.list_turns(around_turn_id=around, limit=page)
                has_more = bool(turns) and bool(
                    tm.store.list_turns(before_turn_id=turns[0]["turn_id"], limit=1)
                )
            else:
                # Newest-last: one extra turn off the old end tells us whether
                # a `before=` fetch would find anything, then it is trimmed.
                turns = tm.store.list_turns(before_turn_id=before or None, limit=page + 1)
                has_more = len(turns) > page
                if has_more:
                    turns = turns[-page:]
            return {"turns": turns, "has_more": has_more, "current_thread": _thread_summary(tm.current())}
        except Exception as e:
            logger.warning(f"Timeline unavailable (non-fatal): {e}")
            return dict(_EMPTY_TIMELINE)

    @router.get("/thread/current")
    async def get_current_thread():
        """The open thread as a dict (plus ``thread_id``), or null."""
        tm = _thread_manager()
        if tm is None:
            return None
        try:
            thread = tm.current()
        except Exception as e:
            logger.warning(f"Current thread unavailable (non-fatal): {e}")
            return None
        if not thread:
            return None
        body = dict(thread)
        body["thread_id"] = thread.get("id") or thread.get("thread_id")
        return body

    @router.delete("/thread/{thread_id}/recall/{recalled_thread_id}")
    async def retract_recall(thread_id: str, recalled_thread_id: str):
        """Mark a pulled-in thread as retracted on ``thread_id`` (spec §6)."""
        tm = _thread_manager()
        if tm is None:
            return {"ok": False}
        try:
            return {"ok": bool(tm.retract_recall(thread_id, recalled_thread_id))}
        except Exception as e:
            logger.warning(f"retract_recall failed (non-fatal): {e}")
            return {"ok": False}

    def _refresh_thread_receipt(tm, thread_id: str) -> None:
        """Regenerate a thread's receipt after a redaction (spec §5)."""
        refresh = getattr(tm, "refresh_receipt", None) or getattr(tm, "_refresh_receipt", None)
        if callable(refresh):
            refresh(thread_id)
            return
        from ...agents.receipt import build_receipt
        thread = tm.store.get_thread(thread_id)
        if thread is None:
            return
        receipt = build_receipt(thread, tm.store.list_messages(thread_id))
        tm.store.upsert_receipt(thread_id, thread.get("title") or "", receipt)

    def _blank_stale_receipt(store, thread_id: str) -> bool:
        """Drop a receipt that could not be regenerated after a redaction."""
        try:
            return bool(store.upsert_receipt(thread_id, "", ""))
        except Exception as e:
            logger.error(f"Blanking the stale receipt for {thread_id} failed: {e}")
            return False

    @router.post("/message/{message_id}/redact")
    async def redact_message(message_id: int):
        """"Forget this" for one row (spec §5): content and blocks become
        "[redacted by admin]", and every derived copy the row left behind goes
        with it -- its FTS index row, the thread title it founded, the
        thread's entity sets -- before the receipt is regenerated from what is
        left. Rows are never deleted.

        404 only ever means "there is no such row". A store that is down
        answers 503 and a redaction that did not land in full answers 500: a
        person who asked to forget something must never be told "nothing to
        forget", or "done", while the words are still readable somewhere
        (A11b review findings 1 and 2).
        """
        from ...agents.conversation_sqlite import RedactionFailed

        tm = _thread_manager()
        store = getattr(tm, "store", None) if tm is not None else None
        if store is None or not getattr(store, "connected", True):
            raise HTTPException(503, "Thread store unavailable")
        try:
            thread_id = store.redact_message(message_id)
        except RedactionFailed as e:
            logger.error(f"Redaction of message {message_id} did not land: {e}")
            raise HTTPException(500, "Redaction failed; the message is unchanged")
        if thread_id is None:
            raise HTTPException(404, "Message not found")
        try:
            _refresh_thread_receipt(tm, thread_id)
        except Exception as e:
            # The row is scrubbed, but `conversations.receipt` / `receipts_fts`
            # still quote it -- and that copy is what recall reads back into
            # later prompts as `retrieved_context`. Blank the stale receipt
            # rather than leave the words standing, and never report the
            # redaction as clean: the next `end_turn` rebuilds the summary.
            logger.error(f"Receipt refresh after redacting {message_id} failed: {e}")
            if not _blank_stale_receipt(store, thread_id):
                raise HTTPException(
                    500, "Message redacted, but its thread receipt still holds the original text"
                )
            return {"ok": True, "thread_id": thread_id, "receipt_refreshed": False}
        return {"ok": True, "thread_id": thread_id}
