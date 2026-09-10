# Where the line between Halbert's memory and Haloysius's goes

**Status:** design memo, founder decision pending (§8). Supersedes the
curated-core half of Packet 01 Phase B as designed.

**Revised 2026-09-10** against `REVIEW-DUAL-MEMORY-INHOUSE-2026-09-10.md`.
Three things in the first draft were wrong and are marked where they changed:
the defence in §1 was rationalisation; §4.1's partition needed a classifier
and so was not a partition; and §4.3's supersession vocabulary was dead
columns on most rows. Fable's second opinion on two remaining questions is
outstanding.

**The question, as the founder put it:** *"we need to think about nuance and if
the computer can resolve ambiguity or slight mismatches in memory (which I
assume is inevitable if we leverage both). perhaps the memory of the computer
is weighted more."*

The premise is right — overlap is inevitable once both stores are live. The
conclusion the research supports is not the one either of us expected.

---

## 1. What the field did in 2026, and it is uncomfortable

**The two most-cited dual-store memory systems both collapsed into a single
synthesized store, two months apart.**

- **Mem0**, PR #4805, merged 2026-04-14: LLM-arbitrated `ADD/UPDATE/DELETE`
  removed; memories are ADD-only. The same PR deleted every graph-database
  integration.
- **OpenAI**, June 2026: "saved memories" superseded by one continually
  re-synthesized summary. Legacy is opt-back-in.

OpenAI documented why, and it is our exact failure mode (verified in a
browser at `help.openai.com`, page updated 2026-08-31):

> The previous saved memories system often became stale and relied on users to
> manually manage updates. **Memories could also contradict one another, such
> as "I'm training for a marathon" and "I sprained my ankle,"** which made
> personalization less accurate.

Neither company reconciled better. **Both removed a store.**

That is a real signal against our architecture and it should be stated
plainly rather than explained away.

**Revised 2026-09-10 after an in-house second read, which found the first
draft's defence to be rationalisation.** That draft argued OpenAI's stores
held "the same kind of fact by different capture routes" while ours hold
different *kinds* of fact — but §4.1 below partitions by observed-versus-told,
which *is* a capture route. The memo contradicted itself, and the defence has
to be dropped.

**The two better arguments:**

**(a) The evidence indicts the curated core, not the split.** Mem0's and
OpenAI's stores held *the same predicates* and *competed for the same prompt
slot* at retrieval. Halbert and Haloysius do that in exactly one place —
Packet 01 Phase B's curated core, which would render user facts into Halbert's
`messages[0]` beside whatever Haloysius says about the same user. **Deleting
the curated core (§6) IS the response to this evidence.** After that deletion
the split is outside its blast radius.

**(b) The costs are not comparable.** Halbert and Haloysius are two
*deployables*, with two lifecycles, two distribution contracts (the
subtractive two-dependency rule) and two ownership/privacy boundaries (the
guest-persona ownership divide, the R9 fence). OpenAI's collapse was a
data-model simplification with no organisational cost. Ours would delete a
**product** boundary. That is the ground to ratify §8.1 on.

## 2. The evidence against automatic merging

**A controlled study of precisely this.** *"Useful Memories Become Faulty When
Continuously Updated by LLMs"* ([arXiv:2605.12978](https://arxiv.org/abs/2605.12978)):
memory utility *"first rises, then degrades, and can fall below the no-memory
baseline."* Consolidating even from **ground-truth** solutions, GPT-5.4
subsequently failed **54% of ARC-AGI problems it had previously solved without
memory**. Agents preserving raw episodes **doubled** the accuracy of
forced-consolidation counterparts. Mechanism: overgeneralisation —
**abstraction strips the applicability conditions**.

**It has already happened in production.**
- Graphiti #1728 (open): **41% of facts in a real graph carried `invalid_at`**
  — contradiction candidates fetched with an unfiltered search and passed to
  the LLM as bare strings. A person's job title retired by an unrelated
  administrative role.
- Mem0 #4573: 10,134 entries over 32 days, **97.8% junk**, including **808
  entries asserting a fabricated "User prefers Vim," 191 exact duplicates** —
  one hallucination amplified because recalled memories were re-extracted.

**The judge is not calibrated enough to hold a destructive privilege.**
Prompt-design F1 standard deviation reaches **18.5** for mid-tier models
(per-dataset up to 26.5); one model swings 85.4 → 33.6 on a reworded prompt.
Changing *"the same"* to *"equivalent"* moves F1 by 9.4 points on average.
LLM matchers over-merge — recall 94–100% against precision as low as **49.5%**.
And self-explanations are unfaithful: Kendall-Tau 0–0.5 between explanations
of the *same decision at temperature 0*.

**The problem is not solvable by a better model**, and Cognee states why in a
source comment that is the sharpest framing of it:

> Most relationships (`knows`, `mentions`, …) are legitimately many-valued and
> **must never be collapsed**, and there is no cardinality metadata to tell
> them apart.

"Likes tea" and "likes coffee" are a contradiction only if `likes` is
functional. Nothing can infer that.

## 3. The line already exists

`MEM-01` (decided 2026-09-03) and `CD-5` (2026-09-05) already say it:
continuity — threads, receipts, recall, open loops, machine-state history —
is Halbert's; identity and semantic memory stay in Haloysius `memory_v2`;
user favourites and opinions are persona insights in Haloysius, **never in
Halbert's event ledger**.

The founder's own framing matches: *Haloysius knows itself and, through
Lenses, the user; Halbert knows this machine.* Nothing needs redrawing. What
was missing is an enforcement mechanism, and §4 is it.

## 4. Recommendation: partition, then declare, then accumulate

**In this order. Each step shrinks the problem the next one has to solve.**

### 4.0 First: most "conflicts" are about facts neither store owns

**The largest class of apparent overlap is claims about *current state*, and
those are re-observable. Neither store is the authority — go look.**

Halbert already says this, and it is the single highest-value line in the
design. `continuity/freshness.py:13-15`:

> holds what cannot be re-derived — intent, rationale, what was tried and
> ruled out, preferences, commitments. The **machine** holds current state.
> So a claim about current state is never answered from memory.

And `continuity/state_store.py:18`:

> Authority is not similarity. Retrieval may *propose* an old receipt; this
> table *resolves* what is currently true.

This **dissolves** conflicts rather than adjudicating them, and it is already
written. Before any weighting, any partition, any predicate list: if the
question is "what is true right now on this machine", the answer comes from
the machine, not from either memory.

The remaining classes are mostly not truth conflicts either. The published
taxonomy splits personal-memory conflict into **context-partitioned** (both
true in unstated contexts), **behaviour-oscillation**, and
**source-contradiction** — and only the third is the case we have been
worrying about. A preference that *changed* is not a store being wrong.

### 4.1 Partition by acquisition mode — not by fact type

**Revised 2026-09-10.** The first draft said "assign every fact *type* to
exactly one store." The in-house read killed that, and the argument is the
strongest thing in the review:

> §4.1's single-writer partition is enforced by a **classifier**, so it is not
> single-writer. Home Assistant has one writer per entity because entity
> identity is *structural* — the device writes its own entity. "My editor is
> nvim" is host state if Halbert observed the process and a preference if the
> user said it; **the same sentence yields either, and an extractor decides.**
> A partition that depends on a fallible judgment call has the contradiction
> problem back, one layer down.

Correct, and fatal to the original step. Partition instead by **acquisition
mode**, which is known with certainty at write time and needs no judgment:

| Acquisition mode | Meaning | Store |
|---|---|---|
| **observed** | a probe, a log, a process table, a sensor | **Halbert** |
| **asserted** | a sentence someone said | **Haloysius** |

This is structural in the way Home Assistant's is structural: the *writer*
knows which it is without inferring anything. Two consequences follow free.

**Never flatten attribution at read time.** The prompt gets *"my log shows A
(observed 03:12); Haloysius reports B (asserted Tuesday)"* — **two true
statements that cannot contradict**, rather than "A vs B, pick one". This is
also the only place §4.5's authority inversion can be countered: by
deterministic framing text, never by a model judgment.

**Step 0 needs a failure branch.** "Go look" is right, but when the probe
cannot run — device gone, process exited, historical question — the memory
answer must come back **stamped with its observation time**, not suppressed.
Otherwise the best line in the design degrades to "I don't know" at exactly
the moment memory is the only source there is.

### 4.2 Declare a merge type per predicate

**Revised 2026-09-10**, collapsing the first draft's §4.2 and §4.3. The review
observed that if §4.1 and the functional-predicate list do their jobs, then
for every *non*-functional predicate nothing is ever superseded — so
`superseded_by` / `superseded_at` would be dead columns on the majority of
rows, and trap 6 says a validity mark the read path does not honour is worse
than none at all. So there is no general supersession vocabulary. There is one
declaration:

| Merge type | Behaviour |
|---|---|
| **`LWW`** | Functional predicate. Recency-ordered **within a store**. The only place supersession exists. |
| **`SET`** | Accumulates. Attributed on read. Never picked between. **The default.** |
| **`ASK`** | The undecided zone (trap 9). Surfaced, never guessed. |

**Unlisted defaults to `SET` and never silently picks.** That inverts the
usual failure: an unclassified predicate accumulates harmlessly rather than
being adjudicated by something that does not know it is guessing.

**Cross-store ordering is unsolved and is fenced off accordingly.** `max(serial)`
orders within one store; across two independently-writing stores a later
timestamp can derive from an *earlier* conversation. Until that is answered,
**`LWW` orders within a store only, and cross-store disagreement on a
functional key routes to `ASK`.**

### 4.3 Build the consumer before the column

The review's best idea, and it answers §8.3 without a hand-maintained list:

**A disagreement meter.** Per-claim-key, the rate at which the two stores
disagree — surfaced as (a) a health signal and (b) **the discovery mechanism
for predicates behaving functionally in the data**, which are the candidates
for `LWW`. So the answer to "who maintains the functional list" is *the data
proposes, the founder ratifies.*

It also satisfies trap 10 — this project's own recurring defect — by giving
the conflict machinery a consumer whose job is **not** "resolve it". Build
this before any provenance column, including the `ClaimStrength`
generalisation: ordinal is the right shape, but adding the column before the
retrieval filter reads it is the wrong order.

### 4.4 On "weight the computer more"

**The instinct is right, better supported than expected, and wrong in three
specific ways as stated.**

**Right, and principled rather than lazy.** You cannot *learn* the weights
from two stores — that is unidentifiability, not difficulty. Two-view
latent-class models have no unique decomposition; identifiability needs a
third conditionally independent view (Allman, Matias & Rhodes, *Ann. Statist.*
2009). With two stores the only statistic is the agreement rate, and it cannot
distinguish "both usually right" from "both usually wrong". Every dataset in
that literature has ≥9 sources. **Do not build a source-weight ↔
claim-confidence loop.** And supplied trustworthiness empirically beats learned
trustworthiness anyway (Li et al., PVLDB 6(2), 2013) — so a hand-set
asymmetry is the recommended answer, not a shortcut.

**Wrong as a veto.** "The less reliable is totally overridden" has a formal
name — Darwiche–Pearl (C2) — and Delgrande, Dubois & Lang (KR 2006,
Proposition 6) prove that adding it collapses the entire operator space to
**linear merging**: the crudest member, which discards the subordinate store
*wholesale on any conflict, including its non-conflicting parts*. Worse, the
outcome then depends on **storage granularity** — write two facts as one
conjunction and you lose the innocent half. Express authority as a
**discount** (`α_A > α_B > 0`), never a veto (`α_B = 0`), which is the
degenerate corner that throws away all of B's evidence.

**Wrong as a per-store scalar.** Reliability is topic-dependent (FaitCrowd,
KDD 2015). Store A is near-authoritative on machine state and near-worthless
on *why* someone did something; Store B is the reverse. A global weight
forces a loss on one axis to win the other. The closest published analogue —
a dual-stream clinical memory separating patient self-report from a validated
clinical record (arXiv:2604.27045) — types confidence **per predicate**: a
stale medication list is discounted, an allergy keeps authority regardless of
age. It also names the two failure modes of a fixed precedence rule:
**hallucinated compliance** (accepting an inaccurate self-report) and
**protocol rigidity** (enforcing an outdated record).

**And one hard constraint I had missed.** The two stores are **not
independent sources** — Store B's contents derive largely from conversations
Store A also logged. Dong, Berti-Équille & Srivastava (PVLDB 2009) show
accuracy-weighting of *dependent* sources performs **worse than plain
voting**, and that copy detection provably cannot see the dependency when the
copied source is accurate (it works by spotting shared *false* values).
**Their agreement must never be counted as corroboration.** That rules out any
naive conjunctive combination.

**The cheapest good version of all this already exists in the tree.**
`persona/claims.py:22-26` has `ClaimStrength: MUTABLE < UNVERIFIED < ASSERTED
< VERIFIED`, currently applied to identity claims. Generalising that ordinal
ladder to memory facts — and typing provenance *within* Store B, since an
LLM-inferred "seems to dislike verbose output" and a stated "never use emoji"
are not the same evidence — is a smaller change than any fusion machinery and
probably buys more. Ordinal also sidesteps a real trap: numeric confidence
from heterogeneous sources is **not commensurable** (Konieczny & Pino Pérez,
*JPL* 2011, §7.2) — a 0.8 from a log and a 0.8 from an extraction are
different objects.

### 4.5 Never let the model adjudicate this

Directly on your question, and the finding is stark: when sensor readings and
user claims conflict, models show **near-zero sensor trust** — Authority
Alignment Index **−0.805** — and the effect is **unchanged from 4B to 35B
parameters** (arXiv:2605.23938, preprint). *A model asked to weigh a machine
log against a stated preference will systematically pick the prose.* Exactly
backwards from your instinct, and not fixable by a bigger model.

Supporting evidence: models weigh a source's *relevance*, largely ignoring the
credibility markers humans use (Wan et al., ACL 2024); their verbalised
confidence is systematically overconfident with no elicitation fix (Xiong et
al., ICLR 2024); and sycophancy contaminates Store B **at the source**, since
asserted facts arrive through a channel with a known bias toward agreeing with
the user (Sharma et al., arXiv:2310.13548).

Meanwhile determinism wins on the measurement: moving recency comparison out
of the prompt into `max(serial)` took single-hop accuracy from 61% to **82%**
at 262K context, and the LLM's long-context collapse simply does not occur
(arXiv:2606.01435, preprint). **Gate deterministically; let the model only
explain the verdict.**

## 5. The counter-case, at full strength

- **Append-only alone does not work.** Mem0 #4956, filed *after* they went
  additive: contradictory memories about mutable state accumulate, and at
  retrieval the older may outrank the newer. §4.2 exists because of this.
- **Stale facts are a real harm.** The strongest advocate for write-time
  consolidation gives the mirror case: an assistant that still thinks the
  customer is on Postgres six weeks after they migrated. §4.2 covers exactly
  the mutable-state facts this describes.
- **"Show the model both" has a cost.** Chroma's context-rot work finds a
  *single* distractor degrades performance. This argues for the current-only
  default filter in §4.3 — do not cite context-rot in favour of showing both;
  a reviewer will catch it.
- **The temporal machinery may not be earning its keep.** One benchmark
  reports Zep/Graphiti at **7%** and Mem0 at **18%** on fact consolidation
  against **plain BM25 at 48%** — sophisticated supersession losing to keyword
  search on the task it was built for. *Unverified single source; treat as a
  reason to measure, not a conclusion.*

## 6. What this changes

**Packet 01 Phase B's curated core, as designed, crosses the MEM-01 line.**
It would render promoted durable facts *about the user* into Halbert's
`messages[0]` — making Halbert a second authority on exactly the facts
`CD-5` assigns to Haloysius.

The replacement: Halbert's ranker hands its **ranked claim keys** to
Haloysius, and Haloysius owns the fact. One authority, both trees keep their
purpose, and the R9 fence stays shut.

`FD-22`'s gate therefore stands for a better reason than "not reviewed yet" —
the design behind it was wrong. A test in
`tests/test_promotion_gates.py` enforces that `rank_candidates` has no
production caller, so this cannot be skipped silently.

## 7. Traps, each of which cost someone

1. **Unscoped contradiction search.** Require structural overlap — same
   endpoints, or one shared endpoint *and* the same relation — before any
   contradiction check.
2. **Two facts at different scopes are not two versions.** "Observed at 3am"
   and "told on Tuesday" are scopes. A shipped postmortem describes exactly
   this: two scoped preferences read as a change of mind, the correct one
   deleted, discovered weeks later as behavioural drift.
3. **Consolidation is a positive feedback loop with no error-correcting
   step.** If a consolidator reads its own output, cap the generations or tag
   derived records so they cannot be re-derived. This is how one hallucination
   became 808 entries.
4. **Deleting a source does not delete what it wrote into a summary.** Any
   derived narrative must be **regenerated, not patched**, when its sources
   change.
5. **Never reuse a retrieval threshold as a merge threshold.** Shipped values
   sit ~0.3 apart (0.6 cosine retrieval vs 0.9 Jaccard merge) and do opposite
   jobs — recall versus precision.
6. **Validity marks are worthless unless the read path honours them.** An
   audit across five agent-memory systems found invalidated facts still
   returned, still outranking their replacements, because retrieval never
   enforced the mark. Closing a window is half the work.
7. **Cosine similarity inverts on exactly the cases a conflict detector
   exists to catch.** Negation pairs score 0.930–0.999 and antonym pairs
   0.960–0.989, while genuinely *equivalent* sentences score 0.568–0.971 —
   contradictions rank **above** equivalences, and bi-encoders (what every
   vector store uses) are worst. Use it for candidate generation only; put a
   claim key or an NLI cross-encoder on the verdict.
8. **Never take a transitive closure over pairwise match decisions.** One
   published case: 157 false links became **1,574**; precision 0.73 → 0.23.
   Similarity is not transitive.
9. **A binary same/different test silently accepts an error rate nobody
   chose.** Fellegi & Sunter (1969) proved the optimal linkage rule has
   *three* outcomes, and the undecided zone is what makes the two error rates
   achievable at all. That is the formal justification for "ask, don't
   guess".
10. **Build the consumer first, or you will build the column and never wire
   it.** Letta's `BlockHistory.actor_type` has writers in `tests/` only and
   zero production readers; Cognee's provenance ledger is off by default with
   no readers. This is cross-cutting theme 1 of OSS pass 2 — *module ported,
   consumer never wired* — arrived at independently by someone reading four
   other codebases.

## 8. Founder decisions needed

**Revised 2026-09-10 after the in-house second read**
(`REVIEW-DUAL-MEMORY-INHOUSE-2026-09-10.md`). Ordered; the first two are
deletions, and each is small.

1. **Ratify that the split holds** — on the *deployable and ownership* ground
   in §1(b), **not** the "kinds of fact" argument, which was rationalisation
   and has been withdrawn.
2. **Replace the curated core** with ranked claim keys handed to Haloysius
   (§6). This is the entire response to the vendor evidence, and it turns
   `FD-22` from a checkpoint into a decision.
3. **Approve the §4.1 acquisition-mode partition** — observed versus asserted
   — replacing the fact-type table the first draft proposed.
4. **Approve the §4.2 merge-type declaration**: `LWW` / `SET` / `ASK`,
   defaulting to `SET`, with no supersession machinery outside `LWW`.
5. **Approve building the disagreement meter first** (§4.3), before any
   provenance column — including deferring the `ClaimStrength` generalisation
   until a retrieval filter reads it.

**Still open, and deliberately not decided here:**

- **Whose namespace are the claim keys?** Decision 2 hands keys to Haloysius,
  which makes Halbert the de-facto schema author. That may be wrong. It is the
  one unresolved seam in the recommended path.
- **Cross-store ordering for `LWW`** when both stores hold the same functional
  predicate. Fenced off in §4.2 until answered.
- **Fable's Q1 and Q3** — whether "merge" is the wrong verb entirely, and
  whether there is a failure worse than the classifier problem. The in-house
  read deliberately went unsent to Fable so the second opinion stays
  unbiased.

## 9. Verification notes

Verified directly in a browser: the OpenAI Memory FAQ quotes in §1. Verified
against primary sources by the research pass: the Mem0 PR and issue numbers,
the Graphiti issues, the arXiv abstracts, the Cognee source comment, Home
Assistant's `core.py` and `helpers/service.py`, Claude Code's memory docs.

Verified in this tree on 2026-09-10: `continuity/freshness.py:13-15`,
`continuity/state_store.py:18`, `persona/claims.py:22-26` — §4.0 and §4.4's
closing recommendation both rest on code that already exists.

The refereed spine is solid: JASA 1969, JSL 1985, KR 2006, PVLDB 2009/2013,
*Ann. Statist.* 2009, KDD 2015, ACL/ICLR 2024.

**Unverified, flagged inline:** Informatica MDM's trust decay (§4.4), the
BM25-beats-temporal benchmark (§5), and the 2026 agent-memory items
(authority inversion, deterministic freshness, the dual-stream clinical
paper) — all unrefereed preprints, several single-author, with numbers no
third party has reproduced. They are used for **framing and mechanism**, where
they are strong; their figures are claims, not results.

**Also worth knowing:** published memory benchmarks are contested. Three
incompatible figures exist for one system depending on who ran it, a quarter
of one benchmark's questions have no ground truth, and full-context beats
every memory system on one vendor's own table. Build our own conflict
measurement rather than trusting a leaderboard.
