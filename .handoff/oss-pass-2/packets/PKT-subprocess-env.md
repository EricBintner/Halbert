# PKT-subprocess_env — Subprocess env builder (blocklist)

Tier: **fable**   Milestone: **M0**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**subprocess_env** — Subprocess env builder (blocklist).

## 2. User problem

Every internal tool that spawns a subprocess today calls `subprocess.run(cmd, capture_output=True, text=True, timeout=...)` with no `env=` argument — which means Python passes the parent's entire `os.environ` unchanged to the child. The concrete leak: `halbert_core/halbert_core/tools/system_tools.py:154 _run_command`, `halbert_core/halbert_core/tools/gpu_tools.py:100 run_command`, `halbert_core/halbert_core/tools/accelerator_tools.py:32 run_command`, `halbert_core/halbert_core/tools/schedule_cron.py:85,94 _read_crontab/_write_crontab`, and the PTY shell path behind `halbert_core/halbert_core/streaming/pty.py:236 PTYSession.spawn` all fork children that inherit `HALBERT_API_TOKEN`, `HALBERT_MCP_TOKEN`, `HALBERT_PEER_TOKEN`, every `*_API_KEY` / `*_TOKEN` / `*_SECRET` the user has exported, and any loader variables (`DYLD_*`, `LD_*`). The same A17-G1 leak class R-09 closed for MCP stdio children (an npx-installed MCP server could read every other server's credential and call back into Halbert as Halbert) is still open at every non-MCP spawn site. The origin's MP-6 packet and backlog §3.7 both name this: R-09's `child_env()` at `halbert_core/halbert_core/mcp/client.py:153` is an allowlist (good for MCP where the child IS the third party), but a flat allowlist is wrong for internal tools like `crontab`/`ps`/`system_profiler` that legitimately need the user's PATH, HOME, locale, and shell context — what they must NOT see is Halbert's own tokens and any credential-shaped name. The fix is a single blocklist primitive at `halbert_core/halbert_core/tools/subprocess_env.py` (sibling to, not a rename of, `mcp/client.py:153`) consumed by every internal subprocess spawn.

## 3. What to build

Create `halbert_core/halbert_core/tools/subprocess_env.py` exposing one public function `build_subprocess_env(extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]` plus a module-level constant `BLOCKED_ENV_NAMES: FrozenSet[str]` and `BLOCKED_ENV_PREFIXES: Tuple[str, ...]`. Semantics: start from `os.environ.copy()`; drop any name in `BLOCKED_ENV_NAMES` (explicit: `HALBERT_API_TOKEN`, `HALBERT_MCP_TOKEN`, `HALBERT_PEER_TOKEN`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`); drop any name matching `BLOCKED_ENV_PREFIXES` (`"DYLD_"`, `"LD_"` for loader-preload hijack prevention, plus the credential-shape suffixes implemented as a predicate `_is_credential_shaped(name)` returning True for names ending in `_API_KEY`, `_TOKEN`, `_SECRET`, `_PASSWORD`, `_PRIVATE_KEY`); merge `extra` on top, applying the same blocklist to `extra` with a `logger.warning` per refused name (mirroring `mcp/client.py:173-176`). The predicate is a pure function, exported for testing. Wire consumers by replacing bare `subprocess.run(...)` / `subprocess.Popen(...)` calls at the four known sites with `subprocess.run(..., env=build_subprocess_env())`: `tools/system_tools.py:157`, `tools/gpu_tools.py:103`, `tools/accelerator_tools.py:35`, `tools/schedule_cron.py:85` and `:94`. Add a static source-guard test `halbert_core/tests/test_subprocess_env_blocklist.py` with (a) unit tests of the predicate and builder against a synthetic `os.environ` containing each blocked name and prefix, asserting they are absent from the result while `PATH`/`HOME`/`LANG`/`LC_ALL`/`TERM` survive; (b) a source-walk test that greps `halbert_core/halbert_core/tools/`, `halbert_core/halbert_core/scheduler/`, and `halbert_core/halbert_core/streaming/` for `subprocess.run(`/`subprocess.Popen(` call sites and asserts each is either inside `subprocess_env.py` itself, inside a test, or within N=5 lines of an `env=build_subprocess_env(` reference (whitelist PTY's `pty.fork()` since it does not go through subprocess's env path and is TT-02's separate scope); (c) a behavioural test using `subprocess.run([sys.executable, "-c", "import os,sys; sys.exit(0 if 'HALBERT_API_TOKEN' not in os.environ else 1)"], env=build_subprocess_env())` asserting exit code 0 when `HALBERT_API_TOKEN` is set in the parent. Do NOT touch `mcp/client.py:153 child_env()` — R-09 owns it, it is allowlist-by-design, and per the registry note this unit is a sibling, not a rename.

## 4. What NOT to build

Do NOT touch the MCP child env (`halbert_core/halbert_core/mcp/client.py:131-179`) — R-09 merged the allowlist there and the registry note is explicit that this unit is a sibling, not a rename or refactor. Do NOT fence the PTY shell at `streaming/pty.py:236 PTYSession.spawn` — that is TT-02's scope (the backlog §3.7 row names PTY as a TT-02 consumer, and the deep-eval verdict on TT-02 says "Keep PTY shell env fencing" as TT-02 residual work, not this unit). Do NOT add a general `run_subprocess_safely()` wrapper or executor — the backlog §3.7 candidate is specifically a `build_subprocess_env()` env-builder primitive, not a subprocess runner. Do NOT add allowlist mode, profile system, per-tool config, or YAML-driven policy — blocklist-on-environment is the entire shape. Do NOT wire consumers outside the four named sites (system_tools, gpu_tools, accelerator_tools, schedule_cron) — discovery scanners under `halbert_core/halbert_core/discovery/scanners/` (system_profile.py, process.py) are read-only probes of the host's own state and are out of MP-6's named scope; if a later audit shows them leaking, that becomes a follow-up. Do NOT build the credential-as-reference pattern (backlog §4 Wave 2 names this MP-6's tail gated by founder decision 3). Do NOT add a doctor check, findings registry entry, or DIAG-01 integration — that's a separate residual.

## 5. Target files
- `halbert_core/halbert_core/tools/subprocess_env.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S. The module itself is ~50 lines: a names frozenset, a prefixes tuple, a four-branch predicate, and a builder function with one logging call. The four consumer edits are mechanical one-line additions of `env=build_subprocess_env()` to existing `subprocess.run(...)` calls — no signature changes, no behaviour change beyond env contents. The test file is ~120 lines: a parametrized predicate test, a builder test against a synthetic environ, the source-walk test with an explicit allowlist of sites, and one behavioural subprocess test. No new dependencies (stdlib only — `os`, `re` optional, `logging`, `typing`), which respects the Haloysius two-dependency contract. R-09 already solved the harder version of this problem (allowlist + deny prefixes + config-env merging) at `mcp/client.py:153-179`, so the shape is proven; this unit copies the pattern with the polarity flipped. No hot files are touched: `tools/system_tools.py`, `tools/gpu_tools.py`, `tools/accelerator_tools.py`, `tools/schedule_cron.py` are leaf utility modules with low dependent counts, and the new module is brand-new. No state machine, no settings, no scheduler, no MCP client. The risk surface is contained: if a consumer is missed the source-walk test catches it; if a needed variable is over-blocked the predicate test names which shape was refused.

## 8. UX rationale

No user-visible surface. This is a backend security primitive — nothing renders in the dashboard, the CLI, the chat, or any notification. The system does not speak about it; there is no first-person line to write. If the source-walk test later trips because a developer added a new subprocess spawn without the env builder, the failure appears in pytest output only, naming the file and line — that is the entirety of the "UX". The one log line (`logger.warning` on a refused extra-env name) lands in the backend log under the existing logging rules and is scrubbed by R-05's `RedactingFilter` like every other record. No colours, no emoji, no model names — trivially satisfied because there is no UI.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/tools/subprocess_env.py` exists and exports `build_subprocess_env`, `BLOCKED_ENV_NAMES`, `BLOCKED_ENV_PREFIXES`, and `_is_credential_shaped` (the last exported for tests).
2. `halbert_core/halbert_core/tools/system_tools.py:157`, `halbert_core/halbert_core/tools/gpu_tools.py:103`, `halbert_core/halbert_core/tools/accelerator_tools.py:35`, `halbert_core/halbert_core/tools/schedule_cron.py:85`, and `halbert_core/halbert_core/tools/schedule_cron.py:94` all pass `env=build_subprocess_env()` to their subprocess call.
3. `halbert_core/halbert_core/mcp/client.py:153 child_env()` is byte-identical to its current form on `main` — no edit, no rename, no shared helper extraction.
4. With `HALBERT_API_TOKEN=leak-test` exported in the parent shell, `python -c "from halbert_core.tools.subprocess_env import build_subprocess_env; import subprocess,sys; sys.exit(subprocess.run([sys.executable,'-c','import os,sys; sys.exit(1 if \"HALBERT_API_TOKEN\" in os.environ else 0)'], env=build_subprocess_env()).returncode)"` exits 0.
5. With `FOO_API_KEY=x`, `BAR_TOKEN=y`, `BAZ_SECRET=z`, `DYLD_INSERT_LIBRARIES=evil`, `PATH=/usr/bin`, `HOME=/Users/x`, `LANG=en_US.UTF-8` set, `build_subprocess_env()` returns a dict containing `PATH`, `HOME`, `LANG` and not containing any of the other five.
6. The source-walk test reports zero uncovered `subprocess.run(`/`subprocess.Popen(` call sites under `halbert_core/halbert_core/tools/`, `halbert_core/halbert_core/scheduler/`, and `halbert_core/halbert_core/streaming/` outside the explicit allowlist (the allowlist today: `tools/subprocess_env.py` itself, `streaming/pty.py` PTY fork path, anything under a `tests/` directory).

## 10. Verification (measured state, not model judgment)

Run from the repo root: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_subprocess_env_blocklist.py -v` — the file must exit 0 with at least these test IDs passing: `test_predicate_blocks_credential_suffixes`, `test_predicate_blocks_loader_prefixes`, `test_builder_strips_halbert_tokens`, `test_builder_preserves_path_home_lang`, `test_builder_extra_respects_blocklist`, `test_source_walk_no_bare_subprocess_in_tools`, `test_spawned_child_does_not_see_halbert_api_token`. Then run the broader tools tests to confirm no consumer broke: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "system_tools or gpu_tools or accelerator_tools or schedule_cron" -x --no-header` — exit code 0. Finally, run the full suite to confirm no cross-file regression: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -x --no-header -q 2>&1 | tail -20` — failure count must not exceed the current `main` baseline (71 failures per memory note; the baseline is not zero and this unit must not raise it). Each of these is a measured state — pytest exit code, per-test pass/fail, baseline failure count comparison — never a model judgment.

## 11. Exclusions

PTY shell env fencing at `streaming/pty.py:236 PTYSession.spawn` — goes to TT-02 (per backlog §3.7's own consumer list naming PTY under TT-02, and the deep-eval verdict on TT-02 saying "Keep PTY shell env fencing"; TT-02's verdict is RESHAPE-verify-R-09 but the PTY fencing is its residual, not this unit's). The MCP child env at `mcp/client.py:131-179` — stays with R-09 (merged, allowlist, sibling not rename per the registry note). Credential-as-reference (a credential resolved at use time, never stored in env at all) — goes to MP-6's Wave-2 tail, gated by founder decision 3 and M8 landing first (backlog §4 Wave 2 "MP-6 (tail): Credential-as-reference — founder decision 3 + M8 landing first"). The doctor-check / findings-registry integration that would surface "N subprocess call sites fenced" as a diagnostic — goes to the M5b tail (DIAG-01's registry is the sink, per backlog §3.5 "one diagnostic sink" — every subsequent check is a new entry in the registry, not a new framework, and this unit does not build a registry entry). Discovery-scanner subprocess spawns under `halbert_core/halbert_core/discovery/scanners/` (system_profile.py, process.py) — out of MP-6's named consumer set; if a later audit finds them leaking, that becomes a follow-up discovery ticket, not this unit. Any per-tool profile or YAML-driven policy — dropped per RESHAPE: the backlog §3.7 shape is one blocklist primitive, and adding configurability is infrastructure for a consumer that does not exist (violates the standing rule against building for nonexistent consumers).

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
