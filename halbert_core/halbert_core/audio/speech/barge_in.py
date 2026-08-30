# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Barge-in interrupt handler — cancels TTS playback when user speaks.

Two cancellation targets (per architecture review finding H6):

1. **Local Piper TTS** (cancellable): The ``BargeInToken`` is an
   ``asyncio.Event`` that the TTS generator checks between chunks.
   When set, TTS generation aborts immediately.

2. **HA satellite playback** (best-effort, lossy): Calls HA's
   ``media_player.stop`` service for the target area. Cannot cancel
   audio HA has already started playing on the satellite speaker.

The latency budget is <150ms from VAD speech detection to local Piper
cancellation. The HA satellite path is documented as lossy.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("halbert.audio.speech.barge_in")


@dataclass
class BargeInResult:
    """Result of a barge-in event."""
    cancelled_local: bool       # local Piper TTS was cancelled
    cancelled_satellite: bool   # HA satellite stop was sent (best-effort)
    latency_ms: float           # time from trigger to local cancel
    area_id: str = ""


class BargeInToken:
    """Cancellation token for barge-in.

    Wraps ``asyncio.Event``. The TTS generator checks ``is_set()`` between
    chunks and aborts when True.
    """

    def __init__(self):
        self._event = asyncio.Event()
        self._triggered_at: float = 0.0

    def trigger(self) -> None:
        """Signal barge-in (user speech detected)."""
        self._triggered_at = time.monotonic()
        self._event.set()

    def reset(self) -> None:
        """Reset for next turn."""
        self._event.clear()
        self._triggered_at = 0.0

    def is_set(self) -> bool:
        return self._event.is_set()

    @property
    def triggered_at(self) -> float:
        return self._triggered_at


class BargeInHandler:
    """Orchestrates barge-in cancellation across local + satellite targets.

    Usage:
        handler = BargeInHandler()
        token = handler.create_token()

        # Start TTS with the token
        async for pcm in tts.synthesize(text, cancel_token=token):
            play(pcm)

        # When VAD detects speech:
        result = await handler.trigger(token, area_id="living_room")
        print(f"Cancelled in {result.latency_ms:.0f}ms")
    """

    def __init__(self, ha_client=None):
        self._ha_client = ha_client

    def create_token(self) -> BargeInToken:
        """Create a new barge-in token for this TTS turn."""
        return BargeInToken()

    async def trigger(
        self,
        token: BargeInToken,
        area_id: str = "",
    ) -> BargeInResult:
        """Trigger barge-in: cancel local TTS + best-effort satellite stop.

        Args:
            token: The BargeInToken passed to the TTS generator.
            area_id: HA area to stop media players in (for satellite barge-in).

        Returns:
            BargeInResult with cancellation status and latency.
        """
        start = time.monotonic()

        # 1. Cancel local Piper TTS (immediate)
        token.trigger()
        local_cancelled = True

        # 2. Best-effort HA satellite stop (lossy)
        satellite_cancelled = False
        if self._ha_client and area_id:
            try:
                await self._ha_client.call_service(
                    "media_player",
                    "stop",
                    {"area_id": area_id},
                )
                satellite_cancelled = True
            except Exception as e:
                logger.debug(f"Satellite barge-in failed (lossy): {e}")

        latency = (time.monotonic() - start) * 1000
        logger.info(
            f"Barge-in: local={local_cancelled}, satellite={satellite_cancelled}, "
            f"latency={latency:.0f}ms, area={area_id}"
        )

        return BargeInResult(
            cancelled_local=local_cancelled,
            cancelled_satellite=satellite_cancelled,
            latency_ms=latency,
            area_id=area_id,
        )
