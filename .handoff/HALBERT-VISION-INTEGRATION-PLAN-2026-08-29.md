# Halbert Vision Integration — Implementation Plan

**Date:** 2026-08-29
**Worktree:** `feat/vision-integration` (to be created from `main`)
**Status:** Ready for execution
**Scope:** Desktop vision only (screenshots, OCR, active window). Frigate/webcam/gesture expansion deferred to a separate design doc.
**Consent gate:** `being.yml` (persona-level autonomy)

---

## Architecture Decisions (from review feedback)

1. **VisualWatcher is standalone, not in DetectorRunner.** The 6-hour detector sweep cadence (`dashboard/app.py:480`) is wrong for visual anomalies. A dedicated background task with 30s-5min adaptive sampling is required.

2. **No VisionAlertRule in AlertEngine.** `AlertEngine` runs `check_rules()` synchronously in a single thread (`engine.py:277-290`). OCR would block all alert rules. Visual findings flow through `ProactiveEventBus` instead. Critical findings can call a new `AlertEngine.raise_alert()` method (to be added) without blocking the rule loop.

3. **Episodic memory stores disk references, not base64.** Screenshots go to `~/.local/share/halbert/vision_cache/<hash>.jpg` with a 7-day TTL / 500MB quota. Memory metadata holds the file URI + OCR text only.

4. **Vision Context Adapter (#11) dropped.** Redundant with `ctx.observations`.

5. **Consent gate in `being.yml`.** A `senses.vision` section controls persona-level vision autonomy. `vision_config.yml` remains the system-level enable/disable gate (hardware-level). Both must be enabled for proactive capture; user-requested capture only needs `vision_config.yml`.

---

## Phase 1 — Consent & Hygiene

**Goal:** Add the persona-level consent gate and fix the tool registration hygiene issues.

### 1.1 Add `SensesConfig` to `BeingConfig`

**File:** `halbert_core/halbert_core/config/being_config.py`

Add a `SensesVisionConfig` dataclass and a `senses` field on `BeingConfig`:

```python
@dataclass
class SensesVisionConfig:
    enabled: bool = False  # persona-level consent for proactive vision
    proactive_monitoring: bool = False  # background VisualWatcher
    capture_on_intent: bool = True  # auto-capture in PLANNING when visual intent detected
    capture_on_error: bool = False  # auto-capture on tool failure (opt-in)
    interval_seconds: int = 60  # VisualWatcher cadence when proactive_monitoring=True
    error_patterns: List[str] = field(default_factory=lambda: [
        "error", "failed", "panic", "warning", "exception",
        "connection refused", "access denied", "not found",
    ])

@dataclass
class SensesConfig:
    vision: SensesVisionConfig = field(default_factory=SensesVisionConfig)
```

Add `senses: SensesConfig = field(default_factory=SensesConfig)` to `BeingConfig`.

Update `validate()` to check `senses.vision.interval_seconds` is >= 10.

Update `from_dict()` — already handles nested dataclasses via the known-fields filter, but `SensesConfig` needs explicit unpacking since `from_dict` only filters top-level keys. Add a helper that unpacks `senses` dict into `SensesConfig`.

**being.yml shape:**
```yaml
senses:
  vision:
    enabled: true
    proactive_monitoring: false
    capture_on_intent: true
    capture_on_error: false
    interval_seconds: 60
    error_patterns:
      - "error"
      - "failed"
      - "kernel panic"
```

### 1.2 Conditional tool registration

**File:** `halbert_core/halbert_core/dashboard/routes/agent.py`

Replace the two unconditional `register_vision_tools()` calls (lines 126, 214) with a single gated call:

```python
from ...vision.config import is_screen_capture_enabled, is_webcam_enabled
if is_screen_capture_enabled() or is_webcam_enabled():
    tool_executor.register_vision_tools()
```

Remove the duplicate at line 214. Keep `register_system_tools()` at line 125 only (remove line 213 duplicate).

**Note:** `vision/config.py` reads on every call (no cache), so this reflects current config at agent-init time. If the user enables vision after the agent is constructed, they need to restart the agent or trigger a re-init. Document this in the Settings UI.

### 1.3 Settings UI — senses section

**File:** `halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`

Add a "Senses" subsection under the Being config area with toggles for:
- `senses.vision.enabled`
- `senses.vision.proactive_monitoring`
- `senses.vision.capture_on_intent`
- `senses.vision.capture_on_error`
- `senses.vision.interval_seconds` (number input, min 10)

The `PUT /api/being-config` endpoint already exists and accepts the full config dict.

### 1.4 Tests

- `test_being_config_senses`: load/save/validate `senses.vision.*` fields.
- `test_conditional_vision_registration`: verify tools are not registered when vision config is disabled.

---

## Phase 2 — Intent-Driven Fast Path

**Goal:** Detect visual intent in user messages and auto-capture the active window before the planning LLM call, eliminating the 2-turn round-trip.

### 2.1 Visual intent detection in intake signals

**File:** `halbert_core/halbert_core/intake/signals.py`

Add a regex and a new signal field:

```python
_VISUAL_INTENT_RE = re.compile(
    r"\b(?:on (?:my|the) screen|look at (?:my|this|the) (?:screen|camera|webcam|window|display)"
    r"|what(?:'s| is) on (?:my|the) screen"
    r"|what do you see|see (?:this|the) (?:error|dialog|window|message)"
    r"|the (?:error|dialog|popup|notification) says"
    r"|what does (?:my|the) screen (?:show|say))\b",
    re.IGNORECASE,
)
```

Add `has_vision_request: bool = False` to `MessageSignals` (line 200).

In `analyze_message()`, after the image references block (line 354-359):
```python
signals.has_vision_request = bool(_VISUAL_INTENT_RE.search(text))
```

**False-positive mitigation:** The regex requires "screen" to be preceded by "my/the" or followed by "show/say", avoiding "screening process", "screenshot tool config", etc. The phrase "what do you see" is gated by requiring it as a standalone question context (the regex anchors on word boundaries).

### 2.2 Propagate `has_vision_request` through intake pipeline

**File:** `halbert_core/halbert_core/intake/pipeline.py`

Add `has_vision_request: bool` to `MessageIntake` (after `has_images` at line 71).

In `analyze()`, update the model selection block (line 172):
```python
if (signals.has_images or signals.has_vision_request) and vision_model_name:
    recommended_model_name = "vision"
    model_name = vision_model_name
```

Pass `has_vision_request=signals.has_vision_request` in the `MessageIntake` constructor (line 200-227).

### 2.3 Auto-capture in PLANNING

**File:** `halbert_core/halbert_core/agents/state_machine.py`

In `_handle_planning()` (line 1561), before the context assembly block (line 1571), add:

```python
# Auto-capture: if the user's message signals visual intent but no
# image has been captured yet, grab the active window before planning.
if (self.ctx.intake and self.ctx.intake.has_vision_request
        and not self.ctx.images
        and is_screen_capture_enabled()):
    try:
        from ..tools.vision_tools import capture_active_window_tool
        result = await capture_active_window_tool({})
        if isinstance(result, dict) and "image" in result:
            self.ctx.images = self.ctx.images or []
            self.ctx.images.append(result["image"])
            if "ocr_text" in result:
                self.ctx.add_observation(
                    f"[Auto-capture] Active window OCR:\n{result['ocr_text']}"
                )
    except Exception as e:
        logger.warning(f"Auto-capture in PLANNING failed: {e}")
```

**Headless/failure handling:** The capture is wrapped in try/except. If it fails (no screen, headless server, permission denied), planning proceeds with no images. The LLM can still request a capture tool call if it decides one is needed. The failure is logged, not surfaced to the user as an error.

**Privacy gate:** `is_screen_capture_enabled()` checks `vision_config.yml` (system-level). `capture_on_intent` from `being.yml` controls whether this behavior is active. Both must be true.

### 2.4 Tests

- `test_visual_intent_detection`: verify `_VISUAL_INTENT_RE` matches "what's on my screen", "look at this error dialog", "what do you see" and does NOT match "screening process", "screenshot tool", "the screen protector is on".
- `test_intake_vision_request_routing`: verify `recommended_model == "vision"` when `has_vision_request=True` and a vision model is configured.
- `test_planning_auto_capture`: mock `capture_active_window_tool`, verify `ctx.images` is populated when `has_vision_request=True` and screen capture is enabled. Verify no capture when disabled.

---

## Phase 3 — Proactive Visual Watcher

**Goal:** A standalone background task that periodically captures the screen, runs OCR, and publishes `ProactiveEvent`s when error patterns match. User-defined reflexes can trigger actions on these findings.

### 3.1 VisualWatcher module

**New file:** `halbert_core/halbert_core/vision/watcher.py`

```python
class VisualWatcher:
    """Background screen monitor. Captures, OCRs, and publishes
    ProactiveEvents when error patterns match.

    NOT part of DetectorRunner — visual anomalies need 30s-5min
    cadence, not the 6-hour filesystem detector sweep.
    """
    def __init__(self, being_config, gate, reflex_matcher=None):
        self.config = being_config
        self.gate = gate
        self.reflex_matcher = reflex_matcher
        self._running = False
        self._thread = None
        self._last_hash = None  # reuse dedup pattern from vision_tools.py

    def start(self): ...
    def stop(self): ...

    def _watch_loop(self):
        while self._running:
            try:
                self._check_screen()
            except Exception as e:
                logger.warning(f"VisualWatcher error: {e}")
            time.sleep(self._adaptive_interval())

    def _check_screen(self):
        # 1. Capture active window (not full screen — privacy)
        # 2. Hash the image; skip if unchanged (reuse _last_hash)
        # 3. If changed, run OCR
        # 4. Match OCR text against error_patterns
        # 5. On match, create Finding + ProactiveEvent
        # 6. Gate check, then publish
        # 7. Evaluate reflexes on the finding

    def _adaptive_interval(self) -> int:
        # If last capture was unchanged, back off (cap at 5 min).
        # If changed, return the configured interval (default 60s).
        ...
```

**Key design points:**
- Captures the **active window only** (not full screen) for privacy. Uses `capture_active_window_tool` from `vision_tools.py`.
- Reuses the MD5 hash dedup pattern from `vision_tools.py:26-30` — if the screen hasn't changed, skip OCR entirely.
- Creates `Finding` objects (from `findings.store`) with `detector="visual_watcher"` so they integrate with the existing finding/proposal/reflex pipeline.
- Publishes `ProactiveEvent(type="visual_finding", category="vision")` through `ProactiveEventBus`.
- The `ProactiveGate` filters by `category="vision"` — the user can silence vision events via `category_overrides` in `being.yml`.

### 3.2 Schedule VisualWatcher

**File:** `halbert_core/halbert_core/dashboard/app.py`

In `schedule_proactive_jobs_delayed()` (line 462), after the detector sweep scheduling block:

```python
# Visual watcher: standalone background thread, not a cron job.
# Cadence is adaptive (30s-5min), too fast for the cron scheduler.
try:
    being_cfg = load_being_config()
    if (being_cfg.senses.vision.enabled
            and being_cfg.senses.vision.proactive_monitoring
            and is_screen_capture_enabled()):
        from ..vision.watcher import VisualWatcher
        watcher = VisualWatcher(
            being_config=being_cfg,
            gate=ProactiveGate(being_config=being_cfg, ...),
            reflex_matcher=reflex_matcher,
        )
        watcher.start()
        logger.info("VisualWatcher started (proactive screen monitoring)")
except Exception as e:
    logger.warning(f"Failed to start VisualWatcher: {e}")
```

### 3.3 Reflex integration

**File:** `halbert_core/halbert_core/proactive/reflexes.py`

No code changes needed. `ReflexMatcher.match()` already matches on `title + body + category` (`reflexes.py:160`). The `VisualWatcher` creates findings with `category="vision"`, so users define reflexes in `~/.config/halbert/reflexes.yml`:

```yaml
- id: auto-restart-ollama
  name: "Restart Ollama on CUDA OOM"
  pattern: "CUDA out of memory"
  threshold: "warning"
  action: "command"
  command: "systemctl restart ollama"
  category: "vision"
  enabled: true
```

The `pattern` field is a regex matched against `f"{title}\n{body}\n{category}"`. The `VisualWatcher` sets `title="Visual error: <matched pattern>"` and `body=<OCR text excerpt>`, so the reflex pattern matches against the OCR content.

### 3.4 Tests

- `test_visual_watcher_unchanged_skip`: mock capture, return same hash twice, verify OCR is not called on the second pass.
- `test_visual_watcher_pattern_match`: mock capture + OCR returning "CUDA out of memory", verify a `ProactiveEvent` is published with `category="vision"`.
- `test_visual_watcher_gate_suppression`: verify events are suppressed when `proactivity="off"` or `category_overrides["vision"]="off"`.
- `test_visual_watcher_reflex`: verify a reflex with `category="vision"` fires on a matching finding.

---

## Phase 4 — Cognitive & Episodic Memory

**Goal:** Wire visual findings into the cognitive layer (worries, drives, emotions) and store important captures as episodic memories with disk-cached images.

### 4.1 Visual anomaly event in system event mapper

**File:** `halbert_core/halbert_core/integrations/system_event_mapper.py`

Add a new event type handler in `_apply_event_to_cognition()` (after `security_anomaly` at line 159):

```python
elif event_type == "visual_anomaly":
    intensity = 0.7 if severity == "critical" else 0.4
    cognition.worries.add_worry(
        content=f"Screen anomaly: {detail}",
        source=source,
        category="visual_stability",
        intensity=intensity,
        intrusion_rate=0.3 if severity == "critical" else 0.1,
    )
    cognition.emotional_state.add_emotion(
        emotion=self._emotion("VIGILANCE"),
        intensity=intensity * 0.6,
        source=source,
    )
    cognition.drives.add_drive(
        category=self._drive("COMPETENCE"),
        content=f"Investigate screen anomaly: {detail}",
        intensity=intensity * 0.5,
        trigger=source,
    )
```

The `VisualWatcher` (Phase 3) calls `event_mapper.add_event("visual_anomaly", severity, "screen:active_window", detail)` when it detects an error pattern. This flows into the next cognitive tick via `populate_cognition()`.

### 4.2 Disk-cached screenshot storage

**New file:** `halbert_core/halbert_core/vision/cache.py`

```python
class VisionCache:
    """Disk cache for screenshots with TTL and quota.

    Stores JPEGs in ~/.local/share/halbert/vision_cache/<hash>.jpg.
    Rolling cleanup: 7-day TTL, 500MB quota. Oldest files pruned first.
    """
    def __init__(self, base_dir=None, ttl_days=7, max_bytes=500*1024*1024):
        ...

    def store(self, image_b64: str) -> str:
        """Decode base64, save as JPEG, return file:// URI."""
        ...

    def cleanup(self) -> int:
        """Delete expired files and prune to quota. Returns deleted count."""
        ...

    def get_uri(self, hash_hex: str) -> Optional[str]:
        """Return URI if file exists, None otherwise."""
        ...
```

### 4.3 Episodic memory storage

**File:** `halbert_core/halbert_core/vision/watcher.py`

When the `VisualWatcher` detects an anomaly, store an episodic memory:

```python
from ..memory.hybrid import HybridMemorySystem, MemoryType
from .cache import VisionCache

# In _check_screen(), after pattern match:
cache = VisionCache()
uri = cache.store(image_b64)
memory.store(
    content=f"Visual anomaly detected: {matched_pattern}\nOCR: {ocr_excerpt}",
    memory_type=MemoryType.EPISODIC,
    metadata={
        "source": "vision",
        "screenshot_uri": uri,
        "pattern": matched_pattern,
        "severity": severity,
    },
    importance=0.7 if severity == "critical" else 0.4,
)
```

**What counts as "important":** Only anomaly detections (pattern matches) are stored. Routine unchanged captures are not stored. This keeps memory growth bounded by anomaly frequency, not capture frequency.

### 4.4 Tests

- `test_system_event_visual_anomaly`: verify `add_event("visual_anomaly", ...)` creates a worry with `category="visual_stability"`, a `VIGILANCE` emotion, and a `COMPETENCE` drive.
- `test_vision_cache_store_cleanup`: store 3 images, verify files exist, run cleanup with a tiny quota, verify oldest is pruned.
- `test_episodic_memory_vision`: mock `HybridMemorySystem.store`, verify it's called with `MemoryType.EPISODIC` and a `screenshot_uri` in metadata (not base64).

---

## Phase 5 — Fail-Safe Diagnostics

**Goal:** Opt-in automatic OCR capture when a tool fails, giving the re-planning LLM diagnostic context.

### 5.1 Auto-capture on tool failure

**File:** `halbert_core/halbert_core/agents/state_machine.py`

In `_handle_executing()`, the error branch (line 2454-2457), add after the existing observation:

```python
else:
    tool_call.status = "error"
    tool_call.error = result.error
    self.ctx.add_observation(f"Executed {tool_name}: {result.error}")

    # Opt-in diagnostic capture: OCR the screen on tool failure.
    # Gated by being.yml senses.vision.capture_on_error (default False).
    # Only fires for command execution failures, not search/read failures.
    if (self._should_diagnostic_capture(tool_name)
            and is_screen_capture_enabled()):
        try:
            from ..tools.vision_tools import capture_and_ocr
            screen = await capture_and_ocr({"include_image": False})
            if isinstance(screen, dict) and "ocr_text" in screen:
                ocr_excerpt = screen["ocr_text"][:500]  # truncate
                self.ctx.add_observation(
                    f"[Diagnostic] Screen OCR at failure:\n{ocr_excerpt}"
                )
        except Exception as e:
            logger.debug(f"Diagnostic capture failed: {e}")
```

Add helper method:
```python
def _should_diagnostic_capture(self, tool_name: str) -> bool:
    """Only capture on failures of command-execution tools, not
    search/read/lookup tools. Avoids context pollution from
    unrelated screen state on benign failures."""
    try:
        being_cfg = load_being_config()
        if not being_cfg.senses.vision.capture_on_error:
            return False
    except Exception:
        return False
    diagnostic_tools = {"run_command", "execute_command", "shell", "bash"}
    return tool_name in diagnostic_tools
```

**Design choices:**
- **OCR only, no image.** Attaching an image would route the turn through the vision model (expensive, slower). OCR text as an observation is cheaper and sufficient for diagnostic context.
- **Truncated to 500 chars.** Full-screen OCR can be thousands of characters. 500 chars captures the error dialog/terminal output without bloating context.
- **Gated to command-execution tools.** A failed `search` or `read_file` doesn't benefit from a screen capture. Only `run_command` / `execute_command` / `shell` / `bash` failures trigger it.
- **Opt-in.** `capture_on_error` defaults to `False` in `SensesVisionConfig`.

### 5.2 Tests

- `test_diagnostic_capture_on_command_failure`: mock `capture_and_ocr`, verify observation is added when `capture_on_error=True` and tool is `run_command`.
- `test_diagnostic_capture_skipped_for_search`: verify no capture when tool is `search`.
- `test_diagnostic_capture_disabled`: verify no capture when `capture_on_error=False`.
- `test_diagnostic_capture_truncation`: verify OCR text is truncated to 500 chars.

---

## Dependency Graph

```
Phase 1 (consent & hygiene)
  ├── 1.1 SensesConfig in BeingConfig
  ├── 1.2 Conditional tool registration  (depends on 1.1 for nothing, but logically after)
  └── 1.3 Settings UI                   (depends on 1.1)
         │
         ▼
Phase 2 (intent fast path)              (depends on 1.1 for capture_on_intent gate)
  ├── 2.1 Visual intent regex
  ├── 2.2 Intake pipeline propagation   (depends on 2.1)
  └── 2.3 PLANNING auto-capture         (depends on 2.2, 1.1)
         │
         ▼
Phase 3 (VisualWatcher)                 (depends on 1.1 for proactive_monitoring gate)
  ├── 3.1 VisualWatcher module
  ├── 3.2 Schedule in app.py            (depends on 3.1)
  └── 3.3 Reflex integration            (no code change, just docs)
         │
         ▼
Phase 4 (cognition & memory)            (depends on 3.1 for watcher to feed events)
  ├── 4.1 System event mapper handler
  ├── 4.2 VisionCache module
  └── 4.3 Episodic memory storage       (depends on 4.2, 3.1)
         │
         ▼
Phase 5 (fail-safe diagnostics)         (depends on 1.1 for capture_on_error gate)
  └── 5.1 Auto-capture on tool failure
```

**Parallelizable:** Phases 3 and 5 can be built in parallel after Phase 1. Phase 4 depends on Phase 3's watcher existing. Phase 2 depends on Phase 1's consent gate but is independent of Phase 3.

**Recommended execution order:** 1 → 2 → 3 → 5 → 4 (defer memory/cognition until the watcher is proven).

---

## File Manifest

### New files
| File | Phase | Purpose |
|------|-------|---------|
| `halbert_core/vision/watcher.py` | 3 | VisualWatcher background task |
| `halbert_core/vision/cache.py` | 4 | Disk cache for screenshots |
| `tests/test_being_config_senses.py` | 1 | SensesConfig tests |
| `tests/test_visual_intent.py` | 2 | Intent detection + routing tests |
| `tests/test_planning_auto_capture.py` | 2 | PLANNING auto-capture tests |
| `tests/test_visual_watcher.py` | 3 | VisualWatcher tests |
| `tests/test_vision_cache.py` | 4 | Disk cache tests |
| `tests/test_diagnostic_capture.py` | 5 | Fail-safe diagnostic tests |

### Modified files
| File | Phase | Changes |
|------|-------|---------|
| `config/being_config.py` | 1 | Add `SensesConfig`, `SensesVisionConfig` |
| `dashboard/routes/agent.py` | 1 | Gate `register_vision_tools()`, remove duplicates |
| `dashboard/frontend/src/pages/Settings.tsx` | 1 | Senses UI section |
| `intake/signals.py` | 2 | `_VISUAL_INTENT_RE`, `has_vision_request` field |
| `intake/pipeline.py` | 2 | `has_vision_request` on `MessageIntake`, routing |
| `agents/state_machine.py` | 2, 5 | PLANNING auto-capture, EXECUTING diagnostic capture |
| `dashboard/app.py` | 3 | Schedule VisualWatcher |
| `integrations/system_event_mapper.py` | 4 | `visual_anomaly` event handler |

---

## Privacy & Consent Summary

| Capability | System gate (`vision_config.yml`) | Persona gate (`being.yml`) |
|---|---|---|
| User-requested capture (LLM tool call) | `screen_capture.enabled` | not required |
| Auto-capture on visual intent (PLANNING) | `screen_capture.enabled` | `senses.vision.capture_on_intent` |
| Proactive monitoring (VisualWatcher) | `screen_capture.enabled` | `senses.vision.enabled` + `senses.vision.proactive_monitoring` |
| Diagnostic capture on tool failure | `screen_capture.enabled` | `senses.vision.capture_on_error` |
| Episodic memory storage | — | `senses.vision.enabled` (via watcher) |

**Both gates must be enabled for proactive/automatic capture.** User-requested capture (the LLM calling `capture_screenshot`) only requires the system gate — the user already opted in by enabling screen capture, and the LLM is responding to an explicit request.

Redaction (`vision_config.yml` `redaction.enabled`) applies to all capture paths — the existing `redact_image()` runs in `vision_tools.py` regardless of how the capture was triggered.
