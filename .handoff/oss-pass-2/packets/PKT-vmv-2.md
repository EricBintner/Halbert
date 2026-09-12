# PKT-VMV-2 — SSE scrubber + output activity tracking + bounded transcript queue (post R-10)

Tier: **opus**   Milestone: **M5a**   Effort: **S-M**
Collision lane: **R**   Merge order: **1/2 in R**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-10 is merged, keep only the genuine residual.

---

## 1. Packet

**VMV-2** — SSE scrubber + output activity tracking + bounded transcript queue (post R-10).

## 2. User problem

Three verified egress-side defects survive R-10 (merged as f82cbc5a, which fixed the spoken/Wyoming path: A10-G5 satellite bypass, A10-G1 reasoning tokens spoken as words, A10-G3 fence scanner, A10-G7 budget hint). (1) SSE think-tag scrubbing is unverified end-to-end: dashboard/routes/agent.py:1494 routes response text through StreamingReasoningParser.process_token, whose _thinking_start_patterns cover <think>/<thinking>/<reasoning>/<thought> (utils/reasoning.py:154-155) — but the deep-eval (HM02-C11) asserts a dashboard-bound relay emitting tag variants or unterminated think blocks can still leak chain-of-thought into the visible stream, and an UNCLOSED tag at stream end (residual drain at agent.py:1505-1511) needs a measured check that buffered reasoning is classified as thinking, never emitted as response text. (2) No output-activity tracking exists on the Wyoming satellite egress (OC11-M3): integrations/wyoming_agent.py sends audio to the satellite and cannot distinguish "satellite swallowed the audio" from "playback mid-sentence," so barge-in and watchdog decisions are blind; nothing records whether speech is actually playing, whether it is interruptible, or whether playback outlived its audio. (3) ChunkQueue in audio/buffer.py:127-153 silently drops the oldest chunk on overflow (put at :137-144, put_nowait at :146-153) with no counter, no log, no signal (OC11-C19) — a transcript-persistence loss the machine cannot see, so any later claim grounded in that transcript is not grounded in measured data. The machine speaks as the computer itself, first person, grounded in measured data: a silent drop is a lie of omission.

## 3. What to build

Phase 0 (verify, write no code): read R-10's merged diff (f82cbc5a) against tts_quality.py:strip_reasoning_tokens and routes/agent.py's SSE parser wiring; run the SSE-path probe in field 10 and record which sub-items already hold. Drop anything R-10 covered on the SSE side. Then build the genuine residual: (1) SSE scrubber closure — extend StreamingReasoningParser coverage if the probe shows a tag family or unterminated-block case leaking to response_delta; the fix lives in utils/reasoning.py with the drain path at routes/agent.py:1505-1511 asserting in_thinking residuals surface as StreamEvent.thinking or nothing, never response text. Deterministic regex/state machine only — no model in the scrub path. (2) Output-activity tracker (OC11-M3): a small module (e.g. audio/output_activity.py) with a monotonic-clock record per egress session — audio_sent_ts, playback_started_ts (from satellite/event ack where observable), playback_ended_ts, interruptible flag, and a watchdog that flags playback still "active" beyond audio duration plus a grace bound. Wire it into integrations/wyoming_agent.py's send path and _set_channel_wyoming_active so barge-in logic can ask "is speech actually playing" instead of assuming. Reuse the turn_activity.py monotonic-generation primitive rather than a new clock. (3) Bounded transcript queue with an overflow signal (OC11-C19): add a monotonic dropped_chunks counter plus a one-line logger.warning on each drop to ChunkQueue.put/put_nowait in audio/buffer.py, expose dropped count on the object, and surface it to the pipeline coordinator (audio/pipeline.py:101) so an overflow is a measured, visible event; on sustained overflow the session stops with a first-person measured statement ("I dropped N audio chunks in the last M seconds; the transcription path cannot keep up") rather than degrading silently. No unbounded growth: the queue stays bounded at maxsize=100; the change is observability plus a stop, not a bigger buffer.

## 4. What NOT to build

Do NOT rebuild the spoken-path sanitizer, Wyoming bypass fix, fence scanner, or budget hint — R-10 (f82cbc5a) owns those; re-implementing them is the reinvention this unit exists to prevent. Do NOT touch the three-axis budget (OC11-M2), the replayable event tail (OC11-M1), or the fast-context shortcut (OC11-C4) — those are VMV-4's residual. Do NOT build the reconnect supervisor itself — it is a declared dependency (net/reconnect_supervisor.py, shared with SCHED-P5); this unit consumes it if present and proceeds without it if not. Do NOT add emoji stripping to the UI path — "no emoji in UI" is already a standing rule; HM08-M4's symbol/temperature-expansion half is excluded by default per the section note (English-only in the origin, founder decision if wanted). Do NOT build the screen-activity logbook or coordinate disclosure — VMV-5. Do NOT add a conversation list, session picker, or any multi-conversation surface. Do NOT name or recommend an AI model anywhere, do NOT put a model in the scrub/redaction path, do NOT build migrations or back-compat shims, and do NOT delete the old silent-drop behavior's data — old logs stay on disk, unread.

## 5. Target files
- `halbert_core/halbert_core/dashboard/routes/audio.py`

## 6. Dependencies

reconnect_supervisor

## 7. Effort

**S-M** — S-M. The heavy thinking was done by R-10 and the deep-eval; this unit is deliberately verification-first so the code volume is the residual only. The ChunkQueue counter-and-signal is genuinely S (one counter, one log line, one exposure on the coordinator, tests against an existing test_audio_buffer.py). The output-activity tracker is the M half: a new small module, wiring into wyoming_agent.py's send/ack path, a watchdog bound, and barge-in integration — but it reuses turn_activity.py's monotonic-generation primitive and has no founder gate. The SSE scrubber closure is bounded by what the probe finds; if agent.py's StreamingReasoningParser already covers all four tag families and the unterminated drain, the SSE item collapses to a regression test and the unit lands at the S end. No new dependencies (Haloysius two-hard-dependency contract holds), no model, no config schema change.

## 8. UX rationale

Nothing new is rendered; this is truth-telling on existing surfaces. When the transcript path overflows, the machine says so in first person grounded in the measured counter — "I dropped N audio chunks; transcription could not keep up, so I stopped listening rather than guess" — never a silent gap presented as a complete transcript. On the voice surface, barge-in behaves correctly because the system knows whether speech is actually playing: an utterance during real playback interrupts; a satellite that swallowed audio does not masquerade as an interruptible mid-sentence state. On the dashboard, no chain-of-thought from any tag family ever appears as visible response text on the SSE stream — reasoning is surfaced only through the existing thinking channel (StreamEvent.thinking), and an interrupted reasoning block at stream end never bleeds into the answer. All copy is the computer speaking as itself, no emoji, colours from shared-tokens/tokens.css only, no model names on any surface.

## 9. Acceptance criteria

1. SSE scrub: a streamed response containing <reasoning>...</reasoning>, <thought>...</thought>, and an UNTERMINATED <think> block emits zero reasoning characters as response text on the /api/agent SSE stream; reasoning arrives only via thinking events; the stream-end drain classifies buffered in-thinking content as thinking or drops it. 2. ChunkQueue: filling the queue past maxsize increments a readable dropped-chunk counter, logs one warning per drop, and the pipeline coordinator exposes the cumulative count; sustained overflow stops the session with the first-person measured message. 3. Output activity: after Wyoming audio is sent, the tracker reports playing/not-playing and interruptible state from recorded timestamps, and the watchdog flags a playback state that outlives audio duration plus grace; barge-in queries the tracker. 4. Verification gate: the R-10 overlap probe (field 10) is run first and its result recorded in the commit message; anything R-10 already covered is dropped from scope, not re-implemented. 5. All existing audio/SSE tests still pass: arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_audio_buffer.py halbert_core/tests/test_tts_quality.py halbert_core/tests/test_tts_egress.py halbert_core/tests/test_audio_routes.py collects and runs green against the pre-change baseline (main is known not-green — diff against the merge-base baseline, not zero).

## 10. Verification (measured state, not model judgment)

Runnable measured checks, no model judgment: (a) SSE leak probe — arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "reasoning or think" -x plus a targeted script that feeds StreamingReasoningParser.process_token the byte stream "<reasoning>secret chain</reasoning>answer<thought>more" and asserts response_delta accumulates exactly "answer" (measured string equality, not inspection). (b) Unterminated-block probe — feed "<think>interrupted reasoning with no closer" then finalize() and assert the drained residual is NOT emitted as response text (exercises routes/agent.py:1505-1511 semantics at the parser level). (c) ChunkQueue overflow — pytest halbert_core/tests/test_audio_buffer.py with a new test that put_nowait's 101 chunks into a maxsize=100 queue and asserts queue.dropped == 1 (counter exists and equals exactly 1) and caplog records one WARNING. (d) Output-activity — a test that records audio_sent for a 2.0s segment, advances the monotonic clock 2.0s + grace + epsilon without a playback-end event, and asserts the watchdog's is_stale() returns True; and False at 1.0s. (e) R-10 overlap gate — git show f82cbc5a --stat output captured in the commit body proving which items were verified as already delivered. Every check is a counter, string equality, timestamp comparison, or pytest assertion against measured state.

## 11. Exclusions

The replayable per-turn event tail (OC11-M1), three-axis budget (OC11-M2), fast-context shortcut (OC11-C4), and duplicate-transcript suppressor (A09-G2) go to VMV-4 (voice ingress hardening). The reconnect supervisor build itself goes to the shared cross-cutting module net/reconnect_supervisor.py (cross-cutting opportunity 6, shared with SCHED-P5); this unit only depends on it. Spoken-path items already owned by R-10/f82cbc5a — Wyoming satellite pipeline bypass (A10-G5), reasoning tokens spoken as words (A10-G1), fence scanner (A10-G3), word-budget hint (A10-G7), spoken tail through turn_digest (A05-G5 via security/turn_digest.py:spoken_tail) — stay with R-10; verify, do not rebuild. HM08-M4's symbol/temperature expansion (English-only in origin) is excluded pending a founder decision; the emoji half is covered by the standing no-emoji rule, not this unit. Screen coordinate disclosure and the day journal go to VMV-5. Capability assertions and idle-unload go to VMV-6. Inbound media bounds (routes/audio.py:215/:267 unbounded b64decode) go to VMV-3 — same file, different defect class; do not fix it here. Text-hygiene consolidation (strip_unicode_tags unification) goes to the cross-cutting security/text_hygiene.py module (opportunity 4).

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
