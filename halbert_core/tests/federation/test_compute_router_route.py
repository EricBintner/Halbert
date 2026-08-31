# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""U6 S4/W18 + P4b: ComputeRouter.route() decision matrix + health probe.

route() was a NotImplementedError stub; the U6 tests pinned the
peer-first chain. P4b reordered it (singular-entity handoff §8): cloud
is the primary tier for every turn type, the local model is tried
before the peer when the cloud is unreachable, and no-AI is the last
resort under the (degraded) template tier. Cognitive monologue is still
never sent to the peer and never deferred (§11.3 / H8); offload-only
hardware (SBC_LOW_POWER) still goes to template thoughts with deferral
per turn type (H7).
"""

import pytest

from halbert_core.federation.compute_router import ComputeRouter, TurnType


def _router(profile="sbc_low_power", peer="http://desktop.lan:8000", **kwargs):
    return ComputeRouter(peer_endpoint=peer, peer_token="tok",
                         hardware_profile=profile, **kwargs)


class _FakeProbe:
    """ConnectivityProbe stand-in — no network, controllable."""

    def __init__(self, online=True):
        self.online = online
        self.calls = 0

    def is_online(self):
        self.calls += 1
        return self.online


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

    async def test_capable_hardware_prefers_local_over_peer(self):
        """P4b reorder pin: with no cloud configured, the local model is
        this node's primary path — chosen before the peer is even probed."""
        router = _router(profile="entry_8gb")
        _force_online(router)  # an ONLINE peer must still lose to local
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "local_model"
        assert result.fallback_used is False
        assert result.fallback_from is None

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


class TestCloudFirstChain:
    """P4b: cloud primary, local second, peer third, template fourth,
    no-AI last — with the ConnectivityProbe deciding the cloud tier."""

    async def test_cloud_online_is_primary_for_every_turn_type(self):
        probe = _FakeProbe(online=True)
        for turn_type in TurnType:
            router = _router(cloud_enabled=True, connectivity=probe)
            result = await router.route([{"role": "user", "content": "x"}], "m",
                                        turn_type=turn_type)
            assert result.source == "cloud", turn_type
            assert result.fallback_used is False
            assert result.deferred is False

    async def test_monologue_goes_to_cloud_not_peer(self):
        """§11.3 forbids the PEER for monologue (GPU flood) — cloud is fine:
        without it an always-on HA node's cognition would be template-only
        forever, which is not the corrected architecture."""
        probe = _FakeProbe(online=True)
        router = _router(cloud_enabled=True, connectivity=probe)
        _force_online(router)
        result = await router.route([{"role": "user", "content": "tick"}], "m",
                                    TurnType.COGNITIVE_MONOLOGUE)
        assert result.source == "cloud"

    async def test_cloud_offline_capable_hardware_falls_back_to_local(self):
        probe = _FakeProbe(online=False)
        router = _router(profile="entry_8gb", cloud_enabled=True, connectivity=probe)
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "local_model"
        assert result.fallback_used is True
        assert result.fallback_from == "cloud"

    async def test_cloud_offline_sbc_uses_peer_before_template(self):
        probe = _FakeProbe(online=False)
        router = _router(profile="sbc_low_power", cloud_enabled=True,
                         connectivity=probe)
        _force_online(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "peer"
        assert result.fallback_used is True
        assert result.fallback_from == "cloud"

    async def test_cloud_offline_peer_offline_lands_on_template(self):
        probe = _FakeProbe(online=False)
        router = _router(profile="sbc_low_power", cloud_enabled=True,
                         connectivity=probe)
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m",
                                    TurnType.INTERACTIVE_USER)
        assert result.source == "template"
        assert result.fallback_used is True
        assert result.fallback_from == "peer"
        assert result.deferred is True

    async def test_no_ai_when_template_tier_is_disabled(self):
        """The last tier: no cloud, no local model, no peer, templates off —
        the entity is honestly unconscious instead of faking a reply."""
        probe = _FakeProbe(online=False)
        router = _router(cloud_enabled=True, connectivity=probe,
                         template_enabled=False)
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m",
                                    TurnType.INTERACTIVE_USER)
        assert result.source == "none"
        assert result.deferred is True  # still queued for replay
        assert "no-AI" in result.reason

    async def test_cloud_disabled_never_touches_the_connectivity_probe(self):
        """No cloud configured → no probe call: the offline chain must not
        pay for (or depend on) a network probe it cannot use."""
        probe = _FakeProbe(online=True)
        router = _router(profile="sbc_low_power", connectivity=probe)
        _force_offline(router)
        result = await router.route([{"role": "user", "content": "hi"}], "m")
        assert result.source == "template"
        assert probe.calls == 0


class TestWakeOnLanFallback:
    """P6b: before the template tier, try to wake a sleeping workstation —
    only for turns that can afford the boot wait."""

    @pytest.fixture
    def wol_peers(self, tmp_path):
        from halbert_core.federation.peers_config import PeersConfig
        cfg = PeersConfig(config_path=tmp_path / "peers.json")
        cfg.add_peer(
            "desk", "Mac Studio", "compute_provider", raw_token="t",
            endpoint="http://desktop.lan:8000",
            capabilities=["gpu_llm"],
            wol_enabled=True, wol_mac="AA:BB:CC:DD:EE:FF",
            wol_broadcast="192.168.1.255",
        )
        return cfg

    def _wol_router(self, wol_peers, **kwargs):
        return _router(
            cloud_enabled=kwargs.pop("cloud_enabled", True),
            connectivity=_FakeProbe(online=False),
            peers_config=wol_peers,
            wol_wait_timeout=kwargs.pop("wol_wait_timeout", 0.2),
            wol_poll_interval=kwargs.pop("wol_poll_interval", 0.01),
            **kwargs,
        )

    async def test_sleep_consolidation_wakes_peer_and_offloads(
        self, wol_peers, monkeypatch,
    ):
        sends = []

        def fake_send(mac, broadcast):
            sends.append((mac, broadcast))
            return True

        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual", fake_send)
        # Probe fails on route()'s first check, succeeds on the wake poll.
        probes = iter([False, True])
        router = self._wol_router(wol_peers)
        monkeypatch.setattr(router, "_http_health_probe", lambda: next(probes))

        result = await router.route([{"role": "user", "content": "synth"}], "m",
                                    TurnType.SLEEP_CONSOLIDATION)
        assert result.source == "peer"
        assert "Wake-on-LAN" in result.reason
        assert sends == [("AA:BB:CC:DD:EE:FF", "192.168.1.255")]

    async def test_high_value_event_wakes_peer(self, wol_peers, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: True)
        probes = iter([False, True])
        router = self._wol_router(wol_peers)
        monkeypatch.setattr(router, "_http_health_probe", lambda: next(probes))
        result = await router.route([{"role": "user", "content": "motion"}], "m",
                                    TurnType.HIGH_VALUE_EVENT)
        assert result.source == "peer"

    async def test_interactive_user_gets_template_without_waking(
        self, wol_peers, monkeypatch,
    ):
        """A voice interaction cannot hold the user through a workstation
        boot — interactive turns take the degraded template immediately."""
        sends = []
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: sends.append(mac) or True)
        router = self._wol_router(wol_peers)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        result = await router.route([{"role": "user", "content": "hi"}], "m",
                                    TurnType.INTERACTIVE_USER)
        assert result.source == "template"
        assert result.deferred is True
        assert sends == []

    async def test_monologue_never_wakes(self, wol_peers, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: True)
        router = self._wol_router(wol_peers)
        monkeypatch.setattr(router, "_http_health_probe", lambda: True)
        result = await router.route([{"role": "user", "content": "tick"}], "m",
                                    TurnType.COGNITIVE_MONOLOGUE)
        assert result.source == "template"
        assert result.deferred is False

    async def test_wake_timeout_falls_through_to_template(
        self, wol_peers, monkeypatch,
    ):
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: True)
        router = self._wol_router(wol_peers)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        result = await router.route([{"role": "user", "content": "synth"}], "m",
                                    TurnType.SLEEP_CONSOLIDATION)
        assert result.source == "deferred"
        assert result.deferred is True
        assert result.fallback_from == "peer"

    async def test_failed_send_skips_the_wait(self, wol_peers, monkeypatch):
        """If no magic packet could be sent, there is nothing to wait for."""
        import time as _time
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: False)
        router = self._wol_router(wol_peers, wol_wait_timeout=5.0)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        started = _time.monotonic()
        result = await router.route([{"role": "user", "content": "synth"}], "m",
                                    TurnType.SLEEP_CONSOLIDATION)
        assert _time.monotonic() - started < 1.0
        assert result.source == "deferred"

    async def test_no_wol_peers_means_no_wake(self, tmp_path, monkeypatch):
        from halbert_core.federation.peers_config import PeersConfig
        cfg = PeersConfig(config_path=tmp_path / "peers.json")
        cfg.add_peer("desk", "Mac Studio", "compute_provider", raw_token="t")
        sends = []
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: sends.append(mac) or True)
        router = self._wol_router(cfg)
        monkeypatch.setattr(router, "_http_health_probe", lambda: False)

        result = await router.route([{"role": "user", "content": "synth"}], "m",
                                    TurnType.SLEEP_CONSOLIDATION)
        assert result.source == "deferred"
        assert sends == []

    async def test_successful_wake_refreshes_the_cached_probe(
        self, wol_peers, monkeypatch,
    ):
        """After a wake, the very next turn reaches the peer without
        re-probing — the wake wired the online state back into the cache."""
        monkeypatch.setattr(
            "halbert_core.federation.compute_router.send_wol_packet_dual",
            lambda mac, broadcast: True)
        probes = iter([False, True])
        router = self._wol_router(wol_peers)
        monkeypatch.setattr(router, "_http_health_probe", lambda: next(probes))
        await router.route([{"role": "user", "content": "synth"}], "m",
                           TurnType.SLEEP_CONSOLIDATION)
        assert router._peer_online is True
        assert router._consecutive_failures == 0

        # Next turn: peer hit straight from the cached probe (no more
        # probe calls left in the iterator — a second call would raise
        # StopIteration and fail the test loudly).
        result = await router.route([{"role": "user", "content": "hi"}], "m",
                                    TurnType.INTERACTIVE_USER)
        assert result.source == "peer"
