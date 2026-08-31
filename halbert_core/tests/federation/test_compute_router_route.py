# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""U6 S4/W18: ComputeRouter.route() decision matrix + health probe.

route() was a NotImplementedError stub. These tests pin the documented
fallback chain (§11.3 / H7 / H8): cognitive monologue is never offloaded
and never deferred; offloadable turns try the peer first; capable
hardware falls back to a local model; offload-only hardware (SBC_LOW_POWER,
U6 S4) goes straight to template thoughts with deferral per turn type.

Ported from the u6-home-simplification worktree and adapted to the
ha-simplification ComputeRouter API (same constructor signature, same
FallbackResult fields).
"""

import pytest

from halbert_core.federation.compute_router import ComputeRouter, TurnType


def _router(profile="sbc_low_power", peer="http://desktop.lan:8000"):
    return ComputeRouter(peer_endpoint=peer, peer_token="tok", hardware_profile=profile)


def _force_online(router):
    router._peer_online = True
    router._has_probed = True
    router._last_probe = __import__("time").monotonic()


def _force_offline(router):
    router._peer_online = False
    router._has_probed = True
    router._last_probe = __import__("time").monotonic()


class TestRouteDecisions:
    async def test_cognitive_monologue_never_offloaded_or_deferred(self):
        router = _router()
        _force_online(router)
        result = await router.route(
            [{"role": "user", "content": "tick"}], "m", TurnType.COGNITIVE_MONOLOGUE,
        )
        assert result.source == "template"
        assert result.deferred is False

    async def test_offloadable_turn_goes_to_online_peer(self):
        router = _router()
        _force_online(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "peer"
        assert result.peer_node_id is not None
        assert "desktop.lan" in result.peer_node_id
        assert result.deferred is False

    async def test_peer_offline_sbc_uses_template_interim(self):
        router = _router(profile="sbc_low_power")
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m",
                                    TurnType.INTERACTIVE_USER)
        assert result.source == "template"
        assert result.deferred is True
        assert result.fallback_used is True
        assert result.fallback_from == "peer"

    async def test_peer_offline_sbc_high_value_event_uses_heuristics(self):
        router = _router(profile="sbc_low_power")
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "x"}], "m",
                                    TurnType.HIGH_VALUE_EVENT)
        assert result.source == "heuristic"
        assert result.deferred is True

    async def test_peer_offline_sbc_sleep_consolidation_deferred(self):
        router = _router(profile="sbc_low_power")
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "x"}], "m",
                                    TurnType.SLEEP_CONSOLIDATION)
        assert result.source == "deferred"
        assert result.deferred is True

    async def test_peer_offline_capable_hardware_falls_back_to_local(self):
        router = _router(profile="entry_8gb")
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "local_model"
        assert result.fallback_used is True
        assert result.fallback_from == "peer"

    async def test_no_peer_and_offload_only_goes_to_template(self):
        router = ComputeRouter(hardware_profile="sbc_low_power")
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "template"
        assert result.deferred is True

    async def test_no_peer_and_capable_hardware_uses_local(self):
        router = ComputeRouter(hardware_profile="laptop_16gb")
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "local_model"


class TestHealthProbe:
    async def test_probe_success_marks_online(self, monkeypatch):
        router = _router()
        calls = []

        def fake_get(url, headers, timeout):
            calls.append((url, headers, timeout))
            return type("R", (), {"status_code": 200})()

        import halbert_core.federation.compute_router as cr
        import requests as requests_mod
        monkeypatch.setattr(requests_mod, "get", fake_get)
        # route triggers the probe lazily
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "peer"
        assert calls[0][0] == "http://desktop.lan:8000/api/compute/v1/health"
        assert calls[0][1] == {"Authorization": "Bearer tok"}

    async def test_three_consecutive_failures_flip_offline(self, monkeypatch):
        """§11.6: a single failure must not flap the peer offline."""
        import requests as requests_mod
        monkeypatch.setattr(requests_mod, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
        router = _router()
        router.health_probe_interval = 0.0

        assert await router._probe_peer_health() is False
        assert await router._probe_peer_health() is False
        assert await router._probe_peer_health() is False
        assert router._consecutive_failures == 3

        # First two failures did not mark offline; the third did (was
        # already False here, so pin the inverse: success resets fully).
        monkeypatch.setattr(requests_mod, "get", lambda *a, **k: type("R", (), {"status_code": 200})())
        assert await router._probe_peer_health() is True
        assert router._consecutive_failures == 0

    async def test_probe_result_is_cached_within_interval(self, monkeypatch):
        import requests as requests_mod
        probe_count = {"n": 0}

        def fake_get(*a, **k):
            probe_count["n"] += 1
            return type("R", (), {"status_code": 200})()

        monkeypatch.setattr(requests_mod, "get", fake_get)
        router = _router()
        router.health_probe_interval = 60.0
        assert await router._probe_peer_health() is True
        assert await router._probe_peer_health() is True
        assert await router._probe_peer_health() is True
        assert probe_count["n"] == 1
