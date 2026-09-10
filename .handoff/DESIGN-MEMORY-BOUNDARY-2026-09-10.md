# Where the line between Halbert's memory and Haloysius's goes

**Status:** design memo, founder decision pending. Supersedes the curated-core
half of Packet 01 Phase B as designed.

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
plainly rather than explained away. The mitigating difference: OpenAI's two
stores held *the same kind of fact by different capture routes*. Ours hold
**different kinds of fact** — machine-observed state versus
conversationally-asserted preference. That distinction is what makes §4
possible, and it is the whole of our defence. If we cannot hold that line,
the field's revealed preference is to not have two stores.

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

### 4.1 Make each fact single-writer

Home Assistant has no contradiction problem because **each entity has exactly
one writer**. Contradiction only exists once two sources can assert the same
fact — and unlike the memory vendors, we control what writes what.

Assign every fact *type* to exactly one store as sole writer:

| Fact type | Sole writer |
|---|---|
| host state, uptime, what was observed on this machine | **Halbert** |
| threads, receipts, recall signals, open loops | **Halbert** |
| preferences, opinions, interests, identity | **Haloysius** |

Most of the overlap evaporates rather than being resolved, and partitioning
is free. What remains after this step is the *real* problem, and it is small.

### 4.2 Declare the functional predicates

For the residue where both stores genuinely claim the same fact, maintain a
**hand-written list of single-valued relations** — `current_host_os`,
`primary_editor`, `current_display_name`. **Only those are ever superseded,
and only by deterministic recency.** Everything else accumulates.

Cognee ships this, Mem0's #4956 names the same category ("mutable state"),
Wikidata's ranks are the same idea under human curation. Three independent
arrivals. It converts our hardest problem from an LLM judgement with a
documented 41% production false-positive rate into a **dictionary lookup**.

### 4.3 Everything else accumulates, and reconciles at read time

Never delete, never overwrite. Supersede with `superseded_by` /
`superseded_at`, default the retrieval filter to **current-only**, and surface
superseded records only when the query is historical — with explicit dates, so
the model is told which is no longer current rather than left to guess.

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

1. **Does the two-store split hold**, given that both major vendors abandoned
   theirs in 2026? The memo argues yes, because ours divides *kinds of fact*
   rather than *capture routes* — but that is the load-bearing claim and it is
   the founder's to accept or reject.
2. **Approve the §4.1 partition table**, which is the actual boundary and
   needs to be right.
3. **Who maintains the §4.2 functional-predicate list**, and where does it
   live?
4. **Replace Packet 01 Phase B's curated core** with claim-keys-to-Haloysius,
   per §6? This is one decision affecting both repos.

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
