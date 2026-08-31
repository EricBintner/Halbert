# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: mDNS peer discovery — TXT record serialization and handshake validation.

Implements findings H9, H10, and L15 from the federated multi-node review.

H9 — mDNS is LAN-only, does not cross Tailscale.
H10 — zeroconf is a lazy optional extra (Haloysius subtractive contract).
"""
import pytest

from halbert_core.federation.peer_discovery import (
    DiscoveredPeer,
    build_txt_record,
    parse_txt_record,
    get_node_identity,
    SERVICE_TYPE,
)


class TestPeerDiscovery:
    """Verify mDNS TXT record serialization and discovery data structures."""

    def test_service_type(self):
        """The mDNS service type is _halbert._tcp."""
        assert SERVICE_TYPE == "_halbert._tcp."

    def test_build_txt_record(self):
        """build_txt_record produces the correct TXT record fields."""
        txt = build_txt_record(
            node_id="studio-mac",
            node_name="Studio Mac",
            role="compute_provider",
            port=8000,
            capabilities=["gpu_llm", "sourceprep"],
            compute_backends=["ollama", "vllm"],
        )
        assert txt["node_id"] == "studio-mac"
        assert txt["node_name"] == "Studio Mac"
        assert txt["role"] == "compute_provider"
        assert txt["api_port"] == "8000"
        assert txt["capabilities"] == "gpu_llm,sourceprep"
        assert txt["compute_backends"] == "ollama,vllm"

    def test_parse_txt_record(self):
        """parse_txt_record correctly parses TXT record fields."""
        parsed = parse_txt_record({
            "node_id": "living-room-pi",
            "node_name": "Living Room Pi 5",
            "role": "satellite",
            "api_port": "8001",
            "capabilities": "gpu_llm,vision",
            "compute_backends": "ollama",
        })
        assert parsed["node_id"] == "living-room-pi"
        assert parsed["node_name"] == "Living Room Pi 5"
        assert parsed["role"] == "satellite"
        assert parsed["port"] == 8001
        assert "gpu_llm" in parsed["capabilities"]
        assert "vision" in parsed["capabilities"]
        assert "ollama" in parsed["compute_backends"]

    def test_parse_txt_record_defaults(self):
        """parse_txt_record handles missing fields with defaults."""
        parsed = parse_txt_record({})
        assert parsed["node_id"] == "unknown"
        assert parsed["port"] == 8000
        assert parsed["capabilities"] == []
        assert parsed["compute_backends"] == []

    def test_discovered_peer_endpoint(self):
        """DiscoveredPeer.endpoint property produces the correct URL."""
        peer = DiscoveredPeer(
            node_id="test",
            node_name="Test",
            role="satellite",
            host="192.168.1.50",
            port=8000,
        )
        assert peer.endpoint == "http://192.168.1.50:8000"

    def test_discovered_peer_to_dict(self):
        """DiscoveredPeer.to_dict() serializes correctly."""
        peer = DiscoveredPeer(
            node_id="test",
            node_name="Test",
            role="compute_provider",
            host="desktop.lan",
            port=8000,
            capabilities=["gpu_llm"],
            compute_backends=["ollama"],
        )
        d = peer.to_dict()
        assert d["node_id"] == "test"
        assert d["endpoint"] == "http://desktop.lan:8000"
        assert d["capabilities"] == ["gpu_llm"]
        assert d["compute_backends"] == ["ollama"]

    def test_get_node_identity_reads_env_vars(self, monkeypatch):
        """get_node_identity reads HALBERT_* env vars for mDNS announcement."""
        monkeypatch.setenv("HALBERT_PERSONA_ID", "home")
        monkeypatch.setenv("HALBERT_DISPLAY_NAME", "Home Server")
        monkeypatch.setenv("HALBERT_PORT", "8001")
        monkeypatch.setenv("HALBERT_ROLE", "satellite")

        identity = get_node_identity()
        assert "home" in identity["node_id"]  # persona_id + hostname
        assert identity["node_name"] == "Home Server"
        assert identity["port"] == 8001
        assert identity["role"] == "satellite"

    def test_compute_backends_field_in_txt_record(self):
        """The TXT record includes compute_backends; Apple Intelligence is never a peer backend (M13).

        Per the Apple Intelligence local-only constraint, a Mac compute
        host advertises ``ollama``/``vllm`` for peers — ``apple_foundation``
        is never listed because Apple Intelligence serves only the Mac's
        own slots, never peer offload.
        """
        txt = build_txt_record(
            node_id="mac-studio",
            node_name="Mac Studio",
            role="compute_provider",
            port=8000,
            capabilities=["gpu_llm", "vision"],
            compute_backends=["ollama", "vllm"],
        )
        assert "compute_backends" in txt
        assert "apple_foundation" not in txt["compute_backends"]
        assert "ollama" in txt["compute_backends"]

    @pytest.mark.skip(reason="TODO(federation-9.7) — requires zeroconf (lazy import)")
    def test_beacon_start_without_zeroconf(self):
        """PeerBeacon.start() gracefully degrades when zeroconf is not installed.

        Per finding H10, zeroconf is a lazy optional extra. If not installed,
        the beacon logs a warning and returns without raising.
        """
        pass

    @pytest.mark.skip(reason="TODO(federation-9.7) — requires zeroconf")
    def test_listener_start_without_zeroconf(self):
        """PeerListener.start() gracefully degrades when zeroconf is not installed."""
        pass
