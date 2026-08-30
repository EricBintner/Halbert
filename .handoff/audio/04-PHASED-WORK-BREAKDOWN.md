# Phased Work Breakdown

> **Document:** `.handoff/audio/04-PHASED-WORK-BREAKDOWN.md`
> Every task assigned a model tier and effort level.

**Model tiers:** `opus` (deep reasoning, architecture, cross-system) / `sonnet` (solid implementation, well-specified) / `haiku` (mechanical, boilerplate, config)

**Effort levels:** `ultracode` (multi-day, deep, novel) / `max` (full session, complex) / `xhigh` (several hours, substantial) / `high` (focused, 1-2hr) / `med` (quick, well-defined)

---

## Phase 1: Core Auditory Engine Foundation

### T1.1 — Module scaffold + config + lazy import gate
**Tier:** sonnet | **Effort:** high

Create `halbert_core/audio/` package structure:
- `__init__.py` (empty, imports cleanly with zero audio deps)
- `config.py` — AudioConfig dataclass, yaml load/save, all OFF by default. Mirror `vision/config.py` exactly: read-on-every-use, `~/.config/halbert/audio_config.yml`.
- `is_available.py` — `is_audio_available()` checks `sherpa_onnx` import

**Acceptance:** `from halbert_core.audio import config` works with no audio deps installed. `is_audio_available()` returns False without sherpa-onnx.

### T1.2 — Ring buffer (platform-split)
**Tier:** opus | **Effort:** xhigh

`halbert_core/audio/buffer.py`:
- Desktop path: documented interface for Rust ring buffer via socket (actual Rust impl in T2.3)
- Headless path: `asyncio.Queue` (maxsize for 10s of 16kHz/16-bit/mono = ~320KB) + `array.array('h')` rolling window
- Multi-consumer safe: consumers read slices without blocking the producer
- 10s rolling memory, pre-trigger context access

**Acceptance:** Unit test: producer writes 10s of synthetic PCM, two consumers read overlapping 1s windows without data loss or blocking.

### T1.3 — Silero VAD v5 wrapper
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/speech/vad.py`:
- Lazy `import sherpa_onnx` inside `__init__`
- Silero VAD v5 ONNX model (2.2MB, 512-sample/32ms windows at 16kHz)
- `detect_speech(pcm_bytes) -> list[SpeechSegment]` with onset/offset timestamps
- Hysteresis thresholds: start=0.5, neg=0.35 (Silero defaults)
- Thread-safe (VAD session per ingress source)

**Acceptance:** Unit test with synthetic PCM (silence + sine wave speech-like burst) verifies onset/offset detection. Test runs without sherpa-onnx installed (skips with clear message).

### T1.4 — Streaming ASR engine
**Tier:** sonnet | **Effort:** xhigh

`halbert_core/audio/speech/asr_engine.py`:
- Lazy `import sherpa_onnx`
- `OnlineRecognizer` with streaming Zipformer INT8 (small English model)
- `transcribe_stream(pcm_iterator) -> AsyncIterator[str]` yielding partial transcripts
- Zero future lookahead (confirmed: chunk-16-left-64 architecture)
- Configurable model path via `audio_config.yml`

**Acceptance:** Unit test with synthetic PCM stream yields partial transcripts. Skips without sherpa-onnx.

### T1.5 — Wake word training ("Hey Halbert")
**Tier:** opus | **Effort:** xhigh

Train openWakeWord model for "Hey Halbert":
- Define target phrase in YAML config
- Generate synthetic TTS positive/adversarial samples
- Pre-compute openWakeWord features
- Run `train.py` (~1hr on Colab or local GPU)
- Export trained `.tflite` / `.onnx` model
- Document training process in `audio/speech/wake_word.py` docstring

`halbert_core/audio/speech/wake_word.py`:
- Lazy `import openwakeword`
- `detect_wake_word(pcm_chunk) -> bool` with confidence threshold
- Load custom "Hey Halbert" model from `data_subdir("audio") / "hey_halbert.ww.tflite"`

**Acceptance:** Trained model file exists. Unit test with synthetic audio returns False for silence, True for phrase-like audio (mocked if no model).

### T1.6 — Piper TTS engine
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/speech/tts_engine.py`:
- Lazy `import sherpa_onnx`
- Piper VITS via `sherpa_onnx.OfflineTTS`
- Voice models from OHF-Voice/piper1-gpl (NOT archived rhasspy/piper)
- `synthesize(text) -> AsyncIterator[bytes]` yielding PCM chunks
- Cancellation token for barge-in (stops generation mid-stream)
- Configurable voice model path via `audio_config.yml`

**Acceptance:** Unit test synthesizes short text, yields PCM chunks. Cancellation token aborts mid-stream. Skips without sherpa-onnx.

### T1.7 — Barge-in cancellation harness + test
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/speech/barge_in.py`:
- `BargeInToken` — asyncio.Event wrapper
- Local target: cancels Piper TTS stream
- HA satellite target: best-effort `media_player.stop` per area (via `HAClient`)
- `test_barge_in_latency.py`: synthetic PCM stream, measure VAD-onset-to-cancel propagation

**Acceptance:** Latency test shows <150ms from VAD speech detection to Piper cancellation. HA satellite path documented as lossy.

### T1.8 — pyproject.toml optional deps
**Tier:** haiku | **Effort:** med

Add to `halbert_core/pyproject.toml`:
```toml
audio-inference = ["sherpa-onnx>=1.10", "onnxruntime>=1.16"]
audio-fingerprint = ["pyacoustid>=1.3"]
cv-inference = ["onnxruntime>=1.16", "ultralytics>=8.0", "opencv-python>=4.8"]
```

**Acceptance:** `pip install halbert-core[audio-inference]` installs sherpa-onnx. Core install remains subtractive (pyyaml + requests only).

---

## Phase 2: Multi-Ingress & Desktop Companion

### T2.1 — Wyoming binary frame reader
**Tier:** opus | **Effort:** xhigh

`halbert_core/audio/ingress/wyoming_ingress.py` (NEW):
- Proper Wyoming protocol frame reader:
  1. `readline()` for JSON header
  2. `readexactly(data_length)` for additional JSON data
  3. `readexactly(payload_length)` for binary PCM payload
- Handle `audio-start` (capture rate/width/channels), `audio-chunk` (PCM), `audio-stop`
- Handle `transcript` (text from HA conversation pipeline)
- Handle `ping`/`pong`/`describe`
- FD cleanup on sudden disconnection (catch `IncompleteReadError`)
- Feed PCM into ring buffer, transcripts into agent pipeline

Leave existing `wyoming_agent.py` as the text-only conversation endpoint.
The new ingress feeds it transcripts.

**Acceptance:** Unit test with mocked TCP stream: binary audio frames parse correctly, text transcripts route to agent, sudden disconnect cleans up FDs.

### T2.2 — Local mic ingress (Python side)
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/ingress/local_mic.py`:
- Reads from loopback TCP socket (127.0.0.1:port)
- Expects 16kHz/16-bit/mono PCM
- Feeds into ring buffer
- Socket path/port configurable via `audio_config.yml`
- Reconnect logic if Rust side restarts

**Acceptance:** Unit test with mock TCP server sending synthetic PCM. Ring buffer receives data.

### T2.3 — Rust cpal capture + loopback socket
**Tier:** opus | **Effort:** max

`src-tauri/src/audio_capture.rs`:
- `cpal` input stream (CoreAudio on macOS, ALSA on Linux)
- `BufferSize::Fixed` for low latency (measure on target hardware)
- AEC via `webrtc-audio-processing` crate (tonarino/webrtc-audio-processing)
  - C++ build dependency: document clang/gcc/meson/ninja requirement
  - Applied to capture stream BEFORE socket dispatch
- Write PCM to loopback TCP socket (127.0.0.1:port)
- Tauri commands for start/stop/mute (control only, NOT audio data)

`src-tauri/Cargo.toml` additions:
```toml
cpal = "0.22"
webrtc-audio-processing = { version = "~2.0", features = ["bundled"] }
```

**Acceptance:** Rust captures mic, applies AEC, writes to socket. Python side (T2.2) receives data. Latency measured on Mac.

### T2.4 — AEC integration
**Tier:** opus | **Effort:** xhigh

Part of T2.3 but called out separately for visibility:
- `webrtc-audio-processing` provides AEC, AGC, noise suppression
- Reference signal: Piper TTS output (fed back as echo reference)
- Without AEC: Halbert hears its own TTS -> VAD false-triggers -> feedback loop
- This is a HARD REQUIREMENT for desktop duplex, not optional

**Acceptance:** With AEC enabled, playing Piper TTS does NOT trigger VAD speech detection on the mic input.

### T2.5 — RTSP camera audio ingress
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/ingress/rtsp_ingress.py`:
- Connect to Frigate RTSP streams
- Extract audio track (commonly Opus)
- Decode via `symphonia` (pure Rust for WAV/PCM) or `symphonia-adapter-libopus` (C dep for Opus)
- Resample to 16kHz/16-bit/mono
- Feed into ring buffer with `source_type="frigate_rtsp"` and `area_id` from camera config

**Acceptance:** Unit test with mock RTSP stream (or skip if no Frigate available). Document libopus C dependency.

### T2.6 — WebRTC/dashboard ingress
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/ingress/webrtc_ingress.py`:
- FastAPI WebSocket endpoint at `/api/audio/stream`
- Browser sends PCM via WebRTC or raw WebSocket
- Used for dashboard "push to talk" button
- Feed into ring buffer with `source_type="dashboard"`

**Acceptance:** Browser can send audio, ring buffer receives it.

### T2.7 — Menu bar tray + global hotkey
**Tier:** sonnet | **Effort:** high

`src-tauri/src/audio_hotkey.rs`:
- `tauri-plugin-global-shortcut` for `Cmd+Shift+Space`
- On hotkey: start capture, show HUD

`src-tauri/src/` tray icon setup:
- Tauri v2 `tray-icon` feature (NSStatusItem on macOS)
- Halbert icon in menu bar
- Click shows menu (Settings, Mute, Quit)

**Acceptance:** Hotkey triggers capture. Menu bar icon appears. Click opens menu.

### T2.8 — Floating HUD (VoiceCompanionPill)
**Tier:** opus | **Effort:** xhigh

`src-tauri/src/audio_hud.rs`:
- `tauri-nspanel` crate for non-stealing NSPanel
- Requires `macos-private-api` feature in Cargo.toml
- Panel floats at top of screen, doesn't steal focus from IDE/terminal
- **Caveat**: may affect App Store distribution. Document this.

`components/VoiceCompanionPill.tsx` (NEW):
- Renders in NSPanel webview
- Shows: Halbert logo, speaker badge, streaming transcript, tool calls, waveform
- Esc to dismiss, Space to pause
- Receives state via Tauri events (NOT audio data via IPC)

**Acceptance:** HUD appears on hotkey, doesn't steal focus, shows transcript. Esc dismisses.

### T2.9 — Pipeline coordinator
**Tier:** opus | **Effort:** xhigh

`halbert_core/audio/pipeline.py`:
- `AudioPipelineCoordinator` — orchestrates all ingress sources, ring buffer, dual-track processing
- Event dispatcher: emits `VoiceTurnObservation` and `AcousticEventObservation`
- State machine: idle -> listening -> recognizing -> thinking -> speaking -> idle
- SSE events for state changes (consumed by frontend aura indicator)
- Graceful degradation: if sherpa-onnx not installed, pipeline is a no-op

**Acceptance:** Integration test: mock ingress sends PCM, pipeline produces observations. Without sherpa-onnx, pipeline starts but produces no observations (no crash).

### T2.10 — Dashboard audio routes
**Tier:** sonnet | **Effort:** high

`halbert_core/dashboard/routes/audio.py` (NEW):
- `GET /api/audio/config` — load audio_config.yml
- `POST /api/audio/config` — save config
- `GET /api/audio/status` — subsystem status
- `GET /api/audio/ingress/status` — connected sources
- Register in `app.py` after vision router

**Acceptance:** Routes return correct data. Config changes take effect without restart (read-on-every-use pattern).

---

## Phase 3: Biometric Speaker Identification & Safety

### T3.1 — CAM++ speaker ID engine
**Tier:** sonnet | **Effort:** xhigh

`halbert_core/audio/speech/speaker_id.py`:
- Lazy `import sherpa_onnx`
- `SpeakerEmbeddingExtractor` — extracts 256-dim embeddings from audio
- `SpeakerEmbeddingManager` — built-in cosine similarity, multi-sample averaging
  - Use `.add(name, [emb1, emb2, ...])` for enrollment (averages samples)
  - Use `.search(embedding, threshold)` for identification
  - Use `.verify(name, embedding, threshold)` for verification
  - Use `.score(name, embedding)` for raw cosine score
- Do NOT reinvent cosine similarity — use the built-in API
- Model: `wespeaker_en_voxceleb_CAM++.onnx` (27.9MB, 256-dim)

**Acceptance:** Unit test: enroll with 3 synthetic embeddings, verify returns correct speaker. Skips without sherpa-onnx.

### T3.2 — Speaker profile store (SQLite)
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/storage/speaker_store.py`:
- SQLite table `speaker_profiles` (256-dim BLOB = 1024 bytes)
- `data_subdir("audio") / "speaker_profiles.db"`
- CRUD: enroll, update_centroid, get, list_all, delete
- Persists centroids; `SpeakerEmbeddingManager` does the math

**Acceptance:** Unit test: enroll, retrieve, update, delete. Data persists across restarts.

### T3.3 — RoleGate safety wrapper
**Tier:** opus | **Effort:** xhigh

`halbert_core/tools/role_gate.py` (NEW):
- Wraps `ToolSafetyFramework.classify()` — can only tighten, never loosen
- `ROLE_MAX_RISK` mapping: admin->critical, member->high, guest->medium, restricted->low, unknown->medium
- Unknown speaker on HIGH-risk: requires confirmation (PIN prompt in UI)
- Mirrors `_check_skill_safety` composition pattern in safety.py
- DO NOT modify `ToolSafetyFramework` itself (high blast radius)

**Acceptance:** Unit test: admin can execute HIGH, guest is blocked from HIGH, unknown requires confirmation. Base classification is never loosened.

### T3.4 — Thread speaker_role through state machine
**Tier:** opus | **Effort:** xhigh

`halbert_core/agents/state_machine.py`:
- `StateContext` gains optional `speaker_role: str = "unknown"`
- Tool execution path calls `RoleGate.classify(tool_name, args, speaker_role)` instead of bare `safety.classify()`
- Voice turn observations set `speaker_role` from `speaker_id.py` verification
- Text/chat turns default to `speaker_role="admin"` (or configurable — text chat is already authenticated)

**Acceptance:** Voice turn with guest speaker is blocked from HIGH-risk tools. Text chat still works as before.

### T3.5 — Speaker enrollment API endpoint
**Tier:** sonnet | **Effort:** high

`POST /api/audio/speakers/enroll` in `dashboard/routes/audio.py`:
- Accepts: audio data (base64), name, role
- Extracts embedding via `SpeakerEmbeddingExtractor`
- Stores via `SpeakerProfileStore.enroll()`
- Returns: speaker_id, confidence, quality_score

`POST /api/audio/speakers/{id}/test`:
- Accepts: audio data
- Extracts embedding, calls `.verify()`, returns match score

**Acceptance:** API test: enroll speaker, test verification with matching/non-matching audio.

### T3.6 — VoiceEnrollmentModal frontend
**Tier:** sonnet | **Effort:** high

`components/VoiceEnrollmentModal.tsx` (NEW):
- 3-step wizard: capture -> extract -> confirm
- Uses browser mic (WebRTC) or local mic
- Shows 256-dim centroid quality (NOT 192-dim)
- Role selector: admin/member/guest/restricted
- POSTs to `/api/audio/speakers/enroll`

**Acceptance:** User can enroll a speaker through the UI. Quality score displayed.

### T3.7 — SpeakerProfilesCard frontend
**Tier:** sonnet | **Effort:** high

`components/SpeakerProfilesCard.tsx` (NEW):
- Lists enrolled speakers from `GET /api/audio/speakers`
- Per-speaker: name, role, confidence, Edit/Test/Delete buttons
- Role selector with permission descriptions
- "Enroll New" button opens VoiceEnrollmentModal

**Acceptance:** Speakers list renders. Edit changes role. Test shows verification result. Delete removes speaker.

---

## Phase 4: Acoustic Event Detection & Music

### T4.1 — CED-tiny audio tagger
**Tier:** sonnet | **Effort:** xhigh

`halbert_core/audio/acoustic/audio_tagger.py` (NOT yamnet.py):
- Lazy `import sherpa_onnx` (or `import onnxruntime`)
- CED-tiny ONNX or Zipformer-small-audio-tagging-int8
- `classify(pcm_1s_window) -> list[(class_label, confidence)]`
- Energy floor gate: bypass when ambient energy < -45dB (saves CPU)
- Check interval: every 2s (configurable)

**Acceptance:** Unit test: synthetic alarm-like audio returns alarm class. Silence returns empty. Skips without deps.

### T4.2 — Anomaly detector + label mapping
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/acoustic/anomaly_detector.py`:
- Maps CED/Zipformer output to anomaly severity (0-3)
- T3/T4 alarm pattern detection (temporal pattern matching, not just class)
- Glass break, water leak, mechanical whine classification
- `label_map.py` — CED class labels to human-readable names

`halbert_core/findings/detectors/acoustic_anomaly.py` (NEW):
- Follows `dropin_conflicts.py` pattern
- `detect()` returns `List[Finding]` with Four-Whys annotations
- Registered in `DetectorRunner.__init__`
- Add to `_EVENT_CATEGORY`: `"acoustic_anomaly": "acoustic"`

**Acceptance:** Anomaly produces Finding with correct severity, why_now/care/so/trust. Finding flows through gate and SSE.

### T4.3 — SystemEventMapper integration
**Tier:** sonnet | **Effort:** med

`halbert_core/integrations/system_event_mapper.py`:
- Add `"acoustic_anomaly"` handler in `_apply_event_to_cognition()`
- Mirror `"security_anomaly"` pattern (lines 159-171):
  - `cognition.worries.add_worry(category="acoustic_safety", ...)`
  - `cognition.emotional_state.add_emotion(FEAR, ...)`
- `anomaly_detector.py` calls `mapper.add_event("acoustic_anomaly", severity, source, detail)`

**Acceptance:** Acoustic anomaly produces cognitive worry + fear emotion on next cognitive tick.

### T4.4 — Music fingerprinting (network-required)
**Tier:** sonnet | **Effort:** high

`halbert_core/audio/acoustic/music_fingerprint.py`:
- Lazy `import pyacoustid` / `import chromaprint`
- Generate fingerprint from PCM (offline-capable)
- Lookup via AcoustID web API (REQUIRES NETWORK + API key)
- In offline/sovereign mode: fingerprint only, no lookup
- Document network requirement in config UI

**Acceptance:** With network: song identified. Without network: fingerprint generated, lookup skipped, logged as "fingerprinted (offline)".

### T4.5 — AcousticAnomalyModule frontend
**Tier:** sonnet | **Effort:** high

`components/modules/AcousticAnomalyModule.tsx` (NEW):
- Register in `modules/registry.py` as `acoustic-anomaly`
- Add to `ModuleRenderer.tsx` lazy registry
- Shows: sound class (human-readable from label_map), location, confidence, dB
- Action buttons: View Camera, Mute/False Alarm, Call Emergency
- Data from `/api/audio/anomalies`

**Acceptance:** Module renders in conversation when agent invokes it. Shows anomaly details.

### T4.6 — Acoustic aura indicator frontend
**Tier:** sonnet | **Effort:** high

`components/AcousticAuraIndicator.tsx` (NEW):
- SVG-based aura animation (no emoji)
- States: idle (breathing), listening (waveform), recognized (badge), thinking (pulse), speaking (sync waveform)
- Polls `/api/audio/status` or reads from existing SSE (`/api/being/events`)
- Placed in `Layout.tsx` header

**Acceptance:** Aura renders in header. State transitions visible when audio state changes.

---

## Phase 5: Cloud Omni Live Duplex

### T5.1 — Gemini Live API bridge
**Tier:** opus | **Effort:** max

`halbert_core/audio/live_bridge.py`:
- WebSocket connection to Gemini Multimodal Live API
- Bidirectional: 16kHz PCM in, 24kHz PCM out
- VAD + barge-in handled by Gemini Live natively
- Latency: ~200-370ms (NOT guaranteed 220ms — treat as target)
- Fallback to local pipeline on connection failure

**Acceptance:** Voice turn via Gemini Live returns response. Barge-in works. Fallback to local on disconnect.

### T5.2 — OpenAI Realtime API bridge (optional)
**Tier:** sonnet | **Effort:** xhigh

`halbert_core/audio/live_bridge_openai.py`:
- WebSocket to OpenAI Realtime API
- Same interface as Gemini bridge
- Configurable which cloud provider to use

**Acceptance:** Voice turn via OpenAI Realtime returns response.

### T5.3 — Cloud vs Local toggle UI
**Tier:** sonnet | **Effort:** high

In `AudioSettingsTab` (Surface 5):
- Radio: Local Sovereign (offline) vs Cloud Omni Live
- Cloud provider selector: Gemini / OpenAI
- Warning: "Cloud mode sends audio to external servers"
- Persisted in `audio_config.yml`

**Acceptance:** Toggle switches between local and cloud. Setting persists.

### T5.4 — Screen + audio multimodal pairing
**Tier:** opus | **Effort:** xhigh

Combine existing vision capture (`vision_tools.py`) with live audio stream:
- Send both screen frames and mic audio to Gemini Live
- Agent can see screen and hear voice simultaneously
- Requires both vision and audio subsystems enabled

**Acceptance:** Agent responds to "what's on my screen right now?" while also hearing voice commands.

---

## Cross-cutting tasks (not phase-specific)

### X1 — Update original handoff with review link
**Tier:** haiku | **Effort:** med

Add header to original `HANDOFF-AUDIO-AI-ARCHITECTURE-AND-UX-2026-08-29.md`:
```
> **STATUS: SUPERSEDED** — See `.handoff/audio/00-REVIEW-SUMMARY.md` for
> corrected architecture after technical scrutiny (2026-08-29).
```

### X2 — Update MASTER-TODO.md
**Tier:** haiku | **Effort:** med

Add audio work reference to `MASTER-TODO.md` with status "Plan complete, ready for implementation."

### X3 — Research suite correction notes
**Tier:** haiku | **Effort:** med

Add correction notes to `audio-research/02-GITHUB-CITATIONS-AND-PATTERNS.md`:
- Fix webrtc-audio-processing URL (alona-d -> tonarino)
- Note Piper repo archived -> OHF-Voice/piper1-gpl
- Note ECAPA-TDNN not in sherpa-onnx, use CAM++
- Note YAMNet not in sherpa-onnx, use CED-tiny
