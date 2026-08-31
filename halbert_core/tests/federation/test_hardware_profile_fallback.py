# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: hardware-profile-aware fallback uses template thoughts on SBC_LOW_POWER.

Implements finding H7 / L15 from the federated multi-node review.

H7 — On SBC_LOW_POWER (≤4GB RAM), a local 3B model will OOM. The fallback
chain must NOT attempt to load a micro-model on these devices. Instead,
it falls back to template thoughts (HALBERT_LLM_THOUGHTS=0).

This test verifies that ComputeRouter._hardware_supports_local_model()
returns False for SBC_LOW_POWER and True for higher profiles.
"""
import pytest

from halbert_core.federation.compute_router import ComputeRouter, TurnType


class TestHardwareProfileFallback:
    """Verify hardware-profile-aware fallback logic."""

    def _make_router(self, profile: str, **kwargs) -> ComputeRouter:
        """Create a ComputeRouter with a given hardware profile."""
        return ComputeRouter(
            peer_endpoint="http://desktop.lan:8000",
            peer_token="test-token",
            hardware_profile=profile,
            **kwargs,
        )

    def test_sbc_low_power_cannot_run_local_model(self):
        """SBC_LOW_POWER (≤4GB) cannot run a local model (OOM risk)."""
        router = self._make_router("sbc_low_power")
        assert router._hardware_supports_local_model() is False

    def test_entry_8gb_can_run_local_model(self):
        """ENTRY_8GB (4-8GB) can run a 3B Q4 model."""
        router = self._make_router("entry_8gb")
        assert router._hardware_supports_local_model() is True

    def test_laptop_16gb_can_run_local_model(self):
        """LAPTOP_16GB can run a 7B-8B model."""
        router = self._make_router("laptop_16gb")
        assert router._hardware_supports_local_model() is True

    def test_workstation_32gb_can_run_local_model(self):
        """WORKSTATION_32GB can run a local model."""
        router = self._make_router("workstation_32gb")
        assert router._hardware_supports_local_model() is True

    def test_unknown_profile_cannot_run_local_model(self):
        """UNKNOWN profile is conservative — cannot run local model."""
        router = self._make_router("unknown")
        assert router._hardware_supports_local_model() is False

    def test_monologue_turn_is_never_deferred(self):
        """Cognitive monologue turns (advance_turn) are never deferred (H8, §11.3)."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.COGNITIVE_MONOLOGUE) is False

    def test_monologue_turn_is_never_offloaded(self):
        """Cognitive monologue turns are never offloaded to the peer (§11.3)."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.COGNITIVE_MONOLOGUE) is False

    def test_interactive_user_is_deferred(self):
        """Interactive user turns are deferred to the replay queue."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.INTERACTIVE_USER) is True

    def test_interactive_user_is_offloaded(self):
        """Interactive user turns are eligible for peer offload."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.INTERACTIVE_USER) is True

    def test_high_value_event_is_deferred(self):
        """High-value event turns (Frigate/security) are deferred."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.HIGH_VALUE_EVENT) is True

    def test_high_value_event_is_offloaded(self):
        """High-value event turns are eligible for peer offload."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.HIGH_VALUE_EVENT) is True

    def test_sleep_consolidation_is_deferred(self):
        """Sleep consolidation turns are deferred (batch replay when Desktop idle)."""
        router = self._make_router("sbc_low_power")
        assert router._should_defer(TurnType.SLEEP_CONSOLIDATION) is True

    def test_sleep_consolidation_is_offloaded(self):
        """Sleep consolidation turns are eligible for peer offload."""
        router = self._make_router("sbc_low_power")
        assert router._should_offload(TurnType.SLEEP_CONSOLIDATION) is True

    async def test_sbc_low_power_falls_back_to_template_not_micro_model(self, monkeypatch):
        """On SBC_LOW_POWER with peer offline, fallback is template thoughts.

        This test verifies the full fallback chain:
        1. Peer is offline (health probe fails)
        2. Hardware profile is SBC_LOW_POWER → cannot run local model
        3. Fallback is template thoughts (not a micro-model that would OOM)
        4. For cognitive_monologue: template, no deferral
        5. For interactive_user: template as interim, deferred to queue
        """
        router = self._make_router("sbc_low_power")
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        result = await router.route(
            [{"role": "user", "content": "hey"}], "any-model",
            turn_type=TurnType.INTERACTIVE_USER,
        )
        assert result.source == "template"       # never "local_model"
        assert result.deferred is True            # interim + queued for replay
        assert len(router._deferred_queue) == 1
        assert router._deferred_queue[0]["turn_type"] == "interactive_user"

    async def test_sbc_monologue_is_template_and_never_deferred(self, monkeypatch):
        """cognitive_monologue on SBC: template, and nothing is queued (H8)."""
        router = self._make_router("sbc_low_power")
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        result = await router.route(
            [{"role": "user", "content": "tick"}], "any-model",
            turn_type=TurnType.COGNITIVE_MONOLOGUE,
        )
        assert result.source == "template"
        assert result.deferred is False
        assert router._deferred_queue == []

    async def test_monologue_never_probes_peer(self, monkeypatch):
        """Monologue turns never touch the peer (§11.3) — not even a probe."""
        router = self._make_router("sbc_low_power")
        probed = {"calls": 0}

        async def _fail_if_probed():
            probed["calls"] += 1
            return False

        monkeypatch.setattr(router, "_probe_peer_health", _fail_if_probed)
        await router.route([{"role": "user", "content": "tick"}], "m",
                           turn_type=TurnType.COGNITIVE_MONOLOGUE)
        assert probed["calls"] == 0

    async def test_monologue_on_capable_hardware_stays_local(self, monkeypatch):
        """Monologue on ENTRY_8GB runs the local model — that is its primary
        path, not a peer fallback, so fallback_used stays False."""
        router = self._make_router("entry_8gb")
        result = await router.route([{"role": "user", "content": "tick"}], "m",
                                    turn_type=TurnType.COGNITIVE_MONOLOGUE)
        assert result.source == "local_model"
        assert result.fallback_used is False

    async def test_peer_online_offloads(self, monkeypatch):
        """A reachable peer wins for every offloadable turn type."""
        router = self._make_router("sbc_low_power")
        monkeypatch.setattr(router, "_http_health_probe", lambda: True)

        result = await router.route([{"role": "user", "content": "hey"}], "m",
                                    turn_type=TurnType.INTERACTIVE_USER)
        assert result.source == "peer"
        assert result.deferred is False

    async def test_no_peer_configured_goes_straight_to_fallback(self):
        """With no peer endpoint, the probe short-circuits and the chain
        lands on template thoughts without touching the network."""
        router = ComputeRouter(hardware_profile="sbc_low_power")
        result = await router._probe_peer_health()
        assert result is False

        routed = await router.route([{"role": "user", "content": "hey"}], "m",
                                    turn_type=TurnType.INTERACTIVE_USER)
        assert routed.source == "template"
        assert routed.deferred is True

    async def test_high_value_event_uses_heuristic_and_defers(self, monkeypatch):
        """High-value events fall back to heuristic rules, queued for replay."""
        router = self._make_router("sbc_low_power")
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        result = await router.route([{"role": "user", "content": "motion"}], "m",
                                    turn_type=TurnType.HIGH_VALUE_EVENT)
        assert result.source == "heuristic"
        assert result.deferred is True

    async def test_sleep_consolidation_is_deferred_only(self, monkeypatch):
        """Sleep consolidation has no interim — it is pure deferral."""
        router = self._make_router("sbc_low_power")
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)
        result = await router.route([{"role": "user", "content": "synth"}], "m",
                                    turn_type=TurnType.SLEEP_CONSOLIDATION)
        assert result.source == "deferred"
        assert result.deferred is True

    async def test_entry_8gb_uses_local_model_before_the_peer(self, monkeypatch):
        """On ENTRY_8GB, the local 3B model is the primary offline path.

        P4b reorder: with no cloud configured, capable hardware uses the
        local model WITHOUT probing the peer — the peer is the third
        tier now, not the first, so an online peer is never preferred
        over this node's own model.
        """
        router = self._make_router("entry_8gb")
        monkeypatch.setattr(router, "_http_health_probe", lambda: True)

        result = await router.route([{"role": "user", "content": "hey"}], "m",
                                    turn_type=TurnType.INTERACTIVE_USER)
        assert result.source == "local_model"
        assert result.fallback_used is False
        assert result.fallback_from is None

    def test_failure_threshold_is_3(self):
        """§11.6: The peer health failure threshold is 3 consecutive failures."""
        router = self._make_router("sbc_low_power")
        assert router._failure_threshold == 3

    def test_consecutive_failures_starts_at_zero(self):
        """The consecutive failure counter starts at 0."""
        router = self._make_router("sbc_low_power")
        assert router._consecutive_failures == 0

    def _online_router(self):
        """A router whose peer is online, probing on every call (no cache)."""
        router = self._make_router("sbc_low_power", health_probe_interval=0.0)
        router._peer_online = True
        return router

    async def test_single_failure_does_not_transition_to_offline(self, monkeypatch):
        """§11.6: A single probe failure does NOT mark the peer offline.

        The peer stays online until 3 consecutive failures.
        """
        router = self._online_router()
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        assert await router._probe_peer_health() is True   # still online
        assert router._consecutive_failures == 1

    async def test_three_consecutive_failures_transition_to_offline(self, monkeypatch):
        """§11.6: 3 consecutive failures transition the peer to OFFLINE."""
        router = self._online_router()
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        assert await router._probe_peer_health() is True
        assert await router._probe_peer_health() is True
        assert await router._probe_peer_health() is False   # third failure
        assert router._peer_online is False

    async def test_success_resets_failure_counter(self, monkeypatch):
        """§11.6: A single successful probe resets the failure counter to 0."""
        router = self._online_router()
        probes = iter([False, False, True])
        monkeypatch.setattr(router, "_http_health_probe", lambda: next(probes))

        await router._probe_peer_health()
        await router._probe_peer_health()
        assert router._consecutive_failures == 2
        await router._probe_peer_health()
        assert router._consecutive_failures == 0
        assert router._peer_online is True

    async def test_probe_result_is_cached_within_the_interval(self, monkeypatch):
        """A burst of turns probes the peer once per interval, not per turn."""
        router = self._make_router("sbc_low_power", health_probe_interval=60.0)
        calls = {"n": 0}

        def _probe():
            calls["n"] += 1
            return True

        monkeypatch.setattr(router, "_http_health_probe", _probe)
        assert await router._probe_peer_health() is True
        assert await router._probe_peer_health() is True
        assert calls["n"] == 1

    async def test_http_probe_hits_the_health_route_with_the_token(self, monkeypatch):
        """The probe GETs /api/compute/v1/health with the bearer token, and
        resolves a peer:// endpoint to http:// like the provider does."""
        import requests

        seen = {}

        class _Resp:
            status_code = 200

        def _fake_get(url, headers=None, timeout=None):
            seen.update(url=url, headers=headers, timeout=timeout)
            return _Resp()

        monkeypatch.setattr(requests, "get", _fake_get)
        router = self._make_router("sbc_low_power", health_probe_interval=0.0)
        router.peer_endpoint = "peer://desktop.lan:8000"

        assert await router._probe_peer_health() is True
        assert seen["url"] == "http://desktop.lan:8000/api/compute/v1/health"
        assert seen["headers"]["Authorization"] == "Bearer test-token"

    async def test_http_probe_swallows_connection_errors(self, monkeypatch):
        """An unreachable peer is an ordinary outcome: the probe returns False."""
        import requests

        def _boom(url, headers=None, timeout=None):
            raise requests.ConnectionError("no route to host")

        monkeypatch.setattr(requests, "get", _boom)
        router = self._make_router("sbc_low_power", health_probe_interval=0.0)
        assert await router._probe_peer_health() is False

    async def test_replay_deferred_still_awaits_the_phase_9_transport(self):
        """Draining the queue needs the peer generation call (Phase 9.3) —
        until then the stub stays honest and raises instead of pretending."""
        router = self._make_router("sbc_low_power")
        with pytest.raises(NotImplementedError):
            await router.replay_deferred()
