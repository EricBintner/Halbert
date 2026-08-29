# Halbert Vision Integration — Design Audit Review Feedback

**Date:** 2026-08-28  
**Reviewer:** Architecture & Perception Systems Agent  
**Document Reviewed:** `HALBERT-VISION-INTEGRATION-REVIEW-REQUEST.md`  
**Status:** Complete Architectural Review & Perception Expansion Blueprint  

---

## Executive Summary

Halbert stands at a unique junction: it is neither just a desktop chatbot nor merely a home automation dashboard. It is an **ambient, embodied homelab & home intelligence** with an inner cognitive life (`PersonaCognition`), an autonomous proactive loop (`DetectorRunner`, `ProactiveGate`, `Reflexes`), and physical/digital sensing capabilities.

The core vision tools implemented in `feat/core-vision` (`tools/vision_tools.py`, `vision/screen_capture.py`, `vision/ocr.py`, `vision/redact.py`) provide a solid foundational substrate. However, the 11 proposed integration points in the review request vary significantly in architectural soundness:

- **Top tier (immediate green light with adjustments):**
  - **#9 (BeingConfig `senses.vision.*`)** & **#10 (Conditional tool registration)**: Foundational consent and privacy gating.
  - **#4 (Intake visual-intent detection)**: Crucial for 1-turn visual comprehension without unnecessary tool loops.
  - **#3 (Reflex matching on visual findings)**: Clean, zero-overhead user customization leveraging existing `Finding` schemas.
- **Needs architectural refactoring (yellow light):**
  - **#1 (Proactive Visual Anomaly Detector)**: Should **not** be grouped with the 6-hour filesystem detectors in `DetectorRunner`. It requires a dedicated, lightweight `VisualWatcher` cadence with frame-differencing debouncing.
  - **#2 (Vision Alert Rule)**: Synchronous OCR in `AlertEngine._monitor_thread` risks thread blocking and state oscillation for transient dialogs. Visual anomalies belong in the Proactive/Event stream, not the persistent Alert table.
  - **#5 (Auto-Capture on Tool Failure)**: Indiscriminate capture on all tool errors causes context pollution and model thrashing. Gating and OCR-only summaries are essential.
  - **#7 (Episodic Memory Storage)**: Must store lightweight disk references and OCR summaries, **never** raw base64 strings in SQLite/vector stores.
- **Redundant / Low Priority (deprecate or defer):**
  - **#11 (Vision Context Adapter)**: Redundant with `ctx.observations` and adds token bloat.

Beyond the 11 review points, this document expands the architecture to integrate **Frigate NVR** as Halbert’s external ocular system, creating a unified multimodal perception loop spanning desktop monitors, webcams, and spatial home cameras.

---

## 1. Verification of "Already Wired" Baseline

Every claim in Section "Current State (Already Wired)" was audited against the codebase:

| Component | Audited File & Lines | Status / Findings |
|---|---|---|
| **Vision Tools** | `halbert_core/tools/vision_tools.py:1-652` | **Verified.** 6 tools implemented (`capture_screenshot`, `capture_webcam`, `capture_and_ocr`, `list_windows`, `capture_window`, `capture_active_window`). |
| **Tool Execution Handler** | `halbert_core/agents/state_machine.py:2415-2444` | **Verified.** Handles `image` key by appending to `ctx.images` and `ocr_text` key by appending direct string observations. |
| **Model Routing** | `halbert_core/dashboard/routes/agent.py:459-465` | **Verified.** `_resolve_turn_model` auto-selects the vision model when `images` is non-empty or `intake_result.recommended_model == "vision"`. |
| **Double Tool Registration** | `halbert_core/dashboard/routes/agent.py:125-126` & `213-214` | **Bug Discovered:** `register_vision_tools()` and `register_system_tools()` are called twice in `get_agent()`. (Safe due to dict overwrites, but redundant). |
| **Image Transport** | `halbert_core/dashboard/routes/agent.py:290-297` | **Verified.** `_attach_images()` correctly formats OpenAI-compatible multimodal message payloads. |
| **Privacy Gates** | `halbert_core/vision/config.py:37-65`, `136-144` | **Verified.** `is_screen_capture_enabled()` and `is_webcam_enabled()` read directly from `~/.config/halbert/vision_config.yml`. |
| **Dedup Hashes** | `halbert_core/tools/vision_tools.py:26-30` | **Verified.** Module-level MD5 tracking prevents duplicate image payloads on static screens. |

---

## 2. Assessment of the 11 Proposed Integration Points

### Tier 1 — Event-Driven Vision

#### Point 1: Proactive Visual Anomaly Detector
- **Assessment:** **Needs Refactoring**
- **Findings (`proactive/detector_runner.py:76-80`, `dashboard/app.py:476-484`):**  
  `DetectorRunner` currently runs `DropinConflictDetector`, `FstabPhantomDetector`, and `PermissionsHygieneDetector` on a **6-hour cron** (`hour: '*/6', minute: 12`). Visual anomalies (error popups, frozen windows, kernel panics, critical alert bars) require a cadence of 15 seconds to 2 minutes. Running filesystem detectors every 30s is wasteful; running visual detection every 6h misses almost every transient error.
- **Recommendations:**
  1. Split into a dedicated `VisualWatcher` autonomous background task with an adaptive sampling rate (e.g. 30s when active, 5min when screen idle).
  2. Implement a two-stage gate: Stage 1 = Fast pixel diff/hash check (MSS grab -> ~15ms); Stage 2 = OCR / pattern match **only** if pixels changed.
  3. Publish findings as `ProactiveEvent(type="visual_finding", category="vision")`.

#### Point 2: Vision Alert Rule
- **Assessment:** **Problematic (Merge with Proactive Event)**
- **Findings (`alerts/engine.py:105-147`, `alerts/engine.py:84-214`):**  
  `AlertEngine` runs `_monitor_thread` synchronously across rules every 60s. Adding OCR (`capture_and_ocr()`) directly into the alert thread can block all alert processing (CPU spikes). Furthermore, `Alert` represents persistent system states requiring explicit clearing/acknowledgment, whereas visual notifications are transient observations.
- **Recommendations:**  
  Do **not** add `VisionAlertRule` directly to `AlertEngine`. Instead, let the `VisualWatcher` (#1) publish `ProactiveEvent`s. If a visual finding is classified as `CRITICAL` (e.g., "Kernel Panic" or "RAID Degradation Banner"), the `VisualWatcher` can programmatically raise an alert via `AlertEngine.add_alert()` without blocking the rule evaluation loop.

#### Point 3: Reflex Matching on OCR Text
- **Assessment:** **Sound (High Value)**
- **Findings (`proactive/reflexes.py:45-78`, `130-171`):**  
  `Reflex.match()` matches against `Finding(title, description, category, severity)`.
- **Recommendations:**  
  When `VisualWatcher` generates a finding, set `category="vision"` and `title="Visual Error: <regex_match>"`. Users can create reflexes like:
  ```yaml
  name: "Auto-restart crashed GPU service"
  trigger:
    category: "vision"
    title_pattern: ".*CUDA out of memory.*"
  action:
    tool: "execute_command"
    args: { command: "systemctl restart ollama" }
  ```
  Zero engine modifications needed.

---

### Tier 1 — Automatic Diagnostic Capture (Agent Loop)

#### Point 4: Intake Visual-Intent Detection
- **Assessment:** **Sound (High Priority)**
- **Findings (`intake/signals.py:163-169`, `intake/pipeline.py:172-175`):**  
  Currently, `signals.has_images` is only set if the user prompt contains markdown images or base64 data URIs. If a user asks *"What error is showing on my screen?"*, the intake pipeline routes to the chat/guide model, forcing a multi-turn tool calling dance.
- **Recommendations:**  
  1. Add `_VISUAL_INTENT_RE = re.compile(r"\b(on (?:my|the) screen|look at (?:my|this|the) (?:screen|camera|webcam|window|display)|what do you see|see (?:this|the) (?:error|dialog|window))\b", re.IGNORECASE)` to `intake/signals.py`.
  2. Populate `signals.has_vision_request = True`.
  3. In `intake/pipeline.py:172-175`, if `(signals.has_images or signals.has_vision_request) and vision_model_name`, set `recommended_model = "vision"`.

#### Point 5: Auto-Capture on Tool Failure
- **Assessment:** **Needs Guardrails**
- **Findings (`agents/state_machine.py:2454-2457`, `2780-2800`):**  
  If any tool fails (e.g., a regex search or a CLI flag typo), indiscriminately grabbing the screen and attaching an image causes:
  - Routing flip to the vision model mid-turn (expensive and slower).
  - Context bloat with unrelated desktop visuals.
- **Recommendations:**  
  1. Gate this behavior: Only auto-capture if `being_config.senses.vision.auto_capture_on_error` is `True` and the failed tool was a GUI action or system service modification.
  2. Use `capture_and_ocr()` instead of full image capture, adding the extracted text as a diagnostic observation rather than routing through the vision model.

#### Point 6: Auto-Capture in PLANNING on Visual Intent
- **Assessment:** **Sound (Paired with #4)**
- **Findings (`agents/state_machine.py:1561-1620`):**  
  When `ctx.intake.has_vision_request` is `True` and `ctx.images` is empty:
- **Recommendations:**  
  Before `self.llm.chat()` in `_handle_planning`, check `is_screen_capture_enabled()`. If enabled, invoke `capture_active_window_tool()` automatically and append the image to `ctx.images`.
  This turns a 2-turn round trip (User -> LLM tool call -> Capture -> LLM answer) into a single, instant response.

---

### Tier 2 — Cognition & Memory

#### Point 7: Episodic Memory Storage
- **Assessment:** **Needs Refactoring (Storage Architecture)**
- **Findings (`memory/hybrid.py:22-30`, `dashboard/routes/agent.py:128-135`):**  
  Embedding base64 images into memory metadata will rapidly bloat the SQLite/ChromaDB database to gigabytes. Note that `dashboard/routes/agent.py:133-135` explicitly fences ChromaDB off the agent path in favor of FTS5/receipts.
- **Recommendations:**  
  1. Store **visual textual descriptions and OCR text** in episodic memory (`MemoryType.EPISODIC`).
  2. Save snapshots as JPEG files on disk in `~/.local/share/halbert/vision_cache/<hash>.jpg` with a rolling 7-day TTL / 500MB quota. Store only the file URI in memory metadata.

#### Point 8: Cognition / System Event Mapping
- **Assessment:** **Sound (Brings Halbert to Life)**
- **Findings (`integrations/system_event_mapper.py:61-183`, `integrations/haloysius_memory_adapter.py:124-149`):**  
  Halbert's cognitive layer models worries, drives, and emotional states (FEAR, CURIOSITY, VIGILANCE).
- **Recommendations:**  
  Add `visual_anomaly` and `camera_event` handlers in `system_event_mapper.py`:
  - A persistent onscreen error increases `intensity` of `stability_worry`.
  - Frigate detecting an unknown person at 2 AM triggers `FEAR`/`VIGILANCE` and spawns a proactive inquiry.
  - Frigate detecting a package delivery triggers `CURIOSITY`/`RELIEF`.

---

### Tier 2 & 3 — Configuration & Context

#### Point 9: Being Config `senses` Section
- **Assessment:** **Sound (Essential Consent Layer)**
- **Findings (`config/being_config.py:32-54`):**  
  Integrate persona-level sensory autonomy into `being.yml`:
  ```yaml
  senses:
    vision:
      enabled: true
      proactive_monitoring: false
      capture_active_window_on_intent: true
      interval_seconds: 60
  ```

#### Point 10: Conditional Tool Registration
- **Assessment:** **Sound (Clean Hygiene)**
- **Findings (`dashboard/routes/agent.py:125-126`, `tools/executor.py:736-750`):**  
  If screen capture and webcam are both disabled in config, do not register `VISION_TOOLS` in `ToolExecutor`. This prevents the LLM from hallucinating screen captures when the user has not granted permission.

#### Point 11: Vision Context Adapter
- **Assessment:** **Redundant (Do Not Implement)**
- **Findings (`context/extra_adapters.py:541-596`, `context/assembler.py:288-300`):**  
  OCR text and visual context are already injected via `ctx.observations` and `ctx.images`. Creating a separate async search adapter querying stale OCR captures adds latency and token clutter.

---

## 3. Revised Implementation Order

1. **Phase 1 — Consent & Hygiene (Points #9, #10):** Add `senses` to `BeingConfig`; gate tool registration conditionally; eliminate double tool registration in `routes/agent.py`.
2. **Phase 2 — Intent-Driven Fast Path (Points #4, #6):** Add visual intent detection in `signals.py`; auto-capture active window during `PLANNING` when intent is detected.
3. **Phase 3 — Proactive Visual Watcher (Points #1, #3):** Create standalone `VisualWatcher` autonomous task with MD5 change detection; emit `ProactiveEvent(type="visual_finding")` for living reflexes.
4. **Phase 4 — Cognitive & Episodic Memory (Points #7, #8):** Wire visual findings into `system_event_mapper.py` (worries/drives); store disk-cached snapshots + OCR in episodic memory.
5. **Phase 5 — Fail-Safe Diagnostics (Point #5):** Implement opt-in OCR diagnostics on command failures.

---

## 4. Expanding the Horizon: In-App CV & Frigate Multi-Camera Architecture

To realize Halbert's vision as a groundbreaking ambient assistant, computer vision must transcend static screenshots and operate as a continuous perceptual fabric across the desktop and the physical home.

```
                     ┌─────────────────────────────────────────────────────────┐
                     │            HALBERT UNIFIED PERCEPTION BUS               │
                     └────────────────────────────┬────────────────────────────┘
                                                  │
            ┌─────────────────────────────────────┼─────────────────────────────────────┐
            │                                     │                                     │
            ▼                                     ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐             ┌───────────────────────┐
│   DESKTOP PERCEPTION  │             │   WEBCAM & EMBODIMENT │             │   FRIGATE NVR (HOME)  │
│ (MSS / ScreenCapKit)  │             │ (OpenCV / MediaPipe)  │             │     (MQTT Broker)     │
├───────────────────────┤             ├───────────────────────┤             ├───────────────────────┤
│ • Active Window OCR   │             │ • User Presence/Gaze  │             │ • Zone Object Tracking│
│ • Terminal Crash Triage│            │ • Gesture Confirmations│            │ • Person / Pet Events │
│ • TUI / UI Parsing    │             │ • Hardware Inspection │             │ • Snapshot / Clips    │
└───────────┬───────────┘             └───────────┬───────────┘             └───────────┬───────────┘
            │                                     │                                     │
            └─────────────────────────────────────┼─────────────────────────────────────┘
                                                  │
                                                  ▼
                     ┌─────────────────────────────────────────────────────────┐
                     │     TIER 0 / TIER 1 LOCAL PERCEPTION FILTER            │
                     │  (MD5 Hashes, Fast OCR, Coral/YOLO, MediaPipe, Qwen-VL) │
                     └────────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼
                     ┌─────────────────────────────────────────────────────────┐
                     │         PERSONA COGNITION & AUTONOMOUS REFLEXES         │
                     │     (Worries, Drives, Episodic Spatial Narratives)      │
                     └────────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼
                     ┌─────────────────────────────────────────────────────────┐
                     │       AGENT STATE MACHINE & FRONTIER VLM ROUTING        │
                     │   (Claude 3.7 / GPT-4o / Local Ollama on High Intent)   │
                     └─────────────────────────────────────────────────────────┘
```

### Breakthrough Use Cases

#### 1. "Ghost in the Terminal" (Desktop TUI & Live Crash Telepathy)
- **Concept:** Halbert understands terminal layouts (btop, htop, k9s, lazydocker, tmux) that fail when scraped as linear text. When a build crashes or red stack traces render in the terminal, Halbert highlights the root cause visually before the user even finishes typing *"why did it fail?"*.

#### 2. Physical Rack & Hardware Gaze (Webcam / Mobile Camera)
- **Concept:** Point the camera at a server rack, switch, or Raspberry Pi cluster. Halbert detects blinking amber disk LEDs, identifies unplugged Ethernet ports, reads MAC address barcodes, and correlates physical LED cadence with SMART disk telemetry.

#### 3. Gesture-Driven Homelab Control (Sci-Fi Hand Confirmation)
- **Concept:** When Halbert asks for confirmation to execute a destructive command (`rm -rf` or `zpool destroy`), the user can give a simple physical "Thumbs Up" or "Open Palm" to the webcam. MediaPipe processes this locally at 0 token cost, bypassing keyboard input entirely.

#### 4. Frigate "Home Narrative" (Episodic Spatial Omniscience)
- **Concept:** Instead of hundreds of raw motion pings, Frigate MQTT events are synthesized into continuous autobiographical memory:
  - *"Eric entered the office at 9:00 AM."*
  - *"Package delivered on front porch at 1:15 PM."*
  - Queryable at any time: *"Where did I leave my soldering iron?"* or *"Did anything unusual happen around the house today?"*

#### 5. Ambient Presence & Privacy Shutter
- **Concept:** Face and gaze detection via MediaPipe checks if the user is actively sitting in front of the screen. When the user steps away, Halbert pauses sensitive screen captures, mutes alert chimes, and secures the dashboard.
