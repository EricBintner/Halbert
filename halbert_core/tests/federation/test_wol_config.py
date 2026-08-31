# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P6c: peers_config WoL fields tests.

Verifies WoL fields on PeerCredential, set_wol method, and
list_wol_enabled_peers filtering.
"""

import pytest

from halbert_core.federation.peers_config import PeersConfig, PeerCredential


@pytest.fixture
def peers_config(tmp_path):
    return PeersConfig(config_path=tmp_path / "peers.json")


class TestWolFields:
    def test_wol_disabled_by_default(self, peers_config):
        cred = peers_config.add_peer("ws", "Workstation", "compute_provider", raw_token="t")
        assert cred.wol_enabled is False
        assert cred.wol_mac is None
        assert cred.wol_broadcast is None

    def test_wol_enabled_at_pairing(self, peers_config):
        cred = peers_config.add_peer(
            "ws", "Workstation", "compute_provider", raw_token="t",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF", wol_broadcast="192.168.1.255",
        )
        assert cred.wol_enabled is True
        assert cred.wol_mac == "AA:BB:CC:DD:EE:FF"
        assert cred.wol_broadcast == "192.168.1.255"

    def test_wol_persists_to_disk(self, peers_config, tmp_path):
        peers_config.add_peer(
            "ws", "Workstation", "compute_provider", raw_token="t",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF",
        )
        reloaded = PeersConfig(config_path=tmp_path / "peers.json")
        peer = reloaded.get_peer("ws")
        assert peer.wol_enabled is True
        assert peer.wol_mac == "AA:BB:CC:DD:EE:FF"

    def test_wol_round_trips_through_dict(self):
        cred = PeerCredential(
            node_id="ws", node_name="WS", role="compute_provider",
            token_hash="sha256:abc", paired_at="2026-01-01",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF", wol_broadcast="192.168.1.255",
        )
        d = cred.to_dict()
        assert d["wol_enabled"] is True
        assert d["wol_mac"] == "AA:BB:CC:DD:EE:FF"
        restored = PeerCredential.from_dict(d)
        assert restored.wol_enabled is True
        assert restored.wol_mac == "AA:BB:CC:DD:EE:FF"

    def test_from_dict_defaults_wol_disabled_when_missing(self):
        d = {
            "node_id": "old", "node_name": "Old", "role": "compute_provider",
            "token_hash": "sha256:abc", "paired_at": "2026-01-01",
        }
        cred = PeerCredential.from_dict(d)
        assert cred.wol_enabled is False
        assert cred.wol_mac is None


class TestSetWol:
    def test_enable_wol_on_existing_peer(self, peers_config):
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t")
        assert peers_config.set_wol("ws", enabled=True, mac="AA:BB:CC:DD:EE:FF")
        peer = peers_config.get_peer("ws")
        assert peer.wol_enabled is True
        assert peer.wol_mac == "AA:BB:CC:DD:EE:FF"

    def test_disable_wol(self, peers_config):
        peers_config.add_peer(
            "ws", "WS", "compute_provider", raw_token="t",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF",
        )
        assert peers_config.set_wol("ws", enabled=False)
        peer = peers_config.get_peer("ws")
        assert peer.wol_enabled is False
        # MAC is retained even when disabled
        assert peer.wol_mac == "AA:BB:CC:DD:EE:FF"

    def test_set_wol_nonexistent_peer(self, peers_config):
        assert peers_config.set_wol("nope", enabled=True, mac="AA:BB:CC:DD:EE:FF") is False

    def test_set_wol_rejects_enable_without_mac(self, peers_config):
        """Enabling WoL without a MAC is rejected (unwakeable state)."""
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t")
        # No MAC provided, no MAC on peer — should return False
        assert peers_config.set_wol("ws", enabled=True) is False
        peer = peers_config.get_peer("ws")
        assert peer.wol_enabled is False

    def test_set_wol_timeout(self, peers_config):
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t")
        peers_config.set_wol("ws", enabled=True, mac="AA:BB:CC:DD:EE:FF", timeout=120)
        peer = peers_config.get_peer("ws")
        assert peer.wol_timeout == 120

    def test_wol_timeout_default_90(self, peers_config):
        cred = peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t")
        assert cred.wol_timeout == 90

    def test_wol_timeout_persists_to_disk(self, peers_config, tmp_path):
        peers_config.add_peer(
            "ws", "WS", "compute_provider", raw_token="t",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF", wol_timeout=60,
        )
        reloaded = PeersConfig(config_path=tmp_path / "peers.json")
        peer = reloaded.get_peer("ws")
        assert peer.wol_timeout == 60

    def test_wol_timeout_round_trips_through_dict(self):
        cred = PeerCredential(
            node_id="ws", node_name="WS", role="compute_provider",
            token_hash="sha256:abc", paired_at="2026-01-01",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF", wol_timeout=45,
        )
        d = cred.to_dict()
        assert d["wol_timeout"] == 45
        restored = PeerCredential.from_dict(d)
        assert restored.wol_timeout == 45

    def test_from_dict_defaults_wol_timeout_90_when_missing(self):
        d = {
            "node_id": "old", "node_name": "Old", "role": "compute_provider",
            "token_hash": "sha256:abc", "paired_at": "2026-01-01",
        }
        cred = PeerCredential.from_dict(d)
        assert cred.wol_timeout == 90

    def test_set_wol_broadcast(self, peers_config):
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t")
        peers_config.set_wol("ws", enabled=True, mac="AA:BB:CC:DD:EE:FF", broadcast="10.0.0.255")
        peer = peers_config.get_peer("ws")
        assert peer.wol_broadcast == "10.0.0.255"


class TestListWolEnabledPeers:
    def test_returns_only_wol_enabled(self, peers_config):
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t",
                              wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF")
        peers_config.add_peer("pi", "Pi", "satellite", raw_token="t2")
        wol_peers = peers_config.list_wol_enabled_peers()
        assert len(wol_peers) == 1
        assert wol_peers[0].node_id == "ws"

    def test_excludes_revoked(self, peers_config):
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t",
                              wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF")
        peers_config.revoke_peer("ws")
        assert len(peers_config.list_wol_enabled_peers()) == 0

    def test_excludes_wol_enabled_without_mac(self, peers_config):
        """WoL enabled but no MAC = not a valid wake target."""
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t",
                              wol_enabled=True)  # no MAC
        assert len(peers_config.list_wol_enabled_peers()) == 0

    def test_empty_when_none_enabled(self, peers_config):
        peers_config.add_peer("ws", "WS", "compute_provider", raw_token="t")
        assert len(peers_config.list_wol_enabled_peers()) == 0

    def test_excludes_inbound_peers(self, peers_config):
        """WoL only applies to outbound compute targets, not inbound peers."""
        peers_config.add_peer(
            "ws", "WS", "compute_provider", raw_token="t",
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF",
            compute_direction="outbound",
        )
        peers_config.add_peer(
            "ha", "HA", "compute_provider", raw_token="t2",
            wol_enabled=True, wol_mac="BB:CC:DD:EE:FF:AA",
            compute_direction="inbound",
        )
        wol_peers = peers_config.list_wol_enabled_peers()
        assert len(wol_peers) == 1
        assert wol_peers[0].node_id == "ws"
