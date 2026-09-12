# PKT-DAEMON-01a — Single-instance flock + exit vocabulary + supervised() probe

Tier: **fable**   Milestone: **M0**   Effort: **S**
Collision lane: **E,F**   Merge order: **1/3 in E; 1/3 in F**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**DAEMON-01a** — Single-instance flock + exit vocabulary + supervised() probe.

## 2. User problem

Today a second Halbert backend can launch against the same data directory and silently run as a duplicate: two schedulers, two heartbeat loops, two terminal-pool reapers, and two writers against one SQLite conversation store — a data-corruption vector on a single-user single-host machine that is supposed to identify as one computer. Both entry paths deliberately make this easy rather than prevent it: `python -m halbert_core.dashboard --find-port` (halbert_core/halbert_core/dashboard/__main__.py:126,146-152) binds a fresh port and starts anyway, and the Tauri shell does the same in Rust (`choose_port`/`port_is_free`, halbert_core/halbert_core/dashboard/frontend/src-tauri/src/lib.rs:33-51), so a Finder double-launch or a stray dev server yields two live backends writing to one store. Separately, the process has no exit vocabulary: `main()` exits 0/1 only, so a supervisor (launchd/systemd) cannot distinguish "restart me" from "fatal config, do not restart," and there is no probe to tell `main()` whether it is running supervised at all — a prerequisite both for the deferred stuck-turn watchdog and for OC22-C10 launch-at-login.

## 3. What to build

DAEMON-01a ships three small mechanisms in the Python backend only.

1. Single-instance advisory lock. A new helper (suggested `halbert_core/halbert_core/dashboard/instance_lock.py`, or a small function inside `dashboard/app.py`) opens `<data_dir>/backend.lock` with `data_dir()` from `halbert_core/halbert_core/utils/paths.py:53` (honours `HALBERT_DATA_DIR`/`Halbert_DATA_DIR`, else XDG `~/.local/share/halbert`), creates the dir if needed, and takes a non-blocking exclusive `fcntl.flock(fd, LOCK_EX|LOCK_NB)` on macOS. `main()` in `halbert_core/halbert_core/dashboard/__main__.py:109` acquires it right after `guard_bind(...)` (line 167) and before `create_app(enable_cors=True)` (line 169). The fd is held open for the process lifetime (module-level reference; closing it releases the lock). On contention, per founder decision FD 1 the second launch ATTACHES to the incumbent rather than spawning: it logs the incumbent's lock-file path and pid, prints the ticket URL it would have served, and exits 0 without calling `uvicorn.run` (never binds a second port). If FD 1 is instead ratified as refuse, exit 78 with a clear message. The lock is keyed to the data dir, not the port, so it also catches the Tauri double-launch case (same data dir, different shell) — though Tauri-side port scanning in lib.rs is out of scope here (see exclusions).

2. Exit vocabulary. Two module constants, e.g. `EXIT_RESTART = 75` (EX_TEMPFAIL) and `EXIT_FATAL_CONFIG = 78` (EX_CONFIG), placed where `main()` can use them. Wire the failure sites that already exist in `main()`: the `RuntimeError` from `find_available_port` (line 152) and the `uvicorn` ImportError (line 198) become `sys.exit(EXIT_RESTART)`; the existing `guard_bind` refusal (auth.py, raised before line 169) and any malformed-config boot failure become `sys.exit(EXIT_FATAL_CONFIG)`. Comment each with what a supervisor should do.

3. `supervised()` probe. A small function (suggested in the same new module) returning whether the backend runs under a supervisor: True when `HALBERT_PARENT_PID` is set (the Tauri sidecar path — the existing parent watchdog at `halbert_core/halbert_core/dashboard/parent_watchdog.py:66` already keys on this env var), or when `INVOCATION_ID`/`NOTIFY_SOCKET` (systemd) or a launchd marker is present. `main()` consults it so exit 75 means "restart me" only when supervised; on a bare terminal it prints the reason and exits 78/0 without implying a supervisor will act.

## 4. What NOT to build

No Tauri/Rust changes: `lib.rs` port scanning (`choose_port`/`port_is_free`, lines 33-51), PID-reuse-safe backend identity `(pid, start_marker)`, and the boot forensics ring buffer are all folded into DIST-01's Tauri-side packaging track per the RESHAPE — DAEMON-01a touches only the Python `__main__.py`/`app.py` seam. No stuck-turn reclamation watchdog, no turn-cancel, no skip-reason enum, no `obs/audit.py` receipt: that is DAEMON-01b, deferred until the state-machine work (R-01/R-06/R-12 touches on `agents/state_machine.py`) settles, and sequenced to merge last in its wave. No `state_machine.py` contact of any kind. No systemd unit authoring, no launchd plist, no launch-at-login toggle (that is OC22-C10 / DIST-02 territory); `supervised()` only *detects* these environments, it does not install into them. No changes to the scheduler, heartbeat, terminal pool, or conversation store — the lock prevents their duplication, it does not modify them. No model involvement anywhere; this is pure process-lifecycle hygiene. No migrations, no back-compat shims, and no deletion of any existing file or data.

## 5. Target files
- `halbert_core/halbert_core/dashboard/__main__.py`
- `halbert_core/halbert_core/dashboard/app.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S (small). The whole unit is one new small module plus edits confined to `main()` in `__main__.py` (a ~95-line function) and optionally one helper in `app.py` — both named target files, neither a hot hub. `fcntl.flock` is stdlib and already the pattern used elsewhere for advisory locks (config_dir lock precedent noted in utils/paths.py:39-50's docstring about being.yml.lock). The exit-code change is two constants and swapping two existing `sys.exit(1)` calls. The `supervised()` probe is an env-var read mirroring the established `HALBERT_PARENT_PID` check in parent_watchdog.py. No new dependencies (satisfies the Haloysius two-hard-dependency contract). No founder decision blocks the mechanism itself — only the attach-vs-refuse *behaviour on contention* is gated (FD 1), and the packet builds the attach default while leaving the refuse path a one-line branch. Effort sits at the low end of S because the risky half of the original DAEMON-01 (stuck-turn watchdog on the hottest file in the tree, and all Rust work) was explicitly split away by the RESHAPE.

## 8. UX rationale

A second launch must never produce a second computer. On contention with FD 1's attach default, the person sees one plain line on stderr/stdout — the incumbent is already running, where its lock file is, and the ticket URL to open — and the duplicate exits cleanly; nothing binds a new port, so the browser the Tauri shell points at always lands on the one true backend. When refused (if FD 1 flips), the message says the data directory is already in use and names the lock path, in the computer's own first-person voice, never a stack trace. Exit codes are invisible to the person but load-bearing for the machine: a supervised restart after exit 75 is silent and expected; exit 78 leaves a clear log line stating which config fact was fatal, so the next `halbert doctor` (DIAG-01) or log read explains it. No new surface, no new colour, no emoji, no model name, no conversation element — this is process behaviour the founder notices only as the absence of a confusing duplicate.

## 9. Acceptance criteria

1. With a backend already running on a data dir, a second `python -m halbert_core.dashboard` against the same `HALBERT_DATA_DIR` does NOT bind a port and does NOT call `uvicorn.run`; per the attach default it exits 0 after printing the attach line, and the incumbent's port still serves. 2. The file `<data_dir>/backend.lock` exists while a backend runs and the advisory lock is held (a second process's non-blocking flock attempt fails). 3. The lock is released when the backend exits (a subsequent launch reacquires it immediately, no stale-lock refusal). 4. `main()` maps its existing failure sites to the new codes: no-available-port and missing-uvicorn exit 75; the guard_bind/config refusal exits 78. 5. `supervised()` returns True when `HALBERT_PARENT_PID` is set (the Tauri sidecar case) and under systemd/launchd markers, False in a bare terminal. 6. No second scheduler/heartbeat/terminal-reaper ever starts from a duplicate launch (the process exits before `create_app`'s startup event, so `start_scheduler_delayed`/`start_thread_tick_heartbeat`/`start_terminal_subsystem` never run). 7. No changes to `lib.rs`, `state_machine.py`, or any file outside the two named targets plus the one new helper module.

## 10. Verification (measured state, not model judgment)

Runnable, measured checks (no model judgement):

A. New unit tests, added under `halbert_core/tests/` (e.g. `tests/dashboard/test_instance_lock.py`), run with the repo's required prefix:
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/dashboard/test_instance_lock.py -q`
   asserting: (i) a held flock on a tmp `backend.lock` makes a second acquire raise/return busy (measured by the second `flock` call failing); (ii) the lock is reacquirable after the holder's fd closes; (iii) `supervised()` returns True with `HALBERT_PARENT_PID` set and False with it unset; (iv) the contention path in `main()` (uvicorn.run mocked) exits 0 without the mock being called — measured by the mock's call_count == 0 and SystemExit.code == 0.

B. A two-process integration check (script or test) that boots a real backend on a throwaway `HALBERT_DATA_DIR` and random free port, waits for the port to answer `/api/health` (HTTP 200), then launches a second `python -m halbert_core.dashboard` with the same data dir and asserts: the second process's exit code is 0 and it never opens a listening socket (verified by attempting to connect to the port it would have taken and by the absence of a second bound port via `lsof -iTCP -sTCP:LISTEN -P` or a connect-scan), while the first backend still answers 200. This measures bound-port state, not a verdict.

C. The existing suite still passes for the touched seam:
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "parent_watchdog or spa_routes or route_auth_census" -q`
   to confirm no regression in the startup/auth surface `__main__.py` and `app.py` share (note: `main` carries a known nonzero baseline of failures per CLAUDE.md; take a baseline run on the merge-base first and diff against it, do not read a red suite as caused by this unit).

## 11. Exclusions

Split per the deep-eval RESHAPE of DAEMON-01 (deep-eval-group4-dashboard-testing-other.md, DAEMON-01 verdict). Stuck-turn reclamation watchdog (no-progress turn cancel, closed skip-reason enum `awaiting_confirm`/`approval_pending`, one typed receipt per reclamation to `obs/audit.py`) → DAEMON-01b: deferred until the opus-tier state-machine work (R-01 interrupt algebra, R-06 turn digest, R-12 session tree — all touching `agents/state_machine.py`) settles, and merges last in its wave; the section file names state_machine.py 'the fourth touch on the file.' PID-reuse-safe backend identity `(pid, start_marker)` so an orphaned sidecar exits on pid recycling → DIST-01 (Tauri-side). Boot forensics ring-buffered stdout/stderr tail surfaced in a native dialog for Finder-launched import-time tracebacks → DIST-01 (Tauri-side). Any change to `lib.rs` port scanning or sidecar spawn → DIST-01. launchd/systemd unit authoring and launch-at-login → OC22-C10 / DIST-02 (`supervised()` here only detects). Nothing is dropped outright; every split piece has a named home. DAEMON-01a depends on none of these and ships now.

---

## OSS reference

hermes single-instance + supervised probe; read F01.

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
