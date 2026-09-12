# PKT-VMV-1 — Wake-word correctness on macOS ARM64

Tier: **opus**   Milestone: **M4**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**VMV-1** — Wake-word correctness on macOS ARM64.

## 2. User problem

The wake word never fires on macOS ARM64, which is Halbert's target platform — so the voice surface is hotkey/VAD-only in practice and every stray speech-like noise opens a turn. Three compounding defects, all verified in tree:

1. Dead detector backend. `halbert_core/halbert_core/audio/speech/wake_word.py` wraps openWakeWord with `inference_framework="onnx"` (wake_word.py:83-86). openWakeWord's ONNX embedding model scores ~0 on Apple Silicon, so `WakeWordSpotter.is_available()` returns True (the model file loads), `detect()` runs every frame, and the score never crosses `DEFAULT_THRESHOLD = 0.5`. The detector arms cleanly and never fires. The failure is silent: pipeline.py:262-263 only logs "model not found" when `is_available()` is False, which never happens — the model loads fine, it just never scores.

2. Frame size is wrong for the detector. `pipeline.py:347` sets `frame_target = SILERO_WINDOW_SAMPLES * 2` = 1024 bytes = 512 samples (32 ms), sized for the VAD (the R9-F03/U2-14 fix that revived the speech path). The same 512-sample frame is then handed verbatim to `self._wake_word.detect(frame)` at pipeline.py:374 — but openWakeWord expects 1280-sample (80 ms) frames. Halbert feeds the detector a frame 2.5x too short. (Note: the wake_word.py:39 comment claims "openWakeWord uses 128-sample frames at 16kHz (8ms)" — that comment is wrong and must be reconciled against the 1280-sample accumulator this unit adds; the registry note flags exactly this discrepancy.)

3. No listener hardening. There is no post-detection cooldown (one wake can retrigger on the tail of its own phrase), no confirmation-frame debounce (a single noisy frame above threshold opens a turn), no dead-mic detection (an ingress adapter that stops delivering chunks is indistinguishable from silence — `_ingress_to_buffer_loop` at pipeline.py:307 just sleeps 10 ms and loops), and no reset-on-resume: after a laptop sleep the ring buffer and `_chunk_queue` hold stale pre-sleep audio, so the first post-resume frames are analyzed against minutes-old context — which is also the pipeline-side root cause of the A09-G2 duplicate-transcript defect flagged in the deep-eval.

The platform probe is also missing: nothing checks Darwin+arm64 before arming the ONNX path, so the broken configuration presents as "working but quiet" instead of a flagged, measured state.

## 3. What to build

All work confined to `halbert_core/halbert_core/audio/speech/wake_word.py` and `halbert_core/halbert_core/audio/pipeline.py`, plus new tests under `halbert_core/tests/`. No new hard dependency: sherpa-onnx is already an optional extra (`audio-inference = ["sherpa-onnx>=1.10", "onnxruntime>=1.16"]`, pyproject.toml:117-120), already used by asr_engine/tts_engine/audio_tagger/speaker_id. The Haloysius subtractive contract is untouched.

1. Platform capability probe (wake_word.py): at `_ensure_initialized` time, check `sys.platform == "darwin"` and `platform.machine() == "arm64"`. On that combination do NOT arm the openWakeWord ONNX path — log a single measured line ("openWakeWord ONNX scores ~0 on macOS ARM64; openWakeWord backend disabled") and either fall through to the sherpa-onnx KWS backend (item 2) or mark unavailable with a distinct reason string so the pipeline's "hotkey-only activation" log tells the truth. Expose the chosen backend name and the unavailability reason on the spotter (e.g. `backend` / `unavailable_reason` attributes) so `pipeline.py:636-637`'s status dict can surface them.

2. sherpa-onnx KWS backend (wake_word.py): add an open-vocabulary keyword-spotting backend using sherpa-onnx's KeywordSpotter, which BPE-tokenizes an arbitrary typed phrase at runtime — zero training, no .tflite artifact. The wake phrase is configuration data derived from `halbert_core/halbert_core/identity.py`'s name resolution (`chosen_name()` / `resolve_entity_name()`, identity.py:69/123) — i.e. the onboarding `ai_name`, never a shipped model name, never "Sovereign", never the raw hostname. Build the name-resolution path ONCE: a small helper that turns the resolved entity name into the KWS keyphrase string, reused by both this backend and any later activation-name matcher. Model files resolve via the existing `data_subdir("audio", "models", ...)` pattern already used at wake_word.py:78-80 and vad.py:87. Backend selection order on Darwin+arm64: sherpa KWS if its model files are present, else unavailable-with-reason. Keep the openWakeWord path for non-ARM64 platforms, behind the same `WakeWordSpotter` interface (`is_available()`, `detect(pcm_bytes)`, `get_scores(pcm_bytes)`) so pipeline.py's call sites (lines 260-265, 373-374) do not change shape.

3. 1280-sample accumulator (pipeline.py): decouple the VAD frame size from the wake-frame size. Keep slicing 512-sample frames for `self._vad.is_speech(frame)` (pipeline.py:365, the R9-F03 fix stays intact), but maintain a small accumulator that concatenates consecutive frames and only calls `self._wake_word.detect(...)` when >= 1280 samples (2560 bytes) have accumulated, sliding forward after each detect call. Fix the wrong comment at wake_word.py:39 (128-sample claim) to state the real 1280-sample / 80 ms requirement.

4. Cooldown + confirmation debounce (wake_word.py or pipeline.py, spotter-owned state preferred): after a positive detection, suppress further positives for a cooldown window (default ~2 s, one named constant). Require the threshold to be crossed on confirmation — either N consecutive above-threshold scores within the accumulator window or a single score above a higher "instant" threshold; one named constant each, no magic numbers inline.

5. Dead-mic detection (pipeline.py `_ingress_to_buffer_loop` and/or `_speech_track_loop`): track last-chunk-arrival time per ingress adapter. If no chunk has arrived for a bounded interval (named constant, e.g. 5 s) while `self._running` is True and at least one adapter is supposed to be delivering, set a measured dead-mic flag, surface it in the status dict at pipeline.py:636-637 (alongside the existing "wake_word" key), and log once per transition, not per loop iteration.

6. Reset-on-resume (pipeline.py): detect wall-clock jumps in the speech-track loop (compare `time.monotonic()` deltas against a bound, e.g. a loop iteration gap > 2 s implies suspend). On detection, drain `_chunk_queue`, clear `frame_buffer` and the wake accumulator, reset the spotter's cooldown/debounce state, and log one measured line. This removes the pipeline-side root cause of A09-G2 duplicate transcripts (stale pre-sleep audio re-analyzed after wake); the relay-side suppressor is explicitly out of scope (field 4).

## 4. What NOT to build

- No new trained wake-word model, no openWakeWord synthetic training pipeline, no Colab session. The wake_word.py docstring's training path (lines 5-19) is superseded by sherpa-onnx KWS; leave the docstring updated, not the pipeline built.
- No activation-name / mid-session transcript matcher (OC11-C1). The deep-eval pairs it with this unit, but it is a transcript-level concern on the ASR/output side, not the detector; the shared piece — the ai_name → phrase resolution helper — is built here once so that matcher can consume it. Where it goes: VMV-4's reshaped scope or a follow-on voice packet; call it out in the handoff note.
- No relay-side duplicate-transcript suppressor (A09-G2 relay half). This unit removes the pipeline-side root cause via reset-on-resume only. Where it goes: VMV-4 reshape, which the deep-eval explicitly pairs with VMV-1's C3.
- No persona-home wake-phrase follow-on (C4 in the backlog row: "wake phrase to persona home"). Founder-gated, default no. Where it goes: founder decision; not built.
- No shared-room rule (OC11-C20) — depends on this theme but is speaker-count logic, not detector correctness. Where it goes: VMV-4 reshape.
- No Wyoming/satellite wake handling, no changes to `ingress/wyoming_ingress.py` — remote satellites run their own KWS.
- No VAD changes. The 512-sample Silero framing (R9-F03/U2-14) is correct and stays exactly as is; only the wake path's frame accumulation changes.
- No changes to speaker_id, asr_engine, tts_engine, audio_tagger. No UI surface changes (the status dict gains keys, but no dashboard work).
- No openwakeword dependency removal from pyproject.toml — it stays as the `audio-wake-word` extra for non-ARM64 platforms. Do not touch the Haloysius two-hard-dependency contract.

## 5. Target files
- `halbert_core/halbert_core/audio/speech/wake_word.py`
- `halbert_core/halbert_core/audio/pipeline.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M, one sitting. The surface is two files plus tests. Item 1 (probe) is ~20 lines. Item 2 (sherpa KWS backend) is the bulk: sherpa-onnx is already in the tree's optional extras and used by four sibling engines, so the import/config/model-path patterns are all copyable from asr_engine.py/vad.py — the new work is the KeywordSpotter wrapper and the ai_name→keyphrase helper, roughly half a day with tests. Items 3-6 are small, mechanical, and each is one focused test: an accumulator (a bytearray and a length check), two named constants with state (cooldown/debounce), a timestamp comparison (dead-mic), and a monotonic-clock jump check with buffer drains (reset-on-resume). No async architecture changes, no new threads, no cross-module refactors. The risk is contained: `WakeWordSpotter`'s interface is unchanged, so pipeline.py:260-265 and 373-374 keep their shape, and a broken KWS model file degrades to the same "hotkey-only activation" path that exists today — the failure mode is the status quo, not a new one.

## 8. UX rationale

Halbert speaks as the computer itself, first person, grounded in measured data — this unit changes what the machine can truthfully claim, and adds no user-facing surface of its own. The user-visible deltas: (1) on macOS ARM64 the wake phrase — the onboarding name the user chose at first run — actually wakes the machine, where today it silently never does; VAD alone no longer opens every turn on any speech-like noise, so the machine stops butting into conversations not addressed to it. (2) Status/logging becomes honest: instead of "Wake word model loaded" followed by eternal quiet, the status dict (pipeline.py:636-637) reports which backend armed, or a plain reason none did ("openWakeWord scores ~0 on this Mac; keyword spotting unavailable, hotkey only"), and a dead microphone appears as a measured flag rather than ambiguous silence. (3) After the laptop wakes from sleep, the machine does not react to stale pre-sleep audio or repeat a transcript. No settings UI, no new toggles beyond the named constants, no model names anywhere on any surface (the wake phrase is the onboarding ai_name; the backend is an internal detail), no emoji, no colour work. Copy tone follows the first-person-computer rule for any log lines a user might read in diagnostics: "I can't hear my wake phrase on this Mac" style, never assistant-voice.

## 9. Acceptance criteria

1. On `sys.platform == "darwin"` + `platform.machine() == "arm64"`, the openWakeWord ONNX path is never armed; the spotter reports its backend and, if nothing is available, a truthful reason — verified by a test that monkeypatches platform and asserts the ONNX model constructor is never called.
2. When sherpa-onnx KWS model files are present, the spotter arms the KWS backend with a keyphrase derived from the resolved onboarding name (helper covered by a unit test with a stubbed `chosen_name()`), and `detect()` returns True for audio the KWS scores above threshold (synthetic/fake spotter injection acceptable for CI).
3. pipeline.py calls the wake detector only on accumulated frames of >= 1280 samples (2560 bytes at 16-bit/16 kHz) while VAD continues to receive 512-sample frames — a framing test in the style of tests/test_audio_vad_framing.py observes the exact byte lengths handed to a fake spotter and a fake VAD.
4. A second detection within the cooldown window is suppressed; a single-frame blip below the confirmation requirement does not trigger; both pass after the cooldown elapses.
5. With no chunks arriving for the dead-mic interval, the status dict's dead-mic flag is set and one log line is emitted per transition (assert via caplog count, not per-iteration spam).
6. A simulated wall-clock jump (monkeypatched `time.monotonic`) causes the chunk queue, frame buffer, wake accumulator, and cooldown state to be reset — asserted by injecting a pre-jump partial frame and verifying the post-jump detect sees only post-jump bytes.
7. The wrong "128-sample frames" comment at wake_word.py:39 is corrected.
8. Full audio test slice passes with the repo's required invocation; no regression in test_audio_vad_framing.py or test_audio_pipeline_speaker.py.

## 10. Verification (measured state, not model judgment)

Runnable, measured checks (never model judgment):

1. New unit tests, run from the repo checkout with the mandatory arm64 prefix:
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_wake_word_backend.py halbert_core/tests/test_audio_wake_framing.py -q`
   (new files; names may vary but must include: a test asserting that under mocked Darwin+arm64 the openWakeWord `Model` constructor is never called and `unavailable_reason` names the platform; a framing test asserting the wake detector receives >= 2560-byte frames while the VAD receives exactly 1024-byte frames, using fake VAD/spotter doubles injected into the pipeline the way tests/test_audio_vad_framing.py does; a cooldown/debounce test asserting the second in-window positive returns False; a reset-on-resume test asserting post-jump detect input contains zero pre-jump bytes.)

2. Regression slice — the existing audio tests must stay green:
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_audio_vad_framing.py halbert_core/tests/test_audio_pipeline_speaker.py halbert_core/tests/test_audio_buffer.py -q`
   Baseline note from project memory: main carries a known nonzero failure baseline — run the same command on the merge-base first and diff the failure sets before attributing anything to this unit.

3. Measured dead-mic flag: a test that starts `_speech_track_loop`/`_ingress_to_buffer_loop` with a fake adapter that yields nothing, advances the clock past the dead-mic interval, and asserts the status dict (the dict built at pipeline.py:636-637) carries the flag and caplog shows exactly one transition line.

4. Static guard: `grep -n "128-sample" halbert_core/halbert_core/audio/speech/wake_word.py` returns nothing (the stale comment is gone), and `grep -n "frame_target" halbert_core/halbert_core/audio/pipeline.py` shows the VAD frame constant unchanged at 512 samples while a separate wake-accumulator constant of 1280 exists.

5. Import hygiene: `arch -arm64 .venv/bin/python -c "import halbert_core.audio.speech.wake_word"` succeeds with neither openwakeword nor sherpa-onnx installed (lazy imports preserved — the module must import clean on a minimal install per the subtractive contract).

## 11. Exclusions

Dependencies: none — no other packet must land first. The unit does consume `chosen_name()`/`resolve_entity_name()` from halbert_core/halbert_core/identity.py (already on main) and the sherpa-onnx optional extra already declared at pyproject.toml:117-120.

Exclusions and where each goes:
- Relay-side duplicate-transcript suppressor (A09-G2 relay half) → VMV-4 reshape; the deep-eval (oss-pass-2/deep-eval-group2-scheduler-terminal-voice.md:329,338) pairs it with this unit's reset-on-resume, which removes only the pipeline-side root cause.
- Transcript-level activation-name matcher for mid-session address (OC11-C1) → follow-on voice packet / VMV-4 reshape; this unit builds the shared ai_name→phrase resolution helper it will consume, per the deep-eval opportunity note (line 275: "build the name-resolution path once").
- Shared-room rule (OC11-C20) → VMV-4 reshape (depends on this theme, per deep-eval line 271).
- Persona-home wake phrase (backlog row 41's C4) → founder decision, default no; not built.
- openwakeword extra removal from pyproject.toml → dropped; kept for non-ARM64 platforms.
- openWakeWord synthetic training pipeline described in the wake_word.py docstring → dropped per the deep-eval's ACCEPT reasoning (sherpa-onnx KWS is zero-training; the docstring is rewritten, the pipeline never built).
- Dashboard/status-surface rendering of the new status keys → not in this unit; the keys are added to the dict, any UI consumes them under the relevant surface packet.

Coordinate, don't duplicate: the deep-eval (line 338) notes A09-G2 pairing is the only overlap with VMV-4; no merged R-xx packet touches wake-word code, so there is nothing to re-verify against R-01/R-02/R-10 here. Test-harness traps from project memory apply: always `arch -arm64` prefix; from a worktree use `./wt_pytest.py` with the venv interpreter; baseline failures on main must be diffed before claiming regressions.

---

## OSS reference

sherpa-onnx KWS (EXISTING optional extra) — no new hard dep.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
