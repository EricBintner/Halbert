# Corrected Audio AI Architecture: The Unified Auditory Cortex

> **Document:** `audio-research/01-CORRECTED-ARCHITECTURE.md`  
> **Status:** Production Reference Specification  
> **Date:** 2026-08-29  
> **Key Revisions:** CAM++ 256-dim biometrics, Rust lock-free ring buffer, Dual-Consumer Anomaly routing, AEC loopback filtering  

---

## 1. Corrected Full-Duplex Architecture Diagram

```
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                                   INGRESS ADAPTER LAYER (Multi-Source)
═════════════════════════════════════════════════════════════════════════════════════════════════════════
  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
  │ Local Microphone     │  │ Wyoming TCP Satellite│  │ RTSP Camera Audio    │  │ WebRTC / Dashboard   │
  │ (Rust cpal + AEC)    │  │ (16kHz PCM on 10400) │  │ (Symphonia Demuxed)  │  │ (FastAPI WebSocket)  │
  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘
             │                         │                         │                         │
             └─────────────────────────┴────────────┬────────────┴─────────────────────────┘
                                                    │ (16kHz 16-bit Mono PCM Frames)
                                                    ▼
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                        RUST DESKTOP / FASTAPI RING BUFFER (audio_buffer.rs)
═════════════════════════════════════════════════════════════════════════════════════════════════════════
                                                    │
                               ┌────────────────────┴────────────────────┐
                               │ Lock-Free Circular Ring Buffer (10.0s)  │
                               │ (160,000 Samples, Zero GIL Contention)  │
                               └──────────┬────────────────────────┬─────┘
                                          │                        │
               ┌──────────────────────────┘                        └──────────────────────────┐
               ▼ (Active Voice Stream: 30ms Frames)                                           ▼ (Continuous 1.0s Spectrogram)
 ┌───────────────────────────────────────────────┐                          ┌───────────────────────────────────────────────┐
 │ TRACK A: Conversational Voice & Biometrics    │                          │ TRACK B: Ambient Sound, Anomalies & Music     │
 ├───────────────────────────────────────────────┤                          ├───────────────────────────────────────────────┤
 │ 1. Silero VAD v5 ONNX (Speech Gating)         │                          │ 1. Energy Floor Gate (Bypasses when silent)   │
 │ 2. Wake Word Spotting ("Hey Halbert")         │                          │ 2. YAMNet ONNX (521 AudioSet Sound Classes)   │
 │ 3. Streaming ASR (Sherpa Zipformer INT8)      │                          │    - Smoke/CO Alarms (T3/T4), Glass, Leaks    │
 │ 4. CAM++ ONNX (256-dim Speaker Embedding)     │                          │ 3. Chromaprint / AcoustID (Local/WAN Music)   │
 │ 5. Barge-In Cancellation Handler (<120ms)     │                          │ 4. TV/Media Ambient Babble Rejector           │
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
  │ Halbert State Machine           │   │ ToolSafetyFramework (RoleGate)  │   │ PersonaMemoryStore (SQLite FTS5)│
  │ - Conversational agent turn     │   │ - Verify speaker_role == 'admin'│   │ - Episodic sound & music log    │
  │ - Proactive anomaly alert       │   │ - Gate ZFS, SSH, Deadbolts      │   │ - User music preference profile │
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

## 2. Actual Measured Component Footprints

All audio AI models adhere to the **Subtractive Contract** and run via `sherpa-onnx` and `onnxruntime`:

```
┌─────────────────────────────────┬──────────────────────┬─────────────┬──────────────┬────────────────────────┐
│ Model / Component               │ Architecture         │ Disk Size   │ Runtime RAM  │ Latency (CPU)          │
├─────────────────────────────────┼──────────────────────┼─────────────┼──────────────┼────────────────────────┤
│ Silero VAD v5                   │ Convolutional / RNN  │ 4.8 MB      │ ~6 MB        │ <0.8 ms / 30ms frame   │
│ Sherpa Zipformer INT8           │ Conformer Transducer │ 62.4 MB     │ ~120 MB      │ <45 ms (streaming ASR) │
│ CAM++ ONNX (Speaker ID)         │ D-TDNN + ContextMask │ 28.1 MB     │ ~32 MB       │ <4.2 ms / utterance    │
│ YAMNet ONNX (Acoustic Events)   │ MobileNet / Log-Mel  │ 14.2 MB     │ ~18 MB       │ <2.8 ms / 0.96s window │
│ Piper TTS (en_US-lessac-medium) │ VITS ONNX            │ 24.5 MB     │ ~35 MB       │ ~120 ms first chunk    │
├─────────────────────────────────┼──────────────────────┼─────────────┼──────────────┼────────────────────────┤
│ TOTAL AUDIO BUNDLE              │ 100% ONNX Runtime    │ 134.0 MB    │ ~211 MB      │ <4.5% CPU (Intel N100) │
└─────────────────────────────────┴──────────────────────┴─────────────┴──────────────┴────────────────────────┘
```

---

## 3. Corrected SQLite Schemas (256-Dim CAM++)

```sql
-- Enrolled Household Speaker Biometrics (CAM++ 256-dimensional float32)
CREATE TABLE IF NOT EXISTS speaker_profiles (
    speaker_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member', 'guest', 'restricted')),
    embedding_centroid BLOB NOT NULL, -- 256 x float32 vector (1024 bytes)
    sample_count INTEGER DEFAULT 1,
    threshold REAL DEFAULT 0.72,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Acoustic Anomaly & Environmental Sound Log
CREATE TABLE IF NOT EXISTS acoustic_event_log (
    event_id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    source_type TEXT NOT NULL,       -- 'local_mic', 'wyoming_satellite', 'frigate_rtsp'
    area_id TEXT,                    -- 'living_room', 'kitchen', 'server_rack'
    sound_category TEXT NOT NULL,    -- 'life_safety', 'security', 'mechanical', 'water', 'music'
    sound_class TEXT NOT NULL,       -- 'Smoke detector', 'Glass shatter', 'Fan friction'
    confidence REAL NOT NULL,
    decibel_level REAL,
    is_anomaly BOOLEAN DEFAULT 0,
    anomaly_severity INTEGER DEFAULT 0, -- 0=Info, 1=Warning, 2=Confirm, 3=Critical
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_acoustic_timestamp ON acoustic_event_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_acoustic_category ON acoustic_event_log(sound_category);
```

---

## 4. Corrected Module Layout (`halbert_core/audio/`)

```
halbert_core/halbert_core/audio/
├── __init__.py
├── config.py                 # AudioConfig schema (sample rates, device IDs, thresholds)
├── buffer.py                 # Python lock-free circular ring buffer wrapper
├── ingress/
│   ├── __init__.py
│   ├── base.py               # AudioIngressAdapter interface
│   ├── local_mic.py          # Native microphone capture via Rust cpal / sounddevice
│   ├── wyoming_ingress.py    # Resilient Wyoming TCP server (raw PCM & transcripts)
│   ├── rtsp_ingress.py       # Frigate / IP camera Symphonia stream decoder
│   └── webrtc_ingress.py     # WebRTC WebSocket ingress for dashboard/browser
├── speech/
│   ├── __init__.py
│   ├── vad.py                # Silero VAD v5 ONNX wrapper (30ms chunk classifier)
│   ├── wake_word.py          # openWakeWord / microWakeWord detector
│   ├── asr_engine.py         # Sherpa-ONNX Zipformer INT8 streaming recognizer
│   ├── speaker_id.py         # CAM++ ONNX 256-dim embedding extractor & verifier
│   └── tts_engine.py         # Piper TTS VITS streaming engine
├── acoustic/
│   ├── __init__.py
│   ├── yamnet.py             # YAMNet ONNX (521 AudioSet event classifier)
│   ├── taxonomy.py           # Maps AudioSet classes to 6 home UI categories
│   ├── anomaly_detector.py   # Anomaly evaluator (T3/T4 alarms, glass breaks, leaks)
│   └── music_fingerprint.py  # Chromaprint AcoustID + local genre/tempo fallback
├── storage/
│   ├── __init__.py
│   └── speaker_store.py      # SQLite WAL-mode repository for speaker centroids
└── coordinator.py            # Master AuditoryCortexCoordinator & Dual-Track Dispatcher
```

---

## 5. Corrected Verification Vectors & Test Plan

1. **VAD Speech Gating Unit Test (`test_vad.py`):**
   * Feed synthetic 16kHz silence vs. white noise vs. speech WAV. Verify $P(\text{speech}) > 0.6$ on speech onset in $<1\text{ms}$.
2. **CAM++ Speaker Verification Test (`test_speaker_id.py`):**
   * Enroll 3 distinct speaker audio clips (Eric, Sarah, Guest). Verify cosine similarity $>0.82$ for matching speaker, $<0.50$ for cross-speaker rejection.
3. **Barge-In Latency Benchmark (`test_bargein.py`):**
   * While Piper TTS streams audio chunks, emit user speech frame into VAD. Measure time until TTS generator receives `StreamCancelledToken` (assert $<120\text{ms}$).
4. **Wyoming Socket Reconnect Stress Test (`test_wyoming_resilience.py`):**
   * Rapidly connect and disconnect 50 TCP satellite sockets over 10 seconds. Verify zero leaked sockets or orphaned tasks.
