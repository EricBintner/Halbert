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
    "/api/compute/v1/chat/completions",
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
    # This is the SAME redaction used by the MCP server.  It strips:
    # - Secret values in config-value-pair shapes
    # - Secret dict keys
    # - PEM blocks, JWTs, URL-embedded credentials, routable IPs in text
    redacted_response = mcp_response(raw_response)

    # Step 4: Serialize and return
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=request.model,
        choices=[ChatCompletionChoice(
            message=ChatMessage(
                role="assistant",
                content=redacted_response.get("content", ""),
            ),
            finish_reason=redacted_response.get("finish_reason", "stop"),
        )],
        usage=ChatCompletionUsage(
            prompt_tokens=redacted_response.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=redacted_response.get("usage", {}).get("completion_tokens", 0),
            total_tokens=redacted_response.get("usage", {}).get("total_tokens", 0),
        ),
    )


# ---------------------------------------------------------------------------
# Model listing — let peers discover what models the Desktop has
# ---------------------------------------------------------------------------

@router.get(
    "/api/compute/v1/models",
)
async def peer_compute_models(
    peer: PeerContext = Depends(require_peer_auth),
) -> Dict[str, Any]:
    """List models available for peer compute on this host.

    Returns an OpenAI-compatible model list so the ``PeerProvider`` can
    implement ``list_models()`` via a standard GET.

    TODO(federation-9.3): Query the local Ollama / vLLM instances and
    merge into a single list.  Filter out models that are not available
    for peer offload (e.g., secure_model is never listed here — finding
    M11; Apple Intelligence is local-only and never listed — it serves
    the Mac's own slots, never peer offload).
    """
    # TODO(federation-9.3): Implement
    return {
        "object": "list",
        "data": [],  # populated with model definitions
    }


# ---------------------------------------------------------------------------
# Internal — submit to compute broker
# ---------------------------------------------------------------------------

async def _submit_to_broker(
    request: ChatCompletionRequest,
    tools: Optional[List[Dict[str, Any]]],
    peer: PeerContext,
) -> Dict[str, Any]:
    """Submit the inference request to the compute broker.

    TODO(federation-9.3): Wire to ComputeBroker.submit() which:
    1. Enqueues the request with the peer's priority level
    2. Waits for a concurrency slot (semaphore)
    3. Calls the local model (Ollama, vLLM) — never Apple Intelligence,
       which is local-only (the Mac's own slots)
    4. Returns the raw response (pre-redaction)

    For Phase 9.2a (1:1 validation), this is a direct call to the local
    model with no queuing.
    """
    raise NotImplementedError("_submit_to_broker — TODO(federation-9.3)")
