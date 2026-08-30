# Corrected Technical Architecture

> **Document:** `.handoff/audio/01-CORRECTED-ARCHITECTURE.md`
> **Status:** Verified against external sources + codebase

---

## 1. Corrected Auditory Cortex Pipeline

```
INGRESS ADAPTER LAYER (Multi-Source)
  Local Microphone        Wyoming TCP Satellite    RTSP Camera Audio       WebRTC / Dashboard
  (Rust cpal -> loopback  (ESP32 / Pi on 10400)    (Frigate Security)      (FastAPI WebSocket)
   TCP socket -> Python)  [BINARY framing]         [Opus -> PCM decode]    [Browser mic]
        |                        |                        |                        |
        +------------------------+-----------------------+------------------------+
                                 | (Normalized 16kHz 16-bit mono PCM Stream)
                                 v
                    HALBERT AUDITORY CORTEX (halbert_core/audio/)
                                 |
                    +------------+------------+
                    | Circular Ring Buffer    |
                    | (10.0s rolling memory)  |
                    | Desktop: Rust ring buf  |
                    | Headless: asyncio.Queue |
                    +-----+--------------+----+
                          |              |
         +----------------+              +----------------+
         v (512-sample/32ms frames)       v (1.0s spectrogram windows)
 +-----------------------------+    +-----------------------------+
 | TRACK A: Conversational     |    | TRACK B: Ambient Sound,     |
 |   Speech & Biometrics       |    |   Anomalies & Music         |
 +-----------------------------+    +-----------------------------+
 | 1. Silero VAD v5 ONNX       |    | 1. Energy Floor Gate        |
 |    (2.2MB, <1ms/chunk)      |    |    (Bypass when silent)     |
 | 2. Wake Word Spotting       |    | 2. CED-tiny ONNX            |
 |    (openWakeWord "Hey       |    |    (audio event classifier, |
 |     Halbert" -- TRAINED)    |    |     NOT YAMNet)             |
 | 3. Streaming ASR            |    |    - Glass, smoke alarm,    |
 |    (Sherpa Zipformer INT8)  |    |      water leak, etc.       |
 | 4. CAM++ ONNX Speaker ID    |    | 3. Chromaprint/AcoustID     |
 |    (256-dim embedding,      |    |    (Music ID -- REQUIRES    |
 |     27.9MB, NOT ECAPA-TDNN) |    |     NETWORK for lookup)     |
 | 5. Barge-In Handler         |    | 4. Acoustic Scene Descriptor|
 |    (cancel Piper + HA sat)  |    |    (TV/Media filter)        |
 +-------------+---------------+    +-------------+---------------+
               |                                  |
               v                                  v
 +-----------------------------+    +-----------------------------+
 | VoiceTurnObservation        |    | AcousticEventObservation    |
 | - text, speaker_id, role,   |    | - class, confidence, dB,    |
 |   area_id, urgency          |    |   anomaly_severity, music   |
 +-------------+---------------+    +-------------+---------------+
               |                                  |
               +-----------------+----------------+
                                 |
                                 v
              COGNITION & SAFETY EXECUTION LAYER
  +-------------------+  +-------------------+  +-------------------+
  | Halbert State     |  | RoleGate          |  | SpeakerProfileStore|
  | Machine           |  | (wraps            |  | (SQLite,           |
  | - Agent turn      |  |  ToolSafety       |  |  256-dim CAM++     |
  | - Proactive alert |  |  Framework, can   |  |  centroids,        |
  |                   |  |  only tighten)    |  |  data_subdir)      |
  +-------------------+  +-------------------+  +-------------------+
                                 |
              +------------------+------------------+
              v                                     v
 +-------------------+               +-------------------+
 | SystemEventMapper |               | DetectorRunner    |
 | (cognition:       |               | -> FindingStore   |
 |  worries/fear)    |               | -> ProactiveGate  |
 |                   |               | -> EventBus -> SSE|
 +-------------------+               +-------------------+
```

Key corrections from original:
- Local mic: Rust cpal -> **loopback TCP socket** -> Python (NOT Tauri IPC)
- Wyoming: **binary frame reader** (header + data_length + payload_length)
- Speaker ID: **CAM++ 256-dim** (NOT ECAPA-TDNN 192-dim)
- Acoustic events: **CED-tiny** (NOT YAMNet)
- Safety: **RoleGate wrapper** (NOT modifying ToolSafetyFramework)
- Anomalies route to **both** SystemEventMapper (cognition) AND DetectorRunner (findings/gate)
- Music ID: **requires network** (AcoustID API)

---

## 2. Corrected Subtractive Contract & Footprint

### Zero-PyTorch Guarantee (CONFIRMED)
sherpa-onnx uses ONNX Runtime only. Zero PyTorch/CUDA in the inference runtime. The pip wheel declares only `sherpa-onnx-core` as a hard dependency. GPU is available via ONNX Runtime CUDA Execution Provider (not PyTorch).

### Corrected Model Footprint Table

| Component | Model | Disk Size | RAM (runtime) | Latency (CPU) | Source |
|-----------|-------|-----------|---------------|---------------|--------|
| VAD | Silero VAD v5 ONNX | 2.2 MB | <5 MB | <1ms per 32ms chunk (189us measured) | snakers4/silero-vad |
| ASR | Zipformer INT8 streaming (small EN) | ~40 MB (encoder), 122 MB tarball | ~120-150 MB | <50ms streaming | k2-fsa/sherpa-onnx |
| Speaker ID | CAM++ (wespeaker_en_voxceleb) | 27.9 MB | ~30 MB | <10ms per utterance | k2-fsa/sherpa-onnx |
| Audio Tagging | CED-tiny or Zipformer-small-int8 | 26 MB (int8) | ~30 MB | ~12-15ms per 1s window | k2-fsa/sherpa-onnx |
| TTS | Piper VITS (1 voice, medium) | 61-75 MB | ~80 MB | streaming | OHF-Voice/piper1-gpl |
| Wake Word | openWakeWord (custom "Hey Halbert") | ~3 MB | ~5 MB | <5ms | dscripka/openWakeWord |
| AEC | webrtc-audio-processing (Rust crate) | compiled | ~10 MB | <1ms per frame | tonarino/webrtc-audio-processing |

### Corrected Total Footprint

| Tier | Disk | RAM | CPU | Components |
|------|------|-----|-----|------------|
| Minimal (VAD + ASR only) | ~45 MB | ~155 MB | <3% | VAD + small ASR |
| Standard (VAD + ASR + Speaker + Tagging) | ~96 MB | ~215 MB | <5% | + CAM++ + CED-tiny |
| Full (all + TTS + WakeWord + AEC) | ~170 MB | ~310 MB | <6% | + Piper + openWakeWord + AEC |
| Extended (multiple TTS voices, larger ASR) | ~200-350 MB | ~450 MB | <10% | + additional voices/models |

The original "<135MB / <300MB" claim is achievable only for the Standard tier without TTS. The Full tier with one TTS voice is ~170MB. Document this honestly.

---

## 3. Corrected SQLite Schemas

### Speaker Profiles (CORRECTED: 256-dim, not 192-dim)

```sql
CREATE TABLE IF NOT EXISTS speaker_profiles (
    speaker_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member', 'guest', 'restricted')),
    embedding_centroid BLOB NOT NULL, -- 256-dim float32 vector (1024 bytes) for CAM++
    sample_count INTEGER DEFAULT 1,
    threshold REAL DEFAULT 0.75,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Note: sherpa-onnx `SpeakerEmbeddingManager` already implements cosine similarity,
multi-sample averaging (`.add(name, [emb1, emb2, ...])`), and verification
(`.verify(name, embedding, threshold)`). The store persists centroids; the
manager does the math. Do not reinvent cosine similarity in Python.

### Acoustic Event Log (companion to findings, not duplicate)

```sql
-- Thin event log for acoustic-specific metadata that doesn't fit Finding schema.
-- Finding state (open/snoozed/dismissed) lives in findings/store.py.
-- This table stores the raw acoustic observation details.
CREATE TABLE IF NOT EXISTS acoustic_event_log (
    event_id TEXT PRIMARY KEY,
    finding_id TEXT,                 -- FK to findings.id if promoted to finding
    timestamp REAL NOT NULL,
    source_type TEXT NOT NULL,       -- 'local_mic', 'wyoming_satellite', 'frigate_rtsp'
    area_id TEXT,
    sound_class TEXT NOT NULL,       -- CED/Zipformer class label
    confidence REAL NOT NULL,
    decibel_level REAL,
    is_anomaly BOOLEAN DEFAULT 0,
    anomaly_severity INTEGER DEFAULT 0, -- 0=Info, 1=Warning, 2=Confirm, 3=Critical
    metadata_json TEXT               -- song metadata, frequency profile, etc.
);
CREATE INDEX IF NOT EXISTS idx_acoustic_timestamp ON acoustic_event_log(timestamp);
```

Source of truth for finding state: `findings/store.py`. This table is for
acoustic-specific metadata only. When an anomaly is promoted to a finding,
the finding_id links them.

---

## 4. Corrected Module Layout

```
halbert_core/halbert_core/audio/
  __init__.py               # Lazy, imports cleanly with zero audio deps
  config.py                 # AudioConfig schema (yaml, all OFF by default)
                             # Mirrors vision/config.py pattern
  buffer.py                 # Platform-dispatched ring buffer
                             # Desktop: Rust ring via socket
                             # Headless: asyncio.Queue + array.array
  is_available.py           # is_audio_available() gate (checks sherpa_onnx import)
  ingress/
    __init__.py
    base.py                 # AudioIngressAdapter ABC
    local_mic.py            # Reads from loopback TCP socket (Rust cpal sender)
    wyoming_ingress.py      # BINARY frame reader (header + data_length + payload_length)
                             # Does NOT use readline() for audio frames
    rtsp_ingress.py         # Frigate RTSP audio (Opus -> PCM via symphonia + libopus)
    webrtc_ingress.py       # Dashboard/browser WebSocket audio
  speech/
    __init__.py
    vad.py                  # Silero VAD v5 ONNX (512-sample/32ms windows at 16kHz)
    wake_word.py            # openWakeWord (requires trained "Hey Halbert" model)
    asr_engine.py           # Sherpa OnlineRecognizer (streaming Zipformer INT8)
    speaker_id.py           # Sherpa SpeakerEmbeddingExtractor + Manager (CAM++, 256-dim)
    tts_engine.py           # Piper TTS via sherpa-onnx (OHF-Voice/piper1-gpl voices)
    barge_in.py             # Cancellation token: local Piper + best-effort HA media_player.stop
  acoustic/
    __init__.py
    audio_tagger.py         # CED-tiny or Zipformer-small ONNX (NOT yamnet.py)
    anomaly_detector.py     # Maps tagger output to anomaly severity (T3/T4 patterns, etc.)
    music_fingerprint.py    # Chromaprint fingerprint + AcoustID lookup (REQUIRES NETWORK)
    scene_descriptor.py     # TV/media filter to suppress false wake-word triggers
  storage/
    __init__.py
    speaker_store.py        # SQLite speaker_profiles table under data_subdir
                             # Uses sherpa SpeakerEmbeddingManager for math
  pipeline.py               # AudioPipelineCoordinator & Event Dispatcher
```

Rust side (src-tauri):
```
src-tauri/src/
  audio_capture.rs          # cpal input stream -> loopback TCP socket
  audio_buffer.rs           # Lock-free ring buffer (desktop only)
  audio_aec.rs              # webrtc-audio-processing AEC before socket dispatch
```

---

## 5. Corrected Verification Vectors

### V1: Wyoming Socket Lifecycle (CORRECTED)
The ingress must use the canonical Wyoming frame reader:
1. `readline()` for JSON header
2. `readexactly(data_length)` for additional JSON data
3. `readexactly(payload_length)` for binary PCM payload
4. Loop

Sudden satellite disconnection: the `readexactly()` will raise
`asyncio.IncompleteReadError` — catch it, close the writer, log, and
allow reconnection. Do NOT mix readline() and readexactly() carelessly.

### V2: Ring Buffer (CORRECTED — split by platform)
Desktop: Rust `cpal` captures -> AEC -> writes to lock-free ring buffer ->
loopback socket -> Python reads. The ring buffer lives in Rust, not Python.

Headless Linux: Single ingress thread writes to `asyncio.Queue` (maxsize
calculated for 10s of audio). Multiple async consumers read slices. Use
`array.array('h', ...)` for the rolling window, not `collections.deque`.

### V3: Barge-In Latency (CORRECTED — two targets)
Target 1 (local Piper): cancellation token reaches `tts_engine.py` and
aborts the VITS stream. Measurable with synthetic PCM test in Phase 1.

Target 2 (HA satellite): best-effort `media_player.stop` per area via
`HAClient.call_service()`. Cannot cancel audio HA already started playing.
Document as lossy.

Budget: <150ms for local, best-effort for satellite.

### V4: AEC (NEW)
Without AEC, Halbert's own Piper TTS output feeds back into the microphone,
causing VAD false-triggers and feedback loops. AEC must be applied to the
`cpal` capture stream BEFORE dispatching to the Python backend. This is a
Phase 2 requirement, not optional.

### V5: Footprint (CORRECTED)
Measure actual `onnxruntime` resident memory with the chosen models loaded.
The "~120MB RAM" ASR figure is model-dependent and often exceeded. Budget
conservatively.
