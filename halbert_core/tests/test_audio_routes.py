# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""/api/audio/status: live pipeline state with a static fallback.

Until the pipeline coordinator is wired onto ``app.state.audio_coordinator``
(O2), the endpoint must return today's static payload unchanged. Once a
coordinator exists, its ``get_status()`` dict is returned verbatim; if that
call raises, the endpoint falls back to the static payload rather than 500ing.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.dashboard.routes.audio import router
from halbert_core.audio.config import AudioConfig


@pytest.fixture
def audio_env(monkeypatch):
    """Deterministic audio availability + config for the route module."""
    monkeypatch.setattr(
        "halbert_core.dashboard.routes.audio.is_audio_available", lambda: True
    )
    cfg = AudioConfig()
    monkeypatch.setattr("halbert_core.dashboard.routes.audio.load_config", lambda: cfg)
    return cfg


@pytest.fixture
def client(audio_env):
    """Fresh app mounting the audio router exactly as app.py mounts it."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _static_payload(cfg=None):
    from halbert_core.dashboard.routes.audio import is_audio_available

    cfg = cfg or AudioConfig()
    return {
        "enabled": cfg.enabled,
        "available": is_audio_available(),
        "sherpa_onnx_installed": is_audio_available(),
        "state": "idle",
        "engines": {
            "vad": is_audio_available(),
            "asr": is_audio_available(),
            "tts": is_audio_available() and cfg.tts.enabled,
            "speaker_id": is_audio_available() and cfg.speaker_id.enabled,
            "audio_tagger": is_audio_available() and cfg.acoustic_events.enabled,
        },
    }


class _StubCoordinator:
    def __init__(self, status=None, raises=None):
        self._status = status if status is not None else {}
        self._raises = raises
        self.calls = 0

    def get_status(self):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._status


def test_no_coordinator_returns_static_payload(client, audio_env):
    """Regression lock: without app.state.audio_coordinator the payload is
    byte-identical to today's static response."""
    app = client.app
    assert not hasattr(app.state, "audio_coordinator")

    r = client.get("/api/audio/status")
    assert r.status_code == 200, r.text
    assert r.json() == _static_payload(audio_env)
    assert r.json()["state"] == "idle"


def test_coordinator_status_returned_verbatim(client, monkeypatch, audio_env):
    stub = _StubCoordinator(
        status={"state": "listening", "level": 0.42, "engines": {"asr": "live"}}
    )
    client.app.state.audio_coordinator = stub
    # The live coordinator path must not consult config/availability at all.
    monkeypatch.setattr(
        "halbert_core.dashboard.routes.audio.load_config",
        lambda: (_ for _ in ()).throw(AssertionError("load_config called on live path")),
    )

    r = client.get("/api/audio/status")
    assert r.status_code == 200, r.text
    assert r.json() == {"state": "listening", "level": 0.42, "engines": {"asr": "live"}}
    assert stub.calls == 1


def test_raising_coordinator_falls_back_to_static_payload(client, audio_env):
    stub = _StubCoordinator(raises=RuntimeError("pipeline blew up"))
    client.app.state.audio_coordinator = stub

    r = client.get("/api/audio/status")
    assert r.status_code == 200, r.text
    assert r.json() == _static_payload(audio_env)
    assert stub.calls == 1