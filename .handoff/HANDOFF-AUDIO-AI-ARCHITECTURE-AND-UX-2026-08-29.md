# Audio AI Architecture, Review Packet & UX Interaction Blueprint

> **Handoff & Specification Document for Peer AI Review & Implementation**  
> **Document:** `.handoff/HANDOFF-AUDIO-AI-ARCHITECTURE-AND-UX-2026-08-29.md`  
> **Author:** Eric Bintner & Halbert Research  
> **Date:** 2026-08-29  
> **Status:** SUPERSEDED — Technical scrutiny found 5 critical, 7 high, 4 medium, 5 low issues.
> See `.handoff/audio/00-REVIEW-SUMMARY.md` for corrected architecture and work breakdown.
> Original research suite (`audio-research/01-03`) remains valid as background; corrections in `01-CORRECTED-ARCHITECTURE.md` are what implementation must follow.  
> **Target Platforms:** macOS Desktop (Tauri Pro / Menu Bar), Linux Homelab Server (HAOS / Docker), Web Dashboard  

---

## 1. Executive Summary

Halbert's current audio footprint relies solely on a downstream text proxy ([`wyoming_agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/wyoming_agent.py)) that receives pre-transcribed text strings from Home Assistant's voice satellites. While functional for basic smart-home relaying, this leaves Halbert completely **deaf to raw acoustic reality** (no environmental anomaly detection, no biometric speaker verification, no music/media tracking, and zero standalone voice capability for Halbert Pro desktop users).

This document packages:
1. **The Technical Architecture Review Packet:** A formal specification of **"The Halbert Auditory Cortex"** (`halbert_core/audio/`), detailing multi-ingress adapters, the dual-track inference engine (Conversational Voice vs. Ambient Sound/Anomalies/Music), Zero-PyTorch Subtractive Contract compliance, and SQLite biometric schemas for peer AI review.
2. **UX & Product Interaction Research:** Concrete interaction blueprints, ASCII wireframes, and frontend component designs explaining how audio perception embodies the user interface across the Web Dashboard, macOS Menu Bar companion, and Temporal Chronicle.

---

## 2. Part I: Technical Architecture Review Packet

### 2.1 The Auditory Cortex Pipeline (`halbert_core/audio/`)

```
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                                   INGRESS ADAPTER LAYER (Multi-Source)
═════════════════════════════════════════════════════════════════════════════════════════════════════════
  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
  │ Local Microphone     │  │ Wyoming TCP Satellite│  │ RTSP Camera Audio    │  │ WebRTC / Dashboard   │
  │ (Rust cpal / Tauri)  │  │ (ESP32 / Pi on 10400)│  │ (Frigate Security)   │  │ (FastAPI WebSocket)  │
  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
             │                         │                         │                         │
             └─────────────────────────┴────────────┬────────────┴─────────────────────────┘
                                                    │ (Normalized 16kHz 16-bit PCM Stream)
                                                    ▼
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                            HALBERT AUDITORY CORTEX (halbert_core/audio/)
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                                                    │
                               ┌────────────────────┴────────────────────┐
                               │   Circular Ring Buffer (10.0s Memory)   │
                               └──────────┬────────────────────────┬─────┘
                                          │                        │
               ┌──────────────────────────┘                        └──────────────────────────┐
               ▼ (Active Voice Stream: 30ms Frames)                                           ▼ (Continuous 1.0s Spectrogram)
 ┌───────────────────────────────────────────────┐                          ┌───────────────────────────────────────────────┐
 │ TRACK A: Conversational Speech & Biometrics   │                          │ TRACK B: Ambient Sound, Anomalies & Music     │
 ├───────────────────────────────────────────────┤                          ├───────────────────────────────────────────────┤
 │ 1. Silero VAD v5 (Speech / Silence Gating)    │                          │ 1. Energy Floor Gate (Bypasses when silent)   │
 │ 2. Wake Word Spotting ("Hey Halbert")         │                          │ 2. YAMNet ONNX (521 AudioSet Sound Classes)   │
 │ 3. Streaming ASR (Sherpa Zipformer / Whisper) │                          │    - Glass break, Smoke alarm, Water leak     │
 │ 4. ECAPA-TDNN ONNX (Speaker ID & Role Auth)   │                          │ 3. Chromaprint / AcoustID (Music Identifier)  │
 │ 5. Barge-In Interrupt Handler                 │                          │ 4. Acoustic Scene Descriptor (TV/Media filter)│
 └───────────────────────┬───────────────────────┘                          └───────────────────────┬───────────────────────┘
                         │                                                                          │
                         ▼                                                                          ▼
 ┌───────────────────────────────────────────────┐                          ┌───────────────────────────────────────────────┐
 │ VoiceTurnObservation                          │                          │ AcousticEventObservation                      │
 │ - text: "reboot host zfs pool"                │                          │ - class: "smoke_detector_alarm" (conf: 0.94)  │
 │ - speaker_id: "eric" (role: "admin")          │                          │ - music: "Daft Punk - Tron Legacy"            │
 │ - area_id: "office"                           │                          │ - anomaly_level: 3 (Critical Life Safety)     │
 └───────────────────────┬───────────────────────┘                          └───────────────────────┬───────────────────────┘
                         │                                                                          │
                         └───────────────────────────────┬──────────────────────────────────────────┘
                                                         │
                                                         ▼
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                                   COGNITION & SAFETY EXECUTION LAYER
═════════════════════════════════════════════════════════════════════════════════════════════════════════
  ┌─────────────────────────────────┐   ┌─────────────────────────────────┐   ┌─────────────────────────────────┐
  │ Halbert State Machine           │   │ ToolSafetyFramework             │   │ PersonaMemoryStore (SQLite FTS5)│
  │ - Conversational agent turn     │   │ - Admin role confirmed for ZFS  │   │ - Episodic sound & music log    │
  │ - Proactive anomaly alert       │   │ - Safe tool execution           │   │ - User music preference profile │
  └─────────────────────────────────┘   └─────────────────────────────────┘   └─────────────────────────────────┘
```

### 2.2 Subtractive Contract & Zero-PyTorch Guarantees
Halbert mandates that `halbert_core` dependencies remain subtractive (`pyyaml>=6.0`, `requests>=2.31.0` as hard core requirements). All ML audio inference runs through **`sherpa-onnx`** (C++ static engine with lightweight Python bindings) or **`onnxruntime`**:
* **Silero VAD v5 ONNX:** $<5\text{MB}$ RAM, $<1\text{ms}$ inference / 30ms chunk.
* **Zipformer INT8 ASR / Moonshine ONNX:** ~120MB RAM, $<50\text{ms}$ streaming latency on CPU.
* **ECAPA-TDNN ONNX (Speaker ID):** 192-dimensional embedding, ~25MB ONNX, $<10\text{ms}$ per utterance.
* **YAMNet ONNX (Acoustic Events):** 521 AudioSet classes, 3.7M parameters (~14MB ONNX), $<3\text{ms}$ per 0.96s window.
* **Total Audio Subsystem Footprint:** $<135\text{MB}$ total disk space, $<300\text{MB}$ runtime RAM, $<5\%$ continuous CPU load on an Intel N100 / Pi 5.

### 2.3 SQLite Biometric & Safety Schemas

```sql
-- Enrolled Household Speaker Biometrics
CREATE TABLE IF NOT EXISTS speaker_profiles (
    speaker_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member', 'guest', 'restricted')),
    embedding_centroid BLOB NOT NULL, -- 192-dim float32 vector (768 bytes)
    sample_count INTEGER DEFAULT 1,
    threshold REAL DEFAULT 0.75,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Acoustic Event Chronicle Log
CREATE TABLE IF NOT EXISTS acoustic_event_log (
    event_id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    source_type TEXT NOT NULL,       -- 'local_mic', 'wyoming_satellite', 'frigate_rtsp'
    area_id TEXT,                    -- 'living_room', 'kitchen', 'server_rack'
    sound_class TEXT NOT NULL,       -- 'Smoke detector', 'Glass shatter', 'Music'
    confidence REAL NOT NULL,
    decibel_level REAL,
    is_anomaly BOOLEAN DEFAULT 0,
    anomaly_severity INTEGER DEFAULT 0, -- 0=Info, 1=Warning, 2=Confirm, 3=Critical
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_acoustic_timestamp ON acoustic_event_log(timestamp);
```

### 2.4 Questions & Verification Vectors for Reviewing AI
1. **Wyoming Socket Lifecycle:** Does the async TCP handler in `wyoming_ingress.py` properly handle buffer drains when switching from 16kHz PCM audio chunk mode to text responses without leaking file descriptors during sudden satellite disconnections?
2. **Lock-Free Ring Buffer vs. GIL:** Is `collections.deque(maxlen=160000)` sufficient for multi-producer thread audio chunk buffering in Python, or should the circular buffer live natively in the Rust Tauri layer (`src-tauri/src/audio_buffer.rs`)?
3. **Barge-In Latency Budget:** When user speech is confirmed via Silero VAD ($P(\text{speech}) > 0.6$ across 3 consecutive frames), can the cancellation token reach the active Piper TTS generator within the $<150\text{ms}$ human perception threshold?

---

## 3. Part II: UX & Product Interaction Architecture

How do these audio capabilities translate into what the user sees, touches, and hears? Halbert’s UX avoids the clutter of standard smart-home dashboards, delivering an ambient, sentient interface across **5 dedicated surfaces**.

---

### UX Surface 1: The Ambient "Acoustic Aura" & Voice Waveform

In both the Web Dashboard and desktop application, Halbert’s header features a dynamic **Acoustic Aura Indicator** that communicates auditory state without distracting text flashes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [Logo] Halbert Home  |  Living Room  |  ( ( ( ● ) ) ) Acoustic State: Idle  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Visual State Transitions:
1. **Idle State (Monitoring):** A calm, breathing charcoal/vermilion aura. Shows connected satellites (e.g. `Living Room Sat • Mic OK`).
2. **Wake-Word / Hotkey Activated (`Listening`):** The aura expands into a real-time 32-bar fluid frequency visualizer (`VoiceWaveformIndicator.tsx`).
3. **Biometric Identification (`Recognized`):** Instantly displays the verified user badge:  
   `[ 👤 Eric (Admin) • 96% Match ]`
4. **Agent Turn (`Thinking`):** A smooth indeterminate pulse as the LLM state machine plans tool executions.
5. **Agent Speaking (`Speaking` / Duplex):** Synchronized speech waveform rendering with a subtle **"Tap or Speak to Interrupt"** prompt (barge-in ready).

```
+-----------------------------------------------------------------------------+
│  VOICE INTERACTION HUD (Active Turn)                                        │
│                                                                             │
│   "Turn off the basement exhaust fan and check ZFS pool status"             │
│   👤 Eric (Admin) | 📍 Office | 🔊 82dB                                      │
│                                                                             │
│   ▂▃▅▇█▆▅▃▂  [Speaking: "ZFS pool is healthy. Shutting off fan..."]         │
│                                                                             │
│   [ Space / Click to Interrupt ]                      [ Mute Microphone ]   │
+-----------------------------------------------------------------------------+
```

---

### UX Surface 2: The macOS Menu Bar & System Tray Companion (`VoiceCompanionPill.tsx`)

For Halbert Pro users, Halbert lives in the macOS Menu Bar (`NSStatusItem`).

* **Global Hotkey:** `Cmd+Shift+Space` (or Hold-to-Talk).
* **Floating Frosted HUD:** A lightweight, non-stealing floating pill appears centered at the top of the screen (similar to Siri / Apple Intelligence HUD), overlaying whichever IDE or terminal the sysadmin is working in.
* **Instant Voice Turn:** Captures voice via Rust `cpal`, streams transcript tokens in real-time, displays tool executions (`tool_call: zpool status`), and reads back the summary via Piper TTS while streaming the result to clipboard or terminal.

```
                  ┌──────────────────────────────────────────────┐
                  │ ⚡ [Halbert Pro] 👤 Eric (Admin)             │
                  │ "Deploying latest container to staging..."   │
                  │ ▂▃▅█▆▅▃▂ [ Esc to dismiss | Space to pause ] │
                  └──────────────────────────────────────────────┘
```

---

### UX Surface 3: Speaker Enrollment & Biometric Governance (`SpeakerProfilesCard.tsx`)

A dedicated Settings interface allows household administrators to enroll voiceprints and configure safety permissions:

```
+-----------------------------------------------------------------------------+
│ HOUSEHOLD VOICE BIOMETRICS & PERMISSION GATES                               │
+-----------------------------------------------------------------------------+
│                                                                             │
│  Enrolled Speakers (3)                                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 👤 Eric Bintner (Admin)                 [ 98% Conf ]  [ Edit ] [ Test ]│  │
│  │    Permissions: Full System Access (ZFS, SSH, Deadbolts, Alarms)       │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 👤 Sarah (Member)                       [ 94% Conf ]  [ Edit ] [ Test ]│  │
│  │    Permissions: Standard Home (Lights, Thermostat, Media, Vacuum)      │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 👤 Guest Voiceprint (Restricted)        [ Auto-Assigned ]      [ Gate ]│  │
│  │    Permissions: Read-Only Info & Safe Lighting (PIN required for locks)│  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [ + Enroll New Household Voice ]                                           │
│                                                                             │
│  Interactive Voice Enrollment Wizard:                                       │
│  Step 1 of 3: "Please say clearly: 'Hey Halbert, check system health'"      │
│  [ 🎙️ Listening... ━━━━━━━━━━━━━━━━━━━━ 100% ]                              │
│  Generated 192-dim acoustic centroid. Quality: Excellent (0.96 SNR).        │
+-----------------------------------------------------------------------------+
```

---

### UX Surface 4: Environmental Acoustic Anomaly Cards in Temporal Chronicle

Non-speech acoustic events are automatically tagged and surfaced directly in the **Temporal Chronicle** (`TemporalChronicle.tsx`):

```
+-----------------------------------------------------------------------------+
│ TEMPORAL CHRONICLE — ACOUSTIC OBSERVATIONS                                  │
+-----------------------------------------------------------------------------+
│                                                                             │
│  [16:42:10] 🚨 CRITICAL ACOUSTIC ANOMALY DETECTED                           │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Sound Class: Smoke detector, smoke alarm (T3 Pattern)                 │  │
│  │ Location: Kitchen (via Wyoming Satellite #2) | Peak: 89dB             │  │
│  │ Confidence: 94.8%                                                     │  │
│  │ Action Taken: Proactive TTS alert dispatched to Living Room & Bedroom.│  │
│  │ [ View Kitchen Camera ]   [ Mute / False Alarm ]   [ Call Emergency ] │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [15:18:04] ⚠️ MECHANICAL ANOMALY ADVISORY                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Sound Class: High-frequency bearing friction / coil whine             │  │
│  │ Location: Server Rack (via Local Host Mic) | Frequency: 4.8kHz        │  │
│  │ Confidence: 81.2%                                                     │  │
│  │ Suggestion: Inspect chassis cooling fan #2 before thermal throttling. │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [14:02:50] 🎵 AMBIENT MUSIC LOGGED                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Track: Daft Punk — Solar Sailer (TRON: Legacy)                        │  │
│  │ Genre: Electronic / Synthwave | Detected in: Office                   │  │
│  │ [ ❤️ Add to Liked Tracks ]   [ View Listening History ]               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
+-----------------------------------------------------------------------------+
```

---

### UX Surface 5: Voice Engine Settings & Ingress Manager (`AudioSettingsTab.tsx`)

```
+-----------------------------------------------------------------------------+
│ AUDIO & VOICE SETTINGS                                                      │
+-----------------------------------------------------------------------------+
│                                                                             │
│  Primary Audio Ingress Engine:                                              │
│  (*) Local Sovereign Engine (Offline)                                       │
│      Uses sherpa-onnx + Silero VAD + Piper TTS (Zero cloud data leakage)    │
│  ( ) Cloud Interactive Omni Stream                                          │
│      Uses Gemini Multimodal Live API (Ultra-low 220ms conversational duplex)│
│                                                                             │
│  Connected Ingress Channels:                                                │
│  [x] Host Built-in Microphone (macOS CoreAudio / cpal)                      │
│  [x] Wyoming TCP Satellites (Listening on port 10400 / 10401)               │
│      • Living Room ESP32-S3 (Area: living_room) — Active                    │
│      • Kitchen Atom Echo (Area: kitchen) — Active                           │
│  [x] Frigate Security Camera RTSP Audio Tracks                              │
│      • Driveway Camera (Area: outdoor) — Monitoring AED only                │
│                                                                             │
│  Acoustic Privacy & Quiet Hours:                                            │
│  [x] Enable Quiet Hours (Mute proactive voice alerts):  [ 22:00 ] to [ 07:00│
│  [x] Ignore background TV/Media speech during music playback                │
│  [x] Delete raw audio buffer immediately after transcription (Retain no WAV)│
+-----------------------------------------------------------------------------+
```

---

## 4. Part III: Implementation Checklist & Phased Delivery Plan

### Phase 1: Core Auditory Engine Foundation (`halbert_core/audio/`)
- [ ] Create `halbert_core/audio/buffer.py` implementing lock-free 10s circular PCM buffer.
- [ ] Implement `halbert_core/audio/speech/vad.py` with Silero VAD v5 ONNX wrapper.
- [ ] Implement `halbert_core/audio/speech/asr_engine.py` integrating `sherpa-onnx` Zipformer INT8.
- [ ] Add unit tests verifying audio chunk ingestion and VAD speech onset/offset detection.

### Phase 2: Multi-Ingress & Desktop Menu Bar Companion
- [ ] Update `wyoming_agent.py` to ingest raw `"audio-chunk"` events alongside `"transcript"`.
- [ ] Implement `LocalMicAdapter` in Rust `src-tauri` using `cpal` with IPC event dispatch to Python backend.
- [ ] Build `VoiceCompanionPill.tsx` Menu Bar HUD with `Cmd+Shift+Space` global hotkey.
- [ ] Implement atomic Barge-In cancellation handling.

### Phase 3: Biometric Speaker Identification & Safety Enforcement
- [ ] Implement `halbert_core/audio/speech/speaker_id.py` using ECAPA-TDNN ONNX (192-dim vector).
- [ ] Create `speaker_profiles` SQLite table in `PersonaMemoryStore`.
- [ ] Build `VoiceEnrollmentModal.tsx` in frontend for 3-step voiceprint enrollment.
- [ ] Wire verified `speaker_role` into `ToolSafetyFramework` to gate privileged sysadmin tools.

### Phase 4: Acoustic Event Detection (AED) & Music Tagging
- [ ] Implement `halbert_core/audio/acoustic/yamnet.py` using YAMNet ONNX (521 AudioSet classes).
- [ ] Build `anomaly_detector.py` for T3/T4 alarm patterns, glass breaks, and mechanical whining.
- [ ] Wire Chromaprint / AcoustID audio fingerprinting for ambient song matching.
- [ ] Surface acoustic anomaly cards in `TemporalChronicle.tsx`.

### Phase 5: Cloud Omni Live Duplex (Gemini Live)
- [ ] Implement WebRTC Bidi stream adapter for Gemini Multimodal Live API in `halbert_core/audio/live_bridge.py`.
- [ ] Add Local vs. Cloud Live toggle in `AudioSettingsTab.tsx`.
- [ ] Test combined visual screen capture + live microphone streaming to Gemini Live.
