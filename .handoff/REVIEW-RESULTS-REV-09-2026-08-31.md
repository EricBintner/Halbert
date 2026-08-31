# REV-09 Review Results — Auditory Cortex & Multimodal Audio AI Pipeline

**Review:** REV-09 (packet `.handoff/REVIEW-PACKET-09-AUDITORY-CORTEX-AND-AUDIO-PIPELINE.md`, 2026-08-29)
**Reviewed:** 2026-08-31, branch `worktree-central-todo-batches` (post-TASK-07: commits 58adce12, 149b3e75; post-Phase-2 modality-voice merge)
**Reviewer:** GLM-5.3, adversarial pass with end-to-end verification
**Method:** full read of all target files; call-site tracing (grep-verified, no assumed callers); read-only test runs via `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py`; import-without-extras verification (Python 3.10.9 venv, sherpa-onnx NOT installed)

**Tally:** 12 CONFIRMED · 3 PLAUSIBLE · 0 unsubstantiated retained. 4 of 5 packet items RESOLVED (1 partially).

---

## 1. Verdicts per area

| Area | Verdict |
|---|---|
| **Wyoming agent** (`integrations/wyoming_agent.py`) | **FIXES VERIFIED, NEW RISK FOUND.** All three packet CRITICALs are genuinely fixed (speaker_role, session UUID, markdown stripper — each traced and covered by `test_task07_voice_turn_plumbing.py`). But the server is unauthenticated, enabled by default, and LAN-bound; its protocol is non-canonical; and it drives the shared agent from a second event loop. |
| **RoleGate + tool execution** (`tools/role_gate.py`, `tools/executor.py`, `agents/state_machine.py`) | **INVARIANT HOLDS.** Verified chain: wyoming → `process(speaker_role="unknown")` → `StateContext.speaker_role` → `_run_tool_streaming` → `executor.execute(speaker_role=...)` → `role_gate.classify`. Unknown/guest can never execute HIGH without confirmation and never CRITICAL (executor blocks CRITICAL unconditionally; `test_role_gate.py` passes). Residual: MEDIUM-risk tools are open to unidentified speakers *by design*, which finding F1 turns into a LAN exposure. |
| **Audio pipeline** (`audio/pipeline.py`, `buffer.py`, `speech/*`, `ingress/*`) | **NON-FUNCTIONAL CORE.** The local speech track can never trigger (VAD frame-size mismatch, F3); speaker enrollment never reaches the runtime matcher (F4); and nothing in production ever constructs `AudioPipelineCoordinator` (grep: zero instantiation sites outside the module itself). The engine code is import-clean and lazy — the subtractive contract holds — but the feature is dead end-to-end. |
| **Modality wiring** (`modality_wiring.py`, `voice_backend.py`, `voice_auth_gate.py`, `channel_capability.py`) | **GLUE SOUND, CHAIN DEAD.** Singletons are lazy and degrade to text-only correctly (17/17 modules import without sherpa-onnx). But modality can never resolve VOICE in production (F6): the channel capability queries a nonexistent `get_audio_pipeline`, `set_wyoming_active` has no caller, and `build_modality_context`'s `speaker_role` parameter is dead code. |
| **TTS / barge-in** (`tts_engine.py`, `barge_in.py`, `voice_backend.py`) | **CONTRACT FALSE.** Barge-in "aborts generation" — it cannot: the full waveform is synthesized before the first chunk is yielded (F7). Additionally `SpeechResult` mislabels raw PCM as WAV at a wrong sample rate (F9). |
| **Rust AEC** (`src-tauri`) | **UNRESOLVED.** No `audio_capture.rs` exists (`src-tauri/src/` holds only `lib.rs`, `main.rs`) — the packet's loopback-AEC item stands as-is. |

**Sanity checks run:** `wt_pytest.py test_audio_buffer.py test_role_gate.py test_task07_voice_turn_plumbing.py test_modality_voice_phase2.py` → **85 passed**. All 17 audio/integration modules import cleanly without sherpa-onnx installed (packet directive §6.1 verified). The findings below are all in code paths those tests do not reach.

---

## 2. Findings (most severe first)

### F1 — CONFIRMED (HIGH, security) — Unauthenticated Wyoming TCP server, enabled by default, exposes MEDIUM-risk tool execution to the LAN
`halbert_core/halbert_core/integrations/wyoming_agent.py:37,62,245-277`; `halbert_core/halbert_core/dashboard/app.py:682-699`; cap chain `tools/safety.py:175-208`, `tools/role_gate.py:43-49`

`WYOMING_ENABLED` defaults to `"1"` and the server binds `0.0.0.0:10400` (started 7 s after boot in a background thread). Any host on the network can open TCP, send `{"type":"transcript","data":{"text":"..."}}\n`, and receive agent responses. The TASK-07 fix correctly caps such turns at `speaker_role="unknown"` — but the RoleGate cap for unknown is MEDIUM *without confirmation* (`ROLE_MAX_RISK["unknown"]="medium"`), and the executor's only hard gates are CRITICAL (block) and HIGH (confirm). MEDIUM-classified commands per the safety rules include `rm <file>`, `mv`, `cp`, `chmod`, `chown`, and `> overwrite` — all executable by an anonymous LAN peer, with system information returned in the response.

**Scenario:** an attacker on the home Wi-Fi sends `{"type":"transcript","data":{"text":"Run: rm -f ~/.ssh/authorized_keys"}}` → `rm\s+(-[rf]+\s+)+` is HIGH → confirmation required (fails closed). But `{"text":"Run: mv ~/documents /tmp/wiped"}` → MEDIUM → executes immediately.

**Fix:** default `WYOMING_ENABLED=0`; require a shared token in the transcript frame (or bind `127.0.0.1` when no token is configured); consider requiring confirmation for MEDIUM on `unknown` voice turns.

### F2 — CONFIRMED (HIGH, race) — Wyoming turns run on a second event loop; the per-loop turn lock lets turns interleave and clobber shared agent state
`halbert_core/halbert_core/dashboard/app.py:686-697`; `halbert_core/halbert_core/agents/state_machine.py:307-336`; `halbert_core/halbert_core/integrations/wyoming_agent.py:227`

`app.py` starts the Wyoming agent with `asyncio.new_event_loop()` in a background thread; its client handlers run on that loop. `wyoming_agent._get_agent()` returns the *same singleton* `AgentStateMachine` the dashboard serves. The `turn_lock` property deliberately builds a **fresh `asyncio.Lock` per event loop** (`if self._turn_lock is None or self._turn_lock_loop is not loop`). So a dashboard turn and a Wyoming turn hold *different locks simultaneously* — the "one turn at a time" invariant (spec §12) is void across loops. Both turns then write the single mutable `self.ctx`, `self.current_state`, and `_apply_generation_params` on the one shared LLM adapter — exactly the clobbering the lock's own docstring says the lock exists to prevent.

**Scenario:** a dashboard user's turn is in RESPONDING streaming a response; a satellite transcript arrives on the Wyoming thread; the voice turn replaces `self.ctx` mid-flight — the dashboard user's reply is assembled from the voice turn's observations (or vice versa), and the LLM adapter's generation params cross-contaminate. Worse, `pending_confirmation` lives on `self.ctx`: a confirmation submitted on one channel can be matched against the other turn's action.

**Fix:** funnel Wyoming turns onto the app's main loop (`asyncio.run_coroutine_threadsafe` from the wyoming loop, or have the wyoming thread only enqueue transcripts), or construct a dedicated `AgentStateMachine` for the voice channel.

### F3 — CONFIRMED (HIGH, functional) — VAD frame-size mismatch: `is_speech` always returns False — wake, speech turns, and VAD barge-in can never trigger
`halbert_core/halbert_core/audio/pipeline.py:292,310,315,332`; `halbert_core/halbert_core/audio/speech/vad.py:31,164-166`

The speech-track loop slices exactly 960-byte frames (`frame_target = 960  # 30ms at 16kHz, 16-bit = 960 bytes` → 480 samples), but Silero VAD operates on 512-sample windows and `VoiceActivityDetector.is_speech` begins:

```python
n = len(pcm_chunk) // 2
if n < SILERO_WINDOW_SAMPLES:   # 512
    return False
```

480 < 512 on every frame, so `is_speech` is permanently False. Consequences: state never leaves IDLE, `_process_speech_segment` (ASR + speaker ID) is unreachable, and the TASK-07 VAD barge-in branch (`elif is_speech and self._state == AudioState.SPEAKING`) can never fire. No test exercises the frame sizing (`test_audio_buffer.py` has no `_speech_track`/`frame_target` coverage), which is why 85 tests pass over a dead loop.

Two secondary defects compound it (both latent until the size is fixed): (a) `is_speech` calls `self._detector.flush()` per frame (vad.py:175), destroying the segment-assembly state the sherpa-onnx VAD needs; (b) sherpa-onnx emits segments only after trailing silence ≥ `min_silence_duration` (500 ms), so a segment-level gate is a *delayed* detector, not the per-frame gate the pipeline assumes — wake detection on the trigger frame (F12) and "VAD alone triggers" semantics both need rethinking against the real API.

**Fix:** slice 1024-byte (512-sample) frames; stop calling `flush()` per frame; keep one long-lived segment stream and map segment start/end to state transitions.

### F4 — CONFIRMED (HIGH, functional/security) — Enrolled voiceprints never reach the runtime matcher: speaker ID is non-functional and the verify endpoint always reports False
`halbert_core/halbert_core/dashboard/routes/audio.py:180-193,222`; `halbert_core/halbert_core/audio/speech/speaker_id.py:163,205,243`; zero loader anywhere (grep verified: no production caller of `SpeakerIdentifier.enroll`, no `manager.add` outside it, no code reading `embedding_as_list()`).

The enrollment route persists the embedding to SQLite via `SpeakerProfileStore.enroll(...)` — but never calls `SpeakerIdentifier.enroll(...)`, the only code that does `SpeakerEmbeddingManager.add()`. Nothing at pipeline startup (or anywhere else) loads stored profiles into the manager. Therefore at runtime `manager.search()` always finds nothing (`identify()` → None → every speaker "unknown"), and `/audio/speakers/{id}/test` → `verify()` hits `speaker_id not in self._manager` → always `(False, 0.0)` — **the test endpoint reports a false negative even for the correct enrolled voice.**

This fails *safe* (everyone unknown → RoleGate tightens), but it defeats the entire feature — including admin voice authentication — and the always-False test endpoint will erode user trust in enrollment. It also masks F11 (the role-override path is currently unreachable only because the manager is always empty).

**Fix:** on first `SpeakerIdentifier` construction (or pipeline start), iterate `SpeakerProfileStore.list_all()` and `manager.add(speaker_id, [profile.embedding_as_list()])` for each profile; delete should call `manager.remove`.

### F5 — CONFIRMED (HIGH, wiring) — Modality can never resolve to VOICE in production: the Phase 2 voice-out chain is dead end-to-end
`halbert_core/halbert_core/integrations/channel_capability.py:141-153` (imports `get_audio_pipeline` — **that function does not exist** in `dashboard/routes/audio.py`, verified by grep: the import always fails → pipeline None); `channel_capability.py:159` (`set_wyoming_active` — zero production callers); `integrations/app_seam.py:417-418` (seam constructs `HalbertChannelCapability()` with defaults: desktop, no wyoming, no pipeline).

With `wyoming_active=False` and no pipeline, `current_modality()` always returns `"text"`, `has_speaker()` False — so the engine's resolver always recommends TEXT, `should_speak()` is False, and `speech_segment` SSE events are never emitted (`state_machine.py:2939`). The tests pass only because `test_modality_voice_phase2.py` constructs the capability directly with `wyoming_active=True`. Compounding it: `build_modality_context`'s `speaker_role` parameter is **dead code** — never read in the body (`modality_wiring.py:247-324`), and no caller passes `audio_features` (`state_machine.py:2707-2710` passes only `user_query` and `speaker_role`), so even the biometric-risk-hobble path is never exercised. Finally, the only frontend consumer of `speechSegments` is `VoiceCompanionPill.tsx` — a 77-line display pill with **no audio playback code**; nothing anywhere synthesizes/plays the spoken response.

**Scenario:** a user enables Wyoming + TTS, speaks to a satellite, the turn is transcribed and answered — always as TEXT modality; no `speech_segment` ever reaches the frontend; nothing speaks.

**Fix:** make the wiring layer call `set_wyoming_active(True/False)` around each Wyoming turn (or pass a per-turn channel capability into `build_modality_context`); thread `ctx.speaker_role` into the `SpeakerIdentity`/context; add a real playback sink (browser SpeechSynthesis or the Piper/HA path).

### F6 — CONFIRMED (MEDIUM-HIGH, security, latent) — Enrollment-assigned role overrides the biometric confidence bands: a 0.75 match yields full admin voice access
`halbert_core/halbert_core/integrations/voice_auth_gate.py:156-159` (`role = profile.role or role`)

The engine's design (spec 5.9) classifies role from CAM++ cosine-similarity bands: admin ≥ 0.82, member ≥ 0.70, guest ≥ 0.60. But once a profile matches (search threshold 0.75 — the config default), the store's enrollment-time role **replaces** the band classification. A replayed recording of the admin, or a household member with a similar voice, matching at 0.75–0.81 — below the admin band — still authenticates as role `"admin"` → `ROLE_MAX_RISK["admin"]="critical"` → full privileged voice access with no PIN and no liveness check.

Currently latent only because of F4 (the matcher is empty); it becomes live the moment F4 is fixed. **Fix:** accept `profile.role` only when `confidence` meets the band threshold for that role; require a PIN challenge for admin-band actions regardless of profile (the `voice_pin_challenged` mechanism exists but is only set for the guest band).

### F7 — CONFIRMED (MEDIUM, functional) — Barge-in cannot abort synthesis: the full waveform is generated before the first chunk is yielded
`halbert_core/halbert_core/audio/speech/tts_engine.py:109-140`

`synthesize()` awaits `loop.run_in_executor(None, _generate)` — the *entire* utterance — before entering the chunk loop where the cancel token is checked (`if cancel_token is not None and cancel_token.is_set(): return`). The docstring's "aborts generation when the user interrupts" is false: generation always completes; only the (already-complete) chunk *streaming* is cut short. The <120/150 ms barge-in budget (spec B5, barge_in.py:15) cannot be met for generation — for a long reply the user waits through full VITS synthesis before hearing anything, and the interrupting user's cancellation saves no compute. (Streaming playback is likewise fake: first chunk arrives only after total synthesis.)

**Fix:** synthesize sentence-by-sentence (per-sentence executor calls with token checks between), or poll a cancellation flag inside a chunked generate loop.

### F8 — CONFIRMED (MEDIUM, functional) — Voice HIGH-risk confirmation flow is unreachable: the satellite user hears a non-sequitur
`halbert_core/halbert_core/agents/state_machine.py:2437-2466`; `halbert_core/halbert_core/integrations/wyoming_agent.py:150,179-195,122`

When an unknown voice speaker triggers a HIGH-risk tool, the turn parks in AWAITING_CONFIRMATION with `pending_confirmation` stored on the per-turn context — but the Wyoming agent mints a **fresh session UUID per turn** (`wyoming-{uuid4}`) and its collector only accumulates `response_chunk` events, ignoring `tool_confirmation_required`. No response text is produced, so the user hears "I'm not sure how to help with that." (line 122) and the pending confirmation is orphaned — it can never be satisfied from the voice channel (a new turn is a new session).

Fails closed (safe), but the confirmation UX is broken and misleading: the user has no idea the action needs approval. **Fix:** when a voice turn yields `tool_confirmation_required`, synthesize the confirmation message as the response ("That needs confirmation — say 'confirm' to proceed"), key the pending confirmation to `conversation_id` (which is already threaded), and route a "confirm" transcript to it.

### F9 — CONFIRMED (MEDIUM, correctness) — SpeechResult mislabels raw PCM as "wav" and always claims 16 kHz regardless of the voice model's real rate
`halbert_core/halbert_core/integrations/voice_backend.py:109,142-145,150`; `halbert_core/halbert_core/audio/speech/tts_engine.py:169`

`sample_rate = getattr(tts, "_sample_rate", None) or 16000` — but `PiperTTS` never sets any `_sample_rate` attribute (verified: no assignment anywhere in the class), so the fallback 16000 is *always* used, while Piper voices commonly output 22050 Hz (the engine's own comment admits "The actual rate is in the generated audio object"; `PiperTTS.sample_rate` likewise returns the hardcoded 16000). The bytes are headerless raw PCM (that is all `synthesize()` yields), yet the result is labeled `format="wav"`. Any consumer honoring `format`/`sample_rate` (engine playback, HA, a browser WAV decoder) mis-parses or mis-pitches the audio (22050 Hz data played at 16 kHz ≈ 27% slow/flat).

**Fix:** return the true rate from generation (`audio.sample_rate` is already produced by `_generate`) — e.g., make `synthesize()` yield `(pcm_chunk, sample_rate)` or set `tts._sample_rate` inside `_generate`; emit a real WAV header or label the format `pcm_s16le`.

### F10 — CONFIRMED (MEDIUM, protocol) — The Wyoming agent speaks a non-canonical JSONL variant; real Wyoming/HA clients cannot interoperate
`halbert_core/halbert_core/integrations/wyoming_agent.py:245-305`

The module docstring claims "HA's native Wyoming integration in Settings → Voice Assistants handles the configuration", but the agent: (a) parses with bare `readline()` — canonical frames carry `payload_length`-prefixed binary payloads after the header, so an audio-chunk's PCM lands on the next readline and spews "Invalid JSON from Wyoming client" warnings while desynchronizing the stream; (b) answers `describe` with another `describe` (the canonical handshake expects an `info` event); (c) emits a `response` event type that does not exist in the Wyoming protocol. `audio/ingress/wyoming_ingress.py:5-14` documents this exact incompatibility and implements the correct reader — which the agent does not use.

**Fix:** route HA connections through the canonical-framed reader (reuse `read_wyoming_frame`/`write_wyoming_frame` in the agent), and implement `info`/`synthesize` if HA is meant to connect natively.

### F11 — CONFIRMED (LOW-MEDIUM, functional) — Wake-word detection runs on the wrong audio: the single frame that triggered VAD, seconds after the word was spoken
`halbert_core/halbert_core/audio/pipeline.py:317-319`

On VAD trigger, `self._wake_word.detect(frame)` inspects only the current 30 ms frame. Even with F3 fixed, sherpa-onnx emits speech segments after trailing silence (≥ 500 ms), so the trigger frame is post-utterance; with VAD-alone triggering the trigger frame is the *first* speech frame, at which point the wake word is still being spoken. In both cases the phrase "Hey Halbert" is not in the inspected frame. Wake-word gating therefore can never work as written (today it is masked because the code falls back to `wake_detected = True` when no model is available).

**Fix:** run wake detection over a rolling feature buffer (openWakeWord is stateful across 128-sample frames — feed it every frame, not just trigger frames), and trigger on wake-word *state*, with VAD as a gate.

### F12 — CONFIRMED (LOW, latent) — Port collision: wyoming_agent and WyomingIngress both default to 0.0.0.0:10400
`halbert_core/halbert_core/integrations/wyoming_agent.py:38`; `halbert_core/halbert_core/audio/config.py:53`

The agent (started from `app.py`) and the pipeline's ingress both bind the same default port; whichever starts second gets EADDRINUSE, logged as a generic "Wyoming ingress failed" error. Latent today only because `AudioPipelineCoordinator` is never started (F5/F13); it bites the moment the pipeline is wired. **Fix:** separate defaults (e.g., agent 10400, ingress 10401) or a startup-time port check.

### F13 — CONFIRMED (LOW, perf) — Blocking ONNX inference and per-sample Python loops on the event loop
`halbert_core/halbert_core/audio/pipeline.py:351` (`transcribe_chunk` — a synchronous full decode of a 10-second buffer — called directly on the loop, no executor), `pipeline.py:432` (`_audio_tagger.classify`, same), `audio/buffer.py:79-83` (per-sample Python write loop, 16k iterations/s/stream under an `asyncio.Lock`), `voice_backend.py:215-225` (`_apply_volume_gain` unpacks whole waveforms into Python int lists).

When the pipeline runs alongside the dashboard/Wyoming servers on one loop, each turn stalls every other asyncio task (SSE streams, the Wyoming socket, the UI) for the duration of the inference — plausibly hundreds of ms to seconds per 10 s window. `tts_engine.synthesize` already demonstrates the right pattern (`run_in_executor`). **Fix:** executor-wrap ASR/tagger calls; write buffer chunks with slice assignment / `array.frombytes`-style bulk ops.

### F14 — PLAUSIBLE (LOW, robustness) — One malformed Wyoming header drops the whole satellite connection mid-stream
`halbert_core/halbert_core/audio/ingress/wyoming_ingress.py:67-70,178-179`

`read_wyoming_frame` returns None on a bad JSON header, and `_handle_client` treats None as clean EOF and closes the connection. A single corrupt/desynchronized line (e.g., after the F10-style framing mismatch, or a partial write) terminates the session mid-utterance instead of resynchronizing. (In the wyoming_agent the same condition merely `continue`s — the ingress is stricter than the agent.)

### F15 — PLAUSIBLE (LOW, unverifiable) — `speaker_id not in self._manager` may raise TypeError
`halbert_core/halbert_core/audio/speech/speaker_id.py:243` — `SpeakerEmbeddingManager.__contains__` support cannot be verified (sherpa-onnx not installed in the review venv). If absent, `verify()` raises TypeError before its guard; callers catch broadly (`identify/verify` wrapped in `except Exception` upstream), so impact is a false "verification failed".

---

## 3. Packet claims now RESOLVED (packet §5 predates TASK-07 / Phase 2)

1. **Wyoming speaker_role="admin" default — RESOLVED.** `wyoming_agent.py:179` passes `speaker_role="unknown"`; verified through the full chain to `RoleGate.classify`; tested (`test_speaker_role_is_unknown_not_admin`, `test_process_defaults_to_dashboard_admin`). Note the exposure is *reduced*, not eliminated (F1).
2. **Markdown stripper — RESOLVED.** `_strip_markdown_for_speech()` (`wyoming_agent.py:424-472`) with a no-engine regex fallback; applied in `proactive_speak` (line 387) and the demux path handles response text.
3. **Session collision — RESOLVED.** Per-turn UUID `wyoming-{uuid4().hex[:12]}` (line 150), conversation_id threaded to `thread_id`; tested.
4. **Barge-in handler wiring — PARTIALLY RESOLVED.** `BargeInHandler` is now instantiated and connected inside `AudioPipelineCoordinator` (pipeline.py:115-119, 526-573), closing the packet's literal gap. However the coordinator itself has **zero production instantiation sites** (grep-verified), so barge-in remains unreachable end-to-end — and even if started, F3 (VAD never fires) and F7 (generation not cancellable) both break it.
5. **Rust AEC — UNRESOLVED.** No `audio_capture.rs` in `src-tauri/src/`.

Additionally resolved relative to the packet: ThreadManager injection (149b3e75), Python 3.10 compatibility (`wait_for` instead of `asyncio.timeout`, verified on 3.10.9), pronunciation lexicon + modality-aware prompt builder + `modality_resolved`/`speech_segment` SSE events (Phase 2) are all present and tested at the unit level.

---

## 4. Test-coverage gaps

- No test drives `_speech_track_loop` with real frame sizes (F3 passed silently for this reason).
- No test covers enrollment → runtime identification (F4: every layer unit-tested in isolation; the seam between `SpeakerProfileStore` and `SpeakerEmbeddingManager` is untested).
- `test_modality_voice_phase2.py` constructs `HalbertChannelCapability` directly with `wyoming_active=True` — the production wiring that would set that flag has no test because it does not exist (F5).
- No test runs the Wyoming agent's turns on a second event loop against the shared machine (F2).