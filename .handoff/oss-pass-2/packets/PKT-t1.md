# PKT-T1 — Hermetic test environment + live-DB guard

Tier: **fable**   Milestone: **M0**   Effort: **M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**T1** — Hermetic test environment + live-DB guard.

## 2. User problem

Halbert's pytest suite runs in one interpreter against the developer's live macOS host, and three confirmed defect classes let a test run touch state it must never touch. (1) Live-store leaks: `halbert_core/halbert_core/agents/conversation_sqlite.py:123-161` (`_default_db_path`) used to resolve the production `conversations.db` even when `HALBERT_DATA_DIR` was unset and a test constructed the store with no `db_path=`; a narrow PYTEST_CURRENT_TEST raise exists there now, but no other store/mkdir/pragma call site is guarded and no generalised `testing_guard` walks process ancestry. (2) Credential / env leakage: nothing scrubs `*_API_KEY`, `*_TOKEN`, `*_SECRET`, Halbert voice/TTS behavioural flags, or pins `TZ`/`LANG`/`PYTHONHASHSEED`; `HOME` is the developer's real `$HOME`, so any test that resolves `~/.config/halbert/...`, `~/.halbert/...`, or `~/Library/Application Support/...` reads host state. (3) Live-system blast radius: 28 test files import `subprocess` and many spawn for real; `streaming/pty.py:362,432` issues `os.kill(self._pid, SIGTERM/SIGKILL)`; `dashboard/routes/services.py` shells `systemctl stop/disable/restart`; `model/client.py`'s context probe spawns an unjoined background thread that outlives per-test mocks and reaches a real daemon (`tests/test_num_ctx.py:29-38` carries the warning comment). A test that accidentally fires a real kill, hits a non-loopback socket, or appends to the developer's `state_ledger.db` audit hash chain destroys the very evidence the audit trail exists to preserve. The full suite is also the prerequisite for T2 (isolated runner) and T4 (wire contracts); without hermeticity those packets inherit an unreliable baseline.

## 3. What to build

Edit `halbert_core/tests/conftest.py` (the only file in this unit). The file already carries autouse fixtures for canon-store redirection (`_isolated_config_canon_store`), capability-registry reset, workspace-layer delenv, `HALBERT_DATA_DIR`/`HALBERT_LOG_DIR` redirection, and skills-root replacement; the work is to add what is missing and to register one marker. Concretely:

1. **`_hermetic_environment` autouse fixture (function-scoped)** that:
   - `monkeypatch.delenv(...)` on `HALBERT_API_TOKEN` (it is re-pinned by `_authenticated_test_clients` at session scope — let that fixture win by ordering ours before it or by leaving the session-scoped value alone), every env var matching `*_API_KEY`, `*_TOKEN` (except the session-scoped `HALBERT_API_TOKEN`), `*_SECRET` present in `os.environ` at test start (snapshot the key list once at fixture entry, iterate, delenv).
   - `delenv`s Halbert's behavioural flags that would produce real synthesis or playback out of the developer's speakers (voice/TTS entry points — enumerate via `grep -n "os.environ" halbert_core/halbert_core/audio/ halbert_core/halbert_core/voice/` at build time and pin the literal list).
   - `monkeypatch.setenv("TZ", "UTC")`, `setenv("LANG", "C.UTF-8")`, `setenv("PYTHONHASHSEED", "0")` (the last is informational for child processes only; the interpreter's hash seed is fixed at startup and that is fine).
   - Redirects `HOME` to `tmp_path / "_home"` via `monkeypatch.setenv("HOME", ...)` so any `Path.home()` / `~/.config/...` resolution lands in the per-test tmpdir. Keep `HALBERT_DATA_DIR` and `HALBERT_LOG_DIR` pointing at their existing per-test tmpdirs (already set by `_isolated_data_and_log_dirs`).

2. **Egress-safety net (function-scoped autouse)** — patch `socket.socket.connect` so any non-loopback destination raises `RuntimeError("test attempted non-loopback egress to <host>:<port>; mark with @pytest.mark.allow_network to opt out")`. Allow `127.0.0.0/8`, `::1`, and `localhost`. Implement by wrapping the original `connect` and inspecting `address[0]` before delegating. Tests that legitimately need egress opt in via `@pytest.mark.allow_network`; register this marker in `halbert_core/pyproject.toml` under `[tool.pytest.ini_options].markers` (the section file explicitly notes this marker does not exist yet and must be added). The net must catch off-thread calls (the `model/client.py` context-probe leak), so patch the class attribute, not an instance.

3. **Generalised live-DB guard (`halbert_core/tests/testing_guard.py`, new module imported by conftest)** — the conversation store already has a narrow raise at `agents/conversation_sqlite.py:153-160` keyed on `PYTEST_CURRENT_TEST`. Generalise: a module-level `_assert_not_live(path)` that, when `PYTEST_CURRENT_TEST` is set AND `HALBERT_DATA_DIR`/`Halbert_DATA_DIR` is unset, raises before open/mkdir/pragma on any path that resolves under the real `utils.paths.data_dir()` or `Path.home() / ".halbert"`. Wire it into the conversation store's `_default_db_path` (replace the inline raise), the state ledger's `default_state_db_path`, and any `mkdir(parents=True)` on a data-dir path. FD-3 ruling: raise, name the path, name the bypass marker. Do not silently redirect.

4. **Live-system guard (function-scoped autouse)** — wrap `os.kill`, `os.killpg`, and `subprocess.Popen` so a call whose target pid belongs to a process outside the current test's process group, or whose argv[0] resolves to a denylist of killer executables (`kill`, `pkill`, `killall`, `systemctl`, `launchctl`, `shutdown`, `reboot`), raises `RuntimeError`. Permit the call when the target pid is the current process or a direct child spawned inside the test. `streaming/pty.py`'s `os.kill(self._pid, ...)` self-kill remains allowed because the PTY child is spawned by the test itself; the guard fires only on pids the test did not create.

5. **Marker registration** — add `allow_network: permit non-loopback socket egress for this test` to `halbert_core/pyproject.toml` `[tool.pytest.ini_options].markers` so strict-marker mode does not reject the opt-out.

Reference: the Hermes pattern at `tests/conftest.py:40-103` plus `hermes_state_guard.py` is the origin shape; do not copy verbatim — Halbert's conftest already has five autouse fixtures and the new work layers on top.

## 4. What NOT to build

Do not refactor or remove any existing autouse fixture in `conftest.py` — `_isolated_config_canon_store`, `_reset_capability_registry`, `_no_declared_workspace_layer`, `models_config_dir`, `capability_registry`, `_isolated_data_and_log_dirs`, `_authenticated_test_clients`, `_skills_user_root_is_not_the_developers` all stay exactly as they are; the new fixtures stack alongside them. Do not touch `agents/conversation_sqlite.py`'s WAL-reset diagnostic, schema, or migration logic — the only permitted change there is swapping the inline `PYTEST_CURRENT_TEST` raise at lines 153-160 for a call into the new `testing_guard` module, preserving its message contract. Do not build the per-file isolation runner (that is T2), do not add a ruff ASYNC gate (T2), do not fix the Darwin `get_memory_info` `/proc/meminfo` defect (T2), do not build the verification evidence ledger (T3), do not add the wire-contract or model-name-surface evals (T4), do not unify findings shapes (T5), and do not add a CSP or npm install-script allowlist test (T6). Do not delete or migrate any existing live data — the guard raises, it never moves or rewrites the developer's files. Do not introduce a third hard dependency; `testing_guard.py` uses stdlib only (`os`, `sys`, `pathlib`, `socket`). Do not add a second feature gate or locality judge — this packet touches test infrastructure only and respects the one-gate rule in `capabilities.py`.

## 5. Target files
- `halbert_core/tests/conftest.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M is the right size. The deep-eval named T1 "the highest-value packet in the testing workstream and possibly across all three workstreams" because the leaks are confirmed and live, not theoretical: the `_default_db_path` comment block (lines 124-160) is a first-person account of one occurrence, `_skills_user_root_is_not_the_developers` at `conftest.py:235-257` is a second, and the `_isolated_config_canon_store` docstring at lines 9-47 references SEC-03/04/11 finding `latest.json` full of pytest tmp paths as a third. The work itself is bounded: one fixture of ~80 lines scrubbing env and pinning TZ/LANG/HOME; one socket-connect wrapper of ~30 lines plus a marker registration; one `testing_guard.py` of ~60 lines plus three call-site wires; one process-kill guard of ~50 lines. None of it touches the hot files (`state_machine.py`, `lease.py`, `conversation_sqlite.py` internals beyond the one-line guard swap). It is a prerequisite for T2 (the isolated runner inherits whatever hermeticity exists) and T4 (wire contracts are meaningless if the suite can read the developer's real config). It is not S because five distinct mechanisms ship, each with its own test coverage; it is not L because every mechanism is a bounded patch inside one file plus one new module, with no cross-cutting refactor and no founder-decision gate (FD-3's raise-vs-redirect is already ruled raise).

## 8. UX rationale

No user-facing surface. This is test-infrastructure plumbing; the dashboard, CLI, voice surface, and onboarding are untouched. The developer-facing experience is what changes: a contributor running `arch -arm64 .venv/bin/python -m pytest halbert_core/tests` no longer risks (a) seeing their real `conversations.db` or `state_ledger.db` audit hash chain mutated, (b) hearing real TTS playback out of the host speakers mid-run, (c) watching the suite reach a live Ollama daemon or phoning a non-loopback host, or (d) having a test fire `systemctl stop` at a real service. Failure messages must be first-person and operator-readable, matching the machine-speaks-as-itself voice already used in `_default_db_path`'s RuntimeError: name the offending path or destination, name the bypass marker (`allow_network`, or `db_path=`/`HALBERT_DATA_DIR` for the store guard), never name a model. No emoji, no colour (terminal output only), no new surface. The marker registration line in `pyproject.toml` is the only pytest-ini change.

## 9. Acceptance criteria

1. `halbert_core/tests/conftest.py` contains a function-scoped autouse fixture that, for any test, leaves `os.environ` free of `*_API_KEY`, `*_TOKEN` (other than the session-scoped `HALBERT_API_TOKEN`), and `*_SECRET` entries; pins `TZ=UTC`, `LANG=C.UTF-8`, `PYTHONHASHSEED=0`; and points `HOME` at a per-test tmpdir.
2. `socket.socket.connect` raises `RuntimeError` for any non-loopback destination during a test unless the test carries `@pytest.mark.allow_network`; the marker is registered in `halbert_core/pyproject.toml` under `[tool.pytest.ini_options].markers` so `--strict-markers` accepts it.
3. `halbert_core/tests/testing_guard.py` exists, exposes a single assertion helper, and is wired into (a) `agents/conversation_sqlite.py._default_db_path` (replacing the inline raise at lines 153-160 with an equivalent message), (b) the state-ledger default-path resolver, and (c) any data-dir `mkdir(parents=True)` site. Under `PYTEST_CURRENT_TEST` with no `HALBERT_DATA_DIR` set, attempting to open the real `~/.local/share/halbert/conversations.db` raises before any connect/pragma.
4. `os.kill`, `os.killpg`, and `subprocess.Popen` raise `RuntimeError` when the target pid was not spawned by the current test or when argv[0] is on the killer-executable denylist; `streaming/pty.py`'s self-kill of its own PTY child still succeeds.
5. The full suite still collects and the existing baseline failure count does not grow beyond the known nonzero baseline documented in CLAUDE.md ("main is not green"); no previously passing test starts failing because of the new fixtures.
6. No file outside `halbert_core/tests/conftest.py`, `halbert_core/tests/testing_guard.py` (new), `halbert_core/halbert_core/agents/conversation_sqlite.py` (one-line guard swap), the state-ledger path resolver, and `halbert_core/pyproject.toml` (marker registration) is modified.

## 10. Verification (measured state, not model judgment)

Runnable commands against measured state, all from the repo root:

1. `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -x -k "not slow" --collect-only -q | tail -1` — must print a test count greater than zero with zero collection errors.
2. `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q 2>&1 | tail -5` — exit code equals the documented pre-T1 baseline (currently nonzero per CLAUDE.md "main is not green"); the new run's failure count must be less than or equal to the baseline captured on the merge-base before the change. Capture the baseline with `git merge-base HEAD main | xargs -I {} git stash && git checkout {} && arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q 2>&1 | tail -1 > /tmp/t1-baseline.txt && git checkout - && git stash pop` first.
3. Targeted hermeticity assertions (new tests shipped with the packet, must pass):
   - `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_hermetic_environment.py -v` — asserts a test that sets `OPENAI_API_KEY=sk-fake` sees the var cleared inside its own body; asserts `Path.home()` resolves under `tmp_path`; asserts `TZ=="UTC"`.
   - `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_egress_guard.py -v` — asserts `socket.create_connection(("8.8.8.8", 53), timeout=1)` raises `RuntimeError` matching `"non-loopback egress"`; asserts a test marked `@pytest.mark.allow_network` is permitted to attempt the same call (assert on the marker-gating branch, not on the network succeeding — assert the guard did NOT raise, regardless of whether the connect itself succeeded).
   - `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_live_db_guard.py -v` — asserts `SqliteConversationStore()` with no `db_path=` and no `HALBERT_DATA_DIR` raises `RuntimeError` naming the resolved production path; asserts the same call with `HALBERT_DATA_DIR=tmp_path` succeeds; asserts the state-ledger default-path resolver raises identically.
   - `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_live_system_guard.py -v` — asserts `os.kill(1, 0)` (a pid the test did not spawn) raises; asserts `subprocess.Popen(["/bin/echo", "hi"])` is intercepted but allowed to proceed for a non-denylisted argv; asserts `subprocess.Popen(["/bin/launchctl", "list"])` raises.
4. `grep -n "allow_network" halbert_core/pyproject.toml` — must print one markers line.
5. `grep -rn "PYTEST_CURRENT_TEST" halbert_core/halbert_core/agents/conversation_sqlite.py` — must return zero hits (the inline raise has been replaced by the `testing_guard` call).

Every check is a process exit code, a stream completing, a test passing, or a grep hit — no model judgment anywhere.

## 11. Exclusions

The deep-eval explicitly split the original T1 scope; several items route elsewhere and none are dropped silently. (1) Per-file isolated test runner (`scripts/run_tests_isolated.py`, ~60 lines, `arch -arm64` prefix, `PYTHONPATH` pinned) → T2, which owns suite-integrity mechanics. (2) Ruff ASYNC gate (ASYNC210/220/221/251 + PLW1514 with per-file-ignores ratchet) → T2. (3) AST shadowed-definition guard (duplicate `FunctionDef`/`AsyncFunctionDef`/`ClassDef` in one scope) → T2. (4) Darwin `get_memory_info` `/proc/meminfo` defect in `tools/system_info.py:75-107` → T2 (live defect, unblocks the "grounded in measured data" directive). (5) Verification evidence ledger + stop-gate seam + invented-completion-claim eval metric → T3 (RESHAPE'd; stop-gate seam deferred until the real handler exists). (6) Wire contracts and model-name-absence surface evals → T4. (7) Findings-shape unification, artifact-hash verification, coverage registry, support-bundle merge → T5 (RESHAPE'd; verify R-15 merge status first per FINAL-CRITICAL §0). (8) CSP test, npm install-script allowlist, narrow upstream-tracking job → T6. (9) The divert/spool/replay path for a replaced conversation store → DIAG-02's deferred tail (per DIAG-02's own RESHAPE note; becomes real only when a restore-from-backup flow exists). (10) FD-3's raise-vs-redirect ruling is already "raise" — no deferral, the choice is locked into field 3's spec. The live-system guard's killer-executable denylist deliberately does NOT try to sandbox network syscalls at the `pf`/`sandbox-exec` layer — that is out of scope for a pytest fixture and would belong to a future macOS-sandboxing packet if one is ever opened.

---

## OSS reference

hermes-agent tests/conftest.py:40-103 + hermes_state_guard.py.

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
