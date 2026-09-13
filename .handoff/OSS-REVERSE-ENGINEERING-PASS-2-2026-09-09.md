# OSS reverse-engineering pass 2 — are the lifts as solid as their origins, and what else is worth taking

**Date:** 2026-09-09
**Sources:** OpenClaw `/Volumes/Thunderbolt/AI/openclaw` (2026.9.2 @ 3f3c5b2ebef), Hermes `/Volumes/Thunderbolt/AI/OSS/hermes-agent` (@ d9833c5615), open-claude-code `/Volumes/Thunderbolt/AI/OSS/open-claude-code` (@ 22a47be)
**Target:** Halbert main `cc03e175` (waves 1–6 of the 2026-09-07 lift program merged)
**Companion files:** `.handoff/oss-pass-2/` — the full remediation plan, the twelve workstream sections, the coverage report, the audit digests and the merged machine-readable results. Section 9 indexes them.
**Predecessors:** `OSS-REVIEW-OPENCLAW-2026-09-07.md`, `OSS-REVIEW-HERMES-2026-09-07.md`, `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`.

The founder asked two things: is every mechanism Halbert lifted from these repos as solid as the origin, and what else in them is worth repurposing for Halbert's own tasks. This document answers both. Every claim below was made by an agent that read the cited code and was then checked by a second, adversarial agent; the counts say how much survived.

---

## 1. Verdict

**The pure modules are as solid as the origins and in several places stronger. The wiring seams are not, and that is where the program's value is still unrealised.**

Seventeen solidity audits compared each lifted mechanism, invariant by invariant, against the origin file it was taken from. Of 221 gaps found, 181 survived a combined origin-accuracy and Halbert-accuracy refutation (20 high, 70 medium, 91 low); 40 were refuted. Of 109 suspected Halbert-side bugs, 105 were confirmed, many by running the module. The shape of the result is the same in every unit:

- **The module that was ported as a file reproduces the origin's invariants**, and Halbert is stronger on a recurring set of axes: fail-closed defaults where the origin defaults open, no model names anywhere, no content stored in promotion signals, a database constraint rather than a cursor for the one-open-leaf rule, defanged summaries at the prompt choke point, a universal camera gate on MCP egress.
- **The consumer the origin wires the module into was often never wired.** Promotion signals are write-only; occurrence idempotency, `rebuild_fts()`, the ask axis, `meets_floor`, `requires` and the modality budget prompt block all exist with no caller. Seventeen mechanisms were merged with a docstring claiming an invariant the running daemon does not have.
- **Where a seam was wired, the order is wrong at the one place the origin pins hardest.** The mid-turn steer runs before the relay receipt and the claim stamp, so an unidentified voice in the room can steer the owner's running admin turn. The registry pass runs after the pattern pass. The catch-up run's completion lands on a sibling job record while registration blanks the parent. The FTS DDL runs before the degradation breadcrumb is read.
- **Three more shapes recur:** synchronous work on the event loop, fail-open on the exception path of an otherwise deny-by-default module, and singletons or tests that resolve the live data directory at import.

The prescription is the same everywhere: keep the modules, re-wire the seams, and add the origin tests that were left behind. The remediation plan groups all 181 gaps and 105 bugs into fifteen file-disjoint packets (section 3.4).

**On the second question:** 46 discovery units read the subsystems the 2026-09-07 reviews never reached. Readers produced 789 candidates; independent verifiers kept 589, dropped 182 and added 274 mechanisms the readers had missed, for a verified pool of 881 items across twelve Halbert workstreams. Twelve synthesis agents grouped them into 74 proposed packets. The single most consequential class of finding was not new features but **live defects the origins had already fixed**: every stdio MCP server inherits Halbert's whole environment including its own MCP token; the terminal "stage into shell" route writes the raw string into a live PTY with no gate and no escaping, so an embedded newline executes; the approval engine sets `expires_at` and nothing reads it, so a pending approval lives forever; the streaming LLM client uses a total timeout that kills a healthy long generation at 120 s; `rm${IFS}-rf` and `$(echo rm) -rf` classify MEDIUM and run; the wake-word detector is hard-coded to an ONNX backend that is dead on the founder's own arm64 machine; the Tauri shell deliberately starts a second backend on another port against the same conversation store. Section 4 lists these first.

Two findings correct standing documents. The C2 speech summarizer is unreachable: the Haloysius engine's voice-risk word budget caps every spoken reply at 12–35 words upstream of the summarizer's 600-character gate, so the master plan's agenda item "spoken summarization once a utility slot exists" is the wrong next step. Meanwhile the Home Assistant satellite path speaks raw `response_chunk` events that bypassed the echo guard, the word cap and the quality rules. And packet 03's decision not to record process start time beside the owner pid is reopened by evidence that boot recovery compares a previous boot's pid against a freshly reassigned namespace.

---

## 2. How the pass ran, and what to trust

**Method.** Two workflows, 134 agent completions, about 32.6 million subagent tokens.

1. *Solidity audits* (17 units, Fable, high effort): each read the Halbert files and the origin files in full, enumerated every origin invariant (over 700 across the 16 units whose text survives), classified Halbert's status per invariant, and wrote gaps with a failure scenario, a test and a fix. Each audit was then refuted by one Opus agent applying both lenses — does the origin really do this and is it load-bearing there; does Halbert really lack it, or does a design doc record a deliberate decision — and confirming or rejecting every suspected bug, often by running the module.
2. *Discovery* (46 units: 24 OpenClaw, 20 Hermes, 2 open-claude-code; Sonnet readers, Opus verifiers): each reader covered one subsystem and wrote candidates with origin `path:lines`, the mechanism, Halbert's state and a task. Each verifier re-opened every citation, corrected Halbert-state claims by reading rather than grepping, dropped what it could not confirm, and listed what the reader missed.
3. *Synthesis* (14 agents, Fable): one section per workstream, one remediation plan over the audits, one coverage report.

**What was lost.** The founder's session usage limit ended the first audit run after ten units; a later reset wiped the session scratch directory. Six audit units (A06 scheduler, A08 store, A10 tts, A11 permission lattice, A13 skills, A15 heartbeat/catch-up) survive only as the orchestrator's digest (titles, truncated evidence and fixes) plus the refuter's full per-gap verdicts. Their gaps are as trustworthy as the rest — the refuter re-verified every one at the real lines — but their `proposed_test`/`proposed_fix` text is truncated; a packet writer must re-derive the test from the origin test named in the record. The recovered data now lives in `.handoff/oss-pass-2/`, never in a temp directory.

**What to distrust.** Audit line numbers drifted (A08's were shifted about 150 lines on the Hermes side; A02/A03/A04 by 3–14 lines); the remediation plan quotes the refuter's corrected lines and packets must not paste the audit's. Grep-derived Halbert-state claims were the most common reader error (HM20 had four wrong, OC03 four, OC05 two); the verifiers corrected them and the sections follow the verifier. Unit HM09 (Hermes MCP client) is the one broken cell: its reader wrote a placeholder file, so its 18 candidates are unverified; the verifier read the unit itself and its 13 first-hand findings are the trustworthy HM09 output. Coverage is thin by construction — about 6.5% of the three repos' source files were opened — and the coverage report shows that miss count does not track read percentage: a second lens on the same pages finds more than more pages.

---

## 3. Solidity audit

### 3.1 Counts

| Unit | Mechanism | Invariants | Gaps confirmed / refuted | Confirmed high | Bugs confirmed |
|---|---|---|---|---|---|
| A01 | memory promotion store | 40 | 13 / 2 | 2 | 10 |
| A02 | eval harness + verdict contract | 50 | 18 / 0 | 1 | 7 |
| A03 | redaction registry + Tier-2 choke point | 43 | 11 / 1 | 1 | 4 (2 rejected) |
| A04 | execute_code + script RPC host | 38 | 11 / 0 | 3 | 6 |
| A05 | echo guard, display seam, turn digest | 50 | 12 / 4 | 2 | 6 (1 rejected) |
| A06 | scheduler durability (lost text) | 52 | 10 / 4 | 3 | 7 |
| A07 | interrupt algebra | 45 | 11 / 2 | 2 | 4 |
| A08 | conversation-store hardening (lost text) | 54 | 10 / 3 | 3 | 7 |
| A09 | channels + voice ingress | 39 | 4 / 2 | 1 | 6 |
| A10 | TTS quality + speech summarizer (lost text) | 42 | 7 / 7 | 2 | 4 |
| A11 | permission lattice + consent (lost text) | 42 | 12 / 0 | 2 | 8 |
| A12 | claims ladder + admission graph | 43 | 8 / 2 | 0 | 6 |
| A13 | skills plane (lost text) | 59 | 13 / 0 | 0 | 10 |
| A14 | utility model slot | 33 | 7 / 2 | 1 | 6 |
| A15 | heartbeat + boot catch-up wiring (lost text) | 34 | 9 / 3 | 0 | 5 |
| A16 | session tree + compaction | 42 | 8 / 2 | 0 | 4 (1 rejected) |
| A17 | MCP client boundary | — | 17 / 6 | 3 | 6 |
| **Total** | | | **181 / 40** | **20** | **105 (4 rejected)** |

High counts are after the refuter's severity adjustments. A10's seven refutations all trace to one fact the audit missed: the engine word cap makes the summarizer unreachable.

### 3.2 Cross-cutting themes

Each theme is a failure shape; the ids are the instances. A packet that fixes one instance should fix every instance in its own files. Full lists are in `oss-pass-2/remediation_plan.md` section 2.

1. **Module ported, consumer never wired; dead vocabulary shipped as merged** — A01-G1, A01-G8, A06-G1 + A15-G2, A06-G8, A08-G3, A10-G7, A11-G1, A12-G2/G4, A13-G6, A16-G3, the A13 `allowed_tools` bug, the A14 `task` bug, the speech summarizer.
2. **Ordering at the wiring seam** — A09-G1 = A07-G1 (steer before receipt and claim), A03-G2 (patterns before registry), A03-G3 (raw secret evicted first), A08-G2 (FTS DDL before breadcrumb), A06 bug 1 + A15-G1 (catch-up on a sibling record), the A13 receipt-before-existence-check bug.
3. **Sync call on the event loop, or no cancellation handle** — A14 bug 3, A10 bug 4, A12 bug 2, A07-G5, A07-G10, A02-G7, A15-G7, A06 bug 3.
4. **Fail-open on the exception path of a deny-by-default module** — A12 bug 1, A11 `halt=None`, A11-G2, A08-G1/G7, A03-G10, A02-G5, A06-G9, A13-G1, A15-G6, A09 bug 1, the A06 `{'status':'error'}`-recorded-as-`ok` bug.
5. **Docstring, test or log claims the origin's invariant the code lacks** — A02-G1, A08 bug 1, A05 `redacted:true`, the vacuous tests in A07/A10/A01, A13's non-existent `halbert skills list`, A04-G5.
6. **Unbounded growth or a bound in the wrong place** — A01-G6, A04-G3, A05-G6/G11, A06-G5, A08-G11, A17-G2/G16, the A13 YAML-alias OOM (a 447-byte frontmatter would OOM the daemon at start), A03-G6.
7. **Test isolation against the live data dir; path pinned at import** — A08-G12 (the conversation store ignores `HALBERT_DATA_DIR`), A01 bug 7, A13 bug 10.
8. **A second egress path outside the one redaction seam** — A10-G5 (Wyoming raw chunks), A05-G2 (timeline reload), A05-G5 (spoken tail, errors, confirmations), A03-G1 (coercion after the choke point), A03-G4/G5/G9, A04-G4, A17 bug 6, A17-G9.
9. **Locality or secret policy not threaded to a new consumer** — A14-G4 (a `:cloud` sibling can receive the spoken copy of a secure turn), A17-G1 (stdio children inherit every token), A15 bug 5 (a `~/.ssh` listing persisted to disk), A01-G4/G5 and A13-G7 (guest and private-mode evidence outside erasure).
10. **Process-global mutation without serialization** — A04 `sys.*` swaps, A04-G11, A08 commit outside the lock, A11 projection race, A03-G10.
11. **In-process thread where the origin owns a child process** — A04-G1/G2, A04 bugs 2/3, A06 bug 3. F-1 accepted in-process `execute_code`; compensating logic is owed.

### 3.3 Fix first

The remediation plan ranks every confirmed high gap and every confirmed bug with a security or data-loss consequence. The seam, failure, fix and pinning test for each are in `oss-pass-2/remediation_plan.md` section 3; this is the ranked list.

| # | Ids | What is wrong |
|---|---|---|
| 1 | A09-G1 = A07-G1 (+ A07 bug 3, A09 bug 2) | An unidentified voice speaker can steer the owner's running admin turn: `routes/agent.py` calls `handle_midturn_arrival` before the relay receipt is consumed and the claim is stamped. |
| 2 | A17-G1 | Stdio MCP servers inherit Halbert's entire environment, including `HALBERT_MCP_TOKEN` and every other server's token. |
| 3 | A17-G3 + bug 2 | `mcp_config.yml` is an unconfirmed arbitrary-command path on macOS: the write classifies MEDIUM and the health monitor launches the new command within a tick. |
| 4 | A14-G4 | The utility-slot ladder never checks locality; a `:cloud` sibling can be picked for a secure turn. |
| 5 | A11-G1 + bug 2 | The ask axis is recorded, never enforced; profile ask rows are written to the ledger as unconditional grants. |
| 6 | A11-G2 + bug 1 | 21 of the 47 shipped profile rows make the first `require()` raise a bare `ValueError` instead of a typed `Denied`. |
| 7 | A03-G1 + bug 1 | Bytes, Paths, Enums and any object with `__str__` are serialized after the Tier-2 choke point (`json.dumps(default=str)`). |
| 8 | A05-G1 + bug 1 | A partial or re-wrapped echo of an acked secret is flagged, delivered anyway, and logged as `redacted: true`. |
| 9 | A10-G5 | The Wyoming/Home Assistant satellite speaks raw `response_chunk` text that bypassed the echo guard, the word cap and the quality rules. |
| 10 | A10-G7 | The model is never told the spoken budget while delivery truncates every voice reply mid-sentence at 12–35 words. |
| 11 | A04-G2 | The script RPC dispatch hook is never disarmed; a thread the script left behind dispatches tools under the old session and role. |
| 12 | A04-G1 + bug 2 | `run_script` never returns when the worker survives the interrupt injection (`except BaseException`, `input()`, `Event().wait()`). |
| 13 | A04-G3 | Unbounded spill file; output counts as activity, so an infinite print loop fills the volume. |
| 14 | A08-G2 + bug 3 | Reopening over a really corrupt FTS index bricks the store: real corruption raises `DatabaseError`, which the open path does not catch. |
| 15 | A08-G3 + bug 7 | No exit from `fts_degraded`; search stays LIKE-only and "forget this" answers 500 forever. |
| 16 | A06 bug 1 + A06-G1 + A15-G1/G2 | Registration blanks the per-job record and catch-up completion lands on a sibling record: duplicate morning reports on a day with two restarts. |
| 17 | A06-G3 | Slots missed while the machine sleeps with the process alive are dropped by APScheduler's 60 s misfire grace. |
| 18 | A07-G2 | An explicit `/stop` while a tool runs is demoted to a steer; the user cannot stop a running command. |
| 19 | A17-G2 + bug 1 | Any stdio JSON-RPC line over 64 KiB kills the MCP transport. |
| 20 | A02-G1 | `run_exam` hands the answerer the gold answer; the R5 harness is not closed-book for any non-regex arm. |
| 21 | A01-G2 + bug 2 | Recency never decays; "decay multiplies ranking" is a no-op. |
| 22 | A15 bug 5 | The monitor-hash probe persists a listing of `~/.ssh` into the data directory. |
| 23 | A08 bug 2 | `add_open_loop` / `close_open_loop` commit outside the store lock. |
| 24 | A08 bug 5 | `forget_request` has no error handling; a runtime without FTS5 aborts the forget. |
| 25 | A13 bugs 1 + 2 | YAML alias expansion turns a 320-byte frontmatter into a 5 M-char description; `budget_multiplier: .nan` fails every matching turn. |
| 26 | A13 bugs 5 + 6 | Skill `protected_paths` compared unnormalized (symlinks, `/./`, the `/bootleg` over-match); `allowed_tools` enforces nothing. |
| 27 | A12 bug 4 | The local-admin predicate accepts the hostname strings `'localhost'` and `'testclient'`. |
| 28 | A12 bugs 5 + 6 | `persona_id` interpolated unescaped into the sibling URL path; the `home:` owner namespace is not fenced from operator node ids. |
| 29 | A12 bug 1 + A09 bug 5 | The claim ladder fails open on its own exception path; a speaker match with a missing profile is a verified claim with no subject. |
| 30 | A09 bug 1 | An unknown modality is treated as a typed admin turn. |
| 31 | A11 bugs 6 + 3 + 7 | `halt=None` is fail-open; a split clock mints a scope-less lease and skips the redaction-required check; `TypeError` escapes `ConsentUnavailable`. |
| 32 | A06 bugs 3 + 2 | A timed-out task thread keeps running while the retry starts a second attempt; a task's `{'status':'error'}` is recorded `ok`. |
| 33 | A17 bug 6 + A03 bug 5 | `MCPToolError` text and the MCP args preview reach the model and UI uncapped and unredacted. |
| 34 | A04 bugs 1 + 4 + 6 | The AST gate misses `from os import system`; runs mutate `sys.*` process-wide; `max_tool_calls=0` becomes 25. |
| 35 | A01 bug 6 + A01-G4/G5 + A13-G7 | Guest and private-mode turns earn promotion evidence; forget does not reach the promotion tables or `skill_events`. |

### 3.4 Remediation packets

Fifteen packets, grouped by module ownership, file-disjoint where possible. Each entry in the plan carries scope, the invariants restored, the origin tests to mirror, phases, STOP conditions and embedded founder decisions. **Dispatch order:** R-01 → R-09 → R-08 → R-05 → R-13 → R-06 → R-10 → R-07 → R-04 → R-03 → R-02 → R-11 → R-14 → R-12 → R-15. R-01, R-09, R-08, R-13 and R-15 are mutually file-disjoint and can run in parallel worktrees. Hot files shared by two or more packets: `agents/state_machine.py` (seven packets), `dashboard/routes/agent.py`, `agents/conversation_sqlite.py`, `agents/threads.py`, `tools/executor.py`, `tools/safety.py`, `tools/role_gate.py`, `dashboard/app.py`, `mcp/config.py`, `mcp/server.py`, `integrations/speech_summarizer.py`.

| Packet | Scope | Units | Gaps / bugs |
|---|---|---|---|
| R-01 | Talk-door ordering and the interrupt algebra: stamp before verb, `/stop` kills, one stop semantics, steer refusal after stop, liveness watchdog, talk-door `IngressDecision` | A07, A09, A12 | 13 / 7 |
| R-09 | MCP client boundary: env whitelist, frame bound, config path CRITICAL + loader rule, description/result hygiene, process groups, breaker, pagination | A17 | 17 / 6 |
| R-08 | Permission lattice: ask axis enforced through an `ApprovalReceipt`, typed `Denied` everywhere, lease expiry and revocation, halt persisted, one clock, surface receipts | A11, A12 | 13 / 8 |
| R-05 | Redaction registry and Tier-2 choke point: registry-first order, newest-raw, min length 6, single-pass alternation, coercion before redaction, MCP credential registration, error-text hygiene, log redaction | A03 | 11 / 4 |
| R-13 | Utility slot: `require_local`, non-chat exclusions, catalog opt-in with negative cache, OpenAI-wire parsing, `task` logging | A14 | 7 / 5 |
| R-06 | Echo guard, display projection, turn digest: guard-side redaction, one scrub seam for every user-visible surface, history projection, digest status and bound | A05 | 12 / 6 |
| R-10 | Speech egress: Wyoming on the committed text through one pipeline, budget hint, fence scanner, barge-in note, sanitizer, summarizer corrected but dormant | A10, A14 | 9 / 5 |
| R-07 | execute_code hardening for the in-process model: deadline, retire on settle, spill cap, redaction, `__main__`, stderr, stop predicate, atomic budget, AST gate | A04 | 11 / 6 |
| R-04 | Conversation store and state ledger: origin corruption predicate, breadcrumb-first open, rebuild at open, zeroed-file quarantine, `last_init_error`, data-dir resolution, pytest guard, WAL posture | A08, A16, A01 | 13 / 9 |
| R-03 | Scheduler durability wiring and heartbeat liveness: parent record keeps last-run facts, occurrence idempotency, wake-time catch-up, rollback classification, receipts retention, liveness markers | A06, A15 | 19 / 12 |
| R-02 | Claims, admission graph, guest routes, voice provenance: prefix graph, closed reason codes, admission receipts, dedupe, end-of-speech read, `seq`/`ts` on the tee | A12, A09 | 9 / 9 |
| R-11 | Skills plane: per-file failure, reload, catalog guidance, description bounds, content scan, `requires` evaluated, telemetry erasure, deterministic ids | A13 | 13 / 10 |
| R-14 | Memory promotion follow-through: read-time recency, trusted counts, clamped components, origin class, erasure, liveness, the ranker's consumer inside the R9 fence | A01 | 13 / 9 |
| R-12 | Session tree: interrupted row, unresolved request in the receipt, deterministic rotation v0 (gated), branch summaries | A16 | 5 / 2 |
| R-15 | Eval harness and verdict contract: closed-book answerer, hedging-aware judge, recovery arm, gate hygiene, judge timeout, breakers | A02 | 18 / 7 |

Six audit units' full text was lost; their packets (R-03, R-04, R-08, R-10, R-11) must re-derive tests from the named origin tests, and the plan recommends re-running those six audits before dispatch if budget allows.

### 3.5 Refuted gaps and rejected bugs

Forty gaps were refuted; five at medium confidence are marked re-check (A01-G10, A08-G13, A14-G8, A15-G10, A17-G17). The plan's section 5 gives the refuter's one-line reason for each so nobody re-raises them. Notable: A07-G12 (no global emergency stop) is refuted because the pause exists and is spelled `safe_mode`; A07-G7 (subagent cancellation) because no `SubagentManager` is constructed in production; A10-G4 (no spoken ceiling) because the engine word cap is the ceiling. Four bugs were rejected, all documented designs (the 80-char echo floor, the deferred `move_leaf` transaction).

---

## 4. Discovery — what else is worth taking

### 4.1 Live defects found in passing

These are not lifts. They are Halbert defects the discovery readers found while comparing against an origin that had already fixed the same thing. Each was spot-checked by a verifier or synthesizer on main `cc03e175`. They belong at the front of any dispatch.

| Id | Defect | Seam |
|---|---|---|
| HM09-M1 = A17-G1 | Every stdio MCP child inherits `os.environ`, including `HALBERT_MCP_TOKEN` and every other server's token. | `mcp/client.py:239` |
| OC22-M1 | The "stage into shell" route writes the raw command into a live PTY with no gate and no control-character escaping; an embedded newline executes. Breaks the standing "staged, never executed" directive today. | `dashboard/routes/terminal.py:407-423`, `streaming/pty.py:329-333` |
| OCC01-M1 | The tree's only `shell=True` runs a caller-supplied string, reachable from `POST /api/settings/simulate/command`, outside every gate. | `approval/simulator.py:176-182` |
| OC14-M2 | Approvals never expire: `expires_at` is set only on request and read by nothing; `ApprovalStatus.EXPIRED` is never assigned; `mode='auto'` grants by argument. | `approval/engine.py:134-158, 317-332` |
| OC05-M1 | `models.yml` (the API-key store) has an unlocked read-modify-write while `being.yml` is flock-guarded; the founder runs concurrent sessions. | `config/being_config.py:506-580` vs the models path |
| OC05-M2 / M3 | `write_config` returns the raw unified diff of any host config file to the model unredacted, and its dry-run preview skips the policy gate entirely. | `tools/write_config.py:198-266`, `tools/base.py:40-59` |
| OC18-M2 = HM03-C7 | The streaming LLM client uses `ClientTimeout(total=120)`, so a healthy long local generation is killed at 120 s while a silent one is not caught for 120 s. | `agents/llm_client.py:225` |
| HM03-M1 | The circuit breaker is write-only: `is_circuit_open` and `record_success` have zero callers. | `agents/error_recovery.py:105-233` |
| HM07-M4 | `rm -rf ~/Documents` requires confirmation but `r\m -rf`, `rm${IFS}-rf` and `$(echo rm) -rf` classify MEDIUM and run (verified live). | `tools/safety.py:642-720` |
| HM02-M1 = HM01-C13 | A local model's truncated tool-call JSON becomes `args = {}` and the tool runs with no arguments. | `model/client.py:456-465`, `agents/llm_client.py:258-267` |
| HM04-M3 | `run_command` spawns without `start_new_session` and kills only the direct child on timeout; orphans survive. The correct reaper already exists in `streaming/pty.py`. | `tools/executor.py:832-909` |
| OCC02-M1 | `run_command` has two execution paths; the subprocess fallback (taken whenever no SSE client is subscribed: scheduler jobs, voice turns, MCP calls) applies no redaction, no output bound and writes no `terminal_blocks` audit row. | `tools/executor.py:832-903` |
| HM16-M1 | The dashboard's cancel button does not stop a scheduled job: `routes/jobs.py` builds its own `SchedulerEngine` and never touches APScheduler. | `dashboard/routes/jobs.py` |
| HM11-M3 | The Tauri shell deliberately starts a second backend on another port against the same conversation store; nothing locks the data dir. | `src-tauri/src/lib.rs:44-70`, `dashboard/__main__.py` |
| OC08-M2 | The backend writes no log file, and its one log line is hand-built JSON that any quote or newline in a message breaks. | `dashboard/__main__.py:22-26` |
| HM08-C1 | The wake-word detector hard-codes `inference_framework=onnx` for a `.tflite` model; dead on macOS arm64. | `audio/speech/wake_word.py:83-86` |
| OC12-M1 = OC24-M2 | Untrusted text is stripped of Halbert's own tags but not of chat-template special tokens; `<|im_start|>system` in a filename forges a role boundary on a local model. | `prompts/agent_prompts.py:1241-1270` |
| OC24-C1 | The dashboard WebSocket accepts a `?token=` query parameter — the exact pattern in OpenClaw's own security advisory. | `dashboard/auth.py` |
| OC19-M1 | The SSRF check validates the URL once and then follows redirects (`allow_redirects=True` on every call). | `dashboard/routes/llm.py:98-128` and eleven call sites |
| HM14-C4 = HM13-M2 = A08-G5 | The venv's SQLite is 3.39.4, inside the documented WAL-reset-bug band, with four WAL stores and several connections per file. | `.venv` (Python 3.10.9) |
| HM19-M1 | Blocking `subprocess.run` calls inside async route handlers stall the heartbeat, the WS pumps and the scheduler tick; no ruff config exists. | `dashboard/routes/services.py:246-261`, `discovery.py:481/501`, `rag.py:408` |
| OC08-C16 | A false `0.00` load average is formatted into the prompt on platforms where it was never measured. | `context/extra_adapters.py:328` |
| HM14-C20 | mDNS broadcasts `persona+socket.gethostname()` as the node id, against the never-raw-hostname directive. | `federation/peer_discovery.py:295` |
| OC22-C7 | `get_memory_info()` reads `/proc/meminfo`; broken on the host it identifies as. | `tools/system_info.py` |

### 4.2 Per-workstream summary

Each section in `oss-pass-2/section_<workstream>.md` groups its items into themes, merges duplicates across repos ("confirmed twice" where OpenClaw and Hermes agree), lists the related confirmed audit gaps, names what not to lift, proposes packets with hot files, and ends with quotable founder questions. Below: item count, the top items, the packets and the decision count.

**Memory** (36 items, 6 packets, 7 decisions). Top: the SQLite WAL-reset version gate; a verified online-backup snapshot of Halbert's own stores (nothing backs them up today; `chromadb_manager.py:862-872` raw-copies a live sqlite file); the compaction gate driven by real `prompt_tokens` (read at `llm_client.py:279,491` and discarded) instead of a character estimate; an origin-class eligibility gate before automatic injection; a read-side visibility filter (ownership, forgotten, cutoff) on search hits — `ownership.py` is writer-only by its own docstring. Packets MEM-P1 read-side trust axis → P2 promotion mechanics + product-boundary test → P3 store durability → P4 continuity doctor and promotion inspector → P5 staged autonomous writes, vault rule, reflex lifecycle → P6 compaction gate.

**Conversation, session, compaction** (65 items, 6 packets, 9 decisions). Top: whole-file corruption quarantine distinct from FTS fail-open, with a startup `quick_check`; an untrusted-tool-result delimiter block through one shared prompt-literal sanitizer (Halbert has that sanitizer three times with different rules); the malformed tool-call argument repair ladder; a chained SIGTERM/SIGINT exit-flush handler installed before uvicorn (no signal handler exists anywhere); reading the row `PRAGMA journal_mode=WAL` returns. Packets CSC-01 turn-boundary trust and decode, CSC-02 deterministic context reclaim, CSC-03 the conversation survives the process, CSC-04 store hardening II, CSC-05 turn admission and mid-turn verbs (the hottest, split in two), CSC-06 terminal reattach and desktop boot.

**Permissions, consent, security** (244 items, 6 packets, 12 decisions — the largest section). Top: the MCP child env allowlist; gating and escaping staged commands; removing the `shell=True`; stripping chat-template special tokens; approvals that expire and fail closed. Themes: the command gate (normalize argv before any pattern sees it, then two-tier classification, ported from Hermes `approval_detection.py` and OpenClaw's `command-analysis` tables); approvals bound to exactly what was shown (artefact digest, argv+cwd fingerprint, one presentation builder, fail-closed timeouts); self-modification (the write-approval staging store as the mechanism behind "staged, never executed", the config-key fence that `consent/selfmod.py` defines and nothing calls, honest config writes); instruction sources (skills, context files, MCP metadata); the third-party process boundary (env allowlist, trusted-bin resolution instead of PATH, process groups, git env hardening); one SSRF guard with redirect re-validation; feeding the redaction registry with every resolved credential; a policy descriptor registry where registration carries authorization and an unclassified name is a startup error. Packets P1 command gate → P2 approvals and descriptor registry → P3 self-modification → P4 egress/secrets/redaction → P5 process boundary and file-path primitives → P6 the door, OS-grant axis, doctor/lint, security documents.

**Scheduler, heartbeat, daemon, watchdog** (83 items, 6 packets, 7 decisions). Top: the fire path re-reads the durable record (the cancel bug); owner identity = pid + process start time (reopening packet 03's line 34); per-job auto-disable with a system-job carve-out (today one broken job safe-modes every job); preflight the local model endpoint before admitting a run, skip never substitute; an inactivity-based job watchdog with a run-claim heartbeat. Packets SCHED-P1 receipt truth → P2 honest timeouts → P3 failure containment and the ESTOP → P4 turn liveness and local-model priority → P5 process lifecycle (the deferred daemon packet: loop watchdog, unclean-exit sentinel, bounded shutdown, exit-code vocabulary) → P6 the scheduled-work surface.

**Terminal, tools, subagents** (96 items, 6 packets, 8 decisions). Top: command normalization and per-command-start scanning; refuse-don't-coerce unparseable tool arguments; the MCP env allowlist; a background-process registry (`executor.py:785` ignores `background=True`; `steering.py` promises yield-to-background and nothing implements it); an unattended-origin approval policy (`_handle_awaiting_confirmation` is a no-op with no timeout or origin check, so a HIGH-risk tool from the scheduler pins the one conversation indefinitely). Packets TT-01 shell executor hardening → TT-02 child-process boundary fence → TT-03 command classifier v2 and the confirmation gate → TT-04 background registry, yield, wake and the watched-terminal surface → TT-05 tool-loop guardrails and malformed-call recovery → TT-06 subagent manager correctness.

**Voice, media, vision** (37 items, 6 packets, 7 decisions). Top: sherpa-onnx open-vocabulary keyword spotting as the wake engine, zero training, using the onboarding name re-tokenized at runtime (removes the blocker Halbert's own docstring defers indefinitely); fixing the dead ONNX backend; hardening the listener (cooldown, confirmation streak, dead-mic detection, reset on resume; `pipeline.py:347` hands a 512-sample frame to a detector expecting 1280); the Wyoming bypass and the unwired budget prompt; a sequenced replayable per-turn event tail so a reconnecting HUD recovers a turn. Packets VMV-1 a wake word that fires → VMV-2 one spoken egress → VMV-3 inbound media bounds → VMV-4 voice ingress hardening and turn replay → VMV-5 screen and vision truthfulness (the consented day journal is founder-gated) → VMV-6 audio runtime footprint and BYO providers.

**Skills, prompts, learning** (52 items, 6 packets, 7 decisions). Top: the `run_command` fallback path (above); orphan processes (above); typed skill readiness from the `requires` schema nothing consumes; annotating the nine builtin skills with `requires` before SK-4 evaluates an empty corpus; retrofitting builtins with When-to-Use / Quick-Reference / Verification sections and shortening the six over-limit descriptions. Also: an ordered fail-open stop-gate chain at the finalize edge; the rule that a self-check must refuse to run when it would destroy the live state it checks; multi-tool dispatch (today the second tool call in one response is silently lost at `state_machine.py:2669`). Packets SP-1 honest and scanned catalog (SK-4 + SK-5 content) → SP-2 prompt assembly honesty and untrusted-content fencing → SP-3 turn-loop seams → SP-4 slash-command catalog → SP-5 curator invariants (SK-6/SK-7 content) → SP-6 authoring commands.

**MCP, channels, gateway, protocol** (50 items, 6 packets, 8 decisions). Top: the env allowlist; process-group spawn with `killpg` escalation and a pipe-EOF parent-death supervisor (a SIGKILL of Halbert orphans every server on the host it claims to be); a dual-gate config-entry screen at save time and spawn time; tool-description injection scan and invisible-Unicode-tag stripping at registration (server-supplied descriptions enter the tool block unchanged every turn); a turn's cause orthogonal to its transport (`InternalTurnSource`) so a scheduler or tick turn need not lie as `dashboard` and inherit an ASSERTED claim. Packets MCP-A child-process boundary → MCP-B result and description hygiene → MCP-C server lifecycle and discovery → CH-A turn provenance at the talk door → GW-A event-stream reconnect and typed errors → CMD-A one command table.

**Models, providers, cost** (54 items, 6 packets, 8 decisions). Top: a locality gate on the resolved default and every utility rung; idle-gap stream timeouts scaled by context size with a capability-keyed reasoning floor; usage-anchored token accounting (`prompt_eval_count` is already read and discarded, while the character estimate drives `num_ctx` and an undercount makes Ollama truncate the head of the conversation); honouring `Retry-After` in full (`rate_limiter.py` clamps it to 60 s and retries five times, each guaranteed to fail); the write-only circuit breaker; plain-text tool-call repair for local models (OpenClaw `packages/tool-call-repair`, the highest-relevance item for an Ollama-first product). Packets MP-1 locality everywhere and utility-slot solidity → MP-2 provider failure semantics → MP-3 transport liveness → MP-4 measured context and residency → MP-5 local-model output robustness → MP-6 credential custody.

**Dashboard, app, onboarding, diagnostics** (111 items, 8 packets, 9 decisions). Top: a single-instance lock scoped to the data dir; the FTS classifier bug on the diagnostics seam; a real rotating redacted log file; `halbert doctor` as a check registry over the existing Finding/Proposal contract (Halbert has no self-diagnostic surface; `utils/health.py` is dead and `SystemHealthCheckTask` asks a model for a threshold decision against a standing directive); stuck-turn reclamation gated by a closed skip-reason enum. Packets DIAG-01 doctor and readiness → DIAG-02 store integrity on the diagnostics seam → DAEMON-01 one backend per data dir, exit vocabulary, boot forensics → LOG-01 log file, tail, Logs page, support bundle → BIND-01 bind what was checked to what is touched → SURFACE-01 a/b/c progress, staleness, polling, approvals, onboarding → TERM-02 watched-terminal read and close tools → DIST-02 signing, entitlements, usage strings, login item.

**Testing, evals, QA, ops** (25 items, 6 packets, 7 decisions). Top: an autouse egress-safety net blocking any non-loopback `socket.connect` in tests (the founder's live slots were `:cloud`); one hermetic-environment autouse fixture (credential scrub, HOME redirect, import-time constant re-pin — `conftest.py` implements one facet and its own docstring records the canon DB filling with junk); a fail-closed live-database test-isolation guard; ruff ASYNC rules with a per-file-ignores ratchet; per-file process isolation as the test-runner design (the merge log's 205 failures that vanish in isolation are cross-file interpreter-state leakage, diagnosed and lived with). Packets T1 test-run blast radius → T2 suite integrity and the async ratchet → T3 verification before "done" (evidence ledger, stop-time nudge) → T4 wire contracts and the model-name surface eval → T5 doctor, diagnostics and host-truth → T6 posture contracts (CSP, npm install scripts, a security-regression rulepack).

**Other** (28 items, 6 packets, 7 decisions). Top: a create-only self-backup engine (volatile filter, tar-EOF retry, symlink containment — the only tar producer today, `persona/memory_purge.py:296`, follows planted symlinks); structural redaction on every log emit path; measured-not-assumed host stats; one bounded-execution helper replacing the SIGALRM path and `retry_with_timeout` (zero callers); atomically minted install identity. Packets OTHER-P1 through P6.

### 4.3 Mechanisms that recur across sections

Several mechanisms were surfaced independently by three or more units and are the most confident lifts in the pool:

- **Untrusted-data delimiters around tool results and fetched content**, with special-token stripping and one shared sanitizer (HM02-M2, OC15-M1, HM01-M1, OC12-M1, OC24-M2, OC24-C4).
- **Process-start-time or incarnation-token ownership identity** for receipts, locks and leases (OC06-C13, OC18-M4, HM16-C17, HM14-C21, OC06-M1).
- **Approval bound to the reviewed artefact**: sha256 of the diff or script, argv+cwd fingerprint, re-verified immediately before execution (OC13-M1, OC17-C11, OC17-M3, OC09-C7, OC16-M1, A11-G9).
- **One SSRF guard** with DNS pinning and redirect re-validation, imported by every URL-taking tool (OC02-C1, OC10-C1, HM06-C3, OCC01-C1, OC19-M1).
- **Trusted-directory binary resolution instead of PATH** for `security`, `ffmpeg`, `codesign`, `lsof` (OC02-M1, OC10-M1, OC04-M3).
- **Environment allowlists for every spawned process** (HM09-M1, HM03-C13, OC01-C16, HM15-M8, OC08-M4).
- **`halbert doctor`** as a typed check registry with opt-in repair through the approval queue (HM14-C1, OC04-C1, HM15-M4, OC04-M1, HM11-C3).
- **Verification before "done"**: an evidence ledger that goes stale on the next edit and a stop-time nudge (HM04-C1, HM04-C2, HM04-M1, OC24-C8).
- **Event replay rings with sequence numbers** for the dashboard WS, the voice HUD and the PTY (HM18-C1, OC11-M1, A09-G4, HM18-M1).

---

## 5. Founder decisions

The remediation plan carries 24 (FD-1 … FD-24) and the twelve sections carry 96 more; every one is phrased as a quotable question with a recommended default, and work proceeds on the default unless overruled. The plan's set:

| Id | Question | Default |
|---|---|---|
| FD-1 | Auto-continue a crash-interrupted turn at boot? | No; heal to `interrupted`, surface the unresolved request |
| FD-2 | Is `/stop` a hard kill of a running command, and is the stop button the same verb under the generation claim? | Yes to both |
| FD-3 | Ship deterministic compaction v0 now, LLM summary deferred to the R5 gate? | Yes |
| FD-4 | The C2 speech summarizer is unreachable behind the engine's 12–35-word cap: keep the cap, wire the budget hint, leave the summarizer dormant, correct the master plan? | Yes |
| FD-5 | Land the D3-P6 halt-persist half now inside R-08? | Yes |
| FD-6 | Enforce ask-every-use through the existing `tool_confirmation_required` flow with one `ApprovalReceipt` carrying the artefact digest? | Yes, no new UI |
| FD-7 | R-08 owns the runtime QUIET check? | Yes |
| FD-8 | MCP `destructiveHint` → HIGH; `readOnlyHint` stays MEDIUM? | Yes; hints raise the floor only |
| FD-9 | Re-open B1 and drain stdio stderr into a bounded ring buffer? | Yes |
| FD-10 | Opt-in OSV malware preflight for npx/uvx MCP servers? | Not now (the MCP section recommends yes, off by default) |
| FD-11 | SQLite 3.39.4 is WAL-reset-vulnerable and Python 3.10.9 lacks `sqlite_errorcode`: rebuild the venv on a newer Python (ties to `ENV-01`)? | Log ERROR now, plan the bump, no silent journal-mode change (the memory section recommends rebuilding now) |
| FD-12 | Store only the digest for the `~/.ssh` monitor-hash surface? | Yes |
| FD-13 | A flock guard so two daemons cannot share `HALBERT_DATA_DIR`? | Yes |
| FD-14 | Require the wake name when more than one person is present? | Build it, default off (the voice section recommends on by default — **conflicting defaults, founder's call**) |
| FD-15 | Minimum registrable secret length 6 (origin) or keep 4 with word-boundary matching? | 6 |
| FD-16 | Add the deterministic pattern pass at the display seam, superseding `display_transport.py:20-25`? | Yes |
| FD-17 | Return partial stdout when a script raises? | Yes |
| FD-18 | `__name__ == '__main__'` inside scripts? | Yes |
| FD-19 | Erase `skill_events` with the run on forget; suppress telemetry for non-Halbert conversations? | Yes to both |
| FD-20 | Trimmed wording for the six bundled SKILL.md descriptions over 60 chars? | Executor proposes, founder approves copy |
| FD-21 | Utility catalog probe opt-in (default false) with a tri-state slot? | Yes |
| FD-22 | Confirm the Phase-B checkpoint for the promotion consumer inside the R9 fence? | Proceed, review before merge |
| FD-23 | Remove `'localhost'`/`'testclient'` string acceptance from the local-admin predicate? | Yes |
| FD-24 | Record in DECISIONS.md that internal tool results route through the shared redaction core (the parked 05-C)? | Yes |

Decisions that recur across sections and deserve one ruling: internal tool results through the redaction core (FD-24, permissions F-A7, conversation decision 6); the WAL-reset posture (FD-11, memory 1, conversation 1); crash auto-continue (FD-1, conversation 2); the OSV switch (FD-10, permissions F-A8, MCP 1); approvals that expire with `mode='auto'` deleted (permissions F-A1); a real `signingIdentity` so TCC grants survive rebuilds (permissions F-A3 — every OS-grant reads UNDETERMINED until then); unattended-origin approval policy (terminal 1, A11-G7); user-created scheduled jobs (scheduler 7); where `halbert doctor` lives (models 8, dashboard FD-9); the wake-name rule's default (FD-14 vs voice 6). The full per-section lists are in each section's last heading.

---

## 6. Coverage and follow-ups

About 6.5% of the three repos' source files were opened. The coverage report (`oss-pass-2/coverage_report.md`) tables every unit's files-in-scope against files-read and reproduces each reader's own list of what it did not reach. Its findings:

- **Thin is the base state.** Twenty-one units read under 5% of their scope or had eight or more verifier-added mechanisms. Miss count does not track read percentage: HM16 read 77% of `cron/` and still missed nine; OC15 read 1.3% of `src/agents` and missed five. The verifier was finding what the reader's framing excluded.
- **Four unassigned areas matter.** `openclaw/src/skills/workshop` (144 files, 0.7% read, in no unit's scope) is a complete self-improving-skill governance lifecycle — propose, review, apply under a lock, hash-pin, roll back — and the SK-series lifted only the format; this is the largest oversight of the split. `openclaw/src/mcp` (12 files, 0% read) is the MCP *server* side, the closest origin analog to Halbert's 18-tool `mcp/server.py` awaiting the founder-ruled B6 audit. `openclaw/apps/macos` was in scope and read at 1.2%. Hermes `docs/` holds the rationale (rfcs, incident write-ups) that several refutations were made for want of.
- **Leave unread on purpose:** the 94 unassigned OpenClaw extensions are chat-platform adapters (multi-tenant fan-out) and model-vendor adapters (baked model identifiers), both against standing directives.

Twenty follow-up units, sized like this pass's. P1: F01 macOS host integration (`apps/macos`, LaunchAgent, TCC, port ownership, sleep/wake — every one of OC22's six macOS candidates was kept); F02 the tool-admission family in `src/agents` (the origin's "one policy pipeline"); F03 the MCP server side plus the HM09 re-run; F04 the skill workshop governance; F05 the origin rationale docs (best value per file); F06 config/state durability (OC05's 24 files already found the `models.yml` lost-update). P2: F07 gateway auth and approvals; F08 Hermes self-diagnosis and update; F09 first-run and onboarding; F10 the plugin capability contract; F11 control-UI patterns; F12 the Hermes plugin runtime; F13 the reference agent loop in the decompiled archive; F14 secrets at rest and the credential broker. P3: F15–F20 (command surface, Hermes tools remainder, desktop RPC bridge, protocol contracts, cross-cutting primitives, the deterministic policy extension).

---

## 7. Corrections to standing documents

- **`OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`, deep-pass agenda item 4** ("spoken summarization once a utility slot exists"): the slot exists; the summarizer is unreachable behind the engine's word cap. Replace with FD-4's disposition.
- **Packet 03 out-of-scope line 34** (owner start-time liveness): reopened by boot-recovery pid reuse (scheduler decision 1); record the start-time field in, the multi-instance matrix still out.
- **`display_transport.py:20-25`** records registry-only redaction at the display seam; FD-16 supersedes it.
- **DECISIONS.md rows to add:** 05-C resolved (internal tool results through the redaction core); the replay-tail eviction reading of never-delete; a declared system channel for machine-originated turns; the wake-name default once ruled; ESTOP and the no-inference-slot-field rule from the scheduler section.
- **ROADMAP rows touched by findings:** VOICE-1 (dead wake backend; satellite bypass; budget hint), MIND-1 (duplicate slots; cancel bug), TRUST-1 (approvals never expire; staged commands unescaped; `shell=True`; command-normalization bypass), CI-1 (per-file isolation explains the 205 failures; no ruff gate), SEC-15 (utility slot bypasses locality), CFG-1 (`models.yml` unlocked RMW; conversation store ignores `HALBERT_DATA_DIR`), TERM-1 (`background=True` ignored; no registry), MCP-1 (env leak; server side unread), DIST-1/APPLE-1 (signing identity for TCC), SKILL-1/KNOW-1 (workshop governance unread).

---

## 8. Process notes and lessons

- **Usage limits shaped the run.** The first audit workflow (83 Fable agents) hit the founder's session limit after ten completions; a resumed run with Sonnet readers, Opus verifiers and one combined Opus refuter per unit completed all 110 remaining agents. That mix is the one to reuse: reading is cheap and verification is load-bearing (23% of candidates were dropped and 274 were added by verifiers).
- **Persist to a durable directory.** A session reset wiped the scratch directory and cost six audits their full text. Everything now lives under `.handoff/oss-pass-2/` and, as a working copy, `~/.claude/projects/-Volumes-4TB-BAD-Halbert/oss-pass-2-data/`.
- **Verify Halbert state by reading, never by grep.** The most common reader error was "grep found nothing, therefore absent"; verifiers reversed several. Line numbers in audits drift; packets must cite the refuter's corrected lines.
- **A second lens beats more pages.** Miss counts did not correlate with read percentage.
- **The pipeline shape worked:** reader → citation verifier → workstream synthesizer, with a refuter for anything that becomes a packet. The remediation plan spot-checked its five load-bearing claims on main before writing.

---

## 9. Where everything is

`.handoff/oss-pass-2/`:

- `remediation_plan.md` — verdict, themes, the 35-row fix-first table with seams and pinning tests, packets R-01…R-15 in full, the 40 refuted gaps with reasons, rejected bugs, FD-1…FD-24.
- `section_<workstream>.md` ×12 — the discovery synthesis per workstream (every kept and verifier-added item appears in exactly one theme or the do-not-lift list).
- `coverage_report.md` — per-unit and per-directory coverage, thin units, unassigned areas, the twenty follow-up units, the HM09 anomaly.
- `audit_overview.md` — all 17 audits: every gap with confirmed/refuted status and effective severity, every bug with its verdict.
- `lost_units_digest.md`, `lost_units_verdicts.md` — the six lost audits' digest and the refuter's per-item reasons.
- `discovery_digest.md` — one line per kept and verifier-added item (881), grouped by workstream.
- `merged_audits.json`, `merged_discoveries.json` — the complete machine-readable results (full audit records for eleven units; every discovery candidate including dropped ones with verifier notes; `unread_areas` and `verify_summary` per unit).

Working data (same content plus per-workstream splits and the raw per-agent files): `~/.claude/projects/-Volumes-4TB-BAD-Halbert/oss-pass-2-data/`. Workflow journals with every agent's full return: `~/.claude/projects/-Volumes-4TB-BAD-Halbert/b0e3f0dd-594e-4bec-b7ce-4859472b38f8/subagents/workflows/{wf_bf71f91c-0be,wf_b6d3ae9c-83f,wf_3fc6edb8-8b7}/journal.jsonl`.
