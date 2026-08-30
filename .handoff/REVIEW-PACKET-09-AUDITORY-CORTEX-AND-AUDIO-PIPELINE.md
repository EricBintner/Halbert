# Review Packet 09: Auditory Cortex & Multimodal Audio AI Pipeline

**Review Level:** **Fable Level Review**  
**Domain:** Local Audio Inference, Sherpa-ONNX Engine, Streaming Zipformer ASR, Silero VAD, Piper TTS, CAM++ Speaker ID, RoleGate Safety, and Wyoming Audio Ingress  
**Target Date:** 2026-08-30  
**Status:** Ready for Deep Subsystem Scrutiny & Safety Audit  

---

## 1. Executive Summary & Review Scope

The Auditory Cortex (`feat/auditory-cortex`) represents the expansion of Halbert into full-duplex, local acoustic cognition. It gives Halbert native hearing and speech while strictly maintaining the **subtractive contract** (zero heavy dependencies loaded unless audio features are explicitly enabled).

Key systems built:
1. **Core Audio Inference Engine:** Async ring buffer (`AsyncRingBuffer`), Silero VAD v5, Streaming Zipformer INT8 ASR, Piper TTS with barge-in cancellation token, and openWakeWord.
2. **Audio Ingress Coordinator:** Dual-track `AudioPipelineCoordinator` supporting Wyoming binary framing, local microphone loopback TCP socket, WebRTC, and RTSP stream ingress.
3. **Speaker Identification & Safety Gate:** CAM++ 256-dimensional embedding extractor, SQLite speaker store (`speaker_profiles`), and the **`RoleGate`** safety wrapper (enforcing an invariant: unknown/guest speakers can never trigger HIGH-risk tools).
4. **Acoustic Anomaly Detector:** CED-tiny/Zipformer audio tagger and proactive acoustic anomaly finding generator.
5. **Frontend Audio UI:** `AudioSettings.tsx`, `SpeakerProfilesCard.tsx`, `VoiceEnrollmentModal.tsx`, `AcousticAnomalyModule.tsx`, and `AcousticAuraIndicator.tsx`.

The reviewing model (**Fable**) must scrutinize the audio state machine, verify memory bounds on ring buffers, audit the RoleGate invariant against privilege escalation, and review the adversarial findings in `documentation/design/13-adversarial-review-modality-handoff.md`.

---

## 2. Planning, Design & Scrutiny Documents

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/audio/00-REVIEW-SUMMARY.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/audio/00-REVIEW-SUMMARY.md) | Technical scrutiny summary | 17 findings (5 critical, 7 high), corrected model footprints |
| [`.handoff/audio/01-CORRECTED-ARCHITECTURE.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/audio/01-CORRECTED-ARCHITECTURE.md) | Corrected technical architecture | Sherpa-onnx APIs, CAM++/CED-tiny substitution, Wyoming framing |
| [`.handoff/audio/02-CODEBASE-INTEGRATION-MAP.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/audio/02-CODEBASE-INTEGRATION-MAP.md) | Codebase integration points | State machine hooks, tool execution boundaries, event mapper |
| [`.handoff/audio/03-UX-SURFACES.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/audio/03-UX-SURFACES.md) | Audio UX & UI specs | Speaker enrollment, visual aura indicator, ambient noise graphs |
| [`.handoff/audio/04-PHASED-WORK-BREAKDOWN.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/audio/04-PHASED-WORK-BREAKDOWN.md) | 35-task phased work breakdown | Task-level breakdown, model tier assignments (Fable/Opus) |
| [`documentation/design/13-adversarial-review-modality-handoff.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/13-adversarial-review-modality-handoff.md) | Adversarial modality review | Wyoming admin default vulnerability, markdown-in-TTS bug, AEC gaps |

---

## 3. Git History & Code Commits (`feat/auditory-cortex`)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `8d8a4673` | 2026-08-29 | Audio: technical scrutiny of auditory cortex architecture | `.handoff/audio/*` |
| `dd1eabae` | 2026-08-29 | Audio: implement Phase 1-3 Python foundation (15 modules, 18 tests) | `audio/*`, `tools/role_gate.py`, `dashboard/routes/audio.py` |
| `384364c6` | 2026-08-29 | Audio: implement Phase 3-4 state machine, findings, and frontend | `findings/detectors/acoustic_anomaly.py`, `components/audio/*` |
| `0a1c9272` | 2026-08-29 | Audio: fix sherpa-onnx API correctness + wire integration gaps | `audio/speech/*`, `audio/pipeline.py` |

---

## 4. Key Files & Architectural Components

- **Core Audio Pipeline:**
  - [`halbert_core/halbert_core/audio/pipeline.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/pipeline.py)
  - [`halbert_core/halbert_core/audio/buffer.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/buffer.py)
  - [`halbert_core/halbert_core/audio/config.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/config.py)
- **Speech & Safety Modules:**
  - [`halbert_core/halbert_core/audio/speech/asr_engine.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/speech/asr_engine.py)
  - [`halbert_core/halbert_core/audio/speech/tts_engine.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/speech/tts_engine.py)
  - [`halbert_core/halbert_core/audio/speech/speaker_id.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/speech/speaker_id.py)
  - [`halbert_core/halbert_core/audio/speech/barge_in.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/speech/barge_in.py)
  - [`halbert_core/halbert_core/tools/role_gate.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/tools/role_gate.py)
- **Ingress Adapters:**
  - [`halbert_core/halbert_core/audio/ingress/wyoming_ingress.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/ingress/wyoming_ingress.py)
  - [`halbert_core/halbert_core/audio/ingress/local_mic.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/audio/ingress/local_mic.py)
- **Frontend Components:**
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/audio/AudioSettings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/audio/AudioSettings.tsx)
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/audio/VoiceEnrollmentModal.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/audio/VoiceEnrollmentModal.tsx)

---

## 5. Incomplete Work & Open Items

1. **CRITICAL: Wyoming Agent Speaker Role Vulnerability:** `wyoming_agent.py` defaults to `speaker_role="admin"`, giving any voice satellite complete root/admin tool execution. Must default to `"unknown"` or HA-authenticated role.
2. **CRITICAL: Markdown Stripper for Speech:** `tts_engine.py` and `proactive_speak()` send raw markdown to Piper/HA TTS. Need a `strip_markdown_for_speech()` utility.
3. **CRITICAL: Wyoming Session Collision:** `session_id=f"wyoming-{os.getpid()}"` in `wyoming_agent.py` causes concurrent requests to collide. Must mint UUID per turn and thread `conversation_id`.
4. **Barge-in Handler Wiring:** `BargeInHandler` is written but never instantiated or connected to `AudioPipelineCoordinator`.
5. **Rust AEC Implementation:** `audio_capture.rs` is missing from `src-tauri`, leaving loopback mic captures prone to self-interruption from speaker output.

---

## 6. Review Directives for Fable

- **Subtractive Contract Verification:** Confirm that all audio modules in `audio/` can be imported when optional extras (`sherpa-onnx`, `onnxruntime`, `piper-tts`) are NOT installed without raising `ImportError`.
- **RoleGate Invariant Proof:** Trace tool execution in `tools/executor.py` through `RoleGate`. Prove mathematically that no combination of speaker roles (`unknown`, `guest`) can execute a `HIGH`-risk tool without human confirmation.
- **Verification Command:** Run `pytest halbert_core/tests/test_audio_buffer.py halbert_core/tests/test_role_gate.py -v`.
