# Core Audio Architecture: The Singular Unified Approach for Halbert

> **Strategic Architecture & Roadmap Document**  
> Document: `audio-research/03-CORE-AUDIO-ARCHITECTURE-AND-UNIFIED-APPROACH.md`  
> Author: Eric Bintner & Halbert Research  
> Date: 2026-08-29  

---

## 1. Executive Problem Statement & Step-Back Synthesis

To date, Halbert's audio capabilities have existed as an external Home Assistant proxy ([`wyoming_agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/wyoming_agent.py)). While Wyoming integration is critical for Home Assistant interoperability, **treating voice as a plain-text relay is fundamentally incomplete**:

1. **Halbert is deaf to non-speech physical reality:** It cannot hear broken glass, smoke/CO alarms, water pipe leaks, or equipment failure noises.
2. **Halbert has zero biometric identity:** It cannot verify *who* is speaking, making it impossible to safely gate privileged administrative tools (e.g. ZFS commands, system reboots, deadbolt unlock).
3. **Halbert cannot hear ambient music or media:** It cannot track songs the user likes, nor can it filter out background TV babble from intentional commands.
4. **Desktop Halbert Pro (macOS/Linux) has no standalone voice:** If a user runs Halbert as a standalone sysadmin assistant without Home Assistant, there is zero voice or audio capability.

We need **one singular, unified acoustic architecture** that seamlessly handles every use case—from low-power homelab servers to standalone desktop Pro apps—while maintaining first-class compatibility with Home Assistant's Wyoming ecosystem.

---

## 2. Evaluation of Architectural Options

```
┌───────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
│ Candidate Approach                            │ Evaluation & Verdict                                        │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Option 1: Pure Wyoming Proxy (Current State)  │ ❌ INSUFFICIENT                                              │
│ - Halbert only receives text from HA Whisper. │ - Deaf to all acoustic sounds, music, and anomalies.        │
│ - No raw audio in Halbert core.               │ - No speaker biometrics or authorization.                   │
│                                               │ - Useless for standalone desktop (Halbert Pro).             │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Option 2: Proprietary Monolithic Audio Stack  │ ❌ FRAGMENTED                                                │
│ - Build custom audio daemon, ignore Wyoming.  │ - Alienates Home Assistant community.                       │
│ - Requires custom mic hardware everywhere.    │ - Duplicates satellite infrastructure.                      │
├───────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Option 3: The Singular Unified Engine         │ ✅ RECOMMENDED SINGULAR APPROACH                             │
│ "The Halbert Auditory Cortex"                 │ - Single, lightweight internal audio perception engine.     │
│ - Multi-Ingress Adapters (Local mic, Wyoming, │ - Multi-ingress: accepts Wyoming TCP, local mic, RTSP.      │
│   RTSP camera audio, WebRTC).                 │ - Dual-track: Speech + Ambient Sound/Anomaly/Music.         │
│ - Dual-track pipeline: Speech + Sound/Music.  │ - Zero PyTorch bloat (under 150MB ONNX runtime).            │
│ - 100% local baseline + optional Cloud Live.  │ - Full speaker biometrics + tool safety gating.             │
└───────────────────────────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 3. The Singular Unified Approach: "The Halbert Auditory Cortex"

The singular architectural model is **The Halbert Auditory Cortex** (`halbert_core/audio/`). It decouples **Audio Ingress (where sound comes from)** from **Audio Perception (what sound means)**:

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
                                                    │
                                                    ▼ (Normalized 16kHz 16-bit PCM Stream + Source Context)
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
  └────────────────┬────────────────┘   └─────────────────────────────────┘   └─────────────────────────────────┘
                   │
                   ▼ (Response Text / Audio)
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                                   EGRESS & VOICE SYNTHESIS LAYER
═════════════════════════════════════════════════════════════════════════════════════════════════════════
  ┌───────────────────────────────┐     ┌───────────────────────────────┐     ┌───────────────────────────────┐
  │ Local Audio Output            │     │ Wyoming TCP Egress            │     │ Proactive HA Speak            │
  │ (Rust cpal / Desktop Speaker) │     │ (Piper TTS PCM to Satellite)  │     │ (tts.speak to Room Media Play)│
  └───────────────────────────────┘     └───────────────────────────────┘     └───────────────────────────────┘
```

---

## 4. Architectural Rules & Subtractive Contract Compliance

Halbert operates under a strict **Subtractive Dependency Contract** (`pyyaml>=6.0`, `requests>=2.31.0` as only hard requirements). To prevent adding massive deep learning frameworks (PyTorch, TorchAudio, Transformers, Librosa) which would add 4GB+ of bloat, the audio engine is designed with the following rules:

1. **Zero PyTorch Dependency in Core:**
   - All models execute via **`onnxruntime`** or standalone **`sherpa-onnx`** (C++ static engine with lightweight Python bindings).
   - Total model bundle footprint: **$<135\text{MB}$ total disk space**.
2. **CPU-First Low-Power Execution:**
   - Inference runs efficiently on quad-core Intel N100 / Raspberry Pi 5 without saturating CPU cores.
   - VAD takes $<1\text{ms}$; YAMNet takes $<3\text{ms}$; ECAPA-TDNN takes $<10\text{ms}$.
3. **Lazy-Loaded Audio Pipeline:**
   - If audio input is disabled or unconfigured, zero audio threads or memory buffers are spawned.

---

## 5. Subsystem Module Layout (`halbert_core/audio/`)

```
halbert_core/halbert_core/audio/
├── __init__.py
├── config.py                 # AudioConfig schema (devices, sample rate, thresholds)
├── buffer.py                 # Lock-free Circular Audio Ring Buffer (10s rolling)
├── ingress/
│   ├── __init__.py
│   ├── base.py               # AudioIngressAdapter abstract base class
│   ├── local_mic.py          # Native microphone capture (via cpal / sounddevice)
│   ├── wyoming_ingress.py    # Wyoming TCP server accepting raw audio-chunk events
│   ├── rtsp_ingress.py       # Frigate / IP camera RTSP audio stream extractor
│   └── webrtc_ingress.py     # WebRTC WebSocket ingress for dashboard/browser
├── speech/
│   ├── __init__.py
│   ├── vad.py                # Silero VAD v5 ONNX wrapper (speech onset/offset)
│   ├── wake_word.py          # openWakeWord / microWakeWord detector
│   ├── asr_engine.py         # Sherpa-ONNX Zipformer / faster-whisper INT8
│   ├── speaker_id.py         # ECAPA-TDNN ONNX speaker embedding & verifier
│   └── tts_engine.py         # Piper TTS / Sherpa VITS streaming synthesizer
├── acoustic/
│   ├── __init__.py
│   ├── yamnet.py             # YAMNet ONNX (521 AudioSet event classifier)
│   ├── anomaly_detector.py   # Anomaly evaluator (smoke alarms, glass break, leaks)
│   └── music_fingerprint.py  # Chromaprint / AcoustID track matcher & scene tagger
├── storage/
│   ├── __init__.py
│   └── speaker_store.py      # SQLite schema for enrolled household voiceprints
└── pipeline.py               # Master AudioPipelineCoordinator & Event Dispatcher
```

---

## 6. Data Schemas & Cognitive Integration

### 6.1 Speaker Profile Schema (SQLite)
```sql
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
```

### 6.2 Acoustic Event Data Structure
```python
from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class AcousticEvent:
    event_id: str
    timestamp: float
    source_type: str            # 'local_mic', 'wyoming_satellite', 'frigate_rtsp'
    area_id: Optional[str]      # 'living_room', 'server_rack', 'kitchen'
    sound_class: str            # 'Smoke detector, smoke alarm', 'Glass shatter', 'Music'
    confidence: float           # 0.0 - 1.0
    decibel_level: float        # Approximate dB FS
    is_anomaly: bool            # True if classified as safety/operational anomaly
    anomaly_severity: int       # 0 = Info, 1 = Warning, 2 = Confirm Required, 3 = Critical Emergency
    metadata: Dict[str, Any]    # Song metadata, raw embedding, etc.
```

### 6.3 Voice Turn Data Structure
```python
@dataclass
class VoiceTurn:
    session_id: str
    transcript: str
    speaker_id: Optional[str]   # 'eric', 'sarah', 'unknown_guest'
    speaker_role: str           # 'admin', 'member', 'guest'
    speaker_confidence: float   # Cosine similarity score (e.g. 0.92)
    area_id: Optional[str]      # Spatial room context
    urgency: float              # Pitch & acoustic energy stress metric (0.0 - 1.0)
    audio_duration_ms: int
```

---

## 7. Concrete Phase-by-Phase Execution Roadmap

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        PHASE-BY-PHASE EXECUTION ROADMAP                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 1: Core Audio Engine & Zero-PyTorch Inference Foundation                        │
│ ├─ Create `halbert_core/audio/` module architecture                                    │
│ ├─ Implement lock-free `CircularAudioBuffer` (10s memory)                              │
│ ├─ Bundle standalone `sherpa-onnx` runtime with Silero VAD v5 + Zipformer INT8 ASR     │
│ └─ Write automated unit tests for VAD chunking and streaming transcription             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 2: Upgraded Wyoming Ingress & Local Desktop Capture                              │
│ ├─ Extend `wyoming_agent.py` to ingest raw `"audio-chunk"` PCM streams from satellites │
│ ├─ Implement `LocalMicAdapter` using Rust `cpal` in Tauri desktop shell (`src-tauri`)  │
│ ├─ Wire instantaneous Global Hotkey (`Cmd+Shift+Space`) in macOS Menu Bar companion    │
│ └─ Implement instant Barge-In playback cancellation                                    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 3: Biometric Speaker Identification & Safety Policy Integration                 │
│ ├─ Implement `speaker_id.py` using ECAPA-TDNN ONNX (192-dim embedding)                 │
│ ├─ Create `SpeakerProfileStore` SQLite database in `PersonaMemoryStore`                │
│ ├─ Add CLI / UI voice enrollment tool (`halbert voice enroll --name "Eric"`)           │
│ └─ Enforce `ToolSafetyFramework` role checks on voice turns before tool execution     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 4: Acoustic Event Detection (AED), Safety Anomalies & Music Tagging              │
│ ├─ Integrate YAMNet ONNX for 521-class environmental sound classification               │
│ ├─ Implement Anomaly Gating (detect smoke alarms, glass breaks, water dripping)        │
│ ├─ Wire Chromaprint / AcoustID fingerprinting for ambient song recognition             │
│ └─ Map acoustic anomalies into `SystemEventMapper` for Temporal Chronicle & Proactive  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 5: Native Cloud Omni Live Duplex (Gemini Live & OpenAI Realtime)                │
│ ├─ Build WebRTC / Bidi WebSocket adapter for Gemini Multimodal Live API               │
│ ├─ Add UI voice toggle (Local Sovereign Mode vs. Cloud Live Ultra-Fluid Mode)          │
│ └─ Real-time visual + audio multi-modal pairing (Screen/Webcam + Mic to Live LLM)      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Summary & Strategic Recommendation

By adopting **The Halbert Auditory Cortex** (Option 3):
1. **Home Assistant users** continue using their existing Wyoming ESP32/Pi satellites seamlessly, but gain automatic speaker identification, room-aware spatial scoping, and acoustic anomaly protection.
2. **Desktop Halbert Pro users** gain a native, low-latency, sovereign voice assistant right in their menu bar with zero Home Assistant dependency.
3. **Homelab servers** gain 24/7 acoustic hearing for smoke alarms, breaking glass, and cooling fan failures under a strict **$<150\text{MB}$ RAM and $<5\%$ CPU budget**.
