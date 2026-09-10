# The disagreement meter

**A portable design.** Written so a team that is not Halbert's can evaluate it.
Halbert is the first instance; nothing below depends on Halbert's internals.

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

1. **A shared claim key.** Some canonical way to say two beliefs are *about
   the same thing*. A `(subject, predicate)` pair is enough. This is the only
   hard prerequisite, and if the two sources cannot agree on a key vocabulary,
   the meter tells you that first — which is itself the most useful thing it
   could tell you.
2. **A read path to each source.** Read-only. No schema change.
3. **A value comparison** for a given predicate. Start with exact equality and
   let the meter report how often that is too crude; do **not** start with
   embedding similarity (see §7).

Notably absent from that list: a confidence score, a trust weight, a
timestamp ordering, or a resolution policy. It needs none of them, which is
why it can be built before any of them exist.

## 5. What it emits

Per claim key, over a window:

- **Disagreement rate** — how often the sources hold different values.
- **Agreement rate** — with a warning attached, see §7.
- **Absence pattern** — how often only one source has an opinion at all. Often
  the largest bucket, and usually the least interesting, which is worth
  knowing before you budget for a resolver.
- **Churn** — how often a single source changes its own value. High churn with
  low cross-source disagreement means the predicate is *volatile*, not
  *contested*.

## 6. The two things it buys you

**(a) A health signal.** A disagreement rate that climbs is a real alarm — a
source degrading, an extractor regressing, a key collision. Nobody currently
has this. Systems discover their reconciliation is broken through user reports
months later.

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
2. **Never treat agreement between two sources as corroboration** unless you
   have established they are independent. If one source's contents derive from
   material the other also saw, they are dependent, and reliability-weighting
   dependent sources is documented to perform **worse than plain voting**.
   Copy detection provably cannot see the dependency when the copied source is
   accurate. The meter should report agreement *with the dependency status
   attached*, or not report it as evidence at all.
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
   Keep the write capability out of the module, not merely unused.

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

## 9. The second-instance question

This document exists because a mechanism that is right for one system is worth
generalising only when a *second* concrete instance wants it — and generalising
from one instance produces an abstraction shaped like that instance.

If your system has:

- two or more sources of belief about the same subjects,
- a claim key you could agree on, and
- an open question about which source wins,

…then the meter is likely to apply, and the two implementations are worth
generalising *from both* rather than lifting one into the other.

**Concretely, what we would want to know from a second instance:**

1. Does your claim key survive contact with ours? A `(subject, predicate)`
   pair is our assumption and it may be parochial.
2. Do you need per-context keys? Our sharpest open problem is that "observed
   at 03:12" and "asserted on Tuesday" are **scopes**, not versions — and a
   meter that reports them as disagreement is measuring the wrong thing.
3. Is your value comparison per-predicate or global? We expect per-predicate
   and have not built it.
4. Do you have the independence problem (trap 2), or are your sources
   genuinely independent? If yours are independent, you can do things with
   agreement that we cannot, and the shared module needs to express the
   difference rather than assume ours.

**Precedent for how this would go:** a named-gate admission record was
generalised across two applications this way — one instance produced denial
reason codes and a gate-graph record, the second adopted the same shape from
its own direction, and the two together justified the module. The rule learned
there is worth repeating: **keep the layers separate.** That record gates
*capability*; the parallel warrant layer gates *legitimacy*; neither is
chained behind the other. A disagreement meter should likewise not be fused to
whatever resolution policy either system eventually adopts.

## 10. What this deliberately does not decide

- **Which source wins.** By construction.
- **Whether to merge at all.** The meter is compatible with never merging, and
  its output is what would justify either choice.
- **How to order events across sources.** Ordering within one source is
  usually available; ordering *across* two independently-writing sources is a
  genuinely open problem — a later timestamp can derive from an earlier
  event — and the meter should report cross-source disagreement on an ordered
  predicate as *undecided*, not resolve it.
