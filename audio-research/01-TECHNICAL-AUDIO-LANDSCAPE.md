# Technical Audio Landscape: Acoustic AI Perception for Intelligent Assistants

> **Foundational Research Document for Halbert** — Homelab Sysadmin & Sentient Home AI Assistant  
> Architecture: macOS + Linux | Tauri (React + Python FastAPI) | Haloysius Cognition Core  
> Author: Eric Bintner & Halbert Research  
> Date: 2026-08-29  

---

## Executive Summary

While Computer Vision provides an AI assistant with "eyes" to observe screens, terminals, and physical spaces, **Acoustic Perception ("ears")** provides continuous, omnidirectional, non-line-of-sight awareness. In both homelab infrastructure and sentient home automation, audio provides critical signals that vision cannot:
1. **Linguistic Speech & Intent:** Conversational voice commands, queries, and ambient requests.
2. **Paralinguistic & Affective Cues:** Speaker urgency, stress, hesitation, emotion, and tone of voice.
3. **Biometric Identity (Speaker ID):** Distinguishing authorized system administrators and specific family members from guests or unauthorized voices.
4. **Acoustic Event Detection (AED) & Safety Anomalies:** Critical non-speech physical transients (e.g., breaking glass, smoke/CO alarm chirps, high-frequency coil whine, HVAC bearing failures, water dripping, door knocks, gunshots, dog barks).
5. **Music Information Retrieval (MIR) & Context:** Ambient song recognition, genre/vibe tracking, and television/media acoustic filtering.

This document establishes the technical, algorithmic, and mathematical foundation for building a unified, multi-tier acoustic perception system for Halbert.

---

## Table of Contents

1. [The 5 Dimensions of Biological-Grade Hearing](#1-the-5-dimensions-of-biological-grade-hearing)
2. [Speech Processing, VAD & Endpointing](#2-speech-processing-vad--endpointing)
3. [Speaker Biometrics, Recognition & Diarization](#3-speaker-biometrics-recognition--diarization)
4. [Environmental Acoustic Event Detection (AED) & Anomaly Recognition](#4-environmental-acoustic-event-detection-aed--anomaly-recognition)
5. [Music Information Retrieval (MIR) & Ambient Sound Tagging](#5-music-information-retrieval-mir--ambient-sound-tagging)
6. [Architectural Paradigms: Cascaded Pipelines vs. End-to-End Multimodal Omni LLMs](#6-architectural-paradigms-cascaded-pipelines-vs-end-to-end-multimodal-omni-llms)
7. [Hardware Profiles & Edge Compute Budgets](#7-hardware-profiles--edge-compute-budgets)
8. [Comprehensive Academic & Industry Citations](#8-comprehensive-academic--industry-citations)

---

## 1. The 5 Dimensions of Biological-Grade Hearing

Human hearing is not a simple speech-to-text transcriber; it is an active, parallel, multi-band sensory organ. For Halbert to achieve true auditory autonomy, its acoustic intake must decompose raw continuous audio into five distinct information streams:

```
                                  ┌─────────────────────────────────────────┐
                                  │       Continuous Audio Stream           │
                                  │   (16kHz / 48kHz, 16-bit Mono/Stereo)   │
                                  └────────────────────┬────────────────────┘
                                                       │
         ┌───────────────────┬─────────────────────────┼─────────────────────────┬───────────────────┐
         ▼                   ▼                         ▼                         ▼                   ▼
┌─────────────────┐ ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐ ┌─────────────────┐
│ 1. Linguistic   │ │ 2. Paralinguistic│      │ 3. Biometric    │       │ 4. Acoustic     │ │ 5. Ambient &    │
│    Speech (ASR) │ │    & Affective  │      │    Identity     │       │    Events (AED) │ │    Music (MIR)  │
├─────────────────┤ ├─────────────────┤       ├─────────────────┤       ├─────────────────┤ ├─────────────────┤
│ "Turn off the   │ │ Tone: Urgent    │       │ Speaker: Eric   │       │ Glass shatter   │ │ Song: Daft Punk │
│  main pump"     │ │ Pitch: High     │       │ Role: Admin     │       │ Smoke alarm     │ │ Mood: Energetic │
│ Language: En-US │ │ Valence: Low    │       │ Confidence: 96% │       │ Water leak      │ │ Source: TV/Media│
└────────┬────────┘ └────────┬────────┘       └────────┬────────┘       └────────┬────────┘ └────────┬────────┘
         │                   │                         │                         │                   │
         └───────────────────┴─────────────────────────┼─────────────────────────┴───────────────────┘
                                                       │
                                                       ▼
                                      ┌─────────────────────────────────┐
                                      │   Auditory Context Synthesizer  │
                                      │   (Fused Structured Observation)│
                                      └────────────────┬────────────────┘
                                                       │
                                                       ▼
                                      ┌─────────────────────────────────┐
                                      │ Halbert State Machine & Memory  │
                                      └─────────────────────────────────┘
```

---

## 2. Speech Processing, VAD & Endpointing

### 2.1 Voice Activity Detection (VAD)
Voice Activity Detection classifies whether an incoming audio frame contains human speech or background noise. It serves as the primary computational gatekeeper: heavy speech-to-text models should remain dormant until VAD confirms voice onset.

* **Energy & Zero-Crossing Rates (Classical):** Fast ($<0.1\text{ms}$) but highly vulnerable to non-stationary acoustic noise (fans, typing, air conditioners).
* **WebRTC VAD (GMM-based):** Gaussian Mixture Models operating on sub-band energy. Extremely lightweight, but struggles with background TV speech and ambient babble.
* **Deep Learning VAD (Silero VAD v5):**
  * Architecture: 800k parameter recurrent/convolutional neural network trained on over 6,000 languages and noisy backgrounds.
  * Input: 30ms or 60ms chunks @ 16kHz (512 samples).
  * Latency: $<1\text{ms}$ inference on a single CPU core.
  * Features: Outputs continuous probability $P(\text{speech}) \in [0.0, 1.0]$ with built-in hysteresis thresholds ($\text{start\_threshold}=0.5$, $\text{neg\_threshold}=0.35$).
  * Memory: $<5\text{MB}$ total runtime footprint in ONNX.

### 2.2 Speech-to-Text (ASR) Engines in 2026

```
┌───────────────────────────┬────────────────────┬─────────────────┬────────────────────┬──────────────────────┐
│ Engine                    │ Architecture       │ Quantization    │ RAM / VRAM         │ Latency (10s Audio)  │
├───────────────────────────┼────────────────────┼─────────────────┼────────────────────┼──────────────────────┤
│ faster-whisper (tiny/base)│ Transformer Seq2Seq│ CTranslate2 INT8│ ~150MB - 250MB RAM │ ~80ms - 150ms (CPU)  │
│ faster-whisper (small)    │ Transformer Seq2Seq│ CTranslate2 INT8│ ~500MB RAM         │ ~250ms - 400ms (CPU) │
│ whisper.cpp (turbo)       │ Transformer Seq2Seq│ GGML Q4_K / Q8_0│ ~800MB RAM         │ ~180ms (Apple NEON)  │
│ Moonshine (base)          │ Hybrid Conv-Transf │ INT8 / ONNX     │ ~190MB RAM         │ ~70ms (Edge CPU)     │
│ Sherpa-ONNX (Zipformer)   │ Conformer Transd.  │ INT8 ONNX       │ ~120MB RAM         │ ~45ms (Streaming ASR)│
│ Parakeet (FastConformer)  │ CTC / RNN-T        │ FP16 / TensorRT │ ~1.2GB VRAM        │ ~30ms (GPU only)     │
└───────────────────────────┴────────────────────┴─────────────────┴────────────────────┴──────────────────────┘
```

#### Key Technical Dynamics:
1. **CTranslate2 & faster-whisper:** Up to 4x faster than vanilla OpenAI Whisper by utilizing customized INT8/INT4 GEMM kernels and efficient KV-cache allocation.
2. **Zipformer / Sherpa-ONNX:** Employs streaming Conformer architectures that emit text tokens incrementally (chunk-by-chunk) with zero lookahead penalty, achieving human-imperceptible endpointing latency.
3. **Moonshine:** Specifically optimized for edge inference on variable-length audio chunks without the quadratic padding overhead inherent in Whisper's rigid 30-second window.

### 2.3 Barge-In & Duplex Audio Orchestration
A critical failure of naive voice assistants is **acoustic feedback** and inability to handle **user interruptions (barge-in)**:
* **Acoustic Echo Cancellation (AEC):** When Halbert is speaking via Piper TTS, the microphone captures both the room ambient sound and Halbert's own speaker output. Without software AEC (via `webrtc-audio-processing` or hardware DSP), the system hears itself and enters feedback loops.
* **Barge-In Flush:** When the VAD detects high-confidence user speech while the TTS playback buffer is active, the engine must execute an atomic **playback cancel and audio ring-buffer flush** in $<150\text{ms}$.

---

## 3. Speaker Biometrics, Recognition & Diarization

### 3.1 Acoustic Feature Representations
Speaker recognition maps variable-length speech waveforms $x_{1:T}$ into a fixed-dimensional speaker embedding vector $\mathbf{e} \in \mathbb{R}^d$ that is invariant to channel conditions, linguistic content, and background noise, while maximizing distance between distinct individuals.

```
                    ┌────────────────────────────────────────────────────────┐
                    │               Raw Speech Waveform                      │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │     80-dimensional Log-Mel Filterbank Extraction       │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │  ECAPA-TDNN / CAM++ Multi-Scale Frame Feature Extractor│
                    │  - Squeeze-and-Excitation Residual Blocks              │
                    │  - Attentive Statistical Pooling                       │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │     L2-Normalized Speaker Embedding (d = 192 / 512)   │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │     Cosine Similarity against Enrolled User Database   │
                    │     S(e_1, e_2) = (e_1 · e_2) / (||e_1|| * ||e_2||)    │
                    └────────────────────────────────────────────────────────┘
```

### 3.2 State-of-the-Art Embedding Architectures
1. **ECAPA-TDNN (Emphasized Channel Attention, Propagation and Aggregation):**
   * Incorporates multi-layer feature aggregation and channel attention into time-delay neural networks.
   * State of the art on VoxCeleb benchmarks (EER $<0.8\%$).
   * Model footprint: ~6.2M parameters (~25MB ONNX int8).
2. **CAM++ (Context-Aware Masking):**
   * Uses densely connected convolutional networks with context-aware frame masking for ultra-fast, robust verification in noisy home environments.
   * Inference: $<8\text{ms}$ on low-power Intel/ARM CPUs.
3. **PyAnnote.audio 3.1:**
   * Gold-standard pipeline for speaker diarization (who spoke when in multi-party conversations).
   * Overkill for single-command voice turns, but essential for ambient multi-person meeting transcription and home chronicle summaries.

### 3.3 Enrollment & Persona Security Gates
Halbert stores enrolled household embeddings in SQLite (`PersonaMemoryStore`):
```sql
CREATE TABLE speaker_profiles (
    speaker_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'member', 'guest', 'restricted')),
    embedding_centroid BLOB NOT NULL, -- 192 x float32 (768 bytes)
    sample_count INTEGER DEFAULT 1,
    last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Biometric Authorization Policy:
* **`role == 'admin'` (e.g. Eric):** Full execution clearance for privileged tools (ZFS management, system reboots, deadbolt unlock, shell commands).
* **`role == 'member'`:** Safe home automation tools (lighting, media playback, thermostat adjustments).
* **`role == 'guest' / 'restricted'`:** Advisory queries only; high-impact tools blocked or prompted with Level 3 PIN verification.

---

## 4. Environmental Acoustic Event Detection (AED) & Anomaly Recognition

### 4.1 Why Environmental Hearing is Crucial
Sysadmin and home automation monitoring extends far beyond human speech. Critical operational failures and security threats produce distinctive acoustic signatures:
* **Homelab / Infrastructure:** Bearing friction in cooling fans, PSU coil whine, hard drive click-of-death, UPS inverter beep codes.
* **Home Security & Life Safety:** Smoke detector T3 alarm pattern (3 pulses at 3kHz), CO detector T4 pattern, window pane breakage (high-frequency shattering $>4\text{kHz}$), water pipe leaks/hissing, door kicks, pet distress.

### 4.2 Acoustic Event Architectures

#### 1. YAMNet (AudioSet Classifier)
* **Design:** Deep convolutional neural network based on MobileNet architecture, trained on Google's AudioSet ontology (521 audio event classes).
* **Input:** Log-mel spectrogram patches ($96 \times 64$ bins covering 0.96 seconds of audio).
* **Footprint:** 3.7 million parameters (~14MB ONNX).
* **Performance:** Executes in $\sim 3\text{ms}$ on a single CPU core.
* **AudioSet Classes Relevant to Halbert:**
  * `Alarm`, `Smoke detector, smoke alarm`, `Fire alarm`, `Siren`
  * `Glass`, `Shatter`, `Cracking`, `Thump, thud`
  * `Water tap, faucet`, `Drip`, `Liquid splash`
  * `Door`, `Knock`, `Slam`
  * `Dog`, `Bark`, `Cat`, `Purr`, `Infant crying`

#### 2. CLAP (Contrastive Language-Audio Pretraining)
* **Design:** Dual-encoder architecture (Audio Transformer + RoBERTa/BERT Text Encoder) trained on paired audio clips and natural language descriptions (similar to CLIP for images).
* **Capability:** **Zero-shot acoustic search and detection**.
* **Use Case:** Halbert can search for custom or ad-hoc acoustic patterns defined in plain English without training a new classifier:
  * Query: *"A high-pitched continuous metallic whine from a server cooling fan"*
  * Query: *"A dry cough or sneezing sound from the bedroom"*
* **Footprint:** $\sim 150\text{MB}$ ONNX; suitable for Tier 2/3 inference.

---

## 5. Music Information Retrieval (MIR) & Ambient Sound Tagging

### 5.1 Acoustic Fingerprinting vs. Neural Music Tagging
Halbert's musical awareness serves two distinct functions:

```
                               ┌────────────────────────────────────────┐
                               │         Ambient Music Stream           │
                               └───────────────────┬────────────────────┘
                                                   │
                         ┌─────────────────────────┴─────────────────────────┐
                         ▼                                                   ▼
        ┌───────────────────────────────────┐               ┌───────────────────────────────────┐
        │   Exact Track Identification      │               │   Affective & Scene Tagging       │
        │   (Chromaprint / AcoustID)        │               │   (CLAP / MusiCNN / Essentia)     │
        ├───────────────────────────────────┤               ├───────────────────────────────────┤
        │ - Extracts acoustic peak hashes   │               │ - Classifies genre, tempo (BPM)   │
        │ - Sub-second lookup in AcoustID   │               │ - Computes Valence & Arousal      │
        │ - Identifies exact song & artist  │               │ - Detects background TV / radio   │
        └─────────────────┬─────────────────┘               └─────────────────┬─────────────────┘
                          │                                                   │
                          └─────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
                               ┌────────────────────────────────────────┐
                               │   PersonaMemoryStore (EPISODIC)        │
                               │   - "Eric listened to synthwave while  │
                               │      working on ZFS maintenance."      │
                               └────────────────────────────────────────┘
```

1. **Exact Identification (AcoustID / Chromaprint):**
   * Converts raw audio into spectral peak fingerprints resilient to background noise and compression.
   * Queried against local or online acoustic databases to track exact song playback without relying on smart speaker metadata.
2. **Acoustic Scene & Speech Filtering:**
   * In multi-room environments, televisions, podcasts, and radios constantly broadcast human speech that is *not* directed at Halbert.
   * MIR and music detection models allow Halbert to tag background music/media and suppress false wake-word activations.

---

## 6. Architectural Paradigms: Cascaded Pipelines vs. End-to-End Multimodal Omni LLMs

The industry is currently divided between two distinct architectural paradigms for audio AI:

### Comparison Matrix

```
┌────────────────────────┬──────────────────────────────────────────┬──────────────────────────────────────────┐
│ Dimension              │ Paradigm 1: Modular Cascaded Pipeline    │ Paradigm 2: Native Omni Multimodal Stream │
├────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────┤
│ Stack                  │ VAD → Whisper → LLM → Piper TTS          │ Raw PCM → Gemini Live / Moshi / Mini-Omni│
│ Modality Fusion        │ Late fusion (Text only)                  │ Early fusion (Joint Audio-Text Tokens)   │
│ End-to-End Latency     │ 750ms – 1800ms                           │ 220ms – 350ms                            │
│ Local Compute Cost     │ Low (runs on $40 N100 or Pi 5)           │ High (requires 16GB+ VRAM or Cloud API)  │
│ Emotional Prosody      │ Lost during STT transcription            │ Full awareness of sarcasm, stress, tone  │
│ Non-Speech Sound Aware │ Requires separate parallel AED (YAMNet)  │ Naturally hears music, alarms, laughter  │
│ Offline Sovereignty    │ 100% offline, local-first                │ Requires heavy local GPU or Cloud stream │
│ Hallucination Surface  │ Confined to ASR mistakes                 │ Audio token drift and hallucinated sounds│
└────────────────────────┴──────────────────────────────────────────┴──────────────────────────────────────────┘
```

### Halbert's Dual-Track Synthesis:
Halbert does not choose one to the exclusion of the other. Halbert's unified architecture deploys **The Modular Cascaded Engine as the 100% local, low-power baseline (Tier 1 & 2)**, while providing a **WebRTC/WebSocket bridge to Native Omni LLMs (Gemini Live / OpenAI Realtime) for Pro users and interactive cloud voice sessions (Tier 3)**.

---

## 7. Hardware Profiles & Edge Compute Budgets

To uphold Halbert's subtractive engineering contract and maintain 24/7 reliability on low-power homelab hardware, the acoustic engine enforces strict computational boundaries:

```
┌───────────────────────────────────┬──────────────────────┬─────────────┬────────────┬────────────────────────┐
│ Profile                           │ Target Hardware      │ Max RAM     │ CPU Load   │ Audio Components       │
├───────────────────────────────────┼──────────────────────┼─────────────┼────────────┼────────────────────────┤
│ Micro Satellite (Edge)            │ ESP32-S3 / Atom Echo │ <8MB        │ N/A (DSP)  │ microWakeWord, PCM Tx  │
│ Homelab Eco (N100, Pi 5, 8GB)     │ HAOS + Halbert Home  │ <350MB      │ <6% Core   │ Silero VAD, YAMNet ONNX│
│                                   │                      │             │            │ Sherpa-Zipformer INT8  │
│                                   │                      │             │            │ ECAPA-TDNN ONNX        │
│ Homelab Pro (x86_64, 32GB)        │ Proxmox / TrueNAS    │ <1.5GB      │ <15% Core  │ faster-whisper (small) │
│                                   │                      │             │            │ CLAP ONNX, PyAnnote    │
│ Desktop Companion (macOS M-Series)│ Halbert Pro (Tauri)  │ <2.0GB      │ Apple NEON │ whisper.cpp Turbo      │
│                                   │                      │             │            │ Gemini Live WebRTC     │
└───────────────────────────────────┴──────────────────────┴─────────────┴────────────┴────────────────────────┘
```

---

## 8. Comprehensive Academic & Industry Citations

### 8.1 Speech Recognition & VAD Foundations
1. **Radford, A., Kim, J. W., Xu, T., Brockman, G., McLeavey, C., & Sutskever, I. (2023).** *Robust Speech Recognition via Large-Scale Weak Supervision.* International Conference on Machine Learning (ICML 2023). [arXiv:2212.04356](https://arxiv.org/abs/2212.04356)
2. **Silero Team. (2024).** *Silero VAD: Pre-trained Enterprise-Grade Voice Activity Detector.* GitHub Repository. [https://github.com/snakers4/silero-vad](https://github.com/snakers4/silero-vad)
3. **Useful Sensors. (2024).** *Moonshine: Fast and Accurate Speech Recognition for Edge Devices.* [https://github.com/usefulsensors/moonshine](https://github.com/usefulsensors/moonshine)
4. **Yao, Z., Guo, L., Yang, X., Kang, W., Kuang, F., Yang, Y., Xie, Z., & Povey, D. (2023).** *Zipformer: A Faster and Better Encoder for End-to-End Speech Recognition.* Interspeech 2023. [arXiv:2310.11230](https://arxiv.org/abs/2310.11230)
5. **Klein, G., Hernandez, D. (2020).** *CTranslate2: Fast Inference Engine for Transformer Models.* OpenNMT. [https://github.com/OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2)
6. **Gerganov, G. (2022).** *whisper.cpp: High-performance inference of OpenAI's Whisper model in C/C++.* [https://github.com/ggerganov/whisper.cpp](https://github.com/ggerganov/whisper.cpp)

### 8.2 Speaker Biometrics & Diarization
7. **Desplanques, B., Thienpondt, J., & Demuynck, K. (2020).** *ECAPA-TDNN: Emphasized Channel Attention, Propagation and Aggregation in TDNN Based Speaker Verification.* Interspeech 2020. [arXiv:2005.07143](https://arxiv.org/abs/2005.07143)
8. **Wang, H., Zheng, S., Chen, Y., Cheng, L., & Chen, Q. (2023).** *CAM++: A Fast and Efficient Network for Speaker Verification Using Context-Aware Masking.* Interspeech 2023. [arXiv:2303.00332](https://arxiv.org/abs/2303.00332)
9. **Bredin, H., Yin, R., Coria, J. M., et al. (2020).** *pyannote.audio: Neural Building Blocks for Speaker Diarization.* ICASSP 2020. [arXiv:1911.01255](https://arxiv.org/abs/1911.01255)
10. **Snyder, D., Garcia-Romero, D., Sell, G., Povey, D., & Khudanpur, S. (2018).** *X-Vectors: Robust DNN Embeddings for Speaker Recognition.* ICASSP 2018.

### 8.3 Environmental Sound Classification & Anomaly Detection
11. **Gemmeke, J. F., Ellis, D. P., Freedman, D., Jansen, A., Lawrence, W., Moore, R. C., Plakal, M., & Ritter, M. (2017).** *Audio Set: An ontology and human-labeled dataset for audio events.* ICASSP 2017.
12. **Gong, Y., Chung, Y. A., & Glass, J. (2021).** *AST: Audio Spectrogram Transformer.* Interspeech 2021. [arXiv:2104.01778](https://arxiv.org/abs/2104.01778)
13. **Elizalde, B., Deshmukh, S., Ismail, M. A., & Wang, H. (2023).** *CLAP: Learning Audio Representations from Natural Language Supervision.* ICASSP 2023. [arXiv:2206.04769](https://arxiv.org/abs/2206.04769)
14. **Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023).** *Large-Scale Contrastive Language-Audio Pretraining with Feature Fusion and Keyword-to-Caption Augmentation.* ICASSP 2023. [arXiv:2211.06687](https://arxiv.org/abs/2211.06687)
15. **Chen, S., Wang, Y., Chen, Z., et al. (2022).** *BEATs: Audio Pre-Training with Acoustic Tokenizers.* ICML 2023. [arXiv:2212.09058](https://arxiv.org/abs/2212.09058)

### 8.4 Music Information Retrieval (MIR) & Audio Fingerprinting
16. **Chernyak, L., & AcoustID Contributors. (2023).** *Chromaprint: Open Source Audio Fingerprinting Library.* [https://acoustid.org/chromaprint](https://acoustid.org/chromaprint)
17. **Wang, A. (2003).** *An Industrial-Strength Audio Search Algorithm.* International Conference on Music Information Retrieval (ISMIR 2003).
18. **Bogdanov, D., Wack, N., Gómez, E., et al. (2013).** *Essentia: An Open-Source Library for Sound and Music Analysis.* ACM Multimedia.

### 8.5 Real-Time Multimodal & Omni LLMs
19. **Kyutai Labs. (2024).** *Moshi: A Speech-Text Foundation Model for Real-Time Full-Duplex Dialogue.* [arXiv:2410.00037](https://arxiv.org/abs/2410.00037)
20. **Xie, Z., et al. (2024).** *Mini-Omni: Language Models Can Hear and Speak.* [arXiv:2408.16725](https://arxiv.org/abs/2408.16725)
21. **Fixie AI. (2024).** *Ultravox: A Fast Multimodal Voice LLM.* [https://github.com/fixie-ai/ultravox](https://github.com/fixie-ai/ultravox)
22. **Google DeepMind. (2024).** *Gemini Multimodal Live API: Bi-directional Audio/Video Streaming.* [Google Cloud Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal-live-api)
23. **OpenAI. (2024).** *OpenAI Realtime API via WebSockets.* [OpenAI Developer Documentation](https://platform.openai.com/docs/guides/realtime)
