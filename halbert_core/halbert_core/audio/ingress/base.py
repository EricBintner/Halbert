# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Abstract base class for audio ingress adapters.

Every adapter can say **which ear it is**. ``source_id`` is the registry-shaped
id — ``mic:<kind>:<instance>`` — that ``continuity/ownership.route_observation``
keys on, so a microphone can be handed to a guest for a private session the way
a camera already can (``.handoff/DESIGN-PERSONA-LAYERS-2026-09-06.md`` §5.3).

The instance is whatever actually distinguishes one of these adapters from
another *at this level*: an area for the local mic, the Wyoming listener and the
dashboard; the camera name for RTSP. Per-satellite and per-peer ids do not exist
here — one adapter serves every satellite that connects to it and every browser
that opens a socket — so nothing pretends they do.
"""

from __future__ import annotations

import abc
import logging
from typing import AsyncIterator, Optional

from ..buffer import AudioChunk

logger = logging.getLogger("halbert.audio.ingress.base")


class AudioIngressAdapter(abc.ABC):
    """Base class for all audio ingress sources.

    Each adapter normalizes incoming audio to 16kHz, 16-bit, mono PCM
    and emits AudioChunk objects via an async iterator.
    """

    #: source_type -> the ``kind`` segment of the source id.
    SOURCE_KINDS = {
        "local_mic": "local",
        "wyoming_satellite": "wyoming",
        "frigate_rtsp": "rtsp",
        "dashboard": "dashboard",
    }

    def __init__(self, source_type: str, area_id: str = "", instance: str = ""):
        self.source_type = source_type
        self.area_id = area_id
        #: What distinguishes this adapter from another of the same kind.
        #: Falls back to the area, then to the kind itself, so the id is
        #: never ``mic:local:`` with an empty tail.
        self.instance = instance or area_id or ""
        self._running = False

    @property
    def source_kind(self) -> str:
        return self.SOURCE_KINDS.get(self.source_type, self.source_type)

    @property
    def source_id(self) -> str:
        """``mic:<kind>:<instance>`` — what a private-source assignment names."""
        kind = self.source_kind
        return f"mic:{kind}:{self.instance or kind}"

    @abc.abstractmethod
    async def start(self) -> None:
        """Start capturing audio."""
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop capturing audio."""
        ...

    @abc.abstractmethod
    def chunks(self) -> AsyncIterator[AudioChunk]:
        """Async iterator yielding AudioChunk objects."""
        ...
        yield  # type: ignore[misc]

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> dict:
        """Status dict for the /api/audio/ingress/status endpoint."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "area_id": self.area_id,
            "running": self._running,
        }
