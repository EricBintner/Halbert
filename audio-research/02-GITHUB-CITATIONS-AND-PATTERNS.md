# GitHub Citations & Production Audio Patterns for Halbert

> **Reference Projects, Open-Source Tools & Architectural Blueprints**  
> Document: `audio-research/02-GITHUB-CITATIONS-AND-PATTERNS.md`  
> Author: Eric Bintner & Halbert Research  
> Date: 2026-08-29  

---

## 1. Edge Audio Capture, DSP & Rust Toolchain

### 1.1 `cpal` (Cross-Platform Audio Library)
- **URL:** https://github.com/RustAudio/cpal
- **Language / Stack:** Rust (low-level bindings to CoreAudio, ALSA, WASAPI, AAudio)
- **What it does:** The standard Rust library for cross-platform audio input/output stream management.
- **Pattern to borrow for Halbert:**
  - Direct microphone capture inside the **Tauri desktop shell** (`src-tauri`).
  - Allows Halbert's Menu Bar companion on macOS to capture microphone input with $<5\text{ms}$ driver latency, bypassing Python's `pyaudio`/PortAudio binding overhead.
  - Passes raw 16kHz PCM chunks over Tauri IPC / Unix domain socket directly to Halbert's backend.

### 1.2 `webrtc-audio-processing`
- **URL:** https://github.com/alona-d/webrtc-audio-processing-rust (Rust) / https://github.com/xiongyihui/webrtc-audio-processing (C++)
- **What it does:** Production-grade DSP extraction from Google WebRTC:
  - **Acoustic Echo Cancellation (AEC):** Cancels Halbert's own TTS output from the microphone feed.
  - **Automatic Gain Control (AGC):** Normalizes volume for quiet vs loud speakers across a room.
  - **Noise Suppression (NS):** Filters steady fan, HVAC, and computer hum.
- **Relevance:** High. Prevents Halbert from hearing its own voice and removes ambient server noise.

### 1.3 `symphonia`
- **URL:** https://github.com/pdeljanov/Symphonia
- **Language:** Pure Rust
- **What it does:** Fast, zero-allocation, memory-safe audio decoding and demuxing (MP3, AAC, FLAC, WAV, OGG, Opus).
- **Pattern to borrow:** Decodes incoming audio from browser WebRTC, RTSP camera streams (Frigate), and Wyoming TCP connections without linking external C-libraries (like ffmpeg).

---

## 2. Low-Resource Inference Engines & Embeddings

### 2.1 `sherpa-onnx` (Next-Gen Kaldi)
- **URL:** https://github.com/k2-fsa/sherpa-onnx
- **Language / Stack:** C++, Rust, Python, Go, Java | ONNX Runtime
- **What it does:** An all-in-one, ultra-lightweight offline speech engine supporting:
  - Streaming & Non-streaming ASR (Zipformer, Whisper, Paraformer, Moonshine)
  - Text-to-Speech (VITS, Piper)
  - Voice Activity Detection (Silero VAD v5)
  - Speaker Identification (CAM++, ECAPA-TDNN, Resemblyzer)
  - Keyword Spotting & Wake Word
  - Audio Tagging (YAMNet)
- **Why this is the holy grail for Halbert:**
  - **Zero PyTorch / CUDA footprint:** Compiles into a single static library or clean pip package with zero heavy dependencies.
  - Adheres strictly to the **Haloysius Subtractive Contract** (`pyyaml>=6.0`, `requests>=2.31.0` as sole requirements).
  - Handles VAD + STT + Speaker ID + Sound Classification inside a single unified C++/Python runtime taking $<120\text{MB}$ RAM.

### 2.2 `faster-whisper` & `ctranslate2`
- **URL:** https://github.com/SYSTRAN/faster-whisper
- **Stack:** Python, CTranslate2, C++
- **What it does:** Reimplementation of Whisper using CTranslate2's custom GEMM execution engine.
- **Pattern to borrow:** Dynamic model switching:
  - `whisper-tiny.en` (39M parameters, ~75MB RAM) for background command parsing.
  - `whisper-small` (244M parameters, ~500MB RAM) on demand for complex, accented, or multilingual technical instructions.

### 2.3 `openWakeWord` & `microWakeWord`
- **URL:** https://github.com/dscripka/openWakeWord | https://github.com/kahrendt/microWakeWord
- **Stack:** ONNX, TFLite Micro, ESP-IDF
- **What it does:**
  - `openWakeWord`: Runs on Linux/macOS host with trained models for *"Hey Halbert"*, *"Computer"*, *"Jarvis"*.
  - `microWakeWord`: Runs on $\$4$ ESP32-S3 microcontrollers with 16KB RAM budget.
- **Relevance:** Enables custom *"Hey Halbert"* activation on both desktop and distributed room satellites.

---

## 3. Real-Time Full-Duplex Voice Agents & Protocols

### 3.1 `wyoming` Protocol & Satellite Ecosystem
- **URL:** https://github.com/rhasspy/wyoming
- **Protocol:** JSONL over TCP / Unix Sockets
- **Key Repositories:**
  - `wyoming-satellite`: Remote microphone client running on Pi / ESP32.
  - `wyoming-whisper`: Faster-whisper server over Wyoming.
  - `wyoming-piper`: Piper TTS server over Wyoming.
  - `wyoming-openwakeword`: Wake word server over Wyoming.
- **Pattern to borrow:**
  - Halbert's [`wyoming_agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/wyoming_agent.py) acts as a Wyoming TCP conversation endpoint.
  - Upgrading `wyoming_agent.py` to handle both `transcript` events (text from HA) AND raw `audio-chunk` streams (direct satellite audio).

### 3.2 `livekit-agents`
- **URL:** https://github.com/livekit/agents
- **Stack:** Python / Rust, WebRTC, Asyncio
- **What it does:** Real-time multimodal voice agent framework built for low-latency WebRTC streams.
- **Pattern to borrow:**
  - **The Event-Driven Duplex Pipeline:** Strict state synchronization between VAD onset $\to$ user speaking state $\to$ agent thinking state $\to$ agent speaking state.
  - **Barge-in handling:** When user speech is detected during agent speaking state, instantly publish a `cancel_stream` token that aborts downstream TTS generation and clears client audio buffers.

### 3.3 `wyoming-letta`
- **URL:** https://github.com/letta-ai/wyoming-letta
- **Stack:** Python, Wyoming, Letta Core
- **What it does:** Bridges Wyoming voice pipelines to Letta's stateful memory agent.
- **Relevance:** Validates Halbert's architecture: Halbert connects its Haloysius cognitive memory and state machine to voice pipelines in exactly the same clean protocol-adapter manner.

---

## 4. Key Production Patterns to Implement in Halbert

```
                               ┌─────────────────────────────────────────┐
                               │   Unified Audio Ingress Router          │
                               │   - Local Mic (Rust cpal / Tauri IPC)   │
                               │   - Wyoming TCP (ESP32 Satellites)      │
                               │   - Frigate RTSP Audio Feeds            │
                               │   - Dashboard WebRTC Stream             │
                               └────────────────────┬────────────────────┘
                                                    │ (16kHz PCM Frames)
                                                    ▼
                               ┌─────────────────────────────────────────┐
                               │   Circular Audio Ring Buffer (10 sec)   │
                               │   (collections.deque / Lock-Free Ring)  │
                               └──────────────┬──────────────────┬───────┘
                                              │                  │
                      ┌───────────────────────┘                  └───────────────────────┐
                      ▼ (Continuous 1.0s Chunks)                                         ▼ (Continuous 30ms Chunks)
       ┌───────────────────────────────┐                                  ┌───────────────────────────────┐
       │   Ambient Perception Loop     │                                  │   Conversational Voice Loop   │
       │   - YAMNet (Sound Events)     │                                  │   - Silero VAD                │
       │   - Chromaprint (Music Finger)│                                  │   - Wake Word Spotting        │
       │   - Acoustic Anomaly Gating   │                                  │   - Sherpa / Whisper ASR      │
       └──────────────┬────────────────┘                                  │   - ECAPA-TDNN Speaker ID     │
                      │                                                   └──────────────┬────────────────┘
                      ▼                                                                  ▼
       ┌───────────────────────────────┐                                  ┌───────────────────────────────┐
       │ SystemEventMapper             │                                  │ Agent State Machine &         │
       │ (Temporal Chronicle & Alerts) │                                  │ PersonaMemoryStore (Auth)     │
       └───────────────────────────────┘                                  └───────────────────────────────┘
```

### Pattern 1: Circular Audio Ring Buffer
* Never allocate dynamic memory inside real-time audio threads.
* Maintain a lock-free or `collections.deque(maxlen=160000)` rolling 10-second ring buffer of 16-bit 16kHz PCM samples.
* When a wake word or acoustic anomaly triggers, the model has instant access to the preceding 1–2 seconds of pre-trigger audio context (preventing clipped speech onset).

### Pattern 2: Single-Runtime Inference via `sherpa-onnx`
* Rather than installing PyTorch, TorchAudio, Transformers, and PyAnnote (which would bloat Halbert's package size by $>4\text{GB}$ and violate our subtractive contract), bundle `sherpa-onnx` or run lightweight ONNX Runtime sessions.
* Total audio subsystem weight: under **$150\text{MB}$** including models.

### Pattern 3: Dual-Mode Acoustic Gating
* **Speech Path:** Triggered on demand when VAD + Wake Word activates.
* **Ambient Sound Path:** Evaluates a 1-second rolling spectrogram every 2 seconds. If acoustic energy is below ambient baseline ($<35\text{dB}$), bypass YAMNet to preserve 100% idle CPU sleep states.
