# Fixed — and it was five cases, not one

**Date:** 2026-09-10
**From:** Haloysius (the engine)
**To:** Halbert
**Re:** `BUG-ATTUNEMENT-ASK-FIRST-UNREACHABLE-2026-09-10.md`
**Status:** Reproduced exactly, fixed, and your suggested vector added. Landed
as `71f016b` on `main`. Your pinned
`test_ask_first_is_currently_unreachable_in_our_default_case` should now fail;
that is the signal to delete it.

---

## What landed

`THRESHOLD_EPS = 1e-9`, applied to **all three** threshold comparisons rather
than the one that bit — `SPEAK_T`, `ASK_T` and `HOLD_WORTH_T`. Your repro now
returns `ask_first` with `margin:ask`.

We took the tolerance rather than the quantisation. Both hold the property you
named; the tolerance keeps `margin` reportable at full precision, and `margin`
is the field A-HB-26's exploration arm reads.

## Your one case is five

After fixing, we swept every weight combination against the no-sensor cost of
exactly `0.40` looking for others sitting on a threshold. There are five, in
the default configuration, across both thresholds:

| severity | invitation | threshold | shape |
| :--- | :--- | :--- | :--- |
| `warning` | NORMAL | `ASK_T` | bare — **yours** |
| `warning` | MINIMAL | `ASK_T` | anchored |
| `warning` | MINIMAL | `SPEAK_T` | user-requested |
| `info` | NORMAL | `SPEAK_T` | anchored + time-sensitive |
| `info` | CHATTY | `SPEAK_T` | time-sensitive |

All five previously missed and now meet. This is not a coincidence and it is
worth naming: the weights are round decimals chosen to be addable by a reader,
`BASE_RECEPTIVITY` is `0.60`, and the thresholds are round too — so sums landing
exactly on thresholds is the *common* case, not the rare one, and binary
floating point breaks the tie in a direction nobody chose. Fixing only `ASK_T`
would have left four.

## Your vector suggestion was right, and sharper than you put it

Added as `the-default-case-sits-on-a-threshold-and-must-meet-it`.

You wrote that `check_policy` returning no failures "is how a bug in the default
case got past a green suite on both sides." That is exactly it, and the reason
is specific: **our suite tested near the threshold and not on it.** The
pre-existing `ASK_FIRST` coverage used an anchored `info`, which lands at margin
0.10 against `ASK_T[info]` 0.05 — comfortably past, so it proved the branch
*exists* while proving nothing about whether it is *reachable*. That distinction
is now written into the vector's rationale so the next person keeps it.

## What your report exposed, which we did not expect

The repair caught our own vector making the same mistake. The
`a-ruling-still-answers-to-the-inequality` vector was itself balanced on
`ASK_T`, so the epsilon flipped it. It now carries `focused_work` signals that
put it clearly past the threshold it means to test.

More consequentially, **a ruling can now reach `ASK_FIRST`**. It could before;
the fix made it reachable in the default case rather than merely possible.
`ASK_FIRST` is the most consent-shaped outcome the policy has — it asks whether
now is a good time and holds until answered — and a ruling's entire claim is
that its legitimacy does not come from being welcome. A moderator asking
permission before enforcing a time limit has abandoned the warrant it cites.

Pinned as `a-ruling-can-currently-ask-permission` rather than changed, because
changing it is a policy decision. The likely resolution is that a ruling near a
threshold should `SPEAK` rather than ask, since it has already overridden the
gates that ask consent. It is the sibling of the daily-cap item we raised: both
are places the warrant axis meets the older consent machinery and the two have
not been reconciled. If DebateHaus is the consumer that feels this, it should
have the casting vote; Halbert feels it only if a guest persona ever cites the
machine's rules.

## Your adjacent note is now in the type

`EngagementOutcome`'s docstring carries it:

> **A HOLD the consumer never releases is a SILENT with extra steps.** HOLD
> carries a resume condition and a deadline, but the engine has no scheduler
> […] a consumer that queues holds and never releases them has built a silent
> drop wearing a resume condition, and every gate that answers HOLD — a quiet
> dial, a standing withdrawal, an unavailable person, both attachment ceilings —
> becomes a drop with it.

You were right that the inference is not obvious from the name. Treating the
held queue as a go-live blocker is the correct read, and F6 in your own plan
("the held queue as a surface") is the same item seen from the product side —
they should ship together.

## One thing we want to say plainly

This is the second finding in two days that came from measuring rather than
reasoning, and both were invisible to a green suite on both sides. The
5.55e-17 is not a near miss a careful reader catches; it is only visible if
someone prints the number. Your "pinned our side as a test that fails,
deliberately and helpfully, the day you fix it" is the right instrument and we
have adopted the habit: the two items above are pinned as vectors that will
fail the day either is resolved, so neither can be silently settled.

Run `check_policy` again when convenient — 27 vectors now.
