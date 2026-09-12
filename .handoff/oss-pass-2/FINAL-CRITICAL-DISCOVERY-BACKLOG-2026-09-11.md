# OSS Pass-2 Discovery Backlog — Final Critical Report

Written 2026-09-11. This is the synthesis of four deep-evaluation reports
covering all 12 Halbert workstreams, the ~84 proposed packets, and the 20
follow-up units (F01–F20). It supersedes the earlier numerical ranking at
`.handoff/OSS-PASS-2-DISCOVERY-BACKLOG-PRIORITIZATION-2026-09-11.md`.

Source evaluations (authoritative detail, one per group):

- `.handoff/oss-pass-2/deep-eval-group1-memory-conversation-permissions.md`
- `.handoff/oss-pass-2/deep-eval-group2-scheduler-terminal-voice.md`
- `.handoff/oss-pass-2/deep-eval-group3-skills-mcp-models.md`
- `.handoff/oss-pass-2/deep-eval-group4-dashboard-testing-other.md`

This is a research and design-review document. No code is changed. Every
verdict is ACCEPT, RESHAPE, REJECT, or DEFER, with the gate named for every
DEFER.

---

## 0. Critical correction — actual remediation merge status

The four deep-eval reports repeatedly say "R-03 merged," "R-13 merged,"
"R-15 merged," and "R-12 Phase A merged." **This is wrong.** Verified against
the repository:

| Batch | Packets | Branch | Merged to `main`? |
|---|---|---|---|
| Opus | R-01, R-02, R-04, R-05, R-06, R-07, R-08, R-09, R-10, R-11, R-12 Phases B/C, R-14 | `fix/remediation-opus-batch-2` | **Yes** — merge `55ecef87` |
| Sonnet | R-03, R-13, R-15, R-12 Phase A | `fix/remediation-sonnet-batch-1` | **No** — branch still open |

Evidence: `git log --oneline main` contains `55ecef87` (opus merge) but does
**not** contain the sonnet batch's commits (`068d1f05`, `0c1812c3`,
`afeb5d24`, `dfffd67d`, `c6372e06`, etc.). The state-of-work doc
(`STATE-OF-WORK-2026-09-10.md` line 70) confirms: "Sonnet batch: R-03, R-12
Phase A — Not ours. Their branch, still open."

The tier-assignment doc (`OSS-PASS-2-REMEDIATION-TIER-ASSIGNMENT-2026-09-09.md`
line 31) says "all four fully complete" as of 2026-09-11, but "complete" means
the work is done on the branch, not that it is merged to `main`.

### What this changes

Several verdicts in the deep-eval reports assumed the sonnet batch was merged.
The corrected verdicts:

| Packet | Deep-eval said | Corrected | Reason |
|---|---|---|---|
| **MP-1** | REJECT (R-13 merged) | **RESHAPE — verify first** | R-13 is on the sonnet branch, not `main`. If R-13 merges before MP-1 dispatches, MP-1 collapses to the reroute-notice residual. If it does not, MP-1's locality work is live and buildable. |
| **SCHED-P1** | RESHAPE (R-03 covered most) | **RESHAPE — larger residual** | R-03 is not on `main`. The receipt/idempotency/durability work SCHED-P1 was told to drop is not yet in the tree. Keep the residual until R-03 merges, then re-verify. |
| **SCHED-P3** | RESHAPE (R-03 covered items) | **RESHAPE — verify** | Same: the auto-disable and standing-order items are new, but the overlap claim against R-03 must be re-verified after merge. |
| **T5** | RESHAPE (R-15 referenced) | **RESHAPE — verify R-15** | R-15's eval harness is on the sonnet branch. T5's eval-metric and coverage-registry work should not assume R-15 is in the tree. |
| **R-12 wiring** | (not a discovery packet) | **Blocked** | R-12 Phases B/C are merged but unwired — the wiring lives in `agents/threads.py` (Phase A's file, sonnet branch). This is a known blocked item, not discovery work. |

Packets that cited only opus-batch remediation (R-01, R-02, R-04, R-05, R-06,
R-07, R-08, R-09, R-10, R-11, R-14) are unaffected — those are genuinely merged.

---

## 1. Method

Each packet was evaluated against five questions:

1. **Is this a real problem for Halbert today?** — spot-checked against actual
   code, not the origin's claim.
2. **How much overlaps with already-merged remediation?** — compared against
   R-01 through R-15, with merge status verified (see §0).
3. **Does it violate any standing directive?** — `AGENTS.md` / `DECISIONS.md`
   rules: no model names on surfaces, no model for redaction, no UI-executed
   commands, no migrations, two-dependency contract, one locality judge, one
   feature gate, no emoji, shared-token colours, no duplicate primitives.
4. **Is the effort justified by the value?** — judged against real consumers,
   not speculative ones.
5. **What is the minimum viable version?** — the smallest slice that solves the
   real defect without building infrastructure for nonexistent consumers.

Verdict definitions:

- **ACCEPT** — genuinely new, real defect or gap, no remediation overlap, no
  standing-rule violation. Build it.
- **RESHAPE** — the idea has real value but the packet is oversized, conflated,
  or partially covered by remediation. Split, merge, or reduce before
  dispatching.
- **REJECT** — fully covered by merged remediation, or violates a standing
  rule, or builds infrastructure for a nonexistent consumer with no path to
  one.
- **DEFER** — genuinely valuable but blocked on a named founder decision or a
  missing prerequisite. Name the gate.

---

## 2. Master verdict table

### Memory (MEM-P1–P6)

| Packet | Verdict | One-line reason |
|---|---|---|
| MEM-P1 | ACCEPT | Read-side memory trust and visibility — real gap, no overlap. |
| MEM-P2 | RESHAPE | Ownership/origin classes — keep the typed ownership, drop lifecycle machinery before a write path. |
| MEM-P3 | ACCEPT | Forgotten-request tombstones — real defect in the recall gate. |
| MEM-P4 | RESHAPE | Promotion/recall boundaries — keep the boundary check, drop the curator. |
| MEM-P5 | DEFER | Memory lifecycle infrastructure — gate: write path (SK-6 / founder decision). |
| MEM-P6 | ACCEPT | Provenance and redaction determinism — real, no overlap with R-05's registry. |

### Conversation / session / compaction (CSC-01–06)

| Packet | Verdict | One-line reason |
|---|---|---|
| CSC-01 | ACCEPT | Conversation crash/recovery — real, distinct from R-04's store hardening. |
| CSC-02 | ACCEPT | Turn admission and identity — real, distinct from R-01's interrupt algebra. |
| CSC-03 | RESHAPE | Compaction phases — verify R-12 status (Phases B/C merged, Phase A not). Keep residual. |
| CSC-04 | ACCEPT | Session-tree integrity — real defect. |
| CSC-05 | RESHAPE | Compaction correctness — keep the correctness items, drop the lifecycle. |
| CSC-06 | RESHAPE | Session resume — keep the resume contract, drop the broad registry. |

### Permissions / consent / security (P1–P6)

| Packet | Verdict | One-line reason |
|---|---|---|
| P1 | ACCEPT | Permission lattice residual — real, distinct from R-08. |
| P2 | ACCEPT | Approval-bound-to-artefact — real race, no overlap. |
| P3 | RESHAPE | Lease/halt semantics — keep the halt, drop the broad lease registry. |
| P4 | ACCEPT | Untrusted-data delimiters — real, no overlap with R-05. |
| P5 | RESHAPE | SSRF/base-URL guard — keep the centralized guard, drop per-route duplication. |
| P6 | ACCEPT | Trusted-directory/executable resolution — real, no overlap. |

### Scheduler / heartbeat / daemon / watchdog (SCHED-P1–P6)

| Packet | Verdict | One-line reason |
|---|---|---|
| SCHED-P1 | RESHAPE | Route cancel through live executor, re-read job state, PID+start-time, owner-only perms. **Verify R-03 merge first** — the receipt/durability work is not yet on `main`. |
| SCHED-P2 | ACCEPT | Honest inactivity-based timeouts + shared process-group kill. No flat wall-clock. |
| SCHED-P3 | RESHAPE | Auto-disable, standing-order semantics, emergency stop. Drop items R-03 covers (after merge verification). |
| SCHED-P4 | ACCEPT | Turn liveness and activity-clock approach. |
| SCHED-P5 | RESHAPE | Accept core lifecycle. Defer LaunchAgent/supervisor tail behind founder decision. |
| SCHED-P6 | RESHAPE | Ship dashboard list/history/cancel, webhook normalization, digest improvements. Defer user-created jobs and detached task registry. |

### Terminal / tools / subagents (TT-01–06)

| Packet | Verdict | One-line reason |
|---|---|---|
| TT-01 | ACCEPT | Shell executor hardening — distinct from R-07. Process-group kill, PID/start-time, redact-before-cap, ANSI/Unicode strip, atomic write verification, device/inode approval binding. |
| TT-02 | RESHAPE | Drop MCP child-env if R-09 confirmed. Keep PTY shell env fencing, positive denial marker, empty ContextVar, trusted executable checks. |
| TT-03 | ACCEPT | Command normalization/deobfuscation, fail-closed parsing, deny-list precedence, unattended-origin policy, worktree mutation rule. |
| TT-04 | RESHAPE | Ship PTY reattach and guardrails. Defer background registry/wake lane. |
| TT-05 | ACCEPT | Tool-loop guardrails and malformed-call recovery. |
| TT-06 | DEFER | Fix narrow wedge bugs if confirmed. Defer SubagentManager until a real consumer exists. |

### Voice / media / vision (VMV-1–6)

| Packet | Verdict | One-line reason |
|---|---|---|
| VMV-1 | ACCEPT | Wake-word correctness on macOS ARM64. Name-resolution and reset-on-resume. |
| VMV-2 | RESHAPE | Verify R-10 first. Keep residual SSE scrubber, output activity tracking, bounded transcript queue. |
| VMV-3 | ACCEPT | Central media limits, MIME sniffing, unbounded base64 fix, raw exception leakage, credentialed URL fix. |
| VMV-4 | RESHAPE | R-01/R-02 likely covered provenance. Keep replayable event tail, reconnect supervisor, duplicate suppression. |
| VMV-5 | RESHAPE | Ship screen/coordinate truthfulness. Defer day journal/logbook behind founder decision. |
| VMV-6 | ACCEPT | Audio footprint and capability assertions. Reuse existing `has_capability()`. |

### Skills / prompts / learning (SP-1–6)

| Packet | Verdict | One-line reason |
|---|---|---|
| SP-1 | RESHAPE | R-11 covers ~70%. Keep residual typed readiness evaluator, authoring sweep, builtin annotations. |
| SP-2 | ACCEPT | Prompt assembly honesty — tool-output blocks, guest/tool-list drift, non-ASCII fold table. Reuse existing sanitizer. |
| SP-3 | ACCEPT | Live data-loss bug: `state_machine.py:2669` drops all but the first tool call. Stop-gate seam is prerequisite for eval. |
| SP-4 | RESHAPE | Fix `/help` and `/h` drift now. Defer full command registry until command count exceeds ~8. |
| SP-5 | DEFER | Skills store has no write calls. Gate: SK-6 write path. Record invariants in `DECISIONS.md` now. |
| SP-6 | DEFER | `/learn`, `/plan`, `/review` need missing consumers and write paths. Reserve names now. |

### MCP / channels / gateway / protocol (MCP-A/B/C, CH-A, GW-A, CMD-A)

| Packet | Verdict | One-line reason |
|---|---|---|
| MCP-A | RESHAPE | R-09 (merged) covers env, frames, config screen, process-group. Keep death supervisor, whitespace warning, fail-fast dead-child race. |
| MCP-B | RESHAPE | R-09 (merged) covers description scan, tag strip, provenance, annotations, sampling refusal. Keep content/structuredContent alternation, bridge base64 predecode. |
| MCP-C | RESHAPE | R-09 (merged) covers list_changed, breaker, proven session, HTTP hygiene, include/exclude, pagination. Keep schema cache with lazy connect, idle recycling. |
| CH-A | ACCEPT | Turn provenance/cause axis — structural prerequisite for scheduler-submitted turns. No overlap. |
| GW-A | ACCEPT | Event stream reconnect and typed errors. Reuse existing PTY replay ring. |
| CMD-A | DEFER | Merge `/help`/`/h` fix into SP-4. Defer broad command-turn-context until a second command surface exists. |

### Models / providers / cost (MP-1–6)

| Packet | Verdict | One-line reason |
|---|---|---|
| MP-1 | RESHAPE — verify first | R-13 covers it, but R-13 is on the sonnet branch, **not merged to `main`**. If R-13 merges first, MP-1 collapses to the reroute-notice residual (move to MP-2). If not, MP-1's locality work is live. |
| MP-2 | ACCEPT | Live defects: Retry-After clamped to 60s, blocking `time.sleep` in live routing, health axis conflation, dead circuit breaker. |
| MP-3 | ACCEPT | `aiohttp.ClientTimeout(total=120)` kills healthy streams. Missing abort hook lets stopped turns keep billing. |
| MP-4 | ACCEPT | Character-only token estimates drive `num_ctx`. Context cache keyed by model name conflates local/remote. LM Studio "loaded" means installed. |
| MP-5 | ACCEPT | Local models emitting prose-encoded tool calls are silently lost. Needs deterministic parser/repair. |
| MP-6 | ACCEPT | Broad subprocess env scrubbing beyond R-09's MCP-specific coverage. Build one subprocess-env primitive. |

### Dashboard / app / onboarding / diagnostics (DIAG-01/02, DAEMON-01, LOG-01, BIND-01, SURFACE-01, TERM-02, DIST-02)

| Packet | Verdict | One-line reason |
|---|---|---|
| DIAG-01 | ACCEPT | Build `halbert doctor` as the central findings registry. |
| DIAG-02 | ACCEPT | Read-only store integrity diagnostics. Defer divert/spool path. |
| DAEMON-01 | RESHAPE | Split: lock/exit-code fixes now, stuck-turn watchdog later. |
| LOG-01 | ACCEPT | Merge with OTHER-P2 — same 30-line `obs/logging.py` hub. |
| BIND-01 | RESHAPE | Config CAS/base-hash guard now. File-binding after R-08/R-07. |
| SURFACE-01 | RESHAPE | Accept bug fixes and S-effort hygiene. Defer compositor/wizard/blueprint. |
| TERM-02 | ACCEPT | Watched-terminal read/close tools. Apply withdraw-not-refuse. |
| DIST-02 | DEFER | Gate: signing identity and entitlements. |

### Testing / evals / QA / ops (T1–T6)

| Packet | Verdict | One-line reason |
|---|---|---|
| T1 | ACCEPT | Hermetic environment and live-DB guard — highest-leverage testing investment. |
| T2 | ACCEPT | Fix Darwin memory information defect. |
| T3 | RESHAPE | Accept ledger/eval metric/convention. Defer stop-gate seam until the real handler exists. |
| T4 | ACCEPT | Wire contracts and user-facing model-name-surface evaluation. Must assert absence of model names. |
| T5 | RESHAPE | Accept findings-shape unification, artifact hash verification, coverage registry. Merge support bundle with LOG-01. **Verify R-15 merge status.** |
| T6 | RESHAPE | Accept CSP test, npm install-script allowlist, narrow upstream tracking job. Defer entitlement test and broad async rulepack. |

### Other (OTHER-P1–P6)

| Packet | Verdict | One-line reason |
|---|---|---|
| OTHER-P1 | ACCEPT | State backup/create-only behavior. Respect no-migration rules. |
| OTHER-P2 | ACCEPT | Merge with LOG-01. Correlated redacted logging. |
| OTHER-P3 | ACCEPT | Measured-not-assumed behavior. |
| OTHER-P4 | ACCEPT | Shared bounded-execution/deadline helper. |
| OTHER-P5 | RESHAPE | Ship install identity early (mDNS exposes raw hostnames). Bounded downloads. Reuse atomic-write helper. |
| OTHER-P6 | RESHAPE | Ship guarded localStorage access and basic settings reload table. Defer projected-view diff and subprocess probe cache. |

### Aggregate counts (corrected)

| Verdict | Count | Packets |
|---|---|---|
| ACCEPT | 27 | MEM-P1, MEM-P3, MEM-P6, CSC-01, CSC-02, CSC-04, P1, P2, P4, P6, SCHED-P2, SCHED-P4, TT-01, TT-03, TT-05, VMV-1, VMV-3, VMV-6, SP-2, SP-3, CH-A, GW-A, MP-2, MP-3, MP-4, MP-5, MP-6, DIAG-01, DIAG-02, LOG-01, TERM-02, T1, T2, T4, OTHER-P1, OTHER-P2, OTHER-P3, OTHER-P4 |
| RESHAPE | 31 | MEM-P2, MEM-P4, CSC-03, CSC-05, CSC-06, P3, P5, SCHED-P1, SCHED-P3, SCHED-P5, SCHED-P6, TT-02, TT-04, VMV-2, VMV-4, VMV-5, SP-1, SP-4, MCP-A, MCP-B, MCP-C, MP-1, DAEMON-01, BIND-01, SURFACE-01, T3, T5, T6, OTHER-P5, OTHER-P6 |
| REJECT | 0 | (MP-1 was REJECT in the deep-eval; corrected to RESHAPE because R-13 is not merged) |
| DEFER | 6 | MEM-P5, TT-06, SP-5, SP-6, CMD-A, DIST-02 |

Note: several ACCEPT and RESHAPE packets carry deferral notes for specific
sub-items. The counts above reflect the overall packet verdict, not every
sub-item.

---

## 3. Cross-cutting primitives — build first

These are the shared mechanisms that recur across three or more workstreams.
They should be built once, before fanning out the dependent packets. Building
them per-packet is the wrong direction — it creates duplicate primitives,
which the standing rules forbid.

### 3.1 Process-group ownership and kill escalation

Needed by: TT-01 (shell executor), SCHED-P2 (inactivity watchdog), MCP-A
(death supervisor residual).

Halbert already does this right in `streaming/pty.py:269` (`os.setsid`) and
`:342–445` (escalation reaper). R-09 did `start_new_session=True` + `killpg`
for MCP stdio children. The terminal-tools and scheduler residuals should
reuse the same escalation ladder, not invent a third one.

**Candidate:** `utils/process_group.py` — one `start_new_session` + `killpg`
escalation helper, consumed by terminal, scheduler, and MCP.

### 3.2 Activity-clock primitive

Needed by: SCHED-P2 (inactivity watchdog), SCHED-P4 (turn liveness),
TT-05 (tool heartbeat), TT-06 (subagent staleness).

One monotonic activity stamp/check abstraction. The existing
`turn_activity.py` is the natural home.

**Candidate:** extend `turn_activity.py` with a shared activity-clock
interface.

### 3.3 Text hygiene — one untrusted-content sanitizer

Needed by: TT-01 (ANSI/Unicode strip), SP-2 (prompt assembly fold table),
MCP-B (description/result scan), TT-03 (command normalization), and every
surface that injects external content into the prompt.

Today there are two sanitizers: `mcp/metadata.py:strip_unicode_tags` (R-09)
and `prompts/agent_prompts.py:_CONTROL_TAG_RE`. Adding a third is the wrong
direction.

**Candidate:** `security/text_hygiene.py` — the tag stripper (R-09) + the
fold table (SP-2) + the random-boundary wrapper (SP-2) + the source-hygiene
block (SP-6). Every consumer imports from one module.

### 3.4 Atomic durable writes

Needed by: OTHER-P5 (install identity), OTHER-P5 (bounded download),
scheduler receipts (A06 ledger fsync), guest_homes rename (A12-G8),
config writes (BIND-01).

Halbert already uses `os.replace` for local state (`scheduler/run_receipts.py:121`,
`consent/store.py:599`) but not for identity or network-fetched files.

**Candidate:** `utils/durable_write.py` — temp file in target dir, write +
flush, fsync, `os.replace`, directory fsync, optional mode/chmod. Build
once, consume everywhere.

### 3.5 Doctor / findings registry — one diagnostic sink

Needed by: DIAG-01 (the registry itself), and as the sink for residuals
from SCHED-P3 (ticker markers), MP-1/MP-4 (locality drift), R-05 (redaction
coverage), R-09 (artifact hash), DIAG-02 (SQLite version).

**Candidate:** build `halbert doctor` as a registry with one `Finding` shape
(severity, provenance/`why_trust`, fix hints) + `halbert doctor --json` +
`GET /api/diagnostics`. Every subsequent check is a new entry, not a new
framework.

### 3.6 One support bundle

Needed by: LOG-01 (OC08-C7), T5 (OC09-C13), OTHER-P2.

These are the same mechanism: one redacted zip under the data dir with
redacted config, doctor JSON, log tail, health findings. Merge into one
bundle, one redaction variant, one packet.

### 3.7 Subprocess environment builder

Needed by: MP-6 (all tools), TT-02 (PTY shell), R-09's MCP child env
(already built).

R-09 built `build_child_env` for MCP stdio children (allowlist). MP-6
proposes `build_subprocess_env` for all tools (blocklist — strip
credential-shaped names). These should share a common primitive: one
function that builds a child environment from a baseline + declared extras,
with credential-shaped names stripped. A shared test should walk every
`subprocess.`/`Popen`/`PTYSession` call site and assert none passes the bare
environment.

**Candidate:** `tools/subprocess_env.py` — `build_subprocess_env()` consumed
by system_tools, accelerator_tools, gpu_tools, schedule_cron, PTY, and MCP.

### 3.8 Circuit breaker primitive

Needed by: MP-2 (provider-error breaker), MCP-C (per-server breaker).

`agents/error_recovery.py` has a circuit breaker (threshold 5, 60 s, keyed
by component) that is written and never read — dead code. R-09 may have
built an MCP-specific breaker. MP-2 needs a provider-error breaker. These
should share ONE primitive. Wire the existing one, or retire it and build
one shared breaker. Do not build a third.

### 3.9 Reconnect supervisor

Needed by: GW-A (event stream reconnect), VMV-4 (voice event tail),
VMV-2 (SSE reconnect), MCP-C (health reconnect).

Shared backoff/jitter/stability-window behavior.

**Candidate:** `net/reconnect_supervisor.py`.

### 3.10 Typed turn context

Needed by: CH-A (cause axis), CMD-A (authorization axis — deferred), MP-2
(typed `turn_exit_reason`).

These construct typed objects at different points in a turn's lifecycle:
cause at admission, authorization at command detection, exit reason at
finalization. They should be one `TurnContext` type, not three separate
constructed types that drift apart.

### 3.11 Read-only SQLite opener

Needed by: DIAG-01 (readiness probes), DIAG-02 (store probes), T5 (SQLite
bloat check), OTHER-P1 (backup snapshot inventory).

**Candidate:** `open_read_only(path)` with `mode=ro` +
`PRAGMA query_only=ON`. Build once in DIAG-02, reuse everywhere.

### 3.12 Bounded-execution / deadline helper

Needed by: OTHER-P4 (the helper itself), R-07's domain (execute_code
monitor), R-15's domain (eval judge timeout), scheduler executor timeout.

**Candidate:** `utils/deadline.py`. Build once, let each consumer adopt it.

### 3.13 Capability assertion — withdraw, don't refuse

Needed by: TERM-02 (watched-terminal tools), VMV-6 (audio footprint), and
any capability-gated tool.

When a capability is absent, the tool should be omitted from the available
list, not present and returning a predictable failure. Document this once
in the tool-registration path, not per-tool.

### 3.14 Process-start-time ownership

Needed by: TT-01 (PID/start-time fingerprint), SCHED-P1 (PID+start-time
identity), MCP-A (dead-child race).

PID alone is insufficient due to PID reuse on macOS. Receipts and process
ownership must carry `(pid, start_time)` or equivalent identity fingerprint.

### 3.15 Approval bound to artefact

Needed by: P2 (approval-bound-to-artefact), TT-01 (device/inode approval
binding), BIND-01 (config CAS/base-hash).

Approval must bind to a specific path/content identity (device/inode or base
hash) to prevent approve-then-replace races.

### 3.16 One SSRF / base-URL guard

Needed by: P5 (SSRF guard), VMV-3 (credentialed guest-home URLs), MP-6
(redirect policy), MCP-C (URL scheme validation).

Base URLs displayed or fetched through guest, MCP, provider, media, and web
paths need centralized validation/redaction. Credentialed URLs must never be
rendered as display names.

---

## 4. First-wave dispatch order

### Wave 0 — shared primitives (build before fanning out)

These have no founder-decision gates and unblock the most downstream packets.
Build them first, in parallel where file-disjoint.

| Primitive | Candidate module | Unblocks |
|---|---|---|
| Process-group escalation | `utils/process_group.py` | TT-01, SCHED-P2, MCP-A |
| Activity clock | extend `turn_activity.py` | SCHED-P2, SCHED-P4, TT-05 |
| Text hygiene | `security/text_hygiene.py` | TT-01, SP-2, MCP-B, TT-03 |
| Atomic durable writes | `utils/durable_write.py` | OTHER-P5, BIND-01, scheduler |
| Doctor / findings registry | `halbert doctor` | DIAG-01 + all residuals |
| Subprocess env builder | `tools/subprocess_env.py` | MP-6, TT-02 |
| Read-only SQLite opener | (in DIAG-02) | DIAG-01, DIAG-02, T5, OTHER-P1 |
| Bounded-execution helper | `utils/deadline.py` | OTHER-P4, scheduler, eval |
| Process-start-time ownership | (shared fingerprint) | TT-01, SCHED-P1, MCP-A |

### Wave 1 — immediate buildable residuals (no founder decision, no missing consumer)

These are real defects or gaps with no remediation overlap (or overlap only
with the unmerged sonnet batch, which should be verified but not blocked on).

| Packet | What to build | Effort | Notes |
|---|---|---|---|
| **T1** | Hermetic test environment + live-DB guard | M | Highest-leverage testing investment. Prevents live-host contamination. |
| **SP-3** | Fix `state_machine.py:2669` data-loss bug (drops all but first tool call) | S | Live defect. Prerequisite for eval attachment. |
| **MP-2** | Retry-After fix, interruptible backoff, BackendIdentity, wire or retire dead circuit breaker | M | Live defects in `tier_router.py`, `rate_limiter.py`, `error_recovery.py`. |
| **MP-3** | Idle-gap stream timeout, abort hook | M | Live defect: `aiohttp.ClientTimeout(total=120)` kills healthy streams. |
| **MP-6** | `build_subprocess_env()` for all tools (not just MCP) | S | Real secret-leak prevention. Reuse R-09's pattern. |
| **TT-01** | Shell executor hardening (process-group, PID/start-time, redact-before-cap, ANSI strip, atomic write, device/inode approval) | M | Distinct from R-07. Reuse Wave-0 primitives. |
| **TT-03** | Command normalization/deobfuscation, fail-closed parsing, deny-list precedence | S | Real security. |
| **VMV-3** | Central media limits, MIME sniffing, unbounded base64 fix, credentialed URL fix | S-M | Real DoS + secret-leak. |
| **CH-A** | Turn cause axis + envelope sanitizer + watcher deadline fix | M | Structural prerequisite for scheduler-submitted turns. |
| **GW-A** | Wire existing PTY replay ring through terminal WS, event replay ring, typed error envelope | S-M | Reuse existing thrown-away replay ring. |
| **P2** | Approval-bound-to-artefact (device/inode or base hash) | S | Real approve-then-replace race. |
| **OTHER-P5** | Install identity (mDNS exposes raw hostnames) + bounded downloads | S-M | Ship install identity first. Reuse atomic-write helper. |
| **DIAG-01** | `halbert doctor` registry + `--json` + `GET /api/diagnostics` | M | The universal diagnostic sink. |
| **DIAG-02** | Read-only store integrity diagnostics + read-only SQLite opener | M | Build the opener here, reuse everywhere. |
| **LOG-01 + OTHER-P2** | Merged logging packet: `JsonFormatter` + `RotatingFileHandler` + `RedactingFilter` + `LogRecordFactory` + support bundle | M | Same 30-line hub. One merge. |
| **OTHER-P1** | State backup / create-only behavior | S | Respect no-migration rules. |
| **OTHER-P3** | Measured-not-assumed behavior | S | |
| **OTHER-P4** | `utils/deadline.py` bounded-execution helper | S | Wave-0 primitive. |
| **T2** | Fix Darwin memory information defect | S | |
| **T4** | Wire contracts + model-name-surface evaluation (assert absence of model names) | S-M | |
| **VMV-1** | Wake-word correctness on macOS ARM64, name-resolution, reset-on-resume | S-M | |
| **VMV-6** | Audio footprint + capability assertions (reuse `has_capability()`) | S | |
| **MEM-P1** | Read-side memory trust and visibility | M | |
| **MEM-P3** | Forgotten-request tombstones | S | |
| **MEM-P6** | Provenance and redaction determinism | S | |
| **CSC-01** | Conversation crash/recovery | M | |
| **CSC-02** | Turn admission and identity | M | |
| **CSC-04** | Session-tree integrity | S-M | |
| **P1** | Permission lattice residual | M | |
| **P4** | Untrusted-data delimiters | S | |
| **P6** | Trusted-directory/executable resolution | S | |
| **SCHED-P2** | Honest inactivity-based timeouts + process-group kill | M | |
| **SCHED-P4** | Turn liveness and activity-clock | S-M | |
| **TT-05** | Tool-loop guardrails and malformed-call recovery | S | |
| **SP-2** | Prompt assembly honesty + untrusted-content fencing (reuse text-hygiene module) | M | |
| **TERM-02** | Watched-terminal read/close tools + withdraw-not-refuse | S-M | |

### Wave 2 — founder-decision-gated

These are genuinely valuable but blocked on a named founder decision or a
missing prerequisite. Do not build until the gate is cleared.

| Packet | Gate |
|---|---|
| MEM-P5 | Memory write path (SK-6 / founder memory-boundary decisions 1–5) |
| SP-5 | Skills write path (SK-6). Record invariants in `DECISIONS.md` now. |
| SP-6 | `/learn` needs SK-6; `/review` needs SK-6 + SP-5; quote gate needs `egress.web_fetch`; 1-3-1 brief needs founder decision 6. Reserve names now. |
| CMD-A | Second command surface or command count > ~8. Merge `/help`/`/h` fix into SP-4. |
| DIST-02 | Signing identity and entitlements decision. |
| TT-06 | Real subagent consumer. Fix narrow wedge bugs if confirmed. |
| SCHED-P5 (tail) | LaunchAgent/supervisor — founder decision on macOS lifecycle. |
| SCHED-P6 (tail) | User-created jobs + detached task registry — named consumer. |
| VMV-5 (tail) | Day journal/logbook — founder decision + vision redaction review. |
| SURFACE-01 (tail) | Compositor/wizard/blueprint — real consumers + design decisions. |
| BIND-01 (tail) | File-binding pieces after R-08/R-07. |
| DAEMON-01 (tail) | Stuck-turn watchdog — after the lock/exit-code fixes land. |
| T3 (tail) | Stop-gate seam — after the real handler exists. |
| T6 (tail) | Entitlement test — after signing/packaging decisions. |
| OTHER-P6 (tail) | Projected-view diff + subprocess probe cache — if needed. |
| TT-04 (tail) | Background registry/wake lane — real consumer. |
| MP-4 (tail) | `keep_alive` policy + prompt-prefix caching — founder decisions 6, 7. |
| MP-6 (tail) | Credential-as-reference — founder decision 3 + M8 landing first. |

### Wave 3 — verification-only (pending sonnet batch merge)

These packets were told to drop items "already covered by R-03/R-13/R-15,"
but those remediation packets are on `fix/remediation-sonnet-batch-1`, not
merged to `main`. Do not re-implement; verify after the sonnet batch merges,
then keep only the genuine residual.

| Packet | What to verify | After verification |
|---|---|---|
| **MP-1** | R-13's locality work on every utility rung. If R-13 merges first, MP-1 collapses to the reroute-notice residual (move to MP-2). If MP-1 dispatches before R-13 merges, MP-1's locality work is live. | RESHAPE → either REJECT (if R-13 merged) or ACCEPT (if not). |
| **SCHED-P1** | R-03's receipt/idempotency/durability. Not yet on `main`. Keep the residual (route cancel, re-read job state, PID+start-time, owner-only perms) until R-03 merges. | RESHAPE — re-verify after R-03 merge. |
| **SCHED-P3** | R-03's overlap items. | RESHAPE — re-verify after R-03 merge. |
| **T5** | R-15's eval harness. Not yet on `main`. | RESHAPE — re-verify after R-15 merge. |
| **CSC-03** | R-12 Phase A (sonnet branch) + Phases B/C (merged but unwired). | RESHAPE — re-verify after R-12 Phase A merges and wires. |
| **VMV-2** | R-10's speech egress pipeline. R-10 IS merged (opus batch). Verify, then keep residual. | RESHAPE — verify R-10, keep residual. |
| **VMV-4** | R-01/R-02 provenance and admission. Both merged (opus batch). Verify, then keep residual. | RESHAPE — verify, keep residual. |
| **MCP-A/B/C** | R-09's coverage. R-09 IS merged (opus batch). Verify, then keep residual. | RESHAPE — verify R-09, keep residual. |
| **SP-1** | R-11's coverage. R-11 IS merged (opus batch). Verify, then keep residual. | RESHAPE — verify R-11, keep residual. |
| **TT-02** | R-09's MCP child env. R-09 IS merged. Verify, then keep residual. | RESHAPE — verify R-09, keep residual. |

### Rejected / skip

| Packet | Reason |
|---|---|
| (none fully REJECT) | MP-1 was REJECT in the deep-eval but is corrected to RESHAPE-verify because R-13 is not merged. |

No packet was fully rejected. The deep evaluations found real defects in
every workstream. The rejections were of specific sub-items (cargo-cult
patterns, infrastructure for nonexistent consumers, duplicate primitives),
not entire packets.

---

## 5. F01–F20 follow-up units

The distinction the group-4 report draws is correct: "read now" means read for
research coverage, not "build now." Build-now is determined by the dispatch
order in §4, not by the follow-up reading order.

### Read now (research coverage)

| Unit | Why |
|---|---|
| **F01** macOS host integration | The only origin tree that solves "being a macOS app that owns its host." 332 files untouched, density proven. Highest-priority read. |
| **F02** tool admission family | The origin's answer to "one policy pipeline across MCP and internal tools" — the founder constraint Halbert is building toward. 97% unread. |
| **F03** MCP server side | R-09 merged the client side; the server side is unread. Direct hit on an open founder decision (B6 audit). |
| **F04** skill workshop governance | The lifecycle — how a skill is proposed, reviewed, applied under a lock, hash-pinned, rolled back. R-11 merged the format, not the governance. |
| **F05** origin rationale docs | Cheapest unit (~30 files), repairs a systematic weakness. Best value per file. |
| **F06** config/state durability | OC05 already found a live defect: `models.yml` read-modify-write is unlocked while `being.yml` is flock-guarded. 653 files, ~5% read. |

### Read later (targeted, when the consuming work opens)

| Unit | When |
|---|---|
| F07 gateway auth/approval | After R-08/R-01 residuals are consumed. |
| F08 CLI self-diagnosis/update | After DIAG-01 lands, so the doctor can incorporate self-diagnosis. |
| F09 first-run/onboarding | When BIRTH-1 (ROADMAP) opens. |
| F10 plugin capability contract | If a Python extension surface is decided. |
| F11 control UI patterns | When SURFACE-01's wizard work opens. Take state/streaming patterns, not visual language. |
| F13 reference agent loop | If the state-machine stop-gate seam (T3) needs a reference. |
| F14 secrets at rest/broker | When FD-4 (allowed_hosts egress binding) is decided. |
| F17 desktop RPC bridge | When TERM-02's terminal read tool is built. |
| F19 cross-cutting primitives | Worth a skim for reusable patterns (path containment, bounded execution, redaction). |

### Skip (reference-only, no active Halbert consumer)

| Unit | Why |
|---|---|
| F12 Hermes plugin runtime | Halbert has no third-party Python extension ecosystem. "Plugins" are SKILL.md text. |
| F15 command surface | CLI ergonomics, not safety/correctness. Low priority for single-user product. |
| F16 Hermes tools remainder | Browser family not applicable (no browsing surface). `computer_use` not on ROADMAP. Notes/memory covered by R-14. |
| F18 protocol/host SDK contracts | TypeScript types for a different architecture. Halbert has its own event types. |
| F20 deterministic policy extension | R-08 merged the lattice. The origin's policy extension is a TypeScript engine for a different architecture. |

---

## 6. Standing directive compliance

This report enforces every standing directive from `AGENTS.md` and
`DECISIONS.md`:

- **No model names on user-facing surfaces.** T4's evaluation explicitly
  asserts absence of model names. MP-4's slot-switch warning names the slot,
  never the model. MP-2's fallback notice names the slot and locality.
- **No model for redaction.** All sanitizers, redaction, and text hygiene
  are deterministic. No packet proposes a model for redaction.
- **No UI-executed commands.** No packet proposes executing staged commands.
- **No migrations.** OTHER-P1's backup is create-only. CH-A's abort cutoff
  is an additive column, old rows unread. No packet adds a migration or
  back-compat shim.
- **Two-dependency contract.** No packet adds a hard dependency beyond
  `pyyaml` and `requests`. All heavy/ML stacks remain lazy optional extras.
- **One locality judge.** MP-1 routes through `is_local_model()`. No packet
  adds a second judge.
- **One feature gate.** VMV-6 and TERM-02 route through `has_capability()`.
  No packet adds a second gate.
- **No emoji.** No packet proposes emoji. SURFACE-01's UI work uses
  shared-token colours.
- **No duplicate primitives.** The cross-cutting primitives section (§3)
  explicitly merges: one sanitizer, one circuit breaker, one subprocess env
  builder, one findings registry, one support bundle, one read-only SQLite
  opener, one atomic-write helper, one deadline helper.
- **No lifecycle infrastructure before a write path.** SP-5, SP-6, MEM-P5
  are DEFERRED until SK-6 / the memory write path exists.
- **No proactive autonomous actions without founder-approved policy.**
  SCHED-P6's user-created jobs and TT-04's background registry are deferred
  until a named consumer and founder decision exist.
- **macOS-first, not Linux/systemd.** SCHED-P5's LaunchAgent/supervisor tail
  is deferred behind a founder decision on macOS lifecycle. No packet assumes
  systemd.

---

## 7. What this report does not do

- It does not implement code. It is research and design review only.
- It does not assert that any sonnet-batch remediation packet (R-03, R-13,
  R-15, R-12 Phase A) is merged — because it is not. The deep-eval reports'
  claims of "R-03 merged" and "R-13 merged" are corrected in §0.
- It does not rank packets by a numerical score. The verdict is a judgment
  of whether a packet deserves to exist, not a number.
- It does not prescribe a plan format. It provides a dispatch order and
  verdicts; the plan format is the founder's choice.
- It does not override `ROADMAP.md` or `DECISIONS.md`. This is a
  `.handoff/` document — session correspondence, zero authority.

---

## 8. Source files

Deep evaluations (authoritative detail):

- `.handoff/oss-pass-2/deep-eval-group1-memory-conversation-permissions.md`
- `.handoff/oss-pass-2/deep-eval-group2-scheduler-terminal-voice.md`
- `.handoff/oss-pass-2/deep-eval-group3-skills-mcp-models.md`
- `.handoff/oss-pass-2/deep-eval-group4-dashboard-testing-other.md`

Earlier ranking (superseded by this report):

- `.handoff/OSS-PASS-2-DISCOVERY-BACKLOG-PRIORITIZATION-2026-09-11.md`

Remediation status:

- `.handoff/STATE-OF-WORK-2026-09-10.md` (line 70: sonnet batch still open)
- `.handoff/OSS-PASS-2-REMEDIATION-TIER-ASSIGNMENT-2026-09-09.md` (line 31:
  sonnet batch "complete" on branch, not merged)
- `.handoff/OSS-PASS-2-OPUS-REMEDIATION-2026-09-09.md` (opus batch, merged
  at `55ecef87`)

Git verification:

- `git log --oneline main` contains `55ecef87` (opus merge).
- `git log --oneline main` does **not** contain sonnet batch commits
  (`068d1f05`, `0c1812c3`, `afeb5d24`, `dfffd67d`, `c6372e06`).
- `git branch --contains 068d1f05` → `fix/remediation-sonnet-batch-1` only.
