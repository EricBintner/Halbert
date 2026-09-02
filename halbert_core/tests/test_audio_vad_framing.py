# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R9-F03 / U2-14: the speech track must hand the VAD windows it can use.

Silero's window is 512 samples, and ``VoiceActivityDetector.is_speech``
returns False outright for anything shorter. The speech track sliced 960-byte
frames — 480 samples — so ``is_speech`` could never once return True, and the
entire speech path behind it was dead: wake word, ASR turns, speaker
identification and VAD barge-in. Live in production since the coordinator
started booting in ``app.py``.

The bug is a frame size, so these tests watch the frames rather than the
outcome: a real VAD would report the same "no speech" either way.
"""
from __future__ import annotations

import asyncio

import pytest

from halbert_core.audio.buffer import AudioChunk
from halbert_core.audio.config import AudioConfig
from halbert_core.audio.pipeline import AudioPipelineCoordinator
from halbert_core.audio.speech.vad import SILERO_WINDOW_SAMPLES


class _RecordingVAD:
    """Records every frame length the track offers it. Never hears speech,
    so the track stays in IDLE and no downstream engine is needed."""

    def __init__(self):
        self.frame_lengths: list[int] = []

    def is_speech(self, pcm: bytes) -> bool:
        self.frame_lengths.append(len(pcm))
        return False


async def _run_track_over(coordinator, pcm: bytes) -> None:
    """Feed one chunk through the speech track and stop it."""
    coordinator._running = True
    task = asyncio.ensure_future(coordinator._speech_track_loop())
    await coordinator._chunk_queue.put(
        AudioChunk(pcm=pcm, samples=len(pcm) // 2, source="test",
                   area_id="test", timestamp=0.0)
    )
    for _ in range(50):
        await asyncio.sleep(0.005)
        if coordinator._vad.frame_lengths:
            break
    coordinator._running = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_frames_are_a_full_silero_window():
    coordinator = AudioPipelineCoordinator(config=AudioConfig())
    coordinator._vad = _RecordingVAD()

    # 10 windows' worth, so short-frame slicing would be obvious.
    await _run_track_over(coordinator, b"\x00\x01" * (SILERO_WINDOW_SAMPLES * 10))

    assert coordinator._vad.frame_lengths, "the speech track never called the VAD"
    expected = SILERO_WINDOW_SAMPLES * 2  # 16-bit samples
    assert set(coordinator._vad.frame_lengths) == {expected}, (
        f"VAD was offered {sorted(set(coordinator._vad.frame_lengths))} bytes; "
        f"anything below {expected} can never report speech"
    )


@pytest.mark.asyncio
async def test_a_short_chunk_is_held_back_rather_than_offered_truncated():
    coordinator = AudioPipelineCoordinator(config=AudioConfig())
    coordinator._vad = _RecordingVAD()

    # Half a window: the track must buffer it, not hand over a runt frame.
    coordinator._running = True
    task = asyncio.ensure_future(coordinator._speech_track_loop())
    await coordinator._chunk_queue.put(
        AudioChunk(pcm=b"\x00\x01" * (SILERO_WINDOW_SAMPLES // 2),
                   samples=SILERO_WINDOW_SAMPLES // 2,
                   source="test", area_id="test", timestamp=0.0)
    )
    await asyncio.sleep(0.05)
    coordinator._running = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert coordinator._vad.frame_lengths == []
