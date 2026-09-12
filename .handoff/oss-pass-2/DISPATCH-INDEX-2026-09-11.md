# DISPATCH INDEX — OSS Pass-2 (corrected)

Written 2026-09-11 by the review session. This is the master control document for
dispatching the OSS pass-2 discovery backlog. It supersedes the milestone tables in
`FORMAL-IMPLEMENTATION-PLAN-2026-09-11.md` (which it corrects per
`REVIEW-FORMAL-PLAN-2026-09-11.md`). The authoritative verdicts remain in
`FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md`; the deep-evals remain the
per-packet detail.

This is correspondence, not authority. `ROADMAP.md` and `DECISIONS.md` are the spine.

**Verified against:** Halbert `main` @ `fbd725e9` (2026-09-11). Sonnet remediation
branch `fix/remediation-sonnet-batch-1` (32 commits) surveyed for merge — clean,
zero conflicts, zero new test failures. Origin repos at `/Volumes/Thunderbolt/AI/OSS/`.

---

## 1. Execution sequence (six steps)

| Step | What | Who | Gate |
|---|---|---|---|
| 0 | Land **SP-3 + SP-4a** (live defects) in their own worktree | fable (us) | founder merge |
| 1 | **Verify + merge sonnet batch** (R-03/R-12-A/R-13/R-15); validation = no new failures vs the 23-failure baseline | fable (us) | founder merge |
| 2 | **Re-baseline M5a verdicts** against the merged tree (MP-1, SCHED-P1/P3, T5, CSC-03v collapse to residuals) | fable (us) | — |
| 3 | Build **M0 substrate** (10 primitives) in one worktree | fable (us) | T1 first |
| 4 | **Dispatch** M1–M4 as parallel packets; M5a after step 2 | opus/sonnet sessions | lane order |
| 5 | **Final integration review**: every merged packet verified against measured state; DIAG-01 gets first real findings | fable (us) | — |

Steps 0–3 and 5 are us (fable). Step 4 is other sessions. The M5b gated units wait on
founder decisions regardless of step.

---

## 2. The dispatch-packet template (deliverable — was missing from the handoff)

Every packet (`PKT-<milestone>-<slug>.md`) is self-contained for a cold session.
Fields, in order:

```
# PKT-<id> — <name>
Tier: fable | opus | sonnet | gated        Milestone: M0..M5b
Collision lane: <lane letter(s)>            Merge order: <rank within lane>
Verified against: halbert main @ <sha> (<date>)

1.  Packet ID + name
2.  User problem            — first-person-machine frame; what the person experiences today
3.  What to build           — minimum viable slice, concrete
4.  What NOT to build       — explicit exclusions + where they go instead
5.  Target files            — each [exists @ path:line (anchor: symbol/string)] or [new file];
                              nearest existing analogue for new files
6.  Dependencies            — unit IDs that must land first; primitives; remediation to verify
7.  Effort + justification  — S/S-M/M/M+/L with a one-line why (from the deep-eval)
8.  UX rationale            — why this improves trust / recoverability / clarity / latency / success
9.  Acceptance criteria     — measurable 'done'
10. Verification            — runnable command or test ID; checks MEASURED OS state, not model judgment
11. Exclusions              — what is NOT in this unit and where it goes

OSS reference      — origin repo file:line to read before building (or 'greenfield — no OSS reference')
Repo traps         — the boilerplate block below
Gate quote         — (gated units only) the verbatim founder decision text + status
Riders             — cross-packet items this unit carries, each recorded in BOTH rows
```

### Repo-trap boilerplate (included verbatim in every packet)

```
- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest
  (the editable install pins halbert_core to the MAIN tree; wt_pytest.py strips the finder).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py,
  test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py
  (~23 failures, from streaming-reasoning/num_ctx work). A failure is yours iff absent from this baseline.
- Work in a git worktree; make narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers to commits. Subject + body only.
- No emoji anywhere (code, comments, UI, docs).
- Colours only from shared-tokens/tokens.css; run scripts/check_contrast.py. Never hardcode a colour.
- Never name or recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: route through is_local_model() (model/llm_config.py:181) — the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499) — never gate on _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py. Scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations or back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: every line cite carries an anchor; re-anchor by grep before editing. A failed anchor
  is a rebase signal, not a spec change.
- Do not modify product code outside this packet's Target files. .handoff/ work is correspondence.
```

---

## 3. Hot-file collision map + merge lanes (deliverable — was incomplete)

Two units that share a file share a lane. Within a lane, merge in the order shown;
`merge-last` units land after all others in their lane. Lanes are file-disjoint from
each other, so packets in different lanes parallelize freely.

| Lane | File | Units (merge order →) |
|---|---|---|
| A | `agents/state_machine.py` (9) | SP-3 → CSC-01 → CSC-02 → CSC-03 → CSC-05 → MP-5 → SCHED-P4 → TT-05 → DAEMON-01b |
| B | `streaming/pty.py` (4) | CSC-06 → GW-A → TT-02 → MP-6 |
| C | `tools/safety.py` (4) | TT-03 → TT-04a → P1 → P6 |
| D | `scheduler/executor.py` (4) | SCHED-P2 → SCHED-P6 → SCHED-P1 → SCHED-P3 |
| E | `dashboard/__main__.py` (3) | DAEMON-01a → CSC-06 → LOG-01 |
| F | `dashboard/app.py` (3) | DAEMON-01a → SCHED-P5 → CSC-03 |
| G | `model/client.py` (3) | MP-3 → MP-4 → MP-5 |
| H | `tools/executor.py` (3) | TT-01 → TT-03 → P1 |
| I | `approval/engine.py` (3) | SURFACE-01a → P2 → P3 |
| J | `agents/conversation_sqlite.py` (3) | CSC-01 → CSC-04 → CSC-03 |
| K | `mcp/client.py` (3) | MCP-A → MCP-C → TT-02 |
| L | `prompts/agent_prompts.py` (2) | text_hygiene → SP-2 |
| M | `agents/llm_client.py` (2) | MP-3 → MEM-P6 |
| N | `model/llm_config.py` (2) | MP-4 → BIND-01a |
| O | `dashboard/routes/settings.py` (2) | BIND-01a → OTHER-P6b |
| P | `continuity/recall_gate.py` (2) | MEM-P1 → MEM-P3 |
| Q | `obs/logging.py` (2) | LOG-01 → OTHER-P2 |
| R | `dashboard/routes/audio.py` (2) | VMV-2 → VMV-3 |

The 9-way `state_machine.py` lane (A) is the hottest. Rule: **one lane-A packet in flight at a time**; SP-3 lands first (step 0), then the rest merge in lane order with TT-05 and DAEMON-01b last. Lane O (`routes/settings.py`, 3491 lines) carries a rebase risk — BIND-01a and OTHER-P6b should not run concurrently. Lane I (`approval/engine.py`) enforces the §2.4 ordering: SURFACE-01a (expiry) lands before P2 (artefact binding), P3 last.

---

## 4. Unit registry

### M0 — Substrate integrity & shared primitives (fable builds)

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **DAEMON-01a** | Single-instance flock + exit vocabulary + supervised() probe | fable | S | EF | — |
| **DIAG-02** ⁿ | Read-only SQLite opener + store integrity + FTS corruption classifier fix | fable | M | - | — |
| **OTHER-P4** ⁿ | Bounded-execution deadline helper | fable | S | - | — |
| **T1** | Hermetic test environment + live-DB guard | fable | M | - | — |
| **activity_clock** ⁿ | Per-instance monotonic activity clock | fable | S | - | — |
| **durable_write** ⁿ | Atomic durable-write helper | fable | S | - | — |
| **process_group** ⁿ | Process-group start/kill escalation | fable | S | - | — |
| **reconnect_supervisor** ⁿ | Reconnect supervisor primitive | fable | S-M | - | — |
| **subprocess_env** ⁿ | Subprocess env builder (blocklist) | fable | S | - | — |
| **text_hygiene** ⁿ | One untrusted-content sanitizer | fable | S-M | L | — |

### M1 — Model pipeline & conversational resilience

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **SP-3** ★ | Multi-tool dispatch loop (fix data-loss) | fable | M | A | — |
| **DAEMON-01b** ⏻ | Stuck-turn reclamation watchdog | opus | M | A | activity_clock, DAEMON-01a |
| **MP-2** | Retry-After + interruptible backoff + write-only breaker fix | opus | M | - | activity_clock |
| **MP-3** | Idle-gap stream timeout + abort hook | opus | M | GM | activity_clock, MP-2 |
| **MP-4** | Usage-anchored token accounting + route-keyed cache | opus | M | GN | — |
| **MP-5** | Local-model tool-call repair | opus | L | AG | SP-3 |

### M2 — Watched terminal & sovereign command engine

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **BIND-01a** | Config CAS precondition (base-hash guard) | opus | S | NO | durable_write |
| **CSC-06** | Terminal reattach + UTF-8 decoder + port announcement | opus | S-M | BE | — |
| **GW-A** ⁿ | Event replay ring + typed MCP error envelope | opus | S-M | B | CSC-06, reconnect_supervisor |
| **P2** | Approval bound to artefact (device,inode,sha256) | opus | M | I | durable_write, SURFACE-01a |
| **SP-2** | Prompt assembly honesty | opus | M | L | text_hygiene |
| **TERM-02** ⁿ | Watched-terminal read/close tools | opus | S-M | - | TT-04a, GW-A |
| **TT-01** | Shell executor hardening | opus | M | H | process_group, text_hygiene, durable_write |
| **TT-03** | Command normalization/deobfuscation + fail-closed parsing | opus | S | CH | text_hygiene |
| **TT-04a** | PTY reattach + foreground-command guardrail | opus | S-M | C | CSC-06, GW-A |
| **TT-05** ⏻ | Tool-loop guardrails + malformed-call recovery | opus | M+ | A | activity_clock |
| **SP-4a** ★ | Fix /help /h drift in RESERVED_SLASH_BUILTINS | sonnet | S | - | — |

### M3 — Memory trust, turn provenance & diagnostic core

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **DIAG-01** ⁿ | halbert doctor findings registry + --json + /api/diagnostics | fable | M | - | DIAG-02 |
| **CH-A** | Turn cause axis + envelope sanitizer + watcher starvation fix | opus | M | - | text_hygiene |
| **CSC-01** | Turn-boundary trust + decode integrity | opus | M | AJ | — |
| **CSC-02** | Deterministic context reclaim + window-relative budgets | opus | M | A | CH-A |
| **CSC-03** | Conversation survives the process (crash-survival) | opus | M | AFJ | — |
| **CSC-04** | Session-tree integrity (corruption quarantine) | opus | S-M | J | — |
| **CSC-05** | Turn admission and identity | opus | M | A | CH-A |
| **LOG-01** | Structured redacted logging (JsonFormatter+RotatingFileHandler+RedactingFilter+LogRecordFactory) | opus | M | EQ | text_hygiene |
| **MEM-P1** | Read-side memory trust (origin_class) | opus | M | P | — |
| **MEM-P3** | Forgotten-request tombstones (recall gate) | opus | S | P | MEM-P1 |
| **MEM-P4** ⁿ | Product-boundary test + contamination backstop (was plan MEM-P2) | opus | S-M | - | MEM-P1 |
| **MEM-P6** | Compaction gate follows real numbers | opus | S | M | MP-4 |
| **OTHER-P1** ⁿ | State backup / recover (merged with plan-MEM-P3 backup scope) | opus | M | - | durable_write, DIAG-02 |
| **OTHER-P2** | Correlated redacted logging | opus | M | Q | text_hygiene |
| **OTHER-P3** | Measured-not-assumed behavior | opus | S | - | — |
| **OTHER-P5** | Install identity (mDNS) + bounded downloads | opus | S-M | - | durable_write, OTHER-P4 |
| **P1** | Permission lattice residual (command gate rebuild) | opus | M | CH | — |
| **P3** | Halt semantics residual (drop broad lease registry) | opus | S | I | — |
| **P4** | Untrusted-data delimiters | opus | S | - | text_hygiene |
| **P5** ⁿ | Centralized SSRF / base-URL guard | opus | S-M | - | — |
| **P6** | Trusted-directory/executable resolution | opus | S | C | — |
| **SUPPORT-BUNDLE** ⁿ | Redacted support bundle (zip: config, doctor JSON, log tail) | opus | S-M | - | DIAG-01, LOG-01 |
| **T3** ⁿ | Verification-evidence ledger + invented-completion eval metric + UI-verify convention | opus | M | - | — |
| **T6** | CSP/window-open contract test + npm install-script allowlist + upstream tracking job | sonnet | S-M | - | — |

### M4 — Grounded UI, voice & ambient stewarding

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **OTHER-P6b** ⁿ | Settings reload plan (declarative table) | opus | S-M | O | — |
| **SCHED-P2** | Honest inactivity-based timeouts + process-group kill | opus | M | D | process_group, activity_clock |
| **SCHED-P4** | Turn liveness (activity-clock) | opus | S-M | A | activity_clock |
| **SCHED-P5** | Core lifecycle (bounded shutdown + unclean-exit sentinel + RSS log + thaw reconnect) | opus | S-M | F | reconnect_supervisor |
| **SCHED-P6** ⁿ | Scheduled-work surface (list/history/cancel) + webhook normalizer + digest | opus | S-M | D | — |
| **SURFACE-01a** | Approval expiry enforcement + stale-tone + LTR defence | opus | S | I | — |
| **SURFACE-01b** ⁿ | Typed refresh policy + skills settings page + reconnect owner | opus | S-M | - | reconnect_supervisor |
| **T4** | Wire contracts + model-name-surface evaluation | opus | S-M | - | — |
| **VMV-1** | Wake-word correctness on macOS ARM64 | opus | S-M | - | — |
| **VMV-3** | Central media limits + MIME sniffing + exception/URL leakage fixes | opus | S-M | R | text_hygiene, P5 |
| **VMV-5** | Coordinate mapping disclosure | opus | S | - | — |
| **VMV-6** | Audio footprint + capability assertions | opus | S | - | — |
| **MP-6** | build_subprocess_env applied to every subprocess call site | sonnet | S-M | B | subprocess_env |
| **OTHER-P6a** | Guarded localStorage accessor (11 sites) | sonnet | S | - | — |
| **T2** | Fix Darwin memory information defect | sonnet | S | - | — |

### M5a — Post-sonnet verification residuals

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **CSC-03v** | R-12 Phase A + B/C wiring verification -> compaction residual | opus | S | - | verify R-12 |
| **MCP-A** | Death supervisor + whitespace warning + fail-fast dead-child race (post R-09) | opus | S-M | K | process_group |
| **MCP-B** | content/structuredContent alternation + bridge base64 predecode (post R-09) | opus | S | - | verify R-09 |
| **MCP-C** | Schema cache with lazy connect + idle recycling (post R-09) | opus | S-M | K | reconnect_supervisor |
| **MP-1** | R-13 locality verification + reroute-notice residual | opus | S | - | MP-2 |
| **SCHED-P1** | Scheduler durability residual (post R-03) | opus | S | D | verify R-03 |
| **SCHED-P3** | Auto-disable (visible) + standing-order semantics + emergency stop (post R-03) | opus | S-M | D | verify R-03 |
| **SP-1** | Typed readiness evaluator + authoring sweep + builtin annotations (post R-11) | opus | S-M | - | verify R-11 |
| **T5** | Eval findings-shape unification + artifact hash + coverage registry (post R-15) | opus | S-M | - | verify R-15 |
| **TT-02** | PTY shell env fencing + positive denial marker + empty ContextVar (post R-09) | opus | S-M | BK | subprocess_env |
| **VMV-2** | SSE scrubber + output activity tracking + bounded transcript queue (post R-10) | opus | S-M | R | reconnect_supervisor |
| **VMV-4** | Replayable event tail + duplicate suppression (post R-01/R-02) | opus | S-M | - | reconnect_supervisor |

### M5b — Founder-decision-gated (recorded, not dispatched)

| Unit | Name | Tier | Effort | Lane | Depends on |
|---|---|---|---|---|---|
| **CMD-A** | Broad command-turn-context | gated | - | - | — |
| **DIST-02** | Signing identity + entitlements | gated | - | - | — |
| **MEM-P5** | Memory lifecycle infrastructure | gated | - | - | — |
| **SP-4** | Full command registry | gated | - | - | — |
| **SP-5** | Skills write path invariants | gated | - | - | — |
| **SP-6** | /learn /review quote-gate 1-3-1 brief | gated | - | - | — |
| **TT-06** | SubagentManager | gated | - | - | — |

★ = land immediately (step 0). ⏻ = merge last in its lane. ⁿ = primary file is new
(create, not edit).

---

## 5. Cross-cutting primitives (build once, consume many)

| Primitive | Unit | Consumers |
|---|---|---|
| activity_clock | M0/M3 | MP-2, MP-3, SCHED-P2, SCHED-P4, DAEMON-01b, TT-05 |
| durable_write | M0/M3 | OTHER-P5, BIND-01a, OTHER-P1, P2, TT-01 |
| process_group | M0/M3 | TT-01, SCHED-P2, MCP-A |
| text_hygiene | M0/M3 | TT-01, TT-03, CH-A, SP-2, P4, VMV-3, LOG-01 |
| subprocess_env | M0/M3 | MP-6, TT-02 |
| OTHER-P4 (deadline) | M0/M3 | scheduler, eval, OTHER-P5 |
| DIAG-02 (sqlite_safety) | M0/M3 | DIAG-01, OTHER-P1, T5 |
| reconnect_supervisor | M0/M3 | GW-A, VMV-4, VMV-2, MCP-C, SCHED-P5, SURFACE-01b |
| P5 (url_guard) | M0/M3 | VMV-3, MP-6 redirect policy |
| DIAG-01 (doctor) | M0/M3 | SUPPORT-BUNDLE, all residuals' findings |

---

## 6. Packet accounting (every report packet + F01–F20)

True counts: **74 packets** (38 ACCEPT / 30 RESHAPE / 6 DEFER / 0 REJECT) — not the
report's erroneous '27 ACCEPT', not '~84'. Plus 20 research follow-ups (F01–F20).

Every one of the 74 report packets maps to a unit above (buildable, verification,
or gated). The 20 F-units are research reads, NOT dispatched as build units; their
consumers are annotated 'read F… before dispatch':

| F-unit | Disposition | Consumer |
|---|---|---|
| F01 macOS host integration | READ NOW | SCHED-P5, DIST-02, DAEMON-01a |
| F07 gateway auth/approval | read later | after R-08/R-01 residuals (P2, P3) |
| F08 CLI self-diagnosis/update | read later | after DIAG-01 lands |
| F09 first-run/onboarding | read later | when BIRTH-1 (ROADMAP) opens |
| F10 plugin capability contract | read later | if a Python extension surface is decided |
| F11 control UI patterns | read later | when SURFACE-01 wizard work opens |
| F13 reference agent loop | read later | if T3's stop-gate seam needs a reference |
| F14 secrets at rest/broker | read later | when FD-4 (allowed_hosts egress) is decided |
| F17 desktop RPC bridge | read later | TERM-02 |
| F19 cross-cutting primitives | skim | M0 primitives |
| F12, F15, F16, F18, F20 | SKIP | no active Halbert consumer |

---

## 7. Integration-review protocol (deliverable — was missing)

1. **Baseline first.** Before any unit in a milestone lands, record a full
   `arch -arm64 .venv/bin/python -m pytest halbert_core/tests` run on the merge-base.
   Known-red baseline (2026-09-11): `test_agent_model_override.py`,
   `test_agent_model_selected_event.py`, `test_no_model_names_in_user_facing_source.py`,
   `test_num_ctx.py` (~23 failures).
2. **Attributable-failure rule.** A failure is attributable to a unit iff it is absent
   from the recorded baseline. Anything else is pre-existing; note it and move on.
3. **Per-unit measured-state assertions** are written as runnable commands or test IDs
   in the packet (field 10). 'It works' is measured — port bound, exit code, file hash,
   SQLite integrity, a >120s stream completing, a /stop returning <0.5s — never asserted.
4. **Frontend units** (SURFACE-01a/b, SCHED-P6, OTHER-P6a/b) verify by `npm test` +
   `npm run typecheck` (root fan-out) plus a named vitest file, and respect
   'staged, never executed.'
5. **Milestone-exit checklist.** Each milestone's OS-observable end-state is enumerated
   in its packet and checked before the milestone is called done.

---

## 8. Tactical directives

1. **Commit the corpus.** The entire `.handoff/oss-pass-2/` tree is untracked. Commit
   it (and this index) to the planning branch before dispatch — it is the dispatch
   manifest for ~85 units across many sessions.
2. **SP-3 + SP-4a land immediately** (user directive, step 0), superseding the prior
   handoff's 'do not modify product code' planning-only constraint.
3. **T1 lands before any test-dependent work.**
4. **Respect the lanes** (§3). One lane-A packet at a time; DAEMON-01b + TT-05 merge
   last in lane A; BIND-01a + OTHER-P6b not concurrent in lane E.
5. **One merge per seam.** LOG-01 absorbs OTHER-P2 (same 66-line hub). CSC-06 + GW-A
   coordinate (same PTY replay ring). MP-2 + MP-3 coordinate (same interruptible
   backoff) — MP-2 first, MP-3 builds on it.
6. **Verification-before-done**, measured not model-judged (§7).
7. **First-person machine tone** in every error/recovery/diagnostic string.
8. **Dependency re-use, not duplication.** No unit builds its own durable_write,
   activity clock, sanitizer, process-group, subprocess-env, deadline, sqlite opener,
   reconnect supervisor, or url guard — consume the M0/M3 primitive.

