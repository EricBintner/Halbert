# PKT-MCP-A — Death supervisor + whitespace warning + fail-fast dead-child race (post R-09)

Tier: **opus**   Milestone: **M5a**   Effort: **S-M**
Collision lane: **K**   Merge order: **1/3 in K**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-09 is merged, keep only the genuine residual.

---

## 1. Packet

**MCP-A** — Death supervisor + whitespace warning + fail-fast dead-child race (post R-09).

## 2. User problem

R-09 merged the bulk of MCP-A (env allowlist, frame bound, entry-guard screen, process-group spawn + killpg escalation — verified in tree: `CHILD_ENV_ALLOWLIST` at `halbert_core/halbert_core/mcp/client.py:135`, `start_new_session=True` at `client.py:447`, `_terminate_group` SIGTERM→grace→SIGKILL at `client.py:531-572`, `mcp/entry_guard.py:validate_server_entry` wired into the loader at `mcp/config.py:615`). Three genuine residuals remain, all confirmed absent from main:

(1) Death supervisor (HM09-M4): R-09's process-group close only runs when `close()` runs. A SIGKILL, OOM-kill, or hard crash of the Halbert process itself never executes `close()`, so every live stdio MCP grandchild (npx→npm→node chains spawned with `start_new_session=True`) is orphaned with its stdio pipes closed but the processes alive — third-party code outliving the steward, holding credentials from its `env:` block, on a machine Halbert is supposed to be stewarding. The invariant is "no third-party subprocess outlives the steward, even on SIGKILL/OOM," and today it holds only for graceful shutdown.

(2) Hidden-whitespace warning (HM09-C16): an operator pastes a bearer token or URL into `mcp_config.yml` with a trailing newline or a stray space. `config.py` silently `.strip()`s the name/transport/command/url scalar fields, but `headers.*` values and `auth.token_env`'s resolved secret value are used as-is — the server then answers an opaque 401, and the operator has no way to see that the byte that broke auth was whitespace they never typed. A deterministic, value-never-logged warning at load time turns a 30-minute debugging session into a one-line log.

(3) Fail-fast dead-child race (HM09-C12): `StdioTransport.request()` (client.py:745) has exactly two outcomes for a call whose server died mid-call: stdout EOF (noticed when the reader loop ends) or the full per-call timeout (default tens of seconds) via `asyncio.wait_for(future, timeout=self.timeout)` at client.py:766. A dead child that holds its stdout open (zombie, wedged launcher) burns the entire timeout per call while the agent retries. "Slow" and "provably gone" are not distinguished; a PID-liveness race (`proc.returncode` / `os.kill(pid, 0)` on a 0.25 s poll, FIRST_COMPLETED against the RPC future) turns a dead server into a named failure in 0.25 s instead of the full timeout.

## 3. What to build

Build exactly three residuals in `halbert_core/halbert_core/mcp/`, each with pinned tests. No model anywhere; every check is deterministic stdlib.

A. `mcp/death_supervisor.py` (new file, ~150 lines, stdlib-only, imports nothing from halbert_core — it must survive Halbert's death):
- One helper process per Halbert process, spawned lazily on the first stdio connect and released when its registration set empties. It is its own session leader (`start_new_session=True`), so it is not in any group it might later have to kill.
- Protocol: the parent holds the only write end of a pipe; the supervisor reads lines `register <pgid>` / `unregister <pgid>` from stdin. Parent death — SIGKILL, OOM, crash, anything — is pipe EOF: exact, free, no polling, no heartbeat. On EOF the supervisor SIGTERMs every registered pgid, waits a 3 s grace (mirror `_GROUP_TERM_GRACE_SECONDS = 3.0` at client.py:126), SIGKILLs survivors, exits.
- If the supervisor itself dies (it is 150 lines of stdlib; treat death as possible anyway), the next register/recognize respawns it and replays the live pgid set; the parent keeps the set as the source of truth.
- Wire-up in `StdioTransport` (client.py): after `self._pgid = os.getpgid(self._proc.pid)` succeeds at client.py:465, send `register <pgid>`; in `close()` after `_terminate_group` completes (client.py:524), send `unregister <pgid>`. Keep the existing close()-time killpg ladder exactly as-is — the supervisor is the backstop for the case close() never runs, not a replacement.
- POSIX-only, matching the rest of the stdio transport; Halbert is single-host macOS/Linux per the standing frame.

B. Hidden-whitespace warning in `mcp/config.py` (HM09-C16): one helper run at entry load (inside the per-server parse that already calls `validate_server_entry` at config.py:615) over: the HTTP `url`, every `headers.*` value, and `auth.token_env`'s *resolved* secret value (post-`resolve_token()`; the section file notes `resolve_token()` at config.py:180-200 returns the value as-is). Warn when the value has leading/trailing whitespace or an embedded `\r`/`\n`. The warning names the field path only (`server 'x': headers.Authorization carries trailing whitespace`) and NEVER the value — the value is a registered secret via `register_server_secrets(env)` at config.py:571, and the log line must stay compatible with that. Dedupe per (server, field) so a health-monitor reload loop does not spam. Warning only, never refusal: whitespace may be significant to a broken-but-real server.

C. Fail-fast dead-child race in `StdioTransport.request()` (client.py:745): keep `proc.pid` already on the instance. Pre-call: if `self._proc.returncode is not None`, raise `MCPDisconnectedError` immediately naming the server and saying the call never reached it. During the call: `asyncio.wait(FIRST_COMPLETED)` between the existing response future and a 0.25 s liveness poll task using `self._proc.returncode` (already maintained by asyncio) with `os.kill(pid, 0)` as a fallback probe — no psutil dependency (Haloysius two-hard-dependency contract). A dead-child win cancels the RPC future, pops `req_id` from `self._pending`, and raises `MCPDisconnectedError` with text in the family the section file's M12 item specifies: "this is not a timeout — the call never reached the server / the server process is gone; do NOT retry until it has been restarted." The poll task is cancelled cleanly on every exit path so it never leaks into the reader loop's lifetime.

## 4. What NOT to build

Everything R-09 already merged, re-verified in tree — do not rebuild, do not "improve," do not re-litigate:
- The child env allowlist (`CHILD_ENV_ALLOWLIST`, `_CHILD_ENV_PREFIXES`, `_CHILD_ENV_DENY_PREFIXES`, `child_env()` — client.py:129-160). Done, tested by the A17-G1 batch.
- The 16 MiB stdio frame bound and drain (`MAX_STDIO_FRAME_BYTES`, `_FRAME_DRAIN_CHUNK`, the LimitOverrun drain in `_read_loop`). Done (A17-G2).
- The entry-guard screen (`mcp/entry_guard.py` + loader wiring at config.py:615 + the dashboard 400 path covered by `test_the_write_path_answers_400_naming_the_finding`). Done (A17-G3/M5).
- Process-group spawn and the SIGTERM→grace→SIGKILL close ladder (`start_new_session=True` at client.py:447, `_terminate_group` at client.py:531). Done (A17-G10). The supervisor in (A) rides on top of this; it does not replace it.
- The OSV/package preflight for npx/uvx servers: explicitly OUT — FD-10's recorded default is "not now; record," and `mcp/package_preflight.py` already landed the fetch-time line (`58216f33 feat(mcp): FD-10's package preflight`). Do not extend it.
- Any change to the HTTP transport, SSE parsing, pagination, session-id handling, or the health monitor's backoff/proven-session logic — all R-09 Phase D/C scope, done.
- No psutil, no new hard dependency (Haloysius contract: exactly two). No model judgment in any check. No back-compat shim for the supervisor's absence on non-POSIX platforms — Halbert ships macOS/Linux only; guard the import the way the stdio transport already does, don't build a Windows stub.

## 5. Target files
- `halbert_core/halbert_core/mcp/client.py`

## 6. Dependencies

process_group

## 7. Effort

**S-M** — S-M overall, matching the packet header. (B) whitespace warning is a genuine S: one helper, one call site, a regex-free `value != value.strip() or '\r' in value or '\n' in value` check, ~40 lines with tests. (C) dead-child race is a genuine S: ~60 lines inside one method plus cancellation hygiene, no new process semantics. (A) death supervisor is the M: a second process with its own lifecycle, a respawn-and-replay path, and register/unregister call sites in connect/close — but it is a well-bounded M because the origin design (Hermes `tools/mcp_death_supervisor.py`, 216 lines) is fully specified in the section file, the protocol is two verbs over a pipe, and the killpg escalation ladder it triggers already exists and is tested. All three touch the same lifecycle surface (`StdioTransport.connect/close/request`, `config.py` entry parse), so test setup (fake stdio servers, `_killpg` indirection) is shared. What keeps it out of L: no config-format change, no API change, no cross-module blast radius beyond `mcp/client.py` + `mcp/config.py` + one new file.

## 8. UX rationale

No new surface; this is reliability the operator feels only by its absence of failure. Three touchpoints, all text-only, all obeying the standing rules:

- Whitespace warning: a single log line per (server, field), e.g. `MCP config: server 'home-assistant' field headers.Authorization has leading/trailing whitespace — a pasted token with a stray newline surfaces as an opaque 401`. Field path named, value never named (it is a registered secret). No emoji, no color — it is a log line, and if it ever reaches the dashboard's MCP status surface it uses the shared-token palette only.
- Dead-child error text: deterministic template, never a model, and it speaks to the agent's control surface the way M12 specifies: reached-or-not, retry-or-not. "The server process is gone; this call never reached it. Do not retry until the server has been restarted." No server-name beyond the config key, no model name, no "Sovereign."
- Death supervisor: invisible by design. The only observable is a log line at supervisor spawn (`MCP death supervisor up (pid N)`) and, on the path that matters, the absence of orphaned node processes after a crash. If it ever has to explain itself on the engaged surface, the computer speaks first person grounded in measured data: "I restarted and cleaned up the 3 helper processes that were still running," not "an assistant terminated stale subprocesses." Commands remain staged, never executed — the supervisor acts on process groups Halbert itself spawned, which is not a user command.

## 9. Acceptance criteria

1. `mcp/death_supervisor.py` exists, stdlib-only (assert: no `halbert_core` import in the file, pinned by a test that parses its AST), spawned lazily on first stdio connect, released when the registration set empties.
2. Probe test: a fake parent registers a real spawned process group (a `sleep`-shaped child that itself spawns a grandchild), the parent is SIGKILLed, and within (3 s grace + margin) the grandchild is gone — asserted by `os.kill(pid, 0)` raising ProcessLookupError, or `os.waitpid` reaping. Second test: `unregister` then parent-death leaves the group ALIVE (proves the supervisor isn't a blanket reaper).
3. Respawn test: kill the supervisor, register a new pgid, assert the live set was replayed (new supervisor's eventual SIGTERM reaches the previously-registered group after parent death).
4. Whitespace: `config.py` load of an entry whose `headers.Authorization` is `"Bearer abc\n"` and whose `url` is `" https://x "` produces exactly one warning per (server, field), the field path appears in the message, the value bytes do not, and a second load with unchanged file identity (the `_CONFIG_MEMO` path at config.py:671) does not re-warn. A clean entry warns zero times. The entry still loads (warn-only).
5. Dead-child race: a fake stdio server that accepts the handshake then `os._exit()`s while holding stdout open causes `request()` to raise `MCPDisconnectedError` in < 2 s (wall-clock assert, generous against the 0.25 s poll), with "never reached the server" in the message; the pending map is empty afterward; the existing `test_death_during_pending_request_fails_the_future` and `test_request_after_server_death_is_disconnected_error` (test_mcp_client.py:460,470) still pass unmodified.
6. Full MCP suite green against the merge-base baseline (main is not green; compare, don't absolute).
7. No new import in `mcp/` beyond stdlib; `pyyaml`/`requests` remain the only hard deps.

## 10. Verification (measured state, not model judgment)

Measured-state checks only, all runnable from the checkout root with the mandatory arch prefix:

1. New pinned tests (this packet adds them):
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_mcp_death_supervisor.py -x -q`
   — the SIGKILL-the-parent probe (acceptance 2) and respawn-replay (acceptance 3). These spawn real process groups on the build host and assert liveness via `os.kill(pid, 0)` / waitpid: measured process state, no judgment.
2. Whitespace and race pins:
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_mcp_config_write.py halbert_core/tests/test_mcp_client.py -q -k "whitespace or dead_child or death_during or request_after_server_death"`
   — includes the wall-clock `< 2 s` assertion on the dead-child race (a timing measurement, not a model verdict).
3. No-regression across the whole MCP surface R-09 touched:
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -q -k "mcp" 2>&1 | tail -5`
   — compare pass/fail counts against the same command run on the merge-base before the branch (main carries a known nonzero baseline; record both).
4. Stdlib-only assertion for the new file (grep check, run in CI-shaped form):
   `! grep -nE "^(import|from) (halbert_core|psutil|requests|yaml)" halbert_core/halbert_core/mcp/death_supervisor.py`
   — must produce no matches.
5. Live smoke (manual, one line): `make dev-web`, add one stdio MCP server whose command spawns a child (`sh -c 'sleep 300 & exec cat'` shape refused by entry_guard — use a trivial node/python one-liner that forks), `kill -9` the backend, then `pgrep -f <server-command>` returns nothing within ~5 s.

## 11. Exclusions

Explicit exclusions and where each goes instead:

- OSV/package preflight for npx/uvx-launched servers (HM06-C12 / A17-G19): stays deferred under founder decision FD-10 ("not now; record"). `mcp/package_preflight.py` already landed the fetch-time line in `58216f33`; any widening is a new founder decision, not this packet.
- The terminal-tools orphan-on-timeout fix (HM04-M3): the section file flags it as sharing the same process-group escalation pattern. It is NOT built here — it belongs to packet TT-01 (shell executor), which the FINAL backlog lists as depending on the same `utils/process_group.py` shared unit. If the executor wants the death-supervisor pattern, it imports `mcp/death_supervisor.py` or, preferably, the supervisor is lifted to `utils/process_group.py` when TT-01 lands (the backlog's shared-units table at line 425 already names `utils/process_group.py` as the shared home for process-group escalation across TT-01, SCHED-P2, and MCP-A — build this packet's supervisor as a self-contained `mcp/death_supervisor.py` first, let TT-01 do the lift so this packet doesn't block on a shared-unit refactor).
- Per-server circuit breaker with model-facing retry text (HM09-C2/M12): done by R-09 for the health-record consult; the error-text rewrite is MCP-B/C residual or done — either way, not this packet. This packet's dead-child message text (C) is a sibling of that family, not a takeover of it.
- Schema cache + lazy first-call connect and idle/max-lifetime recycling: MCP-C's residual, separate packet.
- content-vs-structuredContent alternation and bridge-level result cap: MCP-B's residual, separate packet.
- Dashboard UI for the whitespace warning: the log line is the deliverable; surfacing it on `/api/mcp/status` (health.py:645 `mcp_status_snapshot`) is a one-field follow-up left to whoever next touches the dashboard MCP page (B5/B6 workstream).

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
