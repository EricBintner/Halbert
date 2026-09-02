# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""OpenAI-compatible compute endpoint with MCP redaction boundary.

Implements finding C4 from the federated multi-node review.

C4 — The compute endpoint must apply the same redaction boundary as MCP
-----------------------------------------------------------------------
``/api/compute/v1/chat/completions`` lets a paired satellite send
arbitrary prompts to the Desktop's GPU.  Without redaction on the
response, a compromised satellite can craft a prompt that instructs the
Desktop model to read and return secrets.

Every response from this endpoint passes through ``mcp_response()``
(``halbert_core/mcp/response.py``) — the same redaction boundary used by
the MCP server.  This ensures:
1. Secret values in the model's response are replaced with ``<secret>``.
2. PEM blocks, JWTs, URL-embedded credentials, and routable IPs are
   stripped from the response text.
3. The structural redaction (config-value-pair shape) catches secrets
   even when the model returns structured JSON.

Endpoint shape
--------------
The endpoint is OpenAI-compatible so that the ``PeerProvider``
(``model/providers/peer.py``) can use a standard HTTP client without
custom protocol handling::

    POST /api/compute/v1/chat/completions
    Authorization: Bearer <peer-token>
    Content-Type: application/json

    {
      "model": "qwen2.5:32b",
      "messages": [{"role": "user", "content": "..."}],
      "stream": false,
      "tools": [...]  // optional, filtered by tool_allowlist
    }

Response (non-streaming)::

    {
      "id": "chatcmpl-...",
      "object": "chat.completion",
      "model": "qwen2.5:32b",
      "choices": [{"message": {"role": "assistant", "content": "..."}}],
      "usage": {"prompt_tokens": 42, "completion_tokens": 128, "total_tokens": 170}
    }

The response content is passed through ``mcp_response()`` before
serialization.  This is the egress boundary — the same one MCP uses.

Tool filtering
--------------
If the request includes a ``tools`` array, each tool is checked against
``PEER_ALLOWED_TOOLS``.  Disallowed tools are silently filtered out
(see ``tool_allowlist.filter_tools_for_peer``).  The model never sees
the disallowed tools, so it cannot attempt to call them.

Streaming
---------
TODO(federation-9.4): Streaming responses (``stream: true``) require
redaction on each SSE chunk.  This is harder because a secret might be
split across chunks.  The initial implementation supports non-streaming
only.  Streaming will require a buffering redaction filter that holds
back chunks until it can verify no secret pattern spans the boundary.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..mcp.response import mcp_response
from .peer_middleware import PeerContext, require_peer_auth
from .tool_allowlist import filter_tools_for_peer

logger = logging.getLogger(__name__)

router = APIRouter()

# One spelling of each path, imported by everyone who talks to this endpoint.
# compute_router probed /health, config_wizard probed /health, PeerProvider
# probed /models, and /health existed nowhere — three components disagreeing
# about the address of a route that was not mounted at all (SE-08 / R10-F3).
COMPUTE_API_PREFIX = "/api/compute/v1"
COMPUTE_HEALTH_PATH = f"{COMPUTE_API_PREFIX}/health"
COMPUTE_MODELS_PATH = f"{COMPUTE_API_PREFIX}/models"
COMPUTE_CHAT_PATH = f"{COMPUTE_API_PREFIX}/chat/completions"

# Peers get general-purpose local inference and nothing else. apple-foundation
# is the Mac's own slot and is never offered to a peer; the secure slot exists
# precisely so secret-bearing turns stay on this machine.
PEER_SERVABLE_PROVIDERS = frozenset({"ollama", "vllm", "llamacpp"})
_NEVER_SERVED_TO_PEERS = ("secure_model",)


# ---------------------------------------------------------------------------
# Request / response models (OpenAI-compatible)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request.

    The ``model`` field specifies which model the peer wants to use.
    The Desktop's compute broker maps this to an actual model on its
    GPU (see ``compute_broker.py``).
    """
    model: str = Field(..., description="Model ID (e.g., 'qwen2.5:32b')")
    messages: List[ChatMessage]
    stream: bool = Field(False, description="Stream tokens via SSE (TODO: federation-9.4)")
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="Tool definitions (filtered by allowlist)")
    temperature: float = 0.7
    max_tokens: Optional[int] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    COMPUTE_CHAT_PATH,
    response_model=ChatCompletionResponse,
)
async def peer_compute_chat(
    request: ChatCompletionRequest,
    peer: PeerContext = Depends(require_peer_auth),
) -> ChatCompletionResponse:
    """Handle a peer's inference request.

    This is the core of the federated compute architecture.  A satellite
    Halbert sends a prompt to the Desktop's GPU via this endpoint.

    Security flow:
    1. ``require_peer_auth`` validates the bearer token (C1).
    2. If ``request.tools`` is present, ``filter_tools_for_peer`` strips
       disallowed tools (C4).
    3. The prompt is submitted to the Desktop's local model (via
       ``compute_broker.py`` which manages GPU concurrency).
    4. The model's response passes through ``mcp_response()`` before
       being returned (C4 — the egress redaction boundary).
    5. The redacted response is serialized and sent to the peer.

    The peer never sees:
    - Raw config values (redacted by mcp_response)
    - Secret keys, tokens, passwords (redacted by mcp_response)
    - Disallowed tools (filtered before the model sees them)
    - The Desktop's internal tool call results (only the final text)
    """
    logger.info(
        "Peer compute request from %s (%s): model=%s, messages=%d, tools=%d",
        peer.node_id, peer.node_name, request.model, len(request.messages), len(request.tools or []),
    )

    # Step 1: Filter tools to the peer allowlist (C4)
    filtered_tools = None
    if request.tools:
        # Extract tool names from the OpenAI tool format
        tool_names = [t.get("function", {}).get("name", "") for t in request.tools]
        allowed_names = set(filter_tools_for_peer(tool_names))
        filtered_tools = [t for t in request.tools if t.get("function", {}).get("name", "") in allowed_names]
        if len(filtered_tools) < len(request.tools):
            logger.warning(
                "Filtered %d/%d tools from peer %s (not in allowlist)",
                len(request.tools) - len(filtered_tools), len(request.tools), peer.node_id,
            )

    # Step 2: Submit to the compute broker (H6 — concurrency management)
    # TODO(federation-9.3): Wire to ComputeBroker.submit()
    # The broker queues the request with priority and manages GPU concurrency.
    # For Phase 9.2a (1:1), the broker is effectively pass-through (max_concurrent=1).
    raw_response = await _submit_to_broker(request, filtered_tools, peer)

    # Step 3: Apply the MCP redaction boundary (C4 — the egress choke point)
    # This is the SAME redaction used by the MCP server. It strips:
    # - Secret values in config-value-pair shapes
    # - Secret dict keys
    # - PEM blocks, JWTs, URL-embedded credentials, routable IPs in text
    #
    # Applied to the model's TEXT, not to the whole envelope. The redactor is
    # secret-key-aware and every usage counter is named *_tokens, so running
    # the envelope through it replaced prompt_tokens/completion_tokens/
    # total_tokens with "<secret>" — which then failed integer validation and
    # 500'd the happy path. Counts are integers; they cannot carry a secret.
    redacted_content = mcp_response(raw_response.get("content", "") or "")
    usage = raw_response.get("usage") or {}

    # Step 4: Serialize and return
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=request.model,
        choices=[ChatCompletionChoice(
            message=ChatMessage(role="assistant", content=redacted_content),
            finish_reason=raw_response.get("finish_reason", "stop"),
        )],
        usage=ChatCompletionUsage(
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            completion_tokens=_as_int(usage.get("completion_tokens")),
            total_tokens=_as_int(usage.get("total_tokens")),
        ),
    )


def _as_int(value: Any) -> int:
    """Usage counters, defensively: providers disagree about what they send."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Model listing — let peers discover what models the Desktop has
# ---------------------------------------------------------------------------

@router.get(COMPUTE_MODELS_PATH)
async def peer_compute_models(
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """List models available for peer compute on this host.

    Returns an OpenAI-compatible model list so the ``PeerProvider`` can
    implement ``list_models()`` via a standard GET.

    Only models this host will actually serve a peer are listed: the secure
    slot never (it exists so secret-bearing turns stay here — finding M11)
    and apple-foundation never (it is local-only, serving the Mac's own
    slots). A peer that cannot see a model cannot ask for it, and
    _resolve_peer_model refuses it a second time if it does.
    """
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "owned_by": "halbert",
            }
            for name in sorted(_peer_servable_models())
        ],
    }


@router.get(COMPUTE_HEALTH_PATH)
async def peer_compute_health(
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """Is this host willing and able to serve peer compute right now?

    Authenticated but free: it resolves configuration and touches no model,
    so a satellite can probe it on every routing decision without costing
    the GPU anything. compute_router and config_wizard both probed this
    path and it existed nowhere, so the answer was always 404 (SE-08 /
    R10-F3).
    """
    models = _peer_servable_models()
    return {
        "status": "ok" if models else "no_models",
        "models": sorted(models),
        "peer": peer.node_id,
    }


# ---------------------------------------------------------------------------
# Internal — submit to compute broker
# ---------------------------------------------------------------------------

def _peer_servable_models() -> Dict[str, "ResolvedModel"]:
    """Local models this host is willing to run for a peer, by model name.

    Every enabled slot except the ones peers must never reach, narrowed to
    providers that serve general-purpose local inference. The exclusions are
    the point, so they are named rather than implied:

      * ``secure_model`` — the slot that exists so secret-bearing turns stay
        on this machine. Serving it to a peer inverts its whole reason.
      * ``apple-foundation`` — local-only by licence and by design; it backs
        the Mac's own slots and is never offered for offload.
    """
    from ..model.llm_config import load_file, resolve_from

    try:
        file_cfg = load_file()
    except Exception as e:
        logger.warning("Could not read the model config for peer compute: %s", e)
        return {}

    servable: Dict[str, Any] = {}
    for slot in (file_cfg.get("llm_config") or {}):
        if slot in _NEVER_SERVED_TO_PEERS or not slot.endswith("_model"):
            continue
        resolved = resolve_from(file_cfg, slot)
        if resolved is None:
            continue
        if resolved.provider not in PEER_SERVABLE_PROVIDERS:
            continue
        servable[resolved.model] = resolved
    return servable


def _resolve_peer_model(requested: str) -> "ResolvedModel":
    """The local model that will answer this request, or a 4xx explaining why not."""
    servable = _peer_servable_models()
    if not servable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This host has no model configured for peer compute.",
        )
    if requested and requested in servable:
        return servable[requested]
    if requested:
        # Named a model this host will not serve — which includes the secure
        # slot and apple-foundation, so the refusal is the same either way
        # and reveals nothing about which case it was.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {requested!r} is not available for peer compute here.",
        )
    # No model named: the workstation governs (handoff S3 5.2).
    return next(iter(servable.values()))


async def _submit_to_broker(
    request: ChatCompletionRequest,
    tools: Optional[List[Dict[str, Any]]],
    peer: PeerContext,
) -> Dict[str, Any]:
    """Run the peer's request on a local model.

    Phase 9.2a is 1:1, so this is a direct call with no queuing — the
    ComputeBroker's semaphore and priority queue are for the many-satellite
    case and remain unbuilt (SE-09 / R10-F2). It used to raise
    NotImplementedError, so a home node linked through the Compute Peer card
    got a 500 on every turn; the router was not mounted either, so in
    practice it got a 404 first.

    The response is returned raw: redaction is the caller's step, applied at
    the one egress choke point (mcp_response) rather than here.
    """
    from ..model.client import call_llm_chat

    resolved = _resolve_peer_model(request.model)
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    options: Dict[str, Any] = {"temperature": request.temperature}
    if request.max_tokens:
        options["num_predict"] = request.max_tokens
        options["max_tokens"] = request.max_tokens

    try:
        result = await asyncio.to_thread(
            call_llm_chat,
            resolved.url,
            resolved.model,
            messages,
            provider=resolved.provider,
            stream=False,
            options=options,
            tools=tools or None,
            api_key=resolved.api_key or None,
        )
    except Exception as e:
        logger.error("Peer compute call failed for %s: %s", peer.node_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The local model could not answer this request.",
        )

    return {
        "content": result.get("content", ""),
        "finish_reason": "stop",
        "usage": (result.get("raw") or {}).get("usage", {}) or {},
    }
