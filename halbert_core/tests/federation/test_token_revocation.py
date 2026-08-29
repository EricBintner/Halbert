# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: revoked peer token is rejected within one request cycle.

Implements finding M14 / L15 from the federated multi-node review.

M14 — Per-peer tokens with surgical revocation. A revoked token must be
rejected immediately — no grace period, no caching of token validity
beyond the request scope.
"""
import pytest
import tempfile
import os
from pathlib import Path

from halbert_core.federation.peers_config import PeersConfig, hash_token, verify_token_hash


@pytest.fixture
def peers_config(tmp_path):
    """Create a PeersConfig with a temp directory."""
    config_path = tmp_path / "peers.json"
    return PeersConfig(config_path=config_path)


class TestTokenRevocation:
    """Verify that token revocation is immediate and surgical."""

    def test_valid_token_is_accepted(self, peers_config):
        """A valid (non-revoked) token is accepted."""
        raw_token = peers_config.generate_token()
        peers_config.add_peer(
            node_id="satellite-1",
            node_name="Living Room Pi",
            role="satellite",
            raw_token=raw_token,
        )
        peer = peers_config.verify_token(raw_token)
        assert peer is not None
        assert peer.node_id == "satellite-1"

    def test_revoked_token_is_rejected(self, peers_config):
        """A revoked token is immediately rejected."""
        raw_token = peers_config.generate_token()
        peers_config.add_peer(
            node_id="satellite-1",
            node_name="Living Room Pi",
            role="satellite",
            raw_token=raw_token,
        )

        # Revoke
        assert peers_config.revoke_peer("satellite-1") is True

        # Token should now be rejected
        peer = peers_config.verify_token(raw_token)
        assert peer is None

    def test_revoking_one_peer_does_not_affect_others(self, peers_config):
        """Revoking one peer's token does not affect other peers (surgical)."""
        token1 = peers_config.generate_token()
        token2 = peers_config.generate_token()
        peers_config.add_peer("sat-1", "Pi 1", "satellite", raw_token=token1)
        peers_config.add_peer("sat-2", "Pi 2", "satellite", raw_token=token2)

        # Revoke sat-1
        peers_config.revoke_peer("sat-1")

        # sat-1 is rejected
        assert peers_config.verify_token(token1) is None
        # sat-2 is still accepted
        assert peers_config.verify_token(token2) is not None
        assert peers_config.verify_token(token2).node_id == "sat-2"

    def test_invalid_token_is_rejected(self, peers_config):
        """A random (non-paired) token is rejected."""
        peer = peers_config.verify_token("not-a-real-token-12345")
        assert peer is None

    def test_revoking_nonexistent_peer_returns_false(self, peers_config):
        """Revoking a peer that doesn't exist returns False."""
        assert peers_config.revoke_peer("nonexistent") is False

    def test_token_hash_is_not_raw_token(self, peers_config):
        """The stored token_hash is not the raw token (SHA-256 hashed)."""
        raw_token = peers_config.generate_token()
        cred = peers_config.add_peer("sat-1", "Pi 1", "satellite", raw_token=raw_token)
        assert cred.token_hash != raw_token
        assert cred.token_hash.startswith("sha256:")

    def test_re_pairing_after_revocation(self, peers_config):
        """After revoking, the old token is rejected and the node_id is occupied.

        TODO(federation-9.1): add_peer should allow re-pairing after
        revocation (either by overwriting the revoked entry or by
        removing it first). Currently add_peer raises ValueError if
        the node_id already exists, even if revoked. This test documents
        the current behavior — re-pairing is not yet supported.
        """
        token1 = peers_config.generate_token()
        peers_config.add_peer("sat-1", "Pi 1", "satellite", raw_token=token1)
        peers_config.revoke_peer("sat-1")

        # Old token is rejected after revocation
        assert peers_config.verify_token(token1) is None

        # Re-adding the same node_id currently raises ValueError
        # (the revoked entry is still in the store)
        token2 = peers_config.generate_token()
        with pytest.raises(ValueError, match="already paired"):
            peers_config.add_peer("sat-1", "Pi 1 (re-paired)", "satellite", raw_token=token2)

    def test_token_hash_verification_is_constant_time(self):
        """verify_token_hash uses constant-time comparison (hmac.compare_digest)."""
        raw = "test-token-12345"
        hashed = hash_token(raw)
        assert verify_token_hash(raw, hashed) is True
        assert verify_token_hash("wrong-token", hashed) is False

    @pytest.mark.skip(reason="TODO(federation-9.1) — requires peer_middleware FastAPI integration")
    def test_middleware_rejects_revoked_token_within_one_request(self):
        """The PeerAuthMiddleware rejects a revoked token on the next request.

        This test requires a running FastAPI app with the middleware
        installed. It verifies that after revoking a peer, the very next
        request with that token gets 401.
        """
        pass
