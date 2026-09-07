# RECONCILIATION — OSS Research Program: all ecosystem feedback reviewed and the program reconciled

**Date:** 2026-09-07
**Re:** the revisit pass promised in `HANDOFF-OSS-RESEARCH-PROGRAM-REVIEW-REQUEST-2026-09-07.md` §11
**Inputs reviewed:** four ecosystem replies —
- DebateHaus: `/Volumes/4TB-BAD/Halbert/.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` (canonical in their repo; R-DH-1..6 — already folded into packets 02/06 and the anti-pattern list)
- BrightestMinds: `/Volumes/4TB-BAD/BrightestMinds/.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` (R-BM-1..10)
- Halley: `/Volumes/4TB-BAD/HumanAI/LinuxBrain/.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` (R-HY-1..8)
- Haloysius engine: `/Volumes/4TB-BAD/Haloysius/.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` (R-EN-1..15)
**Note on provenance:** the BrightestMinds, Halley, and Haloysius replies were produced by review agents on each app's behalf, grounded in their codebases, marked for founder confirmation. The DebateHaus reply is from their own session. Treat all four as strong evidence; anything the founder overrides is corrected by appending to this doc.
**Deliverable this pass produces:** the resolved memory fork, the universal-vs-Halbert-specific split, the Haloysius handoff (`/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-MEMORY-ENGINE-PROGRAM-2026-09-07.md`), and the reconciled state of all nine packets.

---

## 1. The memory fork is resolved: **A2 at the store level, with Option B's keying, provenance-first ordering**

Three of the four replies independently converged on this, and the fourth's requirement is satisfied by the same change:

- **BrightestMinds** found the engine Consolidator already keys its legacy gate on `access_count >= 3` (`consolidation.py:305,470`) — bare A1 (read-only recall) would starve an existing consumer. Their verdict: A2 with consolidation as the named first consumer.
- **The engine reply** corrects the record (the gate is epistemic-first; `access_count >= 3` is the legacy fallback) and finds **four existing consumers** of recall data (consolidation gate, `_strengthen_frequent`, importance ACCESS_COUNT factor, epistemic access factor) all fed one conflated integer — every one conflating *returned* with *used*. Verdict: **A2**, built with Option B's keying from day one. R-EN-1.
- **Halley** prefers A1 for itself (no telemetry consumer today) but requires that *either* fork re-base the `access_count` consolidation gate in the same change — which the engine's step 3 (consumer rewiring in the same change) does. Halley also confirms the fix must be **store-level**: no Halley path traverses `UnifiedRetriever.retrieve()` at all (their chat path is `PersonaMemorySystem.get_context()` → `store.search()`), so a retriever-level fix would reach zero Halley sessions — upgrading the second-guess doc's guidance to a hard rule (R-EN-2, confirms BM-1).

**Resolved program order** (R-EN-4, ratified by convergence):
1. **Write-time provenance enum** (closed enum replacing the free `source` string; BM-5's set: `user_organic / user_echo / persona_invention / consolidation / correction` + engine-internal `derived`) — first, because it enforces everything downstream. Recall events copy provenance; they never reclassify (R-EN-5).
2. **A2 + loop-stop as one revertible change at `PersonaMemoryStore.search()`**: stop `.access()`-on-search, stop the per-search `_save_to_disk()` (the durability half — every memory search today rewrites the whole persona store non-atomically, an engine-verified hazard), start recording `(claim content hash, query hash, day, retrieval score, provenance)` into a stdlib SQLite table. Fail-soft, never raises into the turn path. Key on a record-time content hash with `source_memory_id` retained as the link — NOT observation IDs (observations don't exist pre-promotion); ambiguous hash collisions fail closed (R-EN-3, R-EN-7).
3. **Rewire the four named consumers in the same change** (named-consumer rule, satisfied before the table exists). Deliberate fate of the two scoring factors: move to consolidation-applied strengthening or remove — never leave them on a frozen counter (the silent-drift failure).
4. **Re-ingestion guard**: fence on injected context, symmetric strip on the summary/extraction paths, and — the engine's sharpest point — **pin the role-filter invariant by test before the LLM extraction exists**: the only thing standing between assistant responses and the store today is a `role == "user"` check inside a `TODO: use LLM` placeholder. Consumers confirm the risk is live: Halley ingests assistant responses into five tiers with no stripping; BrightestMinds has three live lanes.
5. **Option B's ranker inputs** (query diversity, recall-day spread) once 1–4 are in.
6. **Option C (curated core): stays gated**, and its review is the joint coexistence session with Halbert's packet-01 Phase B (R-EN-9) — the engine's budget math (a 500-token core = 12.5% of the default 4000 budget; Halley overrides to 8000; BrightestMinds runs a consumer-owned RAG the engine's budget never sees) means the engine cannot size a core alone.

**Preconditions** (R-EN-6): consumer notice to Halley and BrightestMinds before the A2 change lands, and their call-path confirmations are gates — this is a four-consumer semantics shift, not a cleanup.

## 2. The universal-vs-Halbert-specific split (the founder's question, answered)

**Universal — the Haloysius engine program** (handed off: `HANDOFF-MEMORY-ENGINE-PROGRAM-2026-09-07.md` in the Haloysius repo):

| # | Item | Why universal |
|---|------|---------------|
| U-1 | Provenance enum at write time | The write path is engine-owned; every consumer inherits enforcement |
| U-2 | A2 retrieval-event table + loop-stop at the store | The `.access()` call site is engine-owned; all three products' recall traffic passes it |
| U-3 | Consumer rewiring (consolidation gate, `_strengthen_frequent`, scoring factors) | Same change as U-2 per the named-consumer rule |
| U-4 | Re-ingestion guard (fence + symmetric strip + pinned role-filter test) | The summary/extraction paths are engine-owned; two consumers verified the leak is live |
| U-5 | Atomic persistence for `PersonaMemoryStore` (eventlog pattern) | Engine's own docstring names the disease; cure is in-repo; composes with U-2 (R-EN-14.i) |
| U-6 | Deferred-write session-boundary API (BM-4) | Mechanism engine-side so consumers stop hand-rolling write-at-boundaries |
| U-7 | Reason-code discipline as a written house rule | Zero-cost adoption; already the engine's de-facto convention (`ActionDecision`, attunement tuples) |

**Recorded engine candidates — NOT now, with their lift conditions** (the two-instance rule, honored):
- `IngressDecision`/gate-graph module → after Halbert's packet 02 merges AND DebateHaus adopts the shape; the engine's natural shape is extending `ActionDecision` (which already has `require_approval` — the `ask` axis collapsed into the record) or a pure module beside `warrant.py` (R-EN-10).
- The eval-harness **protocol** (bank invariance, ceiling arm, scorecards) → after Halbert's packet 09 proves instance one; the engine's `crag/evaluator.py` (deterministic, closed vocabularies, no LLM judge) is the gates-first half already built; `scenario/generator.py` is the corpus seam (R-EN-13).
- Scheduler follow-ups: occurrence idempotency + a delivery-vs-run-success status split for `background/scheduler.py` and `temporal/outbound_events.py` (R-EN-14.ii).
- Write-approval staging mechanics (pending queue, fail-closed committed-write detection) → deferred with Option C; reuse `require_approval`'s held-not-refused disposition (R-EN-12).
- Claims-ladder engine slot: `AttunementContext.subject_confidence` — recorded as the plug-in point if claim strength ever gets a second consumer (R-EN-11).

**Halbert-specific — the nine packets, confirmed:** the engine reply confirms packets 01 (Halbert half), 03–09 as app-internal as scoped, with these refinements folded in: packet 02's lattice/claims ladder stay app-side (one consumer; policy config is app-owned per the engine's Protocol-seam design); packet 06's per-call-policy principle is co-signed by both DebateHaus and the engine ("`authorize_action` was shaped for exactly that"); packet 04's speaker-identity question maps onto existing engine slots (no new seam needed); packet 07 confirmed app-internal (the engine must never own a consumer's turn loop — it would invert the boundary).

**Consumer-side residue each app owes itself** (from their own replies, recorded here for cross-visibility):
- **Halley:** wire the built-but-never-wired consolidation auto-watcher; retire the shipped "recalled N memories" returned-count indicator (it is the exact anti-pattern the Hermes-inputs note names); consult `authorize_action` from `ToolRegistry.execute()` (the per-call-policy gap, packet-06's principle in Halley's organ); note the obfuscated frozen fork ships a pre-shim engine (packaged builds get no engine updates); its three anti-patterns are folded into §3.
- **BrightestMinds:** remove the engine preflight's hard-coded BM figure-topic maps (consumer product data in the engine — their own residue); their six anti-patterns folded into §3.
- **DebateHaus:** adopt the `IngressDecision`-shaped gate_graph on the warrant (R-DH-3, their lane, their repo).

## 3. Anti-pattern additions from the replies (fold into the program's list; masters: review-request §8)

From the **engine** (R-EN-15, all code-verified): (16) a read path that rewrites the whole store — read volume coupled to write hazard and crash-corruption window; (17) one signal feeding many consumers with conflated semantics — changing it is a four-system behavior change dressed as a cleanup; (18) an invariant enforced only by placeholder code — it vanishes in the implementation commit; pin it with a test before the LLM pass exists.

From **Halley** (13–15 in their numbering): fail-open baked into an unwritten-policy seam; persona output ingested as ground truth; budget constants nothing enforces.

From **BrightestMinds**: success-reported-without-artifact (their strongest — endorses packet 03's status taxonomy from scar tissue); success-shaped 200-with-error-body from native endpoints; streaming/non-streaming path drift; fail-soft imports hiding dead headline features; concrete-class-instead-of-Protocol assertions; fail-open persistence on the read path.

From **DebateHaus**: already folded (items 11–15 in the review request).

## 4. Packet refinements from the replies (the authoritative post-feedback deltas)

- **Packet 01**: unchanged in scope; Phase B's review checkpoint now has its joint-session partner defined (engine Q5/R-EN-9 — the coexistence session, one decision, recorded in both repos). The engine's signal-table keying (record-time content hash + `source_memory_id` link) is the alignment target; Halbert's `(subject, predicate)` keys converge at claim level per the existing rule.
- **Packet 02**: add to Phase C's task list — the reason-code consumer surfaces must fail **closed** on unwritten policy (Halley's fail-open warning; the lattice's `merge_policies([]) → deny+ask` default is already the right shape — keep it that way at every integration seam).
- **Packet 03**: BrightestMinds endorses the status taxonomy from their own incident scar tissue (success-reported-without-artifact, commits `d7d57a8`/`46623cb`) — no scope change; confidence raised.
- **Packet 06**: founder sign-off still pending; both DebateHaus (R-DH-4) and the engine co-sign the per-call-policy principle with the semantic-gates refinement (already folded).
- **Packet 08**: techniques apply to Halbert's JSON job files too (atomic temp+rename for the scheduler's per-job files — same discipline, add a small task when dispatched); the engine runs the same cure for its JSON store (U-5).
- **Packet 09**: BrightestMinds' H3b capture (headline RAG append dead on the chat path) is offered as the strongest evidence yet for "harness as the permanent gate," and BM adopts the ceiling-arm method — no scope change; the engine protocol-lift candidate is recorded (§2).

## 5. State of the program after reconciliation

- **Dispatch-ready (unchanged; erratum 2026-09-07 per the Fable scope pass):** 01-A, 02-A/B, 03-A (+addendum), 04-A1/B/C1, 05-A/C2, 08, 09-A/B, 07-A. **03-B wires 03-A's modules — it dispatches after 03-A merges, not in parallel** (an earlier line reading "03-A/B" as parallel-ready was stale shorthand; the dispatch matrix §2/§8 is authoritative). **07-A.** **06 pending founder sign-off.**
- **Newly handed off:** the Haloysius engine program (U-1..U-7 + recorded candidates) — `/Volumes/4TB-BAD/Haloysius/.handoff/HANDOFF-MEMORY-ENGINE-PROGRAM-2026-09-07.md` — with the A2 fork resolved by convergence, provenance-first ordering, and the consumer-notice preconditions as gates.
- **Still founder-gated:** packet 06 sign-off; packet 01 Phase B + engine Option C (the joint coexistence session); the engine's Q2 file-vs-query-time sub-question rides with Option C.
- **Reply-doc provenance caveat stands:** three of four replies were agent-produced on each app's behalf; the founder should spot-check them before treating any single file:line claim as load-bearing in a dispatch decision.