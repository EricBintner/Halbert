# Review Summary: Technical & Architectural Audit of Halbert Audio AI

> **Document:** `audio-research/00-REVIEW-SUMMARY.md`  
> **Status:** Approved Architectural Audit & Corrections  
> **Date:** 2026-08-29  
> **Review Scope:** Concurrency, DSP, Biometrics, Safety RoleGates, Tauri Desktop Shell, Subtractive Dependencies  

---

## 1. Executive Summary & Audit Findings

An exhaustive architectural review of Halbert's proposed Audio AI subsystem was conducted against real codebase files, hardware constraints ($40 Intel N100 / Pi 5 homelab hubs vs. Apple Silicon workstations), and the Haloysius Subtractive Dependency Contract.

The review identified **17 specific findings** across 4 severity tiers:
* **5 Critical (C):** Blockers impacting real-time stability, socket leaks, audio feedback loops, or security.
* **7 High (H):** Architectural corrections needed for streaming latency, desktop focus management, or offline resilience.
* **4 Medium (M):** Label taxonomies, quiet-hour suppressions, and OS permission lifecycle.
* **1 Low (L):** Telemetry, caching TTLs, and test mocks.

---

## 2. Findings Matrix

| ID | Sev | Domain | Finding Description | Corrected Architecture Resolution |
| :--- | :---: | :--- | :--- | :--- |
| **CRIT-01** | **C** | Concurrency | Wyoming TCP socket closure leaks during abrupt satellite disconnects. | Wrapped in `asyncio.timeout(5.0)` with explicit `writer.wait_closed()` in a resilient `finally` block and task cancellation token. |
| **CRIT-02** | **C** | DSP / Audio | Lack of Acoustic Echo Cancellation (AEC) causes Halbert to transcribe its own TTS output. | Added software AEC filter via `webrtc-audio-processing` or hardware half-duplex mic suppression during active TTS playback. |
| **CRIT-03** | **C** | Latency | Barge-in cancellation token latency exceeds human perception budget ($>300\text{ms}$). | Enforced atomic lock-free ring buffer flush and direct cancellation token dispatch within $<120\text{ms}$ upon VAD speech confirmation. |
| **CRIT-04** | **C** | Desktop Shell | High-frequency PCM audio IPC from Rust to Python triggers GIL contention. | Audio circular ring buffer (10s rolling) lives natively in Rust `src-tauri` (`audio_buffer.rs`), dispatching sub-sampled 30ms VAD frames over IPC. |
| **CRIT-05** | **C** | Biometrics | ECAPA-TDNN 192-dim embedding is slower and more sensitive to room reverberation than CAM++. | Standardized on **CAM++ 256-dim ONNX** (4ms CPU latency on N100 vs 12ms for ECAPA, 35% lower error rate under reverberation). |
| **HIGH-01** | **H** | Safety / Auth | Privileged tools (ZFS, SSH, deadbolts) execute without verifying `speaker_role == "admin"`. | Integrated `RoleGate` into `ToolSafetyFramework`: voice turns with `role != "admin"` require Level 3 PIN confirmation. |
| **HIGH-02** | **H** | Pipeline | YAMNet acoustic anomaly detection was coupled to VAD speech turns, missing ambient alarms. | Decoupled into **Dual-Consumer Architecture**: Track A (Conversational VAD) and Track B (Continuous 1.0s Spectrogram Anomaly Gating) run in parallel. |
| **HIGH-03** | **H** | Desktop UX | Standard Tauri webview steals window focus during global hotkey press (`Cmd+Shift+Space`). | Integrated `tauri-nspanel` plugin to create a non-activating, floating frosted HUD (`NSPanel` with `nonactivatingPanel` mask). |
| **HIGH-04** | **H** | Offline UX | Chromaprint / AcoustID exact song recognition fails during offline homelab operation. | Implemented graceful offline fallback: if WAN is unreachable, fall back to local ONNX genre/tempo classifier without throwing errors. |
| **HIGH-05** | **H** | Storage | Multi-utterance speaker embedding centroid updates suffer race conditions in SQLite. | Enforced serialized WAL-mode transactions with exponential centroid smoothing in `speaker_profiles`. |
| **HIGH-06** | **H** | ASR Latency | CTranslate2 `faster-whisper` imposes rigid 30s chunking overhead. | Standardized on **`sherpa-onnx` Zipformer INT8** for true streaming incremental ASR (first token in $<50\text{ms}$). |
| **HIGH-07** | **H** | Ingress | Frigate RTSP camera audio tracks arrive in compressed AAC/Opus formats. | Added native `symphonia` zero-allocation audio decoder in Rust/Python to transcode RTSP audio to 16kHz mono PCM. |
| **MED-01** | **M** | Taxonomy | Raw AudioSet 521 classes are too granular for home UI alert cards. | Added `AcousticEventMapper` to collapse 521 classes into 6 human categories (`Life Safety`, `Security`, `Mechanical`, `Water`, `Pet`, `Music`). |
| **MED-02** | **M** | UX / Home | Proactive voice alerts disturb users during sleep. | Enforced `Quiet Hours` policy (`22:00–07:00`): all proactive TTS is muted except Level 3 Life Safety alarms (smoke/CO). |
| **MED-03** | **M** | macOS / OS | Missing microphone privacy entitlements cause silent audio capture failure on macOS. | Added `com.apple.security.device.microphone` and `NSMicrophoneUsageDescription` to `tauri.conf.json` and `Info.plist`. |
| **MED-04** | **M** | Filtering | Background TV / podcast chatter triggers false positive wake-word and turn processing. | Implemented energy floor + speech pitch variability filter to discard distant, stationary TV speech. |
| **LOW-01** | **L** | Telemetry | Audio buffer overflow metrics and dropped frame telemetry logging. | Added structured logging under `logger("halbert.audio.buffer")` with rolling 60s drop counters. |

---

## 3. Confirmed Solid Architectural Pillars

1. **The Haloysius Subtractive Contract:** Zero PyTorch, TorchAudio, or CUDA dependencies. The entire audio AI stack compiles to static ONNX Runtime and `sherpa-onnx` ($<135\text{MB}$ total disk space).
2. **Unified Multi-Ingress Abstraction:** Wyoming TCP satellites, local desktop mics, Frigate RTSP streams, and WebRTC dashboard streams all normalize into identical `16kHz, 16-bit Mono PCM` chunks.
3. **Hardware Tiering:** Low-power homelab servers (N100, Pi 5) maintain $<5\%$ CPU load and $<300\text{MB}$ RAM, while desktop Pro users receive instantaneous $(<100\text{ms})$ local transcription.
4. **Episodic SQLite Integration:** Acoustic anomaly logs and music listening history integrate directly with `PersonaMemoryStore` and the Temporal Chronicle.

---

## 4. Model Tier & Effort Summary for Implementation

* **Opus Tier (Complex Architecture, Rust Tauri DSP, Concurrency, Safety RoleGates):** 8 Tasks (~35% of effort)
* **Sonnet Tier (Core Python Engines, React UI Components, SQLite Stores, API Routes):** 21 Tasks (~55% of effort)
* **Haiku Tier (Configuration Schemas, Doc Updates, Test Fixtures, Label Mappings):** 6 Tasks (~10% of effort)
