# PKT-SCHED-P1 — Scheduler durability residual (post R-03)

Tier: **opus**   Milestone: **M5a**   Effort: **S**
Collision lane: **D**   Merge order: **3/4 in D**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-03 is merged, keep only the genuine residual.

---

## 1. Packet

**SCHED-P1** — Scheduler durability residual (post R-03).

## 2. User problem

The scheduler's durable job record is not authoritative at fire time, and its run receipts identify their owner by a bare, reusable pid. Concretely on current main: (1) executor.py `wrapped()` (line 581) fires without re-reading the durable record — it goes straight to guardrails and `update_job_state(job_id,'running')`, so a job whose record was set to 'cancelled' by any path other than `SchedulerExecutor.cancel_job` (for example the `dashboard/routes/jobs.py:110` route, which calls `scheduler.cancel_job` on the engine and never removes the live APScheduler job) keeps firing on schedule. There are two divergent cancel paths and only one of them touches APScheduler. (2) run_receipts.py `mark_started` (line 139) records only `owner_pid=os.getpid()` and `recover_on_boot` probes it with `_default_pid_alive` = `os.kill(pid, 0)` (line 56): macOS reassigns pid namespaces across boots, so a stale `running` receipt from a previous boot whose pid collides with a live process is never interrupted, and a genuinely dead owner can be masked by pid reuse. (3) engine.py line 20 creates the scheduler persist dir with a bare `os.makedirs(..., exist_ok=True)` and no chmod anywhere in the module, leaving job records and receipts (which carry owner pids, task names, and error text) at the process umask's default permissions rather than owner-only 0700/0600. All three are residuals that survive even the unmerged R-03 branch (fix/remediation-sonnet-batch-1): diffing that branch against main shows run_receipts.py gains no start-time/create_time fingerprint and executor.py gains no fire-path re-read, so this packet is real work in both merge outcomes, not a duplicate of R-03.

## 3. What to build

Three small, independent fixes in halbert_core/halbert_core/scheduler/. (1) Fire-path re-read: at the top of `wrapped()` in executor.py (before the guardrails block at line 586), re-read the durable record via `self.scheduler_engine.get_job(job_id)` and refuse to fire when the record is missing, terminal, or in a non-runnable state ('cancelled' specifically; use the engine's `Job.is_terminal()` plus an explicit cancelled/paused check rather than inventing a second state judge) — log the refusal and `return None` the way the existing safe-mode skip at lines 588-594 does. Additionally, make the `dashboard/routes/jobs.py:110` cancel path and `settings.py:2979` route converge on the same entry point (`SchedulerExecutor.cancel_job`, which already calls `self.scheduler.remove_job`) so there is exactly one cancel choke point, matching the repo's one-place-each-thing invariant. (2) PID+start_time owner identity: extend `RunReceiptStore.mark_started` in run_receipts.py to also persist the owner's process start time (read from /proc-free macOS via `psutil.Process(pid).create_time()` if psutil is already an optional import here, else a small sysctl `kern.proc.pid`/`kinfo_proc` helper — do NOT add psutil as a third hard dependency, which would break the Haloysius subtractive contract), and extend `_default_pid_alive`/`recover_on_boot` to compare both pid and recorded start time, declaring the owner dead when the pid is absent OR the pid's current create_time differs from the recorded one. Keep the field additive on the receipt dict so old receipts without it are treated as unknown-owner (interrupted on next boot), not migrated — no back-compat shim. (3) Owner-only permissions: after `os.makedirs(self.persist_dir, exist_ok=True)` in engine.py line 20, `os.chmod(self.persist_dir, 0o700)`, and in the atomic-write helper used by `_persist_job`/receipts flush, chmod new files to 0o600 before/after the rename (the shared atomic-write helper in run_receipts.py lines ~110-135 already centralizes the write; add the chmod there so job JSON and receipts.json both inherit it). Each fix lands with its own focused test; no model involvement anywhere — all three are deterministic.

## 4. What NOT to build

Do not rebuild the R-03 scope: occurrence idempotency, boot-recovery coordination, receipt retention, corrupt-store containment, misfire-grace scaling, edit re-anchoring, ticker liveness markers, heartbeat BaseException survival, and the ssh-digest fix are R-03's (currently on fix/remediation-sonnet-batch-1) and must not be re-implemented here — the packet's first step is verifying that merge state, not redoing it. Do not build the per-job fire fence/flock (HM16-M5): the deep-eval itself rated it the weakest residual and said the right fix is one shared engine on app.state, not a lock server — that consolidation, if still needed after R-03, belongs to a follow-up named in DECISIONS.md, not this packet. Do not build OC14-C18 (detach teardown so a timed-out worker can't overwrite a terminal receipt): the deep-eval folded that into SCHED-P2's inactivity watchdog because it only matters once a timeout fires; it stays in SCHED-P2. Do not build the scheduler dashboard page (list/history/cancel UI), the weekly digest additions, or the webhook normalizer — the deep-eval reassigned those to SCHED-P6's ship-now subset. Do not add a pause feature: no pause state exists in engine.py today, so the re-read only needs to honor states the engine can actually write ('cancelled' plus the terminal set); inventing pause machinery is SCHED-P6 surface work. No migrations, no receipt-format back-compat shims (no users yet — leave superseded receipts on disk unread). No launchd/supervisor registration, no ESTOP, no auto-disable streaks (SCHED-P3/P5 scope).

## 5. Target files
- `halbert_core/halbert_core/scheduler/executor.py`

## 6. Dependencies

Verify R-03

## 7. Effort

**S** — S (small) is correct and the deep-eval agrees (it sized each residual item S). Each of the three fixes is a localized change in one or two files with an existing home: the re-read is ~15 lines at the head of an existing wrapper plus deleting one divergent route call; the start-time fingerprint is one added field on an existing dict plus one comparison in an existing liveness probe; the permissions fix is two chmod calls in code paths that already centralize directory creation and atomic writes. There are no new subsystems, no new dependencies (the psutil question is resolved by preferring a tiny sysctl helper or an existing optional import — adding a third hard dependency is explicitly out of bounds), and no cross-module coordination beyond the one route-convergence edit. It is opus-tier only because it touches durability semantics and requires the verify-R-03-first judgment, not because the code volume is large. The dominant cost is care around the merge-state verification and test design (simulating pid reuse and out-of-band cancel), not implementation.

## 8. UX rationale

Nothing in this packet adds a user-facing surface, copy, colour, or control — it is all below the dashboard. The two user-perceptible behaviors it repairs, both experienced through the existing scheduler UI and the machine's first-person voice: (1) when the user cancels a scheduled job from the dashboard, the job actually stops firing — today, cancelling through one of the two routes leaves the job running on its cron, which reads to the user as the machine ignoring an instruction; after the fix, the one conversation can truthfully say the job is stopped, grounded in the durable record. (2) After a reboot or crash, the machine's account of what ran is honest: a stale 'running' receipt from a previous boot is correctly recognized as interrupted instead of being masked by a reused pid, so any first-person statement about whether a job completed is grounded in measured state (pid plus process start time) rather than a pid coincidence. No new notifications, no staged commands, no model judgments, no emoji, no new tokens — the fixes only make existing claims the system already makes (cancel confirmation, run history) stop being false in edge cases. Per the standing rules, any user-visible sentence about these states stays deterministic template text, never model-generated.

## 9. Acceptance criteria

1) Fire-path authority: a job whose durable record is 'cancelled' never executes its task callable, regardless of which cancel path was used — specifically, calling the engine-level cancel (the jobs.py:110 route's path) followed by the APScheduler trigger time passing results in zero invocations of the task and a logged refusal, with the receipt store showing no new 'running' receipt for that fire. 2) Single cancel choke point: dashboard/routes/jobs.py and dashboard/routes/settings.py cancel endpoints both terminate the live APScheduler job (verifiable by `get_scheduled_jobs()` no longer listing the id after either route is exercised). 3) Owner identity: a receipt written with pid P and start-time T is marked 'interrupted' by recover_on_boot when probed in an environment where pid P exists but its create_time differs from T (pid-reuse simulation), and is left 'running' when pid P exists with matching create_time. 4) Permissions: the scheduler persist dir has mode 0700 and every job JSON plus receipts.json has mode 0600 after any write, including on a fresh install where the dir is created by this run. 5) No regression: the existing scheduler suite (test_scheduler_executor.py, test_scheduler_receipts_wiring.py, scheduler/test_run_receipts.py, test_scheduler_atomic_write.py) passes with the arch -arm64 prefix, and any delta versus the pre-change baseline run is attributable only to the new tests. 6) R-03 verification artifact: the packet records in its commit body whether fix/remediation-sonnet-batch-1 was merged at execution time and which residual items were confirmed still absent after that check.

## 10. Verification (measured state, not model judgment)

Run the existing scheduler tests plus the new ones with the mandated prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_scheduler_executor.py halbert_core/tests/test_scheduler_receipts_wiring.py halbert_core/tests/scheduler/test_run_receipts.py halbert_core/tests/test_scheduler_atomic_write.py -x -q` (from the main tree; from a worktree use `arch -arm64 ./wt_pytest.py` with the same pathspec). The three new measured checks to add: (a) a test in test_scheduler_executor.py that cancels via `scheduler_engine.cancel_job(job_id)` directly (the divergent path), advances the trigger, and asserts the task callable's invocation counter is still zero and no new receipt entered 'running'; (b) a test in scheduler/test_run_receipts.py next to `test_boot_recovery_default_pid_check` (line 90) that monkeypatches the create_time lookup to return a different value than the recorded one for a live pid and asserts recover_on_boot interrupts the receipt, then returns the matching value and asserts it does not; (c) a test asserting `stat.S_IMODE(os.stat(persist_dir).st_mode) == 0o700` and `== 0o600` for a job file and receipts.json after writes. Merge-state gate executed first and recorded: `git merge-base --is-ancestor a2d3c89f main && echo merged || echo unmerged` (and likewise for the R-03 tip) — the commit body must state the result and, if merged, the re-run of the residual check (`git diff main <r03-tip> -- halbert_core/halbert_core/scheduler/` showing no start_time field and no fire-path re-read) proving this packet is still needed. All checks are file-mode, invocation-counter, and receipt-status assertions — measured state, no model judgment.

## 11. Exclusions

Per-job fire fence / cross-process flock (HM16-M5) — deferred to a DECISIONS.md-recorded follow-up on consolidating to one shared engine on app.state; the deep-eval judged the flock the weakest residual and explicitly said not to build a lock server. Detach-teardown-on-timeout (OC14-C18) — folded into SCHED-P2's inactivity watchdog, where it only becomes meaningful once a timeout can actually fire. Scheduler dashboard page (list/history/cancel UI), weekly host-state digest additions, webhook URL normalizer — reassigned to SCHED-P6's ship-now subset. Auto-disable failure streaks, ESTOP sentinel, standing-order documents, endpoint preflight — SCHED-P3 scope. Bounded shutdown, unclean-exit sentinel, thaw reconnect, event-loop watchdogs, launchd registration — SCHED-P5 scope (the unclean-exit sentinel there is a state-db integrity check, distinct from this packet's receipt-owner fix). Pause-state machinery and user-created job shapes — SCHED-P6, gated behind founder decision 7. Receipt-format migration or back-compat reading of old receipts — forbidden by the no-users/no-migrations rule; old receipts are simply treated as unknown-owner and left on disk. Any psutil hard dependency — forbidden by the Haloysius two-dependency contract; use a sysctl helper or an already-optional import.

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
