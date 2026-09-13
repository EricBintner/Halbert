# Handoff: Voice Inflection Implementation Status

> **Document:** `.handoff/HANDOFF-VOICE-IMPLEMENTATION-STATUS-2026-09-13.md`
> **Status:** Implementation baseline with scrutiny fixes
> **Date:** 2026-09-13
> **Branch:** `feat/kokoro-tts` (worktree `.claude/worktrees/feat-kokoro-tts`)
> **Parent handoff:** `HANDOFF-VOICE-INFLECTION-AND-HARDWARE-SCALING-2026-09-13.md`

---

## 1. What was built

Seven commits on `feat/kokoro-tts`:

| Commit | Summary |
|--------|---------|
| `27b71aa8` | Kokoro-82M TTS engine behind engine selection |
| `36c34e1a` | Streaming sentence delivery via `split_stream` + `synthesize_stream` |
| `0abf9760` | Streaming, prosody, and Kokoro voice-list corrections |
| `5ef362fd` | Wire streaming TTS into state machine behind `tts.stream_to_egress` flag |
| `f287e0b5` | Hardware detection, spatial arbiter, Wyoming egress, style vectors |
| `bacdb7dc` | Scrutiny fixes: prosody, arbiter, Wyoming egress, logging |
| `96bc7203` | Egress follows ingress, stale frame rejection, voice name resolution |
| `593ffd02` | Seam fixes: governance policy and voice backend protocol compliance |

### Kokoro-82M TTS (`audio/speech/tts_engine.py`)

- `KokoroTTS` class using `sherpa_onnx.OfflineTts` with Kokoro model config.
- Configurable model path, voices.bin, tokens.txt, espeak-ng-data, speaker ID, threads, speed, execution provider.
- Re-chunks long text to respect Kokoro's ~128-phoneme / 5-second limit.
- `synthesize()` async generator yielding PCM chunks with barge-in checks.
- `synthesize_stream()` for incremental sentence-level delivery.
- `sample_rate` returns the initialized model's actual rate (24000 Hz).
- Style resolution: `resolve_style(cadence_style)` maps style labels to speaker IDs via `DEFAULT_STYLE_MAP`.
- Voice name resolution: `resolve_voice_name(voice_id)` maps Kokoro voice names (e.g. "af_heart") to speaker IDs via `VOICE_NAME_MAP` (11 voices for v0_19).

### Streaming TTS in the state machine (`agents/state_machine.py`)

- When `tts.stream_to_egress: true` (default false):
  - LLM tokens are teed into an `asyncio.Queue`.
  - A background consumer runs `stream_spoken_segments()`.
  - Sentence-level segments are synthesized incrementally.
  - PCM is published to both the browser TTS egress hub and the Wyoming egress hub.
  - Barge-in is checked between sentences and between PCM chunks.
  - Display is woken before the first `begin` frame.
  - Full prosody applied per segment: rate, volume gain, whisper cap, voice_id (numeric or name), cadence_style.
  - Spatial arbiter is notified of TTS start/end for ducking and self-speech suppression.
- When false, existing batch behavior is unchanged.

### Hardware detection (`audio/hardware_detect.py`)

- `detect_hardware()` probes ONNX Runtime providers (CUDA, CoreML, NNAPI, DirectML, CPU).
- Falls back to `nvidia-smi` for CUDA detection when ORT lacks CUDA support.
- Apple Silicon detection via `platform.machine()` and `sysctl hw.memsize`.
- Classifies into 4 tiers: workstation (>=40GB VRAM / >=32GB Apple), desktop, low-power (N100/RPi5), mobile.
- `recommended_tts_config()` maps profile to execution_provider, num_threads, quantization.

### Spatial Audio Arbiter (`audio/spatial_arbiter.py`)

- Coincidence grouping: 250ms window, same speaker on different sources = one event.
- Per-speaker turn lock: 1.5s window, suppresses duplicate commands.
- Unknown speakers (empty speaker_id): always accepted — can't distinguish two unknowns.
- Self-speech suppression: VAD from the TTS source during TTS output is feedback.
- Half-duplex ducking: -18dB mic gain, VAD threshold 0.5 -> 0.85 during TTS.
- Media filtering: both per-observation `is_media` flag and persistent `_media_sources` set.
- Egress follows ingress: `egress_sink_for_current_turn(speaker_id)` returns the winning mic's source_id.
- Integrated into `AudioPipeline` — both speech track and Wyoming transcript path arbitrate before dispatch.

### Wyoming egress (`audio/egress/wyoming_egress.py`)

- `WyomingEgressHub` relays synthesized PCM to connected satellite speakers.
- Session-keyed pub/sub, same pattern as the browser TTS egress hub.
- Proper Wyoming framing (newline-terminated JSON header + binary payload).
- Sample rate stored from the `begin` frame and reused for `audio-chunk` frames (Kokoro 24000, not hardcoded 22050).
- No-op when no subscribers.
- Barge-in token registry and `cancel()` method.

### Wyoming ingress stale frame rejection (`audio/ingress/wyoming_ingress.py`)

- Client-monotonic timestamps: frames with `timestamp` field older than 350ms are dropped.
- Defends against network jitter / buffer bloat (Primitive 2 from handoff).
- Timestamp propagated to `AudioChunk.timestamp`.

### Channel capability (`integrations/channel_capability.py`)

- Implements Haloysius `ChannelCapability` protocol (6 methods).
- Adds hardware-aware accessors: `hardware_tier()`, `execution_providers()`, `output_sink_count()`, `remote_streaming_support()`, `sink_per_ingress()`.
- Degrades safely to text-only defaults when audio pipeline access fails.

### Voice backend (`integrations/voice_backend.py`)

- Implements Haloysius `VoiceBackend` protocol (4 methods).
- `synthesize()` applies prosody: rate, volume gain, whisper cap, voice_id (numeric or name), cadence_style.
- `synthesize_segments()` (renamed from `synthesize_stream` to avoid `StreamingVoiceBackend` false positive) consumes segment dicts and yields PCM.
- `list_voices()` returns `VoiceInfo` from `haloysius.seam`.

### Governance policy (`integrations/app_seam.py`)

- `HalbertGovernancePolicy` now implements full `GovernancePolicy` protocol:
  - `check()` returns safe/on_topic/redirect_suggestion dict.
  - `check_detailed()` returns `SimpleGovernanceResult` from `haloysius.seam`.
  - `authorize_action()` returns `ActionDecision.allow()`.

---

## 2. Scrutiny fixes (reverse-engineering pass)

Eight issues found and fixed in commit `bacdb7dc`:

1. `cadence_style` logged as "not yet applied" when it was applied via `resolve_style`.
2. Wyoming egress hardcoded 22050 in audio-chunk frames (Kokoro is 24000).
3. Arbiter suppressed all unknown speakers (empty `speaker_id` lock).
4. Arbiter never checked `_media_sources` in `arbitrate()`.
5. Streaming TTS only published to browser hub, not Wyoming egress hub.
6. Streaming TTS didn't notify arbiter of TTS start/end (no ducking).
7. Streaming TTS didn't apply prosody (volume, whisper, voice_id, cadence_style).
8. Unused `field` imports in hardware_detect and spatial_arbiter.

Three seam violations found and fixed in commit `593ffd02`:

1. `HalbertGovernancePolicy` missing `authorize_action` — tools would fail-closed.
2. `check_detailed` returned `SimpleNamespace` missing `on_topic`/`redirect_suggestion`.
3. `synthesize_stream` signature mismatch with `StreamingVoiceBackend` — false positive `isinstance`.

---

## 3. Test results

- 194 audio/voice/seam tests pass.
- Real Kokoro smoke test passed: 24000 Hz, 11 speakers, RTF 11-23x on Apple Silicon CPU.
- Streaming first-chunk latency: 15s (model warmup), then 43s total for 3.6s audio.
- CPU Kokoro is far slower than real time — hardware acceleration is essential for practical deployment.

---

## 4. What remains

### Voice flow — already wired end-to-end

The full voice interaction path is built and connected:

- **Mic -> Pipeline**: `PcmUplink` (frontend) -> `/api/audio/stream` -> `WebRtcIngress` -> `AudioChunk` -> pipeline -> VAD -> ASR -> speaker ID -> transcript
- **Transcript -> Turn**: pipeline -> `on_voice_turn` -> `_relay_voice_turn` -> `onTranscript` -> `submitTurn` -> `sendMessage` -> state machine
- **LLM -> TTS -> Speaker**: state machine -> `demux_response` -> `_speak_to_tts_egress` (batch) or `_speak_stream_to_tts_egress` (streaming) -> `TtsEgressHub` -> `/api/audio/tts` -> `TtsPlaybackClient` -> speaker

The frontend (`VoiceMode.tsx`) handles:
- Push-to-talk via `TouchBar` and mark tap
- Mic capture via `PcmUplink` (AudioWorklet + ScriptProcessorNode fallback)
- TTS playback via `TtsPlaybackClient` (WebSocket + Web Audio)
- Speaker recognition via `/api/audio/status` poll
- Standby tiers via `StandbyController`
- On-screen keyboard via `OnScreenKeyboard`
- Subtitle ribbon via `SubtitleRibbon`
- Barge-in via `cancel()` on `TtsPlaybackClient` (sends `{"type":"cancel"}` control frame)
- Mute toggle, echo-back, recognition timeout

The backend handles:
- `AudioPipelineCoordinator` — VAD -> ASR -> speaker ID -> barge-in -> `on_voice_turn`
- `WyomingIngress` — satellite audio ingress with stale frame rejection
- `WyomingEgressHub` — satellite audio egress (subscribers receive PCM)
- `TtsEgressHub` — browser TTS egress (session-keyed pub/sub)
- `SpatialAudioArbiter` — multi-mic arbitration, coincidence grouping, turn locks
- `HardwareProfile` — ONNX provider detection, tier classification
- `HalbertVoiceBackend` — TTS execution with prosody, voice name resolution, cadence style
- `HalbertChannelCapability` — capability reporting with hardware extensions
- `HalbertGovernancePolicy` — full `GovernancePolicy` protocol (authorize_action, check_detailed)
- `HalbertAppSeam` — `AppSeam` protocol implementation

### Rebase

The branch was rebased onto main (37 commits of drift — scheduler, continuity, model fixes). 8 commits ahead, 0 behind. Clean rebase, no conflicts.

### Test coverage

49 new tests in `test_voice_extensions.py`:
- Hardware detection (5)
- Channel capability hardware (4)
- Spatial arbiter (14)
- Kokoro voice name resolution (4)
- Wyoming egress hub (6)
- Kokoro style resolution (4)
- Wyoming stale frame rejection (4)
- TTS config stream_to_egress (4)
- Voice flow integration (4)

284 voice/audio/seam tests pass total.

### Test isolation fix

`_voice_turn_patches` now patches `load_config()` to return `stream_to_egress=False`. The developer's real `audio_config.yml` had `stream_to_egress: true`, which triggered the streaming TTS path and created a second barge-in token in tests that expected one.

### Style vectors

- The current style registry maps `cadence_style` labels to speaker IDs (voice packs).
- Native 256-dim style vector blending is not exposed by `sherpa_onnx` 1.13.8.
- If a future `sherpa_onnx` release exposes style vectors, revisit `resolve_style` to do actual vector interpolation instead of voice-pack selection.

### CAM++ biometric dedup

- The spatial arbiter handles coincidence grouping and turn locks.
- CAM++ speaker identification is upstream in Haloysius (speaker_id is an input to the arbiter, not computed by it).
- If Halbert needs local speaker ID (e.g. for Wyoming satellites without Haloysius), that would be a new module.

### Haloysius upstream (Phase 1)

- `ModalityAwarePromptBuilder` teleprompter formatting.
- `EmotionalStateV2` PAD -> `ProsodyMapper` -> `ProsodyHints` on every turn.
- `SpeechTextDemuxer` spoken vs display stream splitting.
- Clause-level streaming tokenizer at punctuation boundaries.

These are Haloysius-side changes, not Halbert-side.
