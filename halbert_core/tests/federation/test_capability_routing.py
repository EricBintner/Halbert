# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P5c: peers_config capability tracking tests.

Verifies the capability vocabulary, per-peer capability lookup (the HA
server's "which peer has sysadmin tools?" question), set_capabilities
for discovery refresh, and the forward-compat rule for unknown
capability names.
"""

import logging

import pytest

from halbert_core.federation.peers_config import (
    KNOWN_PEER_CAPABILITIES,
    PeersConfig,
    PeerCredential,
)


@pytest.fixture
def peers_config(tmp_path):
    return PeersConfig(config_path=tmp_path / "peers.json")


class TestVocabulary:
    def test_known_capabilities_cover_the_handoff_surface(self):
        """The singular-entity handoff's capability axes: workstation
        (terminal, config files, GPU, SourcePrep) and HA server (home
        tools, cameras), plus the MCP tool-routing target."""
        assert {"gpu_llm", "sourceprep", "vision", "terminal",
                "sysadmin_tools", "home_tools", "mcp"} <= KNOWN_PEER_CAPABILITIES

    def test_discovery_announced_names_are_known(self):
        """peer_discovery.py already announces gpu_llm/sourceprep/vision in
        its TXT records — those names must stay routable."""
        assert {"gpu_llm", "sourceprep", "vision"} <= KNOWN_PEER_CAPABILITIES


class TestCapabilityLookup:
    def test_find_peers_with_capability(self, peers_config):
        peers_config.add_peer(
            "desk", "Mac Studio", "compute_provider", raw_token="t1",
            capabilities=["gpu_llm", "sourceprep", "terminal", "sysadmin_tools"],
        )
        peers_config.add_peer(
            "home", "N150", "satellite", raw_token="t2",
            capabilities=["home_tools", "vision"],
        )
        assert [p.node_id for p in peers_config.find_peers_with_capability("terminal")] == ["desk"]
        assert [p.node_id for p in peers_config.find_peers_with_capability("home_tools")] == ["home"]
        assert peers_config.find_peers_with_capability("mcp") == []

    def test_find_peer_with_capability_is_deterministic(self, peers_config):
        """First in pairing order wins — the same config always routes a
        capability to the same peer."""
        peers_config.add_peer("a", "A", "compute_provider", raw_token="t1",
                              capabilities=["terminal"])
        peers_config.add_peer("b", "B", "compute_provider", raw_token="t2",
                              capabilities=["terminal"])
        assert peers_config.find_peer_with_capability("terminal").node_id == "a"

    def test_find_peer_with_capability_none_when_absent(self, peers_config):
        peers_config.add_peer("a", "A", "compute_provider", raw_token="t1",
                              capabilities=["gpu_llm"])
        assert peers_config.find_peer_with_capability("terminal") is None

    def test_revoked_peers_are_not_routed(self, peers_config):
        """Revocation removes a peer from capability routing — a revoked
        peer must not receive proxied tool calls."""
        peers_config.add_peer("desk", "Mac Studio", "compute_provider",
                              raw_token="t1", capabilities=["terminal"])
        peers_config.revoke_peer("desk")
        assert peers_config.find_peers_with_capability("terminal") == []
        assert peers_config.find_peer_with_capability("terminal") is None

    def test_credential_has_capability_helper(self):
        cred = PeerCredential(
            node_id="x", node_name="X", role="satellite",
            token_hash="sha256:0", paired_at="", capabilities=["gpu_llm"],
        )
        assert cred.has_capability("gpu_llm") is True
        assert cred.has_capability("terminal") is False


class TestSetCapabilities:
    def test_set_capabilities_updates_and_persists(self, peers_config, tmp_path):
        """Discovery refresh (P7a): a workstation that gained a GPU starts
        advertising gpu_llm — the record and the disk copy both update."""
        peers_config.add_peer("desk", "Mac Studio", "compute_provider",
                              raw_token="t1", capabilities=["terminal"])
        assert peers_config.set_capabilities(
            "desk", ["terminal", "gpu_llm", "sysadmin_tools"]) is True
        assert peers_config.get_peer("desk").capabilities == [
            "terminal", "gpu_llm", "sysadmin_tools"]
        reloaded = PeersConfig(config_path=tmp_path / "peers.json")
        assert reloaded.find_peer_with_capability("gpu_llm").node_id == "desk"

    def test_set_capabilities_unknown_peer(self, peers_config):
        assert peers_config.set_capabilities("ghost", ["gpu_llm"]) is False

    def test_capabilities_persist_across_reload(self, peers_config, tmp_path):
        peers_config.add_peer("desk", "Mac Studio", "compute_provider",
                              raw_token="t1", capabilities=["sourceprep", "mcp"])
        reloaded = PeersConfig(config_path=tmp_path / "peers.json")
        assert reloaded.find_peer_with_capability("mcp").node_id == "desk"
        assert reloaded.find_peer_with_capability("sourceprep").node_id == "desk"


class TestForwardCompat:
    def test_unknown_capability_is_kept_with_a_warning(self, peers_config, caplog):
        """A newer peer may advertise a capability this node has not
        learned yet — dropping it would break the peer after an upgrade
        in the wrong order. Kept, warned, not rejected."""
        with caplog.at_level(logging.WARNING):
            peers_config.add_peer(
                "future", "New Halbert", "compute_provider", raw_token="t1",
                capabilities=["terminal", "quantum_router"],
            )
        cred = peers_config.get_peer("future")
        assert "quantum_router" in cred.capabilities
        assert any("quantum_router" in r.message for r in caplog.records)

    def test_unknown_capability_is_not_routable_by_lookup(self, peers_config):
        """The lookup only ever answers names; an unknown one stored on a
        peer still answers if asked for by that exact name (the routing
        side gates on its own known set)."""
        peers_config.add_peer("future", "New Halbert", "compute_provider",
                              raw_token="t1", capabilities=["quantum_router"])
        assert peers_config.find_peer_with_capability("quantum_router") is not None
        assert peers_config.find_peer_with_capability("gpu_llm") is None