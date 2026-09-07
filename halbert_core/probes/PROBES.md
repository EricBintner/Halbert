# PROBES.md — the red-seam probe battery (Packet 09 Phase B)

Hermes's postmortem pattern, applied to Halbert: reviewer-authored defect
reproductions as **standalone scripts** — no pytest fixtures, no framework —
where each probe prints one result line and the battery's state is a table
in this file, enforced by `halbert_core/tests/test_probe_registry.py`.

**The rule this battery enforces: probes document, they never fix.**  A
still-red seam is recorded with its status, full stop.  An executor who
quietly makes a test green inside this battery defeats its purpose.

## How to run

```
cd <worktree-root>
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python halbert_core/probes/<probe>.py
# or, as a set:
arch -arm64 ./wt_pytest.py halbert_core/tests/test_probe_registry.py -q
```

Each probe prints exactly one line `PROBE <id> <slug>: <VERDICT> -- <detail>`
and exits 0 when it ran to a verdict (verdicts: `FIXED`, `RED`,
`OBSERVED`); nonzero means the probe harness itself broke, which the
registry treats as a failure regardless of claimed status.  Probes refuse
to run under any interpreter but the project venv (`probes/_env.py`
bootstraps: strips the editable-install MetaPathFinder, pins THIS
worktree's package dir, asserts resolution).

## Empirical red-list collection (2026-09-07, this worktree @ fa22e7ed)

The historical number was **38 real red seams** on main (2026-09-01
triage: R06-F2 33, R06-F1 2, App Store licence gate 2, peerApi 1).  The
packet said collect today's list, don't trust the number.  Collected:

| Run | Invocation | Result |
|---|---|---|
| Run 1 | `arch -arm64 ./wt_pytest.py halbert_core/tests/ -q` | **12 failed** / 5585 passed / 651 skipped |
| Run 2 (canonical) | `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/ -q` | **0 failed** / **6233 passed** / 15 skipped / 6 xfailed |

Run 1's 12 reds decompose as:

- **4 subprocess-based tests** (`test_audit_continuity` x2,
  `test_crypto_storage::test_concurrent_first_starts_agree_on_one_identity`,
  `test_dashboard_main::test_module_help_exits_zero`): they spawn
  `sys.executable`, which under `wt_pytest.py`'s `#!/usr/bin/env python3`
  shebang is the BASE framework python — no venv packages → empty
  subprocess output / `No module named halbert_core...`.
- **5 route tests** (`test_device_routes` x1, `test_peer_pairing_security`
  x4): `TestClient(app, client=(host, port))` — starlette **0.41.2** (base
  interpreter) has no `client` kwarg; starlette **1.6.0** (venv) does.
- **1 timing-flaky test** (`test_scheduler_executor::
  test_one_time_job_runs_and_records_outcome`): red twice during
  collection (solo 11s, whole-file 13s), then green 5x solo and green in
  the canonical full run.
- **1 token-estimate-sensitive test** (`test_conversation_budget_receipt_
  slot` SMALL tier): red under the base interpreter's dependency set, green
  under the venv (see P-05).

**Today's real red count on main, canonical venv environment: 0.**  The
historical 38 are all green: the R06-F2/F1 fixes (commit 2f595bc0 hoisting
`response_modality`, commit 0a2c3dfd moving the defanged query to per-turn
context) are in and guarded by `tests/test_state_machine_rev06_seams.py`;
the licence gate filters self-referential extras (`_project_name` /
`_is_self_reference`); peerApi routes every fetch through `apiUrl()`.
(The repo-root `tests/` tree — a different suite, run separately — shows 12
red, all `ImportError` from a missing `sentence-transformers` extra:
environmental, not seams.)

## The battery

| Probe | Seam | Observed-on revision | Status |
|---|---|---|---|
| P-01 r06-f2-modality (`probe_p01_r06_f2_modality_no_builder.py`) | R06-F2 — `response_modality` resolved only in the prompt-builder arm, read by both → UnboundLocalError on every no-builder turn (Wyoming voice / non-dashboard embedder) | found 2026-08-30, fixed at 2f595bc0 (hoisted assignment); 33 tests red 2026-09-01; guards in `test_state_machine_rev06_seams.py` | fixed-red-on-main |
| P-02 r06-f1-defanged-query (`probe_p02_r06_f1_defanged_query_leak.py`) | R06-F1 — defanged query reset at the start of RESPONDING, not the start of the turn → turn N+1 planned against turn N's question | found 2026-08-30, fixed at 0a2c3dfd (moved to per-turn `ctx.defanged_query`); 2 tests red 2026-09-01 | fixed-red-on-main |
| P-03 licence-self-reference (`probe_p03_licence_self_reference.py`) | App Store licence gate counted the project's own extras (`halbert-core[...]`) as unregistered third-party deps, blocking every check — found 2026-09-01 (2 red in the repo-root suite); fixed on main via `_project_name`/`_is_self_reference` filtering | found 2026-09-01 (2 red in the repo-root suite) | fixed-red-on-main |
| P-04 peerapi-bare-fetch (`probe_p04_peerapi_bare_fetch.py`) | `lib/peerApi.ts` bare `fetch("/api/peers"`, `"/api/fleet"`, ...) → 404 in the Tauri webview — found 2026-09-01 (1 red, frontend suite); fixed on main, all 23 fetches route through `apiUrl()` | found 2026-09-01 (1 red, frontend suite) | fixed-red-on-main |
| P-05 receipt-small-open-loop (`probe_p05_receipt_small_open_loop.py`) | SMALL-tier receipt rendering flattens the producer-reserved `Open loop:` line into the one-liner (`test_a_real_receipt_keeps_its_open_loop_at_every_tier`) | collected 2026-09-07: red under the base interpreter only (token estimator differs); **green under the venv**; one-liner flattening vs contract is a reviewer decision, recorded not judged | observational |
| P-06 ocr-simple-text (`probe_p06_ocr_simple_text.py`) | OCR misreads its own synthetic fixture (`"Error: file not found"` → `"ErFor.' file not found"` under the base interpreter) | collected 2026-09-07: backend- and environment-dependent (tesseract); venv reads it correctly | observational |
| P-07 scheduler-one-time (`probe_p07_scheduler_one_time_job.py`) | one-time job outcome recording is load-sensitive (0.3s scheduling, 10s asserts) | collected 2026-09-07: flaky — red twice, green 5x solo and in the canonical run | observational |
| P-08 wt-pytest-interpreter (`probe_p08_wt_pytest_interpreter.py`) | `wt_pytest.py`'s `env python3` shebang runs the suite on the base interpreter (pytest 7.4 / starlette 0.41) instead of the venv (pytest 9.1 / starlette 1.6) — 12 phantom reds | collected 2026-09-07; changing the wrapper is a separate decision, recorded not made | observational |

Statuses: `fixed-red-on-main` = the seam's defect mechanism is absent on
main and the probe reports `FIXED`; `still-red` = the mechanism is live on
main and the probe reports `RED` (none today); `observational` =
environment- or load-dependent, the probe records what it saw (`OBSERVED`).

## Caveats

- Run 1's decomposition is interpreter forensics, not product truth: the
  four subprocess tests and the starlette kwarg failures would vanish under
  `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/` —
  but that exact invocation from a worktree hits the editable-install trap
  (imports the MAIN tree), which is why `wt_pytest.py` exists.  The trap
  and the shebang are two halves of one harness seam (P-08).
- P-07's flakiness was reproduced twice under load during collection only;
  the probe drives the path once and reports.  A race, if real, needs a
  dedicated load probe — not chased in this battery.
- The `test_probe_registry.py` self-check runs every probe as a subprocess
  under the venv python and asserts the verdict each status predicts, so
  the table above cannot rot silently.  If a probe's verdict changes, the
  registry fails and PROBES.md must be updated to match reality.