# Halbert User Journey Methodology & Workflow Specifications

**Version:** 1.0.0  
**Date:** 2026-08-23  
**Status:** Active Specification (Web Build Standard)  
**Lead:** Visual Design Lead & UX Architect  
**Reads with:** `documentation/design/DESIGN-SYSTEM-SPEC.md`, `documentation/design/COMPONENT-ARCHITECTURE.md`, `documentation/design/the-being.md`  

---

## 1. User-Journey Framework & Methodology

System administration software historically suffers from a severe design failure: **unfiltered telemetry dumps and alert fatigue**. Halbert solves this by anchoring every user journey in a strict human-centered methodology.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE USER-JOURNEY METHODOLOGY CYCLE                       │
│                                                                             │
│  [ TRIGGER ] ──> [ REASONING ] ──> [ FOUR WHYS ] ──> [ ACTION ] ──> [ MEMORY]│
│  System Event    Grounded RAG      User Context       Dry-Run Gate   Autobiography│
│  or User Query   & Telemetry       Verification       & Rollback     Preservation │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Core Personas

| Persona Archetype | Motivation & Daily Context | Halbert Value Proposition | Primary Pain Point Solved |
|---|---|---|---|
| **Alex: Senior Sysadmin / Homelabber** | Manages multiple bare-metal servers & containers. Values reproducibility, deterministic diffs, and privacy. | Speaks to the host in first person; gets instant AST-accurate config diffs and log triage without SSH jumping. | Context-switching across dozens of man pages, logs, and configuration drop-ins. |
| **Elena: Full-Stack Developer / Power User** | Uses macOS / Linux for heavy daily development. Needs high performance and zero mysterious slowdowns. | Proactive notifications about thermal throttling, orphan containers, and full volumes before builds fail. | Mysterious system degredation with cryptic error messages. |
| **Marcus: Infrastructure Engineer** | Oversees production staging hosts, security hardening, and compliance. | Verifiable provenance (SourcePrep doc citations, sha256 manifests, audit trails). | Unverifiable LLM hallucinations and reckless write scripts. |

### 1.2 The Law of Four Whys in Workflow Decision-Making

Every interaction pattern must satisfy all four criteria before rendering in the UI:

```
+-----------------------------------------------------------------------------+
│ 1. WHY NOW?   │ Severity × Proactivity Dial × Quiet Hours State             │
│               │ Is the notification urgent enough to break the user's flow? │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ 2. WHY CARE?  │ Real-world Consequence & Failure Mode                       │
│               │ What breaks if no action is taken within 24 hours?          │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ 3. WHY SO?    │ Config Rationale & Past Intent                              │
│               │ Why was the system configured this way in the past?         │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ 4. WHY TRUST? │ Verifiable Grounding & Provenance                           │
│               │ File paths, journald lines, AST diffs, and SHA256 hashes.   │
+-----------------------------------------------------------------------------+
```

---

## 2. End-to-End User Journey Workflows

---

### Journey 1: First Boot & Sensor Calibration (Identity Discovery)

```
[ User Action ]            [ UI State ]                 [ System State ]
     │                           │                             │
Install & Launch ────────> Welcome Screen ─────────────> Run Initial Discovery
     │                     (Daylight Canvas)             (hwmon, distro, mounts)
     │                           │                             │
Select Model ────────────> Unified Model Picker ───────> Verify Ollama / Local LLM
     │                     (Local Ollama Auto-detect)          │
     │                           │                             │
Click "Meet Host" ───────> First Greeting Stream ──────> Generate Machine Identity
     │                     "I'm ubuntu-server-01..."     Autobiography Seed Created
     ▼                           ▼                             ▼
```

**Step-by-Step Experience:**
1. **First Launch:** The user launches the Tauri app. The window opens with warm paper canvas (`#F7F5F0`) and clear mid-century typography.
2. **Telemetry Ingestion:** Halbert quietly inspects local hardware sensors (`/sys/class/hwmon`), `/etc/os-release`, and mounted drives in under `400ms`.
3. **Model Selection:** The `UnifiedModelPicker` identifies active local Ollama models (e.g. `llama3:8b`, `qwen2.5-coder:7b`) with zero complex API keys required.
4. **The Awakening:** Halbert speaks its first sentence:  
   > *"Hello. I am `ubuntu-server-01`. I run Ubuntu 24.04 on an AMD Ryzen 9 with 64GB RAM. I've mapped 3 storage volumes and calibrated my sensors. How can I help you today?"*
5. **Outcome:** The user feels immediate trust and understanding—Halbert is not an alien bot; it is their computer.

---

### Journey 2: Grounded Reactive Query ("How are you doing?")

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  USER INPUT: "How are you doing?"                                           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: SENSORY INSPECTION (Tool Execution Card)                           │
│  ⚙ read_sensors() ──> CPU 45°C · Load 0.15 · Storage NVMe Healthy (700ms)    │
│  ⚙ query_memory("recent incidents") ──> 3 read errors on /dev/sda1 (600ms)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: EMBODIED RESPONSE GENERATION                                       │
│  Halbert: "I'm running cool at 45°C with light load. One thing though:      │
│  I logged three read errors on /dev/sda1 this morning. I'd keep an eye on   │
│  that drive."                                                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: SUMMON EVIDENCE & PROMPT ACTION                                    │
│  • Right Context Pane opens with [ StorageHealthModule ]                    │
│  • Inline Action Pills: [ Run SMART Benchmark ] [ Snooze 24h ] [ View Logs ]│
└─────────────────────────────────────────────────────────────────────────────┘
```

**UX Mechanics & Feedback Loops:**
- **Zero Hallucination:** Every adjective ("cool", "light", "worried") is strictly tied to a numeric threshold in telemetry.
- **Dynamic Module Summoning:** As Halbert speaks about `/dev/sda1`, the right-hand context pane smoothly slides in with the `StorageSensorsModule`, displaying raw SMART attributes and drive temperature trends.
- **Actionable Off-Ramps:** The user can immediately click `[ Run SMART Benchmark ]` or type a follow-up command.

---

### Journey 3: Proactive Triage & Approval Gate (Silent Conflict)

```
[ Background Daemon ]     [ System Tray / HUD ]        [ Engaged Workspace ]
        │                           │                           │
Detects Drop-in Conflict ───> Ambient Tray Glow ────────> User clicks Notification
(sshd_config.d precedence)   (Orange status pip)                │
        │                           │                           ▼
        │                           │                  Conversational Alert
        │                           │                  + WhyChip: [ ⚠ Config ]
        │                           │                           │
        │                           │                           ▼
        │                           │                  Right Pane Summons:
        │                           │                  [ ConfigDiffInspector ]
        │                           │                           │
        │                           │                           ▼
        │                           │                  [ ApprovalGate ]
        │                           │                  - Atomic Diff
        │                           │                  - Blast Radius (Low)
        │                           │                  - Rollback Guarantee
        │                           │                           │
        │                           │                           ▼
        │                           │                  User clicks [Approve]
        │                           │                  Polkit Elevation Prompt
        │                           │                           │
        │                           │                           ▼
        │                           │                  Write Executed &
        │                           │                  Recorded in Autobiography
```

**Step-by-Step Experience:**
1. **Autonomous Detection:** Halbert's background triage daemon notices two drop-in files (`10-default.conf` and `50-custom.conf`) conflicting on `PasswordAuthentication`.
2. **Attentional Filtering:** The issue is non-fatal; Halbert queues it for the morning review or displays a gentle amber indicator in the menu bar.
3. **Conversational Framing:** When opened, Halbert explains:  
   > *"I noticed a conflict in my SSH configuration: `50-custom.conf` disables password authentication, but `90-cloud-init.conf` quietly re-enabled it. This exposes us to brute-force attempts on port 22."*
4. **Approval Gate Inspection:** The right pane renders the `ApprovalGate` showing:
   - Exact line diff (`- PasswordAuthentication yes` / `+ PasswordAuthentication no`).
   - Blast Radius: *Affects incoming SSH sessions only; active sessions remain connected.*
   - Rollback Snapshot: `#SNAP-20260823-01`.
5. **Execution:** User clicks `[ Approve & Apply ]`, authenticates with Polkit, and Halbert reloads `sshd.service` safely.

---

### Journey 4: Configuration Archeology ("Why is SSH on port 2222?")

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  USER INPUT: "Why is SSH running on port 2222?"                             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  RETRIEVAL: query_memory("ssh port change rationale")                       │
│  Found: Event recorded 2026-07-14 (User requested change to mitigate scans) │
│  SourcePrep Reference: /etc/ssh/sshd_config.d/20-port.conf                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  EMBODIED ANSWER:                                                           │
│  "I moved SSH to port 2222 on July 14th. You instructed me to do so after  │
│  the auth log recorded over 4,000 automated password scan attempts on       │
│  default port 22. It has been quiet since."                                 │
│                                                                             │
│  [ Summoned Module: ConfigDiff + Auth Log Scan Graph from July 14 ]         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Benefit:** Halbert transforms ephemeral system changes into **auditable institutional memory**. The user never has to wonder "who touched this config file or why."

---

### Journey 5: Marketing Conversion & Brand Discovery Funnel

```
[ Visitor Lands ] ──> [ Hero Conversation ] ──> [ Scrollytelling ] ──> [ The Soul ] ──> [ Waitlist ]
   halbert.ai          Animated Terminal        3 Steps of Vitals       "The Colleague    Early Access
   Warm Paper          Plays "How are you?"     & Config Diff           who is your       Capture Form
   Canvas              Typewriter Audio         Interactive Windows     computer"
```

**Step-by-Step Experience:**
1. **Hero Entry:** Visitor lands on `halbert.ai`. The warm paper canvas and Vermilion typography establish instant aesthetic separation from dark crypto/AI tools.
2. **Immediate Proof (Hero):** The visitor watches the live `TerminalFrame` interactively type out the "How are you doing?" dialogue. No vague marketing fluff—just working product demonstration.
3. **Scrollytelling Exploration:** Scrolling down triggers sticky desktop window mockups:
   - Step 1: *It knows itself* (Live sensor vitals).
   - Step 2: *It remembers* (AST configuration diff with rationale tags).
   - Step 3: *It speaks* (Conversational command spine).
4. **The Soul Emotional Climax:** Centered statement: *"The most helpful colleague you have, who happens to be your computer."*
5. **Conversion Action:** Minimalist waitlist email capture with instant confirmation.
