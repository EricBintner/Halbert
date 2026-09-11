# ATN-1, ATN-2, ATN-3 — the evidence, and what I would do

**Date:** 2026-09-10
**For:** the three `pending` rows added to `DECISIONS.md` today
**Method:** read `haloysius/attunement/policy.py` and `types.py`, then ran the
policy directly to confirm each claim rather than inferring it from the code.
Every number below was measured, not reasoned.

---

## 0. The headline, before the three rows

Two findings outrank all three decisions, because they change what the
decisions are *about*.

**1. In Halbert today, a HOLD is a silent drop.** Every outcome the policy can
produce other than SPEAK / SPEAK_MINIMAL / SILENT is a `HOLD` carrying a
`resume_on` and a two-hour deadline. Nothing in this repo releases one —
`grep` for `ResumeCondition` or `.release(` across `halbert_core/` finds no
consumer at all, and F6 ("the held queue as a surface") is listed in the plan
as unlocked-but-unbuilt. So `dial:quiet`, `standing:withdraw`,
`receptivity:unavailable`, `attachment:daily_cap` and
`attachment:new_relationship` would all become **silent drops** the moment the
policy stops being a shadow.

That makes the held queue a **go-live blocker for §4.6 stage 2**, not a
feature. It is also exactly the failure the suppression log was built to
expose, which is a good sign the log is pointed at the right thing.

**2. `ASK_FIRST` is unreachable in the default configuration, by 5.55e-17.**
Measured, on the plain case — a warning, no sensor, normal invitation,
established relationship, default extraversion:

```
value = 0.60   cost = 0.40
margin = value - cost = 0.19999999999999996
ASK_T[warning]        = 0.2
margin >= ask_t       -> False        shortfall 5.55e-17
```

The no-sensor warning lands *exactly* on the ASK threshold and misses it to
floating point. It then falls through to `HOLD`.

This matters more than it looks. `ASK_FIRST` **is** A-HB-26's exploration arm —
the cheap source of positive counterfactuals the whole of Phase C's design
rests on — and `warning` is the dominant severity Halbert's detectors emit. So
as things stand the exploration arm cannot appear in a single Halbert row, and
the reason is a rounding error rather than a policy judgment.

It is also nicely hidden: while `accepted_interactions < 5` the quiet-period
cost puts the margin at −0.05 and the HOLD looks principled. Fixing that
counter (which I did today) is what moves the case onto the boundary. A
consumer would "fix" its wiring and see no change.

Suggested fix, engine-side: compare against the thresholds with a tolerance —
`margin >= ask_t - 1e-9` — or round both to a fixed precision before
comparing. Worth a conformance vector at the boundary, since the boundary is
the default.

---

## 1. ATN-1 — Halbert's attachment ceilings

### What I measured

| Claim | Result |
| :--- | :--- |
| Can the daily cap eat a critical? | **No.** `if not critical:` guards the whole attachment block. Critical at `proactive_count_today=99` → `speak`. |
| Can it eat an info event at Balanced? | Moot — unanchored info is already `SILENT` (`dial:balanced:unanchored_info`) *before* the cap is reached. |
| So what does the cap actually bite? | **Warnings only**, at Balanced. (Warnings and info at Assertive.) |
| What does a capped event become? | `HOLD`, `resume_on=on_user_turn`, deadline `now + 2h` — and see §0: in Halbert that is a drop. |
| Is the finding lost? | **No.** Only the push. The finding is written and stays on the Findings page, which is PULL and never suppressed. |

And on volume: `_run_detector` dedupes by detector+title and `continue`s past a
still-suppressed finding *before* the gate, so a stable machine re-publishes
nothing on its four daily sweeps. Steady state is a handful of new warnings at
most. The two real volume regimes are a **fresh install on a messy `/etc`**
(one-off spike) and the **acoustic path**, where tagger severity 1–2 both map
to `warning` and the bridge runs per sound event.

### Recommendation: keep 24 — but replace the rationale

Keep the number. Drop "a runaway guard, one an hour averaged over a day" — that
is a rationalisation, not a reason. The number is doing something specific and
defensible:

> **24 sits above any plausible config-brain day, including a fresh-install
> spike, and far below a sensor flood.** It separates the two regimes. The
> config brain is the product; the acoustic and visual paths are the things
> that can run away.

The cost of being wrong high is small (findings still reach the page). The cost
of being wrong low is a dropped warning, because of §0.

**Keep `new_relationship_sessions = 0` and `new_relationship_days = 0`.** Two
supporting points I did not have when I set them:

- The engine's condition is `sessions_count < N **and** relationship_age_days <
  D`. Zeroing *either* disables the gate, so zeroing *both* is the honest form
  — zeroing one would leave a live-looking number that decides nothing.
- The gate exists against manufactured intimacy, which is not a risk this
  product has. The analogous real risk — a fresh install being noisy before it
  knows the machine — is a *calibration* problem, and the dial already owns it.

**Follow-up either way:** wire `note_session` / `first_seen_at`. Today
`sessions_count` is 0 and `relationship_age_days` is 0.0 permanently, which is
what makes the alternative unratifiable, and both are inputs Phase C may want.

---

## 2. ATN-2 — the daily cap and `Utterance.authority`

### Haloysius' framing does not survive checking

Their §4.1 says the cap "is the only gate that does not yield to
`Utterance.authority`". Measured, with a ruling (`authority=True`,
`authority_rule="house.rule.3"`) against each gate in turn:

| Gate | Ruling gets through? |
| :--- | :--- |
| `dial:off` | **No** — `silent`, carries the `authority` claim only |
| `dial:quiet` | **No** — `hold` |
| `attachment:daily_cap` | **No** — `hold` |
| `attachment:new_relationship` | **Yes** — `authority:overrode:...` |
| standing requests, invitation floor | **Yes** |

So the cap is not the only one; the **dial** does not yield either, in both OFF
and QUIET. And the engine's own `Utterance` docstring already states the rule
as intended design:

> It bypasses the consent-shaped gates only (standing requests, the invitation
> floor, the new-relationship mute) and is still subject to the dial including
> OFF, the daily cap, receptivity and the inequality.

The grouping is principled, not accidental: **gates shaped by the subject's
consent yield to a role the subject consented to in advance; limits shaped by
the holder's capacity do not.** The cap sits with the dial and receptivity, on
the correct side of that line.

### Recommendation: no change. Keep the cap binding.

The decisive argument is what the alternative costs. If the cap yielded to
`authority`, then `authority` becomes an unbounded bypass of the one ceiling
attachment safety actually has — a consumer need only declare its utterances
rulings. A ceiling a caller can lift by asserting a flag is not a ceiling.

The right answer to *"a moderator's fourth ruling of the day is held"* is that
the moderator's consumer must set its own `max_proactive_per_day`, exactly as
Halbert just did in ATN-1. A moderator app running on a companion's default of
3 is misconfigured, not mis-designed. The engine already invites this in the
same struct's docstring.

The audit story also holds: the `daily_cap` branch appends `auth` to its
reasons, so a surface can still show that *a ruling* was capped rather than an
ordinary gift.

**And I owe Haloysius a correction.** Today's reply says the asymmetry "reads
as an oversight rather than a design". That was wrong — their `Utterance`
docstring documents it as design, and I should not have inferred intent from
the branch without reading the type. Corrected in the handoff.

---

## 3. ATN-3 — F1's threshold, and whether a suggestion is an interruption

### The second half dissolves rather than answers

`_decide_inner` begins:

```python
if u.channel_class is ChannelClass.PULL:
    return _plain(ctx, EngagementOutcome.SPEAK, ("channel:pull",) + claim, value=1.0)
```

A PULL utterance is delivered before any gate is consulted. So **a suggestion
routed to a pull surface never has to pass the gate it is about** — the
question stops being a paradox and starts being a routing decision.

Which is also the substantive answer, not a trick. If the suggestion rides the
dial it proposes to change, the system suppresses its own correction *exactly
when the dial is most wrong* — the quieter you have made it, the less able it
is to tell you it has gone too quiet. That failure is silent and
self-reinforcing, which is the worst combination this design has.

**Recommendation:** the suggestion is **a finding** — PULL, always delivered,
carrying the four whys like any other — **plus a bell badge**, which is AMBIENT
and at a quiet dial yields `SPEAK_MINIMAL, ambient:no_escalation` rather than a
hold, so the badge still updates. Never PUSH, never voice, never auto-open.
`the-being.md` §11 asks "when is auto-suggesting dial changes safe?"; the
answer is that it is safe when it is not an interruption at all.

### The first half: how much evidence

**Test the category against the user's own baseline, not against a constant.**
A person who dismisses 80% of everything does not want storage set to Quiet —
they want the *global* dial lowered, and a per-category test against a fixed
probability would tell them the wrong thing about eight categories at once.

The statistics make this concrete. `the-being.md`'s own worked example is
"you've dismissed six of the last eight storage notices". One-sided exact
binomial:

| Baseline (the user's own negative rate elsewhere) | p for 6 of 8 |
| :--- | :--- |
| 20% | 0.0012 — strong |
| 30% | 0.0113 — marginal |
| 50% | **0.1445 — not significant** |

So the anchor document's own example is a valid suggestion only when the
person's baseline is low. Against a 50% baseline it is noise, and acting on it
would be the ratchet arriving dressed as a feature.

**Recommendation — four rules:**

1. **n ≥ 8** labelled attempts for that category in a trailing window (30 days,
   or the last 20 attempts, whichever is shorter). Below 8 nothing is
   suggested, whatever the rate — small-n significance is exactly the fragile
   kind.
2. **One-sided exact binomial against the user's cross-category negative rate**,
   at **α = 0.05 / (number of categories)** ≈ 0.00625. You are testing every
   category at once; not correcting for that manufactures a suggestion a year
   per user from noise alone.
3. **Negatives are `DISMISSED` only**, until receptivity is wired. `IGNORED`
   cannot distinguish "saw it and did not care" from "was not at the machine",
   so counting it lets a fortnight's holiday teach the system it talks too
   much. `NOT_NOW` is excluded from numerator *and* denominator — a
   postponement is evidence of neither.
4. **Cooldown.** A dismissed suggestion does not return for that category until
   the evidence doubles, or for 90 days. Without this the suggestion becomes
   the nag it exists to prevent, which would be an unusually pure failure.

Plus the two already-ratified constraints: **suggests, never auto-tunes**, and
one click to apply with one click to reverse.

**Blocked on §0's second finding.** The exploration arm cannot produce a single
row until the `ASK_T` boundary is fixed, so the "is silence costly?" half of
the evidence stays empty no matter how long the ledger runs. Phase C's *reader*
is buildable now; the *adjuster* should wait on that fix and on the positive
arm having more than one source.

---

## 4. What I would do, in order

1. **Tell Haloysius about the `ASK_T` boundary today.** It is small, it is
   theirs, and it silently disables the arm they asked us to supply.
2. **Ratify ATN-1 as it stands**, with the rationale above replacing the one in
   the row.
3. **Close ATN-2 as "no change, and the framing was wrong"** — send the
   correction with the measured table.
4. **Record ATN-3's answer to the second half now** (pull surface + ambient
   badge); it is a design decision that needs no data. Hold the threshold rule
   as *recommended, not ratified* until a real ledger exists to sanity-check
   the baseline against.
5. **Name the held queue (F6) a go-live blocker** for stage 2 on `ROADMAP.md`.
   Everything else here is tuning; that one is a correctness gap.
