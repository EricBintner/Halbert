# OSS Pass-2 Discovery — Implementation Plan

Written 2026-09-11. Companion to
`.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md`.

This document groups the ~64 discovery packets into two sets — the **best
ideas** ready to implement now, and the **needs review** set that requires
more thinking, a founder decision, or verification of remediation status —
then lays out a phased implementation plan for the best ones.

No code is changed by this document. It is a plan for dispatch.

---

## Part A — Grouping

### Best ideas (implement now)

These are ACCEPT-verdict packets that fix a live defect, fill a structural
gap with a real consumer, or build a shared primitive that unblocks
downstream work. None require a founder decision. None duplicate merged
remediation.

Grouped by theme:

#### Live defects — must fix

| ID | What | Why it's best |
|---|---|---|
| SP-3 | Multi-tool dispatch data-loss bug | `state_machine.py` drops all but the first tool call when a model emits multiple. Live defect, silently loses work. Prerequisite for eval attachment. |
| MP-2 | Provider failure semantics | `rate_limiter.py` clamps `Retry-After` to 60s (guaranteed-to-fail retries). `tier_router.py` does a bare `time.sleep` in the live 429/529 loop (blocks `/stop` for up to 60s). `error_recovery.py`'s circuit breaker is written and never read (zero callers confirmed). Health mark conflates 401/DNS/timeout into one `False`. |
| MP-3 | Transport liveness | `llm_client.py` uses `aiohttp.ClientTimeout(total=self.timeout)` with default 120s — kills healthy streams mid-generation. Missing abort hook lets a stopped turn keep generating and billing for up to 120s. |
| MP-6 | Subprocess credential custody | `tools/system_tools.py` and `streaming/pty.py` copy the parent environment wholesale into every subprocess/shell. Every `HALBERT_API_TOKEN` / `ANTHROPIC_API_KEY` leaks to child processes. R-09 covered MCP children only; the general case is open. |
| VMV-3 | Central media limits | Unbounded base64/image/audio inputs. Raw exception leakage. Credentialed guest-home URLs rendered as display names. Real DoS + secret-leak surface. |
| TT-03 | Command normalization | Command deobfuscation, fail-closed parsing, deny-list precedence, unattended-origin policy. Real security — a model cannot smuggle a denied command through quoting/encoding. |
| P2 | Approval bound to artefact | Approval must bind to device/inode or base hash, not a path string. Real approve-then-replace race. |
| OTHER-P5 | Install identity + bounded downloads | Current mDNS node IDs expose raw hostnames. Bounded downloads are real DoS protection. Reuse the atomic-write helper. |

#### Structural prerequisites & high-leverage infrastructure

| ID | What | Why it's best |
|---|---|---|
| T1 | Hermetic test environment + live-DB guard | Prior audits found tests opening production `conversations.db` and real `~/.config/halbert/skills`. Highest-leverage testing investment — makes the suite structurally unable to touch the live host. |
| DIAG-01 | `halbert doctor` findings registry | The universal diagnostic sink. Every workstream's residuals (scheduler markers, locality drift, redaction coverage, artifact hashes, SQLite version) become entries in one registry, not new frameworks. |
| DIAG-02 | Read-only store integrity diagnostics | Builds the `open_read_only(path)` SQLite opener that DIAG-01, T5, and OTHER-P1 all consume. |
| CH-A | Turn cause axis | `agents/channels.py` has no representation for "this turn exists because the scheduler asked." A prompted heartbeat or cron-fired task must either be refused or lie and claim the dashboard channel. Structural prerequisite for scheduler-submitted turns (master-plan 03-C). Also fixes a live `config/watcher.py` starvation bug. |
| GW-A | Event stream reconnect | A PTY replay ring ALREADY EXISTS in `streaming/pty.py` and is thrown away. Wiring it through is S effort for a real "reconnect sees history" improvement. Also fixes 55 bare `{'error': str(e)}` returns in `mcp/server.py`. |

#### Shared primitives (build first, unblock downstream)

| ID | What | Unblocks |
|---|---|---|
| OTHER-P4 | `utils/deadline.py` bounded-execution helper | R-07's domain, R-15's domain, scheduler executor, eval judge |
| (primitive) | `utils/process_group.py` — process-group escalation | TT-01, SCHED-P2, MCP-A residual |
| (primitive) | `security/text_hygiene.py` — one untrusted-content sanitizer | TT-01, SP-2, MCP-B, TT-03 |
| (primitive) | `utils/durable_write.py` — atomic durable writes | OTHER-P5, BIND-01, scheduler receipts |
| (primitive) | `tools/subprocess_env.py` — one subprocess env builder | MP-6, TT-02 |
| (primitive) | Read-only SQLite opener (in DIAG-02) | DIAG-01, T5, OTHER-P1 |

#### Solid ACCEPTs that build on the above

| ID | What | Depends on |
|---|---|---|
| TT-01 | Shell executor hardening (process-group, PID/start-time, redact-before-cap, ANSI strip, atomic write, device/inode approval) | process_group, text_hygiene, durable_write |
| LOG-01 + OTHER-P2 | Merged logging packet (JsonFormatter + RotatingFileHandler + RedactingFilter + LogRecordFactory + support bundle) | — (same 30-line `obs/logging.py` hub) |
| TT-05 | Tool-loop guardrails and malformed-call recovery | activity-clock |
| SP-2 | Prompt assembly honesty + untrusted-content fencing | text_hygiene |
| T2 | Fix Darwin memory information defect | — |
| T4 | Wire contracts + model-name-surface evaluation (assert absence of model names) | — |
| VMV-1 | Wake-word correctness on macOS ARM64 | — |
| VMV-6 | Audio footprint + capability assertions (reuse `has_capability()`) | — |
| MEM-P1 | Read-side memory trust and visibility | — |
| MEM-P3 | Forgotten-request tombstones | — |
| MEM-P6 | Provenance and redaction determinism | — |
| CSC-01 | Conversation crash/recovery | — |
| CSC-02 | Turn admission and identity | CH-A (cause axis) |
| CSC-04 | Session-tree integrity | — |
| P1 | Permission lattice residual | — |
| P4 | Untrusted-data delimiters | text_hygiene |
| P6 | Trusted-directory/executable resolution | — |
| SCHED-P2 | Honest inactivity-based timeouts + process-group kill | process_group, activity-clock |
| SCHED-P4 | Turn liveness and activity-clock | activity-clock |
| TERM-02 | Watched-terminal read/close tools + withdraw-not-refuse | — |
| OTHER-P1 | State backup / create-only behavior | read-only SQLite opener |
| OTHER-P3 | Measured-not-assumed behavior | — |

---

### Needs review or more thinking

These are RESHAPE, DEFER, or verify-first packets. They are not bad ideas —
they need a boundary decision, a founder gate, or verification of
remediation status before they can be dispatched.

#### Needs reshaping (split/merge/reduce before dispatch)

| ID | What | Why it needs review |
|---|---|---|
| MEM-P2 | Ownership/origin classes | Keep the typed ownership; drop lifecycle machinery before a write path exists. Boundary between "type" and "lifecycle" needs a decision. |
| MEM-P4 | Promotion/recall boundaries | Keep the boundary check; drop the curator. Same boundary question as MEM-P2. |
| CSC-03 | Compaction phases | R-12 Phase A is on the sonnet branch (not merged); Phases B/C are merged but unwired. Verify R-12 status before scoping the residual. |
| CSC-05 | Compaction correctness | Keep correctness items; drop lifecycle. Boundary with CSC-03 needs resolution. |
| CSC-06 | Session resume | Keep the resume contract; drop the broad registry. Needs a consumer check. |
| P3 | Lease/halt semantics | Keep the halt; drop the broad lease registry. R-08 overlap needs verification. |
| P5 | SSRF/base-URL guard | Keep the centralized guard; drop per-route duplication. Needs a decision on where the one guard lives. |
| SCHED-P1 | Scheduler durability residual | R-03 is NOT merged (sonnet branch). The receipt/durability work SCHED-P1 was told to drop is not yet in the tree. Re-verify after R-03 merges. |
| SCHED-P3 | Auto-disable, standing orders | Same R-03 verification issue. |
| SCHED-P5 | Core lifecycle | Accept the core; defer LaunchAgent/supervisor tail behind a founder decision on macOS lifecycle. |
| SCHED-P6 | Dashboard list/history/cancel | Ship the dashboard pieces; defer user-created jobs and detached task registry until a named consumer exists. |
| TT-02 | PTY shell env fencing | Drop the MCP child-env portion if R-09 is confirmed (it is — opus batch merged). Keep PTY shell fencing, positive denial marker, empty ContextVar. |
| TT-04 | PTY reattach | Ship PTY reattach and guardrails; defer background registry/wake lane. |
| VMV-2 | SSE scrubber, transcript queue | Verify R-10 (merged) first. Keep only the residual. |
| VMV-4 | Replayable event tail, reconnect | Verify R-01/R-02 (merged) first. Keep only the residual. |
| VMV-5 | Screen/coordinate truthfulness | Ship the coordinate disclosure; defer day journal/logbook behind a founder decision + vision redaction review. |
| SP-1 | Honest/scanned catalog residual | R-11 (merged) covers ~70%. Keep only the residual typed readiness evaluator, authoring sweep, builtin annotations. |
| SP-4 | Slash-command catalog | Fix `/help`/`/h` drift now (fold into the immediate fix); defer the full command registry until command count exceeds ~8. |
| MCP-A | Child-process boundary residual | R-09 (merged) covers env, frames, config screen, process-group. Keep only death supervisor, whitespace warning, fail-fast dead-child race. |
| MCP-B | Result/description hygiene residual | R-09 (merged) covers description scan, tag strip, provenance, annotations, sampling refusal. Keep only content/structuredContent alternation, bridge base64 predecode. |
| MCP-C | Server lifecycle residual | R-09 (merged) covers list_changed, breaker, proven session, HTTP hygiene, include/exclude, pagination. Keep only schema cache with lazy connect, idle recycling. |
| MP-1 | Locality everywhere | R-13 covers it but R-13 is NOT merged (sonnet branch). If R-13 merges first, MP-1 collapses to the reroute-notice residual (move to MP-2). If not, MP-1's locality work is live. **Verify before dispatch.** |
| MP-4 | Measured context and residency | Accept the core (usage anchor, error-text parser, route-keyed cache, LM Studio loaded-state). Defer `keep_alive` policy and prompt-prefix caching behind founder decisions 6, 7. |
| DAEMON-01 | Lock/exit-code + stuck-turn watchdog | Split: lock/exit-code fixes now, stuck-turn watchdog later. |
| BIND-01 | Config CAS + file-binding | Config CAS/base-hash guard now. File-binding pieces after R-08/R-07. |
| SURFACE-01 | Dashboard bug fixes + compositor | Accept bug fixes and S-effort hygiene. Defer compositor/wizard/blueprint until real consumers/design decisions exist. |
| T3 | Eval ledger + stop-gate seam | Accept ledger/eval metric/convention. Defer stop-gate seam until the real handler exists. |
| T5 | Findings-shape unification + support bundle | Accept unification, artifact hash, coverage registry. Merge support bundle with LOG-01. **Verify R-15 merge status** (sonnet branch). |
| T6 | CSP test + npm allowlist + entitlements | Accept CSP test, npm allowlist, tracking job. Defer entitlement test and broad async rulepack. |
| OTHER-P5 | (already in best — install identity) | — |
| OTHER-P6 | localStorage guard + settings reload | Ship guarded localStorage + basic reload table. Defer projected-view diff and subprocess probe cache. |

#### Deferred (founder-decision-gated)

| ID | Gate |
|---|---|
| MEM-P5 | Memory write path (SK-6 / founder memory-boundary decisions 1–5) |
| SP-5 | Skills write path (SK-6). Record invariants in `DECISIONS.md` now. |
| SP-6 | `/learn` needs SK-6; `/review` needs SK-6 + SP-5; quote gate needs `egress.web_fetch`; 1-3-1 brief needs founder decision 6. Reserve names now. |
| CMD-A | Second command surface or command count > ~8. Merge `/help`/`/h` fix into SP-4. |
| DIST-02 | Signing identity and entitlements decision. |
| TT-06 | Real subagent consumer. Fix narrow wedge bugs if confirmed. |

#### Verify-first (pending sonnet batch merge)

| ID | What to verify |
|---|---|
| MP-1 | R-13's locality work (sonnet branch, not merged) |
| SCHED-P1 | R-03's receipt/durability work (sonnet branch, not merged) |
| SCHED-P3 | R-03's overlap items (sonnet branch, not merged) |
| T5 | R-15's eval harness (sonnet branch, not merged) |
| CSC-03 | R-12 Phase A (sonnet branch, not merged) + Phases B/C (merged, unwired) |

---

## Part B — Implementation Plan

### Design principles

1. **Primitives before consumers.** Shared modules (process_group,
   text_hygiene, durable_write, subprocess_env, deadline) land before the
   packets that consume them. This prevents duplicate implementations.
2. **Live defects first.** The cheapest, highest-value work is fixing bugs
   that silently lose data or leak credentials today.
3. **One merge per seam.** Packets that touch the same file merge into one
   dispatch unit (e.g., LOG-01 + OTHER-P2 share `obs/logging.py`).
4. **Verify before claiming done.** Every action is validated against the
   resulting artifact/state before reporting completion (verification-before-done).
5. **No model names on surfaces.** No migrations. No second locality judge
   or feature gate. No emoji. Two-dependency contract holds.

### Test discipline

Every implementation unit must include tests. From `AGENTS.md`:

```bash
# Main tree
arch -arm64 .venv/bin/python -m pytest halbert_core/tests

# Worktree
arch -arm64 ./wt_pytest.py halbert_core/tests
```

`main` is not green — get a baseline on the merge-base before attributing
failures. T1 (hermetic environment) is in Phase 0 precisely because it makes
the test suite trustworthy for everything that follows.

---

### Phase 0 — Shared primitives + test foundation

**Goal:** land the reusable modules and the hermetic test environment that
everything else depends on. No founder decisions. File-disjoint — can
parallelize.

| Unit | Scope | Files | Effort | Verification |
|---|---|---|---|---|
| **T1** | Hermetic test fixture that re-pins every import-time path constant away from the live host. Live-DB guard: a check that fails the suite if any test opens `conversations.db` or `~/.config/halbert/skills` on the real host. Shared checklist of every store that resolves a default path at import time. | `tests/conftest.py`, new fixture module | M | Suite runs with zero live-host access; guard test passes |
| **OTHER-P4** | `utils/deadline.py` — a bounded-execution helper (deadline + cancellation check) consumed by execute_code, eval judge, scheduler executor. | new `utils/deadline.py` | S | Unit tests for deadline expiry, cancellation, and clean exit |
| **process_group** | `utils/process_group.py` — `start_new_session` + `killpg` escalation helper. Reuse the pattern from `streaming/pty.py` (already correct). One function, consumed by terminal, scheduler, MCP. | new `utils/process_group.py` | S | Unit test: spawn a child that spawns a grandchild, kill the group, assert grandchild is reaped |
| **text_hygiene** | `security/text_hygiene.py` — consolidate `mcp/metadata.py:strip_unicode_tags` (R-09) + `prompts/agent_prompts.py:_CONTROL_TAG_RE` into one module. Add the NFKC fold table (SP-2), random-boundary wrapper (SP-2), and source-hygiene block (SP-6). Every consumer imports from here. | new `security/text_hygiene.py`; update `mcp/metadata.py` and `prompts/agent_prompts.py` to import from it | S-M | Existing tests pass; new tests for fold table, boundary wrapper, tag strip |
| **durable_write** | `utils/durable_write.py` — temp file in target dir, write + flush, fsync, `os.replace`, directory fsync, optional mode/chmod. | new `utils/durable_write.py` | S | Unit test: write, crash before replace (temp remains, target unchanged), write + replace (target updated), fsync verified |
| **subprocess_env** | `tools/subprocess_env.py` — `build_subprocess_env(baseline, extras)` that strips credential-shaped names. Reuse R-09's `build_child_env` pattern. One function, two policies (MCP allowlist, general blocklist). | new `tools/subprocess_env.py` | S | Unit test: credential-shaped names stripped; declared extras preserved; shared test walks every `subprocess.`/`Popen`/`PTYSession` call site |
| **DIAG-02** | Read-only store integrity diagnostics + `open_read_only(path)` SQLite opener (`mode=ro`, `PRAGMA query_only=ON`). | new diagnostic module; `open_read_only` in a shared util | M | Open production store read-only; assert no write possible; integrity check runs |

**Sequencing within Phase 0:** T1 first (makes the test suite trustworthy).
Everything else is file-disjoint and can parallelize after T1.

---

### Phase 1 — Live defect fixes

**Goal:** fix the bugs that silently lose data, leak credentials, or kill
healthy work today. These are independent of each other (different files)
and can parallelize after Phase 0.

| Unit | Scope | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **SP-3** | Fix the multi-tool dispatch data-loss bug in `state_machine.py` (drops all but the first tool call). Add a test that emits two tool calls and asserts both execute. | `agents/state_machine.py` | S | — | Test: two tool calls both execute; test: one tool call still works |
| **MP-2** | (1) Fix `rate_limiter.py` `Retry-After` clamp — honour full `Retry-After` up to 600s, cap only the exponential branch. (2) Replace bare `time.sleep` in `tier_router.py` 429/529 loop with interruptible backoff (a `/stop` lands within 0.5s). (3) Fix health axis conflation — `BackendIdentity` + `FailureScope` so a fallback candidate is skipped only along the axis the failure invalidated. (4) Wire or retire `error_recovery.py`'s dead circuit breaker (zero callers confirmed). | `model/rate_limiter.py`, `model/tier_router.py`, `agents/error_recovery.py` | M | — | Test: `Retry-After: 3600` waits 3600s not 60s; test: `/stop` during backoff returns within 0.5s; test: 401 does not mark DNS unhealthy; test: breaker opens after 5 failures, closes after success |
| **MP-3** | (1) Replace `aiohttp.ClientTimeout(total=self.timeout)` in `llm_client.py` with idle-gap detector (`sock_read=idle_gap, total=None`) scaled by context size. (2) Add abort hook that closes the aiohttp response/session for a cancelled generation (from a foreign thread). | `agents/llm_client.py`, `model/client.py` | M | MP-2 (shares the interruptible backoff) | Test: healthy stream survives past 120s; test: stopped turn closes the connection within 0.5s; test: idle stream times out |
| **MP-6** | `build_subprocess_env()` applied to every `subprocess.run`/`Popen`/`PTYSession` call site: `tools/system_tools.py`, `streaming/pty.py`, accelerator/gpu tools, `schedule_cron`. Credential-shaped names stripped. | `tools/system_tools.py`, `streaming/pty.py`, `tools/subprocess_env.py` | S-M | subprocess_env (Phase 0) | Test: no subprocess receives `HALBERT_API_TOKEN` or `ANTHROPIC_API_KEY`; shared call-site walk test |
| **VMV-3** | Central media limits (max base64/image/audio size), MIME sniffing, raw exception leakage fix, credentialed guest-home URL fix (never render as display name). Bind privileged unredacted paths to host-owned retained sets. | `routes/audio.py`, `frigate_tools.py`, media handlers | S-M | text_hygiene (for URL scrub) | Test: oversized input rejected; test: raw exception not leaked; test: credentialed URL not in display name |
| **TT-03** | Command normalization/deobfuscation, fail-closed parsing, deny-list precedence over allow-list, combined approval, unattended-origin policy, worktree mutation rule. | `tools/executor.py`, command parsing | S | text_hygiene | Test: denied command through quoting is refused; test: deny-list wins over allow-list; test: unattended origin refused |
| **P2** | Approval bound to artefact — bind approval to device/inode or base hash, not a path string. Prevents approve-then-replace race. | approval/consent modules | S | — | Test: approve file, replace file, assert approval no longer valid |
| **OTHER-P5** | (1) Install identity — replace raw-hostname mDNS node IDs with a stable install identity. (2) Bounded downloads — size + deadline limit on network-fetched files. Reuse `durable_write` for atomic persistence. | install identity module, download helper | S-M | durable_write (Phase 0) | Test: mDNS node ID is not the raw hostname; test: oversized download is cut; test: identity survives restart |

---

### Phase 2 — Structural prerequisites & infrastructure

**Goal:** land the structural pieces that downstream packets depend on.
Some depend on Phase 0/1; others are independent.

| Unit | Scope | Files | Effort | Depends on | Verification |
|---|---|---|---|---|---|
| **DIAG-01** | `halbert doctor` as a findings registry: one `Finding` shape (severity, provenance/`why_trust`, fix hints) + `halbert doctor --json` + `GET /api/diagnostics`. Build the registry; populate incrementally from every workstream's residuals. | new doctor module, dashboard route | M | DIAG-02 (read-only opener) | Test: `halbert doctor --json` returns findings; test: `GET /api/diagnostics` returns the registry; test: a new finding registers correctly |
| **CH-A** | (1) Turn cause axis — `InternalTurnSource` (scheduler/tick/tool-event) carried beside `ChannelDeclaration` so a machine-originated turn is admitted with honest provenance and NO speaker claim. (2) Sanitized bracketed inbound envelope for every admitted turn. (3) `config/watcher.py` starvation bug fix (cancels and re-creates a `threading.Timer` on every file change with no floor deadline). | `agents/channels.py`, `config/watcher.py` | M | — | Test: scheduler-originated turn admitted with correct provenance, no dashboard claim; test: watcher does not starve under rapid file changes |
| **GW-A** | (1) Wire the existing PTY replay ring (thrown away in `streaming/pty.py`) through the terminal WS. (2) `dashboard/event_replay.py` with per-session seq stamping + epoch + bounded ring-buffer replay for `/ws` broadcast. (3) `since_seq` reconnect parameter client-side. (4) Typed error envelope for the 55 bare `{'error': str(e)}` returns in `mcp/server.py`. | `streaming/pty.py`, new `dashboard/event_replay.py`, `mcp/server.py` | S-M | — | Test: reconnect with `since_seq` sees missed events; test: PTY replay wired through WS; test: MCP error returns typed envelope |
| **LOG-01 + OTHER-P2** | Merged logging packet: `JsonFormatter` on `RotatingFileHandler`, `RedactingFilter` on root handler, `LogRecordFactory`, first-character pre-check, redacted support bundle (merged with T5's bundle). One commit sequence — same 30-line `obs/logging.py` hub. | `obs/logging.py`, `dashboard/__main__.py` | M | — | Test: log records are JSON, redacted; test: support bundle is redacted, local, staged; test: root handler has the filter |

---

### Phase 3 — Solid ACCEPTs that build on Phases 0–2

**Goal:** land the remaining ACCEPT packets that depend on the primitives
and structural pieces. These are real gaps with real consumers, but lower
urgency than the live defects. Grouped by dependency.

#### Depends on process_group + text_hygiene

| Unit | Scope | Effort |
|---|---|---|
| **TT-01** | Shell executor hardening: process-group kill, PID+start-time fingerprint, redact-before-cap ordering, ANSI/Unicode strip, deterministic exit interpretation, atomic write + read-back verification, device/inode approval binding. Route all redaction through R-05's registry. | M |
| **SCHED-P2** | Honest inactivity-based timeouts (not flat wall-clock) + shared process-group kill helper. Must not kill healthy active work. | M |

#### Depends on activity-clock

| Unit | Scope | Effort |
|---|---|---|
| **SCHED-P4** | Turn liveness and activity-clock approach. | S-M |
| **TT-05** | Tool-loop guardrails and malformed-call recovery. | S |

#### Depends on text_hygiene

| Unit | Scope | Effort |
|---|---|---|
| **SP-2** | Prompt assembly honesty: tool-output blocks, guest/tool-list drift, non-ASCII fold table. Reuse text_hygiene module. | M |
| **P4** | Untrusted-data delimiters. | S |

#### Depends on CH-A (cause axis)

| Unit | Scope | Effort |
|---|---|---|
| **CSC-02** | Turn admission and identity — builds on the cause axis. | M |

#### Depends on read-only SQLite opener

| Unit | Scope | Effort |
|---|---|---|
| **OTHER-P1** | State backup / create-only behavior. Respect no-migration rules. | S |

#### Independent (no Phase 0–2 dependency)

| Unit | Scope | Effort |
|---|---|---|
| **T2** | Fix Darwin memory information defect. | S |
| **T4** | Wire contracts + model-name-surface evaluation. Must assert absence of model names, not recommend or surface them. | S-M |
| **VMV-1** | Wake-word correctness on macOS ARM64, name-resolution, reset-on-resume. | S-M |
| **VMV-6** | Audio footprint + capability assertions (reuse `has_capability()`). | S |
| **MEM-P1** | Read-side memory trust and visibility. | M |
| **MEM-P3** | Forgotten-request tombstones in the recall gate. | S |
| **MEM-P6** | Provenance and redaction determinism. | S |
| **CSC-01** | Conversation crash/recovery. | M |
| **CSC-04** | Session-tree integrity. | S-M |
| **P1** | Permission lattice residual. | M |
| **P6** | Trusted-directory/executable resolution. | S |
| **TERM-02** | Watched-terminal read/close tools + withdraw-not-refuse convention. | S-M |
| **OTHER-P3** | Measured-not-assumed behavior. | S |

---

### Phase 4 — Reshape residuals (after verification)

**Goal:** after the sonnet batch (R-03, R-13, R-15, R-12 Phase A) merges to
`main`, re-verify the overlap claims and dispatch only the genuine residuals.

| Unit | Trigger | What remains |
|---|---|---|
| **MP-1** | R-13 merges | If R-13 merged: collapses to reroute-notice residual (move to MP-2). If not: full locality work is live. |
| **SCHED-P1** | R-03 merges | Route cancel through live executor, re-read job state, PID+start-time, owner-only perms. Drop duplicated receipt/durability work. |
| **SCHED-P3** | R-03 merges | Auto-disable, standing-order semantics, emergency stop. Drop R-03-covered items. |
| **T5** | R-15 merges | Findings-shape unification, MCP artifact hash verification, coverage registry. Merge support bundle with LOG-01. |
| **CSC-03** | R-12 Phase A merges + wires | Compaction correctness residual. |
| **MCP-A** | Verify R-09 (already merged) | Death supervisor, whitespace warning, fail-fast dead-child race. |
| **MCP-B** | Verify R-09 | content/structuredContent alternation, bridge base64 predecode. |
| **MCP-C** | Verify R-09 | Schema cache with lazy connect, idle recycling. |
| **SP-1** | Verify R-11 (already merged) | Typed readiness evaluator, authoring sweep, builtin annotations. |
| **VMV-2** | Verify R-10 (already merged) | SSE scrubber, output activity tracking, bounded transcript queue. |
| **VMV-4** | Verify R-01/R-02 (already merged) | Replayable event tail, reconnect supervisor, duplicate suppression. |
| **TT-02** | Verify R-09 (already merged) | PTY shell env fencing, positive denial marker, empty ContextVar, trusted executable checks. |

---

### Phase 5 — Founder-decision-gated

**Goal:** dispatch when the named gate is cleared. Do not build before.

| Unit | Gate |
|---|---|
| MEM-P5 | Memory write path (SK-6 / founder memory-boundary decisions 1–5) |
| SP-5 | Skills write path (SK-6). Record invariants in `DECISIONS.md` now. |
| SP-6 | `/learn` needs SK-6; `/review` needs SK-6 + SP-5; quote gate needs `egress.web_fetch`; 1-3-1 brief needs founder decision 6. Reserve names now. |
| CMD-A | Second command surface or command count > ~8. |
| DIST-02 | Signing identity and entitlements decision. |
| TT-06 | Real subagent consumer. |
| SCHED-P5 (tail) | LaunchAgent/supervisor — founder decision on macOS lifecycle. |
| SCHED-P6 (tail) | User-created jobs + detached task registry — named consumer. |
| VMV-5 (tail) | Day journal/logbook — founder decision + vision redaction review. |
| SURFACE-01 (tail) | Compositor/wizard/blueprint — real consumers + design decisions. |
| BIND-01 (tail) | File-binding pieces after R-08/R-07. |
| DAEMON-01 (tail) | Stuck-turn watchdog — after lock/exit-code fixes land. |
| T3 (tail) | Stop-gate seam — after the real handler exists. |
| T6 (tail) | Entitlement test — after signing/packaging decisions. |
| OTHER-P6 (tail) | Projected-view diff + subprocess probe cache — if needed. |
| TT-04 (tail) | Background registry/wake lane — real consumer. |
| MP-4 (tail) | `keep_alive` policy + prompt-prefix caching — founder decisions 6, 7. |
| MP-6 (tail) | Credential-as-reference — founder decision 3 + M8 landing first. |

---

## Part C — Sequencing summary

```
Phase 0 (primitives + test foundation)
  T1 ──────────────────────────────────────────────> makes tests trustworthy
  OTHER-P4 (deadline) ──┐
  process_group ────────┤
  text_hygiene ─────────┤── file-disjoint, parallel after T1
  durable_write ────────┤
  subprocess_env ───────┤
  DIAG-02 (read-only) ──┘

Phase 1 (live defects) ── parallel, different files
  SP-3 (data-loss bug)
  MP-2 (provider failure) ──┐── MP-3 shares interruptible backoff
  MP-3 (transport liveness)┘
  MP-6 (subprocess env) ────── needs subprocess_env from Phase 0
  VMV-3 (media limits)
  TT-03 (command normalization) ── needs text_hygiene from Phase 0
  P2 (approval-bound-to-artefact)
  OTHER-P5 (install identity) ── needs durable_write from Phase 0

Phase 2 (structural prerequisites)
  DIAG-01 (doctor registry) ── needs DIAG-02 from Phase 0
  CH-A (turn cause axis)
  GW-A (event stream reconnect)
  LOG-01 + OTHER-P2 (merged logging)

Phase 3 (solid ACCEPTs) ── depends on Phases 0–2
  TT-01, SCHED-P2 ── need process_group
  SCHED-P4, TT-05 ── need activity-clock
  SP-2, P4 ── need text_hygiene
  CSC-02 ── needs CH-A
  OTHER-P1 ── needs read-only opener
  T2, T4, VMV-1, VMV-6, MEM-P1, MEM-P3, MEM-P6,
  CSC-01, CSC-04, P1, P6, TERM-02, OTHER-P3 ── independent

Phase 4 (reshape residuals) ── after sonnet batch merges
  MP-1, SCHED-P1, SCHED-P3, T5, CSC-03 ── verify R-03/R-13/R-15/R-12
  MCP-A/B/C, SP-1, VMV-2, VMV-4, TT-02 ── verify R-09/R-11/R-10/R-01/R-02

Phase 5 (founder-gated) ── when the gate clears
  MEM-P5, SP-5, SP-6, CMD-A, DIST-02, TT-06, + tails
```

---

## Part D — What this plan does not do

- It does not implement code. It is a dispatch plan.
- It does not assert that any sonnet-batch remediation packet (R-03, R-13,
  R-15, R-12 Phase A) is merged — because it is not. Phase 4 verifies first.
- It does not override `ROADMAP.md` or `DECISIONS.md`. This is a `.handoff/`
  document — session correspondence, zero authority.
- It does not prescribe a plan format for the executor. It provides scope,
  files, effort, dependencies, and verification per unit.
- It does not commit to timelines. Effort estimates (S/M/L) are relative,
  not calendar.

---

---

## Part E — Scrutiny pass: UX review of the "needs review" set

The "needs review" set in Part A contains 30 RESHAPE packets, 6 DEFER
packets, and 5 verify-first packets. This section re-examines each from a
**UX perspective** — does it improve what the person experiences when
interacting with Halbert? — and identifies the ones that should be promoted
to the implementation plan.

Halbert's UX contract, from `AGENTS.md` and `DECISIONS.md`:

- One seamless conversation — hidden topic threads, no conversation list.
- Halbert speaks as the computer itself, in first person, grounded in
  measured data.
- Commands staged from the UI are staged, never executed.
- No model names on any user-facing surface.
- No emoji — icon fonts or graphic design.

A "UX-valuable" idea is one that makes the conversation more honest, more
seamless, more responsive, more trustworthy, or prevents a bad experience
(crash, hang, silent failure, data loss, secret leak).

### UX scrutiny of each "needs review" packet

#### MEM-P2 — Promotion mechanics and the product-boundary test

**UX angle:** When Halbert recalls something, the person should be able to
trust *why* Halbert knows it. "You told me" vs "the camera observed" vs "I
read it in a file" are different trust levels. The origin-class column is the
mechanism that makes Halbert honest about its sources. Without it, every
recall is undifferentiated — Halbert either over-claims ("you told me X"
when it actually observed X) or under-claims ("I remember X" with no source).

**Verdict:** The typed ownership (origin classes) is UX-valuable. The
product-boundary test (a secret in a transcript does not survive into
promoted memory) is a trust property the person relies on without knowing
it. The A01 mechanics (recency decay, reload bug, hash/day caps) are R-14's
territory (merged). **Promote the residual:** product-boundary test +
contamination backstop + envelope strip check.

**Promoted to Phase 3 as:** MEM-P2 (residual).

---

#### MEM-P4 — Continuity doctor and the promotion inspector

**UX angle:** A "Queued for promotion" table in the Memory page would let the
person see what Halbert is considering remembering. This is a transparency
surface — the person can see what's being promoted and why. The continuity
doctor (typed findings about corrupt artifacts, dead claim keys) feeds
`halbert doctor`, which is the "Halbert tells you what's wrong with itself"
surface.

**Verdict:** The doctor findings are UX-valuable (Halbert self-diagnoses).
The "Queued for promotion" table is UX-valuable (transparency). But the
promotion inspector depends on the memory write path, which is gated on
founder decisions 1–5. **Keep DEFERRED** — the gate is real.

---

#### CSC-03 — The conversation survives the process

**UX angle:** When the backend crashes and restarts, does the person lose
their place in the conversation? If compaction is broken, a long
conversation silently degrades — Halbert "forgets" something said 20 turns
ago. This is invisible when it works and very visible when it doesn't.

**Verdict:** Genuinely UX-valuable, but blocked on R-12 Phase A (sonnet
branch, not merged). **Keep in Phase 4 (verify-first).**

---

#### CSC-05 — Turn admission, identity and mid-turn verbs

**UX angle:** When the person sends a message while Halbert is still
generating, what happens? If the mid-turn verbs are broken, the person's
input is lost or delayed. This is a responsiveness UX issue.

**Verdict:** R-01 (merged) covered the interrupt algebra. The residual is
compaction correctness, which is CSC-03's territory. **Keep in Phase 4
(verify-first).**

---

#### CSC-06 — Terminal reattach and desktop boot

**UX angle:** This is the **"one seamless conversation"** directive made
literal. Three live defects:

1. Per-chunk `errors="replace"` decoding corrupts multi-byte UTF-8 code
   points split across read boundaries — non-ASCII terminal output (any
   path with accented characters, emoji, or CJK) is silently corrupted.
2. The PTY reattach loop is half-built and wired nowhere —
   `streaming/pty.py:320` drops the replay item, the frontend marks a
   running shell as `exitCode -1` on any close. Laptop sleep or a wifi flap
   shows a running shell as exited while the process keeps running.
3. The port decision is a textbook TOCTOU — `lib.rs:33-35` binds and drops
   a `TcpListener`, then passes the port to the sidecar. This has already
   bitten once (the comment at `:56` records it).

The person's experience: they close the laptop, open it, and their terminal
is gone. Or Halbert starts on the wrong port and the dashboard can't
connect. These are direct UX failures on the "seamless" promise.

**Verdict:** All three are live defects with no remediation overlap. The
UTF-8 decoder fix and the port announcement are S effort. The PTY reattach
loop is S-M. **Promote to Phase 2** (structural prerequisite — it's the
desktop boot + terminal reattach foundation).

**Promoted to Phase 2 as:** CSC-06.

---

#### P3 — Self-modification: fence, staging store, honest config writes

**UX angle:** When Halbert modifies its own config, the person should be
able to trust that the modification was honest — no silent overwrite, no
instruction injection. The "honest config writes" part is UX: a setting
that silently reverts (because a concurrent session overwrote it) is a
trust failure.

**Verdict:** The config-write honesty overlaps with BIND-01a (config CAS
preconditions), which is already promoted. The self-modification fence and
staging store are security infrastructure, not directly UX. **Keep as
RESHAPE** — the UX-relevant part is already in BIND-01a.

---

#### P5 — Third-party process boundary and file-path primitives

**UX angle:** Mostly security. The one UX-relevant piece is "credentialed
URLs must never be rendered as display names" — if Halbert shows
`https://user:password@host` in a surface, that's both a security leak and
a bad UX. But this is already covered by the cross-cutting SSRF guard
primitive.

**Verdict:** The UX-relevant part is the SSRF guard, which is a
cross-cutting primitive. **Keep as RESHAPE** — build the primitive, let
P5's residual ride on it.

---

#### SCHED-P1 — Scheduler durability residual

**UX angle:** If a scheduled job fires twice or not at all, the person sees
flaky behavior — "I told Halbert to check the camera every hour and it
didn't." This is a trust failure. But R-03 (sonnet branch) covers the
receipt/durability work.

**Verdict:** Blocked on R-03 merge. **Keep in Phase 4 (verify-first).**

---

#### SCHED-P3 — Auto-disable, standing orders

**UX angle:** "Standing orders" is a UX concept — "always tell me when the
camera sees a person" is a standing order the person gives once and
expects Halbert to honor. If Halbert silently stops doing it, that's a
trust failure. But the auto-disable (stop doing something that keeps
failing) needs to be **visible** — Halbert should tell the person "I
stopped checking the camera because it's been failing for 3 hours."

**Verdict:** The standing-order semantics and auto-disable-with-visibility
are UX-valuable. But the overlap with R-03 must be verified first.
**Keep in Phase 4 (verify-first).** The visibility piece (Halbert tells the
person it stopped) should be noted as a UX requirement when the residual
is scoped.

---

#### SCHED-P5 — Process lifecycle (core)

**UX angle:** "Does Halbert survive a restart?" is a fundamental UX
expectation for a steward that lives on your machine. The core lifecycle
items are:

1. **Bounded shutdown** — `dashboard/app.py:1623-1724` has ten unbounded
   awaits; one hung websocket close forces SIGKILL. The person sees
   "Halbert won't quit" and force-quits.
2. **Unclean-exit sentinel** — `app.py:141-172` heals turn rows on EVERY
   boot without classifying the previous death. Running `quick_check(1)`
   only on suspicious boot catches corruption early. The person sees
   "Halbert repaired itself" instead of "Halbert is confused."
3. **Thaw reconnect** — after a laptop sleep, HA stream/Frigate
   MQTT/Wyoming each reconnect on their own sweep, but a coordinated thaw
   reconnect from the heartbeat tick gap is cleaner. The person sees
   "Halbert came back" instead of "Halbert is silent after sleep."

These are all founder-independent (no LaunchAgent/supervisor needed). The
gated tail (event-loop watchdog, startup-deadlock, launchd) is correctly
deferred.

**Verdict:** The core (bounded shutdown + unclean-exit sentinel + thaw
reconnect) is UX-valuable and dispatchable now. **Promote to Phase 2.**

**Promoted to Phase 2 as:** SCHED-P5 (core only).

---

#### SCHED-P6 — The scheduled-work surface (dashboard pieces)

**UX angle:** The person should be able to **see and control** what Halbert
is scheduled to do. Today the frontend exports
`getScheduledJobs()`/`cancelScheduledJob()` against live endpoints and
**nothing in the frontend calls them** — dead client code. The person has
no way to see what's scheduled, what has run, or cancel a job. This is a
direct UX gap on a surface the founder has already directed ("user shells
stay but are watched by the AI").

The dashboard list/history/cancel is S-M effort, no founder decision
needed. The webhook normalizer (~20 lines) applies to any outbound URL
Halbert accepts from config. The weekly digest improvements (coverage-gaps
section + read-back verification) are deterministic and medium effort.

**Verdict:** The dashboard list/history/cancel + webhook normalizer +
weekly digest are UX-valuable and dispatchable now. The user-created jobs
and detached task registry are correctly deferred. **Promote to Phase 3.**

**Promoted to Phase 3 as:** SCHED-P6 (dashboard pieces only).

---

#### TT-02 — PTY shell env fencing

**UX angle:** Mostly security. The "positive denial marker" (when a tool
is denied, the model gets a clear reason) is slightly UX — the model can
tell the person "I can't do X because Y" instead of failing silently. But
this is a secondary effect.

**Verdict:** The UX value is indirect. The security value is real but
overlaps with R-09 (merged). **Keep as RESHAPE** — verify R-09, keep the
PTY-specific residual.

---

#### TT-04 — Background registry, yield, wake, and the watched-terminal surface

**UX angle:** The PTY reattach (Half A) is directly UX-valuable: laptop
sleep or a wifi flap shows a running shell as exited while the process
keeps running. The person sees "my terminal died" when it didn't. The
foreground-command guardrail is also UX: today `npm run dev` burns the
full DEFAULT_TIMEOUT because the foreground command can't be backgrounded.

The ProcessRegistry (Half B) is infrastructure for a consumer that doesn't
exist yet. The yield-to-background may be done by R-01.

**Verdict:** Half A (PTY reattach + foreground guardrail + progress labels
+ bounded wait) is UX-valuable and dispatchable now. Half B is correctly
deferred. **Promote Half A to Phase 3.**

**Promoted to Phase 3 as:** TT-04a (PTY reattach + guardrails).

---

#### VMV-2 — SSE scrubber, transcript queue

**UX angle:** When voice output has garbage characters (Unicode tags,
control sequences), the person hears garbage. The SSE full-tag scrubber
is a voice-quality UX issue. The bounded transcript queue prevents the
voice HUD from lagging behind. Both are real UX on the voice surface.

**Verdict:** UX-valuable, but R-10 (merged) may have covered the speech
egress pipeline. **Keep in Phase 4 (verify-first)** — verify R-10, keep
only the residual.

---

#### VMV-4 — Replayable event tail, reconnect

**UX angle:** If the voice stream drops and reconnects, the person misses
what was said. The replayable event tail means the person can hear what
they missed. This is a "seamless" UX issue on the voice surface.

**Verdict:** UX-valuable, but R-01/R-02 (merged) may have covered the
provenance and admission ordering. **Keep in Phase 4 (verify-first)** —
verify R-01/R-02, keep only the residual.

---

#### VMV-5 — Screen and vision truthfulness

**UX angle:** When Halbert says "I see a window at position (100, 200)" and
the coordinate is wrong by 2x because the screenshot was downscaled, the
person can't trust what Halbert says about the screen. This is a
**truthfulness** issue — Halbert is lying about what it sees, without
knowing it. The coordinate mapping disclosure (thread pre/post geometry
and crop origin out of ScreenCapture, append a scale/offset note) is S
effort, no founder gate.

The person's experience: Halbert stages a command that clicks at (100,
200), but the actual screen position is (200, 400). The person approves a
click on the wrong target. This is a safety-relevant UX defect.

**Verdict:** The coordinate disclosure is UX-valuable, S effort, no gate.
**Promote to Phase 3.** The day journal/logbook is correctly deferred.

**Promoted to Phase 3 as:** VMV-5 (coordinate disclosure only).

---

#### SP-1 — Honest/scanned catalog residual

**UX angle:** When a skill is available but not ready (its dependency is
missing, its backend is down), does Halbert know? The typed readiness
evaluator means Halbert can say "I can't do X because Y isn't ready"
instead of silently failing. This is a truthfulness UX issue.

**Verdict:** UX-valuable, but R-11 (merged) covers ~70%. **Keep in Phase 4
(verify-first)** — verify R-11, keep only the residual.

---

#### SP-4 — Slash-command catalog

**UX angle:** The `/help` and `/h` drift is a direct UX bug. The person
types `/help` and gets one thing; they type `/h` and get another (or a
skill named `help` shadows the builtin). This is confusing on the one
surface where the person explicitly asks for help. The fix is S effort —
add `/help` and `/h` to `RESERVED_SLASH_BUILTINS` and pin with a test.

The full command registry (fuzzy scoring, level normaliser, one-table) is
L effort for a surface with four commands. Correctly deferred.

**Verdict:** The `/help`/`/h` drift fix is UX-valuable and S effort.
**Promote to Phase 1** (it's a live bug, fix it with the other live defects).

**Promoted to Phase 1 as:** SP-4a (`/help`/`/h` drift fix).

---

#### MCP-A/B/C — MCP residuals

**UX angle:** Mostly security/infrastructure. The schema cache (MCP-C) is
slightly UX — the dashboard opens faster because it doesn't spawn N
third-party subprocesses on boot. The content/structuredContent alternation
(MCP-B) is token cost, not directly UX. The death supervisor (MCP-A) is
not UX.

**Verdict:** Low UX value. **Keep in Phase 4 (verify-first)** — verify
R-09, keep only the residual.

---

#### MP-1 — Locality everywhere

**UX angle:** If a secure turn runs on a cloud connection, the person's
data leaves their machine without their knowledge. This is a
**privacy/trust** UX issue — the person expects "my steward runs on my
machine" and silently it doesn't.

**Verdict:** UX-valuable, but R-13 (sonnet branch, not merged) covers it.
**Keep in Phase 4 (verify-first).**

---

#### MP-4 — Measured context and residency

**UX angle:** If Halbert claims to handle a 128k context but actually
truncates at 32k, that's **dishonest** — the person asks a question about
something said 100k tokens ago and Halbert has silently forgotten it. The
measured context core (usage-anchored token accounting, error-text parser,
route-keyed cache, LM Studio loaded-state) makes the context window
honest. The slot-switch warning ("this turn ran on a cloud connection") is
a transparency UX issue.

The person's experience: Halbert says "I can handle long conversations"
but after 30k tokens it starts forgetting earlier parts. The person
doesn't know why. The usage anchor fixes this — Halbert knows its real
window and can say "I'm nearing my context limit" honestly.

**Verdict:** The core (usage anchor + error-text parser + route-keyed
cache + LM Studio loaded-state + slot-switch warning + usage-row
instrumentation) is UX-valuable and dispatchable now. The `keep_alive`
policy and prompt-prefix caching are correctly deferred behind founder
decisions 6, 7. **Promote to Phase 3.**

**Promoted to Phase 3 as:** MP-4 (core only).

---

#### DAEMON-01 — Single-instance lock, exit vocabulary, stuck-turn watchdog

**UX angle:** Three UX-critical items:

1. **Single-instance lock** — today a second launch spawns a second
   backend with two schedulers, two heartbeats, two writers against one
   conversation store. The person sees "Halbert is behaving strangely"
   (duplicate scheduled runs, conflicting writes) and doesn't know why.
   S effort.
2. **Exit vocabulary** — two constants + a `supervised()` probe. Prerequisite
   for the stuck-turn watchdog and for launch-at-login. S effort.
3. **Stuck-turn reclamation watchdog** — `state_machine.py:512-519`
   bounds only the acquire side; a wedged turn holds the lock for the
   process lifetime. The person sends a message and **nothing happens**.
   This is one of the worst UX experiences — a hung conversation with no
   feedback. M effort, but touches `state_machine.py` (hot file — the
   section file names it "the fourth touch on the file; merge last").

The person's experience with a stuck turn: they type a message, hit send,
and the spinner spins forever. No error, no timeout, no recovery. They
force-quit Halbert. This is the single worst UX failure mode in the
product.

**Verdict:** The single-instance lock + exit vocabulary (DAEMON-01a) is S
effort and prevents data corruption — **promote to Phase 1**. The
stuck-turn watchdog (DAEMON-01b) is M effort and hot-file-sensitive —
**promote to Phase 3** with a note to merge last in the wave. Both are
UX-critical.

**Promoted to Phase 1 as:** DAEMON-01a (single-instance lock + exit
vocabulary).
**Promoted to Phase 3 as:** DAEMON-01b (stuck-turn watchdog).

---

#### BIND-01 — Config CAS + file-binding

**UX angle:** The config CAS (content-addressed precondition on config
writes) prevents a setting from being silently overwritten by a concurrent
session. The person changes a setting, it appears to save, and then it
reverts because another session overwrote it. This is a "Halbert didn't
listen to me" UX failure. S effort, confirmed live defect.

The file-binding pieces (bind_path activation, path boundary, exec
allowlist) are security, not directly UX.

**Verdict:** The config CAS is UX-valuable and S effort. **Promote to
Phase 1** (it's a live bug). The file-binding pieces stay in Phase 5
(after R-08/R-07).

**Promoted to Phase 1 as:** BIND-01a (config CAS precondition).

---

#### SURFACE-01 — Dashboard bug fixes

**UX angle:** This IS the UX surface. Six sub-items are confirmed bugs or
S-effort and independent:

1. **Approval expiry enforcement** — `approval/engine.py:317-332` never
   compares `expires_at` to now; `EXPIRED` is never assigned. A timed-out
   approval can still be approved. The person sees an expired approval
   work when it shouldn't. Security-relevant UX defect. S effort.
2. **Stale-tone override** — `Dashboard.tsx:48-58` keeps the last metrics
   on a failed poll, so a wedged backend leaves a red bar over data of
   unknown age. The person sees "everything is fine" (stale green) or
   "everything is broken" (stale red) when neither is true. Violates
   "grounded in measured data." S effort.
3. **LTR trojan-source defence** — `ConfirmationDialog.tsx:52-57` renders
   via `dangerouslySetInnerHTML` with no direction attribute. A
   right-to-left override character in a command can make the approval
   dialog show a different command than what will execute. S effort,
   security-relevant UX.
4. **Typed refresh policy** — 20+ `setInterval` sites, a Tauri window left
   open all day keeps the host busy answering polls nobody reads. The
   person sees the dashboard consume CPU when idle. M effort, frontend-only.
5. **Skills settings page** — there is no skill disable surface today. The
   person can't turn off a skill. M effort.
6. **Reconnect owner** — the 3-5s fixed backoff works for localhost but
   has no jitter or stability window. S effort, low priority.

**Verdict:** Items 1–3 are confirmed bugs, S effort — **promote to Phase
1**. Items 4–6 are S-M effort, independent — **promote to Phase 3**. The
compositor, wizard, blueprint catalog are correctly deferred.

**Promoted to Phase 1 as:** SURFACE-01a (approval expiry + stale-tone +
LTR defence).
**Promoted to Phase 3 as:** SURFACE-01b (refresh policy + skills settings
page + reconnect owner).

---

#### T3 — Eval ledger + stop-gate seam

**UX angle:** The eval ledger is infrastructure, not UX. The stop-gate
seam is about when a turn stops — slightly UX (a turn that can't stop
cleanly is a stuck turn, which is DAEMON-01b's territory).

**Verdict:** Low UX value beyond what DAEMON-01b covers. **Keep as
RESHAPE** — the stop-gate seam defers until the real handler exists.

---

#### T5 — Findings-shape unification + support bundle

**UX angle:** The support bundle is UX — when something goes wrong, the
person can export a redacted bundle for support. But the support bundle is
already merged into LOG-01 + OTHER-P2 (Phase 2). The findings-shape
unification is infrastructure.

**Verdict:** The UX-relevant part is already in the plan. **Keep as
RESHAPE** — verify R-15, keep the residual.

---

#### T6 — CSP test + npm allowlist

**UX angle:** Security, not UX. The CSP test prevents a malicious script
from running in the dashboard, but this is not a direct UX improvement.

**Verdict:** Low UX value. **Keep as RESHAPE.**

---

#### OTHER-P6 — Settings reload + localStorage guard

**UX angle:** Two UX-critical items:

1. **Guarded localStorage accessor** — `DebugContext.tsx:37` is inside a
   `useState` initializer of a provider that wraps the app. A throwing
   `localStorage` (Tauri webview with storage disabled, private mode) takes
   the **whole dashboard down at mount**. The person sees a blank screen.
   S effort, one-file fix.
2. **Settings reload plan** — only the personality block hot-reloads
   (`dashboard/routes/settings.py:3201-3209`); everything else requires a
   restart or silently hot-patches. The founder runs concurrent sessions
   editing settings — a blanket restart on every save is disruptive. The
   person changes a setting and has to restart Halbert. S-M effort.

**Verdict:** Both are UX-valuable. The localStorage guard prevents a
total dashboard crash — **promote to Phase 1**. The settings reload plan
makes settings changes take effect without a restart — **promote to
Phase 3**.

**Promoted to Phase 1 as:** OTHER-P6a (guarded localStorage accessor).
**Promoted to Phase 3 as:** OTHER-P6b (settings reload plan).

---

### Summary of promoted packets

| Packet | Promoted to | What | UX reason | Effort |
|---|---|---|---|---|
| **CSC-06** | Phase 2 | UTF-8 decoder fix + PTY reattach loop + port announcement | Seamless conversation: terminal survives reconnect, dashboard connects on the right port | S-M |
| **SCHED-P5** | Phase 2 | Bounded shutdown + unclean-exit sentinel + thaw reconnect | Halbert quits cleanly, repairs itself on boot, comes back after sleep | S-M |
| **DAEMON-01a** | Phase 1 | Single-instance lock + exit vocabulary | Prevents two backends corrupting one store | S |
| **DAEMON-01b** | Phase 3 | Stuck-turn reclamation watchdog | Hung conversation is the worst UX failure mode | M |
| **BIND-01a** | Phase 1 | Config CAS precondition | Setting silently reverts = "Halbert didn't listen" | S |
| **SP-4a** | Phase 1 | `/help`/`/h` drift fix | Help command is confused = bad first impression | S |
| **SURFACE-01a** | Phase 1 | Approval expiry + stale-tone + LTR defence | Expired approval works, stale data lies, trojan command | S |
| **OTHER-P6a** | Phase 1 | Guarded localStorage accessor | Blank dashboard on storage-disabled webview | S |
| **SCHED-P6** | Phase 3 | Dashboard list/history/cancel + webhook normalizer + digest | Person can see and control scheduled work | S-M |
| **TT-04a** | Phase 3 | PTY reattach + foreground guardrail + progress labels | Terminal survives laptop sleep, long commands don't block | S-M |
| **VMV-5** | Phase 3 | Coordinate mapping disclosure | Halbert is honest about screen coordinates | S |
| **MP-4** | Phase 3 | Usage anchor + error-text parser + route-keyed cache + LM Studio loaded-state + slot-switch warning + usage rows | Context window is honest, Halbert knows its real limit | M |
| **SURFACE-01b** | Phase 3 | Refresh policy + skills settings page + reconnect owner | Dashboard consumes CPU when idle, can't disable skills | S-M |
| **OTHER-P6b** | Phase 3 | Settings reload plan | Settings take effect without restart | S-M |
| **MEM-P2** | Phase 3 | Product-boundary test + contamination backstop + envelope strip check | Secrets don't survive into promoted memory; Halbert is honest about sources | S-M |

### What stays in "needs review" and why

| Packet | Why it stays |
|---|---|
| MEM-P4 | Gated on memory write path (founder decisions 1–5) |
| CSC-03, CSC-05 | Blocked on R-12 Phase A (sonnet branch, not merged) |
| P3 | UX-relevant part (config honesty) is already in BIND-01a |
| P5 | UX-relevant part (SSRF guard) is a cross-cutting primitive |
| SCHED-P1, SCHED-P3 | Blocked on R-03 (sonnet branch, not merged) |
| TT-02 | Low UX value; verify R-09 first |
| VMV-2, VMV-4 | Verify R-10/R-01/R-02 first |
| SP-1 | Verify R-11 first |
| MCP-A/B/C | Low UX value; verify R-09 first |
| MP-1 | Verify R-13 (sonnet branch, not merged) |
| T3, T5, T6 | Low UX value; infrastructure or verify-first |
| MEM-P5, SP-5, SP-6, CMD-A, DIST-02, TT-06 | Founder-decision-gated |

---

## Part F — Updated phase plan (with promoted packets)

The promoted packets are inserted into the existing phases. Phase numbers
and contents below supersede Part B for the affected phases.

### Phase 0 — Shared primitives + test foundation (unchanged)

| Unit | Scope | Effort |
|---|---|---|
| T1 | Hermetic test environment + live-DB guard | M |
| OTHER-P4 | `utils/deadline.py` bounded-execution helper | S |
| process_group | `utils/process_group.py` — process-group escalation | S |
| text_hygiene | `security/text_hygiene.py` — one untrusted-content sanitizer | S-M |
| durable_write | `utils/durable_write.py` — atomic durable writes | S |
| subprocess_env | `tools/subprocess_env.py` — one subprocess env builder | S |
| DIAG-02 | Read-only store integrity diagnostics + `open_read_only()` | M |

### Phase 1 — Live defect fixes (updated with promoted UX fixes)

| Unit | Scope | Files | Effort | Depends on |
|---|---|---|---|---|
| SP-3 | Fix multi-tool dispatch data-loss bug | `agents/state_machine.py` | S | — |
| MP-2 | Retry-After fix, interruptible backoff, BackendIdentity, wire/retire circuit breaker | `model/rate_limiter.py`, `model/tier_router.py`, `agents/error_recovery.py` | M | — |
| MP-3 | Idle-gap stream timeout, abort hook | `agents/llm_client.py`, `model/client.py` | M | MP-2 |
| MP-6 | `build_subprocess_env()` for all tools | `tools/system_tools.py`, `streaming/pty.py` | S-M | subprocess_env |
| VMV-3 | Central media limits, MIME sniffing, credentialed URL fix | `routes/audio.py`, `frigate_tools.py` | S-M | text_hygiene |
| TT-03 | Command normalization, fail-closed parsing, deny-list precedence | `tools/executor.py` | S | text_hygiene |
| P2 | Approval bound to artefact (device/inode or base hash) | approval/consent modules | S | — |
| OTHER-P5 | Install identity + bounded downloads | install identity module, download helper | S-M | durable_write |
| **DAEMON-01a** | **Single-instance lock + exit vocabulary + `supervised()` probe** | `dashboard/__main__.py`, `dashboard/app.py` | **S** | — |
| **BIND-01a** | **Config CAS precondition on config writes (base-hash guard)** | `model/llm_config.py`, `routes/settings.py` | **S** | — |
| **SP-4a** | **Fix `/help`/`/h` drift — add to `RESERVED_SLASH_BUILTINS`, pin with test** | `skills/reserved.py` | **S** | — |
| **SURFACE-01a** | **Approval expiry enforcement + stale-tone override + LTR trojan-source defence** | `approval/engine.py`, `Dashboard.tsx`, `ConfirmationDialog.tsx` | **S** | — |
| **OTHER-P6a** | **Guarded localStorage accessor (prevent dashboard crash at mount)** | `DebugContext.tsx` + 10 other sites | **S** | — |

### Phase 2 — Structural prerequisites (updated with promoted UX fixes)

| Unit | Scope | Files | Effort | Depends on |
|---|---|---|---|---|
| DIAG-01 | `halbert doctor` findings registry + `--json` + `GET /api/diagnostics` | new doctor module, dashboard route | M | DIAG-02 |
| CH-A | Turn cause axis + envelope sanitizer + watcher deadline fix | `agents/channels.py`, `config/watcher.py` | M | — |
| GW-A | Wire PTY replay ring through WS, event replay ring, typed error envelope | `streaming/pty.py`, `dashboard/event_replay.py`, `mcp/server.py` | S-M | — |
| LOG-01 + OTHER-P2 | Merged logging packet + support bundle | `obs/logging.py`, `dashboard/__main__.py` | M | — |
| **CSC-06** | **UTF-8 decoder fix + PTY reattach loop + port announcement on stdout** | `streaming/pty.py`, `src-tauri/src/lib.rs`, `dashboard/__main__.py` | **S-M** | — |
| **SCHED-P5** | **Bounded shutdown + unclean-exit sentinel + thaw reconnect** | `dashboard/app.py`, heartbeat tick | **S-M** | — |

### Phase 3 — Solid ACCEPTs + promoted UX packets (updated)

| Unit | Scope | Effort | Depends on |
|---|---|---|---|
| TT-01 | Shell executor hardening | M | process_group, text_hygiene, durable_write |
| SCHED-P2 | Honest inactivity-based timeouts + process-group kill | M | process_group, activity-clock |
| SCHED-P4 | Turn liveness and activity-clock | S-M | activity-clock |
| TT-05 | Tool-loop guardrails and malformed-call recovery | S | activity-clock |
| SP-2 | Prompt assembly honesty + untrusted-content fencing | M | text_hygiene |
| P4 | Untrusted-data delimiters | S | text_hygiene |
| CSC-02 | Turn admission and identity | M | CH-A |
| OTHER-P1 | State backup / create-only behavior | S | read-only opener |
| T2 | Fix Darwin memory information defect | S | — |
| T4 | Wire contracts + model-name-surface evaluation | S-M | — |
| VMV-1 | Wake-word correctness on macOS ARM64 | S-M | — |
| VMV-6 | Audio footprint + capability assertions | S | — |
| MEM-P1 | Read-side memory trust and visibility | M | — |
| MEM-P3 | Forgotten-request tombstones | S | — |
| MEM-P6 | Provenance and redaction determinism | S | — |
| CSC-01 | Conversation crash/recovery | M | — |
| CSC-04 | Session-tree integrity | S-M | — |
| P1 | Permission lattice residual | M | — |
| P6 | Trusted-directory/executable resolution | S | — |
| TERM-02 | Watched-terminal read/close tools + withdraw-not-refuse | S-M | — |
| OTHER-P3 | Measured-not-assumed behavior | S | — |
| **DAEMON-01b** | **Stuck-turn reclamation watchdog (merge last — hot file)** | **M** | DAEMON-01a, state-machine work |
| **SCHED-P6** | **Dashboard list/history/cancel + webhook normalizer + weekly digest** | **S-M** | — |
| **TT-04a** | **PTY reattach + foreground guardrail + progress labels + bounded wait** | **S-M** | GW-A (replay ring) |
| **VMV-5** | **Coordinate mapping disclosure (scale/offset note on downscaled captures)** | **S** | — |
| **MP-4** | **Usage anchor + error-text parser + route-keyed cache + LM Studio loaded-state + slot-switch warning + usage rows** | **M** | — |
| **SURFACE-01b** | **Typed refresh policy + skills settings page + reconnect owner** | **S-M** | — |
| **OTHER-P6b** | **Settings reload plan (declarative table: personality hot, slots hot rebuild, bind/token/restart)** | **S-M** | — |
| **MEM-P2** | **Product-boundary test + contamination backstop + envelope strip check** | **S-M** | MEM-P1 (origin-class column) |

### Phase 4 — Reshape residuals (unchanged)

After the sonnet batch (R-03, R-13, R-15, R-12 Phase A) merges to `main`,
re-verify and dispatch only the genuine residuals. See Part B Phase 4.

### Phase 5 — Founder-decision-gated (unchanged)

See Part B Phase 5.

---

## Source

- `.handoff/oss-pass-2/FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md` — the
  full critical report with every packet verdict.
- `.handoff/oss-pass-2/deep-eval-group{1,2,3,4}-*.md` — the four deep
  evaluations with per-packet reasoning.
- `.handoff/STATE-OF-WORK-2026-09-10.md` — confirms sonnet batch is still
  on its branch, not merged to `main`.
- `AGENTS.md` — standing directives, test commands, invariants.
