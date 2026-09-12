# PKT-VMV-6 — Audio footprint + capability assertions

Tier: **opus**   Milestone: **M4**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**VMV-6** — Audio footprint + capability assertions.

## 2. User problem

Every resident audio model stays loaded for the daemon's whole life. `AudioPipelineCoordinator._init_engines()` (halbert_core/halbert_core/audio/pipeline.py:238) constructs `StreamingASR`, `PiperTTS`, `SpeakerIdentifier`, `AudioTagger`, and `WakeWordSpotter` at pipeline start; each engine lazy-loads its ONNX model on first use via its own `_ensure_initialized()` (e.g. asr_engine.py:53, tts_engine.py:51, acoustic/audio_tagger.py:46) and then holds the recognizer/synthesizer object forever. On a machine that speaks for two minutes a day, several hundred MB of ASR/TTS/tagger weights sit resident for the other 23:58. Second, `has_capability()` (capabilities.py:499) is a bare boolean: every consumer that finds a capability absent writes its own refusal string, so refusal text drifts across `dashboard/routes/agent.py`, `tools/executor.py`, `skills/readiness.py` and the other ~15 call sites, and none of them state what the machine actually has versus what the operation needed — which the machine's first-person voice requires. Third, when an engine fails at runtime the only record is a `logger.warning` in `_init_engines`; `get_status()` (pipeline.py:602) reports engines as present/absent with no failure history, so the machine cannot say "this part of me stopped working, at this time, for this reason." Discovery items HM08-M1 (idle-unload watcher), OC11-M4 (declare-and-assert capability layer), OC11-M5 (durable runtime health records), and founder-gated HM08-C11 (BYO CLI STT/TTS provider slot) are the accepted remedies; verdict ACCEPT in FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md with the note "Reuse existing has_capability()."

## 3. What to build

Three ungated pieces plus one founder-gated piece (C11) that ships dark unless the founder says yes.

1) Idle-unload watcher (HM08-M1). New module halbert_core/halbert_core/audio/model_residency.py: a `ModelResidency` registry where each engine registers a `release()` callback, a monotonic `last_used` stamp, and a config `idle_unload_s` (new field on `AudioConfig` in audio/config.py, default 900, 0 disables). A single asyncio task inside `AudioPipelineCoordinator` (started in `start()`, cancelled in `stop()`) sweeps registered engines every 30s and calls `release()` on any engine idle past `idle_unload_s`. Each engine grows a paired `release()` that drops its model object and flips its initialized flag: `StreamingASR.release()` sets `self._recognizer = None; self._initialized = False` (next `_ensure_initialized()` reloads from the same paths); `PiperTTS.release()`, `SpeakerIdentifier.release()`, and `AudioTagger.release()` likewise. The invariant from the deep-eval holds: an in-flight use always holds its own reference — engines take a lightweight `_in_use` counter (context manager or explicit acquire/release around `transcribe_stream`/`synthesize`/`classify`/`identify`) and the sweeper skips engines with `_in_use > 0`. Wire `touch()` on every public use entry point. Expose residency in `get_status()` engines map: each engine reports `{"loaded": bool, "idle_s": int}` instead of bare presence, so /api/audio/status (dashboard/routes/audio.py:144) shows measured state. Pure config + lifecycle, no model involvement.

2) Declare-and-assert capability layer (OC11-M4). Extend capabilities.py, do not fork it: add `require_capabilities(op: str, required: Iterable[str]) -> None` on `CapabilityRegistry` (and a module-level convenience next to `has_capability()`), which probes the singleton, computes present/missing from `self._capabilities`, and raises a new `CapabilityUnavailable` exception carrying `op`, `required`, `missing`, `present`. One formatter produces the refusal text in the machine's first person, grounded in measured data: "I can't run {op}: this body is missing {missing} (it has {present})." Deterministic template — never a model. Migrate the audio and vision call sites first per the deep-eval: the voice pipeline entry (`AudioPipelineCoordinator.start()` asserts `CAP_AUDIO` before binding ingress), the TTS speak path (pipeline.py `speak()` asserts audio before touching `PiperTTS`), and the two known refusal-writers `tools/executor.py` and `dashboard/routes/agent.py` swap their hand-rolled strings for the exception. Also document once, in the tool-registration path, the §3.13 rule from the final backlog: a capability-gated tool whose capability is absent is omitted from the available list rather than present-and-failing — the assert layer is for the residual case where omission isn't possible. Voice/vision consumers migrate in this packet; the other ~13 `has_capability()` call sites keep working unchanged (the layer is additive) and migrate one by one in later packets. No second gate: everything routes through the existing probe registry, never `_is_home_variant`.

3) Runtime health records (OC11-M5). New module halbert_core/halbert_core/obs/health.py: a `HealthRecord` dataclass {subsystem, state (ok|failed|quarantined), since (ISO-8601), reason, last_error} persisted as JSON lines in a new file under the obs data dir (new record kind, no migration, old files untouched per no-users-no-legacy). A module-level `record_failure(subsystem, reason, exc)` / `record_ok(subsystem)` pair with an in-process map plus append-only durable log; expiry of a quarantine is process liveness (in-process map cleared on boot, the durable log is history). Replace the bare `logger.warning(f"ASR init failed: {e}")` calls in `_init_engines()` with `record_failure("audio.asr", "init", e)` etc., so `get_status()` can read the health map and report per-engine `{loaded, idle_s, health: {state, since, reason}}`. The dashboard status endpoint then answers "this part of me is not working, since when, why" with measured data. This is the seam SCHED-P3's failure containment and TT-03's admission checks will reuse later — build it general, consume it in audio first.

4) BYO CLI STT/TTS slot (HM08-C11 — founder decision 4, recommended yes; ship dark). If ratified: two new optional config blocks on `AudioConfig` (`stt_command`, `tts_command` as shell templates with `{wav_path}` / `{text}` placeholders), a `CommandSTT`/`CommandTTS` engine pair implementing the same interface as `StreamingASR`/`PiperTTS`, executed exclusively through the existing RoleGate + safety pipeline in tools/role_gate.py — never a bare subprocess.run. Halbert code names no vendor or model; the config file declares the command (connection slots, not model menus). Off by default; if either block is present it overrides the sherpa-onnx engine for that direction and registers with the residency watcher like any other engine.

## 4. What NOT to build

- HM08-M2 (unbounded spill file in execute-code output) — re-homed per section_voice-media-vision.md to the terminal-tools packet carrying A04; it touches tools/executor.py spill handling, not audio. Owner: the TT-01/A04 packet.
- OC11-M6 — re-homed to a memory packet per the same section.
- HM12-C6 and HM12-C2 (iMessage channel via BlueBubbles-style helper) — held with no packet pending founder decision 2; do not build in this packet.
- Migrating the ~13 non-audio has_capability() consumers (web/search_config.py, dashboard/routes/llm.py, model/tier_router.py, skills/readiness.py, etc.) to require_capabilities — the layer is additive; only audio/vision and the two refusal-writers (tools/executor.py, dashboard/routes/agent.py) migrate here. The rest is follow-up, one consumer per packet.
- Any new capability probe, preset change, or a second feature gate — capabilities.py's probe order (override → probe → preset) is untouched; CAP_AUDIO's `_probe_audio()` stays presence-only.
- Network-probing capabilities or remote health aggregation — probes stay cheap/local per the capabilities.py module contract; health records are local process-liveness only.
- Model quantization, swapping sherpa-onnx for another runtime, or changing model file layouts — release() reloads from the same paths _ensure_initialized already computes.
- Any UI beyond what /api/audio/status already serves — no new dashboard page; the status payload grows fields, the frontend's existing rendering decides what to show (a dashboard surfacing pass is a separate surface packet).
- The OC11-C8 output-loopback verifier and OC18 typing-keepalive stack — explicitly do-not-lift in the section file.

## 5. Target files
- `halbert_core/halbert_core/audio/`
- `halbert_core/halbert_core/capabilities.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S (small) matches the verdict table (FINAL-CRITICAL-DISCOVERY-BACKLOG line 463 sizes VMV-6 as S). The engines already have the exact lifecycle seam needed: each lazy-loads behind `_ensure_initialized()` guarded by an `_initialized` flag, so release() is a flag flip plus dropping one object reference — no engine redesign. The pipeline already centralizes construction in `_init_engines()` and already ships a status dict in `get_status()`, so the residency watcher and health fields have one choke point each. The capability layer is additive to a registry that already computes the full present/missing map at probe time (`CapabilityRegistry.probe()` logs enabled/disabled lists today), so require_capabilities is ~40 lines plus the exception type. Health records are an append-only JSONL writer and an in-process dict — the codebase has this pattern in obs/ already. The only genuinely new moving part is the sweeper task and the _in_use counting, which is mechanical. C11 is config parsing plus two thin engine shims because RoleGate already exists. No cross-packet dependency, no migration, no founder gate for three of the four pieces.

## 8. UX rationale

The machine speaks first person, grounded in measured data. The capability refusal template is the only new user-facing string: "I can't run spoken replies: this body is missing audio (it has local_llm, web)." — states what was asked, what the machine has, what it lacks, no model named, no emoji, deterministic. Memory pressure relief is silent by design (the machine simply doesn't hold what it isn't using); the only visible trace is /api/audio/status showing an engine's loaded flag flip false after the idle window and true again on the next spoken turn, with idle_s counting — measured, never asserted. A failed engine surfaces as health.state "failed" with since/reason in the same status payload, so the engaged surface can say "my speech recognition stopped working at 14:03: missing model file" instead of today's silent absence. Health record text and refusal strings go through the existing response choke point (security/display_transport.py) like all other system text; audio config paths stay in audio_config.yml with documented defaults; the BYO command templates never interpolate a model name, only {wav_path}/{text}.

## 9. Acceptance criteria

- With audio enabled and idle_unload_s=3 (test override), load the ASR engine with one transcription, wait past the window, and StreamingASR._initialized is False and _recognizer is None; a second transcription reloads and returns text. Measured via get_status(): engines.asr goes {"loaded": true} → {"loaded": false, "idle_s": >=3} → {"loaded": true}.
- An engine held mid-use (_in_use > 0) is never unloaded even when idle past the window — proven by holding the acquire context manager across two sweep intervals and asserting loaded stays true.
- idle_unload_s=0 disables the sweeper; engines stay loaded indefinitely (current behaviour preserved as default-off escape hatch).
- require_capabilities("spoken replies", ["audio"]) on a registry with audio False raises CapabilityUnavailable whose rendered message names the op, the missing capability, and the present set; with audio True it returns None. The refusal string contains no model name and no emoji (assert with a regex over the rendered text).
- Unplugging the ASR model file and starting the pipeline produces a health record {"subsystem": "audio.asr", "state": "failed", "since": <timestamp>, "reason": "init"} readable from get_status(); a successful init after that records state "ok". Records are appended to the durable JSONL and the in-process map clears on process restart.
- tools/executor.py and dashboard/routes/agent.py refusal paths route through CapabilityUnavailable instead of their hand-rolled strings (grep shows no remaining per-site refusal literals for the migrated operations).
- If C11 is ratified: setting stt_command to a fake helper script in audio_config.yml makes the pipeline transcribe through it via RoleGate (assert role_gate invoked, no subprocess.run import in the new engines); unset blocks leave sherpa-onnx engines in place.
- All existing capability tests (test_capabilities.py) and audio tests (test_audio_pipeline_speaker.py, test_audio_routes.py, test_audio_vad_framing.py) keep passing unchanged.

## 10. Verification (measured state, not model judgment)

Run: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_capabilities.py halbert_core/tests/test_audio_pipeline_speaker.py halbert_core/tests/test_audio_routes.py -x -q` (existing suites must stay green) plus a new test module `halbert_core/tests/test_audio_model_residency.py` whose key test IDs are: `test_idle_engine_unloads_after_window` (monkeypatched clock advances past idle_unload_s; asserts `StreamingASR._initialized is False` and `get_status()["engines"]["asr"]["loaded"] is False`), `test_in_flight_engine_never_unloaded`, `test_reload_on_next_use_restores_loaded_true`, and `test_unload_disabled_when_idle_s_zero`; plus `halbert_core/tests/test_capability_require.py::test_require_raises_with_required_missing_present_in_message` (asserts the exception's `missing`/`present` fields against a registry built with audio=False) and `halbert_core/tests/test_obs_health.py::test_failure_record_visible_in_audio_status` (forces `_init_engines` ASR import failure, asserts `get_status()` carries state "failed" with a since timestamp, and the JSONL line exists on disk). Every assertion is against measured object state, status-payload fields, or file contents — no model judgment anywhere. Baseline: capture the pre-change failure set first (`main` carries a known nonzero baseline per CLAUDE.md) and diff.

## 11. Exclusions

Out of scope and where each lives instead: HM08-M2 (spill-file bounds) → the TT-01/A04 terminal-tools packet (tools/executor.py). OC11-M6 → the memory packet. HM12-C6/HM12-C2 (iMessage) → held, founder decision 2. Migrating the remaining ~13 has_capability() call sites to require_capabilities → follow-up packets, one consumer each; this packet migrates only audio/vision entry points and the two refusal-writers. Founder-gated C11 (BYO CLI providers) ships only if founder decision 4 is answered yes — the rest of the packet does not wait on it. Do not touch _probe_audio's presence-only contract, the override→probe→preset ordering, or add any second feature gate or variant check. Do not add network probes, remote health aggregation, a new dashboard page, engine/runtime swaps, or the do-not-lift items (OC11-C8 loopback verifier, OC18 keepalive stack). Leave all existing on-disk stores untouched and unread — health records are a new JSONL kind.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

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
