# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P4e: Compute fallback chain tests.

Tests the full fallback chain (P4b order):
1. Cloud LLM when internet is up
2. Local model when no internet but hardware supports it
3. Peer when no local model (never for cognitive_monologue)
4. Template thoughts (degraded, marked per P4c) when no peer
5. No-AI when template tier is disabled

Also tests connectivity detection integration and WoL pre-fallback (P6b).
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from halbert_core.federation.compute_router import (
    ComputeRouter,
    FallbackResult,
    TurnType,
)


def _make_router(
    peer_endpoint="http://desktop.lan:8000",
    hardware_profile="sbc_low_power",
    cloud_enabled=True,
    template_enabled=True,
    peers_config=None,
    **kwargs,
):
    """Create a ComputeRouter with mocked connectivity."""
    router = ComputeRouter(
        peer_endpoint=peer_endpoint,
        peer_token="test-token",
        hardware_profile=hardware_profile,
        cloud_enabled=cloud_enabled,
        template_enabled=template_enabled,
        peers_config=peers_config,
        **kwargs,
    )
    return router


class TestCloudPrimary:
    """Tier 1: Cloud LLM is the primary when internet is up."""

    @pytest.mark.asyncio
    async def test_cloud_when_internet_up(self):
        router = _make_router(cloud_enabled=True)
        with patch.object(router._connectivity, "is_online", return_value=True):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "gpt-4",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "cloud"
        assert result.fallback_used is False
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_cloud_serves_cognitive_monologue(self):
        """Cloud serves monologue too (not just interactive)."""
        router = _make_router(cloud_enabled=True)
        with patch.object(router._connectivity, "is_online", return_value=True):
            result = await router.route(
                [{"role": "user", "content": "tick"}], "gpt-4",
                turn_type=TurnType.COGNITIVE_MONOLOGUE,
            )
        assert result.source == "cloud"

    @pytest.mark.asyncio
    async def test_cloud_serves_all_turn_types(self):
        router = _make_router(cloud_enabled=True)
        with patch.object(router._connectivity, "is_online", return_value=True):
            for tt in TurnType:
                result = await router.route([{"role": "user", "content": "x"}], "m", turn_type=tt)
                assert result.source == "cloud"


class TestLocalModelFallback:
    """Tier 2: Local model when no internet but hardware supports it."""

    @pytest.mark.asyncio
    async def test_local_model_on_capable_hardware(self):
        router = _make_router(hardware_profile="entry_8gb", cloud_enabled=True)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "llama3",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "local_model"
        assert result.fallback_used is True
        assert result.fallback_from == "cloud"
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_local_model_when_no_cloud_configured(self):
        """Without cloud, local model is primary (not a fallback)."""
        router = _make_router(hardware_profile="entry_8gb", cloud_enabled=False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "llama3",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "local_model"
        assert result.fallback_used is False


class TestPeerFallback:
    """Tier 3: Peer when no local model (never for cognitive_monologue)."""

    @pytest.mark.asyncio
    async def test_peer_offload_when_online(self, monkeypatch):
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: True)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "peer"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_monologue_never_offloaded_to_peer(self, monkeypatch):
        """§11.3: cognitive_monologue never touches the peer."""
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        probed = {"calls": 0}

        async def _fail_if_probed():
            probed["calls"] += 1
            return False

        monkeypatch.setattr(router, "_probe_peer_health", _fail_if_probed)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "tick"}], "m",
                turn_type=TurnType.COGNITIVE_MONOLOGUE,
            )
        assert result.source == "template"
        assert probed["calls"] == 0  # never probed


class TestTemplateFallback:
    """Tier 4: Template thoughts (degraded) when no peer."""

    @pytest.mark.asyncio
    async def test_template_degraded_marker(self, monkeypatch):
        """P4c: template responses carry the degraded marker."""
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "template"
        assert result.degraded is True
        marker = result.degraded_marker()
        assert marker is not None
        assert "no thinking power" in marker

    @pytest.mark.asyncio
    async def test_template_interactive_is_deferred(self, monkeypatch):
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.deferred is True
        assert len(router._deferred_queue) == 1

    @pytest.mark.asyncio
    async def test_template_monologue_not_deferred(self, monkeypatch):
        """§11.3: cognitive_monologue is never deferred."""
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "tick"}], "m",
                turn_type=TurnType.COGNITIVE_MONOLOGUE,
            )
        assert result.deferred is False
        assert len(router._deferred_queue) == 0

    @pytest.mark.asyncio
    async def test_high_value_event_uses_heuristic(self, monkeypatch):
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "alert"}], "m",
                turn_type=TurnType.HIGH_VALUE_EVENT,
            )
        assert result.source == "heuristic"
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_sleep_consolidation_deferred_only(self, monkeypatch):
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "sleep"}], "m",
                turn_type=TurnType.SLEEP_CONSOLIDATION,
            )
        assert result.source == "deferred"
        assert result.deferred is True


class TestNoAI:
    """Tier 5: No-AI when template tier is disabled."""

    @pytest.mark.asyncio
    async def test_no_ai_when_template_disabled(self, monkeypatch):
        router = _make_router(
            hardware_profile="sbc_low_power",
            cloud_enabled=True,
            template_enabled=False,
        )
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        # When template is disabled and no other tier available,
        # the result should not be template/heuristic
        assert result.source not in ("template", "heuristic")


class TestConnectivityIntegration:
    """ConnectivityProbe integration with the fallback chain."""

    @pytest.mark.asyncio
    async def test_offline_uses_local_model(self):
        """When ConnectivityProbe says offline, cloud is skipped."""
        router = _make_router(hardware_profile="entry_8gb", cloud_enabled=True)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "local_model"

    @pytest.mark.asyncio
    async def test_online_uses_cloud(self):
        """When ConnectivityProbe says online, cloud is used."""
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        with patch.object(router._connectivity, "is_online", return_value=True):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "cloud"

    @pytest.mark.asyncio
    async def test_no_cloud_no_internet_uses_local(self):
        """No cloud configured + no internet = local model (not a fallback)."""
        router = _make_router(hardware_profile="entry_8gb", cloud_enabled=False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "local_model"
        assert result.fallback_used is False


class TestFullChainScenarios:
    """End-to-end fallback chain scenarios."""

    @pytest.mark.asyncio
    async def test_cloud_to_local_to_peer_to_template(self, monkeypatch):
        """Full chain: cloud down → local down → peer down → template."""
        router = _make_router(hardware_profile="sbc_low_power", cloud_enabled=True)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "template"
        assert result.degraded is True
        assert result.deferred is True

    @pytest.mark.asyncio
    async def test_no_peer_configured_goes_to_template(self, monkeypatch):
        router = _make_router(
            peer_endpoint=None,
            hardware_profile="sbc_low_power",
            cloud_enabled=True,
        )
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "template"
        assert result.degraded is True

    @pytest.mark.asyncio
    async def test_capable_hardware_skips_peer(self, monkeypatch):
        """Capable hardware uses local model, never probes peer."""
        router = _make_router(hardware_profile="laptop_16gb", cloud_enabled=True)
        probed = {"calls": 0}

        async def _fail_if_probed():
            probed["calls"] += 1
            return True

        monkeypatch.setattr(router, "_probe_peer_health", _fail_if_probed)
        with patch.object(router._connectivity, "is_online", return_value=False):
            result = await router.route(
                [{"role": "user", "content": "hi"}], "m",
                turn_type=TurnType.INTERACTIVE_USER,
            )
        assert result.source == "local_model"
        assert probed["calls"] == 0  # peer never probed
