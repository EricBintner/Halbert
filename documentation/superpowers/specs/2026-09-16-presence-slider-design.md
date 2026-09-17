# Presence Slider — Design Spec (v2)

**Date:** 2026-09-16 · **Status:** v2. v1 was founder-approved in outline 2026-09-16; v2 folds in
the twenty amendments from research passes 2 and 3. Not yet planned; slice 1 is being planned
from this revision.
**Research:** `documentation/research/presence/opus/` — pass 1 (control law: M1–M8, F1–F6,
C-1–C-10), pass 2 (prior art and outcomes: P1–P24, §8.1–§8.9), pass 3 (epistemology and
psychology: E-1–E-5, P-1–P-6, EP-1–EP-7). Cited below by those ids.
**Engine spec it extends:** Haloysius `docs/superpowers/specs/2026-09-06-social-attunement-design.md` (rev 2).
**Naming:** consumers by role; the two closed siblings are the companion consumer and the
persona-authoring consumer.

### Changes from v1

| From | Change | Where |
|---|---|---|
| pass 3 E-5, pass 2 §8.9 | the problem statement now says *why* unbidden speech is warranted, and cites the field's definitional gap | §1 |
| pass 3 P-6, P-3 | seven epistemic principles and the reciprocity rationale join the principles | §4 |
| pass 3 E-1 | `Warrant` on the utterance, derived from class, rendered as *why trust* | §7.1, §7.4, §14 |
| pass 3 P-2 | affect split: system-state vs social; Halbert's curve admits only the former | §7.1, §8, §14, §20 |
| pass 2 §8.3, pass 3 E-3 | three new gates: topic recency, common ground, deferred schedule | §10, §16 |
| pass 2 §8.2, pass 3 E-2, E-4, P-1 | four stance rules: "yes, and"; form follows warrant; open loops close with a plan; offer, never rescue | §10.1 |
| pass 2 §8.6 | ambient indicators expire; `ASK_FIRST` on an ambient-capped class is an indicator, not speech | §11 |
| pass 2 §8.7 | arrival and departure acknowledgments as `SCHEDULED` | §14 |
| pass 2 §8.1, §8.8, pass 3 P-4 | seven named rungs are the primary control; the copy states the objective and why the default is low | §15 |
| pass 2 §8.5 | shadow-review gate is two weeks, reading week 1 vs week 2 | §17, §19 |
| pass 3 P-5, E-2, E-4, P-1 | four new test obligations incl. consistency across levels | §18 |
| pass 2 §8.4 | the only permitted future learning: per-class offset on explicit marks | §3, §20 row 7 |
| — | the build is sliced; slice 1 is the whole contract in shadow plus the preview | §19 |

---

## 1. Problem

The family has a four-position proactivity dial (`DialLevel`: OFF / QUIET / BALANCED /
ASSERTIVE). It cannot express either end of the range the founder wants:

- **0 — soft mute.** `OFF` is off. `assess_presence` returns `SILENT` on `dial:off` before
  consulting anything (`policy.py:379`). There is no position at which only what cannot wait is
  spoken and everything else is still *findable*.
- **10 — a friend who keeps the conversation alive.** `_NEVER_SPEAKS = (RANDOM, TEMPORAL,
  SCENE)` filters the three impulse classes capable of companionable speech before the policy
  runs (`autonomous_engine.py:594-599`). No setting reaches it.

Between the ends, the dial is a severity threshold (`gate.py:44-49`), so it can only make the
system more or less forthcoming *about things that happened*. Presence — legible attention,
appropriate forthcomingness, continuity across time (pass 1 §1.5) — has more axes than that, and
the cheap ones are not on the dial at all.

**Why unbidden speech is warranted at all.** A person cannot ask about what they do not know they
lack. Proactivity is justified precisely for those unknown unknowns, and only under "principled
constraints on when, how, and to what extent" the system intervenes (pass 3 E5). In this spec,
*admission* is the epistemic grounding — what counts as a known-unknown worth raising — and
*channel, patience and budget* are the behavioural grounding.

**A vocabulary problem.** The field labels "fundamentally different behaviors — from simple
reminders to advanced AI systems" as proactive (pass 2 P20). `ImpulseClass` (§7.1) is this
family's answer: a typed set of things that can want to be said, each with a grade of warrant.

## 2. Goals

1. One number, 0–10, that a person sets, whose every position has a sayable meaning.
2. 0 is soft mute; 10 admits spontaneous speech; 3 is the default and behaves as today's
   `BALANCED`.
3. The number is **never read by a gate**. It resolves through an authored curve into a
   `PresenceVector`, and gates read the vector (M8).
4. The curve is **data**. Changing what level 6 does is a table edit, not a code change.
5. Shared across the family: the engine owns the vocabulary, the vector, the resolution and the
   law; each consumer owns its impulse classification, its curve and its ceilings (`ENGINE-1`).
6. Every wall comes down **shadow-first** and stays explainable (C-7).
7. The person can **feel the setting before it acts**: the preview (§15) reconstructs a week of
   the shadow log at any level.

## 3. Non-goals

- No learned policy in v1. The shadow log is replayed to evaluate a curve; it never sets one
  (M5). **The only learning permitted later** is a per-class band offset moved in real time on
  *explicit, consistent* reactions from a person (`ENGAGED` / `DISMISSED`), never on inferred
  silence (pass 2 §8.4, Gmail P7). Recorded as DECISIONS row 7 so nobody builds the inferred form.
- No model-level steering (M4).
- No per-subject sliders. One slider per body; `SubjectConfidence.UNKNOWN` inherits
  most-restrictive as today.
- No new `EngagementOutcome`. Channel is *how*; outcomes stay *whether*.
- No change to receptivity weights, `CD-3` (arithmetic selection), or the redaction choke point.
- No open-loop producer in slices 1–3. `OPEN_LOOP` is typed and stays unreachable until one
  exists (slice 4 / workstream D).
- No migration or back-compat shim for `DialLevel`. It is retired.
- No social affect in Halbert at any level (§7.1, P-2).

## 4. Principles

**Structural**
- Admission, channel, patience, budget are the axes. Thresholds are derived (M1 is derived from
  the others; exposing both would be two controls over one quantity).
- The two axes stay two: the slider is what the person *set*; `InvitationLevel` is what the
  relationship *earned*, still capped by the set axis (C-1).
- Ceilings are never targets (C-2). Budget is a cap the policy may not spend toward.
- Not reachable by persuasion: `persona_may_solicit_invitation=False` is untouched (C-3).
- Regular, not surprising, at the top: bounded deferral plus a budget makes spontaneous
  *generation* regular in *delivery*; the variable-ratio risk is defeated by mechanism (C-4).
- The engine ships the strictest curve; consumers relax it in a reviewed table (C-5).
- Critical and life safety are not on the slider (C-10).
- The band translates; it does not scale (F3, C-9).
- `AMBIENT` creates no obligation to respond; `PUSH` does. "May update, must not escalate" is the
  refusal to convert an offer into a demand (P-3).

**Epistemic** (pass 3 §2.10)
- **EP-1 Warrant before volume.** The ladder descends in warrant, not in frequency.
- **EP-2 Assert only what is known; voice the rest as thought or question.** The knowledge norm
  applies to the machine; form follows warrant.
- **EP-3 Show the source with the claim.** Introspection needs no citation; observation and
  testimony do; inference has none and says so by its form.
- **EP-4 Do not tell the person what is in common ground.** Least collaborative effort.
- **EP-5 Speak for the unknown unknown.** Presence is justified by what the person cannot ask.
- **EP-6 The person's mean, held by the machine.** Judgement is theirs; evidence is ours.
- **EP-7 Attention given, never solicited.**

## 5. Architecture

```
  person sets level ──► PresenceCurve (data) ──► resolve_presence() ──► PresenceVector
                                                        ▲                     │
                                          AttachmentSafety (clamp)            │
                                                                              ▼
   impulse ──► consumer classifies ──► Utterance(impulse_class, warrant) ──► decide()
                                                                       │ 0. admitted?          (vector.admits)
                                                                       │ 0a. already known?     (common ground)
                                                                       │ 0b. raised recently?   (topic recency)
                                                                       │ 1. standing requests
                                                                       │ 2. invitation / attachment / budget
                                                                       │ 3. receptivity + inequality, band-shifted
                                                                       ▼
                                                              EngagementDecision
                                                                       │
                                                consumer delivers ◄────┘ routed by vector.channel[class]
                                                     │                   held to vector.patience_s
                                                     ▼                   why-trust rendered from warrant
                                          PUSH / AMBIENT / PULL
```

The engine never reads the level. `resolve_presence` is the only function that does, and it is
pure. In slice 1 the whole right-hand side runs in the shadow lane; the live gate is unchanged.

## 6. Package layout

**Haloysius** — `src/haloysius/attunement/`

| File | Change |
|---|---|
| `types.py` | add `ImpulseClass`, `Warrant`, `PresenceVector`, `PresenceRung`, `PresenceCurve`; add `impulse_class`, `warrant` to `Utterance`; add `ON_BREAKPOINT` to `ResumeCondition`; **remove** `DialLevel`, `ProactivityDial`, `_DIAL_TO_INVITATION`, `_DIAL_CEILING`, `invitation_for_dial`, `invitation_ceiling_for_dial` |
| `presence.py` | **new** — `DEFAULT_CURVE`, `resolve_presence()`, curve validation, `warrant_for()` |
| `policy.py` | steps 0/0a/0b become admission, common ground, recency; step 2 reads budget from the vector; step 3 applies `band_shift`; `assess_presence` reads `vector.presence_signal` |
| `stance.py` | four stance rules keyed on class and warrant (§10.1) |
| `constants.py` | add `BAND_SHIFT_MAX`, `PATIENCE_DEFAULT_S`, `RECENCY_WINDOW_S`; `HOLD_MAX_S` becomes the ceiling on patience (§11) |
| `conformance.py` | vectors for resolution, admission, form-follows-warrant, offer-not-rescue, plan-closes-loop, consistency-across-levels |
| `cognition/autonomous_engine.py` | `_NEVER_SPEAKS` removed; trigger→`ImpulseClass` map; `_should_speak` gates on `vector.admits` |

**Halbert** — `halbert_core/halbert_core/`

| File | Change |
|---|---|
| `config/being_config.py` | `proactivity: str` → `presence: int` (0–10); `category_overrides` → `presence_overrides: Dict[ImpulseClass, int]` |
| `attunement/impulses.py` | **new** — `classify(event) -> (ImpulseClass, Warrant)`; `classify_trigger(t)` |
| `attunement/common_ground.py` | **new** — `known_to_subject(topic, window)` over the thread store, summoned-module state, recent ledger rows |
| `attunement/breakpoints.py` | **new** (slice 3) — coarse-breakpoint sensor |
| `attunement/curve.py` | **new** — Halbert's curve table (relaxes the engine default; no social affect) |
| `proactive/gate.py` | slice 1: computes the vector verdict and channel **in shadow** beside the dial; slice 2: `_PROACTIVITY_THRESHOLD` removed, vector is live, channel routing live |
| `attunement/shadow.py` | rows gain `presence_level`, `impulse_class`, `warrant`, `channel_resolved`; four new keys |
| `attunement/reactions.py` | unchanged in v1; the only future writer of a per-class offset (§3) |
| `dashboard/routes/settings.py` + frontend | seven named rungs, fine adjust, copy, preview |

## 7. The contract (`types.py`)

### 7.1 `ImpulseClass` and `Warrant`

```python
class ImpulseClass(str, Enum):
    """What kind of thing wants to be said. The seam between engine and consumer:
    the engine types the rungs; a consumer classifies its own sources into them."""
    LIFE_SAFETY    = "life_safety"    # never gated by presence (C-10)
    CRITICAL       = "critical"       # never gated by presence (C-10)
    WARNING        = "warning"
    SCHEDULED      = "scheduled"      # a report, a digest, an arrival or departure acknowledgment
    RECURRENCE     = "recurrence"     # a pattern in the observation ledger
    SUBJECT_LINKED = "subject_linked" # bears on the current turn's subject
    OPEN_LOOP      = "open_loop"      # a commitment or thread falling due
    ASSOCIATION    = "association"    # what the current context reminds it of
    AFFECT_STATE   = "affect_state"   # affect about the machine's own condition ("I'm worried about sda1")
    AFFECT_SOCIAL  = "affect_social"  # affect about the relationship ("I missed you") — companion consumers only
    ABSENCE        = "absence"        # the person has been gone
    SPONTANEOUS    = "spontaneous"    # a thought for no reason; the clock; the scene

class Warrant(str, Enum):
    """How the machine knows what it is about to say (pass 3 §2.1). Governs the
    permitted speech act and the why-trust rendering."""
    INTROSPECTED = "introspected"     # its own state; first-person assertion, no citation needed
    OBSERVED     = "observed"         # the world, via ledger/sensor; assertion with provenance
    TOLD         = "told"             # what the person said; reported assertion with thread ref
    INFERRED     = "inferred"         # association, thought, mood; no assertion licensed
```

`warrant_for(impulse_class)` gives the default: `LIFE_SAFETY`/`CRITICAL`/`WARNING`/`AFFECT_STATE`
→ `INTROSPECTED`; `SCHEDULED` → `INTROSPECTED` (a report of state) or `OBSERVED` by producer
choice; `RECURRENCE`/`SUBJECT_LINKED` → `OBSERVED`; `OPEN_LOOP` → `TOLD`;
`ASSOCIATION`/`AFFECT_SOCIAL`/`ABSENCE`/`SPONTANEOUS` → `INFERRED`. A producer may set a
*stronger* warrant than the default only with a citation (`source_ref`); never a weaker one
silently.

`ImpulseClass` is **not** ordered. Admission is a set, not a threshold; the default curve happens
to be monotone but a consumer's curve need not be.

### 7.2 `PresenceVector`

```python
@dataclass(frozen=True)
class PresenceVector:
    level: int                                    # the level this vector was resolved from (plan D2)
    admits: FrozenSet[ImpulseClass]
    channel: Mapping[ImpulseClass, ChannelClass]  # ceiling per admitted class
    patience_s: Optional[float]                   # None = wait for a pull; never push
    budget_per_day: int                           # ceiling
    invitation_target: InvitationLevel
    invitation_ceiling: InvitationLevel
    presence_signal: ChannelClass                 # how "I am here" is shown; AMBIENT at 0
    closes_after: Optional[int]                   # persona-initiated exchanges before it lets go
    band_shift: float                             # derived; see 7.5
```

`__post_init__`: `LIFE_SAFETY` and `CRITICAL` always admitted and always `PUSH` (C-10); every
admitted class has a channel and no non-admitted class has one; `budget_per_day >= 0`;
`patience_s` `None` or `>= 0`; `band_shift ∈ [−0.30, +0.30]`; `invitation_target <=
invitation_ceiling`. `channel[c]` is a **ceiling**: an utterance whose own `channel_class` is
lower is delivered at its own class; one whose class is higher is capped.

### 7.3 `PresenceRung` and `PresenceCurve`

```python
@dataclass(frozen=True)
class PresenceRung:
    level: int                    # 0..10, the position this rung anchors
    name: str                     # stable key
    says: str                     # first-person copy; the settings surface shows it
    why: str                      # one sentence: what this rung is for (the objective, made visible — pass 2 §8.8)
    admits: FrozenSet[ImpulseClass]
    channel: Mapping[ImpulseClass, ChannelClass]
    patience_s: Optional[float]
    budget_per_day: int
    invitation_target: InvitationLevel
    invitation_ceiling: InvitationLevel
    presence_signal: ChannelClass
    closes_after: Optional[int]

@dataclass(frozen=True)
class PresenceCurve:
    rungs: Tuple[PresenceRung, ...]   # ascending by level; 0 and 10 required
    owner: str                        # "haloysius" | consumer name
```

Validation at construction: levels strictly ascending; 0 and 10 present; every rung passes
`PresenceVector.__post_init__`; `budget_per_day` non-decreasing and `patience_s` non-increasing
across rungs. Admission and channel are *not* required monotone.

### 7.4 `Utterance`

Add `impulse_class: Optional[ImpulseClass] = None`, `warrant: Optional[Warrant] = None`,
`source_ref: Optional[str] = None` (a ledger row id, thread turn id, or sensor name). `__post_init__`
(amended 2026-09-16 after review — plan D9, D10): every enum field, `severity` included, is coerced,
and a foreign enum sharing a value string is rejected. **The class and the flags must agree.** When
`impulse_class` is unstated it is *derived* — `LIFE_SAFETY` if `life_safety`, else `CRITICAL` if
`severity` is critical, else `WARNING`. When stated, a contradiction with the flags is a
`ValueError` in both directions: a flag demanding a class the producer did not give, or an
always-admitted class given without its flag. `warrant` defaults to `warrant_for(impulse_class)`; a
warrant stronger than that default requires `source_ref`, which must be `None` or a non-empty
string. `category` stays for overrides but overrides are keyed by `ImpulseClass` (§9).

### 7.5 `band_shift` (derived, not authored)

```
band_shift(level) =  BAND_SHIFT_MAX * (3 - level) / 3      for level in 0..3
                  = -BAND_SHIFT_MAX * (level - 3) / 7      for level in 3..10
                    →  +0.30 at 0,  0.0 at 3,  −0.30 at 10
```

Piecewise so 3 is exactly neutral and both ends reach the full shift. `BAND_SHIFT_MAX = 0.30`.
Applied as `SPEAK_T[sev] + band_shift` and `ASK_T[sev] + band_shift`. `HOLD_WORTH_T` and the
`CRITICAL` thresholds are not shifted. Hysteresis is not touched. This is the **only** place level
affects the inequality.

### 7.6 `ResumeCondition.ON_BREAKPOINT`

Added. A consumer with a breakpoint sensor releases holds on it; one without treats it as
`ON_TRANSITION`.

## 8. Resolution (`presence.py`)

```python
def resolve_presence(level: int, curve: PresenceCurve, safety: AttachmentSafety) -> PresenceVector:
```

Pure. `level` clamped to 0..10. Finds the bracketing rungs `lo`, `hi`: discrete fields take
`lo`'s value; `patience_s` and `budget_per_day` interpolate linearly (budget rounded down;
`None` on either side yields `None`); `budget_per_day = min(budget,
safety.max_proactive_per_day)`; `band_shift` per §7.5.

**The engine's `DEFAULT_CURVE`** is the strictest in the family (C-5): it admits `AFFECT_SOCIAL`
at no level — a consumer that wants it authors it in — caps the top rung's budget at 5, and sets
`closes_after=3`. Halbert's curve (§14) relaxes budget and `closes_after`, and likewise never
admits `AFFECT_SOCIAL` (P-2). The companion consumer's curve may admit it under the founder's
2026-09-15 ruling and that consumer's own `AttachmentSafety`.

## 9. Overrides

`presence_overrides: Mapping[ImpulseClass, int]` — a per-class *level* resolving that class alone
through the curve; the "linked precise control" (pass 1 L14). May be more permissive than the
global level (A-HB-13). An override substitutes that class's admission and channel and lifts
`budget_per_day` to at least its rung's: an override funds what it admits, and it never shrinks
the budget, since removal is done by admission. Patience and the band stay the base level's
(a class admitted at mute is still spoken at mute's pace). `LIFE_SAFETY` and `CRITICAL` reject
overrides.

## 10. Policy (`policy.py`)

Step order in `decide()`:

0. **Admission.** `if u.impulse_class not in vector.admits: SILENT("presence:not_admitted")`.
   `LIFE_SAFETY` and `CRITICAL` cannot fail this. *Replaces the `dial:off` short-circuit.*
0a. **Common ground** (EP-4; pass 3 E-3). For `SUBJECT_LINKED` and `ASSOCIATION`: if the
   consumer's `known_to_subject(topic, window)` says the topic is already in front of the person
   — on a summoned module, in recent terminal output, said in the thread within the window —
   `SILENT("presence:already_known")`. The engine defines the hook; the consumer supplies it.
0b. **Topic recency** (pass 2 §8.3a). For `ASSOCIATION` and `SPONTANEOUS`: a topic raised within
   `RECENCY_WINDOW_S` → `SILENT("presence:recent_topic")`.
1. Standing requests — unchanged.
2. Invitation, attachment, budget — `budget_per_day` from the vector. `dial:quiet` and
   `dial:balanced:unanchored_info` branches removed; their intent lives in the curve.
3. Receptivity and the inequality — thresholds shifted by `vector.band_shift`.

**Deferred schedule** (pass 2 §8.3b): a `SCHEDULED` impulse the person skips or defers lowers its
own priority for the next cycle (a consumer-side counter read at step 2) rather than repeating
unchanged.

`assess_presence()`: `dial:off` → `if vector.presence_signal is ChannelClass.PULL: SILENT`.

`EngagementDecision.reasons` gains `presence:{level}`, `impulse:{class}`, `warrant:{warrant}`.

### 10.1 Stance rules (`stance.py`)

Rendered into the `[ATTUNEMENT]` block by class and warrant; each has a conformance vector (§18).

| Rule | Applies to | Says |
|---|---|---|
| **Form follows warrant** (EP-2; pass 3 E-2) | `warrant == INFERRED` | The utterance is an expressive ("I was thinking about…") or a question. Never a flat assertion; never a hedged one. |
| **Offer, never rescue** (pass 3 P-1) | every class | The form is an offer that leaves the person's competence intact — "I noticed X; want me to Y?" Implying omission ("you missed X") is forbidden. |
| **Yes, and** (pass 2 §8.2) | `ASSOCIATION`, `SPONTANEOUS`, `AFFECT_*` | Build on the person's current subject, task or recent statement. Never redirect, contradict, or open an unrelated line. |
| **Close with a plan** (pass 3 E-4) | `OPEN_LOOP` | Offer or confirm a concrete next step (a staged command, a scheduled check). Bare recall is forbidden. |

`CD-3` extends to form: the model may phrase; it may not choose the speech act.


**The stamp (amended 2026-09-17 after review).** Every `decide()` decision carries, appended after its verdict and any authority claim so `reasons[0]` stays the verdict, `presence:<level>`, `impulse:<class>`, `warrant:<warrant>`; a presence assessment carries the level alone. The stamp is applied once, before stability, so a dwelt decision keeps the level it was made at (a row that wants the current level reads the context), and it is total: a context too broken to stamp keeps its verdict, since the stamp sits on the life-safety path. `assess_presence` answers `SILENT("presence:signal:pull")` when the vector's `presence_signal` is `PULL`. Match the level as `presence:\d+` — `presence:` also prefixes verdict keys.
## 11. Patience, bounded deferral, ambient expiry

- `vector.patience_s` is the deadline for any `HOLD` issued on an admitted impulse with
  `resume_on=ON_BREAKPOINT`.
- `HOLD_MAX_S` becomes the ceiling a curve may set `patience_s` to; the engine default never
  exceeds 240 s above level 0 (pass 1 L2, L17: the useful deferral window is 120–240 s).
- On the deadline with no breakpoint: deliver at `vector.channel[class]` — bounded, not
  indefinite.
- `patience_s=None` (level 0 for non-critical classes): never push; route to the class's channel
  ceiling, which at 0 is `PULL`.
- **Ambient expiry** (pass 2 §8.6a): an `AMBIENT` indicator not acknowledged within `patience_s`
  expires to `PULL` rather than persisting.
- **Ambient ask** (pass 2 §8.6b): `ASK_FIRST` on a class whose channel ceiling is `AMBIENT` is
  rendered as an indicator state, not a spoken question.

A `HOLD` nothing releases is still a silent drop. **Every consumer that issues `ON_BREAKPOINT`
holds must run a release loop on its breakpoint sensor and on the deadline.**

## 12. Budget

Spent by delivered `PUSH` only; `AMBIENT`, `PULL`, `LIFE_SAFETY`, `CRITICAL` do not spend it.
Exhaustion → `HOLD(ON_USER_TURN)`, reason `presence:budget_exhausted`; day boundary is the
consumer's local midnight.

## 13. Endpoints (`closes_after`)

When set, the consumer counts persona-initiated exchanges in the current thread. On reaching
`closes_after`, the next admitted impulse in that thread resolves to `SPEAK_MINIMAL`, reason
`presence:closing`, and the stance block tells the persona to let the thread end. Resets on a
user-initiated turn. Answers "absence of natural endpoints" (pass 2 P27).

## 14. Halbert wiring

**Classification** (`attunement/impulses.py`): `ProactiveEvent` → class by `type` first
(`morning_report`→`SCHEDULED`; arrival/departure acknowledgments→`SCHEDULED` (pass 2 §8.7);
recurrence remarks→`RECURRENCE`; life-safety types→`LIFE_SAFETY`), then `severity`
(`critical`→`CRITICAL`, `warning`→`WARNING`), then `finding_id` ∩ current subject→
`SUBJECT_LINKED`, else `ASSOCIATION`. `TriggerType` → class: `RANDOM|TEMPORAL|SCENE`→
`SPONTANEOUS`, `USER_ABSENCE`→`ABSENCE`, `EMOTIONAL|DRIVE|WORRY`→`AFFECT_STATE`,
`MEMORY|BELIEF`→`ASSOCIATION`. Warrant by `warrant_for()`, with `source_ref` set to the finding
id, ledger row id, or thread turn id.

**Common ground** (`attunement/common_ground.py`): `known_to_subject(topic, window)` consults the
thread store (last `window` turns), the summoned-module state (what is on the panel), and the
observation ledger's recent rows (what the person has been shown).

**Gate** (`proactive/gate.py`). *Slice 1:* alongside the existing dial evaluation, resolve the
vector, classify, run `decide()` in shadow, compute `channel_resolved`, and write every result to
the shadow row. The live verdict is unchanged. *Slice 2:* `_PROACTIVITY_THRESHOLD` removed; step 1
becomes admission; the new keys fire live; `channel_resolved = min(event.channel_class,
vector.channel[class])` returned with the verdict.

**Delivery.** `PUSH` → today's speech/notification path. `AMBIENT` → the presence pill / bell
count / an indicator state "I have something" (no text). `PULL` → the findings list only. The
*why trust* affordance is rendered from `warrant` + `source_ref`: nothing for `INTROSPECTED`; the
ledger row for `OBSERVED`; the thread turn for `TOLD`; for `INFERRED`, the form itself is the
disclosure.

**Breakpoint sensor** (`attunement/breakpoints.py`, slice 3): `ON_BREAKPOINT` on an operation
finishing, a terminal returning to prompt after ≥ 60 s of activity, a focus change between panels,
idle ≥ 45 s after activity. No hardware (pass 1 L16). Release loop under the existing heartbeat.

**Halbert curve** (`attunement/curve.py`): the seven-rung table (design message of 2026-09-16, pass
1 §4), owner `"halbert"`, top-rung budget 8, `closes_after=5`, `AFFECT_SOCIAL` admitted at no
level (P-2). Each rung carries `says` and `why`.

**Config**: `presence: int = 3`, `presence_overrides: Dict[str, int] = {}`. `proactivity` and
`category_overrides` removed; the validator rejects them naming the new keys. Old on-disk values
are left unread. *Slice 1 is additive: `proactivity` and `category_overrides` remain and the live
gate reads them; slice 2 retires them (plan D1).*

## 15. Settings surface

- **Primary control: the seven named rungs**, each shown by its `says` copy, in first person. Every
  shipped control in pass 2 has two to four positions; the names are what people can predict.
- **Secondary: the 0–10 fine adjust** beneath, interpolating budget and patience between rungs.
- Beside the current rung, its `why` — the objective made visible (pass 2 §8.8). Level 3's copy
  says, in the machine's voice, that it stays out of the way by default so the person's own
  judgement stays in charge (pass 3 P-4).
- **The preview**, from the shadow log: the last 7 days re-resolved at the *hovered* level — "I
  would have said N things, shown M, and held K" with the list, held items included. This is the
  calibration instrument (Lee & See) and the answer to the objection that sliders fail when
  effects take days.
- Per-class overrides behind a disclosure, listed by `says`-style copy, not enum names.
- No emoji; tokens only; no model names.

## 16. Suppression log

Every row gains `presence_level`, `impulse_class`, `warrant`, `channel_resolved`. Keys:
`presence:not_admitted`, `presence:already_known`, `presence:recent_topic`,
`presence:channel_capped`, `presence:budget_exhausted`, `presence:closing`. Every row's `reasons` also end with the §10 stamp.
`recent_suppressions` filters by any of them. In slice 1 the rows carry both the live dial verdict
and the shadow vector verdict, distinguished by `decision_source`.

## 17. Error handling, safety, privacy

- `resolve_presence` cannot raise on a valid curve; an invalid curve fails at construction, at
  start-up, never per-decision.
- Any exception in admission, common ground, recency or routing → the pre-presence behaviour for
  that event (admits `{LIFE_SAFETY, CRITICAL, WARNING}`, channel `PUSH`). Fail toward today's
  balanced, never toward silence and never toward chatter.
- The curve, the level, every resolved vector and every shadow row contain no user content beyond
  ids.
- **Shadow-first, two weeks.** Any rung above the level that reproduces today's `ASSERTIVE`
  admission set is delivered only to the shadow lane until a founder review of **two weeks** of
  shadow rows, reading week 1 against week 2 per class (the novelty cliff is at two weeks, pass 2
  §4.3). The `ROADMAP` row carries the gate.

## 18. Testing

- `resolve_presence`: property tests — clamp, monotone interpolation, step on discrete fields,
  band width preserved at every level and severity, `AttachmentSafety` clamp always wins,
  `AFFECT_SOCIAL` never admitted by the engine default or Halbert's curve.
- Curve validation: rejects non-ascending, missing 0/10, non-monotone budget/patience, a
  non-admitted class with a channel, an admitted class without one.
- Conformance vectors (language-neutral, so a second consumer can prove its resolution):
  - for each level 0..10 and each `ImpulseClass`: admitted / channel / patience;
  - **form follows warrant**: an `INFERRED` utterance rendered as a flat assertion fails;
  - **offer, never rescue**: a rendering that implies omission fails;
  - **close with a plan**: an `OPEN_LOOP` rendering with no next step fails;
  - **consistency across levels** (pass 3 P-5): for a fixed impulse, the rendering at level 2 and
    at level 9 differs only in delivery and channel, never in register or warrant.
- Policy: `ASK_FIRST` reachable at every level where it was reachable before, per severity (the
  5.55e-17 regression test generalised across the band shift).
- Gate: every suppression path still records; `critical` and life safety pass at level 0;
  slice-1 shadow rows carry both verdicts.
- Replay: a fixture of one week of shadow rows re-resolved at each level yields the preview
  counts deterministically, held items included.
- Halbert: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`; worktrees use
  `./wt_pytest.py`.

## 19. Slices

| Slice | Scope | Proves | Gate to next |
|---|---|---|---|
| **1 — feel it before it acts** | §7–§9 in full; §10 admission + reasons; `DEFAULT_CURVE`; Halbert classification, curve, config; gate in shadow (§14); shadow rows (§16); the settings surface with the preview (§15) | the whole contract end to end on real traffic; the person can see the machine's judgement at any level with nothing live changed | none — start now |
| 2 — live below the line | gate reads the vector live for levels whose admission ⊆ today's `ASSERTIVE`; channel routing live; ambient expiry; common-ground, recency, deferred-schedule gates; arrival/departure acks; why-trust rendering | soft mute; admitted-but-ambient; the four whys per rung | two weeks of shadow rows reviewed, week 1 vs week 2 per class |
| 3 — patience | breakpoint sensor; bounded deferral; `HOLD_MAX_S` recalibrated; ambient ask | the largest measured effect in the literature, from timing alone | slice 2 live |
| 4 — open loops (workstream D) | the commitment record with a due condition; `OPEN_LOOP` producer; close-with-a-plan | the rung every embodied product lacked | independent of 1–3; unlocks 6–7 |
| 5 — thought and question | `ASSOCIATION` / `SPONTANEOUS` producers; form follows warrant; yes-and; `closes_after`; shadow-first again | the top of the range as a computer with more to say | slice 4; two more weeks of shadow |

## 20. `DECISIONS.md` rows this spec requires

1. Supersedes 2026-08-23 "Proactive dial Off/Quiet/Balanced/Assertive": presence is a 0–10
   level resolved through an authored curve into a vector; `DialLevel` retired, no shim.
2. `RANDOM` / `TEMPORAL` / `SCENE` are admissible at the top rung under budget, bounded
   deferral and the consumer's `AttachmentSafety`; `_NEVER_SPEAKS` is retired in favour of
   admission.
3. Hard off is not on the slider; it remains `WITHDRAW` and Do Not Disturb.
4. The engine ships the strictest curve; each consumer's curve is a reviewed table in its own
   repo with a named owner. **Halbert's curve admits no social affect at any level; a companion
   consumer's may, under the founder's 2026-09-15 ruling.**
5. Level 3 is the default and reproduces today's `BALANCED`.
6. Every rung above today's `ASSERTIVE` admission set ships shadow-first for two weeks.
7. The only permitted learning is a per-class band offset moved on explicit, consistent reactions
   from a person; never on inferred silence.
8. Unbidden utterances carry a warrant; `INFERRED` warrant may not be rendered as assertion.

## 21. Assumptions and open items

- **A1.** Seven rungs suffice for v1. More can be added to a curve without a contract change.
- **A2.** `band_shift` linear-piecewise in level is adequate for v1; the replay harness is how we
  find out.
- **A3.** The breakpoint sensor's four signals are a v1 guess at Iqbal & Bailey's feature set for
  this product; the shadow log will say which fire.
- **A4.** Budget is spent by `PUSH` only. If ambient deliveries turn out to cost attention in
  practice, a separate ambient budget is a one-field addition.
- **A5.** `known_to_subject`'s three sources (thread, panel, recent rows) are sufficient for
  Halbert; other consumers will need their own.
- **O1.** Per-subject presence — deferred; `UNKNOWN` inheritance covers the household case.
- **O2.** Whether `closes_after` should also apply to `SUBJECT_LINKED` at mid levels — decide from
  shadow data.
- **O3.** The persona-authoring consumer's simulation-time need (pass 1 §6) — not addressed.
- **O4.** Whether the fine adjust (0–10) survives contact with users, or the seven rungs alone do —
  decide from settings-engagement data after slice 1.
