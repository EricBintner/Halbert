# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Wyoming protocol binary frame reader — proper audio-chunk ingestion.

The Wyoming protocol is NOT pure JSONL. It uses a hybrid framing:

1. A single newline-terminated JSON header line:
   ``{"type": "audio-chunk", "data": {...}, "data_length": N, "payload_length": M}\n``
2. If ``data_length > 0``: exactly N bytes of additional JSON data
3. If ``payload_length > 0``: exactly M bytes of binary payload (raw PCM)

The existing ``wyoming_agent.py`` uses ``readline()`` only, which works for
text-only events (transcript, ping, describe) but BREAKS on audio-chunk
frames — the readline parser tries to parse raw PCM bytes as JSON.

This module implements the canonical Wyoming frame reader and feeds PCM
into the audio ring buffer while routing transcripts to the conversation
agent. The existing ``wyoming_agent.py`` remains as the text-only
conversation endpoint — this ingress feeds it transcripts.

Wire format reference:
  - https://github.com/rhasspy/wyoming (README Format section)
  - https://github.com/rhasspy/rhasspy3/blob/master/docs/wyoming.md

Default satellite audio: 16kHz, 16-bit, mono, little-endian PCM.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from .base import AudioIngressAdapter
from ..buffer import AudioChunk

logger = logging.getLogger("halbert.audio.ingress.wyoming")


@dataclass
class WyomingFrame:
    """A parsed Wyoming protocol frame."""
    msg_type: str
    data: dict
    payload: bytes = b""
    payload_length: int = 0


async def read_wyoming_frame(reader: asyncio.StreamReader) -> Optional[WyomingFrame]:
    """Read one complete Wyoming frame from a stream reader.

    Implements the canonical reader algorithm:
    1. readline() for JSON header
    2. readexactly(data_length) for additional JSON data
    3. readexactly(payload_length) for binary payload

    Returns None on clean EOF. Raises IncompleteReadError on disconnect.
    """
    # 1. Read the JSON header line
    line = await reader.readline()
    if not line:
        return None  # clean EOF

    try:
        header = json.loads(line.decode("utf-8").strip())
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid Wyoming header: {line!r}: {e}")
        return None

    msg_type = header.get("type", "")
    data = header.get("data", {})
    data_length = header.get("data_length", 0) or 0
    payload_length = header.get("payload_length", 0) or 0

    # 2. Read additional JSON data if present
    if data_length > 0:
        extra_bytes = await reader.readexactly(data_length)
        try:
            extra_data = json.loads(extra_bytes.decode("utf-8"))
            data.update(extra_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Invalid Wyoming data block: {e}")

    # 3. Read binary payload if present
    payload = b""
    if payload_length > 0:
        payload = await reader.readexactly(payload_length)

    return WyomingFrame(
        msg_type=msg_type,
        data=data,
        payload=payload,
        payload_length=payload_length,
    )


async def write_wyoming_frame(
    writer: asyncio.StreamWriter,
    msg_type: str,
    data: dict,
    payload: bytes = b"",
) -> None:
    """Write a Wyoming frame to a stream writer."""
    header = {"type": msg_type, "data": data}
    if payload:
        header["payload_length"] = len(payload)
    line = (json.dumps(header) + "\n").encode("utf-8")
    writer.write(line)
    if payload:
        writer.write(payload)
    await writer.drain()


class WyomingIngress(AudioIngressAdapter):
    """Wyoming TCP server that ingests raw satellite audio.

    Listens on a TCP port and accepts connections from Wyoming satellites
    (ESP32-S3, Atom Echo, Pi). Parses binary-framed audio-chunk events
    and feeds PCM into the ring buffer.

    Text events (transcript) are routed to the conversation agent via
    a callback. The existing ``wyoming_agent.py`` handles the text-only
    conversation flow — this ingress handles the audio.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 10400,
        area_id: str = "",
        transcript_callback=None,
    ):
        super().__init__(source_type="wyoming_satellite", area_id=area_id)
        self._host = host
        self._port = port
        self._transcript_callback = transcript_callback
        self._server: Optional[asyncio.AbstractServer] = None
        self._chunk_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=200)
        self._audio_format: dict = {}  # rate, width, channels from audio-start

    async def start(self) -> None:
        """Start the Wyoming TCP server."""
        if self._running:
            logger.warning("Wyoming ingress already running")
            return

        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._host,
            port=self._port,
        )
        self._running = True
        logger.info(f"Wyoming ingress listening on {self._host}:{self._port}")

    async def stop(self) -> None:
        """Stop the Wyoming TCP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._running = False
        logger.info("Wyoming ingress stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single Wyoming satellite connection."""
        peer = writer.get_extra_info("peername")
        logger.info(f"Wyoming satellite connected: {peer}")

        try:
            while True:
                frame = await read_wyoming_frame(reader)
                if frame is None:
                    break  # clean disconnect

                await self._process_frame(frame, writer, peer)

        except asyncio.IncompleteReadError:
            logger.info(f"Wyoming satellite disconnected (incomplete read): {peer}")
        except Exception as e:
            logger.error(f"Wyoming client error: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"Wyoming satellite disconnected: {peer}")

    async def _process_frame(
        self,
        frame: WyomingFrame,
        writer: asyncio.StreamWriter,
        peer: str,
    ) -> None:
        """Process a single Wyoming frame."""
        if frame.msg_type == "audio-start":
            # Satellite is starting an audio stream
            self._audio_format = {
                "rate": frame.data.get("rate", 16000),
                "width": frame.data.get("width", 2),
                "channels": frame.data.get("channels", 1),
            }
            logger.debug(f"Audio start from {peer}: {self._audio_format}")

        elif frame.msg_type == "audio-chunk":
            # Raw PCM audio payload
            if frame.payload and self._audio_format:
                chunk = AudioChunk(
                    pcm=frame.payload,
                    samples=len(frame.payload) // self._audio_format.get("width", 2),
                    source=self.source_type,
                    area_id=self.area_id,
                )
                try:
                    self._chunk_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    # Drop oldest to make room
                    try:
                        self._chunk_queue.get_nowait()
                        self._chunk_queue.put_nowait(chunk)
                    except asyncio.QueueEmpty:
                        pass

        elif frame.msg_type == "audio-stop":
            # Satellite finished an audio stream
            logger.debug(f"Audio stop from {peer}")

        elif frame.msg_type == "transcript":
            # Text transcript from HA (routed to conversation agent)
            text = frame.data.get("text", "")
            conversation_id = frame.data.get("conversation_id", "")
            context = frame.data.get("context", {})
            area_id = context.get("area_id", self.area_id)

            if self._transcript_callback and text.strip():
                await self._transcript_callback(
                    text=text,
                    conversation_id=conversation_id,
                    area_id=area_id,
                )

        elif frame.msg_type == "ping":
            await write_wyoming_frame(writer, "pong", {})

        elif frame.msg_type == "describe":
            await write_wyoming_frame(writer, "describe", {
                "name": "halbert-audio",
                "description": "Halbert Auditory Cortex — audio ingress",
                "capabilities": {
                    "conversation": True,
                    "streaming": True,
                    "audio_input": True,
                },
            })

        else:
            logger.debug(f"Unknown Wyoming message type: {frame.msg_type}")

    async def chunks(self) -> AsyncIterator[AudioChunk]:
        """Async iterator yielding AudioChunk objects from connected satellites."""
        while self._running:
            chunk = await self._chunk_queue.get()
            yield chunk

    @property
    def status(self) -> dict:
        base = super().status
        base.update({
            "host": self._host,
            "port": self._port,
            "queue_size": self._chunk_queue.qsize(),
            "audio_format": self._audio_format,
        })
        return base
