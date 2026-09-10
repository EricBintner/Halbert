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

The instinct is right; a trust score is the wrong expression of it. **Nobody
in shipped agent memory resolves conflicts by provenance — everybody resolves
by recency.** Provenance fields exist in four of five systems whose source was
read and feed no ranker anywhere.

Where provenance *does* ship, it is a **write-time authorization** boundary,
not a read-time truth weight. Home Assistant: a null `context.user_id` means
"no human caused this" and skips the permission check. Letta: `read_only` is
derived from origin. **Claude Code — the product we are using — splits two
stores by author and weights them by context budget**: the human-written file
loads in full; the model-written store loads as a capped index. Plus
write-time deference: *"Claude skips anything your CLAUDE.md files already
say."*

So express the weighting as **budget and write-time precedence**, not a score.
Nothing to miscalibrate, and it is shipped prior art.

If we ever do want a numeric weight, the only mature precedent is Informatica
MDM's per-source trust with time decay (Maximum Trust, Minimum Trust, Decay
Period, curve) — which would say *"a machine reading from three seconds ago
beats a user claim from last March"* far better than a flat multiplier. **That
source is unverified — it blocks automated fetch and needs a manual look
before anyone builds on it.**

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
6. **Build the consumer first, or you will build the column and never wire
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

**Unverified, flagged inline:** Informatica MDM's trust decay (§4.4), the
BM25-beats-temporal benchmark (§5). Neither is load-bearing for the
recommendation; both would strengthen or weaken specific claims.
