# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""RTSP camera audio ingress — Frigate security camera audio extraction.

Connects to RTSP streams (typically from Frigate NVR), extracts the audio
track, decodes it to 16kHz/16-bit/mono PCM, and feeds into the ring buffer.

Audio track is commonly Opus or AAC encoded in the RTSP container.
Decoding requires either:
- ``symphonia`` (pure Rust, handles WAV/PCM/FLAC natively)
- ``symphonia-adapter-libopus`` (C dep for Opus decoding)
- Or ffmpeg/ffprobe as a subprocess fallback

The area_id comes from the camera configuration so acoustic events can be
attributed to the correct location (driveway, backyard, etc.).

Lazy and optional — only starts if rtsp_ingress is enabled in config.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import struct
from typing import AsyncIterator, Dict, List, Optional

from .base import AudioIngressAdapter
from ..buffer import AudioChunk

logger = logging.getLogger("halbert.audio.ingress.rtsp")

SAMPLE_RATE = 16_000


class RtspIngress(AudioIngressAdapter):
    """RTSP camera audio extractor using ffmpeg subprocess.

    Uses ffmpeg to decode the RTSP audio track to raw PCM, which is then
    fed into the pipeline. This is the simplest approach — ffmpeg handles
    all codec decoding (Opus, AAC, G.711, etc.) and resampling.

    For a pure-Python approach, symphonia + symphonia-adapter-libopus could
    be used, but ffmpeg is more robust and already available on most
    homelab servers.
    """

    def __init__(
        self,
        camera_name: str = "",
        rtsp_url: str = "",
        area_id: str = "",
    ):
        super().__init__(source_type="frigate_rtsp", area_id=area_id)
        self._camera_name = camera_name
        self._rtsp_url = rtsp_url
        self._process: Optional[asyncio.subprocess.Process] = None
        self._chunk_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=100)

    async def start(self) -> None:
        """Start the ffmpeg subprocess to decode RTSP audio."""
        if self._running or not self._rtsp_url:
            return

        try:
            self._process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i", self._rtsp_url,
                "-vn",                    # no video
                "-ac", "1",               # mono
                "-ar", str(SAMPLE_RATE),  # 16kHz
                "-f", "s16le",            # 16-bit little-endian
                "-acodec", "pcm_s16le",
                "pipe:1",                 # output to stdout
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._running = True
            logger.info(f"RTSP ingress started: {self._camera_name} ({self._rtsp_url})")
        except FileNotFoundError:
            logger.error(
                "ffmpeg not found — RTSP audio ingress requires ffmpeg. "
                "Install ffmpeg: apt install ffmpeg (or brew install ffmpeg)"
            )
        except Exception as e:
            logger.error(f"RTSP ingress start failed: {e}")

    async def stop(self) -> None:
        """Stop the ffmpeg subprocess."""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            except Exception:
                pass
            self._process = None
        logger.info(f"RTSP ingress stopped: {self._camera_name}")

    async def _read_loop(self) -> None:
        """Read PCM from ffmpeg stdout and enqueue chunks."""
        if not self._process or not self._process.stdout:
            return

        chunk_bytes = 1920  # 60ms at 16kHz, 16-bit = 1920 bytes
        while self._running:
            try:
                data = await self._process.stdout.readexactly(chunk_bytes)
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
            except asyncio.IncompleteReadError:
                logger.debug(f"RTSP stream ended: {self._camera_name}")
                break
            except Exception as e:
                logger.debug(f"RTSP read error: {e}")
                break

    async def chunks(self) -> AsyncIterator[AudioChunk]:
        """Async iterator yielding AudioChunk objects."""
        if self._process and self._process.stdout:
            read_task = asyncio.create_task(self._read_loop())

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
            "camera_name": self._camera_name,
            "rtsp_url": self._rtsp_url[:30] + "..." if len(self._rtsp_url) > 30 else self._rtsp_url,
            "process_alive": self._process is not None and self._process.returncode is None,
            "queue_size": self._chunk_queue.qsize(),
        })
        return base
