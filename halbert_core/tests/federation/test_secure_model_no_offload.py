# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: secure_model slot never routes to a peer endpoint.

Implements finding M11 / L15 from the federated multi-node review.

M11 — The 4-slot model architecture defines which slots can peer-offload:
  - chat_model: CAN peer-offload
  - specialist_model: CAN peer-offload
  - vision_model: CAN peer-offload (if peer has vision capability)
  - secure_model: MUST NOT peer-offload (local-only by architectural rule)

This test verifies that PeerProvider.can_serve_slot() and the standalone
can_serve_slot() function enforce these rules.
"""
import pytest

from halbert_core.model.providers.peer import (
    PeerProvider,
    can_serve_slot,
    PEER_ELIGIBLE_SLOTS,
    SECURE_SLOT,
)


class TestSecureModelNoOffload:
    """Verify that secure_model is never routed to a peer."""

    def test_secure_model_never_eligible(self):
        """can_serve_slot returns False for secure_model regardless of capabilities."""
        assert can_serve_slot("secure_model") is False
        assert can_serve_slot("secure_model", peer_capabilities=["gpu_llm"]) is False
        assert can_serve_slot("secure_model", peer_capabilities=["vision", "gpu_llm"]) is False

    def test_chat_model_eligible(self):
        """chat_model can be served by a peer."""
        assert can_serve_slot("chat_model") is True
        assert can_serve_slot("chat_model", peer_capabilities=[]) is True

    def test_specialist_model_eligible(self):
        """specialist_model can be served by a peer."""
        assert can_serve_slot("specialist_model") is True

    def test_vision_model_requires_vision_capability(self):
        """vision_model requires the peer to advertise 'vision' capability."""
        # Without vision capability → denied
        assert can_serve_slot("vision_model") is False
        assert can_serve_slot("vision_model", peer_capabilities=["gpu_llm"]) is False
        # With vision capability → allowed
        assert can_serve_slot("vision_model", peer_capabilities=["vision"]) is True
        assert can_serve_slot("vision_model", peer_capabilities=["gpu_llm", "vision"]) is True

    def test_unknown_slot_denied(self):
        """An unknown slot name is denied (default-deny)."""
        assert can_serve_slot("unknown_slot") is False
        assert can_serve_slot("") is False

    def test_secure_slot_not_in_eligible_set(self):
        """secure_model is not in the PEER_ELIGIBLE_SLOTS set."""
        assert SECURE_SLOT not in PEER_ELIGIBLE_SLOTS
        assert SECURE_SLOT == "secure_model"

    def test_provider_can_serve_slot_secure(self):
        """PeerProvider.can_serve_slot() returns False for secure_model."""
        provider = PeerProvider(
            endpoint="peer://desktop.lan:8000",
            peer_token="test-token",
            peer_node_id="desktop",
            peer_capabilities=["gpu_llm", "vision"],
        )
        assert provider.can_serve_slot("secure_model") is False

    def test_provider_can_serve_slot_chat(self):
        """PeerProvider.can_serve_slot() returns True for chat_model."""
        provider = PeerProvider(
            endpoint="peer://desktop.lan:8000",
            peer_token="test-token",
            peer_capabilities=["gpu_llm"],
        )
        assert provider.can_serve_slot("chat_model") is True
        assert provider.can_serve_slot("specialist_model") is True

    def test_provider_vision_without_capability(self):
        """PeerProvider without vision capability cannot serve vision_model."""
        provider = PeerProvider(
            endpoint="peer://desktop.lan:8000",
            peer_token="test-token",
            peer_capabilities=["gpu_llm"],  # no vision
        )
        assert provider.can_serve_slot("vision_model") is False

    def test_provider_vision_with_capability(self):
        """PeerProvider with vision capability can serve vision_model."""
        provider = PeerProvider(
            endpoint="peer://desktop.lan:8000",
            peer_token="test-token",
            peer_capabilities=["gpu_llm", "vision"],
        )
        assert provider.can_serve_slot("vision_model") is True

    @pytest.mark.skip(reason="TODO(federation-9.3) — requires llm_config integration test")
    def test_llm_config_rejects_peer_url_for_secure_model(self):
        """llm_config._is_local_url() rejects peer:// for secure_model.

        This is the first layer of defense (llm_config.py:417-421).
        The PeerProvider.can_serve_slot() is the second layer.
        """
        pass
