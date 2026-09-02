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
          peer_capabilities: [gpu_llm, vision]

The ``peer://`` scheme is resolved to ``http://`` for the actual HTTP
call.  The ``peer_node_id`` is used to look up the bearer token from
``PeersConfig``.

Health checking
---------------
``health_check()`` probes ``GET /api/compute/v1/models`` on the peer with
a 1.5s timeout — authenticated, read-only, and costs no GPU time.  (The
dedicated ``/api/compute/v1/health`` route from Pillar 3 is not built on
the workstation side yet — TODO(federation-9.3) — so the models route is
the lightweight probe.)  The result feeds ``TierRouter``'s
``_model_health`` tracking and ``ComputeRouter``'s fallback logic.

Model selection
---------------
An HA node has no model picker (handoff
HOME-AUTOMATION-SIMPLIFICATION-2026-08-30 §5.2/5.3): both slots point at
the same peer endpoint and the *workstation's* model configuration
governs which model serves the request.  ``PEER_GOVERNED_MODEL`` is the
model tag a slot sends for that contract — the compute host resolves it
to its own configured model rather than a specific tag
(TODO(federation-9.3) on the workstation side).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

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

# The compute contract on the paired node: OpenAI's wire format served under
# /api/compute/v1 rather than /v1. Re-exported from the module that SERVES
# these paths, so the client and the server cannot disagree about the address
# again — /health had three spellings across three files and existed in none
# of them (SE-08 / R10-F3).
from ...federation.compute_endpoint import (  # noqa: E402
    COMPUTE_CHAT_PATH,
    COMPUTE_HEALTH_PATH,
    COMPUTE_MODELS_PATH,
)

# Health probe budget (Pillar 3: lightweight, no GPU time).
HEALTH_TIMEOUT_S = 1.5

# Model listing budget. Not the health probe — a slow WAN link to a
# Tailscale peer is allowed to take longer than 1.5s to answer once.
LIST_TIMEOUT_S = 10.0

# Model tag a peer slot sends when the workstation governs model choice
# (see the module docstring, "Model selection"). An HA node's chat_model
# and specialist_model both carry this tag against the same peer://
# endpoint — "the same endpoint, the same model list" (handoff §5.2).
PEER_GOVERNED_MODEL = "auto"


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
        returns an OpenAI-compatible model list; each entry's ``id`` is
        the tag a slot sends back in the ``model`` field.

        Returns exactly what the peer advertises — the workstation's
        models route is still a stub that lists nothing
        (compute_endpoint.py, TODO(federation-9.3)), so until that side
        is built this yields an empty list.  No models are invented
        locally to fill the gap.
        """
        try:
            response = requests.get(
                f"{self._endpoint}{COMPUTE_MODELS_PATH}",
                headers=self._headers,
                timeout=LIST_TIMEOUT_S,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise GenerationError(
                f"Peer model listing failed for {self._endpoint}: {e}"
            ) from e

        models: List[ModelConfig] = []
        for entry in response.json().get("data") or []:
            if not isinstance(entry, dict):
                continue
            model_id = str(entry.get("id") or "").strip()
            if not model_id:
                continue
            models.append(ModelConfig(
                model_id=model_id,
                provider="peer",
                capabilities=[ModelCapability.CHAT],
                # The peer owns the GPU; these are not this node's numbers.
                memory_mb=0,
                context_length=int(entry.get("context_length") or 0),
                metadata={
                    "peer_node_id": self._peer_node_id,
                    "owned_by": entry.get("owned_by"),
                },
            ))
        return models

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
        """
        start = time.time()
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = tools

        try:
            response = requests.post(
                f"{self._endpoint}{COMPUTE_CHAT_PATH}",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise GenerationError(
                f"Peer compute request to {self._endpoint} failed: {e}"
            ) from e

        if response.status_code in (401, 403):
            raise GenerationError(
                f"Peer {self._peer_node_id or self._endpoint} rejected the "
                f"bearer token (HTTP {response.status_code}) — revoked or "
                "re-paired on the workstation?",
                status_code=response.status_code,
            )
        if response.status_code == 503:
            raise GenerationError(
                "Peer compute broker is full (HTTP 503) — the workstation "
                "is saturated; retry or fall back",
                status_code=503,
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise GenerationError(
                f"Peer compute request failed: {e}", status_code=response.status_code,
            ) from e

        data = response.json()
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices else {}) or {}
        usage = data.get("usage") or {}
        return ModelResponse(
            text=str(message.get("content") or "").strip(),
            model_id=model_id,
            provider="peer",
            tokens_used=int(usage.get("total_tokens") or 0),
            latency_ms=(time.time() - start) * 1000.0,
            metadata={
                "peer_node_id": self._peer_node_id,
                "tool_calls": message.get("tool_calls") or [],
            },
        )

    def is_loaded(self, model_id: str) -> bool:
        """Check if a model is available on the peer.

        The peer owns model loading (via its compute broker), so
        "loaded" here means "named in the peer's model list". The
        workstation's list is still empty (TODO(federation-9.3)), so
        this is False for every tag until that side is built — except
        ``PEER_GOVERNED_MODEL``, which the workstation resolves itself.
        """
        if model_id == PEER_GOVERNED_MODEL:
            return True
        try:
            return model_id in {m.model_id for m in self.list_models()}
        except Exception:
            return False

    def get_model_info(self, model_id: str) -> ModelConfig:
        """Get model info from the peer's model list."""
        for model in self.list_models():
            if model.model_id == model_id:
                return model
        raise ModelNotFoundError(f"Model not available on peer {self._peer_node_id or self._endpoint}: {model_id}")

    # ------------------------------------------------------------------
    # Health checking (used by TierRouter._model_health)
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check if the peer is online and accepting compute requests.

        Probes ``GET /api/compute/v1/models`` with a 1.5s timeout —
        authenticated, read-only, and costs no GPU time. (The dedicated
        ``/api/compute/v1/health`` route from Pillar 3 is not built on
        the workstation side yet — TODO(federation-9.3) — so the models
        route is the probe.)
        """
        try:
            response = requests.get(
                f"{self._endpoint}{COMPUTE_MODELS_PATH}",
                headers=self._headers,
                timeout=HEALTH_TIMEOUT_S,
            )
            return response.status_code == 200
        except Exception:
            return False

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
