# REMAINING WORK — full inventory with model-tier and effort assignments

**Date:** 2026-09-07
**Re:** the complete remaining scope of the OSS-lift program across Halbert, the Haloysius engine, and the ecosystem, following the reconciled review (`RECONCILIATION-OSS-RESEARCH-PROGRAM-2026-09-07.md`).
**Tier vocabulary:** model = `fable / opus / sonnet` (+ `haiku` for micro-chores); effort = `ultracode / max / xhigh / high / med` per the house fleet convention. "Gated" items cannot start until their named gate opens.
**Companion dispatch:** the Fable scope-overview pass runs before any opus-level work begins (per founder direction): its output is `FABLE-SCOPE-OVERVIEW-AND-APPROVAL-2026-09-07.md` — the approval package for this whole scope.

---

## §1. Where the program stands (one paragraph)

Research done (two OSS syntheses, sixteen deep-dives), implementation designed (nine Halbert packets + a five-phase Haloysius engine program), ecosystem review complete and reconciled (four replies; memory fork resolved to A2-store-level/provenance-first; the universal-vs-app split answered). What remains is: **(a)** the nine Halbert packet executions, most of them dispatch-ready now; **(b)** the Haloysius engine program, handed off and authorized through Phase 3; **(c)** the founder-gated decisions (packet 06 sign-off, the joint Option-C/Phase-B coexistence session); **(d)** the deep-pass design work that was deliberately un-packeted (session tree, skills system, permission system, channel design, watchdog); **(e)** small consumer-side cleanups each app owes itself; **(f)** the recorded engine candidates with their lift conditions.

---

## §2. Halbert dispatch queue — the nine packets, phase by phase

### PACKET 01 — Memory promotion + curated core
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 01-A | Promotion signal store (`continuity/promotion.py`), SQLite persistence, wiring at the two live recall sites (thread auto-recall in `begin_turn`, the `recall_memory` tool), fail-soft proof | **sonnet / high** | Ready now |
| 01-B | Curated core: `build_curated_core` + budget-capped marker eviction + new deterministic `curated` source in `ContextAssembler`; edits the R9 fence comments in two files + `routes/agent.py:164-166`, and a `DECISIONS.md` entry in the same commit | **opus / xhigh** | Gated: review checkpoint + the frozen-vs-per-turn question + the joint coexistence session with the engine's Option C (one decision, both repos) |
| 01-C | Recorded decisions (recall-intent escalation lane; plan-based consolidation port when the LLM pass un-gates; cross-repo alignment — already binding) | — (recorded; no work) | Rides packet 09's scorecard |

### PACKET 02 — Policy lattice, named-gate decisions, claims ladder
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 02-A1/A2 | The lattice (`persona/policy.py`) + the guest-floor parity pin | **sonnet / high** | Ready now |
| 02-B1/B2 | `admission.py` decision records + `claims.py` strength ladder (pure, with the DebateHaus composition rules written into the contract) | **sonnet / high** | Ready now |
| 02-C1 | Gate-list integration on the guest dashboard routes with reason codes surfaced in API error payloads | **opus / xhigh** | Review before dispatch (touches live routes); add Halley's fail-closed note at every integration seam |
| 02-C2 | RoleGate lattice policy view over the write plane | **opus / high** | After 02-A/B merge |
| 02-C3 | Pairing-as-onboarding | — (deferred, recorded) | Only when guests arrive over a non-local channel |

### PACKET 03 — Scheduler durability (with the Hermes addendum)
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 03-A1 | Catch-up policy (`scheduler/catchup.py`) — **with the addendum's cadence-scaled grace** (half-period clamped [120s, 2h]), fast-forward-at-dispatch, retire-past-grace one-shots | **sonnet / high** | Ready now |
| 03-A2 | Restart budget (`scheduler/restart_budget.py`) with clock-rollback hold | **sonnet / med** | Ready now |
| 03-A3 | Run receipts (`scheduler/run_receipts.py`) + **occurrence-level idempotency** (addendum) + closed status set `ok/error/delivery_failed/blocked_config` | **sonnet / high** | Ready now |
| 03-A4 | Monitor-hash gate (new from the addendum — the strongest idle-cost idea: unchanged hash → agent run suppressed) | **sonnet / high** | Ready now |
| 03-B1 | Wire receipts + restart budget into `AutonomousExecutor` (boot recovery, bounded re-run, safe-mode hold) | **opus / high** | After 03-A |
| 03-B2 | Boot catch-up for registered proactive jobs (stagger, per-job max-age, satellite guard) | **opus / high** | After 03-A1 |
| 03-C | Prompted-heartbeat founder decision — Hermes ground rules attached; Hermes ships NO prompted heartbeat, liveness = receipts + status enum | **fable / med** (decision memo) | Founder session; coordinate with attunement workstream |

### PACKET 04 — Typed voice ingress
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 04-A1 | Modality + speaker fields end-to-end (request model, `process()` threading, `build_modality_context` call site, frontend payload) — voice turns never default to admin | **opus / high** | Ready now |
| 04-A2 | Claim strength at the voice gate (records, doesn't enforce) | **sonnet / med** | After 02-B merges |
| 04-B | Turn-scoped mutation digest (`security/turn_digest.py`) wired to voice replies + audit log | **sonnet / high** | Ready now |
| 04-C1 | TTS code-heavy fallback + fence-stripping (`integrations/tts_quality.py`) | **sonnet / med** | Ready now |
| 04-C2 | Spoken summarization | — (deferred) | Blocked on the utility-model slot |
| 04-addendum | Hermes voice-memo disciplines (transcribe-once event cache, echo-back, interrupt-with-transcript, dup suppression) — fold into A1/B | (included above) | — |

### PACKET 05 — Redaction hardening
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 05-A1 | Secret variant registry (raw + URL-encoded + JSON-escaped, bounded FIFO) | **sonnet / high** | Ready now |
| 05-A2 | Register egress-acked values in `get_config_value` | **sonnet / med** | After A1 |
| 05-A3 | `mcp_response()` consults the registry | **sonnet / med** | After A1 |
| 05-B1 | Echo guard pure detector (`security/echo_guard.py`) | **sonnet / high** | Ready now |
| 05-B2 | Locate the outbound seam (verify-first) + wire warn-and-redact | **opus / high** | After B1; chosen seam recorded before wiring |
| 05-C1 | Parity-pinned single redaction core shared MCP/internal | **opus / high** | After A |
| 05-C2 | Camera-gate registration-time assertion | **sonnet / med** | Ready now |
| 05-addendum | Display-side redact+cap seam on UI transport emissions | **opus / high** | After A; audit-first for the seam(s) |
| 05-pre | Pre-flight against `worktree-sec-1-one-door` (6 commits unmerged) | (checklist step) | Before every dispatch |

### PACKET 06 — Zero-context script execution (`execute_code`)
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 06-A1/A2 | Stub-module generator + host RPC (token/allow-list/budget, refusals-free) | **opus / high** | **FOUNDER SIGN-OFF first** (new capability surface; co-signed by DebateHaus + engine) |
| 06-B1 | The registered tool: per-call policy preserved (dispatch through `ToolExecutor.execute()`), stdout cap + spill, inactivity timeout, guest-floor pins | **opus / xhigh** | After A + sign-off |
| 06-B2 | Schema + prompt guidance (when-to-use discipline) | **sonnet / med** | After B1 |
| 06-C | Kernels / file-RPC / failure-hints | — (deferred) | Usage evidence first |

### PACKET 07 — Interrupt algebra
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 07-A1/A2 | Turn-activity generations + the stop/steer/redirect decision core (pure) | **sonnet / med** | Ready now |
| 07-B | State-machine integration — verify-first mapping of abort paths/model-request cancellation, then generation-claimed stop, steer-at-batch-boundary, single pending slot, the race test | **opus / xhigh** | After 07-A + the verify-first findings recorded |
| 07-C | Per-channel busy modes, burst windows, queue editing | — (deferred) | Usage after 07-B |

### PACKET 08 — Conversation-store hardening
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 08-A1 | darwin durability PRAGMAs on both stores | **sonnet / med** | Ready now |
| 08-A2 | FTS fail-open contract (breadcrumb + atomic trigger-drop, rebuild refusal over unknown gap, LIKE continuity) | **sonnet / high** | Ready now |
| 08-A3 | Declarative column reconciliation + backfill discipline + compacted-rows-remain-searchable visibility rule | **sonnet / high** | Ready now |
| 08-addendum | Atomic writes for the scheduler's per-job JSON files (BM/03 feedback) | **sonnet / med** | Fold into 03-B1 or standalone |

### PACKET 09 — R5 eval harness + red-seam probe battery
| Item | What remains | Tier / effort | Gate |
|---|---|---|---|
| 09-A1 | Deterministic synthetic corpus with planted facts (extend `corpus.py`, don't parallel) | **sonnet / high** | Ready now |
| 09-A2 | Question-bank invariance + closed-book exam + hedged-guess scoring (extend `recall_eval.py`) | **opus / high** | After A1 |
| 09-A3 | Policy matrix (NO_CONSOLIDATION ceiling / current deterministic / TRUNCATE_OLDEST baseline; LLM arm SKIPPED-GATE-CLOSED) + first committed scorecard | **opus / high** | After A2 |
| 09-B | Red-seam probe battery: empirically collect the current red list, one standalone probe per seam, self-checking registry (splittable per-seam across sessions) | **sonnet / high** (parallelizable; **ultracode / high** as a batch if run in one session) | Ready now |
| 09-C | CRAG gates-before-judge verdict contract (`continuity/verdict.py`) | **sonnet / med** | After 09-A2 |

---

## §3. The Haloysius engine program (handed off — their sessions execute; tiers recorded for their dispatch)

| Phase | Work | Tier / effort | Gate |
|---|---|---|---|
| EN-1 | Write-time provenance enum (closed set, legacy-value mapping, choke-point enforcement) | **sonnet / high** | Authorized |
| EN-2 | A2 event table + loop-stop (stop `.access()`-on-search, stop per-search `_save_to_disk()`) + atomic persistence migration — one revertible change; four-consumer semantics shift | **opus / max** (highest blast radius in the program) | Authorized; **consumer notice + Halley/BM call-path confirmations are preconditions before merge** |
| EN-3 | Consumer rewiring (consolidation gate, `_strengthen_frequent`, importance + epistemic factors — move or remove, never frozen) + deferred-write API | **opus / high** | After EN-2 |
| EN-4 | Re-ingestion guard: injection fences, symmetric strip, **the pinned role-filter test before the LLM extraction exists** | **opus / high** | After EN-2 (can parallel EN-3) |
| EN-5 | Option B ranker inputs | **sonnet / high** | After EN-3/4 |
| EN-6 | Option C curated core + staging mechanics | **fable / max** (joint design session) | **Gated: the cross-repo coexistence session with Halbert 01-B — one decision, both repos** |
| EN-candidates | IngressDecision lift (after Halbert 02 merges + DebateHaus adopts); eval-protocol lift (after Halbert 09); scheduler status split; write-approval staging (with Option C); `subject_confidence` ladder slot | — (recorded) | Their lift conditions |

---

## §4. Deep-pass design work (deliberately un-packeted — design passes first, then packets)

| Pass | What it is | Tier / effort | Notes |
|---|---|---|---|
| D-1 **Session tree / compaction** | The brainstorm + design pass for the append-only conversation tree (hidden topic threads), designing against Hermes's `publish_compression_child` reference (atomic rotation, watermark tail-clone, lineage-rooted leases, persisted anti-thrash, JSON-marker edge types) — lands ON TOP of packet 08's hardening | **fable / high** (design) → then **opus / max** implementation packets | The strongest long-term structural lift; touches `conversation_sqlite.py`, `threads.py`, state-machine context assembly |
| D-2 **Skills system** | Design pass carrying the Hermes learning-loop skeleton: CC-compatible SKILL.md format with hard >60-char create-time rejection, deterministic nudge counters, post-delivery review with dispatch whitelist, anti-hoarding policy text (lift near-verbatim), read-before-write guard, `created_by` provenance sidecar, archive-not-delete curator, calibrated linter, **and the runner for the Verification section Hermes never built** | **fable / high** (design) → then packet series | Feeds from the OpenClaw §7 findings too |
| D-3 **Permission system (five axes)** | Implementation pass over `PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` (ceiling ∧ affordance ∧ os_grant ∧ consent ∧ ¬halted) consuming packet 02's lattice/gates/claims as the mechanism layer + DebateHaus's composition rules | **opus / max** | After 02-C merges; the doc has no code today |
| D-4 **Channel design** | Per-channel session keys, IDOR-proof cross-surface resume, turn lease by transcript-owner, delivery-obligation ledger, TeeTransport second-frontend — belongs with terminal-channel integration alongside 06/07 | **fable / high** (design) | After 07-B (the verbs exist first) |
| D-5 **Watchdog/daemon** | OpenClaw §8 lifts (close-code 1013, watchdog alignment, crash-loop budgets, restart handoff) + Hermes's startup watchdog template — write the packet when the daemon workstream is scheduled | **fable / med** (when scheduled) | Parked |
| D-6 **Voice RoleGate enforcement** | Turn 04-A2's recording into enforcement (biometric identity feeding the gates; `voice_auth_gate` reachability) | **opus / high** | After 04-A2 + 02-C2 |
| D-7 **Model-picker utility slot** | Hermes's ProviderProfile-derived aux-model ladder (`resolve_aux_model`, per-task `prefer_fast`), honest cost accounting with `pricing_version` | **sonnet / high** | Independent; unblocks 04-C2 |

---

## §5. Founder decision items (the only human-gated items left)

| Item | What it decides | Suggested tier for the prep memo |
|---|---|---|
| F-1 Packet 06 sign-off | Whether `execute_code` (per-call-policy preserved) becomes a capability surface | Already prepped (packet + two co-signs); **fable / med** second-guess memo if wanted |
| F-2 Reply spot-check | The three agent-produced replies (BrightestMinds/Halley/Haloysius) — read before their file:line claims become load-bearing | Founder read; flag corrections into the reconciliation doc |
| F-3 Joint Option-C / 01-B coexistence session | Two curated cores never double-inject; engine budget math; query-time-vs-file; staging shape | **fable / max** joint session (engine Q2/Q5 agenda attached) |
| F-4 Prompted heartbeat | Whether it exists at all (both OSS projects ground rules attached; Hermes ships none) | **fable / med** decision memo (03-C) |

---

## §6. Ecosystem residues (their sessions; recorded for cross-visibility)

| App | Cleanup | Tier |
|---|---|---|
| Halley | Wire the built-but-never-wired consolidation watcher; retire the "recalled N memories" returned-count indicator; consult `authorize_action` in `ToolRegistry.execute()`; note the obfuscated frozen fork ships a pre-shim engine | sonnet / med each |
| BrightestMinds | Remove BM topic maps hard-coded in engine preflight; JSON-store hardening (BM's own case; engine U-5 covers the shared store) | sonnet / med |
| DebateHaus | Adopt `IngressDecision`-shaped gate_graph on the warrant (R-DH-3) | sonnet / med |

---

## §7. The dispatch matrix (one view)

| # | Work | Tier | Effort | State |
|---|------|------|--------|-------|
| 1 | Halbert 01-A promotion store | sonnet | high | READY |
| 2 | Halbert 02-A/B lattice+gates+claims | sonnet | high | READY |
| 3 | Halbert 03-A (incl. A4 monitor hash) | sonnet | high | READY |
| 4 | Halbert 04-A1 voice ingress | opus | high | READY |
| 5 | Halbert 04-B digest, 04-C1 TTS rules | sonnet | high/med | READY |
| 6 | Halbert 05-A + C2 | sonnet | high | READY |
| 7 | Halbert 08 (all three tasks) | sonnet | high | READY |
| 8 | Halbert 09-A (corpus → exam → scorecard) | opus | high | READY |
| 9 | Halbert 09-B probe battery | sonnet (or **ultracode batch** / high) | READY |
| 10 | Halbert 03-B executor wiring | opus | high | after 03-A |
| 11 | Halbert 07-A algebra core | sonnet | med | READY |
| 12 | Halbert 05-B2 echo-guard seam, 05-C1 core, 05-addendum display seam | opus | high | after 05-A |
| 13 | Halbert 02-C route/RoleGate integration | opus | xhigh | review-gated |
| 14 | Halbert 07-B state-machine integration | opus | xhigh | after 07-A + verify findings |
| 15 | Halbert 06 (A→B) | opus | xhigh | FOUNDER SIGN-OFF |
| 16 | Halbert 01-B curated core | opus | xhigh | JOINT SESSION F-3 |
| 17 | Halbert 04-A2 claim recording | sonnet | med | after 02-B |
| 18 | Halbert 09-C CRAG contract | sonnet | med | after 09-A2 |
| 19 | Engine EN-1 provenance | sonnet | high | AUTHORIZED |
| 20 | Engine EN-2 A2+loop-stop+atomic | opus | **max** | AUTHORIZED; consumer confirmations gate merge |
| 21 | Engine EN-3 consumer rewiring + write API | opus | high | after EN-2 |
| 22 | Engine EN-4 re-ingestion guard | opus | high | after EN-2 |
| 23 | Engine EN-5 Option B inputs | sonnet | high | after EN-3/4 |
| 24 | Engine EN-6 / Halbert 01-B coexistence | fable | max | F-3 joint session |
| 25 | Deep-pass D-1 session tree design | fable | high | design pass |
| 26 | Deep-pass D-2 skills design | fable | high | design pass |
| 27 | Deep-pass D-3 permission system build | opus | max | after 02-C |
| 28 | Deep-pass D-4 channel design | fable | high | after 07-B |
| 29 | Deep-pass D-6 voice enforcement | opus | high | after 04-A2 |
| 30 | Deep-pass D-7 utility slot | sonnet | high | independent |
| 31 | Decisions F-1/F-4 memos | fable | med | founder sessions |
| 32 | Ecosystem residues | sonnet | med | their sessions |

## §8. Recommended sequencing (first three waves)

**Wave 1 (dispatch now, parallel — all independent, all well-specified):** 01-A, 02-A/B, 03-A, 08, 09-A, 09-B, 04-A1, 05-A/C2, 07-A, and engine EN-1. Rationale: pure-function ports and hardening with strong test shapes (sonnet/high), the voice-ingress gap (opus/high — it's a real security gap, don't let it wait), and the engine provenance enum (everything downstream needs it).
**Wave 2 (after wave-1 merges):** 03-B, 04-B/C1, 05-B2/C1/addendum, 04-A2, 09-C, engine EN-2 (with its consumer-confirmation preconditions), then EN-3/EN-4.
**Wave 3 (gated items + design passes):** F-1 sign-off → 06; F-3 joint session → 01-B + EN-6; D-1/D-2 fable design passes can start anytime (they don't touch code) and should — their outputs become the next packet series; 02-C and 07-B when their reviews open.

**Total opus-level work that can begin immediately after the Fable approval:** items 4, 8, 12, 13, 14, 15 (after sign-off), 16 (after F-3) on the Halbert side, and 20-22 on the engine side — the sonnet items can even begin before the approval since they're low-risk, if the founder prefers.