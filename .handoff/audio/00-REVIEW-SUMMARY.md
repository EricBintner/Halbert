# Audio AI Architecture — Scrutiny Review Summary

> **Document:** `.handoff/audio/00-REVIEW-SUMMARY.md`
> **Parent:** `.handoff/HANDOFF-AUDIO-AI-ARCHITECTURE-AND-UX-2026-08-29.md`
> **Date:** 2026-08-29
> **Status:** Scrutinized & Corrected — Ready for Implementation
> **Worktree:** `feat/auditory-cortex`

---

## What happened

The original handoff + research suite (01-03) was reviewed against (a) external reality — library repos, protocol specs, PyPI, crate registries — via four parallel verification subagents, and (b) the actual Halbert codebase — every integration point was traced to real files. The research foundation is strong, but several foundational technical claims are refuted by external evidence, and several integration points reference components that don't exist or are misidentified.

This review packet supersedes the original handoff's technical specs. The original research suite (`audio-research/01-03`) remains valid as background; the corrections below are what implementation must follow.

---

## Companion files

| File | Contents |
|------|----------|
| `00-REVIEW-SUMMARY.md` | This file — findings table, model tier assignments, status |
| `01-CORRECTED-ARCHITECTURE.md` | Corrected pipeline diagram, subtractive contract, schemas, model choices |
| `02-CODEBASE-INTEGRATION-MAP.md` | Every integration point mapped to actual codebase files |
| `03-UX-SURFACES.md` | Corrected 5 UX surfaces with frontend component mapping |
| `04-PHASED-WORK-BREAKDOWN.md` | Phase-by-phase task list with model tier + effort level per task |

---

## Findings summary (17 total)

### CRITICAL (5)

| ID | Finding | Resolution |
|----|---------|------------|
| C1 | `SystemEventMapper` referenced for anomaly→chronicle routing, but the actual findings/gate pipeline is `detector_runner → findings/store → proactive/gate → events → SSE`. SystemEventMapper exists but is a cognition bridge (worries/drives/emotions), not a findings pipeline. | Route anomalies through BOTH: (1) new acoustic Detector in `detector_runner` for findings/gate/chronicle, (2) `SystemEventMapper.add_event()` for cognition. |
| C2 | `ToolSafetyFramework` has no identity/role axis. Wiring `speaker_role` into it is a design change to a high-blast-radius component. | Create `RoleGate` wrapper that composes with `ToolSafetyFramework.classify()` (can only tighten, never loosen). Mirror existing `_check_skill_safety` pattern. |
| C3 | `PersonaMemoryStore` does not exist. Speaker profiles have no home. | Create `audio/storage/speaker_store.py` under `utils.paths.data_subdir`. Stop using the name "PersonaMemoryStore" in specs. |
| C4 | ECAPA-TDNN and YAMNet are NOT supported by sherpa-onnx. ECAPA-TDNN causes errors per sherpa's own scripts. YAMNet is absent from the repo. | Swap to CAM++ (256-dim, 27.9MB) for speaker ID. Swap to CED-tiny or Zipformer-small-audio-tagging for acoustic events. Update schema from 192-dim to 256-dim. |
| C5 | `<135MB disk / <300MB RAM` footprint is refuted. Minimal model set is ~170MB. | Revise budget: ~170MB minimal, ~200MB typical, ~400MB RAM runtime. Document per-model sizes with actual measured values. |

### HIGH (7)

| ID | Finding | Resolution |
|----|---------|------------|
| H4 | Wyoming `audio-chunk` uses binary framing (header + data_length + payload_length), NOT JSONL. Current `wyoming_agent.py` readline() parser will break on audio frames. | Implement new `audio/ingress/wyoming_ingress.py` with proper frame reader. Leave `wyoming_agent.py` as text-only conversation endpoint. |
| H5 | `collections.deque` is insufficient for multi-producer overlapping-read audio buffering. | Split by platform: Rust ring buffer for desktop (Tauri), `asyncio.Queue` + `array.array` for headless Linux. |
| H6 | Barge-in cancellation targets (Piper TTS, HA satellite playback) don't exist yet. | Phase 2 must define two cancellation targets: (1) local Piper (cancellable), (2) HA satellite (best-effort `media_player.stop`). |
| H7 | Piper TTS original repo (`rhasspy/piper`) is archived. | Use `OHF-Voice/piper1-gpl` fork for voice models and tooling. |
| H8 | "Hey Halbert" wake word requires training — not pre-trained in openWakeWord. | Add Phase 1 sub-task: train openWakeWord model using synthetic data pipeline (~1hr on Colab). |
| H9 | Chromaprint/AcoustID song recognition requires network access to AcoustID API. No offline database. | Document that music ID requires network. Disable in offline/sovereign mode. Local fingerprint DB is a future enhancement. |
| H10 | YAMNet <3ms is NPU-only. On CPU it's ~12.5ms. (Moot since YAMNet isn't supported — see C4 — but the replacement model's latency must be measured.) | Budget ~12-15ms per 1s window on CPU for the ambient track. Measure actual CED/Zipformer latency. |

### MEDIUM (4)

| ID | Finding | Resolution |
|----|---------|------------|
| M7 | `sherpa-onnx` must be a lazy optional extra, not a hard dep. | Add `audio-inference = ["sherpa-onnx>=1.10", "onnxruntime>=1.16"]` to pyproject.toml. All audio modules use function-level lazy imports. |
| M8 | AEC is missing from all phase checklists but is required for desktop duplex. | Add AEC to Phase 2. Use `webrtc-audio-processing` crate (tonarino/webrtc-audio-processing, not the 404 URL in research). |
| M9 | UX surfaces assume frontend components that don't exist and aren't mapped to existing architecture. | Map each surface to existing frontend: header slot in Layout.tsx, settings tab alongside Vision, module registry for anomaly cards. |
| M10 | `pyproject.toml` is missing `cv-inference` optional group that vision code references. | Fix `cv-inference` group while adding `audio-inference`. |

### LOW (5)

| ID | Finding | Resolution |
|----|---------|------------|
| L10 | `acoustic_event_log` schema overlaps with `findings/store.py`. | If anomalies become findings (C1), this table is a thin companion log only. Pick one source of truth for finding state. |
| L11 | Barge-in <150ms is untestable without a latency harness. | Add Phase 1 test: synthetic PCM stream measuring VAD-onset-to-cancel-token propagation. |
| L12 | `describe` capability in `wyoming_agent.py` reports `streaming: False`. | Update to reflect ASR capabilities once audio ingress lands. |
| L13 | `cpal` <5ms latency is achievable but not guaranteed. | Use `BufferSize::Fixed`, measure on target Mac hardware. |
| L14 | sherpa-onnx `SpeakerEmbeddingManager` already implements cosine similarity and multi-sample averaging. | Use built-in `.add()`, `.search()`, `.verify()`, `.score()` instead of reinventing in `speaker_store.py`. |

---

## Model tier & effort level assignments

Each task in the work breakdown (file `04-PHASED-WORK-BREAKDOWN.md`) is assigned:

- **Model tier**: `opus` (deep reasoning, architecture, cross-system design) / `sonnet` (solid implementation, well-specified code) / `haiku` (mechanical, boilerplate, config)
- **Effort level**: `ultracode` (multi-day, deep, novel) / `max` (full session, complex) / `xhigh` (several hours, substantial) / `high` (focused, 1-2 hours) / `med` (quick, well-defined)

### Summary by phase

| Phase | Tasks | Recommended tier | Effort range |
|-------|-------|-------------------|--------------|
| Phase 1: Core Engine | 8 tasks | opus for architecture, sonnet for implementation | xhigh–max |
| Phase 2: Ingress + Desktop | 10 tasks | opus for Rust/transport, sonnet for Python ingress | max–ultracode |
| Phase 3: Speaker ID + Safety | 7 tasks | opus for RoleGate design, sonnet for enrollment | xhigh–max |
| Phase 4: Acoustic Events + Music | 6 tasks | sonnet for detection, haiku for wiring | high–xhigh |
| Phase 5: Cloud Omni Live | 4 tasks | opus for WebRTC bridge, sonnet for UI toggle | xhigh–max |

---

## What was confirmed solid (no changes needed)

- sherpa-onnx as unifying engine (zero PyTorch, ONNX Runtime only)
- Silero VAD v5 (2.2MB, <1ms per 32ms chunk)
- Streaming Zipformer ASR (chunk-by-chunk, zero future lookahead)
- Piper TTS via sherpa-onnx (use OHF-Voice fork)
- Wyoming binary framing for satellite audio (16kHz/16-bit/mono PCM)
- HA native Wyoming integration (no HACS needed)
- Tauri v2 global hotkeys + menu bar tray (NSStatusItem)
- Speaker ID enrollment/verification API (built into sherpa-onnx)
- OpenAI Realtime API (WebSocket bidirectional audio)
- Gemini Live API (WebSocket bidirectional, latency is soft ~200-370ms)
- The dual-track architecture (Speech vs Ambient) is correct
- The 5-phase sequencing is mostly right (AEC pulled into Phase 2)
