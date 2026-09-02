# RESULTS — SONNET-01 security-merge dispatch (2026-09-02)

**Packet:** `DISPATCH-2026-09-01-SONNET-01-security-merge.md`
**Worktree used:** `~/.config/superpowers/worktrees/Halbert/sec01` (branch `chore/security-review-01-merge`), removed after merge.
**Final local main head:** `0c894e4c` (fast-forwarded from `ad0cb372`, 12 commits ahead). **Nothing pushed to origin** — `origin/main` remains at `ad0cb372`, confirmed via `git rev-list --left-right --count origin/main...main` → `0  12` immediately before finishing.

---

## Task 1 — Merge `feat/security-review-01`

Merge commit: `909b56c4` (`merge: feat/security-review-01 into main`).

- Exactly one conflict, as the packet predicted: `halbert_core/tests/test_mcp_server.py`. `server.py` and `redaction.py` auto-merged clean.
- The current-main version of the conflicted test file was confirmed to be a pure subset of the packet's stale (old-main) reference resolution — a diff between them showed zero deletions/changes, only the three expected additions (`TestPathAllowlist` class + two `_load_latest_snapshot` monkeypatch inserts). Used the reference file directly.
- Verification: `test_mcp_server.py`+`test_redaction_gaps.py` → 90 passed. Second batch (`test_tier2_guarantee.py test_mcp_response_boundary.py test_mcp_http.py test_security_roles.py test_config_queries.py test_cli_security.py test_secure_response.py test_redact.py`) → 158 passed.
- Added the "path must be in the host's config snapshot manifest" precondition note to `get_config_value`/`get_config_structure`/`get_config_dependencies` tool descriptions (`c36ae12e`).
- Tried the suggested `_is_allowed_config_path` mtime-cache optimization (step 5, marked optional) — **reverted it**. It went stale whenever the data source (`_load_latest_snapshot`) was swapped without the underlying file's mtime changing, which is exactly what test monkeypatching does (and would equally miss a same-mtime rewrite in production). Left a docstring note explaining why the naive re-read-every-call version stays; not worth the correctness risk for a P3 "if trivial" optimization.
- Updated `.handoff/SCOPE-01-SECURITY-REVIEW-PROGRESS.md` §6 with the merge sha and an enumerated list of main-side work the branch predated (Opus 01-05 batch, SONNET-02 cleanup, and the specific security/config shas named in the packet).
- Did not commit the branch's two untracked docs (obsolete, per the packet).
- Fast-forwarded local main, deleted `feat/security-review-01`, removed its worktree (had to run `worktree remove` before `branch -d` — the reverse order errors).

## Task 2 — `R1-F4` `set_autonomy_level` race (commit `f41d7124`)

`_tool_set_autonomy_level` did `cfg = load_being_config(); ...; save_being_config(cfg)` — two separate lock cycles with an unprotected window between them. Rewrote it to pass a mutator into `update_being_config` (one exclusive lock spanning the whole load-modify-save), matching the pattern `settings.py`'s dashboard route already uses. The phrase-required rejection now raises a private exception inside the mutator to abort the composite (nothing persisted) instead of returning early after a bare load.

New test `TestSetAutonomyLevelRace` hooks `being_config_lock` itself (the one primitive both the old and new code paths go through) so a genuine concurrent load-modify-save fires the instant the first lock cycle here releases — this reproduces the clobber against the old two-cycle implementation (confirmed by temporarily reverting the fix and re-running: fails as expected) and confirms the fixed single-cycle version can't lose it. Updated `TestAutonomyEscalationPhrase`'s `_patch_being` fixture to fake `update_being_config` instead of `load_being_config`/`save_being_config`, since the tool no longer calls those directly — otherwise all 5 of its tests broke (confirmed, then fixed).

## Task 3 — `R2-P3` id-less `tools/call` executes (commit `cfdfc727`)

`handle_request` ran the tool handler unconditionally on `tools/call` and only checked `is_notification` afterward to decide whether to respond. Moved the `is_notification` check to the top of the branch so a notification never reaches `TOOL_HANDLERS` at all — a notification tool call could otherwise still execute a side-effecting tool (`run_scanner`, `approve_proposal`); the caller just never learned the result, which is the bug, not a feature.

Extended `test_notification_tools_call_no_response` to assert the handler itself was never invoked (spy on `TOOL_HANDLERS["get_vitals"]`). This surfaced a **regression** in an unrelated, pre-existing test — `test_tier2_guarantee.py::TestDispatchChokePoint::test_notification_tools_call_still_wraps` — which pinned the *old* intended behavior ("handler runs, response is discarded"). Renamed it `test_notification_tools_call_never_dispatches`, updated its assertion and the module's docstring to describe the new (correct) guarantee, and confirmed the full suite returns to the exact original 26-failure baseline afterward (diffed test-by-test, zero difference).

## Task 4 — Unredacted rebuild gate (SEC-03/04/11) (commit `b2e69190`)

**Code, all done:**
- Rewrote `scripts/rebuild_sourceprep_unredacted.py` step 2 to call `SourcePrepSetup().apply(redact_host=False, build_fast_sync_only=True)` against the unified `halbert` project (confirmed id `735a592e-a2da-499b-a614-854a5fc461f5` via `GET /projects`), instead of `register_host_project()`, which targets the legacy, retired `halbert-host` project. `build_fast_sync_only=True` re-stages `host/` and does an incremental fast_sync + CodeIndex build only — it does not touch `knowledge/`'s deep_enrichment, so this config-only rebuild never re-embeds the ~16K-doc corpus.
- Made the egress check's boundary 2 lock-aware, per the packet's caveat: boundary 2 goes through `_tool_get_config_value -> load_being_config()` — the host's REAL current secret tier — unlike boundary 1, which always probes the hardcoded `local_only` default. If the host is unlocked (`cloud_ok_acknowledged`, unexpired), a value crossing via the legitimate `_egress_ack` hatch is not a leak; it's now downgraded to an informational note in the report instead of a false `exit(2)`. A leak while the host is genuinely locked still hard-fails. New test file `test_rebuild_sourceprep_unredacted.py` (2 tests) proves both branches, and confirms (by temporarily reverting the script) that the "downgrade" test fails against the old, non-lock-aware code.
- Added an autouse `conftest.py` fixture (`_isolated_config_canon_store`) redirecting `CANON_DIR`/`SNAP_DIR`/`RAW_DIR` — and their independent copies in `queries.py`/`drift.py`/`edge_extractor.py`/`indexer.py` (each holds its own binding; patching `snapshot.py`'s globals alone doesn't reach them) — to a per-test `tmp_path`. Confirmed via a targeted rerun of the config-heavy test files that the real store stays empty afterward.
- Cleared the real `~/.local/share/halbert/config/{canon,snapshots,raw}` store: every single record in it (3 canon files, 1 snapshot, 4 raw texts) was pytest tmp-path junk on inspection — including one MORE that leaked in from my own baseline run before the conftest fix landed. Wiped clean; re-verified it stays clean after running the relevant test suites.

**Operational run — dry-run done, real run deliberately deferred:**
- `--dry-run` succeeded cleanly: daemon reachable, token present, manifest found, correct project targeted.
- Before the real run I checked for a live collision per the packet's explicit warning (`ps aux` for `staged_knowledge_embed`/`prep.cli`, plus the daemon's own `/pipeline/status` and `/status` endpoints). Found: `pipeline/status` reports `any_running: true` for the `halbert` project, persisting unchanged across a multi-hour gap (this session was interrupted by an account-wide rate limit mid-task and resumed later — re-checked both before and after, identical result); `/status` for the `halbert` project times out completely (confirmed twice, 5s and 15s timeouts, ~1hr apart); `/status` for a second, completely unrelated project (`SourcePrep`, id `f1636374-...`) **also** times out — so this isn't specific to our project, it's a daemon-wide symptom. Meanwhile the daemon process itself (`prep.cli serve --port 8400`, pid 89851) shows negligible CPU (0.1%), not the profile of a genuinely busy build.
- Given the packet's own explicit caution ("a previous collision froze the machine") and this daemon — shared live by ~9 other concurrent `prep mcp` client processes on this machine — showing a reproducible, daemon-wide broken/hung endpoint plus a persistently-stuck `any_running` flag, I judged it unsafe to fire the real unredacted-rebuild `apply()` call right now: either it queues behind whatever's already wedged (my run just hangs) or it collides and risks exactly the freeze the packet warns about, affecting every other live session on the shared daemon.
- **This is the one item from the packet I did not complete.** Recommend the founder/coordinator check the SourcePrep daemon's health (a restart of `prep.cli serve` is the likely fix for a stuck `/status` handler) before attempting the real run — I did not restart it myself since it's shared infrastructure other live sessions depend on and that's outside a security-merge packet's scope to touch unilaterally.

## Task 5 — Low residuals

Done:
- **R2-P5** (commit `b8672fa6`) — `_check_auth`'s `auth.startswith("Bearer ")` was an exact-case match; RFC 7235's auth-scheme is case-insensitive. Fixed to `auth[:7].lower() == "bearer "`; token comparison stays exact/constant-time. New parametrized test (`bearer`/`BEARER`/`BeArEr` all authenticate; `Basic` still rejected).
- **R2-OBS-1** (commit `6ea9b0c5`) — `mcp/__init__.py`'s docstring claimed `camera_gate.py` actively strips image data from responses. It doesn't: `TOOL_HANDLERS` registers no frigate/vision/camera tool at all, so nothing calls `gate_response()` or any handler in that file — it's tested in isolation but unreachable from a real request. Not a live gap today (no camera-data tool surface exists to leak through), but corrected both docstrings so it isn't a landmine for whoever adds one.
- **R2-P4** (commit `363a2999`) — `run_stdio` used `for line in sys.stdin:`, an unbounded readline; a malfunctioning or adversarial peer never sending a newline grows the buffer without limit. Replaced with bounded `readline(max_line)` reads (1MB cap, matching the HTTP transport's `_MAX_REQUEST_SIZE`); an oversized/unterminated line is rejected (`-32600`) and drained in bounded chunks so the stream resyncs at the next newline. 3 new tests.
- **NEW-01** (commit `0c894e4c`) — documented, not fixed. `response.py`/`queries.py` both claimed `_egress_ack` is "set only by `get_config_value`" as if enforced; it isn't — `_redact_dict` honours the marker on any dict at any depth purely by structural shape. Did **not** narrow this: the existing test suite (`test_egress_ack_does_not_leak_to_sibling_dicts`, `test_nested_secret_dict_keys_still_redacted_under_marker`) deliberately exercises and relies on the current at-any-depth behavior for nested/multi-result payloads, so scoping the exemption to a provenance-checked top-level-only check is a real design decision, not a mechanical P3 fix, and risks breaking a currently-intended contract. Documented as a known risk in both files instead.

Explicitly skipped:
- **R2-P1 / R2-P2** — both live in `halbert_core/halbert_core/federation/peers_config.py`. The packet's Coordination section states "OPUS-03 owns `federation/**`"; even though R2-P1/P2 are listed in my Task 5 checklist, I judged the ownership line as the controlling instruction (only R2-F6 was called out as a *specific example* of what to leave, not an exhaustive list) given the real risk of colliding with concurrent federation work on the shared main checkout. Left untouched.
- **R2-F2b** (no socket timeout on the HTTP handler) — not attempted; ran out of allotted time after the above.
- **SEC-14** (SourcePrep daemon `/projects` answers with no bearer) — per the packet, report only, not a fix for this packet (CoDRAG's). **Reporting it here**: confirmed still true — `GET http://127.0.0.1:8400/projects` was called with `auth_headers()` throughout this session's checks, but worth flagging to the founder that this is a known, unaddressed gap.

## Test counts

- **Fresh baseline** (before any change, full suite via `wt_pytest.py halbert_core/tests`): **26 failed, 4679 passed, 40 skipped** (95.5s). This supersedes the stale 71-failure baseline from the old audit doc — the Opus 01-05 batch already fixed most of those.
- **Final** (after all commits above): **26 failed, 4701 passed, 40 skipped** (101.8s). The 26 failing test names are byte-identical to the baseline list (`diff` against the saved baseline file returns empty) — zero new failures, +22 net new passing tests from this packet's additions.
- The 26 pre-existing failures are all unrelated to this packet's scope (corpus license gate, cv_extensions/motion detection needing `cv2`, llm_config layering/parse-cache, llm_discover/routes fresh-install flows, multi_instance home endpoint, vision_tools OCR, frontend relative-URL lint) — left untouched, as instructed.

## State pending push

Local `main` is at `0c894e4c`, 12 commits ahead of `origin/main` (still at `ad0cb372`), 0 behind. **Nothing was pushed** — confirmed via `git rev-list --left-right --count origin/main...main` → `0  12` as the last check before finishing. The `chore/security-review-01-merge` branch and its worktree have been deleted/removed after the fast-forward, per the same cleanup pattern as `feat/security-review-01`.

Commits, in order, now on main:
1. `909b56c4` — merge: feat/security-review-01 into main (Task 1)
2. `c36ae12e` — docs(mcp): tool-description precondition notes + Scope 01 progress doc (Task 1)
3. `f41d7124` — fix(mcp): route set_autonomy_level through update_being_config (Task 2, R1-F4)
4. `cfdfc727` — fix(mcp): reject id-less tools/call before dispatch (Task 3, R2-P3)
5. `b2e69190` — fix(sourceprep): retarget unredacted rebuild gate + conftest isolation (Task 4, SEC-03/04/11)
6. `b8672fa6` — fix(mcp): case-insensitive Bearer scheme match (Task 5, R2-P5)
7. `6ea9b0c5` — docs(mcp): flag camera_gate as unwired dead code (Task 5, R2-OBS-1)
8. `363a2999` — fix(mcp): bound stdio transport line reads (Task 5, R2-P4)
9. `0c894e4c` — docs(mcp): flag the _egress_ack marker as unenforced-provenance (Task 5, NEW-01)

## Residuals left open (for the next dispatch or founder review)

1. **Real unredacted-rebuild run** — deferred for daemon-health safety reasons above; run once the SourcePrep daemon's `/status` hang is investigated/resolved.
2. R2-P1, R2-P2 — federation/peers_config.py, left to OPUS-03's ownership.
3. R2-F2b — no socket timeout on the HTTP handler; not attempted, time-boxed out.
4. NEW-01 — documented, not fixed; needs a deliberate design decision (provenance-scoped egress-ack) if it's to be narrowed.
5. SEC-14 — SourcePrep daemon `/projects` with no bearer; report to founder, CoDRAG's to fix.
