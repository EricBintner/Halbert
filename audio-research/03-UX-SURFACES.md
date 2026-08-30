# UX Surfaces & Product Interaction Plan: Halbert Audio AI

> **Document:** `audio-research/03-UX-SURFACES.md`  
> **Status:** Final UX Specification & Frontend Component Plan  
> **Date:** 2026-08-29  
> **Target Framework:** React 18.2 / 19 (TypeScript, Tailwind CSS, Lucide Icons, Tauri v2)  

---

## 1. UX Design Philosophy: Ambient Sentience

Halbert's audio user experience adheres to three core design rules:
1. **Never Jarring, Always Glanceable:** Audio perception is communicated through organic ambient cues (the "Acoustic Aura" gradient and subtle frequency waveforms) rather than aggressive popups.
2. **Context-Aware Biometrics:** When an authorized administrator speaks, the UI reflects verification instantly (`[ 👤 Eric • Admin ]`), confirming security clearance before executing sensitive commands.
3. **Non-Intrusive Desktop Companion:** For sysadmin workflows, Halbert Pro's voice HUD never steals focus from active IDEs or terminals (`tauri-nspanel` non-activating floating panel).

---

## 2. The 5 Core UX Surfaces

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                HALBERT AUDIO UX SUITE                                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Ambient Acoustic Aura & Waveform  │ Top bar header & Chat input (Real-time duplex)  │
│ 2. macOS Floating Voice Companion    │ Global hotkey (Cmd+Shift+Space) non-stealing HUD│
│ 3. Speaker Voiceprint & Role Gates   │ 3-step enrollment wizard & permission matrix    │
│ 4. Acoustic Anomaly Chronicle Cards  │ Alarm/Anomaly feeds with camera snapshot inlays │
│ 5. Audio Ingress & Privacy Settings  │ Local vs Cloud toggle, Quiet Hours scheduler    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### UX Surface 1: The Ambient "Acoustic Aura" & Voice Waveform

Located in the global application header ([`Layout.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/Layout.tsx)) and the chat input area ([`AgentChat.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx)).

```
+-----------------------------------------------------------------------------+
│ [Logo] Halbert | 📍 Office | ( ( ( ● ) ) ) [ 👤 Eric • Admin (96%) ]        │
+-----------------------------------------------------------------------------+
```

#### Component: `AcousticAura.tsx`
* **Props:**
  ```typescript
  interface AcousticAuraProps {
    state: 'idle' | 'listening' | 'recognizing' | 'thinking' | 'speaking' | 'muted'
    decibelLevel: number // -60dB to 0dB
    speaker?: { name: string; role: 'admin' | 'member' | 'guest'; confidence: number }
    activeArea?: string
  }
  ```
* **State Progression:**
  * `idle`: Subtle, breathing canvas aura (`opacity-40`, charcoal ring).
  * `listening`: Expands into dynamic 16-bar frequency visualizer reacting to microphone input volume.
  * `recognizing`: Displays pill badge: `[ 👤 Eric (Admin) • 96% ]`.
  * `thinking`: Fluid vermilion gradient pulse across header bar.
  * `speaking`: Symmetric vocal waveform with clickable **"Tap or Press Space to Interrupt"** (barge-in).

```
+-----------------------------------------------------------------------------+
│ ACTIVE DUPLEX VOICE HUD (Inside AgentChat or Overlay)                       │
│                                                                             │
│  "Shut down the test database container and rebuild ZFS pool"               │
│  👤 Eric Bintner (Admin Verified • 98%) | 📍 Server Room | 🔊 76dB          │
│                                                                             │
│  ▂▃▅▇█▆▅▃▂ [Speaking: "Stopping container db-test-01. Starting ZFS..."]    │
│                                                                             │
│  [ Space / Click to Interrupt ]                       [ Mute Mic (Cmd+M) ]  │
+-----------------------------------------------------------------------------+
```

---

### UX Surface 2: macOS Menu Bar Floating Companion (`VoiceCompanionPill.tsx`)

#### Desktop Shell Caveat (`tauri-nspanel`)
A major usability flaw in standard desktop voice assistants is that summoning the voice UI steals window focus from the user's active code editor or terminal. Halbert Pro solves this using **`tauri-nspanel`** (Rust bindings to macOS `NSPanel` with the `.nonactivatingPanel` style mask):
* The floating HUD renders on screen without defocusing the active VS Code / Terminal window.
* Global Hotkey: `Cmd+Shift+Space` (or Push-to-Talk).

```
                  ┌──────────────────────────────────────────────┐
                  │ ⚡ Halbert Pro  |  👤 Eric (Admin)           │
                  │ "Rebuilding ZFS pool data-01..."             │
                  │ ▂▃▅█▆▅▃▂  [ Esc: dismiss | Space: pause ]    │
                  └──────────────────────────────────────────────┘
```

#### Interaction Flow:
1. User presses `Cmd+Shift+Space`.
2. Floating HUD smoothly slides down from the macOS menu bar at top-center.
3. User speaks command; live transcript streams into the HUD in real-time.
4. Agent executes tools with live status indicators (`[✓ Container Stopped]`).
5. Agent speaks response audio via Piper TTS; pressing `Esc` dismisses the HUD immediately.

---

### UX Surface 3: Speaker Voiceprint & Role Governance (`SpeakerProfilesCard.tsx`)

Located in [`pages/Settings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx) under `System & Security → Audio & Voice`.

```
+-----------------------------------------------------------------------------+
│ HOUSEHOLD VOICE BIOMETRICS (CAM++ 256-Dim Embeddings)                       │
+-----------------------------------------------------------------------------+
│                                                                             │
│  Enrolled Speakers (3)                                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 👤 Eric Bintner (Admin)                 [ 98% Match ]  [ Test ] [ Edit]│  │
│  │    Permissions: Full Root (ZFS, SSH, Reboot, Alarm Disarm)            │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 👤 Sarah (Member)                       [ 94% Match ]  [ Test ] [ Edit]│  │
│  │    Permissions: Standard Home (Lighting, Thermostat, Media, Vacuum)   │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 👤 Guest / Unknown Voice (Restricted)   [ Auto-Gated ]        [ Rules ]│  │
│  │    Permissions: Safe Queries Only (PIN required for high-risk actions)│  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [ + Enroll New Household Voice ]                                           │
+-----------------------------------------------------------------------------+
```

#### Enrollment Wizard Modal (`VoiceEnrollmentModal.tsx`):
1. **Turn 1:** *"Please say: 'Hey Halbert, check system health'"* (Captures speech baseline).
2. **Turn 2:** *"Please say: 'Turn off the lights in the office and lock the front door'"* (Captures acoustic cadence).
3. **Turn 3:** *"Please say: 'Halbert, emergency system status'"* (Captures stress/pitch variance).
4. **Result:** Computes 256-dim centroid with SNR quality score: `[ Centroid Generated • Quality: 96% Excellent ]`.

---

### UX Surface 4: Environmental Acoustic Anomaly Cards in Temporal Chronicle

Environmental sound events and alarms are categorized into **6 Human Categories** via `AcousticEventMapper` and rendered directly in the Temporal Chronicle ([`Timeline.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/agent/Timeline.tsx)):

```
+-----------------------------------------------------------------------------+
│ TEMPORAL CHRONICLE — ACOUSTIC OBSERVATIONS                                  │
+-----------------------------------------------------------------------------+
│                                                                             │
│  [16:42:10] 🚨 CRITICAL LIFE SAFETY ANOMALY                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Category: Life Safety | Class: Smoke Detector (T3 Pulse Alarm)         │  │
│  │ Location: Kitchen (Wyoming Satellite #2) | Sound Level: 89 dB FS      │  │
│  │ Confidence: 94.8% (YAMNet CED Model)                                  │  │
│  │ Action Taken: Proactive TTS broadcast dispatched to all living areas. │  │
│  │ [ View Kitchen Camera ]   [ Mute False Alarm ]   [ Call Emergency ]   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [15:18:04] ⚠️ MECHANICAL ACOUSTIC ADVISORY                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Category: Mechanical | Class: High-frequency bearing friction / whine │  │
│  │ Location: Server Rack (Local Host Mic) | Peak Frequency: 4.8 kHz      │  │
│  │ Confidence: 81.2% | Severity: Advisory                                │  │
│  │ Recommendation: Inspect chassis fan #2 before thermal throttling.     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  [14:02:50] 🎵 AMBIENT MUSIC LOGGED                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Track: Daft Punk — Solar Sailer (TRON: Legacy)                        │  │
│  │ Genre: Electronic / Synthwave | Identified via: AcoustID / Local CLAP │  │
│  │ [ ❤️ Add to Liked Tracks ]   [ View Listening History ]               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
+-----------------------------------------------------------------------------+
```

---

### UX Surface 5: Audio Ingress & Privacy Settings (`AudioSettingsTab.tsx`)

```
+-----------------------------------------------------------------------------+
│ AUDIO & VOICE SETTINGS                                                      │
+-----------------------------------------------------------------------------+
│                                                                             │
│  Inference Engine Mode:                                                     │
│  (*) Local Sovereign Engine (Offline)                                       │
│      Uses sherpa-onnx + Silero VAD + Piper TTS (<135MB, zero cloud egress)  │
│  ( ) Cloud Interactive Omni Stream                                          │
│      Uses Gemini Multimodal Live API (Ultra-low 220ms fluid conversational) │
│                                                                             │
│  Ingress Sources:                                                           │
│  [x] Host Built-in Microphone (macOS CoreAudio / cpal)                      │
│  [x] Wyoming TCP Satellites (Listening on port 10400 / 10401)               │
│      • Living Room Satellite (Area: living_room) — [ Online ]               │
│      • Kitchen Atom Echo (Area: kitchen) — [ Online ]                       │
│  [x] Frigate Security Camera RTSP Audio Tracks                              │
│      • Driveway Camera (Area: outdoor) — [ Monitoring AED Only ]            │
│                                                                             │
│  Acoustic Privacy & Quiet Hours:                                            │
│  [x] Enable Quiet Hours (Mute proactive voice alerts):  [ 22:00 ] to [ 07:00│
│  [x] Discard raw audio buffers immediately after transcription (No WAVs)    │
│  [x] Filter background TV / Media babble during music playback              │
+-----------------------------------------------------------------------------+
```
