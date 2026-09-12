# PKT-MP-6 — build_subprocess_env applied to every subprocess call site

Tier: **sonnet**   Milestone: **M4**   Effort: **S-M**
Collision lane: **B**   Merge order: **4/4 in B**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**MP-6** — build_subprocess_env applied to every subprocess call site.

## 2. User problem

Every subprocess and PTY shell Halbert spawns inherits the parent process environment wholesale, including credential-shaped variables like HALBERT_API_TOKEN and ANTHROPIC_API_KEY. Confirmed leak sites: halbert_core/halbert_core/tools/system_tools.py:157-162 (`_run_command` calls subprocess.run with no env= argument, so the child gets the full parent env); streaming/pty.py:317-321 (PTYSession.spawn does `child_env = dict(os.environ)` then execvpe's /bin/sh with it, so every watched terminal shell carries the parent's credentials into whatever the user or agent types); plus the same no-env= pattern in tools/accelerator_tools.py:35, tools/gpu_tools.py:103, and tools/schedule_cron.py:85,94. R-09 closed this only for stdio MCP children (mcp/client.py:153 `child_env()` uses an allowlist + DYLD_/LD_ deny prefixes); the general tool/PTY surface was left open. Halbert's posture is that secrets custody is deterministic and enforced at the process boundary — a credential the model never sees still leaks to any child process, any shell command, and anything those children spawn. This unit is Lane D of MP-6: apply the Phase-0 `build_subprocess_env()` primitive (dependency: subprocess_env unit, M0/M3) to every subprocess/PTY call site so no child receives credential-shaped env.

## 3. What to build

Wire `build_subprocess_env()` from the new `halbert_core/halbert_core/tools/subprocess_env.py` (built by the Phase-0 `subprocess_env` dependency — do NOT build that module here; if it is not yet merged, stop and re-dispatch after it lands) into every subprocess call site in the two target files, plus the three adjacent tool files the registry names for this unit's sweep:

1. halbert_core/halbert_core/tools/system_tools.py — `_run_command(cmd, timeout)` at :154-168: pass `env=build_subprocess_env()` to the subprocess.run call at :157.

2. halbert_core/halbert_core/streaming/pty.py — `PTYSession.spawn()` at :263-333: replace the wholesale `child_env = dict(os.environ)` at :317 with `child_env = build_subprocess_env()`, preserving the existing layering order: builder output as the base, then `child_env.update(_PAGER_NEUTERED)` (:318), then `child_env.update(self._env)` for the session's declared extras (:319-320), so a PTY session's explicit env still wins. Do not touch the fork/setsid/TIOCSCTTY sequence or the escalation reaper — TERM-1 owns watched-shell semantics; this unit changes only how the child's env dict is assembled.

3. tools/accelerator_tools.py:35 and tools/gpu_tools.py:103 — the two identical `run_command` helpers: add `env=build_subprocess_env()` to both subprocess.run calls.

4. tools/schedule_cron.py:85 (`crontab -l`) and :94 (`crontab -`): add `env=build_subprocess_env()` to both subprocess.run calls.

5. Shared call-site walk test (the backlog's §3.7 requirement): add halbert_core/tests/tools/test_subprocess_env_callsites.py that statically walks the halbert_core package AST, finds every `subprocess.run(...)`/`subprocess.Popen(...)` call and every `os.execvpe` in pty.py's spawn, and asserts each either passes an env derived from build_subprocess_env/child_env or is on an explicit documented-exceptions list (mcp/client.py's stdio launch already routes through R-09's child_env; execute_code.py is covered separately if it already scrubs — verify and list it). Plus a behavioural test: monkeypatch os.environ to contain HALBERT_API_TOKEN and ANTHROPIC_API_KEY, call the four run_command/_run_command helpers with a trivial command (`/usr/bin/env` or `['/bin/sh','-c','env']`), and assert neither variable name appears in captured stdout. For pty.py, a test that constructs a PTYSession with the tainted os.environ, spawns `env`, reads the bounded output, and asserts the credential names are absent (mirroring the existing spawn-pattern tests in tests/test_pty.py).

Keep it deterministic — no model anywhere in the path; this is process-boundary custody, consistent with the Tier-2 posture.

## 4. What NOT to build

Do not build `tools/subprocess_env.py` itself — that is the Phase-0 `subprocess_env` primitive unit (M0/M3), a declared dependency; this unit only consumes it. Do not touch mcp/client.py `child_env()` or the MCP stdio launch path — R-09 already covers MCP children with the allowlist policy, and merging the two policies into the shared primitive is the dependency unit's job. Do not change PTYSession's fork/setsid/TIOCSCTTY/echo handling, the escalation reaper, `_PAGER_NEUTERED`, or watched-shell behaviour — TERM-1 owns that lane; coordinate only at the env-assembly lines. Do not touch terminal-tools `run_command` orphan/timeout handling (HM04-M3 residual, owned by the terminal-tools packet, which reuses pty.py's killpg ladder). Do not build the credential-as-reference work (saved-endpoint API keys as Keychain/`token_env` references), the requests.Session redirect policy, or the Authorization header-merge helper — those are other MP-6 lanes/exclusions (see exclusions). No migrations, no back-compat shims; no UI surface; nothing user-facing changes.

## 5. Target files
- `halbert_core/halbert_core/tools/system_tools.py`
- `halbert_core/halbert_core/streaming/pty.py`

## 6. Dependencies

subprocess_env

## 7. Effort

**S-M** — S-M is right. The work is mechanical and small in diff size: one import plus one env= kwarg at four trivial sites (system_tools, accelerator_tools, gpu_tools, schedule_cron ×2) and a three-line env-assembly change in pty.py preserving the existing update-layering. What lifts it above pure-S is the shared call-site walk test (§3.7 of the backlog): writing a robust AST walk over the package that correctly attributes env provenance (direct dict(os.environ), os.environ passthrough, builder-derived, or documented exception) without false-positiving on legitimate uses takes care, and the PTY behavioural test needs the existing async spawn/read machinery from tests/test_pty.py. No design decisions remain — the verdict is ACCEPT, the primitive shape (`build_subprocess_env(baseline, extras)`) is fixed by the dependency unit, and the layering order in pty.py is dictated by existing code. Half a day of focused work including test runs against the known-non-green main baseline.

## 8. UX rationale

No user-facing surface changes. This is invisible custody hardening at the process boundary. The only observable behaviour change: commands run inside watched terminal sessions and tool-spawned subprocesses no longer see Halbert's own credential env vars — which is the intended posture, and matches what MCP child servers already experience under R-09. If a user's shell workflow genuinely depended on reading HALBERT_API_TOKEN out of a watched terminal (it should not — the dashboard never documents that), the correct answer per the custody ladder is the deterministic Tier-2 template, not restoring the leak. No colours, no copy, no first-person surface text involved.

## 9. Acceptance criteria

1. Every subprocess.run call in tools/system_tools.py (:157), tools/accelerator_tools.py (:35), tools/gpu_tools.py (:103), and tools/schedule_cron.py (:85, :94) passes env= derived from build_subprocess_env (or the shared primitive's equivalent).
2. PTYSession.spawn in streaming/pty.py builds child_env via build_subprocess_env() instead of dict(os.environ), with _PAGER_NEUTERED and self._env still layered on top in the existing order; fork/setsid/TIOCSCTTY/reaper code untouched.
3. New behavioural tests prove a tainted os.environ (HALBERT_API_TOKEN, ANTHROPIC_API_KEY set) does not reach child processes for the four run_command helpers or a spawned PTYSession.
4. The shared call-site walk test exists and passes: every subprocess./Popen/execvpe site in halbert_core is either builder-derived or on the documented-exceptions list (mcp/client.py via R-09's child_env).
5. No new test failures against the merge-base baseline (main is known non-green; baseline first).

## 10. Verification (measured state, not model judgment)

From the checkout root (worktree: use ./wt_pytest.py), all with the arch -arm64 prefix:

Baseline first: `arch -arm64 ./wt_pytest.py halbert_core/tests -x -q 2>&1 | tail -5` and record the failure count — main carries a known nonzero baseline; only deltas matter.

Targeted runs:
1. `arch -arm64 ./wt_pytest.py halbert_core/tests/tools/test_subprocess_env_callsites.py -v` — the new walk test + behavioural tests pass (exit code 0).
2. `arch -arm64 ./wt_pytest.py halbert_core/tests/test_pty.py halbert_core/tests/test_pty_fanout.py halbert_core/tests/test_pty_no_pager_escape.py -q` — existing PTY tests still pass, proving the spawn-path change didn't regress watched-shell behaviour (exit code 0, no new failures vs baseline).
3. Live measured check: `arch -arm64 .venv/bin/python -c "import os; os.environ['HALBERT_API_TOKEN']='probe-leak'; from halbert_core.tools.system_tools import _run_command; ok,out,err=_run_command(['/usr/bin/env']); assert 'HALBERT_API_TOKEN' not in out and 'probe-leak' not in out, 'LEAK'; print('no leak')"` — must print `no leak` and exit 0. Same probe against accelerator_tools.run_command and gpu_tools.run_command.
4. PTY measured check: spawn a PTYSession with the tainted environ running `env`, collect bounded output, assert 'HALBERT_API_TOKEN' absent (encode as a pytest in the new test file so it's repeatable; assert exit code 0).
5. Grep gate: `grep -rn "dict(os.environ)" halbert_core/halbert_core/ --include="*.py" | grep -v test | grep -v subprocess_env` returns no call sites that feed a child process (any remaining hit must be on the documented-exceptions list in the walk test).

## 11. Exclusions

Named exclusions from the MP-6 packet scope, each with its destination:

1. Credential-as-reference (M5b: saved endpoint API keys as Keychain items / `token_env` names resolved through crypto/storage.py's custody ladder) — goes to the M5b tail, explicitly gated on founder decision 3 AND on this unit's M8 work landing first (backlog line: 'MP-6 (tail) | Credential-as-reference — founder decision 3 + M8 landing first'). Do not start it here.
2. The credentialed model-call redirect policy (M3: shared requests.Session with allow_redirects=False for model calls, e.g. mcp/client.py:526-528's Authorization: Bearer POST) — another MP-6 lane/unit, sequenced after the Phase-0 url_guard/P5 primitive per the dispatch index ('P5 (url_guard) | M0/M3 | VMV-3, MP-6 redirect policy'). Not this unit.
3. The Authorization header-merge helper (M6: replace-never-append, credentials only to the configured origin) — another MP-6 lane/unit riding with the redirect policy. Not this unit.
4. Merging R-09's allowlist `child_env` (mcp/client.py:153) with the general blocklist into one shared primitive — that is the Phase-0 `subprocess_env` dependency unit's deliverable; this unit consumes the primitive and only adds the call-site walk test that §3.7 requires.
5. Terminal-tools `run_command` orphan/timeout process-leak (HM04-M3, killpg ladder) — the terminal-tools residual packet, cross-cutting opportunity #6; this unit's pty.py change is env-assembly only.
6. Watched-shell semantics in streaming/pty.py (echo clearing, ctty acquisition, escalation reaper, TERM, env fencing beyond credential stripping) — TERM-1/TT-02's lane (lane B in the dispatch index: CSC-06 → GW-A → TT-02 → MP-6); coordinate, don't encroach.
7. execute_code.py / sandboxed execution env handling — verify during the walk test; if it already scrubs, list it as a documented exception; if it leaks, file it as a follow-up finding rather than expanding this unit's scope.

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
