# Presence Slider — Slice 1 ("feel it before it acts") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the whole presence contract in the engine, wire Halbert to run it in the shadow lane beside the live dial, and ship a settings surface whose only live effect is a preview of what the machine would have said last week at any level. Nothing the user hears changes.

**Architecture:** A `PresenceCurve` (data) resolves a 0–10 level into a `PresenceVector` (admission set, per-class channel ceilings, patience, budget, invitation target/ceiling, band shift). `decide()` gates on admission first and translates the ask/speak band by `band_shift`. Halbert classifies each `ProactiveEvent` into an `ImpulseClass` with a `Warrant`, resolves its own curve, and hands the engine a context; the existing `ShadowDecider` → `SuppressionRecorder` path runs it and writes both verdicts to one row. A preview endpoint re-runs admission + channel over stored rows at any level.

**Tech Stack:** Python 3.10+ stdlib (engine `attunement` package is stdlib-only by policy), pytest; Halbert FastAPI + SQLite (`AttunementStore`), React 18 + TypeScript + Vitest.

**Spec:** `documentation/superpowers/specs/2026-09-16-presence-slider-design.md` (v2), §19 row 1.

---

## Decisions this plan makes (read before Task 1)

**D1 — Additive in Halbert.** `BeingConfig.proactivity` and `category_overrides` **stay** in slice 1 and the live `ProactiveGate` keeps reading them, because slice 1 promises no live change. `presence: int = 3` and `presence_overrides` are **added**. The shadow path reads `presence`. Retiring the old fields is slice 2. Every Halbert test that constructs `BeingConfig(proactivity=...)` for the *live* gate is untouched.

**D2 — `PresenceVector.level`.** The vector carries the level it was resolved from (one int beyond spec §7.2). It is the input the vector was computed from, it lets `decide()` emit a stable `presence:{level}` reason key, and it lets the shadow row record `presence_level` without a side channel. Spec §7.2 should gain the field; noted here so the spec is amended, not silently diverged from.

**D3 — Budget keeps both keys.** `resolve_presence` clamps `budget_per_day` to `AttachmentSafety.max_proactive_per_day`, so the two ceilings coincide. The policy emits `("presence:budget_exhausted", "attachment:daily_cap")` together: every existing vector and test that expects `attachment:daily_cap` still passes, and the new key is present.

**D4 — Per-class overrides resolve that class alone, and fund it.** `resolve_presence(level, curve, safety, overrides={cls: lvl})` takes admission and channel for `cls` from the rung at `lvl`, lifts `budget_per_day` to at least that rung's when the override admits (never shrinks it — removal is done by admission), and takes everything else from the base level. Without the lift an override at level 0 admits a class the zero budget can never fund, so the control is a no-op that looks like one (Task 7 finding). `LIFE_SAFETY`/`CRITICAL` reject overrides (spec §9).

**D5 — The Halbert gate is not edited.** The recorder already runs `ShadowDecider.decide` → `build_context` → engine `decide()`. Slice 1 changes what `build_context` builds; `proactive/gate.py` is byte-identical.

**D6 — One shadow verdict flips, on purpose.** At `presence=0` a `critical` is admitted and the shadow says `speak` while a live `proactivity="off"` gate still suppresses it. That disagreement is the first thing slice 1 exists to show; a test asserts it.

**D7 — Preview is admission + channel, not a full re-decide.** A stored row has no live receptivity or standing requests; re-running the inequality would be fiction. Re-running admission and channel at another level is exact.

**D9 — The class and the flags must agree (review of `ad5fc0b`).** Spec v2 §7.4 said `life_safety=True` *forces* `LIFE_SAFETY` and `severity=CRITICAL` *forces* `CRITICAL`. Silent forcing was the one place in `types.py` where a wrong value was rounded rather than rejected, and it let a mislabelled severity lift the warrant rule. Amended: `impulse_class` defaults to `None` and is *derived* from the flags when unstated; when stated, a contradiction with the flags is a `ValueError`, in both directions. Every existing call site passes no class, so results are unchanged. Spec §7.4 edited to match. *Consequence for later readers:* the derived class is materialised into the field, so `dataclasses.replace(u, life_safety=True)` on an utterance built without a class re-feeds the stored `WARNING` beside the flipped flag and raises; pass `impulse_class=None` when rebuilding with changed flags. No task in this plan rebuilds an `Utterance` from stored fields.

**D10 — `warrant` defaults to `None`, not `INTROSPECTED`.** Spec v2 §7.4 literally wrote `warrant: Warrant = Warrant.INTROSPECTED`, which contradicts §7.1 ("`warrant_for(impulse_class)` gives the default") and would make every `ASSOCIATION` utterance raise. The plan's `Optional[Warrant] = None` is the correct reading; spec §7.4 edited to say so.

**D11 — The proactivity card stays beside the presence card in slice 1.** D1 keeps the live gate reading `proactivity`; deleting its card would leave the person unable to change *live* behaviour from Settings for the whole shadow period, with a control on screen that changes only the preview. The `PresenceCard` is inserted above the Proactivity card, says on its face that it changes the preview and not yet what is heard, and the Proactivity card retires with the dial in slice 2. (Ruled 2026-09-17 while staging Task 22.)

**D8 — Rung copy is data.** `GET /api/being/presence/rungs` serves the curve's `name`/`says`/`why`; the frontend never hardcodes copy.

**Worktrees (execution reality).** Both repos are worked in isolated worktrees, never the main checkouts (the founder's live daemon imports the main engine tree, and the main Halbert checkout holds another session's edits):
- Engine: `~/.config/superpowers/worktrees/Haloysius/presence-vector` on `feat/presence-vector`. Its venv is the main checkout's, whose editable install points at the MAIN tree — so every engine command is prefixed `PYTHONPATH=$PWD/src`.
- Halbert: `~/.config/superpowers/worktrees/Halbert/presence-slice-1` on `feat/presence-slice-1`. Tests run as `PYTHONPATH=<engine worktree>/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py …` — the `PYTHONPATH` makes Halbert see the engine *branch*; `wt_pytest.py` makes it see the Halbert *worktree*; the venv interpreter is required (bare `./wt_pytest.py` dies on its own flag).

Commit per task; subject + body only, no trailers.

**Test commands.**
- Engine: `cd ~/.config/superpowers/worktrees/Haloysius/presence-vector && PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m pytest src/haloysius/attunement/tests -q`.
- Halbert: `cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1 && PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/<file> -q`. **Always** `arch -arm64`; **always** the venv interpreter; **always** the engine `PYTHONPATH`.
- Frontend: `cd /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/settings/tabs/PresenceCard.test.tsx` and `npx tsc --noEmit`.

---

## File map

**Engine (`/Volumes/4TB-BAD/Haloysius/src/haloysius/`)**

| File | Responsibility | Change |
|---|---|---|
| `attunement/types.py` | the frozen contract | add `ImpulseClass`, `Warrant`, `warrant_for`, `warrant_rank`, `PresenceVector`, `PresenceRung`, `PresenceCurve`, `ResumeCondition.ON_BREAKPOINT`; extend `Utterance`; `AttunementContext.dial` → `.presence`; **remove** `DialLevel`, `ProactivityDial`, `_DIAL_TO_INVITATION`, `_DIAL_CEILING`, `invitation_for_dial`, `invitation_ceiling_for_dial` |
| `attunement/presence.py` | **new** — `DEFAULT_CURVE`, `band_shift`, `resolve_presence`, `default_presence` | create |
| `attunement/constants.py` | every number | add `BAND_SHIFT_MAX`, `PATIENCE_DEFAULT_S`, `RECENCY_WINDOW_S` |
| `attunement/policy.py` | `decide` / `assess_presence` | admission step 0; remove dial branches; budget from vector; `_thresholds()` with band shift; reasons gain `presence:`/`impulse:`/`warrant:` |
| `attunement/ledger.py` | standing requests + invitation | `invitation()`/`apply()` take `presence` not `dial` |
| `attunement/turn.py` | reactive path | `dial=` → `presence=` |
| `attunement/conformance.py` + `testing/vectors/policy.json` | agreement vectors | `presence`/`presence_overrides` in schema; 4 vectors rewritten; new `presence.json` + `check_presence` |
| `cognition/autonomous_engine.py` | impulse generator | `_NEVER_SPEAKS` → `_IMPULSE_CLASS` map; `_should_speak` passes `impulse_class` |
| `attunement/__init__.py` | exports | add the new names |
| tests: `attunement/tests/test_types.py`, `test_presence.py` (new), `test_policy.py`, `test_ledger.py`, `test_authority.py`, `test_conformance.py`, `cognition/tests/test_autonomous_attunement.py` | | |

**Halbert (`/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/`)**

| File | Responsibility | Change |
|---|---|---|
| `config/being_config.py` | being.yml | add `presence`, `presence_overrides` + validation |
| `attunement/impulses.py` | **new** — `classify(event)` → (class, warrant, source_ref) | create |
| `attunement/curve.py` | **new** — `HALBERT_CURVE` | create |
| `attunement/context.py` | engine context builder | `dial_for` → `presence_for`; `utterance_for` sets class/warrant; `build_context` passes `presence` |
| `attunement/shadow.py` | the row | `_verdict` adds `presence_level`, `impulse_class`, `warrant`, `channel_resolved`, `channel_capped` |
| `attunement/preview.py` | **new** — re-resolve stored rows at a level | create |
| `dashboard/routes/settings.py` | being config API | `BeingConfigUpdate.presence`, `.presence_overrides` |
| `dashboard/routes/being.py` | proactive channel API | `GET /being/presence/rungs`, `GET /being/presence/preview` |
| `dashboard/frontend/src/components/settings/tabs/PresenceCard.tsx` | **new** — seven rungs, fine adjust, preview | create |
| `dashboard/frontend/src/components/settings/tabs/BeingTab.tsx` | settings tab | mount `PresenceCard`; remove the Proactivity card |
| tests: `tests/test_being_config.py`, `test_attunement_impulses.py` (new), `test_attunement_curve.py` (new), `test_attunement_shadow_decide.py`, `test_attunement_preview.py` (new), `test_being_presence_routes.py` (new), `test_settings_being_presence.py` (new), frontend `PresenceCard.test.tsx` (new) | | |

---

# Part A — Engine

### Task 1: `ImpulseClass`, `Warrant`, `warrant_for`

**Files:**
- Modify: `/Volumes/4TB-BAD/Haloysius/src/haloysius/attunement/types.py` (after `class Reaction`, line ~263)
- Test: `/Volumes/4TB-BAD/Haloysius/src/haloysius/attunement/tests/test_presence.py` (new)

- [ ] **Step 1: Create the branch**

```bash
cd /Volumes/4TB-BAD/Haloysius && git checkout -b feat/presence-vector
```

- [ ] **Step 2: Write the failing test**

Create `src/haloysius/attunement/tests/test_presence.py`:

```python
"""The presence contract: impulse classes, warrants, the vector, the curve,
resolution (spec 2026-09-16 presence-slider v2, §7–§9)."""

from __future__ import annotations

import pytest

from haloysius.attunement.types import (
    ImpulseClass,
    Warrant,
    warrant_for,
    warrant_rank,
)


def test_impulse_classes_are_the_twelve_rungs():
    assert {c.value for c in ImpulseClass} == {
        "life_safety", "critical", "warning", "scheduled", "recurrence",
        "subject_linked", "open_loop", "association", "affect_state",
        "affect_social", "absence", "spontaneous",
    }


def test_warrant_defaults_follow_the_source_of_knowledge():
    # introspection: the machine's own state
    for c in (ImpulseClass.LIFE_SAFETY, ImpulseClass.CRITICAL, ImpulseClass.WARNING,
              ImpulseClass.AFFECT_STATE, ImpulseClass.SCHEDULED):
        assert warrant_for(c) is Warrant.INTROSPECTED
    # observation: the world via the ledger
    for c in (ImpulseClass.RECURRENCE, ImpulseClass.SUBJECT_LINKED):
        assert warrant_for(c) is Warrant.OBSERVED
    # testimony: what the person said
    assert warrant_for(ImpulseClass.OPEN_LOOP) is Warrant.TOLD
    # inference: no assertion licensed
    for c in (ImpulseClass.ASSOCIATION, ImpulseClass.AFFECT_SOCIAL,
              ImpulseClass.ABSENCE, ImpulseClass.SPONTANEOUS):
        assert warrant_for(c) is Warrant.INFERRED


def test_warrant_rank_orders_inferred_below_introspected():
    assert (warrant_rank(Warrant.INFERRED) < warrant_rank(Warrant.TOLD)
            < warrant_rank(Warrant.OBSERVED) < warrant_rank(Warrant.INTROSPECTED))
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd /Volumes/4TB-BAD/Haloysius && .venv/bin/python -m pytest src/haloysius/attunement/tests/test_presence.py -q`
Expected: FAIL with `ImportError: cannot import name 'ImpulseClass'`

- [ ] **Step 4: Implement**

In `types.py`, directly after the `Reaction` enum (after line 262, before the `# Helpers` banner), add:

```python
class ImpulseClass(str, Enum):
    """What kind of thing wants to be said (presence spec v2 §7.1).

    The seam between engine and consumer: the engine types the rungs, a
    consumer classifies its own sources into them.  **Not ordered.**
    Admission is a set, not a threshold.
    """

    LIFE_SAFETY = "life_safety"        # never gated by presence (C-10)
    CRITICAL = "critical"              # never gated by presence (C-10)
    WARNING = "warning"
    SCHEDULED = "scheduled"            # a report, a digest, an arrival/departure acknowledgment
    RECURRENCE = "recurrence"          # a pattern in the observation ledger
    SUBJECT_LINKED = "subject_linked"  # bears on the current turn's subject
    OPEN_LOOP = "open_loop"            # a commitment or thread falling due
    ASSOCIATION = "association"        # what the current context reminds it of
    AFFECT_STATE = "affect_state"      # affect about the machine's own condition
    AFFECT_SOCIAL = "affect_social"    # affect about the relationship — companion consumers only
    ABSENCE = "absence"                # the person has been gone
    SPONTANEOUS = "spontaneous"        # a thought for no reason; the clock; the scene


class Warrant(str, Enum):
    """How the machine knows what it is about to say (presence spec v2 §7.1).

    Governs the permitted speech act and the why-trust rendering:
    INTROSPECTED needs no citation; OBSERVED and TOLD need one; INFERRED
    licenses no assertion at all.
    """

    INTROSPECTED = "introspected"
    OBSERVED = "observed"
    TOLD = "told"
    INFERRED = "inferred"


#: Classes a vector must always admit, always at PUSH (C-10).
ALWAYS_ADMITTED = frozenset({ImpulseClass.LIFE_SAFETY, ImpulseClass.CRITICAL})

_WARRANT_RANK = {Warrant.INFERRED: 0, Warrant.TOLD: 1, Warrant.OBSERVED: 2, Warrant.INTROSPECTED: 3}

_DEFAULT_WARRANT = {
    ImpulseClass.LIFE_SAFETY: Warrant.INTROSPECTED,
    ImpulseClass.CRITICAL: Warrant.INTROSPECTED,
    ImpulseClass.WARNING: Warrant.INTROSPECTED,
    ImpulseClass.AFFECT_STATE: Warrant.INTROSPECTED,
    ImpulseClass.SCHEDULED: Warrant.INTROSPECTED,
    ImpulseClass.RECURRENCE: Warrant.OBSERVED,
    ImpulseClass.SUBJECT_LINKED: Warrant.OBSERVED,
    ImpulseClass.OPEN_LOOP: Warrant.TOLD,
    ImpulseClass.ASSOCIATION: Warrant.INFERRED,
    ImpulseClass.AFFECT_SOCIAL: Warrant.INFERRED,
    ImpulseClass.ABSENCE: Warrant.INFERRED,
    ImpulseClass.SPONTANEOUS: Warrant.INFERRED,
}


def warrant_for(impulse_class: ImpulseClass) -> Warrant:
    """The default warrant for a class — what its source of knowledge licenses."""
    return _DEFAULT_WARRANT[ImpulseClass(impulse_class)]


def warrant_rank(warrant: Warrant) -> int:
    """INFERRED < TOLD < OBSERVED < INTROSPECTED, as an int for comparisons."""
    return _WARRANT_RANK[Warrant(warrant)]
```

Add to `__all__` (the `# enums` line): `"ImpulseClass", "Warrant",` and to `# helpers`: `"warrant_for", "warrant_rank", "ALWAYS_ADMITTED",`.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_presence.py -q`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add src/haloysius/attunement/types.py src/haloysius/attunement/tests/test_presence.py
git commit -m "attunement: ImpulseClass and Warrant, the typed rungs and their grade of knowledge

The seam between engine and consumer for the presence slider: the engine
types twelve kinds of thing that can want to be said, and for each the
default warrant — introspected, observed, told, inferred — which is what
licenses an assertion at all. Not ordered: admission is a set."
```

---

### Task 2: `PresenceVector`

**Files:**
- Modify: `types.py` (after `PolicyStability`, before `AttunementConfig`)
- Test: `tests/test_presence.py`

- [ ] **Step 1: Write the failing test**

Extend the single `from haloysius.attunement.types import (...)` block at the top of `test_presence.py` to `ALWAYS_ADMITTED, ChannelClass, ImpulseClass, InvitationLevel, PresenceVector, Severity, Warrant, channel_rank, warrant_for, warrant_rank` (one block; never a second mid-file import). Add `from dataclasses import FrozenInstanceError, replace` beneath `from __future__ import annotations`. Directly after the Task 1 tests add:

```python
def test_always_admitted_is_the_two_ungated_classes():
    assert ALWAYS_ADMITTED == frozenset({ImpulseClass.LIFE_SAFETY, ImpulseClass.CRITICAL})
    assert all(warrant_for(c) is Warrant.INTROSPECTED for c in ALWAYS_ADMITTED)


def test_every_class_has_a_warrant_and_helpers_accept_value_strings():
    assert all(warrant_for(c) in Warrant for c in ImpulseClass)
    assert warrant_for("open_loop") is Warrant.TOLD and warrant_rank("told") == 1
    with pytest.raises(ValueError):
        warrant_for("nope")


C = ImpulseClass
PUSH, AMBIENT, PULL = ChannelClass.PUSH, ChannelClass.AMBIENT, ChannelClass.PULL


def _vector(**kw):
    base = dict(
        level=3,
        admits=frozenset({C.LIFE_SAFETY, C.CRITICAL, C.WARNING}),
        channel={C.LIFE_SAFETY: PUSH, C.CRITICAL: PUSH, C.WARNING: PUSH},
        patience_s=240.0, budget_per_day=3,
        invitation_target=InvitationLevel.NORMAL, invitation_ceiling=InvitationLevel.CHATTY,
        presence_signal=AMBIENT, closes_after=None, band_shift=0.0,
    )
    base.update(kw)
    return PresenceVector(**base)


def test_vector_accepts_a_well_formed_value():
    v = _vector()
    assert v.level == 3 and C.WARNING in v.admits and v.channel[C.WARNING] is PUSH


def test_life_safety_and_critical_are_always_admitted_at_push():
    with pytest.raises(ValueError):
        _vector(admits=frozenset({C.LIFE_SAFETY, C.WARNING}),
                channel={C.LIFE_SAFETY: PUSH, C.WARNING: PUSH})
    with pytest.raises(ValueError):
        _vector(channel={C.LIFE_SAFETY: PUSH, C.CRITICAL: AMBIENT, C.WARNING: PUSH})


def test_channel_keys_are_exactly_the_admitted_classes():
    with pytest.raises(ValueError):   # admitted without a channel
        _vector(channel={C.LIFE_SAFETY: PUSH, C.CRITICAL: PUSH})
    with pytest.raises(ValueError):   # channel for a non-admitted class
        _vector(channel={C.LIFE_SAFETY: PUSH, C.CRITICAL: PUSH, C.WARNING: PUSH, C.ABSENCE: PULL})


@pytest.mark.parametrize("bad,match", [
    (dict(level=11), "level must be 0..10"),
    (dict(level=-1), "level must be 0..10"),
    (dict(budget_per_day=-1), "budget_per_day"),
    (dict(patience_s=-1.0), "patience_s"),
    (dict(band_shift=0.31), "band_shift"),
    (dict(band_shift=-0.31), "band_shift"),
    (dict(closes_after=0), "closes_after"),
    (dict(invitation_target=InvitationLevel.CHATTY, invitation_ceiling=InvitationLevel.NORMAL), "invitation_target"),
])
def test_vector_rejects_out_of_range_fields(bad, match):
    with pytest.raises(ValueError, match=match):
        _vector(**bad)


def test_vector_normalises_string_members():
    v = _vector(admits=frozenset({"life_safety", "critical", "warning"}),
                channel={"life_safety": "push", "critical": "push", "warning": "push"})
    assert C.WARNING in v.admits and v.channel[C.WARNING] is PUSH


def test_vector_rejects_a_foreign_enum_that_shares_a_value_string():
    # ImpulseClass.WARNING and Severity.WARNING are both "warning"; coercion must
    # not let one pass as the other (quality review of d470cf6, Important 1).
    with pytest.raises(TypeError):
        _vector(admits=frozenset({C.LIFE_SAFETY, C.CRITICAL, Severity.WARNING}))


def test_channel_rank_orders_pull_below_push():
    assert channel_rank(PULL) < channel_rank(AMBIENT) < channel_rank(PUSH)
    assert channel_rank("ambient") == 1
    with pytest.raises(ValueError):
        channel_rank("loud")


def test_vector_accepts_its_bounds_inclusively():
    _vector(level=0)
    _vector(level=10)
    _vector(band_shift=0.30)
    _vector(band_shift=-0.30)
    _vector(band_shift=0.1 + 0.2)
    _vector(closes_after=1)
    _vector(patience_s=0.0)
    _vector(patience_s=None)
    _vector(invitation_target=InvitationLevel.NORMAL, invitation_ceiling=InvitationLevel.NORMAL)


def test_vector_rejects_a_non_integral_level_rather_than_rounding_it():
    for bad in (3.7, "3", True, -0.5):
        with pytest.raises(TypeError):
            _vector(level=bad)
    with pytest.raises(TypeError):
        _vector(budget_per_day=2.5)
    with pytest.raises(TypeError):
        _vector(closes_after=True)


def test_vector_normalises_every_enum_field_and_rejects_foreign_ones():
    v = _vector(presence_signal="ambient", invitation_target=2, invitation_ceiling=3)
    assert v.presence_signal is AMBIENT and v.invitation_target is InvitationLevel.NORMAL
    with pytest.raises(TypeError):
        _vector(presence_signal=Severity.INFO)
    with pytest.raises(TypeError):
        _vector(channel={C.LIFE_SAFETY: PUSH, C.CRITICAL: PUSH, C.WARNING: Severity.INFO})
    with pytest.raises(TypeError):
        _vector(invitation_target=Severity.INFO)


def test_channel_is_immutable_and_replace_revalidates():
    v = _vector()
    with pytest.raises(TypeError):
        v.channel[C.ABSENCE] = PUSH          # mappingproxy has no __setitem__
    with pytest.raises(FrozenInstanceError):
        v.level = 4
    widened = replace(v, admits=frozenset({C.LIFE_SAFETY, C.CRITICAL, C.WARNING, C.ABSENCE}),
                      channel={**v.channel, C.ABSENCE: AMBIENT})
    assert C.ABSENCE in widened.admits and widened.channel[C.ABSENCE] is AMBIENT
    with pytest.raises(ValueError):
        replace(v, channel={**v.channel, C.CRITICAL: AMBIENT})
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_presence.py -q`
Expected: FAIL with `ImportError: cannot import name 'PresenceVector'`

- [ ] **Step 3: Implement** — first, in the `# Helpers` section of `types.py` directly after `warrant_rank`, add the coercion helper the rest of the presence contract uses (the `typing` import gains `Type, TypeVar`):

```python
_E = TypeVar("_E", bound=Enum)


def coerce_enum(enum_cls: Type[_E], value: Any, what: str) -> _E:
    """``enum_cls(value)`` for a member or its value string — but a *foreign*
    enum is rejected, not coerced through a shared value string.
    ``ImpulseClass.CRITICAL`` and ``Severity.CRITICAL`` are both
    ``"critical"``; without this, a ``Severity`` passed where an
    ``ImpulseClass`` belongs would silently succeed (review of d470cf6)."""
    if isinstance(value, Enum) and not isinstance(value, enum_cls):
        raise TypeError(f"{what} must be {enum_cls.__name__} or its value string, not {type(value).__name__}")
    return enum_cls(value)
```

`coerce_enum` is public: add `"coerce_enum",` to `__all__`'s `# helpers` line. It is the one door for every enum-or-value-string entry point — the vector's fields (below), the utterance's (Task 4), the resolver's override keys (Task 5) — so a foreign enum is rejected uniformly wherever a consumer hands one in, and a second module never imports a private name to get the same rule (review of 5b15084).

Then, after `class PolicyStability` (ends ~line 667) add:

```python
_CHANNEL_RANK = {ChannelClass.PULL: 0, ChannelClass.AMBIENT: 1, ChannelClass.PUSH: 2}


def channel_rank(channel: ChannelClass) -> int:
    """PULL < AMBIENT < PUSH — how much attention a channel spends."""
    return _CHANNEL_RANK[ChannelClass(channel)]


@dataclass(frozen=True)
class PresenceVector:
    """What a presence level resolves to; the only thing a gate reads (spec v2 §7.2).

    ``level`` is the input the vector was resolved from — carried so a
    decision can say ``presence:3`` and a log row can record it.
    ``channel[c]`` is a *ceiling*: an utterance whose own channel is lower
    is delivered at its own; one whose channel is higher is capped.
    """

    level: int
    admits: FrozenSet[ImpulseClass]
    channel: Mapping[ImpulseClass, ChannelClass]
    patience_s: Optional[float]          # None = never push; wait for a pull
    budget_per_day: int                  # a ceiling, never a target (C-2)
    invitation_target: InvitationLevel   # what the earned axis decays toward
    invitation_ceiling: InvitationLevel  # what speech may raise it to
    presence_signal: ChannelClass        # how "I am here" is shown
    closes_after: Optional[int]          # persona-initiated exchanges before it lets go
    band_shift: float                    # derived by resolve_presence; translates ASK_T and SPEAK_T together

    def __post_init__(self) -> None:
        # Normalise first, on every field, so the checks below see members
        # and never raw input.  Integral fields are strict: a level of 3.7
        # or "3" is a bug upstream, not a value to round — this number is
        # what a decision stamps into ``presence:<level>`` (review of 07c9e1b).
        for name in ("level", "budget_per_day"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(f"{name} must be an int, got {v!r}")
        if self.closes_after is not None and (isinstance(self.closes_after, bool) or not isinstance(self.closes_after, int)):
            raise TypeError(f"closes_after must be None or an int, got {self.closes_after!r}")
        for name in ("patience_s", "band_shift"):
            v = getattr(self, name)
            if v is None and name == "patience_s":
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise TypeError(f"{name} must be a number, got {v!r}")
        if not 0 <= self.level <= 10:
            raise ValueError(f"level must be 0..10, got {self.level!r}")
        admits = frozenset(coerce_enum(ImpulseClass, c, "admits member") for c in self.admits)
        channel = {
            coerce_enum(ImpulseClass, k, "channel key"): coerce_enum(ChannelClass, v, "channel value")
            for k, v in dict(self.channel).items()
        }
        target = coerce_enum(InvitationLevel, self.invitation_target, "invitation_target")
        ceiling = coerce_enum(InvitationLevel, self.invitation_ceiling, "invitation_ceiling")
        signal = coerce_enum(ChannelClass, self.presence_signal, "presence_signal")
        object.__setattr__(self, "admits", admits)
        object.__setattr__(self, "channel", MappingProxyType(channel))
        object.__setattr__(self, "invitation_target", target)
        object.__setattr__(self, "invitation_ceiling", ceiling)
        object.__setattr__(self, "presence_signal", signal)
        for c in ALWAYS_ADMITTED:
            if c not in admits:
                raise ValueError(f"{c.value} is always admitted (C-10)")
            if c not in channel:
                raise ValueError(f"{c.value} is admitted but has no channel; C-10 requires PUSH")
            if channel[c] is not ChannelClass.PUSH:
                raise ValueError(f"{c.value} is always PUSH (C-10), got {channel[c].value!r}")
        if set(channel) != set(admits):
            raise ValueError(
                "every admitted class has a channel and no other class does; "
                f"mismatched: {sorted(c.value for c in admits ^ set(channel))!r}"
            )
        if self.budget_per_day < 0:
            raise ValueError("budget_per_day must be non-negative")
        if self.patience_s is not None and self.patience_s < 0:
            raise ValueError("patience_s must be None or non-negative")
        if not -0.30 - 1e-9 <= self.band_shift <= 0.30 + 1e-9:   # 1e-9: float sums such as 0.1 + 0.2
            raise ValueError("band_shift must be within [-0.30, +0.30]")
        if int(target) > int(ceiling):
            raise ValueError("invitation_target may not exceed invitation_ceiling")
        if self.closes_after is not None and self.closes_after < 1:
            raise ValueError("closes_after must be None or >= 1")
```

At the top of `types.py`, the import line `from typing import Any, Mapping, Optional, Tuple` becomes `from typing import Any, FrozenSet, Mapping, Optional, Tuple, Type, TypeVar` and add `from types import MappingProxyType` beneath the `enum` import. Add `"PresenceVector", "channel_rank",` to `__all__` under `# wiring-time configuration`.

In the module docstring, after the paragraph beginning `Authoritative spec:`, add one paragraph:

```
The presence contract — ``ImpulseClass``, ``Warrant``, ``PresenceVector``,
``PresenceRung``, ``PresenceCurve`` — is specified in
``docs/superpowers/specs/2026-09-16-presence-slider-design.md`` (v2) §7;
``C-10`` and the other constraint ids cited below are its §4.
```

(Task 12 places that file in this repository.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_presence.py -q`
Expected: `23 passed` (Task 1's 3, plus 20 here: 12 named tests and an 8-case parametrize)

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/types.py src/haloysius/attunement/tests/test_presence.py
git commit -m "attunement: PresenceVector, the resolved thing every gate reads

Admission set, per-class channel ceilings, patience, budget, invitation
target and ceiling, presence signal, closes_after, and the derived band
shift. Life safety and critical are always admitted at PUSH; every
admitted class has a channel and no other class does."
```

---

### Task 3: `PresenceRung`, `PresenceCurve`

**Files:**
- Modify: `types.py` (after `PresenceVector`)
- Test: `tests/test_presence.py`

- [ ] **Step 1: Write the failing test** (append)

```python
from haloysius.attunement.types import PresenceCurve, PresenceRung


def _rung(level, admits, budget, patience, **kw):
    channel = {c: PUSH for c in admits}
    base = dict(level=level, name=f"r{level}", says="…", why="…",
                admits=frozenset(admits), channel=channel, patience_s=patience,
                budget_per_day=budget, invitation_target=InvitationLevel.NORMAL,
                invitation_ceiling=InvitationLevel.CHATTY, presence_signal=AMBIENT,
                closes_after=None)
    base.update(kw)
    return PresenceRung(**base)


LC = {C.LIFE_SAFETY, C.CRITICAL}


def test_curve_requires_ascending_levels_with_0_and_10():
    PresenceCurve(rungs=(_rung(0, LC, 0, None), _rung(10, LC | {C.WARNING}, 5, 60.0)), owner="t")
    with pytest.raises(ValueError, match="anchor level 0 and level 10"):
        PresenceCurve(rungs=(_rung(1, LC, 0, None), _rung(10, LC, 5, 60.0)), owner="t")
    with pytest.raises(ValueError, match="anchor level 0 and level 10"):
        PresenceCurve(rungs=(_rung(0, LC, 0, None), _rung(9, LC, 5, 60.0)), owner="t")
    with pytest.raises(ValueError, match="strictly ascending"):
        PresenceCurve(rungs=(_rung(0, LC, 0, None), _rung(0, LC, 5, 60.0), _rung(10, LC, 5, 60.0)), owner="t")
    with pytest.raises(ValueError, match="needs rungs"):
        PresenceCurve(rungs=(), owner="t")
    with pytest.raises(ValueError, match="level must be 0..10"):
        _rung(12, LC, 0, None)


def test_curve_requires_monotone_budget_and_patience():
    with pytest.raises(ValueError, match="budget_per_day"):
        PresenceCurve(rungs=(_rung(0, LC, 3, None), _rung(10, LC, 1, 60.0)), owner="t")
    with pytest.raises(ValueError, match="patience_s"):
        PresenceCurve(rungs=(_rung(0, LC, 0, 60.0), _rung(10, LC, 5, 240.0)), owner="t")
    with pytest.raises(ValueError, match="patience_s"):   # None mid-curve is +inf and breaks the descent
        PresenceCurve(rungs=(_rung(0, LC, 0, 60.0), _rung(5, LC, 2, None), _rung(10, LC, 5, 30.0)), owner="t")
    # equal budgets, and None-then-numbers, are both allowed
    PresenceCurve(rungs=(_rung(0, LC, 3, None), _rung(5, LC, 3, None), _rung(10, LC, 3, 240.0)), owner="t")


def test_rung_validates_as_a_vector_and_adopts_its_normalised_fields():
    with pytest.raises(ValueError, match="critical is always admitted"):
        _rung(0, {C.LIFE_SAFETY}, 0, None)   # drops CRITICAL
    r = _rung(0, {"life_safety", "critical"}, 0, None,
              channel={"life_safety": "push", "critical": "push"}, presence_signal="ambient")
    assert C.CRITICAL in r.admits and r.channel[C.CRITICAL] is PUSH and r.presence_signal is AMBIENT
    with pytest.raises(TypeError):
        r.channel[C.WARNING] = PUSH          # frozen, not a plain dict
    for bad in (dict(name=""), dict(says=" "), dict(why=None), dict(name=3)):
        with pytest.raises(ValueError, match="non-empty string"):
            _rung(0, LC, 0, None, **bad)


def test_curve_rejects_duplicate_names_non_rungs_and_an_empty_owner():
    with pytest.raises(ValueError, match="names must be unique"):
        PresenceCurve(rungs=(_rung(0, LC, 0, None, name="same"), _rung(10, LC, 5, 60.0, name="same")), owner="t")
    with pytest.raises(TypeError, match="must be PresenceRung"):
        PresenceCurve(rungs=(_rung(0, LC, 0, None), _vector(level=10)), owner="t")
    with pytest.raises(ValueError, match="owner"):
        PresenceCurve(rungs=(_rung(0, LC, 0, None), _rung(10, LC, 5, 60.0)), owner="")
    cv = PresenceCurve(rungs=[_rung(0, LC, 0, None), _rung(10, LC, 5, 60.0)], owner="t")
    assert isinstance(cv.rungs, tuple)


def test_lookups_bracket_a_level_and_clamp_at_the_ends():
    cv = PresenceCurve(rungs=(_rung(0, LC, 0, None), _rung(4, LC, 2, 120.0), _rung(10, LC, 5, 60.0)), owner="t")
    assert cv.rung_at(0).level == 0 and cv.rung_above(0).level == 4
    assert cv.rung_at(3).level == 0 and cv.rung_above(3).level == 4
    assert cv.rung_at(4).level == 4 and cv.rung_above(4).level == 10
    assert cv.rung_at(7).level == 4 and cv.rung_above(7).level == 10
    assert cv.rung_at(10).level == 10 and cv.rung_above(10) is None
    assert cv.rung_at(-1).level == 0 and cv.rung_at(11).level == 10
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL with `ImportError: cannot import name 'PresenceCurve'`

- [ ] **Step 3: Implement** — first settle the layout (review of 07c9e1b, Minor 6): move `_CHANNEL_RANK` and `channel_rank` up into the `# Helpers` section directly after `coerce_enum`, and move `"channel_rank"` in `__all__` from the wiring-time group to the `# helpers` line. Then, immediately above `class PresenceVector`, add a section banner in the file's own style:

```python
# ---------------------------------------------------------------------------
# Presence — the resolved vector, the authored rungs, the curve (spec v2 §7)
# ---------------------------------------------------------------------------
```

and after `PresenceVector`, under that banner:

```python
@dataclass(frozen=True)
class PresenceRung:
    """One authored point on a curve (spec v2 §7.3).  ``says`` is first-person
    copy the settings surface shows; ``why`` is what the rung is for."""

    level: int
    name: str
    says: str
    why: str
    admits: FrozenSet[ImpulseClass]
    channel: Mapping[ImpulseClass, ChannelClass]
    patience_s: Optional[float]
    budget_per_day: int
    invitation_target: InvitationLevel
    invitation_ceiling: InvitationLevel
    presence_signal: ChannelClass
    closes_after: Optional[int]

    def __post_init__(self) -> None:
        for f in ("name", "says", "why"):
            v = getattr(self, f)
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"a rung's {f} must be a non-empty string, got {v!r}")
        vec = self.vector(0.0)   # validates every field through the vector's rules...
        for f in ("admits", "channel", "invitation_target", "invitation_ceiling", "presence_signal"):
            object.__setattr__(self, f, getattr(vec, f))   # ...and adopts its normalised, frozen forms

    def vector(self, band_shift: float) -> PresenceVector:
        return PresenceVector(
            level=self.level,
            admits=self.admits, channel=self.channel, patience_s=self.patience_s,
            budget_per_day=self.budget_per_day, invitation_target=self.invitation_target,
            invitation_ceiling=self.invitation_ceiling, presence_signal=self.presence_signal,
            closes_after=self.closes_after, band_shift=band_shift,
        )


@dataclass(frozen=True)
class PresenceCurve:
    """The authored map from level to vector (spec v2 §7.3).  Data, not code."""

    rungs: Tuple[PresenceRung, ...]
    owner: str

    def __post_init__(self) -> None:
        if not isinstance(self.owner, str) or not self.owner.strip():
            raise ValueError(f"a curve names its owner, got {self.owner!r}")
        rungs = tuple(self.rungs)
        if not rungs:
            raise ValueError("a curve needs rungs anchoring level 0 and level 10")
        for r in rungs:
            if not isinstance(r, PresenceRung):
                raise TypeError(f"rungs must be PresenceRung, got {type(r).__name__}")
        object.__setattr__(self, "rungs", rungs)
        levels = [r.level for r in rungs]
        if levels != sorted(set(levels)):
            raise ValueError("rung levels must be strictly ascending")
        if levels[0] != 0 or levels[-1] != 10:
            raise ValueError("a curve must anchor level 0 and level 10")
        names = [r.name for r in rungs]
        if len(set(names)) != len(names):
            raise ValueError("rung names must be unique within a curve")
        budgets = [r.budget_per_day for r in rungs]
        if budgets != sorted(budgets):
            raise ValueError("budget_per_day must be non-decreasing across rungs")
        patience = [float("inf") if r.patience_s is None else float(r.patience_s) for r in rungs]
        if patience != sorted(patience, reverse=True):
            raise ValueError("patience_s must be non-increasing across rungs")

    def rung_at(self, level: int) -> PresenceRung:
        """The highest rung at or below ``level``.

        The lookups clamp and truncate deliberately: they are queries, not
        the value object — ``PresenceVector`` is where a non-integral level
        is a defect — and the resolver clamps the same way before calling.
        """
        level = max(0, min(10, int(level)))
        chosen = self.rungs[0]
        for r in self.rungs:
            if r.level <= level:
                chosen = r
        return chosen

    def rung_above(self, level: int) -> Optional[PresenceRung]:
        """The lowest rung strictly above ``level``, or None at the top.  Clamps as ``rung_at`` does."""
        level = max(0, min(10, int(level)))
        for r in self.rungs:
            if r.level > level:
                return r
        return None
```

Add `"PresenceRung", "PresenceCurve",` to `__all__` (the wiring-time group, next to `"PresenceVector"`).

Finally, so the Presence section ends with the curve and not with unrelated wiring: move the whole `class AttunementConfig` block (byte-identical) to directly after `class PolicyStability`, *before* the Presence banner.

- [ ] **Step 4: Run to verify it passes**

Expected: `28 passed`

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/types.py src/haloysius/attunement/tests/test_presence.py
git commit -m "attunement: PresenceRung and PresenceCurve — the slider is data

A curve is ascending rungs anchoring 0 and 10, budget non-decreasing and
patience non-increasing across them, each rung validated through the
vector it produces. Admission and channel are deliberately not required
monotone: a consumer may admit a class low that another admits high."
```

---

### Task 4: `Utterance` carries class and warrant; `ON_BREAKPOINT`

**Files:**
- Modify: `types.py` — `class Utterance` (line ~548) and `class ResumeCondition` (line ~206)
- Test: `tests/test_presence.py`

- [ ] **Step 1: Write the failing test** — add `ResumeCondition, Utterance` to the single top-of-file `from haloysius.attunement.types import (...)` block (`Severity` is already there; never a second import block), then append:

```python
def test_utterance_defaults_warrant_from_its_class():
    u = Utterance(source="s", impulse_class=C.RECURRENCE)
    assert u.warrant is Warrant.OBSERVED
    u2 = Utterance(source="s", impulse_class=C.SPONTANEOUS)
    assert u2.warrant is Warrant.INFERRED


def test_utterance_default_class_is_warning_introspected():
    u = Utterance(source="s")
    assert u.impulse_class is C.WARNING and u.warrant is Warrant.INTROSPECTED


def test_life_safety_and_critical_derive_their_class_and_reject_a_contradiction():
    assert Utterance(source="s", life_safety=True).impulse_class is C.LIFE_SAFETY
    assert Utterance(source="s", severity=Severity.CRITICAL).impulse_class is C.CRITICAL
    assert Utterance(source="s", life_safety=True, severity=Severity.CRITICAL).impulse_class is C.LIFE_SAFETY
    with pytest.raises(ValueError, match="contradicts"):
        Utterance(source="s", life_safety=True, impulse_class=C.ASSOCIATION)
    with pytest.raises(ValueError, match="contradicts"):
        Utterance(source="s", severity=Severity.CRITICAL, impulse_class=C.ASSOCIATION)
    with pytest.raises(ValueError, match="contradicts"):
        Utterance(source="s", impulse_class=C.LIFE_SAFETY)          # the class without the flag
    with pytest.raises(ValueError, match="contradicts"):
        Utterance(source="s", impulse_class=C.CRITICAL)             # the class without the severity
    # explicit and consistent: stays as stated
    assert Utterance(source="s", severity=Severity.WARNING, impulse_class=C.SCHEDULED).impulse_class is C.SCHEDULED
    assert Utterance(source="s", life_safety=True, impulse_class=C.LIFE_SAFETY).impulse_class is C.LIFE_SAFETY


def test_a_stronger_warrant_than_default_needs_a_citation():
    with pytest.raises(ValueError, match="needs a source_ref"):
        Utterance(source="s", impulse_class=C.ASSOCIATION, warrant=Warrant.OBSERVED)
    ok = Utterance(source="s", impulse_class=C.ASSOCIATION, warrant=Warrant.OBSERVED, source_ref="finding:42")
    assert ok.warrant is Warrant.OBSERVED and ok.source_ref == "finding:42"
    # weaker than default is always allowed
    Utterance(source="s", impulse_class=C.WARNING, warrant=Warrant.INFERRED)


def test_on_breakpoint_is_a_resume_condition():
    assert ResumeCondition.ON_BREAKPOINT.value == "on_breakpoint"


def test_a_foreign_enum_is_rejected_as_impulse_class_or_warrant():
    with pytest.raises(TypeError):
        Utterance(source="s", impulse_class=Severity.CRITICAL)
    with pytest.raises(TypeError):
        Utterance(source="s", warrant=Severity.INFO)
    # value strings are still accepted, per the file's convention
    assert Utterance(source="s", impulse_class="recurrence").impulse_class is C.RECURRENCE


def test_severity_is_coerced_like_every_other_enum_field():
    u = Utterance(source="s", severity="critical")
    assert u.severity is Severity.CRITICAL and u.impulse_class is C.CRITICAL
    with pytest.raises(TypeError):
        Utterance(source="s", severity=C.CRITICAL)      # the "critical" value-string collision, from the other side


def test_source_ref_is_none_or_a_non_empty_string():
    with pytest.raises(ValueError, match="source_ref"):
        Utterance(source="s", impulse_class=C.ASSOCIATION, warrant=Warrant.OBSERVED, source_ref="   ")
    with pytest.raises(ValueError, match="source_ref"):
        Utterance(source="s", source_ref=42)
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'impulse_class'`

- [ ] **Step 3: Implement**

In `class ResumeCondition`, after `AT_TIME = "at_time"` add:

```python
    ON_BREAKPOINT = "on_breakpoint"      # a coarse task boundary the consumer's sensor reports (presence v2 §7.6)
```

In `class Utterance`, after `authority_rule: str = ""` add three fields:

```python
    impulse_class: Optional[ImpulseClass] = None         # presence v2 §7.4 — None → derived from life_safety / severity, else WARNING
    warrant: Optional[Warrant] = None                    # None → warrant_for(impulse_class)
    source_ref: Optional[str] = None                     # ledger row id, thread turn id, sensor name — the citation
```

Replace the existing `__post_init__` of `Utterance` with:

```python
    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("an Utterance must name its source")
        if self.authority_rule and not self.authority:
            raise ValueError("authority_rule names a rule the utterance does not claim; set authority=True")
        severity = coerce_enum(Severity, self.severity, "severity")
        object.__setattr__(self, "severity", severity)
        # The class and the flags must agree.  Unstated, the class is derived
        # (C-10: life safety and critical are always their own class); stated,
        # a contradiction is a producer bug and is rejected, not rounded.
        derived = (ImpulseClass.LIFE_SAFETY if self.life_safety
                   else ImpulseClass.CRITICAL if severity is Severity.CRITICAL
                   else ImpulseClass.WARNING)
        if self.impulse_class is None:
            cls = derived
        else:
            cls = coerce_enum(ImpulseClass, self.impulse_class, "impulse_class")
            flagged = derived in ALWAYS_ADMITTED
            if (flagged and cls is not derived) or (not flagged and cls in ALWAYS_ADMITTED):
                raise ValueError(
                    f"impulse_class {cls.value} contradicts life_safety={self.life_safety} / "
                    f"severity={severity.value}; the class and the flags must agree"
                )
        object.__setattr__(self, "impulse_class", cls)
        if self.source_ref is not None and (not isinstance(self.source_ref, str) or not self.source_ref.strip()):
            raise ValueError(f"source_ref must be None or a non-empty string, got {self.source_ref!r}")
        default = warrant_for(cls)
        warrant = default if self.warrant is None else coerce_enum(Warrant, self.warrant, "warrant")
        if warrant_rank(warrant) > warrant_rank(default) and not self.source_ref:
            raise ValueError(
                f"warrant {warrant.value} is stronger than {cls.value}'s default "
                f"{default.value}; a stronger warrant needs a source_ref"
            )
        object.__setattr__(self, "warrant", warrant)
```

Extend the `Utterance` class docstring with this closing paragraph: ``impulse_class`` is the kind of thing this is and ``warrant`` its grade of knowledge (presence spec v2 §7.1, §7.4).  Unstated, the class is derived from ``life_safety`` and ``severity``; stated, it must agree with them.  A warrant stronger than the class's default requires ``source_ref``. And in the `Warrant` enum docstring, the line about citations becomes: INTROSPECTED needs no citation; OBSERVED and TOLD carry one to render provenance, and raising a warrant above a class's default requires one; INFERRED licenses no assertion at all.

- [ ] **Step 4: Run to verify it passes**

Run the whole attunement suite too — `Utterance` is used everywhere:
`.venv/bin/python -m pytest src/haloysius/attunement/tests -q`
Expected: all previously passing tests still pass; `test_presence.py` `36 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/types.py src/haloysius/attunement/tests/test_presence.py
git commit -m "attunement: an Utterance says what kind of thing it is and how it knows

impulse_class is derived from life_safety and severity when unstated and
must agree with them when stated; severity is coerced like every other
enum field; warrant defaults from the class and may only be raised with a
source_ref — the citation the why-trust affordance will render. A
foreign enum sharing a value string is rejected, not coerced.
ResumeCondition gains ON_BREAKPOINT for bounded deferral."
```

---

### Task 5: Constants, `band_shift`, `DEFAULT_CURVE`, `resolve_presence`

**Files:**
- Modify: `attunement/constants.py`
- Create: `attunement/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: Write the failing tests** — extend the single top-of-file `from haloysius.attunement.types import (...)` block with `AttachmentSafety` (alphabetical; never a second block), and add these two imports after the other top-of-file imports:

```python
from haloysius.attunement.constants import CONSTANTS
from haloysius.attunement.presence import (
    DEFAULT_CURVE,
    band_shift,
    default_presence,
    resolve_presence,
)
```

Then append at the end of the file:

```python
SAFE = AttachmentSafety(max_proactive_per_day=24)


def test_constants_carry_the_presence_numbers():
    assert CONSTANTS["BAND_SHIFT_MAX"] == 0.30
    assert CONSTANTS["PATIENCE_DEFAULT_S"] == 240.0
    assert CONSTANTS["RECENCY_WINDOW_S"] == 3 * 86400


@pytest.mark.parametrize("level,expected", [(0, 0.30), (3, 0.0), (10, -0.30), (1, 0.20), (5, -0.30 * 2 / 7)])
def test_band_shift_is_piecewise_with_three_neutral(level, expected):
    assert band_shift(level) == pytest.approx(expected)


def test_default_curve_is_valid_and_admits_no_social_affect():
    assert DEFAULT_CURVE.owner == "haloysius"
    for r in DEFAULT_CURVE.rungs:
        assert C.AFFECT_SOCIAL not in r.admits


def test_level_three_reproduces_balanced():
    v = resolve_presence(3, DEFAULT_CURVE, SAFE)
    assert v.admits == {C.LIFE_SAFETY, C.CRITICAL, C.WARNING, C.SCHEDULED, C.RECURRENCE}
    assert v.invitation_target is InvitationLevel.NORMAL and v.invitation_ceiling is InvitationLevel.CHATTY
    assert v.band_shift == 0.0 and v.budget_per_day == 3 and v.level == 3


def test_level_zero_is_soft_mute_not_off():
    v = resolve_presence(0, DEFAULT_CURVE, SAFE)
    assert v.admits == {C.LIFE_SAFETY, C.CRITICAL}
    assert v.budget_per_day == 0 and v.patience_s is None
    assert v.presence_signal is AMBIENT               # still here
    assert v.invitation_target is v.invitation_ceiling is InvitationLevel.SILENT


def test_level_ten_admits_spontaneous():
    v = resolve_presence(10, DEFAULT_CURVE, SAFE)
    assert C.SPONTANEOUS in v.admits and v.channel[C.SPONTANEOUS] is PUSH
    assert v.closes_after == 3 and v.band_shift == pytest.approx(-0.30)
    assert v.invitation_target is v.invitation_ceiling is InvitationLevel.CHATTY   # the old ASSERTIVE mapping


def test_discrete_fields_step_and_continuous_fields_interpolate():
    v2 = resolve_presence(2, DEFAULT_CURVE, SAFE)   # between rung 1 (budget 1, 240s) and rung 3 (budget 3, 240s)
    assert v2.admits == resolve_presence(1, DEFAULT_CURVE, SAFE).admits
    assert v2.budget_per_day == 2
    v5 = resolve_presence(5, DEFAULT_CURVE, SAFE)   # between rung 4 (180s) and rung 6 (120s)
    assert v5.patience_s == pytest.approx(150.0)


def test_subject_linked_is_ambient_at_the_middle():
    v = resolve_presence(4, DEFAULT_CURVE, SAFE)
    assert v.channel[C.SUBJECT_LINKED] is AMBIENT


def test_attachment_safety_clamps_the_budget():
    v = resolve_presence(10, DEFAULT_CURVE, AttachmentSafety(max_proactive_per_day=2))
    assert v.budget_per_day == 2


def test_level_is_clamped_to_the_range():
    assert resolve_presence(99, DEFAULT_CURVE, SAFE).level == 10
    assert resolve_presence(-4, DEFAULT_CURVE, SAFE).level == 0


def test_an_override_admits_one_class_and_funds_it():
    v = resolve_presence(0, DEFAULT_CURVE, SAFE, overrides={C.WARNING: 3})
    assert C.WARNING in v.admits and v.channel[C.WARNING] is PUSH
    assert v.budget_per_day == 3                       # lifted to rung 3's: an override funds what it admits
    assert v.patience_s is None and v.band_shift == pytest.approx(0.30)   # pace and band stay the base level's
    down = resolve_presence(10, DEFAULT_CURVE, SAFE, overrides={C.SPONTANEOUS: 3})
    assert C.SPONTANEOUS not in down.admits and down.budget_per_day == 5   # removal never shrinks the budget


def test_life_safety_and_critical_reject_overrides():
    with pytest.raises(ValueError):
        resolve_presence(3, DEFAULT_CURVE, SAFE, overrides={C.CRITICAL: 0})


def test_default_presence_is_level_three_under_engine_safety():
    v = default_presence()
    assert v.level == 3 and v.budget_per_day == 3


def test_the_door_truncates_a_level_and_names_a_bad_one():
    # The resolver is the lenient door in front of the strict vector: a
    # future "make it strict" is a deliberate edit here, not a silent drift.
    assert resolve_presence("3", DEFAULT_CURVE, SAFE).level == 3
    assert resolve_presence(3.7, DEFAULT_CURVE, SAFE).level == 3
    with pytest.raises(ValueError, match="level"):
        resolve_presence("three", DEFAULT_CURVE, SAFE)
    with pytest.raises(ValueError, match="level"):
        resolve_presence(float("inf"), DEFAULT_CURVE, SAFE)
    with pytest.raises(TypeError, match="level"):
        resolve_presence(None, DEFAULT_CURVE, SAFE)
    with pytest.raises(TypeError, match="level"):   # a YAML `presence: true` must not resolve to rung 1
        resolve_presence(True, DEFAULT_CURVE, SAFE)
    with pytest.raises(ValueError, match=r"presence_overrides\[warning\]"):
        resolve_presence(3, DEFAULT_CURVE, SAFE, overrides={C.WARNING: "x"})


def test_override_keys_accept_value_strings_and_reject_foreign_enums():
    v = resolve_presence(0, DEFAULT_CURVE, SAFE, overrides={"warning": 3})
    assert C.WARNING in v.admits
    with pytest.raises(TypeError, match="presence_overrides key"):
        resolve_presence(0, DEFAULT_CURVE, SAFE, overrides={Severity.WARNING: 3})


def test_an_override_cannot_admit_what_the_curve_never_admits():
    base = resolve_presence(3, DEFAULT_CURVE, SAFE)
    v = resolve_presence(3, DEFAULT_CURVE, SAFE, overrides={C.AFFECT_SOCIAL: 10})
    assert v.admits == base.admits and dict(v.channel) == dict(base.channel)


def test_patience_is_none_when_either_bracketing_rung_never_pushes():
    # Not reachable on DEFAULT_CURVE (rungs 0 and 1 are adjacent); spec §8:
    # None on either side yields None — between "never push" and 240 s the
    # answer is "never push".
    def rung(level, name, patience):
        return PresenceRung(level=level, name=name, says=name, why=name,
                            admits=ALWAYS_ADMITTED, channel={c: PUSH for c in ALWAYS_ADMITTED},
                            patience_s=patience, budget_per_day=0,
                            invitation_target=InvitationLevel.SILENT, invitation_ceiling=InvitationLevel.SILENT,
                            presence_signal=AMBIENT, closes_after=None)
    curve = PresenceCurve(owner="t", rungs=(rung(0, "a", None), rung(10, "b", 240.0)))
    assert resolve_presence(5, curve, SAFE).patience_s is None


def test_the_engines_own_ceiling_clamps_the_top_of_the_curve():
    assert resolve_presence(10, DEFAULT_CURVE, AttachmentSafety()).budget_per_day == 3
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `KeyError: 'BAND_SHIFT_MAX'` (or import error on `presence`)

- [ ] **Step 3: Add the constants** — in `constants.py`, inside `CONSTANTS`, after `"HOLD_MAX_S": 7200,` add:

```python
    # -- presence (spec 2026-09-16 v2 §7.5, §10, §11)
    "BAND_SHIFT_MAX": 0.30,        # ASK_T and SPEAK_T translate together by up to this much
    "PATIENCE_DEFAULT_S": 240.0,   # bounded deferral: the useful window is minutes (pass 1 L2, L17)
    "RECENCY_WINDOW_S": 3 * 86400, # topic-recency gate (slice 2) — a topic raised within this is not re-raised
```

- [ ] **Step 3b: Drop the unused keyword** — in `types.py`, `PresenceRung.vector`'s signature becomes `def vector(self, band_shift: float) -> PresenceVector:` with `level=self.level`; the resolver below builds its vector directly (it also needs interpolated budget and patience), so the `level=` override has no caller (review of 1890743, Minor 10).

- [ ] **Step 4: Create `presence.py`**

```python
"""Resolution: a level and a curve become the vector every gate reads.

Spec: ``docs/superpowers/specs/2026-09-16-presence-slider-design.md`` (v2)
§7.5, §8.  Pure: no clock, no I/O.  Importing this module pulls only the
standard library.

``DEFAULT_CURVE`` is the strictest in the family (C-5): a consumer relaxes
it in its own reviewed table.  Its ``says`` copy is placeholder text and
deliberately in no voice: a consumer supplies the voice (D8), and these
lines are not to be tuned into the engine's.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional

from .constants import CONSTANTS
from .types import (
    ALWAYS_ADMITTED,
    AttachmentSafety,
    ChannelClass,
    ImpulseClass,
    InvitationLevel,
    PresenceCurve,
    PresenceRung,
    PresenceVector,
    coerce_enum,
)

__all__ = ["DEFAULT_CURVE", "band_shift", "resolve_presence", "default_presence"]

_C = ImpulseClass
_PUSH, _AMBIENT = ChannelClass.PUSH, ChannelClass.AMBIENT


def _level(value: Any, what: str) -> int:
    """The lenient door, once: a level is truncated and clamped to 0..10, and
    a value that is not a number is refused by field name — a wrong type
    (``bool`` included) as ``TypeError``, a bad value (``"three"``, ``inf``)
    as ``ValueError``, the same split ``coerce_enum`` and the strict
    ``PresenceVector`` make.  This is the only clamp on the way in."""
    if isinstance(value, bool):
        raise TypeError(f"{what} must be a number 0..10, not {value!r}")
    try:
        n = int(value)
    except TypeError:
        raise TypeError(f"{what} must be a number 0..10, not {value!r}") from None
    except (ValueError, OverflowError):
        raise ValueError(f"{what} must be a number 0..10, not {value!r}") from None
    return max(0, min(10, n))


def band_shift(level: int) -> float:
    """Piecewise so 3 is exactly neutral and both ends reach the full shift (§7.5)."""
    level = _level(level, "level")
    m = CONSTANTS["BAND_SHIFT_MAX"]
    if level <= 3:
        return m * (3 - level) / 3
    return -m * (level - 3) / 7


def _rung(level: int, name: str, says: str, why: str, channel: Mapping[ImpulseClass, ChannelClass],
          patience_s: Optional[float], budget: int, target: InvitationLevel, ceiling: InvitationLevel,
          closes_after: Optional[int]) -> PresenceRung:
    return PresenceRung(
        level=level, name=name, says=says, why=why,
        admits=frozenset(channel), channel=dict(channel), patience_s=patience_s,
        budget_per_day=budget, invitation_target=target, invitation_ceiling=ceiling,
        presence_signal=_AMBIENT, closes_after=closes_after,
    )


_L0 = {_C.LIFE_SAFETY: _PUSH, _C.CRITICAL: _PUSH}
_L1 = {**_L0, _C.WARNING: _PUSH}
_L3 = {**_L1, _C.SCHEDULED: _PUSH, _C.RECURRENCE: _PUSH}
_L4 = {**_L3, _C.SUBJECT_LINKED: _AMBIENT}
_L6 = {**_L4, _C.OPEN_LOOP: _PUSH, _C.ABSENCE: _AMBIENT}
_L8 = {**_L6, _C.ASSOCIATION: _PUSH, _C.AFFECT_STATE: _PUSH}
_L10 = {**_L8, _C.SPONTANEOUS: _PUSH}

_S, _M, _N, _CH = (InvitationLevel.SILENT, InvitationLevel.MINIMAL,
                   InvitationLevel.NORMAL, InvitationLevel.CHATTY)

DEFAULT_CURVE = PresenceCurve(owner="haloysius", rungs=(
    # level, name, says, why, channel, patience_s, budget, target, ceiling, closes_after
    _rung(0, "mute", "Only what cannot wait.", "Nothing interrupts; everything stays findable.",
          _L0, None, 0, _S, _S, None),
    _rung(1, "warn", "Warnings, and nothing else unbidden.", "Warnings are worth attention; the rest waits to be looked at.",
          _L1, 240.0, 1, _M, _M, None),   # target == ceiling: "talk to me more" must not widen a quiet level (Halbert Q7.6)
    _rung(3, "scheduled", "The scheduled report, and what keeps happening.", "The default: informed without being interrupted.",
          _L3, 240.0, 3, _N, _CH, None),
    _rung(4, "notice", "What bears on the current work is shown, not spoken.", "Attention is offered, never taken.",
          _L4, 180.0, 3, _N, _CH, None),
    _rung(6, "recall", "Things come back up when they fall due.", "Continuity: what was said is not lost.",
          _L6, 120.0, 4, _N, _CH, 3),
    _rung(8, "associate", "What the work brings to mind.", "Thought is voiced as thought, never as fact.",
          _L8, 90.0, 5, _CH, _CH, 3),
    _rung(10, "think", "A thought when there is one, not only when something happens.", "Company, bounded.",
          _L10, 60.0, 5, _CH, _CH, 3),
))


def resolve_presence(level: int, curve: PresenceCurve, safety: AttachmentSafety,
                     overrides: Optional[Mapping[ImpulseClass, int]] = None) -> PresenceVector:
    """A level through a curve, clamped by the consumer's ceilings (§8, §9).

    Discrete fields step at rungs; ``patience_s`` and ``budget_per_day``
    interpolate linearly between the bracketing rungs.  An override resolves
    one class through the curve at its own level and substitutes that class's
    admission and channel; it lifts the budget to at least its rung's (an
    override funds what it admits) and never shrinks it.  Patience and the
    band stay the base level's (D4).
    """
    level = _level(level, "level")
    lo = curve.rung_at(level)
    hi = curve.rung_above(level)
    if hi is None or hi.level == lo.level:
        t = 0.0
        hi = lo
    else:
        t = (level - lo.level) / float(hi.level - lo.level)

    budget = int(math.floor(lo.budget_per_day + t * (hi.budget_per_day - lo.budget_per_day)))
    if lo.patience_s is None or hi.patience_s is None:
        patience: Optional[float] = None
    else:
        patience = lo.patience_s + t * (hi.patience_s - lo.patience_s)

    admits = set(lo.admits)
    channel = dict(lo.channel)
    for raw_cls, raw_lvl in (overrides or {}).items():
        cls = coerce_enum(ImpulseClass, raw_cls, "presence_overrides key")
        if cls in ALWAYS_ADMITTED:
            raise ValueError(f"{cls.value} rejects overrides (C-10)")
        r = curve.rung_at(_level(raw_lvl, f"presence_overrides[{cls.value}]"))
        if cls in r.admits:
            admits.add(cls)
            channel[cls] = r.channel[cls]
            budget = max(budget, r.budget_per_day)   # an override funds what it admits (D4)
        else:
            admits.discard(cls)
            channel.pop(cls, None)

    return PresenceVector(
        level=level,
        admits=frozenset(admits),
        channel=channel,
        patience_s=patience,
        budget_per_day=min(budget, int(safety.max_proactive_per_day)),
        invitation_target=lo.invitation_target,
        invitation_ceiling=lo.invitation_ceiling,
        presence_signal=lo.presence_signal,
        closes_after=lo.closes_after,
        band_shift=band_shift(level),
    )


def default_presence() -> PresenceVector:
    """Level 3 through the engine curve under the engine's own ceilings."""
    return resolve_presence(3, DEFAULT_CURVE, AttachmentSafety())
```

- [ ] **Step 5: Run to verify it passes**

Expected: `test_presence.py` `58 passed` (the band-shift parametrize is 5 cases)

- [ ] **Step 6: Commit**

```bash
git add src/haloysius/attunement/constants.py src/haloysius/attunement/presence.py src/haloysius/attunement/types.py src/haloysius/attunement/tests/test_presence.py
git commit -m "attunement: resolve_presence, band_shift and the engine's default curve

Seven rungs, strictest in the family: social affect admitted at no
level, top budget 5, closes_after 3. Discrete fields step, budget and
patience interpolate, the consumer's AttachmentSafety clamps, and the
band shift is derived — never authored — so the ask band keeps its width
at every level."
```

---

### Task 6: `AttunementContext.presence` replaces `.dial`

**Files:**
- Modify: `types.py` — `class AttunementContext` line ~793 `dial: ProactivityDial = field(default_factory=ProactivityDial)`
- Test: `tests/test_presence.py`

- [ ] **Step 1: Write the failing test** — add `AttunementContext` to the single top-of-file `from haloysius.attunement.types import (...)` block (alphabetical; never a second block), add `fields` to the `from dataclasses import ...` line, then append:

```python
def test_context_defaults_to_level_three():
    ctx = AttunementContext(persona_id="p")
    assert ctx.presence.level == 3
    assert "dial" not in {f.name for f in fields(AttunementContext)}   # the declaration, not an instance
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `AttributeError: 'AttunementContext' object has no attribute 'presence'`

- [ ] **Step 3: Implement** — in `types.py` replace the line

```python
    dial: ProactivityDial = field(default_factory=ProactivityDial)
```

with

```python
    # Resolved by the consumer via resolve_presence; the engine's own default is level 3.
    presence: PresenceVector = field(default_factory=_default_presence)
```

and, above `class AttunementContext`, add:

```python
def _default_presence() -> PresenceVector:
    # Lazy: presence.py imports this module; a module-level import here would cycle.
    from .presence import default_presence
    return default_presence()
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_presence.py -q`
Expected: `59 passed`. (The rest of the suite is now broken on `dial=`; Tasks 7–10 repair it.)

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/types.py src/haloysius/attunement/tests/test_presence.py
git commit -m "attunement: the context carries a PresenceVector, not a dial"
```

---

### Task 7: Policy — admission first, band translation, budget from the vector

**Files:**
- Modify: `attunement/policy.py` (imports line 24; `_decide_inner` lines 256–360; `assess_presence` line 379)
- Modify: `tests/test_policy.py` (the `CASES` table lines 71, 79, 81, 82 and line 185)
- Modify: `tests/test_authority.py` (lines 102, 116, 160, 165, 176, 185, 197–198)

- [ ] **Step 1: Rewrite the failing tests**

In `tests/test_policy.py` replace the import of `DialLevel,` and `ProactivityDial,` with:

```python
    ImpulseClass,
    AttachmentSafety,
```

and add after the `from haloysius.attunement.types import (...)` block:

```python
from haloysius.attunement.presence import DEFAULT_CURVE, resolve_presence

SAFE = AttachmentSafety(max_proactive_per_day=24)


def P(level, **overrides):
    return resolve_presence(level, DEFAULT_CURVE, SAFE, overrides={ImpulseClass(k): v for k, v in overrides.items()})
```

In `CASES`, replace the four dial rows:

```python
    ("dial_off", dict(utterance=U(), dial=ProactivityDial(DialLevel.OFF)), EngagementOutcome.SILENT),
```
→
```python
    ("mute_does_not_admit_a_warning", dict(utterance=U(), presence=P(0)), EngagementOutcome.SILENT),
    ("mute_still_speaks_a_critical", dict(utterance=U(severity=Severity.CRITICAL), presence=P(0), **_established()), EngagementOutcome.SPEAK),
```

```python
    ("category_override_beats_dial", dict(utterance=U(category="security", severity=Severity.WARNING, anchored=True), dial=ProactivityDial(DialLevel.OFF, {"security": DialLevel.ASSERTIVE}), **_established()), EngagementOutcome.SPEAK),
```
→
```python
    # The override admits WARNING at level 0 and lifts the budget to rung 3's; the base level's band
    # (+0.30) still applies (D4), so time_sensitive supplies the margin an admitted-but-hard-banded
    # warning needs to clear SPEAK_T.
    ("class_override_admits_and_funds_one_class", dict(utterance=U(severity=Severity.WARNING, anchored=True, time_sensitive=True), presence=P(0, warning=3), **_established()), EngagementOutcome.SPEAK),
```

```python
    ("quiet_dial_holds_warning", dict(utterance=U(severity=Severity.WARNING, anchored=True), dial=ProactivityDial(DialLevel.QUIET), **_established()), EngagementOutcome.HOLD),
    ("quiet_dial_lets_critical_through", dict(utterance=U(severity=Severity.CRITICAL), dial=ProactivityDial(DialLevel.QUIET), **_established()), EngagementOutcome.SPEAK),
```
→
```python
    ("level_one_admits_a_warning_but_the_band_is_high", dict(utterance=U(severity=Severity.WARNING), presence=P(1), invitation=InvitationLevel.MINIMAL, **_established()), EngagementOutcome.HOLD),
    ("level_one_lets_critical_through", dict(utterance=U(severity=Severity.CRITICAL), presence=P(1), **_established()), EngagementOutcome.SPEAK),
```

Replace `balanced_drops_unanchored_info` row's expectation: at level 3 an unanchored INFO `WARNING`-class utterance is *admitted* (the class is WARNING) and falls to the inequality: value 0.30, cost 0.40 → margin −0.10 < `HOLD_WORTH_T[info]` 0.45 → SILENT. Keep the row, rename:

```python
    ("unanchored_info_falls_silent_on_the_margin", dict(utterance=U(), **_established()), EngagementOutcome.SILENT),
```

In `test_dwell_keeps_previous_outcome_and_user_turn_resets`, pin the single stamp on a kept decision (add `import re` at the top): after the assertion that `"stability:dwell" in kept.reasons`, add `assert [r for r in kept.reasons if re.fullmatch(r"presence:\\d+", r)] == [r for r in prev.reasons if re.fullmatch(r"presence:\\d+", r)]` and `assert sum(1 for r in kept.reasons if r.startswith("impulse:")) == 1` (adapt the names `kept`/`prev` to the test's own).

Line 185: `assert assess_presence(ctx(dial=ProactivityDial(DialLevel.OFF))).outcome is EngagementOutcome.SILENT` → the vector at 0 still signals AMBIENT, so presence is AVAILABLE; assert the new truth and the PULL case:

```python
    assert assess_presence(ctx(presence=P(0))).outcome is EngagementOutcome.AVAILABLE
    from dataclasses import replace as _replace
    silent = _replace(P(0), presence_signal=ChannelClass.PULL)
    assert assess_presence(ctx(presence=silent)).outcome is EngagementOutcome.SILENT
```

Append three new tests at the end of `test_policy.py`:

```python
from haloysius.attunement.policy import thresholds


def test_the_ask_band_keeps_its_width_at_every_level():
    for sev in (Severity.INFO, Severity.WARNING):
        width = CONSTANTS["SPEAK_T"][sev] - CONSTANTS["ASK_T"][sev]
        for level in range(11):
            speak_t, ask_t = thresholds(sev, P(level).band_shift, None, 0.0)
            assert speak_t - ask_t == pytest.approx(width)
            assert ask_t < speak_t


# The F3 result made visible: a bare warning with no sensor (value 0.60, cost 0.40,
# margin 0.20 exactly) climbs the ladder as the band drops.  A wrong constant moves a rung.
LADDER = {0: EngagementOutcome.SILENT, 1: EngagementOutcome.HOLD, 2: EngagementOutcome.HOLD,
          3: EngagementOutcome.ASK_FIRST, 4: EngagementOutcome.ASK_FIRST, 5: EngagementOutcome.ASK_FIRST,
          **{lvl: EngagementOutcome.SPEAK for lvl in range(6, 11)}}


def test_the_decision_agrees_with_the_shifted_thresholds_at_every_level():
    for level in range(11):
        d = decide(ctx(utterance=U(severity=Severity.WARNING), presence=P(level), **_established()))
        assert d.outcome is LADDER[level], level
        if level == 0:
            assert d.reasons[0] == "presence:not_admitted"
            continue
        speak_t, ask_t = thresholds(Severity.WARNING, P(level).band_shift, None, 0.0)
        eps = CONSTANTS["THRESHOLD_EPS"]
        if 0.20 >= speak_t - eps:
            assert d.outcome is EngagementOutcome.SPEAK, level
        elif 0.20 >= ask_t - eps:
            assert d.outcome is EngagementOutcome.ASK_FIRST, level
        else:
            assert d.outcome in (EngagementOutcome.HOLD, EngagementOutcome.SILENT), level


def test_the_critical_sentinel_does_not_shift():
    for prev in (None, EngagementOutcome.HOLD, EngagementOutcome.SPEAK):
        neutral = thresholds(Severity.CRITICAL, 0.0, prev, 0.05)
        assert thresholds(Severity.CRITICAL, 0.30, prev, 0.05) == neutral
        assert thresholds(Severity.CRITICAL, -0.30, prev, 0.05) == neutral


def test_hysteresis_biases_toward_the_previous_outcome():
    speak_t, ask_t = thresholds(Severity.WARNING, 0.0, None, 0.05)
    assert thresholds(Severity.WARNING, 0.0, EngagementOutcome.SPEAK, 0.05) == (pytest.approx(speak_t - 0.05), ask_t)
    assert thresholds(Severity.WARNING, 0.0, EngagementOutcome.HOLD, 0.05) == (pytest.approx(speak_t + 0.05), ask_t)
    assert thresholds(Severity.WARNING, 0.0, EngagementOutcome.ASK_FIRST, 0.05) == (speak_t, pytest.approx(ask_t - 0.05))


def test_reasons_carry_presence_impulse_and_warrant():
    d = decide(ctx(utterance=U(severity=Severity.WARNING, anchored=True), presence=P(3), **_established()))
    assert "presence:3" in d.reasons and "impulse:warning" in d.reasons and "warrant:introspected" in d.reasons
    held = decide(ctx(utterance=U(), presence=P(0)))
    assert held.reasons[0] == "presence:not_admitted"
    assert "presence:0" in held.reasons and "impulse:warning" in held.reasons
    # Every exit is stamped, including the two that return before admission.
    ls = decide(ctx(utterance=U(life_safety=True), presence=P(0)))
    assert ls.reasons == ("life_safety_bypass", "presence:0", "impulse:life_safety", "warrant:introspected")
    pull = decide(ctx(utterance=U(channel_class=ChannelClass.PULL), presence=P(0)))
    assert pull.reasons == ("channel:pull", "presence:0", "impulse:warning", "warrant:introspected")


def test_a_context_too_broken_to_stamp_still_gets_its_verdict():
    # _tagged sits on the life-safety path and on both fail-quiet fallbacks; it may never raise.
    d = decide(ctx(utterance=U(life_safety=True), presence=None))
    assert d.outcome is EngagementOutcome.SPEAK and d.reasons == ("life_safety_bypass",)
    d = decide(ctx(utterance=U(severity=Severity.WARNING), presence=None))
    assert d.outcome is EngagementOutcome.HOLD and d.reasons[0] == "policy_error"
    assert assess_presence(ctx(presence=None)).reasons[0] == "policy_error"


def test_a_presence_assessment_stamps_the_level_but_no_impulse():
    d = assess_presence(ctx(utterance=U()))
    assert "presence:3" in d.reasons and not any(r.startswith("impulse:") for r in d.reasons)


def test_budget_exhaustion_carries_both_keys():
    d = decide(ctx(utterance=U(severity=Severity.WARNING, anchored=True), presence=P(3),
                   proactive_count_today=3, **_established()))
    assert d.outcome is EngagementOutcome.HOLD
    assert "presence:budget_exhausted" in d.reasons and "attachment:daily_cap" in d.reasons
```

In `tests/test_authority.py` replace the imports `DialLevel,` / `ProactivityDial,` with `ImpulseClass, AttachmentSafety,` and add the same `P()` helper (copy the four lines from `test_policy.py` — `SAFE`, `def P`). Then:
- every `dial=ProactivityDial(level=DialLevel.OFF)` → `presence=P(0)`
- every `dial=ProactivityDial(level=DialLevel.QUIET)` → `presence=P(1)`
- lines 197–198 `for dial in (DialLevel.OFF, DialLevel.QUIET, DialLevel.BALANCED): d = decide(ctx(U(**kw), dial=ProactivityDial(level=dial)))` → `for level in (0, 1, 3): d = decide(ctx(U(**kw), presence=P(level)))`

Six tests assert the dial's reason strings; their intent — the holder's limits bind a ruling, and a silenced ruling is legible as one — is unchanged, so they are rewritten to the vector's strings, not deleted (`ctx()` in this file already carries an established relationship):

- `TestConsentShapedGatesAreBypassed.test_a_ruling_counts_as_bidden_at_balanced` — **delete**. The balanced dial's unbidden-trivia rule is retired (DECISIONS row 1); what silences unanchored info now is the margin, which binds a ruling as it binds a gift, so there is no gate left for a ruling to be exempt from.
- `TestTheHoldersLimitsStillBind.test_the_dial_off_silences_a_ruling_too` → `test_mute_silences_a_ruling_too`; the comment's "the silence itself is unchanged" stays; assert `d.outcome is EngagementOutcome.SILENT and d.reasons[0] == "presence:not_admitted"`.
- `TestTheHoldersLimitsStillBind.test_a_quiet_dial_still_holds_a_ruling` →

```python
    def test_a_low_level_still_binds_a_ruling(self):
        """Level 1 admits a warning but bands it high; the band binds a ruling as it binds a gift."""
        gift = decide(ctx(U(severity=Severity.WARNING), presence=P(1), invitation=InvitationLevel.MINIMAL))
        d = decide(ctx(ruling(severity=Severity.WARNING), presence=P(1), invitation=InvitationLevel.MINIMAL))
        assert gift.outcome is EngagementOutcome.HOLD
        assert d.outcome is gift.outcome and "presence:1" in d.reasons
```

- `TestASilencedRulingIsLegibleAsOne.test_dial_off_for_a_ruling_names_the_ruling` → `test_mute_for_a_ruling_names_the_ruling`; expected tuple `("presence:not_admitted", "authority", "authority:timeRules.rebuttal", "presence:0", "impulse:warning", "warrant:introspected")` (verdict, claim, then the stamp).
- `TestASilencedRulingIsLegibleAsOne.test_dial_off_for_a_ruling_without_a_named_rule` → `test_mute_for_a_ruling_without_a_named_rule`; expected `("presence:not_admitted", "authority", "presence:0", "impulse:warning", "warrant:introspected")`.
- `TestAGiftsEarlyReturnsAreByteIdentical.test_dial_off_for_a_gift_is_unchanged` → `test_mute_for_a_gift_carries_no_claim`; expected `d.outcome is EngagementOutcome.SILENT and d.reasons == ("presence:not_admitted", "presence:0", "impulse:warning", "warrant:introspected")`.
- The exact-tuple assertions on the two pre-admission exits gain the stamp at the end: `test_life_safety_is_separate_and_first` → `("life_safety_bypass", "presence:3", "impulse:life_safety", "warrant:introspected")`; `test_a_pull_channel_ruling_names_the_ruling` → `("channel:pull", "authority", "authority:timeRules.rebuttal", "presence:3", "impulse:warning", "warrant:introspected")`; `test_a_pull_channel_gift_is_unchanged` → `("channel:pull", "presence:3", "impulse:warning", "warrant:introspected")`. Three more exact-tuple assertions gain the same trailing stamp — never reorder what precedes it: `test_policy.py::test_policy_error_fails_quiet_except_life_safety` → `("policy_error", "presence:3", "impulse:warning", "warrant:introspected")`; `test_policy.py::test_assess_presence`'s `asleep` tuple → `("receptivity:unavailable:sleep", "presence:3")` (no utterance, so the level alone); `test_subtractive.py::test_life_safety_is_never_inferred_and_never_suppressed` → `("life_safety_bypass", "presence:3", "impulse:life_safety", "warrant:introspected")`. `Receptivity.reasons` / `d.receptivity.reasons` are a different field and are untouched.
- Add to `TestTheHoldersLimitsStillBind` (the margin binds a ruling as it binds a gift — the property the deleted balanced-dial test used to stand in for):

```python
    def test_the_margin_binds_a_ruling_as_it_binds_a_gift(self):
        gift = decide(ctx(U(severity=Severity.INFO)))
        d = decide(ctx(ruling(severity=Severity.INFO)))
        assert gift.reasons[0] == d.reasons[0] == "margin:silent"
        assert d.margin == pytest.approx(gift.margin)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_policy.py src/haloysius/attunement/tests/test_authority.py -q`
Expected: FAIL — `ImportError: cannot import name 'thresholds'` and `TypeError ... 'dial'`

- [ ] **Step 3: Implement** in `policy.py`

Imports: remove `DialLevel,`; add `ImpulseClass,` and `Warrant,` (alphabetical positions).

Add after `_apply_stability` (before `def decide`):

```python
def thresholds(sev: Severity, band_shift: float, prev: Optional[EngagementOutcome], hyst: float) -> Tuple[float, float]:
    """``(speak_t, ask_t)`` for one decision: the constants, translated together
    by the vector's band shift (presence v2 §7.5), then biased toward the
    previous outcome by hysteresis (§11.3).  Translation preserves the ask
    band's width at every level; scaling would not."""
    c = CONSTANTS
    shift = 0.0 if sev is Severity.CRITICAL else band_shift   # the CRITICAL sentinel never moves (§7.5)
    speak_t = c["SPEAK_T"][sev] + shift
    ask_t = c["ASK_T"][sev] + shift
    speak_t = speak_t - (hyst if prev in (EngagementOutcome.SPEAK, EngagementOutcome.SPEAK_MINIMAL) else 0.0) \
        + (hyst if prev in (EngagementOutcome.HOLD, EngagementOutcome.SILENT) else 0.0)
    ask_t = ask_t - (hyst if prev is EngagementOutcome.ASK_FIRST else 0.0)
    return speak_t, ask_t
```

Add directly after `_plain` (one choke point; review of 4485228, Important 3):

```python
def _tagged(ctx: AttunementContext, d: EngagementDecision, impulse: bool = True) -> EngagementDecision:
    """Every decision says the level it was made at and, when it decided an
    impulse, what kind of thing it was and how it knew (presence v2 §10).
    Appended, never prepended: ``reasons[0]`` stays the verdict.  Match the
    level as ``presence:\\d+`` — ``presence:`` also prefixes verdict keys.
    Stamped before stability, so a dwelt decision carries the level it was
    made at; a row that wants the current level reads the context.  Total,
    and all or nothing: this sits on the life-safety path, so a context too
    broken to stamp keeps its verdict rather than losing it (spec §15)."""
    try:
        tag: Tuple[str, ...] = (f"presence:{ctx.presence.level}",)
        u = ctx.utterance
        if impulse and u is not None:
            tag += (f"impulse:{u.impulse_class.value}", f"warrant:{u.warrant.value}")
        return replace(d, reasons=d.reasons + tag)
    except Exception:   # same width as the fail-quiet handlers beside it (spec §15)
        return d
```

In `decide()`, stamp every exit *before* stability, so a dwelt decision keeps the tag it was made with instead of gaining a second:

```python
    if u.life_safety:
        d = _tagged(ctx, _plain(ctx, EngagementOutcome.SPEAK, ("life_safety_bypass",), value=10.0))
        ctx.decision = d
        return d

    try:
        d = _decide_inner(ctx)
    except Exception:  # fail quiet on inference (spec §15)
        d = _hold(ctx, ("policy_error",), ResumeCondition.ON_USER_TURN, None)
    d = _apply_stability(ctx, _tagged(ctx, d))
```

and in `assess_presence()` the line `d = _apply_stability(ctx, d)` becomes `d = _apply_stability(ctx, _tagged(ctx, d, impulse=False))` — a presence assessment decided no impulse, so it carries the level alone even when the context happens to hold an utterance. Drop the dead `c = CONSTANTS` / `cfg = ctx.config` locals at the top of `decide()` and the unused `SubjectConfidence` import if `grep` confirms it unused.

In `_decide_inner`, replace

```python
    dial = ctx.dial.level_for(u.category)
    if dial is DialLevel.OFF:
        return _plain(ctx, EngagementOutcome.SILENT, ("dial:off",) + claim)
```

with

```python
    pv = ctx.presence
    # 0. Admission (presence v2 §10).
    #    LIFE_SAFETY returned above; CRITICAL is always in the set (C-10).
    if u.impulse_class not in pv.admits:
        return _plain(ctx, EngagementOutcome.SILENT, ("presence:not_admitted",) + claim)
```

Delete the two dial branches in step 2:

```python
    if dial is DialLevel.QUIET and not critical:
        if u.channel_class is ChannelClass.AMBIENT:
            return _plain(ctx, EngagementOutcome.SPEAK_MINIMAL, ("dial:quiet", "ambient:no_escalation") + auth)
        return _hold(ctx, ("dial:quiet",) + auth, ResumeCondition.ON_USER_TURN, None)
    # A ruling was bidden in advance: the balanced dial's rule against
    # unbidden trivia does not describe it.
    if dial is DialLevel.BALANCED and sev is Severity.INFO and not (u.anchored or u.user_requested or ruling):
        return _plain(ctx, EngagementOutcome.SILENT, ("dial:balanced:unanchored_info",))
```

Replace the daily-cap check

```python
        if ctx.proactive_count_today >= att.max_proactive_per_day:
            return _hold(ctx, ("attachment:daily_cap",) + auth, ResumeCondition.ON_USER_TURN, None)
```

with

```python
        # The config's ceiling binds a vector it did not resolve: the two
        # coincide when the consumer resolved under this same AttachmentSafety
        # and differ when the vector came from elsewhere or was built by hand.
        # Both keys ride so nothing that read the old one goes blind (D3).
        if ctx.proactive_count_today >= min(pv.budget_per_day, att.max_proactive_per_day):
            return _hold(ctx, ("presence:budget_exhausted", "attachment:daily_cap") + auth, ResumeCondition.ON_USER_TURN, None)
```

Replace the hysteresis block

```python
    hyst = cfg.stability.threshold_hysteresis
    prev = ctx.previous_decision.outcome if ctx.previous_decision is not None else None
    speak_t = c["SPEAK_T"][sev] - (hyst if prev in (EngagementOutcome.SPEAK, EngagementOutcome.SPEAK_MINIMAL) else 0.0) \
        + (hyst if prev in (EngagementOutcome.HOLD, EngagementOutcome.SILENT) else 0.0)
    ask_t = c["ASK_T"][sev] - (hyst if prev is EngagementOutcome.ASK_FIRST else 0.0)
```

with

```python
    hyst = cfg.stability.threshold_hysteresis
    prev = ctx.previous_decision.outcome if ctx.previous_decision is not None else None
    speak_t, ask_t = thresholds(sev, pv.band_shift, prev, hyst)
```

Remove from `base_reasons` the element `f"dial:{dial.value}"`, i.e.

```python
    base_reasons: Tuple[str, ...] = (f"receptivity:{r.level.value}" + (f":{r.reasons[0]}" if r.reasons else ""),
                                     f"severity:{sev.value}") + escalated + auth
```

In `assess_presence`, replace

```python
        if ctx.dial.level is DialLevel.OFF:
            d = _plain(ctx, EngagementOutcome.SILENT, ("dial:off",))
```

with

```python
        if ctx.presence.presence_signal is ChannelClass.PULL:
            d = _plain(ctx, EngagementOutcome.SILENT, ("presence:signal:pull",))
```

Export `thresholds`: add it to the module docstring's bullet list and to `__all__` (after `"best_resume"`).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_policy.py src/haloysius/attunement/tests/test_authority.py src/haloysius/attunement/tests/test_presence.py -q`
Expected: all pass. If `level_one_admits_a_warning_but_the_band_is_high` returns SILENT rather than HOLD: value = 0.60 + W_INVITE[MINIMAL] −0.20 = 0.40 ≥ HOLD_WORTH_T[warning] 0.30 → HOLD is expected; check `invitation=InvitationLevel.MINIMAL` was passed.

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/policy.py src/haloysius/attunement/tests/test_policy.py src/haloysius/attunement/tests/test_authority.py
git commit -m "attunement: the policy admits by impulse class and translates the band

Step 0 is admission against the vector; dial:off, dial:quiet and the
balanced unanchored-info rule are gone, their intent carried by the curve.
ASK_T and SPEAK_T move together by the vector's band shift, so ASK_FIRST
stays reachable at every level (F3). Budget reads from the vector and
emits both its own key and attachment:daily_cap. Every decision carries
presence:<level>, impulse:<class>, warrant:<warrant>."
```

---

### Task 8: Ledger and turn take a `PresenceVector`

**Files:**
- Modify: `attunement/ledger.py` (imports lines 48, 56–57; `invitation()` line 624; `apply()` line 656–669; lines 765 and 780)
- Modify: `attunement/turn.py` (import line 30; parameter line 65; line 78; the `ledger.apply(...)` call at 98; the `ledger.invitation(...)` call at 106)
- Modify: `tests/test_ledger.py` (imports; lines 118–153)

- [ ] **Step 1: Rewrite the failing tests** — in `test_ledger.py` replace the imports `DialLevel,` / `ProactivityDial,` with `AttachmentSafety,` (in the single `from haloysius.attunement.types import (...)` block — never a second block from `types`; `PresenceVector` itself is not needed) and add after it:

```python
from haloysius.attunement.presence import DEFAULT_CURVE, resolve_presence

P3 = resolve_presence(3, DEFAULT_CURVE, AttachmentSafety())
P1 = resolve_presence(1, DEFAULT_CURVE, AttachmentSafety())
```

Then in the four tests:
- every `ProactivityDial()` argument → `P3`
- `quiet = ProactivityDial(level=DialLevel.QUIET)` → `quiet = P1`; the two lines using `quiet` keep their shape (`dial=quiet` → `presence=quiet`; `L2.invitation("primary", iso(T0), quiet)` unchanged positionally)
- the test name `test_invite_raises_invitation_once_per_day_and_never_past_dial` → `..._never_past_the_ceiling`
- two hand-built decisions further down use dial reason strings as arbitrary data (`reasons=("dial:balanced",)` near line 220, `reasons=("dial:off",)` near line 237): `"dial:balanced"` → `"margin:speak"`, `"dial:off"` → `"presence:not_admitted"` — the keys the policy actually emits, so a reader of the ledger tests sees real vocabulary
- `..._never_past_the_ceiling` must exercise the apply-side cap, not the read-side clamp (review of 685f20f, Important 1): after the `L2.apply(... presence=quiet)` line add `assert L2.state("primary").last_invite_raise_at is None   # refused at apply, not clamped on read`
- decay toward a *non-NORMAL* target is otherwise unobservable — every `DEFAULT_CURVE` rung with target < ceiling has target NORMAL (Important 2). Add, in the shape of `test_invitation_decays_toward_default_with_half_life` (same ledger construction and half-life; `replace` from `dataclasses`):

```python
def test_invitation_decays_toward_the_vectors_target_not_a_constant():
    PM = replace(P3, invitation_target=InvitationLevel.MINIMAL)   # target MINIMAL, ceiling CHATTY
    L = <the same ledger construction the decay test uses, half-life 7 days>
    L.apply(Directive(DirectiveKind.INVITE), "primary", DirectiveContext(), iso(T0), presence=P3)   # persisted CHATTY
    assert L.invitation("primary", iso(T0 + timedelta(days=7)), PM) is InvitationLevel.NORMAL    # two steps above target → one
    assert L.invitation("primary", iso(T0 + timedelta(days=21)), PM) is InvitationLevel.MINIMAL  # → the target (14 d is a round-half tie; 21 d is 0.25 → 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m pytest src/haloysius/attunement/tests/test_ledger.py src/haloysius/attunement/tests/test_turn.py -q`
Expected: 4 FAIL — `ValueError: 3 is not a valid DialLevel`: the old `invitation()`/`apply()` still call `invitation_for_dial(dial.level)` and a vector's `level` is an int (`ledger.py` itself still imports `ProactivityDial`, so there is no ImportError yet)

- [ ] **Step 3: Implement**

`ledger.py` imports: remove `ProactivityDial,`, `invitation_ceiling_for_dial,`, `invitation_for_dial,`; add `PresenceVector,`. Add after the types import block:

```python
from .presence import default_presence
```

`invitation()`:

```python
    def invitation(self, subject_id: str, now: str, presence: Optional[PresenceVector] = None) -> InvitationLevel:
        """The current invitation level, decayed toward the vector's target.

        The persisted ``invitation`` is the level *set* at
        ``invitation_updated_at``; the decayed value is computed on read and
        never persisted, so the curve does not restart on every read.
        """
        presence = presence or default_presence()
        base = presence.invitation_target
        ceiling = presence.invitation_ceiling
```

(the body below `ceiling = …` is unchanged.)

`apply()` signature and first lines:

```python
    def apply(
        self,
        directive: Directive,
        subject_id: str,
        ctx: Optional[DirectiveContext],
        now: str,
        presence: Optional[PresenceVector] = None,
    ) -> AppliedDirective:
        ctx = ctx or DirectiveContext()
        presence = presence or default_presence()
        now_dt = _now_dt(now)
        kind = directive.kind
        invitation_before = self.invitation(subject_id, now, presence)
```

Line 765: `ceiling = invitation_ceiling_for_dial(dial.level)` → `ceiling = presence.invitation_ceiling`. Line 780: `invitation_after=self.invitation(subject_id, now, dial)` → `invitation_after=self.invitation(subject_id, now, presence)`. The `invitation()` docstring's "decayed toward the dial's default" and the three comments in its body ("the dial's default", "the dial's ceiling", "offset from the dial default") say "the vector's target" / "the vector's ceiling" / "offset from the vector's target".

`turn.py`: import `PresenceVector,` instead of `ProactivityDial,`; parameter `dial: Optional[ProactivityDial] = None,` → `presence: Optional[PresenceVector] = None,`; `dial = dial or ProactivityDial()` → `presence = presence or default_presence()` with `from .presence import default_presence` added to the imports; `ledger.apply(directive, subject_id, ctx, now, dial)` → `ledger.apply(directive, subject_id, ctx, now, presence)`; line 106 `ledger.invitation(subject_id, now, dial)` → `ledger.invitation(subject_id, now, presence)`. After the edit `grep -n 'dial' src/haloysius/attunement/ledger.py src/haloysius/attunement/turn.py` must show no identifier (prose only, if any — report it).

- [ ] **Step 4: Run** the two test files. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/ledger.py src/haloysius/attunement/turn.py src/haloysius/attunement/tests/test_ledger.py
git commit -m "attunement: the ledger decays toward the vector's invitation target and caps at its ceiling"
```

---

### Task 9: Conformance — schema, four vectors rewritten, `presence.json`, `check_presence`

**Files:**
- Modify: `attunement/conformance.py` (imports; `build_context` lines 127, 139; add `check_presence`, `presence_vectors`)
- Modify: `attunement/testing/vectors/policy.json`
- Create: `attunement/testing/vectors/presence.json` (generated)
- Create: `attunement/testing/gen_presence_vectors.py`
- Modify: `attunement/testing/__init__.py` (`__all__`)
- Modify: `tests/test_conformance.py` (lines 76, 85, 117) and add tests

- [ ] **Step 1: Write the failing tests** — append to `test_conformance.py`:

```python
from haloysius.attunement.conformance import PRESENCE_VECTORS_PATH, check_presence, presence_vectors
from haloysius.attunement.presence import DEFAULT_CURVE, resolve_presence
from haloysius.attunement.types import AttachmentSafety, ImpulseClass


def test_the_engine_resolution_passes_its_own_presence_vectors():
    assert check_presence(lambda level, overrides: resolve_presence(level, DEFAULT_CURVE, AttachmentSafety(), overrides)) == []


def test_presence_vectors_cover_every_level_and_class():
    v = presence_vectors()
    base = [x for x in v["vectors"] if not x.get("presence_overrides")]
    assert len(base) == 11 * len(ImpulseClass)
    assert {(x["level"], x["impulse_class"]) for x in base} == {(l, c.value) for l in range(11) for c in ImpulseClass}
    assert {x["id"] for x in v["vectors"] if x.get("presence_overrides")} == {
        "level-0-warning-override-warning-3", "level-0-subject_linked-override-subject_linked-4",
        "level-10-spontaneous-override-spontaneous-3", "level-0-scheduled-override-warning-3"}


def test_the_committed_presence_vectors_are_the_generator_output():
    from haloysius.attunement.testing.gen_presence_vectors import build
    assert json.loads(PRESENCE_VECTORS_PATH.read_text(encoding="utf-8")) == build(DEFAULT_CURVE), \
        "regenerate: PYTHONPATH=src .venv/bin/python -m haloysius.attunement.testing.gen_presence_vectors"


def test_a_resolution_that_admits_everything_is_caught():
    def loose(level, overrides):
        real = resolve_presence(level, DEFAULT_CURVE, AttachmentSafety(), overrides)
        return replace(real, admits=frozenset(ImpulseClass), channel={c: real.channel.get(c, real.presence_signal) for c in ImpulseClass})
    assert any("spontaneous" in f for f in check_presence(loose))


def test_a_resolution_that_pushes_the_ambient_rung_is_caught():
    def loud(level, overrides):
        real = resolve_presence(level, DEFAULT_CURVE, AttachmentSafety(), overrides)
        return replace(real, channel={c: ChannelClass.PUSH for c in real.channel})
    assert any("subject_linked" in f and "channel" in f for f in check_presence(loud))


def test_a_resolution_that_never_waits_is_caught():
    v = presence_vectors()
    assert all("patience_s" in x for x in v["vectors"])
    def hasty(level, overrides):
        return replace(resolve_presence(level, DEFAULT_CURVE, AttachmentSafety(), overrides), patience_s=0.0)
    assert any("patience_s" in f for f in check_presence(hasty))
```

(Spec §18's other conformance vectors — form follows warrant, offer never rescue, close with a plan, consistency across levels — are about *rendering*, which slice 1 does not touch; they belong to the slice that renders.)

Add `ChannelClass,` to the `from haloysius.attunement.types import (` block at the top of `test_conformance.py`.

Update the three existing assertions:
- line 76: `("dial:off",)` → `("presence:not_admitted",)`
- line 85: `"off-dial-is-silent"` → `"mute-does-not-admit-a-warning"`
- line 117: `"a-ruling-silenced-by-the-dial-is-still-legible-as-a-ruling"` → `"a-ruling-not-admitted-at-mute-is-still-legible-as-a-ruling"`
- any assertion naming `"an-unanchored-info-is-dropped-at-the-default-dial"` → `"an-unanchored-info-falls-silent-on-the-margin"` (grep the file; there may be none)

After Step 3, `grep -n dial src/haloysius/attunement/testing/vectors/policy.json` must print nothing: the JSON is not swept by Task 10's `*.py` grep, so every mention — keys, ids, reason strings, prose in `why` — goes here.

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `ImportError: cannot import name 'PRESENCE_VECTORS_PATH'` (the first missing name in the import tuple)

- [ ] **Step 3: Rewrite the four vectors in `policy.json`**

Open `src/haloysius/attunement/testing/vectors/policy.json`. In `context_schema`, replace the `"dial"` and `"overrides"` entries with:

```json
    "presence": "presence level 0..10, default 3 (resolved through the engine's DEFAULT_CURVE under AttachmentSafety())",
    "presence_overrides": "impulse class -> presence level; that class resolves alone at that level and the budget lifts to its rung's"
```

In `vocabulary`, replace the `"dial"` entry with:

```json
    "impulse_class": ["life_safety", "critical", "warning", "scheduled", "recurrence", "subject_linked", "open_loop", "association", "affect_state", "affect_social", "absence", "spontaneous"],
    "warrant": ["introspected", "observed", "told", "inferred"]
```

Replace the four vectors:

`life-safety-bypasses-everything`: `"dial": "off"` → `"presence": 0`; in its `why`, "an off dial and a silent invitation" → "the mute level and a silent invitation".

`an-unanchored-info-is-dropped-at-the-default-dial` (near the end of the policy vectors; it required `dial:balanced:unanchored_info`, a reason the policy no longer emits) →
```json
{
  "id": "an-unanchored-info-falls-silent-on-the-margin",
  "class": "policy",
  "utterance": {"severity": "info"},
  "invitation": "normal",
  "relationship": "established",
  "expect": {"outcome": "silent", "require_reasons": ["margin:silent", "impulse:warning"], "forbid_reasons": ["presence:not_admitted"]},
  "why": "Proactive speech is anchored or it is filler. The old balanced-level rule against unbidden trivia retired along with it (DECISIONS row 1): an unanchored info is admitted at level 3 and falls silent on the margin, value 0.30 against cost 0.40. The second positive control: this must be silent while the anchored warning above is not."
}
```

`a-ruling-silenced-by-the-dial-is-still-legible-as-a-ruling` → 
```json
{
  "id": "a-ruling-not-admitted-at-mute-is-still-legible-as-a-ruling",
  "class": "policy",
  "utterance": {"authority": true, "authority_rule": "format.time_limit", "impulse_class": "warning"},
  "presence": 0,
  "expect": {"require_reasons": ["authority", "presence:not_admitted"]},
  "why": "A moderator's ruling that the mute level does not admit must still say it was a ruling, or the audit surface cannot distinguish a suppressed ruling from a suppressed gift."
}
```

`off-dial-is-silent` →
```json
{
  "id": "mute-does-not-admit-a-warning",
  "class": "policy",
  "utterance": {"severity": "warning", "anchored": true, "impulse_class": "warning"},
  "presence": 0,
  "invitation": "normal",
  "expect": {"outcome": "silent", "require_reasons": ["presence:not_admitted", "impulse:warning"]},
  "why": "Level 0 is soft mute: a warning is not admitted and stays findable on a pull surface. If this vector fails the mute level leaks warnings."
},
{
  "id": "mute-still-speaks-a-critical",
  "class": "policy",
  "utterance": {"severity": "critical", "impulse_class": "critical"},
  "presence": 0,
  "invitation": "silent",
  "relationship": "established",
  "expect": {"outcome": "speak", "require_reasons": ["margin:speak"], "forbid_reasons": ["invitation:silent", "presence:budget_exhausted", "life_safety_bypass"]},
  "why": "Hard off is not on the slider (v2 §3.1). A critical at level 0 speaks, on its margin, through the silent invitation. If this fails, soft mute has become off."
}
```

`a-category-override-is-a-substitution-not-a-floor` →
```json
{
  "id": "a-class-override-admits-and-funds-one-class",
  "class": "policy",
  "utterance": {"severity": "warning", "anchored": true, "time_sensitive": true, "impulse_class": "warning"},
  "presence": 0,
  "presence_overrides": {"warning": 3},
  "relationship": "established",
  "expect": {"outcome": "speak", "forbid_reasons": ["presence:not_admitted", "presence:budget_exhausted"]},
  "why": "An override resolves one class at its own level, funds it (the budget lifts to its rung's) and may be more permissive than the global level (A-HB-13). Admission is the override's; the band is still the base level's, so the utterance is time-sensitive to clear it."
}
```

- [ ] **Step 4: Implement in `conformance.py`**

Imports: remove `DialLevel,` and `ProactivityDial,`; add `AttachmentSafety,` and `ImpulseClass,`. Add `from .presence import DEFAULT_CURVE, resolve_presence`.

Replace in `build_context`:

```python
    overrides = {k: DialLevel(v) for k, v in (vector.get("overrides") or {}).items()}
```
→
```python
    overrides = dict(vector.get("presence_overrides") or {})   # the resolver coerces keys and levels; no int() here, or "presence": true resolves to 1
```
and
```python
        dial=ProactivityDial(level=DialLevel(vector.get("dial", "balanced")), overrides=overrides),
```
→
```python
        presence=resolve_presence(vector.get("presence", 3), DEFAULT_CURVE, AttachmentSafety(), overrides),
```

(`Utterance` coerces `impulse_class`/`warrant` value strings itself via `coerce_enum`, so `build_context` passes a vector's `"impulse_class": "warning"` through untouched — no conversion line.)

Append to `conformance.py`:

```python
PRESENCE_VECTORS_PATH = Path(__file__).resolve().parent / "testing" / "vectors" / "presence.json"


def presence_vectors() -> Dict[str, Any]:
    """The shared resolution vectors, as data (``testing/vectors/presence.json``)."""
    return json.loads(PRESENCE_VECTORS_PATH.read_text(encoding="utf-8"))


def check_presence(resolve_fn: Callable[[int, Dict[ImpulseClass, int]], Any]) -> List[str]:
    """Run the resolution vectors against ``resolve_fn(level, overrides)``.

    One vector per (level, class): admitted or not, the channel ceiling when
    admitted, and the level's ``patience_s`` (spec §18); then override rows.
    The vector ``resolve_fn`` returns needs only ``.admits`` supporting
    ``in`` against an ``ImpulseClass`` or its value string, ``.channel[cls]``
    yielding a member with ``.value`` or the string itself, and
    ``.patience_s`` (a number or ``None``).  Generated from ``DEFAULT_CURVE`` by
    ``testing/gen_presence_vectors.py`` and committed as data, so a
    consumer in another language proves the same table.
    """
    failures: List[str] = []
    for v in presence_vectors()["vectors"]:
        vid = v["id"]
        overrides = {ImpulseClass(k): int(x) for k, x in (v.get("presence_overrides") or {}).items()}
        try:
            vec = resolve_fn(int(v["level"]), overrides)
        except Exception as exc:
            failures.append(f"{vid}: raised {type(exc).__name__}: {exc}")
            continue
        cls = ImpulseClass(v["impulse_class"])
        admitted = cls in vec.admits
        if admitted != bool(v["admitted"]):
            failures.append(f"{vid}: {cls.value} admitted={admitted}, expected {v['admitted']}")
            continue
        want_p, got_p = v.get("patience_s"), getattr(vec, "patience_s", None)
        try:
            mismatch = (want_p is None) != (got_p is None) or (want_p is not None and not (abs(float(got_p) - float(want_p)) <= 1e-6))   # NaN fails, as it should
        except (TypeError, ValueError):   # a consumer's non-numeric patience is that row's failure, not an escape
            mismatch = True
        if mismatch:
            failures.append(f"{vid}: patience_s={got_p!r}, expected {want_p!r}")
        if admitted:
            got = getattr(vec.channel[cls], "value", vec.channel[cls])
            if got != v["channel"]:
                failures.append(f"{vid}: {cls.value} channel={got!r}, expected {v['channel']!r}")
    return failures
```

Update `__all__` in `conformance.py`: add `"check_presence", "presence_vectors", "PRESENCE_VECTORS_PATH"`.

Create `src/haloysius/attunement/testing/gen_presence_vectors.py`:

```python
"""Regenerate ``vectors/presence.json`` from ``DEFAULT_CURVE``.

Run after any change to the engine curve, from the repository root::

    PYTHONPATH=src .venv/bin/python -m haloysius.attunement.testing.gen_presence_vectors

``OUT`` resolves beside this file — right for a source tree, wrong for an
installed wheel; regenerate from a checkout.  ``build`` is separate from
``main`` so a test can hold the committed file to the generator's output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..presence import DEFAULT_CURVE, resolve_presence
from ..types import AttachmentSafety, ImpulseClass, PresenceCurve

OUT = Path(__file__).resolve().parent / "vectors" / "presence.json"


def build(curve: PresenceCurve) -> Dict[str, Any]:
    """The resolution table for one curve: every (level, class), then the
    override rows that prove an override resolves at *its* rung, and that
    class alone."""
    safety = AttachmentSafety()

    def row(level: int, cls: ImpulseClass, overrides: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        vec = resolve_presence(level, curve, safety, overrides or {})
        admitted = cls in vec.admits
        out: Dict[str, Any] = {
            "id": f"level-{level}-{cls.value}" + ("-override-" + "-".join(f"{k}-{v}" for k, v in overrides.items()) if overrides else ""),
            "level": level,
            "impulse_class": cls.value,
            "admitted": admitted,
            "channel": vec.channel[cls].value if admitted else None,
            "patience_s": vec.patience_s,
        }
        if overrides:
            out["presence_overrides"] = dict(overrides)
        return out

    vectors = [row(level, cls) for level in range(11) for cls in ImpulseClass]
    vectors += [
        # The first two are a pair.  An implementation that took the class's channel from
        # presence_signal (ambient on every rung) passes the ambient row and fails the push
        # row; one that delivers every override at PUSH passes the push row and fails the
        # ambient row.  Neither row alone tells them apart.
        row(0, ImpulseClass.WARNING, {"warning": 3}),                 # admitted, push: an override admits
        row(0, ImpulseClass.SUBJECT_LINKED, {"subject_linked": 4}),   # admitted, ambient: the channel is the override rung's
        row(10, ImpulseClass.SPONTANEOUS, {"spontaneous": 3}),        # not admitted: an override removes
        row(0, ImpulseClass.SCHEDULED, {"warning": 3}),               # not admitted: an override resolves that class *alone*
    ]
    return {
        "version": 1,
        "purpose": "Resolution agreement: for each level and impulse class, whether the engine's DEFAULT_CURVE admits it, at what channel ceiling, and with what patience; plus override rows.",
        "curve_owner": curve.owner,
        "vectors": vectors,
    }


def main() -> None:
    doc = build(DEFAULT_CURVE)
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(doc['vectors'])} vectors to {OUT}")


if __name__ == "__main__":
    main()
```

Run it from the worktree, never the main checkout: `PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m haloysius.attunement.testing.gen_presence_vectors`
Expected: `wrote 136 vectors to …/presence.json` (132 base rows + 4 override rows) — and the path printed must be inside the worktree.

In `testing/__init__.py`, `__all__` gains `"check_presence", "presence_vectors"` and the lazy `__getattr__` (if present) or import block re-exports them from `..conformance` the same way `check_policy` is.

- [ ] **Step 5: Run** `.venv/bin/python -m pytest src/haloysius/attunement/tests/test_conformance.py -q`
Expected: all pass, including the two mutation tests.

- [ ] **Step 6: Commit**

```bash
git add src/haloysius/attunement/conformance.py src/haloysius/attunement/testing/ src/haloysius/attunement/tests/test_conformance.py
git commit -m "attunement: conformance vectors speak presence, and a resolution table is data

Five policy vectors rewritten for the mute level, class overrides and
the retired unanchored-info rule; 136 generated resolution vectors
(11 levels x 12 classes, plus four override rows) committed as JSON so
a second consumer can prove its curve resolution matches, with mutation
tests that catch a resolution that admits everything, pushes the ambient
rung or never waits."
```

---

### Task 10: Retire `DialLevel` and `ProactivityDial`

**Files:**
- Modify: `types.py` — delete `class DialLevel` (246–252), `_DIAL_TO_INVITATION` (271–276), `_DIAL_CEILING` (284–289), `invitation_for_dial`, `invitation_ceiling_for_dial` (292–305), `class ProactivityDial` (619–633); `__all__`
- Modify: `tests/test_types.py` (lines 11, 19, 26, 61–71)
- Modify: `attunement/__init__.py`

- [ ] **Step 1: Rewrite the failing tests** — in `test_types.py` remove the `DialLevel,`, `ProactivityDial,`, `invitation_for_dial,` imports; delete `test_dial_override_is_substitution_not_floor`; replace `test_invitation_level_is_ordered_int_and_maps_from_dial` with:

```python
def test_invitation_level_is_an_ordered_int():
    assert InvitationLevel.SILENT < InvitationLevel.MINIMAL < InvitationLevel.NORMAL < InvitationLevel.CHATTY


def test_the_dial_is_gone():
    import haloysius.attunement.types as t
    for name in ("DialLevel", "ProactivityDial", "invitation_for_dial", "invitation_ceiling_for_dial"):
        assert not hasattr(t, name), name
```

and in the existing `test_package_import_exposes_contract_lazily` add, after its single-name check, `for n in pkg.__all__: getattr(pkg, n)` (adapting the module variable's name) — a name added to the package `__all__` without a `__getattr__` branch is the one drift star-import does not catch at collection time.

- [ ] **Step 2: Run** — expected FAIL on `test_the_dial_is_gone`.

- [ ] **Step 3: Delete** the six definitions listed above from `types.py`, and from `__all__` remove `"DialLevel"`, `"ProactivityDial"`, `"invitation_for_dial"`, `"invitation_ceiling_for_dial"`. Grep to confirm nothing else references them:

```bash
grep -rn "DialLevel\|ProactivityDial\|invitation_for_dial\|invitation_ceiling_for_dial\|_DIAL_" src/haloysius
```
Expected: exactly one hit — `test_the_dial_is_gone`'s own string literals in `tests/test_types.py`. Anything else is a live reference: the `types.py` module docstring names `ProactivityDial` among the wiring-time types ("the wiring-time `AttunementConfig`, `ProactivityDial` and `DirectiveContext`") → `PresenceCurve` in its place.

Then sweep the prose, which the identifier grep cannot see (review of 540ea2f, Minor 5):

```bash
grep -rniw "dial" src/haloysius/attunement --include='*.py'
```

(`-w`: `\bdial` also matches "dialogue".) Three hits are legitimate and stay: `directives.py`'s user-phrase regex (`the dial|dial to` — a person may still say "dial"), `tests/test_directives.py`'s `"set the dial to quiet"` case for it, and `tests/test_presence.py`'s `"dial" not in {f.name for f in fields(AttunementContext)}` tripwire. Everything else is reworded.

Three docstring mentions in `types.py` are known to survive Tasks 6–9 and must be reworded here, each in a phrase, without rewriting the docstring around it: the `EngagementOutcome.HOLD` docstring's list of gates that answer HOLD, "a quiet dial" → "an exhausted presence budget" (admission answers SILENT, not HOLD); the `Utterance` docstring's "subject to the dial including OFF" → "subject to the presence vector's admission"; the `EngagementDecision` docstring's reason-key example ``dial:quiet`` → ``presence:not_admitted``. `policy.py` has one: the history comment above the claim hoist ("A moderator whose dial is OFF used to yield rows…") → "A moderator's ruling that was not admitted used to yield rows…". `tests/test_authority.py` has three, all prose: the module docstring's "subject to the dial (including OFF), the daily cap" → "subject to the presence vector's admission, the daily cap"; the two comment lines ending "…rather than the balanced dial's rule against unbidden info, which sits before it" are deleted outright — with admission by class, an INFO gift reaches the new-relationship gate exactly as a WARNING does, so no sentence about severity belongs there (the `severity=Severity.WARNING` on the two calls stays, inert); the `TestASilencedRulingIsLegibleAsOne` docstring's "a moderator whose dial was turned off" → "a moderator whose presence was at mute". Any other hit is a test name or comment: reword the same way. While there: rewrap the reworded claim-hoist comment to the block's ~78-column width, and re-join `"severity_rank",` with the next line of `__all__`'s helpers group (the deletion's footprint). Expected after the sweep: no output (tests in `tests/` that name the old behaviour were already rewritten in Tasks 7–9; if one remains, rename it, do not delete it).

`attunement/__init__.py`: the `__all__` list already spreads `_types_all`; add to the explicit list `"resolve_presence", "default_presence", "DEFAULT_CURVE", "band_shift", "check_presence", "presence_vectors"` and in `__getattr__` add:

```python
    if name in ("resolve_presence", "default_presence", "DEFAULT_CURVE", "band_shift"):
        from . import presence
        return getattr(presence, name)
    if name in ("check_presence", "presence_vectors"):
        from . import conformance
        return getattr(conformance, name)
```

- [ ] **Step 4: Run the whole attunement suite**

`PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m pytest src/haloysius/attunement/tests -q` — Expected: `658 passed` (two dial-era tests out, two in). Then the whole engine, `… -m pytest src/haloysius -q` — expected all pass.

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/attunement/types.py src/haloysius/attunement/__init__.py src/haloysius/attunement/tests/test_types.py
git commit -m "attunement: retire DialLevel and ProactivityDial (DECISIONS row 1; no shim)"
```

---

### Task 11: Autonomous engine — `_NEVER_SPEAKS` becomes admission

**Files:**
- Modify: `cognition/autonomous_engine.py` (lines 583–648)
- Modify: `cognition/tests/test_autonomous_attunement.py`

- [ ] **Step 1: Rewrite the failing tests** — replace `NonSpeakableTriggersTestCase` with:

```python
class SpontaneousTriggersReachThePolicyTestCase(unittest.TestCase):
    """RANDOM, TEMPORAL and SCENE are described as SPONTANEOUS and the
    policy — admission first — decides (presence v2 §3.2, DECISIONS row 2)."""

    def test_random_temporal_and_scene_are_spontaneous_impulses(self) -> None:
        from haloysius.attunement.types import ImpulseClass
        for trigger_type in (TriggerType.RANDOM, TriggerType.TEMPORAL, TriggerType.SCENE):
            with self.subTest(trigger=trigger_type):
                seen = {}

                def decide(utterance):
                    seen["u"] = utterance
                    return _decision(EngagementOutcome.SILENT)

                engine = AutonomousCognitionEngine(persona_id="p", decide=decide)
                self.assertFalse(engine._should_speak(CognitiveTrigger(trigger_type, "spontaneous", 1.0)))
                self.assertIs(seen["u"].impulse_class, ImpulseClass.SPONTANEOUS)

    def test_a_policy_that_admits_spontaneous_lets_it_speak(self) -> None:
        engine = AutonomousCognitionEngine(persona_id="p", decide=lambda u: _decision(EngagementOutcome.SPEAK))
        self.assertTrue(engine._should_speak(CognitiveTrigger(TriggerType.RANDOM, "spontaneous", 1.0)))
```

The no-policy case belongs with the other legacy assertions: in `LegacyThresholdsTestCase.test_other_triggers_stay_internal`, extend the tuple to

```python
        for trigger_type in (
            TriggerType.WORRY,
            TriggerType.DRIVE,
            TriggerType.BELIEF,
            TriggerType.MEMORY,
            # With no policy wired, spontaneous thoughts stay internal exactly as before.
            TriggerType.RANDOM,
            TriggerType.TEMPORAL,
            TriggerType.SCENE,
        ):
```

Delete `PolicyWiredTestCase.test_a_permissive_policy_does_not_revive_a_random_thought`: its premise — a constant outranks the policy — is what DECISIONS row 2 retires, and `test_a_policy_that_admits_spontaneous_lets_it_speak` above asserts the new truth. Delete `test_worry_is_described_as_an_anchored_warning` and `test_emotional_is_described_as_unanchored_info` too — the table-driven test below is the one place that says how each trigger is described. Then add to `PolicyWiredTestCase`:

```python
    def test_every_trigger_type_is_described_once(self) -> None:
        """One row per TriggerType, no default: an unclassified trigger is a bug, not a quiet fallback."""
        from haloysius.attunement.types import ImpulseClass   # Severity is already imported at module level
        self.assertEqual(set(TriggerType), set(AutonomousCognitionEngine._DESCRIBE))
        expected = {
            TriggerType.WORRY: (Severity.WARNING, True, ImpulseClass.AFFECT_STATE),
            TriggerType.EMOTIONAL: (Severity.INFO, False, ImpulseClass.AFFECT_STATE),
            TriggerType.DRIVE: (Severity.INFO, False, ImpulseClass.AFFECT_STATE),
            TriggerType.USER_ABSENCE: (Severity.INFO, True, ImpulseClass.ABSENCE),
            TriggerType.BELIEF: (Severity.INFO, True, ImpulseClass.ASSOCIATION),
            TriggerType.MEMORY: (Severity.INFO, True, ImpulseClass.ASSOCIATION),
            TriggerType.RANDOM: (Severity.INFO, False, ImpulseClass.SPONTANEOUS),
            TriggerType.TEMPORAL: (Severity.INFO, False, ImpulseClass.SPONTANEOUS),
            TriggerType.SCENE: (Severity.INFO, False, ImpulseClass.SPONTANEOUS),
        }
        for t, (sev, anchored, cls) in expected.items():
            seen = {}

            def decide(utterance):
                seen["u"] = utterance
                return _decision(EngagementOutcome.SILENT)

            AutonomousCognitionEngine(persona_id="p", decide=decide)._should_speak(CognitiveTrigger(t, "x", 1.0))
            u = seen["u"]
            self.assertEqual(u.source, "autonomous_thought")   # what an audit surface keys on
            self.assertEqual((u.severity, u.anchored, u.impulse_class), (sev, anchored, cls), t)

    def test_admission_is_the_policys_call_at_the_real_curve(self) -> None:
        """Classification moves a worry's admission from rung 1 (derived WARNING) to rung 8
        (affect_state): at the default level it is not admitted; at 8 it is (spec §14, C-5)."""
        from haloysius.attunement.policy import decide
        from haloysius.attunement.presence import DEFAULT_CURVE, resolve_presence
        from haloysius.attunement.types import AttachmentSafety, AttunementContext

        captured = {}

        def spy(utterance):
            captured["u"] = utterance
            return _decision(EngagementOutcome.SILENT)

        AutonomousCognitionEngine(persona_id="p", decide=spy)._should_speak(CognitiveTrigger(TriggerType.WORRY, "intrusion", 0.8))

        def at(level):
            return decide(AttunementContext(
                persona_id="p", now="2026-09-17T12:00:00+00:00", utterance=captured["u"],
                presence=resolve_presence(level, DEFAULT_CURVE, AttachmentSafety()),
                sessions_count=10, relationship_age_days=30.0, accepted_interactions=10))

        self.assertEqual(at(3).reasons[0], "presence:not_admitted")
        self.assertNotEqual(at(8).reasons[0], "presence:not_admitted")
```

- [ ] **Step 2: Run** (from the engine worktree, never the main checkout) `PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m pytest src/haloysius/cognition/tests/test_autonomous_attunement.py -q` — Expected: FAIL.

- [ ] **Step 3: Implement** — in `autonomous_engine.py` replace *both* class-level tables — the `_SPEAKABLE` block (the comment and the dict, ~lines 583–592) and the `_NEVER_SPEAKS` block (the comment and the tuple, ~594–599) — with one table (review of 45b5037: two tables left `_SPEAKABLE`'s `.get` default silently describing three triggers):

```python
    # How each trigger is described to the attunement policy (presence v2
    # §14): (severity, anchored, impulse class).  Held as string values so
    # importing this module never pulls in the attunement package.  Every
    # TriggerType has a row and the lookup is a plain index: an unclassified
    # trigger is a bug, not a quiet default.  RANDOM / TEMPORAL / SCENE reach
    # the policy as SPONTANEOUS; admission at the top rung — under budget,
    # bounded deferral and the consumer's ceilings — is the policy's call,
    # not a constant's (DECISIONS row 2).  Classification moves admission:
    # before it every thought derived to WARNING and was admitted from rung 1
    # of the engine curve; now affect_state and association are first
    # admitted at rung 8 and absence at rung 6 (C-5).
    _DESCRIBE: Dict[TriggerType, Tuple[str, bool, str]] = {
        TriggerType.WORRY: ("warning", True, "affect_state"),
        TriggerType.EMOTIONAL: ("info", False, "affect_state"),
        TriggerType.DRIVE: ("info", False, "affect_state"),
        TriggerType.USER_ABSENCE: ("info", True, "absence"),
        TriggerType.BELIEF: ("info", True, "association"),
        TriggerType.MEMORY: ("info", True, "association"),
        TriggerType.RANDOM: ("info", False, "spontaneous"),
        TriggerType.TEMPORAL: ("info", False, "spontaneous"),
        TriggerType.SCENE: ("info", False, "spontaneous"),
    }
```

In `_should_speak`, delete the `if trigger.trigger_type in self._NEVER_SPEAKS: return False` lines; the `if self.decide is None:` branch keeps its two threshold checks and final `return False` unchanged (that `return False` is what keeps spontaneous thoughts internal with no policy — say so in its comment: "A consumer that wires nothing sees exactly the behaviour it had before: a long absence or a very intense emotion speaks; every other thought, spontaneous ones included, stays internal."). Replace

```python
        severity, anchored = self._SPEAKABLE.get(
            trigger.trigger_type, ("info", False)
        )
```

with

```python
        severity, anchored, impulse_class = self._DESCRIBE[trigger.trigger_type]
```

and the `from haloysius.attunement.types import (...)` inside `_should_speak` gains `ImpulseClass,`; the `Utterance(...)` call gains:

```python
                impulse_class=ImpulseClass(impulse_class),
```

`grep -n '_SPEAKABLE\|_NEVER_SPEAKS\|_IMPULSE_CLASS' src/haloysius` must print nothing.

The test module's own top docstring says RANDOM/TEMPORAL/SCENE "do not reach the policy at all" — reword that bullet to the new behaviour (they reach it as SPONTANEOUS; the policy admits or not); its citations of "spec rev 2 §11.1" / "Task 13 of the Phase B wiring plan" gain a pointer to the slice-1 plan; `_should_speak`'s docstring likewise if it says spontaneous thoughts never reach the policy.

- [ ] **Step 4: Run** the cognition test file and the whole engine suite:
`PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m pytest src/haloysius -q` — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/haloysius/cognition/autonomous_engine.py src/haloysius/cognition/tests/test_autonomous_attunement.py
git commit -m "cognition: spontaneous thoughts reach the policy as SPONTANEOUS impulses

_NEVER_SPEAKS was a constant standing where an admission decision
belongs. Each trigger type is described to the policy in one table —
severity, anchored, impulse class — and the policy admits by class
against the vector; a consumer with no policy wired keeps the legacy
behaviour exactly. Classification moves admission: the six thoughts
that derived to WARNING (rung 1) are affect_state / association (rung
8) and absence (rung 6) now."
```

---

### Task 12: Engine suite green; push the branch

- [ ] **Step 1:** from the engine worktree: `PYTHONPATH=$PWD/src /Volumes/4TB-BAD/Haloysius/.venv/bin/python -m pytest src/haloysius -q`
Expected: `passed`, no failures. Note the count.

- [ ] **Step 2: Place the presence spec in this repository** so the pointer added to `types.py`'s header in Task 2 resolves:

```bash
cp /Volumes/4TB-BAD/Halbert/documentation/superpowers/specs/2026-09-16-presence-slider-design.md docs/superpowers/specs/2026-09-16-presence-slider-design.md
git add docs/superpowers/specs/2026-09-16-presence-slider-design.md
git commit -m "docs: the presence slider spec (v2), the contract types.py now cites"
```

- [ ] **Step 3:** Update `CHANGELOG.md`. Its unreleased entries are topic-headed H2s (`## Unreleased — content policy leaves the core`), so presence gets its own, inserted directly above the existing unreleased H2:

```markdown
## Unreleased — the presence vector

The four-position dial becomes a resolved vector: a level 0–10 through a
consumer-authored curve, admission by impulse class, a band shift that
translates the ask band, a funded budget, and a stamp on every decision.
Spec: `docs/superpowers/specs/2026-09-16-presence-slider-design.md` (v2).

### Added — presence (2026-09-16)
- `attunement.ImpulseClass`, `Warrant`, `PresenceVector`, `PresenceRung`, `PresenceCurve`; `attunement.presence.resolve_presence`, `band_shift`, `DEFAULT_CURVE`; `conformance.check_presence` with 136 generated resolution vectors.
- `Utterance.impulse_class`, `.warrant`, `.source_ref`; `ResumeCondition.ON_BREAKPOINT`.
- Every decision carries `presence:<level>`, `impulse:<class>`, `warrant:<warrant>`; new keys `presence:not_admitted`, `presence:budget_exhausted`, `presence:signal:pull`.

### Removed
- `DialLevel`, `ProactivityDial`, `invitation_for_dial`, `invitation_ceiling_for_dial`. `AttunementContext.dial` → `.presence`; `StandingRequestLedger.invitation`/`.apply` and `begin_turn` take `presence=`.
- `autonomous_engine._NEVER_SPEAKS`: spontaneous triggers reach the policy as `SPONTANEOUS`.
```

- [ ] **Step 4: Commit and push**

```bash
git add CHANGELOG.md
git commit -m "changelog: presence contract (slice 1)"
git push -u origin feat/presence-vector
```

The Halbert side installs the engine from this branch (Task 13).

---

# Part B — Halbert (shadow only)

### Task 13: Branch, and point the venv at the engine branch

- [ ] **Step 1: The branch already exists** — the Halbert worktree `~/.config/superpowers/worktrees/Halbert/presence-slice-1` is on `feat/presence-slice-1` (from `main` at `1b091ac3`). Never branch, check out or edit in `/Volumes/4TB-BAD/Halbert` itself: another session's uncommitted marketing edits live there. Confirm:

```bash
git -C ~/.config/superpowers/worktrees/Halbert/presence-slice-1 status --short --branch | head -3
```
Expected: `## feat/presence-slice-1` and a clean tree.

- [ ] **Step 2: Point Halbert at the engine worktree (no install; a path prefix)**

Halbert's venv resolves `haloysius` to the MAIN engine checkout via a `.pth` entry. The engine branch lives in a worktree, so every Halbert command in Tasks 13–23 carries `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src`. Verify it reaches through `wt_pytest.py`'s re-exec:

```bash
cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1
PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -c "import haloysius,os;print(os.path.dirname(haloysius.__file__))"
```
Expected: a path under `…/worktrees/Haloysius/presence-vector/src`. Nothing is pip-installed.

- [ ] **Step 3: Verify the new contract is importable from Halbert's venv** (same prefix; every Halbert command from here on carries it)

```bash
PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -c "from haloysius.attunement.presence import resolve_presence, DEFAULT_CURVE; from haloysius.attunement.types import ImpulseClass, PresenceVector; print('ok', len(DEFAULT_CURVE.rungs))"
```
Expected: `ok 7`

- [ ] **Step 4: Baseline the Halbert suite** (`main` is not green; know the number before you change anything). From the worktree, always through `./wt_pytest.py` with the venv interpreter — bare pytest in a worktree tests the main tree:

```bash
PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests -q --co | tail -1
PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_attunement_shadow_decide.py halbert_core/tests/test_proactive_gate.py halbert_core/tests/test_being_config.py -q
```
Expected on the second command: `test_attunement_shadow_decide.py` now **fails** (`dial_for` imports the retired `DialLevel`) — that is the work of Task 17; the other two pass.

Baseline measured 2026-09-17 at `1b091ac3` with the engine branch at `66afc4b`: `9651 collected`; three-file run `5 failed, 77 passed` (all five in `test_attunement_shadow_decide.py`, cause `AttunementContext.__init__() got an unexpected keyword argument 'dial'`); whole suite `58 failed, 9569 passed, 18 skipped, 6 xfailed, 1 error in 341.69s`. Task 23 compares against these numbers: the only permitted change is new passes.

---

### Task 14: `BeingConfig.presence` and `presence_overrides`

**Files:**
- Modify: `halbert_core/halbert_core/config/being_config.py` (constants ~line 35; fields ~line 213–222; `validate()` ~line 326–341)
- Test: `halbert_core/tests/test_being_config.py`

- [ ] **Step 1: Write the failing tests** (append to `test_being_config.py`)

```python
class TestPresence:
    def test_default_is_three(self):
        cfg = BeingConfig()
        assert cfg.presence == 3 and cfg.presence_overrides == {}

    def test_old_dial_fields_still_exist_in_slice_one(self):
        # D1: the live gate still reads these; retirement is slice 2.
        cfg = BeingConfig()
        assert cfg.proactivity == "balanced"

    @pytest.mark.parametrize("bad", [-1, 11, "3", True, 3.5])
    def test_presence_must_be_an_int_in_range(self, bad):
        with pytest.raises(ValueError, match="presence must be an integer 0..10"):
            BeingConfig(presence=bad).validate()

    def test_overrides_are_keyed_by_impulse_class(self):
        BeingConfig(presence_overrides={"warning": 5, "association": 9}).validate()
        with pytest.raises(ValueError, match="Unknown impulse class"):
            BeingConfig(presence_overrides={"security": 5}).validate()
        with pytest.raises(ValueError, match=r"0\.\.10"):
            BeingConfig(presence_overrides={"warning": 12}).validate()

    def test_life_safety_and_critical_reject_overrides(self):
        # match= so this cannot pass through the unknown-class branch if a name were dropped
        for cls in ("life_safety", "critical"):
            with pytest.raises(ValueError, match="C-10"):
                BeingConfig(presence_overrides={cls: 0}).validate()

    def test_a_null_overrides_map_on_disk_loads_as_empty(self):
        cfg = BeingConfig.from_dict({"presence_overrides": None})
        assert cfg.presence_overrides == {}

    def test_round_trips_through_dict(self):
        cfg = BeingConfig(presence=6, presence_overrides={"subject_linked": 8})
        back = BeingConfig.from_dict(cfg.to_dict())
        assert back.presence == 6 and back.presence_overrides == {"subject_linked": 8}
```

And in `halbert_core/tests/test_attunement_engine_sync.py` — the file that exists to keep every local mirror of an engine enum honest — add, under its existing `engine_types = pytest.importorskip(...)` guard and using its `_values` helper:

```python
def test_impulse_class_values_match():
    """A class the engine has that we lack is a value the settings UI can never
    offer; one we have that the engine lacks is a 400 the resolver never returns."""
    from halbert_core.config.being_config import VALID_IMPULSE_CLASSES
    assert VALID_IMPULSE_CLASSES == _values(engine_types.ImpulseClass)


def test_presence_unoverridable_matches_engine_always_admitted():
    """C-10 is the engine's rule; the config refuses exactly the classes the engine refuses."""
    from halbert_core.config.being_config import _PRESENCE_UNOVERRIDABLE
    assert _PRESENCE_UNOVERRIDABLE == {c.value for c in engine_types.ALWAYS_ADMITTED}
```

- [ ] **Step 2: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_being_config.py -q -k Presence` — Expected: FAIL (`TypeError: unexpected keyword 'presence'`).

- [ ] **Step 3: Implement** — after `VALID_PROACTIVITY = {...}` add:

```python
#: Presence slider (documentation/superpowers/specs/2026-09-16-presence-slider-design.md §14).
#: Spelled here so being_config never imports the engine, which is optional.
VALID_IMPULSE_CLASSES = {
    "life_safety", "critical", "warning", "scheduled", "recurrence", "subject_linked",
    "open_loop", "association", "affect_state", "affect_social", "absence", "spontaneous",
}
_PRESENCE_UNOVERRIDABLE = {"life_safety", "critical"}


def _is_presence_level(value: Any) -> bool:
    """A non-bool int 0..10. Stricter than the engine's clamp on purpose: a
    config value is rejected, never rounded; bool is excluded as the engine does."""
    return not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= 10
```

(`Any` is already imported.) The module docstring's list of what the file controls gains "the presence level and per-class overrides" beside the proactivity dial.

After `category_overrides: Dict[str, str] = field(default_factory=dict)` add:

```python
    # Presence slider, 0..10. Read by the shadow lane in slice 1; the live
    # gate still reads ``proactivity`` until slice 2 retires it (plan D1).
    presence: int = 3
    presence_overrides: Dict[str, int] = field(default_factory=dict)  # impulse class -> level
```

In `validate()`, after the `category_overrides` loop add:

```python
        if not _is_presence_level(self.presence):
            raise ValueError(f"presence must be an integer 0..10, got {self.presence!r}")
        for cls, level in self.presence_overrides.items():
            if cls not in VALID_IMPULSE_CLASSES:
                raise ValueError(
                    f"Unknown impulse class '{cls}' in presence_overrides. "
                    f"Must be one of: {sorted(VALID_IMPULSE_CLASSES)}"
                )
            if cls in _PRESENCE_UNOVERRIDABLE:
                raise ValueError(f"presence_overrides: '{cls}' rejects overrides (C-10)")
            if not _is_presence_level(level):
                raise ValueError(f"presence_overrides['{cls}'] must be an integer 0..10, got {level!r}")
```

(Every message spells `presence_overrides` literally: the settings route returns `str(e)` as the 400 detail and a UI highlights the field by substring.) In `from_dict`, beside the existing `morning_report: null` handling, a `presence_overrides: null` on disk means "none", not a `None`-typed field the shadow lane would trip on:

```python
        # ``presence_overrides: null`` means none, not a None-typed field the
        # shadow lane would trip on.  (``presence: null`` stays loud: a level
        # that is not a level is rejected, not defaulted.)
        if "presence_overrides" in known and known["presence_overrides"] is None:
            del known["presence_overrides"]
```

- [ ] **Step 4: Run** the file. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add halbert_core/halbert_core/config/being_config.py halbert_core/tests/test_being_config.py
git commit -m "being_config: presence level and per-class overrides (additive; the dial stays until slice 2)"
```

---

### Task 15: Halbert's curve

**Files:**
- Create: `halbert_core/halbert_core/attunement/curve.py`
- Test: `halbert_core/tests/test_attunement_curve.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's presence curve (presence spec v2 §14): the engine's shape,
Halbert's copy, top budget 8, closes_after 5, and no social affect at any
level (pass 3 P-2)."""

import re

import pytest

from halbert_core.attunement.curve import halbert_curve

engine = pytest.importorskip("haloysius.attunement.types")

C = engine.ImpulseClass


def test_curve_is_valid_and_owned_by_halbert():
    curve = halbert_curve()
    assert curve.owner == "halbert"
    assert [r.level for r in curve.rungs] == [0, 1, 3, 4, 6, 8, 10]


def test_no_social_affect_at_any_level():
    for r in halbert_curve().rungs:
        assert C.AFFECT_SOCIAL not in r.admits


def test_level_three_is_the_default_and_admits_the_morning():
    r = halbert_curve().rung_at(3)
    assert r.admits == {C.LIFE_SAFETY, C.CRITICAL, C.WARNING, C.SCHEDULED, C.RECURRENCE}


def test_copy_is_first_person_and_every_rung_says_why():
    for r in halbert_curve().rungs:
        assert re.search(r"\bI('ll| )", r.says) and r.why   # the person, not the letter


def test_admission_channel_and_patience_agree_with_the_engine_vectors():
    """The shape is the engine's, rung for rung; only budget, closes_after and
    the copy are Halbert's to change. The engine's own 136 vectors say so."""
    from haloysius.attunement.conformance import check_presence
    from haloysius.attunement.presence import resolve_presence
    from halbert_core.attunement.context import halbert_config
    failures = check_presence(
        lambda level, ov: resolve_presence(level, halbert_curve(), halbert_config().attachment, ov))
    assert not failures, "\n".join(failures)


def test_top_rung_relaxes_the_engine_default():
    top = halbert_curve().rung_at(10)
    assert top.budget_per_day == 8 and top.closes_after == 5


def test_halbert_curve_is_cached():
    assert halbert_curve() is halbert_curve()
```

- [ ] **Step 2: Run** — Expected: FAIL (`ModuleNotFoundError: halbert_core.attunement.curve`).

- [ ] **Step 3: Implement** `attunement/curve.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert's presence curve — the engine's shape in Halbert's voice.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§14 (curve), §15 (the ``says`` copy is the settings surface). The engine's
``DEFAULT_CURVE`` is the strictest in the family (C-5); this relaxes the top
budget and ``closes_after`` and never admits social affect (pass 3 P-2):
Halbert's affect is about its own condition, never the relationship.

Lazy on purpose: nothing in this package imports the engine at module
scope. ``halbert_curve()`` is cached; a bad table fails on first call, not
per decision.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover - the engine is optional at runtime
    from haloysius.attunement.types import PresenceCurve


@lru_cache(maxsize=1)
def halbert_curve() -> "PresenceCurve":
    from haloysius.attunement.types import (
        ChannelClass,
        ImpulseClass,
        InvitationLevel,
        PresenceCurve,
        PresenceRung,
    )

    C = ImpulseClass
    PUSH, AMBIENT = ChannelClass.PUSH, ChannelClass.AMBIENT
    S, M, N, CH = (InvitationLevel.SILENT, InvitationLevel.MINIMAL,
                   InvitationLevel.NORMAL, InvitationLevel.CHATTY)

    l0 = {C.LIFE_SAFETY: PUSH, C.CRITICAL: PUSH}
    l1 = {**l0, C.WARNING: PUSH}
    l3 = {**l1, C.SCHEDULED: PUSH, C.RECURRENCE: PUSH}
    l4 = {**l3, C.SUBJECT_LINKED: AMBIENT}
    l6 = {**l4, C.OPEN_LOOP: PUSH, C.ABSENCE: AMBIENT}
    l8 = {**l6, C.ASSOCIATION: PUSH, C.AFFECT_STATE: PUSH}
    l10 = {**l8, C.SPONTANEOUS: PUSH}

    def rung(level: int, name: str, says: str, why: str, channel: Dict[Any, Any],
             patience: Optional[float], budget: int, target: Any, ceiling: Any,
             closes: Optional[int]) -> PresenceRung:
        return PresenceRung(
            level=level, name=name, says=says, why=why,
            admits=frozenset(channel), channel=dict(channel), patience_s=patience,
            budget_per_day=budget, invitation_target=target, invitation_ceiling=ceiling,
            presence_signal=AMBIENT, closes_after=closes,
        )

    # Where this table leaves the engine's DEFAULT_CURVE, and why.  Admission,
    # channel and patience are the engine's rung for rung (the conformance
    # vectors hold that).  Budget: engine 0,1,3,3,4,5,5 → Halbert 0,2,3,4,5,6,8,
    # a strictly increasing ramp so every step of the fine adjust moves
    # something — the engine's plateaus (3–4, 8–10) would make those steps
    # dead for budget.  closes_after: 3 → 5.  Rung 3 is named "morning"
    # because that is what the person meets there: the morning report.
    return PresenceCurve(owner="halbert", rungs=(
        # level, name, says, why, channel, patience_s, budget, target, ceiling, closes_after
        rung(0, "mute",
             "I'll only speak for what can't wait.",
             "Nothing interrupts you. Everything else waits where you can find it.",
             l0, None, 0, S, S, None),
        rung(1, "warn",
             "I'll warn you. Everything else stays where you can find it.",
             "Warnings are worth your attention. Nothing else interrupts you.",
             l1, 240.0, 2, M, M, None),   # target == ceiling: "talk to me more" must not widen a quiet level (Q7.6)
        rung(3, "morning",
             "I'll give you the morning report, and tell you what keeps happening.",
             "The default. I stay out of the way so your own judgement stays in charge.",
             l3, 240.0, 3, N, CH, None),
        rung(4, "notice",
             "If I notice something about what you're on, I'll show it — not interrupt.",
             "Attention offered, never taken: an indicator you can pull on, not a voice.",
             l4, 180.0, 4, N, CH, None),
        rung(6, "recall",
             "I'll bring things back up when they fall due.",
             "What you told me isn't lost. When I raise it, I'll come with a next step.",
             l6, 120.0, 5, N, CH, 5),
        rung(8, "associate",
             "I'll say what your work reminds me of, and how I'm running.",
             "A thought, voiced as a thought — never as a fact I don't have.",
             l8, 90.0, 6, CH, CH, 5),
        rung(10, "think",
             "I'll talk when I have a thought, not only when something happens.",
             "Company, within a daily limit, and I'll let a thread end.",
             l10, 60.0, 8, CH, CH, 5),
    ))
```

- [ ] **Step 4: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_attunement_curve.py -q` — Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add halbert_core/halbert_core/attunement/curve.py halbert_core/tests/test_attunement_curve.py
git commit -m "attunement: Halbert's presence curve, in Halbert's voice

The engine's seven rungs with first-person copy on each, top budget 8,
closes_after 5, and social affect admitted at no level: Halbert's affect
is about its own condition, never the relationship."
```

---

### Task 16: `classify()` — a `ProactiveEvent` as an impulse

**Files:**
- Create: `halbert_core/halbert_core/attunement/impulses.py`
- Modify: `halbert_core/halbert_core/attunement/context.py` — move `_life_safety` (lines 137–157) into `impulses.py` as `life_safety_event`; leave `context.py` importing it
- Test: `halbert_core/tests/test_attunement_impulses.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Classifying Halbert's proactive events into the engine's impulse classes
with a warrant and a citation (presence spec v2 §14)."""

import pytest

engine = pytest.importorskip("haloysius.attunement.types")

from halbert_core.attunement.impulses import PRODUCED_CLASSES, classify  # noqa: E402
from halbert_core.proactive.events import ProactiveEvent  # noqa: E402

C, W = engine.ImpulseClass, engine.Warrant


def ev(data=None, affected_paths=None, **kw):
    base = dict(type="finding", severity="warning", title="t", body="b")
    base.update(kw)
    e = ProactiveEvent.create(**base)   # the same constructor the gate tests use
    if data is not None:
        e.data = data
    if affected_paths is not None:
        e.affected_paths = list(affected_paths)
    return e


def test_critical_severity_is_critical_introspected_with_a_citation():
    cls, warrant, ref = classify(ev(severity="critical", finding_id="f1"))
    assert (cls, warrant, ref) == (C.CRITICAL, W.INTROSPECTED, "finding:f1")


def test_warning_severity_is_warning():
    assert classify(ev(severity="warning"))[0] is C.WARNING


def test_morning_report_and_guest_session_are_scheduled():
    assert classify(ev(type="morning_report", severity="info"))[0] is C.SCHEDULED
    assert classify(ev(type="guest_session", severity="info"))[0] is C.SCHEDULED


def test_approval_request_is_a_warning_about_the_machines_own_action():
    assert classify(ev(type="approval_request", severity="info"))[0] is C.WARNING


def test_a_recurring_finding_is_recurrence_observed():
    cls, warrant, _ = classify(ev(severity="info", data={"recurrence_count": 3}))
    assert (cls, warrant) == (C.RECURRENCE, W.OBSERVED)


def test_an_info_finding_touching_the_current_subject_is_subject_linked():
    cls, warrant, _ = classify(ev(severity="info", affected_paths=["/etc/ssh/sshd_config"]),
                               current_subject_paths=["/etc/ssh/sshd_config"])
    assert (cls, warrant) == (C.SUBJECT_LINKED, W.OBSERVED)


def test_an_unlinked_info_finding_is_an_observed_association():
    cls, warrant, ref = classify(ev(severity="info", finding_id="f9"))
    assert (cls, warrant, ref) == (C.ASSOCIATION, W.OBSERVED, "finding:f9")


def test_an_unlinked_info_event_with_no_finding_falls_to_inferred():
    # An event id is identity, not provenance: only a finding is a citation.
    cls, warrant, ref = classify(ev(severity="info"))
    assert (cls, warrant, ref) == (C.ASSOCIATION, W.INFERRED, None)


def test_a_recurring_warning_stays_a_warning():
    # Recurrence reclassifies info; a warning that keeps happening is still a warning (rung 1).
    assert classify(ev(severity="warning", data={"recurrence_count": 3}))[0] is C.WARNING


def test_a_warning_on_the_current_subject_stays_a_warning():
    cls = classify(ev(severity="warning", affected_paths=["/etc/fstab"]), current_subject_paths=["/etc/fstab"])[0]
    assert cls is C.WARNING


def test_critical_outranks_every_type_and_data_hint():
    # C-10: the engine derives CRITICAL from severity and refuses a contradicting class.
    assert classify(ev(type="morning_report", severity="critical", data={"recurrence_count": 3}))[0] is C.CRITICAL


def test_produced_classes_matches_what_classify_returns():
    """Both directions, without the engine: every ``C.<NAME>`` returned by
    ``classify`` is in the set, and nothing in the set is unreturned."""
    import ast
    import inspect
    from halbert_core.attunement import impulses
    tree = ast.parse(inspect.getsource(impulses.classify))
    returned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "C":
                    returned.add(sub.attr.lower())
    assert returned == set(PRODUCED_CLASSES)


def test_confirmed_acoustic_anomaly_is_life_safety():
    e = ev(severity="info", category="acoustic", data={"anomaly_severity": 2})
    assert classify(e)[0] is C.LIFE_SAFETY


def test_produced_classes_is_what_classify_can_return():
    assert PRODUCED_CLASSES == {C.LIFE_SAFETY, C.CRITICAL, C.WARNING, C.SCHEDULED,
                                C.RECURRENCE, C.SUBJECT_LINKED, C.ASSOCIATION}
```

- [ ] **Step 2: Run** — Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `attunement/impulses.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A ``ProactiveEvent`` as an impulse: which class, on what warrant, citing what.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§14 (classification) and §7.1 (warrant). Three of Halbert's judgments are
made here and marked:

* **Life safety is caller-set, never derived from severity** (A-HB-15). It
  comes from the event's category and from the acoustic tagger's own
  confirmation — what ``ProactiveGate`` already treats as life safety.
* **An unlinked info finding is an *observed* association.** It is a real
  thing in the ledger that nothing in particular brought up; it is admitted
  only at the association rung, which is today's "assertive: all findings"
  — and it carries its finding id, so the stronger-than-default warrant is
  cited (engine ``Utterance.__post_init__``). **Only a finding is a
  citation.** An event id is identity, not provenance: it resolves to
  nothing durable, so an info event with no finding behind it is honestly
  ``INFERRED`` — a thought, not a fact.
* **Recurrence reclassifies info, never a warning.** A warning that keeps
  happening is still a warning: rung 1 pushes it, and would drop a
  ``RECURRENCE``.
* **``approval_request`` is a warning about the machine's own pending
  action** — introspected, not observed.

Nothing here imports the engine at module scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence, Tuple

if TYPE_CHECKING:  # pragma: no cover - the engine is optional at runtime
    from haloysius.attunement.types import ImpulseClass, Warrant

    from ..proactive.events import ProactiveEvent


def life_safety_event(event: "ProactiveEvent") -> bool:
    """Whether this event is life safety. Never derived from severity (A-HB-15).

    Two sources, both of which ``ProactiveGate`` already honours: the
    engine's life-safety category set, and a confirmed acoustic anomaly
    (tagger severity >= 2), which the wake chain treats as life safety
    because a glass break at 3am is exactly when it matters.
    """
    category = getattr(event, "category", None) or ""
    try:
        from ..integrations.modality_wiring import is_life_safety_event
    except ImportError:   # an optional integration; a bug in the predicate must not read as "not life safety"
        is_life_safety_event = None
    if is_life_safety_event is not None and is_life_safety_event(category):
        return True
    if category == "acoustic":
        data = getattr(event, "data", None)
        if isinstance(data, dict) and data.get("anomaly_severity", 0) >= 2:
            return True
    return False


def _citation(event: "ProactiveEvent") -> Optional[str]:
    """A finding id, or nothing: an event id is identity, not provenance."""
    finding_id = getattr(event, "finding_id", None)
    return f"finding:{finding_id}" if finding_id else None


def classify(event: "ProactiveEvent", *, current_subject_paths: Sequence[str] = ()
             ) -> "Tuple[ImpulseClass, Warrant, Optional[str]]":
    """``(ImpulseClass, Warrant, source_ref)`` for one event.

    Two classes have a branch here and no producer yet, so they are
    reachable in principle and unreachable in fact in slice 1:
    ``SUBJECT_LINKED`` needs ``current_subject_paths`` (what the person is on
    right now — config paths a summoned module shows, paths named in the
    current thread), which nothing on the proactive path carries; and
    ``RECURRENCE`` needs ``data["recurrence_count"]``, which no detector sets.
    The shadow log is what says when either starts arriving.

    Contract: every class this can return appears literally as ``C.<MEMBER>``
    in a ``return`` — the ``PRODUCED_CLASSES`` test reads them by AST.
    """
    from haloysius.attunement.types import ImpulseClass as C, Warrant as W

    ref = _citation(event)
    etype = str(getattr(event, "type", "") or "").lower()
    severity = str(getattr(event, "severity", "") or "info").lower()

    if life_safety_event(event):
        return C.LIFE_SAFETY, W.INTROSPECTED, ref
    if severity == "critical":
        return C.CRITICAL, W.INTROSPECTED, ref
    if etype in ("morning_report", "guest_session"):
        return C.SCHEDULED, W.INTROSPECTED, ref
    if etype == "approval_request":
        return C.WARNING, W.INTROSPECTED, ref

    if severity == "warning":
        return C.WARNING, W.INTROSPECTED, ref

    data = getattr(event, "data", None)
    if isinstance(data, dict):
        try:
            if int(data.get("recurrence_count", 0) or 0) > 1:
                return C.RECURRENCE, W.OBSERVED, ref
        except (TypeError, ValueError):
            pass

    paths = set(getattr(event, "affected_paths", None) or [])
    if paths and paths & set(current_subject_paths):
        return C.SUBJECT_LINKED, W.OBSERVED, ref

    # An observed thing brought up by no particular association. Stronger
    # than ASSOCIATION's default warrant, so it must cite; with nothing to
    # cite it is honestly inferred.
    return C.ASSOCIATION, (W.OBSERVED if ref else W.INFERRED), ref


#: Every class ``classify`` has a branch for — what the rungs endpoint calls
#: "classifiable" (plan D8).  Classifiable means the classifier can say it,
#: not that a producer emits it today; the shadow log answers the second.
#: Value strings, not members:
#: ``ImpulseClass`` is a ``str`` enum, so ``"warning" == ImpulseClass.WARNING``
#: and this set compares equal to the engine's without importing it.
PRODUCED_CLASSES = frozenset({
    "life_safety", "critical", "warning", "scheduled",
    "recurrence", "subject_linked", "association",
})
```

In `context.py`: delete `_life_safety` (the function at lines 137–157) and add near the top imports `from .impulses import life_safety_event`; in `utterance_for` replace `life_safety=_life_safety(event),` with `life_safety=life_safety_event(event),`. The module docstring's list of judgements "made here" — the life-safety one now lives in `impulses.py`; point that bullet there.

- [ ] **Step 4: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_attunement_impulses.py -q` — Expected: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add halbert_core/halbert_core/attunement/impulses.py halbert_core/halbert_core/attunement/context.py halbert_core/tests/test_attunement_impulses.py
git commit -m "attunement: classify a ProactiveEvent into an impulse class with a warrant and a citation"
```

---

### Task 17: The shadow context carries the presence vector

**Files:**
- Modify: `halbert_core/halbert_core/attunement/context.py` — replace `dial_for` (lines 110–134) with `presence_for`; `utterance_for` passes class/warrant/ref; `build_context` passes `presence`
- Modify: `halbert_core/tests/test_attunement_shadow_decide.py` (lines 67, 78, 86, 97, 112–116, 122–125) + new tests

- [ ] **Step 1: Rewrite the failing tests** in `test_attunement_shadow_decide.py`

Line 67 and 78: `cfg = _config(proactivity="balanced")` → `cfg = _config(presence=3)`.

Line 86: `cfg = _config(proactivity="off")` → `cfg = _config(proactivity="off", presence=0)`.

Line 97: `cfg = _config(proactivity="quiet")` → `cfg = _config(proactivity="quiet", presence=1)` — level 1 is the dial's `quiet` (warnings admitted, nothing else unbidden); the assertion `row["gate_reasons"] == ["dial:quiet"]` is about the live gate and stays.

Lines 112–116, replace the whole test:

```python
def test_disagreement_is_recorded_as_a_flag_not_inferred_later(store):
    """Shadow mode's whole product is the disagreement. A reader should not
    have to re-derive which engine outcomes count as speech."""
    cfg = _config(proactivity="off", presence=0)
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event(severity="warning"))

    row = _row(store)
    assert row["shadow_agrees"] is True  # both hold a warning: off dial, mute level


def test_a_critical_at_mute_disagrees_with_a_hard_off_gate(store):
    """Hard off is not on the slider (spec §3.1). Level 0 admits a critical
    and the shadow speaks; the live gate at ``off`` still suppresses. This
    row is the first thing slice 1 exists to show (plan D6)."""
    cfg = _config(proactivity="off", presence=0)
    allowed, _ = ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event(severity="critical"))

    assert allowed is False                      # live: unchanged
    row = _row(store)
    assert row["gate_outcome"] == "silent"
    assert row["outcome"] == "speak"             # shadow: the new truth
    assert row["reasons"][0] == "margin:speak"   # on its margin — not a life-safety bypass
    assert row["shadow_agrees"] is False
    assert "presence:0" in row["reasons"] and "impulse:critical" in row["reasons"]
```

Lines 122–125, the `cases` list:

```python
    # The dial↔level pairing is a fixture convention, not a claim: balanced↔3
    # is spec §20 row 5; off↔0 is D6's deliberate mismatch; quiet (gate
    # threshold: critical-only) has no exact rung, 1 is the nearest. The
    # assertion below is independent of the pairing.
    cases = [
        (_config(proactivity="quiet", presence=1), _event(severity="info")),
        (_config(proactivity="quiet", presence=1), _event(severity="critical")),
        (_config(proactivity="balanced", presence=3), _event(severity="warning")),
        (_config(proactivity="off", presence=0), _event(severity="critical")),
    ]
```

Append two new tests:

```python
def test_a_config_the_engine_refuses_keeps_the_level_and_drops_the_overrides():
    """The fallback is a belt for validate()'s braces: an unvalidated fixture
    or a class-name skew must not stamp rows with a level the person never
    chose. The level survives; the overrides go; a refused level means None."""
    from halbert_core.attunement.context import presence_for
    v = presence_for(_config(presence=8, presence_overrides={"not_a_class": 5}))
    assert v is not None and v.level == 8
    assert presence_for(_config(presence=True)) is None


def test_the_row_carries_the_presence_fields(store):
    cfg = _config(presence=3)
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event(severity="warning"))

    row = _row(store)
    assert row["presence_level"] == 3
    assert row["impulse_class"] == "warning"
    assert row["warrant"] == "introspected"
    assert row["channel_resolved"] == "push" and row["channel_capped"] is False


def test_a_class_capped_to_ambient_is_recorded_as_capped(store, monkeypatch):
    """At level 4 SUBJECT_LINKED is admitted at AMBIENT; the shadow decision
    is taken at PUSH, so the row says the channel would have been capped."""
    from halbert_core.attunement import context as ctx_mod
    cfg = _config(presence=4)
    ev = _event(severity="info")
    ev.affected_paths = ["/etc/fstab"]
    original = ctx_mod.classify
    monkeypatch.setattr(ctx_mod, "classify", lambda e, **kw: original(e, current_subject_paths=["/etc/fstab"]))
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(ev)

    row = _row(store)
    assert row["impulse_class"] == "subject_linked"
    assert row["channel_resolved"] == "ambient" and row["channel_capped"] is True
```

- [ ] **Step 2: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_attunement_shadow_decide.py -q` — Expected: FAIL (`ImportError: cannot import name 'DialLevel'` from `dial_for`).

- [ ] **Step 3: Implement** in `context.py`

Replace the whole `dial_for` function with:

```python
def presence_for(being_config: Any) -> Any:
    """``BeingConfig.presence`` and ``presence_overrides`` as the engine's vector, or None.

    Resolves Halbert's own curve under Halbert's own ceilings
    (:func:`halbert_config`). The values go to the resolver raw — it is the
    door that coerces a level and an override key and refuses a ``bool`` —
    and ``BeingConfig.validate()`` is where a bad ``being.yml`` is rejected
    before it gets here. A config that slipped past both — a fixture built
    without ``validate()``, or a class-name skew between this repo's mirror
    and the engine — keeps the person's *level* and drops the overrides,
    so no durable row is stamped with a level they never chose; if the
    level itself is refused the answer is None and the row says nothing
    (``decision_source: gate``) rather than something wrong. Logged once
    per distinct rejection, not per event.
    """
    return resolve_vector(getattr(being_config, "presence", 3),
                          dict(getattr(being_config, "presence_overrides", None) or {}))


def resolve_vector(level: Any, overrides: Mapping[str, Any]) -> "Optional[PresenceVector]":
    """``level`` through Halbert's curve under Halbert's ceilings, or None.

    The one place the drop rule lives (the preview asks the same question
    at a hypothetical level): refused overrides are dropped and the level
    kept; a refused level is None. Each rejection is logged once. If both
    are refused only the level's warning fires — the override rejection is
    moot for an event the shadow lane sits out.
    """
    try:
        from haloysius.attunement.presence import resolve_presence
    except ImportError:
        return None
    from .curve import halbert_curve

    config = halbert_config()
    if config is None:
        return None
    try:
        return resolve_presence(level, halbert_curve(), config.attachment, overrides)
    except (TypeError, ValueError) as first:
        first_message = str(first)   # the name `first` is unbound once its except block ends
    try:
        vector = resolve_presence(level, halbert_curve(), config.attachment, {})
    except (TypeError, ValueError) as exc:
        _warn_once(f"presence level rejected by the engine ({exc}); the shadow lane is off for this event")
        return None
    _warn_once(f"presence_overrides rejected by the engine ({first_message}); resolving without them")
    return vector


_last_warning: Optional[str] = None


def _warn_once(message: str) -> None:
    """A skewed config would otherwise log on every proactive event."""
    global _last_warning
    if message != _last_warning:
        logger.warning(message)
        _last_warning = message
```

(`context.py` already has a module ``logger``.) In `halbert_config`'s docstring the sentence "The dial is already the volume policy (off/quiet/balanced/assertive with per-category overrides), so the cap's remaining job is to catch a detector loop" describes the *live* gate (D1); prefix it "Live gate, slice 1:" and add "in the shadow the vector's own ``budget_per_day`` (Halbert's top rung: 8) is the volume policy and the 24 never binds."

Add `from .impulses import classify, life_safety_event` to the imports (replacing the `life_safety_event` import from Task 16).

In `utterance_for`, the severity read becomes case-insensitive so it and `classify` (which lowercases) can never disagree — a `"CRITICAL"` event must not become `Utterance(severity=INFO, impulse_class=CRITICAL)`, which the engine refuses under D9:

```python
    try:
        severity = Severity(str(getattr(event, "severity", "info") or "info").lower())
    except ValueError:
        severity = Severity.INFO
```

and before `return Utterance(`, add:

```python
    impulse_class, warrant, source_ref = classify(event)
```

and add to the `Utterance(...)` call:

```python
        impulse_class=impulse_class,
        warrant=warrant,
        source_ref=source_ref,
```

In `build_context`, replace `dial = dial_for(being_config)` with:

```python
    presence = presence_for(being_config)
    if presence is None:
        return None
```

and in the `AttunementContext(...)` call replace

```python
        dial=dial,
        invitation=ledger.invitation(subject_id, now, dial),
```
with
```python
        presence=presence,
        invitation=ledger.invitation(subject_id, now, presence),
```

Update the module docstring's third bullet and `build_context`'s docstring where they say "the dial": "the decision rests on the dial, the standing requests and the ceilings" → "rests on the presence vector, the standing requests and the ceilings".

- [ ] **Step 4: Run** the file. The two new field tests still fail (Task 18); the rest pass. Expected: `2 failed` (`presence_level` KeyError), others pass.

- [ ] **Step 5: Commit** (partial, honest)

```bash
git add halbert_core/halbert_core/attunement/context.py halbert_core/tests/test_attunement_shadow_decide.py
git commit -m "attunement: the shadow context carries Halbert's presence vector

presence_for replaces dial_for; utterance_for classifies the event and
cites it. Two new tests for the row's presence fields are red until the
recorder writes them."
```

---

### Task 18: The row records presence, class, warrant, resolved channel

**Files:**
- Modify: `halbert_core/halbert_core/attunement/shadow.py` — `record()` entry dict (~line 248) and `_verdict()` (~line 274)

- [ ] **Step 1:** The failing tests are the two from Task 17 Step 1. Run to confirm: `… -k "presence_fields or capped"` → FAIL.

- [ ] **Step 2: Implement**

In `record()`, after `"channel_class": channel_class.value,` add:

```python
                # What kind of thing this was, on what warrant — recorded for
                # every row, decider or not, so the preview can re-resolve it.
                # From the shadow's own utterance when there is one, so the row
                # and the decision cannot disagree about the class.
                **self._classification(event, context),
```

Add to `SuppressionRecorder`:

```python
    @staticmethod
    def _classification(event: Any, context: Any = None) -> Dict[str, Any]:
        """What kind of thing this was and on what warrant — from the shadow's
        own utterance on the decider path, so the row and the decision's
        ``impulse:`` stamp come from one ``classify`` call; from ``classify``
        itself on a gate-only row. An absent engine is expected and quiet; any
        other failure is a classifier bug and is logged, and the row survives
        with the two fields None."""
        utterance = getattr(context, "utterance", None)
        if utterance is not None:
            return {
                "impulse_class": getattr(utterance.impulse_class, "value", utterance.impulse_class),
                "warrant": getattr(utterance.warrant, "value", utterance.warrant),
            }
        try:
            from .impulses import classify
            cls, warrant, _ = classify(event)
        except ImportError:
            return {"impulse_class": None, "warrant": None}
        except Exception as exc:  # a bug, not an absence: say so
            logger.warning("attunement: classify failed on a gate-only row: %s", exc)
            return {"impulse_class": None, "warrant": None}
        return {"impulse_class": getattr(cls, "value", cls), "warrant": getattr(warrant, "value", warrant)}

    @staticmethod
    def _resolved_channel(context: Any) -> Dict[str, Any]:
        """The channel the vector would deliver at, and whether that capped
        the utterance's own (presence v2 §14) — the shadow's forecast, since
        routing goes live in slice 2. None when no engine context, and None
        when the class was not admitted: nothing was resolved for a delivery
        that does not happen, and a None is never a default here."""
        utterance = getattr(context, "utterance", None)
        presence = getattr(context, "presence", None)
        if utterance is None or presence is None:
            return {"channel_resolved": None, "channel_capped": None}
        ceiling = presence.channel.get(utterance.impulse_class)
        if ceiling is None:                      # not admitted: no ceiling, no delivery
            return {"channel_resolved": None, "channel_capped": None}
        from haloysius.attunement.types import channel_rank   # the engine's ordering, not a second table
        own = getattr(utterance.channel_class, "value", utterance.channel_class)
        ceiling = getattr(ceiling, "value", ceiling)
        if channel_rank(own) > channel_rank(ceiling):
            return {"channel_resolved": ceiling, "channel_capped": True}
        return {"channel_resolved": own, "channel_capped": False}
```

In `_verdict`, the `decision is None` branch gains:

```python
                "presence_level": None,
                "channel_resolved": None,
                "channel_capped": None,
```

and the engine branch gains:

```python
            # The context's level, which is the level the decision was made at:
            # the shadow never dwells (build_context passes no previous_decision).
            "presence_level": getattr(getattr(context, "presence", None), "level", None),
            **self._resolved_channel(context),
```

The comment above `**self._classification(event, context)` in `record()` scopes its "cannot disagree" claim to the decider path (`record()`'s caller-supplied `decision=` has no context and is unused in production).

Two more row shapes, appended to `test_attunement_shadow_decide.py`:

```python
def test_a_not_admitted_row_resolves_no_channel(store):
    """Nothing was resolved for a delivery that does not happen: None, not
    "checked, not capped" (the file's own rule — a None is never a default)."""
    cfg = _config(proactivity="off", presence=0)
    ProactiveGate(cfg, recorder=_recorder(store, cfg)).should_notify(_event(severity="warning"))

    row = _row(store)
    assert row["reasons"][0] == "presence:not_admitted" and row["presence_level"] == 0
    assert row["channel_resolved"] is None and row["channel_capped"] is None


def test_a_gate_only_row_still_says_what_kind_of_thing_it_was(store):
    """No engine ran, so the engine-derived fields are None; the class and
    warrant come from the same classifier the engine path would have used."""
    cfg = _config(proactivity="quiet")
    ProactiveGate(cfg, recorder=SuppressionRecorder(store=store)).should_notify(_event(severity="info"))

    row = _row(store)
    assert row["decision_source"] == "gate"
    assert (row["presence_level"], row["channel_resolved"], row["channel_capped"]) == (None, None, None)
    assert (row["impulse_class"], row["warrant"]) == ("association", "inferred")
```

- [ ] **Step 3: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_attunement_shadow_decide.py halbert_core/tests/test_attunement_shadow.py halbert_core/tests/test_proactive_gate_records.py halbert_core/tests/test_attunement_recorder_wiring.py -q` — Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add halbert_core/halbert_core/attunement/shadow.py
git commit -m "attunement: every shadow row says its impulse class, warrant, level and resolved channel"
```

---

### Task 19: The preview — re-resolve stored rows at any level

**Files:**
- Create: `halbert_core/halbert_core/attunement/preview.py`
- Test: `halbert_core/tests/test_attunement_preview.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The preview: "at this level, here is what I would have said this week,
shown, and held" — admission and channel re-run over stored rows (spec
v2 §15, plan D7). Deterministic; no model, no live context."""

from datetime import datetime, timedelta, timezone

import pytest

from halbert_core.attunement.preview import preview_for_level
from halbert_core.config.being_config import BeingConfig

pytest.importorskip("haloysius.attunement.types")   # the preview needs the engine at call time

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def row(days_ago, impulse_class, channel="push", severity="warning", gate="silent", attempt="a"):
    return {
        "attempt_id": f"{attempt}-{days_ago}-{impulse_class}",
        "ts": (NOW - timedelta(days=days_ago)).isoformat(),
        "source": "finding", "severity": severity,
        "channel_class": channel, "impulse_class": impulse_class,
        "gate_outcome": gate,
    }


ROWS = [
    row(1, "critical"), row(2, "warning"), row(3, "recurrence"),
    row(4, "subject_linked"), row(5, "association"), row(6, "spontaneous"),
    row(9, "warning"),                          # outside a 7-day window
    {"attempt_id": "old", "ts": (NOW - timedelta(days=2)).isoformat(), "gate_outcome": "silent"},  # pre-slice row, no class
]


def test_level_zero_says_only_the_critical():
    p = preview_for_level(ROWS, 0, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"], p["unclassified"]) == (1, 0, 5, 1)
    assert p["level"] == 0 and p["days"] == 7


def test_level_three_adds_warning_and_recurrence():
    p = preview_for_level(ROWS, 3, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"]) == (3, 0, 3)


def test_level_four_shows_the_subject_linked_row_ambiently():
    p = preview_for_level(ROWS, 4, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"]) == (3, 1, 2)
    item = next(i for i in p["items"] if i["impulse_class"] == "subject_linked")
    assert item["verdict"] == "shown" and item["channel"] == "ambient"


def test_level_ten_still_shows_subject_linked_ambiently():
    # SUBJECT_LINKED is AMBIENT at every rung from 4 up (curve.py l4..l10 spread it
    # forward unchanged), so the top level says five and shows one — never six said.
    p = preview_for_level(ROWS, 10, being_config=BeingConfig(), days=7, now=NOW)
    assert (p["said"], p["shown"], p["held"]) == (5, 1, 0)


def test_items_carry_the_live_outcome_beside_the_preview_verdict():
    p = preview_for_level(ROWS, 3, being_config=BeingConfig(), days=7, now=NOW)
    assert all("live_outcome" in i and "verdict" in i for i in p["items"])
    assert len(p["items"]) == 6


def test_overrides_from_the_config_apply():
    cfg = BeingConfig(presence_overrides={"spontaneous": 10})
    p = preview_for_level(ROWS, 0, being_config=cfg, days=7, now=NOW)
    assert p["said"] == 2   # critical + the overridden spontaneous


def test_the_budget_rides_beside_the_counts_and_undated_rows_are_counted():
    rows = ROWS + [{"attempt_id": "nots", "impulse_class": "warning", "gate_outcome": "silent"},
                   {**row(1, "warning", attempt="z"), "ts": NOW.isoformat().replace("+00:00", "Z")}]
    p = preview_for_level(rows, 3, being_config=BeingConfig(), days=7, now=NOW)
    assert p["budget_per_day"] == 3 and p["undated"] == 1
    assert p["said"] == 4   # the Z-suffixed row is read, not dropped


def test_a_refused_override_is_dropped_and_the_preview_still_answers():
    from types import SimpleNamespace
    cfg = SimpleNamespace(presence_overrides={"not_a_class": 5})   # never validate()d
    p = preview_for_level(ROWS, 0, being_config=cfg, days=7, now=NOW)
    assert p["engine"] is True and p["said"] == 1   # critical only; the override went


def test_items_are_newest_first_by_time_not_by_string():
    mixed = [{**row(1, "warning", attempt="p"), "ts": "2026-09-15T13:30:00+02:00"},   # 11:30 UTC
             {**row(1, "critical", attempt="q"), "ts": "2026-09-15T12:00:00+00:00"}]  # 12:00 UTC — newer
    p = preview_for_level(mixed, 3, being_config=BeingConfig(), days=7, now=NOW)
    assert [i["impulse_class"] for i in p["items"]] == ["critical", "warning"]
```

- [ ] **Step 2: Run** — Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `attunement/preview.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""What the machine would have said at another level — from the shadow log.

Spec: ``documentation/superpowers/specs/2026-09-16-presence-slider-design.md``
§15. The preview is admission and channel re-run over stored rows at a
hypothetical level (plan D7). It is *not* a re-decide: a stored row has no
live receptivity and no standing requests, so the inequality cannot be
re-run honestly. What can be re-run exactly is whether the class would be
admitted and at what channel — and that is what the person is choosing.

Nor is the budget re-run: exhaustion is a deferral to the next turn, per
day at the consumer's midnight, and neither the deadline nor the timezone
is in a stored row — so the counts are "what would have been admitted",
and ``budget_per_day`` rides beside them for the surface to say "up to N a
day".

"Held" here is the person's word (spec §15, the rung-0 copy): not brought
up, and waiting where they can find it. It is not the engine's
``EngagementOutcome.HOLD``, which is an *admitted* impulse deferred with a
resume condition and a deadline. A shadow row with ``outcome: "hold"`` and
a preview verdict "held" are two different statements.

Rows written before slice 1 carry no ``impulse_class``; they are counted
as ``unclassified`` and never guessed at. A row whose timestamp cannot be
read is counted as ``undated`` so the totals reconcile with the store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: The verdict a delivery channel reads as, in the person's words: pushed is
#: "said", ambient is "shown", pull is "held" (findable, never pushed — the
#: engine never suppresses a pull utterance; no slice-1 row carries pull,
#: every shadow row is decided at PUSH). A label table; the *ranking* is
#: the engine's ``channel_rank``.
_VERDICT_BY_CHANNEL = {"push": "said", "ambient": "shown", "pull": "held"}


def _parse(ts: Any) -> Optional[datetime]:
    """The store writes tz-aware UTC; a naive value reads as UTC, and a
    trailing ``Z`` is accepted (``fromisoformat`` rejects it before 3.11)."""
    text = str(ts)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def preview_for_level(rows: Iterable[Dict[str, Any]], level: int, *, being_config: Any,
                      days: int = 7, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Counts and per-row verdicts for ``level`` over the last ``days``.

    The config's own level is irrelevant here — the person is asking about
    ``level`` — only its overrides ride along, through the one drop rule in
    ``context.resolve_vector``.
    """
    from .context import resolve_vector

    vector = resolve_vector(level, dict(getattr(being_config, "presence_overrides", None) or {}))
    if vector is None:
        return {"level": level, "days": days, "said": 0, "shown": 0, "held": 0,
                "unclassified": 0, "undated": 0, "budget_per_day": None, "items": [], "engine": False}
    from haloysius.attunement.types import ImpulseClass, channel_rank

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    counts = {"said": 0, "shown": 0, "held": 0}
    unclassified = undated = 0
    dated: List[Tuple[datetime, Dict[str, Any]]] = []

    for r in rows:
        ts = _parse(r.get("ts"))
        if ts is None:
            undated += 1
            continue
        if ts < cutoff:
            continue
        raw = r.get("impulse_class")
        if not raw:
            unclassified += 1
            continue
        try:
            cls = ImpulseClass(raw)
        except ValueError:
            unclassified += 1
            continue
        # Every shadow row is decided at PUSH (context.SHADOW_CHANNEL_CLASS) and
        # the recorder writes the field with the row; the default is the loudest
        # reading for a row that somehow lacks it.
        own = str(r.get("channel_class") or "push")
        if cls not in vector.admits:
            verdict, channel = "held", None
        else:
            ceiling = vector.channel[cls].value
            try:
                capped = channel_rank(own) > channel_rank(ceiling)
            except ValueError:            # a channel the engine does not know: resolve at the ceiling
                capped = True
            channel = ceiling if capped else own
            verdict = _VERDICT_BY_CHANNEL[channel]
        counts[verdict] += 1
        dated.append((ts, {
            "attempt_id": r.get("attempt_id"), "ts": r.get("ts"),
            "source": r.get("source"), "severity": r.get("severity"),
            "context_key": r.get("context_key"),
            "impulse_class": cls.value, "verdict": verdict, "channel": channel,
            "live_outcome": r.get("gate_outcome"),
        }))

    dated.sort(key=lambda pair: pair[0], reverse=True)   # chronological, not lexical
    return {"level": vector.level, "days": days, **counts,
            "unclassified": unclassified, "undated": undated,
            "budget_per_day": vector.budget_per_day,
            "items": [item for _, item in dated], "engine": True}
```

- [ ] **Step 4: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_attunement_preview.py -q` — Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add halbert_core/halbert_core/attunement/preview.py halbert_core/tests/test_attunement_preview.py
git commit -m "attunement: the preview — admission and channel re-run over the shadow log at any level"
```

---

### Task 20: Settings API accepts `presence`

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/settings.py` — `BeingConfigUpdate` (~line 3150) and the `mutate` closure (~line 3212)
- Test: `halbert_core/tests/test_settings_being_presence.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""POST /api/settings/being carries the presence level and overrides."""

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The settings router alone over an isolated config dir.

    Nothing under test may touch the developer's real being.yml: the route
    resolves it through get_config_dir(), which honours HALBERT_CONFIG_DIR
    (test_entity_name_write_through.py's pattern). And the POST's hot-reload
    branch calls get_agent(), which would boot the whole agent and open the
    developer's real ChromaDB; a stub singleton makes that branch a no-op
    (test_agent_interrupt_routes.py's pattern).
    """
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from halbert_core.dashboard.routes import agent as agent_routes
    from halbert_core.dashboard.routes import settings as settings_routes
    monkeypatch.setattr(agent_routes, "_agent_instance", SimpleNamespace(prompt_builder=None))
    app = FastAPI()
    app.include_router(settings_routes.router, prefix="/api/settings")
    return TestClient(app)


def test_presence_round_trips(client):
    r = client.post("/api/settings/being", json={"presence": 6, "presence_overrides": {"warning": 2}})
    assert r.status_code == 200, r.text
    cfg = client.get("/api/settings/being").json()["config"]
    assert cfg["presence"] == 6 and cfg["presence_overrides"] == {"warning": 2}


def test_out_of_range_presence_is_rejected(client):
    r = client.post("/api/settings/being", json={"presence": 11})
    assert r.status_code == 400
    r = client.post("/api/settings/being", json={"presence_overrides": {"critical": 0}})
    assert r.status_code == 400


def test_the_old_dial_field_still_saves_in_slice_one(client):
    assert client.post("/api/settings/being", json={"proactivity": "quiet"}).status_code == 200
    assert client.get("/api/settings/being").json()["config"]["proactivity"] == "quiet"


@pytest.mark.parametrize("bad", [True, "6", 6.5])
def test_a_wrong_type_is_refused_before_it_can_be_laundered(client, bad):
    # Pydantic's lax int would read true as 1; StrictInt makes a wrong type a 422
    # and leaves the range check to validate()'s 400.
    assert client.post("/api/settings/being", json={"presence": bad}).status_code == 422
    assert client.get("/api/settings/being").json()["config"]["presence"] == 3
```

- [ ] **Step 2: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_settings_being_presence.py -q` — Expected: first test FAIL (`presence` stays 3: Pydantic drops the unknown field).

- [ ] **Step 3: Implement** — in `BeingConfigUpdate`, after `category_overrides: Optional[Dict[str, str]] = None` add:

```python
    # Presence slider (spec 2026-09-16 v2 §15). Additive in slice 1. Strict:
    # Pydantic's lax int accepts true (→ 1) and "6"; the config module and the
    # engine's door refuse a bool, and the route must not launder one first.
    # A wrong *type* is therefore a 422 here; a wrong *range* is validate()'s 400.
    # presence_overrides replaces the whole map: {} clears it, and null (the
    # field absent) means "leave it" here — unlike a null in being.yml, which
    # means "none" (from_dict).
    presence: Optional[StrictInt] = None
    presence_overrides: Optional[Dict[str, StrictInt]] = None
```

The `POST /being` route's docstring gains one paragraph a frontend author would read: "Errors: a wrong *type* in the body is FastAPI's 422, whose `detail` is a list of `{loc, msg, type}`; a value the config refuses (range, an unknown class, C-10) is a 400 whose `detail` is one sentence naming the field."

(`StrictInt` from `pydantic`; add it to the existing `from pydantic import ...` line.)

In `mutate`, after the `category_overrides` block add:

```python
                if update.presence is not None:
                    cfg.presence = update.presence
                if update.presence_overrides is not None:
                    cfg.presence_overrides = dict(update.presence_overrides)
```

`validate()` runs inside the locked updater (`config/being_config.py` `update_being_config`, imported by the route as `update_being_config_locked`) after `mutate`, and the POST route already maps `ValueError → 400` in its outer `except` arms (verified 2026-09-17), so the second test passes with no route change beyond the two fields. The GET returns `cfg.to_dict()`, so `presence` round-trips with no change there either.

- [ ] **Step 4: Run** the file. Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add halbert_core/halbert_core/dashboard/routes/settings.py halbert_core/tests/test_settings_being_presence.py
git commit -m "settings: the being config API carries presence and per-class overrides"
```

---

### Task 21: `GET /api/being/presence/rungs` and `/preview`

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/being.py`
- Test: `halbert_core/tests/test_being_presence_routes.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The two read-only presence endpoints: the rungs (copy as data, plan D8)
and the preview over the shadow log."""

from datetime import datetime, timedelta, timezone

import pytest

engine = pytest.importorskip("haloysius.attunement.types")

from halbert_core.attunement.store import AttunementStore  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The preview route loads being.yml through get_config_dir(); point it at
    # an empty temp dir so the test reads defaults, never the developer's file.
    monkeypatch.setenv("HALBERT_CONFIG_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.app import create_app
    return TestClient(create_app())


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = AttunementStore(db_path=str(tmp_path / "attunement.db"))
    from halbert_core.dashboard.routes import being as being_mod
    monkeypatch.setattr(being_mod, "_attunement_store", lambda: s)
    return s


def _seed(store, impulse_class, days_ago):
    store.record_outcome_raw({
        "attempt_id": f"{impulse_class}-{days_ago}", "persona_id": "halbert", "subject_id": "primary",
        "outcome": "silent", "ts": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "source": "finding", "severity": "warning", "channel_class": "push",
        "impulse_class": impulse_class, "gate_outcome": "silent",
    })


def test_rungs_are_served_with_copy_and_reachability(client):
    body = client.get("/api/being/presence/rungs").json()
    assert body["status"] == "ok" and "owner" not in body   # the curve's owner id is internal
    levels = [r["level"] for r in body["rungs"]]
    assert levels == [0, 1, 3, 4, 6, 8, 10]
    by_level = {r["level"]: r for r in body["rungs"]}
    assert by_level[3]["says"].startswith("I") and by_level[3]["why"]
    assert by_level[3]["classifiable"] is True
    assert by_level[6]["classifiable"] is False   # nothing can yet be described as OPEN_LOOP or ABSENCE
    assert "subject_linked" in by_level[4]["channel"] and by_level[4]["channel"]["subject_linked"] == "ambient"


def test_preview_counts_the_last_week_at_the_hovered_level(client, store):
    _seed(store, "critical", 1)
    _seed(store, "warning", 2)
    _seed(store, "association", 3)
    _seed(store, "warning", 20)
    body = client.get("/api/being/presence/preview", params={"level": 0, "days": 7}).json()
    assert (body["said"], body["held"]) == (1, 2)
    body = client.get("/api/being/presence/preview", params={"level": 8, "days": 7}).json()
    assert body["said"] == 3


def test_preview_validates_its_range(client):
    assert client.get("/api/being/presence/preview", params={"level": 11}).status_code == 422
```

- [ ] **Step 2: Run** — Expected: FAIL (404s).

- [ ] **Step 3: Implement** — append to `routes/being.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Presence (spec 2026-09-16 v2 §15). Read-only; the level itself is written
# through /api/settings/being.
# ─────────────────────────────────────────────────────────────────────────────

def _attunement_store():
    """The shadow log. A function so tests can point it at a temp DB."""
    from ...attunement.store import AttunementStore
    return AttunementStore()


@router.get("/being/presence/rungs")
def presence_rungs() -> dict:
    """The curve's rungs with their first-person copy — the settings surface
    never hardcodes it (plan D8) — and whether each rung is *classifiable*
    yet: every class it newly admits has a classification branch
    (``PRODUCED_CLASSES``). Whether a producer emits the class today is the
    shadow log's question, not this endpoint's. Plain ``def``: Starlette
    runs it off the event loop, like ``findings.py``'s handlers."""
    try:
        from ...attunement.curve import halbert_curve
        from ...attunement.impulses import PRODUCED_CLASSES
        curve = halbert_curve()
    except ImportError:
        raise HTTPException(status_code=503, detail="attunement engine not installed")
    rungs, previous = [], set()
    for r in curve.rungs:
        newly = set(r.admits) - previous
        rungs.append({
            "level": r.level, "name": r.name, "says": r.says, "why": r.why,
            "admits": sorted(c.value for c in r.admits),
            "channel": {c.value: ch.value for c, ch in r.channel.items()},
            "budget_per_day": r.budget_per_day, "patience_s": r.patience_s,
            "closes_after": r.closes_after,
            "classifiable": newly <= PRODUCED_CLASSES,   # str-enum members compare equal to their value strings
        })
        previous = set(r.admits)
    return {"status": "ok", "rungs": rungs}   # the curve's owner id is internal, not a surface string


#: A safety cap on rows read for one preview; the window itself is a ``since``
#: filter in SQL, so this binds only a store far busier than a month of
#: proactive events. When it binds, ``truncated`` says so on the wire.
_PREVIEW_ROWS = 20000


@router.get("/being/presence/preview")
def presence_preview(
    level: int = Query(..., ge=0, le=10),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """What I would have said, shown and held over the last ``days`` at
    ``level`` — admission and channel re-run over the shadow log. The counts
    see every row in the window (a ``since`` filter in SQL; ``truncated``
    only if the safety cap bound); ``items`` is cut to ``limit`` for the
    wire. 503 without the engine, like the rungs; 400 on a config the
    loader refuses, like the settings GET. Plain ``def``: three synchronous
    reads (a SQLite open, the window, the YAML) stay off the event loop."""
    from datetime import datetime, timedelta, timezone

    from ...attunement.context import DEFAULT_PERSONA_ID
    from ...attunement.preview import preview_for_level
    from ...config.being_config import load_being_config
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _attunement_store().list_outcomes_raw(DEFAULT_PERSONA_ID, limit=_PREVIEW_ROWS, since=since)
    try:
        config = load_being_config()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    preview = preview_for_level(rows, level, being_config=config, days=days)
    if not preview["engine"]:
        raise HTTPException(status_code=503, detail="attunement engine not installed")
    preview["items"] = preview["items"][:limit]
    preview["truncated"] = len(rows) >= _PREVIEW_ROWS
    preview["status"] = "ok"   # the envelope last, so no preview key can shadow it
    return preview
```

`attunement/store.py`, `list_outcomes_raw` gains `since: Optional[str] = None` — when given, `sql += " AND ts >= ?"` with the value appended to `args` (the store writes `ts` as tz-aware UTC ISO, so the comparison is lexical and exact, the same comparison `trim_outcomes` already makes); the index `idx_outcomes_persona(persona_id, ts DESC)` serves it. One test in `test_attunement_store.py` (or the store's existing test file): two rows a day apart, `since` between them → only the newer.

The route tests: `test_rungs_are_served_with_copy_and_reachability` → `test_rungs_are_served_with_copy_and_classifiability`, asserting `classifiable` and no `owner` key; add

```python
def test_preview_cuts_items_but_not_counts(client, store):
    for i in range(3):
        _seed(store, "warning", i + 1)
    body = client.get("/api/being/presence/preview", params={"level": 3, "limit": 2}).json()
    assert body["said"] == 3 and len(body["items"]) == 2 and body["truncated"] is False


def test_preview_says_when_the_safety_cap_bound(client, store, monkeypatch):
    from halbert_core.dashboard.routes import being as being_mod
    monkeypatch.setattr(being_mod, "_PREVIEW_ROWS", 2)
    for i in range(3):
        _seed(store, "warning", i + 1)
    assert client.get("/api/being/presence/preview", params={"level": 3}).json()["truncated"] is True


@pytest.mark.parametrize("params", [{"level": 11}, {"level": -1}, {"level": 3, "days": 0}, {"level": 3, "limit": 0}])
def test_preview_validates_its_range(client, params):
    assert client.get("/api/being/presence/preview", params=params).status_code == 422


def test_a_row_the_recorder_writes_is_a_row_the_preview_reads(client, store):
    """The recorder→preview seam: a rename of a row key in either would
    otherwise pass both files' own tests and make every row unclassified."""
    from halbert_core.attunement.shadow import SuppressionRecorder
    from halbert_core.proactive.events import ProactiveEvent
    ev = ProactiveEvent.create(type="finding", severity="critical", title="t", body="b")
    SuppressionRecorder(store=store).record(ev, allowed=False)
    body = client.get("/api/being/presence/preview", params={"level": 0}).json()
    assert body["said"] == 1 and body["unclassified"] == 0
```

(replacing the plan's single `test_preview_validates_its_range`; check `record()`'s real signature for the `allowed=` keyword and adapt). `test_settings_being_presence.py`: the parametrized bad values become `[True, "6", 6.0]` (`6.5` is refused by lax int too and discriminates nothing; `6.0` is the one lax launders) and gain a second parametrized test for `presence_overrides={"warning": <bad>}` → 422.

- [ ] **Step 4: Run** `PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_being_presence_routes.py halbert_core/tests/test_being_routes.py -q` — Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add halbert_core/halbert_core/dashboard/routes/being.py halbert_core/tests/test_being_presence_routes.py
git commit -m "being: read-only presence endpoints — the rungs as data, and the preview over the shadow log"
```

---

### Task 22: `PresenceCard` — seven rungs, fine adjust, preview

**Files:**
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/PresenceCard.tsx`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/PresenceCard.test.tsx`
- Modify: `…/BeingTab.tsx` (lines 492–528: the Proactivity card) and `…/BeingTab.test.tsx` (line 29 fixture)

- [ ] **Step 1: Write the failing test** — `PresenceCard.test.tsx` (uses `@testing-library/react`, as the sibling tests do; check `BeingTab.test.tsx`'s imports and match its render helper if it wraps in providers):

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PresenceCard } from './PresenceCard'

const rungs = {
  status: 'ok',
  rungs: [
    { level: 0, name: 'mute', says: "I'll only speak for what can't wait.", why: 'Nothing interrupts you.', classifiable: true },
    { level: 3, name: 'morning', says: "I'll give you the morning.", why: 'The default.', classifiable: true },
    { level: 6, name: 'recall', says: "I'll bring things back up.", why: 'Not lost.', classifiable: false },
    { level: 10, name: 'think', says: "I'll talk when I have a thought.", why: 'Company, bounded.', classifiable: false },
  ],
}
const preview = { status: 'ok', level: 3, days: 7, said: 2, shown: 1, held: 4, unclassified: 0, undated: 0, budget_per_day: 3, truncated: false, items: [] }

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () => (String(url).includes('/presence/rungs') ? rungs : preview),
  }))
  vi.stubGlobal('fetch', fetchMock)
})

const lastPreviewUrl = () =>
  String(fetchMock.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('/presence/preview')).pop() ?? '')

describe('PresenceCard', () => {
  it('renders the rungs as the primary control with their copy', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    expect(await screen.findByText("I'll give you the morning.")).toBeTruthy()
    expect(screen.getByText('The default.')).toBeTruthy()
  })

  it('says on its face which rungs nothing can yet be described as, and still lets them be chosen', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    const recall = await screen.findByRole('button', { name: /recall/i })
    expect(recall.textContent).toContain('(not yet)')
    expect(recall.hasAttribute('disabled')).toBe(false)
  })

  it('marks the saved rung for a screen reader, and keeps the mark there while another is hovered', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    const morning = await screen.findByRole('button', { name: /morning/i })
    const think = await screen.findByRole('button', { name: /think/i })
    expect(morning.getAttribute('aria-pressed')).toBe('true')
    expect(think.getAttribute('aria-pressed')).toBe('false')

    fireEvent.mouseEnter(think)          // hovering asks about a rung; it does not select one
    expect(morning.getAttribute('aria-pressed')).toBe('true')
    expect(think.getAttribute('aria-pressed')).toBe('false')

    fireEvent.focus(think)               // and tabbing to one does not either — the case C1 was about
    expect(morning.getAttribute('aria-pressed')).toBe('true')
    expect(think.getAttribute('aria-pressed')).toBe('false')
  })

  it('choosing a rung saves its level', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    fireEvent.click(await screen.findByRole('button', { name: /think/i }))
    expect(onChange).toHaveBeenCalledWith({ presence: 10 })
  })

  it('the fine adjust writes once, when the drag ends', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    const slider = await screen.findByRole('slider')
    fireEvent.change(slider, { target: { value: '4' } })
    fireEvent.change(slider, { target: { value: '5' } })
    expect(onChange).not.toHaveBeenCalled()          // a drag is not a save
    fireEvent.pointerUp(slider)
    fireEvent.blur(slider)                           // the backstop must not write again
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ presence: 5 })
  })

  it('snaps back when a save ends without changing the level', async () => {
    const { rerender } = render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    fireEvent.change(await screen.findByRole('slider'), { target: { value: '7' } })
    expect(screen.getByText(/Fine adjust: 7/)).toBeTruthy()

    rerender(<PresenceCard level={3} saving={true} onChange={() => {}} />)
    rerender(<PresenceCard level={3} saving={false} onChange={() => {}} />)   // refused: the level never arrived
    expect(screen.getByText(/Fine adjust: 3/)).toBeTruthy()
  })

  it('hovering a rung previews it without choosing it', async () => {
    const onChange = vi.fn()
    render(<PresenceCard level={3} saving={false} onChange={onChange} />)
    fireEvent.mouseEnter(await screen.findByRole('button', { name: /think/i }))
    await waitFor(() => expect(lastPreviewUrl()).toContain('level=10'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('reaches the preview from the keyboard too', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    fireEvent.focus(await screen.findByRole('button', { name: /mute/i }))
    await waitFor(() => expect(lastPreviewUrl()).toContain('level=0'))
  })

  it('shows the preview counts for the current level, by name', async () => {
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    await waitFor(() => expect(screen.getByText(/at 3 \(morning\)/i)).toBeTruthy())
    expect(screen.getByText(/said 2/i)).toBeTruthy()
    expect(screen.getByText(/shown 1/i)).toBeTruthy()
    expect(screen.getByText(/held 4/i)).toBeTruthy()
  })

  it('says so in its own words when it cannot read the log, and keeps the fine adjust', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })))
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    expect(await screen.findByRole('slider')).toBeTruthy()
    await waitFor(() => expect(screen.getByText(/the part of me that keeps it isn't answering/i)).toBeTruthy())
    expect(screen.getByText(/could not read the levels/i)).toBeTruthy()
  })

  it("never puts the platform's own wording on the surface", async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    render(<PresenceCard level={3} saving={false} onChange={() => {}} />)
    await waitFor(() => expect(screen.getByText(/could not read the log just now/i)).toBeTruthy())
    expect(screen.queryByText(/Failed to fetch/)).toBeNull()
  })
})
```

- [ ] **Step 1b: Install the worktree's frontend dependencies once** (done 2026-09-17 by the coordinator, `npm ci` exit 0 — verify `ls node_modules` and skip) — a fresh worktree has `package-lock.json` but no `node_modules`, so the first `npx vitest` would fail for the wrong reason:

```bash
cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1/halbert_core/halbert_core/dashboard/frontend && npm ci
```

- [ ] **Step 2: Run** `cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/settings/tabs/PresenceCard.test.tsx` — Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `PresenceCard.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

/** The window the preview reads. The spec's week (§15) — the API accepts
 *  1–30 and the copy reads the window back off the response, so this is the
 *  spec's number, not a placeholder for a control. */
const PREVIEW_DAYS = 7
const PREVIEW_ITEMS = 20
/** Below the hover-intent threshold: a deliberate hover still feels instant,
 *  while a sweep across the rungs asks the log for nothing. */
const PREVIEW_DEBOUNCE_MS = 200

/** What raised it, in the person's words. The row never shows the event's own
 *  type token — the surface carries no enum names (spec §15). */
const SOURCE_COPY: Record<string, string> = {
  finding: 'a finding',
  morning_report: 'the morning report',
  approval_request: 'an approval',
  system_anomaly: 'an anomaly',
}

export interface PresenceRung {
  level: number
  name: string
  says: string
  why: string
  classifiable: boolean   // every class this rung newly admits is one I can describe something as today
}

interface PreviewItem {
  attempt_id: string
  ts: string
  source: string
  verdict: 'said' | 'shown' | 'held'
  live_outcome: string | null
}

interface Preview {
  level: number
  days: number
  said: number
  shown: number
  held: number
  unclassified: number
  undated: number
  budget_per_day: number | null
  truncated: boolean
  items: PreviewItem[]
}

interface Props {
  level: number
  saving: boolean
  onChange: (updates: Record<string, unknown>) => void
}

/**
 * The presence control (spec 2026-09-16 v2 §15).
 *
 * Seven named rungs are the primary control; the 0–10 fine adjust sits
 * beneath. Copy comes from the API — the curve is data (D8). The preview
 * reads the shadow log at the hovered or dragged level, so the person can
 * see the machine's judgement before trusting it. Nothing here changes live
 * behaviour in slice 1: the level is read by the shadow lane only, and the
 * proactivity card below still governs what is heard (D1, D11).
 *
 * Two levels are in play and they are kept apart on purpose. ``level`` is
 * what the config holds: it drives the selected mark, which a screen reader
 * reads, so hovering never moves it. ``shown`` is what is being *asked
 * about* — hovered, focused or dragged — and drives only the preview and
 * the explanation beneath the rungs.
 *
 * The fine adjust writes once, when the drag ends: a range input's onChange
 * fires per step, and each write is a config save. It is disabled while a
 * save is in flight — not mid-gesture, since the write happens on release —
 * because a drag released during one would otherwise be dropped in silence.
 */
export function PresenceCard({ level, saving, onChange }: Props) {
  const [rungs, setRungs] = useState<PresenceRung[]>([])
  const [rungsFailed, setRungsFailed] = useState(false)
  const [hover, setHover] = useState<number | null>(null)
  const [draft, setDraft] = useState<number | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const sent = useRef<number | null>(null)
  const wasSaving = useRef(saving)

  useEffect(() => {
    fetch(`${API_BASE}/being/presence/rungs`)
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => { setRungs(body?.rungs ?? []); setRungsFailed(!body?.rungs?.length) })
      .catch(() => { setRungs([]); setRungsFailed(true) })
  }, [])

  // The drag's value stands until the save round-trips. Cleared when the
  // saved level arrives — and when a save *ends* without it arriving, so a
  // refused write cannot leave the control showing a level I do not hold.
  useEffect(() => { setDraft(null); sent.current = null }, [level])
  useEffect(() => {
    if (wasSaving.current && !saving) { setDraft(null); sent.current = null }
    wasSaving.current = saving
  }, [saving])

  const sliderValue = draft ?? level
  const shown = hover ?? sliderValue

  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetch(`${API_BASE}/being/presence/preview?level=${shown}&days=${PREVIEW_DAYS}&limit=${PREVIEW_ITEMS}`,
            { signal: controller.signal })
        .then(async (r) => {
          if (r.ok) return r.json()
          const body = await r.json().catch(() => ({}))
          // Carry the status, not a message: the platform's own wording
          // ("Failed to fetch") must not reach a surface I speak on.
          throw Object.assign(new Error('preview unavailable'), { status: r.status, detail: body?.detail })
        })
        .then((body) => { setPreview(body); setPreviewError(null) })
        .catch((err) => {
          if (err?.name === 'AbortError' || controller.signal.aborted) return
          setPreview(null)
          setPreviewError(
            err?.status === 503 ? "I can't read my own log here — the part of me that keeps it isn't answering."
              : err?.status === 400 ? "I can't read my configuration file — something in it is wrong."
                : 'I could not read the log just now.')
        })
    }, PREVIEW_DEBOUNCE_MS)
    return () => { clearTimeout(timer); controller.abort() }
  }, [shown])

  const rungAt = (n: number) => [...rungs].reverse().find((r) => r.level <= n) ?? null
  const selected = rungAt(level)          // what the config holds
  const current = rungAt(shown)           // what is being asked about
  const previewRung = preview ? rungAt(preview.level) : null

  const commit = () => {
    if (saving || draft === null || draft === level || draft === sent.current) return
    sent.current = draft
    onChange({ presence: draft })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Presence</CardTitle>
        <CardDescription>How much I bring up on my own. Nothing here changes what you hear yet — it changes what the preview shows.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label id="presence-rungs-label">How present</Label>
          <div role="group" aria-labelledby="presence-rungs-label" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-7">
            {rungs.map((r) => (
              <Button
                key={r.name}
                variant={selected?.name === r.name ? 'default' : 'outline'}
                aria-pressed={selected?.name === r.name}
                onClick={() => onChange({ presence: r.level })}
                onMouseEnter={() => setHover(r.level)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(r.level)}
                onBlur={() => setHover(null)}
                disabled={saving}
                className="h-auto flex-col items-start whitespace-normal text-left"
              >
                <span className="capitalize">
                  {r.name}
                  {!r.classifiable && <span className="font-normal text-muted-foreground"> (not yet)</span>}
                </span>
                <span className="text-xs font-normal text-muted-foreground">{r.says}</span>
              </Button>
            ))}
          </div>
          {rungsFailed && <p className="text-xs text-muted-foreground">I could not read the levels just now; the fine adjust below still works.</p>}
          {current && <p className="text-xs text-muted-foreground">{current.why}{!current.classifiable && " Not yet: nothing I do is described as what this rung admits."}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="presence-fine">Fine adjust: {sliderValue}</Label>
          <input
            id="presence-fine"
            type="range"
            min={0}
            max={10}
            step={1}
            value={sliderValue}
            disabled={saving}
            onChange={(e) => setDraft(Number(e.target.value))}
            onPointerUp={commit}
            onKeyUp={commit}
            onBlur={commit}
            className="w-full"
            aria-valuetext={`${sliderValue}${rungAt(sliderValue) ? `, ${rungAt(sliderValue)!.name}` : ''}`}
          />
        </div>

        <div className="space-y-1 rounded-md border p-3">
          <p className="text-sm">
            {preview
              ? `Over the last ${preview.days} days at ${preview.level}${previewRung ? ` (${previewRung.name})` : ''}, I would have said ${preview.said}, shown ${preview.shown}, and held ${preview.held}${preview.budget_per_day != null ? `, up to ${preview.budget_per_day} a day` : ''}.`
              : previewError || 'No preview yet.'}
          </p>
          {preview && preview.unclassified > 0 && (
            <p className="text-xs text-muted-foreground">{preview.unclassified} rows I can't place yet, so I haven't counted them.</p>
          )}
          {preview && preview.undated > 0 && (
            <p className="text-xs text-muted-foreground">{preview.undated} rows carry no readable time, so I haven't counted them.</p>
          )}
          {preview && preview.truncated && (
            <p className="text-xs text-muted-foreground">I only read the newest rows; the oldest days may be under-counted.</p>
          )}
          {preview && preview.items.length > 0 && (
            <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-xs">
              {preview.items.map((i) => {
                const live = i.live_outcome
                const disagrees = live != null && (i.verdict === 'said') !== (live === 'speak')
                return (
                  <li key={i.attempt_id} className="grid grid-cols-6 items-baseline gap-2">
                    <span className="col-span-2 truncate text-muted-foreground">{new Date(i.ts).toLocaleString()}</span>
                    <span className="col-span-2 truncate">{SOURCE_COPY[i.source] ?? 'something else'}</span>
                    <span className="capitalize">{i.verdict}</span>
                    <span className="truncate text-muted-foreground">
                      {disagrees ? (live === 'speak' ? 'I said it' : 'I stayed quiet') : ''}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
```

In `BeingTab.tsx`: add `import { PresenceCard } from './PresenceCard'` beside the other component imports, and insert directly *above* the `{/* Proactivity Setting */}` comment (line 492), leaving that card and its `Zap` import exactly as they are (D11):

```tsx
      {/* Presence (spec 2026-09-16 v2 §15). Shadow-only in slice 1: the
          Proactivity card below still governs what is heard (D1, D11). */}
      <PresenceCard level={config.presence ?? 3} saving={saving} onChange={saveConfig} />

```

In `BeingTab.test.tsx` line 29, after `proactivity: 'balanced',` add `presence: 3,`. Its `renderTab()` fetch mock answers any unrecognised URL with `{ status: 'ok' }`, which would make the card inside `BeingTab` render "Over the last undefined days…" during those tests; add two branches above the catch-all `return jsonResponse({ status: 'ok' })` so the renders are deterministic:

```tsx
    if (url === '/api/being/presence/rungs') {
      return jsonResponse({ status: 'ok', rungs: [
        { level: 0, name: 'mute', says: "I'll only speak for what can't wait.", why: 'Nothing interrupts you.', classifiable: true },
        { level: 3, name: 'morning', says: "I'll give you the morning report.", why: 'The default.', classifiable: true },
      ] })
    }
    if (url.startsWith('/api/being/presence/preview')) {
      return jsonResponse({ status: 'ok', level: 3, days: 7, said: 0, shown: 0, held: 0, unclassified: 0, undated: 0, budget_per_day: 3, truncated: false, items: [] })
    }
```

`BeingTab.tsx`'s `saveConfig` renders errors as `` `Error: ${err.detail || 'Failed to save'}` `` (line ~251); a FastAPI 422's `detail` is a list, which renders as `[object Object]` — and the presence fields are `StrictInt`, so a wrong type is exactly a 422. Add beside `saveConfig` a helper and use it at that line (leave the other two `err.detail` sites as they are — not this card's):

```tsx
const errorText = (detail: unknown, fallback: string): string =>
  Array.isArray(detail) ? detail.map((d: any) => d?.msg ?? String(d)).join('; ') : (detail ? String(detail) : fallback)
```

and route **all three** of `BeingTab.tsx`'s `err.detail` toasts through it — `saveConfig` (~251), the persona delete (~231), and `saveSenses` (~742), which POSTs the *same* `/api/settings/being` endpoint and so hits the same 422 — each keeping its own fallback string. `errorText` ends `|| fallback`, so an empty `detail` list cannot produce a bare "Error: ". (`SecurityTab.tsx` carries a fourth copy of the pattern; out of this slice's scope.)

The range input is the dashboard's only `type="range"` and `index.css` sets no `accent-color`, so it would paint in the browser's own blue on a surface whose colour comes only from `shared-tokens/tokens.css`. Add a base rule beside `index.css`'s other element rules, using the primary token as that file already spells it (read the name out of `index.css`/`tokens.css` rather than guessing):

```css
input[type="range"] {
  accent-color: hsl(var(--primary));
}
```

then run `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python scripts/check_contrast.py` from the repo root and report its verdict.

- [ ] **Step 4: Run**

```bash
cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/components/settings/tabs/ && npx tsc --noEmit
```
Expected: PresenceCard `11 passed`; the tabs directory `98 passed` (baseline measured 2026-09-17 in the worktree: 10 files / 87 tests, `tsc --noEmit` exit 0 — so 87 + 11, and BeingTab's own tests unchanged in count); `tsc` clean.

- [ ] **Step 5: Commit**

```bash
cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1 && git add halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/PresenceCard.tsx halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/PresenceCard.test.tsx halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/BeingTab.tsx halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/BeingTab.test.tsx
git commit -m "settings: the presence control — seven rungs as the primary control, a fine adjust, and the preview

Copy is served by the API; the preview re-resolves the last week of the
shadow log at the hovered level so the person can feel the setting before
it acts. Sits above the four-button proactivity card, which still governs
what is heard until slice 2 retires the dial (D1, D11)."
```

---

### Task 23: Whole-suite verification, the spine, push

- [ ] **Step 1: Halbert suite**

```bash
cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1 && PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests -q 2>&1 | tail -3
```
Compare against the Task 13 baseline: the only changes must be new passes. Any new failure is yours; the pre-existing baseline is not.

- [ ] **Step 2: Frontend**

```bash
cd halbert_core/halbert_core/dashboard/frontend && npx vitest run 2>&1 | tail -3 && npx tsc --noEmit && echo tsc-clean
```

- [ ] **Step 3: Engine conformance from Halbert's side** — `test_attunement_curve.py::test_admission_channel_and_patience_agree_with_the_engine_vectors` holds this in the suite since Task 15; run the one-liner once more here as the hand-back proof:

```bash
PYTHONPATH=$HOME/.config/superpowers/worktrees/Haloysius/presence-vector/src arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -c "
from haloysius.attunement.conformance import check_presence
from haloysius.attunement.presence import resolve_presence
from halbert_core.attunement.curve import halbert_curve
from halbert_core.attunement.context import halbert_config
f = check_presence(lambda level, ov: resolve_presence(level, halbert_curve(), halbert_config().attachment, ov))
print('halbert curve agrees with engine vectors:', not f); print('\n'.join(f))
"
```
Expected: `halbert curve agrees with engine vectors: True`

- [ ] **Step 4: Bring the untracked design record into the worktree.** The research passes, spec and this plan live under `documentation/research/presence/` and `documentation/superpowers/` in the MAIN Halbert checkout and are untracked there, so the worktree does not have them. Copy, then they are committed with the spine in Step 6:

```bash
cd ~/.config/superpowers/worktrees/Halbert/presence-slice-1
mkdir -p documentation/research/presence documentation/superpowers
cp -R /Volumes/4TB-BAD/Halbert/documentation/research/presence/. documentation/research/presence/
cp -R /Volumes/4TB-BAD/Halbert/documentation/superpowers/. documentation/superpowers/
```

- [ ] **Step 5: Verify the spec carries D1/D2** (applied 2026-09-17, before the engine's copy): `grep -c 'plan D2' documentation/superpowers/specs/2026-09-16-presence-slider-design.md` prints 1 (§7.2's `level` field) and `grep -c 'Slice 1 is additive' …` prints 1 (§14 Config). The engine's copy under `docs/superpowers/specs/` must be byte-identical to this file. It was stale (the six→seven rung corrections) and was re-copied, committed and pushed on the engine branch as `a466a05` on 2026-09-17; `cmp` the two files once more here and only act if they differ again.

- [ ] **Step 6: The spine** — `DECISIONS.md`, under `## Decided`, appended after the last existing row (the table's recent rows carry an ID column: `| date | \`ID\` | decision | source |`; follow that, not the three-column header):

```
| 2026-09-16 | `PRES-1` | Presence is a 0–10 level resolved through an authored curve into a vector (admission by impulse class, channel ceilings, patience, budget, band shift). Supersedes 2026-08-23 "Proactive dial Off/Quiet/Balanced/Assertive"; `DialLevel` retired in the engine, no shim. Slice 1 is additive on the Halbert side: the live gate reads the dial until slice 2. | presence spec v2 §20 row 1; founder-approved design 2026-09-16 |
| 2026-09-16 | `PRES-2` | `RANDOM` / `TEMPORAL` / `SCENE` thoughts are admissible at the top rung under budget, bounded deferral and the consumer's `AttachmentSafety`; the engine's `_NEVER_SPEAKS` constant is retired in favour of admission. | presence spec v2 §20 row 2 |
| 2026-09-16 | `PRES-3` | Hard off is not on the slider; it remains `WITHDRAW` and Do Not Disturb. Level 0 is soft mute: life safety and criticals still speak. | presence spec v2 §20 row 3 |
| 2026-09-16 | `PRES-4` | The engine ships the strictest curve; each consumer's curve is a reviewed table in its own repo with a named owner. Halbert's curve admits no social affect at any level; a companion consumer's may, under the founder's 2026-09-15 ruling. | presence spec v2 §20 row 4 |
| 2026-09-16 | `PRES-5` | Level 3 is the default and reproduces today's `BALANCED`. | presence spec v2 §20 row 5 |
| 2026-09-16 | `PRES-6` | Every rung above today's `ASSERTIVE` admission set ships shadow-first for two weeks; the gate to slice 2 is a founder review of week 1 vs week 2 per impulse class. | presence spec v2 §20 row 6; §17 |
| 2026-09-16 | `PRES-7` | The only permitted learning is a per-class band offset moved on explicit, consistent reactions from a person — never on inferred silence. | presence spec v2 §20 row 7 |
| 2026-09-16 | `PRES-8` | Unbidden utterances carry a warrant; an `INFERRED` warrant may not be rendered as assertion. | presence spec v2 §20 row 8 |
```

`ROADMAP.md` §3 Now (`| Id | Workstream | Definition of done | Status / evidence | Gating decision |`): add row

```
| PRES-1 | Presence slider, slice 1 | engine contract merged; Halbert runs the vector in shadow beside the dial; seven-rung control + preview live; **gate to slice 2:** two weeks of shadow rows reviewed, week 1 vs week 2 per impulse class (spec §17) | `feat/presence-vector` (engine), `feat/presence-slice-1` (Halbert) | — |
```

- [ ] **Step 7: Commit and push**

```bash
git add DECISIONS.md ROADMAP.md documentation/research/presence documentation/superpowers
git commit -m "spine: presence slider decisions, the slice-1 row, and the design record

Three research passes, the v2 spec and the slice-1 plan, committed with the
rows they justify."
git push -u origin feat/presence-slice-1
```

- [ ] **Step 8: Hand back.** Report: the engine and Halbert suite counts against baseline, `tsc` clean, the conformance line, and — the point of the slice — open Settings › Being, move the control, and read the preview. The two-week shadow review starts the day this lands.
