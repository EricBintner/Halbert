# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P4d: peers_config compute direction correction tests.

Verifies that PeersConfig supports both outbound (HA→workstation) and
inbound (workstation←HA) compute directions, with outbound as the default.
"""

import json
from pathlib import Path

import pytest

from halbert_core.federation.peers_config import PeersConfig, PeerCredential


@pytest.fixture
def peers_config(tmp_path):
    """Fresh PeersConfig with a temp file."""
    return PeersConfig(config_path=tmp_path / "peers.json")


class TestComputeDirection:
    def test_default_direction_is_outbound(self, peers_config):
        """New peers default to 'outbound' (HA → workstation)."""
        cred = peers_config.add_peer(
            "workstation", "Mac Studio", "compute_provider", raw_token="tok123",
        )
        assert cred.compute_direction == "outbound"
        assert cred.is_compute_target() is True
        assert cred.is_compute_source() is False

    def test_explicit_outbound_direction(self, peers_config):
        cred = peers_config.add_peer(
            "workstation", "Mac Studio", "compute_provider",
            raw_token="tok123", compute_direction="outbound",
        )
        assert cred.compute_direction == "outbound"
        assert cred.is_compute_target() is True

    def test_inbound_direction(self, peers_config):
        """Workstation's peers.json lists HA server as inbound."""
        cred = peers_config.add_peer(
            "ha-server", "N150 HA Server", "satellite",
            raw_token="tok123", compute_direction="inbound",
        )
        assert cred.compute_direction == "inbound"
        assert cred.is_compute_target() is False
        assert cred.is_compute_source() is True

    def test_direction_persists_to_disk(self, peers_config, tmp_path):
        peers_config.add_peer(
            "workstation", "Mac Studio", "compute_provider",
            raw_token="tok123", compute_direction="outbound",
        )
        # Reload from disk
        reloaded = PeersConfig(config_path=tmp_path / "peers.json")
        peer = reloaded.get_peer("workstation")
        assert peer.compute_direction == "outbound"

    def test_direction_round_trips_through_dict(self):
        cred = PeerCredential(
            node_id="ha", node_name="HA", role="satellite",
            token_hash="sha256:abc", paired_at="2026-01-01T00:00:00Z",
            compute_direction="inbound",
        )
        d = cred.to_dict()
        assert d["compute_direction"] == "inbound"
        restored = PeerCredential.from_dict(d)
        assert restored.compute_direction == "inbound"

    def test_from_dict_defaults_to_outbound_when_missing(self):
        """Old peers.json without compute_direction defaults to outbound."""
        d = {
            "node_id": "old-peer",
            "node_name": "Old Peer",
            "role": "compute_provider",
            "token_hash": "sha256:abc",
            "paired_at": "2026-01-01T00:00:00Z",
        }
        cred = PeerCredential.from_dict(d)
        assert cred.compute_direction == "outbound"

    def test_list_compute_targets_returns_only_outbound(self, peers_config):
        peers_config.add_peer(
            "workstation", "Mac Studio", "compute_provider",
            raw_token="tok1", compute_direction="outbound",
        )
        peers_config.add_peer(
            "ha-satellite", "Pi HA", "satellite",
            raw_token="tok2", compute_direction="inbound",
        )
        targets = peers_config.list_compute_targets()
        assert len(targets) == 1
        assert targets[0].node_id == "workstation"

    def test_list_compute_targets_excludes_revoked(self, peers_config):
        peers_config.add_peer(
            "workstation", "Mac Studio", "compute_provider",
            raw_token="tok1", compute_direction="outbound",
        )
        peers_config.revoke_peer("workstation")
        targets = peers_config.list_compute_targets()
        assert len(targets) == 0

    def test_both_directions_coexist(self, peers_config):
        """A node can have both outbound and inbound peers simultaneously."""
        peers_config.add_peer(
            "workstation", "Mac Studio", "compute_provider",
            raw_token="tok1", compute_direction="outbound",
        )
        peers_config.add_peer(
            "kitchen-pi", "Kitchen Pi", "satellite",
            raw_token="tok2", compute_direction="inbound",
        )
        all_peers = peers_config.list_peers()
        assert len(all_peers) == 2
        targets = peers_config.list_compute_targets()
        assert len(targets) == 1
        assert targets[0].node_id == "workstation"
