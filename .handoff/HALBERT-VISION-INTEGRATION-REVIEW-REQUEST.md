# Halbert Vision Integration — Design Audit Review Request

**Date:** 2026-08-28
**From:** Vision integration design audit session
**To:** Review AI
**Status:** Awaiting design review and feedback

---

## Context

Halbert's computer vision feature set (OCR, per-window capture, active window
detection, regex-based blocklist redaction, Wayland support) has been fully
implemented, tested, and merged into `main` on the `feat/core-vision` branch.
The current state is **request-driven only**: vision tools fire when the LLM
calls them or when a user hits the HTTP API. There is no event-driven,
proactive, or automatic capture path.

This handoff captures the output of a design audit that mapped every
invocation point for the new vision functionality across the codebase and
curated the highest-value integration solutions. The audit was produced by
three parallel read-only research subagents covering: (1) the agent loop and
automatic capture insertion points, (2) proactive/alert/cognition/memory
integration surfaces, and (3) intake/context/model-routing wiring.

**This is a design review, not an implementation handoff.** No code has been
written for the integration points below. We want architectural feedback
before any of these are built.

---

## What Was Audited

The audit covered the full `halbert_core` tree at
`/Volumes/4TB-BAD/Halbert/halbert_core/halbert_core` and identified 11
integration points across 6 subsystems:

1. Intake / context stage (signal detection, model routing, context assembly)
2. Agent state machine (PLANNING, EXECUTING, OBSERVING, RESPONDING, ERROR)
3. Alert system (AlertEngine, AlertRule)
4. Cognition / memory (PersonaCognition, system event mapper, episodic memory)
5. Proactive / suggestion system (ProactiveEventBus, ProactiveGate,
   DetectorRunner, reflexes, morning report)
6. Configuration / consent (BeingConfig, vision config, tool registration)

The full audit findings are in the session transcript. The highest-value
points are summarized below with exact file paths and line numbers.

---

## Current State (Already Wired)

These are done and merged. The review should confirm they are sound, but
they are not the focus.

| Layer | Location | Status |
|---|---|---|
| Vision tools | `tools/vision_tools.py` (6 tools: screenshot, webcam, OCR, list/capture windows, active window) | Implemented, registered via `register_vision_tools()` |
| Tool execution | `agents/state_machine.py:2415-2433` | Detects `image`/`ocr_text` keys, appends to `ctx.images`/`ctx.observations` |
| Model routing | `dashboard/routes/agent.py:459-464` (`_resolve_turn_model`) | Auto-selects vision tier when `ctx.images` non-empty or intake recommends |
| Image transport | `dashboard/routes/agent.py:290-297` (`_attach_images`) | Hangs base64 on last user message |
| Privacy gates | `vision/config.py:37-65` | `is_screen_capture_enabled()` / `is_webcam_enabled()` + redaction module |
| HTTP API | `dashboard/routes/vision.py` | `/api/vision/screenshot`, `/webcam`, `/config`, `/status` |
| Settings UI | `dashboard/frontend/src/pages/Settings.tsx` | Screen capture, webcam, grayscale, redaction toggles |
| Dedup | `tools/vision_tools.py` | Per-tool hash variables (`_last_screenshot_hash`, `_last_window_hash`, `_last_active_window_hash`, `_last_webcam_hash`) |
| Redaction on OCR | `tools/vision_tools.py` (`capture_and_ocr` handler) | Redacts OCR text results |

---

## Proposed Integration Points (For Review)

### Tier 1 — Event-Driven Vision (new capability)

#### 1. Proactive Visual Anomaly Detector

**Files:**
- `proactive/detector_runner.py:76-80` — detector list (currently
  `DropinConflictDetector`, `FstabPhantomDetector`, `PermissionsHygieneDetector`)
- `proactive/events.py:26-63` — `ProactiveEvent` dataclass
- `proactive/gate.py:38-100` — `ProactiveGate` filters by proactivity dial,
  quiet hours, snooze, dismissal
- `dashboard/app.py:462-514` — `schedule_proactive_jobs_delayed()` schedules
  `detector_sweep` every 6h and `morning_report` daily

**Proposal:** Add a `VisualAnomalyDetector` to the detector list. It
periodically captures the screen, runs OCR, and publishes
`ProactiveEvent(type="visual_finding", category="vision")` when known error
strings/regexes match. The existing `ProactiveGate` respects
`category_overrides` so the user can tune or silence vision events. A
`vision_sweep` cron job would be added alongside `detector_sweep`.

**Review questions:**
- Is the detector runner the right seam, or should this be a standalone
  background task with its own loop and interval?
- The existing detectors run every 6h. Visual anomaly detection likely needs
  a shorter interval (30s-5min). Does mixing cadences in one runner create
  scheduling problems?
- Should the detector capture the full screen or only the active window? Full
  screen catches system dialogs; active window is more privacy-preserving.

#### 2. Vision Alert Rule

**Files:**
- `alerts/engine.py:21-60` (`Alert`, `AlertSeverity`, `AlertRule`)
- `alerts/engine.py:84-214` (`AlertEngine`, `_register_default_rules` at
  105-147)
- `dashboard/routes/alerts.py:30-117` — REST endpoints

**Proposal:** Add a `VisionAlertRule` whose `check_fn` runs OCR and matches
error patterns ("Error", "Failed", "Connection refused", "Kernel panic").
Register in `_register_default_rules()`.

**Review questions:**
- The `AlertEngine` runs rules on a thread with a configurable interval. Is
  OCR heavy enough to block the alert thread, or should it be offloaded?
- Should vision alerts be a separate `AlertSeverity` or reuse
  `AlertSeverity.WARNING`?
- Is there overlap with the proactive detector (#1)? Should one be the
  primary and the other a thin wrapper, or are they genuinely different
  systems (alerts = persistent state + acknowledgment; proactive events =
  transient notifications)?

#### 3. Reflex Matching on OCR Text

**Files:**
- `proactive/reflexes.py:45-78` (`Reflex`), `130-171` (`match()`)

**Proposal:** Add user-defined regex reflexes that fire on OCR text patterns.
`Reflex.match()` already matches on `title/body/category`.

**Review questions:**
- Reflexes currently match on detector findings. Would OCR text flow through
  the same finding structure, or does it need a new finding type?
- Is this redundant with #1 and #2, or is it the user-customizable layer on
  top of the hardcoded detectors?

### Tier 1 — Automatic Diagnostic Capture (agent loop enhancement)

#### 4. Intake Visual-Intent Detection

**Files:**
- `intake/signals.py:163-169, 353-359` — `analyze_message()` extracts
  `has_images` from markdown/HTML/data-URIs
- `intake/pipeline.py:80-83` (`MessageIntake.recommended_model`),
  `130-169, 172-175` — forces `recommended_model = "vision"` when
  `has_images and vision_model_name`

**Proposal:** Extend `analyze_message()` to detect visual-intent phrases
("what's on my screen", "I see an error", "screenshot", "the dialog says").
Add a `has_vision_request` flag to `MessageIntake`. When set, force
`recommended_model = "vision"`.

**Review questions:**
- Is phrase-matching in the intake signal detector the right layer, or should
  this be a separate "vision intent" classifier?
- Should `has_vision_request` also trigger an automatic capture (coupling
  intent detection with capture), or should capture remain a separate
  decision in the state machine?
- What phrases qualify? Is there a risk of false positives (e.g., "screen"
  in "screening process")?

#### 5. Auto-Capture on Tool Failure

**Files:**
- `agents/state_machine.py:2454-2457` — tool error branch in
  `_handle_executing()`
- `agents/state_machine.py:2780-2800` — `_handle_error()` recovery

**Proposal:** When `result.success is False` and screen capture is enabled,
call `capture_and_ocr()` and add OCR text + optional image as observations
before re-planning. The dedup hash in `vision_tools.py` prevents redundant
captures.

**Review questions:**
- Is this too aggressive? Every tool failure would trigger a screen capture.
  Should it be gated to specific failure types (e.g., command execution
  failures, not search failures)?
- The OCR text could be large. Should it be truncated before being added to
  observations?
- Should the image be attached (routing the turn through the vision model,
  which is more expensive) or just the OCR text (cheaper, text-only)?

#### 6. Auto-Capture in PLANNING When Visual Query Has No Images

**Files:**
- `agents/state_machine.py:1561-1620` — `_handle_planning()` before
  `self.llm.chat()`

**Proposal:** If `ctx.images` is empty but the query implies visual context
(from intake #4), call `capture_active_window_tool()` before the planning
LLM call. Eliminates the round-trip where the LLM requests a screenshot it
obviously needs.

**Review questions:**
- Does this short-circuit the LLM's agency? The model might decide it doesn't
  need a screenshot. Is automatic capture too presumptuous?
- Should this be opt-in (a config flag) or always-on when vision is enabled?
- What happens if the capture fails (no screen access, headless server)?
  Does the planning call proceed with no images, or does it error?

### Tier 2 — Cognition & Memory

#### 7. Episodic Memory Storage

**Files:**
- `memory/hybrid.py:22-30` (`MemoryType.EPISODIC`), `142-204` (`store()`)
- `context/adapters.py:180-305` (`MemoryServiceAdapter`, `recall` at
  230-263)

**Proposal:** Store important screen captures as episodic memories:
`store(content=ocr_text, memory_type=MemoryType.EPISODIC,
metadata={"screenshot_b64": img, "source": "vision"})`.

**Review questions:**
- Storing base64 images in memory metadata could bloat the vector store. Is
  this a real concern? Should images be stored on disk with a path reference
  instead?
- What counts as "important"? Every capture, or only anomaly detections?
- The agent path is fenced from ChromaDB memory
  (`dashboard/routes/agent.py:128-135`). Does this fence apply here?

#### 8. Cognition / System Event Mapping

**Files:**
- `integrations/system_event_mapper.py:61-98` (`add_event`),
  `99-183` (`_apply_event_to_cognition`)
- `integrations/haloysius_memory_adapter.py:124-149` (`add_system_event`)
- `integrations/cognition_wiring.py:52-69` (`_create_cognition`)

**Proposal:** Add a `visual_anomaly` event type. When OCR detects errors,
call `add_event("visual_anomaly", "warning", "screen", <text>)` to generate
worries/drives in the persona's cognitive state.

**Review questions:**
- Is "visual_anomaly" the right event type, or should it be more specific
  ("screen_error", "dialog_detected")?
- How does this interact with the existing system event sources (CPU, memory,
  disk)? Does the cognitive model handle visual events differently from
  metric events?
- Should non-anomaly visual observations (e.g., "user is looking at a
  terminal") also flow into cognition, or only anomalies?

### Tier 2 — Configuration & Consent

#### 9. Being Config `senses` Section

**Files:**
- `config/being_config.py:27-28` (`VALID_PROACTIVITY`), `32-54`
  (`BeingConfig`)
- `persona/personality_prompt.py:58-129` (`generate_personality_section`)

**Proposal:** Add a `senses` section to `BeingConfig`:
`senses.vision.enabled`, `senses.vision.interval_seconds`,
`senses.vision.category`. This feeds `ProactiveGate.category_overrides` and
the personality prompt.

**Review questions:**
- Is `being.yml` the right place for this, or should it stay in
  `vision_config.yml`? Being config is persona-level; vision config is
  system-level. Which axis does "allow screen vision" belong to?
- Should `senses.vision.enabled` be a hard gate (disables all vision) or a
  proactivity gate (only affects proactive capture, not user-requested)?

#### 10. Conditional Tool Registration

**Files:**
- `dashboard/routes/agent.py:125-126, 213-214` —
  `register_vision_tools()` called unconditionally
- `tools/executor.py:736-750` — `register_vision_tools()` implementation
- `vision/config.py:136-143` — `is_screen_capture_enabled()`,
  `is_webcam_enabled()`

**Proposal:** Gate `register_vision_tools()` on
`is_screen_capture_enabled() or is_webcam_enabled()`. Prevents the LLM from
being offered capture tools when the user hasn't opted in.

**Review questions:**
- Is this safe? If vision config loads after the agent is constructed, the
  tools won't be registered. Is there a reload path?
- Should webcam and screen capture be registered independently (so the LLM
  sees only the enabled subset)?

### Tier 3 — Context Enrichment

#### 11. Vision Context Adapter

**Files:**
- `context/extra_adapters.py:541-596` (`create_extended_context_assembler`)
- `context/assembler.py:131-143` (`assemble`), `288-300` (observations
  formatting)

**Proposal:** Add a `VisionContextAdapter` with `async search()` returning
recent OCR text as context. Wire into `extra_sources` and
`extended_priorities`.

**Review questions:**
- Is this redundant with the observations path (#5, #6)? If OCR text is
  already in `ctx.observations`, does a separate adapter add value?
- What's the freshness window? OCR text from 10 minutes ago may be stale.

---

## Recommended Implementation Order

The audit proposes this sequence. We want feedback on whether this ordering
is correct.

1. **Being config `senses.vision.*`** (#9) — consent foundation, blocks
   everything else
2. **Conditional tool registration** (#10) — quick win, privacy-correct
3. **Intake visual-intent detection** (#4) — enables auto-routing to vision
   model
4. **Auto-capture on tool failure** (#5) — highest-value agent loop
   enhancement
5. **Proactive visual anomaly detector** (#1) — the headline feature
6. **Vision alert rule** (#2) — complements the detector
7. **Episodic memory + cognition** (#7, #8) — persistence layer
8. **Reflex matching** (#3) — user-customizable triggers

---

## How to Review

1. Read these source files to verify the audit's claims about insertion
   points and existing wiring:
   - `halbert_core/halbert_core/agents/state_machine.py` — lines 1561-1638
     (PLANNING), 2320-2464 (EXECUTING), 2466-2511 (OBSERVING), 2597-2682
     (RESPONDING), 2780-2800 (ERROR)
   - `halbert_core/halbert_core/intake/signals.py` — lines 163-169, 353-359
   - `halbert_core/halbert_core/intake/pipeline.py` — lines 80-83, 130-175
   - `halbert_core/halbert_core/proactive/detector_runner.py` — lines 48-164
   - `halbert_core/halbert_core/proactive/events.py` — lines 26-180
   - `halbert_core/halbert_core/proactive/gate.py` — lines 38-100
   - `halbert_core/halbert_core/alerts/engine.py` — lines 21-214
   - `halbert_core/halbert_core/integrations/system_event_mapper.py` — lines
     61-183
   - `halbert_core/halbert_core/memory/hybrid.py` — lines 22-30, 142-204
   - `halbert_core/halbert_core/config/being_config.py` — lines 27-54
   - `halbert_core/halbert_core/tools/vision_tools.py` — full file (existing
     tool implementations)
   - `halbert_core/halbert_core/vision/config.py` — lines 37-65, 136-143
   - `halbert_core/halbert_core/dashboard/routes/agent.py` — lines 107-241
     (get_agent), 366-484 (_resolve_turn_model), 290-297 (_attach_images)
   - `halbert_core/halbert_core/dashboard/app.py` — lines 462-514
     (schedule_proactive_jobs_delayed)
2. Verify the "Already Wired" table is accurate — check that the claimed
   line numbers actually contain what the audit says they contain.
3. For each of the 11 proposed integration points, assess:
   - Is the insertion point correct?
   - Is the proposal architecturally sound?
   - Are there missing concerns (privacy, performance, error handling)?
   - Is there a better insertion point the audit missed?
4. Assess the implementation order. Are there dependencies the ordering
   misses? Should any items be merged or split?
5. Identify any integration points the audit missed entirely.

---

## Feedback Format

Write feedback to:
`/Volumes/4TB-BAD/Halbert/.handoff/HALBERT-VISION-INTEGRATION-REVIEW-FEEDBACK.md`

For each of the 11 integration points:

1. **Assessment:** Sound / Needs work / Problematic / Redundant
2. **Findings:** Specific issues, inaccuracies, or confirmations (cite file
   paths and line numbers)
3. **Recommendations:** Concrete changes to the proposal if any
4. **Open questions:** Things that need a human decision

Then provide:

5. **Implementation order feedback:** Is the proposed sequence correct?
6. **Missing integration points:** Anything the audit missed?
7. **Overall assessment:** Is this the right set of features to build next,
   or should the focus be elsewhere?

Be direct and critical. We want to catch architectural mistakes before
implementation begins.

---

## Review Status (Completed & Merged 2026-08-29)

The comprehensive design audit review is documented in:
📄 [`.handoff/HALBERT-VISION-INTEGRATION-REVIEW-FEEDBACK.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-VISION-INTEGRATION-REVIEW-FEEDBACK.md)

All verified recommendations (Intent-Driven Fast Path, Proactive Visual Watcher, BeingConfig `senses`, Frigate NVR, and Local CV inference) were implemented, tested (151/151 tests passing), and merged into `main`.
