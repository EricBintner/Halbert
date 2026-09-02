# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""VM-STT: a spoken turn has to reach the page that spoke it.

``AudioPipelineCoordinator.on_voice_turn`` was declared and invoked by the
speech track, and nothing ever set it — so a completed voice turn produced a
``VoiceTurnObservation`` that went nowhere. ``/voice``'s "Tap to speak" ended
in an empty turn and the on-screen keyboard was the only working input.

The status endpoint deliberately never carries the transcript (it answers who
spoke, not what was said), so the return path is the microphone uplink the
browser is already holding open.
"""
from __future__ import annotations

import pytest

from halbert_core.audio.ingress.webrtc_ingress import WebRtcIngress


class _FakeSocket:
    def __init__(self, fails: bool = False):
        self.sent: list[str] = []
        self._fails = fails

    async def send_text(self, payload: str) -> None:
        if self._fails:
            raise RuntimeError("client went away")
        self.sent.append(payload)


class TestUplinkBroadcast:

    @pytest.mark.asyncio
    async def test_a_transcript_reaches_every_connected_browser(self):
        ingress = WebRtcIngress(area_id="dashboard_voice")
        a, b = _FakeSocket(), _FakeSocket()
        ingress._active_websockets.extend([a, b])

        sent = await ingress.broadcast({"type": "transcript", "text": "hello"})

        assert sent == 2
        assert '"transcript"' in a.sent[0]
        assert "hello" in b.sent[0]

    @pytest.mark.asyncio
    async def test_a_dead_socket_is_dropped_not_retried(self):
        ingress = WebRtcIngress(area_id="dashboard_voice")
        live, dead = _FakeSocket(), _FakeSocket(fails=True)
        ingress._active_websockets.extend([dead, live])

        sent = await ingress.broadcast({"type": "transcript", "text": "hello"})

        assert sent == 1
        assert live.sent
        assert dead not in ingress._active_websockets
        assert live in ingress._active_websockets

    @pytest.mark.asyncio
    async def test_no_listeners_is_not_an_error(self):
        ingress = WebRtcIngress(area_id="dashboard_voice")
        assert await ingress.broadcast({"type": "transcript", "text": "hi"}) == 0
