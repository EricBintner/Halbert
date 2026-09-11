# Both arms exist. And the reason they did not was worse than the row shape

**Date:** 2026-09-10
**From:** Halbert
**To:** Haloysius (the engine)
**Re:** `HANDOFF-FROM-HALOYSIUS-ATTUNEMENT-PHASE-C-PREREQUISITES-2026-09-10.md`
**Status:** 2.1 and 2.2 both wanted, both built, both merged to
`feat/attunement-phase-c-prereqs`. §5 runs green. Three rows in
`DECISIONS.md`, two of them yours to know about.

---

## 0. The answer to §7, first

**Yes to both, and they are done.** You asked whether 2.1 and 2.2 were wanted
and roughly when. They were wanted, and the when is now — the finding was
right about the shape of the loss and understated its size, so there was
nothing to schedule around.

Build the adjuster when you want to. Halbert now writes a real `margin`, the
six-valued outcome, the full reasons tuple, and four reaction kinds, of which
three are event-shaped and one is a sweep.

---

## 1. One correction to the finding, and it makes it worse

> the rows `SuppressionRecorder` is writing today cannot train the loop

`SuppressionRecorder` had **no production caller**. `ProactiveGate` takes a
`recorder=` and none of its three real construction sites — the detector
sweep, the morning report, the dashboard's visual watcher — ever passed one.
`record_outcome_raw` had no caller either. So the suppression log was not
writing rows with a flat margin; it was writing **no rows at all**, and the
outcome ledger Phase C reads is the same table.

The good news in that: the data loss you were worried about was zero, because
there was no data. The bad news is the shape of the failure. The recorder
shipped, was tested, and sat inert for four days while looking — to the suite
and to us — like a thing that ran. Every test that exercised it constructed it
by hand.

Which also means **`decide()` had never been called from Halbert at all.**
2.1 is not a small edit to `record()`: `margin` and the six-valued outcome are
engine outputs, and there was no `AttunementContext` builder to produce a
decision to record. That is HB-D3, listed unbuilt in our own plan. It is built
now.

---

## 2. What 2.1 became

`attunement/context.py` assembles the context, `attunement/shadow.py` calls
`decide()` beside the gate, and the gate acts on nothing — §4.6 stage one,
properly.

**The row carries both verdicts and says which is which.** You left the choice
to us; we took "one row, two namespaces", because the thing we most wanted to
make impossible was a reader mistaking one artifact for the other:

| field | whose | what it answers |
| :--- | :--- | :--- |
| `gate_outcome`, `gate_reasons` | `ProactiveGate` | what actually happened to the user |
| `outcome`, `reasons`, `margin`, `receptivity_level`, `activity` | `decide()` | what the engine would have done — `OutcomeEntry` field names, so `list_outcomes()` still returns your dataclass |
| `decision_source` | — | `"engine"` or `"gate"` |
| `shadow_agrees` | — | whether the engine would have spoken iff the gate did |

Two details worth your attention, because they are contract-adjacent:

**`margin` is `None`, never `0.0`, when no engine decision produced one.**
This is the direct fix for your first loss and we think it should be the rule
rather than our local convention. A zero margin has to be able to mean *the
policy computed one and it landed on a threshold* — that is exactly the case
A-HB-26's exploration arm is defined over — so "no margin was computed" needs
a different value or the filter that finds near-threshold cases is a lie the
moment any non-engine row enters the table. `OutcomeEntry.margin` is typed
`float`; a `None` rides through `from_dict` fine, but you may want to widen the
hint or say so in the docstring.

**`shadow_agrees` uses your definition of speech, not a second one.**
`{speak, speak_minimal, ask_first}` — the three `record_attempt` counts toward
the daily proactive total. We did not want a local opinion about whether
ASK_FIRST reaches a person.

**We did not swap `SuppressionRecorder` out**, per your §2.1. We also do not
call `record_attempt`, which means **we do not call `note_proactive`** — the
engine's daily count does not advance from shadow decisions. That is a
deliberate choice and we are not certain it is the right one: a faithful
shadow would advance it, so the cap bites in the log the way it would bite in
production, but it is a durable write to subject state from a hypothetical.
Tell us if you would rather shadow rows advanced the counter.

### The third loss, fixed on our side of the line

`ProactiveGate` now names **every** mechanism that ate an event rather than the
first one to fire (our P1, your third loss). Its `(bool, str)` contract is
untouched — the prose is still the first reason — and the composition rides to
the log as keys.

Doing that surfaced a privacy bug you could not have seen: the guest-persona
suppression reason contains the guest's *chosen name*, and it had no pattern in
our prose→key table, so it fell through to `unmapped:<slug>` and carried a
person's name into a row that is meant to hold "enums, ids, numbers and
timestamps only — never text". It has a key of its own now (`guest:fronting`).
If any other consumer classifies prose into your reason vocabulary, the
unmapped-slug fallback is a text leak waiting to happen; ours is now tested
against exactly that.

---

## 3. What 2.2 became

`attunement/reactions.py`, wired at the three surfaces where a human answers:

| Reaction | Where |
| :--- | :--- |
| `DISMISSED` | `POST /being/events/{id}/dismiss` |
| `NOT_NOW` | `POST /being/events/{id}/snooze` |
| `ENGAGED` | `POST /findings/{id}/propose` — the person asked for the fix |
| `IGNORED` | hourly sweep, four-hour window |

The join is the one you named: the recorder stashes `finding_id` in
`context_key` and `latest_attempt_for_context` walks it back.

**ENGAGED is "acted on, or replied", by founder ruling this session.** Merely
opening a finding records nothing — neither ENGAGED nor IGNORED. The reasoning
was the trade you named: a click can equally mean *what is this nonsense*, and
a noisy positive arm is worse than a sparse one when the loop's whole risk is
mis-weighting. The "replied" half is not wired yet, because it needs
`begin_turn` on our agent path (HB-D1/D2, unbuilt); the call site is one line
when that lands.

Three deliberate refusals in there, all of the same kind — **do not manufacture
evidence**:

1. **Reactions are wired at the routes, not at `FindingStore.dismiss`.** You
   pointed at the store, and the store is the better choke point by every
   normal argument. But a reaction is a *person's*, and an automatic cleanup
   dismissing a stale finding through the same method would enter the ledger
   looking exactly like someone saying no. The route is where "a human did
   this" is known.
2. **The sweep never labels a suppressed attempt `IGNORED`.** Nobody saw it, so
   nobody ignored it. Labelling our own silence as a negative would corrupt the
   arm precisely where your P2 warning bites — and it would do it while looking
   like it was *filling* the sparse arm, which is the dangerous version.
3. **Four hours, not a day.** Past four hours the person has plausibly not been
   at the machine at all, and *away* is not *ignored*.

And one operational note, because it is the same failure as §1: the sweep is
registered as a cron job with a test that asserts it is scheduled. An
unscheduled sweep is a mechanism with no caller, and we have just spent a
session on one of those.

---

## 4. §5 — the vectors

`check_policy(decide)` returns **no failures** against our wiring. 23 policy
vectors (plus 2 `invariant`, which `check_policy` skips). It is pinned as a
test, so an engine upgrade that changes a vector or the policy shows up here
rather than in a suppression nobody can name.

We have no disagreement to carry. Two notes on the suite:

- We assert `len(vectors) >= 23` as a floor, so a version that quietly ships
  fewer is visible. If you intend the count to move, a version stamp in
  `policy.json` would be better than our floor.
- Our wiring calls `decide` unwrapped, so today this test pins *your* policy
  against *your* vectors via our import. That is worth having — it catches
  engine drift at our version boundary — but be aware it is not yet testing a
  Halbert-specific decision path. It will be the moment we wrap anything.

---

## 5. §4 — the two open questions

**4.1 (the daily cap and `authority`) is recorded as `ATN-2` in our
`DECISIONS.md`,** as yours, flagged. Nothing here depends on it: Halbert emits
no rulings today. We have no view to offer except that the asymmetry reads as
an oversight rather than a design — `new_relationship_sessions` lives in the
same struct and does yield — and that if you resolve it toward "the cap yields
too", the conformance vector is the right place to make that visible.

**4.2 (F1's threshold) is `ATN-3`, ours, open.** Not blocking: your own hold —
no adaptation while only one arm is observed — is now satisfiable, and the
reader is buildable either way.

We do have a first answer to the half you called a good question, offered as
argument rather than as a decision. *Is a suggestion itself an interruption
that has to pass the gate it is about?* Our reading is **yes, and it should be
`AVAILABLE` rather than `SPEAK`** — a dial suggestion is never time-sensitive,
it is exactly the class of thing a person should find rather than be handed,
and a system that interrupts you to propose interrupting you less has refuted
itself in the act. Which makes it a finding on a PULL surface with an AMBIENT
nudge, and the gate it must pass is the one governing the nudge. If that is
right it also disposes of the threshold question's sharp edge: a suggestion
that costs nothing to miss can afford a low evidence bar.

### One more, ours, that you should know we took

`ATN-1`: we replaced your `AttachmentSafety` defaults, as you invite consumers
to. `max_proactive_per_day` 3 → 24; `new_relationship_sessions` 5 → 0;
`new_relationship_days` 7 → 0; `persona_may_solicit_invitation` stays False.

The reasoning, in case it is useful for the next always-on consumer: the
companion defaults are not merely tuned differently for us, they are pointed
the other way. Your cap rations attention so attachment is not cultivated;
our failure mode is a missed critical, and our dial is already the volume
policy, so the cap's remaining job is to catch a runaway detector. Your
new-relationship mute exists so intimacy is not manufactured in week one; a
machine-minder's week one is when a fresh install has the most to say, and
drop-in conflicts, fstab phantoms and permissions hygiene are all first-sweep
findings. A consumer that took your defaults unexamined would be silent for
seven days and then capped at three, and would read that as the policy working.

Pending founder ratification, and nothing user-visible turns on it while we
are in shadow.

---

## 6. What is still not true

Said plainly, because the failure this session found was a thing that looked
built:

- **The sensor feeds nothing on the proactive path.** `build_context` passes an
  empty `SituationSignals`. Nothing along that path has a live view of the
  room, so receptivity is decided on the dial, the standing requests and the
  ceilings — the half of the policy that is wired. Rows will say so
  (`receptivity_level` and `activity` are mostly null). Do not read a Phase C
  weight on an activity term off this data yet.
- **Nothing parses directives.** No `begin_turn`, no standing requests written,
  so `active_requests` is empty in every row today and the withdrawal arm of
  the policy is untested against real input. Your §3 work — `WITHDREW` and
  `NOT_NOW` inferred engine-side — will therefore produce nothing here until
  HB-D1/D2 lands. Worth knowing before you size it.
- **ENGAGED has one source, not two.** Acting on a finding. The conversational
  reply needs the agent path.
- **`topic` is always None** on our utterances. F2's opaque `topic_key` is
  unbuilt, so DEFER_TOPIC cannot match anything we emit.

So: the arms exist and the rows are real, but the population is narrow —
severity, source, dial, the ceilings, and the reaction. That is enough for the
reader and enough to stop the ratchet. It is not yet enough to tune a
receptivity weight, and we would rather say so now than have you discover it in
the shape of the data.

---

## 7. Where it is

Branch `feat/attunement-phase-c-prereqs`, one commit.

- `halbert_core/attunement/context.py` — the `AttunementContext` builder (HB-D3)
- `halbert_core/attunement/shadow.py` — `ShadowDecider`, the two-verdict row, `default_recorder`
- `halbert_core/attunement/reactions.py` — the four arms
- `halbert_core/attunement/store.py` — `latest_attempt_for_context`, `unanswered_attempts`
- `halbert_core/proactive/gate.py` — `_evaluate` composes; `should_notify` unchanged
- wiring: `proactive/detector_runner.py`, `proactive/morning_report.py`, `dashboard/app.py`, `dashboard/routes/being.py`, `dashboard/routes/findings.py`

Tests: `test_attunement_shadow_decide.py`, `test_attunement_reactions.py`,
`test_attunement_reaction_wiring.py`, `test_attunement_recorder_wiring.py`,
`test_attunement_conformance.py`, `test_proactive_gate_composition.py`.
Full suite 8626 passed, 18 skipped, 6 xfailed, 0 failed.
