# OSS Pass-2 Discovery — Formal Implementation Plan

Written 2026-09-11. This is the consolidated, formal implementation plan.
It supersedes:

- `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-2026-09-11.md` (the original
  plan, Parts A–D and the UX scrutiny pass in Parts E–F)
- `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-REVIEW-AND-REINVENTIONS-2026-09-11.md`
  (the external review)

It incorporates the review's valid corrections, adopts its milestone
restructuring where it improves dispatch, and pushes back where the review
overstepped. The authoritative verdicts remain in
`.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md`.

No code is changed by this document. It is a dispatch plan.

---

## 1. External review — what we accept and what we push back on

### Accepted corrections

Three real errors in the original plan, all confirmed by verification:

1. **MP-5 was accidentally dropped.** MP-5 (local-model tool-call repair)
   was ACCEPT in the final report but absent from every phase table in the
   implementation plan. `model/client.py:_normalise_tool_calls` coerces
   unparseable arguments to `{}`, silently destroying tool calls from local
   models that emit markdown-wrapped or prose-prefixed JSON. This is a live
   defect for Halbert's primary target (local models). **Corrected: MP-5
   added to Milestone 1.**

2. **activity_clock was never built.** The plan listed activity-clock as a
   dependency for SCHED-P2, SCHED-P4, TT-05, and DAEMON-01b but never put it
   in Phase 0. Four consumers, zero builder. **Corrected: activity_clock
   added to Milestone 0.**

3. **Phase 3 was a 28-unit logjam.** The original plan's Phase 3 mixed
   terminal PTY reattach, Darwin memory probes, audio wake-word tuning,
   SQLite integrity, dashboard polling, and stuck-turn reclamation into one
   undifferentiated mass. The review's milestone restructuring groups work
   into cohesive subsystems, which is a better dispatch shape.
   **Corrected: adopted the milestone structure with corrections (below).**

### Pushback — where the review overstepped

1. **The review dropped text_hygiene from Milestone 0.** The review's
   Milestone 0 table lists 8 primitives but omits text_hygiene, even though
   TT-03, CH-A, LOG-01, VMV-3, and VMV-5 all list it as a dependency. A
   primitive that five consumers need but nobody builds is the exact defect
   the milestone restructuring was supposed to fix. **Corrected:
   text_hygiene restored to Milestone 0.**

2. **The review dropped ~15 packets.** The review's 5 milestones account for
   ~35 packets. The original plan had ~50. Missing: GW-A, SCHED-P2,
   SCHED-P4, SCHED-P5, TT-05, SP-2, CSC-01, CSC-02, CSC-04, P1, P4, P6, T2,
   T4, OTHER-P1, OTHER-P3, OTHER-P5, BIND-01a, SP-4a. These are ACCEPT or
   promoted-ACCEPT packets with real consumers. Dropping them is not
   defensible. **Corrected: all packets accounted for in the milestone
   plan below.**

3. **The "reinvention" framing overstates novelty.** The review proposes
   four "reinventions" from Warp, Open-Claude-Code, Hermes, and OpenClaw.
   Three of the four are already in the plan under different names:
   - "Semantic Watched Envelopes" (Warp) — Halbert already has OSC 133/7
     shell integration in `streaming/shell_integration.py` and
     `streaming/agent_pool.py`. The reinvention is already built; the
     residual is CSC-06 (reconnect) + TT-04a (guardrails), which are in
     Milestone 2.
   - "Unified Staging & Inode Approval Protocol" (Open-Claude-Code) — this
     is P2 + TT-03 + SURFACE-01a, already in the plan.
   - "Turn Cause Axis" (OpenClaw) — this is CH-A, already in the plan.
   Only "Measured Machine Stop-Gates" (Hermes reinvention of T3/TT-05) adds
   a genuinely useful framing: verification should check measured OS state,
   not ask a model. This is the "verification-before-done" cross-cutting
   primitive, and it is adopted as a design principle below.

4. **"Receipt-to-Reflex Staging" is gated.** The review proposes that
   successful troubleshooting sequences become staged "Machine Reflexes."
   This is SP-5/SP-6, which are DEFERRED behind the skills write path (SK-6)
   and founder decisions. The review does not acknowledge this gate. The
   idea is sound; the gate is real. It stays in Milestone 5.

5. **Tactical directives are too rigid.** "Do not touch product code before
   Milestone 0 lands" would block SP-3 (a one-line data-loss fix) behind T1
   (a multi-day test infrastructure effort). SP-3 is independent of T1 and
   should land immediately. "Dispatch milestones sequentially" would block
   CSC-06 (terminal reconnect, no model-pipeline dependency) behind MP-5
   (tool-call repair). The milestones are thematic groupings, not strict
   serialization barriers. **Corrected: milestones are dispatch themes;
   within-milestone parallelism and cross-milestone independence are
   respected.**

### Adopted from the review

- The milestone structure (cohesive subsystem groupings instead of a flat
  phase list).
- The `activity_clock` primitive and its contract.
- The `DiagnosticFinding` shape for `halbert doctor` (domain, code,
  severity, message, why_trust, remediation).
- The "measured machine stop-gate" framing: verification checks measured OS
  state, not model judgment.
- The first-person machine-tone reminder for error and recovery states
  (already a standing directive, but worth restating).

---

## 2. Design principles

1. **Primitives before consumers.** Shared modules land before the packets
   that consume them. This prevents duplicate implementations (the standing
   rule against duplicate primitives).
2. **Live defects first.** The cheapest, highest-value work is fixing bugs
   that silently lose data or leak credentials today.
3. **One merge per seam.** Packets that touch the same file merge into one
   dispatch unit.
4. **Verification-before-done.** A claimed action is validated against the
   resulting artifact/state before reporting completion. Verification
   checks measured OS state (port bound, exit code, file hash), not model
   judgment.
5. **Milestones are dispatch themes, not serialization barriers.** Within a
   milestone, file-disjoint units parallelize. Across milestones, a unit
   may proceed if its dependencies are met even if the prior milestone is
   not fully complete.
6. **Standing directives hold.** No model names on surfaces. No model for
   redaction. No UI-executed commands. No migrations. Two-dependency
   contract. One locality judge. One feature gate. No emoji. Shared-token
   colours. No duplicate primitives. No lifecycle infrastructure before a
   write path exists. macOS-first, not Linux/systemd.

---

## 3. Test discipline

Every implementation unit includes tests. From `AGENTS.md`:

```bash
# Main tree
arch -arm64 .venv/bin/python -m pytest halbert_core/tests

# Worktree
arch -arm64 ./wt_pytest.py halbert_core/tests
```

`main` is not green — get a baseline on the merge-base before attributing
failures. Milestone 0's T1 (hermetic environment) is first precisely
because it makes the test suite trustworthy for everything after.

---

## 4. Remediation status (verified)

| Batch | Packets | Merged to `main`? |
|---|---|---|
| Opus | R-01, R-02, R-04, R-05, R-06, R-07, R-08, R-09, R-10, R-11, R-12 Phases B/C, R-14 | **Yes** — merge `55ecef87` |
| Sonnet | R-03, R-13, R-15, R-12 Phase A | **No** — branch `fix/remediation-sonnet-batch-1` still open |

Packets that cite opus-batch remediation (R-01, R-02, R-04–R-11, R-14) may
assume it is merged. Packets that cite sonnet-batch remediation (R-03,
R-13, R-15, R-12 Phase A) must verify before claiming overlap. Milestone 5
handles this verification.

---

## 5. The milestone plan

Six milestones. Each is a cohesive subsystem, not a serialization barrier.
Within each, units are file-disjoint and parallelize unless noted.

### Milestone 0 — Substrate integrity & shared primitives

**Goal:** hermetic test suite, single-instance daemon, and the reusable
modules that everything else depends on. No founder decisions. File-disjoint
— parallelize after T1.

| Unit | Scope | Files | Effort | Verification |
|---|---|---|---|---|
| **T1** | Hermetic test fixture re-pinning every import-time path constant away from the live host. Live-DB guard: suite fails if any test opens `conversations.db` or `~/.config/halbert/skills` on the real host. | `tests/conftest.py`, new fixture | M | Suite runs with zero live-host access |
| **DAEMON-01a** | Single-instance `flock` on data dir; exit vocabulary (75=restart, 78=fatal); `supervised()` probe. | `dashboard/__main__.py`, `dashboard/app.py` | S | Second launch exits cleanly; probe detects supervisor |
| **durable_write** | `utils/durable_write.py` — temp + flush + fsync + `os.replace` + dir fsync + 0600. | new `utils/durable_write.py` | S | Crash before replace: target unchanged. Write + replace: target updated |
| **process_group** | `utils/process_group.py` — `start_new_session` + `killpg` escalation. Reuse pattern from `streaming/pty.py`. | new `utils/process_group.py` | S | Child spawns grandchild; group kill reaps both |
| **activity_clock** | `utils/activity_clock.py` — monotonic activity tracker: `record_activity()`, `idle_seconds()`, `is_stalled()`. | new `utils/activity_clock.py` | S | Activity resets idle; timer fires on inactivity |
| **text_hygiene** | `security/text_hygiene.py` — consolidate `mcp/metadata.py:strip_unicode_tags` (R-09) + `prompts/agent_prompts.py:_CONTROL_TAG_RE` + NFKC fold table + random-boundary wrapper + source-hygiene block. One sanitizer, all consumers. | new `security/text_hygiene.py`; update `mcp/metadata.py`, `prompts/agent_prompts.py` to import | S-M | Existing tests pass; new tests for fold table, boundary, tag strip |
| **subprocess_env** | `tools/subprocess_env.py` — `build_subprocess_env(baseline, extras)` stripping credential-shaped names. Reuse R-09's `build_child_env` pattern. | new `tools/subprocess_env.py` | S | No child receives `*_API_TOKEN` / `*_KEY`; call-site walk test |
| **OTHER-P4** | `utils/deadline.py` — bounded-execution deadline + cancellation. | new `utils/deadline.py` | S | Deadline expiry, cancellation, clean exit |
| **DIAG-02** | Read-only SQLite opener (`mode=ro`, `PRAGMA query_only=ON`) + store integrity diagnostics. | new `utils/sqlite_safety.py` | M | Open production store read-only; writes throw `OperationalError` |

**Sequencing:** T1 first (makes tests trustworthy). Everything else
file-disjoint, parallel after T1.

---

### Milestone 1 — Model pipeline & conversational resilience

**Goal:** fix silent data-loss, enable reliable local-model tool execution,
and eliminate stream/transport failures that kill healthy work.

| Unit | Scope | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **SP-3** | Fix multi-tool dispatch data-loss bug (drops all but first tool call). | `agents/state_machine.py` | S | — | Two tool calls in one turn both execute |
| **MP-5** | Local-model tool-call repair: deterministic extractor for markdown-wrapped JSON, prose-prefixed tool calls, trailing-comma repair. Schema-guided argument coercion. Garbled-output detection scoped by `is_local_model()`. | `model/client.py`, `agents/state_machine.py` | S-M | SP-3 (shares tool-call path) | Raw ````json {"tool":...}```` string produces clean tool execution; garbled output triggers retryable error |
| **MP-2** | Retry-After honoured up to 600s (cap exponential branch only). Interruptible backoff replacing bare `time.sleep`. `BackendIdentity` + `FailureScope` (401 ≠ DNS ≠ timeout). Wire or retire dead circuit breaker in `error_recovery.py` (zero callers confirmed). | `model/rate_limiter.py`, `model/tier_router.py`, `agents/error_recovery.py` | M | activity_clock | `/stop` during backoff returns <0.5s; 401 marks credential unhealthy not DNS; breaker opens after 5 failures |
| **MP-3** | Replace `aiohttp.ClientTimeout(total=120)` with idle-gap detector (`sock_read=idle_gap, total=None`). Abort hook closing aiohttp response from foreign thread. | `agents/llm_client.py`, `model/client.py` | M | activity_clock, MP-2 (shares interruptible backoff) | Healthy stream >120s completes; stopped stream terminates <0.5s |
| **MP-4** | Usage-anchored token accounting (delta from provider's last count). Error-text parser learning real context window. Route-keyed cache `(provider, base_url, model)`. LM Studio loaded-state from its own API. Slot-switch warning. Usage-row instrumentation. | `model/client.py`, `model/llm_config.py`, `context/tokens.py` | M | — | Local and remote same model name hold independent context limits; `num_ctx` driven by measured tokens |
| **DAEMON-01b** | Stuck-turn reclamation watchdog: monitor turn-lock age, auto-reclaim wedged locks after no-progress timeout, gated by skip-reason enum (`awaiting_confirm`, `approval_pending`). One typed receipt per reclamation. **Merge last — touches `state_machine.py`, the hottest file.** | `agents/state_machine.py` | M | activity_clock, DAEMON-01a | Simulated wedged tool call triggers reclamation; lock released cleanly |

---

### Milestone 2 — Watched terminal & sovereign command engine

**Goal:** crash-proof, injection-proof terminal environment with honest
approval binding. Halbert already has OSC 133/7 shell integration in
`streaming/shell_integration.py` and `streaming/agent_pool.py` — this
milestone completes the reconnect and hardening, not the block model.

| Unit | Scope | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **CSC-06** | UTF-8 decoder fix (per-connection incremental decoder, not per-chunk `errors="replace"`). PTY reattach loop (deliver replay buffer as typed `replay` frame, currently dropped). Port announcement on stdout (`HALBERT_BACKEND_READY port=<N>`). Panic hook in Tauri shell. | `streaming/pty.py`, `src-tauri/src/lib.rs`, `dashboard/__main__.py` | S-M | — | CJK/emoji across read boundary decoded cleanly; drop socket, session reattaches; port announced |
| **GW-A** | Wire existing PTY replay ring through terminal WS. `dashboard/event_replay.py` with seq stamping + epoch + bounded ring. `since_seq` reconnect. Typed error envelope for 55 bare `{'error': str(e)}` in `mcp/server.py`. | `streaming/pty.py`, new `dashboard/event_replay.py`, `mcp/server.py` | S-M | CSC-06 (shares PTY replay) | Reconnect with `since_seq` sees missed events; MCP errors typed |
| **TT-01** | Shell executor hardening: process-group kill, PID+start-time fingerprint, redact-before-cap ordering, ANSI/Unicode strip, deterministic exit interpretation, atomic write + read-back, device/inode approval binding. Route redaction through R-05's registry. | `tools/executor.py`, `streaming/agent_pool.py` | M | process_group, text_hygiene, durable_write | Timeout kills process tree; secret across truncation boundary redacted |
| **TT-03** | Command normalization/deobfuscation, fail-closed parsing, deny-list precedence over allow-list, unattended-origin policy, worktree mutation rule. | `tools/safety.py`, `tools/executor.py` | S | text_hygiene | `rm${IFS}-rf` classifies HIGH; deny-list wins; unattended origin refused |
| **TT-04a** | PTY reattach + foreground-command guardrail (nudge `npm run dev` to background) + progress labels + bounded wait on watched session. | `streaming/session_manager.py`, `tools/safety.py` | S-M | CSC-06, GW-A | `npm run dev` yields foreground guidance; PTY survives client restart |
| **P2** | Approval bound to artefact: `(device, inode, content_sha256)`, not path string. Approve-then-replace race prevented. | `approval/engine.py` | S | durable_write | Approve file, modify out-of-band, execution rejected |
| **TERM-02** | Watched-terminal read/close tools. Read passes through display seam + echo guard. Close hides tile, does not kill. Withdraw-not-refuse when no renderer attached. | new `tools/terminal_tools.py` | S-M | TT-04a, GW-A | Terminal tools withdrawn gracefully when no session active |
| **BIND-01a** | Config CAS precondition on config writes (base-hash guard). Prevents silent overwrite by concurrent session. | `model/llm_config.py`, `routes/settings.py` | S | — | Concurrent save rejected with base-mismatch; no silent revert |
| **SP-4a** | Fix `/help`/`/h` drift — add to `RESERVED_SLASH_BUILTINS`, pin with test. | `skills/reserved.py` | S | — | Every name `Terminal.tsx` handles is reserved; `/help` == `/h` |
| **SP-2** | Prompt assembly honesty: tool-output blocks, guest/tool-list drift, non-ASCII fold table. Reuse text_hygiene. | `prompts/agent_prompts.py` | M | text_hygiene | Tool output fenced as data; non-ASCII folded; guest list honest |
| **TT-05** | Tool-loop guardrails: 3-strike repair budget, signature-hashed per-tool guardrails (failing-repeat, no-progress, identical-streak), per-run tool-call ceiling, detach-not-cancel, UNKNOWN-effect marker. | `agents/state_machine.py` | S | activity_clock | 40 tool calls in one message bounded; failing repeat after edit+retry allowed |

---

### Milestone 3 — Memory trust, turn provenance & diagnostic core

**Goal:** honest memory (origin classes, product-boundary test, durable
SQLite), honest turn provenance (cause axis), and the universal diagnostic
sink.

| Unit | Scope | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **CH-A** | Turn cause axis: `InternalTurnSource` (scheduler/tick/tool-event) beside `ChannelDeclaration`. Sanitized bracketed inbound envelope. `config/watcher.py` starvation bug fix. | `agents/channels.py`, `config/watcher.py` | M | text_hygiene | Scheduler turn admitted with honest provenance, no dashboard claim; watcher does not starve |
| **MEM-P1** | Read-side memory trust: `origin_class` column, untrusted rows excluded from silent prompt injection. | `continuity/memory_v2.py`, `continuity/recall_gate.py` | M | — | Untrusted tool observation stored but never silently injected |
| **MEM-P2** | Product-boundary test (secret in transcript does not survive into promoted memory). Contamination backstop (disjunctive content-shape filter + fix dead `provenance` parameter). Envelope strip check. | new test file, `continuity/promotion.py` | S-M | MEM-P1 | Secret in transcript scrubbed before promotion; clean candidate present |
| **MEM-P3** | SQLite durability: `PRAGMA integrity_check`, `halbert backup` (online backup API + verified manifest), `halbert recover` (copy-first salvage). Durable-write helper consolidation. Provenance subject canonicalisation. | `continuity/backup.py`, `continuity/provenance.py` | M | durable_write, DIAG-02 | Backup verified; corrupted DB salvaged without overwriting live |
| **MEM-P6** | Compaction follows real numbers: persist provider `prompt_tokens` per thread; compaction gate uses measured counts, not character estimates. | `agents/assembler.py`, `agents/llm_client.py` | S | MP-4 (usage anchor) | Compaction triggers on actual provider usage |
| **DIAG-01** | `halbert doctor` findings registry: `DiagnosticFinding(domain, code, severity, message, why_trust, remediation)` + `halbert doctor --json` + `GET /api/diagnostics`. Universal sink for every workstream's residuals. | new `obs/doctor.py`, `dashboard/routes/diagnostics.py` | M | DIAG-02 | `--json` outputs structured findings; `GET /api/diagnostics` returns registry |
| **LOG-01 + OTHER-P2** | Merged logging: `JsonFormatter` on `RotatingFileHandler`, `RedactingFilter` on root handler, `LogRecordFactory`, first-char pre-check, redacted support bundle (merged with T5's bundle). One commit — same 30-line `obs/logging.py` hub. | `obs/logging.py`, `dashboard/__main__.py` | M | text_hygiene | Log records valid JSON; secrets redacted; bundle staged, local, redacted |
| **CSC-01** | Conversation crash/recovery: turn-boundary trust, decode integrity. | `agents/state_machine.py`, `agents/conversation_sqlite.py` | M | — | Crashed turn heals to persisted status; no re-submit |
| **CSC-02** | Turn admission and identity: deterministic context reclaim, window-relative budgets. | `agents/state_machine.py` | M | CH-A | Mid-turn input admitted with correct identity |
| **CSC-04** | Session-tree integrity: corruption quarantine, error taxonomy, refcounted registry. | `agents/conversation_sqlite.py` | S-M | — | Corrupt leaf quarantined; tree remains navigable |
| **P1** | Permission lattice residual: command gate rebuild, two-tier classifier, argv-normalisation tables, schema validation at executor seam. | `tools/safety.py`, `tools/executor.py` | M | — | `env FOO=1 python3 -Ic 'rm -rf /'` classified HIGH; schema validation catches malformed args |
| **P4** | Untrusted-data delimiters: deterministic boundaries for external content entering the prompt. | `security/` modules | S | text_hygiene | External content fenced; no prompt injection through delimiter confusion |
| **P6** | Trusted-directory/executable resolution: resolve security-sensitive binaries against trusted paths. | `tools/safety.py` | S | — | Binary outside trusted dirs flagged |
| **OTHER-P1** | State backup / create-only behavior. Respect no-migration rules. | `continuity/` | S | DIAG-02 (read-only opener) | Backup creates new file, never overwrites live |
| **OTHER-P3** | Measured-not-assumed behavior: Halbert reports measured state, not assumptions. | various | S | — | Claim validated against measured artifact before reported |
| **OTHER-P5** | Install identity (replace raw-hostname mDNS node IDs) + bounded downloads (size + deadline). | `federation/peer_discovery.py`, download helper | S-M | durable_write | mDNS node ID not raw hostname; oversized download cut |

---

### Milestone 4 — Grounded UI, voice & ambient stewarding

**Goal:** dashboard reflects live measured data, voice surface works on
macOS ARM64, scheduled work is visible and controllable.

| Unit | Scope | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **SURFACE-01a** | Approval expiry enforcement (`expires_at` never compared to now). Stale-tone override (wedged backend leaves red bar over stale data). LTR trojan-source defence (`dangerouslySetInnerHTML` with no direction attribute). | `approval/engine.py`, `Dashboard.tsx`, `ConfirmationDialog.tsx` | S | — | Expired approval rejected; stale data flagged; RTL override neutralized |
| **SURFACE-01b** | Typed refresh policy (20+ `setInterval` → declarative TTL/interruption/coalescing). Skills settings page (no disable surface today). Reconnect owner (jittered backoff). | `usePolling.ts`, `SkillsSettings.tsx` | S-M | — | Idle dashboard polling CPU near-zero; disabled skill omitted |
| **SCHED-P6** | Dashboard scheduled-work surface: list/history/cancel (frontend already exports `getScheduledJobs()`/`cancelScheduledJob()`, nothing calls them). Webhook URL normalizer. Weekly digest improvements. | `ScheduledJobs.tsx`, `scheduler/executor.py` | S-M | — | Cancel button cancels job directly; webhook URLs normalized |
| **SCHED-P2** | Honest inactivity-based timeouts (not flat wall-clock) + shared process-group kill. Must not kill healthy active work. | `scheduler/executor.py` | M | process_group, activity_clock | Active work survives; truly idle work timed out |
| **SCHED-P4** | Turn liveness: activity-clock approach to turn-level liveness. | `agents/state_machine.py` | S-M | activity_clock | Live turn distinguished from wedged turn |
| **SCHED-P5** | Core lifecycle: bounded shutdown (ten unbounded awaits in `app.py`), unclean-exit sentinel (integrity check on suspicious boot), thaw reconnect (coordinated reconnect after sleep). | `dashboard/app.py`, heartbeat tick | S-M | — | Shutdown completes under timeout; suspicious boot triggers integrity check; sleep/wake reconnects |
| **OTHER-P6a** | Guarded localStorage accessor (11 unguarded sites; `DebugContext.tsx:37` crashes the whole dashboard at mount). | `DebugContext.tsx` + 10 sites | S | — | Storage-disabled webview mounts cleanly |
| **OTHER-P6b** | Settings reload plan: declarative table (`personality.*` → hot, `models.slots.*` → hot rebuild, `dashboard.bind`/`token`/`mcp.servers.*` → restart). | `dashboard/settings_reload_plan.py`, `routes/settings.py` | S-M | — | Personality change takes effect without restart |
| **VMV-1** | Wake-word correctness on macOS ARM64 (openWakeWord ONNX scores near zero on Apple Silicon). sherpa-onnx KWS. Listener hardening (1280-sample frame size, reset-on-resume). | `voice/wake.py`, `voice/pipeline.py` | S-M | — | Wake word fires on ARM64; frame size correct; reset on resume |
| **VMV-3** | Central media limits (max base64/image/audio), MIME sniffing, raw exception leakage fix, credentialed guest-home URL fix. | `routes/audio.py`, `frigate_tools.py` | S-M | text_hygiene | Oversized input rejected; raw exception not leaked; credentialed URL not in display |
| **VMV-5** | Coordinate mapping disclosure: thread pre/post geometry and crop origin, append scale/offset note. | `tools/vision_tools.py` | S | — | Downscaled capture appends scale metadata; coordinates honest |
| **VMV-6** | Audio footprint: idle-unload watcher for resident audio models. Capability assertions (declare-and-assert via `has_capability()`). Runtime health records. | `voice/`, `capabilities.py` | S | — | Idle audio models unloaded; capability refusal names what's missing |
| **T2** | Fix Darwin memory information defect. | `utils/platform.py` | S | — | Memory info correct on macOS |
| **T4** | Wire contracts + model-name-surface evaluation. Must assert absence of model names, not recommend or surface them. | test suite | S-M | — | No model name on any user-facing surface |
| **MP-6** | `build_subprocess_env()` applied to every `subprocess.run`/`Popen`/`PTYSession` call site. | `tools/system_tools.py`, `streaming/pty.py` | S-M | subprocess_env | No subprocess receives credential-shaped env vars |

---

### Milestone 5 — Upstream harmonization & founder gates

**Goal:** verify the unmerged sonnet batch, then dispatch only genuine
residuals. Dispatch founder-gated work when the gate clears.

#### 5a. Sonnet batch verification (after `fix/remediation-sonnet-batch-1` merges)

| Unit | Verify | After verification |
|---|---|---|
| **MP-1** | R-13's locality work on every utility rung | If merged: collapses to reroute-notice residual (move to MP-2). If not: full locality work is live. |
| **SCHED-P1** | R-03's receipt/idempotency/durability | Keep residual: route cancel, re-read job state, PID+start-time, owner-only perms. |
| **SCHED-P3** | R-03's overlap items | Keep residual: auto-disable, standing-order semantics, emergency stop. |
| **T5** | R-15's eval harness | Keep residual: findings-shape unification, artifact hash, coverage registry. Merge bundle with LOG-01. |
| **CSC-03** | R-12 Phase A + Phases B/C wiring | Keep residual: compaction correctness. |
| **MCP-A** | R-09 (already merged) | Keep residual: death supervisor, whitespace warning, fail-fast dead-child race. |
| **MCP-B** | R-09 (already merged) | Keep residual: content/structuredContent alternation, bridge base64 predecode. |
| **MCP-C** | R-09 (already merged) | Keep residual: schema cache with lazy connect, idle recycling. |
| **SP-1** | R-11 (already merged) | Keep residual: typed readiness evaluator, authoring sweep, builtin annotations. |
| **VMV-2** | R-10 (already merged) | Keep residual: SSE scrubber, output activity tracking, bounded transcript queue. |
| **VMV-4** | R-01/R-02 (already merged) | Keep residual: replayable event tail, reconnect supervisor, duplicate suppression. |
| **TT-02** | R-09 (already merged) | Keep residual: PTY shell env fencing, positive denial marker, empty ContextVar. |

#### 5b. Founder-decision-gated

| Unit | Gate |
|---|---|
| MEM-P5 | Memory write path (SK-6 / founder memory-boundary decisions 1–5) |
| SP-5 | Skills write path (SK-6). Record invariants in `DECISIONS.md` now. |
| SP-6 | `/learn` needs SK-6; `/review` needs SK-6 + SP-5; quote gate needs `egress.web_fetch`; 1-3-1 brief needs founder decision 6. Reserve names now. |
| CMD-A | Second command surface or command count > ~8. |
| DIST-02 | Signing identity and entitlements decision. |
| TT-06 | Real subagent consumer. Fix narrow wedge bugs if confirmed. |
| SCHED-P5 (tail) | LaunchAgent/supervisor — founder decision on macOS lifecycle. |
| SCHED-P6 (tail) | User-created jobs + detached task registry — named consumer. |
| VMV-5 (tail) | Day journal/logbook — founder decision + vision redaction review. |
| SURFACE-01 (tail) | Compositor/wizard/blueprint — real consumers + design decisions. |
| BIND-01 (tail) | File-binding pieces after R-08/R-07. |
| DAEMON-01 (tail) | PID-reuse identity + boot forensics — fold into DIST-01 Tauri work. |
| T3 (tail) | Stop-gate seam — after the real handler exists. |
| T6 (tail) | Entitlement test — after signing/packaging decisions. |
| OTHER-P6 (tail) | Projected-view diff + subprocess probe cache — if needed. |
| TT-04 (tail) | Background registry/wake lane — real consumer. |
| MP-4 (tail) | `keep_alive` policy + prompt-prefix caching — founder decisions 6, 7. |
| MP-6 (tail) | Credential-as-reference — founder decision 3 + M8 landing first. |

---

## 6. Dependency graph

```
Milestone 0 (primitives + test foundation)
  T1 ──────────────────────────────────────────────> makes tests trustworthy
  DAEMON-01a ──┐
  durable_write┤
  process_group┤── file-disjoint, parallel after T1
  activity_clock┤
  text_hygiene ┤
  subprocess_env┤
  OTHER-P4 ────┤
  DIAG-02 ─────┘

Milestone 1 (model pipeline) ── depends on activity_clock
  SP-3 ────────────────────────────────────────────> one-line fix, no deps
  MP-5 ── needs SP-3 (shares tool-call path)
  MP-2 ── needs activity_clock
  MP-3 ── needs activity_clock, MP-2 (shares interruptible backoff)
  MP-4 ── independent
  DAEMON-01b ── needs activity_clock, DAEMON-01a; merge LAST (hot file)

Milestone 2 (terminal & command) ── depends on M0 primitives
  CSC-06 ── independent (can start before M1 completes)
  GW-A ── needs CSC-06 (shares PTY replay)
  TT-01 ── needs process_group, text_hygiene, durable_write
  TT-03 ── needs text_hygiene
  TT-04a ── needs CSC-06, GW-A
  P2 ── needs durable_write
  TERM-02 ── needs TT-04a, GW-A
  BIND-01a ── independent (can start before M1 completes)
  SP-4a ── independent (one-line fix)
  SP-2 ── needs text_hygiene
  TT-05 ── needs activity_clock; merge LATE (touches state_machine.py)

Milestone 3 (memory & diagnostics) ── depends on M0 primitives
  CH-A ── needs text_hygiene
  MEM-P1 ── independent
  MEM-P2 ── needs MEM-P1
  MEM-P3 ── needs durable_write, DIAG-02
  MEM-P6 ── needs MP-4 (usage anchor)
  DIAG-01 ── needs DIAG-02
  LOG-01+OTHER-P2 ── needs text_hygiene
  CSC-01, CSC-02, CSC-04 ── independent (CSC-02 needs CH-A)
  P1, P4, P6 ── P4 needs text_hygiene
  OTHER-P1 ── needs DIAG-02
  OTHER-P3, OTHER-P5 ── OTHER-P5 needs durable_write

Milestone 4 (UI, voice, scheduler) ── depends on M0 primitives
  SURFACE-01a, SURFACE-01b ── independent
  SCHED-P6 ── independent
  SCHED-P2 ── needs process_group, activity_clock
  SCHED-P4 ── needs activity_clock
  SCHED-P5 ── independent
  OTHER-P6a, OTHER-P6b ── independent
  VMV-1, VMV-6 ── independent
  VMV-3 ── needs text_hygiene
  VMV-5 ── independent
  T2, T4 ── independent
  MP-6 ── needs subprocess_env

Milestone 5 (verification + founder gates)
  5a: Sonnet batch merges → verify → keep residuals
  5b: Founder decisions clear → dispatch
```

---

## 7. Packet accounting

Every packet from the final critical report is accounted for in this plan.

| Milestone | Units | Count |
|---|---|---|
| M0 | T1, DAEMON-01a, durable_write, process_group, activity_clock, text_hygiene, subprocess_env, OTHER-P4, DIAG-02 | 9 |
| M1 | SP-3, MP-5, MP-2, MP-3, MP-4, DAEMON-01b | 6 |
| M2 | CSC-06, GW-A, TT-01, TT-03, TT-04a, P2, TERM-02, BIND-01a, SP-4a, SP-2, TT-05 | 11 |
| M3 | CH-A, MEM-P1, MEM-P2, MEM-P3, MEM-P6, DIAG-01, LOG-01+OTHER-P2, CSC-01, CSC-02, CSC-04, P1, P4, P6, OTHER-P1, OTHER-P3, OTHER-P5 | 16 |
| M4 | SURFACE-01a, SURFACE-01b, SCHED-P6, SCHED-P2, SCHED-P4, SCHED-P5, OTHER-P6a, OTHER-P6b, VMV-1, VMV-3, VMV-5, VMV-6, T2, T4, MP-6 | 15 |
| M5a | MP-1, SCHED-P1, SCHED-P3, T5, CSC-03, MCP-A, MCP-B, MCP-C, SP-1, VMV-2, VMV-4, TT-02 | 12 (verify) |
| M5b | MEM-P5, SP-5, SP-6, CMD-A, DIST-02, TT-06 + 12 tails | 18 (gated) |
| **Total** | | **87** (includes shared primitives and split packets) |

No packet is dropped. No packet is unaccounted for.

---

## 8. Tactical directives

1. **SP-3 and SP-4a land immediately.** They are one-line fixes with no
   dependencies. Do not gate them behind Milestone 0.
2. **T1 lands before any test-dependent work.** The hermetic fixture is the
   prerequisite for trusting every subsequent test.
3. **DAEMON-01b and TT-05 merge last in their milestones.** Both touch
   `state_machine.py`, the hottest file in the tree. Sequence after all
   other state-machine work in their milestone.
4. **Milestones are themes, not barriers.** CSC-06 (terminal reconnect, no
   model-pipeline dependency) may proceed before Milestone 1 completes.
   BIND-01a (config CAS, no terminal dependency) may proceed before
   Milestone 2 completes.
5. **One merge per seam.** LOG-01 + OTHER-P2 are one commit (same 30-line
   `obs/logging.py` hub). CSC-06 + GW-A coordinate (same PTY replay ring).
   MP-2 + MP-3 coordinate (same interruptible backoff).
6. **Verification-before-done.** Every claimed action is validated against
   the resulting artifact/state. Verification checks measured OS state
   (port bound, exit code, file hash, SQLite integrity), not model judgment.
7. **First-person machine tone.** Error and recovery messages speak as the
   computer: "My local inference server on port 11434 stopped responding
   mid-generation. I preserved your conversation state and restarted the
   connection." Never: "I apologize, an error occurred."
8. **Test commands.** Every Python test run needs `arch -arm64`. From a
   worktree, use `./wt_pytest.py`. `main` is not green — baseline first.

---

## Source

- `.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md` —
  authoritative verdicts for every packet.
- `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-2026-09-11.md` — original plan
  (superseded by this document, but Parts E–F contain the UX scrutiny
  reasoning that informed the milestone groupings).
- `.handoff/oss-pass-2/IMPLEMENTATION-PLAN-REVIEW-AND-REINVENTIONS-2026-09-11.md`
  — external review (three valid corrections adopted; overstated claims
  pushed back on in §1).
- `.handoff/oss-pass-2/deep-eval-group{1,2,3,4}-*.md` — per-packet
  reasoning.
- `.handoff/STATE-OF-WORK-2026-09-10.md` — confirms sonnet batch is still
  on its branch, not merged to `main`.
- `AGENTS.md` — standing directives, test commands, invariants.
