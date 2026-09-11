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
`record_outcome_raw` had no caller either — none outside the typed `record_outcome` façade, which is to say no production path. So the suppression log was not
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
moment any non-engine row enters the table.

**And it needs one line from you.** `ledger.py:209` is
`margin=float(data.get("margin", 0.0))`, and an explicit `null` is not a
missing key, so `_outcome_from_dict` raises `TypeError` on one of our rows. We
decode through our own `attunement/codec.py`, which short-circuits on `None`,
so nothing of ours breaks — but Phase C's reader would, and
`OutcomeEntry.margin` is a required non-`Optional` `float`. We have pinned it
as a tripwire test on our side (`test_the_engines_own_decoder_cannot_yet_read_a_null_margin`)
that fails, deliberately and helpfully, the day you widen the hint. Our earlier
draft of this paragraph said a `None` rides through `from_dict` fine; that was
true of our codec and false of yours, and we would rather correct it here than
have you find it in Phase C.

**`shadow_agrees` uses your definition of speech, not a second one.**
`{speak, speak_minimal, ask_first}` — the three `record_attempt` counts toward
the daily proactive total. We did not want a local opinion about whether
ASK_FIRST reaches a person.

**We did not swap `SuppressionRecorder` out**, per your §2.1, and we do not
call `record_attempt`. We *do* advance two of the counters it would have
advanced, and both were forced on us by the same discovery — a counter the
wiring cannot move does not stay neutral, it pins a term in the policy:

- **`note_proactive`**, when the shadow's own decision speaks. Left alone,
  `proactive_count_today` is zero on every row, `attachment:daily_cap` can
  never appear, and the shadow models a policy whose cap does not exist. It is
  a durable write from a hypothetical, which is why we flagged it as a
  question in our first draft; the answer turned out to be that not doing it
  makes the log describe nothing anyone would ship. Per-day, reset daily, read
  by nothing else. **This is the line to tell us to delete if you disagree.**
- **`note_accepted`**, via your `record_reaction` rather than a bare
  `update_reaction`. This one was a real defect in our first cut and it is
  worth your attention because any consumer wiring reactions by hand will hit
  it: `policy.py:337` adds `W_QUIET_PERIOD` (0.25) to `cost` while
  `accepted_interactions < QUIET_PERIOD_N`, and nothing in a hand-wired
  consumer advances `accepted_interactions`. Measured on our own context
  before the fix, every margin carried a fixed −0.25 that could never clear —
  `hold, margin −0.05` where the same decision with the counter past the
  threshold gives `hold, margin +0.20`. The sign of the margin was being
  decided by a counter our wiring could not move. A note in `record_reaction`'s
  docstring saying it is not a wrapper around `update_reaction` would have
  saved us; `record_attempt` has the same shape with `note_proactive`.

**Two counters we still do not advance, and you should size §3 knowing it:**
`sessions_count` and `first_seen_at` — nothing calls `note_session`, so
`relationship_age_days` is 0.0 and `sessions_count` is 0 on every row, forever.
With our ATN-1 zeros the new-relationship gate is inert either way; with your
defaults it would be a permanent mute rather than a week's one.

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
2. **No reaction ever lands on an attempt the gate suppressed** — not the
   sweep, and not the three event-shaped arms. This is worth spelling out
   because our first cut got it wrong in a way that is easy for any consumer
   to reproduce, and it was *not* an edge case. A finding is still written and
   still listed when its push is suppressed, so the ordinary path is: dial is
   quiet → no interruption → the person meets the finding on the Findings page
   → dismisses it → the dismissal lands on the suppressed attempt. With a
   shadow attached that row's `outcome` is the *engine's* verdict, so the row
   reads *"the engine would have spoken, and the person said no"* about an
   event the person never saw. That is your P2 ratchet being fed by the
   product's own silence, arriving through the arm meant to protect against
   it. The join now defaults to spoken attempts only
   (`latest_attempt_for_context(..., spoken_only=True)`), and the sweep
   filters in SQL before the `LIMIT` rather than after — suppressed rows stay
   unanswered forever, so filtering them in the consumer let enough of them
   hide every spoken row behind them.

   **The consequence for Phase C, stated positively:** a `reaction` only ever
   attaches to a row where `gate_outcome == "speak"`. So on any reacted row
   the engine's `outcome` is a counterfactual *about an event the person
   actually saw* — a `hold` on a row the gate spoke and the person engaged
   with is exactly the retrospective evidence A-HB-26 asks for, and the pairing
   is sound rather than dangerous.
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

Pending founder ratification — with one caveat we owe you, since it bears on
your defaults rather than ours: **keeping the engine's numbers is not currently
a ratifiable option here.** Nothing calls `note_session`, so `sessions_count`
is 0 and `relationship_age_days` is 0.0 permanently; with 5/7 the
new-relationship gate would not mute Halbert for a week, it would mute it
forever. Our zeros make it inert, which is why the gap has not bitten. Either
way the counters want wiring before that ceiling means anything, and that is
ours to do.

Nothing user-visible turns on any of it while we are in shadow.

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
- **`channel_class` is PUSH on every row, and that over-states us.**
  `ProactiveGate` makes one decision for the whole event bus, whose
  subscribers span a bell badge (AMBIENT) and, where wired, voice and the
  auto-opening panel (PUSH). PUSH is the loudest reachable surface, so it is
  the conservative default for a suppression system — but the bias has a
  direction: you treat AMBIENT more permissively (a quiet dial yields
  `SPEAK_MINIMAL` rather than a hold; the social cost applies to PUSH alone),
  so **the shadow reads quieter than the product would be** if it decided per
  surface. Named as `SHADOW_CHANNEL_CLASS` so the choice is visible rather
  than an accidental default.
- **`previous_decision` is never passed**, so `PolicyStability`'s hysteresis
  and dwell never apply to a shadow row. Our P5 (decision flapping reads as a
  hardware fault) is therefore unmeasured here.
- **`sessions_count` and `relationship_age_days` are pinned at 0** — see §2.
- **We pass `ledger.active()`, not `active_for_unknown()`.** With
  `subject_confidence=UNATTRIBUTED` that is the right reading for a push to
  the host's primary user, but it does mean A-HB-3's most-restrictive
  inheritance is not exercised. Latent today because nothing writes standing
  requests at all; flagged so it is not discovered later as a gap.

So: the arms exist and the rows are real, but the population is narrow —
severity, source, dial, the ceilings, and the reaction. That is enough for the
reader and enough to stop the ratchet. It is not yet enough to tune a
receptivity weight, and we would rather say so now than have you discover it in
the shape of the data.

---

## 7. Where it is

Branch `feat/attunement-phase-c-prereqs`, three commits.

- `halbert_core/attunement/context.py` — the `AttunementContext` builder (HB-D3)
- `halbert_core/attunement/shadow.py` — `ShadowDecider`, the two-verdict row, `default_recorder`
- `halbert_core/attunement/reactions.py` — the four arms
- `halbert_core/attunement/store.py` — `latest_attempt_for_context`, `unanswered_attempts`
- `halbert_core/proactive/gate.py` — `_evaluate` composes; `should_notify` unchanged
- wiring: `proactive/detector_runner.py`, `proactive/morning_report.py`, `dashboard/app.py`, `dashboard/routes/being.py`, `dashboard/routes/findings.py`

Tests: `test_attunement_shadow_decide.py`, `test_attunement_reactions.py`,
`test_attunement_reaction_wiring.py`, `test_attunement_recorder_wiring.py`,
`test_attunement_conformance.py`, `test_proactive_gate_composition.py`.
Full suite 8641 passed, 18 skipped, 6 xfailed, 0 failed.
