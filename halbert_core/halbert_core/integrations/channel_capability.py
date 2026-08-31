# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""HalbertChannelCapability — reports the delivery channel's hardware state.

Implements the engine's ``ChannelCapability`` Protocol (spec section 3.2).
The engine's ``resolve_modality()`` wiring helper queries this per-turn to
fill ``ModalityContext.has_speaker``, ``has_screen``, ``is_hands_free``,
and ``channel_modality`` — the inputs the resolver uses to decide
TEXT vs VOICE vs MIXED.

Halbert's channel state:
- **Tauri desktop**: has_screen=True, has_speaker depends on audio pipeline,
  has_keyboard=True, is_hands_free=False, modality="text" (or "voice" when
  the audio pipeline is in LISTENING/SPEAKING state).
- **Wyoming satellite** (HA voice pipeline): has_screen=False, has_speaker=True,
  has_keyboard=False, is_hands_free=True, modality="voice".
- **Text-only** (no audio pipeline): has_screen=True, has_speaker=False,
  has_keyboard=True, is_hands_free=False, modality="text".

The capability is queried lazily; a broken audio pipeline query degrades to
the text-only defaults (subtractive contract).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("halbert.integrations.channel_capability")


class HalbertChannelCapability:
    """ChannelCapability Protocol implementation for Halbert.

    Reports the current delivery channel's capabilities to the engine's
    modality resolver. The state is read from the audio pipeline coordinator
    (if running) and the Tauri desktop shell.

    All accessors are defensive: a missing or broken audio pipeline degrades
    to text-only defaults so the engine never crashes on a capability query.
    """

    def __init__(
        self,
        audio_pipeline: Optional[object] = None,
        is_desktop: bool = True,
        wyoming_active: bool = False,
    ):
        self._audio_pipeline = audio_pipeline
        self._is_desktop = is_desktop
        self._wyoming_active = wyoming_active

    # ------------------------------------------------------------------
    # ChannelCapability Protocol
    # ------------------------------------------------------------------

    def has_microphone(self) -> bool:
        """Can the user speak to us?

        True when the audio pipeline is running with a VAD/wake-word engine
        (local mic) or a Wyoming satellite is connected.
        """
        if self._wyoming_active:
            return True
        pipeline = self._get_pipeline()
        if pipeline is None:
            return False
        try:
            status = pipeline.get_status()
            engines = status.get("engines", {})
            return bool(engines.get("vad") or engines.get("wake_word"))
        except Exception:
            return False

    def has_speaker(self) -> bool:
        """Can we speak back?

        True when the audio pipeline has a TTS engine loaded, or a Wyoming
        satellite is connected (satellites have speakers for HA TTS).
        """
        if self._wyoming_active:
            return True
        pipeline = self._get_pipeline()
        if pipeline is None:
            return False
        try:
            status = pipeline.get_status()
            return bool(status.get("engines", {}).get("tts"))
        except Exception:
            return False

    def has_screen(self) -> bool:
        """Can we render text/markdown?

        True for the Tauri desktop app. False for satellite-only deployments.
        """
        return self._is_desktop

    def has_keyboard(self) -> bool:
        """Can the user type?

        True for the Tauri desktop app. False for satellite-only (voice-only).
        """
        return self._is_desktop

    def is_hands_free(self) -> bool:
        """Is the user in a hands-free context?

        True when a Wyoming satellite is the active ingress (the user is
        speaking to a wall-mounted device, not sitting at a keyboard).
        """
        return self._wyoming_active

    def current_modality(self) -> str:
        """Current primary modality: 'voice', 'text', or 'mixed'.

        - 'voice' when the audio pipeline is in LISTENING/THINKING/SPEAKING
          state, or a Wyoming satellite is active.
        - 'text' otherwise (desktop with no active voice turn).
        - 'mixed' is not currently used by Halbert (the resolver decides
          MIXED from cognitive state, not from channel capability).
        """
        if self._wyoming_active:
            return "voice"
        pipeline = self._get_pipeline()
        if pipeline is None:
            return "text"
        try:
            state = pipeline.state
            state_value = getattr(state, "value", str(state))
            if state_value in ("listening", "thinking", "speaking", "recognized"):
                return "voice"
        except Exception:
            pass
        return "text"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_pipeline(self) -> Optional[object]:
        """Return the audio pipeline coordinator, or None if not running.

        If no pipeline was passed at construction, try to get the singleton
        from the dashboard routes (lazy, defensive).
        """
        if self._audio_pipeline is not None:
            return self._audio_pipeline
        try:
            from ..dashboard.routes.audio import get_audio_pipeline
            return get_audio_pipeline()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Halbert-specific state updates (called by the wiring layer)
    # ------------------------------------------------------------------

    def set_wyoming_active(self, active: bool) -> None:
        """Update the Wyoming satellite connection state."""
        self._wyoming_active = active

    def set_audio_pipeline(self, pipeline: Optional[object]) -> None:
        """Update the audio pipeline reference (e.g. after start/stop)."""
        self._audio_pipeline = pipeline
