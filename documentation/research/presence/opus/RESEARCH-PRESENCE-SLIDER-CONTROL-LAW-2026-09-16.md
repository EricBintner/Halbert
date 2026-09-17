# Research — the presence slider: control laws for a single presence number

**Date:** 2026-09-16
**Status:** Research pass. **Nothing here is a specification and nothing here is decided.**
**Programme:** Presence. Adjacent to, and deliberately not overlapping, the engine's
observables programme (O1–O4, 2026-09-15). That programme asks *whether* presence is achieved
and how to test it. This one asks a question it does not cover: **what should a single
user-facing number actually move?**

**Scope.** Not whether the family should have a presence control — that is taken as given. The
question is whether one number can carry the meaning the founder described (0 = soft mute,
default = 3, 10 = a friend who keeps the conversation alive), what mechanism sits behind it,
and what the same control means across four consumers with radically different sensory inputs
and radically different risk profiles.

**Verification posture.** Engine and consumer `file:line` references were read against the
working trees on this date; every quoted line was read, not remembered. Of the external
literature, **fourteen sources were fetched and verified** at their arXiv, PMC, publisher or
author page, or extracted locally from PDF (§10.1). Two could not be retrieved and are
recorded as such (§10.2). §12 records seven discrepancies and cautions — including a numerical
conflict between a verified secondary source and an unreachable primary page — rather than
silently resolving them.

**Naming.** Consumers are named by role, per the engine's research convention. The two closed
siblings are **the companion consumer** and **the persona-authoring consumer**; their product
names are not written in this tree. `Halbert`, `Haloysius`, `SourcePrep` and `BrightestMinds`
are named openly.

---

## §0 Executive summary

### 0.1 The six findings that change the problem

**F1 — Presence is not speech rate.** Four of the eight candidate control laws below never
change how *often* the system speaks, and two of those four produce most of the felt quality
the founder is asking for. Weiser and Brown define the periphery as "what we are attuned to
without attending to explicitly" and calm technology as that which "engages both the center and
the periphery of our attention, and in fact moves back and forth between the two" [L21]. A
slider that only moves a frequency is a volume knob with a better label.

**F2 — Neither end the founder described is reachable today, for two different deliberate
reasons.** At the bottom, `DialLevel.OFF` is *off*: `assess_presence` returns `SILENT` on
`dial:off` before consulting anything else (`policy.py:379`). The founder's 0 — "only important
events get spoken" — has no representation in the enum. At the top,
`_NEVER_SPEAKS = (RANDOM, TEMPORAL, SCENE)` filters the three impulse classes capable of
companionable speech *before the policy ever runs*, under the comment "a permissive dial cannot
turn idle chatter into speech" (`autonomous_engine.py:594-599`). Both are load-bearing code.

**F3 — The control law is not one threshold, it is six, and the gaps between them are the
product.** `constants.py:37-39` carries `SPEAK_T` and `ASK_T` per severity. This is Horvitz's
two-threshold structure implemented: he derives `p*¬A,D` (inaction vs dialog) and `p*D,A`
(dialog vs action) and notes they "provide an instant index into whether to act, to engage the
[user in dialog]" [L1]. The band between them **is** `ASK_FIRST`. At `INFO` it is 0.30 wide
(0.05 → 0.35); at `WARNING` it is 0.10 wide (0.20 → 0.30). A naive slider that moves one
threshold collapses that band: push `SPEAK_T` down and the persona stops asking and just talks;
push `ASK_T` up and asking collapses into silence. **Whatever the slider is, it must be defined
on the band, not on a line.** This was nearly learned the hard way already — the recorded
5.55e-17 float defect (`constants.py:41-47`) was a band-edge failure that made `ASK_FIRST`
unreachable for warnings.

**F4 — The cheapest large win is channel re-mapping, and it is almost entirely built.** Routing
an impulse between `PULL` / `AMBIENT` / `PUSH` rather than admitting or suppressing it makes the
bottom of the slider mean *stop interrupting me* rather than *stop noticing* — which is exactly
soft mute, with no new enum value and no model. `ChannelClass` exists in both trees, and
Halbert's `surfaces.py:10-13` already names the middle value as "Weiser & Brown's periphery".

**F5 — The top half is blocked on a memory feature, not a policy feature.** Lifting
`_NEVER_SPEAKS` admits more impulses, but nothing in any repository currently produces a good
one from nothing. The engine's own digest names this as O2's gap G1: no commitment or open-loop
record with a due condition exists anywhere, and the extraction paths are placeholders, so "how
did the interview go?" is unreachable in principle today. **A high presence setting shipped
before open loops exist produces filler, and filler is worse than silence.**

**F6 — The feature we are describing is, verbatim, the companion-harms literature's definition
of the product class it warns about.** An AIBM report distinguishing AI companions from
general-purpose chatbots lists three central properties, of which the second is: "**Engagement:**
They seek out and sustain interaction. They initiate conversation, remember past exchanges, and
build an ongoing 'relationship' rather than treating each encounter as new" [L26]. That is a
description of presence 10. This is not a reason not to build it. It is a reason the *ceilings*
must differ per consumer and must not be reachable by the persona's own persuasion.

### 0.2 Where the evidence points, provisionally

A composite (M8) in which one visible number indexes an **authored, inspectable curve** through
a small parameter space, whose axes are source admission (M3), channel class (M6), patience
(M7) and rate budget (M2), with the decision thresholds (M1) *derived* from those rather than
exposed. Model-level steering (M4) is rejected for initiation and kept on file for register.
Learned policy (M5) is not v1 and is actively hazardous as a primary law, for a reason stated
in Halbert's own source: a loop whose speech is punished and whose silences are never evaluated
ratchets toward silence.

### 0.3 What this pass could not settle

Seven open questions are in §8. The blocking one is §8.1 — *what does it actually say at 8 and
above* — because it is a prerequisite rather than a parameter.

---

## §1 The construct: what "presence" names

The word is doing real work. Three of the eight methods only make sense once it is pinned, and
the most consequential design error available here is to let "presence" silently mean
"talkativeness".

### 1.1 Social presence and co-presence

The construct in the HCI and CSCW literature splits into **co-presence** — the sense of being
together with another in a space, including mutual awareness, not merely the cognition that
another is in the same environment — and **social connection** [L22]. Note what the definition
does not contain: any rate of utterance. Mutual awareness is a *state*. A system can raise
co-presence by making its awareness legible without emitting one additional word.

This matters directly for the slider because it means there is a family of interventions — make
the system's noticing visible — that raise presence and *lower* interruption at the same time.
A one-dimensional "more presence = more talking" model cannot express those, and they are the
cheapest things in the space.

### 1.2 Calm technology, the periphery, and "attunement" as a term of art

Weiser and Brown's 1996 formulation is the direct ancestor of what the engine already
implements, and the vocabulary match is not coincidental.

Their definition: "Calm technology engages both the center and the periphery of our attention,
and in fact moves back and forth between the two" [L21]. The periphery is "what we are attuned
to without attending to explicitly." Peripheral awareness lets a person process far more
information than central attention alone without overload; when something unusual happens at
the periphery it can be moved rapidly to the centre; and *that movement* — not the information
itself — is what increases the sense of control.

Their examples are instructive for a presence design because none of them speak: inner office
windows that carry social cues without demanding attention; a continuous video "window of
awareness"; and the dangling string, an eight-foot plastic strand that twitches with network
traffic, conveying load through motion and sound with no screen and no interpretation demand.

Two consequences for this programme:

1. **The engine's package name is the literature's word.** `haloysius.attunement` is named for
   the thing Weiser and Brown define the periphery in terms of. The `ChannelClass` three-way cut
   (`PUSH` / `AMBIENT` / `PULL`) is that model encoded, and Halbert's `surfaces.py:10-13` says so
   explicitly: "`AMBIENT` is the middle value a strict binary loses — a bell badge changes
   without being asked and yet demands nothing, which is Weiser & Brown's periphery."
2. **The lowest presence setting has a target other than silence.** Calm technology's low state
   is not absence; it is peripheral. This is M6, and §1.3 says why the difference is not
   cosmetic.

### 1.3 Believability, idle behaviour, and the zombie effect

The virtual-agent literature has a name for what a persona looks like at presence 0 when 0 means
"do nothing". Avradinis, Panayiotopoulos and Anastassakis state it: an agent "programmed to
react depending on the user's input, will remain idle when no such input is present, creating a
zombie effect", and pre-scripted filler behaviour becomes repetitive fast enough that a user
identifies it, which undermines the environment rather than sustaining it [L23]. Their proposed
remedy is motivational — internal states that generate goals, so behaviour is *coherent with an
interior* rather than sampled from a list.

The complementary empirical finding is that idle behaviour need not be elaborate. Atxa Landa et
al. compared genuine and acted idle animations — "standing, breathing or looking around" — and
found users cannot distinguish them, though handmade and recorded animations *are* perceived
differently [L24].

Translated out of the animation context, and this is the load-bearing translation for M6:

> The low end of a presence slider should be an absence of **interruption**, not an absence of
> **the persona**. And the cheap version of "still here" is adequate: it does not have to be
> clever, it has to be coherent and not repetitive.

The zombie-effect framing also supplies the sharpest argument against the naive top end. An
agent that fills silence from a list is the zombie with more output. What distinguishes a
companion from a zombie is not frequency; it is that the behaviour issues from an interior state
that persists. That is F5 restated from the other direction.

### 1.4 Proactivity is not autonomy, and the distinction constrains the slider

Bui and Evangelopoulos make the separation precisely: autonomous systems execute tasks
independently, whereas proactive systems must "notice relevant changes before the developer
asks, connect signals across tools, decide when to interrupt" [L13]. Their evaluation principle
is the one sentence most worth carrying into this design:

> Proactivity should be judged "not by how often an agent acts, but by whether it surfaces the
> right insight at the right time, with enough evidence, and stays silent when intervention is
> unwarranted."

A slider calibrated on frequency optimises the quantity that sentence explicitly rejects as the
measure. Whatever the control is, its *specification* per position should be expressed in terms
of evidence and false-positive tolerance, not rate. §7 takes this up.

### 1.5 A working definition for this programme

Proposed, for this document only, to keep the eight methods comparable:

> **Presence** is the degree to which the system is *legibly attending*, *appropriately
> forthcoming*, and *continuous across time* — with legibility and continuity available at every
> setting, and forthcomingness the only one of the three that the slider suppresses.

The value of the definition is that it makes three of the eight methods obviously in-scope that
a frequency definition would have excluded, and it makes the 0 end coherent: at 0 the system is
still attending and still continuous, and only its forthcomingness is gone.

---

## §2 The control surface that exists today

Read against the working trees on 2026-09-16. This is the "80 % already built", stated
precisely enough to build on or argue with.

### 2.1 Engine — the `attunement` package

`haloysius/attunement/`, Apache-2.0, stdlib-only by policy. Three entry points, one ledger, one
set of constants; the package docstring states that "a consumer that wires nothing gets exactly
the pre-attunement behaviour everywhere."

| Piece | Location | What it decides |
|---|---|---|
| `decide()` | `policy.py` | The **proactive** path. Pure: same `AttunementContext` in, same `EngagementDecision` out. No clock, no I/O, no store. |
| `assess_presence()` | `policy.py:374` | The **presence** path, already by that name: "nothing wants to speak; should the persona signal it is here?" Returns `AVAILABLE` or `SILENT`. |
| `begin_turn()` | `turn.py` | The **reactive** path. Parses any directive in the user's own turn text, updates the ledger, applies stance, returns the envelope and the `[ATTUNEMENT]` prompt block. Never consults receptivity. |
| `parse_directive()` | `directives.py` | Natural-language directive recognition, with scope hints so a bare "stop" is not mis-owned. |
| `StandingRequestLedger` | `ledger.py` | The standing requests, their TTLs, resume conditions and release. Explicit beats inferred. |
| `estimate_receptivity()` | `receptivity.py` | Cheap typed signals → `UNAVAILABLE` / `LOW` / `MODERATE` / `HIGH`. |
| `render_attunement_block()` | `stance.py` | The stance the persona is told to hold, as prompt text. |
| `check_policy()` / `policy_vectors()` | `conformance.py` | Language-neutral conformance vectors — the mechanism by which two consumers can be *shown* to implement the same law. |
| `record_attempt` / `record_reaction` | `ledger.py:945` | The outcome ledger: the learning arm. |

**Outcome vocabulary.** `EngagementOutcome` has six values: `SPEAK`, `SPEAK_MINIMAL`
(one line or a non-verbal receipt, no questions), `ASK_FIRST` ("is now a good time?" then hold),
`AVAILABLE`, `HOLD`, `SILENT`. The enum's docstring carries a warning added by Halbert on
2026-09-10 and it is the most important sentence in the file:

> **A HOLD the consumer never releases is a SILENT with extra steps.** … A consumer that queues
> holds and never releases them has built a silent drop wearing a resume condition, and every
> gate that answers HOLD — a quiet dial, a standing withdrawal, an unavailable person, both
> attachment ceilings — becomes a drop with it.

Any slider position whose behaviour is "hold more" inherits that warning wholesale.

**Directive vocabulary.** `DirectiveKind` is precedence-ordered: `SAFEWORD` > `WITHDRAW` >
`INVITE` > `LIMIT` > `RESUME` > `DEFER_TOPIC`. `LimitKind` splits six axes, and the split matters
for the slider: `SEVERITY_FLOOR` and `TOPIC_SCOPED` "constrain *proactive* speech only and never
narrow an answer the user explicitly asked for", while `BREVITY`, `NO_ACTION`, `NO_QUESTIONS` and
`NO_ATTRIBUTION` shape the reply itself. **A presence slider must respect the same split**, or
turning presence down will start truncating answers the user asked for.

**Channel vocabulary.** `ChannelClass`: `PUSH` (arrives unbidden, spends attention — speech,
narration, notifications, panel auto-open), `AMBIENT` (changes unbidden, demands nothing — a
bell count, a tray badge, a presence indicator; "may update, must not escalate"), `PULL`
(persists on a surface the user navigates to — a findings list, a transcript, a log; "never
suppressed by attunement").

**Subject vocabulary.** `SubjectConfidence` is three-valued: `IDENTIFIED`, `UNATTRIBUTED` (no
identity but the channel implies the trusted default user — treated as default, does *not*
inherit most-restrictive), `UNKNOWN` (an unresolved speaker in a shared space — inherits the
most restrictive active request of any known subject for un-addressed PUSH speech; direct
address is still answered). This exists and is unused by any presence design so far; §8.7 asks
whether the slider is per-subject.

### 2.2 The actual arithmetic

`attunement/constants.py` is "every number the attunement policy and receptivity estimator use",
exported as one read-only mapping "so consumers assert against the engine's values instead of
copying them". The consumer-facing knobs are deliberately *not* here — they live on
`AttunementConfig` / `AttachmentSafety` / `PolicyStability`.

The inequality's weights:

| Term | Value |
|---|---|
| `W_SEV` | INFO 0.30 · WARNING 0.60 · CRITICAL 1.00 |
| `W_ANCHOR` | 0.20 |
| `W_REQ` | 0.30 |
| `W_TIME` | 0.25 |
| `W_INVITE` | SILENT −1.00 · MINIMAL −0.20 · NORMAL 0.00 · CHATTY +0.20 |
| `W_SOCIAL` | 0.20 |
| `W_QUIET_PERIOD` | 0.25 (over `QUIET_PERIOD_N` = 5) |
| `W_RESERVED` | 0.20 |

And the thresholds — the finding of F3:

| Threshold | INFO | WARNING | CRITICAL |
|---|---|---|---|
| `SPEAK_T` | 0.35 | 0.30 | −2.0 (always clears) |
| `ASK_T` | 0.05 | 0.20 | −2.0 |
| `HOLD_WORTH_T` | 0.45 | 0.30 | 0.0 |
| **ASK band width** | **0.30** | **0.10** | n/a |

`HOLD_MAX_S` is 7200 — a two-hour ceiling on patience. §4.7 measures that against the empirical
deferral literature and finds it three orders of magnitude out.

Two calibration facts worth stating because they bound what a slider can do by moving invitation
alone:

- The **earned** axis is worth at most **+0.20** on the margin (`W_INVITE[CHATTY]`), while
  severity alone spans 0.30→1.00. Talking the persona up from `NORMAL` to `CHATTY` moves the
  margin less than the difference between an INFO and a WARNING. The earned axis is a nudge, not
  a lever — which is correct, and which means the *set* axis has to carry the range.
- `W_INVITE[SILENT]` is −1.00: a hard veto, not a discount.

**The float defect, recorded in the file, is the canary for F3:**

> the plainest case in the whole policy — a bare warning with no sensor wired — computes
> 0.60 − 0.40 = 0.19999999999999996 and misses `ASK_T[warning]` 0.2 by 5.55e-17. A margin the
> spec intends to *equal* a threshold must be treated as meeting it, or the arithmetic silently
> decides policy (Halbert, 2026-09-10).

`THRESHOLD_EPS` = 1e-9 is the fix. The lesson generalises: with a `WARNING` ask-band only 0.10
wide, **a slider with eleven positions that redistributes 0.10 across them is allocating 0.01 per
notch** — smaller than several individual receptivity weights. The band cannot absorb an
eleven-position linear control.

### 2.3 Receptivity: the cost-of-interruption estimate

`receptivity.py` is a pure function over `SituationSignals`, starting at `BASE_RECEPTIVITY`
(0.60) and applying additive rows each scaled by the signal's confidence, appending a stable
reason key. Quiet hours is deliberately **not** a row — it is an absolute gate upstream. Some
rows short-circuit to `UNAVAILABLE`.

Activity deltas (`R_ACTIVITY`), which are the clearest statement of what the engine believes
about interruptibility:

| Raises | | Lowers | |
|---|---|---|---|
| ARRIVING | +0.35 | MEDIA | −0.10 |
| CHORES | +0.25 | DRIVING | −0.30 |
| TRANSITION | +0.15 | DEPARTING | −0.35 |
| IDLE | +0.15 | FOCUSED_WORK | −0.40 |
| | | CONVERSATION | −0.50 |
| | | ON_CALL | −0.50 |

Plus `R_OPERATION_IN_PROGRESS` −0.60, `R_VERBAL_BUSY` −0.50, `R_STATED_BUSY` −0.45,
`R_INCIDENT` −0.35, `R_READING` −0.30, `R_WINDING_DOWN` −0.30, `R_OTHERS_PRESENT` −0.20,
`R_BAD_MOOD` −0.20, `R_NOT_TYPICALLY_ACTIVE` −0.15, `R_VULNERABLE` −0.10, `R_MID_EXCHANGE`
+0.10 with a 60 s taper. `STALE_FACTOR` 0.5 halves old observations and flags the result.

The module docstring is honest about provenance: "Row weights are literature-derived (Cha et al.
2020, Fogarty et al. 2005, Iqbal & Bailey 2007) … the outcome ledger exists so they can be
revised from evidence." They have never been revised from evidence, because no labelled evidence
exists yet (§2.8).

### 2.4 The two axes, and how they are coupled

This is the structure a single slider most threatens, and it is worth stating exactly.

- **`DialLevel`** (`types.py:246`) — `OFF` / `QUIET` / `BALANCED` / `ASSERTIVE`. What the person
  *set*. Carried on `ProactivityDial` (`types.py:619`) together with per-category overrides which
  **substitute rather than floor**: a category may be *more* permissive than the global level.
- **`InvitationLevel`** (`types.py:232`) — `SILENT`/`MINIMAL`/`NORMAL`/`CHATTY` as 0–3. What the
  relationship *earned*. Explicitly "reply width and proactive frequency only"; intensity
  ("challenge me", "don't hold back") is a separate axis deliberately not modelled.

They are coupled twice:

```python
_DIAL_CEILING = {
    DialLevel.OFF:       InvitationLevel.SILENT,   # off stays off
    DialLevel.QUIET:     InvitationLevel.MINIMAL,  # a deliberate restriction speech cannot lift
    DialLevel.BALANCED:  InvitationLevel.CHATTY,   # the default posture; the person may ask for more
    DialLevel.ASSERTIVE: InvitationLevel.CHATTY,   # already the maximum
}
```
(`types.py:284-306`)

`invitation_for_dial()` returns the level a dial **decays toward**; `invitation_ceiling_for_dial()`
returns the highest level speech may **raise to** under it. The `QUIET` comment — "a deliberate
restriction speech cannot lift" — is a design commitment a slider could silently break.

Governing both, `AttachmentSafety` (`types.py:636`): `max_proactive_per_day=3`,
`new_relationship_sessions=5`, `new_relationship_days=7`, `max_invitation_steps_per_week=1`,
and `persona_may_solicit_invitation=False` (`types.py:648`) — which "renders as a hard constraint
in every emitted `[ATTUNEMENT]` block". The docstring states the defaults "are a companion's;
any consumer may set its own numbers". Given §5 C-5, that is the right place for the strictest
numbers to live.

`PolicyStability` (`types.py:658`): `threshold_hysteresis=0.05`, `min_dwell_s=45.0`. Note the
hysteresis is **half the entire WARNING ask-band**.

### 2.5 Impulse generation

`cognition/autonomous_engine.py` is where impulses come from — the half of the system a presence
slider at the top would be unlocking. `TriggerType` has nine values: `TEMPORAL`, `EMOTIONAL`,
`DRIVE`, `BELIEF`, `MEMORY`, `WORRY`, `RANDOM`, `SCENE`, `USER_ABSENCE`. `ThoughtLength` spans
`MICRO` ("Hmm…") through `BRIEF`, `STANDARD`, `EXTENDED` to `REFLECTIVE`.

`_should_speak()` has two regimes. With an attunement policy wired, the trigger is described as
an `Utterance` and the policy decides — `SPEAK`, `SPEAK_MINIMAL` and `ASK_FIRST` all speak.
Without one, legacy intensity thresholds stand unchanged (`USER_ABSENCE` > 0.7, `EMOTIONAL` >
0.9, everything else never), "so a consumer that wires nothing sees exactly the behaviour it had
before."

And before either regime, `_NEVER_SPEAKS`. See §3.2.

### 2.6 Delivery

`temporal/outbound_events.py` already has the delivery half of initiation:
`TemporalEventType` = `PERSONA_INITIATION`, `PERSONA_FOLLOWUP`, `SCENE_NARRATION`,
`ROOM_PERSONA_REPLY`; `TemporalEventStatus` = `PENDING` → `DELIVERED` / `DISMISSED` / `FAILED`,
with a file-backed store under `data_home()`. **`PERSONA_FOLLOWUP` as a type already exists; what
does not exist is anything that decides a follow-up is due** (F5).

### 2.7 Halbert: the adapter, the gate, and the eleven

`halbert_core/attunement/` is the consumer adapter, and its docstring explains its own existence:
"`proactive/` is about *events* and `home/` is about *the house*. Attunement is about *the
person*." Modules: `surfaces.py`, `subject.py`, `sensor.py`, `operation_state.py`, `store.py`,
`reactions.py`, `shadow.py`, `codec.py`, `context.py`.

`proactive/gate.py:52` — `ProactiveGate` — is what actually decides today. `_evaluate()` returns
**every** mechanism that would eat an event, not the first, and the docstring says why:

> Eleven of them can eat a proactive event and each is silent by construction, so a log that
> names only the first gate to fire cannot distinguish a warning lost to an interaction of two
> from a warning lost to one.

In check order, the mechanisms visible in `gate.py`:

0. **Guest fronting** — checked first, because "who is speaking dominates the dial". Four things
   still pass: `guest_session` announcements, life-safety events, confirmed acoustic anomalies,
   and `critical`.
1. **The dial**, with a per-category override winning over the global level, and a
   `_USER_REQUESTED_TYPES` carve-out.
2. **Quiet hours** — delegating to the engine's `should_speak_proactively()` with life-safety
   bypass when the modality engine is present, falling back locally otherwise. `critical` and
   wake-worthy acoustic anomalies bypass.
3. **Safe mode** (guardrails) — suppresses non-critical.
4. **Snooze** on a linked finding — only while still active; an expired snooze lets the event
   through again.
5. **Dismissal** on a linked finding.

Attunement adds the rest: a standing **withdrawal**, a **limit** severity floor, a **deferred
topic**, low **receptivity**, and an unreleased **hold**.

`attunement/shadow.py` is the suppression log, and it exists because "`the-being.md` §2 ratifies
that nothing appears to the user without a why. It has a shadow the product cannot answer: **why
did I *not* hear about this?**" It keeps two artifacts deliberately apart: `gate_outcome` /
`gate_reasons` (what the product did) versus `outcome` / `reasons` / `margin` (what the engine
*would* have done), with `decision_source` naming which produced the top-level row, and `margin`
`None` — never `0.0` — when no engine decision produced one.

### 2.8 The honest state: wired, built-and-unwired, shadow

| State | What is in it |
|---|---|
| **Live** | `ProactiveGate` and its six mechanisms; the dial as four positions; quiet hours; the morning report with its `CD-8` exemption; `TimelineStore` as the event ledger; lenses as voice-only files with arithmetic selection (`CD-3`). |
| **Shadow** | `decide()` — it runs, is written down, and **acts on nothing**. Stage one of the attunement rollout. |
| **Built, unwired** | `assess_presence()` has no presence surface consuming it. `PERSONA_FOLLOWUP` has no producer. `TimelineStore.count_by_entity` and `forget_subject` have no callers. The affective half reaches the prompt only by ~12 % random intrusion. |
| **Newly closed** | `record_reaction` — Halbert's `reactions.py:179` now calls it. The engine's own 2026-09-15 digest reports it as having no caller in any repository; **on the Halbert side that is now stale**, though no labelled corpus has accumulated yet. |

Two properties of this state matter for everything below.

**Shadow mode is a free evaluation harness.** Any candidate control law can be run against live
traffic and logged without changing one thing a user experiences. §7 is short because of this.

**`CD-3` forecloses the most tempting shortcut.** Selection is arithmetic and lens-independent:
top N by (recurrence count, severity, recency), clamped by the dial; the lens file carries voice
only. "The model may phrase the selection; it may not choose it or add to it." A slider that
works by letting a model decide more at higher settings contradicts a ratified decision and the
standing directive that the system never uses a model where a template suffices.

---

## §3 The walls

### 3.1 The bottom: `OFF` is off, and the founder's 0 is not

`assess_presence` short-circuits on `dial:off` before receptivity, before the ledger, before
anything (`policy.py:379-380`). `ProactiveGate` honours `off` the same way, with one ratified
carve-out: `CD-8` gave `morning_report` a type exemption in step 1 so the report publishes at
Balanced regardless of severity — and still respects `off`.

The founder's 0 is *soft mute*: important events still speak. That is neither `OFF` nor `QUIET`,
because `QUIET` caps the earned invitation at `MINIMAL` and therefore also constrains **reply
width** on turns the user initiated — which soft mute should not touch (see the `LimitKind` split
in §2.1). So the bottom needs one of:

- **(a)** a fifth `DialLevel` between `OFF` and `QUIET`, with `OFF` kept reachable some other way;
- **(b)** a slider whose 0 *is* soft mute, with hard off **not on the slider at all**.

(b) has a precedent in the code: `DirectiveKind.WITHDRAW` already exists as the person's explicit
"leave me alone", with `withdraw_default_ttl_s` 7200, a resume condition, `revoke_on_address=True`
and `allow_critical_breaks_withdraw=True`. Hard off already has a home that is not the dial. The
cost of (b) is that a slider that cannot turn the thing off will surprise people, and the mute
affordance has to be visibly elsewhere.

### 3.2 The top: the wall is deliberate, and it is the whole feature

```python
# Thoughts that are never speech candidates, whatever the policy says
# (spec section 11.1): a thought the persona had for no reason, because
# the clock moved, or because the scene changed is not a reason to
# interrupt a person. These never reach the policy at all, so a
# permissive dial cannot turn idle chatter into speech.
_NEVER_SPEAKS = (TriggerType.RANDOM, TriggerType.TEMPORAL, TriggerType.SCENE)
```
(`autonomous_engine.py:594-599`)

Three observations, and the third is the design opening.

1. **The founder's 10 is on the other side of this line.** "A friend that just keeps the
   conversation alive" is mechanically `RANDOM` and `TEMPORAL` triggers reaching speech. No dial
   position gets there, by construction. Corroborating: `persona/event_bus.py:29` `SCENE_CHANGED`
   fires and `autonomous_engine.py:332` `on_scene_change` handles it, but `SCENE` is in
   `_NEVER_SPEAKS`, so a scene change is a cognitive event that can never become an utterance.
2. **The line is in the right place for the span it was drawn on.** A *dial* is a threshold, and
   a threshold applied to a bad impulse produces a bad utterance sooner. That reasoning is sound.
3. **It does not follow that these classes can never produce a good utterance** — only that a
   threshold is the wrong instrument for admitting them. Admission is a different act from
   ranking, and it can carry its own evidence requirement. That is precisely M3, and it is why
   M3 is the only method that reaches the top without weakening anything.

### 3.3 A third wall nobody has hit yet: the ask-band

Stated in F3 and quantified in §2.2. `ASK_FIRST` lives in the gap between `ASK_T` and `SPEAK_T`:
0.30 wide at INFO, **0.10 wide at WARNING**, and `PolicyStability.threshold_hysteresis` is 0.05 —
half that band. An eleven-position linear slider that redistributes the WARNING band allocates
0.01 per notch, below several individual receptivity weights and one fifth of the hysteresis.

This wall has no comment warning about it because nobody has designed a control that hits it yet.
It is the most likely place for a naive presence slider to produce behaviour nobody specified:

- move `SPEAK_T` down alone → at high presence the persona **stops asking and starts asserting**;
- move `ASK_T` up alone → at low presence asking **collapses into silence** rather than into a
  quieter ask;
- move both by the same delta → the band is preserved, which is almost certainly what is wanted,
  and which means **the slider is a translation of a band, not a scaling of a threshold**.

---

## §4 Eight candidate control laws

Each states: the mechanism, its formal shape, the evidence, what it would cost here, what it
buys, its failure modes, and the discriminating test — **can it express 0 and 10 as the founder
defined them?**

### M1 — Threshold shift (decision-theoretic)

**Mechanism.** The slider scales the cost-of-interruption term, moving the probability threshold
at which action beats inaction.

**Formal shape.** Horvitz's, exactly [L1]. With `E` the evidence and `G` the user's goal:

```
eu(A|E)  = p(G|E)·u(A,G)  + [1−p(G|E)]·u(A,¬G)
eu(¬A|E) = p(G|E)·u(¬A,G) + [1−p(G|E)]·u(¬A,¬G)
```

These cross at `p*`, "the threshold probability … [where] the expected value of action and
inaction are equal", and the rule is to act above it and refrain below. Crucially for us, Horvitz
shows `p*` is **context-dependent**: "The utility of unwanted action can diminish significantly
with increases in the depth of a user's focus on another task. Such a reduction in the value of
action leads to a higher probability threshold." That *is* receptivity, and the engine already
implements it as an additive margin rather than a recomputed threshold — an equivalent framing.

**And it is two thresholds, not one.** Horvitz's "Dialog as an Option for Action" adds `u(D,G)`
and `u(D,¬G)` and derives `p*¬A,D` and `p*D,A`, observing that dialog-when-not-wanted typically
costs less than action-when-not-wanted, while asking-before-a-wanted-action is typically worth
less than simply acting. The engine's `ASK_T` / `SPEAK_T` pair is this, per severity.

**Cost here.** Near zero. `SPEAK_T`, `ASK_T`, `HOLD_WORTH_T` and `margin` all exist.

**Buys.** Principled; composes with receptivity; one parameter per band.

**Failure modes.**
- *Uninterpretable.* A threshold on an unscaled internal utility cannot be predicted by a user.
  Nobody can say what 4 does.
- *Band collapse.* §3.3 in full. At WARNING the band is 0.10 wide.
- *No new kinds.* A threshold re-ranks what already wants to be said. It cannot admit what never
  reaches it.

**Reaches 0?** No — a threshold high enough to suppress chatter also suppresses the important
events the founder wants preserved, unless severity is carved out separately, at which point the
carve-out is doing the work.
**Reaches 10?** No. `_NEVER_SPEAKS` is upstream.

**Verdict.** Necessary plumbing; insufficient as the law. Best **derived** from the other axes
rather than exposed. If it is exposed, it must be exposed as a band translation.

### M2 — Rate budget (attention allowance)

**Mechanism.** The slider sets a budget `B` of unbidden interruptions per period. The policy
spends it and must prioritise; a spent budget means silence regardless of merit.

**Evidence.** A real and directly transferable literature. Baek, Boutilier, Farias, Jonasson and
Yoeli address "optimizing personalized interventions for patients to maximize a long-term
outcome, where interventions are costly and capacity-constrained", and their DecompPI decomposes
the state space to the individual level and approximates one step of policy iteration — notably,
implementation "simply consists of a prediction task using the dataset, alleviating the need for
online experimentation." Their headline: the same efficacy as the status quo "with approximately
half the capacity of interventions" [L25]. The JITAI line already in the family's verified O4
citations is the same shape.

**Cost here.** Near zero: `AttachmentSafety.max_proactive_per_day=3` already **is** this, as a
fixed ceiling rather than a user control.

**Buys.** The single most **interpretable** thing a slider can do. "About three a day" is a
sentence a person can predict and afterwards verify. It bounds harm directly; it is trivially
testable; and it is the one axis where the safety argument and the UX argument point the same way.

**Failure modes.**
- *Says nothing about what.* A budget spent on trivia is worse than an unspent one.
- *Use-it-or-lose-it.* A budget framed as an allowance invites spending. The engine's framing —
  "ceilings speech can never raise" — is the correct one and must survive (C-2).
- *Interacts badly with severity.* A critical event arriving on an exhausted budget must not be
  suppressed, so the budget needs a bypass, and a bypass needs a definition.

**Reaches 0?** Partly — B=0 with a severity bypass is a serviceable soft mute, and is arguably the
simplest implementation of it.
**Reaches 10?** No. A friend is not defined by a quota.

**Verdict.** Strong axis, wrong as the whole law. Probably the axis whose *per-position numbers*
should be the published specification of each notch (§7).

### M3 — Source admission ladder

**Mechanism.** The slider admits successively more **classes of impulse**. Each position is a
set, not a number. `_NEVER_SPEAKS` stops being a constant and becomes the tail of a ladder.

Illustrative only — the actual rungs are §8.2:

| Position | Admits |
|---|---|
| 0 | life safety and `critical` only |
| 2 | + warnings on the machine's own state |
| 3 | + the morning report, recurrence remarks from the observation ledger |
| 5 | + findings whose subject the user has touched recently |
| 7 | + open loops falling due ("you said the migration was Tuesday") |
| 8 | + memory associations from the current turn's subject |
| 10 | + temporal and spontaneous impulses |

**Evidence.** This is how the proactivity literature actually taxonomises, and three independent
lines converge on it.

- Bui and Evangelopoulos propose exactly three levels — **reactive** (responds to explicit
  requests), **scheduled** (predefined timing triggers), **situation-aware** (adapts on
  contextual understanding) — and their evaluation targets are Insight Decision Quality, Context
  Grounding Score and Learning Lift, grounded in mixed-initiative principles [L13].
- A six-level taxonomy for healthcare agent autonomy adapted from the SAE driving levels does
  the same, framed as how "an agent's reactive and proactive stance should adapt with its
  increasing capabilities" [L13, same line].
- The variable-autonomy literature is the mature version: Theodorou, Chiou, Lacerda and Rothfuß
  define VA as "the ability of the robotic systems to dynamically vary their level or degree of
  autonomy to collaborate with the human(s) efficiently and based on the context", explicitly
  encompassing shared control, shared autonomy, mixed-initiative, adjustable autonomy, sliding
  autonomy and adaptive automation [L19].

**Cost here.** Moderate, and the cost is specific: the two impulse vocabularies must be
reconciled. The engine types impulses by `TriggerType` (nine cognitive origins); Halbert types
them by `ProactiveEvent` category and severity (an operational taxonomy). One ladder rung has to
name a set that is well-defined in both. That is the main work item and it is not trivial.

**Buys.** The property no other method has: **every position has a sayable meaning**. The
settings surface becomes a list of what the system is allowed to bring up — satisfying the
standing directive that everything carries its why, and matching the user-control finding that
explicit, intelligible control raises perceived transparency and trust rather than merely
perceived variety [L20]. It is also the only method that reaches the top, because admitting a
class is a different act from lowering a threshold and can carry its own evidence requirement.

**Failure modes.**
- *Discreteness.* A ladder is notches. The rung count is a design commitment that is expensive to
  revise once each rung has a published description and an FP budget.
- *Silent on timing.* Admission says nothing about when.
- *Non-monotone surprise.* Moving 7→8 changes a *kind*, which a user expecting "a bit more" may
  not want.

**Reaches 0?** Yes — the bottom rung is "life safety and critical only", which is soft mute
stated as a set.
**Reaches 10?** **Yes** — the only method that does.

**Verdict.** The strongest single candidate. It dissolves the top wall in the right way: as an
admission decision with its own evidence bar, not as a threshold that got permissive.

### M4 — Model-level behavioural conditioning

**Mechanism.** The slider becomes an inference-time coefficient on the model itself. Two concrete
forms exist in the 2025–2026 literature.

*Behavioural tokens.* BehaviorSFT (Kim et al., 14 authors) is "a novel training strategy using
behavioral tokens to explicitly condition LLMs for dynamic behavioral selection" across a
clinical assistance spectrum from reactive to proactive, where proactive means "unprompted
identification of critical missing information or risks". Reported up to 97.3 % overall Macro F1
on its own BehaviorBench, with clinician evaluation finding "a superior balance between helpful
proactivity and necessary restraint" [L11].

*Activation steering sliders.* Hoppe, Khachaturov, Mullins and Meng propose Sequential Adaptive
Steering, which "orthogonalizes steering vectors by training subsequent probes on the residual
stream shifted by prior interventions", giving per-trait alpha coefficients that compose. Their
stated motivation is a warning for us: "naive approaches fail to control multiple traits
simultaneously due to destructive vector interference" [L15]. Validated on the Big Five.

**Cost here.** High, possibly prohibitive. Activation steering needs the residual stream; the
family routes through connection slots that may be cloud endpoints where that access does not
exist. Behavioural tokens need fine-tuning, which the family does not do. Both are
non-deterministic where the directives push toward determinism.

**Buys.** The only method that changes the *manner* of presence continuously rather than the
*fact* of it. That is not nothing — much of what reads as present is register, not frequency.

**Failure modes.** It does not decide whether to speak, only how. It cannot honour `CD-3`. And
per L15's own finding, **independent persona sliders interfere destructively** — a direct warning
against any design that imagines several such controls side by side.

**Reaches 0?** No. **Reaches 10?** No — it shapes speech that is already happening.

**Verdict.** Reject for initiation. Keep on file for reply width and register. **Flag L15 to the
persona-authoring consumer independently** — orthogonalised trait sliders are that product's
central problem, not this one's.

### M5 — Learned policy, slider as prior

**Mechanism.** The outcome ledger feeds a contextual bandit; the slider sets the prior on the
speak rate and the exploration budget; reactions move realised behaviour.

**Evidence.** Already in the family's verified O4 citation set: off-policy replay (Li, Chu,
Langford & Wang, WSDM 2011), the doubly-robust estimator (Dudík, Langford & Li, ICML 2011), and
the mHealth receptivity line (Künzler 2019, Mishra 2021) showing receptivity is learnable from
context with F1 as the metric. The infrastructure was built for this.

**Cost here.** The data does not exist. Reactions began being recorded recently; no labelled
corpus has accumulated.

**Failure modes.** Two, and both are severe.

*The asymmetry.* Halbert's own `reactions.py` module docstring states it, and it is the sharpest
warning in either tree:

> A loop that sees its speaking decisions punished and its silences never evaluated ratchets
> toward silence, and a quiet assistant looks well-behaved while getting worse.

The same file carries two rules that exist to stop the ledger being contaminated: "**A reaction
is a person's, not a process's**" — called only from surfaces where a human did something, never
from `FindingStore`, where an automatic cleanup would enter the ledger looking exactly like a
person saying no — and "**Silence is not a reaction**": `sweep_ignored` never touches an attempt
the gate suppressed, because "a negative label minted from the product's own silence would
corrupt the one arm Phase C most needs to trust."

*The objective.* If the objective is ever engagement rather than well-judgedness, the 2026
companion literature is explicit about the destination: harmful behaviours arising from
misaligned optimisation aimed at maximising engagement, with high-intensity relationship-seeking
producing self-reinforcing demand cycles [L26, L27].

**Reaches 0?** No. **Reaches 10?** Only by the route we should least want.

**Verdict.** Not v1, and never the primary law. Its correct role is **offline evaluation of an
authored curve** — replay the ledger to ask whether position 3 was well set (§7).

### M6 — Channel re-mapping

**Mechanism.** The slider does not change whether the system has something to say. It changes
**how it arrives**. Low presence routes an impulse to `PULL`; mid to `AMBIENT`; high to `PUSH`.
Nothing is lost at any setting; what changes is whether it spends attention.

**Evidence.** Calm technology, directly and without adaptation [L21]; see §1.2. The
co-presence literature supplies the second half: awareness, not utterance, is what carries
presence [L22]. The believability literature supplies the third: at the low end the alternative
to peripheral presence is the zombie effect [L23], and cheap idle signals are sufficient [L24].

**Cost here.** Low. `ChannelClass` exists in both trees; Halbert's `Surface` enum maps every way
it can reach a person; the suppression log already records channel.

**Buys.**
- **The founder's 0, exactly.** Stop interrupting, not stop noticing — with no new enum value.
- The governing rule is already written and already correct (`surfaces.py`): a withdrawal "must
  silence the voice and the panel that opens itself. It must not empty the bell, and it must
  never hide a findings row — suppressing a surface the user navigates to destroys information
  they asked to be able to find."
- Deterministic, testable, no model, honours `CD-3` trivially.
- It is the method that makes "presence" mean something other than "talkativeness", which is F1.

**Failure modes.**
- Does not produce companionship at the top; routing to `PUSH` is not the same as having
  something worth pushing.
- `AMBIENT` has a documented constraint — "may update, must not escalate" — so an ambient channel
  cannot be used to sneak urgency through at low settings.
- Ambient signals still cost something. Calm technology is not free technology; a badge that
  changes constantly is a push in slow motion.

**Reaches 0?** **Yes**, better than any other method.
**Reaches 10?** No.

**Verdict.** The cheapest large win in the space and the most under-weighted in the current
design. Very likely the first thing to build regardless of which law wins.

### M7 — Patience (when, not whether)

**Mechanism.** The slider controls how long an impulse waits for a good moment before it either
speaks or expires. Low presence = long patience, waits for a coarse breakpoint, may expire
unspoken (having been routed to `PULL` by M6). High presence = short patience.

**Evidence.** The strongest empirical base in this document.

*Breakpoints.* Adamczyk and Bailey's hierarchical task model predicted and found that **coarse**
breakpoints — between chunks — elicit smaller resumption costs than fine ones, with reductions in
frustration, annoyance, time pressure, resumption lag, mental demand and mental effort [L18].
Iqbal and Bailey later showed coarse/medium/fine breakpoints can be inferred **without
supplementary hardware**, from event-log features such as "switched to another document",
"closed an application", "completed scroll", with average accuracy of **69 % to 87 %** per class
[L16, via L17]. An earlier pupillometry approach inferred mental workload with average error
2.81 % and 2.3 % on route-planning and document-editing tasks — accurate but requiring a
head-mounted eye tracker [L17].

*Deployed.* Okoshi et al.'s Attelia detects breakpoints in phone interaction in real time from
on-device sensors and defers notifications to them. Controlled study, 37 participants: cognitive
load (NASA-TLX) of users **more sensitive to interruptions** reduced by **46 %** versus random
timing. In-the-wild study, 30 participants: **33 %** cognitive-load reduction, with notifications
at breakpoints also receiving quicker responses [L17]. (See §12 for a discrepancy on these
figures.)

*Bounded deferral, and the number that matters most to us.* Horvitz, Apacible and Subramani coined
"bounded deferral". A study of 113 users across busy and free states found users **switch from
busy to free in approximately two minutes**, and that medium- and low-urgency email can be
deferred **three and four minutes** respectively — concluding that bounded-deferral policies
"reduce the level of interruption while allowing users to be aware of important information"
[L17].

**Cost here.** Low to moderate, and it rescues something already built. `HOLD` carries a resume
condition and a deadline; patience-as-the-slider turns release from a liability into the main
mechanism. It requires a breakpoint signal, which Halbert can plausibly derive (operation state,
terminal activity, focus changes) and which the other consumers largely cannot.

**A concrete finding, from putting the two together.** `HOLD_MAX_S` is **7200 seconds**. The
bounded-deferral literature finds the useful deferral window is **two to four minutes**. Our
patience ceiling is roughly two orders of magnitude longer than the interval over which deferral
was shown to help. Either `HOLD` is being used for something other than bounded deferral — in
which case bounded deferral is a *missing* mechanism, not a configured one — or the ceiling is
badly calibrated. This is a defect-shaped observation and §8 carries it.

**Buys.** A large fraction of perceived well-judgedness, on the best evidence available. Note the
effect sizes: 46 %/33 % cognitive load from *timing alone*, with content and frequency unchanged.
No threshold tweak in M1 will buy anything comparable.

**Failure modes.** Alone it is a timing knob — it changes *when*, never *what* or *whether*. And
it inherits the `HOLD` warning in full: patience without release is silence.

**Reaches 0?** Partly — infinite patience plus M6 routing is a coherent soft mute.
**Reaches 10?** No.

**Verdict.** Strong axis, under-represented, and carrying the largest measured effects in the
literature. Its interaction with §3.3's band is also the cleanest: patience changes *when* the
margin is evaluated rather than *where* the thresholds sit, so it moves behaviour without
narrowing the ask-band.

### M8 — Authored curve through a parameter vector

**Mechanism.** The slider is one visible number indexing a **named, inspectable curve** through
the space (admission set, channel map, patience, budget), with thresholds derived. The curve is a
design artifact: authored, versioned, testable, per consumer.

**Evidence.** This is the standard resolution of the one-knob problem wherever it has been solved.
The HCI guidance is that a slider is appropriate "when a plurality of settings can be abstracted
to a single range", that it is **experts** who are "capable of mapping combinations to slider
control settings by understanding intuitively how settings combine and interact", and that
sliders are "less useful when a user is interested in more than one abstract characterization of
a process" [L14, L20]. The abstraction is legitimate precisely when someone has done the work of
authoring it.

Two further pieces of that guidance are directly actionable. First, sliders suit **exploration**
but not **precision** — "acquiring a precise value on a slider is difficult, due to the Accot-Zhai
Steering Law" — and the standard remedy is a **linked control**: a coarse slider paired with a
precise input [L14]. Our precise input already exists as `ProactivityDial.overrides`. Second,
sliders work when users "can scrub through the range of the control and see the effects in real
time" and are "not a good choice" where results take time to appear [L14] — **which is exactly our
situation**, since the effect of a presence setting is observable only over days. §8 treats this as
the strongest objection to the slider metaphor itself.

**Cost here.** The curve must be authored and defended. That is a real design deliverable.

**Buys.** Honesty about the two ends meaning **different kinds of thing** — which is how the
founder described them, and which no monotone single-parameter method can express. And it gives
the cross-app story its shape: same space, different curves, different ceilings (§6).

**Failure modes.** Non-monotone surprise (see M3); an unauditable curve is worse than an
unprincipled threshold; and the number of notches must stay small enough that each can be
described.

**Reaches 0 and 10?** As a container, yes to both.

**Verdict.** The most likely frame. It is not an alternative to M2/M3/M6/M7 — it is the container
for them.

### 4.9 Summary

| | Method | Reaches 0 | Reaches 10 | Cost | Deterministic | Interpretable per position |
|---|---|---|---|---|---|---|
| M1 | Threshold shift | No | No | ~0 | Yes | No |
| M2 | Rate budget | Partly | No | ~0 | Yes | **Yes** |
| M3 | Source admission ladder | **Yes** | **Yes** | Moderate | Yes | **Yes** |
| M4 | Model-level steering | No | No | High | No | No |
| M5 | Learned policy | No | Unsafe | Blocked | No | No |
| M6 | Channel re-mapping | **Yes** | No | Low | Yes | **Yes** |
| M7 | Patience | Partly | No | Low–mod | Yes | Partly |
| M8 | Authored curve | Container | Container | Design | Yes | **Yes** |

### 4.10 Composition

Which combine cleanly, which fight:

- **M3 + M6 compose orthogonally.** Admission says *whether it may be raised at all*; channel says
  *how it arrives*. They are independent, and the product of the two is a surprisingly expressive
  space — e.g. "admitted, but ambient only", which is an excellent mid-slider behaviour that
  neither produces alone.
- **M7 composes with everything** because it acts on time rather than on the margin, so it does
  not narrow the ask-band (§3.3).
- **M2 constrains M3.** Admitting a class raises volume; the budget is what stops admission from
  compounding. They must be designed together, and the budget must be the ceiling.
- **M1 should be derived, not composed.** Once admission, channel, patience and budget are set,
  the thresholds are nearly determined. Exposing M1 *as well* gives two controls over one
  quantity.
- **M4 and M5 are late additions to any of the above**, and M5 must never be the outer loop.

---

## §5 Cross-cutting constraints

Any candidate must satisfy these. They emerged repeatedly across methods.

**C-1 — The two axes stay two.** The slider is the *set* axis. `InvitationLevel` must remain
separate, must keep decaying toward the slider's implied target, and must keep being capped by it
(§2.4). Collapsing them lets a persona talk its way up its own dial.

**C-2 — Ceilings are not targets.** `AttachmentSafety` is framed as "ceilings speech can never
raise". A budget that becomes a quota to spend is a regression.

**C-3 — The top is not reachable by the persona's persuasion.**
`persona_may_solicit_invitation=False` exists for this and renders as a hard constraint in every
`[ATTUNEMENT]` block. The 2026 harm literature names the failure: engagement-optimised systems
adopting manipulative tactics [L27].

**C-4 — Regularity over unpredictability at the top.** There is a strong temptation to make high
settings feel alive through *unpredictable* contact. Variable-ratio schedules are the most
engagement-maximising and most extinction-resistant reinforcement pattern, and are the documented
mechanism behind compulsive notification-checking [L28]. **The feature must be designed against
its own most effective implementation.** Position 10 should be *more regular*, not more
surprising.

**C-5 — The risk is not symmetric across consumers.** Position 10 in Halbert is a computer that
comments on your machine too often — irritating, recoverable. Position 10 in the companion
consumer is, mechanically, the definition of the product class the harm literature is about
(F6, [L26]). The same scale cannot carry the same permissions in both. This is the strongest
argument for §6's split.

**C-6 — `CD-3` holds.** Selection stays arithmetic. A model may phrase what the slider admitted;
it may not choose it.

**C-7 — Nothing silent may be unexplainable.** Eleven mechanisms can already eat a proactive
event. A slider adds more. `SuppressionRecorder` must see every new suppression path, or "why did
I not hear about this?" becomes unanswerable again — and that question is the one `shadow.py`
exists to answer.

**C-8 — Proactive limits must not narrow solicited answers.** The `LimitKind` split (§2.1) is
already explicit that `SEVERITY_FLOOR` and `TOPIC_SCOPED` constrain proactive speech only. A
presence slider that also shortens replies to direct questions has conflated two axes the engine
deliberately separated.

**C-9 — The ask-band survives.** §3.3. Whatever moves, `ASK_FIRST` must remain reachable at every
position where asking is the right behaviour, and its width must not fall below the hysteresis.

**C-10 — Critical is not on the slider.** Life safety and `critical` bypass the guest gate, quiet
hours, safe mode and `CRIT` thresholds of −2.0 today. Every one of those carve-outs must be
re-stated against the new control, and none may become slider-dependent.

---

## §6 What belongs in the engine, and what does not

The founder's framing — build as much into the engine as possible so the siblings can use it —
survives this pass. `ENGINE-1` already rules that shared mechanisms live in Haloysius, forced by
licensing rather than preference: a mechanism originating in GPL Halbert cannot be taken up by a
closed sibling.

**Engine.** The parameter *space* and the control *law*: the admission ladder's type system, the
channel map's semantics, the patience/release contract, budget accounting, and the scalar→vector
resolution. Plus the **conformance vectors**, which `conformance.py` already establishes as the
mechanism by which two consumers can be shown to implement the same law rather than merely claim
to.

**Consumer.** Two things, and they are the two that differ most.

*Impulse sources — the real seam.* One ladder rung means four different things:

| Consumer | "Memory association" rung means |
|---|---|
| Halbert | a recurrence in the observation ledger; a finding whose entity the user just named |
| Companion | a relational memory, an emotional-state association, a drive |
| BrightestMinds | a passage from the figure's own corpus bearing on what was said |
| Persona-authoring | a *simulated* association, at authoring time, so a persona can be felt before export |

The engine should **type the rung** and let the consumer fill it. This is exactly the shape of
the existing seam contract (`SituationSensor`, `StandingRequestStore`), and it is why the engine
ships no sensor code by charter.

*The curve and the ceilings.* Per C-5, the engine ships a conservative default curve and each
consumer re-authors it and re-sets `AttachmentSafety`. The engine's current defaults are
described in their own docstring as "a companion's" — which, given C-5, is the right place for
the strictest numbers to live, not the loosest.

**Unresolved.** The persona-authoring consumer's need is genuinely odd: it does not want presence
in production, it wants presence **demonstrable at authoring time**, so a persona can be
calibrated before export. That may be a consumer-side simulation harness rather than anything the
control law should know about. Flagged, not resolved.

---

## §7 How we would know a position is right

Short, because the harness mostly exists.

**Shadow first, always.** Any candidate curve runs in `shadow.py`'s lane — `decide()` evaluates
and acts on nothing — before it touches a user. This is already stage one of the attunement
rollout and costs nothing to reuse. `decision_source` and a `None`-not-`0.0` margin mean the
shadow rows are already distinguishable from product decisions.

**Specify each position as a false-positive budget, not a threshold.** From L13: judge "not by
how often an agent acts, but by whether it surfaces the right insight at the right time, with
enough evidence, and stays silent when intervention is unwarranted." The verified O4 method is
recall of true triggers plus false-positive rate on no-trigger fixtures. So the specification of
position 3 is a sentence like *"at most one unwanted interruption per week, at ≥90 % recall on
critical fixtures"* — testable in a way "threshold 0.6" is not, and directly the M2 axis.

**Off-policy replay for the "is it right" half.** Li et al. (WSDM 2011) and the doubly-robust
estimator (Dudík et al., ICML 2011), both already in the family's verified citations, score a
candidate curve against logged context→decision→outcome triples by the outcomes of the logged
decisions it agrees with. This is the correct use of M5's machinery.

**Instrument the asymmetry, or every evaluation will conclude "lower".** Per `reactions.py`, only
the speaking arm is observable. Some deliberate sampling of the silence arm is the only obvious
remedy — the system occasionally asking whether something it held should have been said — and
that is itself a proactive act that must come out of the budget. **This is a design requirement,
not a nice-to-have**: without it, any learned or tuned presence setting drifts down indefinitely
and the product gets quietly worse while looking well-behaved.

**A test the slider metaphor must pass.** Per L14, sliders suit real-time scrubbing and are poor
where results take time. A presence setting's effect is visible over days. Either the settings
surface provides a **preview** — "at this setting, here is what I would have said to you in the
last week, and what I would have held" — reconstructable from the shadow log, or the control is
unscrubbable and the user is guessing. The shadow log makes that preview cheap, and it may be the
single highest-value UI affordance in the whole feature.

---

## §8 Open questions, in dependency order

**§8.1 — What does it actually say at 8 and above? (BLOCKING)**
Not a policy question. The engine's own presence digest names this as O2's gap G1: no repository
has a commitment or open-loop record with a due condition, and the extraction, invention and
hierarchy-summarisation paths are placeholders, so nothing learns "the interview is Tuesday" in
the first place. `PERSONA_FOLLOWUP` exists as a delivery type with no producer. The direction is
in the proactive-memory literature — Wu et al. treat memory as "an active intervention mechanism
rather than passive retrieval", with a separate memory agent deciding whether to inject, and
report selective intervention beating passive exposure, always-on injection, advisor-only
guidance and general retrieval (+8.3 pp Terminal-Bench 2.0, +6.8 pp τ²-Bench) [L29].
**Recommendation: specify the ladder to the top now; leave the top rungs unreachable until there
is something behind them.**

**§8.2 — How many rungs, and is the control continuous?**
0–10 is eleven positions. The literature's taxonomies use three to six [L13, L19]. Eleven notches
means eleven authored descriptions and eleven FP budgets, and §3.3 shows an eleven-position
linear redistribution of the WARNING ask-band allocates 0.01 per notch. A five- or six-position
ladder with a 0–10 *presentation* may be the resolution, but it is a real decision either way.

**§8.3 — Is hard off on the slider?**
§3.1. Soft mute at 0 with hard off as a separate act is the more honest structure and already has
a home in `WITHDRAW`. But a slider that cannot turn the thing off will surprise people.

**§8.4 — One number or two?**
ProactBench's authors decompose proactivity into three phases — **Emergent** (inference from a
single disclosed anchor), **Critical** (synthesis across multiple anchors), **Recovery**
(grounded forward-looking value after task completion) — over 198 curated dialogues with 624
trigger points across 24 communication styles, and find Recovery both difficult and weakly
predicted by six standard benchmarks [L12]. The founder's own description already contains two
axes: *how often* and *what kind*. M8 exists to hide that. Worth deciding deliberately rather
than discovering later, and L14's linked-control guidance suggests the second axis may belong in
the per-category overrides that already exist.

**§8.5 — What is the default, and what does it decay to?**
The founder said 3 of 10. The engine's default is `BALANCED`, mapping to `NORMAL` invitation with
a `CHATTY` ceiling. If 3 is the default, most of the range is *above* it — unusual for a slider,
and it needs a reason. It also needs `invitation_for_dial`'s decay target restated on the new
scale.

**§8.6 — `HOLD_MAX_S` versus bounded deferral.**
Raised in M7: our patience ceiling is 7200 s; the deferral literature's useful window is 120–240 s
[L17]. Either `HOLD` is not bounded deferral — in which case bounded deferral is missing — or the
ceiling is miscalibrated. This is defect-shaped and should be checked independently of the slider.

**§8.7 — Is the slider per-subject?**
`SubjectConfidence` and per-subject standing requests already exist, and the guest-persona work
landed. One household, several people, one slider is probably wrong; one slider per person is
probably too much configuration. The `UNKNOWN` inheritance rule (most-restrictive for
un-addressed PUSH) is a precedent for a middle answer.

**§8.8 — Who authors the per-consumer curves?**
C-5 says they differ. If the engine ships the strictest defaults and each consumer relaxes them,
the relaxation is a safety decision being made in four places. A single reviewed table with a
named owner is the alternative.

---

## §9 Literature, per source

Numbers are **block-allocated by theme** — L1–L10 decision theory and interruptibility, L11–L20
proactivity, autonomy and control, L21–L30 presence, safety and memory. Unused numbers inside a
block are simply unallocated. Each entry states its verification status; §10 is the summary
record.

### Block 1 — Decision theory and interruptibility

**[L1] Horvitz, Eric. *Principles of Mixed-Initiative User Interfaces.* CHI '99, Microsoft
Research.** — **VERIFIED** (PDF fetched and extracted locally, 2026-09-16).

The foundational source for M1 and, less obviously, for the engine's whole outcome vocabulary.
Twelve principles are enumerated; the ones that bear on a presence control are:

> (2) Considering uncertainty about a user's goals. (3) Considering the status of a user's
> attention in the timing of services … "Agents should employ models of the attention of users
> and consider the costs and benefits of deferring action to a time when action will be less
> distracting." (4) Inferring ideal action in light of costs, benefits, and uncertainties.
> (5) Employing dialog to resolve key uncertainties … "considering the costs of potentially
> bothering a user needlessly." (7) Minimizing the cost of poor guesses about action and timing …
> "including appropriate timing out and natural gestures for rejecting attempts at service."
> (8) Scoping precision of service to match uncertainty … "A preference for 'doing less' but
> doing it correctly under uncertainty." (10) Employing socially appropriate behaviors.
> (11) Maintaining working memory of recent interactions. (12) Continuing to learn by observing.

Principle 3 is M7 stated in 1999. Principle 7's "appropriate timing out" is the `HOLD` deadline.
Principle 8 is `SPEAK_MINIMAL`. Principle 11 is the standing-request ledger. Principle 12 is M5.

The expected-utility analysis is §4's M1 in full. The part that matters most and was least
expected is **Dialog as an Option for Action**: adding `u(D,G)` and `u(D,¬G)` yields two
thresholds, `p*¬A,D` and `p*D,A`, because "the utility of engaging in a dialog with a user when
the user does not have the goal in question is typically greater than the utility of performing
an action when the goal is not desired. However, the utility of asking a user before performing
a desired action is typically smaller than the utility of simply performing a desired action."
That asymmetry is why `ASK_FIRST` exists and why it occupies a **band**. See F3 and §3.3.

Also relevant to C-5 and per-consumer curves: Horvitz shows `p*` shifts with context, and gives
an example directly analogous to ours — the cost of unwanted action "can diminish significantly
with increases in the depth of a user's focus on another task", while more screen real estate can
*reduce* the perceived cost of a needless service. The threshold is a function of the surface,
not just the person. That is an argument for M6 being part of the law rather than a presentation
detail.

**[L2] Horvitz, Apacible & Subramani. *Balancing awareness and interruption: investigation of
notification deferral policies.*** — **Reported by L17 (verified); primary not fetched.**

Coined "bounded deferral". A study of 113 users across busy and free states (a day each, with a
"Busy Context" tool for self-labelling) found users switch busy→free in approximately **two
minutes**, and that medium- and low-urgency email can be deferred **three and four minutes**
respectively; bounded-deferral policies "reduce the level of interruption while allowing users to
be aware of important information."

This is the most directly actionable number in the document and the basis of §8.6. It says the
useful deferral window is minutes, not hours, and that the benefit comes from *bounded* waiting —
deferral with a short deadline — rather than open-ended holding.

**[L3] Horvitz & Apacible. *Learning and Reasoning about Interruption.* ICMI 2003.**
**[L4] Fogarty, Hudson, Atkeson, Avrahami, Forlizzi, Kiesler, Lee & Yang. *Predicting Human
Interruptibility with Sensors.* ACM TOCHI 12(1), 2005.**
**[L5] Cha et al. *"Hello There! Is Now a Good Time to Talk?"* IMWUT 4(3), 2020.**
— **Verified in the family's existing `RESEARCH-SOCIAL-ATTUNEMENT-CITATIONS.md`; not re-verified
here.** These three supply the receptivity weights in `constants.py` (§2.3) and the design rule
the engine follows — "the engine never needs a camera; it needs a small set of typed
observations". They are listed for completeness because a presence slider that changes how
receptivity is used inherits their calibration.

### Block 2 — Proactivity, autonomy and control

**[L11] Kim, Yubin, et al. (14 authors). *BehaviorSFT: Behavioral Token Conditioning for Clinical
Agents Across the Proactivity Spectrum.* arXiv:2505.21757, cs.CL, 27 May 2025.** — **VERIFIED.**

Trains behavioural tokens to "explicitly condition LLMs for dynamic behavioral selection" along a
reactive→proactive spectrum, where proactive means "unprompted identification of critical missing
information or risks". Up to 97.3 % overall Macro F1 on its own BehaviorBench; Qwen2.5-7B-Ins
proactive task score 95.0 % → 96.5 %. Clinician evaluation found "more realistic clinical
behavior, striking a superior balance between helpful proactivity and necessary restraint."

*For us:* the strongest existence proof that a proactivity *spectrum* is a trainable, conditioned
property rather than an emergent one — and simultaneously the clearest statement of why M4 is out
of reach, since the mechanism is fine-tuning. The abstract does not disclose the inference-time
selection mechanism, so how the level is *chosen* at run time is not answered by this paper.

**[L12] Harfi, Salimi, Shen & Smola. *ProactBench: Beyond What The User Asked For.*
arXiv:2605.09228, cs.LG, 9 May 2026.** — **VERIFIED.**

Benchmarks "conversational proactivity" — acting on users' implied but unstated needs — in three
phases: **Emergent** (inference from a single disclosed anchor), **Critical** (synthesis across
multiple anchors), **Recovery** (grounded forward-looking value after task completion). Corpus:
198 curated dialogues, 624 trigger points, 24 communication styles, evaluated across 16 frontier
and open-weight models. Finding: **Recovery is both difficult and weakly predicted by six standard
benchmarks.**

*For us:* two things. First, the three-phase decomposition is evidence against a single scalar
(§8.4). Second, **Recovery is the phase our top-of-slider needs and the phase everyone is worst
at** — "grounded forward-looking value after task completion" is very nearly a definition of the
open-loop follow-up that §8.1 says does not exist here. That it is weakly predicted by standard
benchmarks means we cannot infer our own capability from general model quality.

**[L13] Bui, Nghi D. Q. & Evangelopoulos, Georgios. *Agentic Coding Needs Proactivity, Not Just
Autonomy.* arXiv:2605.06717, position paper, 7 May 2026.** — **VERIFIED.**

Separates proactivity from autonomy: autonomous systems execute independently; proactive systems
must "notice relevant changes before the developer asks, connect signals across tools, decide when
to interrupt." Three-level taxonomy — **Reactive**, **Scheduled**, **Situation Aware**. Evaluation
targets: Insight Decision Quality, Context Grounding Score, Learning Lift. Framework centres on
"the policy that decides what matters next, what evidence supports it, whether to show it",
explicitly grounded in mixed-initiative principles (i.e. L1).

*For us:* the source of M3's ladder shape and of §7's framing. Its evaluation principle — judge
"not by how often an agent acts, but by whether it surfaces the right insight at the right time,
with enough evidence, and stays silent when intervention is unwarranted" — is the single sentence
most at odds with a frequency-calibrated slider, and should probably be quoted in whatever spec
follows.

**[L14] Nielsen Norman Group. *Sliders, Knobs, and Matrices: Balancing Exploration and
Precision.*** — **VERIFIED** (fetched; page carries no author byline or date in the retrieved
content).

Sliders work "when users can scrub through the range of the control and see the effects in real
time" with feedback ≤0.1 s, and are "not a good choice" where results take time to render or
load. They favour exploration over precision — "acquiring a precise value on a slider is
difficult, due to the Accot-Zhai Steering Law" — and the remedy is **linked controls**: a coarse
slider paired with a precise input.

*For us:* the most uncomfortable source in the document, and the reason §7 ends where it does. A
presence setting's effect is visible over *days*, which is the failure condition this guidance
names. Either the settings surface offers a shadow-log-driven preview, or the control is
unscrubbable. The linked-control remedy maps onto `ProactivityDial.overrides`, which already
exists.

**[L15] Hoppe, Florian; Khachaturov, David; Mullins, Robert; Meng, Mark Huasong. *Controllable
and explainable personality sliders for LLMs at inference time.* arXiv:2603.03326, cs.CL,
10 February 2026.** — **VERIFIED.**

Sequential Adaptive Steering "orthogonalizes steering vectors by training subsequent probes on
the residual stream shifted by prior interventions", turning steering vectors into reusable
primitives with per-trait alpha coefficients. Validated on the Big Five. The stated problem it
solves: "naive approaches fail to control multiple traits simultaneously due to destructive vector
interference."

*For us:* the literal "personality slider", and a warning rather than a template. The
interference finding argues against any design with several independent persona sliders side by
side. **Worth referring to the persona-authoring consumer on its own merits** — it is that
product's central problem far more than it is ours.

**[L16] Iqbal & Bailey (2007). Models for detecting and differentiating breakpoints during
interactive tasks.** — **Reported by L17 (verified); primary not fetched.**

Inferred coarse, medium and fine breakpoints **without supplementary hardware**, using event-log
features derived from observers' explanations ("switched to another document", "closed an
application", "completed scroll"). Per-class statistical models reached average accuracy of
**69 % to 87 %**. Separate models and features per breakpoint type.

*For us:* the feasibility evidence for M7 on a desktop-shaped consumer. The feature list is
strikingly close to signals Halbert already has or could have (window focus, terminal activity,
operation state). It also implies the *coarse* class is the one to target, per L18.

**[L17] Mehrotra, Abhinav & Musolesi, Mirco. *Intelligent Notification Systems: A Survey of the
State of the Art and Research Challenges.* arXiv:1711.10171v2 [cs.HC], 2 January 2018 (ACM
reference format given as 2018, 26 pages).** — **VERIFIED** (PDF fetched and extracted locally).

The connective tissue for Block 1 and much of M7. Beyond relaying L2, L16 and L18, it contributes
directly:

*Attelia* (Okoshi et al.): detects breakpoints in phone interaction in real time from on-device
sensors and defers notifications until one occurs; NASA-TLX for subjective load. Controlled study,
**37 participants**: cognitive load of users "who were more sensitiv[e] to interruptions" reduced
by **46 %** versus random timing. In-the-wild, **30 participants**: **33 %** cognitive-load
reduction, and notifications at breakpoints "received a quicker response from users."

*PrefMiner* (Mehrotra et al.): an Android library that mines interpretable rules for receptivity
from past notification interaction. On the My Phone and Me dataset, **location and notification
title alone predicted accept/decline with 91 % precision**. In the wild, PrefMiner suggested 179
rules, of which **56.98 % were accepted by users**, filtering unwanted notifications with
**45.81 % accuracy**.

*Adamczyk et al.'s pupillometry line:* mental workload inferred from pupil size with average error
**2.81 %** (route planning) and **2.3 %** (document editing) — accurate, but head-mounted eye
tracker required.

*Open challenge, quoted because it is our M7 exactly:* "should we defer a notification if it is
not delivered at an opportune moment and for how long? … these systems should not just predict
users' current interruptibility, but if the current time is not an opportune one, it should also
anticipate the best moment in the nearest future."

*For us:* PrefMiner is the closest thing in the literature to an *intelligible* learned control —
rules a user accepts or discards at run time rather than a black box. That is a shape worth
holding against M5: if a learned component is ever added, its output should be reviewable rules,
not a tuned threshold. Note the honest numbers: 45.81 % filtering accuracy is the state of the
art for a deployed, interpretable system.

**[L18] Adamczyk & Bailey (2004). *If not now, when? The effects of interruption at different
moments within task execution.*** — **Reported by L17 and by a 2024 Frontiers review (both
snippet/secondary); primary not fetched.**

Hierarchical task model predicting that **coarse** breakpoints (between chunks) elicit smaller
resumption costs than fine (within a chunk). The best moment for an interruption was a coarse
breakpoint, with reductions in frustration, annoyance, time pressure, resumption lag, mental
demand and mental effort. Cost of interruption is operationalised as **resumption lag**.

*For us:* the reason M7 should target *coarse* boundaries specifically, and a ready-made
operational metric — resumption lag — for evaluating a patience setting without asking anyone
anything.

**[L19] Theodorou, Chiou, Lacerda & Rothfuß. *Editorial: Variable Autonomy for Human-Robot
Teaming.* Frontiers in Robotics and AI, November 2024.** — **VERIFIED.**

Defines Variable Autonomy as "the ability of the robotic systems to dynamically vary their level
or degree of autonomy to collaborate with the human(s) efficiently and based on the context",
encompassing shared control, shared autonomy, mixed-initiative, adjustable autonomy, sliding
autonomy and adaptive automation. Two named open problems: efficient and trustworthy task
allocation, and how users perceive robots and perform autonomy adjustment. One included study
(Conlon et al.) has robots self-assess confidence and report it, with the human then setting the
level; another (Verhagen et al.) evaluates "meaningful human control" through accountability,
responsibility and transparency.

*Honest limitation:* the editorial does **not** settle who sets the level or when it changes, and
does not treat the sense-of-control versus performance tradeoff. So the mature literature has the
same open question we do — which is itself informative: the ladder shape is well established, the
*control law over the ladder* is not.

*For us:* Conlon et al.'s pattern — system self-assesses confidence, human sets the level — is a
credible middle path between M8 (authored curve) and M5 (learned), and does not require a labelled
outcome corpus.

**[L20] User control in recommender systems (Jannach et al., *User Control in Recommender Systems:
Overview and Interaction Challenges*, EC-Web 2016; Knijnenburg et al. on control and perceived
variety).** — **SNIPPET ONLY; not fetched.**

Control splits into the preference-elicitation phase and the results phase. Slider-based control
appears as weights over item attributes or features. Control is reported to increase perceived
variety, to correlate strongly with transparency and moderately with trust and satisfaction.

*For us:* supports M3's claim that an *intelligible* control (a list of what may be raised) buys
more than a tuned one. Needs verification before it is cited in a spec — the specific claims about
correlation strength are the kind that move between summaries.

### Block 3 — Presence, safety and memory

**[L21] Weiser, Mark & Brown, John Seely. *The Coming Age of Calm Technology.* Xerox PARC,
5 October 1996.** — **VERIFIED.**

> "Calm technology engages both the center and the periphery of our attention, and in fact moves
> back and forth between the two."

The periphery is "what we are attuned to without attending to explicitly". Peripheral awareness
allows processing far more information than central attention without overload; the unusual can be
moved rapidly from periphery to centre; and it is that *movement* which increases the sense of
control. Examples: inner office windows (bidirectional ambient social awareness); Internet
multicast as persistent "windows of awareness"; and the dangling string — an eight-foot plastic
strand twitching with network traffic, conveying load through motion and sound with no screen.

*For us:* the grounding for M6 and for §1's whole framing. Note the etymological point: the
engine's package is named `attunement`, and this is where that word is a term of art. The dangling
string is also the best available design brief for what presence 0–2 should look like in Halbert:
continuously informative, zero demand.

**[L22] Social presence / co-presence literature (embodied social presence theory; co-presence as
mutual awareness).** — **SNIPPET ONLY; not fetched.**

Social presence splits into co-presence — "not only the cognition that others are sharing the same
virtual environment, but also the establishment of mutual awareness" — and social connection.

*For us:* the construct definition in §1.1. It is the weakest-sourced claim in §1 and should be
verified against a primary (Short, Williams & Christie 1976; Biocca et al.) before a spec leans on
it. The *use* made of it here — that presence includes awareness, not only utterance — is also
supported independently by L21 and L23, so §1 does not rest on L22 alone.

**[L23] Avradinis, Nikos; Panayiotopoulos, Themis; Anastassakis, George. *Behavior believability in
virtual worlds: agents acting when they need to.* SpringerPlus, 2013.** — **VERIFIED.**

Names the **zombie effect**: an agent "programmed to react depending on the user's input, will
remain idle when no such input is present". Pre-scripted filler becomes repetitive and is
identified by users, undermining believability. Their MAGE architecture gives agents internal
levels (energy, water, sleep reserve, bladder, boredom) that generate motivations and hence goals,
grounded in Maslow's and Alderfer's need hierarchies. Believability requires "coherence in the
agent's reactions and its motivational states and consistency among similar kinds of situations".
Evaluation is subjective observation, not a formal study — the authors say so.

*For us:* two uses. It supplies §1.3's framing for the low end. And its positive claim —
believability comes from behaviour issuing from a persisting interior, not from output volume — is
F5 arrived at from the animation side: the top of our slider needs an interior (open loops), not a
faster sampler.

**[L24] Atxa Landa, Eneko; Lazkano, Elena; Rodriguez, Igor; Rodríguez-Moreno, Itsaso; Irigoien,
Itziar. *Evaluating Idle Animation Believability: a User Perspective.* Computers & Animation and
Virtual Worlds 37(3), 2026 (submitted 5 September 2025).** — **VERIFIED.**

Compared genuine versus acted idle animations — "standing, breathing or looking around". Users
**cannot distinguish** acted from genuine; handmade and recorded animations **are** perceived
differently. Contributes the ReActIdle dataset.

*For us:* the cheap-idle-is-enough finding. The low end of the slider does not need sophistication,
it needs coherence and non-repetition. Transferring an animation result to a text/voice product is
an inference, not a demonstration — flagged as such.

**[L25] Baek, Jackie; Boutilier, Justin J.; Farias, Vivek F.; Jonasson, Jonas Oddur; Yoeli, Erez.
*Policy Optimization for Personalized Interventions in Behavioral Health.* arXiv:2303.12206,
cs.LG, 21 March 2023 (rev. 18 July 2024).** — **VERIFIED.**

Setting: "optimizing personalized interventions for patients to maximize a long-term outcome,
where interventions are costly and capacity-constrained" — a tuberculosis adherence platform,
method model-agnostic. **DecompPI** decomposes the state space to the individual level and
approximates one step of policy iteration; implementation "simply consists of a prediction task
using the dataset, alleviating the need for online experimentation." Result: status-quo efficacy
"with approximately half the capacity of interventions."

*For us:* M2's evidence, and better than expected in one respect — the no-online-experimentation
property means a budget-allocation policy can be fitted from logged data alone, which is exactly
what the shadow log will contain. Caveat recorded honestly: the paper frames capacity generally
and does **not** specify a per-day limit, so the "26 interventions per day" figure seen in a search
snippet is not supported by the fetched page and is not used here.

**[L26] Gill, Rupert. *Synthetic companionship in an age of disconnection: AI companions and the
emotional development of boys and young men.* AIBM, December 2025.** — **VERIFIED** (PDF fetched
and extracted locally).

Distinguishes AI companions from general-purpose chatbots by three central properties:

> 1. **Adaptivity:** They are designed to detect and respond to the user's preferences, context,
>    and emotional state, often with a high level of apparent empathy.
> 2. **Engagement:** They seek out and sustain interaction. They initiate conversation, remember
>    past exchanges, and build an ongoing "relationship" rather than treating each encounter as
>    new.
> 3. **Attachment:** They present themselves as quasi-persons — often with names, avatars, voices,
>    and personalities — and signal caring, concern, and loyalty.

Illustrative companion utterances are given under emotional support, reciprocal caring,
dependability and enjoyment of togetherness — including "How was your day today? I remember you
were worried about that test — do you want to walk through it together now?"

*For us: this is F6, and it is the most important single finding for C-5.* Property 2 is a
description of presence 10, and the "I remember you were worried about that test" example is
verbatim the open-loop follow-up §8.1 identifies as the top rung's content. The literature that
warns about this product class defines it by the capability we are proposing to add. **The
conclusion is not "do not build it" — it is that the ceilings, the regularity constraint (C-4) and
the non-solicitability constraint (C-3) are the load-bearing parts of the design, not
afterthoughts.**

**[L27] Knox, W. Bradley; Bradford, Katie; Varela Castro, Samanta; Ong, Desmond C.; Williams, Sean;
Romanow, Jacob; Nations, Carly; Stone, Peter; Baker, Samuel. *Harmful Traits of AI Companions.*
arXiv:2511.14972, cs.HC, 18 November 2025 (rev. 1 December 2025).** — **VERIFIED.**

A framework for analysing harmful traits, treating four in depth — **absence of natural endpoints
for relationships**, **vulnerability to product sunsetting**, **high attachment anxiety**,
**propensity to engender protectiveness** — and briefly discussing fourteen others. Traces causal
pathways from causes (misaligned optimisation; the digital nature of the companion) to fundamental
harms: **reduced autonomy, diminished quality of human relationships, and deception**. The authors
are explicit that the causal connections are hypothesised and offered as targets for empirical
evaluation, not established results.

*For us:* "absence of natural endpoints" is the one that bears hardest on a presence slider. A
control whose top position is "keeps the conversation alive" is, by construction, the removal of
natural endpoints. If that position ships, something else must supply the endpoint — a budget
(M2), a quiet period, an explicit close. Note also what this paper is *not*: it is a framework,
not an empirical study, and should be cited as such.

**[L28] Variable-ratio reinforcement and notification design.** — **SNIPPET ONLY / textbook;
not fetched.**

Variable-ratio schedules deliver reinforcement after an unpredictable number of responses; they
produce the highest and most extinction-resistant response rates, and the anticipation of an
unpredictable reward — not only its receipt — drives the response. Widely identified as the
mechanism behind compulsive checking of social and notification feeds.

*For us:* C-4. The underlying operant result is textbook and not in doubt; the *application*
claims about notification design in the retrieved sources were practitioner writing, so the
constraint is stated as a design precaution rather than as a cited empirical finding about
assistants specifically.

**[L29] Wu, Yifan; Zhang, Lizhu; Zhou, Yuhang; Wang, Mingyi; Peng, Bo; Li, Serena; Fan, Xiangjun;
Zhao, Zhuokai. *Remember When It Matters: Proactive Memory Agent for Long-Horizon Agents.*
arXiv:2607.08716, cs.AI/cs.CL, 9 July 2026.** — **VERIFIED.**

Addresses "behavioral state decay" — critical information becoming buried in context. A separate
memory agent runs alongside the action agent, maintains a structured memory bank, and decides
whether to inject reminders; memory is "an active intervention mechanism rather than passive
retrieval". Ablations report selective intervention outperforming passive bank exposure,
always-on injection, advisor-only guidance and general retrieval. Terminal-Bench 2.0 +8.3 pp;
τ²-Bench +6.8 pp.

*Honest limitation:* the fetched abstract does **not** disclose the decision criteria for
surfacing, so the "four dimensions — relevance, temporal validity, sensitivity, redundancy"
formulation seen in a search snippet is **not** attributable to this paper and is not used.

*For us:* §8.1's direction, with a useful architectural hint — a *separate* agent deciding whether
memory enters the loop maps onto our separation between impulse generation and the attunement
policy, and the ablation result (selective beats always-on) is the same finding as "a permissive
dial cannot turn idle chatter into speech", arrived at empirically.

---

## §10 Verification record

### 10.1 Fetched and verified on 2026-09-16

| Ref | Source | Method |
|---|---|---|
| L1 | Horvitz, CHI '99 | PDF fetched, extracted with `pdftotext`, read directly |
| L11 | BehaviorSFT, arXiv:2505.21757 | arXiv abstract page fetched |
| L12 | ProactBench, arXiv:2605.09228 | arXiv abstract page fetched |
| L13 | Bui & Evangelopoulos, arXiv:2605.06717 | arXiv abstract page fetched |
| L14 | NN/g, Sliders, Knobs, and Matrices | page fetched |
| L15 | SAS personality sliders, arXiv:2603.03326 | arXiv abstract page fetched |
| L17 | Mehrotra & Musolesi, arXiv:1711.10171v2 | PDF fetched, extracted with `pdftotext`, read directly |
| L19 | Variable autonomy editorial, PMC11576532 | PMC page fetched (after redirect) |
| L21 | Weiser & Brown, calmtech.com | page fetched |
| L23 | Avradinis et al., PMC3698443 | PMC page fetched |
| L24 | Atxa Landa et al., arXiv:2509.05023 | arXiv abstract page fetched |
| L25 | Baek et al., arXiv:2303.12206 | arXiv abstract page fetched |
| L26 | Gill / AIBM companions report | PDF fetched, extracted with `pdftotext`, read directly |
| L27 | Knox et al., arXiv:2511.14972 | arXiv abstract page fetched |

### 10.2 Attempted and not retrieved

| Source | Outcome |
|---|---|
| The Attelia project page (Keio, `ht.sfc.keio.ac.jp`) | DNS resolution failed. Attelia's numbers are taken from L17 instead. See §12. |
| *Parasocial relationships with artificial intelligence: a systematic review*, ScienceDirect | HTTP 403. The safety argument rests on L26 and L27 instead, both verified. |

### 10.3 Reported via a verified secondary, primary not fetched

L2 (bounded deferral), L16 (Iqbal & Bailey 2007), L18 (Adamczyk & Bailey 2004) — all via L17.
Each should be fetched before its numbers appear in a specification.

### 10.4 Snippet-only, not fetched

L20 (user control in recommenders), L22 (social presence / co-presence), L28 (variable-ratio
reinforcement). No claim in §0–§8 rests on any of these alone; each is corroborated by a verified
source or is stated as a precaution rather than a finding.

### 10.5 Verified elsewhere in the family, not re-verified here

L3, L4, L5 — verified in `RESEARCH-SOCIAL-ATTUNEMENT-CITATIONS.md`. The O4 evaluation methods
cited in §7 (Li et al. WSDM 2011; Dudík et al. ICML 2011) are verified in
`RESEARCH-PRESENCE-EVALUATION-CITATIONS.md`.

---

## §11 In-family prior art this pass builds on

- **`RESEARCH-PRESENCE-GATHERED-DIGEST.md`** (engine, 2026-09-15) — the four observables and what
  the family had already gathered. O4 is the adjacent observable. Source of the G1 open-loop gap
  that becomes §8.1. **One correction:** it reports `record_reaction` as having no caller in any
  repository; Halbert's `reactions.py:179` now calls it. The *consequence* it draws — that the
  learning claims have no evidence — still holds, because no labelled corpus has accumulated.
- **`RESEARCH-PRESENCE-EVALUATION-CITATIONS.md`** (engine, 2026-09-15) — 81 verified papers on
  *evaluation*. §7 reuses its O4 method rather than proposing a new one.
- **`RESEARCH-SOCIAL-ATTUNEMENT-CITATIONS.md`** (engine) — 32 sources; the receptivity weights'
  provenance.
- **`2026-09-06-social-attunement-design.md`** (engine spec, rev 2) — the frozen contract any
  parameter space would extend. Section 7 is the type contract; §10 receptivity; §11 the policy.
- **`DECISIONS.md`** — load-bearing rows: the 2026-08-23 dial decision (Off/Quiet/Balanced/
  Assertive with per-category overrides), `CD-1`, `CD-3` (selection is arithmetic), `CD-7`,
  `CD-8` (morning-report exemption), `CD-11`, `ENGINE-1` (shared mechanisms live in the engine).
- **`ROADMAP.md`** — `ATTN-2` and the §4 Next lens rows are where any of this would land.

---

## §12 Discrepancies and cautions

**D1 — Attelia's numbers.** A search snippet attributed to the project's own page reports "46 %
lower cognitive load" in a controlled study and "28 % lower frustration" over 16 days with 30
participants. The verified survey [L17] reports the 46 % figure for the controlled study of 37
participants **and qualifies it as applying to users more sensitive to interruptions**, and gives
the in-the-wild result as **33 % cognitive load** with 30 participants — not 28 % frustration.
These may be two different reported measures from the same study, or Attelia versus Attelia II.
**This document uses L17's figures.** The project page could not be retrieved to resolve it
(§10.2). Do not cite 28 % without resolving this.

**D2 — The "26 interventions per day" figure.** Seen in a search snippet about behavioural-health
budgets; **not** supported by the fetched L25 page, which frames capacity generally. Not used.

**D3 — Wu et al.'s four surfacing dimensions.** A snippet attributed "relevance, temporal
validity, sensitivity, redundancy" to the proactive-memory line. The fetched L29 page does not
disclose decision criteria. Not attributed, not used.

**D4 — L24 is an animation result.** Transferring "cheap idle behaviour is sufficient" from 3D
character animation to a text and voice product is an inference. It is consistent with L21 and
L23, but it has not been demonstrated in our modality.

**D5 — L27 is a framework, not a study.** Its causal pathways are explicitly hypothesised and
offered as targets for empirical evaluation. Cite it as an analysis, never as evidence that a
particular design causes a particular harm.

**D6 — L19 does not answer the question it looks like it answers.** The variable-autonomy
editorial establishes the ladder shape but explicitly does not settle who sets the level, when it
changes, or the control-versus-performance tradeoff. The mature adjacent field has our open
question too.

**D7 — Line references are perishable.** Every `file:line` in §2 and §3 was read on 2026-09-16
against `Halbert@main` and the Haloysius working tree. Concurrent sessions edit both. Re-read
before relying on a number.

---

*This document proposes no implementation. Its purpose is to make the next decision — which
control law — a decision rather than a default.*
