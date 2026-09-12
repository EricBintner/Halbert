# PKT-TT-01 — Shell executor hardening

Tier: **opus**   Milestone: **M2**   Effort: **M**
Collision lane: **H**   Merge order: **1/3 in H**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**TT-01** — Shell executor hardening.

## 2. User problem

TT-01 — Shell executor hardening (ACCEPT in both the deep-eval and FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md; M2 / opus / effort M; target files halbert_core/halbert_core/tools/executor.py and halbert_core/halbert_core/streaming/agent_pool.py; dependencies process_group, text_hygiene, durable_write; Lane C on executor.py).

The shell-exec path and the agent pool are Halbert's primary interaction surface with the host, and the verifier confirmed six live defects there that the merged remediation (R-05 redaction registry, R-06 echo guard, R-07 execute_code hardening) did not touch because R-07 scoped itself to execute_code, not _run_command or the pool:

1. Orphaned grandchildren on every timeout. tools/executor.py:948 spawns via asyncio.create_subprocess_shell with no start_new_session, and the except-BaseException path at :1029 calls bare proc.kill() — a SIGKILL to the /bin/sh wrapper only. Every shell timeout orphans the whole pipeline tree the shell forked (sleep 1000 | tee …, a daemonising helper). This is audit OC13-C5/OC08-C1 and also closes A17-G10 (stdio MCP server kill).

2. PID reuse keeps orphaned backends alive. scheduler/run_receipts.py:61 and dashboard/parent_watchdog.py:33 probe liveness with bare os.kill(pid, 0). On macOS a reused PID means a dead process's slot now names an unrelated live process, so a receipt that should be reaped stays "running" forever. Audit OC06-C13 family.

3. Redact-after-cap leaks straddling secrets. streaming/agent_pool.py:312-324 severs head (first 20 lines) from tail (last 4 KiB) and only then calls streaming/redact.redact() on each fragment independently (:330-331). A secret that straddles the cut boundary — e.g. a base64 key whose halves land in different fragments — leaks in halves, and each half on its own matches no pattern. The verifier confirmed this against the live code. This violates the standing rule "scrub deterministically BEFORE the model" — the model sees the fragments.

4. Raw ANSI/Unicode control sequences reach the model unfiltered. Both the subprocess fallback path (executor.py:972 pump, decodes with errors='replace' and hands the raw string to the model) and the pool path (agent_pool.py run_block) pass subprocess output containing ANSI escapes, OSC sequences, C0/C1 controls and Unicode tag characters straight into the tool result. The model can copy a tag sequence into a later file write or the frontend can be fed an escape that repaints the terminal. This also closes A17-G5 (remote tool descriptions enter the prompt without tag stripping) on the result side.

5. A non-zero exit reads as success. executor.py:1018 returns f"Exit code {returncode}\n{output}\n{errors}" as a plain tool-result string with success semantics; the model then spends a turn misdiagnosing e.g. "ModuleNotFoundError" as a missing package (A05-G4). The standing rule "never a model where a template suffices" applies: exit-code/signal interpretation is deterministic, not a model judgment.

6. _write_file writes through hardlinks/symlinks and trusts the write. executor.py:1214 does plain open(path, 'w').write(content) — for a tool the agent uses to edit launchd/systemd units and shell rc files, a pre-planted hardlink at the target makes the write land somewhere else entirely, and there is no read-back verification that the bytes on disk match the bytes asked for (the after_text read-back at :1227 reads the same symlinked path, so it verifies nothing about the real target). Additionally the approve-then-execute gap (execute() at :672 returns requires_confirmation=True, then a later confirmed=True call re-enters) is not bound to the artefact approved: an attacker (or another session — the founder runs concurrent sessions in this checkout) can swap the target between approval and execution. Primitives 3.14 (process-start-time ownership) and 3.15 (approval bound to artefact, device/inode) in the backlog name these.

## 3. What to build

Six changes, all deterministic, all reusing Wave-0 primitives (do not build a second redaction registry, a second sanitizer, or a second kill ladder — the standing rule forbids duplicate primitives):

1. Process-group ownership on the subprocess fallback path (executor.py _run_command, :948 and the kill at :1029). Spawn with the process-group primitive from utils/process_group.py (the Wave-0 module, factoring the proven escalation ladder in streaming/pty.py:269 os.setsid and :342-445 escalation reaper — same ladder R-09 used for MCP stdio children). Concretely: pass start_new_session=True equivalent into asyncio.create_subprocess_shell (preexec_fn=os.setsid on POSIX, matching pty.py:296), and on timeout/cancel replace proc.kill() with the graded killpg ladder: SIGTERM to the group, grace wait, SIGKILL to the group. The helper is shared with SCHED-P2 and MCP-A — build it once in utils/process_group.py if Wave 0 has not landed it yet, otherwise import it. The pool path already kills via session_manager.TerminalSessionManager.kill (:189) → PTYSession.kill; verify that path also reaps the group (pty.py does setsid, so killpg reaches it) and only patch if it does not.

2. PID+start-time identity fingerprint. Add a small helper (e.g. in utils/process_group.py or a shared utils module — the backlog leaves placement open: "(shared fingerprint)") that captures (pid, start_time) at spawn from /proc-equivalent — on macOS use sysctl KERN_PROC_PID via the platform layer (utils/platform.py) or ps -o lstart= -p pid as the portable fallback; both parent_watchdog.py and run_receipts.py probe sites are in other packets' scope, but the fingerprint helper belongs to this unit's Wave-0 surface and the executor's own background path (_run_command_background, executor.py:912) must stamp its spawned child with the fingerprint so receipts it writes are reuse-safe. The terminal spawn events published at :958 and agent_pool.py:170 must carry the start_time alongside pid so downstream probes can compare.

3. Redact-before-cap in the pool (agent_pool.py:308-331). Reorder: decode output_bytes once, run streaming/redact.redact() on the FULL output text first, then sever head (first 20 lines) and tail (last 4 KiB) from the already-redacted text. was_redacted becomes the single flag from that one pass. This keeps the existing elided_lines accounting (:318-325) intact — compute it after redaction on the redacted lines. One redact pass, then cut; never cut then redact. Route through the existing redact() — R-05's registry is the choke point; do not add patterns here.

4. Text hygiene on every model-bound result. Import the Wave-0 sanitizer from security/text_hygiene.py (the backlog's §3.3: tag stripper from mcp/metadata.py:strip_unicode_tags + prompts/agent_prompts.py:_CONTROL_TAG_RE folded into one module; if Wave 0 has not landed it, this unit builds the minimal ANSI-escape + C0/C1 + Unicode-tag stripper there and TT-03/SP-2 reuse it). Apply it to the tool-result string at the two choke points where subprocess output crosses to the model: (a) executor.py _run_command's return paths (:1020 and :1023), and (b) agent_pool.py run_block's output_head/output_tail before they are returned in the result dict (:375 region) and before _format_block_result formats them. Streaming SSE chunks (publish_terminal_event output events) are display-bound and already cross R-06's display projection — do not strip the live stream (terminals legitimately render ANSI); strip only the model-bound copies.

5. Deterministic exit interpretation (executor.py:1018). Replace the bare f"Exit code {returncode}..." interpolation with a template that (a) reports the exit state structurally — non-zero code, or signal (returncode < 0 → signal number and name, e.g. "killed by SIGTERM"), (b) appends a deterministic failure hint for the common cases (127 → command not found; 126 → not executable; 1 with stderr containing ModuleNotFoundError/No such file → name what the stderr actually says is missing; 137/SIGKILL → likely OOM or external kill), and (c) never paraphrases via a model. The template is a lookup, per "never a model where a template suffices." The ExecutionResult from execute() should also carry the exit state so a non-zero exit does not present as an unqualified success to the turn.

6. Atomic write with read-back verification + device/inode approval binding in _write_file (executor.py:1150-1237). (a) Replace open(path, mode).write() with the Wave-0 utils/durable_write.py primitive: temp file in the target directory, write+flush, fsync, os.replace, directory fsync (the pattern scheduler/run_receipts.py:121 and consent/store.py:599 already use), with an append path that falls back to open('a')+fsync since replace cannot append. (b) Refuse to write through symlinks/hardlinks: lstat the target first; if it is a symlink, either resolve-then-verify or refuse per the write_guard seam (continuity/write_guard.py is the existing guard — extend it, do not add a second check); after os.replace, lstat again and verify (st_dev, st_ino) of the new file and read back the first/last bytes to confirm what landed. (c) Bind approval to artefact: when execute() returns requires_confirmation for a write (:672), capture (st_dev, st_ino, size, mtime_ns) of the target — or its absence — into the confirmation payload; on the confirmed re-entry, re-lstat and refuse with a deterministic "target changed since approval" message if the identity differs. This closes the approve-then-replace race (backlog §3.15, BIND-01 family) without any new UX.

All changes keep the existing public shapes: _run_command still returns str, run_block still returns the same dict keys (adding start_time is additive), _write_file's ledger record (record_file_change at :1218) now records the post-replace verified after_text.

## 4. What NOT to build

Do NOT rebuild or extend the redaction pattern set in streaming/redact.py — R-05 owns the registry; this unit only reorders cap-vs-redact in agent_pool.py and calls the existing redact(). Do NOT build a second sanitizer: the strip goes in security/text_hygiene.py (Wave 0 §3.3) and mcp/metadata.py:strip_unicode_tags plus prompts/agent_prompts.py:_CONTROL_TAG_RE fold into it per that plan — if Wave 0 has not landed it, build only the minimal stripper and leave the fold to SP-2. Do NOT touch the MCP child-environment allowlist (R-09/TT-02 scope), the PTY shell env fence (TT-02), the command normalizer/de-obfuscator or fail-closed parsing (TT-03 — it consumes text_hygiene step one but builds the rest), or the unattended-origin approval policy (TT-03's HM06-M2; this unit's device/inode binding is artefact identity, not origin policy). Do NOT change the SSE live-stream rendering or the frontend terminal tile — display projection is R-06's seam; ANSI passes through to the live stream untouched. Do NOT fix parent_watchdog.py:33 or scheduler/run_receipts.py:61 themselves — those probe sites belong to SCHED-P1; this unit ships the shared (pid, start_time) helper they will consume and stamps its own spawn paths. Do NOT build the background process registry, yield/wake, or PTY reattach (TT-04 RESHAPE scope). Do NOT add any model-based interpretation of failures, any new tool schema, any migration of existing terminal_blocks rows (no users yet — leave old rows unread), any new colour/emoji/surface copy, or any LLM call anywhere in these paths — every behaviour here is a deterministic template.

## 5. Target files
- `halbert_core/halbert_core/tools/executor.py`
- `halbert_core/halbert_core/streaming/agent_pool.py`

## 6. Dependencies

process_group, text_hygiene, durable_write

## 7. Effort

**M** — M (medium) is right and matches the backlog's own estimate (Wave-1 table: TT-01, effort M). The work is six well-bounded changes concentrated in two files totalling ~1,724 lines, and three of the six lean on Wave-0 primitives that either land ahead of this unit or are small to build once: the kill ladder is copied from pty.py's proven pattern (~50 lines of helper plus two call-site swaps), the text stripper is a regex table (~40 lines), durable_write generalizes a pattern already used twice in the repo. The genuinely careful parts are: the redact-before-cap reorder in agent_pool.py, which must preserve the elided_lines accounting and the terminal_complete event shape (the frontend renders from head/tail/elided and nothing else — a miscount there shows the user a wrong elision number); the device/inode binding, which must thread the artefact identity through the requires_confirmation → confirmed round-trip without changing ExecutionResult's public shape in a breaking way; and the write-path symlink policy, which must extend continuity/write_guard.py rather than bolt on a parallel check. Nothing here needs a founder decision, new UX, model calls, or cross-session coordination beyond respecting Lane C's ownership of executor.py. Testing is the larger half of the effort: process-group reaping, PID-reuse fingerprinting, straddling-secret redaction, and approve-then-swap refusal each need a live subprocess test, not a mock.

## 8. UX rationale

No new surface, no copy change, no colour, no emoji. What changes is what the model and the existing terminal tiles report. The model-bound tool result for a failed command now reads as a deterministic statement in Halbert's first-person measured voice, e.g. "The command exited 127: zsh: command not found: lso" instead of the bare "Exit code 127" blob the model used to misdiagnose — the system states what it measured, never an assistant paraphrase, and never names an AI model. The existing terminal_block card keeps its exact head/tail/elided-lines rendering; the elided count stays truthful because it is computed after the single redact pass. A refused write after an approve-then-swap surfaces as a plain deterministic refusal through the existing write_guard message channel: "Refused to write /etc/…: the file changed since approval. Nothing was written." — same shape as the existing guard refusals at executor.py:1203, grounded in the measured (st_dev, st_ino) change, no alarm styling. A timeout kill now reports that the whole process group was stopped, so the conversation does not later discover a stray daemon still holding a port — again one measured sentence in the existing terminal_complete/result flow. Nothing is staged differently: commands remain staged-never-executed from the UI per the standing rule; this unit only changes how an already-approved execution is contained and reported. Streaming tiles continue to render ANSI live (that is what a terminal is for); only the model's copy is stripped.

## 9. Acceptance criteria

1. Process-group kill: executor._run_command's subprocess fallback spawns with its own session/process group (start_new_session equivalent), and on timeout the kill escalates SIGTERM→grace→SIGKILL to the whole group via the shared utils/process_group.py helper — no bare proc.kill() remains on the shell wrapper, and no second kill ladder is invented in executor.py.
2. PID+start-time fingerprint: a shared helper captures (pid, start_time) at spawn; _run_command_background and every terminal spawn event (executor.py:958, agent_pool.py:170) carry the fingerprint alongside pid; the helper is importable by SCHED-P1's probe sites.
3. Redact-before-cap: agent_pool.py run_block calls redact() exactly once on the full decoded output, then severs head/tail; a secret straddling the 20-line/4KiB cut appears nowhere in either fragment; output_elided_lines remains accurate against the redacted text; terminal_blocks rows still store the same columns.
4. Text hygiene: security/text_hygiene.py strips ANSI escapes, C0/C1 controls, and Unicode tag chars; it is applied to the model-bound results of _run_command (both return paths) and run_block (head/tail in the result dict); the SSE live stream is byte-identical to before (not stripped).
5. Deterministic exit interpretation: non-zero exits and signal deaths produce a template string stating code/signal name plus a lookup-table hint for 126/127/137 and stderr-matched ModuleNotFoundError/No-such-file; no model is consulted; zero-exit output is unchanged in shape.
6. Atomic write + binding: _write_file writes via utils/durable_write.py (temp+fsync+os.replace+dir fsync), refuses or safely resolves symlink/hardlink targets through continuity/write_guard.py, verifies the landed file's (st_dev, st_ino) and read-back bytes, and the requires_confirmation payload binds the target's (st_dev, st_ino, size, mtime_ns) — a confirmed re-entry against a swapped target refuses with the deterministic message and writes nothing; the ledger's record_file_change records the verified post-replace content.
7. No regression in existing pool/executor tests, and the standing rules hold: no hardcoded colours, no emoji, no model names, redaction stays in R-05's registry, display projection stays in R-06's seam.

## 10. Verification (measured state, not model judgment)

Run from the worktree with the venv interpreter and the arch prefix, per repo rules:

  arch -arm64 ./wt_pytest.py halbert_core/tests/test_agent_pool.py halbert_core/tests/test_agent_pool_reaping.py halbert_core/tests/test_executor_pool.py halbert_core/tests/test_agent_pool_shell_syntax.py

— all pre-existing files must stay at their current pass counts (get the baseline from the merge-base first; main is not green, so diff against that baseline, never against zero).

New tests this unit adds (each asserts measured state, not a judgment):

- test_executor_process_group.py::test_timeout_reaps_grandchildren — spawn `sh -c 'sleep 60 & wait'` via _run_command with timeout≈0.5s; after the timeout, assert the grandchild sleep's PID is gone: os.kill(grandchild_pid, 0) raises ProcessLookupError. Measures a dead PID, exit-path taken.
- test_executor_process_group.py::test_graceful_commands_unaffected — `echo hello` returns "hello" with exit 0 and no regression in the result string.
- test_pid_fingerprint.py::test_reused_pid_not_confused — capture (pid, start_time) for a spawned child, reap it, spawn enough churn children that a PID could recycle (or monkeypatch the start-time read), assert the fingerprint comparison reports the old identity as dead while a bare os.kill(pid,0) might not. Measures the (pid,start_time) tuple mismatch.
- test_agent_pool_redact_before_cap.py::test_straddling_secret_redacted — feed run_block output where a redact() pattern's match straddles the 20-line head boundary (e.g. a fake key whose prefix is line 19-20 and suffix is in the elided middle); assert neither output_head nor output_tail contains any fragment of the secret and the "[redacted]" marker appears in head. Measures string absence/presence.
- test_agent_pool_redact_before_cap.py::test_elided_lines_truthful_after_redaction — known N-line output with one redacted line; assert output_elided_lines == N - head_lines - tail_lines exactly. Measures the count.
- test_text_hygiene.py::test_ansi_and_unicode_tags_stripped — input with CSI/OSC sequences, a NUL, C1 controls, and U+E0001-style tag chars; assert output contains none of them and printable ASCII survives. Measures byte content.
- test_executor_exit_interpretation.py::test_127_template — run a nonexistent command via _run_command; assert the result string contains "127" and "command not found". test_signal_template — a command that kills itself with SIGTERM; assert the result names the signal. Measures exact template substrings.
- test_write_file_atomic.py::test_write_lands_via_replace_and_verifies — write through _write_file, assert the file's content matches and (st_dev, st_ino) changed from any pre-existing file (proving replace, not in-place). Measures inode change + content equality.
- test_write_file_atomic.py::test_symlink_target_not_written_through — plant a symlink at the target pointing at a canary file; assert the write refuses or replaces the link itself and the canary's bytes are unchanged. Measures canary content.
- test_write_file_atomic.py::test_approval_bound_to_artefact — obtain requires_confirmation for a write, swap the target file between approval and the confirmed call, assert the confirmed call refuses, writes nothing, and the message states the target changed. Measures exit state + unchanged disk content.

Full-suite sanity after the change: arch -arm64 ./wt_pytest.py halbert_core/tests — pass count ≥ merge-base baseline with zero new failures attributable to these files.

## 11. Exclusions

- MCP stdio child environment allowlist and the PTY shell env fence (child_env = dict(os.environ) in streaming/pty.py:289-293, env=None in session_manager.py:99) → TT-02 RESHAPE scope; the backlog explicitly assigns the env fence there after R-09 covered the MCP half.
- Positive denial marker (HALBERT_CHILD_CONTEXT), background-offloads-in-empty-Context (the 20+ bare asyncio.to_thread sites), trusted-executable check on sandbox binaries → TT-02's kept items per its RESHAPE verdict.
- Command normalization/de-obfuscation (NFKC, $IFS collapse, escape stripping, iterated command starts), fail-closed-on-unparseable, founder-authored deny list, unattended-origin approval policy (the no-op _handle_awaiting_confirmation), combined approval requests, self-repo worktree-mutation rule → TT-03, ACCEPT; it consumes this unit's text_hygiene stripper as its normalizer step one but builds the rest itself.
- Background ProcessRegistry with poll/log/wait/kill, yield-to-background, watch-pattern throttle, wake-into-conversation, PTY socket reattach, bounded wait on watched sessions → TT-04 RESHAPE (only PTY reattach and guardrails survived the reshape; registry/wake lane deferred).
- parent_watchdog.py:33 and scheduler/run_receipts.py:61 bare-pid probe fixes → SCHED-P1 (this unit ships the shared fingerprint helper they consume; patching those call sites crosses lanes).
- SCHED-P2's inactivity watchdog use of the kill ladder → SCHED-P2; this unit builds the shared helper in utils/process_group.py if Wave 0 has not, but does not wire the scheduler.
- The full text_hygiene fold (absorbing prompts/agent_prompts.py:_CONTROL_TAG_RE and the SP-2 fold table + random-boundary wrapper) → SP-2 / MCP-B per backlog §3.3; if Wave 0 has not landed the module, TT-01 builds only the minimal stripper its own paths need.
- write_config.py's atomic write (HM07-M2) → routed through the same utils/durable_write.py primitive but the call-site migration belongs to the config-write/BIND-01 packet (OTHER-P5/BIND-01 row), not this unit; this unit converts _write_file only.
- execute_code-specific hardening (monitor deadline, dispatch-hook disarm, sys.* mutation) → already shipped in R-07; explicitly out of TT-01 per the verdict ("TT-01's scope is the shell-exec path... which R-07 did not touch").
- LaunchAgent/supervisor tail and any watchdog-daemon lifecycle → dropped from TT scope per SCHED-P5's RESHAPE (deferred behind founder decision).
- Any migration or re-redaction of existing terminal_blocks rows → dropped per the standing rule "no users yet — leave superseded data on disk, unread."

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
