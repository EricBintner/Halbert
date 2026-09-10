# The disagreement meter

**A portable design, revised 2026-09-10 against a second instance.** DebateHaus
replied (`REPLY-DISAGREEMENT-METER-2026-09-10.md`, their repo) and the reply
changed this document in six places, each marked **[R-DM-n]**. Their answers to
§9 were mostly *not* the ones hoped for, which is what made them worth having.

Two instances now exist, so the abstraction below is generalised **from both**
rather than lifted from ours.

---

## 1. In one paragraph

When a system holds beliefs about the same subject from two or more sources,
those beliefs will sometimes differ. The instinct is to build a resolver. The
disagreement meter is the thing you should build *instead*, first: a
deterministic instrument that measures **how often, and about what, the
sources disagree** — and deliberately does not resolve anything. It is cheap,
it cannot corrupt data because it never writes to the belief stores, and its
output is the evidence you need before any resolution policy can be written
honestly.

## 2. The problem it addresses

Two independent belief sources about one subject produce three failure modes,
and only one of them is a contradiction:

| What it looks like | What it usually is |
|---|---|
| A says X, B says Y | **Context partition** — both true, in unstated contexts |
| A said X, now B says Y | **Change** — the world moved; nobody was wrong |
| A says X, B says Y | **Contradiction** — the residual, and the smallest class |

Systems that jump to a resolver treat all three as the third. The published
consequences are severe: one production knowledge graph had **41% of its facts
marked invalid** by an over-eager contradiction pass; one memory store
accumulated **808 entries asserting a fabricated preference** — 191 exact
duplicates — from a single hallucination re-extracted from its own output. A
controlled study found that continuously consolidating memory drives utility
*below the no-memory baseline*.

**The meter exists because you cannot write a resolution policy for a
distribution you have never measured.**

## 3. The design property that matters

**It is a consumer of conflict information whose job is not to resolve
conflict.**

That sentence is the whole design. It is what makes the meter safe to build
before any of the hard decisions are made, and it is what distinguishes it
from every mechanism it superficially resembles:

- It **never writes** to either belief store. No supersession, no
  invalidation, no delete. A bug in the meter costs you a wrong number, never
  a lost fact.
- It **contains no model**. Disagreement is computed from keys and values, not
  judged. (This matters more than it sounds: asked to weigh a sensor reading
  against a stated claim, models show near-zero sensor trust — Authority
  Alignment Index −0.805 — and the effect is unchanged from 4B to 35B
  parameters. Any model in this loop would systematically believe the prose.)
- It **has no authority ordering**. It does not know or care which source is
  more reliable. That is exactly the decision it exists to inform.

## 4. What it needs from a host system

Three things, and only three:

1. **A correspondence function** — how you decide two beliefs are *about the
   same thing*. **[R-DM-1]** The first draft said "a shared claim key, a
   `(subject, predicate)` pair is enough", which assumed the key matches
   exactly. DebateHaus's layer-1 key is `(discussionId, span±ε, type, label)`
   — **time-indexed and fuzzy in the key itself**, with a grace window on
   interval overlap. Their observation is the one structural correction to
   this design:

   > Your design puts all the fuzziness in the value comparison and assumes
   > the key matches exactly. We need fuzzy *correspondence* and fuzzy
   > *value*, as two separate tolerances.

   So both are **per-predicate injected functions**, not one assumption:

   ```
   correspond(a, b) -> same | different | undecided
   compare(a, b)    -> same | different | undecided
   ```

   Exact equality is `correspond` with a tolerance of zero — a special case,
   not the general one. This also answers the old §9 Q3 more completely than
   it was asked: per-predicate, **on the key as well as the value**.

   If the two sources cannot agree on a key vocabulary at all, the meter tells
   you that first — which is itself the most useful thing it could tell you.
   *Confirmed empirically:* DebateHaus discovered they fail this prerequisite
   outright (events written to random Firestore ids, so two analysis runs
   produce two incomparable belief sets and a re-run silently doubles a user's
   annotations) **without building anything.**
2. **A read path to each source.** Read-only. No schema change.
3. **An interpretation of what a rising rate means** — supplied by the
   consumer, see §6.

Notably absent from that list: a confidence score, a trust weight, a
timestamp ordering, or a resolution policy. It needs none of them, which is
why it can be built before any of them exist.

## 5. What it emits

**The outcome vocabulary is frozen [R-DM-7]**, because vocabulary drift is
what would make a later shared module impossible, and agreeing it costs
nothing today:

`agree · partition · change · contradict · absent · undecided`

Per claim key, over a window:

- **Disagreement rate** — how often the sources hold different values.
- **Agreement rate** — reported **with its dependency status attached**, or
  not reported as evidence at all (§7 trap 2).
- **Absence** — **[R-DM-3]** first-class, with a **direction** (*which* source
  was silent) and a **not-yet versus never-answered** distinction. The first
  draft called this "often the largest bucket, and usually the least
  interesting". For a single mind that is right — it means one store had not
  learned something. Between two debaters it means *"you did not answer
  that"*, which is the oldest scoring rule in adjudicated debate and possibly
  the most valuable metric the product could emit. Neither the direction nor
  the not-yet/never split was expressible in the first draft's shape.
- **Partition** — **[R-DM-4]** a reported, surfaceable outcome, not merely
  the thing to avoid mistaking for a contradiction. For Halbert it is the
  sharpest open problem (scopes, not versions). For a debate product,
  *"you two are using that word differently"* is the highest-value
  intervention available and is currently invisible.
- **Churn** — how often a single source changes its own value. High churn with
  low cross-source disagreement means the predicate is *volatile*, not
  *contested*.

## 6. The two things it buys you

**(a) A signal whose *meaning is supplied by the consumer* [R-DM-2].** The
first draft asserted that "a disagreement rate that climbs is a real alarm".
That is a true statement about a memory system and a **false** one about a
debate — between two people, a rising rate means a good argument. So the
instrument emits the rate; *what a rising rate means* is a consumer-supplied
interpretation and must never be a constant baked into the module.

For a memory system it is an alarm: a source degrading, an extractor
regressing, a key collision. Nobody currently has this — systems discover
their reconciliation is broken through user reports months later. *Confirmed:*
DebateHaus found a live key collision by reading this section — their dedupe
key omits `labels`, so two events at the same half-second with different
labels collapse and the loser's labels are silently discarded.

**(b) Functional-predicate discovery, which is the valuable one.**

The hardest question in any two-source design is: *for which predicates does a
new value replace an old one, and for which do both stay true?* "Likes tea"
and "likes coffee" conflict only if `likes` is single-valued. **No system can
infer cardinality**, and every system that guesses gets it wrong in both
directions — over-collapsing distinct facts, and under-collapsing stale ones.

The usual answer is a hand-maintained list, which is incomplete on day one and
stays incomplete. The meter replaces that with **the data proposes, a human
ratifies**: predicates whose values behave functionally in the observed
distribution surface as candidates. The list stops being something someone
must imagine in advance and becomes something the system nominates from
evidence.

## 7. Traps, each of which has cost someone

1. **Do not use embedding similarity as the same-value test.** Cosine
   similarity *inverts* on exactly the cases a disagreement detector exists to
   catch: negation pairs score 0.930–0.999 and antonym pairs 0.960–0.989,
   while genuinely *equivalent* sentences score 0.568–0.971 — contradictions
   rank **above** equivalences. Bi-encoders, which most vector stores use, are
   worst. Use similarity for candidate generation only.
2. **Assume dependence. [R-DM-5]** The first draft said "never treat agreement
   as corroboration *unless you have established they are independent*", which
   made independence the thing you opt out of. DebateHaus inverted it, and
   they are right:

   > You should assume dependence, not independence, in the shared design. If
   > a future instance has genuinely independent sources it can opt into
   > corroboration; a module that assumes independence and is wrong produces
   > confident nonsense.

   Their layer-1 sources are *the same model* run over *overlapping text*, and
   their dedupe rule is a reliability weighting over dependent sources — the
   exact configuration documented to perform **worse than plain voting**. Copy
   detection provably cannot see the dependency when the copied source is
   accurate. **Corroboration is opt-in and must be justified; the default is
   that agreement means nothing.**
3. **Do not take a transitive closure over pairwise decisions.** One published
   case turned 157 false links into **1,574**; precision 0.73 → 0.23.
   Similarity is not transitive.
4. **A binary same/different test silently accepts an error rate nobody
   chose.** Fellegi & Sunter proved in 1969 that the optimal linkage rule has
   *three* outcomes, and the undecided zone is what makes the two error rates
   achievable at all. Give the meter an explicit *undecided* bucket rather
   than forcing every comparison.
5. **Resist adding resolution.** The moment the meter can write, it stops
   being safe to run and starts needing the decisions it exists to inform.
   Keep the write capability out of the module, not merely unused. (What
   happens when you eventually *do* need to act is §8.1.)

**The traps are a conformance suite, not advice. [R-DM-6]** Each becomes named,
language-neutral test vectors: negation pairs that must **not** score as
equivalent (trap 1), a transitivity case that must **not** close (trap 3), a
three-outcome case that must land `undecided` (trap 4). Two codebases in two
languages can run them against their own implementations tomorrow, and any
future shared module inherits them as its acceptance criteria. DebateHaus
rates this the highest-value shared artifact and puts it **ahead of adopting
any code** — trap 1 alone is existential for them, since the two central
claims of a debate are frequently exact negations of each other, so a naive
embedding check would score the crux of the debate as *agreement* and the
product would fail hardest on its best debates.

## 8. Why this shape, and not a resolver

The field's revealed preference is against resolvers, recently and at scale.
In 2026 the two most-cited multi-store memory systems both **removed a store**
rather than reconcile between them — one going append-only and deleting its
graph integration, the other replacing an explicit store with a single
synthesized summary, citing contradictions it could not resolve. Meanwhile
across five surveyed memory systems, published conflict-resolution scores run
from 7% to 54% single-hop and *at most 6% multi-hop*; in one benchmark, plain
keyword search outscored every purpose-built temporal mechanism on the exact
task those mechanisms were built for.

The honest reading is not "reconciliation is impossible". It is that **the
field is building resolvers before it has instruments**, and the resolvers are
failing in ways nobody is positioned to notice. The meter is the instrument.

### 8.1 Where the meter sits: one ladder, six rungs [R-DM-8]

DebateHaus's largest contribution. The through-line both instances share:
**two propositions are related, but you do not yet know how, and the discipline
is to characterise the relation before acquiring the standing to act on it.**
Halbert calls the acting "resolution"; DebateHaus calls it "the moderator
speaks". Same act, same hazard.

| # | Rung | The question | State it produces |
|---|---|---|---|
| 0 | **Correspondence** | are these two beliefs about the same thing? | keyed / unkeyed |
| 1 | **Comparison** | do their values match? | same / different / **undecided** |
| 2 | **Relation** | how do they stand? | agree · partition · change · contradict · absent · undecided |
| 3 | **Characterisation** | *why* — which predicate, which unstated context? | a named reason, or none |
| 4 | **Standing** | may anything act, and under whose rule? | granted(rule) / withheld / hand-over |
| 5 | **Act** | say it, and put the citation on the record | an event carrying its rule |

**Each rung is a separate module and none may be skipped.** The meter is rungs
0–2, and it stops at 2 **on purpose**.

The striking finding is that across the family, each application has built a
**different, non-overlapping half**:

- **This design / the engine** — rungs 0–2, and refuses 3–5 by construction.
- **The DebateHaus moderator** — rungs 4–5 built (a warrant, a mandate, a
  citation on the stored row), with **nothing at 0–2**; its blockers are all
  *"we cannot form a belief in the first place"*.
- **The DebateHaus analyzer** — built the bottom and then **jumped straight to
  5**, acting on an unmeasured correspondence with no standing layer at all.
- **Rung 3 is unbuilt by anyone.**

### 8.2 Rung 3 is the shared frontier, and it is the same computation

- Halbert wants: *"these disagree because the predicate is scoped and the
  scope is unstated"* — this design's sharpest open problem.
- DebateHaus wants: *"these two debaters disagree because they are using this
  word in two senses"* — the best intervention their moderator could make.

**Those are one computation:** given a corresponded pair that reads as a
contradiction, decide whether an unstated context makes both true. It is the
one rung neither party has started, so neither has an existing shape to
unpick. Two constraints from their side, before anyone writes a line: it must
be **model-free, or model-bounded with the §3 discipline visible** — in a
debate *both* inputs are prose and *both* are adversarial, and a model in this
loop believes the prose; and its output must be **a reason, not a verdict**,
consumable at rung 4 by something that independently decides whether anyone
may say it aloud.

### 8.3 What happens when you *do* need to act [R-DM-9]

Trap 5 says keep the write capability out of the module. It says what must not
happen and leaves *"and then what?"* unanswered. DebateHaus supplied the
missing half: **their warrant is rung 4**, built and tested — five frozen
fields, a mandate derived from the agreement that can only narrow it, denial
**by name rather than by absence**, enforcement at two points because a model
imitates calls it saw earlier, and the citation riding onto the stored row so
*"by what right?"* is answerable without re-running anything. A refusal is a
`200` with a citable reason: the mechanism working, not a failure — the same
stance trap 5 takes toward not resolving.

**The boundary rule, in their words, and it is the sharpest sentence in the
exchange:**

> **Meter where you do not yet know who wins. Gate where legitimacy is already
> decided.** Rung 2 must have no authority ordering. Rung 4 must have nothing
> *but* an authority ordering. **Fusing them produces a resolver that cites
> itself.**

The corollary matters as much: some things that *look* like two sources
disagreeing about one subject should **not** get a meter. Their
mandate-versus-emitted-type check is correctly a fail-closed gate, because the
participants already decided. Knowing where not to put the instrument is part
of the design.

## 9. The second-instance question — answered once, still open

**Answered 2026-09-10 by DebateHaus.** They turn out to be *two* instances in
one product, with **opposite value signs**: a machine-internal layer (several
detectors disagreeing about one utterance) that is this problem in a costume
and would use the meter unchanged, and a product layer (two humans disagreeing)
where **disagreement is not a defect signal, it is the content**. Having both
in one deployment is what forced the generalisations above — a health signal
whose meaning is supplied rather than assumed, and an absence class with a
direction.

Their answers to the four questions, and none was the hoped-for one:

| | Asked | Answered |
|---|---|---|
| Q1 | Does our claim key survive? | **Partly.** Theirs is time-indexed and fuzzy *in the key*. → R-DM-1 |
| Q2 | Do you need per-context keys? | **Yes, and the harder form** — the context is *unstated*. → R-DM-4 |
| Q3 | Per-predicate or global comparison? | **Per-predicate**, with evidence: their per-label threshold table was **dead code for its entire life**, not merely incomplete but *inert* |
| Q4 | Are your sources independent? | **No, in the worst available form** — the same model over overlapping text. → R-DM-5 |

**A third instance is still worth having**, and the questions for it are now
sharper. If your system has two or more sources of belief about the same
subjects and an open question about which wins, the ones we would ask are:

1. Is your `correspond` exact, fuzzy, or something neither instance has —
   probabilistic, transitive, hierarchical?
2. Is your rising-rate interpretation alarm, content, or something else?
3. Does your absence class need a direction, and does *not-yet* differ from
   *never*?
4. Where does your rung 4 live, if you have one at all?

**Reuse posture, agreed with DebateHaus: share the contract and the
conformance vectors, not the module — for now.** The languages differ, the
deployment shapes differ, and rung 0 is a genuinely different function in each
instance. What is shared today: the frozen outcome vocabulary, the metric names
and denominators, the traps as language-neutral test vectors, and the
refusal-to-act contract. §4's injectable `correspond`/`compare` is what would
make a shared module real later.

## 10. What this deliberately does not decide

- **Which source wins.** By construction.
- **Whether to merge at all.** The meter is compatible with never merging, and
  its output is what would justify either choice.
- **How to order events across sources.** Ordering within one source is
  usually available; ordering *across* two independently-writing sources is a
  genuinely open problem — a later timestamp can derive from an earlier
  event — and the meter should report cross-source disagreement on an ordered
  predicate as *undecided*, not resolve it.
