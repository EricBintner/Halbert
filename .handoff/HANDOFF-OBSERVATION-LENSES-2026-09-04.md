# HANDOFF: Observation Lenses — Review and Counter-Proposal

**Date**: 2026-09-04
**Status**: Design review + revised plan — ready for founder decision
**Supersedes**: `.handoff/HANDOFF-NERD-SCOPES-DYNAMIC-PERSONALITY-2026-09-04.md`
(referred to below as "the original")

**Primary finding**: the original proposes building four subsystems that already
exist in this tree. Three of them are fully written, tested, and **not wired**.
The work is not construction. It is connection.

---

## 0. How to read this document

Section 1 is the summary and the decision being asked for.
Section 2 is the verification record — every claim in the original, checked
against the code, with file and line. Read it if you want to know why the plan
changed.
Section 3 is the three defects found while verifying. Two are live bugs
independent of anything in this plan.
Section 4 is the conceptual reframe, which is the part worth arguing about.
Section 5 is the inventory of machinery to reuse.
Section 6 is the revised architecture.
Sections 7–9 are the tracks, task by task.
Section 10 records design decisions and why the alternatives lost.
Sections 11–13 are invariants, the trim list, and open questions.

---

## 1. Executive summary

### 1.1 What the original got right

The premise is sound and worth building. Halbert can control *how* it speaks
(demeanor, communication style, Big Five traits, voice presentation) and *what
it may touch* (tool safety, approval gates). It has no control over **what it
finds worth remarking on**. That is a real gap, and the original names it
correctly.

The original is also right to reject fine-tuned "personality models" for an OS
companion, and right that the steering layer must be human-readable files on
the user's disk rather than opaque weights. Both conclusions survive review
unchanged.

### 1.2 What the original got wrong

It treats this as a greenfield subsystem. It is not. Specifically:

| The original proposes building | Already exists |
|---|---|
| `haloysius/scopes/` — `.md` parser, loader, matcher, tier composer | `halbert_core/skills/` — 1,055 lines, 5 modules, 8 built-in skills, 3 test files |
| A salience decay engine with promotion/demotion | `halbert_core/home/behavior.py` — `PatternInferrer` + `BehaviorStore`, with confidence feedback and `degrade_stale_patterns()` |
| An observation ledger with recurrence detection | `halbert_core/home/timeline.py` — `TimelineStore`, append-only, indexed, with `get_correlations()` |
| Bottom-up topic discovery | `PatternInferrer.infer_from_timeline()` — deterministic recurrence over the same ledger |

The original reverse-engineers `open-claude-code` across a full page for prior
art and never notices Halbert's own skills subsystem, which is strictly more
capable than the one it studied (it has `extends` inheritance, aliases,
declarative safety constraints, and per-skill tool allowlists; Claude Code's
skills have none of these).

### 1.3 What is actually blocking

Three defects, all verified, all small:

1. **The skills subsystem is dark.** `IntakePipeline` is constructed without a
   `skill_matcher`, so no skill ever activates. `ComposedSkills.prompt` is built
   by the composer and consumed by nothing, anywhere.
2. **Observations are computed and discarded.** `FrigateEventMapper` and
   `HAEventMapper` both call `_add_observation()`, which tests for two
   attributes that `PersonaCognition` does not have. Every observation string is
   built, formatted, and dropped. Silently — no exception, no log line.
3. **`TimelineStore` and `PatternInferrer` are namespaced under `home/`** and
   reachable only in the home variant, despite being generic.

### 1.4 The decision being asked for

Approve the reframe in §4 (a lens interprets observations; it is not a joke
bank), then approve Track A as standalone work. Track A is worth doing whether
or not the rest of this plan is ever built, because two shipped integrations
currently throw away their output.

---

## 2. Verification record

Every claim the original makes about existing machinery, checked.

### 2.1 Confirmed accurate

| Claim | Verified at |
|---|---|
| `BeingConfig` holds Big Five, tone descriptors, speech patterns, directives, archetype id, and a `custom_personality_prompt` escape hatch | [config/being_config.py:190](../halbert_core/halbert_core/config/being_config.py) |
| `generate_personality_section()` renders it, with a documented first-match-wins pipeline | [persona/personality_prompt.py:72](../halbert_core/halbert_core/persona/personality_prompt.py) |
| `PromptBuilder` accepts `personality_section` and wraps it in `<personality>` | [prompts/builder.py:99](../halbert_core/halbert_core/prompts/builder.py), :135 |
| Five communication styles (`concise`, `balanced`, `detailed`, `analytical`, `casual`) | [persona/archetypes.py:370](../halbert_core/halbert_core/persona/archetypes.py) |
| Settings has a `being` tab | [dashboard/frontend/src/pages/Settings.tsx:888](../halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx) — labelled "Identity & Voice" |
| `advance_turn()` runs a six-phase lifecycle with the stated decay constants | `Haloysius/src/haloysius/persona/cognition_tick.py:44-46` — `DRIVE_DECAY_PER_TURN = 0.03`, `WORRY_DECAY_PER_TURN = 0.02`, `EMOTION_DECAY_PER_TURN = 0.1` |
| `UserKnowledge` / self-editing persona exists | `Haloysius/src/haloysius/persona/self_editing.py` |
| `StateStore` enforces non-fabricated provenance | [continuity/state_store.py](../halbert_core/halbert_core/continuity/state_store.py) — `reason` and `actor` are keyword-only with no default, so omission is a `TypeError` at the call site |

### 2.2 Wrong, or unverifiable as stated

**`UnifiedPromptPipeline` is not the shipped assembly path.**
Its own module docstring (`Haloysius/src/haloysius/context/prompt_pipeline.py:9-12`):

> the chat handlers in api/app.py still assemble their prompts by
> concatenation. This pipeline is the assembly path continuity state is designed
> for, available for that migration; adopting it is a separate change, because
> it reorders every section of the shipped prompt.

Further, Halbert does not use it at all. Halbert assembles context through
[context/assembler.py](../halbert_core/halbert_core/context/assembler.py) and
builds prompts through [prompts/builder.py](../halbert_core/halbert_core/prompts/builder.py).
**Phase 2 of the original, as written, would wire flavor into a seam that
nothing reads, in a repo that is not the consumer.** It would produce zero
observable behaviour.

**`keyword_injection.py` is not at `src/haloysius/context/`.**
The path given in the original does not exist. `KeywordInjector` may exist
elsewhere; this was not resolved (tooling interruption during verification).
Confirm before planning around it. Note that Halbert's `SkillMatcher` already
does keyword activation with whole-word boundaries, so `KeywordInjector` may
be redundant regardless.

**§4.1 contradicts §9.4 arithmetically.**
§4.1 allows Tier 1 at 60–100 tokens × max 2, plus Tier 2 at 120–200 tokens.
Maximum 400. §9.4 declares a hard cap of 250 across all active scopes.

**The salience formula does not close.**
`S_t = (S_{t-1} · e^{-λΔt}) + α·M_turn + β·A_user`

- `β` is used but never assigned a value.
- `λ` is given as "0.05 per turn; idle time decay = 0.1 per day" — two
  incompatible units inside a single `Δt` term. Turns and days do not share a
  clock, and the formula has only one.
- Six tunable constants with no stated evaluation method. There is no way to
  tell whether a chosen value is right.

---

## 3. Defects found during verification

These are findings, not proposals. Two are live bugs.

### 3.1 DEFECT-1 — The skills subsystem never activates (severity: high)

`halbert_core/skills/` is complete and tested:

- [parser.py](../halbert_core/halbert_core/skills/parser.py) — `SKILL.md` with YAML
  frontmatter; accepts both `<name>/SKILL.md` and bare `<name>.md`
- [loader.py:33](../halbert_core/halbert_core/skills/loader.py) — four-location
  precedence chain: `builtin/` → `~/.config/halbert/skills/` →
  `<cwd>/.halbert/skills/` → `<cwd>/.claude/skills/`
- [matcher.py](../halbert_core/halbert_core/skills/matcher.py) — weighted scoring
  over domains (3), keywords (2), intent (1), platform (1); `MIN_SCORE` requires
  real topical evidence; `MAX_ACTIVE_SKILLS = 3`; explicit invocation bypasses
  triggers entirely
- [composer.py](../halbert_core/halbert_core/skills/composer.py) — merges N active
  skills into one decision set: prompts concatenate under labelled headers,
  safety takes the most restrictive, tools intersect, model tier goes to the
  highest-priority skill, budget takes max appetite
- [registry.py](../halbert_core/halbert_core/skills/registry.py) — aliases and
  `extends` inheritance with cycle detection
- Eight built-in skills: `config-ops`, `discovery-ops`, `frigate-ops`,
  `home-ops`, `network-ops`, `security-ops`, `service-ops`, `storage-ops`

**The break.** [dashboard/routes/agent.py:223](../halbert_core/halbert_core/dashboard/routes/agent.py)
constructs the pipeline with three arguments and no matcher:

```python
intake_pipeline = IntakePipeline(
    complexity_router=complexity_router,
    budget_fn=get_context_budget,
    model_config=model_config,
)
```

`skill_matcher` defaults to `None`, so `IntakePipeline.analyze()` leaves
`active_skills` empty, `_composed_skills()` returns `None`, and every downstream
consumer no-ops.

**Second break, independent of the first.** `ComposedSkills.prompt` is
constructed at [composer.py:99](../halbert_core/halbert_core/skills/composer.py)
(`f"[Active Skill: {skill.name}]\n..."`) and has **zero consumers in the entire
tree**. A repo-wide search for `composed.prompt` returns only its definition.
Even with a matcher wired, no skill's expertise would reach the model.

**Third break.** `ToolSafetyFramework.set_skill_safety()`
([tools/safety.py:302](../halbert_core/halbert_core/tools/safety.py)) is called
only from tests. Declared skill safety constraints never bind in production.

Net effect: eight expert skills, matched by nothing, injected nowhere, enforcing
nothing.

### 3.2 DEFECT-2 — Observations are silently discarded (severity: high)

Both event mappers end at the same dead function.

```python
# integrations/frigate/frigate_event_mapper.py:279
# integrations/home_assistant/ha_event_mapper.py:161
def _add_observation(self, cognition, text: str) -> None:
    try:
        if hasattr(cognition, "internal_state"):
            cognition.internal_state.add_observation(text)
        elif hasattr(cognition, "observations"):
            cognition.observations.append(text)
    except Exception as e:
        logger.debug(f"Could not add observation: {e}")
```

`PersonaCognition` (`Haloysius/src/haloysius/persona/cognition.py`, 263 lines) is
a dataclass whose fields are: `persona_id`, `realities`, `scene_context`,
`recent_memories`, `conversation_id`, `beliefs`, `values`, `emotional_state`,
`drives`, `worries`, `thoughts`.

Verified: the strings `internal_state` and `observations` appear **zero times**
in that file. There is no `__getattr__` and no `@property`. `add_observation` is
defined nowhere in Haloysius.

Both `hasattr` branches are therefore false, the `if/elif` falls through, no
exception is raised, and the `except` never fires. **The loss is silent by
construction** — there is not even a debug log.

What is lost, per event:

- `"Detected person (Amazon) at front_door in driveway"`
- `"Front door was unlocked"`
- `"Sarah arrived home"`
- `"Package detected at porch"`
- `"Motion detected: garage sensor"`
- `"person left front_door"`

What survives: `worries.add_worry()` and `_add_emotion()`, which write to real
attributes and reach the prompt via `to_prompt_block()`.

**The consequence is precisely inverted from what higher cognition needs.** The
being feels the front door open and holds no record that it did. It carries the
affect and loses the fact.

Note also that `populate_cognition()` *is* genuinely called before
`advance_turn()` — [agents/state_machine.py:2823](../halbert_core/halbert_core/agents/state_machine.py)
and [home/cognitive_loop.py:263,269,275](../halbert_core/halbert_core/home/cognitive_loop.py),
with `CompositeEventMapper` fan-out at
[integrations/cognition_wiring.py:508](../halbert_core/halbert_core/integrations/cognition_wiring.py).
The pipeline is live end to end. Only the sink is missing.

### 3.3 DEFECT-3 — Generic machinery trapped behind a variant (severity: medium)

`TimelineStore` and `PatternInferrer` live in `halbert_core/home/` and are
exported from `home/__init__.py`. Nothing about either is home-specific:

`TimelineStore`'s own docstring lists its purpose as HA state changes, Frigate
events, **scanner discoveries**, **findings and proposals**, occupancy, user
commands, and cognitive tick decisions — most of which are sysadmin concerns.

Per the capability-registry decision (`capabilities.py` replaced `_is_home_variant`
gating), these should be capability-gated, not variant-gated. Today a sysadmin
install has no event ledger at all.

---

## 4. The reframe: what makes this entertaining

This is the part of the review most worth disagreeing with, so the argument is
given in full.

### 4.1 The original's model, and why it fails

The original models flavor as a **reference library**. A scope file carries:

- `## Analogy & Metaphor Domain` — an enumerated bank of comparisons
- `## Reference Universe & Canon` — lists of hardware, software, cultural anchors
- `## Recommendations` — books

This is the weakest available version of "entertaining", for three reasons.

**It is redundant with the weights.** A 250-token budget spent telling the model
what an Amiga 1000 is buys nothing. Every model that can hold a conversation
already knows. The scope file is paying rent for knowledge that is free.

**Enumeration produces forced output.** Handing a model a list of analogies and
telling it to be flavorful reliably produces *deployed* analogies — inserted
because they were available, not because they fit. This is the exact failure
mode that makes AI companions insufferable, and the original's design contains
nothing that tells the model when an analogy has earned its place. §3.2's
"ABSOLUTE RULE" is a sentence inside a user-editable markdown file; it is a
request, not a mechanism.

**It has no referent.** A metaphor about cooperative multitasking is a statement
about the world in general. It cannot be wrong, cannot be surprising, and
carries no evidence that anything was paying attention.

### 4.2 The alternative

> **"Third time that grey van's parked out front this week."**

That sentence is more entertaining than any metaphor in the original, and it
contains no wit devices at all. It is entertaining because it is **specific,
earned, and could only have come from something that was watching**. Wit is
compression of shared context, not a reference library.

So the abstraction inverts:

> **A lens is not a joke bank. It is an interpretation of the observation
> stream — what this way of seeing notices, and how it says so.**

Retro-computing stops being *"compare goroutines to the Amiga"* and becomes
*"the disk that keeps dropping out is the one you swore at in March"* —
noticing, plus a voice. The canon and analogy sections drop to near-zero value.
The valuable content of a lens file becomes two things:

1. **What does this lens consider worth remarking on?** (selection)
2. **How does it say so?** (voice)

### 4.3 Three problems this solves for free

**The token budget stops being absurd.** 250 tokens cannot hold a reference
universe, and the original's own arithmetic (§2.2) proves it tried and failed.
250 tokens comfortably holds "here are three observations from the last day this
lens finds notable, rendered in this voice."

**Anti-derailment becomes structural rather than aspirational.** Observations
already carry `event_type`, `source`, `severity`, and a timestamp. The gate keys
off the observation's own metadata and the turn's intent — both deterministic,
neither delegated to the model's discretion. The original's §9.1 invariant
becomes enforceable instead of hortatory.

**Bottom-up discovery gets a substrate that can support it.** The original
proposes clustering chat topics, which yields noise ("docker", "the thing we
tried", "yeah"). Recurrence in *observations* is deterministic and meaningful:
this van, this door, this disk, three times, with timestamps. `PatternInferrer`
already does exactly this for house routines. Same mechanism, better data,
already written.

### 4.4 The corollary about surfaces

If flavor is interpretation of observations, then the right first surface is not
the chat turn. It is the **morning report** — which already exists, already runs
on a schedule, already aggregates a 24-hour window, and is the one place where
flavor is unambiguously safe. Nobody is mid-`fdisk` at 8am reading their brief.

A morning report written through a lens, over a real day of observations, *is*
the product. Ship it there and prove the idea before it goes anywhere near a
live turn.

---

## 5. Inventory: machinery to reuse

### 5.1 Observation capture and storage

| Component | Location | State |
|---|---|---|
| `FrigateEventMapper` | `integrations/frigate/frigate_event_mapper.py` | Live. Accumulates MQTT events, maps to worries/emotions. Observation sink dead (DEFECT-2). |
| `HAEventMapper` | `integrations/home_assistant/ha_event_mapper.py` | Same. |
| `SystemEventMapper` | `integrations/system_event_mapper.py` | Live. Adds events, checks critical conditions. Does not call `_add_observation`. |
| `CompositeEventMapper` | `integrations/cognition_wiring.py:508` | Live. Fans `populate_cognition()` across primary + secondary mappers. |
| `FrigateStateTracker` | `frigate_event_mapper.py:32` | Live. Answers "what is on camera right now". |
| **`TimelineStore`** | **`home/timeline.py`** | **Complete, tested, variant-trapped.** Append-only `timeline_events` (timestamp, event_type, source, entity_id, severity, title, description, JSON data), four indexes. API: `record()`, `record_simple()`, `query()`, `get_recent(hours)`, `get_correlations(entity_id, window)`, `cleanup(max_age_days)`, `stats()`. |
| `StateStore` | `continuity/state_store.py` | Live. Temporal triples with `valid_from`/`valid_to`, mandatory `reason`/`actor`, `thread_id`. API: `record_state()`, `current_state()`, `state_history()`, `why()`. |

### 5.2 Interpretation and lifecycle

| Component | Location | State |
|---|---|---|
| **`PatternInferrer`** | **`home/behavior.py:335`** | **Complete, tested, variant-trapped.** `infer_from_timeline(hours=168)` extracts time-of-day, day-of-week, seasonal, guest, and device-usage patterns from the timeline. `predict_next()`. |
| **`BehaviorStore`** | **`home/behavior.py:107`** | Confidence feedback loop: `confirm_pattern()`, `dismiss_pattern()`, `record_correction()`, `record_occurrence()`. **`degrade_stale_patterns()`** decays patterns unseen for four weeks. |
| `Finding` + `FindingStore` | `findings/store.py` | Live. Four Whys (`why_now`, `why_care`, `why_so`, `why_trust`), severity, status lifecycle (open/snoozed/resolved/dismissed), detector attribution. |
| `SomaticBlock` + `SomaticStore` | `somatic/` | SENSORY → DELIBERATION → PROPOSAL → ACTION → REFLECTION, SQLite, SSE timeline events (`agents/events.py:452`). |
| `DetectorRunner` | `proactive/detector_runner.py` | Live. Runs detectors, dedupes against existing findings, publishes `ProactiveEvent`s. Four detectors exist. |
| Cognitive tick | `Haloysius .../cognition_tick.py` | Live. Decay → trigger → reinforce → promote → conflict → persist. |

### 5.3 Delivery surfaces

| Component | Location | Notes |
|---|---|---|
| `ProactiveGate` | `proactive/gate.py:38` | Proactivity dial → minimum severity (`off`/`quiet`/`balanced`/`assertive`), quiet hours, per-category overrides, guardrails, snooze and dismissal state. Returns `(should_notify, reason_if_suppressed)`. |
| **`MorningReportGenerator`** | **`proactive/morning_report.py:24`** | **Already accepts a `summarizer: Callable[[str], str]`** that "rewrites the template body. Its output becomes the report body when it returns non-empty text." Also accepts `config_changes_provider: Callable[[int], List[Any]]`. Fails closed when no gate can be evaluated. |
| Context assembler | `context/assembler.py` | `assemble(..., observations=...)` with a budgeted `observations` category at every tier (`intake/budget.py`: 75 tokens at MEDIUM, 450 at the next tier, 1100, 2200). Formatter at `_format_observations()`. |
| Skills subsystem | `skills/` | See §3.1. Complete, dark. |

### 5.4 The point of the inventory

Of the machinery the original proposes to build, the following already exists in
working, tested form: the markdown parser, the multi-location loader, the
keyword/domain matcher, the multi-scope composer, the token budget reallocator,
the retrieval-scope binding, the observation ledger, the recurrence detector,
the confidence-decay engine, the interrupt policy, and a scheduled ambient
surface with a flavor injection point already in its constructor signature.

What does not exist: the wiring between them, an observation sink, and a lens
file format. That is the whole of the remaining work.

---

## 6. Revised architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ OBSERVATION → INTERPRETATION → EXPRESSION                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  CAPTURE                                                                 │
│   Frigate MQTT ─┐                                                        │
│   HA states    ─┼─► EventMappers ─► populate_cognition() ─┐              │
│   System scan  ─┘        │                                │              │
│   Detectors ─────────────┼─► Finding (Four Whys) ─────────┤              │
│                          │                                │              │
│                          ▼                                ▼              │
│                  ┌───────────────┐              worries / emotions       │
│                  │ TimelineStore │              (existing, live)         │
│                  │ append-only   │                                       │
│                  └───────┬───────┘                                       │
│                          │                                               │
│  INTERPRET               ▼                                               │
│                  ┌───────────────────┐   ┌──────────────────┐            │
│                  │ PatternInferrer   │   │ StateStore       │            │
│                  │ recurrence,       │   │ what is true now │            │
│                  │ confidence, decay │   │ + why + since    │            │
│                  └─────────┬─────────┘   └────────┬─────────┘            │
│                            │                      │                      │
│                            └──────────┬───────────┘                      │
│                                       ▼                                  │
│                          ┌────────────────────────┐                      │
│                          │ ACTIVE LENS            │                      │
│                          │ (a skill, kind:flavor) │                      │
│                          │ selection + voice      │                      │
│                          └────────────┬───────────┘                      │
│                                       │                                  │
│  ═══════════ SUPPRESSION GATE (deterministic, non-negotiable) ═════════  │
│         intent ∈ {destructive, diagnostic, incident} → no flavor         │
│         approval pending → no flavor                                     │
│         severity ≥ warning on the turn's subject → no flavor             │
│                                       │                                  │
│  EXPRESS                              ▼                                  │
│         ┌──────────────────┬──────────────────┬──────────────────┐       │
│         │ Morning report   │ Conversation     │ Timeline UI      │       │
│         │ (lens as         │ (remarks, hard-  │ (what it saw,    │       │
│         │  summarizer)     │  gated)          │  inspectable)    │       │
│         └──────────────────┴──────────────────┴──────────────────┘       │
└──────────────────────────────────────────────────────────────────────────┘
```

The only genuinely new boxes are **ACTIVE LENS** (a new `kind` on an existing
file format) and **SUPPRESSION GATE** (roughly 40 lines). Everything else is an
existing component being connected.

---

## 7. Track A — Close the observation loop

**Rationale**: worth doing on its own merits. Two shipped integrations currently
discard their output. Nothing else in this plan works without it.

### A1. Promote `TimelineStore` out of `home/`

Move `home/timeline.py` to `observations/timeline.py` (or `continuity/timeline.py`),
keeping a re-export in `home/__init__.py` so existing home callers are
unaffected. Gate availability on `capabilities.py`, not on
`BeingConfig.variant`, per the capability-registry decision.

No schema change. No data migration — per project standing rule, existing home
databases keep their path and are simply read from the new import site.

**Verification**: `test_timeline_store.py` and `test_behavior_store.py` pass
unchanged; a sysadmin-variant install can construct a `TimelineStore`.

### A2. Give `_add_observation` a real sink

Replace the dead `hasattr` chain in both mappers with a write to
`TimelineStore.record_simple()`:

```python
def _add_observation(self, cognition, text: str, *, entity_id: str = "",
                     event_type: str = "frigate_event", severity: str = "info") -> None:
    if self._timeline is None:
        return
    try:
        self._timeline.record_simple(
            event_type=event_type,
            source="frigate",
            entity_id=entity_id,
            severity=severity,
            title=text,
        )
    except Exception as e:
        logger.debug(f"Could not record observation: {e}")
```

Two requirements on this change:

- **Do not silently drop again.** If no timeline is configured, log once at
  startup, not per event. The current defect is dangerous specifically because
  it is invisible.
- **Keep the existing worry/emotion writes.** They work and they are the
  affective half. This adds the factual half; it does not replace anything.

**Verification**: a synthetic Frigate detection produces a row in
`timeline_events`; `get_recent(1)` returns it.

### A3. Decide the store per observation shape

**This is the subtle part and it must not be got wrong.**

`StateStore.record_state()` deduplicates. In `_record_body`:

```python
if cur["object"] == obj:
    return None            # unchanged; leave the history alone
```

That is correct and desirable for *state*, and fatal for *events*. Recording
`("grey_van", "seen", "true")` three times produces **one row**. The recurrence —
the entire point — is destroyed by the store's core invariant.

Therefore:

| Observation shape | Store | Why |
|---|---|---|
| **State** — door locked/unlocked, presence home/away, disk healthy/degraded, service up/down | `StateStore` | Dedup is a feature; `state_history()` gives transitions free; `why()` answers "since when and who" |
| **Event** — a detection at a timestamp, a delivery, a sighting, a command | `TimelineStore` | Append-only; recurrence is countable; `get_correlations()` answers "what else happened around then" |

Route each mapper call site accordingly. HA lock/alarm/presence transitions are
state. Frigate detections are events. Some HA events are both — a door
*opening* is an event, a door *being open* is state; record both when the
distinction matters to a question someone would actually ask.

**Do not** attempt to make `StateStore` hold events by embedding a timestamp in
the object value to defeat the dedup. That defeats a deliberate invariant and
leaves the ledger unable to answer `current_state()` meaningfully.

### A4. Feed observations into the assembler

`ContextAssembler.assemble()` already takes `observations: List[str]` with a
budgeted category at every tier. Today it is fed only ReAct tool output
(`ctx.observations`, `agents/states.py:153`), and the formatter is headed
`## Tool Observations`.

Add world observations as a second contributor:

- Split the header: `## Tool Observations` and `## Recent Observations`, or
  introduce a distinct `world_observations` source with its own budget line.
  Do not merge them under one heading — "I ran `systemctl status`" and "the
  front door opened" are different kinds of claim and conflating them invites
  the model to attribute one to the other.
- Source from `TimelineStore.get_recent(hours=N, limit=M)`, filtered by the
  active lens (Track B) when one is active, unfiltered otherwise.

### A5. Recurrence query

Add a thin recurrence helper over `TimelineStore` — count of matching events by
`entity_id` (or by `title` for un-keyed observations) within a window. Plain
SQL, no new store.

Before writing one, check `PatternInferrer.infer_from_timeline()`: it may
already cover the need, in which case A5 is a call site rather than new code.

**Verification**: three synthetic detections of the same entity in a week
return a count of 3 and a first/last timestamp.

---

## 8. Track B — Wire skills, add the lens kind

**Rationale**: this is the delivery mechanism. Unchanged from the first review
except that "flavor scope" is now "lens".

### B1. Wire the matcher

At [dashboard/routes/agent.py:223](../halbert_core/halbert_core/dashboard/routes/agent.py),
construct a `SkillMatcher` over `SkillRegistry.from_disk()` and pass it to
`IntakePipeline`. Matching already fails soft — a broken skill file costs the
turn its expertise, not its answer.

### B2. Inject `composed.prompt`

Thread `ComposedSkills.prompt` into the system prompt. The composer already
labels each contribution (`[Active Skill: storage-ops]`) precisely so the model
can attribute an instruction to its source when two skills are co-active.

Place it after the personality section and before retrieval results. This is a
ten-line change and it is the single highest-leverage line in this document:
eight written expert skills begin working the moment it lands.

### B3. Bind skill safety

Call `ToolSafetyFramework.set_skill_safety(composed.safety)` for the turn.
Currently only tests do. `storage-ops` declares `protected_paths: [/boot, /dev,
/etc/fstab, /etc/zfs]` and `blocked_commands: [mkfs*, dd*of=/dev/*, zpool
destroy*, diskutil eraseDisk*]` — declarations that presently bind nothing.

Note this is a **safety-tightening** change: `_check_skill_safety` only ever
raises the risk level (`tools/safety.py:381-385`). It cannot relax a base
classification.

### B4. The suppression gate

New, deterministic, ~40 lines. A lens contributes nothing to the prompt when
any of the following hold:

- turn intent is destructive, diagnostic, or incident-shaped
- an approval is pending
- the turn's subject carries an open finding at `warning` or above
- global flavor intensity is `off`
- the proactivity dial is `off` (reuse `_PROACTIVITY_THRESHOLD` semantics)

This must live in the composer or immediately downstream of it, **not** in
prompt text. The original's §9.1 states this as an invariant and implements it
as a polite request inside a user-editable file. That is not an invariant.

**Verification**: a turn matching a destructive intent produces a prompt with no
lens block, asserted directly rather than by inspecting model output.

### B5. `kind: flavor` on the existing format

Add three frontmatter fields to the existing `SKILL.md` schema:

```yaml
kind: flavor            # flavor | ops (default: ops)
intensity: 0.6          # 0.0–1.0, multiplied by the global dial
suppress_on: [destructive, diagnostic, incident]   # additive to B4's defaults
```

Matcher changes:
- Lens skills occupy their own slot and do not compete with ops skills for
  `MAX_ACTIVE_SKILLS = 3`.
- At most one lens active per turn (start strict; relax only with evidence).

### B6. Global flavor intensity

One `BeingConfig` field (`flavor_intensity: str = "subtle"`), one prompt line,
one radio group (Off / Subtle / Flavorful) in the existing `being` tab
alongside communication style. Highest value-per-line in the original document,
and it belongs next to the other demeanor controls rather than in a separate
card.

### B7. One built-in lens

Ship exactly one so the shape is concrete and reviewable. Body structure:

```markdown
## What this lens notices
- Repetition, especially in things that are supposed to be one-offs.
- Hardware that is behaving the way hardware behaves before it fails.
- The gap between what a config says and what the machine is doing.

## How it says so
- Understated. State the observation; let it carry its own weight.
- One sentence. Never two.
- Never during recovery, diagnosis, or a destructive operation.

## What it does not do
- No metaphors unless the reader asked "why".
- No name-dropping hardware for flavor.
```

Note what is absent: no canon list, no analogy bank, no recommendations
section. Compare to the original's §3.2 example, most of which is cut.

---

## 9. Track C — The entertaining surface

### C1. Morning report through the lens

`MorningReportGenerator.__init__` **already accepts** `summarizer:
Optional[Callable[[str], str]]`, documented as: "rewrites the template body. Its
output becomes the report body when it returns non-empty text; otherwise the
template body stands."

That is the flavor injection point, already built, with the correct failure
mode (falls back to the deterministic template). Supply a lens-driven
summarizer.

Also supply `config_changes_provider` — currently unset in some paths — from
`StateStore` changes in the window, so the report includes what actually changed
and why.

Add the day's notable observations from `TimelineStore.get_recent(24)`,
selected by the lens.

**Why this surface first**: it is scheduled, aggregate, gated (fails closed when
proactivity is off), and temporally distant from any dangerous operation. The
risk of a badly-judged remark is a mildly annoying paragraph, not a derailed
recovery.

### C2. Recurrence remarks in conversation

Only after C1 has been in daily use. Hard-gated by B4. Sourced from A5 /
`PatternInferrer`. Rate-limited: at most one unsolicited remark per session,
never two turns running.

### C3. UI

- **One** Skills list — ops and lenses together, filterable by kind. Not a
  second card competing with the first.
- Raw markdown inspection per the original's §7.3, which is a good requirement
  and should be kept verbatim: every directive must be readable on disk.
- An observation timeline view. The somatic-block timeline
  (`agents/events.py:452`) may already provide most of this surface.

---

## 10. Design decisions and rejected alternatives

**D1 — Build in Halbert, not Haloysius.**
The original places the engine in Haloysius for universality. But the four-tier
search path, the storage roots, the RAG scope binding, the safety gate, the
timeline, the behavior inferrer, and the entire UI are Halbert. Haloysius would
hold roughly 200 lines of frontmatter parsing and arithmetic, duplicating a
Halbert parser that already exists and does more (`extends`, aliases, safety,
tool allowlists). Universality is a cost paid when a second consumer exists.
There is not one. Keep it in Halbert; lift it if H2/H3 ever need it.

**D2 — Extend the skills format; do not create a second one.**
The original proposes `~/.config/halbert/nerd_scopes/` alongside the existing
`~/.config/halbert/skills/`. Two loaders, two frontmatter dialects, two
precedence chains, in the same config directory. Users will not know which file
to write and neither will we in six months.

**D3 — Do not call these "scopes".**
Beyond the founder's stated dislike of the semantics, `scope` is load-bearing
and already means *"which slice of the corpus to retrieve from"*:
`canonical_scope_id()`, `knowledge_scope`, `resolve_retrieval_scope()`,
SourcePrep scope ids. Overloading it to mean "personality flavor pack" inside
the very modules that perform retrieval scoping will cause real bugs, not merely
aesthetic complaints. If the surface stays **Skills**, with `kind: flavor`, the
naming problem disappears entirely and no new vocabulary is introduced. "Lens"
is used in this document as prose, not as a proposed identifier.

**D4 — Two stores, chosen by observation shape.**
See A3. The dedup in `StateStore._record_body` is correct for state and fatal
for events. Do not work around it; route around it.

**D5 — Runtime state does not live in the user's markdown.**
The original writes `salience_score`, `last_engaged_at`, `tier`, and `purged_at`
back into frontmatter every turn. This churns user files, races the user's own
editor, produces git noise for anyone versioning their skills, and converts a
declarative file into a mutable database. Halbert's existing parser is
deliberately read-only. Lifecycle state belongs in `BehaviorStore` or a sibling
table, keyed by skill name.

**D6 — Replace the salience formula with counting.**
`PatternInferrer` + `BehaviorStore` already implement recurrence with a
confidence feedback loop and `degrade_stale_patterns()`. Reuse them. If a
bespoke lens lifecycle is still wanted, use `hit_count`, `last_engaged_at`,
`pinned`, and two thresholds — quantities that can be inspected and reasoned
about, rather than six constants of which two are undefined.

**D7 — Drop purge-to-memory with an LOD digest.**
The original's reactivation argument for it is void: the file stays on disk with
its keywords, so the matcher can already see a dormant lens for free. The
residual value — "what did we establish while this was hot" — is a timeline
query once Track A lands. And a *deterministic* digest is concatenation, not a
summary; a real summary requires a model call, which the original's own Finding
B forbids.

**D8 — Bottom-up discovery from observations, not chat.**
See §4.3. The original's mechanism cannot work on its chosen data. The same
mechanism on timeline recurrence already exists and does work.

---

## 11. Invariants

Carried forward from the original where sound, with mechanisms attached.

1. **Safety primacy.** A lens contributes nothing during destructive,
   diagnostic, or incident-shaped turns. *Mechanism*: deterministic suppression
   in the composer (B4), asserted by test on the assembled prompt — not on model
   behaviour.
2. **Deterministic before model.** Recurrence, decay, promotion, and selection
   are arithmetic over stored rows. The model receives a selection; it does not
   make one.
3. **No fabricated provenance.** Observations written to `StateStore` carry a
   self-naming deterministic reason (`"frigate: detection event"`). `UNRECORDED`
   is never replaced by a generated rationale.
4. **Silent loss is a defect.** Any observation path that can drop data must log
   it. DEFECT-2 is severe precisely because it is invisible.
5. **Full transparency.** Every behavioural directive exists as an editable file
   on disk, inspectable in the UI. Kept verbatim from the original §9.6.
6. **Safety composes upward only.** Skill safety may raise a risk
   classification, never lower it (already true at `tools/safety.py:381-385`).
7. **Token honesty.** One budget, one number, enforced. Not two numbers that
   contradict each other.

---

## 12. Trim list

Cut from the original, with reasons.

| Cut | Reason |
|---|---|
| `haloysius/scopes/` module | Duplicates `halbert_core/skills/` (D1) |
| `~/.config/halbert/nerd_scopes/` | Second parallel file system (D2) |
| `## Reference Universe & Canon` | Redundant with model weights (§4.1) |
| `## Analogy & Metaphor Domain` as an enumerated bank | Produces forced analogies; reduce to one line of voice guidance (§4.1) |
| `## Recommendations` | Same; also note the standing directive that the product never names or recommends AI models — keep any recommendation content well clear of that boundary |
| The salience formula | Undefined `β`, mixed units, six unevaluable constants (§2.2, D6) |
| Purge-to-memory with LOD digest | Reactivation argument void; digest needs a model (D7) |
| Chat-topic-clustering discovery | Cannot work on that data (D8) |
| `invoke_nerd_scope` tool | Costs schema tokens every turn; duplicates retrieval. Defer until a case appears that retrieval cannot serve. |
| Phase 2 (`UnifiedPromptPipeline` wiring) | Not the shipped path; not used by Halbert at all (§2.2) |
| The `/scope` slash command as new work | Already exists as `SkillMatcher.match(explicit=[...])`; only needs exposing |

---

## 13. Open questions for the founder

1. **Lens count.** One active lens at a time, or several composing? Start with
   one; several risks a voice that is nobody's. Needs a call before B5.
2. **Default state.** Does a fresh install ship with a lens active, or is flavor
   opt-in? Recommendation: `subtle` intensity with no lens active — the dial
   works, but nothing has an opinion until the user gives it one.
3. **Observation retention.** `TimelineStore.cleanup()` defaults to 90 days. Is
   that right for a sysadmin install that will accumulate scanner findings, and
   for a home install with camera events? Possibly different per event type.
4. **Whether C2 happens at all.** Conversational remarks are where this can go
   wrong. It is entirely reasonable to ship A + B + C1 and stop, judging from
   the morning report whether unsolicited remarks are wanted.
5. **Licence check.** The original reverse-engineers
   `/Volumes/Thunderbolt/AI/OSS/open-claude-code`. Halbert is GPL-3.0-or-later.
   Adopting architectural ideas is fine; confirm that repo's licence before any
   code is copied across. Nothing in this plan requires copying any.

---

## 14. Verification checklist

- [ ] `TimelineStore` constructible outside the home variant; existing tests pass
- [ ] A synthetic Frigate detection produces a `timeline_events` row
- [ ] A synthetic HA lock transition produces a `StateStore` triple, not a timeline row
- [ ] No observation path drops data without logging
- [ ] Recurrence query returns 3 for three same-entity events in a week
- [ ] World observations appear in the assembled prompt under their own heading, within budget
- [ ] With a matcher wired, a storage question activates `storage-ops`
- [ ] `composed.prompt` appears in the assembled system prompt
- [ ] `storage-ops` protected paths block a `mkfs` attempt in a live turn
- [ ] A destructive-intent turn contains no lens block (asserted on the prompt)
- [ ] Flavor intensity `off` produces a prompt byte-identical to no-lens
- [ ] Morning report renders through the lens; falls back to the template when the summarizer returns empty
- [ ] Morning report is not published when proactivity is `off` (fails closed)
- [ ] Every active directive is readable as a file on disk from the UI

---

## 15. Summary

The original identifies a real gap and reaches two correct conclusions: flavor
must not come from model weights, and it must live in user-editable files.

It then proposes building an engine that exists, a lifecycle that exists, an
observation ledger that exists, and a recurrence detector that exists — while
three of those sit unwired and one silently discards its input.

It also models entertainment as a reference library, which is the version that
fails. The version that works is interpretation of a real observation stream:
specific, earned, and impossible to fake. That reframe costs fewer tokens,
makes the safety invariant enforceable instead of hortatory, and gives
bottom-up discovery data it can actually work on.

The revised plan is three tracks. Track A closes an observation loop that is
currently broken and is worth doing regardless. Track B connects a skills
subsystem that is written, tested, and dark. Track C ships flavor first on the
morning report, where it is safe, before it is ever allowed near a live turn.

The test of whether a plan is well-aimed is whether its first step is worth
taking on its own. Track A is.
