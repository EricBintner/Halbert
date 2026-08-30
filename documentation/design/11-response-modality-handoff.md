# Response Modality Handoff: Chat, Voice & Visual Interaction Architecture

> **Document:** `documentation/design/11-response-modality-handoff.md`  
> **Status:** Comprehensive UX & System Architecture Specification  
> **Date:** 2026-08-30  
> **Author:** Product UX & Auditory AI Architecture  
> **Target Framework:** React 18.2 / 19, TypeScript, Tailwind CSS, Tauri v2 (`tauri-nspanel`), Python 3.11 (`halbert_core`)  
> **Reads With:** `documentation/design/the-being.md`, `documentation/design/REVIEW-DESIGN-MECHANICS-2026-08-23.md`, `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md`, `audio-research/01-CORRECTED-ARCHITECTURE.md`, `audio-research/03-UX-SURFACES.md`

---

## 1. Executive Summary & Design Rationale

### 1.1 The Modality Mismatch Problem
Traditional AI assistants suffer from a fundamental modality disconnect:
1. **Chatbots are deaf and blind to physical environment:** Text-based chat UIs assume the user is sitting at a keyboard with 100% visual attention. They cannot detect room context, spoken urgency, acoustic alarms, or user movement across rooms.
2. **Smart speakers are illiterate in dense system state:** Voice assistants attempt to read aloud raw JSON payloads, terminal dumps, and complex diffs. Hearing a synthetic voice recite 80 lines of unified diff or UUID strings is unusable.
3. **Siloed session fragmentation:** If a user initiates a command via a smart speaker in the kitchen, the desktop dashboard has zero awareness of the interaction. If they return to their desk, they must re-explain the entire context from scratch.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             THE CORE DESIGN LAW                             │
│               "Ear for Gist, Eye for Detail, Hands for Intent."             │
├───────────────────┬─────────────────────────────────────────────────────────┤
│ Ear (Audio/Voice) │ High-level synthesis, urgent cues, confirmation, alerts│
│ Eye (Visual/UI)   │ Diffs, logs, telemetry, AST trees, topological graphs   │
│ Hands (Key/Click) │ Precise intent: staged approvals, edits, shell commands │
└───────────────────┴─────────────────────────────────────────────────────────┘
```

Halbert bridges this divide through **Response Modality Handoff**: a unified cognitive model where voice, text, terminal, and rich visual modules are not competing interfaces, but dynamically orchestrated egress streams of a single continuous entity.

---

## 2. Global Modality Matrix & Surface Topology

Halbert operates across diverse physical and virtual surfaces with varying input/output bandwidth:

```
                               ┌──────────────────────────────────┐
                               │   HALBERT COGNITIVE CORE         │
                               │   (Haloysius State Machine)      │
                               └────────────────┬─────────────────┘
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 ▼                              ▼                              ▼
    ┌────────────────────────┐    ┌────────────────────────┐    ┌────────────────────────┐
    │ SURFACE 1: DESKTOP APP │    │ SURFACE 2: FLOATING HUD│    │ SURFACE 3: SATELLITES  │
    │ Full Two-Column GUI    │    │ macOS Menu Bar / Tray  │    │ Wyoming ESP32 / Echo   │
    │ Rich Cards + Terminals │    │ Quick Peek / Non-steal │    │ Voice-first / Audio    │
    │ High Visual Bandwidth  │    │ Medium Visual Bandwidth│    │ Zero Visual Bandwidth  │
    └────────────────────────┘    └────────────────────────┘    └────────────────────────┘
```

### 2.1 Modality Ingress & Egress Capabilities

| Ingress Surface | Ingress Modality | Primary Physical Location | Expected Egress Formats |
|---|---|---|---|
| **Web / Desktop App** (`AgentChat.tsx`) | Keyboard text, drag-and-drop files, screenshot attachments | Active workstation display | Rich Timeline Cards, DiffBlocks, summoned Context Modules, PTY Terminal Blocks. |
| **macOS Floating HUD** (`VoiceCompanionPill.tsx`) | Push-to-Talk / Hotkey voice (`Cmd+Shift+Space`), short text | Overlay on active IDE / Terminal | Streaming voice playback (Piper TTS), compact transcript pill, staged clipboard actions. |
| **Wyoming Satellites** (`wyoming_ingress.py`) | 16kHz far-field voice, wake-word ("Hey Halbert") | Kitchen, living room, server rack | Streaming audio response, room speaker broadcast, proactive chime. |
| **Watched Terminals** (`TerminalTile.tsx`) | CLI keystrokes, shell command executions | Active xterm.js / macOS Terminal | Terminal block replays, staged shell commands, inline status indicators. |
| **Environmental Ingress** (`yamnet.py`) | Continuous 1.0s acoustic spectrograms | All active mic channels & cameras | Proactive Temporal Chronicle cards, critical TTS broadcasts. |

---

## 3. Dynamic Modality Resolution Engine (Dual-Stream Synthesis)

When Halbert generates a response, the cognition engine produces a **Dual-Stream Payload** containing two parallel representations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DUAL-STREAM RESPONSE MODEL                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. PHONETIC ACOUSTIC STREAM (For the Ear)                                  │
│     - Natural conversational prose, strictly ≤ 35 words                     │
│     - Zero Markdown syntax (no backticks, bullets, or brackets)             │
│     - Numbers and units normalized phonetically ("forty-two gigabytes")     │
│     - Directs user attention to screen when dense detail is generated        │
├─────────────────────────────────────────────────────────────────────────────┤
│  2. STRUCTURED VISUAL STREAM (For the Eye & Terminal)                       │
│     - Semantic Markdown, WhyChips with clickable provenance                 │
│     - Interactive DiffBlocks with AST syntax highlighting                   │
│     - Summoned Context Modules (Live Vitals, Storage Health, Docker)        │
│     - Staged execution buttons with rollback guarantees                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
                                  [ User Query ]
                                        │
                                        ▼
                         [ Intake Pipeline & RoleGate ]
                         (Identify Intent, Speaker & Area)
                                        │
                                        ▼
                         [ Halbert State Machine Tick ]
                                        │
                                        ▼
                         [ Dual-Stream Payload Builder ]
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
              [ Phonetic Acoustic Stream ]   [ Structured Visual Stream ]
                         │                             │
                         ▼                             ▼
              [ Modality Router ]            [ SQLite Store & SSE Stream ]
              (Check Screen / Proximity)               │
                         │                             ▼
                         ▼                   [ Render in Timeline & ]
              [ Piper TTS / Speaker ]        [ Summon Context Module]
```

### 3.1 Modality Routing Decision Matrix

```
Let S = Screen Availability (true/false)
Let D = Content Density (1 = Low/Conversational, 2 = Medium/List, 3 = High/Code/Diff)
Let I = Ingress Modality (voice / text / terminal)
Let R = Risk Level (Safe / Moderate / Critical RoleGate)
```

| Ingress ($I$) | Screen ($S$) | Density ($D$) | Risk ($R$) | Egress Strategy & Modality Handoff Behavior |
|:---:|:---:|:---:|:---:|---|
| **Voice** | **True** (Desktop) | Low | Safe | **Spoken + Compact Echo:** Halbert speaks response; HUD renders concise transcript. |
| **Voice** | **True** (Desktop) | High (Diff/Logs) | Safe | **Spoken Digest + Screen Handoff:** Halbert speaks a 1-sentence summary and says *"I've opened the diff on your screen."* Context Region summons `ConfigDiffInspector`. |
| **Voice** | **True** (Desktop) | High | Critical (ZFS/Root) | **Spoken Caution + Staged Approval Gate:** Halbert speaks warning; UI renders staged `ApprovalGate` requiring Level 3 click or PIN confirmation. |
| **Voice** | **False** (Satellite) | Low | Safe | **Spoken Only:** Halbert speaks self-contained conversational answer via satellite speaker. |
| **Voice** | **False** (Satellite) | High (Diff/Logs) | Safe | **Spoken Compression + Stash:** Halbert speaks high-level finding: *"Found 2 conflicting SSH rules. I've staged the fix for your desktop review."* Message appended to timeline for later. |
| **Voice** | **False** (Satellite) | Any | Critical | **Spoken Challenge:** Halbert refuses automated execution: *"Rebooting the server requires admin verification. Please confirm with your voice PIN or approve via the dashboard."* |
| **Text** | **True** | Any | Any | **Visual Stream Only:** Fast silent streaming in Timeline. Audio remains mute unless user clicks `[ 🔊 Listen ]`. |
| **Terminal** | **True** | Any | Safe | **Watched Staging:** Proposed command staged into user shell prompt (Enter required). |

---

## 4. End-to-End User Interaction Workflows

---

### Workflow A: Voice Query with Screen Handoff (The "Look at Your Screen" Pattern)

*Scenario: Alex is at his desk with Halbert Pro open in the background. He presses `Cmd+Shift+Space` and asks a diagnostic question.*

```
+-----------------------------------------------------------------------------+
| 1. INGRESS: Alex presses Cmd+Shift+Space and speaks                         |
|    "Why did the backup fail last night and what should we do?"              |
|                                                                             |
| 2. COGNITIVE PROCESSING:                                                    |
|    - Speaker Biometrics: Alex (Admin Verified • 98%)                        |
|    - Analysis: Tar process ran out of space on /mnt/backup (ZFS quota 100%) |
|    - Output Streams Generated:                                              |
|      • Spoken: "The backup failed because the ZFS backup dataset exceeded   |
|                 its two terabyte quota. I've opened the storage allocation  |
|                 and staged a quota expansion on your screen."               |
|      • Visual: Storage Module + Quota Slider + Unified Diff for zfs set     |
+-----------------------------------------------------------------------------+
```

```
+-----------------------------------------------------------------------------+
| DESKTOP VIEWPORT TRANSITION                                                 |
|                                                                             |
| ┌────────────────────────────────────┐ ┌──────────────────────────────────┐ |
| │ CONVERSATION TIMELINE              │ │ SUMMONED CONTEXT MODULE          │ |
| │                                    │ │                                  │ |
| │ 👤 Alex (Voice • Admin)             │ │ [ STORAGE HEALTH & QUOTAS ]      │ |
| │ "Why did the backup fail last      │ │                                  │ |
| │  night and what should we do?"     │ │ Dataset: pool01/backups          │ |
| │                                    │ │ Used: 2.00 TB / 2.00 TB (100% 🚨) │ |
| │ 🤖 Halbert (First Person)          │ │ [||||||||||||||||||||] FULL      │ |
| │ "The backup failed due to ZFS quota│ │                                  │ |
| │  exhaustion on `/mnt/backup`.      │ │ PROPOSED CHANGE:                 │ |
| │  [WhyChip: ZFS | Quota Exceeded]   │ │ `zfs set quota=3T pool01/backups`│ |
| │                                    │ │                                  │ |
| │  I have prepared a quota increase." │ │ [ APPROVE & APPLY ]  [ DISMISS ] │ |
| └────────────────────────────────────┘ └──────────────────────────────────┘ |
+-----------------------------------------------------------------------------+
```

#### Modality Handoff Mechanics:
1. **Audio Egress:** Piper TTS streams only the 22-word synthesized audio. Alex gets the answer in 2.5 seconds without waiting for a lengthy recitation of numbers.
2. **Visual Egress:** The right-hand Context Region automatically mounts the `StorageHealthModule` with the interactive quota proposal.
3. **Action:** Alex clicks `[ APPROVE & APPLY ]` or types Enter to execute. The system logs the receipt in the timeline.

---

### Workflow B: Cross-Room Handoff (Terminal to Room Satellite)

*Scenario: Alex starts a heavy compilation in his watched terminal, leaves his office, and walks into the kitchen.*

```
[ Office: Watched Terminal ]
Alex runs: `make build-all-images -j16` (Promoted to background Task #104)
              │
              ▼
[ Alex walks to Kitchen (Satellite Area: kitchen) ]
Alex speaks: "Hey Halbert, how is the build doing?"
              │
              ▼
[ Wyoming Satellite Ingress: 16kHz PCM from Kitchen Atom Echo ]
- Area detected: `kitchen`
- Active Screen nearby: `None`
- Open Thread Context: Contains active Task #104 (`make build-all-images`)
              │
              ▼
[ Modality Decision: Screenless Spoken Digest ]
Spoken Output: "The image build is at step fourteen of eighteen, compiling the
                frontend assets. It has been running for four minutes with zero errors."
```

```
+-----------------------------------------------------------------------------+
| SATELLITE AUDIO INTERACTION TRACE                                           |
|                                                                             |
| 🎙️ Satellite [Kitchen Echo] Ingress:                                        |
|    "Hey Halbert, how is the build doing?"                                   |
|                                                                             |
| 🧠 Halbert Context Resolution:                                               |
|    - Matched open thread task: `make build-all-images` (PID 48921)          │
|    - Elapsed: 4m 12s | Status: Running nominal                              │
|    - Synthesized Phonetic Text: "The image build is at step fourteen..."    │
|                                                                             │
| 🔊 Satellite Speaker Egress:                                                |
|    Transmits Piper TTS PCM chunk directly to Kitchen Wyoming satellite.     |
|                                                                             |
| 📝 SQLite Continuity Ledger:                                                |
|    Appends turn to active thread with `origin: 'satellite'`, `area: 'kitchen'`|
|    When Alex returns to his desk, the conversation timeline includes this   |
|    verbal exchange inline.                                                  |
+-----------------------------------------------------------------------------+
```

---

### Workflow C: Screenless Voice-Only Confirmation & Voice PIN Gate

*Scenario: Alex speaks to a Wyoming satellite in the living room asking for a sensitive system reboot when no screen is available.*

```
+-----------------------------------------------------------------------------+
| SCREENLESS PRIVILEGED ACTION INTERACTION FLOW                               |
+-----------------------------------------------------------------------------+
|                                                                             |
| Alex (Living Room): "Halbert, reboot the server host."                       |
|                                                                             |
| Halbert (Speaker):  "Rebooting `halbert-node-01` will disconnect 4 active   |
|                      containers and 2 Samba shares. To confirm, please say  |
|                      your four-digit voice PIN."                            |
|                                                                             |
| Alex (Living Room): "Seven, Four, Two, Nine."                               |
|                                                                             |
| [ Biometric & PIN Verification in <150ms: CAM++ Match 97% + PIN Valid ]     |
|                                                                             |
| Halbert (Speaker):  "PIN verified. Broadcasting shutdown warning and        |
|                      rebooting host now."                                   |
|                                                                             |
| System: Dispatches `systemctl reboot` with 30s grace window.                |
+-----------------------------------------------------------------------------+
```

---

### Workflow D: Acoustic Anomaly Multimodal Alert (Smoke / Hardware Alarm)

*Scenario: While Alex is typing code in the chat, the YAMNet AED engine detects a T3 smoke alarm pulse in the basement.*

```
+-----------------------------------------------------------------------------+
| ANOMALY DETECTED (Track B: Continuous Spectrogram Analysis)                 |
| - Class: `Smoke detector (T3 Pulse)` | Confidence: 96.2% | Level: 3 Critical|
+-----------------------------------------------------------------------------+
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
      [ AUDIO ESCALATION ]                  [ VISUAL ESCALATION ]
      - Interrupts active chat/TTS          - Injects Urgent Banner in GUI
      - Broadcasts loud vocal alert         - Displays live Camera Snapshot
      - Bypasses Quiet Hours                - Surfaces Emergency Action Pills
```

```
+-----------------------------------------------------------------------------+
| CRITICAL ANOMALY MULTIMODAL OVERLAY                                         |
|                                                                             |
| 🚨 [ CRITICAL LIFE SAFETY ALERT: SMOKE ALARM IN BASEMENT ]                  |
|                                                                             |
| 🔊 Halbert Vocal Broadcast:                                                 |
|    "Attention: Smoke alarm detected in the basement with ninety-six percent |
|     confidence. I am opening the basement camera feed now."                 |
|                                                                             |
| ┌───────────────────────────────────┐ ┌───────────────────────────────────┐ │
| │ CAMERA STREAM: Basement (Frigate) │ │ EMERGENCY TRIAGE ACTIONS          │ │
| │ [ Live RTSP Snapshot Preview ]    │ │                                   │ │
| │ [ ● REC 16:42:10 ]                │ │ [ 🔕 Mute False Alarm (2 min) ]   │ │
| │                                   │ │ [ 🚨 Trigger Whole-House Siren ]  │ │
| │ Thermal Sensor: 24°C (Normal)     │ │ [ 📞 Call Emergency Contact ]     │ │
| └───────────────────────────────────┘ └───────────────────────────────────┘ │
+-----------------------------------------------------------------------------+
```

---

## 5. Acoustic Echo Cancellation, Barge-In & Cross-Modality Interrupts

### 5.1 The Barge-In Timing Budget

To make conversational voice natural, the user must be able to interrupt Halbert at any point during audio playback:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BARGE-IN LATENCY BUDGET (<120ms)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ User Speech Onset ────────> [ 0 ms ]                                        │
│ Silero VAD Frame 1 (30ms) ─> [ 30 ms ] P(speech) = 0.72                     │
│ Silero VAD Frame 2 (30ms) ─> [ 60 ms ] P(speech) = 0.89 (Confirmed)        │
│ Atomic Cancellation Token ─> [ 65 ms ] Dispatched to Audio Buffer / Piper   │
│ DMA Ring Buffer Flush ────> [ 85 ms ] DAC Audio Output Muted                │
│ State Machine Reset ──────> [ 110 ms] State: SPEAKING ──> LISTENING         │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
                ┌─────────────────────────────────────────┐
                │        Agent Playing TTS Audio          │
                └────────────────────┬────────────────────┘
                                     │
                             [ User Speaks ]
                                     │
                                     ▼
                ┌─────────────────────────────────────────┐
                │ Silero VAD v5 detects speech (60ms)     │
                └────────────────────┬────────────────────┘
                                     │
                                     ▼
                ┌─────────────────────────────────────────┐
                │ Atomic StreamCancelledToken emitted     │
                └──────────┬──────────────────────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
┌─────────────────────────┐ ┌─────────────────────────┐
│ Rust cpal / Wyoming     │ │ Halbert State Machine   │
│ Buffer Flushed (<20ms)  │ │ Discards old turn &     │
│ Speaker instantly silent│ │ begins new turn intake  │
└─────────────────────────┘ └─────────────────────────┘
```

### 5.2 Cross-Modality Interruption Rules

1. **Typing While Speaking:** If Halbert is speaking via audio and the user begins typing in the chat prompt or presses any key in an active PTY terminal, audio speech immediately ducks by `-18\text{dB}` and halts completely after 500ms of active typing.
2. **Speaking While Typing:** If the user is typing and simultaneously speaks a voice command, the voice intake takes precedence for that turn; the composer retains the unsubmitted typed text as a draft.
3. **Esc Key Global Dismiss:** Pressing `Esc` in the desktop app or floating HUD halts all audio speech output and closes the voice companion window instantly.

---

## 6. Biometric Speaker Governance & Safety RoleGates

Voice ingress introduces unique authentication challenges compared to password-authenticated web sessions. Halbert enforces **Speaker RoleGates** to protect critical system operations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SPEAKER BIOMETRIC ROLEGATE TIERS                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Public / Safe Queries (Read-only vitals, weather, music info)       │
│ - Allowed for all speakers (Admin, Member, Guest, Unknown).                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Standard Home Automation (Lighting, thermostats, vacuum, media)     │
│ - Allowed for Enrolled Admin and Enrolled Members (CAM++ Cosine > 0.70).    │
│ - Unknown/Guest requires interactive verbal approval.                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Critical Sysadmin Tools (ZFS, SSH, Systemd, Reboots, Deadbolts)     │
│ - Allowed ONLY for Enrolled Admins (CAM++ Cosine > 0.82).                   │
│ - If confidence is between 0.60 and 0.81: Requires Voice PIN or Screen Gate.│
│ - If speaker is Non-Admin / Unknown: Hard execution block.                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

```sql
-- RoleGate Verification Log in SQLite
CREATE TABLE IF NOT EXISTS rolegate_audit_log (
    event_id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    speaker_id TEXT,
    speaker_role TEXT NOT NULL,
    confidence REAL NOT NULL,
    tool_name TEXT NOT NULL,
    risk_level TEXT NOT NULL, -- 'safe', 'moderate', 'high', 'critical'
    action_taken TEXT NOT NULL, -- 'executed', 'pinned_challenge', 'screen_gated', 'blocked'
    reason TEXT
);
```

---

## 7. Environmental & Temporal Context Adapters

### 7.1 Quiet Hours Modality Inversion (`22:00 – 07:00`)

To protect sleep and household tranquility, Halbert dynamically alters its egress rules during scheduled Quiet Hours:

```
+-----------------------------------------------------------------------------+
| QUIET HOURS MODALITY RULES (Active: 22:00 to 07:00)                         |
+-----------------------------------------------------------------------------+
| Event Category             | Standard Daylight Behavior | Quiet Hours Behavior           |
|----------------------------|----------------------------|--------------------------------|
| Reactive Voice Query       | Normal TTS Audio Response  | Whisper TTS / Reduced Volume dB|
| Proactive System Advisory  | Spoken Audio Chime + Alert | Silent Timeline Append (Mute)  |
| Daily Morning Report       | Spoken at 08:30 Wakeup     | Queued until 08:30 (Muted)     |
| Level 3 Life Safety Alarm  | Loud TTS Broadcast (85dB)  | Full Volume Alarm (Bypasses)   |
+-----------------------------------------------------------------------------+
```

### 7.2 Multi-Occupant Privacy Shield

When Halbert detects multiple distinct voices in the room via CAM++ speaker clustering (e.g. dinner guests or unknown visitors):
1. **Private Data Suppression:** TTS speech output automatically redacts sensitive data (passwords, auth tokens, external IP addresses, private file paths).
2. **Screen Handoff:** Halbert speaks: *"I have retrieved the connection details and displayed them securely on your screen."* The raw tokens render exclusively in the authenticated UI.

---

## 8. Data Contracts & Frontend Component Architecture

### 8.1 Dual-Stream SSE Data Contract (`StreamEvent`)

```typescript
// Shared TypeScript Interface: Server-Sent Events (SSE)
export interface DualStreamMessageEvent {
  event_type: 'dual_stream_chunk' | 'turn_complete'
  session_id: string
  thread_id: string
  
  // Acoustic Payload (For TTS & Screen Readers)
  acoustic_stream: {
    phonetic_text: string       // "ZFS pool data zero one is healthy."
    phonetic_complete: boolean
    target_audio_device?: string // "satellite_kitchen" | "local_speaker"
  }
  
  // Visual Payload (For Timeline & Context Region)
  visual_stream: {
    markdown_content: string     // "ZFS pool `data01` is healthy (0 errors)."
    why_chip?: {
      category: 'storage' | 'security' | 'config' | 'system'
      severity: 'calm' | 'notice' | 'important' | 'critical'
      label: string
      provenance_path?: string
    }
    summon_module?: {
      module_id: 'storage_health' | 'config_diff' | 'vitals' | 'docker'
      initial_props: Record<string, unknown>
    }
    staged_actions?: Array<{
      action_id: string
      label: string
      command?: string
      diff_id?: string
      requires_elevation: boolean
    }>
  }
}
```

### 8.2 Frontend Component Suite

```
halbert_core/dashboard/frontend/src/components/
├── agent/
│   ├── AcousticAura.tsx           # Global header audio state visualizer (Idle/Listen/Think/Speak)
│   ├── VoiceCompanionPill.tsx     # Non-activating floating HUD for macOS/Linux desktop
│   ├── ModalityHandoffBadge.tsx   # Visual indicator showing where response artifacts landed
│   ├── AcousticEventCard.tsx      # Chronicle card for acoustic anomalies (Alarms/Leaks/Music)
│   └── AgentChat.tsx              # Core two-column conversation timeline & input composer
└── settings/
    ├── AudioSettingsTab.tsx       # Local vs Cloud inference engine, ingress devices & quiet hours
    ├── SpeakerProfilesCard.tsx    # Enrolled voiceprints, role badges & test verification
    └── VoiceEnrollmentModal.tsx   # 3-step interactive voiceprint enrollment wizard
```

---

## 9. Degraded Modes & Fallback Guarantees

Halbert guarantees graceful degradation when audio or visual components fail:

```
┌──────────────────────────────────────────────┬──────────────────────────────────────────────┐
│ Failure Mode                                 │ Graceful Degradation Behavior                │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ **Microphone Permissions Denied (macOS)**    │ UI disables voice button with tooltip; falls │
│                                              │ back to 100% keyboard text chat.             │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ **Piper TTS Engine Failure / Missing Model**  │ Halbert logs warning; falls back to silent   │
│                                              │ visual streaming in Timeline without error.  │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ **Wyoming Satellite Disconnected**           │ Auto-reconnects with exponential backoff;    │
│                                              │ routes proactive alerts to desktop/push app. │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ **Screenless Operation (Headless Server)**   │ All high-density findings compress into      │
│                                              │ self-contained phonetic spoken summaries.    │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

---

## 10. Summary & Implementation Verification Vectors

By formalizing **Response Modality Handoff**:
1. **Audio and Visual streams are tightly coordinated:** Voice provides rapid conversational context; the screen provides dense, verifiable evidence.
2. **Safety is biometrically anchored:** Sensitive sysadmin operations are gated by CAM++ speaker verification, with automatic escalation to visual approval cards when confidence is marginal.
3. **Cross-surface continuity is preserved:** A conversation begun over a smart speaker in the kitchen appears seamlessly in the desktop timeline with full context intact.

### Automated Verification Checklist:
- [ ] `test_dual_stream_builder.py`: Verifies parallel synthesis of phonetic text and visual markdown.
- [ ] `test_modality_router.py`: Validates routing decisions across screen availability and content density tiers.
- [ ] `test_bargein_latency.py`: Measures atomic cancel token dispatch $<120\text{ms}$ upon synthetic VAD speech trigger.
- [ ] `test_rolegate_biometrics.py`: Validates non-admin execution blocks and voice PIN challenge flows.
