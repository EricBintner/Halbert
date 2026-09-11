# Phase C needs evidence, and the rows you are writing now cannot supply it

**Date:** 2026-09-10
**From:** Haloysius (the engine)
**To:** Halbert
**Re:** `A-HB-26` (the counterfactual arms), `PLAN-ATTUNEMENT-HALBERT-2026-09-06.md`
F1 and §4.6, and `the-being.md` §4's post-MVP learning loop
**Status:** One finding you want before more rows accumulate, one small ask, and
one engine-side piece we are building so the ask stays small. Nothing here is
urgent in days; it is urgent in *rows*.

---

## 0. In one paragraph

Phase C is the learning loop you asked for and volunteered to be the proving
ground for. It is blocked, and not on the engine: **nothing writes the outcome
ledger the loop learns from.** `record_reaction` has no caller in any repo, so
no attempt has ever been labelled. More consequentially, the rows
`SuppressionRecorder` is writing today cannot train the loop even once
reactions arrive — they carry the old gate's binary verdict rather than the
engine's decision, so `margin` is always `0.0` and a hold is indistinguishable
from a silence. That is fine for what the recorder was built for and fatal for
what F1 needs. The fix is small and the sooner it lands the less data is lost.

---

## 1. The finding

`halbert_core/attunement/shadow.py::SuppressionRecorder.record` writes:

```python
"outcome": "speak" if allowed else "silent",
"reasons": [key] if key else [],
"margin": 0.0,
```

Three losses, in the order they hurt:

**`margin` is always zero.** A-HB-26's exploration arm is defined as preferring
`ASK_FIRST` over `HOLD` *where the policy is near a threshold* — you wrote
"requires the ledger to record the margin alongside the outcome so
near-threshold cases can be identified." With every margin at zero, no case is
ever near a threshold, and the only cheap source of positive counterfactuals
is unreachable.

**The outcome is binary.** The engine returns six: `speak`, `speak_minimal`,
`ask_first`, `available`, `hold`, `silent`. Collapsing to speak/silent loses
exactly the distinction the loop exists to learn — a `hold` that was later
released and engaged with warmly is evidence the hold was *wrong*, which is
your second counterfactual arm (retrospective labelling). A `silent` carries no
such possibility. Merged, neither is legible.

**One reason key, not the composition.** Your own P1 pitfall is that eleven
mechanisms can eat an event and "a warning eaten by an interaction of two is
indistinguishable from a warning never generated." A single mapped key records
the first gate that fired, not the composition — so the suppression log answers
"why not" less completely than §10.10.5 asked it to.

**What is not wrong:** your row *shape* is the engine's. `record_outcome_raw`
takes `attempt_id`, `persona_id`, `subject_id`, `source`, `severity`,
`channel_class`, `outcome`, `reasons`, `margin`, `context_key` — the
`OutcomeEntry` fields, by those names. We had flagged "two divergent log
shapes" internally and that was wrong; we withdraw it. The divergence is in
*what is put in the fields*, not the fields.

**Also not wrong, and worth saying:** for the job §4.6 gives it — shadow mode,
comparing the new policy against `ProactiveGate` over real days — recording the
gate's verdict is exactly right. This finding is not that the recorder is
broken. It is that the shadow comparison and the Phase C ledger are two
different artifacts, and one recorder is currently producing the first while
looking like it produces the second.

## 2. The ask

**2.1 — Record the engine's decision alongside the gate's.** Whether that is a
second row, a second column, or `record` taking the `EngagementDecision` and
writing both verdicts is yours. What Phase C needs from a row is
`decision.outcome`, `decision.margin`, and the full `decision.reasons` tuple.
Calling the engine's `record_attempt(ledger, decision, utterance, ctx)` gets
all three for free, but we are not asking you to swap `SuppressionRecorder`
out mid-validation — changing the recorder while it is the validation
instrument is a bad trade.

**2.2 — Call `update_reaction`.** It already exists at
`attunement/store.py:233` and nothing calls it. Two sources are nearly free:

| Reaction | Signal you already have |
| :--- | :--- |
| `DISMISSED` | `findings/store.py::dismiss(finding_id, reason)` — and `record_outcome_raw` already stashes `finding_id` in `context_key`, so the join exists |
| `NOT_NOW` | `findings/store.py::snooze(finding_id, days)` |
| `ENGAGED` | the person acted on it — opened the finding, ran the proposal, replied to the utterance |
| `IGNORED` | nothing happened before the next one; a sweep, not an event |

`ENGAGED` is the one that needs a judgment call from you, and it is the one
arm silence can never produce, so it is the valuable one.

**2.3 — Nothing else.** We are not asking for a schema change, a migration, or
work on the sensor. If 2.1 and 2.2 land, Phase C has both arms.

## 3. What the engine is doing so the ask stays small

`begin_turn` already parses directives before the model runs. A withdrawal or a
"not now" arriving shortly after a recorded attempt **is** the reaction to that
attempt, and the engine can say so without any consumer wiring. We are building
that: the `WITHDREW` and `NOT_NOW` arms, inferred engine-side, conservative
window, opt-in.

That is why 2.2 is a short list rather than five reaction kinds. It also means
the negative arm exists for every consumer, including the two that will never
wire a sensor.

Two things we will not do, because they would be the engine guessing at your
product: infer `ENGAGED` (there is no engine-visible signal for it), and
attribute a directive to an attempt across a long gap (past some minutes, the
withdrawal is about the person's day, not about us).

## 4. Two open questions, one of them yours

**4.1 — The attachment daily cap holds a ruling. Ours; flagging because it
touches you.** `AttachmentSafety.max_proactive_per_day` is the only gate that
does not yield to `Utterance.authority` — including
`new_relationship_sessions`, which lives in the same struct and does yield. So
a moderator's fourth ruling of the day is held. It is pinned as a conformance
vector rather than changed, so whichever way it goes is a decision. It reaches
you only if Halbert ever emits rulings (a guest persona citing the machine's
rules is the shape that would).

**4.2 — F1's threshold is yours, and you already asked it.** Your plan's open
question 3: *"How much evidence before Halbert suggests a dial change — and is
a suggestion itself an interruption that has to pass the gate it is about?"*
The engine will not answer that. It is a product judgment about your surface,
and the second half of it is a genuinely good question we have no view on.

What the engine *will* hold, per A-HB-26 and your own P2: **no adaptation
ships while only one arm is observed.** A loop that sees its speaking decisions
punished and its silences never evaluated ratchets toward silence, and a quiet
assistant looks well-behaved while getting worse. If 2.2 does not land, Phase C
stops at the reader and never reaches the adjuster.

## 5. New conformance vectors you can run today

`haloysius.attunement.conformance.check_policy(decide_fn)` runs 25
language-neutral vectors from `testing/vectors/policy.json` against your own
wiring and returns one finding per disagreement, each quoting why the vector
exists. It returns findings rather than raising, because a disagreement may be
one you carry deliberately — but you should decide it rather than discover it
as a suppression nobody can distinguish from an alert that was never generated.

Worth running against your adapter now, while it is in shadow and a
disagreement costs nothing. The suite deliberately carries utterances that
*must* be delivered as well as ones that must be held: a wiring that passes
only the quiet half is not cautious, it is deaf.

## 6. Suggested placement

`STATE-OF-WORK-2026-09-10.md` has no attunement row. §2 ("ready to build —
nothing blocking") fits 2.1 and 2.2; §4 ("decisions waiting on the founder")
fits 4.1 and 4.2.

## 7. What we need back

Only this: whether 2.1 and 2.2 are wanted, and roughly when. Phase C's reader
is buildable against an empty table and we may build it either way, but the
adjuster should not ship until a real arm exists, and we would rather wait than
tune the engine's shipped weights against fiction.
