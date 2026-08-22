# Haloysius Handoff: Thought Generation Fix in advance_turn()

**Date:** 2026-08-22
**From:** Halbert integration planning
**To:** Haloysius maintainers
**Status:** Awaiting founder decision (D-A) on Option A vs Option B
**Related:** `FINAL-PLAN-2026-08-22.md` §1, `RQ-C-SYSTEM-EVENT-TRIGGERS-2026-08-22.md` §9.11

---

## 1. The problem

`advance_turn()` in `cognition_tick.py` calls the thought generator with only the trigger context — it does not pass any cognitive state (worries, emotions, drives, scene) to the generator:

```python
# cognition_tick.py line 468
thought = generator.generate(trigger)
```

The `ThoughtGenerator.generate()` method accepts optional parameters for `scene_context`, `emotional_state`, `active_drives`, and `recent_messages`, but none are passed. As a result:

- `_generate_with_llm()` receives empty strings for all context fields
- `_describe_trigger()` produces generic descriptions:
  - WORRY: `"A worry surfaces in your mind"` (line 319)
  - MEMORY_ECHO: `"A memory comes back to you"` (line 322)
  - CONVERSATION: `"Something from the conversation stays with you"` (line 325)
- The LLM prompt (`THOUGHT_GENERATION_PROMPT`) gets `"Neutral"` for emotional state, `"No pressing wants"` for drives, `"No specific scene"` for scene context

This means generated thoughts are generic ("I can't stop thinking about it...") instead of specific ("I need to check on /dev/sda1 — those SMART warnings could mean my primary drive is dying").

**This affects all consumers**, not just Halbert. Human-persona apps (H2, H3) also get generic thoughts because the cognitive state is never passed to the generator.

---

## 2. The fix — Option A (recommended): 4-line core change

Pass the cognitive state that's already available in `advance_turn()` to the generator:

```python
# cognition_tick.py, replace line 468:
#   thought = generator.generate(trigger)
# with:

active_worries = cognition.worries.get_active_worries()
worry_summary = "; ".join(w.content for w in active_worries[:3]) if active_worries else ""
emotion_summary = ", ".join(
    f"{e.emotion.value}({e.intensity:.1f})"
    for e in cognition.emotional_state.emotions
    if e.intensity > 0.3
) or ""
drive_summary = ", ".join(
    f"{d.content}({d.intensity:.1f})"
    for d in cognition.drives.drives
    if d.intensity > 0.3
) or ""
thought = generator.generate(
    trigger,
    scene_context=cognition.scene_context or user_message[:200],
    emotional_state=emotion_summary,
    active_drives=drive_summary,
    recent_messages=user_message[:200],
)
```

**Backward compatibility:** All passed values are strings (or empty strings). The `generate()` method already has defaults of `""` for each parameter. Existing consumers that don't set cognitive state will pass empty strings — identical to current behavior.

### Optional enhancement: Enrich _describe_trigger() for WORRY

The WORRY case in `_describe_trigger()` (line 318-319) could include the actual worry content:

```python
# thought_generator.py, replace lines 318-319:
#   elif ctx.trigger == ThoughtTrigger.WORRY:
#       return "A worry surfaces in your mind"
# with:

elif ctx.trigger == ThoughtTrigger.WORRY:
    intrusions = ctx.trigger_data.get("intrusions", [])
    if intrusions:
        contents = [w.get("content", "") for w in intrusions[:2]]
        return f"A worry surfaces: {'; '.join(contents)}"
    return "A worry surfaces in your mind"
```

This is optional — the main fix (passing cognitive state to `generate()`) is sufficient for the LLM to produce specific thoughts. But this enrichment helps the fallback path (`_generate_fallback()`) and improves the trigger description even when the LLM is available.

---

## 3. The alternative — Option B: Consumer-side subclass

If the Haloysius team prefers not to touch core, Halbert can subclass `ThoughtGenerator`:

```python
# halbert_core/integrations/halbert_thought_generator.py

from haloysius.persona.thought_generator import ThoughtGenerator

class HalbertThoughtGenerator(ThoughtGenerator):
    def generate(self, trigger_context, scene_context="",
                 emotional_state="", active_drives="", recent_messages=""):
        # Pre-populate from cognition before calling super
        # Halbert sets these via a closure or thread-local
        return super().generate(
            trigger_context,
            scene_context=self._enrich_scene(scene_context),
            emotional_state=self._enrich_emotions(emotional_state),
            active_drives=self._enrich_drives(active_drives),
            recent_messages=recent_messages,
        )
```

**Downsides:**
- Halbert must maintain a reference to the `PersonaCognition` object in the generator
- The `advance_turn()` call site (`generator = thought_generator or _get_generator(cognition)`) means Halbert must pass its custom generator every call
- Does not fix the problem for H2/H3 — they still get generic thoughts
- More code to maintain for the same result

---

## 4. Recommendation

**Option A** (4-line core change). It:
- Fixes the problem for ALL consumers (H2, H3, Halbert)
- Is backward-compatible (empty strings = current behavior)
- Requires no consumer-side code
- Has no API surface change (optional params already exist)

---

## 5. Verification

After the fix, a WORRY trigger with cognitive state containing `"My disk /dev/sda1 is degrading"` should produce a thought like `"I need to check on /dev/sda1 — those SMART warnings could mean my primary drive is dying"` instead of `"I can't stop thinking about it..."`.

Test: Create a `PersonaCognition` with a worry (`add_worry("My disk /dev/sda1 is degrading", ...)`, intensity=0.9, intrusion_rate=1.0), call `advance_turn()`, verify the generated thought references the disk.
