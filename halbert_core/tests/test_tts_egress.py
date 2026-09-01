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
import logging
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


# ---------------------------------------------------------------------------
# State machine speak-path hook
# ---------------------------------------------------------------------------

class _Mod:
    """ResponseModality stand-in: only ``value`` is read on this path."""

    value = "voice"


class _FakeCtx:
    recommended_modality = _Mod()


class _FakeSegment:
    def __init__(self, text, is_spoken=True, rate=1.0):
        self.text = text
        self.is_spoken = is_spoken
        self.role = None
        self.prosody = type("P", (), {"rate": rate, "volume": 1.0, "whisper": False})()


class _FakePayload:
    speech_text = "spoken words"
    display_text = "spoken words"

    def __init__(self, *segments):
        self.segments = list(segments)


class _ChunkedTTS:
    """PiperTTS stand-in: records calls, yields deterministic PCM chunks.

    ``cancel_after`` simulates VAD barge-in: the token fires after that many
    chunks and the generator stops (exactly how the real engine aborts).
    """

    def __init__(self, chunks=(b"\x01\x02", b"\x03\x04"), cancel_after=None):
        self._speed = 1.0
        self._sample_rate = 22050
        self._chunks = tuple(chunks)
        self._cancel_after = cancel_after
        self.calls = []  # (text, speed, cancel_token)

    async def synthesize(self, text, cancel_token=None):
        self.calls.append((text, self._speed, cancel_token))
        for i, chunk in enumerate(self._chunks):
            if self._cancel_after is not None and i >= self._cancel_after:
                if cancel_token is not None:
                    cancel_token.trigger()
                return
            yield chunk


class _RecordingHub:
    """TtsEgressHub stand-in with the surface the hook touches.

    ``fire_token_on_end`` simulates a barge-in landing in the window between
    one segment's end frame and the next segment's synthesis: the session's
    registered token (the hook's own) fires as the end frame goes out.
    """

    def __init__(self, *subscribed_sessions, fire_token_on_end=False):
        self._subscribed = set(subscribed_sessions)
        self.published = []
        self.registered_tokens = {}
        self.token_registrations = []  # every (session, token) ever registered
        self.cleared_sessions = []
        self.pipeline = None
        self._fire_token_on_end = fire_token_on_end

    def has_subscribers(self, session_id):
        return session_id in self._subscribed

    async def publish(self, session_id, data):
        self.published.append((session_id, data))
        if self._fire_token_on_end and data == {"type": "end"}:
            token = self.registered_tokens.get(session_id)
            if token is not None:
                token.trigger()

    def register_cancel_token(self, session_id, token):
        self.token_registrations.append((session_id, token))
        self.registered_tokens[session_id] = token

    def clear_cancel_token(self, session_id):
        self.cleared_sessions.append(session_id)
        self.registered_tokens.pop(session_id, None)


class _StreamingLLM:
    """Minimal streaming client — the RESPONDING path only needs these."""

    async def stream(self, messages, on_model_selected=None, **kwargs):
        for word in ("The", "answer", "is", "42."):
            yield word + " "

    async def chat(self, messages, tools=None, on_model_selected=None, **kwargs):
        return type("R", (), {"content": "The answer is 42.", "tool_calls": None})()


class _EmptyService:
    async def search(self, query, limit=5):
        return []

    async def recall(self, query, limit=5):
        return []

    async def store_interaction(self, **kw):
        return None


def _build_agent():
    from halbert_core.agents.state_machine import AgentStateMachine
    from halbert_core.tools import ToolSafetyFramework, ToolExecutor
    from halbert_core.context import ContextAssembler, TokenCounter
    from halbert_core.prompts import AgentPromptBuilder

    return AgentStateMachine(
        llm_client=_StreamingLLM(),
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        context_assembler=ContextAssembler(
            rag_service=_EmptyService(),
            memory_service=_EmptyService(),
            discovery_service=_EmptyService(),
            token_counter=TokenCounter(),
        ),
        prompt_builder=AgentPromptBuilder(),
        max_loops=3,
    )


def _voice_turn_patches(monkeypatch, payload, pronounce=lambda t: t):
    """Force the RESPONDING modality path into voice mode with a fake
    demuxed payload, without needing the Haloysius resolver machinery."""
    from halbert_core.integrations import modality_wiring as mw

    ctx = _FakeCtx()
    monkeypatch.setattr(mw, "build_modality_context", lambda *a, **k: ctx)
    monkeypatch.setattr(mw, "resolve_turn_modality", lambda c: c)
    monkeypatch.setattr(mw, "defang_user_input", lambda t: t)
    monkeypatch.setattr(mw, "should_speak", lambda c: True)
    monkeypatch.setattr(mw, "apply_pronunciation", pronounce)
    monkeypatch.setattr(mw, "demux_response", lambda *a, **k: payload)
    monkeypatch.setattr(mw, "get_speech_text", lambda p: p.speech_text)
    monkeypatch.setattr(mw, "get_display_text", lambda p: p.display_text)
    return ctx


def _patch_hub(monkeypatch, hub):
    from halbert_core.dashboard.routes import tts_egress
    monkeypatch.setattr(tts_egress, "get_tts_egress_hub", lambda: hub)


SESSION = "sess-tts"


class TestStateMachineTtsEgressHook:

    async def test_no_subscriber_means_no_synthesis(self, monkeypatch):
        """The hub gate: a voice turn with no browser listening synthesizes
        nothing — the hook must not so much as touch Piper."""
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub()  # nobody subscribed
        _patch_hub(monkeypatch, hub)
        tts = _ChunkedTTS()
        agent = _build_agent()
        agent._egress_tts = tts

        events = [e async for e in agent.process("hello", session_id=SESSION)]

        assert tts.calls == []
        assert hub.published == []
        assert [e.type for e in events if e.type == "speech_segment"]

    async def test_spoken_segments_stream_begin_pcm_end(self, monkeypatch):
        """With a subscriber, each spoken segment is synthesized with the
        post-pronunciation text and published as begin -> PCM chunks -> end,
        in order, while the speech_segment SSE events still go out."""
        payload = _FakePayload(
            _FakeSegment("Hello there", rate=1.0),
            _FakeSegment("(never spoken)", is_spoken=False),
            _FakeSegment("Second segment", rate=1.5),
        )
        _voice_turn_patches(
            monkeypatch, payload, pronounce=lambda t: t + " (said)"
        )
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)
        tts = _ChunkedTTS()
        agent = _build_agent()
        agent._egress_tts = tts

        events = [e async for e in agent.process("hello", session_id=SESSION)]

        begin = {"type": "begin", "sample_rate": 22050, "format": "s16le"}
        # Two spoken segments -> two full begin/chunks/end cycles.
        assert hub.published == [
            (SESSION, begin),
            (SESSION, b"\x01\x02"),
            (SESSION, b"\x03\x04"),
            (SESSION, {"type": "end"}),
            (SESSION, begin),
            (SESSION, b"\x01\x02"),
            (SESSION, b"\x03\x04"),
            (SESSION, {"type": "end"}),
        ]
        # Synthesis used the post-pronunciation segment text (what the
        # ribbon shows), with each segment's rate as Piper speed.
        assert [c[0] for c in tts.calls] == [
            "Hello there (said)",
            "Second segment (said)",
        ]
        assert [c[1] for c in tts.calls] == [1.0, 1.5]
        # The SSE speech segments still reached the stream (2, not 3).
        seg_events = [e for e in events if e.type == "speech_segment"]
        assert len(seg_events) == 2
        assert seg_events[0].data["text"] == "Hello there (said)"
        # Speed override restored after each segment.
        assert tts._speed == 1.0
        # The turn still completes normally.
        assert any(e.type == "response_complete" for e in events)
        # The barge-in token was registered for the session and cleared.
        assert SESSION in hub.cleared_sessions
        assert SESSION not in hub.registered_tokens

    async def test_barge_in_between_chunks_publishes_cancelled(self, monkeypatch):
        """A token fired mid-stream (VAD barge-in) stops synthesis and ends
        the segment with {"type": "cancelled"} instead of end."""
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)
        tts = _ChunkedTTS(cancel_after=1)  # fire after the first chunk
        agent = _build_agent()
        agent._egress_tts = tts

        [e async for e in agent.process("hello", session_id=SESSION)]

        assert hub.published == [
            (SESSION, {"type": "begin", "sample_rate": 22050, "format": "s16le"}),
            (SESSION, b"\x01\x02"),
            (SESSION, {"type": "cancelled"}),
        ]

    async def test_barge_in_between_segments_publishes_cancelled(self, monkeypatch):
        """A token firing in the window between segment 1's end and segment
        2's first chunk must still reach the browser: without the turn-level
        check, segment 2 never ``began`` and the browser would play the
        already-scheduled clip to completion. The remaining segment is also
        never synthesized — no wasted sherpa-onnx pass."""
        payload = _FakePayload(
            _FakeSegment("First segment"),
            _FakeSegment("Second segment"),
        )
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION, fire_token_on_end=True)
        _patch_hub(monkeypatch, hub)
        tts = _ChunkedTTS()
        agent = _build_agent()
        agent._egress_tts = tts

        [e async for e in agent.process("hello", session_id=SESSION)]

        assert hub.published == [
            (SESSION, {"type": "begin", "sample_rate": 22050, "format": "s16le"}),
            (SESSION, b"\x01\x02"),
            (SESSION, b"\x03\x04"),
            (SESSION, {"type": "end"}),
            # Segment 2 was never synthesized; the cancelled frame for it
            # comes from the turn-level check after the loop.
            (SESSION, {"type": "cancelled"}),
        ]
        # No generation pass was spent on the barged-in segment.
        assert [c[0] for c in tts.calls] == ["First segment"]

    async def test_pipeline_token_is_used_when_the_pipeline_runs(self, monkeypatch):
        """The hook mints its barge-in token from the coordinator when the
        pipeline is up, so VAD barge-in cancels browser playback too — and
        releases the coordinator's slot when the turn ends so it cannot go
        stale and eat the next VAD barge-in."""
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)

        class _FakePipeline:
            def __init__(self):
                self.tokens = []
                self.released = []

            def create_barge_in_token(self):
                token = _FakeToken()
                self.tokens.append(token)
                return token

            def release_barge_in_token(self, token):
                self.released.append(token)

        pipeline = _FakePipeline()
        hub.pipeline = pipeline
        _patch_hub(monkeypatch, hub)
        tts = _ChunkedTTS()
        agent = _build_agent()
        agent._egress_tts = tts

        [e async for e in agent.process("hello", session_id=SESSION)]

        assert len(pipeline.tokens) == 1
        # The token handed to PiperTTS is the coordinator's.
        assert tts.calls[0][2] is pipeline.tokens[0]
        # ...and it was registered with the hub for cancel control frames
        # (cleared again when the turn ends, hence the history check).
        assert hub.token_registrations == [(SESSION, pipeline.tokens[0])]
        assert SESSION not in hub.registered_tokens
        # The coordinator's active-token slot was handed back.
        assert pipeline.released == [pipeline.tokens[0]]

    async def test_hook_is_silent_without_a_tts(self, monkeypatch):
        """No voice backend / no Piper model: the hook steps aside and the
        turn still completes — voice egress is strictly optional."""
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)
        import haloysius.seam as seam_mod
        monkeypatch.setattr(seam_mod, "get_app_seam", lambda: None)
        agent = _build_agent()
        # _egress_tts left unset and the seam has nothing -> stays silent

        events = [e async for e in agent.process("hello", session_id=SESSION)]

        assert hub.published == []
        assert any(e.type == "response_complete" for e in events)

    async def test_tts_failure_is_non_fatal(self, monkeypatch):
        """A synthesize that raises must not break the turn — the events
        above the hook have already been yielded to the user."""
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)

        class _BrokenTTS:
            _speed = 1.0
            _sample_rate = 22050

            async def synthesize(self, text, cancel_token=None):
                raise RuntimeError("sherpa-onnx exploded")
                yield b""  # pragma: no cover

        agent = _build_agent()
        agent._egress_tts = _BrokenTTS()

        events = [e async for e in agent.process("hello", session_id=SESSION)]

        assert hub.published == []
        assert any(e.type == "response_complete" for e in events)
        assert any(e.type == "speech_segment" for e in events)

    async def test_hook_failure_warns_once_then_stays_quiet(
        self, monkeypatch, caplog
    ):
        """The first egress failure is a wiring problem an operator should
        see; every later one is the deployment's steady state — warning
        once, debug after (the machine is the process singleton)."""
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)

        class _BrokenTTS:
            _speed = 1.0
            _sample_rate = 22050

            async def synthesize(self, text, cancel_token=None):
                raise RuntimeError("sherpa-onnx exploded")
                yield b""  # pragma: no cover

        agent = _build_agent()
        agent._egress_tts = _BrokenTTS()

        with caplog.at_level(
            logging.WARNING, logger="halbert.agents.state_machine"
        ):
            [e async for e in agent.process("hello", session_id=SESSION)]
            [e async for e in agent.process("again", session_id=SESSION)]

        warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "TTS egress" in r.message
        ]
        assert len(warnings) == 1


class TestWakeBeforeSpeak:
    """P2: a voice turn that starts from standby raises the panel before
    the browser hears the first ``begin`` frame — talking at a black screen
    is exactly the failure the standby tiers exist to prevent. The call is
    best-effort: unavailable display hardware (every macOS dev machine)
    and even a raising wake must not break the turn."""

    @staticmethod
    def _patch_wake(monkeypatch, order=None, calls=None, raises=False):
        from halbert_core.system import display_power as dp

        def _wake():
            if calls is not None:
                calls.append("wake")
            if order is not None:
                order.append("wake")
            if raises:
                raise RuntimeError("no backlight on this bench")

        monkeypatch.setattr(dp, "wake", _wake)

    async def test_subscribed_turn_wakes_before_the_first_begin(self, monkeypatch):
        order = []
        self._patch_wake(monkeypatch, order=order)
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        original_publish = hub.publish

        async def publish(session_id, data):
            if isinstance(data, dict) and data.get("type") == "begin":
                order.append("begin")
            await original_publish(session_id, data)

        hub.publish = publish
        _patch_hub(monkeypatch, hub)
        agent = _build_agent()
        agent._egress_tts = _ChunkedTTS()

        [e async for e in agent.process("hello", session_id=SESSION)]

        assert order == ["wake", "begin"]

    async def test_wake_is_once_per_turn_not_per_segment(self, monkeypatch):
        calls = []
        self._patch_wake(monkeypatch, calls=calls)
        payload = _FakePayload(
            _FakeSegment("First segment"), _FakeSegment("Second segment")
        )
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)
        agent = _build_agent()
        agent._egress_tts = _ChunkedTTS()

        [e async for e in agent.process("hello", session_id=SESSION)]

        begins = [
            d for _s, d in hub.published
            if isinstance(d, dict) and d.get("type") == "begin"
        ]
        assert len(begins) == 2  # two segments began...
        assert calls == ["wake"]  # ...but the panel was raised once

    async def test_unsubscribed_turn_does_not_wake(self, monkeypatch):
        calls = []
        self._patch_wake(monkeypatch, calls=calls)
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub()  # nobody subscribed
        _patch_hub(monkeypatch, hub)
        tts = _ChunkedTTS()
        agent = _build_agent()
        agent._egress_tts = tts

        [e async for e in agent.process("hello", session_id=SESSION)]

        assert calls == []
        assert tts.calls == []

    async def test_a_raising_wake_does_not_break_the_turn(self, monkeypatch):
        self._patch_wake(monkeypatch, raises=True)
        payload = _FakePayload(_FakeSegment("Hello there"))
        _voice_turn_patches(monkeypatch, payload)
        hub = _RecordingHub(SESSION)
        _patch_hub(monkeypatch, hub)
        agent = _build_agent()
        agent._egress_tts = _ChunkedTTS()

        events = [e async for e in agent.process("hello", session_id=SESSION)]

        begins = [
            d for _s, d in hub.published
            if isinstance(d, dict) and d.get("type") == "begin"
        ]
        assert begins
        assert any(e.type == "response_complete" for e in events)


class TestCoordinatorTokenRelease:
    """``release_barge_in_token`` — the hook's hand-back of the
    coordinator's active-token slot (no stale tokens eating the next VAD
    barge-in)."""

    def test_release_clears_only_the_matching_token(self):
        from halbert_core.audio.config import AudioConfig
        from halbert_core.audio.pipeline import AudioPipelineCoordinator

        coord = AudioPipelineCoordinator(config=AudioConfig(enabled=True))
        token = coord.create_barge_in_token()
        assert coord._active_barge_in_token is token

        # A newer token occupies the slot: releasing the old one is a no-op.
        newer = coord.create_barge_in_token()
        coord.release_barge_in_token(token)
        assert coord._active_barge_in_token is newer

        coord.release_barge_in_token(newer)
        assert coord._active_barge_in_token is None
