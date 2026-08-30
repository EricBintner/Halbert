# Codebase Integration Map

> **Document:** `.handoff/audio/02-CODEBASE-INTEGRATION-MAP.md`
> Every integration point mapped to actual files in the Halbert codebase.

---

## 1. Existing patterns to mirror

The audio subsystem should follow the **vision subsystem pattern** exactly.
Vision was built with the same subtractive contract, lazy imports, config
gating, and agent tool integration that audio needs.

### Vision pattern reference

| Concern | Vision file | Audio equivalent (new) |
|---------|-------------|----------------------|
| Config schema (yaml, all OFF by default) | `halbert_core/vision/config.py` | `halbert_core/audio/config.py` |
| Config path | `~/.config/halbert/vision_config.yml` | `~/.config/halbert/audio_config.yml` |
| Lazy inference modules | `halbert_core/vision/inference/` | `halbert_core/audio/speech/` + `audio/acoustic/` |
| Agent tools | `halbert_core/tools/vision_tools.py` | `halbert_core/tools/audio_tools.py` |
| Dashboard routes | `halbert_core/dashboard/routes/vision.py` | `halbert_core/dashboard/routes/audio.py` |
| Settings tab | `pages/Settings.tsx` -> VisionSettings component | `pages/Settings.tsx` -> AudioSettings component |
| Route registration | `app.py` line 300 | `app.py` (add after vision) |

### Key vision patterns to copy

1. **Config read-on-every-use** (not cached): `vision/config.py` reads yaml
   on every capture attempt so disabling webcam takes effect immediately.
   Audio config must do the same — a user who disables mic access must not
   have frames captured before next restart.

2. **Feature flag gating**: `is_screen_capture_enabled()` /
   `is_webcam_enabled()` gates. Audio needs `is_audio_enabled()`,
   `is_local_mic_enabled()`, `is_wyoming_ingress_enabled()`.

3. **Lazy import inside functions**: `vision/inference/detector.py` does
   `try: import onnxruntime` inside functions, not at module top. Every
   audio module must do the same with `sherpa_onnx`.

4. **Tool handler returns dict**: `vision_tools.py` returns
   `{"image": base64, "description": text}`. Audio tools return
   `{"transcript": text, "speaker_id": name, "speaker_role": role}`.

---

## 2. Anomaly routing — dual consumer

Acoustic anomalies must flow through TWO existing systems:

### Consumer 1: Findings pipeline (for chronicle, gate, SSE)

```
audio/acoustic/anomaly_detector.py
  -> creates Finding(detector="acoustic_anomaly", severity=..., ...)
  -> DetectorRunner stores in FindingStore
  -> ProactiveGate checks: proactivity dial, quiet hours, snooze, dismissal
  -> EventBus publishes ProactiveEvent
  -> SSE route (/api/being/events) streams to frontend
  -> ProactiveEventsBadge.tsx shows notification
```

**Files involved:**
- `halbert_core/proactive/detector_runner.py` — add `AcousticAnomalyDetector` to `self.detectors` list
- `halbert_core/findings/store.py` — `Finding` dataclass (has `detector`, `severity`, `why_now/care/so/trust`)
- `halbert_core/proactive/gate.py` — `ProactiveGate` (checks dial, quiet hours, snooze)
- `halbert_core/proactive/events.py` — `ProactiveEvent` + `get_event_bus()`
- `halbert_core/dashboard/routes/being.py` — SSE stream at `/api/being/events`

**New file:** `halbert_core/findings/detectors/acoustic_anomaly.py`
- Follows pattern of `findings/detectors/dropin_conflicts.py`
- `detect()` method returns `List[Finding]`
- Registered in `DetectorRunner.__init__` `self.detectors` list
- Add to `_EVENT_CATEGORY` mapping: `"acoustic_anomaly": "acoustic"`

### Consumer 2: Cognition (for worries, emotions)

```
audio/acoustic/anomaly_detector.py
  -> SystemEventMapper.add_event(
       event_type="acoustic_anomaly",
       severity="critical" | "warning",
       source="audio:kitchen_satellite",
       detail="Smoke detector alarm detected, 94.8% confidence"
     )
  -> populate_cognition() on next cognitive tick
  -> cognition.worries.add_worry(category="acoustic_safety", ...)
  -> cognition.emotional_state.add_emotion(FEAR, ...)
```

**File:** `halbert_core/integrations/system_event_mapper.py`
- `add_event(event_type, severity, source, detail)` — thread-safe, queues for next tick
- Need to add `"acoustic_anomaly"` handler in `_apply_event_to_cognition()`
- Pattern: mirror the existing `"security_anomaly"` handler (lines 159-171)

---

## 3. Speaker role gating — RoleGate wrapper

### Current state
`halbert_core/tools/safety.py` `ToolSafetyFramework.classify(tool_name, args)`
classifies by command pattern + sensitive paths + skill constraints. It is
synchronous, stateless, and has NO identity/role axis.

### Design: RoleGate (new, do NOT modify ToolSafetyFramework)

```python
# halbert_core/tools/role_gate.py (NEW)

class RoleGate:
    """Wraps ToolSafetyFramework to enforce speaker-role-based access.
    
    Can only TIGHTEN (never loosen) the base classification.
    Mirrors how _check_skill_safety composes with _classify_builtin.
    """
    
    ROLE_MAX_RISK = {
        "admin":    "critical",  # admin can do anything the base allows
        "member":   "high",      # member capped at HIGH
        "guest":    "medium",    # guest capped at MEDIUM
        "restricted": "low",     # restricted capped at LOW
        "unknown":  "medium",    # unknown speaker treated as guest
    }
    
    def __init__(self, safety_framework):
        self._safety = safety_framework
    
    def classify(self, tool_name, args, speaker_role="unknown"):
        base = self._safety.classify(tool_name, args)
        
        max_risk = self.ROLE_MAX_RISK.get(speaker_role, "medium")
        if _RISK_ORDER[base.risk_level.value] > _RISK_ORDER[max_risk]:
            return SafetyCheckResult(
                risk_level=RiskLevel(max_risk),
                allowed=False,  # BLOCKED by role gate
                requires_confirmation=False,
                reason=f"Blocked: speaker role '{speaker_role}' cannot execute {base.risk_level.value} operations",
                matched_rule="role_gate",
            )
        
        # For unknown speakers on HIGH-risk ops, require confirmation
        if speaker_role == "unknown" and base.risk_level == RiskLevel.HIGH:
            return SafetyCheckResult(
                risk_level=base.risk_level,
                allowed=True,
                requires_confirmation=True,
                reason=f"Unknown speaker — confirmation required for {base.risk_level.value} operation",
                matched_rule="role_gate.unknown_confirm",
            )
        
        return base
```

### Integration point
The agent state machine calls `classify()` before tool execution. The
`RoleGate` wraps the existing `ToolSafetyFramework` instance. The speaker
role comes from `speaker_id.py` verification, threaded through the voice
turn observation into the state machine context.

**Files:**
- `halbert_core/tools/safety.py` — DO NOT MODIFY (high blast radius)
- `halbert_core/tools/role_gate.py` — NEW
- `halbert_core/agents/state_machine.py` — thread `speaker_role` into tool execution path

---

## 4. Speaker profile storage

### Current state
No biometric store exists. `memory/hybrid.py` is a vector + episodic memory
system (MemoryType.EPISODIC). It is not designed for biometric centroids.

### Design: SpeakerProfileStore (new)

```python
# halbert_core/audio/storage/speaker_store.py (NEW)

class SpeakerProfileStore:
    """SQLite store for enrolled household speaker voiceprints.
    
    Uses sherpa-onnx SpeakerEmbeddingManager for cosine similarity math.
    This class handles persistence only.
    """
    
    def __init__(self, db_path=None):
        # Default: data_subdir("audio") / "speaker_profiles.db"
        ...
    
    def enroll(self, speaker_id, name, role, embedding, threshold=0.75): ...
    def update_centroid(self, speaker_id, new_embedding): ...
    def get(self, speaker_id) -> Optional[SpeakerProfile]: ...
    def list_all(self) -> List[SpeakerProfile]: ...
    def delete(self, speaker_id): ...
```

**Path:** `halbert_core/utils/paths.py` `data_subdir()` — same pattern as
`findings/store.py` which uses `data_subdir("findings")`.

---

## 5. Frontend integration

### Settings tab
`pages/Settings.tsx` has a `SETTINGS_SECTIONS` array (line ~1271) with
sections including `vision`. Add an `audio` section:

```typescript
// In SETTINGS_SECTIONS, add to the appropriate section:
{ id: 'audio', label: 'Audio & Voice', icon: AudioLines },
```

And a corresponding `<TabsContent value="audio">` panel.

### Acoustic aura (header)
`components/Layout.tsx` — the header bar. Add `AcousticAuraIndicator`
component next to the mode switch / instance switch area.

### Anomaly cards (module registry)
`halbert_core/modules/registry.py` — register a new module:
```python
ModuleDef(
    name="acoustic-anomaly",
    component="AcousticAnomalyModule",
    data_fetcher="/api/audio/anomalies",
    prop_contract={"finding_id": "str", "sound_class": "str", ...},
    standalone_route="/audio/anomalies",
    icon="alert-triangle",
    description="Acoustic anomaly observation card",
)
```

`components/ModuleRenderer.tsx` — add to `MODULE_REGISTRY`:
```typescript
const AcousticAnomalyModule = lazy(() => import('./modules/AcousticAnomalyModule'))
// Add to registry: 'acoustic-anomaly': AcousticAnomalyModule,
```

### Voice waveform
`components/agent/AgentChat.tsx` — the conversation area. Add
`VoiceWaveformIndicator` below the response area when audio state is active.

### Proactive events badge
`components/agent/ProactiveEventsBadge.tsx` — ALREADY EXISTS from Phase 8.
Acoustic findings will automatically appear here via the existing SSE pipeline.

---

## 6. Dashboard routes

### New route file
`halbert_core/dashboard/routes/audio.py` (NEW) — mirrors `routes/vision.py`:

```
GET  /api/audio/config           — Load audio_config.yml
POST /api/audio/config           — Save audio config
GET  /api/audio/status           — Audio subsystem status (available, active, sources)
GET  /api/audio/speakers         — List enrolled speaker profiles
POST /api/audio/speakers/enroll  — Enroll new speaker (accepts audio upload)
DELETE /api/audio/speakers/{id}  — Delete speaker profile
POST /api/audio/speakers/{id}/test — Test speaker verification
GET  /api/audio/anomalies        — List recent acoustic events
GET  /api/audio/ingress/status   — List connected ingress sources
```

### Registration
`halbert_core/dashboard/app.py` — add after vision router (line 300):
```python
app.include_router(audio.router, prefix="/api", tags=["audio"])
```

---

## 7. pyproject.toml changes

Add optional dependency groups:

```toml
[project.optional-dependencies]
# ... existing light = [...]

# Audio inference — sherpa-onnx + onnxruntime for VAD/ASR/Speaker ID/AED/TTS
audio-inference = [
  "sherpa-onnx>=1.10",
  "onnxruntime>=1.16",
]

# Acoustic fingerprinting (optional, for music recognition)
audio-fingerprint = [
  "pyacoustid>=1.3",
  "chromaprint>=0.7",  # or system libchromaprint
]

# Fix missing cv-inference group that vision code references
cv-inference = [
  "onnxruntime>=1.16",
  "ultralytics>=8.0",
  "opencv-python>=4.8",
]
```

---

## 8. Agent tools (audio_tools.py)

`halbert_core/tools/audio_tools.py` (NEW) — mirrors `vision_tools.py`:

```python
async def listen(args: Dict) -> Dict[str, Any]:
    """Capture a voice turn from the active audio ingress.
    
    Returns:
        - transcript: str
        - speaker_id: Optional[str]
        - speaker_role: str ("unknown" if not identified)
        - speaker_confidence: float
        - area_id: Optional[str]
        - audio_duration_ms: int
    """

async def identify_speaker(args: Dict) -> Dict[str, Any]:
    """Identify the current speaker from active audio.
    Returns speaker_id, role, confidence.
    """

async def get_audio_status(args: Dict) -> Dict[str, Any]:
    """Get audio subsystem status (sources, VAD state, etc.)
    """
```

### Registration in agent route
`halbert_core/dashboard/routes/agent.py` — register audio tools alongside
existing vision tools, with platform guard (audio only where available).

### Safety classification
`halbert_core/tools/safety.py` — add audio tools to the SAFE classification
list (alongside `capture_screenshot`, `capture_webcam`):
```python
elif tool_name in ("listen", "identify_speaker", "get_audio_status"):
    return SafetyCheckResult(
        risk_level=RiskLevel.SAFE,
        allowed=True,
        requires_confirmation=False,
        reason="Audio capture (read-only)"
    )
```
