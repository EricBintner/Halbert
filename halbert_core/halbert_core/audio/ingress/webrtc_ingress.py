# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""WebRTC / Dashboard ingress — browser microphone via WebSocket.

Provides a FastAPI WebSocket endpoint at ``/api/audio/stream`` that accepts
raw PCM audio from the browser. Used for the dashboard "push to talk"
button — the browser captures mic audio and sends it via WebSocket.

The browser side uses the Web Audio API to capture, resample to 16kHz,
convert to 16-bit PCM, and send as binary WebSocket frames.

This is a simpler alternative to full WebRTC (no STUN/TURN needed for
local network). For remote access, WebRTC would be needed — but the
dashboard is typically accessed on the LAN.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

from .base import AudioIngressAdapter
from ..buffer import AudioChunk

logger = logging.getLogger("halbert.audio.ingress.webrtc")

SAMPLE_RATE = 16_000


class WebRtcIngress(AudioIngressAdapter):
    """WebSocket-based audio ingress from the dashboard browser.

    Accepts binary WebSocket frames containing 16kHz/16-bit/mono PCM.
    The browser captures audio via the Web Audio API and sends it here.

    This is NOT full WebRTC — it's a raw PCM WebSocket stream. Sufficient
    for LAN dashboard access. For remote access, a proper WebRTC
    implementation with STUN/TURN would be needed.
    """

    def __init__(self, area_id: str = "dashboard"):
        super().__init__(source_type="dashboard", area_id=area_id)
        self._chunk_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=100)
        self._active_websockets: list = []

    async def start(self) -> None:
        """Start the ingress (WebSocket endpoint is registered separately)."""
        self._running = True
        logger.info("WebRTC/dashboard ingress ready")

    async def stop(self) -> None:
        """Stop the ingress and close all WebSocket connections."""
        self._running = False
        for ws in self._active_websockets:
            try:
                await ws.close()
            except Exception:
                pass
        self._active_websockets.clear()
        logger.info("WebRTC/dashboard ingress stopped")

    async def handle_websocket(self, websocket) -> None:
        """Handle a WebSocket connection from the browser.

        Args:
            websocket: A Starlette/FastAPI WebSocket instance.
        """
        self._active_websockets.append(websocket)
        logger.info(f"Dashboard audio WebSocket connected ({len(self._active_websockets)} active)")

        try:
            while self._running:
                data = await websocket.receive_bytes()
                chunk = AudioChunk(
                    pcm=data,
                    samples=len(data) // 2,
                    source=self.source_type,
                    area_id=self.area_id,
                )
                try:
                    self._chunk_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    try:
                        self._chunk_queue.get_nowait()
                        self._chunk_queue.put_nowait(chunk)
                    except asyncio.QueueEmpty:
                        pass
        except Exception as e:
            logger.debug(f"Dashboard WebSocket disconnected: {e}")
        finally:
            if websocket in self._active_websockets:
                self._active_websockets.remove(websocket)

    async def broadcast(self, message: dict) -> int:
        """Send one JSON frame down every connected browser socket.

        The uplink is bidirectional and was only ever used upward. This is
        the return path: the browser is already connected here pushing mic
        audio, so a transcript needs no second endpoint and no session
        bookkeeping to find its way back to the page that spoke.

        Returns the number of sockets the message actually reached; a socket
        that fails is dropped rather than retried.
        """
        import json as _json

        payload = _json.dumps(message)
        delivered = 0
        for ws in list(self._active_websockets):
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception as e:
                logger.debug(f"Dropping dashboard audio WebSocket: {e}")
                if ws in self._active_websockets:
                    self._active_websockets.remove(ws)
        return delivered

    async def chunks(self) -> AsyncIterator[AudioChunk]:
        """Async iterator yielding AudioChunk objects."""
        while self._running:
            try:
                chunk = await asyncio.wait_for(self._chunk_queue.get(), timeout=1.0)
                yield chunk
            except asyncio.TimeoutError:
                continue

    @property
    def status(self) -> dict:
        base = super().status
        base.update({
            "active_connections": len(self._active_websockets),
            "queue_size": self._chunk_queue.qsize(),
        })
        return base
