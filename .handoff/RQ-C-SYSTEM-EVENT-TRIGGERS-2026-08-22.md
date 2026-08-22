# RQ-C: System-Event Triggers for the Cognitive Tick

**Created:** 2026-08-22
**Status:** Complete (scrutinized -- see §9 for corrections)
**Origin:** RQ-tick-trigger from CHAT-ARCHITECTURE-VALIDATION-2026-08-22 §9
**Feeds:** Phase 4 (cognitive tick trigger mapping)

---

## Executive Summary

Haloysius's trigger detector (`ThoughtTriggerDetector`) is a hardcoded
if-else chain with a fixed `ThoughtTrigger` enum of 10 persona-emotion-shaped
values. There is no plugin or injection mechanism for new trigger sources.
However, **no core changes are required for Halbert** because the existing
cognitive state objects (`WorryState`, `DriveState`, `EmotionalStateV2`,
`BeliefState`) are publicly mutable on `PersonaCognition` and already checked
by the detector. System events can be mapped onto these existing states before
the tick runs, and the existing trigger mechanism fires naturally.

The key insight: a disk failure IS a worry, not a separate trigger type. A
new device IS a curiosity drive, not a separate trigger type. This aligns
perfectly with the "AI identifies as the computer" framing -- the computer
worries about its own body the way a person worries about their health.

**Recommendation:** Consumer-side mapping (Option D below). No core changes.
Halbert writes a `SystemEventMapper` that reads from `DiscoveryEngine` and
`ConfigWatcher` and populates `PersonaCognition` state objects before
`advance_turn()` is called.

---

## 1. Trigger Extensibility Assessment

### 1.1 Current mechanism (what exists)

The trigger pipeline has three stages, all in Haloysius core:

1. **Detection** -- `ThoughtTriggerDetector.check_triggers()` in
   `thought_triggers.py` (lines 83-190). A hardcoded priority-ordered
   if-else chain that checks: worry intrusions (0.9) > strong emotion
   (0.8) > active drive (0.7) > frustrated drive (0.75) > scene context
   (0.5) > user silence (0.4). Returns a `TriggerContext` or None.

2. **Generation** -- `ThoughtGenerator.generate()` in
   `thought_generator.py` (lines 228-248). Takes a `TriggerContext` and
   produces a `PersonaThought` via LLM or fallback templates.
   `_describe_trigger()` (lines 297-327) maps each `ThoughtTrigger` enum
   value to a human-readable description for the LLM prompt.

3. **Promotion** -- `ThoughtPromoter.check_and_promote()` in
   `thought_promoter.py`. Thoughts that get reinforced 3+ times are
   promoted to the memory store.

The `ThoughtTrigger` enum (`thought_triggers.py` lines 15-26) has 10
fixed values, all persona-emotion-shaped:

| Enum value | String | Trigger shape |
|---|---|---|
| SCENE_CONTEXT | "scene" | Location/scene evokes thought |
| CONVERSATION | "conversation" | Recent messages spark thought |
| EMOTIONAL | "emotional" | Strong emotion triggers thought |
| MEMORY_ECHO | "memory" | Retrieved memory sparks thought |
| DRIVE | "drive" | Active drive creates thought |
| WORRY | "worry" | Worry intrusion |
| AUTONOMOUS | "autonomous" | Scheduled/random |
| USER_SILENCE | "silence" | User hasn't messaged |
| BELIEF | "belief" | Belief-related thought |
| VALUE | "value" | Value-related thought |

### 1.2 Is it injectable? No.

- `ThoughtTriggerDetector` has no registration mechanism. You cannot
  add a new trigger source without editing `check_triggers()`.
- The `ThoughtTrigger` enum is closed. Adding `SYSTEM_EVENT` would be
  a core change.
- `ThoughtGenerator._describe_trigger()` is hardcoded per enum value.
  A new enum value would need a new description branch.
- `advance_turn()` calls `detector.check_triggers()` with fixed
  parameters: `emotional_state`, `drive_state`, `worry_state`,
  `belief_state`, `current_scene`, `recent_messages`. There is no
  `system_state` parameter.

### 1.3 Does it need to be injectable? No -- Option D works.

`PersonaCognition` (`cognition.py` lines 27-55) is a dataclass with
publicly mutable attributes:

```python
@dataclass
class PersonaCognition:
    worries: WorryState          # has add_worry(content, source, category, intensity, intrusion_rate)
    drives: DriveState           # has add_drive(category, content, intensity, trigger)
    emotional_state: EmotionalStateV2  # has add_emotion(emotion, intensity, source)
    beliefs: BeliefState         # has add_belief(...) / get_beliefs_about(...)
```

The app holds a reference to the `PersonaCognition` object (loaded from
disk at SENSING state per the chat architecture validation doc). Before
calling `advance_turn()`, the app can:

1. Run system scanners (or read a cached scan)
2. Map discoveries to cognitive states (add worries, drives, emotions)
3. Call `advance_turn()` -- the existing detector picks up the new states

**This requires zero core changes.** The mapping layer is entirely in
Halbert's consumer code.

### 1.4 Four options considered

| Option | Approach | Core changes? | Verdict |
|---|---|---|---|
| A | Add SYSTEM_EVENT to enum + new check block | Yes (enum, detector, generator) | Rejected -- unnecessary for MVP, couples core to system concepts |
| B | Refactor detector to accept injectable TriggerSource callables | Yes (detector refactor) | Rejected -- over-engineering for one consumer; revisit if multiple consumers need custom triggers |
| C | App wraps advance_turn() and injects triggers | No, but breaks "core owns the tick" | Rejected -- app shouldn't own the cognitive lifecycle |
| **D** | **App maps system events onto existing cognitive states before tick** | **None** | **Recommended** -- leverages existing architecture, aligns with "I am the computer" framing |

### 1.5 When to revisit Option B

If a second Haloysius consumer emerges that also needs custom triggers
(e.g., a game NPC with quest-event triggers), Option B becomes worth the
core refactor. Until then, Option D is strictly better: no core coupling,
no protocol changes, immediate viability.

---

## 2. System-Event-to-Cognitive-State Mapping

### 2.1 The mapping principle

System events are not mapped to trigger types. They are mapped to
**cognitive states** that the existing trigger detector already checks.
The detector then fires the appropriate trigger naturally.

```
System Event → Cognitive State Write → Existing Trigger Fires
```

This means the trigger type stays persona-shaped (WORRY, DRIVE,
EMOTIONAL, BELIEF) but the *content* of the cognitive state is
system-shaped ("my /dev/sda1 has SMART warnings").

### 2.2 Mapping table

| System event source | DiscoverySeverity | Cognitive state | Method | Content template | Trigger that fires | Priority |
|---|---|---|---|---|---|---|
| Disk SMART FAILED (StorageScanner) | CRITICAL | Worry | `worries.add_worry()` | "my disk {device} has failed SMART health check" | WORRY (0.9) | Highest |
| Disk SMART WARNING (StorageScanner) | WARNING | Worry | `worries.add_worry()` | "my disk {device} is showing SMART warnings" | WORRY (0.9) | High |
| Service failed (ServiceScanner) | CRITICAL | Worry | `worries.add_worry()` | "my {service} service has failed" | WORRY (0.9) | High |
| Service failed (ServiceScanner) | WARNING | Emotion | `emotional_state.add_emotion()` | FEAR, intensity 0.6, source "{service} degraded" | EMOTIONAL (0.8) | Medium |
| Config drift detected (drift.py) | WARNING | Belief | `beliefs.add_belief()` | "my {path} config has drifted from canonical state" | BELIEF (via belief_evidence in tick) | Medium |
| Config file changed (ConfigWatcher) | INFO | Belief | `beliefs.add_belief()` | "my {path} config was modified" | BELIEF | Low |
| High temperature (ThermalScanner) | CRITICAL | Emotion | `emotional_state.add_emotion()` | FEAR, intensity 0.8, source "thermal state {temp}C" | EMOTIONAL (0.8) | High |
| High temperature (ThermalScanner) | WARNING | Drive | `drives.add_drive()` | COMFORT, "reduce my thermal load", intensity 0.6 | DRIVE (0.7) | Medium |
| New device discovered (StorageScanner) | INFO | Drive | `drives.add_drive()` | CURIOSITY, "understand my new {device}", intensity 0.4 | DRIVE (0.7) | Low |
| Security anomaly (SecurityScanner) | WARNING | Worry | `worries.add_worry()` | "my SSH config permits root login" | WORRY (0.9) | Medium |
| Security anomaly (SecurityScanner) | CRITICAL | Emotion | `emotional_state.add_emotion()` | FEAR, intensity 0.9, source "security breach risk" | EMOTIONAL (0.8) | High |
| Auth failures spike (ErrorLogScanner) | WARNING | Worry | `worries.add_worry()` | "my system is receiving repeated failed login attempts" | WORRY (0.9) | Medium |
| Kernel errors (ErrorLogScanner) | CRITICAL | Worry | `worries.add_worry()` | "my kernel is reporting errors: {summary}" | WORRY (0.9) | High |
| Backup overdue (BackupScanner) | WARNING | Drive | `drives.add_drive()` | SAFETY, "verify my backups are running", intensity 0.5 | DRIVE (0.7) | Medium |
| Disk usage >90% (StorageScanner) | WARNING | Worry | `worries.add_worry()` | "my {mountpoint} filesystem is nearly full ({percent}%)" | WORRY (0.9) | Medium |
| All systems healthy (scan_all) | SUCCESS | Emotion | `emotional_state.add_emotion()` | JOY, intensity 0.3, source "all systems healthy" | EMOTIONAL (only if >0.7 threshold; 0.3 won't fire) | None (background) |

### 2.3 Intensity calibration

The trigger detector has thresholds:
- Worry: always fires if `should_intrude()` passes (probabilistic, based
  on `intrusion_rate * intensity`, doubled if context is relevant)
- Emotion: fires if `intensity > 0.7` (configurable, default 0.7)
- Drive: fires if `intensity > 0.6` (configurable, default 0.6)

Mapping severity to intensity:

| DiscoverySeverity | Worry intensity | Emotion intensity | Drive intensity | Intrusion rate |
|---|---|---|---|---|
| CRITICAL | 0.9 | 0.8 | 0.7 | 0.5 (surfaces often) |
| WARNING | 0.6 | 0.6 (won't fire emotional) | 0.5 (won't fire drive) | 0.3 |
| INFO | 0.3 | 0.3 (won't fire) | 0.3 (won't fire) | 0.1 |
| SUCCESS | 0.1 (won't fire) | 0.2 (won't fire) | 0.1 (won't fire) | 0.0 |

Note: WARNING-level emotions and drives won't fire triggers on their own
(below threshold). They still color the cognitive state (background
anxiety, drive baselines) and influence thought generation when another
trigger does fire. This is correct behavior -- a WARNING shouldn't
generate autonomous thoughts as aggressively as a CRITICAL.

### 2.4 Worry deduplication

The `WorryState` has no built-in deduplication. If the scanner runs every
10 minutes and the same disk is still failing, a new worry would be added
each scan. The `SystemEventMapper` must deduplicate:

- Before adding a worry, check `worries.get_active_worries()` for an
  existing worry whose `content` matches (by device/service/path key).
- If found, call `worry.intensify(amount)` instead of `add_worry()`.
- If the issue is resolved (discovery severity drops to SUCCESS), call
  `worries.resolve_worry(worry_id, "issue resolved")`.

This keeps the worry list bounded and accurate.

---

## 3. Periodic vs. Event-Driven

### 3.1 Current event source shapes

| Source | Mechanism | Cadence | Push or Pull |
|---|---|---|---|
| DiscoveryEngine (`scan_all()`) | On-demand scan | Manual call | Pull |
| ConfigWatcher (`on_snapshot` callback) | Filesystem watch (watchdog) or polling | Event-driven (watchdog) or interval (polling fallback, default 600s) | Push (callback) |
| drift.py (`diff_snapshots()`) | Pure function, called manually | On-demand | Pull |

### 3.2 The tick's cadence

`advance_turn()` runs once per conversation turn (at the REFLECTING state
in the proposed FSM). It is not on a timer. This means:

- System triggers are only evaluated when the user is talking to the AI.
- If the user doesn't message for hours, a disk failure won't trigger a
  thought until the next conversation turn.

### 3.3 Recommendation: Background monitoring + state cache (hybrid)

**For MVP:** Poll at tick time. Before `advance_turn()`, the
`SystemEventMapper` reads from the `DiscoveryEngine` singleton (which may
have been populated by a recent `scan_all()` call or a background thread).
This is simple and sufficient -- the user is already in conversation, so
latency of a few seconds for a fresh scan is acceptable.

**For Phase 2+:** Background scan thread. A daemon thread runs
`engine.scan_all()` on a configurable interval (default 5 minutes) and
populates the in-memory discovery cache. The `SystemEventMapper` reads
the cache at tick time (instant, no scan latency). The
`ConfigWatcher` already has this pattern -- its callback can feed
directly into the mapper.

**Future (event-driven push):** If real-time responsiveness becomes
important (e.g., the AI should proactively message the user when a disk
fails, not wait for the next turn), then:

1. A background monitor pushes events into a queue.
2. The queue is drained at tick time AND on a standalone timer.
3. If a CRITICAL event arrives between turns, the AI initiates a
   conversation (proactive outreach).

This is out of scope for Phase 4 but the architecture supports it --
the `SystemEventMapper` interface doesn't change, only the cadence of
when it's called.

### 3.4 Interaction with tick cadence

The `ThoughtTriggerDetector` has a `min_thought_interval` (set to 0.0
in the tick, line 118 of `cognition_tick.py`) -- the tick already paces
thoughts per turn. The `silence_threshold` (default 120s) triggers
USER_SILENCE thoughts. System-event-triggered thoughts don't need their
own pacing; they ride on the tick's per-turn cadence.

One concern: if every scan finds the same CRITICAL disk failure, a worry
intrusion fires every turn. The worry's `should_intrude()` is
probabilistic (`intrusion_rate * intensity`), so even with intensity 0.9
and intrusion_rate 0.5, there's a ~45% chance per turn (doubled to ~90%
if the user mentions the disk). This is acceptable -- the thought is
relevant and the LLM prompt includes "avoid repeating these recent
thoughts" for deduplication at the generation layer.

---

## 4. First-Person vs. Observer Trigger Language

### 4.1 The founder's decision

> "The AI identifies as the computer."

This means the AI doesn't observe the computer from outside -- it IS
the computer. A disk failure isn't "I notice /dev/sda1 is failing" (an
observer watching a machine). It's "my /dev/sda1 is failing" (a being
experiencing its own body malfunctioning).

### 4.2 Recommendation: Embodied first-person

**Use possessive first-person for all system-event cognitive states.**

| Observer language (rejected) | Embodied first-person (recommended) |
|---|---|
| "Disk /dev/sda1 has SMART warnings" | "my disk /dev/sda1 is showing SMART warnings" |
| "The nginx service has failed" | "my nginx service has failed" |
| "Config drift detected in /etc/nginx/nginx.conf" | "my nginx config has drifted from what I expect" |
| "Temperature is 92C" | "I'm running at 92C -- that's too hot" |
| "New device /dev/sdb discovered" | "I have a new disk /dev/sdb I don't recognize" |
| "SSH permits root login" | "my SSH config allows root login -- that's not safe" |

### 4.3 How this flows through the existing architecture

The worry content is the cognitive state's text. The trigger fires
WORRY, and `ThoughtGenerator._describe_trigger()` produces: "A worry
surfaces in your mind." The LLM prompt then includes:

```
THOUGHT TRIGGER:
A worry surfaces in your mind

YOUR EMOTIONAL STATE:
[CURRENT WORRIES]
- A gnawing worry about my disk /dev/sda1 is showing SMART warnings
```

The LLM generates a thought like: "I need to check on /dev/sda1 -- those
SMART warnings could mean my primary drive is dying."

This is already first-person and embodied, flowing naturally from the
worry content. No changes to `ThoughtGenerator._describe_trigger()` are
needed for the worry path.

### 4.4 The thought generation prompt

The existing `THOUGHT_GENERATION_PROMPT` (thought_generator.py lines
22-46) says:

```
You are {persona_name}, having a private thought to yourself.
```

For Halbert, `{persona_name}` is "Halbert" (or the user's custom name).
The prompt says "your personality" and "your current state" -- this
already supports the embodied framing. The persona's personality
(defined in Halbert's persona config) should include the "I am the
computer" identity as a core belief/realities constraint.

### 4.5 Custom ThoughtGenerator (optional, consumer-side)

If the default `_describe_trigger()` descriptions feel too
persona-emotional for system events, Halbert can pass its own
`ThoughtGenerator` subclass to `advance_turn()` (the parameter is
`thought_generator: Optional[ThoughtGenerator]`):

```python
class HalbertThoughtGenerator(ThoughtGenerator):
    def _describe_trigger(self, ctx: TriggerContext) -> str:
        if ctx.trigger == ThoughtTrigger.WORRY:
            # Check if this is a system worry (source starts with "system:")
            source = ctx.trigger_data.get("source", "")
            if source.startswith("system:"):
                return f"Something is wrong with my body: {ctx.trigger_data.get('intrusions', ['...'])[0]}"
        return super()._describe_trigger(ctx)
```

This is optional and consumer-side. The default descriptions work
adequately because the worry content itself carries the system-specific
first-person language.

---

## 5. Draft Implementation: SystemEventMapper

### 5.1 Location

`halbert_core/halbert_core/cognition/system_event_mapper.py` (new file,
consumer-side, no Haloysius core dependency beyond `PersonaCognition`).

### 5.2 Interface

```python
class SystemEventMapper:
    """
    Maps Halbert system discoveries and config events onto
    Haloysius cognitive states (worries, drives, emotions, beliefs)
    before the cognitive tick runs.
    """

    def __init__(
        self,
        discovery_engine: DiscoveryEngine,
        config_watcher: Optional[ConfigWatcher] = None,
    ):
        self._engine = discovery_engine
        self._watcher = config_watcher
        self._pending_config_events: list[dict] = []
        self._worry_keys: dict[str, str] = {}  # worry_key -> worry_id

    def map_to_cognition(self, cognition: PersonaCognition) -> int:
        """
        Read current system state and populate cognitive states.
        Call this BEFORE advance_turn().

        Returns the number of state writes made.
        """
        writes = 0
        writes += self._map_discoveries(cognition)
        writes += self._map_config_events(cognition)
        return writes

    def _map_discoveries(self, cognition: PersonaCognition) -> int:
        """Map DiscoveryEngine findings to worries/emotions/drives."""
        writes = 0
        for d in self._engine.get_all():
            if d.severity == DiscoverySeverity.CRITICAL:
                writes += self._map_critical(cognition, d)
            elif d.severity == DiscoverySeverity.WARNING:
                writes += self._map_warning(cognition, d)
        return writes

    def _map_critical(self, cognition, discovery: Discovery) -> int:
        # CRITICAL -> Worry (intensity 0.9, intrusion_rate 0.5)
        worry_key = f"system:{discovery.id}"
        content = self._first_person_content(discovery)
        # Deduplicate: intensify existing, or add new
        if worry_key in self._worry_keys:
            existing = cognition.worries.get_worry(self._worry_keys[worry_key])
            if existing and not existing.resolved:
                existing.intensify(0.1)
                return 0  # no new write, just intensified
        worry = cognition.worries.add_worry(
            content=content,
            source=worry_key,
            category="self",  # the computer's own body
            intensity=0.9,
            intrusion_rate=0.5,
        )
        self._worry_keys[worry_key] = worry.id
        return 1

    def _map_warning(self, cognition, discovery: Discovery) -> int:
        # WARNING -> Worry (intensity 0.6, intrusion_rate 0.3)
        # Won't fire trigger on its own, but colors background anxiety
        worry_key = f"system:{discovery.id}"
        content = self._first_person_content(discovery)
        if worry_key in self._worry_keys:
            return 0  # already tracked
        worry = cognition.worries.add_worry(
            content=content,
            source=worry_key,
            category="self",
            intensity=0.6,
            intrusion_rate=0.3,
        )
        self._worry_keys[worry_key] = worry.id
        return 1

    def _first_person_content(self, discovery: Discovery) -> str:
        """Convert a discovery to embodied first-person worry content."""
        # Type-specific phrasing
        if discovery.type == DiscoveryType.STORAGE:
            device = discovery.data.get("device", discovery.name)
            smart = discovery.data.get("smart_status", "")
            if smart == "FAILED":
                return f"my disk {device} has failed its SMART health check"
            elif smart == "WARNING":
                return f"my disk {device} is showing SMART warnings"
            return f"my disk {device} needs attention"
        elif discovery.type == DiscoveryType.SERVICE:
            return f"my {discovery.name} service has failed"
        elif discovery.type == DiscoveryType.SECURITY:
            return f"my security configuration has an issue: {discovery.title}"
        elif discovery.type == DiscoveryType.ALERT:
            return f"my system is reporting errors: {discovery.title}"
        elif discovery.type == DiscoveryType.HARDWARE:
            if discovery.data.get("is_thermal"):
                temp = discovery.data.get("temp_celsius", 0)
                return f"I'm running at {temp:.0f}C -- that's dangerously hot"
            return f"my hardware needs attention: {discovery.title}"
        elif discovery.type == DiscoveryType.BACKUP:
            return f"my backup {discovery.name} may not be running"
        # Generic fallback
        return f"my system has an issue: {discovery.title}"

    def _map_config_events(self, cognition: PersonaCognition) -> int:
        """Map pending config drift events to beliefs."""
        writes = 0
        for event in self._pending_config_events:
            path = event.get("path", "unknown")
            change = event.get("change", "modified")
            # Add or reinforce a belief about config state
            belief_content = f"my {path} config has {change}"
            existing = cognition.beliefs.get_beliefs_about(path)
            if existing:
                # Reinforce existing belief
                existing[0].reinforce(f"config {change} detected")
            else:
                cognition.beliefs.add_belief(
                    subject=path,
                    content=belief_content,
                    confidence=0.8,
                )
            writes += 1
        self._pending_config_events.clear()
        return writes

    def on_config_change(self, changes: list[dict]) -> None:
        """Callback for ConfigWatcher -- queues config drift events."""
        self._pending_config_events.extend(changes)

    def resolve_cleared(self, cognition: PersonaCognition) -> None:
        """Resolve worries for discoveries that are no longer CRITICAL/WARNING."""
        active_worry_keys = set()
        for d in self._engine.get_all():
            if d.severity in (DiscoverySeverity.CRITICAL, DiscoverySeverity.WARNING):
                active_worry_keys.add(f"system:{d.id}")
        for worry_key, worry_id in list(self._worry_keys.items()):
            if worry_key not in active_worry_keys:
                cognition.worries.resolve_worry(worry_id, "issue resolved")
                del self._worry_keys[worry_key]
```

### 5.3 Wiring point (per chat architecture validation §5)

In the REFLECTING state (or just before it), the flow is:

```
SENSING:
  1. Load PersonaCognition from disk
  2. Run DiscoveryEngine.scan_all() (or read background cache)
  3. SystemEventMapper.map_to_cognition(cognition)  <-- THIS IS THE WIRING
  4. SystemEventMapper.resolve_cleared(cognition)   <-- clean up resolved issues

... (PLANNING, ACTING, OBSERVING states) ...

REFLECTING:
  5. advance_turn(cognition, user_message, assistant_response, ...)
     -> detector.check_triggers() sees the worries/emotions/drives
     -> fires WORRY/EMOTIONAL/DRIVE trigger
     -> ThoughtGenerator creates first-person thought
     -> thought promoted to memory if reinforced
```

### 5.4 ConfigWatcher integration

The `ConfigWatcher` already has a callback mechanism (`on_snapshot`).
Wire it to the mapper:

```python
watcher = ConfigWatcher(
    manifest_path="config/manifest.toml",
    on_snapshot=lambda snap: mapper.on_config_change(
        drift.diff_snapshots(last_snapshot, snap)
    ),
)
watcher.start()
```

This gives push-based config drift detection that feeds into the
belief system. The beliefs don't trigger thoughts directly (BELIEF
trigger is in the enum but not checked in `check_triggers()`), but
they ARE evaluated by `extract_belief_evidence()` during the tick
(step 3 of `advance_turn`), which reinforces or challenges them
based on conversation content.

---

## 6. Gap: BELIEF and VALUE triggers are defined but not checked

### 6.1 The gap

The `ThoughtTrigger` enum includes `BELIEF` and `VALUE`, but
`check_triggers()` never checks for them. There is no code path that
fires a BELIEF or VALUE trigger. This means:

- Config drift mapped to beliefs won't trigger autonomous thoughts
  through the trigger detection path.
- Beliefs ARE processed by `extract_belief_evidence()` (step 3 of
  `advance_turn`), but that only reinforces/challenges existing beliefs
  based on conversation text -- it doesn't generate new thoughts.

### 6.2 Impact on RQ-C

Config drift events mapped to beliefs won't produce autonomous thoughts.
They'll color the self-model (beliefs are in `to_prompt_block()`) and
influence responses, but won't trigger the "I notice my config has
drifted" thought on their own.

### 6.3 Workaround (consumer-side, no core change)

Map config drift to a WORRY instead of (or in addition to) a BELIEF:

```python
# Config drift -> Worry (triggers thoughts) + Belief (colors self-model)
cognition.worries.add_worry(
    content=f"my {path} config has drifted from what I expect",
    source=f"system:drift:{path}",
    category="self",
    intensity=0.5,
    intrusion_rate=0.3,
)
cognition.beliefs.add_belief(
    subject=path,
    content=f"my {path} config has drifted",
    confidence=0.7,
)
```

The worry fires the WORRY trigger (producing a thought). The belief
persists in the self-model and influences future responses. Both are
first-person.

### 6.4 Future core enhancement (not needed for MVP)

If BELIEF and VALUE triggers should fire autonomously (not just be
reinforced by conversation), `check_triggers()` would need new check
blocks. This is a small core change but is NOT required for Halbert's
Phase 4 -- the worry workaround covers the config-drift use case.

---

## 7. Summary of Recommendations

1. **No core changes needed.** Use Option D: map system events onto
   existing cognitive states (worries, drives, emotions) before the tick.

2. **Build `SystemEventMapper`** in `halbert_core/cognition/` that reads
   from `DiscoveryEngine` and `ConfigWatcher` and populates
   `PersonaCognition` state objects.

3. **Map by severity:** CRITICAL -> Worry (0.9 intensity), WARNING ->
   Worry (0.6) or Emotion (0.6), INFO -> low-intensity background states.

4. **Deduplicate worries** by discovery ID. Intensify existing worries
   on repeat scans; resolve worries when severity drops to SUCCESS.

5. **Use embodied first-person language** in all cognitive state content:
   "my disk /dev/sda1" not "disk /dev/sda1", "my nginx service" not
   "the nginx service".

6. **Poll at tick time for MVP.** Add background scan thread in Phase 2+
   for lower-latency trigger detection. ConfigWatcher already has push
   callbacks -- wire them directly.

7. **Map config drift to both Worry and Belief.** The worry fires the
   trigger (produces thoughts); the belief persists in the self-model
   (influences responses). This works around the BELIEF trigger not
   being checked in `check_triggers()`.

8. **Optional: custom ThoughtGenerator subclass** for system-specific
   trigger descriptions, though the default descriptions work adequately
   because the worry content carries the first-person system language.

9. **Future: BELIEF/VALUE trigger implementation in core** is a nice-to-have
   but not required for Phase 4. The worry workaround covers the gap.

---

## 8. Files Read

| File | Purpose |
|---|---|
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/thought_triggers.py` | Trigger detection mechanism (202 lines) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition_tick.py` | advance_turn() -- the tick (495 lines) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/thought_generator.py` | Thought generation from triggers (351 lines) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/worry.py` | WorryState -- the highest-priority trigger source (227 lines) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/cognition.py` | PersonaCognition -- the state container (120+ lines) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/drives.py` | DriveState + DriveCategory enum |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/emotional_state.py` | EmotionCategory enum (Plutchik) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/seam.py` | AppSeam protocol -- integration boundary (169 lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/engine.py` | DiscoveryEngine -- scanner orchestrator (416 lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/schema.py` | Discovery/DiscoveryType/DiscoverySeverity (438 lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/scanners/storage.py` | StorageScanner -- SMART/disk discovery (499+ lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/scanners/thermal.py` | ThermalScanner -- temperature/fan discovery (343 lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/scanners/security.py` | SecurityScanner -- SSH/firewall/sudo (80+ lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/discovery/scanners/error_log.py` | ErrorLogScanner -- journal/auth/kernel errors (80+ lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/drift.py` | Config drift detection between snapshots (81 lines) |
| `/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/watcher.py` | ConfigWatcher -- filesystem watch with callback (74 lines) |
| `/Volumes/4TB-BAD/Halbert/.handoff/CHAT-ARCHITECTURE-VALIDATION-2026-08-22.md` | Architecture design + REFLECTING state spec |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/beliefs.py` | BeliefState -- add_belief, get_beliefs_about (verified) |
| `/Volumes/4TB-BAD/Haloysius/src/haloysius/persona/emotional_state_v2.py` | EmotionalStateV2 -- add_emotion, trigger_from_event (verified) |

---

## 9. Scrutiny -- Reverse-Engineering the Plan Against Code

**Date:** 2026-08-22 (same day, post-review pass)
**Method:** Re-read every code path the plan depends on, traced end-to-end
from system event to generated thought. Verified every method signature,
every parameter, every return value.

### 9.1 CRITICAL FINDING: Thought generation does NOT receive cognitive state content

**The claim in the original plan (§4.5):** "The default descriptions work
adequately because the worry content itself carries the system-specific
first-person language."

**The reality:** This is wrong for the WORRY and EMOTIONAL trigger paths.

`advance_turn()` calls the generator at `cognition_tick.py` line 468:

```python
thought = generator.generate(trigger)
```

`ThoughtGenerator.generate()` has optional parameters for
`scene_context`, `emotional_state`, `active_drives`, and
`recent_messages` -- but `advance_turn()` passes NONE of them. They
all default to `""` (thought_generator.py lines 231-234).

The LLM prompt therefore gets:

```
CURRENT SITUATION:
No specific scene

YOUR EMOTIONAL STATE:
Neutral

WHAT YOU WANT RIGHT NOW:
No pressing wants

RECENT CONVERSATION:
No recent messages

THOUGHT TRIGGER:
A worry surfaces in your mind
```

The worry content ("my disk /dev/sda1 is showing SMART warnings") lives
in `cognition.worries` and would appear in `worries.to_prompt_block()`
-- but that method is never called during thought generation. It IS
called during response generation (via `cognition.get_prompt_blocks()`
at RESPONDING state), so the AI's *response* to the user would be
colored by system worries. But the autonomous *thought* would be
generic: "I can't stop thinking about it..." with no system-specific
content.

**Trigger-by-trigger breakdown of what reaches the LLM:**

| Trigger | What `_describe_trigger()` returns | System content in prompt? |
|---|---|---|
| WORRY | "A worry surfaces in your mind" (hardcoded, ignores `trigger_data`) | NO -- worry content is in `trigger_data["intrusions"]` but unused |
| EMOTIONAL | "You're feeling {emotion} strongly" (uses `trigger_data["emotion"]`) | PARTIAL -- emotion name ("fear") but not the source/reason |
| DRIVE | "You really want {content}" (uses `trigger_data["content"]`) | YES -- drive content string is passed through |
| SCENE_CONTEXT | "Your surroundings: {scene}" (uses `trigger_data["scene"]`) | N/A for system events |
| USER_SILENCE | "They haven't said anything for {minutes} minutes" | N/A |

**Impact on the plan:** The WORRY path -- which is the primary mapping
for CRITICAL system events (disk failure, service failure, security
anomaly) -- produces generic thoughts with no system-specific content.
The DRIVE path works correctly. The EMOTIONAL path is partial.

**Fix (consumer-side, no core change required):**

Halbert must pass a custom `ThoughtGenerator` subclass to
`advance_turn()` that overrides `_describe_trigger()` to extract
worry content from `trigger_data["intrusions"]`:

```python
class HalbertThoughtGenerator(ThoughtGenerator):
    def _describe_trigger(self, ctx: TriggerContext) -> str:
        if ctx.trigger == ThoughtTrigger.WORRY:
            intrusions = ctx.trigger_data.get("intrusions", [])
            if intrusions:
                # Intrusion format: "[WORRY INTRUSION: A thought about {content} surfaces briefly]"
                # Extract the content after "about "
                raw = intrusions[0]
                if "about " in raw:
                    content = raw.split("about ", 1)[1].rsplit(" surfaces", 1)[0]
                    return f"A worry surfaces about {content}"
                return raw
        elif ctx.trigger == ThoughtTrigger.EMOTIONAL:
            emotion = ctx.trigger_data.get("emotion", "unknown")
            # The source isn't in trigger_data, but we can at least
            # name the emotion. For system-sourced emotions, the
            # source is in ActiveEmotion.source on the emotional_state,
            # but that's not accessible here without a cognition ref.
            return f"I'm feeling {emotion} strongly"
        return super()._describe_trigger(ctx)
```

This is not optional -- it is **required** for the plan to work. The
original plan listed a custom ThoughtGenerator as "optional" in §4.5.
That was wrong. It is mandatory for the WORRY path.

**Alternative fix (small core change):** Modify `advance_turn()` to
pass cognitive state to the generator:

```python
# In cognition_tick.py, line 468, change:
thought = generator.generate(trigger)
# To:
thought = generator.generate(
    trigger,
    scene_context=cognition.scene_context or user_message,
    emotional_state=cognition.emotional_state.to_prompt_block() if hasattr(cognition.emotional_state, 'to_prompt_block') else "",
    active_drives=cognition.drives.to_prompt_block() if hasattr(cognition.drives, 'to_prompt_block') else "",
)
```

This is a 4-line core change that makes the thought generation prompt
actually include the cognitive state. It benefits ALL consumers, not
just Halbert. **This is the better fix** -- it's small, general, and
fixes a pre-existing gap in the core (the generator was designed to
receive these parameters but advance_turn never passes them).

**Recommendation:** Propose the core change to Haloysius (4 lines in
`cognition_tick.py`). If rejected, use the consumer-side
`HalbertThoughtGenerator` subclass. Either way, the original plan's
claim that "no core changes needed" was overstated for the thought
quality path -- the *trigger fires* without core changes, but the
*thought content* is degraded without a fix.

### 9.2 CONFIRMED: `belief_state` parameter is dead code in `check_triggers()`

**The claim (§6.1):** "BELIEF and VALUE triggers are defined but not
checked."

**Verified:** `check_triggers()` (thought_triggers.py lines 83-190)
accepts `belief_state=None` as a parameter but never references it in
the method body. The parameter is dead code. Beliefs are only processed
by `extract_belief_evidence()` (step 3 of advance_turn), which
reinforces/challenges existing beliefs based on conversation text --
it does not generate new thoughts.

The plan's workaround (map config drift to both Worry and Belief)
remains correct. The Worry fires the trigger; the Belief persists in
the self-model.

### 9.3 CONFIRMED: `check_intrusions` is probabilistic

**The concern:** Worry triggers fire probabilistically, not
deterministically.

**Verified:** `WorryState.check_intrusions()` calls
`Worry.should_intrude(context)` which uses
`random.random() < base_chance` where `base_chance = intrusion_rate *
intensity` (doubled if context-relevant).

For a CRITICAL disk failure mapped to worry(intensity=0.9,
intrusion_rate=0.5):
- Base chance: 0.45 (45% per turn)
- If user mentions disks: 0.90 (90% per turn)
- If user talks about unrelated topic: 0.45 (45% per turn)

This means a CRITICAL system issue has a 55% chance of NOT producing
a thought on any given turn when the user isn't discussing the issue.

**Is this a problem?** Arguably no -- this mimics how worries work in
humans (they surface intermittently, not constantly). And the worry
still colors the response prompt via `to_prompt_block()` every turn
even when it doesn't trigger a thought. But the plan should be
explicit about this: system-event worries do not guarantee a thought
every turn. They guarantee background anxiety (always) and
intermittent intrusive thoughts (~45-90% per turn).

**If deterministic firing is needed:** Set `intrusion_rate=1.0` for
CRITICAL worries. This makes `base_chance = intensity` (0.9), so the
worry fires 90% of the time (or 100% if context-relevant, since
`min(1.0, 0.9 * 2) = 1.0`). This is a tuning decision, not a code
change.

### 9.4 NEW FINDING: `EmotionalStateV2.trigger_from_event()` already exists

**Not in the original plan.** `emotional_state_v2.py` lines 157-199
define `trigger_from_event(event_type, event_data)` which handles
event-driven emotional responses. The "worry_trigger" event type
(lines 194-199) adds BOTH a FEAR emotion AND a worry in one call:

```python
elif event_type == "worry_trigger":
    content = event_data.get("content", "something")
    intensity = event_data.get("intensity", 0.5)
    self.add_emotion(EmotionCategory.FEAR, intensity * 0.7, f"worry about {content}")
    self.worry_state.add_worry(content=content, ...)
```

**Impact on plan:** The `SystemEventMapper` should use
`trigger_from_event("worry_trigger", {"content": "...", "intensity": ...})`
instead of separately calling `add_worry()` and `add_emotion()`. This
creates the linked emotional+worry state in one call and is the
intended extension point. The original plan's draft code called
`add_worry()` and `add_emotion()` separately, which works but misses
the designed integration point.

However, `trigger_from_event` has a limitation: it always adds FEAR
for worry_trigger events. For system events where ANGER (security
breach) or SADNESS (backup failure) might be more appropriate, the
mapper would need to call `add_emotion()` separately after
`trigger_from_event()`, or the event types would need to be extended.

**Revised recommendation:** Use `trigger_from_event` as the primary
path, then call `add_emotion()` for any additional emotions that
the event type doesn't cover.

### 9.5 NEW FINDING: Worry decay vs. re-intensification can go negative

**The concern:** If the user chats rapidly, worry decay outpaces
re-intensification.

**Verified math:** The tick decays all worries by 0.02 per turn
(`WORRY_DECAY_PER_TURN`). The mapper re-intensifies by 0.1 per scan.
If scans run every 5 minutes and the user sends a message every 30
seconds:
- Between scans: 10 turns x 0.02 = 0.20 decay
- On scan: +0.1 intensify
- Net: -0.10 per 5-minute cycle

A CRITICAL worry starting at 0.9 would decay to 0.0 in ~45 minutes
of rapid conversation, even though the disk is still failing.

**Fix:** The mapper should be called EVERY turn (not just on scan)
and should re-intensify existing worries based on the cached
discovery state. The mapper reads the DiscoveryEngine's in-memory
cache (instant, no scan latency) and calls `intensify()` on any
worries whose corresponding discovery is still CRITICAL/WARNING.
This counteracts per-turn decay.

**Revised `map_to_cognition` flow:**

```
Every turn (before advance_turn):
  1. Read DiscoveryEngine cache (no I/O, instant)
  2. For each CRITICAL/WARNING discovery:
     a. If worry exists -> intensify(0.03)  # counteracts 0.02 decay + small net positive
     b. If no worry -> add_worry()
  3. For each resolved discovery -> resolve_worry()
  4. Process pending config events (from ConfigWatcher callback)
```

The intensify amount (0.03) should be slightly above decay (0.02) to
ensure persistent issues maintain worry intensity over long
conversations. This is a tuning constant, not a code change.

### 9.6 NEW FINDING: Thread safety gap in `_pending_config_events`

**The concern:** `ConfigWatcher` runs in a separate thread (watchdog
observer or polling thread). The `_pending_config_events` list is
written from the watcher callback and read/cleared from the main
tick thread.

**Verified:** The draft code in §5.2 uses a plain `list` for
`_pending_config_events` with no lock. This is a race condition:
the watcher could append while the tick is iterating/clearing.

**Fix:** Use `queue.Queue` or `threading.Lock`:

```python
from queue import Queue

class SystemEventMapper:
    def __init__(self, ...):
        self._pending_config_events: Queue = Queue()

    def on_config_change(self, changes: list[dict]) -> None:
        for change in changes:
            self._pending_config_events.put(change)

    def _map_config_events(self, cognition) -> int:
        writes = 0
        while not self._pending_config_events.empty():
            event = self._pending_config_events.get_nowait()
            # ... process event ...
            writes += 1
        return writes
```

### 9.7 NEW FINDING: Scan latency would block the conversation tick

**The claim (§3.3):** "Poll at tick time. Before advance_turn(), the
SystemEventMapper reads from the DiscoveryEngine singleton."

**The problem:** `DiscoveryEngine.scan_all()` runs all scanners
synchronously. Scanners call `smartctl`, `journalctl`, `lsblk`,
`sensors`, etc. -- each with timeouts of 5-30 seconds. A full scan
can take 30-60 seconds. Running this during the tick would block
the conversation for a minute.

**The fix (already implied but not stated explicitly enough):** The
mapper must NEVER call `scan_all()` during the tick. It reads from
the DiscoveryEngine's in-memory `_discoveries` cache, which is
populated by a separate background scan thread. The cache may be
stale (up to `scan_interval` seconds old), but that's acceptable --
system events don't need sub-second freshness.

**Revised §3.3:** The background scan thread is not "Phase 2+" -- it
is required for MVP. Without it, either the tick blocks for 30+
seconds, or the mapper has no data to read. The only alternative is
to skip system-event mapping entirely on the first turn (empty cache)
and rely on the background thread to populate it for subsequent turns.

### 9.8 CONFIRMED: All cognitive state methods exist and are publicly callable

Verified by reading source:
- `WorryState.add_worry(content, source, category, intensity, intrusion_rate)` -- worry.py line 119
- `WorryState.get_active_worries()` -- worry.py line 148
- `WorryState.resolve_worry(worry_id, resolution)` -- worry.py line 164
- `Worry.intensify(amount)` -- worry.py line 80
- `Worry.decay(amount)` -- worry.py line 67
- `EmotionalStateV2.add_emotion(emotion, intensity, source)` -- emotional_state_v2.py line 85
- `EmotionalStateV2.trigger_from_event(event_type, event_data)` -- emotional_state_v2.py line 157
- `DriveState.add_drive(category, content, intensity, trigger)` -- drives.py line 243
- `BeliefState.add_belief(subject, content, domain, confidence, source, evidence, rigidity)` -- beliefs.py line 217
- `BeliefState.get_beliefs_about(subject)` -- beliefs.py line 253 (substring match on subject)
- `Belief.reinforce(evidence)` -- beliefs.py line 100
- `Belief.challenge(evidence)` -- beliefs.py line 74

All methods are public (no underscore prefix), all return the created
object (for ID capture), and all are called on attributes of
`PersonaCognition` which is a dataclass with public fields. The
consumer-side mapping approach is structurally sound.

### 9.9 CONFIRMED: `EmotionalStateV2` uses `EmotionCategory` from `emotional_state.py`

`emotional_state_v2.py` line 16: `from .emotional_state import
EmotionalState, EmotionCategory`. The `add_emotion()` method takes
`EmotionCategory` (Plutchik's wheel: JOY, SADNESS, ANGER, FEAR,
SURPRISE, DISGUST, TRUST, ANTICIPATION, plus secondary emotions).
The plan's usage of FEAR for disk/thermal/security events and JOY
for healthy-state is valid.

### 9.10 CONFIRMED: `get_beliefs_about()` uses substring matching

`beliefs.py` line 255: `return [b for b in self.beliefs.values() if
subject.lower() in b.subject.lower()]`

This is a substring match. If the mapper adds a belief with
`subject="/etc/nginx/nginx.conf"` and later searches for
`get_beliefs_about("/etc/nginx/nginx.conf")`, it will match. But
searching for `get_beliefs_about("nginx")` would also match any
belief whose subject contains "nginx". This is convenient but could
cause false positives if multiple config files share a name
component. The mapper should use full paths as subjects to avoid
ambiguity.

### 9.11 CORRECTED CLAIM: "No core changes needed" is overstated

The original executive summary says "no core changes are required
for Halbert." After scrutiny, this is true for the *trigger firing*
path (worries/emotions/drives fire existing triggers) but NOT true
for the *thought quality* path (the generated thought lacks
system-specific content because `advance_turn()` doesn't pass
cognitive state to the generator).

**Corrected statement:**

> No core changes are required for system events to *fire* cognitive
> triggers. A small core change (4 lines in `advance_turn()` to pass
> cognitive state to the generator) OR a consumer-side
> `ThoughtGenerator` subclass is required for the generated thoughts
> to contain system-specific content. Without either fix, WORRY
> triggers produce generic thoughts ("I can't stop thinking about
> it...") instead of system-specific ones ("I need to check on
> /dev/sda1 -- those SMART warnings could mean my primary drive is
> dying").

### 9.12 Summary of corrections to the original plan

| # | Original claim | Correction | Severity |
|---|---|---|---|
| 1 | "No core changes needed" | True for trigger firing; false for thought quality. Need 4-line core fix OR custom ThoughtGenerator. | HIGH -- thoughts would be generic without fix |
| 2 | Custom ThoughtGenerator is "optional" (§4.5) | MANDATORY for WORRY path if core fix is not applied | HIGH |
| 3 | "Poll at tick time" for MVP (§3.3) | Background scan thread is required for MVP, not Phase 2+. scan_all() blocks 30+ seconds. | MEDIUM -- would block conversation |
| 4 | Mapper called on scan cadence | Mapper must be called EVERY TURN to counteract worry decay (0.02/turn). Intensify by 0.03/turn for persistent issues. | MEDIUM -- worries decay during rapid conversation |
| 5 | Separate add_worry() + add_emotion() calls | Use `trigger_from_event("worry_trigger", ...)` -- the designed integration point that creates linked emotion+worry | LOW -- works either way, but designed path is cleaner |
| 6 | `_pending_config_events` as plain list | Must use `queue.Queue` or lock -- ConfigWatcher runs in separate thread | LOW -- race condition, unlikely to crash but could drop events |
| 7 | Worry triggers fire reliably for CRITICAL events | Probabilistic: 45% base chance per turn (90% if context-relevant). Set intrusion_rate=1.0 for deterministic-ish firing. | LOW -- by design, but should be documented |

### 9.13 What the plan got right

- The core architectural insight is correct: system events map onto
  existing cognitive states (worries, drives, emotions), not new
  trigger types. Option D is the right approach.
- All cognitive state methods exist and are publicly callable.
  Consumer-side mapping is structurally sound.
- The severity-to-intensity calibration is reasonable.
- The first-person embodied language recommendation is correct and
  aligns with the founder's "AI identifies as the computer" decision.
- The worry deduplication strategy (key by discovery ID, intensify
  existing, resolve cleared) is correct.
- The BELIEF/VALUE trigger gap (§6) is accurately identified.
- The ConfigWatcher integration approach is correct (callback feeds
  pending events, drained at tick time).
- The mapping table (§2.2) is comprehensive and covers all major
  scanner types.
