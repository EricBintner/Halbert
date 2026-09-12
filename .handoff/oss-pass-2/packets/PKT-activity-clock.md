# PKT-activity_clock — Per-instance monotonic activity clock

Tier: **fable**   Milestone: **M0**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**activity_clock** — Per-instance monotonic activity clock.

## 2. User problem

Halbert has no shared monotonic activity clock, so every liveness check in the tree falls back to flat wall-clock deadlines — and the deep-eval confirmed this produces three live defects. (1) `scheduler/executor.py:62-86 _call_with_timeout` joins a worker thread for `timeout_s` of pure wall clock: a job doing healthy long work (a big local-model generation) is killed at the deadline, while a genuinely wedged job is not noticed until the same deadline — the timeout cannot tell idle from busy (SCHED-P2/HM16-C16; the A06 own-bug where the thread keeps running with side effects after the receipt says error). (2) `agents/llm_client.py:225` wraps `OllamaClient.stream` (`:195`) in `aiohttp.ClientTimeout(total=self.timeout)` — a total-stream deadline that aborts healthy long generations and is blind to mid-stream stalls (SCHED-P2/OC18-M2, MP-3's 120 s kill). (3) `agents/state_machine.py:223-232 TURN_LOCK_TIMEOUT_S` bounds only a QUEUED waiter; a wedged turn holding the one conversation's lock is never released, so Halbert stops responding with no mechanism that can distinguish "turn is making progress" from "turn is stuck" (SCHED-P4/HM01-C2). The FINAL-CRITICAL-DISCOVERY-BACKLOG §3.2 names the fix as the Wave-0 "Activity-clock primitive" needed by SCHED-P2, SCHED-P4, TT-05 (tool heartbeat) and TT-06, and SCHED-P4's verdict is ACCEPT explicitly for the "turn liveness and activity-clock approach". The registry header for this unit corrects one thing in the deep-eval: the backlog guessed the primitive should "extend `turn_activity.py`", but `agents/turn_activity.py` is a cancellation-generation counter (`TurnActivity.stamp()/claim(gen, fn)`) — it owns a lock and a monotonic integer generation for race-safe abort claims and has no timestamps, no `time.monotonic()`, no idle semantics. Folding a clock into it would conflate two unrelated invariants. So this unit is a NEW module, `halbert_core/halbert_core/utils/activity_clock.py`, that the six named consumers (MP-2, MP-3, SCHED-P2, SCHED-P4, DAEMON-01b, TT-05) will each adopt in their own packets.

## 3. What to build

Create `halbert_core/halbert_core/utils/activity_clock.py` — a small, dependency-free (stdlib-only, per the Haloysius two-dependency contract), thread-safe per-instance monotonic activity clock with this exact contract:

- `class ActivityClock`: one instance per watched activity (one per turn, one per streaming response, one per scheduled-job run, one per tool call). Not a singleton, not process-global — the scheduler executor, the state machine, and the LLM client each hold their own instance on the object they already own.
- `record_activity(source: str) -> None`: stamps `time.monotonic()` under a `threading.Lock`. `source` is a short static string naming the progress kind (`"stream_chunk"`, `"tool_start"`, `"tool_complete"`, `"handler_entry"`, `"receipt_write"`); kept as the last-source for diagnostics but never parsed.
- `idle_seconds() -> float`: returns `time.monotonic() - last_stamp` under the lock; `0.0` immediately after construction (construction stamps the clock).
- `is_stalled(idle_timeout: float) -> bool`: pure read — `idle_seconds() >= idle_timeout`. Takes the timeout as an argument; the clock owns no policy (ceilings belong to the consumers: SCHED-P4's founder-decision-4 30-minute ceiling, MP-3's stream idle-gap, TT-05's tool heartbeat interval).
- Constructor takes an optional `clock: Callable[[], float] = time.monotonic` so tests inject a fake clock without monkeypatching `time` — matching how `_RateLimiter` in `mcp/server.py:1667` already uses monotonic time.
- `last_source: Optional[str]` property for the diagnostic surface (doctor/SCHED-P4 receipt can say "stalled after tool_start").
- Module docstring names the consumers and states the invariant: measures observed progress, never wall-clock-alone (the FINAL-BACKLOG §2 mechanism "Output/activity watchdogs based on observed progress").

Plus `halbert_core/tests/test_activity_clock.py` covering: construction stamps at t0; `record_activity` resets idle; `idle_seconds` advances with the fake clock; `is_stalled` threshold edges (just below / exactly at / above); thread-safety smoke (N threads stamping, final `idle_seconds() >= 0` and no exception); `source` is recorded; fake-clock injection works with zero monkeypatching.

No consumer wiring in this unit — MP-2/MP-3/SCHED-P2/SCHED-P4/DAEMON-01b/TT-05 adopt the clock in their own packets.

## 4. What NOT to build

- NOT an extension of `agents/turn_activity.py`. The deep-eval §3.2 candidate said "extend turn_activity.py"; the registry note overrules it — `TurnActivity` is a generation counter for race-safe cancellation claims, and mixing a wall/monotonic clock into it conflates cancellation generations with liveness timestamps.
- No consumer adoption: no changes to `scheduler/executor.py` `_call_with_timeout`, `agents/llm_client.py`'s `ClientTimeout`, `state_machine.py`, `tools/executor.py`, or any streaming code. Those are MP-2, MP-3, SCHED-P2, SCHED-P4, DAEMON-01b, TT-05 respectively.
- No watchdog/sampler thread, no callback registry, no observer: the clock is a passive stamp/check primitive; the *sampler* that polls `is_stalled` and acts (force-abort a turn, interrupt a job, close a stream) belongs to each consumer packet (SCHED-P4's sampler, SCHED-P2's inactivity watchdog).
- No cancellation/abort logic, no `claim()`/generation semantics — that is `TurnActivity`'s job and stays there.
- No phase-aware budgets (queued/model_resolution/executing deadlines — SCHED-P2 OC18-M1), no DaemonThreadPoolExecutor (HM07-C19), no process-group kill (HM16-M4, shared `utils/process_group.py` Wave-0 primitive), no policy/ceiling defaults, no config keys, no founder-decision-4 ceiling value.
- No persistence, no receipts, no metrics export, no logging beyond a module logger; no asyncio (consumers stamp from both threads and the event loop, but the clock itself is sync).

## 5. Target files
- `halbert_core/halbert_core/utils/activity_clock.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S — one new stdlib-only module (~60-80 lines with docstrings: a lock, two float fields, a string field, three methods plus constructor) plus one focused test file (~120 lines) using an injected fake clock. No existing file is touched, so zero hot-file coordination (`state_machine.py`, `executor.py`, `llm_client.py` all stay untouched — their packets land separately). No founder decision: the registry notes and the FINAL-BACKLOG Wave-0 table both place the activity clock in "no founder-decision gates" Wave 0, and the only gated item (SCHED-P4's 30-minute ceiling, founder decision 4) is consumer policy, not this primitive. It is deliberately the smallest Wave-0 primitive because six downstream packets block on it: MP-2 (typed turn_exit_reason stamping), MP-3 (idle-gap stream timeout replacing `ClientTimeout(total=120)`), SCHED-P2 (inactivity watchdog), SCHED-P4 (turn liveness sampler), DAEMON-01b (stuck-turn reclamation age check), TT-05 (tool-execution heartbeat). Building it once here prevents six per-packet reimplementations — the duplicate-primitive failure the standing rules and FINAL-BACKLOG §3 preamble both forbid.

## 8. UX rationale

No user-facing surface — this is an internal primitive with no UI, no CLI, no copy. Its user-visible *effect* arrives only through the consumer packets: a healthy long local-model generation is no longer killed at a flat 120 s wall clock (MP-3/SCHED-P2), a genuinely wedged turn gets reclaimed instead of pinning the one conversation forever (SCHED-P4/DAEMON-01b), and a stalled tool call trips a heartbeat-based guard rather than a total deadline (TT-05). The only constraint this unit carries from the Halbert frame is negative: the `source` strings and `last_source` property must be static machine strings (`"stream_chunk"`, `"tool_start"`) — never model names, never slot internals — because SCHED-P4's receipt and the doctor surface will render them; and no emoji anywhere, including docstrings and test names.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/utils/activity_clock.py` exists, is importable as `from halbert_core.utils.activity_clock import ActivityClock`, and exposes exactly `record_activity(source)`, `idle_seconds()`, `is_stalled(idle_timeout)`, `last_source`, with construction stamping the clock.
2. All timing goes through the injected clock (default `time.monotonic`) — a test with a fake clock controls every assertion without sleeping or monkeypatching `time`.
3. Thread-safe: a stress test with multiple threads calling `record_activity` concurrently completes with no exception and a consistent `idle_seconds() >= 0.0`.
4. `is_stalled(t)` is a pure read (no mutation, no policy) and returns the correct boolean at the boundary (idle == t → stalled).
5. `agents/turn_activity.py` is byte-identical before and after this unit — no changes to `TurnActivity`.
6. No other production file is modified (verified by `git diff --stat` showing only the new module + new test file).
7. Module carries the standard SPDX GPL-3.0-or-later header and copyright line matching `agents/turn_activity.py` / `utils/retry.py`.

## 10. Verification (measured state, not model judgment)

Run the new test file with the mandated invocation and require exit code 0:

`arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_activity_clock.py -v`

Expected: every test passes (approximately 8-10 tests covering the acceptance list). Then confirm the primitive is importable in the real interpreter and measures real monotonic time (not the fake):

`arch -arm64 .venv/bin/python -c "import time; from halbert_core.utils.activity_clock import ActivityClock; c = ActivityClock(); time.sleep(0.2); assert 0.19 < c.idle_seconds() < 2.0, c.idle_seconds(); assert c.is_stalled(0.1) and not c.is_stalled(60.0); c.record_activity('stream_chunk'); assert c.idle_seconds() < 0.2 and c.last_source == 'stream_chunk'; print('activity_clock OK')"`

Expected output `activity_clock OK` and exit code 0. Also confirm isolation from the cancellation counter: `git diff --stat main...HEAD -- halbert_core/halbert_core/agents/turn_activity.py` prints nothing (file untouched). Note for the runner: if dispatched in a worktree, use `arch -arm64 ./wt_pytest.py halbert_core/tests/test_activity_clock.py` instead of bare pytest (the shared venv's editable install pins `halbert_core` to the main tree).

## 11. Exclusions

- Consumer adoption of the clock → each consumer's own packet: MP-2 (Retry-After/turn_exit_reason stamping), MP-3 (idle-gap `sock_read` stream timeout replacing `aiohttp.ClientTimeout(total=...)` at `agents/llm_client.py:225` and the Anthropic stream at `:392`), SCHED-P2 (inactivity watchdog HM16-C16 replacing `_call_with_timeout`'s flat join at `scheduler/executor.py:62-86`, plus process-group kill HM16-M4 which also needs the separate Wave-0 `utils/process_group.py` primitive), SCHED-P4 (turn-liveness sampler HM01-C2 + tool heartbeat HM01-C3 + the founder-decision-4 ceiling default), DAEMON-01b (stuck-turn reclamation watchdog — itself a RESHAPE deferral from DAEMON-01, sequenced after the state-machine work), TT-05 (tool-execution heartbeat shared with the signature-hashed guardrails).
- The deep-eval's "extend turn_activity.py" suggestion → dropped per the registry note (turn_activity.py is a cancellation-generation counter, not the home); recorded here so the M5b tail or a reviewer does not re-propose it.
- Phase-aware budgets (OC18-M1) and DaemonThreadPoolExecutor (HM07-C19) → SCHED-P2 Phase 2 per the deep-eval's own two-phase split.
- Subagent staleness monitor (TT-06/HM05-M1) → TT-06 is DEFERRED (no production SubagentManager consumer); when it opens, it consumes this clock.
- Process-group kill escalation → separate Wave-0 primitive `utils/process_group.py` (FINAL-BACKLOG §3.1), not this module.
- The watchdog sampler/callback loop that polls `is_stalled` and acts → consumer packets; this unit ships only the passive stamp/check primitive.
- No config keys, no ceiling defaults, no doctor/finding integration → consumer packets and DIAG-01 respectively.

---

## OSS reference

openclaw src/infra/agent-run-registry.ts:720 + agent-events.ts:267; use time.monotonic().

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
