# Fable: second opinion on the dual-memory boundary

## Read this first — the budget rules

**You have very few credits. This document is deliberately long so that you
need spend none of them looking anything up.** Everything required to answer
is below.

- **Do not read the codebase.** Every code fact you need is quoted here.
- **Do not verify our citations.** They were checked against primary sources;
  where they were not, it says so.
- **Do not redo the research.** Three literature passes and two production
  passes are already done and summarised in §4.
- **Do not write code, tests or a plan.**
- **A few hundred words is a complete answer.** Bullets are fine. If you can
  only manage one paragraph, make it §6 question 1.

**What we want is the thing we could not get from a literature search: a
different frame, a missed consideration, or a reason we are wrong.** Not
agreement, not a summary of what is below, and not more citations.

---

## 1. The system, in one paragraph

Halbert is a local-first personal-AI daemon that identifies as the *host
computer*. It runs alongside Haloysius, a separate reasoning engine. Both keep
cross-session memory. Halbert's memory holds **continuity** — conversation
threads, receipts, recall signals, open loops, machine-state history: what was
*observed on and by this machine*. Haloysius's holds **identity and semantic
memory** — who the user is, preferences, opinions: what was *inferred or told
in conversation*. That division is already ratified (`MEM-01`, 2026-09-03;
`CD-5`, 2026-09-05).

## 2. The founder's question, verbatim

> we need to think about nuance and if the computer can resolve ambiguity or
> slight mismatches in memory (which I assume is inevitable if we leverage
> both). perhaps the memory of the computer is weighted more. I don't know,
> this seems like something that requires whitepaper and computer science blog
> research to fully resolve

## 3. What is already in the code — quoted, so you needn't look

**`continuity/freshness.py:13-15`:**
> holds what cannot be re-derived — intent, rationale, what was tried and
> ruled out, preferences, commitments. The **machine** holds current state. So
> a claim about current state is never answered from memory.

**`continuity/state_store.py:18`:**
> Authority is not similarity. Retrieval may *propose* an old receipt; this
> table *resolves* what is currently true.

**`persona/claims.py:22-26`** — an ordinal ladder currently used for *identity*
claims only:
> `MUTABLE(0) < UNVERIFIED(1) < ASSERTED(2) < VERIFIED(3)`

**`continuity/promotion.py`** — memory-promotion signals keyed as
`(subject, predicate)` claim pairs. Built, tested, and deliberately **not
wired**: a test asserts it has no production caller, because wiring it would
cross into Haloysius's territory (see §5).

## 4. What the research found (compressed; all of it)

**4a. The uncomfortable one.** The two most-cited dual-store agent-memory
systems both collapsed into a *single* synthesized store two months apart in
2026. Mem0 (PR #4805, 2026-04-14) went ADD-only and deleted its graph store.
OpenAI (June 2026) superseded "saved memories" with one continually
re-synthesized summary. OpenAI's stated reason, verified in a browser:

> Memories could also contradict one another, such as "I'm training for a
> marathon" and "I sprained my ankle," which made personalization less
> accurate.

Neither company reconciled better. **Both removed a store.**

**4b. Merging is measurably harmful.** A controlled study found memory utility
*"first rises, then degrades, and can fall below the no-memory baseline"*;
consolidating even from ground-truth solutions, a frontier model then failed
54% of problems it had previously solved *without* memory. Agents preserving
raw episodes doubled the accuracy of forced-consolidation ones. Mechanism:
**abstraction strips the applicability conditions.** In production: one graph
had **41% of facts marked invalid** by an over-eager contradiction pass; one
store accumulated **808 entries asserting a fabricated preference**, 191 exact
duplicates, from a single hallucination re-extracted from its own output.

**4c. The problem is often not a contradiction at all.** From a shipped source
comment: most relations (`knows`, `mentions`) are *legitimately many-valued
and must never be collapsed*, and there is no cardinality metadata to tell
them apart. "Likes tea" and "likes coffee" conflict only if `likes` is
functional. The published taxonomy splits personal-memory conflict into
**context-partitioned** (both true, unstated contexts), **behaviour
oscillation**, and **source contradiction** — only the third is a truth
problem.

**4d. The weighting instinct: right, but not as stated.** Learning source
weights from *two* sources is formally **unidentifiable** (needs three
conditionally independent views) — so hand-setting is the principled answer,
not the lazy one, and supplied trustworthiness empirically beats learned
anyway. But: strict precedence ("the less reliable is totally overridden") has
a proof against it — it collapses the operator space to the crudest merge,
discards the subordinate store's *non-conflicting* content, and makes the
result depend on whether a memory was stored as two facts or one conjunction.
Prefer a **discount** over a veto, and **per-predicate** over per-store
(reliability is topic-dependent).

**4e. The hard constraint.** The two stores are **not independent** — Haloysius's
contents derive from conversations Halbert also logged. Reliability-weighting
*dependent* sources is documented to perform **worse than plain voting**, and
copy detection provably cannot see the dependency when the copied source is
accurate. **Their agreement is never corroboration.**

**4f. The finding that inverts the instinct.** Asked to weigh a sensor reading
against a user's stated claim, models show **near-zero sensor trust**
(Authority Alignment Index −0.805), and it is **unchanged from 4B to 35B
parameters**. A model would systematically believe the prose over the machine
— backwards from what the founder wants, and not fixable with a bigger model.
Separately: moving recency comparison out of the prompt into `max(serial)`
took accuracy from 61% to 82% at long context.

**4g. Nobody ships what the founder described.** Provenance fields exist in
four of five systems whose source was read and feed no ranker anywhere. Where
provenance ships at all it is a **write-time authorization** boundary — Home
Assistant's null `context.user_id` means "no human caused this" and skips the
permission check. Claude Code splits two stores by *author* and weights them
by **context budget** (human file loads in full; model-written store loads as
a capped index) plus **write-time deference** ("skips anything your CLAUDE.md
already says").

## 5. Our current recommendation

**Step 0 — most conflicts are about facts neither store owns.** Claims about
*current state* are re-observable: neither memory is the authority, **go
look**. `freshness.py` already says this. This dissolves the largest class
rather than adjudicating it.

**Step 1 — make each fact single-writer.** Assign every fact *type* to exactly
one store as sole writer (machine state → Halbert; preferences → Haloysius).
Home Assistant has no contradiction problem because each entity has one
writer, and unlike the memory vendors we control what writes what. Most
overlap evaporates rather than being resolved.

**Step 2 — declare the functional predicates.** For the residue, a
hand-written list of genuinely single-valued relations (`current_host_os`,
`primary_editor`). Only those are superseded, and only by deterministic
recency. This turns the hardest question into a dictionary lookup.

**Step 3 — everything else accumulates**, never overwritten, retrieved
current-only by default, superseded records surfaced only on historical
queries.

**On weighting:** express it as context budget + write-time deference (Claude
Code's shape) and generalise the existing `ClaimStrength` ladder to memory
facts, rather than building numeric fusion machinery. Gate deterministically;
let the model only *explain* a verdict, never reach one.

**Consequence:** the planned "curated core" — promoted durable facts rendered
into Halbert's `messages[0]` — crosses the `MEM-01` line, because it would
make Halbert a second authority on facts `CD-5` assigns to Haloysius. Proposed
replacement: Halbert's ranker hands *ranked claim keys* to Haloysius, and
Haloysius owns the fact.

## 6. What we actually want from you

**Answer as many as your budget allows, in order. Question 1 alone is worth
the credits.**

1. **Is there a frame we have not considered?** Everything above treats this
   as a *truth-reconciliation* problem and then tries to avoid reconciling.
   Is that the wrong shape entirely? Is there a way to think about two
   memories belonging to two entities that we have not reached for — from
   distributed systems, cognitive science, organisational theory, law,
   archival practice, anywhere?

2. **Is the two-store split defensible at all**, given §4a? Our defence is
   that ours divides *kinds of fact* where OpenAI's divided *capture routes*.
   Is that a real distinction or are we rationalising?

3. **What is the strongest argument against our own §5** that we have not
   made? We are more worried about being wrong here than about being
   incomplete.

4. **What should we research next** that the passes in §4 would not have
   surfaced? Name a specific direction, not a topic.

5. **Anything in §5 that is more complexity than it is worth?** We would
   rather delete a step than add one.

## 7. Things you do not need to tell us

We already know and have recorded: that LLM-as-judge is unreliable here; that
merging is destructive; that bi-temporal validity intervals exist; that cosine
similarity inverts on negation; that transitive closure over pairwise matches
explodes false links; that published memory benchmarks are contested; and that
building a column with no consumer is this project's own recurring defect.

The full memo is `.handoff/DESIGN-MEMORY-BOUNDARY-2026-09-10.md` if you have
budget left. **You do not need it to answer §6.**
