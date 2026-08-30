# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Local microphone ingress — reads PCM from Rust cpal loopback socket.

The Rust side (``src-tauri/src/audio_capture.rs``) captures audio via cpal,
applies AEC via webrtc-audio-processing, and writes 16kHz/16-bit/mono PCM
to a loopback TCP socket on 127.0.0.1. This Python module reads from that
socket and feeds chunks into the pipeline.

Tauri IPC is NOT used for audio data (JSON serialization + IPC overhead
makes it unsuitable for streaming — finding C6). Tauri IPC is used only
for control commands (start/stop/mute).

Usage:
    from halbert_core.audio.ingress.local_mic import LocalMicIngress
    mic = LocalMicIngress(socket_port=51000)
    await mic.start()
    async for chunk in mic.chunks():
        process(chunk)
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

from .base import AudioIngressAdapter
from ..buffer import AudioChunk

logger = logging.getLogger("halbert.audio.ingress.local_mic")


class LocalMicIngress(AudioIngressAdapter):
    """Reads PCM from a Rust cpal loopback TCP socket.

    The Rust side captures audio, applies AEC, and writes to a TCP socket
    on 127.0.0.1. This module connects to that socket and reads PCM chunks.

    If the Rust side isn't running (headless Linux, no Tauri), this ingress
    simply doesn't start — the pipeline falls back to Wyoming-only ingress.
    """

    def __init__(
        self,
        socket_host: str = "127.0.0.1",
        socket_port: int = 0,
        area_id: str = "local",
    ):
        super().__init__(source_type="local_mic", area_id=area_id)
        self._socket_host = socket_host
        self._socket_port = socket_port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._chunk_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=200)

    async def start(self) -> None:
        """Start connecting to the Rust cpal loopback socket."""
        if self._running:
            return
        self._running = True
        self._reconnect_task = asyncio.create_task(self._connect_loop())
        logger.info(f"Local mic ingress started (target: {self._socket_host}:{self._socket_port})")

    async def stop(self) -> None:
        """Stop the ingress and disconnect."""
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        logger.info("Local mic ingress stopped")

    async def _connect_loop(self) -> None:
        """Reconnect loop — keeps trying to connect to the Rust socket."""
        while self._running:
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self._socket_host,
                    self._socket_port,
                )
                logger.info(
                    f"Connected to Rust cpal socket at "
                    f"{self._socket_host}:{self._socket_port}"
                )
                await self._read_loop()
            except asyncio.CancelledError:
                break
            except (ConnectionRefusedError, OSError) as e:
                # Rust side not running yet — retry after delay
                logger.debug(f"Cannot connect to cpal socket: {e}, retrying in 2s")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Local mic connection error: {e}")
                await asyncio.sleep(2)

    async def _read_loop(self) -> None:
        """Read PCM chunks from the socket and enqueue them."""
        assert self._reader is not None
        # Read in ~30ms chunks (480 samples * 2 bytes = 960 bytes at 16kHz)
        chunk_bytes = 960
        while self._running:
            data = await self._reader.readexactly(chunk_bytes)
            chunk = AudioChunk(
                pcm=data,
                samples=chunk_bytes // 2,
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
            "socket_host": self._socket_host,
            "socket_port": self._socket_port,
            "connected": self._reader is not None,
            "queue_size": self._chunk_queue.qsize(),
        })
        return base
