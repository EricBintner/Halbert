# Codebase Integration Map: Halbert Audio AI Subsystem

> **Document:** `audio-research/02-CODEBASE-INTEGRATION-MAP.md`  
> **Status:** Codebase Integration Mapping  
> **Date:** 2026-08-29  

---

## 1. Mirroring the Vision Subsystem Pattern

Halbert's audio subsystem directly mirrors the proven architecture established for Vision in [`cv-research/04-CORE-OPENCV-PLAN.md`](file:///Volumes/4TB-BAD/Halbert/cv-research/04-CORE-OPENCV-PLAN.md):

```
┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
│ Vision Component (Established)       │ Corresponding Audio Component (Audio Cortex)                │
├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ `halbert_core/vision/capture.py`     │ `halbert_core/audio/ingress/local_mic.py`                    │
│ `halbert_core/vision/frame_proc.py`  │ `halbert_core/audio/buffer.py` (16kHz PCM circular ring)    │
│ `halbert_core/dashboard/routes/vision.py`│ `halbert_core/dashboard/routes/audio.py`                │
│ `dashboard/frontend/.../VisionSettings.tsx`│ `dashboard/frontend/.../AudioSettingsTab.tsx`           │
│ `integrations/state_trackers.py`     │ `audio/acoustic/anomaly_detector.py`                        │
│ `AgentChat.tsx` (Camera capture icon)│ `AgentChat.tsx` / `Layout.tsx` (Acoustic Aura & Mic toggle) │
└──────────────────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 2. Integration Points by Codebase File

### 2.1 Backend Ingress & Engine Integration
1. **[`halbert_core/halbert_core/dashboard/app.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/app.py):**
   * Mount new FastAPI audio router: `app.include_router(audio.router, prefix="/api/audio", tags=["audio"])`.
   * Start `AuditoryCortexCoordinator` background task during server startup (delayed background thread alongside Wyoming).
2. **[`halbert_core/halbert_core/integrations/wyoming_agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/wyoming_agent.py):**
   * Upgrade line 232 (`elif msg_type == "audio-chunk": pass`) to pipe raw binary PCM chunks into `AuditoryCortexCoordinator.push_pcm_chunk()`.
   * Preserve existing `transcript` handler for backwards compatibility with legacy text-only satellites.
3. **[`halbert_core/halbert_core/integrations/system_event_mapper.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/integrations/system_event_mapper.py):**
   * Add `map_acoustic_event(event: AcousticEvent) -> SystemEvent`:
     * Maps `smoke_detector_alarm` $\to$ `SystemEvent(level=SystemEventLevel.CRITICAL, category="life_safety")`.
     * Maps `glass_shatter` $\to$ `SystemEvent(level=SystemEventLevel.SECURITY, category="perimeter")`.
     * Maps `music_detected` $\to$ `SystemEvent(level=SystemEventLevel.INFO, category="ambient_media")`.

---

### 2.2 Safety & RoleGate Authorization
1. **[`halbert_core/halbert_core/approval/engine.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/approval/engine.py) & [`tools/system_tools.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/tools/system_tools.py):**
   * Introduce `RoleGateCheck`:
   ```python
   def evaluate_voice_authorization(turn: VoiceTurn, tool_name: str) -> bool:
       if tool_name in PRIVILEGED_SYSADMIN_TOOLS: # ZFS rebuild, system reboot, iptables
           return turn.speaker_role == "admin" and turn.speaker_confidence >= 0.75
       return True
   ```

---

### 2.3 Cognition & Persona Memory
1. **[`halbert_core/halbert_core/memory/persona_memory.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/memory/persona_memory.py):**
   * Store enrolled speaker embeddings in `speaker_profiles` SQLite table.
   * Store acoustic anomalies and ambient music tracks in `PersonaMemoryStore` under `MemoryType.EPISODIC`.

---

### 2.4 Frontend Integration Map (`dashboard/frontend/src/`)
1. **[`pages/Settings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx):**
   * Add `{ id: 'audio', label: 'Audio & Voice', icon: Mic }` to `SETTINGS_SECTIONS` under `system-security`.
   * Render `<AudioSettingsTab />` and `<SpeakerProfilesCard />`.
2. **[`components/Layout.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx):**
   * Add `<AcousticAura />` into the global header bar next to `<ModeSwitch />` and background indicators.
3. **[`components/agent/AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx):**
   * Add microphone toggle button to chat input box, triggering local VAD stream with live token transcript.
4. **[`components/agent/Timeline.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx) / `pages/Home.tsx`:**
   * Render `<AcousticEventCard />` for environmental alarms and music listening history in the Temporal Chronicle.

---

### 2.5 Desktop Shell Integration (`src-tauri/`)
1. **[`src-tauri/Cargo.toml`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src-tauri/Cargo.toml):**
   * Add crates: `cpal = "0.15"`, `rubato = "0.14"`, `tauri-nspanel = "2.0"` (for macOS non-activating floating HUD).
2. **[`src-tauri/src/lib.rs`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src-tauri/src/lib.rs):**
   * Register global hotkey `Cmd+Shift+Space` triggering `<VoiceCompanionPill />` HUD.
   * Manage local microphone stream lifecycle with OS permissions.

---

### 2.6 Package Dependencies (`pyproject.toml`)
```toml
# halbert_core/pyproject.toml
[project.optional-dependencies]
audio = [
    "sherpa-onnx>=1.10.0",
    "onnxruntime>=1.18.0",
    "sounddevice>=0.4.6",
    "pyacoustid>=1.2.2",
]
```
*(Remains optional extra under Haloysius subtractive contract — installed automatically in `home` and `pro` desktop variants).*
