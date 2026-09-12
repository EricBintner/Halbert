# PKT-OTHER-P4 — Bounded-execution deadline helper

Tier: **fable**   Milestone: **M0**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**OTHER-P4** — Bounded-execution deadline helper.

## 2. User problem

Halbert has no single bounded-execution primitive, and the ad-hoc mechanisms it does have are broken in three concrete ways. (1) The scheduler's `_call_with_timeout` at `halbert_core/halbert_core/scheduler/executor.py:62-86` runs the job on a daemon thread and joins with a timeout, but when the deadline passes the worker thread keeps running with live side effects while the caller raises `TimeoutError` — the run receipt is marked `'error'` (not `'timeout'`) and the retry path can start a second copy of the same job, so one job can run twice concurrently against the conversation store (audit A06's own-bug, confirmed in the deep-eval). (2) `halbert_core/halbert_core/utils/retry.py:300-339` ships a `retry_with_timeout` that arms a process-global `SIGALRM` handler — main-thread-only, unsafe on APScheduler's worker pool — and it has zero production callers: dead unsafe code waiting to be misused. (3) `halbert_core/halbert_core/agents/error_recovery.py:110-135 classify_error` substring-matches only `str(error)` and `type(error).__name__` and never walks `__cause__`/`__context__`; with 29 `raise ... from e` sites in the core, a wrapped `TimeoutError` or `ConnectionError` falls through to `ErrorType.UNKNOWN` and gets the wrong backoff strategy. Three consumers already need a shared helper: the scheduler executor timeout, the R-07 domain (execute_code monitor loop has no deadline when the worker survives KeyboardInterrupt injection, A04-G1), and the R-15 domain (eval judge timeout, A02-G7). Verdict in the final backlog: ACCEPT, Wave-0 cross-cutting primitive (§3.12), effort S.

## 3. What to build

One new module `halbert_core/halbert_core/utils/deadline.py` plus a migration, a deletion, and an error-classification fix.

1. `utils/deadline.py` exposing four functions:
   - `clamp_timeout(value: Optional[float], *, default: float, floor: float = 0.0, ceiling: Optional[float] = None) -> float` — normalises caller-supplied timeouts (None/negative/non-finite → default; clamps to floor/ceiling). This is the single place timeout normalisation is decided, so every consumer stops hand-rolling `if timeout_s and timeout_s > 0` checks like the one at `executor.py:81`.
   - `run_bounded_sync(func: Callable[[], T], timeout_s: Optional[float], *, job_id: str) -> T` — the thread-join pattern lifted from `executor.py:62-86`, generalised: daemon worker thread named `halbert-job-{job_id}`, join with deadline, raise `TimeoutError` carrying the job_id when the worker survives, propagate worker exceptions unchanged. Docstring states the abandonment contract: on timeout the worker is still running and must be treated as abandoned by the caller.
   - `run_bounded_async(coro: Coroutine[Any, Any, T], timeout_s: Optional[float]) -> T` — `asyncio.wait_for` wrapper applying `clamp_timeout` semantics and raising the same `TimeoutError` shape as the sync flavour so callers can catch one type.
   - `kill_process_tree(pid: int, *, grace_s: float = 2.0) -> None` — SIGTERM to the process group (children first), wait up to `grace_s`, escalate to SIGKILL, reap. Reuses the escalation ladder already proven in `streaming/pty.py:406 _escalate_kill` — do not invent a second ladder (final backlog §3.1 names this the shared pattern).

2. Migrate `scheduler/executor.py:_call_with_timeout` to delegate to `run_bounded_sync`. At the call site in the executor's job-run path, catch the `TimeoutError` separately and (a) record `status='timeout'` on the run receipt via `RunReceiptStore.mark_finished` (`scheduler/run_receipts.py:157`) instead of folding it into `'error'`, and (b) mark the worker abandoned so the retry decorator (`_on_retry` at `executor.py:769`) does not schedule a second attempt for a job whose thread is still alive — the abandonment flag is checked before retry.

3. Delete `retry_with_timeout` from `utils/retry.py` (lines ~300-339) outright — zero callers, and the SIGALRM approach is process-global and main-thread-only. No shim, no deprecation: no users exist, and the standing rule is no back-compat shims unasked.

4. Fix `agents/error_recovery.py:110-135`: add a `ClassifiedError(Exception)` carrying an explicit `error_type: ErrorType`, and a `_walk_causes(exc) -> Iterator[BaseException]` that yields `exc`, then walks `__cause__`, then `__context__`, with a `seen` set against cycles. `classify_error` first checks whether any exception in the chain is a `ClassifiedError` and returns its `error_type` directly; otherwise it applies the existing substring ladder to every exception in the chain (not just the outermost) and returns the first hit. Scope: classification only — `execute_with_retry` picks up the corrected verdicts with no signature change.

5. Record the fatal/transient/config-error taxonomy (OC02-C12) as a short design note in the module docstring of `utils/deadline.py` only: name the `EX_CONFIG=78` exit-code convention and state that the taxonomy lands when a top-level handler exists. Do not build the handler.

Pure-stdlib (threading, asyncio, os, signal) — the two-hard-dependency contract is untouched.

## 4. What NOT to build

- No top-level fatal/transient/config exception handler — OC02-C12 is a design note only; the handler does not exist and the section file says "not dispatchable alone." Deferred until the handler exists.
- No process-killing of the abandoned worker thread in `run_bounded_sync` — Python cannot kill threads; the contract is abandonment-plus-retry-suppression, not forced termination. `kill_process_tree` exists for the subprocess case, not threads.
- No migration of OTHER consumers (execute_code monitor loop A04-G1, eval judge timeout A02-G7, web fetches). Those are their own units: A04-G1 belongs to the execute_code/R-07 follow-on, A02-G7 to the eval-harness/R-15 follow-on, and OTHER-P5's bounded downloads is a separate packet (also flagged for coordination on `executor.py` in the final backlog). This unit builds the primitive and proves it on exactly one consumer (the scheduler executor).
- No `QueueListener`, no async logging, no receipt-schema change beyond accepting `'timeout'` as a status value.
- No third bounded-execution flavour (no signal-based, no multiprocessing-based) — one sync, one async, one process-tree kill. The standing rule forbids duplicate primitives.

## 5. Target files
- `halbert_core/halbert_core/utils/deadline.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S, as assigned. The deep-eval prices it M-for-helper-plus-migration + S-for-classification, but the helper is ~60 lines of stdlib code whose pattern already exists at `executor.py:62-86` and is being moved, not invented; the migration is one call site plus a status-string change at the receipt write; the deletion is confirmed zero-caller; the classification fix is ~25 lines inside one method with no signature change. There is exactly one hot-file risk: `scheduler/executor.py` was touched by R-03 (scheduler durability, sonnet branch `fix/remediation-sonnet-batch-1`, verified NOT merged to main as of the §0 correction in the final backlog). R-03 added receipt/idempotency machinery around this same code path, so the migration must rebase against the current `executor.py` at dispatch time and must not assume R-03's receipt vocabulary is on main — check `git log main --oneline | grep -c 55ecef87` confirms only the opus batch merged. If R-03 merges before this dispatches, re-verify that `status='timeout'` and the abandonment flag do not collide with R-03's receipt protocol; the final backlog flags the same overlap note ("If R-03 closed it, the deadline helper is still valuable for the async flavour and clamp normalisation"). Tier fable: pure Python, no UI, no model involvement, deterministic behaviour.

## 8. UX rationale

No user-facing surface. This is invisible plumbing; nothing renders, nothing is staged, no copy exists. The one operator-visible effect is diagnostic honesty: the scheduler's run history (`halbert job history` / the jobs surface fed by `RunReceiptStore`) now shows a job that overran its deadline as `timeout` rather than a generic `error`, and no second copy of the job silently runs alongside the first — which is the machine reporting measured truth about its own execution, consistent with the "grounded in measured data, speaks as the computer itself" frame. No model is named anywhere; the helper is deterministic; no emoji, no colour tokens, no templates. The deleted `retry_with_timeout` removes a footgun a future session could have wired in unknowingly.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/utils/deadline.py` exists with `clamp_timeout`, `run_bounded_sync`, `run_bounded_async`, `kill_process_tree`, each with docstrings naming the abandonment contract and the `EX_CONFIG=78` convention note.
2. `scheduler/executor.py` no longer defines its own thread-join logic; `_call_with_timeout` delegates to `utils.deadline.run_bounded_sync`, and a deadline overrun writes `status='timeout'` to the run receipt and suppresses the retry that would have launched a second copy.
3. `grep -rn "retry_with_timeout" halbert_core/` returns zero hits (definition and all references gone).
4. `agents/error_recovery.py classify_error` resolves a `ClassifiedError` found anywhere in a `__cause__`/`__context__` chain, and the substring ladder applies to every exception in the chain; a wrapped `TimeoutError` (e.g. `raise RuntimeError("boom") from TimeoutError("t")`) no longer classifies as `ErrorType.UNKNOWN`.
5. No new imports beyond stdlib in `utils/deadline.py`; `pyyaml`/`requests` contract untouched.
6. Module docstring records which consumers are documented adopters (scheduler executor now; execute_code monitor and eval judge as named follow-ons) so no second bounded-execution helper gets built.

## 10. Verification (measured state, not model judgment)

New tests at `halbert_core/tests/test_deadline.py` plus one updated classification test, run with the repo's mandated invocation:

`cd /Volumes/4TB-BAD/Halbert && arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_deadline.py halbert_core/tests/agents/test_error_recovery.py -x -q`

Measured assertions the suite must contain:
- `test_run_bounded_sync_timeout_leaves_receipt_timeout`: a func that sleeps 5s run with `timeout_s=0.1` raises `TimeoutError`; the fake `RunReceiptStore` records `mark_finished(status='timeout')` (not `'error'`), and the retry callback is never invoked (count == 0).
- `test_run_bounded_sync_success_passthrough`: func returning 42 under a 5s bound returns 42 and no receipt is written.
- `test_run_bounded_async_timeout`: a coroutine sleeping 5s bounded at 0.1s raises `TimeoutError`; `asyncio` task count returns to baseline after the test (no leaked pending tasks — `len(asyncio.all_tasks())` compared before/after).
- `test_clamp_timeout_normalises`: `clamp_timeout(None, default=30) == 30`, `clamp_timeout(-5, default=30) == 30`, `clamp_timeout(float('nan'), default=30) == 30`, `clamp_timeout(1e9, default=30, ceiling=300) == 300`.
- `test_classify_error_walks_cause_chain`: `classify_error(RuntimeError("wrapper"))` where the wrapper has `__cause__ = TimeoutError("t")` returns a timeout ErrorType, never `ErrorType.UNKNOWN`; a `ClassifiedError(ErrorType.NETWORK_ERROR)` buried two `raise ... from` levels deep returns `NETWORK_ERROR`.
- `test_retry_with_timeout_is_gone`: `import halbert_core.utils.retry; assert not hasattr(halbert_core.utils.retry, 'retry_with_timeout')`.
- Exit code of the pytest run is 0, and the collection count for `test_deadline.py` is >= 6 (measured from the pytest summary line).

Regression guard: the full suite `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q` must not increase the known main baseline failure count (memory records 71 baseline failures on main, 38 real; capture `git merge-base` baseline first per CLAUDE.md — `main` is not green, so compare counts, not zero).

## 11. Exclusions

- execute_code monitor-loop deadline (A04-G1) → follow-on to the R-07 domain; this unit ships `kill_process_tree` and the sync bound it will consume, but does not touch `tools/execute_code.py`.
- Eval-judge timeout (A02-G7) → follow-on to the R-15/eval-harness domain; same reasoning — consumer adoption, not this unit.
- Bounded downloads / `homebrew.py` / `web_search.py` fetch caps → OTHER-P5 (RESHAPE, separate packet); the final backlog explicitly tells OTHER-P5 to coordinate with this unit on `executor.py`, not merge into it.
- Fatal/transient/config-error taxonomy implementation (OC02-C12) → deferred per the deep-eval ("not dispatchable alone"); recorded here as a docstring design note carrying only the `EX_CONFIG=78` convention so DAEMON-01a's exit-vocabulary work picks it up consistently.
- Process-group escalation ladder generalisation (`utils/process_group.py`) → final backlog §3.1 names it a separate Wave-0 candidate shared by TT-01/SCHED-P2/MCP-A; `kill_process_tree` here follows the `streaming/pty.py:406` pattern but does not claim to be that shared module — if §3.1 lands first, `kill_process_tree` should delegate to it; if this lands first, §3.1 absorbs this function.
- Thread killing / forced cancellation of abandoned workers → dropped as impossible in CPython; the abandonment-plus-retry-suppression contract replaces it (this is the RESHAPE-era correction the deep-eval ratified: the bug is the receipt lying and the retry duplicating, not the thread living).

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
