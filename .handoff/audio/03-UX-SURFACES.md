# UX Surfaces (Corrected)

> **Document:** `.handoff/audio/03-UX-SURFACES.md`
> Each surface mapped to existing frontend architecture.

---

## Surface 1: Acoustic Aura & Voice Waveform

Location: `components/Layout.tsx` header bar, next to mode switch.

```
[Logo] Halbert Home | Living Room | ( ( ( . ) ) ) Idle
```

### States
1. **Idle**: Calm breathing aura. Shows connected satellites.
2. **Listening** (wake-word/hotkey): 32-bar fluid frequency visualizer.
3. **Recognized**: Speaker badge `[ Eric (Admin) - 96% Match ]`
4. **Thinking**: Indeterminate pulse (LLM planning).
5. **Speaking**: Synchronized speech waveform + "Tap to Interrupt" prompt.

### Component
`components/AcousticAuraIndicator.tsx` (NEW)
- Polls `/api/audio/status` for state
- Renders SVG-based aura animation (no emoji — use icon fonts or SVG)
- State transitions driven by SSE events from `/api/being/events` (existing)

### Voice HUD (active turn)
`components/agent/AgentChat.tsx` — add `VoiceTurnHUD` sub-component below
response area when audio turn is active. Shows transcript, speaker, dB,
waveform, interrupt/mute controls.

### Data flow
```
audio/pipeline.py -> SSE event (audio_state_change)
  -> /api/being/events (existing SSE)
  -> useBeingEvents hook (existing)
  -> AcousticAuraIndicator reads state
```

---

## Surface 2: macOS Menu Bar Companion

### Tauri integration
- **Menu bar tray**: Tauri v2 `tray-icon` feature (CONFIRMED built-in). Uses
  `NSStatusItem` on macOS.
- **Global hotkey**: `tauri-plugin-global-shortcut` (CONFIRMED built-in).
  `Cmd+Shift+Space` registered in Rust.
- **Floating HUD**: Requires `tauri-nspanel` crate (third-party) +
  `macos-private-api` feature. This creates a non-stealing NSPanel like
  Siri/Apple Intelligence. **Caveat**: may affect App Store distribution.
  If App Store is required, use standard Tauri windows (steals focus).

### Rust side
```
src-tauri/src/
  audio_capture.rs    # cpal input -> AEC -> loopback TCP socket
  audio_hud.rs        # NSPanel management (via tauri-nspanel)
  audio_hotkey.rs     # Global shortcut registration
```

### Cargo.toml additions
```toml
[dependencies]
# existing...
cpal = "0.22"
tauri-plugin-global-shortcut = "2"
tauri-nspanel = "0.4"  # macOS floating HUD (requires macos-private-api)

[features]
# existing tray-icon...
# Enable for HUD: macos-private-api
```

### Component
`components/VoiceCompanionPill.tsx` (NEW)
- Renders in the NSPanel webview
- Shows: Halbert logo, speaker badge, streaming transcript, tool call
  indicators, waveform, Esc/Space controls
- Communicates with main app via Tauri events (NOT IPC for audio data)

### Audio transport (CORRECTED)
Rust `cpal` captures PCM -> AEC applied -> writes to **loopback TCP socket**
(127.0.0.1:port) -> Python `audio/ingress/local_mic.py` reads from socket.

Tauri IPC is used ONLY for:
- Start/stop capture commands
- Mute toggle
- HUD state updates (transcript text, speaker name)

NOT for audio data. Tauri IPC serializes <1024 byte payloads as JSON arrays
and blocks ~50ms per chunk. Audio must go through the socket.

---

## Surface 3: Speaker Enrollment & Biometric Governance

Location: `pages/Settings.tsx` -> Audio tab -> Speaker Profiles section.

```
+-------------------------------------------------------------------+
| HOUSEHOLD VOICE BIOMETRICS & PERMISSION GATES                     |
+-------------------------------------------------------------------+
|  Enrolled Speakers (3)                                            |
|  [ Eric Bintner (Admin)     98% Conf  Edit  Test ]               |
|    Permissions: Full System Access (ZFS, SSH, Deadbolts)          |
|  [ Sarah (Member)           94% Conf  Edit  Test ]               |
|    Permissions: Standard Home (Lights, Thermostat, Media)         |
|  [ Guest (Restricted)       Auto-Assigned       Gate ]           |
|    Permissions: Read-Only (PIN required for locks)                |
|                                                                   |
|  [ + Enroll New Household Voice ]                                 |
|                                                                   |
|  Enrollment Wizard:                                               |
|  Step 1 of 3: "Say: 'Hey Halbert, check system health'"          |
|  [ Listening... =========== 100% ]                               |
|  Generated 256-dim CAM++ centroid. Quality: Excellent (0.96).    |
+-------------------------------------------------------------------+
```

### Components
`components/SpeakerProfilesCard.tsx` (NEW)
- Lists enrolled speakers from `GET /api/audio/speakers`
- Edit/Test/Delete buttons per speaker
- Role selector (admin/member/guest/restricted)

`components/VoiceEnrollmentModal.tsx` (NEW)
- 3-step wizard:
  1. Capture audio (browser mic or local mic)
  2. Extract embedding (POST to `/api/audio/speakers/enroll`)
  3. Confirm quality + assign role
- Shows 256-dim centroid quality score (NOT 192-dim)

### Backend
`POST /api/audio/speakers/enroll` accepts:
- Audio data (base64 WAV or raw PCM)
- Name, role
- Returns: speaker_id, confidence, quality_score

Uses `sherpa_onnx.SpeakerEmbeddingExtractor` to compute embedding,
`SpeakerEmbeddingManager.add()` to store, `SpeakerProfileStore` to persist.

---

## Surface 4: Acoustic Anomaly Cards

Location: Existing proactive events system + module registry.

### Via existing findings pipeline
Acoustic anomalies become `Finding` objects (detector="acoustic_anomaly").
They automatically appear in:
- `ProactiveEventsBadge.tsx` (bell icon, unread count) — ALREADY EXISTS
- SSE stream at `/api/being/events` — ALREADY EXISTS
- Snooze/dismiss actions — ALREADY EXISTS (via `being.py` routes)

### Via module registry (for inline conversation rendering)
Register `acoustic-anomaly` module in `modules/registry.py`:
```python
ModuleDef(
    name="acoustic-anomaly",
    component="AcousticAnomalyModule",
    data_fetcher="/api/audio/anomalies",
    ...
)
```

`components/modules/AcousticAnomalyModule.tsx` (NEW):
- Shows sound class (CED/Zipformer label, NOT AudioSet label)
- Location (area_id + source satellite)
- Confidence, dB level
- Action taken (proactive TTS alert)
- Buttons: View Camera, Mute/False Alarm, Call Emergency

### Corrected class labels
The original wireframe shows `"Smoke detector, smoke alarm (T3 Pattern)"`
which is an AudioSet/YAMNet class name. Since we use CED-tiny (not YAMNet),
the actual class labels will differ. Map CED output to human-readable labels:

```python
# audio/acoustic/label_map.py (NEW)
CED_TO_HUMAN = {
    "Smoke_alarm": "Smoke detector alarm",
    "Glass_breaking": "Glass break",
    "Water": "Water leak / running water",
    "Mechanical_fan": "Fan / mechanical noise",
    # ... map actual CED-tiny output classes
}
```

### Temporal Chronicle
The existing findings UI IS the temporal chronicle for anomalies. No
separate `TemporalChronicle.tsx` component needs to be built — the
findings list with timestamps, severity, and Four-Whys annotations
already provides this.

---

## Surface 5: Audio & Voice Settings

Location: `pages/Settings.tsx` -> Audio tab (new, alongside Vision tab).

```
+-------------------------------------------------------------------+
| AUDIO & VOICE SETTINGS                                            |
+-------------------------------------------------------------------+
|  Primary Audio Ingress Engine:                                    |
|  (*) Local Sovereign Engine (Offline)                             |
|      sherpa-onnx + Silero VAD + CAM++ + Piper TTS                 |
|  ( ) Cloud Interactive Omni Stream                                |
|      Gemini Live API (~200-370ms duplex, not guaranteed)          |
|                                                                   |
|  Connected Ingress Channels:                                      |
|  [x] Host Built-in Microphone (macOS CoreAudio / cpal)            |
|  [x] Wyoming TCP Satellites (port 10400)                          |
|      Living Room ESP32-S3 (living_room) - Active                  |
|      Kitchen Atom Echo (kitchen) - Active                         |
|  [x] Frigate Security Camera RTSP Audio                           |
|      Driveway Camera (outdoor) - AED only                         |
|                                                                   |
|  Acoustic Privacy & Quiet Hours:                                  |
|  [x] Enable Quiet Hours: [22:00] to [07:00]                      |
|  [x] Ignore background TV/Media speech during music               |
|  [x] Delete raw audio buffer after transcription (no WAV stored)  |
|                                                                   |
|  Music Recognition:                                               |
|  [x] Enable ambient music tagging (REQUIRES NETWORK for AcoustID) |
|      Offline mode: fingerprinting only, no song lookup            |
+-------------------------------------------------------------------+
```

### Component
`components/AudioSettingsTab.tsx` (NEW) or inline in Settings.tsx as
`AudioSettings` function component (mirroring `VisionSettings` pattern).

### Config file
`~/.config/halbert/audio_config.yml`:
```yaml
enabled: false  # ALL OFF by default (mirrors vision pattern)
local_mic:
  enabled: false
  device_index: 0
  sample_rate: 16000
  aec_enabled: true
wyoming_ingress:
  enabled: false
  host: "0.0.0.0"
  port: 10400
rtsp_ingress:
  enabled: false
  cameras: []
acoustic_events:
  enabled: false
  energy_floor_db: -45
  check_interval_s: 2.0
music_recognition:
  enabled: false
  requires_network: true
speaker_id:
  enabled: false
  threshold: 0.75
tts:
  enabled: false
  voice_model: ""  # path to Piper .onnx voice
  speaker_id: 0
quiet_hours:
  enabled: false
  start: "22:00"
  end: "07:00"
privacy:
  delete_raw_after_transcription: true
  ignore_tv_media: true
  retain_no_wav: true
```

### Quiet hours integration
`halbert_core/proactive/gate.py` already checks `BeingConfig.quiet_hours`.
The audio config's quiet_hours should sync with `being_config.quiet_hours`
to avoid two separate quiet-hours settings. Either:
- (a) Audio reads `being_config.quiet_hours` directly, or
- (b) Audio config has its own quiet_hours for audio-specific muting
  (proactive TTS suppression) while being_config handles general
  proactivity.

Recommendation: (b) — audio quiet hours mutes TTS output specifically,
while being quiet hours mutes all proactive events. They can overlap.
