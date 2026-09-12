# PKT-DAEMON-01b — Stuck-turn reclamation watchdog

Tier: **opus**   Milestone: **M1**   Effort: **M**
Collision lane: **A**   Merge order: **9/9 in A**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Merge LAST in its lane.**

---

## 1. Packet

**DAEMON-01b** — Stuck-turn reclamation watchdog.

## 2. User problem

A wedged turn holds the state machine's one turn lock for the life of the process. `halbert_core/halbert_core/agents/state_machine.py` bounds only the ACQUIRE side: `_acquire_turn_lock` (~line 1060) wraps `self.turn_lock.acquire()` in `asyncio.wait_for(..., timeout=self.TURN_LOCK_TIMEOUT_S)`, so a caller that never gets the lock streams `_turn_lock_timeout_events()` ("The previous turn is still running. Try that again in a moment.") and gives up — but the turn already holding the lock has no ceiling at all. If that turn wedges mid-stream (a local model server that stops producing chunks without closing the connection, a tool whose subprocess neither exits nor writes, an await that never returns), every later message from every channel — dashboard chat, terminal channel, voice ingress — queues behind the "waiting" badge and then times out, forever, until the founder restarts the backend. This is audit A07-G10 / discovery item OC08-M1 (verifier-added, confirmed in the section file at `.handoff/oss-pass-2/section_dashboard-app-onboarding-diagnostics.md:46`, which spot-verifies `state_machine.py:512-519,1477-1482` as bounding only the acquire side). On a single-user single-host machine that speaks as the computer itself, a permanently wedged turn is the machine going mute with no self-recovery: the one seamless conversation just stops answering, and the only remedy is a process restart the user has to know to perform. The reclamation must NOT fire on legitimate long waits: a turn paused in `AgentState.AWAITING_CONFIRMATION` (`agents/states.py:41`, handled by `_handle_awaiting_confirmation` at `state_machine.py:~4464`) is correctly waiting on a human at the `/confirm` door; an approval pending in `approval/engine.py` is the same class; a tool actively streaming output is making progress, not wedged. A naive wall-clock timeout would kill exactly these healthy turns, so the watchdog must be progress-based (observed activity, not elapsed time) and gated by a closed enum of skip reasons — deterministic thresholds only, no model judgment anywhere in the decision.

## 3. What to build

Build the stuck-turn reclamation watchdog inside `halbert_core/halbert_core/agents/state_machine.py`, per OC08-M1's spec (section file line 46). Concretely:

1. **Progress stamp.** Add a monotonic `last_activity` marker (monotonic clock, wall timestamp for display) on the turn's `StateContext`, touched at: handler entry under the lock (right where `_turn_generation = self.turn_activity.stamp()` already fires, ~line 604 and again at ~1646 for a resumed confirm), each tool call start and each tool call completion in EXECUTING/OBSERVING, and each model stream chunk in RESPONDING. Reuse the existing `TurnActivity` generation discipline from `agents/turn_activity.py` (the R-01 merged interrupt algebra — the packet's `activity_clock` dependency): progress updates must be cheap, thread/task-safe, and attributable to the current generation so a reclaim fired against generation N declines if the turn has since moved to N+1 (same stale-claim rule `TurnActivity.claim()` already enforces for `/api/agent/stop`).

2. **Closed skip-reason enum.** A module-level `ReclaimSkipReason` enum in `state_machine.py` (or `agents/states.py` beside `AgentState`): `AWAITING_CONFIRM` (state is `AgentState.AWAITING_CONFIRMATION` — the paused `/confirm` turn at ~1477 is a legitimate human wait, settled by `_supersede_paused_turn` when a new message arrives, never by the watchdog), `APPROVAL_PENDING` (a request is live in `approval/engine.py`'s pending set), `GUEST_HANDBACK_PENDING`, `TOOL_RUNNING_WITH_LIVE_OUTPUT` (the active tool has produced output within the no-progress window), `ALREADY_RECLAIMING` (in-flight dedupe by logical session, per the origin's `diagnostic-session-recovery.ts:7-19` eleven named no-fire reasons). The gate evaluates state + pending-confirmation + tool-liveness deterministically; any skip reason present means no reclaim that poll.

3. **Reclaim poll.** A low-frequency asyncio task started with the state machine (cadence ~15 s settle, per the origin's `diagnostic-stuck-session-recovery.runtime.ts:35-90`: `STUCK_SESSION_PROGRESS_STALE_MS` = 5 min). Each tick: if `turn_lock.locked()` and no skip reason applies and `now_monotonic - ctx.last_activity > STUCK_TURN_NO_PROGRESS_S` (default 300 s), reclaim: cancel the task owning the wedged turn (generation-claimed, so a turn that completes during the cancel races safely), force-release the lock if the cancel does not unwind the `finally` at ~946, reset machine state to IDLE via the same path `_supersede_paused_turn` uses, and end the persisted turn as cancelled with a block recording "not run — turn wedged, reclaimed" so the receipt says what happened.

4. **One typed receipt per reclamation.** Call `obs/audit.py:212 write_audit(tool="turn_reclaim", mode="watchdog", request_id=<turn's request_id>, ok=True, summary=..., reason="stuck_turn_no_progress", actor=ACTOR_SYSTEM, ...)` with extras carrying the source tag from the activity clock (`turn_activity.generation` at fire time — the registry note's "needs activity_clock source tag"), the no-progress age observed, the state the turn died in, and which skip reasons were evaluated empty. `write_audit` never raises and returns the shard path.

5. **Surface on `/health`.** Extend the health payload at `dashboard/routes/agent.py:~1993-2005` (currently `status`, `active_sessions`, `current_state`) with `last_reclaim` (timestamp, turn age, died-in-state) or null — coarse, no model names, no turn content.

Deterministic thresholds only; no LLM anywhere in the watchdog decision; every threshold a named module constant.

## 4. What NOT to build

- **Not the single-instance lock, exit vocabulary, or `supervised()` probe** — that is DAEMON-01a (the deep-eval's RESHAPE split: `backend.lock` flock, exit codes 75/78, `XPC_SERVICE_NAME` detection). DAEMON-01b depends on 01a only for the exit vocabulary a reclaim never uses (reclamation is in-process; it must NOT exit 75 — the machine recovers the turn, it does not restart itself).
- **Not PID-reuse-safe backend identity (`(pid, start_marker)`, `HALBERT_PARENT_START`) and not the boot-forensics ring buffer** — both folded into DIST-01's Tauri/Rust-side packaging work per the deep-eval's RESHAPE ruling (`lib.rs` changes, out of this lane).
- **Not a hard turn wall-clock deadline.** A turn legitimately running a 10-minute build with live output must not be reclaimed. Progress-based only; `TOOL_RUNNING_WITH_LIVE_OUTPUT` is a skip reason, not a shorter timeout. The turn-deadline-ceiling question is SCHED-P4's FD 4, not this unit.
- **Not auto-retry or auto-continue of the reclaimed turn.** The founder-gated resume behavior (auto-continue after crash) is CSC-03's FD 2. Reclamation ends the turn as cancelled and says so; it never silently re-asks the user's question.
- **Not model/stream-layer transport fixes** (slow-or-silent local model server fixtures, cancel-in-flight, abort hooks) — that is MP-3. The watchdog is the last-resort net for whatever the transport layer fails to bound; do not fix the model client here.
- **Not the per-session StateContext clearing-scope refactor** (HM11-M6, section file line 49: annotate `StateContext` fields by clearing scope) — the section file says "bundle with OC08-M1 or leave"; leave it. It is a separate S-effort unit.
- **No UI work beyond the `/health` field** — no banner, no badge, no notification design. The user-visible "the turn died and I recovered" utterance, if any is wanted, is a surfacing decision for SURFACE-01a, not this packet.

## 5. Target files
- `halbert_core/halbert_core/agents/state_machine.py`

## 6. Dependencies

activity_clock, DAEMON-01a

## 7. Effort

**M** — M (medium). The mechanism is small but the file is the hottest in the tree. The actual new machinery is: one monotonic stamp field on `StateContext` plus ~4 touch sites (handler entry, tool start, tool complete, stream chunk), one ~80-line reclaim poll task, one closed 5-member skip-reason enum with a deterministic gate, one `write_audit` call, one `/health` field, and tests. That is S-sized code. It earns M because (a) `agents/state_machine.py` is the fourth touch on the file per the section file — R-01 (interrupt algebra, merged), R-06 (turn digest, merged), R-12 Phase A (two narrow ranges, done), TT-05, SP-3, CSC-05, MP-1 all queue on it — so every edit needs care against the merged interrupt algebra and the lock's release paths (~lines 594, 946), and the registry note says MERGE LAST in lane A for exactly this reason; (b) the reclaim path must be proven race-safe against `TurnActivity`'s generation-claim semantics (a reclaim that fires as the turn finalizes must decline, exactly as a late `/stop` declines) — that race test is the packet's real engineering; (c) the cancel-the-owning-task path must be verified to actually unwind the `asyncio.wait_for`/lock `finally` and release, with a force-release fallback if it does not; (d) skip-reason coverage needs a fixture per reason (paused `/confirm` turn, live approval, streaming tool) proving the watchdog does NOT fire. Origin reference behavior to mirror (not copy): openclaw `src/logging/diagnostic-stuck-session-recovery.runtime.ts:35-90` and `src/logging/diagnostic-session-recovery.ts:7-19,49-75` at `/Volumes/Thunderbolt/AI/openclaw`. Opus tier per the packet header: the judgment calls are which waits are legitimate (the skip enum) and the generation-race correctness, both security-adjacent (a wrong reclaim kills a turn mid-tool; a missing reclaim wedges the machine).

## 8. UX rationale

Deliberately almost invisible — the success case is that nothing user-visible ever happens. The machine that would have gone permanently mute instead recovers itself: the next message the user sends (after the current one's "still running" timeout, which already exists) simply gets answered, instead of every message timing out until someone restarts the backend. That is the whole UX: the one seamless conversation stays one seamless conversation. Voice of the machine: when a reclamation happens, the turn ends as cancelled with a persisted receipt block ("not run — turn wedged, reclaimed"), so if the user asks what happened the machine can answer in first person grounded in the measured record ("I stalled on that turn for five minutes with no progress, so I stopped it and freed myself") — the receipt is the grounding, never a generated excuse. Surfaces touched: exactly one field on the existing `/health` payload (`last_reclaim`: timestamp, age, died-in-state, or null) — coarse, no model names, no turn content, no model anywhere in producing it. No new dashboard UI, no banner, no badge, no notification, no emoji; if a visible indicator is later wanted it belongs to SURFACE-01a's staleness/progress design, fed by this field. No settings toggle in v1: the 300 s no-progress threshold and 15 s poll cadence are module constants; making them configurable is OTHER-P6's settings-reload seam if it is ever wanted. The audit receipt (`obs/audit.py` shard) is the durable, tamper-evident record a founder or `halbert doctor` can inspect after the fact — DIAG-01's doctor registry can later add a "recent reclaims" check reading the same source.

## 9. Acceptance criteria

1. A turn that makes no progress (no stream chunk, no tool start/complete, no handler re-entry) for `STUCK_TURN_NO_PROGRESS_S` (300 s) while holding `turn_lock` is reclaimed: the owning task is cancelled, the lock is released (verified free, not just cancellation requested), machine state returns to `AgentState.IDLE`, and the persisted turn is ended `cancelled` with a block recording the wedge.
2. The skip gate holds: a turn parked in `AWAITING_CONFIRMATION` (staged HIGH-risk action awaiting `/confirm`) is NEVER reclaimed regardless of age; same for a live `approval/engine.py` pending request (`APPROVAL_PENDING`), `GUEST_HANDBACK_PENDING`, a tool producing output inside the window (`TOOL_RUNNING_WITH_LIVE_OUTPUT`), and a second poll while a reclaim is in flight (`ALREADY_RECLAIMING`). Each reason has its own fixture proving no fire.
3. Generation race: a reclaim fired against turn-activity generation N declines (no cancel, no lock release, no receipt) if the turn stamps generation N+1 before the claim executes — same stale-claim rule as `/api/agent/stop`.
4. Exactly one `write_audit` receipt per reclamation, `tool="turn_reclaim"`, `reason="stuck_turn_no_progress"`, `actor=ACTOR_SYSTEM`, carrying the activity-clock generation tag, observed no-progress age, and died-in state; zero receipts when the gate skips.
5. `/health` reports `last_reclaim` (or null) — verified by reading the endpoint JSON, no content fields, no model names.
6. After reclamation, a new `process()` call acquires the lock immediately and completes a normal turn (no restart required).
7. Acquire-side behavior unchanged: `TURN_LOCK_TIMEOUT_S` timeout path and `_turn_lock_timeout_events()` still fire identically for a queued caller while a healthy turn runs.

## 10. Verification (measured state, not model judgment)

Runnable, measured-state checks (worktree: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py halbert_core/tests/ -q`):

1. New test module `halbert_core/tests/agents/test_stuck_turn_reclaim.py`, red-first, asserting:
   - `test_wedged_turn_is_reclaimed`: a fake turn acquires `turn_lock`, stamps `last_activity` 301 s in the past (monotonic injected/frozen), no skip reasons; run one watchdog tick; assert `state_machine.turn_lock.locked() is False`, `current_state == AgentState.IDLE`, and exactly one audit row with `tool="turn_reclaim"` appears in the test audit shard (read the JSONL file back, parse, assert fields including the generation tag and `reason="stuck_turn_no_progress"`).
   - `test_awaiting_confirmation_never_reclaimed`: state forced to `AgentState.AWAITING_CONFIRMATION` with a stale stamp; tick; assert lock still held, zero audit rows.
   - `test_tool_with_live_output_skipped`: stale turn-level stamp but a tool-output stamp inside the window; tick; assert no reclaim.
   - `test_stale_generation_claim_declines`: stamp generation, snapshot it, stamp again, then fire a reclaim carrying the old generation; assert it returns without cancelling and writes no receipt (exit state: lock still held by the live turn).
   - `test_reclaim_receipts_exactly_once`: two consecutive ticks against the same wedged turn; assert one audit row total (`ALREADY_RECLAIMING` dedupe).
   - `test_next_turn_runs_after_reclaim`: after the reclaim tick, drive a minimal `process()` turn to completion; assert stream reaches a terminal event and the lock is free at the end (exit code of the coroutine: clean return, no `TimeoutError`).
2. Existing suites must stay green over the touched file: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python wt_pytest.py halbert_core/tests/agents/ -q` (covers the interrupt-algebra/stop tests from R-01 and the lock-timeout tests) — compare against a baseline run on the merge-base before the branch, since main carries a known nonzero failure baseline.
3. Endpoint check (measured): boot the backend in dev (`make dev-web`), `curl -s localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'last_reclaim' in d"` — exit code 0 asserts the field exists; after forcing a reclaim in a test harness, assert it is an object with `ts`, `age_s`, `state` and no `model`/`content` keys (assert by key set, exit nonzero on violation).

## 11. Exclusions

- Single-instance `backend.lock` flock, exit codes 75/78, `supervised()` probe → DAEMON-01a (same RESHAPE split; ships first in lane A; 01b merges last in that lane).
- PID-reuse-safe backend identity (`(pid, start_marker)`, ownership file, orphan reap) and ring-buffered boot forensics → DIST-01 (Tauri/Rust packaging track, per the deep-eval's fold instruction).
- Per-session `StateContext` clearing-scope annotation (HM11-M6) → separate S-effort unit; the section file explicitly allows "bundle with OC08-M1 or leave" — left, to keep this diff minimal on the hot file.
- Transport-layer slow/silent-server cancellation and abort hooks → MP-3 (needs MP-2 C6 first); this watchdog is the net below those fixes, not a substitute.
- Turn wall-clock deadline ceiling → SCHED-P4's FD 4 (founder-gated); reclamation here is progress-based only.
- Auto-retry/auto-continue of a reclaimed turn → CSC-03's FD 2 (founder-gated resume half); reclamation cancels and records, never re-asks.
- User-facing "I recovered" banner/badge/notification and any settings toggle → SURFACE-01a (surfacing) and OTHER-P6 (settings reload) respectively; this unit ships the `/health` field and audit receipt they would consume.
- A `halbert doctor` "recent reclaims" check → DIAG-01's registry (read-only consumer of this unit's audit rows, once the registry exists).
- Configurable thresholds → dropped from v1 per the minimal-surface rule; module constants until OTHER-P6's reload table exists.

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
