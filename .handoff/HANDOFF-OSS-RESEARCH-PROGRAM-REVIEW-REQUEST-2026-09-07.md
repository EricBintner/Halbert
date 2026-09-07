# HANDOFF — OSS Research Program: review request for the ecosystem

**Date:** 2026-09-07
**From:** the Halbert lift-program sessions (OpenClaw + Hermes review passes)
**To:** reviewers across the ecosystem — Halbert core, Haloysius (engine), Halley, DebateHaus/Warrant, and any other app consuming these patterns
**Purpose:** this is the single entry point to the OSS research program. Read this doc first; it indexes and *verbosely summarizes* everything so a reviewer can evaluate the work without having been in the room. **Feedback requested — see §9 and §10 for exactly what we want back and where to put it.**

---

## 1. What happened (the short version)

Over one day, we ran two full OSS pattern-mining reviews, the same way both times: a structural survey of the target repo, then eight parallel deep-dive explorations (each briefed on Halbert's verified current state and asked for learn/lift verdicts with file-level evidence), then a synthesis ranked against Halbert's live workstreams, then implementation packets with tasks, test gates, and stop conditions, and finally a master plan that indexes everything.

- **Target 1: OpenClaw** (`/Volumes/Thunderbolt/AI/openclaw` — the personal AI assistant gateway, TypeScript pnpm monorepo, version 2026.9.2 @ 3f3c5b2ebef). Its architecture case — *"trusted gateway, untrusted execution, deterministic policy"* — is nearly word-for-word Halbert's security posture, which is why so much of it was liftable.
- **Target 2: Hermes Agent** (`/Volumes/Thunderbolt/AI/OSS/hermes-agent` — Nous Research's self-improving agent, Python). The most language-portable target reviewed yet (Python throughout, so lifts are ports). Its incident history is the strongest external argument yet for the deterministic-policy-first directive: every cited incident (#29912, #67140, #61521) is an LLM-judgment path that had to be re-fenced with a deterministic guard after it misbehaved.

Both reviews follow an earlier open-claude-code pass (conversational; no doc produced). The memory findings also produced a decision-document exchange with the Haloysius repo (§6).

**Nothing has been dispatched.** Nine implementation packets exist, dispatch-ready or gated; the program is parked here specifically so the ecosystem can weigh in before execution begins.

---

## 2. Artifact index (everything to read, in recommended order)

All paths absolute; Halbert-repo docs live in `/Volumes/4TB-BAD/Halbert/.handoff/`.

| # | Artifact | What it is | Audience |
|---|----------|-----------|----------|
| 1 | **This doc** | entry point + verbose summary + feedback request | everyone |
| 2 | `/Volumes/4TB-BAD/Halbert/.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` | OpenClaw synthesis (8 deep-dive reports condensed; ranked lifts; anti-patterns) | everyone |
| 3 | `/Volumes/4TB-BAD/Halbert/.handoff/OSS-REVIEW-HERMES-2026-09-07.md` | Hermes synthesis (8 more reports; cross-referenced against OpenClaw) | everyone |
| 4 | `/Volumes/4TB-BAD/Halbert/.handoff/OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md` | the dispatch plan: all nine packets, executor-tier guidance, dependencies, review checkpoints, deep-pass agenda, status log | anyone executing or reviewing packets |
| 5–13 | `OPENCLAW-LIFT-PACKET-01..09-*-2026-09-07.md` (same directory) | the nine implementation packets — each self-contained: verified current-state facts, phased TDD tasks with test code, out-of-scope guards, verification gates, executor gotchas | executors + reviewers of the relevant area |
| 14 | `/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-OPENCLAW-MEMORY-PROMOTION-SECOND-GUESS-2026-09-07.md` | the Haloysius-side decision document: whether the promotion pattern belongs in the engine, Options A/B/C, five founder questions | **Haloysius reviewers especially** |
| 15 | `/Volumes/4TB-BAD/Haloysius/.handoff/HERMES-INPUTS-MEMORY-SECOND-GUESS-2026-09-07.md` | evidence addendum to #14 from the Hermes pass (the A1/A2 fork, re-ingestion half, staging governance) | **Haloysius reviewers especially** |

Per-packet index (for quick navigation):

| Packet | File | One line |
|--------|------|----------|
| 01 | `OPENCLAW-LIFT-PACKET-01-MEMORY-PROMOTION-2026-09-07.md` | Recall-driven promotion signal store + curated always-in-context core for Halbert-owned memory; Phase B gated on the R9 fence |
| 02 | `OPENCLAW-LIFT-PACKET-02-POLICY-LATTICE-2026-09-07.md` | security×ask lattice (guest = capability floor), named-gate ingress decisions with reason codes, identifier-claim strength ladder |
| 03 | `OPENCLAW-LIFT-PACKET-03-SCHEDULER-DURABILITY-2026-09-07.md` | Catch-up, restart budgets, run receipts + Hermes addendum (cadence-scaled grace, occurrence idempotency, monitor-hash gate, status taxonomy) |
| 04 | `OPENCLAW-LIFT-PACKET-04-VOICE-INGRESS-2026-09-07.md` | Typed voice turn ingress (speaker claims — today voice turns default RoleGate to admin), mutation digest, TTS quality rules + Hermes addendum (transcribe-once, echo-back, interrupt-with-transcript) |
| 05 | `OPENCLAW-LIFT-PACKET-05-SECURITY-HARDENING-2026-09-07.md` | Secret variant registry (raw+urlencoded+json-escaped), echo guard, one redaction pipeline, camera-gate assertion + Hermes addendum (display-side redact+cap seam) |
| 06 | `OPENCLAW-LIFT-PACKET-06-SCRIPT-EXECUTION-2026-09-07.md` | `execute_code`: one-turn tool pipelines via generated stub module; per-call policy preserved; **awaiting founder sign-off** |
| 07 | `OPENCLAW-LIFT-PACKET-07-INTERRUPT-ALGEBRA-2026-09-07.md` | stop/steer/redirect as three protocol verbs; generation claims; yield-not-kill |
| 08 | `OPENCLAW-LIFT-PACKET-08-STORE-HARDENING-2026-09-07.md` | darwin fsync PRAGMAs, FTS fail-open contract, declarative column reconciliation |
| 09 | `OPENCLAW-LIFT-PACKET-09-EVAL-HARNESS-2026-09-07.md` | The R5 eval harness (question-bank invariance, ceiling arm, committed scorecards) + the red-seam probe battery + the CRAG verdict contract |

---

## 3. The OpenClaw review — verbose summary

*(Full detail in artifact #2. This section is self-sufficient for review.)*

OpenClaw is a mature multi-channel assistant gateway. We reviewed eight areas: agent runtime/sessions, memory, skills/prompt assembly, security/approvals, channels/routing/multi-user, tools/cron/terminal, gateway/daemon/MCP/lifecycle, models/voice/UI.

### 3.1 Memory (its most transferable subsystem)

The design: plain Markdown files + one SQLite index (FTS5 + sqlite-vec) + a background consolidation pass ("dreaming"), under five stated rules worth adopting verbatim: no hidden state (memory is files you can edit); **writing is the hard part** (they cite LongMemEval that what gets written matters more than how it's indexed); the write path is the security boundary; deterministic gates with model judgment only inside them; **memory failures never eat a turn**.

Structure: a **two-tier model** — a tiny curated core (MEMORY.md/USER.md, ~10KB, always injected) bridged from a lossless episodic tier (daily notes + indexed transcripts, never auto-injected) by **promotion gates only**. The distinctive mechanism: **promotion is recall-driven** — chunks earn durability by being *useful* (recall count, query-hash diversity, multi-day recurrence), not by being written confidently. Consolidation is **plan-based**: the model returns `{action: added|merged|superseded, priorEntries: exact text}` operations; the host validates and applies; any failure falls back to append-only — hallucinated deletions are structurally impossible.

The wiring answers: write at compaction/session boundaries (never per turn; a pre-compaction flush turn guarantees summarization never erases unwritten facts); recall on every turn via a cheap deterministic lexical trigger lane (curated tier only), escalating to a real retrieval agent only on recall-intent phrasing; inject as hidden prepended context, never chat items; guard the recall echo loop (recalled content can never re-enter promotion) from day one. Decay is a ranking multiplier that never deletes; evergreen entries are exempt.

### 3.2 Continuous conversation

The transcript is an **append-only tree**; context is a projection of a path. This is the exact data model for "one continuous conversation with hidden topic threads": each topic thread is a branch, switching topics moves the leaf, and a **branch summary** is computed once, persisted as an entry. Compaction is the most complete portable subsystem in either review: cut points only at turn boundaries, iterative structured summaries that preserve exact file paths and error text, the unresolved user request carried across compaction generations, binary-searched to fit budget. Steering: a two-queue system (mid-run steering + post-run follow-ups) with `inFlight→commit→restore` tri-state so a failed run restores queued messages. Interruption is persisted as transcript facts, not runtime state. Schema versioning: one `PRAGMA user_version` integer, idempotent migration ladder, hard refusal on future-version files.

### 3.3 Security/approvals (the closest match to Halbert's posture)

- The **two-axis lattice**: every policy is `security: deny|allowlist|full` × `ask: off|on-miss|always`; layers merge with **min() over capability and max() over ask** — strictest capability and most prompting always win. Guest becomes a capability floor (`minSecurity(guest, x) == deny`), not a special case.
- **Named-gate ingress decisions**: ordered gates, each producing a record with a reason code; the decision names its decisive gate — every deny is explainable after the fact.
- **Identifier authentication ladder**: `verified > asserted > unverified > mutable` — grades identity *claims*, not names; capability grants declare a minimum floor.
- Durable consents: pending rows persisted before the waiter exists; CAS first-answer-wins; runtime-epoch stamping; allow-once is single-spend; **allow-always only mints when the grant is mechanically re-verifiable later**, else silently downgrades to allow-once. Byte-exact approval bindings (argv + cwd + executable + operand sha256) recomputed at execution; drift → deny. Fail-closed on every failure mode (timeout/no-route/storage-corrupt/authority-closed all become recorded terminal denies).
- MCP: one policy pipeline shared across internal and MCP surfaces (no bypass path); order-stable sanitized tool names; guest-value ownership transfer via WeakMap so sensitive values never serialize into model-visible content; secret sentinels + egress proxy with per-secret destination allowlists; the redaction registry registers the exact value **plus URL-encoded and JSON-escaped forms** (the leak class plain-value redaction misses).

### 3.4 Scheduler/heartbeat

Heartbeat IS a declaratively-reconciled cron job (system-owned jobs the agent can't edit). The **NO_REPLY/HEARTBEAT_OK token protocol** with every model failure mode documented; a **zero-token idle short-circuit** (empty scratch buffer → the LLM call is skipped entirely); single re-armed timer with minute-cadence safety wakes; run reservations persisted before execution; bounded/staggered/deferrable startup catch-up; agent-proposed next-run delay, clamped; wake **settlements** (scheduled work awaits its terminal result).

### 3.5 Channels/multi-user (the guest-persona material)

Access groups as named indirection in allowlists with structured resolution states (`referenced/matched/missing/unsupported/failed` — deny reasons are diagnosable); pairing as challenge codes with TTL'd pending state and a `pairing-required` middle admission state (deny → onboarding is one state machine); admission evidence as unforgeable one-shot carriers for audit; session-key grammar with `identityLinks` (same human over several channels → one session); golden **wire-trace testing** for channel delivery; pre-crypto resource guards (shape/size/skew/rate limits before expensive work, overrides can only tighten).

### 3.6 Voice

Speech reaches the agent **only through a typed consult tool** — no implicit transcript side-channel exists to forget to wire (Halbert's past defect becomes structurally impossible). Durable voice-session records with a **mutation digest** of what the agent changed during a call. Fast-context shortcut (bounded memory search before any agent run). "Speak exactly this" replay authorized by host-owned retained state, never a model-emitted marker.

### 3.7 Skills

SKILL.md format **byte-compatible with Claude Code's by design** (ecosystem skill packs ingestible by matching the `<available_skills>` catalog shape); a binary-search truncation ladder with names/locations as an uncut identity floor; capability gating via frontmatter `requires` probed against the live host; a stable-prefix/cache-boundary split in prompt assembly; content security scanning + boundary-safe reads; **custodian skills** (dangerous ops runbooks hidden from user-facing agents by discovery scoping, with a mandatory live "Prove" step).

### 3.8 Models/UI

Primary/Utility/Fallback slot trio with model-agnostic quality dials (thinking level, fast mode) remapped per-model behind the scenes — the concrete shape for the providers-only picker; declarative provider manifests with `status: deprecated → replacedBy` lifecycles; remote catalog overlays that can never change endpoints/headers; model selection as a transaction with a `conflict` result status.

### 3.9 Watchdog/lifecycle (noted, not packeted)

Close-code 1013 "gateway starting, retry in X ms"; watchdog clamped to the server's own declared deadline; crash-loop restart budgets (max 10/hour + cooldowns + clock-rollback test); detached restart handoff with PID-wait and a durable restart log; staged shutdown drains with per-step budgets.

---

## 4. The Hermes review — verbose summary

*(Full detail in artifact #3.)*

Eight areas: state machinery, learning loop/skills, memory/user modeling, gateway/channels, cron, subagents/script-RPC/terminals, MCP/providers/TUI, evals/batch/datagen.

### 4.1 State machinery (the session tree, pre-solved)

Hermes is what Halbert's conversation store looks like after ~4 years of production incidents, each leaving a comment with its issue number. The compression rotation is exactly the planned append-only tree: **`publish_compression_child`** — one transaction closes the parent, publishes the summary child, and stamps the parent (readers never see an ended parent with a missing child), with a **watermark** so messages arriving *during* the slow summarization are column-cloned into the child. **Turn leases key on the lineage root**, so turns can't interleave across rotations. Anti-thrash counters are persisted on the session row, not in-process. Cheap permanent wins: **darwin durability PRAGMAs** (`checkpoint_fullfsync=1`, forced `synchronous=FULL` — Apple's fsync guarantees neither ordering nor landing, and a shutdown was observed corrupting "durable" checkpoints); the **FTS fail-open contract** (breadcrumb + trigger-drop atomically; a corrupt derived index never blocks canonical writes; nobody reinstalls triggers over an unknown gap); **declarative column reconciliation** from one SCHEMA_SQL source (kills the skipped-migration class); repair on a scratch copy promoted via the online backup API with a fingerprinted attempt ledger; title provenance as a derived<llm<user CAS in storage.

### 4.2 The learning loop (for the skills deep pass)

Triggers are **deterministic counters** (≥10 tool iterations → skill review; 10 user turns without a memory write → memory review; reset on actual use; rehydrated from history on restart). The review runs **post-delivery on a background fork** sharing the parent's cache, under a **dispatch-side tool whitelist** (advertised tools stay byte-identical), auto-denying dangerous commands, cancellable by any live turn. The prompt policy is the real IP: an **anti-hoarding doctrine** — never capture environment-dependent failures, transient errors, negative tool claims ("these harden into refusals the agent cites against itself for months"), or unresolved failures; patch-this-session's-skill-first preference ladder; frustration is a first-class signal. Guards: read-before-write enforced per-fork (transcript quoting doesn't count), `created_by: agent` provenance sidecar (never inferred from location), pins (autonomous pin blocks all writes; foreground pin blocks only deletes), **archive-not-delete** with tarball rollback before any mutating pass, and a delete guard requiring an `absorbed_into=` forwarding target after the LLM archived active clusters with zero verified consolidations (#29912). A calibrated linter turns hoarding into machine checks. Noted gap we'd fix: Hermes's skill format has a "## Verification" section but nothing executes it.

### 4.3 Memory (the input that matters for Haloysius)

Hermes is the **existence proof that rich recall works with no retrieval-driven strengthening at all**: FTS5 session search is stateless BM25 with no write-back; external-provider reads are read-only; built-in memory is wholesale-injected so no per-item ranking loop is even possible. Ranking pathologies are fixed with deterministic rules over source **metadata** (cron sessions demoted below interactive ones — "recall blindness"; current-session hits suppressed while still in context). Where Hermes records usage, it's the "used" hierarchy: the skill ledger records actual invocations and a deterministic curator consumes them — **event tables only with a named consumer.** Claim-identity is structurally forced (content-substring addressing, ambiguous-match rejection; corrections supersede by writing a new claim). `write_approval` staging governs who may auto-write the always-injected core (auto-writes staged to a pending queue, replayed on approval, fail-closed committed-write detection). And the loop-breaker the second-guess doc missed: **sanitize in both directions** — recalled context stripped from outgoing sync so retrieval can never re-ingest its own output.

### 4.4 Gateway/channels

Per-platform session keys with **opt-in cross-channel continuity** via an IDOR-proof `/resume` (the DB row must prove platform+thread+chat+user match; legacy NULL rows fail closed). The **turn lease keyed by transcript-owner, not route** (resume makes route→session many-to-one). A durable **delivery-obligation ledger** (pending→attempting→delivered/failed, with differentiated, honest "♻️ may be a duplicate" markers per crash state). Two-axis permissions (who may talk vs. who may run which commands). Voice-memo discipline: STT-eligible vs file-audio classification, transcribe-once cached on the event, echo-back for live verification, **interrupt-with-transcript**, duplicate suppression. `TeeTransport` gives a second client the TUI's event stream for free.

### 4.5 Cron (upgrades the scheduler packet)

Grace **scaled to cadence** (half the period, clamped [120s, 2h]); beyond grace → fast-forward (fire once now, persist `next_run_at` at dispatch time under the lock); one-shots past grace retire with a diagnostic; **occurrence-level idempotency** (a completed scheduled instant can never fire again); the **monitor-hash gate** (cheap probe hashed each tick; unchanged → the agent run is suppressed entirely; changed → a capped diff is injected); closed status set `ok/error/delivery_failed/blocked_config` (run success ≠ user notified); fail-before-spend preflight; fresh-session-per-fire with continuity via per-job KV notepads + `context_from` chaining; inactivity-based timeouts; consent-first self-scheduling (a capped suggestion queue; nothing auto-creates); incident signature-dedup for alert fatigue. Anti-pattern: don't pay the hand-edited-JSON repair tax.

### 4.6 Subagents / zero-context script execution / terminals

The **`execute_code` pattern**: the model writes one Python script; a **generated stub module** (compiled per-run from the enabled-tool intersection — a disabled tool physically doesn't exist in it) calls real agent tools over RPC (UDS locally; atomic-rename file pairs over any remote execute channel); only capped stdout returns to context with a digest-keyed spill file and a read-pointer. Enforcement host-side in one function: constant-time token, frozenset allow-list, mutable budget (refusals are free). Background delegation results **re-enter as a new turn, never mid-turn**, backed by a durable SQLite ledger with bounded replay age. Progress-based staleness (idle-450s/same-tool-1200s) instead of wall-clock — "heavy work must never be killed for taking long." Session-scoped containers with orphan reapers. Do-not-copy: in-process subagent isolation; Hermes's admission that scripts can `os.system` past tool guards — our packet 06 fixes this by dispatching stub calls through the standard `ToolExecutor` policy pipeline.

### 4.7 MCP / providers / TUI

**ProviderProfile**: a dataclass + hooks where every vendor quirk is a documented overridable hook, not a boolean; the **utility slot resolves from the provider's own catalog** (hardcoded cheap-model IDs rot). Cost accounting with `estimated` vs `actual` + `pricing_version`. A **display-side redact+cap seam** on every UI transport emission (the cap is an OOM defense — unbounded output killed the TUI parent, #34095). MCP as server is thin — the approval-respond tool pops an in-memory dict with no enforcement path (do-not-copy); as a client, a PR-reviewed manifest catalog with dual-gate validation (save time AND spawn time). The **interrupt algebra** (best single finding): stop (generation-claimed so a lost race declines), steer (appended to the last tool result, never interrupts), redirect (cancels only the model request; degrades to steer mid-tool with a **yield-not-kill** rule); one shared lock so a stop can't become a retry.

### 4.8 Evals (two open Halbert problems get blueprints)

The **compaction eval** is the blueprint for the R5 gate: question banks generated from the region-to-be-destroyed, cached by content hash (every arm answers the identical exam); closed-book answering with forced "NOT IN CONTEXT"; a judge that sees gold and scores hedged guesses as partial; a **ceiling control arm** (without it a score is meaningless — 96.7% uncompacted vs 45.8% shipped was only visible because the control existed); committed dated scorecards with methodology caveats; sentinel tripwire tests; synthetic transcripts so the harness smoke-tests in CI without LLMs; **"harness as the permanent gate."** The **postmortem probe battery** is the answer to the red seams: reviewer-authored defect reproductions as standalone scripts, pass = exit 0 + expected stdout marker, a PROBES table, no framework. `judge_goal` supplies the CRAG structure: **deterministic gates short-circuit the LLM judge**, a closed verdict vocabulary with structured wait directives, anti-self-congratulation prompt language, parse-failure vs transport-failure circuit breakers.

---

## 5. Cross-referenced verdicts

**Confirmed by both projects (highest confidence — adopt):**
- SKILL.md/agentskills.io format compatibility + a 60-char description discipline (Hermes hard-rejects over-budget descriptions at create time).
- Challenge-code pairing with TTL/caps (Hermes adds NIST-style lockout and "default ignore, not pair" once any allowlist exists).
- Silent-reply token suppression for unattended turns.
- Run receipts where "interrupted/unknown" requires proof the owner died, never a timeout guess.
- Incident-deduped failure alerting (signature grouping, ack, changed-error-mints-new-incident).
- Background/post-turn writes never touch the live prompt (frozen snapshots for cache stability).
- Session search never returns what's already in live context.

**Contradictory (a real fork for the ecosystem to weigh):**
- **Memory:** OpenClaw = signal stores + recall-driven promotion; Hermes = no retrieval strengthening at all, deterministic rules over source metadata. **Both reject what Haloysius does today** (`.access()` strengthening on every search result). The decision doc (§6) now frames this as A1 vs A2.
- **Curated core:** OpenClaw re-renders per turn with budget compaction; Hermes freezes per session (cache-stable, but long sessions drift against stale memory).

---

## 6. The memory decision trail (for Haloysius reviewers especially)

Read artifacts #14 and #15 together. The state of the question:

1. The **second-guess doc** (Haloysius repo) re-examined the first-pass "Haloysius has 70% of the pattern" claim and found it misleading: Haloysius has the *consumption* side (importance/epistemic scoring can use signals) but the *production* side (recording what was recalled, with what query, on what day, with what provenance) is greenfield. It identified a **pre-existing feedback loop** — `PersonaMemoryStore.search()` calls `.access()` on every result, strengthening +0.05, which raises retrieval odds, which strengthens again — and recommends: **Option A** (fix the loop: retrieval events in a table instead of strengthen-on-retrieval) → **Option B** (claim-keyed signal store + query diversity) → **Option C** (curated core injection — founder review required). It also ruled promotion should be **claim-keyed (observation content hashes), not memory-ID-keyed**, and posed five open founder questions.
2. The **Hermes-inputs note** (same repo, artifact #15) adds from the Hermes review:
   - The `.access()` fix forks into **A1: read-only recall** (simplest possible; Hermes's shape — recall never mutates the store; strengthening only at consolidation) vs **A2: retrieval-event table** (preserves recall telemetry for the eval harness and future promotion, at the cost of a table + recording discipline). The deciding question: does Haloysius need recall *telemetry*? If yes A2; if no A1.
   - The loop has a **second half**: re-ingestion. If any pipeline ingests assistant responses into the stores (or embeds them), recalled content re-enters as new observations regardless of the `.access()` fix — the write path needs symmetric stripping/marking (Hermes's sanitize-in-both-directions), which also argues for provenance classification at write time (second-guess question 4).
   - **Write-approval staging** (Hermes's `memory.write_approval`: background auto-writes staged to a pending queue with summary/diff/provenance, replayed on approval, fail-closed committed-write detection) is the governance shape for Option C's "who may auto-write the always-injected core."
   - Do-not-build: a "recalled N memories" indicator that counts *returned* items (conflates returned/used); telemetry living solely inside an external engine (Hermes keeps its skill ledger local for auditability).
3. **Halbert-side alignment** (already binding in the master plan): Halbert's packet 01 keys promotion signals on `(subject, predicate)` ledger keys — claim-shaped — and its Phase B (curated core) review must answer the coexistence question so two curated cores can never double-inject the same claim.

---

## 7. The lift program (nine packets, state of play)

*(Full detail in the master plan, artifact #4, and each packet file.)*

**OpenClaw-derived (01–05):**
1. **Memory promotion + curated core** — the Halbert-owned half of the memory design; Phase A (signal store + wiring at the two live recall sites) ready; Phase B (curated core behind the R9 fence) gated on review including the frozen-vs-per-turn question and the Haloysius coexistence question.
2. **Policy lattice + named-gate decisions + claims ladder** — the mechanism layer for the unimplemented five-axis permission design (`PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` has no code; ceiling/affordance/os_grant/halt don't exist). Does not rewrite the working guest allowlist; pins the lattice to it with a parity test.
3. **Scheduler durability** (+ Hermes addendum) — cadence-scaled grace, dispatch-time persistence, occurrence idempotency, monitor-hash gate, restart budgets with clock-rollback hold, simplified run receipts, closed status taxonomy. The prompted-heartbeat question is recorded as a founder decision with both projects' ground rules attached (notably, Hermes ships **no prompted heartbeat at all** — durable receipts + a status enum deliver "are my automations alive" without an LLM).
4. **Typed voice ingress** (+ Hermes addendum) — closes a verified gap (voice turns arrive with no speaker_role and RoleGate defaults them to admin), the per-turn mutation digest, TTS quality rules, and the voice-memo discipline.
5. **Redaction hardening** (+ Hermes addendum) — variant registry, echo guard, parity-pinned single redaction core, camera-gate registration assertion, display-side redact+cap seam. Pre-flights against the unmerged sec branch.

**Hermes-derived (06–09):**
6. **Zero-context script execution** — `execute_code` with generated stubs; the one deliberate improvement over Hermes: stub calls dispatch through `ToolExecutor.execute()` so **per-call policy is preserved** (Hermes documents that raw scripts can shell past tool guards; we don't accept that). **Awaiting founder sign-off as a new capability surface.**
7. **Interrupt algebra** — the three verbs with generation claims and yield-not-kill; Phase A pure, Phase B verify-first into the state machine.
8. **Store hardening** — darwin PRAGMAs, FTS fail-open, declarative column reconciliation. Small, permanent, and the foundation the session-tree migration will stand on. **Best first packet for a smaller executor.**
9. **R5 harness + probe battery** — builds the instrument while the Consolidator LLM gate stays closed; its first scorecard (deterministic baseline + ceiling arm) is the founder's evidence for opening the gate. Also the CRAG gates-before-judge contract.

**Deliberately un-packeted (deep-pass agenda, ranked):** memory follow-through; the session-tree migration (pre-solved by Hermes's rotation machinery; needs its own brainstorming pass); the five-axis permission-system implementation; voice RoleGate enforcement; the skills system (now carrying the Hermes learning-loop skeleton); watchdog/daemon (when that workstream is scheduled); channel design (per-channel session keys, IDOR-proof cross-surface resume, delivery-obligation ledger, TeeTransport).

---

## 8. Anti-patterns we have committed to refusing (from both reviews)

1. LLM judgment on security paths without deterministic guards — both projects' incident histories say: start with the guards.
2. Env-var allowlists / first-writer-wins config bridges as a security source of truth.
3. Approval-shaped wire tools with no enforcement path.
4. Inline shell expansion during prompt/skill preprocessing (prompt-to-RCE).
5. Hand-edited stores whose read paths become eternal repair passes; and **hand-written invariants docs** (Hermes's own cron AGENTS.md contradicts its code — generate invariants from tests or they lie).
6. In-process subagent isolation for security-relevant work.
7. Regex-parsing your own rendered prompt (structured snapshots; render late).
8. Cache-parity agent forks as the implementation shape for background work (first-class queued jobs instead).
9. Size-budget module splits (module boundaries follow linter rules, not domain boundaries).
10. The implicit "no approvers configured → anyone may approve" fallback (guest persona must have no analog).

**Additions from DebateHaus feedback (2026-09-07, R-DH-5)** — named forms of existing entries, recorded because a future reviewer recognizes the concrete shape faster than the abstract rule:

11. Applying consent-shaped suppression to speech whose legitimacy does not depend on being welcome now (a consent gate is a security path; an authority-bearing voice needs a deterministic bypass or it is silenceable by the very speech it moderates).
12. Unilateral speech-origin revocation of a jointly-negotiated role (the inverse of #10 — "anyone may revoke by speech"; the defect is invisible: the moderator silently stops moderating).
13. Fail-closed on the wrong axis in an adversarial multi-party room — fail-closed on consent when parties have opposed interests silences the referee; fail-closed belongs on the authority axis when the two diverge.
14. A voice with authority and no ambient channel will either interrupt or be invisible (surface taxonomy PUSH/AMBIENT/PULL is the fix; authority needs a channel that is not interruption).
15. An unidentified speaker treated as an identified speaker is a silent authority escalation (the claims ladder's `MUTABLE` floor is the guard; the same refusal as "authority is derived, not asserted," applied to identity).

---

## 9. What we want feedback on (by reviewer)

**Halbert core maintainers:**
- Packet accuracy: every packet embeds "verified current state" facts from a 2026-09-07 state mapping — flag anything stale or wrong before dispatch (especially packet 04's voice-path claims, packet 07's unmapped abort paths, and packet 09's assumption that `recall_eval.py`/`corpus.py` can be extended).
- The dispatch set: are 06–09 the right four Hermes packets, or is something in the synthesis (artifact #3 §"Ranked verdict") under-prioritized? The zero-context script tool (06) especially needs a security ruling: is `execute_code`-with-per-call-policy acceptable as a capability surface?
- The R9 fence question (packet 01 Phase B): is a deterministic curated core an acceptable second injection path, and frozen-per-session vs re-rendered-per-turn?

**Haloysius (engine) reviewers:**
- The full decision trail in §6 / artifacts #14–15: A1 vs A2, the re-ingestion half, provenance at write time, claim-keyed signals, and the five open founder questions in the second-guess doc. Does the engine agree with "event tables only with a named consumer"? Does the `UnifiedRetriever` budget math change the curated-core calculus?

**Halley reviewers:**
- The second-guess doc's fourth verdict applies to you: the re-export shims propagate *code*, not *behavior* — the 8000-vs-4000 token budget changes what a curated core crowds out, and the call path through `halley_backend.py`/`retrieval_adapter.py` needs verifying before any claim of automatic propagation. Please verify your call path and report; nothing in the proposed work should be merged without that verification.

**DebateHaus / Warrant reviewers:**
- Packet 02's lattice and named-gate decisions are the reference instance of the voice-vs-authority axis the Warrant work built on (`authority-axis-warrant`). Specifically: does the `security × ask` min/max merge express "by what authority" adequately for the moderator app's needs? Is the identifier-authentication ladder (claim strength, never name tiers) consistent with Warrant's model of authority? Would you consume `IngressDecision` reason codes directly?
- Packet 06's per-call-policy principle (the stub calls back through the standard executor) is a generalizable rule for any app exposing agent tools to scripts — worth a look from your side too.

**All reviewers:** the anti-pattern list in §8 — anything you'd add from your own incidents?

## 10. How to give feedback

- **Primary:** write a response doc in your own repo's `.handoff/` named `REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md`, structured by the sections above (or free-form). Reference docs by artifact number (§2) and packet number.
- **Alternatively:** propose in-place edits to any of the packet or review docs; treat them as living documents until the first dispatch happens.
- **For founder decisions:** the parked questions are enumerated in the master plan §"Review checkpoints" and the Haloysius second-guess §"Open questions" — flag which you want pulled into a decision session.
- **Deadline/cadence:** none imposed — the program is parked until you've weighed in; we'll re-run a revisit pass after feedback lands and reconcile the packets before anything dispatches.

## 11. Process notes for the revisit pass

When feedback arrives, the revisit will: (1) reconcile each packet against its replies; (2) re-verify any "current state" claims older than ~2 weeks (the state mapping is dated — the codebase moves, concurrent sessions edit the repo); (3) re-rank the dispatch order; (4) resolve the A1/A2 memory fork and the 06 sign-off; (5) update the master plan status log and this doc. The two synthesis docs (artifacts #2, #3) are point-in-time research records — corrections to *those* go in reply docs, not rewrites; packets and the master plan are the living layer.