# Cross-Session Continuity — Design Strategies

**Date:** 2026-08-26
**Status:** Design research. No implementation. No plan tasks created.
> **SUPERSEDED IN PART (same day).** `CONTINUITY-MECHANISM-AUDIT-2026-08-26.md` verified
> these mechanisms by execution and found that `haloysius.memory_v2` — already installed and
> working — provides supersession, decay, consolidation, importance scoring and semantic
> dedup, of which Halbert wires 4 of 58 capabilities. **§4.3 and §7.3 N3 below are superseded**
> by that audit's finding F4. Read the audit alongside this document.

**Companion to:** `CROSS-SESSION-CONTINUITY-RESEARCH-2026-08-26.md` (the foundational
research). That document surveys the landscape and proposes an architecture; this one
verifies its claims against the repo, resolves the design tensions it leaves open, and
answers the sequencing question: *what must land before this can begin, and what must not
wait.*

Every `file:line` below was verified against the working tree on 2026-08-26.

---

## 0. The four things that matter

1. **Halbert does not lack a continuity system. It has eight stores and no owner.** The
   foundational research reads as greenfield; the repo has eight live memory/state stores
   plus 63 `.handoff/` documents. A ninth store would make bleeding worse, not better. §2

2. **Plan A already builds most of the proposed architecture, under different names.**
   Receipts are the structured handoff artifact. `detected_domains` is the domain tag.
   "Deterministic recall on strong match, no model call" is "no LLM in the read path."
   Roughly two thirds of §10 of the foundational research is approved, planned, and
   executing right now. §3

3. **The threat model is wrong, and the correction changes the design.** The foundational
   research imports a *multi-tenant* threat model (UCC, 57–71% cross-user contamination)
   into a *single-tenant* product. Halbert has one admin and one host. Its real risks are
   **staleness** (recalling re-observable state that has since changed) and **environment
   poisoning** (log lines, config comments, package metadata and web docs becoming
   remembered fact on a root-privileged agent). Both call for different mechanisms than
   cross-user isolation. §4.2, §4.9

4. **Waiting is right, with exactly three exceptions.** The dependency analysis supports
   the founder's instinct: this is a layer on top of Plan A and Plan B, not beside them.
   But Plan A task **A2 (receipts) is being written this week**, and three schema/content
   decisions inside it cost minutes now and require a migration plus re-derivation later.
   §7.3

---

## 1. Verification pass

The foundational research was written by another agent in a session that (by its own
Appendix A) was operating under heavy context bleed. Its landscape survey holds up well.
Its claims about Halbert's own state do not.

### 1.1 Verified correct

| Claim | Evidence |
|---|---|
| `agent.process()` is called with no `conversation_history` | `routes/agent.py:853` — passes `query`, `session_id`, `images`, `model_override`, `tier_override`. No history. |
| The plumbing to receive it already exists | `state_machine.py:195` accepts the kwarg, `:228` stores it on `ctx`, `:643` feeds the assembler. The parameter is wired end to end and never filled. |
| `ContextWatermark` has no production consumer | `context/watermark.py` is referenced only by `tests/test_context_watermark.py`. |
| `.handoff/` does not scale | 63 documents, no index, no tags, no retrieval. |
| `compress_conversation_history()` returns a real summary its caller discards | `conversation/summarization.py:109`, called at `context/assembler.py:365-367`. |
| StatePlane is real and as described | arXiv 2603.13644 — episodic segmentation, selective encoding, goal-conditioned retrieval with intent routing, reconstructive synthesis, adaptive forgetting. |
| The UCC paper and its 57–71% figure are real | arXiv 2604.01350, *No Attacker Needed*. Also confirmed: sanitization leaves residual risk when shared state includes **executable artifacts**, and failures are **silent wrong answers**. |

### 1.2 Corrections

**C1 — `memory/` already exists, and §12.6 would collide with it.** The research says to
create `memory/store.py`, `memory/artifact.py`, `memory/retrieval.py`,
`memory/forgetting.py`. Two of those names are taken:

- `memory/retrieval.py` — `MemoryRetrieval`, the **Haloysius file-based** memory reader
  (core / runtime / personas subdirectories). Live: `Halbert/main.py:496,522,1735`,
  `routes/memory.py`.
- `memory/writer.py` — `MemoryWriter`. Live: `main.py:541,1738`, `scheduler/executor.py:550`.
- `memory/hybrid.py` — `HybridMemorySystem`, 28 KB, reached via `context/adapters.py:204-205`.

**C2 — "Phase 4: adaptive forgetting" is largely already implemented, and deliberately
switched off.** `HybridMemorySystem` already has `reinforce():304`, `forget():323`,
`consolidate():336`, `edit():386`, `merge():445`, `flag_contradiction():501`,
`get_contradictions():544`, `summarize_cluster():562`. Its `Memory` dataclass already
carries `importance` (salience), `access_count`, `last_accessed`, `edit_history`,
`parent_ids` and `contradiction_ids`. The approved spec puts it **off the thread path** on
purpose, because ChromaDB is eval-only (`the-being.md` §9) and because
`memory.store_interaction` on the agent path would inject every turn's Q/A into unrelated
threads. Phase 4 is not a build. It is a decision about an existing module.

**C3 — `scope_mode="hard"` is not Halbert machinery.** It is a parameter Halbert *sends*
to the SourcePrep daemon (`integrations/sourceprep_client.py:115,128`). The pre-filter runs
inside SourcePrep's `CodeIndex.search` (`HANDOFF-SCOPE-FILTER-REVIEW-2026-08-26.md` §F3).
Halbert has no local hard-filter to generalize from — the pattern has to be ported, not reused.

**C4 — the sequencing premise is inverted.** §11.1 phases the work as "E-3 first, then
wake/sleep, then a domain-scoped store." E-3 is not a separate phase: it is inside Plan A
(task A9c wires `conversation_history` through `begin_turn`/`end_turn`). And most of
"wake/sleep" is Plan A's turn pipeline and thread lifecycle. The real Phase 1 is *finish
Plan A*, not *start E-3*.

**C5 — the guardrails in §12.4 would break the approved product.** Guardrail 3 ("Every
session starts with `wake(session_id, domains, task)`. The agent cannot pivot to undeclared
domains") and verification test 5 ("Verify the agent refuses or asks for a scope expansion")
contradict the founder's direction of 2026-08-26: *"One seamless chat without the need to
click into a list of conversations."* An admin will not declare `domains=[disk]`, and an
agent that refuses a question because it is off-scope is a worse product than one that
bleeds a little. This is the central tension and it is resolvable — see §4.1.

**C6 — the threat model does not transfer.** UCC studies *"a single agent serving multiple
users within teams or organizations, reusing a shared knowledge layer across user
identities."* Halbert is one admin, one host. Principal isolation is trivially satisfied.
Importing the multi-tenant defenses wholesale means paying for isolation Halbert does not
need while leaving its actual exposure unaddressed. §4.2 and §4.9 give the corrected model.

**C7 — line-number citations across these documents have already drifted.** The same call
site is cited as `routes/agent.py:686` (spec §1), `:864` (foundational research §9.2), and
is at `:853` today. Treat every `file:line` in the handoff corpus as a hint, not a fact.

### 1.3 What the foundational research missed

Three sources published since — or overlooked by — that session change specific
recommendations.

**ECHO — *A Cognitively Inspired, Auditable Memory Plane for Long-Horizon Agents*
(arXiv 2608.21755, this month).** Its thesis sharpens the "no LLM in the read path"
principle into something more useful: **existing systems conflate retrieval with
authority.** A nearest-neighbour store will happily return both an old value and its
correction with no way to say which is current. ECHO separates them — *"similarity
proposes; the ledger resolves"* — with a bitemporal ledger and a **three-valued resolver**
(exists uniquely / missing / conflicts) that **never uses similarity to break ties**. Also
valuable: **selective realization**, where the reader *abstains* when the evidence closure
is incomplete rather than answering from partial support.

And a result worth taking seriously before committing to this class of architecture:
**ECHO failed its own preregistered generalization gate** (BEAM five-history: 78.65% Hit@10
against a ≥85% threshold, 40.80% turn recall against ≥50%), and **lost to Mem0 by 23
points on end-to-end QA** (41.76% vs 64.84% on a matched 91-question sample, McNemar
p=.00107) *despite* far stronger retrieval metrics on its development sets. The authors
state their contribution is "architectural and methodological" rather than a demonstration
of better answers. The honest reading: an auditable evidence plane buys **provable
currentness and staleness-safety**, not accuracy. Build it for the first reason. Do not
promise the second. §4.3 sizes the cheap version accordingly.

**ATANT — *An Evaluation Framework for AI Continuity* (arXiv 2604.06710, and v1.1 at
2604.10981; Kenotic-Labs).** The foundational research has no evaluation methodology beyond
six manual checks in §12.5. ATANT supplies one, and three of its design choices are
directly applicable: it tests **the full write-path-to-read-path pipeline, not retrieval
alone**; it puts **no LLM in the evaluation loop**; and its **cumulative mode measures
disambiguation under memory load** — which the authors note no prior benchmark did. Its own
reference implementation scores 100% isolated but 96% at 250-story cumulative scale.
Precision degradation as the store grows is real, measurable, and invisible to every test
Plan A currently has (all of which run at one or two threads). The corpus itself is
narrative and life-domain, so it is not runnable against a sysadmin agent — the
*methodology* ports, the *tests* do not. §6.

**A Survey on Long-Term Memory Security in LLM Agents (arXiv 2604.16548).** Organises
attacks and defences across a six-phase lifecycle (write / store / retrieve / execute /
share / forget-and-rollback). Two things matter here. First, the **environment-only** attack
class: eTAMP shows an attacker needs only to *manipulate a web page* — no interaction with
the agent at all — and the attack surface becomes "any observable context that can influence
what the agent decides to store." For an agent that reads logs, config comments and package
metadata with root, that is the live exposure. Second, its **Verifiable Memory Governance**
primitives — Write Authorization, Provenance Visibility, Principal-Scoped Retrieval,
Rollbackability, Verified Forgetting — form a dependency tower, and its conclusion is the
sequencing argument this document is making: *"LTM security cannot be retrofitted at
retrieval or execution time alone, but must be anchored in storage-time provenance,
versioning, and policy-aware retention from the outset."* That is the case for settling the
three schema decisions in §7.3 now rather than after 500 receipts exist.

(*Also noted, not leaned on:* arXiv 2605.16746, *State Contamination in Memory-Augmented LLM
Agents*, covers persistence of contamination across interactions. Its figures were extracted
from PDF and are not quoted here.)

**One caveat on the foundational research's own top pick.** It rates Nūr "Halbert fit: Very
high." The repository is real and the feature list checks out — constitution, belief decay,
relational continuity with commitments and open loops, `nur.db` / `life_history.db`. It has
**3 stars**. It is an excellent source of *patterns* — its relational-continuity layer is
the single best articulation of the gap in §3.2 below — and not a candidate for dependency.

---

## 2. The reframe: eight stores and no owner

The foundational research asks "what memory architecture should Halbert build?" The repo
answers a different question first.

| # | Store | Substrate | Live callers | Status |
|---|---|---|---|---|
| 1 | `agents/conversation.py` JSON `ConversationStore` | JSON files | dashboard routes | **deleted by Plan A A12d** |
| 2 | `agents/conversation_sqlite.py` | SQLite + FTS5 | none | **becomes store of record in Plan A** |
| 3 | `memory/hybrid.py` `HybridMemorySystem` | ChromaDB + graph + self-knowledge | `context/adapters.py:204` | fenced off the thread path |
| 4 | `memory/retrieval.py` + `writer.py` | Haloysius **files** (core/runtime/personas) | `main.py`, `scheduler/executor.py` | **non-functional** — writer/reader schema mismatch, 0 entries live (audit F1); **toss** |
| 5 | Haloysius `memory_v2.PersonaMemoryStore` | SQLite (Haloysius) | `integrations/cognition_wiring.py` | write target; **no read path** |
| 6 | `somatic/store.py` `SomaticStore` | SQLite (`~/.halbert/somatic_blocks.db`) | somatic lifecycle | live |
| 7 | `index/chroma_index.py` `self_*` collections | ChromaDB | `routes/memory.py` | eval/browser only |
| 8 | SourcePrep `prep_observe` | external daemon | agent tooling | underused |
| — | `.handoff/*.md` | 63 markdown files | humans and agents, by hand | the real memory today |

Two of these are surfaced by the same dashboard router under different endpoints
(`routes/memory.py` serves the Haloysius file memory at `/stats` and `/search`, and the
ChromaDB browser at `/index/*`) — the file itself documents the split in its module
docstring. That is the whole problem in one file.

**The disease is not missing design. It is unwired design.** The approved spec says so in
its own §1: *"The sub-agent, affinity-router, SQLite+FTS5 store, summarisation cascade and
watermark modules are all committed with zero production callers."* Verified today for two
of the five, plus `HybridMemorySystem`'s entire advanced API (contradiction flagging,
merging, consolidation, cluster summarisation) which exists and is never called.

And Plan A is about to add a **sixth** instance of the pattern: it writes one Haloysius
episodic line per closed thread (spec §8), while a semantic read tier via
`memory_v2.search` is **explicitly deferred** (spec §6). That is a write-only memory. For a
root-privileged agent it is worse than no memory: an unread, unaudited store that accretes
content derived from logs and config files, which is exactly the substrate the memory-
security survey says must carry provenance and verified forgetting *from the outset*.

This yields the first and most portable design rule, and it is a process rule, not an
architecture:

> **R1 — No memory write path merges without its read path in the same plan.**
> If the read path is deferred, defer the write too. A store nobody reads is a liability
> that grows.

---

## 3. Plan A already builds most of the proposed architecture

### 3.1 The mapping

| Foundational research (§10) | Plan A / spec equivalent | Status |
|---|---|---|
| Domain tag on artifacts | `topic_domains` column + entity alias table in `intake/signals.py` | A1, A4 |
| Structured handoff artifact (§10.7 YAML) | **Receipt** — 9 fixed sections, ≤1,500 chars, extractive | A2 |
| `wake()` — retrieve state, reconstruct bounded context | Turn pipeline: signals → thread resolution → deterministic recall → `<continuity>` hint | A5, A6, A9c |
| `sleep()` — summarise, write artifact, clean up | Thread close at grace-window expiry: final receipt, FTS index, Haloysius line | A6b, A3 |
| "No LLM in the read path" | "Deterministic recall on strong match… **No model call**" (spec §6) | A6b |
| Bounded reconstruction, `\|C_t\| ≤ L_max` | `compute_num_ctx` clamp + hint ≤120 tokens + 6 raw turns + receipt slot | A10, A8 |
| Multi-signal retrieval | FTS5 `porter unicode61` over receipts + canonical entity overlap + recency gate | A3, A4 |
| Provenance on artifacts | Receipt carries commands with exit codes and files written; blocks carry `redacted` | A2 |
| Anti-bleed | `memory.store_interaction` **removed** from the agent path (spec §7) | A9a |
| Session scope | Thread resolution — inferred and revisable, not declared | A5, A6 |

That is a substantial fraction of §10 delivered, and in several places delivered *better*
than proposed. The receipt beats the §10.7 YAML: it is zero-cost and extractive where the
YAML implies an LLM write; it is one row on the thread rather than a file per session; and
it stores **file paths and commands** rather than file contents and command outputs — which,
as §4.2 shows, is the single most important property a sysadmin memory can have, and Plan A's
authors got it right by instinct.

### 3.2 What Plan A genuinely does not cover

Six gaps. These, and only these, are the cross-session continuity layer.

**G1 — Nothing is pushed. Everything is pulled.** Receipts surface only on FTS or entity
match. A thread that closed with *"Open loop: monitor disk for 24h to confirm the fix
held"* surfaces at hour 24 only if the admin happens to mention disks. There is no
commitment ledger and no due date anywhere in the schema. This is Nūr's relational
continuity, and it is the one genuinely *cross-session* behaviour — everything else in
Plan A is recall-on-demand.

**G2 — Receipts never abstract.** Ten Samba threads produce ten receipts that all match the
same entities. Nothing promotes *"on 14 Jul we set `guest ok = no`"* into *"this admin
always wants explicit `valid users`"*. Plan A reaches the Reflection stage of the
Storage → Reflection → Experience framing and stops there.

**G3 — Precision decays with N, silently.** FTS5 lookup stays O(log n); *precision* does
not. At 500 threads a query for `samba` matches dozens. "Top-2 with scores" hides the
degradation rather than fixing it. Every Plan A test runs at one or two threads. ATANT's
cumulative mode exists precisely because this failure is invisible in isolated testing.

**G4 — No supersession.** A July thread says sshd is on 22; an August thread moves it to
2222. Both receipts match `sshd`. Recall may return either or both, and nothing marks the
older as superseded. `HybridMemorySystem.flag_contradiction():501` exists and is off the
path.

**G5 — The Haloysius line is write-only.** Per R1, this should not ship as designed.

**G6 — No host/identity boundary.** Halbert identifies as the host. Nothing states what
memory survives a reinstall, or what happens when one admin runs Halbert on three machines.

---

## 4. Design strategies

Each section states the tension, the real options, and a recommendation.

### 4.1 Scope is a property of the query, not of the session

**Tension.** SESS-03 says limit each session to a declared task; the founder says one
seamless chat with no list and no clicking in. These look irreconcilable, and the
foundational research resolves them in the direction that breaks the product (C5).

**Options.**

- **(a) Declared scope, hard-enforced.** Faithful to SESS-03. Requires the admin to declare
  domains, and produces an agent that refuses off-scope questions. Rejected — it contradicts
  an explicit founder decision.
- **(b) Inferred scope, buffer isolation only.** Plan A as built: the working context *is*
  the open thread, so unrelated context is absent rather than filtered. Prevents bleeding by
  construction. No enforcement point, nothing auditable, and recall can still cross domains.
- **(c) Inferred scope, enforced at the retrieval boundary.** The session never declares.
  Every *recall query* carries a scope, derived from the open thread's `topic_domains` and
  canonical entities. Cross-domain candidates require either an explicit `recall_thread`
  call by the model or ≥2 canonical entity overlaps.

**Recommend (c).** The move that dissolves the tension: **enforcement belongs at the recall
boundary, not at the session boundary.** The admin is never asked to declare anything and is
never refused; a scope crossing becomes a logged, testable event rather than a user-visible
refusal. This is the memory-security survey's **Principal-Scoped Retrieval** primitive,
generalised from *principal* to *topic* — which is the right generalisation for a product
with exactly one principal.

Concretely, on top of Plan A: `search_receipts()` gains a `domains` argument defaulting to
the open thread's domains, and emits a `scope_crossed` telemetry event when a returned
candidate shares no domain with the open thread. Nothing in the UI changes.

### 4.2 The re-observability rule

**This is the most important section in this document.**

**Tension.** Generic agent memory assumes the world is not re-readable, so remembering state
is the whole point. For a sysadmin agent the opposite holds: **the machine is the database.**
`df -h` is faster, cheaper and more accurate than any recollection of disk usage from six
weeks ago. Remembering re-observable state is not merely wasteful — it is the direct
generator of the UCC failure mode, *silent wrong answers*, in a single-user product where
cross-user contamination cannot occur.

> **R2 — Before writing a claim to memory, ask whether a command can re-derive it in under
> a second. If yes, store the command, not the answer.**

Memory holds what cannot be re-observed: **intent, rationale, what was tried and rejected,
what the admin prefers, what was promised, and the provenance of a change.** The machine
holds the state. Memory is the journal, not the state.

**Applied to Plan A's nine receipt fields** (from task A2's specification):

| Field | Re-observable? | Verdict |
|---|---|---|
| `Title` | No | keep |
| `When` | No — a historical fact | keep |
| `Domains` | No | keep |
| `Entities` | No | keep |
| `Started with` | No — this is **intent**, the highest-value durable content in the whole system | keep; most valuable field |
| **`Last said`** | **Often yes** — present-tense state claims | **the leak** |
| `Commands` | No — and doubles as a re-derivation recipe | keep; best-designed field |
| `Files written` | No — stores **paths**, not contents | keep; already the correct pattern |
| `Open loop` | No — a commitment | keep, and promote to a row (§4.4) |

Eight of nine already pass. The receipt is a well-designed artifact. The exception is
`Last said`, and A2's own test fixture demonstrates the failure exactly:

```
Last said: The share mounts from the laptop at //nas/media (v3.1 client).
```

That is a present-tense assertion about mutable state, extracted into a durable artifact,
retrieved six weeks later and injected verbatim as `retrieved_context[0]`. It will
eventually be false, and it will be quoted with confidence.

**Three fixes, cheapest first.**

1. **Date-stamp the field at build time** — `Last said (2026-07-14): …`. A one-string change
   in `build_receipt`. The model then cannot quote the claim without carrying its date.
2. **Make the `<continuity>` prompt component say it** — recalled receipts are past
   observations; verify current state before asserting it. The spec's own worked example
   already does this correctly by hand (*"On Jul 14 we added `[media]`…"*); make it a rule
   rather than an accident of one example.
3. **Later — abstain and probe.** ECHO's selective realization: when an answer needs current
   state and only a past receipt supports it, do not answer from the receipt. Probe.

Point 3 is where Halbert's domain gives it an advantage no general agent has. Probing costs
milliseconds and one command. **A memory system for an agent that can re-observe its world
should be biased toward abstain-and-probe** — which makes the entire staleness failure class
disappear rather than mitigating it. That is the design thesis for Halbert's continuity
layer, and it follows from "the machine is the project."

### 4.3 Authority is not similarity

**Tension.** G4. Two receipts match `sshd`; one is current, one is superseded; ranking by
relevance cannot tell them apart, and adding a re-ranker does not change the category error.

**Options.**

- **(a) Recency-weighted ranking.** One line of code. Wrong whenever the older thread is the
  more relevant one — and it still returns a superseded claim, just lower down.
- **(b) Full bitemporal ledger (ECHO / Graphiti).** Correct and auditable. Expensive: valid
  time and transaction time per claim, revision relations, a three-valued resolver,
  provenance-closed packing. And ECHO — the paper that argues for it hardest — failed its own
  generalization gate and lost to Mem0 by 23 points end to end.
- **(c) Supersession flag on entity-signature match.** At thread close, compute the thread's
  `(domains, canonical entities)` signature. Any earlier **closed** thread whose signature is
  a subset gets `superseded_by` set to the new thread. Recall excludes superseded receipts by
  default; `recall_thread` can request history explicitly.

**Recommend (c) — but do not build it.** *(Superseded by audit finding F4.)* Haloysius's
`TemporalStateLedger` already implements option (b): `record()` automatically closes the
previous triple's valid-time interval, `get_current()` returns only live state,
`get_history()` returns the audit trail, each triple carries a `source`. Verified working.
The correct move is to **wire the ledger at thread close**, not to add a column. What
follows is retained as the rationale for why supersession matters.

It adopts ECHO's principle — *similarity proposes, the ledger resolves* —
at roughly 3% of the cost, and it is fully deterministic. The substrate is already present:
receipts carry `When` (valid time) and rows carry timestamps (transaction time), so
upgrading to (b) later is an extension rather than a rewrite. Given ECHO's negative result,
buying the full ledger now would be paying a large cost for a benefit that has not been
demonstrated.

~~Schema cost today: one nullable `superseded_by` column on `conversations`.~~ Superseded:
call `ledger.record(persona_id, subject, predicate, object, source=thread_id)` at thread
close. See the audit's §6 N3.

### 4.4 Commitments are rows, not prose

**Tension.** G1. `Open loop:` is the single most valuable durable output of a thread and it
is trapped inside a text blob, so nothing can ask *"what is outstanding on this machine?"*

**Recommend:** promote it. An `open_loops` table — `thread_id`, `text`, `domains`,
`created_at`, `due_at` (nullable), `status` (`open | met | dropped`), `closed_by_thread_id`.

The payoff is disproportionate:

- The `<continuity>` hint carries *"2 open loops in this domain"* in roughly 40 tokens —
  cross-session continuity with no retrieval machinery at all.
- Plan C's proactive channel gets something real to be proactive **about**. Today it has
  findings; this gives it promises.
- It becomes queryable, and therefore auditable by the admin.

**And the extractor already exists.** A2 builds the `Open loop:` line today. Writing the row
at the same moment is nearly free. Deriving it later means re-parsing every historical
thread. This is §7.3's second item.

### 4.5 Where the write path pays

**Options.** Per-turn LLM extraction (Mem0) — rejected already on cost and local-first
grounds, and it is the highest-bleed pattern besides. Per-turn extractive (Plan A receipts) —
correct, keep. Deferred consolidation at idle — the missing half.

**Recommend: extractive on the hot path, abstraction at idle.** G2's cross-thread
abstraction cannot be done extractively; it needs a model. It also does not need to be done
in a turn. Run it offline, budgeted, interruptible, resumable.

Halbert has an advantage here that is easy to miss: **it is the machine, so it knows when
it is idle.** `state_trackers.py` and the resource monitors already report load; the
scheduler (`scheduler/executor.py`, `scheduler/autonomous_tasks.py`) already exists. Halbert
can schedule consolidation into genuinely quiet windows in a way a cloud agent cannot. This
is the spec's deferred "Dream Cycle," and this is where it belongs.

One dependency worth flagging: consolidation needs a model slot, and it should not be the
chat slot. That is an `llm_config` question — adjacent to the model picker work, not blocked
by it. §7.2.

### 4.6 One owner for beliefs

**Tension.** Haloysius owns beliefs, drives and worries through `PersonaCognition` and
`PersonaMemoryStore`. A continuity layer that also stored beliefs would create a dual-write
with no reconciliation rule.

**Recommend: Haloysius owns beliefs. The continuity layer supplies evidence and reads
state — and the read path ships with the write path (R1).** The spec's deferred "semantic
tier via `memory_v2.search`" *is* that read path. Either land it in the same plan as the
episodic line, or do not write the line yet. Writing into a store with no reader is how the
codebase got eight stores.

### 4.7 Three tables, not a ninth store

**Recommend: extend the Plan A database.** After Plan A, `SqliteConversationStore` is the
store of record with WAL, a busy timeout, a single write lock and two FTS5 indexes. The
continuity layer needs `open_loops` (§4.4), `facts` (consolidated output of §4.5), and a
`superseded_by` column (§4.3).

One database means one backup, one migration path, one lock, and free joins — a commitment
can reference its thread and its turn directly. More importantly it means **cross-session
continuity is not a new subsystem.** It is two tables, one column, a scheduled job and a
hint line, on top of a store that will already exist.

This is the direct answer to *"this is a challenging piece to add."* As specified by the
foundational research — five new modules, a new store, a session-lifecycle protocol — it is
challenging. As an extension of Plan A it is not.

### 4.8 The host boundary

**Recommend: memory is host-bound; admin preferences are the only portable tier.**
`guest ok = no on /srv/media` is a fact about this machine and dies with it. *"This admin
always wants explicit `valid users`"* is a fact about the relationship and should survive a
reinstall and move to a second machine. That line falls out of R2 — it is the same
durable/re-observable split applied to identity — and it gives a principled export boundary
for free. It is also the honest reading of "the machine is the project": the project's
memory dies with the project; the relationship's memory does not.

### 4.9 The threat model, corrected

Halbert is single-tenant, so the cross-user contamination defences are not the priority. Two
risks are, and both are underserved by the foundational research.

**Staleness** — covered by R2 and §4.3. In a single-user system this *is* the contamination
mechanism, and it produces the same silent wrong answers the UCC paper describes, by a
different route.

**Environment poisoning** — the serious one, and unaddressed. Halbert reads log lines,
config comments, package descriptions and web documentation, with root. The memory-security
survey's **environment-only** class (eTAMP) requires no interaction with the agent at all:
the attack surface is *any observable context that can influence what the agent decides to
store*. If untrusted text becomes a remembered fact, an attacker gains a persistent
influence channel on a privileged agent.

Mitigations, in order of cost:

1. **Origin on every memory row.** Plan A already distinguishes `origin` (`human`,
   `assistant`, `terminal`, `system`) on messages, and already refuses to write the
   Haloysius line for `origin=terminal` content. Carry the same discipline into every
   continuity table: a durable claim derived from tool output is marked as such.
2. **`Files written` and `Commands` are pointers, not content** — already true (§4.2), and
   the reason it matters is security, not just freshness: a path is inert, a remembered
   command *output* is attacker-controlled text.
3. **Consolidation reads only human- and assistant-origin content** unless a claim is
   corroborated by an explicit admin confirmation. Free to state now, expensive to retrofit.

That is Write Authorization and Provenance Visibility from the survey's VMG tower, at
approximately no cost, *if* the origin column is honoured from the first write.

---

## 5. What this actually costs

Assuming Plan A and Plan B have landed:

| Item | Size | Depends on |
|---|---|---|
| `open_loops` table + extractor row-write + hint line | small | A2 receipt builder |
| `superseded_by` column + close-time signature check | small | A1 schema, A6b close path |
| Scope argument on recall + `scope_crossed` telemetry | small | A3 search |
| `Last said` date stamp + `<continuity>` temporal framing | trivial | A2, A8 |
| Consolidation job (idle-scheduled, model-backed) + `facts` table | medium | scheduler, a cheap model slot |
| Haloysius `memory_v2.search` read tier | medium | Haloysius API |
| Abstain-and-probe policy in the responder | medium | state machine, tool policy |
| Cumulative evaluation harness (§6) | medium | thread store |

No item is large. The largest risk is not any one of them; it is starting before the
substrate they all attach to is stable.

---

## 6. How you would know it works

The foundational research's §12.5 is six manual checks. Borrowing ATANT's methodology gives
something that can actually gate a merge:

1. **Test the whole pipeline, write path to read path** — not retrieval in isolation. A
   receipt that indexes perfectly and is never recalled at the right moment scores 100% on
   retrieval and 0% on the product.
2. **No LLM in the evaluation loop.** Assertions over structured outputs — which thread was
   recalled, which domains were crossed, whether a superseded receipt appeared.
3. **Cumulative mode is the one that matters.** Run the same recall suite at 10, 100 and 500
   synthetic threads and record precision at each. G3 is invisible at N=2, and every Plan A
   test today runs at N=2. This is the single highest-value test to build, and it can be
   built before any of the design above, against Plan A alone.
4. **Measure end to end, not just retrieval.** ECHO's result — excellent retrieval metrics,
   worse answers than a simpler baseline — is the cautionary case. Retrieval quality is a
   proxy, and a leaky one.
5. **A staleness suite.** Write a receipt asserting a state; change the state on the host;
   ask a question that would be answered wrongly from the receipt. Correct behaviour is
   probe-then-answer, not recall-then-assert. This test does not exist in any framework
   surveyed, because no other agent *is* the machine it remembers.

Item 5 is Halbert-specific and is the one that would differentiate the product.

---

## 7. Sequencing — the answer to "when can we begin"

**The instinct to wait is correct.** Here is the precise version.

### 7.1 Hard blockers

**B1 — Plan A, backend tasks A1–A13.** Creates the store of record, `threads` with
`topic_domains` and `entities_json`, receipts, `receipts_fts`, `thread_id` on
`StateContext`, and deletes the JSON `ConversationStore`. Every continuity table
foreign-keys to `conversations`. Building against the pre-Plan-A schema means migrating
twice. *(Status: launched. A1 in progress in the worktree — `conversation_sqlite.py`
modified, `test_thread_store.py` untracked.)*

**B2 — Plan B §9.2, the OSC 133 block parser.** Not obvious, and load-bearing. The receipt's
`Commands` and `Files written` fields are built from block records carrying `exit` /
`result.exit_code` (visible in A2's test fixture). Those come from Plan B's shell-integration
parser. **Plan A can build receipts; only Plan B makes their provenance fields
trustworthy** — and consolidation over low-quality receipts produces low-quality facts that
then need retracting. Receipt *existence* is Plan A; receipt *quality* is Plan B.

**B3 — the store-consolidation decision.** Is `HybridMemorySystem` retired, repaired, or
permanently fenced? Does the Haloysius line get its read path or get withdrawn (R1)? Until
these are answered the continuity layer cannot know where a consolidated fact belongs, and
answering them wrongly means writing into a ninth store.

### 7.2 Soft — better first, not blocking

**B4 — a model slot for consolidation.** §4.5 needs a cheap slot that is not the chat slot.
An `llm_config` question, adjacent to the model picker work now on `main`. Worth deciding
before the consolidation job is written; not worth waiting on.

### 7.3 The three things that should not wait

Plan A is executing. A1 is in flight and **A2 (`agents/receipt.py`) is next**. All three
items below are decisions about *schema and content* rather than features — the class of
thing that costs minutes inside a task being written this week and costs a migration plus
re-derivation from raw message history afterwards. This is the memory-security survey's
point applied literally: storage-time provenance cannot be retrofitted.

**N1 — date-stamp `Last said` in `build_receipt`.** One string: `Last said (2026-07-14): …`.
Closes the staleness leak at its source (§4.2). Every receipt written without it is a future
confident-and-wrong answer.

**N2 — write the `open_loops` row when A2 extracts the `Open loop:` line.** The extractor is
being written right now. The row costs one insert. Retrofitting means re-parsing every
thread's message history (§4.4).

**N3 — *(revised by audit F4)* have thread close record its established state into
Haloysius's `TemporalStateLedger`** — `ledger.record(persona_id, subject, predicate, object,
source=thread_id)` — instead of adding a `superseded_by` column. The ledger supersedes prior
values automatically and keeps the audit trail. Blocked on audit fix W1 (`sync_to_ledger`
calls a non-existent `set_state`, and is never passed a ledger).

Everything else in this document should wait for B1–B3.

---

## 8. Open questions for the founder

1. **`HybridMemorySystem`** — retire, repair, or permanently fence? (B3, and it determines
   whether §4.5's `facts` are a new table or an existing store.)
2. **The Haloysius episodic line** — land `memory_v2.search` alongside it, or withhold the
   write until the read exists? R1 says withhold; the spec currently ships the write alone.
3. **Abstain-and-probe** (§4.2, item 3) — is an assistant that says *"we set that on 14 Jul;
   let me confirm it is still current"* and runs a command the behaviour you want, or is the
   extra step friction? This is a product question, and it decides how far the
   re-observability principle is taken.
4. **Commitment surfacing** — when an open loop comes due, does Halbert speak
   unprompted (Plan C's proactive channel), or wait to be asked? The founder's
   "notify-only, no autonomous continuation" decision suggests the former with a light
   touch, but a commitment coming due is a different signal from a finding.
5. **The portable tier** (§4.8) — is "this admin's preferences move between machines" a
   product goal, or is Halbert strictly one mind per host?

---

## 9. Sources added to the foundational research

- **ECHO: A Cognitively Inspired, Auditable Memory Plane for Long-Horizon Agents** —
  arXiv 2608.21755. Similarity proposes, the ledger resolves; three-valued resolver;
  selective realization / abstention. Includes the negative result in §1.3.
- **ATANT: An Evaluation Framework for AI Continuity** — arXiv 2604.06710; v1.1 at
  2604.10981; `github.com/Kenotic-Labs/ATANT`. Write-path-to-read-path evaluation, no LLM in
  the loop, cumulative mode.
- **A Survey on Long-Term Memory Security in LLM Agents** — arXiv 2604.16548. Six-phase
  lifecycle; environment-only attacks (eTAMP); the VMG primitive tower; storage-time
  provenance cannot be retrofitted.
- **State Contamination in Memory-Augmented LLM Agents** — arXiv 2605.16746. Noted; figures
  not relied on.
- **No Attacker Needed: Unintentional Cross-User Contamination in Shared-State LLM Agents** —
  arXiv 2604.01350. Verified, with the scope correction in C6.
- **StatePlane** — arXiv 2603.13644. Verified as described.
- **Nūr** — `github.com/balfiky/nur`. Verified; 3 stars, MIT. Pattern source, not a
  dependency.

---

*End of document.*
