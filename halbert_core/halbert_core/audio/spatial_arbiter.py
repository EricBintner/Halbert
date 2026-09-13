# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Spatial Audio Arbiter — multi-microphone arbitration.

When multiple ingress devices (local mic, Wyoming satellites, mobile
clients) capture audio simultaneously, the arbiter decides which
observation is the "real" turn and which are duplicates to suppress.

Problems solved (from the handoff):
  - Same speaker captured by mobile and room mic -> duplicate ASR,
    duplicate command execution.
  - Adjacent-room boundary bleed.
  - Moving mid-sentence between microphones.
  - Simultaneous occupants with different privilege levels.
  - Network jitter causing delayed duplicate turns.
  - Television/podcast false wakeups.
  - Acoustic feedback loops from Halbert's own speech.

Primitives:
  - **Coincidence grouping**: observations within a 250ms window from
    different sources for the same speaker are grouped as one event.
  - **Atomic per-speaker turn lock**: once a speaker's turn is
    accepted, further observations from that speaker within 1.5s are
    suppressed (the lock window).
  - **Self-speech suppression**: while TTS is speaking, VAD detections
    from the same device are suppressed (feedback loop prevention).
  - **Half-duplex ducking**: during TTS output, mic gain is reduced
    by -18dB and VAD threshold raised from 0.5 to 0.85.
  - **TV/media filtering**: acoustic-tagged media is not treated as
    privileged admin speech even if it triggers a wake word.

The arbiter is a passive consumer of VoiceTurnObservation and
AcousticEventObservation — it does not own the audio pipeline. The
pipeline calls ``arbitrate()`` before dispatching a turn; the arbiter
returns ``Accept`` or ``Suppress`` with a reason.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger("halbert.audio.spatial_arbiter")


# --- Tunable constants (from the handoff) ---

#: Observations within this window (seconds) from different sources for
#: the same speaker are grouped as one coincidence event.
COINCIDENCE_WINDOW_S: float = 0.250

#: Once a speaker's turn is accepted, further observations from that
#: speaker within this window are suppressed.
TURN_LOCK_WINDOW_S: float = 1.5

#: Mic gain reduction during TTS output (dB).
DUCK_GAIN_DB: float = -18.0

#: VAD threshold during TTS output (raised to avoid feedback).
DUCK_VAD_THRESHOLD: float = 0.85

#: Normal VAD threshold.
NORMAL_VAD_THRESHOLD: float = 0.5


class ArbitrationDecision(str, Enum):
    """The arbiter's verdict on an observation."""
    ACCEPT = "accept"
    SUPPRESS = "suppress"
    DEFER = "defer"  # wait for more data (e.g. mid-sentence move)


@dataclass
class ArbitrationResult:
    """The arbiter's decision for one observation."""
    decision: ArbitrationDecision
    reason: str = ""
    coincidence_group: Optional[str] = None  # group id if part of a coincidence
    speaker_locked: bool = False  # True if this speaker is in a turn lock


@dataclass
class _SpeakerLock:
    """Per-speaker turn lock state."""
    speaker_id: str
    accepted_at: float = 0.0
    source_id: str = ""


@dataclass
class _CoincidenceEntry:
    """One observation in a coincidence group."""
    speaker_id: str
    source_id: str
    timestamp: float


class SpatialAudioArbiter:
    """Multi-microphone arbitration for the audio pipeline.

    Thread-safe via the GIL (all state is in-memory dicts). The arbiter
    is a singleton held by the AudioPipelineCoordinator.

    Usage:
        arbiter = SpatialAudioArbiter()
        result = arbiter.arbitrate(
            speaker_id="alice",
            source_id="local_mic",
            text="turn on the lights",
            is_media=False,
        )
        if result.decision == ArbitrationDecision.ACCEPT:
            await dispatch_turn(observation)
    """

    def __init__(self) -> None:
        # speaker_id -> _SpeakerLock
        self._locks: Dict[str, _SpeakerLock] = {}
        # Coincidence tracking: list of recent observations for grouping.
        self._recent: List[_CoincidenceEntry] = []
        # Sources that are currently known to be media (TV, podcast).
        self._media_sources: Set[str] = set()
        # Whether TTS is currently speaking (for ducking/feedback prevention).
        self._tts_speaking: bool = False
        # The source_id that is currently speaking TTS (for self-speech
        # suppression — VAD detections from the same device are feedback).
        self._tts_source_id: str = ""

    # ------------------------------------------------------------------
    # Main arbitration entry point
    # ------------------------------------------------------------------

    def arbitrate(
        self,
        speaker_id: str,
        source_id: str,
        text: str = "",
        is_media: bool = False,
        confidence: float = 0.0,
    ) -> ArbitrationResult:
        """Decide whether to accept or suppress a voice turn observation.

        Args:
            speaker_id: The identified speaker (empty if unknown).
            source_id: The ingress source (local_mic, wyoming_satellite, etc.).
            text: The transcribed text (for duplicate detection).
            is_media: True if the acoustic tagger classified this as media.
            confidence: Speaker identification confidence (0-1).

        Returns:
            ArbitrationResult with the decision and reason.
        """
        now = time.monotonic()

        # 1. Media filtering: TV/podcast audio is never privileged speech.
        #    Check both the per-observation is_media flag and the
        #    persistent media source set.
        if is_media or source_id in self._media_sources:
            logger.debug(
                f"Arbiter: suppressing media from {source_id} "
                f"(speaker={speaker_id})"
            )
            return ArbitrationResult(
                decision=ArbitrationDecision.SUPPRESS,
                reason="media_filtered",
            )

        # 2. Self-speech suppression: if TTS is speaking from this source,
        #    VAD detections are feedback (Halbert hearing itself).
        if self._tts_speaking and source_id == self._tts_source_id:
            logger.debug(
                f"Arbiter: suppressing self-speech feedback from {source_id}"
            )
            return ArbitrationResult(
                decision=ArbitrationDecision.SUPPRESS,
                reason="self_speech_feedback",
            )

        # Unknown speakers (empty speaker_id, e.g. Wyoming satellite
        # transcripts that don't do speaker ID) skip the turn lock and
        # coincidence check — we can't distinguish two different unknown
        # speakers, so locking would suppress the wrong person.
        if not speaker_id:
            logger.info(
                f"Arbiter: ACCEPT unknown speaker, source={source_id}"
            )
            return ArbitrationResult(
                decision=ArbitrationDecision.ACCEPT,
                reason="unknown_speaker",
            )

        # 3. Per-speaker turn lock: if this speaker recently had a turn
        #    accepted, suppress duplicates (same speaker, different mic).
        lock = self._locks.get(speaker_id)
        if lock is not None:
            elapsed = now - lock.accepted_at
            if elapsed < TURN_LOCK_WINDOW_S:
                # Same source re-triggering within the lock window is
                # normal (the lock prevents duplicate commands from the
                # same mic). A different source is a coincidence duplicate.
                if source_id != lock.source_id:
                    logger.debug(
                        f"Arbiter: suppressing coincidence duplicate "
                        f"(speaker={speaker_id}, source={source_id}, "
                        f"locked_source={lock.source_id}, "
                        f"elapsed={elapsed:.3f}s)"
                    )
                    return ArbitrationResult(
                        decision=ArbitrationDecision.SUPPRESS,
                        reason="coincidence_duplicate",
                        speaker_locked=True,
                    )
                else:
                    logger.debug(
                        f"Arbiter: suppressing same-source re-trigger "
                        f"(speaker={speaker_id}, source={source_id})"
                    )
                    return ArbitrationResult(
                        decision=ArbitrationDecision.SUPPRESS,
                        reason="turn_lock",
                        speaker_locked=True,
                    )

        # 4. Coincidence grouping: check if another source recently
        #    observed the same speaker. If so, this is likely the same
        #    physical event captured by two mics.
        group_id: Optional[str] = None
        for entry in self._recent:
            elapsed = now - entry.timestamp
            if elapsed > COINCIDENCE_WINDOW_S:
                continue
            if entry.speaker_id == speaker_id and entry.source_id != source_id:
                # This is a coincidence — but we need to decide which
                # one wins. The first-arriving observation wins; this
                # one is a duplicate.
                logger.debug(
                    f"Arbiter: suppressing coincidence (speaker={speaker_id}, "
                    f"source={source_id}, first_source={entry.source_id}, "
                    f"elapsed={elapsed:.3f}s)"
                )
                return ArbitrationResult(
                    decision=ArbitrationDecision.SUPPRESS,
                    reason="coincidence_duplicate",
                    coincidence_group=f"{speaker_id}@{entry.timestamp:.3f}",
                )

        # 5. Accept the turn. Register the lock and record the observation.
        self._locks[speaker_id] = _SpeakerLock(
            speaker_id=speaker_id,
            accepted_at=now,
            source_id=source_id,
        )
        self._recent.append(_CoincidenceEntry(
            speaker_id=speaker_id,
            source_id=source_id,
            timestamp=now,
        ))

        # Prune old entries.
        self._prune(now)

        logger.info(
            f"Arbiter: ACCEPT speaker={speaker_id}, source={source_id}, "
            f"confidence={confidence:.2f}"
        )
        return ArbitrationResult(
            decision=ArbitrationDecision.ACCEPT,
            reason="accepted",
        )

    # ------------------------------------------------------------------
    # TTS state management (for ducking and self-speech suppression)
    # ------------------------------------------------------------------

    def on_tts_start(self, source_id: str = "") -> None:
        """Called when TTS output begins on the given source."""
        self._tts_speaking = True
        self._tts_source_id = source_id
        logger.debug(f"Arbiter: TTS start (source={source_id}), ducking enabled")

    def on_tts_end(self) -> None:
        """Called when TTS output ends."""
        self._tts_speaking = False
        self._tts_source_id = ""
        logger.debug("Arbiter: TTS end, ducking disabled")

    @property
    def is_ducking(self) -> bool:
        """True when TTS is speaking and mics should be ducked."""
        return self._tts_speaking

    @property
    def current_vad_threshold(self) -> float:
        """The VAD threshold the pipeline should use right now.

        Raised during TTS output to prevent feedback loops.
        """
        return DUCK_VAD_THRESHOLD if self._tts_speaking else NORMAL_VAD_THRESHOLD

    @property
    def current_mic_gain_db(self) -> float:
        """The mic gain (dB) the pipeline should use right now.

        Reduced during TTS output (half-duplex ducking).
        """
        return DUCK_GAIN_DB if self._tts_speaking else 0.0

    # ------------------------------------------------------------------
    # Media source management
    # ------------------------------------------------------------------

    def mark_media_source(self, source_id: str) -> None:
        """Mark a source as currently playing media (TV, podcast).

        Observations from this source will be filtered as media until
        unmarked.
        """
        self._media_sources.add(source_id)
        logger.debug(f"Arbiter: marked {source_id} as media source")

    def unmark_media_source(self, source_id: str) -> None:
        """Unmark a source as media."""
        self._media_sources.discard(source_id)
        logger.debug(f"Arbiter: unmarked {source_id} as media source")

    def is_media_source(self, source_id: str) -> bool:
        """Check if a source is currently marked as media."""
        return source_id in self._media_sources

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune(self, now: float) -> None:
        """Remove expired entries from locks and recent observations."""
        # Prune expired turn locks.
        expired = [
            sid for sid, lock in self._locks.items()
            if now - lock.accepted_at > TURN_LOCK_WINDOW_S * 4
        ]
        for sid in expired:
            del self._locks[sid]

        # Prune old coincidence entries.
        self._recent = [
            e for e in self._recent
            if now - e.timestamp < COINCIDENCE_WINDOW_S * 2
        ]

    def reset(self) -> None:
        """Clear all state (for testing or pipeline restart)."""
        self._locks.clear()
        self._recent.clear()
        self._media_sources.clear()
        self._tts_speaking = False
        self._tts_source_id = ""
