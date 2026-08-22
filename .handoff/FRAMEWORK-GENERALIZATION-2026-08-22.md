# Haloysius Framework Generalization: State Tracking Beyond Human Personas

**Date:** 2026-08-22
**Origin:** RQ-E audit finding E6 (state renderer is degraded for system predicates) + founder concern that clothing/location hardcoding is the biggest gap in Halbert integration.
**Status:** Design exploration. No decision made. This document maps the problem and evaluates options.

---

## 1. The problem in one paragraph

Haloysius's continuity system has two hardcoded state machines — `ClothingStateMachine` and `LocationStateMachine` — that are wired into `continuity.py`'s `_advance()` function by name. They dual-write to the `TemporalStateLedger` with fixed predicates (`wearing`, `at_location`, `clothing_category`, `location_type`). The state renderer has hardcoded special-case prose for those predicates. The default identity prompt assumes a human body. This works for human-persona chat apps (H2, H3) but is unhelpful for Halbert, which needs system-state tracking (`disk_health`, `service_status`, `thermal_state`) instead of clothing, and has privacy concerns about location. The question is: how do we make Haloysius a general framework that serves both human-persona apps and machine-persona apps without forking the core?

---

## 2. What is hardcoded vs. what is already generic

### Already generic (no change needed)

| Component | Why it's generic |
|-----------|------------------|
| `TemporalStateLedger` | Schema-free SQLite: `subject TEXT, predicate TEXT, object TEXT`. Accepts any triple. `record()` closes previous values rather than overwriting. |
| `Worry` | `category` is a plain string, not an enum. `"disk_failure"` works as well as `"relationship"`. |
| `DriveCategory` | Has `COMFORT`, `SAFETY`, `COMPETENCE`, `AUTONOMY` — these map naturally to machine concepts (thermal comfort, security posture, successful operations, self-modification). |
| `Belief` | `domain` includes `SELF`, `WORLD`. `source` includes `OBSERVATION`. No human-specific assumptions in the data model. |
| `PersonaMemoryStore` | `MemoryType` has `EPISODIC`, `SEMANTIC`, `OBSERVATION` (wait — actually it's `EPISODIC`, `SEMANTIC`, `TACIT`, `EMOTIONAL`, `THINKING`, `INVENTED`). No human-specific types. Content is free text. |
| `PersonaCognition` container | The 4-layer structure (realities, context, prism, experience) is domain-agnostic. The human-ness comes from what you put in it, not the container itself. |

### Hardcoded to human personas (needs attention)

| Component | What's hardcoded | Impact on Halbert |
|-----------|------------------|-------------------|
| `continuity.py` `_advance()` | Imports and calls `update_clothing_from_message` and `update_location_from_message` by name. No registry, no plugin system. | Halbert gets clothing/location parsing it doesn't need. System-state tracking has no entry point. |
| `ClothingStateMachine` | Regex patterns for outfit changes ("wearing a red dress", "takes off jacket"). Clothing categories (casual, formal, sleepwear). Dual-writes `wearing` + `clothing_category` predicates to ledger. | Entirely irrelevant. A machine doesn't wear clothes. |
| `LocationStateMachine` | Regex patterns for movement ("goes to the kitchen", "walks to the park"). Location types (indoor, outdoor, public, private). Dual-writes `at_location` + `location_type` predicates. | Partially relevant (hostname/network is a kind of location) but the regex parsing is conversation-based, not system-based. Privacy concern: the laptop knowing it's "at Starbucks" is a surveillance feature. |
| `state_renderer.py` `_PREDICATE_LABELS` | Maps 10 human predicates to display labels. System predicates fall through to `_label()` fallback (title-cased predicate name). | Functional but degraded — "Disk Health: degraded" instead of natural prose. |
| `state_renderer.py` `_render_natural()` | Special-case prose for `at_location` ("You are at X"), `wearing` ("wearing Y"), `feeling` ("You feel Z"), `current_activity` ("You are Z"). System predicates get generic "Label: value" format. | Functional but reads like a status report, not self-awareness. |
| `state_renderer.py` `_SUBJECT_ORDER` | `["persona", "user", "scene", "world"]` — system subjects like `"disk:/dev/nvme0n1"` sort after these. | Minor — grouping is suboptimal but not broken. |
| `identity.py` `_default_human_identity()` | Hardcoded: "You are a complete human being with a body, memories, and genuine feelings. You have a face, hands, a body you're aware of." | Must be overridden via `human-identity.txt` file. Silent fallback to human identity if file is missing. |
| `PersonaReality` categories | `PHYSICAL_BODY` ("Has no arms"), `SENSORY` ("Is blind"), `PHYSICAL_ABILITY` ("Cannot fly") — human body shaped. | Syntactically works for hardware ("Has 64 GB RAM" in PHYSICAL_BODY) but semantically stretched. |

---

## 3. The design space

### Option A: Pluggable StateTracker Registry

**Concept:** Define a `StateTracker` protocol in Haloysius. Clothing and Location become the default human-persona implementations. Consumers register their own trackers. The continuity module iterates registered trackers instead of hardcoding two.

**What changes:**

```python
# haloysius/persona/state_tracker.py (new)
class StateTracker(Protocol):
    """A state tracker that updates from conversation turns and syncs to the ledger."""
    name: str  # "clothing", "location", "system_health", etc.

    def load(self) -> None: ...
    def update_from_turn(self, persona_id: str, user_message: str,
                         ai_response: str, scene_markers: list[str] | None = None) -> None: ...
    def sync_to_ledger(self) -> None: ...

# haloysius/context/continuity.py (modified)
_trackers: list[StateTracker] = []

def register_state_tracker(tracker: StateTracker) -> None:
    _trackers.append(tracker)

def _advance(persona_id, user_message, ai_response, scene_markers=None):
    for tracker in _trackers:
        try:
            tracker.update_from_turn(persona_id, user_message, ai_response, scene_markers)
        except Exception as e:
            logger.warning(f"State tracker {tracker.name} failed: {e}")
            _continuity_failures += 1

# Default registration (human personas)
register_state_tracker(ClothingStateTracker())
register_state_tracker(LocationStateTracker())
```

**Pros:**
- Clothing and location stay as-is for H2/H3 — no behavior change for existing consumers.
- Halbert registers `SystemHealthTracker`, `ServiceStatusTracker`, `ThermalStateTracker` — each writes its own predicates to the ledger.
- The continuity module becomes truly agnostic — it just iterates trackers.
- Clean separation: Haloysius provides the protocol + default trackers; Halbert provides its own.

**Cons:**
- The state renderer still needs to know about predicates for natural prose. A registry of trackers doesn't solve the rendering problem — the renderer still falls back to label-value pairs for unknown predicates.
- The `StateTracker` protocol's `update_from_turn()` is conversation-centric (takes user_message/ai_response). Halbert's system-state trackers don't update from conversation — they update from system events. The protocol signature doesn't fit.
- Adding a registry is a core change, contradicting the "no core changes" claim (though this is a small, backward-compatible addition).

**Verdict:** Good structural improvement, but doesn't solve the rendering problem or the conversation-vs-event update mismatch.

---

### Option B: Generalized Internal State Layer

**Concept:** Add a new sub-layer to `PersonaCognition` (or as a peer to realities) called "Internal State" — a generic key-value state with typed categories. Clothing and location become the human-persona instances of internal state. System health becomes the machine-persona instance.

**What changes:**

```python
# haloysius/persona/internal_state.py (new)
class InternalStateCategory(str, Enum):
    """Categories of internal state — domain-agnostic."""
    PHYSIOLOGICAL = "physiological"    # Human: clothing, hunger. Machine: disk_health, thermal_state.
    ENVIRONMENTAL = "environmental"    # Human: location, weather. Machine: network, hostname.
    OPERATIONAL = "operational"        # Human: current_activity. Machine: service_status, uptime.
    RELATIONAL = "relational"          # Human: relationship_to_user. Machine: user_session.

@dataclass
class InternalStateEntry:
    category: InternalStateCategory
    key: str               # "clothing", "disk_health", "location", "service_status"
    value: str             # "red dress", "degraded", "Starbucks", "running"
    priority: str = "medium"
    source: str = ""       # "clothing_sm", "smart_monitor", "systemd"
    updated_at: str = ""
```

**The key insight:** "hungry" and "disk-full" are the same kind of thing — an internal state that affects how the persona thinks and acts. The category is the same (`PHYSIOLOGICAL`); the key differs.

**Pros:**
- Conceptually clean — "internal state" is a generalization that covers both human and machine needs.
- The state renderer can be made category-aware: `PHYSIOLOGICAL` states get "I am experiencing X" phrasing regardless of whether X is "hunger" or "disk degradation."
- The clothing/location state machines become adapters that populate `InternalStateEntry` objects — they're not deleted, just reframed.
- Halbert's system monitors become adapters that populate the same structure.
- The `PersonaCognition` container gains a first-class slot for internal state, making it visible to the cognitive tick.

**Cons:**
- This is a core change — new module, new enum, new dataclass, new field on `PersonaCognition`.
- The existing clothing/location state machines would need to be refactored to write `InternalStateEntry` objects instead of (or in addition to) direct ledger writes.
- The state renderer needs to learn the new category-based rendering.
- Risk of over-abstraction — is "internal state" too generic to be useful? The categories help, but the boundary between "internal state" and "realities" is fuzzy (is "I have 64 GB RAM" a reality or an internal state?).

**Verdict:** Conceptually the cleanest, but the most core change. The abstraction risk is real — need to validate that the categories are stable across at least 3 use cases (human-persona, machine-persona, and a hypothetical third) before committing.

---

### Option C: Disable + Direct Ledger Writes (no core change)

**Concept:** Halbert doesn't use the continuity module's `_advance()` at all. It writes directly to the `TemporalStateLedger` from its own event detection layer. The state renderer's fallback handles unknown predicates. No Haloysius core changes.

**What changes:**

```python
# Halbert-side only
# halbert_core/halbert_core/cognition/system_state_writer.py (new)

class SystemStateWriter:
    """Writes system state directly to Haloysius's TemporalStateLedger."""

    def on_disk_event(self, event):
        ledger = get_state_ledger()
        ledger.record(
            persona_id="halbert",
            subject="disk:/dev/nvme0n1",
            predicate="disk_health",
            object="degraded (42 reallocated sectors)",
            source="smart_monitor",
            priority="high",
        )

    def on_service_event(self, event):
        ledger.record(
            persona_id="halbert",
            subject="service:nginx",
            predicate="service_status",
            object="failed",
            source="systemd_monitor",
            priority="critical",
        )
```

**Halbert disables clothing/location by not calling `continuity.advance_from_user_message()` / `advance_from_response()`.** Instead, Halbert's chat handler calls `render_state_block()` directly (which reads the ledger) and writes system state to the ledger from its own event loop.

**Pros:**
- Zero Haloysius core changes. The "no core changes" claim holds.
- Halbert has full control over what predicates it writes and when.
- The state renderer's fallback (`_label()`) produces "Disk Health: degraded" — functional, if not natural prose.
- Fastest to implement — Halbert just writes to the ledger and calls `render_state_block()`.

**Cons:**
- The rendering is degraded — label-value pairs, not natural prose. "Disk Health: degraded" works but "I am experiencing disk degradation on my primary NVMe drive" is better for the self-model.
- Halbert bypasses the continuity module entirely, which means it also bypasses any future improvements to continuity (budget-adaptive rendering, state machine conflict detection, etc.).
- The clothing/location state machines are still imported by `continuity.py` — if Halbert calls `advance_from_user_message()` at all, it gets clothing parsing it doesn't want. Halbert must NOT call the advance functions, only `render_state_block()`.
- No framework improvement — the next non-human consumer has to do the same thing.

**Verdict:** Pragmatic for MVP. Gets Halbert working fastest. But it's a workaround, not a framework improvement. The rendering quality gap is real for the self-model's "I am the computer" identity.

---

### Option D: Hybrid — StateTracker Protocol + Category-Aware Renderer

**Concept:** Combine A and C. Add a `StateTracker` protocol (Option A) so the continuity module is agnostic. Make the state renderer category-aware (Option B's insight) but driven by a predicate-to-category map that consumers can extend, rather than a new cognitive layer.

**What changes:**

```python
# haloysius/persona/state_tracker.py (new — small)
class StateTracker(Protocol):
    name: str
    def update_from_turn(self, persona_id, user_message, ai_response,
                         scene_markers=None) -> None: ...
    def sync_to_ledger(self) -> None: ...

# haloysius/context/continuity.py (modified)
_trackers: list[StateTracker] = []

def register_state_tracker(tracker: StateTracker) -> None:
    """Register a state tracker. Consumers call this at startup."""
    _trackers.append(tracker)

def clear_state_trackers() -> None:
    """Clear all trackers. Consumers that don't want defaults call this first."""
    _trackers.clear()

# Default: clothing + location registered for backward compat
# (existing H2/H3 apps see no change)
register_state_tracker(ClothingStateTrackerAdapter())
register_state_tracker(LocationStateTrackerAdapter())

# haloysius/context/state_renderer.py (modified)
# Add a consumer-extensible predicate category map:
_PREDICATE_CATEGORIES = {
    "wearing": "physiological",
    "at_location": "environmental",
    "feeling": "emotional",
    # ... existing predicates ...
}

def register_predicate_category(predicate: str, category: str,
                                 label: str | None = None,
                                 prose_template: str | None = None) -> None:
    """Let consumers teach the renderer about their predicates.

    prose_template uses {object} as a placeholder:
        "My {label} is {object}"
        "I am experiencing {object}"
    """
    _PREDICATE_CATEGORIES[predicate] = category
    if label:
        _PREDICATE_LABELS[predicate] = label
    if prose_template:
        _PROSE_TEMPLATES[predicate] = prose_template
```

**Halbert's startup:**
```python
# Halbert clears the default human trackers and registers its own
from haloysius.context.continuity import clear_state_trackers, register_state_tracker
from haloysius.context.state_renderer import register_predicate_category

clear_state_trackers()
register_state_tracker(SystemHealthTracker())
register_state_tracker(ServiceStatusTracker())

# Teach the renderer about system predicates
register_predicate_category("disk_health", "physiological",
    label="Disk Health",
    prose_template="My disk health is {object}")
register_predicate_category("service_status", "operational",
    label="Service Status",
    prose_template="Service {subject} is {object}")
register_predicate_category("thermal_state", "physiological",
    label="Thermal State",
    prose_template="My thermal state is {object}")
```

**Pros:**
- Backward compatible — H2/H3 see no change (default trackers + default predicates).
- Halbert gets natural prose rendering for its system predicates via `register_predicate_category()`.
- The continuity module becomes agnostic via the tracker registry.
- The renderer is extensible without a new cognitive layer — it's just a map that consumers populate.
- Core changes are small and additive: one new protocol file, one new registry function in continuity, one new registration function in the renderer. No existing behavior changes unless a consumer calls `clear_state_trackers()`.

**Cons:**
- The `StateTracker.update_from_turn()` signature is still conversation-centric. Halbert's system-state trackers would implement it as a no-op (system state doesn't update from conversation) and update from their own event loop via direct ledger writes. This is a bit awkward — the tracker is registered but doesn't do anything in the turn cycle.
- The prose template approach is limited — `"My disk health is {object}"` can't handle complex objects like `"degraded (42 reallocated sectors)"` gracefully. The template would need conditional logic or the tracker would need to pre-format the object string.
- Two registration mechanisms (trackers for update, predicate categories for rendering) — slightly more moving parts.

**Verdict:** The most balanced option. Small, additive core changes. Backward compatible. Solves both the update path (tracker registry) and the rendering path (predicate category registry). The conversation-vs-event mismatch is the main awkwardness.

---

### Option E: Event-Driven State Trackers (decouple from conversation turns)

**Concept:** The `StateTracker` protocol has two update paths: `update_from_turn()` for conversation-driven state (clothing, location) and `update_from_event()` for externally-driven state (system events). The continuity module calls `update_from_turn()` on each turn; the event loop calls `update_from_event()` when system events arrive.

**What changes:**

```python
class StateTracker(Protocol):
    name: str

    def update_from_turn(self, persona_id, user_message, ai_response,
                         scene_markers=None) -> None:
        """Update from conversation content. No-op for event-driven trackers."""
        ...

    def update_from_event(self, event: dict) -> None:
        """Update from an external event. No-op for conversation-driven trackers."""
        ...

    def sync_to_ledger(self) -> None: ...
```

**Pros:**
- Cleanly separates the two update paths. Clothing/location implement `update_from_turn()`; system health implements `update_from_event()`.
- The continuity module's `_advance()` calls `update_from_turn()` on all trackers — the system trackers no-op, the clothing tracker parses the conversation.
- Halbert's event loop calls `update_from_event()` on system trackers — the clothing tracker no-ops.
- Both paths sync to the same ledger, so `render_state_block()` sees all state.

**Cons:**
- Requires a dispatch mechanism for events — who calls `update_from_event()`? If it's Halbert's event loop, then the tracker needs to be registered with both the continuity module (for turn updates) and Halbert's event loop (for event updates). Two registration points.
- The `event: dict` parameter is untyped — what keys? This could drift into a second protocol or a typed event system.
- More complex than Option D for a problem that might be solved by just having Halbert write directly to the ledger (Option C) and letting the renderer handle it.

**Verdict:** Clean separation of concerns, but may be over-engineered for MVP. The event-driven path could be added later if the conversation-centric tracker proves too limiting.

---

## 4. The rendering problem (independent of the update problem)

Regardless of which update mechanism we choose, the rendering problem remains: how does the state renderer produce natural first-person prose for system predicates?

### Current state

The renderer has three rendering modes (natural, structured, minimal) selected by model tier. The natural mode (`_render_natural()`) has special-case prose for 4 predicates (`at_location`, `wearing`, `feeling`, `current_activity`) and falls back to `"Label: value"` for everything else.

### Rendering options

**R1: Predicate registration (from Option D).** Consumers register prose templates at startup. The renderer looks up the template by predicate and formats it.

```python
register_predicate_category("disk_health", "physiological",
    prose_template="My disk health is {object}")
# Renders: "My disk health is degraded (42 reallocated sectors)"
```

**R2: Category-based rendering.** The renderer groups predicates by category and renders each category with a category-specific template.

```python
# Physiological: "I am experiencing {object}" or "My {key} is {object}"
# Environmental: "I am at {object}" or "My environment is {object}"
# Operational: "{subject} is {object}" or "My {key} is {object}"
```

This is more general but requires the renderer to know the category of each predicate — which means either a registration mechanism (same as R1) or a convention (predicate name implies category).

**R3: LLM-formatted rendering.** The renderer passes raw triples to the LLM and lets it format the state block. This is the most flexible but adds latency and cost to every turn.

**R4: Consumer-provided renderer.** The consumer (Halbert) provides its own `render_state_block()` implementation that knows about system predicates. Haloysius's renderer is bypassed entirely for Halbert.

**Recommendation:** R1 (predicate registration) for MVP. It's the smallest change, backward compatible, and gives Halbert control over how its predicates render. R2 (category-based) is the natural evolution if more consumers arrive. R3 (LLM-formatted) is expensive and R4 (consumer-provided) defeats the purpose of having a shared renderer.

---

## 5. The privacy concern with location

The user raised a valid concern: a laptop knowing it's "at Starbucks" is a surveillance feature. This is specific to the `LocationStateMachine` — it parses conversation text for location clues and records them.

For Halbert, location is different:
- **Machine location** (hostname, IP, network) is legitimate system state — Halbert needs to know its own network identity.
- **Physical location** (GPS, WiFi triangulation, conversation-inferred "at Starbucks") is a privacy concern and should be opt-in, not default.

### Options for location

**L1: Halbert disables location tracking entirely.** Don't register a location tracker. The machine's "location" is its hostname/network identity, written to the ledger as a reality, not as a tracked state.

**L2: Halbert registers a `NetworkIdentityTracker`** that writes `network_identity` and `hostname` predicates to the ledger — but does NOT parse conversation for physical location. This is a different kind of tracker than `LocationStateMachine`.

**L3: Make location tracking opt-in for all consumers.** The default `LocationStateMachine` is only registered if the consumer explicitly enables it. This is a behavior change for H2/H3 — they'd need to explicitly enable location tracking.

**Recommendation:** L1 for MVP. Halbert doesn't need location tracking — its "location" is a static reality (hostname, network), not a tracked state that changes during conversation. L2 is the evolution if Halbert ever needs to track network changes (e.g., "I just connected to a new WiFi network").

---

## 6. The clothing question specifically

Clothing is the clearest case of a human-specific feature that has no machine equivalent. A machine doesn't wear clothes. But the *function* of clothing state — tracking a visible external attribute that changes during interaction — has a machine analog: **configuration state**. The machine's "outfit" is its current configuration profile.

However, this analogy is strained. Configuration state is better tracked through SourcePrep (the config tree index) and the drift detector, not through a conversation-parsing state machine. The clothing state machine's value proposition (parsing "I take off my jacket" from conversation) has no machine equivalent — machines don't narrate their config changes in conversation.

**Recommendation:** Halbert simply doesn't register a clothing tracker. The `ClothingStateMachine` stays in Haloysius for H2/H3. No generalization needed for clothing specifically — it's a human-persona feature with no machine analog. The generalization (Options A/D) is about the *framework* that holds clothing/location/system trackers, not about making clothing itself generic.

---

## 7. What about the identity prompt?

The `_default_human_identity()` fallback is a separate but related issue. If Halbert's `human-identity.txt` file is missing, the persona gets "You are a complete human being with a body, memories, and genuine feelings. You have a face, hands, a body you're aware of." This is a silent failure — no error, just wrong identity.

### Options

**I1: Fail-loud if identity file is missing.** The `IdentityPromptBuilder` raises an error if `human-identity.txt` is not found AND no custom prompts directory is set. This is a behavior change — currently it silently falls back.

**I2: Make the default identity configurable.** Instead of a hardcoded fallback, the default identity is loaded from a package-included file (`haloysius/prompts/default-identity.txt`). Consumers can override the default by shipping their own file in their prompts directory.

**I3: Add a `default_identity` parameter to `IdentityPromptBuilder.__init__()`.** Consumers pass their own default identity text at construction time. If the file is missing, this default is used instead of the hardcoded human identity.

**Recommendation:** I3 is the cleanest — it's a constructor parameter, no file system changes, no behavior change for existing consumers (the default is still the human identity text). Halbert passes its machine identity as the `default_identity` parameter. If the file is missing, Halbert gets machine identity, not human identity.

---

## 8. Evaluation matrix

| Option | Core changes | Backward compat | Solves update path | Solves rendering | Solves identity | Complexity |
|--------|-------------|-----------------|-------------------|-----------------|----------------|------------|
| A: Tracker registry | Small | Yes | Yes | No | No | Low |
| B: Internal state layer | Large | Yes (additive) | Yes | Yes (category-based) | No | High |
| C: Disable + direct writes | None | Yes | Workaround | No (fallback) | No | Lowest |
| D: Hybrid (A + R1) | Small | Yes | Yes | Yes | No | Medium |
| E: Event-driven trackers | Medium | Yes | Yes | No | No | Medium-high |
| + I3: Configurable default identity | Tiny | Yes | — | — | Yes | Trivial |

**Recommended combination for MVP:** **C (disable + direct writes) + I3 (configurable default identity)**

This gets Halbert working with zero core changes to the update path and a trivial change to the identity builder. The rendering is degraded (label-value pairs) but functional. The framework improvement can come later.

**Recommended combination for Phase 2 (framework improvement):** **D (hybrid tracker registry + predicate registration) + I3**

This makes Haloysius a proper framework with pluggable state trackers and extensible rendering. Small, additive, backward-compatible core changes. Halbert and future non-human consumers get natural prose rendering for their predicates.

**Recommended combination for Phase 3+ (if abstraction proves stable):** **B (internal state layer) + I3**

Only if at least 3 consumers exist and the category abstraction is validated. The internal state layer is the conceptually cleanest but carries the most risk of over-abstraction.

---

## 9. The "generalized internal state" insight

The user's intuition — "maybe in Haloysius we could have a generalized internal state (hungry or disk-full for instance)" — is the core insight behind Option B. The observation is that `hungry` and `disk-full` are the same kind of cognitive state:

- Both are **physiological**: they describe the body's internal condition.
- Both **affect attention**: a hungry persona thinks about food; a disk-full machine thinks about cleanup.
- Both **drive behavior**: hunger motivates eating; disk-full motivates cleanup.
- Both **have intensity**: slightly hungry vs. starving; 80% full vs. 99% full.
- Both **change over time**: hunger increases; disk fills up.

The existing `DriveCategory.COMFORT` and `DriveCategory.SAFETY` already capture this generalization at the drive level. The gap is at the state level — there's no generic "I am currently experiencing X" state tracker. The clothing and location state machines are specific instances of this pattern, but they're hardcoded rather than generalized.

The question is whether to generalize now (Option B) or let the pattern emerge from multiple specific implementations (Options A/D first, B later if needed). The software engineering answer is usually "let the pattern emerge" — abstract after you have 3 instances, not before. We have 2 (clothing, location) and a hypothetical 3rd (system health). That's enough to see the pattern but maybe not enough to commit to the abstraction.

---

## 10. Open questions for the founder

1. **MVP vs. framework first?** Do we ship Halbert with the pragmatic workaround (Option C) and improve the framework later? Or do we invest in the framework first (Option D) so Halbert is built on a clean foundation?

2. **Location privacy.** Is the concern about location tracking specific to Halbert (a machine shouldn't infer physical location from conversation), or is it a general concern (H2/H3 also shouldn't track location without opt-in)? If general, should location tracking become opt-in for all consumers?

3. **How many non-human consumers do we expect?** If Halbert is the only one, the framework generalization has limited ROI. If we expect more (IoT devices, game NPCs, autonomous systems), the framework investment pays off.

4. **Is the "internal state" abstraction worth the risk?** Option B is conceptually clean but adds a new cognitive layer. Is the cognitive architecture stable enough to absorb it, or is it still evolving?

5. **The identity fallback.** Should the default identity be human (current behavior) or neutral ("You are an AI assistant")? A neutral default would be safer for all consumers, with human-persona apps overriding to human identity and Halbert overriding to machine identity.

---

## 11. Dependencies on other research

- **RQ-B** (system-state predicates): The predicate extensibility assessment validates that the ledger accepts system predicates. This is confirmed — the ledger is schema-free. The rendering question (how those predicates are displayed) is what this document addresses.

- **RQ-C** (system-event triggers): The event-to-cognitive-trigger mapping is the "update from event" path that Options D/E address. RQ-C maps events to trigger semantics; this document addresses how those triggers reach the state tracking layer.

- **RQ-E** (self-model architecture): The three-layer composition assumes Haloysius can track machine state. This document addresses the gap between that assumption and the hardcoded human-persona state machines.

---

*End of design exploration. Awaiting founder decision on which option to pursue.*
