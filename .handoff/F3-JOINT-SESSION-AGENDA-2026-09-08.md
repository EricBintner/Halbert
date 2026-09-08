# F-3 Joint Session Agenda — the curated-core coexistence ruling (Halbert 01-B × Haloysius Option C)

**Date:** 2026-09-07 (session date TBD by founder)
**Attendees:** founder; Halbert session (fable); Haloysius engine session (med)
**Reads in evidence:** Halbert `.handoff/OPENCLAW-LIFT-PACKET-01-MEMORY-PROMOTION-2026-09-07.md` (Phase B + Phase C-3); Haloysius `.handoff/HANDOFF-MEMORY-ENGINE-PROGRAM-2026-09-07.md` (§Phase 5, EN-5 addendum); Haloysius `.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` (§1.6, Q2/Q5, R-EN-8/9/12); Halbert `.handoff/DESIGN-SESSION-TREE-AND-COMPACTION-2026-09-07.md` (§2.4, §7 F-3 items); BrightestMinds `.handoff/REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md` (R-BM-3).

## Purpose

Two curated always-in-context cores are now on adjacent gates: Halbert's packet 01 Phase B (a deterministic `## What I remember` block, the only sanctioned new injection into the agent prompt) and the Haloysius engine's Option C (a fifth always-present `ContextBuilder` source). Every upstream document agrees neither repo can rule alone — the engine reply §1.6 shows the budget competition includes sources outside engine accounting, and packet 01 Phase C-3 rules the cores must never double-inject one claim. This session decides whether and how they coexist, at what cost to each side's context budget, in what assembly shape, under whose write authority, and in what build order. **One decision, recorded in both repos:** whatever the founder rules lands as a DECISIONS entry in Halbert and a handoff amendment in Haloysius, same wording, same date. No code is opened, scheduled, or promised beyond this session.

**Verified convergence to lean on (do not re-litigate):** both sides are already claim-keyed. Halbert's `halbert_core/halbert_core/continuity/promotion.py` keys signals on `PromotionKey = (subject, predicate)` ledger claim keys — the code comment states "claim-shaped on purpose… never a memory-row id." The engine's `src/haloysius/memory_v2/recall_events.py` keys on `recall_claim_hash = sha256(content.strip().lower())[:16]` (the same normalization as `ObservationStore.content_hash`), with `source_memory_id` as link and fail-closed collision handling. The binding rule going in: **no third keying scheme is introduced by anything this session approves.**

---

## R1 — Do the two cores coexist at all?

**Question:** Ship both curated cores, defer one, or cut one permanently?

**Evidence on the table:**
- Packet 01 Phase C-3 (the binding alignment note): Halbert's core and the engine's (if Option C is ever approved) "must not double-inject the same claims into a prompt."
- Engine reply Q5 / R-EN-9: Option C is inherently cross-repo; a joint session with one decision recorded in both repos.
- BM R-BM-3: the question is bigger than two cores — BrightestMinds already runs five-plus always-injected deterministic lanes; the engine-side answer is "a composition contract, not another lane."
- D-1 §2.4: three layers (transcript projection, curated core, RAG/world) with the rule that compaction can never write the core, and the ready-made guard: a claim sourced from a thread on the current projection path is elided from the core for that turn.

**Options:** (a) coexist with a claim-level dedup guard on both sides; (b) Halbert-only (engine Option C shelved until a second consumer needs it); (c) neither (both stay gated).

**Recommendation: (a).** Both signal stores exist and are claim-keyed; the dedup rule is deterministic (`claim on path → elided`), not judgment; and BM R-BM-3's composition-contract point is satisfied by ruling that any future always-injected lane — wherever it lives — must register its claims at the same choke point rather than adding a parallel block.

**Decision line:** *"Both cores may exist. One claim is injected at most once per prompt, resolved deterministically on the claim key; every always-injected lane, present or future, registers through that guard."*

## R2 — The budget split: who pays for always-injected context?

**Question:** A ~500-token core is 12.5% of the engine's 4000-token default before any retrieval happens. Who pays, and how much?

**Evidence on the table:**
- Engine reply §1.6: `ContextBuilder.build()` first-fits by priority until the 4000 default is exhausted; a core is a fifth always-present source at CRITICAL/HIGH. Halley subclasses to 8000 (halving the share). BM's consumer-owned RAG (R-BM-3) is invisible to the engine budget — "the engine cannot size a curated core on its own."
- Halbert side: D-1 §7 F-3 item 1 — the curated core rides `messages[0]` with the identity/receipt block, and the count-then-clip cap (`assembler` :889) needs a two-tenant budget: the path-receipt block and the curated core share one ceiling.

**Options:** (a) fixed per-side caps (Halbert: explicit split of the `messages[0]` cap; engine: fixed share of `max_context_tokens`); (b) engine-agnostic percentage contract consumers override (Halley's 8000 override already does this implicitly); (c) no caps yet, measure first.

**Recommendation: (a) + (b) combined.** Halbert: rule the two-tenant `messages[0]` budget explicitly (receipt first, core second, both capped) — it is Halbert's cap to split and needs no engine change. Engine: a budget-share contract — core capped at ~12.5% of `max_context_tokens` (≈500 tokens at the default), explicitly overridable per consumer. BM's lanes stay consumer-owned but must be enumerated in the consumer's composition contract (R-BM-3).

**Decision line:** *"Always-injected memory pays rent from a named cap on each side — the `messages[0]` two-tenant split in Halbert, a ~12.5% budget share with consumer override in the engine — and no lane is exempt from enumeration."*

## R3 — Query-time assembly vs frozen-per-session vs file-as-authority

**Question:** Is the core assembled fresh per turn from the ranked claim store, frozen once per session, or a human-editable file that is the authority?

**Evidence on the table:**
- Engine Q2 / R-EN-8: recommend query-time assembly (ranked `get_active()` under a CRITICAL/HIGH section, budget-capped by the existing `ContextBuilder`) plus a materialized read-only inspection artifact per persona. File-as-authority drags in write-approval staging and conflict resolution against the ranker — a real founder sub-decision, not a default.
- D-1 §7 F-3 item 2 (the new vote): the projection is positionally stable (entries are rows) but the receipt block at `messages[0]` mutates on every leaf move — prefix cache at `messages[0]` is busted either way; the frozen-snapshot argument loses and per-turn rendering is strengthened.
- BM R-BM-3: no strong opinion; re-renders per turn with byte-stable goldens by construction; "defer to the heavier consumer" (Halbert).

**Options:** (a) query-time assembly + read-only materialized dump; (b) frozen snapshot minted at session start; (c) file-as-authority with staging.

**Recommendation: (a).** Both independent lines of evidence (engine Q2, D-1's cache-stability observation) land on query-time. File-as-authority (c) is explicitly *not* rejected — it is parked as a founder sub-decision that imports R4 whole.

**Decision line:** *"The core is assembled fresh each turn from the ranked claim store, budget-capped, with a read-only materialized artifact for inspection; a human-editable file of authority is a separate founder decision, not a default."*

## R4 — Write-approval staging: adopt Hermes's shape, where, and when?

**Question:** If background machinery proposes writes to an always-injected core, who may auto-write? Adopt Hermes's `memory.write_approval` shape (pending queue, summary/diff/provenance, fail-closed committed-write detection) for both sides, Halbert-only, or neither yet?

**Evidence on the table:**
- Engine R-EN-12: staging is store-level machinery the engine should own if Option C is approved — pending queue, fail-closed committed-write detection, staged artifact format — reusing `ActionDecision.require_approval`'s held-not-refused disposition ("staged ≠ denied"); the approval UX is consumer-side. Design-now, build-later, attached to the Option C gate.
- Packet 01 Phase B: Halbert's core is built with promotion-gate-only writes — deterministic, no background auto-writes exist to stage yet.
- R3's parked sub-decision: file-as-authority makes staging mandatory.

**Options:** (a) record the shared shape (engine mechanics / consumer UX per R-EN-12) as binding for both, build neither until a core has auto-writes to stage; (b) Halbert builds staging now; (c) defer the question entirely.

**Recommendation: (a).** Today neither core has a background writer — the promotion gates are deterministic and the LLM consolidation stays gated — so there is nothing to stage. But the division of ownership should be ruled now so neither side later invents a parallel shape: engine owns store mechanics, consumer owns approval flow, `require_approval` is the disposition model.

**Decision line:** *"Staging is ruled, not built: the engine owns the pending-queue mechanics reusing held-not-refused, the consumer owns approval UX; neither side builds it until an auto-writer exists."*

## R5 — Build order

**Question:** If R1–R4 are approved, which side builds first, and what gates the other?

**Evidence on the table:**
- Halbert: packet 01 Phase A (signal store + persistence + two wiring sites) is merged on main — `continuity/promotion.py` exists. Phase B is gated on the R9-fence review with a DECISIONS.md entry in the same commit, and edits both fence comment sites (`context/adapters.py`, `routes/agent.py:164-166`).
- Engine: Phases 1–4 authorized and largely built (EN-2/EN-3 delivered `recall_events` + `claim_recurrence` and all four consumer rewires; EN-5's residues live unmerged on `feat/engine-en5-optionb` @ e9c4a88). Phase 5.2 (Option C) is gated on this session.
- D-1 §7 F-3 items 3–4: confirm the four signal sites (auto-recall admit, `recall_memory` results, thread-close events, compaction boundaries) as one set so the promotion schema ships once; packet 08 merges before D-1's T1.

**Recommendation:** **Halbert builds first.** Phase B proceeds immediately post-session (its fence review is this session's R1–R3 in effect; the DECISIONS entry records them). Engine Option C proceeds second, behind one gate: Halbert's core live on the founder's machine with measured budget behavior (the dogfood posture — the founder's machine is the test corpus). Rationale: Halbert's core has the narrower blast radius (one consumer, its own `messages[0]` cap), its guard rule (path elision) is already specified by D-1, and the engine's sizing depends on seeing a real core's cost (§1.6's "cannot size alone"). Engine staging machinery (R4) builds last, only when an auto-writer exists.

**Decision line:** *"Halbert's Phase B ships first under the ruled budget split; the engine's Option C is approved-in-principle and gated on Halbert's core being live and measured; staging builds when an auto-writer exists."*

---

## Post-session dispatch checklist

**Halbert executor (packet 01 Phase B) needs:**
1. The R1–R5 decision lines, verbatim, for the DECISIONS.md entry that rides the fence-edit commit.
2. The ruled `messages[0]` two-tenant split (receipt/core cap numbers from R2).
3. The elision rule spec (claims sourced from the current projection path are elided; keyed on `(subject, predicate)`).
4. The four-signal-site set confirmed (two existing + thread-close + compaction-boundary; the last two are no-ops until D-1's T1/T3 land and packet 08 precedes T1).
5. The planned file list already in packet 01 Phase B (`continuity/curated.py`, assembler `curated` tier, `adapters.py` fence-comment rewrite, tests) — unchanged by this session if R1/R3 recommend as above.

**Engine executor needs:**
1. The R1 coexistence rule and claim keying (no third scheme; `recall_claim_hash` stands).
2. The R2 budget-share contract (~12.5% of `max_context_tokens`, consumer-overridable) and the consumer-notice obligation to Halley and BrightestMinds when Option C builds.
3. The R3 shape: query-time assembly over `claim_recurrence` ranking + materialized read-only per-persona artifact.
4. The R4 disposition: no staging build; `require_approval` reuse recorded for when it comes.
5. The gate: wait for Halbert's core live-and-measured before opening Option C implementation.
6. Housekeeping: decide the fate of `feat/engine-en5-optionb` @ e9c4a88 (EN-5's memory-pipeline residue + documented decay semantics) separately — it is not part of this session's rulings.

---

## Opening paragraph (founder reads)

> We are here because two repos independently arrived at the same small idea — a tiny, always-present block of memory that earned its place by being recalled, not by being written confidently — and every reviewer told us neither repo may rule it alone. The stores are already aligned: both key on claims, and nothing today proposes a third keying. What is not aligned is the prompt: one claim can only be said once, context budgets are finite and partly invisible to each other, and we have three honest answers for how the block is assembled and who may write it. Five questions, five decisions, one record kept in both repos. When we leave this room, Halbert's Phase B has its fence review done, the engine knows its gate, and both executors can start tomorrow morning.
