# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Audio pipeline coordinator — orchestrates ingress, ring buffer, and dual-track processing.

The coordinator:
1. Starts all enabled ingress adapters (local mic, Wyoming, RTSP, WebRTC)
2. Feeds incoming PCM chunks into the ring buffer
3. Runs two concurrent tracks:
   - Track A (Speech): VAD -> wake word -> ASR -> speaker ID -> barge-in
   - Track B (Ambient): energy gate -> audio tagger -> anomaly detector
4. Emits observations (VoiceTurnObservation, AcousticEventObservation)
5. Publishes state changes via SSE for the frontend aura indicator

Graceful degradation: if sherpa-onnx is not installed, the pipeline starts
but produces no observations (no crash). This mirrors the vision subsystem
behavior when onnxruntime is missing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Dict, List, Optional

from .buffer import AsyncRingBuffer, AudioChunk, ChunkQueue
from .config import AudioConfig, load_config
from .is_available import is_audio_available

logger = logging.getLogger("halbert.audio.pipeline")


class AudioState(str, Enum):
    """Audio pipeline state — drives the frontend aura indicator."""
    IDLE = "idle"              # monitoring, no active speech
    LISTENING = "listening"    # wake word detected or hotkey pressed
    RECOGNIZED = "recognized"  # speaker identified
    THINKING = "thinking"      # agent processing the turn
    SPEAKING = "speaking"      # TTS output in progress
    ERROR = "error"


@dataclass
class VoiceTurnObservation:
    """Result of a complete voice turn (speech track)."""
    text: str
    speaker_id: str = ""
    speaker_name: str = ""
    speaker_role: str = "unknown"
    speaker_confidence: float = 0.0
    area_id: str = ""
    urgency: str = "normal"        # "normal", "urgent", "critical"
    audio_duration_ms: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AcousticEventObservation:
    """Result of an ambient acoustic event (ambient track)."""
    sound_class: str
    confidence: float
    area_id: str = ""
    decibel_level: float = 0.0
    is_anomaly: bool = False
    anomaly_severity: int = 0     # 0=Info, 1=Warning, 2=Confirm, 3=Critical
    music_track: str = ""         # "Daft Punk - Solar Sailer" if music detected
    source: str = ""
    timestamp: float = field(default_factory=time.time)


# Type aliases for callbacks
VoiceTurnCallback = Callable[[VoiceTurnObservation], Awaitable[None]]
AcousticEventCallback = Callable[[AcousticEventObservation], Awaitable[None]]
StateChangeCallback = Callable[[AudioState, Dict], Awaitable[None]]


class AudioPipelineCoordinator:
    """Orchestrates the full audio pipeline.

    Starts ingress adapters, feeds the ring buffer, runs dual-track
    processing, and emits observations via callbacks.

    Usage:
        coordinator = AudioPipelineCoordinator()
        coordinator.on_voice_turn = handle_voice_turn
        coordinator.on_acoustic_event = handle_acoustic_event
        coordinator.on_state_change = handle_state_change
        await coordinator.start()
    """

    def __init__(self, config: Optional[AudioConfig] = None):
        self._config = config or load_config()
        self._ring_buffer = AsyncRingBuffer()
        self._chunk_queue = ChunkQueue()
        self._ingress_adapters: List = []
        self._state = AudioState.IDLE
        self._running = False
        self._tasks: List[asyncio.Task] = []

        # Callbacks
        self.on_voice_turn: Optional[VoiceTurnCallback] = None
        self.on_acoustic_event: Optional[AcousticEventCallback] = None
        self.on_state_change: Optional[StateChangeCallback] = None

        # Lazy-initialized engines (only if sherpa-onnx available)
        self._vad = None
        self._asr = None
        self._tts = None
        self._wake_word = None
        self._speaker_id = None
        self._audio_tagger = None

        # Barge-in handler (TASK-07: wired into SPEAKING state).
        # Created lazily on first use; cancels TTS playback when VAD
        # detects speech during synthesis (<120ms budget).
        self._barge_in_handler = None
        self._active_barge_in_token = None

    @property
    def state(self) -> AudioState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start the audio pipeline."""
        if self._running:
            logger.warning("Audio pipeline already running")
            return

        if not self._config.enabled:
            logger.info("Audio pipeline disabled in config — not starting")
            return

        logger.info("Starting audio pipeline...")
        self._running = True

        # Initialize engines if sherpa-onnx is available
        if is_audio_available():
            await self._init_engines()
        else:
            logger.warning(
                "sherpa-onnx not installed — audio pipeline will run "
                "but produce no observations. Install with: "
                "pip install halbert-core[audio-inference]"
            )

        # Start ingress adapters
        await self._init_ingress()

        # Start processing tasks
        self._tasks.append(
            asyncio.create_task(self._ingress_to_buffer_loop())
        )
        self._tasks.append(
            asyncio.create_task(self._speech_track_loop())
        )
        self._tasks.append(
            asyncio.create_task(self._ambient_track_loop())
        )

        await self._set_state(AudioState.IDLE, {"reason": "pipeline started"})
        logger.info("Audio pipeline started")

    async def stop(self) -> None:
        """Stop the audio pipeline."""
        self._running = False

        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        for adapter in self._ingress_adapters:
            try:
                await adapter.stop()
            except Exception as e:
                logger.error(f"Error stopping ingress {adapter.source_type}: {e}")
        self._ingress_adapters.clear()

        logger.info("Audio pipeline stopped")

    # ------------------------------------------------------------------
    # Ingress registration (public surface for the dashboard bootstrap)
    # ------------------------------------------------------------------

    async def add_ingress(self, adapter) -> bool:
        """Register and start an external ingress adapter.

        Used by the dashboard bootstrap (O2) to attach the WebRTC/browser
        ingress — the one adapter that has no config-file section of its
        own. Starts the adapter (mirroring ``_init_ingress``) so its
        ``chunks()`` iterator spins, then appends it to the adapter list;
        the ``_ingress_to_buffer_loop`` picks up adapters dynamically, so
        this is safe before or after ``start()``.

        Returns True if the adapter was registered, False if its ``start()``
        raised (the failure is logged and isolated — one broken ingress
        never takes the pipeline or the dashboard down).
        """
        try:
            await adapter.start()
        except Exception as e:
            logger.error(f"Ingress start failed ({adapter.source_type}): {e}")
            return False
        self._ingress_adapters.append(adapter)
        logger.info(f"Ingress registered: {adapter.source_type} (area={adapter.area_id})")
        return True

    def get_ingress(self, source_type: str):
        """Return the first registered ingress adapter with the given
        ``source_type``, or None if none matches."""
        return next(
            (a for a in self._ingress_adapters if a.source_type == source_type),
            None,
        )

    async def _init_engines(self) -> None:
        """Initialize speech and acoustic engines (lazy)."""
        try:
            from .speech.vad import VoiceActivityDetector
            self._vad = VoiceActivityDetector()
        except Exception as e:
            logger.warning(f"VAD init failed: {e}")

        try:
            from .speech.asr_engine import StreamingASR
            self._asr = StreamingASR()
        except Exception as e:
            logger.warning(f"ASR init failed: {e}")

        if self._config.tts.enabled:
            try:
                from .speech.tts_engine import PiperTTS
                self._tts = PiperTTS()
            except Exception as e:
                logger.warning(f"TTS init failed: {e}")

        try:
            from .speech.wake_word import WakeWordSpotter
            self._wake_word = WakeWordSpotter()
            if not self._wake_word.is_available():
                logger.info("Wake word model not found — hotkey-only activation")
        except Exception as e:
            logger.warning(f"Wake word init failed: {e}")

        if self._config.speaker_id.enabled:
            try:
                from .speech.speaker_id import SpeakerIdentifier
                self._speaker_id = SpeakerIdentifier()
            except Exception as e:
                logger.warning(f"Speaker ID init failed: {e}")

        if self._config.acoustic_events.enabled:
            try:
                from .acoustic.audio_tagger import AudioTagger
                self._audio_tagger = AudioTagger()
            except Exception as e:
                logger.warning(f"Audio tagger init failed: {e}")

    async def _init_ingress(self) -> None:
        """Start enabled ingress adapters."""
        if self._config.local_mic.enabled:
            try:
                from .ingress.local_mic import LocalMicIngress
                adapter = LocalMicIngress(
                    socket_port=self._config.local_mic.socket_port,
                )
                await adapter.start()
                self._ingress_adapters.append(adapter)
            except Exception as e:
                logger.error(f"Local mic ingress failed: {e}")

        if self._config.wyoming_ingress.enabled:
            try:
                from .ingress.wyoming_ingress import WyomingIngress
                adapter = WyomingIngress(
                    host=self._config.wyoming_ingress.host,
                    port=self._config.wyoming_ingress.port,
                    transcript_callback=self._handle_wyoming_transcript,
                )
                await adapter.start()
                self._ingress_adapters.append(adapter)
            except Exception as e:
                logger.error(f"Wyoming ingress failed: {e}")

    async def _ingress_to_buffer_loop(self) -> None:
        """Read chunks from all ingress adapters and feed into ring buffer."""
        while self._running:
            # Collect chunks from all adapters
            any_chunk = False
            for adapter in self._ingress_adapters:
                try:
                    chunk_gen = adapter.chunks()
                    async for chunk in chunk_gen:
                        await self._ring_buffer.write(chunk.pcm)
                        await self._chunk_queue.put(chunk)
                        any_chunk = True
                        break  # one chunk per adapter per iteration
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.debug(f"Ingress read error ({adapter.source_type}): {e}")

            if not any_chunk:
                await asyncio.sleep(0.01)  # brief yield if no data

    async def _speech_track_loop(self) -> None:
        """Track A: VAD -> wake word -> ASR -> speaker ID.

        Processes 32ms frames from the chunk queue. When VAD detects speech
        and either wake word is spotted or hotkey is active, starts ASR
        streaming and speaker identification.
        """
        if not self._vad:
            return

        frame_buffer = bytearray()
        frame_target = 960  # 30ms at 16kHz, 16-bit = 960 bytes

        while self._running:
            try:
                chunk = await asyncio.wait_for(self._chunk_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return

            frame_buffer.extend(chunk.pcm)

            # Process complete frames
            while len(frame_buffer) >= frame_target:
                frame = bytes(frame_buffer[:frame_target])
                del frame_buffer[:frame_target]

                try:
                    is_speech = self._vad.is_speech(frame)
                except Exception as e:
                    logger.debug(f"VAD error: {e}")
                    continue

                if is_speech and self._state == AudioState.IDLE:
                    # Check wake word if available
                    wake_detected = True  # default: VAD alone triggers
                    if self._wake_word and self._wake_word.is_available():
                        wake_detected = self._wake_word.detect(frame)

                    if wake_detected:
                        await self._set_state(
                            AudioState.LISTENING,
                            {"source": chunk.source, "area_id": chunk.area_id},
                        )
                        # Collect speech segment and run ASR
                        await self._process_speech_segment(chunk.source, chunk.area_id)

                # TASK-07: Barge-in — if VAD detects speech while SPEAKING,
                # cancel the current TTS playback (<120ms budget, spec B5).
                # Halbert uses cancel_all mode: all queued segments are cancelled.
                elif is_speech and self._state == AudioState.SPEAKING:
                    area_id = chunk.area_id if hasattr(chunk, "area_id") else ""
                    await self.trigger_barge_in(area_id=area_id)

    async def _process_speech_segment(self, source: str, area_id: str) -> None:
        """Collect a speech segment, run ASR + speaker ID, emit observation."""
        if not self._asr:
            await self._set_state(AudioState.IDLE, {})
            return

        # Read the last 10s from the ring buffer as the speech segment
        pcm = await self._ring_buffer.read_last_seconds(10.0)
        if not pcm:
            await self._set_state(AudioState.IDLE, {})
            return

        await self._set_state(AudioState.THINKING, {"reason": "transcribing"})

        try:
            text = self._asr.transcribe_chunk(pcm)
        except Exception as e:
            logger.error(f"ASR error: {e}")
            text = ""

        if not text:
            await self._set_state(AudioState.IDLE, {})
            return

        # Speaker identification
        speaker_id = ""
        speaker_name = ""
        speaker_role = "unknown"
        speaker_confidence = 0.0

        if self._speaker_id:
            try:
                match = self._speaker_id.identify(pcm)
                if match:
                    speaker_id = match.speaker_id
                    speaker_confidence = match.confidence
                    # Look up name/role from store
                    from .storage.speaker_store import SpeakerProfileStore
                    store = SpeakerProfileStore()
                    profile = store.get(speaker_id)
                    if profile:
                        speaker_name = profile.name
                        speaker_role = profile.role
                    await self._set_state(
                        AudioState.RECOGNIZED,
                        {"speaker": speaker_name, "role": speaker_role,
                         "confidence": speaker_confidence},
                    )
            except Exception as e:
                logger.debug(f"Speaker ID error: {e}")

        observation = VoiceTurnObservation(
            text=text,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            speaker_role=speaker_role,
            speaker_confidence=speaker_confidence,
            area_id=area_id,
            audio_duration_ms=len(pcm) // 32,  # 16kHz * 2 bytes = 32 bytes/ms
        )

        if self.on_voice_turn:
            try:
                await self.on_voice_turn(observation)
            except Exception as e:
                logger.error(f"Voice turn callback error: {e}")

        await self._set_state(AudioState.IDLE, {"reason": "turn complete"})

    async def _ambient_track_loop(self) -> None:
        """Track B: energy gate -> audio tagger -> anomaly detector.

        Processes 1-second windows from the ring buffer every check_interval_s.
        Bypasses when ambient energy is below the floor threshold.
        """
        if not self._config.acoustic_events.enabled or not self._audio_tagger:
            return

        interval = self._config.acoustic_events.check_interval_s

        while self._running:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return

            try:
                pcm = await self._ring_buffer.read_last_seconds(1.0)
                if not pcm:
                    continue

                # Energy floor gate
                if self._energy_below_floor(pcm):
                    continue

                # Classify
                events = self._audio_tagger.classify(pcm)
                for event in events:
                    obs = AcousticEventObservation(
                        sound_class=event.get("class", "unknown"),
                        confidence=event.get("confidence", 0.0),
                        decibel_level=event.get("decibel", 0.0),
                        is_anomaly=event.get("is_anomaly", False),
                        anomaly_severity=event.get("severity", 0),
                        source="ambient",
                    )
                    if self.on_acoustic_event:
                        try:
                            await self.on_acoustic_event(obs)
                        except Exception as e:
                            logger.error(f"Acoustic event callback error: {e}")

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug(f"Ambient track error: {e}")

    def _energy_below_floor(self, pcm: bytes) -> bool:
        """Check if audio energy is below the configured floor (dB)."""
        import math
        import struct
        n = len(pcm) // 2
        if n == 0:
            return True
        samples = struct.unpack(f'<{n}h', pcm)
        # RMS
        sum_sq = sum(s * s for s in samples)
        rms = (sum_sq / n) ** 0.5
        if rms == 0:
            return True
        # dBFS = 20 * log10(rms / 32768)
        db = 20 * math.log10(max(rms, 1) / 32768.0)
        return db < self._config.acoustic_events.energy_floor_db

    async def _handle_wyoming_transcript(
        self,
        text: str,
        conversation_id: str = "",
        area_id: str = "",
    ) -> None:
        """Handle a transcript from a Wyoming satellite (HA conversation pipeline)."""
        observation = VoiceTurnObservation(
            text=text,
            area_id=area_id,
            speaker_role="unknown",  # HA satellites don't do speaker ID
        )
        if self.on_voice_turn:
            try:
                await self.on_voice_turn(observation)
            except Exception as e:
                logger.error(f"Transcript callback error: {e}")

    async def _set_state(self, state: AudioState, context: Dict) -> None:
        """Update state and notify callback."""
        if state == self._state:
            return
        old = self._state
        self._state = state
        logger.debug(f"Audio state: {old.value} -> {state.value} ({context})")
        if self.on_state_change:
            try:
                await self.on_state_change(state, context)
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    def get_status(self) -> dict:
        """Status dict for the /api/audio/status endpoint."""
        return {
            "enabled": self._config.enabled,
            "running": self._running,
            "available": is_audio_available(),
            "state": self._state.value,
            "ingress_sources": [
                a.status for a in self._ingress_adapters
            ],
            "engines": {
                "vad": self._vad is not None,
                "asr": self._asr is not None,
                "tts": self._tts is not None,
                "wake_word": self._wake_word is not None
                and self._wake_word.is_available(),
                "speaker_id": self._speaker_id is not None,
                "audio_tagger": self._audio_tagger is not None,
            },
        }

    # ------------------------------------------------------------------
    # Voice delivery + barge-in (TASK-07)
    # ------------------------------------------------------------------

    def _get_barge_in_handler(self):
        """Get or create the BargeInHandler (lazy)."""
        if self._barge_in_handler is None:
            try:
                from .speech.barge_in import BargeInHandler
                self._barge_in_handler = BargeInHandler()
            except Exception as e:
                logger.warning(f"BargeInHandler init failed: {e}")
        return self._barge_in_handler

    def create_barge_in_token(self):
        """Create a BargeInToken for the current TTS turn.

        The wiring layer calls this before starting voice synthesis and
        passes the token to both the VoiceBackend (for synthesis cancellation)
        and the pipeline (for VAD-triggered barge-in). When VAD detects
        speech during SPEAKING state, ``trigger_barge_in()`` fires the token,
        cancelling synthesis in <120ms (spec B5).
        """
        handler = self._get_barge_in_handler()
        if handler is None:
            return None
        token = handler.create_token()
        self._active_barge_in_token = token
        return token

    async def trigger_barge_in(self, area_id: str = "") -> Optional[Any]:
        """Trigger barge-in: cancel current TTS playback.

        Called when VAD detects speech during SPEAKING state. Cancels all
        queued speech segments (Halbert uses ``cancel_all`` mode per spec
        4.4). The <120ms budget is from VAD detection to local audio silence.

        Returns a BargeInResult, or None if no barge-in handler is available.
        """
        handler = self._get_barge_in_handler()
        if handler is None or self._active_barge_in_token is None:
            return None
        result = await handler.trigger(
            self._active_barge_in_token,
            area_id=area_id,
        )
        self._active_barge_in_token = None
        logger.info(
            f"Barge-in triggered: latency={result.latency_ms:.0f}ms, "
            f"local={result.cancelled_local}"
        )
        return result

    async def speak(
        self,
        text: str,
        prosody: Optional[Any] = None,
    ) -> None:
        """Synthesize and play text through the TTS engine with barge-in support.

        This is the pipeline's voice delivery entry point. The wiring layer
        calls this when the modality resolver decides the response should be
        spoken (VOICE modality). The method:
        1. Transitions to SPEAKING state
        2. Creates a BargeInToken for cancellation
        3. Synthesizes text through PiperTTS (checking the token between chunks)
        4. Plays the PCM audio through the output device
        5. Transitions back to IDLE when done

        Barge-in: if VAD detects speech during synthesis, the speech track
        loop calls ``trigger_barge_in()`` which fires the token, causing
        the TTS generator to abort immediately (<120ms).
        """
        if not self._tts:
            logger.warning("Cannot speak: TTS engine not initialized")
            return

        await self._set_state(AudioState.SPEAKING, {"reason": "tts playback"})
        token = self.create_barge_in_token()

        try:
            async for pcm_chunk in self._tts.synthesize(text, cancel_token=token):
                if token is not None and token.is_set():
                    logger.debug("Speak: barge-in received, aborting playback")
                    break
                # In a full implementation, this would write to the audio
                # output device. For now, the chunks are consumed by the
                # VoiceBackend adapter which handles playback.
                # The pipeline's role is state management + barge-in coordination.
                pass
        except Exception as e:
            logger.error(f"Speak failed: {e}")
        finally:
            self._active_barge_in_token = None
            await self._set_state(AudioState.IDLE, {"reason": "playback complete"})
