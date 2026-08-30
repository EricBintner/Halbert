# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Abstract base class for audio ingress adapters."""

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

    def __init__(self, source_type: str, area_id: str = ""):
        self.source_type = source_type
        self.area_id = area_id
        self._running = False

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
            "area_id": self.area_id,
            "running": self._running,
        }
