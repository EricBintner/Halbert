# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Task O2: audio pipeline coordinator bootstrap + /api/audio/stream ingress.

Covers:
- The ``audio`` capability probe (config enabled AND sherpa-onnx importable
  — a presence check, never a variant check).
- ``AudioPipelineCoordinator.add_ingress()`` / ``get_ingress()`` — the
  public registration surface used by the dashboard bootstrap.
- The ``/api/audio/stream`` WebSocket route: binary frames from the browser
  reach the real ``WebRtcIngress`` as ``AudioChunk``s; connections are
  refused with 1013 when no coordinator (or no dashboard ingress) exists.
"""
import asyncio
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from halbert_core.audio.buffer import AudioChunk
from halbert_core.audio.config import AudioConfig
from halbert_core.audio.ingress.base import AudioIngressAdapter
from halbert_core.audio.ingress.webrtc_ingress import WebRtcIngress
from halbert_core.audio.pipeline import AudioPipelineCoordinator
from halbert_core.capabilities import (
    ALL_CAPABILITIES,
    CAP_AUDIO,
    CapabilityRegistry,
    _PRESET_HOME,
    _PRESET_SYSADMIN,
    _probe_audio,
)
from halbert_core.dashboard.routes.websocket import router


# ---------------------------------------------------------------------------
# Capability probe — presence check, not a variant gate
# ---------------------------------------------------------------------------

class TestAudioCapabilityProbe:
    def test_audio_capability_registered(self):
        assert CAP_AUDIO == "audio"
        assert CAP_AUDIO in ALL_CAPABILITIES

    def test_audio_preset_default_true_both_variants(self):
        """Both a sysadmin node and a home node can be the voice terminal."""
        assert _PRESET_SYSADMIN[CAP_AUDIO] is True
        assert _PRESET_HOME[CAP_AUDIO] is True

    def test_probe_true_when_config_enabled_and_sherpa_available(self, monkeypatch):
        monkeypatch.setattr(
            "halbert_core.audio.config.load_config",
            lambda: AudioConfig(enabled=True),
        )
        monkeypatch.setattr(
            "halbert_core.audio.is_available.is_audio_available",
            lambda: True,
        )
        assert _probe_audio() is True

    def test_probe_false_when_config_disabled(self, monkeypatch):
        """audio_config.yml enabled: false disables the capability."""
        monkeypatch.setattr(
            "halbert_core.audio.config.load_config",
            lambda: AudioConfig(enabled=False),
        )
        monkeypatch.setattr(
            "halbert_core.audio.is_available.is_audio_available",
            lambda: True,
        )
        assert _probe_audio() is False

    def test_probe_false_when_sherpa_missing(self, monkeypatch):
        """No inference runtime -> no audio capability (config alone is not enough)."""
        monkeypatch.setattr(
            "halbert_core.audio.config.load_config",
            lambda: AudioConfig(enabled=True),
        )
        monkeypatch.setattr(
            "halbert_core.audio.is_available.is_audio_available",
            lambda: False,
        )
        assert _probe_audio() is False

    def test_probe_false_on_error(self, monkeypatch):
        """A broken config file must not crash the registry probe."""
        def boom():
            raise RuntimeError("bad yaml")

        monkeypatch.setattr("halbert_core.audio.config.load_config", boom)
        assert _probe_audio() is False

    def test_being_yml_override_wins_over_probe(self):
        """capabilities: {audio: false} is the operator kill switch."""
        reg = CapabilityRegistry()
        reg._load_config = lambda: ("sysadmin", {CAP_AUDIO: False})
        probes = {CAP_AUDIO: lambda: True}
        with patch("halbert_core.capabilities._PROBES", probes):
            reg.probe()
        assert reg.has(CAP_AUDIO) is False

    def test_being_yml_override_can_force_on(self):
        """capabilities: {audio: true} forces the pipeline on even without
        sherpa-onnx (the coordinator degrades gracefully to no observations)."""
        reg = CapabilityRegistry()
        reg._load_config = lambda: ("home", {CAP_AUDIO: True})
        probes = {CAP_AUDIO: lambda: False}
        with patch("halbert_core.capabilities._PROBES", probes):
            reg.probe()
        assert reg.has(CAP_AUDIO) is True


# ---------------------------------------------------------------------------
# Coordinator add_ingress / get_ingress — the public registration surface
# ---------------------------------------------------------------------------

class _FakeAdapter(AudioIngressAdapter):
    """Minimal ingress adapter recording start/stop calls."""

    def __init__(self, source_type="test", area_id=""):
        super().__init__(source_type=source_type, area_id=area_id)
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def chunks(self):
        yield  # pragma: no cover


class _BrokenStartAdapter(_FakeAdapter):
    async def start(self) -> None:
        raise RuntimeError("no audio device")


def _coordinator() -> AudioPipelineCoordinator:
    return AudioPipelineCoordinator(config=AudioConfig(enabled=True))


class TestAddIngress:
    def test_add_ingress_starts_and_registers_adapter(self):
        coord = _coordinator()
        adapter = _FakeAdapter(source_type="dashboard", area_id="voice")

        registered = asyncio.run(coord.add_ingress(adapter))

        assert registered is True
        assert adapter.started is True
        assert coord.get_ingress("dashboard") is adapter

    def test_get_ingress_returns_none_when_absent(self):
        coord = _coordinator()
        assert coord.get_ingress("dashboard") is None

    def test_get_ingress_matches_on_source_type(self):
        coord = _coordinator()
        a = _FakeAdapter(source_type="local_mic")
        b = _FakeAdapter(source_type="dashboard")

        asyncio.run(coord.add_ingress(a))
        asyncio.run(coord.add_ingress(b))

        assert coord.get_ingress("dashboard") is b
        assert coord.get_ingress("local_mic") is a
        assert coord.get_ingress("wyoming_satellite") is None

    def test_add_ingress_isolated_on_adapter_failure(self):
        """An adapter whose start() raises is not registered and does not
        take the coordinator (or the dashboard bootstrap) down."""
        coord = _coordinator()
        broken = _BrokenStartAdapter(source_type="dashboard")

        registered = asyncio.run(coord.add_ingress(broken))

        assert registered is False
        assert coord.get_ingress("dashboard") is None

    def test_added_adapter_appears_in_status(self):
        coord = _coordinator()
        adapter = _FakeAdapter(source_type="dashboard", area_id="voice")
        asyncio.run(coord.add_ingress(adapter))

        sources = coord.get_status()["ingress_sources"]
        assert any(s["source_type"] == "dashboard" for s in sources)


# ---------------------------------------------------------------------------
# /api/audio/stream route
# ---------------------------------------------------------------------------

class _StubCoordinator:
    """Coordinator stand-in: only get_ingress matters to the route."""

    def __init__(self, *adapters):
        self._adapters = list(adapters)

    def get_ingress(self, source_type):
        return next(
            (a for a in self._adapters if a.source_type == source_type),
            None,
        )


@pytest.fixture
def client():
    """Fresh app mounting the websocket router exactly as app.py mounts it
    (no prefix — WS paths carry their full path string)."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _wait_for(predicate, timeout=5.0):
    """The WS handler runs on the TestClient portal thread; poll until the
    frame has been processed (or fail on timeout)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class TestAudioStreamRoute:
    def test_closes_1013_when_no_coordinator(self, client):
        """Pipeline not bootstrapped: tell the browser to try again later."""
        assert not hasattr(client.app.state, "audio_coordinator")
        with client.websocket_connect("/api/audio/stream") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_bytes()
        assert exc.value.code == 1013

    def test_closes_1013_when_coordinator_has_no_dashboard_ingress(self, client):
        client.app.state.audio_coordinator = _StubCoordinator()
        with client.websocket_connect("/api/audio/stream") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_bytes()
        assert exc.value.code == 1013

    def test_binary_frames_enqueue_audio_chunks(self, client):
        """The real WebRtcIngress.handle_websocket path: a binary WS frame of
        16kHz s16le mono PCM becomes an AudioChunk on the ingress queue."""
        ingress = WebRtcIngress(area_id="dashboard_voice")
        asyncio.run(ingress.start())  # set _running so the receive loop spins
        client.app.state.audio_coordinator = _StubCoordinator(ingress)

        pcm = b"\x01\x02\x03\x04\x05\x06"  # 3 samples, s16le mono
        with client.websocket_connect("/api/audio/stream") as ws:
            ws.send_bytes(pcm)

        assert _wait_for(lambda: ingress._chunk_queue.qsize() == 1)
        chunk = ingress._chunk_queue.get_nowait()
        assert isinstance(chunk, AudioChunk)
        assert chunk.pcm == pcm
        assert chunk.samples == 3
        assert chunk.source == "dashboard"
        assert chunk.area_id == "dashboard_voice"

    def test_route_registered_at_full_path(self):
        """The router is mounted without a prefix; the path string itself
        must be the public /api/audio/stream URL."""
        paths = {r.path for r in router.routes}
        assert "/api/audio/stream" in paths