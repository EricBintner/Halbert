# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Peer model provider — calls a paired Halbert node's compute endpoint.

Implements findings C3 and M11 from the federated multi-node review.

C3 — Extends tier_router.py, does not replace it
-------------------------------------------------
This is a new ``ModelProvider`` subclass (following the same pattern as
``OllamaProvider``, ``AnthropicProvider``, etc.) that proxies inference
requests to a paired Halbert node's compute endpoint
(``/api/compute/v1/chat/completions``).

It is registered in ``TierRouter`` as a new provider type ``PEER``
(alongside ``OLLAMA``, ``ANTHROPIC``, ``OPENAI``, ``OPENROUTER``).  The
satellite's ``chat_model`` or ``specialist_model`` slot can point at a
``peer://`` endpoint, and the existing ``TierRouter`` fallback machinery
handles health checking, fallback tracking, and cost-cascade routing.

M11 — Slot-level routing rules
-------------------------------
Not all model slots can be offloaded to a peer:

  - ``chat_model``: CAN peer-offload (general conversation)
  - ``specialist_model``: CAN peer-offload (complex reasoning — the main use case)
  - ``vision_model``: CAN peer-offload ONLY if peer advertises ``vision`` capability
  - ``secure_model``: MUST NOT peer-offload (local-only by architectural rule)

The ``secure_model`` slot has a hard local-only URL enforcement in
``llm_config.py:417-421`` — ``_is_local_url()`` rejects non-loopback
endpoints.  A ``peer://`` URL is not local, so ``secure_model`` is
automatically rejected by the existing enforcement.  This provider also
implements ``can_serve_slot()`` as a second layer of defense.

URL scheme
-----------
Peer endpoints use the ``peer://`` scheme in models.yml::

    endpoints:
      - id: desktop-peer
        url: peer://desktop.lan:8000
        provider: peer
        metadata:
          peer_node_id: studio-mac
          peer_capabilities: [gpu_llm, apple_foundation, vision]

The ``peer://`` scheme is resolved to ``http://`` for the actual HTTP
call.  The ``peer_node_id`` is used to look up the bearer token from
``PeersConfig``.

Health checking
---------------
``health_check()`` calls ``GET /api/compute/v1/health`` on the peer
with a 1.5s timeout (per Pillar 3).  This is used by ``TierRouter``'s
``_model_health`` tracking and by ``ComputeRouter``'s fallback logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import (
    ModelProvider,
    ModelConfig,
    ModelResponse,
    ModelCapability,
    ModelNotFoundError,
    GenerationError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slot routing rules (M11)
# ---------------------------------------------------------------------------

# Slots that CAN be served by a peer provider.
# secure_model is NOT in this list — it must stay local-only.
PEER_ELIGIBLE_SLOTS = frozenset({"chat_model", "specialist_model", "vision_model"})

# secure_model is NEVER eligible for peer offload.
# This is enforced at two layers:
# 1. llm_config.py _is_local_url() rejects peer:// for secure_model
# 2. PeerProvider.can_serve_slot() returns False for secure_model
SECURE_SLOT = "secure_model"


def can_serve_slot(slot_name: str, peer_capabilities: Optional[List[str]] = None) -> bool:
    """Check if a model slot can be served by a peer provider.

    Per finding M11:
    - secure_model: NEVER (local-only by architectural rule)
    - chat_model, specialist_model: YES
    - vision_model: YES, but only if the peer advertises 'vision' capability

    Args:
        slot_name: The model slot name (chat_model, specialist_model, etc.)
        peer_capabilities: The peer's advertised capabilities from mDNS TXT record.
            Required for vision_model; ignored for other slots.
    """
    if slot_name == SECURE_SLOT:
        return False
    if slot_name not in PEER_ELIGIBLE_SLOTS:
        return False
    if slot_name == "vision_model":
        if not peer_capabilities or "vision" not in peer_capabilities:
            return False
    return True


# ---------------------------------------------------------------------------
# PeerProvider
# ---------------------------------------------------------------------------

class PeerProvider(ModelProvider):
    """Model provider that proxies to a paired Halbert node's compute endpoint.

    This provider does NOT load models locally — it sends inference
    requests over HTTP to the peer's ``/api/compute/v1/chat/completions``
    endpoint.  The peer's compute broker manages GPU allocation.

    The peer applies ``mcp_response()`` redaction on its response (C4),
    so secrets are already stripped.  This provider does NOT apply
    redaction again — the peer is the egress boundary, and the
    satellite is the destination (not a third-party cloud).
    """

    def __init__(
        self,
        endpoint: str,
        peer_token: str,
        peer_node_id: str = "",
        peer_capabilities: Optional[List[str]] = None,
        timeout: float = 120.0,
    ):
        """
        Args:
            endpoint: The peer's compute endpoint URL
                (e.g., "http://desktop.lan:8000").  The ``peer://``
                scheme is converted to ``http://`` here.
            peer_token: Bearer token for authenticating to the peer.
            peer_node_id: The peer's node_id (for logging and health tracking).
            peer_capabilities: The peer's advertised capabilities
                (from mDNS or peers.json).  Used by can_serve_slot().
            timeout: HTTP timeout for inference requests (seconds).
                Default 120s — LLM generation can take a while.
        """
        # Convert peer:// to http://
        self._endpoint = endpoint.replace("peer://", "http://", 1)
        self._peer_token = peer_token
        self._peer_node_id = peer_node_id
        self._peer_capabilities = peer_capabilities or []
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {peer_token}",
            "Content-Type": "application/json",
        }

        logger.info(
            "PeerProvider initialized: node=%s, endpoint=%s, caps=%s",
            peer_node_id, self._endpoint, self._peer_capabilities,
        )

    # ------------------------------------------------------------------
    # ModelProvider interface
    # ------------------------------------------------------------------

    def list_models(self) -> List[ModelConfig]:
        """List models available on the peer.

        Calls ``GET /api/compute/v1/models`` on the peer.  The peer
        returns an OpenAI-compatible model list.

        TODO(federation-9.3): Implement using requests.get.
        Returns models that the peer's compute broker can serve.
        """
        raise NotImplementedError("PeerProvider.list_models() — TODO(federation-9.3)")

    def load_model(self, model_id: str, **kwargs) -> bool:
        """No-op for peer provider — models are loaded on the peer, not locally.

        Returns True always — the peer manages its own model loading
        via its compute broker.  This method exists to satisfy the
        ModelProvider interface.
        """
        logger.debug("PeerProvider.load_model(%s) — no-op (peer manages loading)", model_id)
        return True

    def unload_model(self, model_id: str) -> bool:
        """No-op for peer provider — models are unloaded on the peer."""
        return True

    def generate(
        self,
        prompt: str,
        model_id: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ) -> ModelResponse:
        """Generate text by proxying to the peer's compute endpoint.

        Sends a POST to ``/api/compute/v1/chat/completions`` with the
        prompt as a single user message.  The peer's compute broker
        queues the request, runs it on the GPU, and returns the result.

        The peer applies ``mcp_response()`` redaction on the response
        (C4), so secrets are already stripped before they reach us.

        TODO(federation-9.3): Implement using requests.post:
        1. Build OpenAI-compatible request body
        2. POST to {endpoint}/api/compute/v1/chat/completions
        3. Parse response
        4. Build ModelResponse
        5. Handle errors (401 = token revoked, 503 = broker full, timeout)
        """
        raise NotImplementedError("PeerProvider.generate() — TODO(federation-9.3)")

    def is_loaded(self, model_id: str) -> bool:
        """Check if a model is available on the peer.

        TODO(federation-9.3): Check if the model is in the peer's model
        list (cached from last list_models() call).
        """
        raise NotImplementedError("PeerProvider.is_loaded() — TODO(federation-9.3)")

    def get_model_info(self, model_id: str) -> ModelConfig:
        """Get model info from the peer's model list.

        TODO(federation-9.3): Look up in cached model list.
        """
        raise NotImplementedError("PeerProvider.get_model_info() — TODO(federation-9.3)")

    # ------------------------------------------------------------------
    # Health checking (used by TierRouter._model_health)
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check if the peer is online and accepting compute requests.

        Calls ``GET /api/compute/v1/health`` with a 1.5s timeout.
        This is a lightweight probe — no GPU time, no model loading.

        TODO(federation-9.3): Implement using requests.get with timeout=1.5.
        """
        raise NotImplementedError("PeerProvider.health_check() — TODO(federation-9.3)")

    # ------------------------------------------------------------------
    # Slot eligibility (M11)
    # ------------------------------------------------------------------

    def can_serve_slot(self, slot_name: str) -> bool:
        """Check if this peer can serve a given model slot.

        Per finding M11:
        - secure_model: NEVER (local-only by architectural rule)
        - chat_model, specialist_model: YES
        - vision_model: YES only if peer advertises 'vision' capability
        """
        return can_serve_slot(slot_name, self._peer_capabilities)
