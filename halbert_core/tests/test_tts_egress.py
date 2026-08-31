# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Task O3: TTS egress — Piper PCM streamed to the browser.

Covers:
- ``TtsEgressHub``: session-keyed pub/sub between the agent state machine
  (publisher) and ``/api/audio/tts`` WebSockets (subscribers). bytes publish
  as binary PCM frames, dicts as JSON text frames; dead subscribers are
  dropped, never leaked.
- The ``/api/audio/tts?session_id=...`` WebSocket route: subscription,
  disconnect cleanup, and the client "cancel" control frame.
- The state machine's speak-path hook (further down): spoken segments are
  synthesized through the voice backend's PiperTTS and published as
  begin -> PCM chunks -> end/cancelled, only when a subscriber exists.
"""

from __future__ import annotations

import asyncio
import json
from typing import List, Optional, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from halbert_core.dashboard.routes.websocket import router


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeWebSocket:
    """Records frames instead of touching a network. Optionally fails every
    send, standing in for a socket the server already saw die."""

    def __init__(self, fail: bool = False):
        self.frames: List[Tuple[str, object]] = []
        self.fail = fail

    async def send_bytes(self, data: bytes) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.frames.append(("bytes", bytes(data)))

    async def send_text(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.frames.append(("text", text))


class _FakeToken:
    """BargeInToken stand-in: records trigger()."""

    def __init__(self):
        self.triggered = False

    def trigger(self) -> None:
        self.triggered = True

    def is_set(self) -> bool:
        return self.triggered


@pytest.fixture(autouse=True)
def _fresh_hub():
    """Isolate the module singleton per test (it outlives any one app)."""
    from halbert_core.dashboard.routes.tts_egress import _reset_tts_egress_hub
    _reset_tts_egress_hub()
    yield
    _reset_tts_egress_hub()


def _hub():
    from halbert_core.dashboard.routes.tts_egress import get_tts_egress_hub
    return get_tts_egress_hub()


# ---------------------------------------------------------------------------
# Hub pub/sub
# ---------------------------------------------------------------------------

class TestTtsEgressHub:

    async def test_publish_bytes_is_a_binary_frame(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        ws = _FakeWebSocket()
        hub.subscribe("s1", ws)

        await hub.publish("s1", b"\x01\x02\x03")

        assert ws.frames == [("bytes", b"\x01\x02\x03")]

    async def test_publish_dict_is_a_json_text_frame(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        ws = _FakeWebSocket()
        hub.subscribe("s1", ws)

        await hub.publish("s1", {"type": "begin", "sample_rate": 22050})

        assert ws.frames == [
            ("text", json.dumps({"type": "begin", "sample_rate": 22050})),
        ]

    async def test_publish_to_unknown_session_is_a_noop(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()

        await hub.publish("nobody", b"\x01")  # must not raise

    async def test_dead_subscriber_is_dropped_not_leaked(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        dead = _FakeWebSocket(fail=True)
        hub.subscribe("s1", dead)

        await hub.publish("s1", b"\x01")  # raises inside -> subscriber dropped

        assert hub.has_subscribers("s1") is False
        # A later publish to the same session must not re-raise through the
        # dead socket.
        await hub.publish("s1", b"\x02")

    async def test_unsubscribe_handle_removes_only_that_subscriber(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        a, b = _FakeWebSocket(), _FakeWebSocket()
        hub.subscribe("s1", a)
        unsub = hub.subscribe("s1", b)

        unsub()

        assert hub.has_subscribers("s1") is True
        await hub.publish("s1", b"\x01")
        assert a.frames == [("bytes", b"\x01")]
        assert b.frames == []

    async def test_two_subscribers_of_one_session_both_receive(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        a, b = _FakeWebSocket(), _FakeWebSocket()
        hub.subscribe("s1", a)
        hub.subscribe("s1", b)

        await hub.publish("s1", {"type": "end"})

        assert a.frames == b.frames == [("text", json.dumps({"type": "end"}))]

    async def test_sessions_are_isolated(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        a, b = _FakeWebSocket(), _FakeWebSocket()
        hub.subscribe("s1", a)
        hub.subscribe("s2", b)

        await hub.publish("s2", b"\x01")

        assert a.frames == []
        assert b.frames == [("bytes", b"\x01")]

    async def test_has_subscribers_false_when_empty(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        assert hub.has_subscribers("s1") is False

    async def test_cancel_fires_the_registered_token_and_publishes(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        ws = _FakeWebSocket()
        hub.subscribe("s1", ws)
        token = _FakeToken()
        hub.register_cancel_token("s1", token)

        await hub.cancel("s1")

        assert token.triggered is True
        assert ws.frames == [("text", json.dumps({"type": "cancelled"}))]

    async def test_cancel_without_token_still_publishes(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        ws = _FakeWebSocket()
        hub.subscribe("s1", ws)

        await hub.cancel("s1")

        assert ws.frames == [("text", json.dumps({"type": "cancelled"}))]

    async def test_clear_cancel_token(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        token = _FakeToken()
        hub.register_cancel_token("s1", token)
        hub.clear_cancel_token("s1")
        hub.subscribe("s1", _FakeWebSocket())

        await hub.cancel("s1")

        assert token.triggered is False

    def test_set_pipeline_is_readable_back(self):
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        hub = TtsEgressHub()
        coordinator = object()
        hub.set_pipeline(coordinator)
        assert hub.pipeline is coordinator
        hub.set_pipeline(None)
        assert hub.pipeline is None

    def test_singleton_accessor_returns_one_instance(self):
        from halbert_core.dashboard.routes.tts_egress import (
            TtsEgressHub,
            get_tts_egress_hub,
        )
        assert isinstance(get_tts_egress_hub(), TtsEgressHub)
        assert get_tts_egress_hub() is get_tts_egress_hub()


# ---------------------------------------------------------------------------
# /api/audio/tts route
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Fresh app mounting the websocket router exactly as app.py mounts it
    (no prefix), plus a test-only endpoint that publishes through the hub on
    the app's own event loop — the state machine's publisher position."""
    app = FastAPI()
    app.include_router(router)
    hub = _hub()

    @app.get("/__publish/{sid}")
    async def _publish(sid: str):
        await hub.publish(sid, b"\x01\x02\x03")
        return {"ok": True}

    @app.get("/__publish_json/{sid}")
    async def _publish_json(sid: str):
        await hub.publish(sid, {"type": "end"})
        return {"ok": True}

    return TestClient(app)


class TestTtsEgressRoute:

    def test_route_registered_at_full_path(self):
        """The router is mounted without a prefix; the path string itself
        must be the public /api/audio/tts URL."""
        paths = {r.path for r in router.routes}
        assert "/api/audio/tts" in paths

    def test_closes_4400_without_session_id(self, client):
        with client.websocket_connect("/api/audio/tts") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
        assert exc.value.code == 4400

    def test_published_frames_reach_the_subscriber(self, client):
        with client.websocket_connect("/api/audio/tts?session_id=s1") as ws:
            client.get("/__publish/s1")
            assert ws.receive_bytes() == b"\x01\x02\x03"
            client.get("/__publish_json/s1")
            assert json.loads(ws.receive_text()) == {"type": "end"}

    def test_frames_for_other_sessions_do_not_arrive(self, client):
        """A subscription is scoped to one turn's session id — PCM for
        another session's browser must never cross wires."""
        with client.websocket_connect("/api/audio/tts?session_id=mine") as ws:
            client.get("/__publish/someone-else")
            client.get("/__publish_json/mine")
            assert json.loads(ws.receive_text()) == {"type": "end"}

    def test_app_state_hub_is_preferred_over_the_singleton(self, client):
        """app.py aliases the singleton onto app.state.tts_egress; when an
        app carries its own hub, the route must subscribe there (tests and
        multi-app processes), not to the module singleton."""
        from halbert_core.dashboard.routes.tts_egress import TtsEgressHub
        app_hub = TtsEgressHub()
        client.app.state.tts_egress = app_hub

        @client.app.get("/__publish_app_hub/{sid}")
        async def _publish_app_hub(sid: str):
            await app_hub.publish(sid, b"\xaa\xbb")
            return {"ok": True}

        with client.websocket_connect("/api/audio/tts?session_id=s1") as ws:
            client.get("/__publish/s1")  # singleton hub: must NOT arrive
            client.get("/__publish_app_hub/s1")
            assert ws.receive_bytes() == b"\xaa\xbb"

    def test_disconnect_unsubscribes(self, client):
        hub = _hub()
        with client.websocket_connect("/api/audio/tts?session_id=s1"):
            assert hub.has_subscribers("s1") is True
        assert hub.has_subscribers("s1") is False

    def test_cancel_control_frame_publishes_cancelled(self, client):
        """The browser can barge in over the same socket: a
        {"type": "cancel"} text frame makes the hub fire the session's
        registered token and answer with {"type": "cancelled"}."""
        hub = _hub()
        token = _FakeToken()
        hub.register_cancel_token("s1", token)

        with client.websocket_connect("/api/audio/tts?session_id=s1") as ws:
            ws.send_text(json.dumps({"type": "cancel"}))
            assert json.loads(ws.receive_text()) == {"type": "cancelled"}

        assert token.triggered is True

    def test_non_control_frames_are_ignored(self, client):
        """Unknown client frames must not kill the socket — the stream stays
        usable for later audio."""
        with client.websocket_connect("/api/audio/tts?session_id=s1") as ws:
            ws.send_text("hello?")
            ws.send_bytes(b"\x00\x00")
            client.get("/__publish_json/s1")
            assert json.loads(ws.receive_text()) == {"type": "end"}