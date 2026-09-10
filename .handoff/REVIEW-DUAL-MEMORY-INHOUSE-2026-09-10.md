# Dual-memory boundary — in-house second read

**Status:** review of `DESIGN-MEMORY-BOUNDARY-2026-09-10.md` §4–§6 and the
Fable handoff, 2026-09-10. Answers the handoff's §6 questions 2, 4, 5 so Fable
can spend its credits on 1 and 3. Founder decision still pending on §8.
**Not sent to Fable** — it is the founder's decision input, and sending it
would bias the second opinion the handoff exists to get.

Verified in tree before writing: `continuity/freshness.py:13-15`,
`continuity/state_store.py:18`, `persona/claims.py:22-26`, and
`rank_candidates` has callers only in `tests/`. `MEM-01`, `CD-5`, `FD-22`
exist in `DECISIONS.md` as the memo describes.

---

## 1. The one finding that changes the shape

**§4a indicts the curated core, not the two-store split.**

Mem0 and OpenAI each collapsed two stores that held the *same predicates* and
*competed for the same prompt slot* at retrieval. That is the failure mode.
Halbert and Haloysius only do that in one place: Packet 01 Phase B's curated
core, which would render user facts into Halbert's `messages[0]` beside
whatever Haloysius says about the same user. §6 already deletes it.

So: deleting the curated core **is** the response to the vendor evidence.
After that deletion the split is outside the evidence's blast radius, and the
"kinds of fact vs capture routes" defence in §1 — which reads as
rationalisation, and Fable will say so — is not needed to carry the weight.

The sturdier leg, which the memo does not stand on: **Halbert and Haloysius
are two deployables with two lifecycles, two distribution contracts (the
subtractive two-dependency rule), and two ownership/privacy boundaries** (the
guest-persona ownership divide, the R9 fence). OpenAI's collapse was a
data-model simplification with no organisational cost. Ours would delete a
*product* boundary. Ratify §8.1 on that ground.

## 2. Answers to the handoff's §6, in-house

### Q2 — is the split defensible?
Yes, per §1 above. Note the memo's own §4.1 quietly *partitions by capture
route* (observed → Halbert, told → Haloysius), which is the thing it says
OpenAI did and we don't. That is fine — route-partition fails only when both
routes then compete for one slot — but it means the "kinds of fact" defence
is weaker than stated. Drop it; use the deployable/ownership defence.

### Q4 — what to research next
Sent to Fable as 6b.6–6b.11. The two we think matter most:
- **Cross-store ordering without a shared clock.** §4.2's "deterministic
  recency" is the weakest line in the design — `max(serial)` works inside one
  store; across two independently-writing stores a later timestamp can derive
  from an earlier conversation.
- **Update vs revision** (Katsuno–Mendelzon 1991). Every merge result cited in
  §4.4 is a *revision* operator. A preference that changed is *update*.
  Applying one to the other is a known category error.

### Q5 — what to delete from §5
**Fold §4.3 into §4.2 and delete the general supersession vocabulary.** If
single-writer (4.1) and functional predicates (4.2) do their jobs, then for
every *non*-functional predicate nothing is ever superseded — `superseded_by`
/ `superseded_at` are dead columns on the majority of rows, and the memo's own
trap 6 says validity marks the read path doesn't honour are worse than none.
Supersession only needs to exist for the functional set, which is already
ordered. Everything else is an append-only log with no supersession
vocabulary at all.

Also: **do not generalise `ClaimStrength` to memory facts until the retrieval
filter reads it** (trap 10, this repo's recurring defect). Ordinal is the right
shape; adding the column before the consumer is the wrong order.

## 3. The strongest argument against §5 (for the founder; Fable is asked for a stronger one)

**§4.1's single-writer partition is enforced by a classifier, so it is not
single-writer.** Home Assistant has one writer per entity because entity
identity is *structural* — the device writes its own entity. "My editor is
nvim" is host state if Halbert observed the process and a preference if the
user said it; the same sentence yields either, and an extractor decides. A
partition that depends on a fallible judgment call has the contradiction
problem back, one layer down.

Fix: partition by **acquisition mode** — *observed* (a probe, a log, a
process table) vs *asserted* (a sentence) — which is known with certainty at
write time. Then two things follow for free:

- **Never flatten attribution at read time.** The prompt gets *"my log shows A
  (observed 03:12); Haloysius reports B (asserted Tuesday)"* — two true
  statements that cannot contradict, not "A vs B, pick". This is also the only
  place §4.5's authority inversion can be countered: deterministic framing
  text, not a model judgment.
- **Step 0 needs a failure branch.** "Go look" is right; `freshness.py` returns
  a decision and the caller acts. When the probe cannot run (device gone,
  process exited, historical question) the memory answer must come back
  *stamped with its observation time*, not suppressed — otherwise the best line
  in the design degrades to "I don't know" exactly when memory is the only
  source.

## 4. Recommended path

In order. Each is small; 1–2 are deletions.

1. **Ratify §8.1 (split holds)** on the deployable/ownership ground, not
   "kinds of fact".
2. **Ratify §8.4: replace the curated core** with ranked claim keys →
   Haloysius. `FD-22` becomes a decision, not a checkpoint. This is the entire
   response to §4a.
3. **Revise §4.1: partition by acquisition mode**, not fact type. Update the
   §8.2 table's left column accordingly before approving it.
4. **Collapse §4.2 + §4.3 into one declaration: a merge type per predicate**
   — `LWW` (functional, recency-ordered *within* a store), `SET` (accumulate,
   attributed, never picked), `ASK` (undecided zone, trap 9). Default is
   `SET`. Unlisted never silently picks. No supersession machinery outside
   `LWW`.
5. **Attributed read path.** Both stores render as nested claims with source
   and time; no flattening; deterministic framing. Gate here, per §4.5.
6. **Build one consumer before any column: the disagreement meter.**
   Per-claim-key rate at which the two stores disagree, surfaced (a) as a
   health signal and (b) as the discovery mechanism for predicates behaving
   functionally in the data — candidates for `LWW`. This answers §8.3 ("who
   maintains the list") with *the data proposes, the founder ratifies*, and
   it satisfies trap 10 by giving the conflict machinery a consumer that is
   not "resolve it".
7. Everything else (ClaimStrength generalisation, provenance typing within
   Store B, the ask UX) waits for Fable's Q1/Q3 and for a consumer.

## 5. What this does not decide

- Whether the claim-key namespace is Halbert's, Haloysius's, or a third
  artifact (Fable 6b.8). Step 2 above hands keys to Haloysius, which makes
  Halbert the de-facto schema author. That may be wrong; it is the one open
  seam in the recommended path.
- Cross-store ordering for `LWW` when both stores hold the same functional
  predicate (Fable 6b.6). Until answered, `LWW` orders within a store only and
  cross-store disagreement on a functional key routes to `ASK`.
