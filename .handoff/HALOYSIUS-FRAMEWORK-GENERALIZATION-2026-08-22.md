# Haloysius Framework Generalization — Handoff to Haloysius

**Date:** 2026-08-22
**From:** Halbert foundational-realignment research (RQ-E audit, framework generalization design exploration)
**To:** A future session working in the **Haloysius** repo
**Status:** Design approved by founder. This is the implementation handoff.
**Origin docs:**
- `/Volumes/4TB-BAD/Halbert/.handoff/DEEP-RESEARCH-QUESTIONS-2026-08-22.md` (RQ-E + RQ-E audit, sections E2-E10)
- `/Volumes/4TB-BAD/Halbert/.handoff/FRAMEWORK-GENERALIZATION-2026-08-22.md` (full design exploration)

---

## 1. Context in one paragraph

Haloysius is the agnostic chat-engine core shared by three apps: H2, H3 (human-persona chat apps, real names confidential), and Halbert (an AI sysadmin whose identity is "I am the computer"). The state tracking layer — `continuity.py`, `ClothingStateMachine`, `LocationStateMachine`, and `AdaptiveStateRenderer` — is hardcoded to human-persona assumptions. The identity prompt builder has a hardcoded human-body fallback. This works for H2/H3 but blocks Halbert integration. The founder has approved building the correct framework generalization now (not phased). This document specifies the exact changes needed in the Haloysius repo.

---

## 2. The design (what to build)

Four changes, all small and backward-compatible. Existing H2/H3 behavior must not change unless they explicitly opt in to the new mechanisms.

### 2.1. StateTracker protocol + tracker registry in continuity.py

**New file:** `haloysius/persona/state_tracker.py`

```python
"""StateTracker protocol — the framework seam for pluggable state tracking.

A state tracker observes conversation turns (and optionally external events),
updates its internal state, and syncs to the TemporalStateLedger. The
continuity module iterates registered trackers instead of hardcoding
clothing and location.

Existing trackers (ClothingStateMachine, LocationStateMachine) become the
default implementations. Non-human consumers (Halbert) register their own
trackers and clear the defaults.
"""
from __future__ import annotations
from typing import Optional, List, Protocol, runtime_checkable


@runtime_checkable
class StateTracker(Protocol):
    """A state tracker that updates from conversation turns and syncs to the ledger.

    Implementations may be conversation-driven (clothing, location) or
    event-driven (system health, service status). Event-driven trackers
    implement update_from_turn() as a no-op and are updated externally
    via their own event loop, calling sync_to_ledger() directly.
    """

    @property
    def name(self) -> str:
        """Short identifier for logging ('clothing', 'location', 'system_health')."""
        ...

    def update_from_turn(
        self,
        persona_id: str,
        user_message: str,
        ai_response: str,
        scene_markers: Optional[List[str]] = None,
    ) -> None:
        """Update state from a conversation turn.

        Called by continuity._advance() on every turn. Event-driven trackers
        should implement this as a no-op.
        """
        ...

    def sync_to_ledger(self) -> None:
        """Write current state to the TemporalStateLedger.

        Called after update_from_turn() and may also be called independently
        by event-driven trackers after an external event arrives.
        """
        ...
```

**Modified file:** `haloysius/context/continuity.py`

Replace the hardcoded `_advance()` with a tracker registry:

```python
# Module-level registry
_trackers: list[StateTracker] = []

def register_state_tracker(tracker: StateTracker) -> None:
    """Register a state tracker. Consumers call this at startup."""
    _trackers.append(tracker)

def clear_state_trackers() -> None:
    """Clear all registered trackers. Consumers that don't want the
    defaults (clothing, location) call this first, then register their own."""
    _trackers.clear()

def _advance(persona_id: str, user_message: str, ai_response: str,
             scene_markers: Optional[List[str]] = None) -> None:
    for tracker in _trackers:
        try:
            tracker.update_from_turn(persona_id, user_message, ai_response,
                                     scene_markers=scene_markers)
        except Exception as e:
            global _continuity_failures
            _continuity_failures += 1
            logger.warning(f"State tracker '{tracker.name}' failed for {persona_id}: {e}")

# At import time, register the default human-persona trackers so
# existing H2/H3 apps see no behavior change:
from haloysius.persona.clothing_tracker import ClothingStateTracker
from haloysius.persona.location_tracker import LocationStateTracker
register_state_tracker(ClothingStateTracker())
register_state_tracker(LocationStateTracker())
```

**New files:** `haloysius/persona/clothing_tracker.py` and `haloysius/persona/location_tracker.py`

These are thin adapters that wrap the existing state machines and implement the `StateTracker` protocol. The existing `clothing_state_machine.py` and `location_state_machine.py` files stay unchanged — the adapters call their existing `update_*_from_message()` and `_sync_to_ledger()` methods.

```python
# halosysius/persona/clothing_tracker.py
"""ClothingStateTracker — adapter wrapping ClothingStateMachine for the
StateTracker protocol. This is the default human-persona clothing tracker."""
from __future__ import annotations
from typing import Optional, List
from haloysius.persona.clothing_state_machine import update_clothing_from_message


class ClothingStateTracker:
    """StateTracker protocol adapter for clothing state."""

    @property
    def name(self) -> str:
        return "clothing"

    def update_from_turn(self, persona_id: str, user_message: str,
                         ai_response: str, scene_markers: Optional[List[str]] = None) -> None:
        update_clothing_from_message(persona_id, user_message, ai_response,
                                     scene_markers=scene_markers)

    def sync_to_ledger(self) -> None:
        # ClothingStateMachine._sync_to_ledger() is called internally by
        # update_clothing_from_message() via save(). No separate sync needed.
        pass
```

```python
# halosysius/persona/location_tracker.py
"""LocationStateTracker — adapter wrapping LocationStateMachine for the
StateTracker protocol. This is the default human-persona location tracker."""
from __future__ import annotations
from typing import Optional, List
from haloysius.persona.location_state_machine import update_location_from_message


class LocationStateTracker:
    """StateTracker protocol adapter for location state."""

    @property
    def name(self) -> str:
        return "location"

    def update_from_turn(self, persona_id: str, user_message: str,
                         ai_response: str, scene_markers: Optional[List[str]] = None) -> None:
        update_location_from_message(persona_id, user_message, ai_response,
                                     scene_markers=scene_markers)

    def sync_to_ledger(self) -> None:
        # LocationStateMachine._sync_to_ledger() is called internally by
        # update_location_from_message() via save(). No separate sync needed.
        pass
```

**Key constraint:** The existing `clothing_state_machine.py` and `location_state_machine.py` files must NOT be modified. The adapters wrap them. This keeps the existing state machine logic (regex parsing, JSON persistence, dual-write to ledger) untouched and testable independently.

---

### 2.2. Extensible predicate rendering in state_renderer.py

**Modified file:** `haloysius/context/state_renderer.py`

Add a registration function so consumers can teach the renderer about their predicates. The existing `_PREDICATE_LABELS` dict and `_render_natural()` special-case prose stay as the defaults. Registered predicates override or supplement them.

```python
# New module-level structures (alongside existing _PREDICATE_LABELS)
_PROSE_TEMPLATES: Dict[str, str] = {}  # predicate -> prose template with {object}
_SUBJECT_LABELS: Dict[str, str] = {}   # subject -> display label for grouping

def register_predicate(
    predicate: str,
    label: Optional[str] = None,
    prose_template: Optional[str] = None,
) -> None:
    """Teach the renderer about a predicate.

    Args:
        predicate: The ledger predicate string (e.g. "disk_health").
        label: Display label for structured rendering (e.g. "Disk Health").
            If None, the existing fallback (title-cased predicate) is used.
        prose_template: Template for natural rendering, using {object} as a
            placeholder. Examples:
                "My disk health is {object}"
                "Service {subject} is {object}"
            If None, the existing fallback ("Label: value") is used.
    """
    if label is not None:
        _PREDICATE_LABELS[predicate] = label
    if prose_template is not None:
        _PROSE_TEMPLATES[predicate] = prose_template

def register_subject_label(subject: str, label: str) -> None:
    """Teach the renderer a display label for a subject prefix.

    System subjects like "disk:/dev/nvme0n1" or "service:nginx" can be
    given shorter labels for grouping headers. If not registered, the
    full subject string is used.
    """
    _SUBJECT_LABELS[subject] = label
```

**Modify `_render_natural()`** to check `_PROSE_TEMPLATES` before falling back to the existing special-case prose:

```python
def _render_natural(self, grouped: Dict[str, List[StateTriple]]) -> str:
    parts = ["[CURRENT STATE]"]
    if "persona" in grouped:
        has_location = any(t.predicate == "at_location" for t in grouped["persona"])
        location_wearing = []
        feelings = []
        other = []
        for t in grouped["persona"]:
            # NEW: check for registered prose template first
            if t.predicate in _PROSE_TEMPLATES:
                other.append(_PROSE_TEMPLATES[t.predicate].format(
                    object=t.object, subject=t.subject
                ))
            elif t.predicate == "at_location":
                location_wearing.append(f"You are at {t.object}")
            elif t.predicate == "wearing":
                if has_location:
                    location_wearing.append(f"wearing {t.object}")
                else:
                    location_wearing.append(f"You're wearing {t.object}")
            elif t.predicate == "feeling":
                feelings.append(f"You feel {t.object}")
            elif t.predicate == "current_activity":
                feelings.append(f"You are {t.object}")
            else:
                other.append(f"{_label(t.predicate)}: {t.object}")
        # ... rest unchanged ...
```

**Also modify `_group_by_subject()`** to use registered subject labels for grouping. Subjects with a registered label are grouped under that label; unregistered subjects keep the existing ordering (standard subjects first, then alphabetical).

**Key constraint:** The existing rendering for `wearing`, `at_location`, `feeling`, `current_activity` must NOT change. Registered prose templates are checked FIRST, but no one registers those 4 predicates (they're already handled). The registration mechanism is purely additive.

---

### 2.3. Configurable default identity in identity.py

**Modified file:** `haloysius/persona/identity.py`

Add a `default_identity` parameter to `IdentityPromptBuilder.__init__()`:

```python
class IdentityPromptBuilder:
    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        model_name: Optional[str] = None,
        default_identity: Optional[str] = None,  # NEW
    ):
        # ... existing code ...
        self._default_identity = default_identity  # NEW
        self.human_identity = self._load_human_identity()
```

**Modify `_load_human_identity()`** to use the injected default instead of the hardcoded one:

```python
def _load_human_identity(self, content_level: str = "sfw") -> str:
    identity_file = self.prompts_dir / 'human-identity.txt'
    if identity_file.exists():
        return identity_file.read_text()
    # Fallback: use injected default if provided, else the hardcoded human identity
    if self._default_identity is not None:
        return self._default_identity
    return self._default_human_identity()
```

**Key constraint:** If `default_identity` is None (the default), behavior is identical to today — the hardcoded `_default_human_identity()` is used. H2/H3 pass no `default_identity` and see no change. Halbert passes its machine identity text as `default_identity`.

**Also consider:** Rename `_default_human_identity()` to `_default_identity_text()` and update the docstring to say "Default identity prompt if file not found and no default_identity was injected." The method name currently says "human" but with the parameter it's no longer necessarily human. This is a cosmetic rename — low priority but reduces confusion.

---

### 2.4. InternalStateCategory enum (lightweight, for self-documentation)

**New file or addition to `state_tracker.py`:**

```python
class InternalStateCategory(str, Enum):
    """Categories of internal state — domain-agnostic.

    Used by trackers for self-description and by the renderer for
    potential future category-based grouping. Not enforced; trackers
    declare their category for documentation and future use.

    Human-persona examples:
        PHYSIOLOGICAL: clothing, hunger, fatigue
        ENVIRONMENTAL: location, weather, lighting
        OPERATIONAL: current_activity, occupation
        RELATIONAL: relationship_to_user

    Machine-persona examples (Halbert):
        PHYSIOLOGICAL: disk_health, thermal_state, memory_pressure
        ENVIRONMENTAL: network_identity, hostname
        OPERATIONAL: service_status, uptime, config_state
        RELATIONAL: user_session, admin_presence
    """
    PHYSIOLOGICAL = "physiological"
    ENVIRONMENTAL = "environmental"
    OPERATIONAL = "operational"
    RELATIONAL = "relational"
```

This enum is **not enforced** — trackers declare their category for self-documentation and potential future category-based rendering. It does NOT become a field on `PersonaCognition`. It does NOT replace the `PersonaReality` categories. It's a lightweight classification tag that the renderer MAY use in the future for grouping.

**Add `category` as an optional attribute on `StateTracker`:**

```python
@runtime_checkable
class StateTracker(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def category(self) -> InternalStateCategory:
        """What kind of internal state this tracker manages."""
        ...

    def update_from_turn(...) -> None: ...
    def sync_to_ledger(self) -> None: ...
```

The default trackers declare:
- `ClothingStateTracker.category = InternalStateCategory.PHYSIOLOGICAL`
- `LocationStateTracker.category = InternalStateCategory.ENVIRONMENTAL`

---

## 3. What NOT to change

| Component | Why it stays |
|-----------|-------------|
| `clothing_state_machine.py` | Existing logic works for H2/H3. The tracker adapter wraps it. No internal changes. |
| `location_state_machine.py` | Same — wrapped by adapter, not modified. |
| `TemporalStateLedger` (`temporal_graph.py`) | Already schema-free. No changes needed. |
| `PersonaCognition` (`cognition.py`) | No new field. Internal state lives in the ledger, not on the cognition container. |
| `PersonaReality` categories | Keep the existing 8 categories. Halbert uses them with semantic stretch (PHYSICAL_BODY for hardware). No new categories needed for MVP. |
| `DriveCategory`, `Worry`, `Belief`, `EmotionalStateV2` | Already generic enough. No changes. |
| `PersonaMemoryStore` | No changes. The wrapper adapter (Halbert-side) handles dict-to-PersonaMemory conversion. |

---

## 4. Files to create

| File | Purpose |
|------|---------|
| `haloysius/persona/state_tracker.py` | `StateTracker` protocol + `InternalStateCategory` enum |
| `haloysius/persona/clothing_tracker.py` | Adapter wrapping `ClothingStateMachine` |
| `haloysius/persona/location_tracker.py` | Adapter wrapping `LocationStateMachine` |

## 5. Files to modify

| File | Changes |
|------|---------|
| `haloysius/context/continuity.py` | Replace hardcoded `_advance()` with tracker registry. Add `register_state_tracker()`, `clear_state_trackers()`. Register default clothing/location trackers at import time. |
| `haloysius/context/state_renderer.py` | Add `register_predicate()`, `register_subject_label()`. Modify `_render_natural()` to check `_PROSE_TEMPLATES` first. Modify `_group_by_subject()` to use registered subject labels. |
| `haloysius/persona/identity.py` | Add `default_identity` parameter to `__init__()`. Modify `_load_human_identity()` to use injected default. Optionally rename `_default_human_identity()` to `_default_identity_text()`. |

## 6. Tests to update

| Test file | What to verify |
|-----------|----------------|
| `context/tests/test_continuity_integration.py` | Existing tests must pass unchanged (default trackers registered at import). Add new tests: clear_state_trackers() + register custom tracker → only custom tracker runs. |
| `context/tests/test_state_renderer.py` | Existing tests must pass unchanged. Add new tests: register_predicate() with prose_template → natural rendering uses template. Unregistered predicate → fallback (existing behavior). |
| `persona/tests/test_clothing_state_machine.py` | Must pass unchanged (state machine logic untouched). |
| `persona/tests/test_location_state_machine.py` | Must pass unchanged. |
| **New:** `persona/tests/test_state_tracker.py` | Test the protocol: ClothingStateTracker and LocationStateTracker implement it. Custom mock tracker works. clear + register flow. |
| **New:** `context/tests/test_renderer_registration.py` | Test predicate registration, subject label registration, prose template formatting. |

---

## 7. Backward compatibility checklist

Before merging, verify ALL of these:

- [ ] H2/H3 startup with no changes: clothing and location trackers are registered at import time, behavior identical to before.
- [ ] `advance_from_user_message()` and `advance_from_response()` still work without any consumer calling `register_state_tracker()`.
- [ ] `render_state_block()` with no registered predicates produces identical output to before.
- [ ] `IdentityPromptBuilder()` with no `default_identity` parameter produces identical identity text to before.
- [ ] All existing tests pass without modification.
- [ ] `continuity_failure_count()` still increments on tracker failures (the counter logic moves into the registry loop).

---

## 8. What Halbert will do with this (consumer-side, for context)

Halbert's startup code (in the Halbert repo, NOT Haloysius) will:

```python
from haloysius.context.continuity import clear_state_trackers, register_state_tracker
from haloysius.context.state_renderer import register_predicate, register_subject_label
from haloysius.persona.identity import IdentityPromptBuilder

# 1. Clear default human-persona trackers
clear_state_trackers()

# 2. Register machine-persona trackers (Halbert-side implementations)
register_state_tracker(SystemHealthTracker())
register_state_tracker(ServiceStatusTracker())
register_state_tracker(ThermalStateTracker())

# 3. Teach the renderer about system predicates
register_predicate("disk_health", label="Disk Health",
    prose_template="My disk health is {object}")
register_predicate("service_status", label="Service Status",
    prose_template="Service {subject} is {object}")
register_predicate("thermal_state", label="Thermal State",
    prose_template="My thermal state is {object}")
register_predicate("memory_pressure", label="Memory Pressure",
    prose_template="My memory pressure is {object}")

# 4. Configure identity with machine fallback
identity_builder = IdentityPromptBuilder(
    prompts_dir=halbert_prompts_dir,
    default_identity=MACHINE_IDENTITY_TEXT,
)
```

The `SystemHealthTracker`, `ServiceStatusTracker`, etc. are Halbert-side classes that implement the `StateTracker` protocol. They write to the `TemporalStateLedger` from Halbert's event detection layer (discovery engine, config watcher, SMART monitor). Their `update_from_turn()` is a no-op (system state doesn't change from conversation); their `sync_to_ledger()` is called from the event loop.

This is NOT part of the Haloysius work — it's documented here only to show how the framework seams are consumed.

---

## 9. Constraints and conventions

- **Licensing:** Haloysius is MIT. These changes are framework infrastructure, not app-specific. No app names (H2, H3, Halbert) should appear in the Haloysius code or comments. Use "consumer" or "app" as the generic term.
- **Naming:** The `StateTracker` protocol, `InternalStateCategory` enum, and registration functions are the public API. Name them clearly — they're the framework seam.
- **No Halbert imports:** Haloysius must not import from or reference Halbert. The framework is generic; Halbert is one consumer.
- **No human-specific language in new code:** The `StateTracker` protocol docstring should use "conversation-driven" and "event-driven" as the distinction, not "human-persona" and "machine-persona." The `InternalStateCategory` docstring can mention both as examples but should not assume either is the primary use case.
- **Existing human-specific language stays:** The existing `clothing_state_machine.py`, `location_state_machine.py`, and `_default_human_identity()` contain human-specific language. These are the default implementations and their language is correct for their purpose. Do not sanitize them.
- **Test coverage:** New code must have tests. Existing tests must pass unchanged. The backward compatibility checklist (section 7) is a merge gate.

---

## 10. Open questions for the implementer

1. **Import-time registration vs. lazy registration.** The design registers default clothing/location trackers at import time of `continuity.py`. This means importing `continuity` has the side effect of registering trackers. Is this acceptable, or should registration be explicit (a `register_default_trackers()` function that H2/H3 call at startup)? Import-time registration is simpler for backward compat (no H2/H3 changes needed) but has the side-effect smell. **Recommendation:** import-time registration, with `clear_state_trackers()` available for consumers that want to start clean. Document the side effect in the module docstring.

2. **`sync_to_ledger()` on the protocol.** The clothing/location adapters implement `sync_to_ledger()` as a no-op because their underlying state machines sync internally during `update_from_turn()`. Is this confusing? Should the protocol instead have `update_from_turn()` return a bool indicating whether it synced, or should `sync_to_ledger()` be removed from the protocol entirely? **Recommendation:** keep `sync_to_ledger()` on the protocol. Event-driven trackers need it (they sync after external events, not during turns). The no-op implementation for conversation-driven trackers is fine and documented.

3. **Subject label grouping.** The current `_group_by_subject()` uses `_SUBJECT_ORDER = ["persona", "user", "scene", "world"]`. System subjects like `"disk:/dev/nvme0n1"` sort after these. Should registered subject labels create new groups, or should they be collapsed under an existing group (e.g., all `disk:*` subjects under a "Disks" group)? **Recommendation:** for MVP, keep the existing grouping behavior. Registered subject labels are used for display in the group header, not for creating new groups. Group restructuring is a future enhancement if the output is unreadable with many system subjects.

4. **Prose template complexity.** The `{object}` and `{subject}` placeholders in prose templates are simple string formatting. Should the template system support conditionals (e.g., different text for "degraded" vs. "healthy")? **Recommendation:** no. If a tracker needs conditional rendering, it should pre-format the object string before writing to the ledger (e.g., write "degraded — 42 reallocated sectors" as the object, not just "degraded"). The template is a formatting wrapper, not a logic engine.

---

## 11. Sequencing

1. **Create `state_tracker.py`** — the protocol + enum. No dependencies.
2. **Create `clothing_tracker.py` and `location_tracker.py`** — adapters wrapping existing state machines. Depend on step 1.
3. **Modify `continuity.py`** — tracker registry, replace hardcoded `_advance()`, register defaults at import. Depends on steps 1-2.
4. **Modify `state_renderer.py`** — predicate registration, prose template lookup. Independent of steps 1-3.
5. **Modify `identity.py`** — `default_identity` parameter. Independent of steps 1-4.
6. **Write tests** — protocol tests, registration tests, backward compat tests. Depends on all above.
7. **Run full test suite** — verify backward compatibility checklist (section 7).

Steps 1-3 can be done as one unit. Steps 4 and 5 are independent and can be done in parallel. Step 6 depends on all.

---

## 12. What this unblocks

Once this Haloysius work is done:

- **Halbert Phase 4** can proceed: Halbert registers its own trackers, predicates, and identity at startup. The self-model architecture from RQ-E becomes implementable without workarounds.
- **Future non-human consumers** (IoT, game NPCs, autonomous systems) can use the same framework without forking.
- **H2/H3** see no behavior change — the default trackers and default identity are unchanged.

---

*End of handoff. The implementer should read the origin docs (section: Origin docs) for full context on why each change is needed, but this document is self-contained for implementation.*
