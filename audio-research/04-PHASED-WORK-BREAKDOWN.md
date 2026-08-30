# Phased Work Breakdown: Halbert Audio AI Implementation

> **Document:** `audio-research/04-PHASED-WORK-BREAKDOWN.md`  
> **Status:** Approved Engineering Work Breakdown  
> **Date:** 2026-08-29  
> **Scope:** 38 Total Tasks (35 Phased Tasks + 3 Cross-Cutting Tasks)  
> **Model Tiers:** `opus` (Architecture / DSP / Rust / Concurrency), `sonnet` (Python Engines / React UI / SQLite), `haiku` (Configs / Schemas / Docs)  

---

## Task Matrix Overview

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               PHASED IMPLEMENTATION ROADMAP                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 1: Core Auditory Engine & Zero-PyTorch Inference        │ 8 Tasks  │ ~25% Effort │
│ Phase 2: Multi-Ingress Adapters & Desktop Menu Bar Companion  │ 7 Tasks  │ ~20% Effort │
│ Phase 3: Biometric Speaker Identification & Safety RoleGates  │ 7 Tasks  │ ~20% Effort │
│ Phase 4: Acoustic Event Detection (AED) & Music Tagging       │ 7 Tasks  │ ~20% Effort │
│ Phase 5: Cloud Omni Live Duplex & WebRTC Multi-Modal Stream   │ 6 Tasks  │ ~10% Effort │
│ Cross-Cutting: Verification, Packaging & Telemetry            │ 3 Tasks  │ ~5% Effort  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Auditory Engine Foundation (`halbert_core/audio/`)

### `TSK-AUD-01` Scaffold Audio Module Architecture & Config
* **Target Files:** `halbert_core/halbert_core/audio/__init__.py`, `halbert_core/halbert_core/audio/config.py`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Create base `AudioConfig` dataclass supporting sample rates (16kHz), chunk sizes (512 samples / 32ms), energy floor thresholds, device IDs, and ONNX model paths.
* **Acceptance Criteria:** `AudioConfig.from_env()` loads environment variables with sane defaults; unit tests verify serialization.

### `TSK-AUD-02` Lock-Free Circular Audio Ring Buffer
* **Target Files:** `halbert_core/halbert_core/audio/buffer.py`
* **Model Tier:** `opus` | **Effort:** `xhigh`
* **Description:** Implement lock-free 10-second rolling circular buffer (160,000 samples @ 16-bit 16kHz PCM) with atomic slice extraction and zero GIL locking.
* **Acceptance Criteria:** Unit tests verify continuous concurrent writes and reads with zero dropped frames or thread deadlocks over 100,000 frames.

### `TSK-AUD-03` Silero VAD v5 ONNX Integration
* **Target Files:** `halbert_core/halbert_core/audio/speech/vad.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Wrap Silero VAD v5 ONNX model for 30ms frame speech onset and offset classification with hysteresis thresholding.
* **Acceptance Criteria:** Correctly detects speech onset ($P > 0.6$) and silence offset with $<1.0\text{ms}$ inference latency on single CPU core.

### `TSK-AUD-04` Sherpa-ONNX Zipformer INT8 Streaming ASR
* **Target Files:** `halbert_core/halbert_core/audio/speech/asr_engine.py`
* **Model Tier:** `sonnet` | **Effort:** `max`
* **Description:** Integrate `sherpa-onnx` streaming Zipformer INT8 engine to incrementally emit transcription tokens as audio frames arrive.
* **Acceptance Criteria:** Transcribes 16kHz audio with first-token latency $<50\text{ms}$; achieves $<8\%$ WER on LibriSpeech clean benchmark.

### `TSK-AUD-05` Piper TTS Streaming Audio Synthesizer
* **Target Files:** `halbert_core/halbert_core/audio/speech/tts_engine.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Integrate Piper neural TTS VITS ONNX model generating streaming 16kHz PCM chunks with cancellation token support.
* **Acceptance Criteria:** Generates first audio chunk in $<150\text{ms}$; stops generating immediately when cancellation token is set.

### `TSK-AUD-06` Atomic Barge-In Stream Cancellation Handler
* **Target Files:** `halbert_core/halbert_core/audio/speech/barge_in.py`
* **Model Tier:** `opus` | **Effort:** `xhigh`
* **Description:** Coordinate VAD speech detection with active TTS playback buffer: when user speaks during TTS output, emit atomic cancel and flush audio buffers within $<120\text{ms}$.
* **Acceptance Criteria:** Benchmark test confirms audio playback output halts in $<120\text{ms}$ upon synthetic speech onset.

### `TSK-AUD-07` Auditory Cortex Master Coordinator
* **Target Files:** `halbert_core/halbert_core/audio/coordinator.py`
* **Model Tier:** `opus` | **Effort:** `ultracode`
* **Description:** Central coordinator managing Track A (Conversational Voice) and Track B (Ambient Anomaly Perception), routing events into Halbert State Machine.
* **Acceptance Criteria:** Full turn-based end-to-end integration test passes from PCM chunk ingestion to completed agent response.

### `TSK-AUD-08` Phase 1 Unit & Benchmark Test Suite
* **Target Files:** `tests/test_audio_core.py`, `tests/test_audio_buffer.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Automated test suite covering buffer overflow, VAD classification, ASR streaming accuracy, and TTS synthesis.
* **Acceptance Criteria:** 100% test pass rate with coverage $>90\%$ across `halbert_core/audio/`.

---

## Phase 2: Multi-Ingress Adapters & Desktop Menu Bar Companion

### `TSK-AUD-09` Upgraded Wyoming Ingress (PCM Audio Chunks)
* **Target Files:** `halbert_core/halbert_core/integrations/wyoming_agent.py`, `halbert_core/halbert_core/audio/ingress/wyoming_ingress.py`
* **Model Tier:** `opus` | **Effort:** `max`
* **Description:** Update Wyoming TCP server on port 10400/10401 to handle raw `"audio-chunk"` JSONL payloads with resilient socket cleanup and timeout protection (`CRIT-01`).
* **Acceptance Criteria:** Accepts streaming PCM chunks from Home Assistant ESP32 satellites with zero leaked socket descriptors under stress testing.

### `TSK-AUD-10` Rust Microphone Capture & DSP via `cpal`
* **Target Files:** `src-tauri/src/audio_capture.rs`, `src-tauri/src/lib.rs`
* **Model Tier:** `opus` | **Effort:** `ultracode`
* **Description:** Implement native CoreAudio / ALSA microphone stream capture in Rust with software AEC filtering via `webrtc-audio-processing`.
* **Acceptance Criteria:** Captures clean 16kHz mono PCM with $<5\text{ms}$ driver latency and filters loopback speaker output.

### `TSK-AUD-11` macOS Non-Activating Floating Panel (`tauri-nspanel`)
* **Target Files:** `src-tauri/src/floating_panel.rs`, `src-tauri/Cargo.toml`
* **Model Tier:** `opus` | **Effort:** `xhigh`
* **Description:** Create floating HUD using `tauri-nspanel` (`NSPanel` with `.nonactivatingPanel` mask) to prevent stealing focus from active IDE or terminal (`HIGH-03`).
* **Acceptance Criteria:** Pressing global hotkey displays HUD on top of full-screen terminal without losing cursor focus in the terminal.

### `TSK-AUD-12` Global Hotkey Registration (`Cmd+Shift+Space`)
* **Target Files:** `src-tauri/src/lib.rs`
* **Model Tier:** `sonnet` | **Effort:** `med`
* **Description:** Register global system shortcut (`Cmd+Shift+Space` on macOS, `Ctrl+Shift+Space` on Linux) to toggle floating voice companion.
* **Acceptance Criteria:** Shortcut toggles voice companion HUD globally across all desktop spaces.

### `TSK-AUD-13` Frigate RTSP Audio Track Ingress via Symphonia
* **Target Files:** `halbert_core/halbert_core/audio/ingress/rtsp_ingress.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Extract and decode audio tracks from Frigate / IP camera RTSP streams into 16kHz PCM using `symphonia` (`HIGH-07`).
* **Acceptance Criteria:** Successfully transcodes live RTSP AAC/Opus audio to raw PCM and pushes to ambient anomaly ring buffer.

### `TSK-AUD-14` WebRTC WebSocket Audio Ingress for Browser Dashboard
* **Target Files:** `halbert_core/halbert_core/dashboard/routes/audio.py`, `halbert_core/halbert_core/audio/ingress/webrtc_ingress.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** FastAPI WebSocket endpoint `/api/audio/stream` accepting binary PCM / Opus chunks from web browser client.
* **Acceptance Criteria:** Web dashboard microphone stream connects, negotiates VAD, and streams transcription over WebSocket.

### `TSK-AUD-15` Frontend Voice Companion Floating HUD Component
* **Target Files:** `dashboard/frontend/src/components/agent/VoiceCompanionPill.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** React floating HUD rendering live streaming speech tokens, active tool badges, and waveform animations.
* **Acceptance Criteria:** Renders smooth 60fps animations; dismisses on `Escape` key; displays real-time agent responses.

---

## Phase 3: Biometric Speaker Identification & Safety RoleGates

### `TSK-AUD-16` CAM++ ONNX 256-Dim Speaker Embedding Extractor
* **Target Files:** `halbert_core/halbert_core/audio/speech/speaker_id.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Implement CAM++ ONNX model generating 256-dimensional L2-normalized speaker embedding vectors from speech utterances.
* **Acceptance Criteria:** Extracts 256-dim embedding vector in $<5\text{ms}$ on CPU; cosine similarity $>0.80$ for matching speaker.

### `TSK-AUD-17` SQLite Speaker Profile Repository (`speaker_profiles`)
* **Target Files:** `halbert_core/halbert_core/audio/storage/speaker_store.py`
* **Model Tier:** `sonnet` | **Effort:** `med`
* **Description:** SQLite repository managing household voiceprints with atomic centroid smoothing and threshold calibration (`HIGH-05`).
* **Acceptance Criteria:** Enrolls, updates, and matches speaker embeddings with SQLite WAL-mode transactional safety.

### `TSK-AUD-18` Safety RoleGate Integration in Tool Framework
* **Target Files:** `halbert_core/halbert_core/approval/engine.py`, `halbert_core/halbert_core/tools/system_tools.py`
* **Model Tier:** `opus` | **Effort:** `xhigh`
* **Description:** Enforce `RoleGate`: privileged tools (ZFS, SSH, reboot, alarm disarming) require verified `speaker_role == "admin"` (`HIGH-01`).
* **Acceptance Criteria:** Attempting privileged tool from non-admin voice turn triggers Level 3 confirmation block or PIN requirement.

### `TSK-AUD-19` Interactive Voice Enrollment Modal Component
* **Target Files:** `dashboard/frontend/src/components/settings/VoiceEnrollmentModal.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** 3-turn interactive voice enrollment wizard with real-time volume VU meter and SNR quality feedback.
* **Acceptance Criteria:** Guides user through 3 spoken prompts, computes centroid, and displays enrollment success confirmation.

### `TSK-AUD-20` Household Voice Biometrics Settings Card
* **Target Files:** `dashboard/frontend/src/components/settings/SpeakerProfilesCard.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Renders enrolled household speakers with role badges, confidence thresholds, and test-voice verification buttons.
* **Acceptance Criteria:** Allows admin to view, rename, adjust role permissions, or delete enrolled voice profiles.

### `TSK-AUD-21` Speaker Identification FastAPI Endpoints
* **Target Files:** `halbert_core/halbert_core/dashboard/routes/audio.py`
* **Model Tier:** `sonnet` | **Effort:** `med`
* **Description:** REST endpoints for enrolling speaker (`POST /api/audio/speakers/enroll`), testing voice (`POST /api/audio/speakers/test`), and listing profiles (`GET /api/audio/speakers`).
* **Acceptance Criteria:** Endpoints validate input audio payloads and return structured match confidence results.

### `TSK-AUD-22` Phase 3 Biometric Security & RoleGate Test Suite
* **Target Files:** `tests/test_speaker_biometrics.py`, `tests/test_rolegate_safety.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Automated tests validating cross-speaker rejection, centroid update smoothing, and unauthorized tool execution blocks.
* **Acceptance Criteria:** 100% pass rate on biometric security tests.

---

## Phase 4: Acoustic Event Detection (AED) & Music Tagging

### `TSK-AUD-23` YAMNet ONNX Environmental Sound Classifier
* **Target Files:** `halbert_core/halbert_core/audio/acoustic/yamnet.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Implement YAMNet ONNX inference on 0.96s log-mel spectrogram patches classifying 521 AudioSet sound categories.
* **Acceptance Criteria:** Executes in $<3.5\text{ms}$ on CPU; correctly identifies smoke alarm chirps, glass breaks, and music.

### `TSK-AUD-24` Acoustic Taxonomy & Category Mapper
* **Target Files:** `halbert_core/halbert_core/audio/acoustic/taxonomy.py`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Map raw 521 AudioSet classes into 6 human categories: `Life Safety`, `Security`, `Mechanical`, `Water`, `Pet`, `Music` (`MED-01`).
* **Acceptance Criteria:** Mapping dictionary correctly groups all AudioSet classes and assigns severity levels (0 to 3).

### `TSK-AUD-25` Anomaly Evaluator & SystemEvent Integration
* **Target Files:** `halbert_core/halbert_core/audio/acoustic/anomaly_detector.py`, `halbert_core/halbert_core/integrations/system_event_mapper.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Evaluate sliding spectrograms for T3 smoke / T4 CO alarm patterns and pipe hissing; emit structured `SystemEvent` to cognitive bus.
* **Acceptance Criteria:** T3 alarm sound pattern triggers Level 3 critical life safety event dispatch.

### `TSK-AUD-26` Chromaprint / AcoustID Music Identifier with Offline Fallback
* **Target Files:** `halbert_core/halbert_core/audio/acoustic/music_fingerprint.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Audio fingerprinting via Chromaprint; query AcoustID API when WAN is online, fall back to local ONNX genre/tempo classifier when offline (`HIGH-04`).
* **Acceptance Criteria:** Correctly identifies popular songs online; falls back gracefully to genre tagging when offline.

### `TSK-AUD-27` Quiet Hours Policy & Suppression Rules
* **Target Files:** `halbert_core/halbert_core/audio/acoustic/quiet_hours.py`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Mute proactive voice alerts during configured quiet hours (`22:00–07:00`) unless event severity is Level 3 Life Safety (`MED-02`).
* **Acceptance Criteria:** Advisory and warning voice alerts are muted during quiet hours; smoke alarm alerts bypass muting.

### `TSK-AUD-28` Acoustic Event Card Component in Temporal Chronicle
* **Target Files:** `dashboard/frontend/src/components/agent/AcousticEventCard.tsx`, `dashboard/frontend/src/components/agent/Timeline.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Chronicle event card displaying acoustic category, confidence, sound level (dB), camera snapshot inlays, and quick action buttons.
* **Acceptance Criteria:** Renders styled alert cards in timeline with 1-click camera snapshot preview.

### `TSK-AUD-29` Phase 4 AED & Music Recognition Test Suite
* **Target Files:** `tests/test_yamnet_aed.py`, `tests/test_music_fingerprint.py`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Unit tests validating AudioSet classification, anomaly gating, quiet hours suppression, and music fallback.
* **Acceptance Criteria:** 100% pass rate across all acoustic perception tests.

---

## Phase 5: Cloud Omni Live Duplex & Frontend Settings

### `TSK-AUD-30` Gemini Multimodal Live API WebRTC / WebSocket Bridge
* **Target Files:** `halbert_core/halbert_core/audio/live_bridge.py`
* **Model Tier:** `opus` | **Effort:** `max`
* **Description:** Bidirectional streaming connector to Google Gemini Multimodal Live API over WebSockets/WebRTC (PCM audio + JPEG screen frames).
* **Acceptance Criteria:** Streams duplex audio with $<300\text{ms}$ round-trip latency to Gemini Live model.

### `TSK-AUD-31` Ambient Acoustic Aura Header Indicator Component
* **Target Files:** `dashboard/frontend/src/components/agent/AcousticAura.tsx`, `dashboard/frontend/src/components/Layout.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Organic header indicator rendering idle aura, listening spectrum, recognized speaker pill, and thinking pulses.
* **Acceptance Criteria:** Animates smoothly between states; reflects live decibel levels and speaker identification badge.

### `TSK-AUD-32` Audio & Voice Settings Tab Component
* **Target Files:** `dashboard/frontend/src/components/settings/AudioSettingsTab.tsx`, `dashboard/frontend/src/pages/Settings.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Settings tab under `System & Security → Audio & Voice` managing inference engine mode, ingress sources, and quiet hours.
* **Acceptance Criteria:** Loads and saves audio configuration via REST API; displays live satellite connection status.

### `TSK-AUD-33` Multi-Modal Live Audio + Screen Capture Pairing
* **Target Files:** `halbert_core/halbert_core/dashboard/routes/agent.py`, `dashboard/frontend/src/components/agent/AgentChat.tsx`
* **Model Tier:** `sonnet` | **Effort:** `high`
* **Description:** Wire combined screen capture snapshot with live voice turn for visual-audio reasoning in agent chat.
* **Acceptance Criteria:** Chat turn with attached screenshot and voice command correctly passes both modalities to LLM.

### `TSK-AUD-34` Audio Telemetry & Buffer Drop Logging
* **Target Files:** `halbert_core/halbert_core/audio/telemetry.py`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Track audio buffer latency, VAD trigger counts, ASR inference durations, and dropped frames (`LOW-01`).
* **Acceptance Criteria:** Emits structured JSON metrics to telemetry engine and debug log.

### `TSK-AUD-35` Phase 5 End-to-End System Integration Suite
* **Target Files:** `tests/test_audio_system_e2e.py`
* **Model Tier:** `sonnet` | **Effort:** `max`
* **Description:** Full end-to-end integration test exercising multi-ingress, ASR, biometrics, safety gates, and UI event streaming.
* **Acceptance Criteria:** Complete end-to-end user voice session passes automated verification.

---

## Cross-Cutting Tasks

### `TSK-AUD-36` macOS Permissions & Sandbox Entitlements
* **Target Files:** `src-tauri/tauri.conf.json`, `src-tauri/Info.plist`, `packaging/entitlements.mac.plist`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Configure microphone device entitlements (`com.apple.security.device.microphone`) and `NSMicrophoneUsageDescription` (`MED-03`).
* **Acceptance Criteria:** macOS build prompts user cleanly for microphone access on first launch without crash.

### `TSK-AUD-37` Package Manifests & Optional Extras Configuration
* **Target Files:** `halbert_core/pyproject.toml`, `deploy/Dockerfile.home`, `deploy/Dockerfile.pro`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Add `[project.optional-dependencies] audio = [...]` and bundle ONNX models in Docker and desktop build artifacts.
* **Acceptance Criteria:** `pip install -e ".[audio]"` installs cleanly with zero dependency conflicts.

### `TSK-AUD-38` Architectural & User Documentation Updates
* **Target Files:** `documentation/architecture/AUDIO-ARCHITECTURE.md`, `documentation/guides/VOICE-ASSISTANT-SETUP.md`
* **Model Tier:** `haiku` | **Effort:** `med`
* **Description:** Comprehensive architectural guide and user manual for setting up Wyoming voice satellites, enrolling voiceprints, and configuring Quiet Hours.
* **Acceptance Criteria:** Complete, polished markdown documentation committed to the repository.
