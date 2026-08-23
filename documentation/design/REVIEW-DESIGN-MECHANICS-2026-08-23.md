# Review: Design Mechanics, User Flows & Interaction Lifecycles

**Status:** Completed Review & Comprehensive Design Specification  
**Reviewer:** Senior Product Designer & UX Architect  
**Date:** 2026-08-23  
**Target Environment:** Tauri Desktop App (React + Radix UI + Tailwind) / Linux (Ubuntu) & macOS  
**Reads with:** `.handoff/HANDOFF-REVIEW-2026-08-23.md`, `documentation/design/the-being.md`, `documentation/design/explorations.md`, `.handoff/ROADMAP-2026-08-23.md`

---

## Executive Summary: Bridging Architecture to Lived Experience

Halbert's core paradigm shift is moving from a *monitoring dashboard with a chatbot attached* to an **embodied host entity** ("a being that *is* the computer"). 

Architecturally, Halbert has solid foundations: the Haloysius cognitive tick, SourcePrep awareness substrate, the config physiology brain, and the SQLite findings/approval engine. However, a technical architecture is not an experience. Without explicit, nuanced user flows, even the most sophisticated cognitive core can feel unpredictable, chatty, or uncanny.

This design specification bridges this gap by defining:
1. **The Core Interaction Principles:** Grounding every pixel in Halbert's Four Whys.
2. **12 Comprehensive User Workflows:** End-to-end screen states, ASCII wireframes, micro-interactions, branching logic, and underlying architectural seams covering the entire lifecycle from first boot to daily rituals.
3. **Signature Micro-Interactions:** The `WhyChip`, proactive interrupt cards, diff and blast-radius visualizers, the module invocation container lifecycle, and the ambient system tray.
4. **Resilience & Degraded States:** Honest self-disclosure when LLM, RAG, or OS subsystems fail.
5. **Living Rhythm & Attention Budgets:** Calibration of interruptions across a 7-day operating cycle.
6. **Keyboard & Accessibility Model:** Full keyboard navigability and screen reader semantics for power users.

---

## 1. Design Principles & The Interaction Philosophy

```
+-----------------------------------------------------------------------------+
|                               THE DESIGN LAW                                |
|                  "Nothing appears without its four whys."                   |
+----------------------+------------------------------------------------------+
| 1. Why Now           | Severity x Category x Proactivity Dial x Quiet Hours  |
| 2. Why Care          | Consequence & failure mode if ignored                |
| 3. Why So            | System rationale, config history, underlying intent  |
| 4. Why Trust         | Verifiable provenance: file paths, logs, diffs, hash |
+----------------------+------------------------------------------------------+
```

### 1.1 Core Tenets

1. **Embodied, Not Personified:** Halbert does not pretend to have human emotions; it has *computational embodiment*. It speaks as the machine caring for itself and collaborating with its administrator.
2. **Triage Over Telemetry:** Raw metrics and alerts create fatigue. Halbert never displays a naked metric without stating its consequence, trend context, or operational relevance.
3. **Zero Unjustified Interruptions:** An interruption must justify its cost to the user's attention before the window opens.
4. **Reversible Agency:** Every write action is bounded by an atomic dry-run, an explicit blast-radius estimate, and an immediate single-click rollback guarantee.
5. **Continuous Conversation Spine:** Interaction is an ongoing relationship over time, segmented into days and rituals, rather than isolated, disposable chat sessions.

---

## 2. Global Layout & Container Architecture

Halbert operates in three distinct display modes:

```
+-----------------------------------------------------------------------------+
| MODE 1: ENGAGED (Default Workspace — Two-Column Conversation + Context)     |
|                                                                             |
| +------------------------------------+------------------------------------+ |
| | CONVERSATION SPINE (Left 45-50%)   | CONTEXT REGION (Right 50-55%)      | |
| |                                    |                                    | |
| | [Timeline / Daily Divider]         | [Active Summoned Module]           | |
| |                                    | - Live Vitals Gauge Grid           | |
| | Halbert:                           | - Interactive Config Diff & Edges  | |
| | "I detected conflicting SSH        | - Storage Health & SMART Status    | |
| | drop-in configs in sshd_config.d." | - Evidence Drawer (Logs/Journald)  | |
| | [WhyChip: Important | Config]      |                                    | |
| |                                    | [Approve Action] [Dismiss] [Snooze]| |
| | User:                              |                                    | |
| | "Which configuration wins?"        | [Pin Module] [Minimize] [Close]    | |
| |                                    |                                    | |
| | Halbert:                           |                                    | |
| | "50-cloud-init.conf overrides..."  |                                    | |
| +------------------------------------+------------------------------------+ |
| | [Input Prompt: Ask or command...]                [Cmd+K Modules] [Mic]  | |
| +-------------------------------------------------------------------------+ |
+-----------------------------------------------------------------------------+
```

```
+-----------------------------------------------------------------------------+
| MODE 2: BROWSING (Under the Hood — Full Grid View)                          |
|                                                                             |
| [Top Nav: System Status Bar | Search | Being Status | [Engage Mode Toggle]] |
| +-------------------+-------------------+-------------------+-------------+ |
| | Vitals & Load     | Storage & Pools   | System Services   | Security    | |
| | [Live Graph]      | [Mount Points]    | [Active Daemons]  | [Firewall]  | |
| +-------------------+-------------------+-------------------+-------------+ |
| | Network & DNS     | Containers/Docker | Config Registry   | Approvals   | |
| +-------------------+-------------------+-------------------+-------------+ |
+-----------------------------------------------------------------------------+
```

```
+-----------------------------------------------------------------------------+
| MODE 3: AMBIENT (At Rest — System Tray & Minimal HUD)                       |
|                                                                             |
| [macOS Menu Bar / Ubuntu AppIndicator]  --> [Halbert Icon: Calm / Dot Badge]|
|   Left Click: Quick Peek HUD Dropdown / Slide-out Spine                     |
|   Right Click: Context Menu (Status, Mute 1h, Proactivity Dial, Settings)   |
+-----------------------------------------------------------------------------+
```

---

## 3. Comprehensive User Workflows & Lifecycles

### Workflow Index
- **Flow 01:** First-Run Awakening & Hardware Discovery (Onboarding / Birth)
- **Flow 02:** Purpose Alignment & Profile Ingestion
- **Flow 03:** Ambient Background Sweep & Worry State Generation
- **Flow 04:** Proactive Config Conflict Interrupt & Interactive Triage
- **Flow 05:** Config Change Proposal, Blast-Radius Inspection & Rollback
- **Flow 06:** Reactive State Inquiry ("How are you?") with Provenance Drilldown
- **Flow 07:** Root-Cause Troubleshooting ("Why did Docker fail?")
- **Flow 08:** Manual Module Summoning via Palette (Cmd+K)
- **Flow 09:** The Morning Report Ritual & Batch Triage
- **Flow 10:** Config Rationale Capture (WhyBrain Revived via SourcePrep Concepts)
- **Flow 11:** Degraded Sensor & Subsystem Recovery (Local LLM / SourcePrep down)
- **Flow 12:** Cross-Platform Transition (macOS Dev Host vs Ubuntu Lab Host)

---

### Flow 01: First-Run Awakening & Hardware Discovery (Birth)

```
[User Launches App First Time]
             |
             v
[Tauri Shell Inits -> FastAPI Boot]
             |
             v
[Silent Baseline Discovery Scan (CPU, Memory, Disks, OS, Network)]
             |
             v
[ENGAGED View Opens -> Halbert Self-Introduction Message Appears]
             |
             v
[Context Region Renders Baseline System Inventory Module]
```

#### Step-by-Step Micro-Interactions:
1. **Initial Screen:** The window opens in `ENGAGED` mode. No blocking modal setup wizards. The conversation spine displays a typewriter-rendered message in the configured default voice (First Person):
   > *"Hello. I am initializing on `halbert-node-01` (Ubuntu 24.04 LTS, Linux 6.8.0-31-generic). I have mapped our hardware: 16 cores (AMD Ryzen 7), 64 GB ECC RAM, and 3 storage volumes. I am beginning a baseline pass over `/etc` and active systemd units."*
2. **Context Region:** Automatically populates with the **Host Baseline Module**, highlighting live discovered components with subtle pulse indicators as scanning completes.
3. **Affordances:**
   - Conversation spine displays prompt suggestions: `[Looks good]`, `[Define machine purpose]`, `[Configure alerts]`.
   - No forced blocking buttons; the user can immediately type or click a chip.

---

### Flow 02: Purpose Alignment & Profile Calibration

```
User selects or types: "This machine is a dedicated ZFS NAS and Docker host."
                               |
                               v
Intake Pipeline -> Signal Analysis (intent: configure_purpose, domain: storage/containers)
                               |
                               v
State Machine Tick -> Updates being.yml (purpose: "ZFS NAS and Docker host")
                               |
                               v
Halbert Response -> Calibrates Monitor Priorities & Confirms
```

#### Micro-Interactions:
1. **User Input:** User specifies machine identity in free text or selects suggested tags.
2. **Entity Response:**
   > *"Understood. I will prioritize ZFS pool integrity, scrub schedules, disk temperature thresholds, and container restart policies over general desktop services. I will dial down desktop audio/display monitoring."*
3. **Visual Confirmation:** A subtle tag chip `[Purpose: ZFS NAS & Docker Host]` appears under the Being Status header in the navigation bar.
4. **Behind the Seams:** Saved to `~/.config/halbert/being.yml` and indexed as a primary anchor in SourcePrep's `identity.md`.

---

### Flow 03: Ambient Background Sweep & Worry State Generation

```
[Background Timer (Hourly) OR inotify Config Watcher Trigger]
                           |
                           v
              [Config Detectors Run (E1-E3)]
                           |
              [Detector Hits: e.g. fstab Phantom]
                           |
                           v
        [Build Finding Object (Four Whys Grounded)]
                           |
                           v
  [Proactivity Gate: Severity (Critical) >= Dial (Balanced)?]
        /                                       \
      YES                                        NO
      /                                           \
[Push via SSE /api/being/events]      [Persist in SQLite findings store]
[Update Tray to Needs-Attention]       [Queue for Morning Report]
```

#### Micro-Interactions:
1. **Detector Discovery:** Background worker notices `/etc/fstab` contains a UUID entry for a disk unmounted 14 days ago that fails `blkid` check.
2. **Finding Synthesis:** Consequence evaluated: *"System boot may stall into emergency maintenance mode on next kernel update or reboot."*
3. **Internal State:** Haloysius ledger registers `worries_about(fstab_phantom_uuid_9a4f)`.

---

### Flow 04: Proactive Config Conflict Interrupt & Interactive Triage

```
+-----------------------------------------------------------------------------+
| CONVERSATION SPINE                   | CONTEXT REGION: Finding f_01J5K...   |
|                                      |                                      |
| Halbert:                             | [SEVERITY: IMPORTANT] [CATEGORY: SSH]|
| "I noticed a configuration conflict  |                                      |
| in sshd_config.d that affects your   | WHAT:                                |
| login security."                     | PasswordAuthentication set to 'yes'  |
|                                      | in 60-cloudimg.conf but 'no' in      |
| [WhyChip: Important | SSH Conflict]  | 99-local-hardening.conf.             |
|                                      |                                      |
| "According to sshd drop-in           | CONSEQUENCE (Why Care):              |
| precedence, 99-local-hardening wins, | Password login is currently disabled |
| but 60-cloudimg creates false audit  | but may reactivate if files are      |
| alerts and drift."                   | renamed or ordered differently.      |
|                                      |                                      |
| What would you like to do?           | PROVENANCE (Why Trust):              |
| [View Diff & Proposal]               | - /etc/ssh/sshd_config.d/60-cloudimg |
| [Snooze 7 Days]  [Mark Intentional]  | - /etc/ssh/sshd_config.d/99-local    |
+--------------------------------------+--------------------------------------+
```

#### Step-by-Step Micro-Interactions:
1. **Trigger:** The being pushes a notification event. If the app is minimized, the tray pulses amber; clicking it slides open the `ENGAGED` window.
2. **Finding Card in Context Region:**
   - Displays **What**, **Why Care (Consequence)**, and **Why Trust (Provenance)**.
   - Provides four explicit primary actions:
     - `[Generate Proposed Fix]`: Initiates Flow 05.
     - `[Snooze...]`: Opens dropdown (`1 Day`, `7 Days`, `Next Reboot`).
     - `[Mark as Intentional (Dismiss)]`: Prompts user for a 1-sentence reason ("Why is this kept?"). Persists into SourcePrep concepts as permanent rationale.
     - `[Why?]`: Expands deep reasoning chain and precedence graph.

---

### Flow 05: Config Change Proposal, Blast-Radius Inspection & Rollback

```
[User clicks "View Diff & Proposal"]
                 |
                 v
[write_config Dry-Run -> Generates Unified Diff + Dependency Blast-Radius]
                 |
                 v
[Context Region Updates to Diff & Blast-Radius Inspector]
```

```
+-----------------------------------------------------------------------------+
| CONTEXT REGION: Proposal p_01J5K89                                          |
|                                                                             |
| TARGET: /etc/ssh/sshd_config.d/60-cloudimg.conf                             |
| ACTION: Comment out redundant 'PasswordAuthentication yes'                  |
|                                                                             |
| --- /etc/ssh/sshd_config.d/60-cloudimg.conf                                 |
| +++ /etc/ssh/sshd_config.d/60-cloudimg.conf (proposed)                      |
| @@ -4,7 +4,7 @@                                                            |
|  PubkeyAuthentication yes                                                   |
| -PasswordAuthentication yes                                                 |
| +# PasswordAuthentication yes (disabled by Halbert: matches 99-local)       |
|                                                                             |
| BLAST-RADIUS (Direct Dependents):                                           |
| [!] ssh.service (Daemon reload required - active connections unaffected)    |
| [i] fail2ban.service (Monitors /var/log/auth.log - no rule change required) |
|                                                                             |
| ROLLBACK PLAN:                                                              |
| Instant snapshot backup created at /var/backups/halbert/60-cloudimg.bak.01  |
|                                                                             |
| [APPROVE & APPLY NOW]          [EDIT MANUALLY]          [REJECT PROPOSAL]   |
+-----------------------------------------------------------------------------+
```

#### Execution & Rollback Execution Steps:
1. **User clicks `[APPROVE & APPLY NOW]`:**
   - System prompts for privilege elevation (polkit / sudo auth token via secure backend helper).
   - `write_config.py` creates backup snapshot `60-cloudimg.bak.01`.
   - File is atomically written.
   - Post-apply hook executes syntax verification (`sshd -t`).
   - If syntax check **passes**: Service reloaded (`systemctl reload ssh`).
   - Conversation spine prints:
     > *"I applied the change and reloaded `ssh.service`. Verified syntax clean. 0 existing sessions dropped."*
   - Context card transforms into a persistent receipt with a prominent `[UNDO / ROLLBACK]` button.
2. **If syntax check FAILS:**
   - Atomic rollback is automatically executed within 250ms.
   - Conversation spine alerts:
     > *"Verification failed during `sshd -t` test. I immediately restored the original config. No services were disrupted."*

---

### Flow 06: Reactive State Inquiry ("How are you?") with Provenance

```
User types: "How are you doing today?"
                     |
                     v
Intake Router: intent=system_inquiry, complexity=2 (Guide Model)
                     |
                     v
Retrieval Backend: Fetches System Biography (Uptime, Thermal, Disk SMART, Recent Changes)
                     |
                     v
Cognition Tick: Formulates Response in configured Voice (First Person)
                     |
                     v
Stream SSE Event: text response + module_invoke("vitals")
```

```
+-----------------------------------------------------------------------------+
| CONVERSATION SPINE                   | CONTEXT REGION: Live Vitals Module   |
|                                      |                                      |
| Halbert:                             | [CPU USAGE]      [MEMORY (64 GB)]    |
| "I'm running smoothly overall.       | 12% Avg (45C)    24.2 GB used (38%)  |
| Uptime is 18 days, 4 hours.          | [||||........]   [||||||||......]    |
|                                      |                                      |
| I have two minor items on my mind:   | [STORAGE POOLS]                      |
| 1. NVMe drive `/dev/nvme0n1` peaked  | rpool (ZFS): 42% (Healthy, Scrub OK) |
|    at 62C during the 03:00 backup    | data01:      78% (Healthy)           |
|    [WhyChip: Logs | Temp Event].     |                                      |
| 2. Memory pressure is low (38%), but | [ACTIVE ALERTS (1)]                  |
|    Docker container `plex` consumed  | - Thermal spike on nvme0n1 at 03:14  |
|    6 GB cache [WhyChip: Metrics].    |                                      |
|                                      | [Pin to Sidebar] [Open Full Vitals]  |
| All systemd services are nominal."   |                                      |
+-----------------------------------------------------------------------------+
```

#### Micro-Interaction: Clicking the `[WhyChip: Logs | Temp Event]`:
1. The Context Region dynamically slides down a drawer showing the raw excerpt:
   ```
   SOURCE: journald cursor s=a8b3... [2026-08-23 03:14:02 UTC]
   kernel: nvme nvme0: sensor 1 temperature 62 C exceeds warning threshold (60 C)
   kernel: smartd[1042]: Device: /dev/nvme0n1, Temperature 62 Celsius
   ```
2. One-click action `[Copy Citation]` or `[Query Related Events]`.

---

### Flow 07: Root-Cause Troubleshooting ("Why did Docker fail?")

```
User types: "Why did docker fail last night?"
                     |
                     v
Intake Pipeline: intent=troubleshooting, complexity=4 (Specialist Model Tier)
                     |
                     v
Context Assembler: Queries SourcePrep tree (logs/daemon.log, systemd units, memory cgroup)
                     |
                     v
Haloysius Cognitive Tick: Synthesizes Fault Tree Analysis
```

```
+-----------------------------------------------------------------------------+
| CONVERSATION SPINE                   | CONTEXT REGION: Incident Evidence    |
|                                      |                                      |
| Halbert:                             | TIMELINE: Incident at 02:41:18 UTC   |
| "Docker daemon was terminated by     |                                      |
| the Linux OOM-killer at 02:41 UTC    | 02:40:00 - Memory usage reaches 96%  |
| due to total host memory exhaustion. | 02:41:12 - ZFS ARC cache at 32 GB    |
|                                      | 02:41:18 - kernel: Out of memory:    |
| Here is the failure sequence:        |            Kill process 14201        |
| 1. A scheduled backup job spawned a  |            (dockerd) score 842       |
|    heavy tar compression process.    | 02:41:20 - systemd: docker.service:  |
| 2. ZFS ARC cache did not release     |            Main process exited       |
|    RAM quickly enough.               |                                      |
| 3. `dockerd` had the highest OOM bad | ROOT CAUSE:                          |
|    score and was killed.             | ZFS ARC limit unset; competed with   |
|                                      | backup compression process.          |
| I propose setting `zfs_arc_max` to   |                                      |
| 24GB in `/etc/modprobe.d/zfs.conf`." | PROPOSED REMEDIATION:                |
|                                      | [Review & Apply zfs_arc_max Fix]     |
| [View Incident Timeline]             |                                      |
+-----------------------------------------------------------------------------+
```

---

### Flow 08: Manual Module Summoning via Palette (Cmd+K)

```
[User presses Cmd+K (or clicks 'Modules' in input bar)]
                         |
                         v
[Radix UI Modal Overlay Opens centered on screen]
                         |
                         v
[Fuzzy-search filter: type "sto" -> Storage, ZFS Pools, SMART Disks]
                         |
                         v
[Press Enter on 'Storage' -> Context Region renders Storage Module]
```

```
+-----------------------------------------------------------------------------+
|  SUMMON MODULE                                                [ESC to Close] |
|  > storage                                                                  |
|                                                                             |
|  MODULES                                                                    |
|  > [Storage & Disks]        Inspect mount points, ZFS pools, SMART health   |
|    [Services & Systemd]     Inspect, restart, and analyze unit states       |
|    [Config Tree]            Browse /etc snapshots and precedence rules      |
|    [Network & Firewall]     Active interfaces, sockets, and ufw rules       |
|    [Pending Approvals]      Review queued system changes and dry-runs       |
+-----------------------------------------------------------------------------+
```

---

### Flow 09: The Morning Report Ritual & Batch Triage

```
[User wakes workstation / launches app at 08:35 AM (Configured 08:30)]
                               |
                               v
[ENGAGED View initializes with Dedicated Morning Digest Container]
```

```
+-----------------------------------------------------------------------------+
| CONVERSATION SPINE                   | CONTEXT REGION: Daily Triage Queue   |
|                                      |                                      |
| Halbert:                             | MORNING DIGEST - 2026-08-23          |
| "Good morning. Here is your overnight|                                      |
| summary for `halbert-node-01`:       | [1] CONFIG DRIFT (Important)         |
|                                      |     Unmanaged edit in /etc/hosts     |
| - 1 Important config drift detected  |     [Inspect Diff] [Acknowledge]     |
| - 2 Minor package updates available  |                                      |
| - All overnight backups completed in | [2] STORAGE INTEGRITY (Calm)         |
|   42 minutes with zero errors.       |     ZFS pool 'rpool' scrub complete  |
| - System load remained under 15%.    |     0 checksum errors, 0 repaired    |
|                                      |                                      |
| Would you like to review the hosts   | [3] PENDING PACKAGES (Notice)        |
| drift item now?"                     |     openssl (security), curl         |
|                                      |     [Queue for Upgrade]              |
| [Review Drift Item] [Dismiss All]    |                                      |
+---------------------------------------------+-------------------------------+
```

#### Interaction Logic:
- The Morning Report is not a standard chat message; it is a **structured digest container**.
- Clicking any item in the digest expands its dedicated interactive sub-module in the Context Region without leaving the digest stream.
- Actions can be taken individually or via `[Dismiss All Calm Items]`.

---

### Flow 10: Config Rationale Capture (WhyBrain Revived via SourcePrep Concepts)

```
[User manually edits /etc/sysctl.d/99-custom.conf]
                         |
                         v
[config/watcher.py detects inotify WRITE_CLOSE event]
                         |
                         v
[Halbert prompts quietly in Timeline]:
"I noticed you updated `vm.swappiness` to 10 in 99-custom.conf.
 Would you like to record why this was set for future reference?"
                         |
                         v
[User types: "Minimize swap usage for database stability on NVMe"]
                         |
                         v
[Persisted as SourcePrep Concept anchored to /etc/sysctl.d/99-custom.conf:vm.swappiness]
```

#### Benefits in Action:
- 6 months later, when the user or an automated detector asks *"Why is swappiness set to 10?"*, Halbert cites:
  > *"Configured by you on 2026-08-23: 'Minimize swap usage for database stability on NVMe'."*
- If the file is modified externally or deleted, SourcePrep automatically marks the concept as **stale** and prompts for review.

---

### Flow 11: Degraded Sensor & Subsystem Recovery

```
[Subsystem Check: Ollama / Local Model Backend Connection Refused]
                                 |
                                 v
[App seamlessly enters Autonomous Safe Mode / UI Notification Banner]
```

```
+-----------------------------------------------------------------------------+
| [!] LOCAL INFERENCE ENGINE OFFLINE | Falling back to rule-based triage      |
+------------------------------------+----------------------------------------+
| CONVERSATION SPINE                 | CONTEXT REGION: System Diagnostics     |
|                                    |                                        |
| Halbert:                           | SERVICE STATUS:                        |
| "My cognitive inference backend is | [X] ollama.service: Inactive (dead)    |
| unreachable on localhost:11434.    |                                        |
|                                    | DIAGNOSTIC CHECK:                      |
| While my conversational voice is   | Port 11434 connection refused.         |
| degraded, my system watchers and   | Service crashed 3 minutes ago.         |
| rule-based detectors are still     | Exit code 137 (Out of Memory).         |
| active.                            |                                        |
|                                    | ACTIONS:                               |
| I can attempt to restart the       | [RESTART INFERENCE SERVICE]            |
| service for you."                  | [SWITCH TO CLOUD BACKEND (Settings)]   |
+------------------------------------+----------------------------------------+
```

---

### Flow 12: Cross-Platform Transition (macOS Dev Host vs Ubuntu Lab Host)

```
[Halbert starts on macOS (Darwin arm64)]
                   |
                   v
[Platform Detection Adapter inits]
                   |
                   v
[Gracefully disables Linux-only scanners: journald, systemd, bcachefs, ufw]
                   |
                   v
[Enables macOS adapters: launchd, unified log stream, diskutil/APFS, pfctl]
                   |
                   v
[First Conversation / Self-Check reflects host realities honestly]
```

#### Conversational Expression:
> *"I am running on macOS (Darwin 24.1.0, Apple M3 Max). I do not have access to `journald` or `systemd` on this system. I am monitoring via `launchd` and macOS unified log streams. GPU monitoring will utilize Apple Silicon unified memory metrics instead of NVML."*

---

## 4. Micro-Interaction Design Specifications

### 4.1 The `WhyChip` & Provenance Drawer

The `WhyChip` is the primary visual anchor of Halbert's interaction design. It appears alongside statements, findings, and metrics.

```
Visual Shape:
+---------------------------------------------------+
| [i] Why: Important | Precedence Conflict (sshd)  |
+---------------------------------------------------+
```

#### Hover & Click Behaviors:
- **Default State:** A pill badge with subtle border and category icon (`[i]`, `[!]`, `[x]`).
- **Hover:** Tooltip reveals a 2-line summary:
  - *Consequence:* What happens if ignored.
  - *Evidence:* Grounding file path or log timestamp.
- **Click:** Transitions the Context Region (or opens an overlay slide-out drawer) displaying full provenance:
  - Exact file path with line numbers and diff viewer.
  - Journald cursor hash or raw log excerpt.
  - Relevant concept rationale.

---

### 4.2 Proactive Interrupt Presentation Across Application States

| App State | Visual Presentation | Dismiss / Act Behavior |
|---|---|---|
| **App Open (ENGAGED)** | New message card appears in Conversation Spine with a subtle visual glow; Context Region previews the finding card. | User can continue current typing or click `[Triage Now]`. |
| **App Open (BROWSING Grid)** | A top-level alert banner slides down: `[Critical Finding: fstab phantom] [Review in Conversation]`. | Clicking banner flips view to `ENGAGED` with finding loaded. |
| **App Minimized to Tray** | Tray icon changes from Calm (Circle) to Urgent (Amber dot/badge). System desktop notification posted. | Clicking notification brings app forward directly to finding. |
| **App Closed (Daemon Active)** | OS notification dispatched via Tauri notification API (title, consequence summary, no sensitive passwords). | Launching app opens directly into the pending triage queue. |

---

### 4.3 The Proactivity Dial & Category Override Matrix

Configured in `~/.config/halbert/being.yml`:

```
+-----------------------------------------------------------------------------+
| PROACTIVITY DIAL SETTING                                                    |
|                                                                             |
|  ( ) Off          Purely reactive. Only responds when queried.              |
|  ( ) Quiet        Only Critical findings (hardware failure, security breach)|
|  (*) Balanced     Important/Critical findings + Morning Report (Default)    |
|  ( ) Assertive    Proactively mentions optimizations, drift, and patterns.  |
|                                                                             |
| CATEGORY OVERRIDES                                                          |
| Security:  [ Assertive v ]   Storage:   [ Balanced  v ]                     |
| Config:    [ Balanced  v ]   Services:  [ Quiet     v ]                     |
|                                                                             |
| QUIET HOURS                                                                 |
| [X] Suppress non-critical interrupts between: [ 23:00 ] and [ 08:00 ]       |
+-----------------------------------------------------------------------------+
```

---

### 4.4 The Voice Selector & Live Preview

```
+-----------------------------------------------------------------------------+
| VOICE SELF-REFERENCE                                                       |
|                                                                             |
|  (*) First Person (Default)                                                 |
|      "I am monitoring our ZFS pool. I detected an unmanaged config drift."  |
|                                                                             |
|  ( ) The Computer                                                           |
|      "The host system is nominal. An unmanaged config drift was detected."  |
|                                                                             |
|  ( ) Hybrid                                                                 |
|      "System state is nominal. I recommend reviewing the recent drift."     |
+-----------------------------------------------------------------------------+
```

---

## 5. Living Rhythm & Attention Budget (The 7-Day Cycle)

To prevent notification fatigue, Halbert enforces a strict **Attention Budget Engine**:

```
+-----------------------------------------------------------------------------+
| WEEKLY CADENCE TIMELINE                                                     |
|                                                                             |
| MON    08:30  Morning Report (Weekly hygiene overview & package updates)     |
| TUE    14:00  [Proactive Interrupt] Triggered by bad SSH drop-in edit       |
| WED    --:--  Silent monitoring (Zero interrupts; 3 notices queued in log)   |
| THU    08:30  Morning Report (Notices summarized in 2 bullets)              |
| FRI    17:00  Pre-weekend check (Backup destination disk space verification)|
| SAT    --:--  Quiet Hours active (Non-critical alerts suppressed)           |
| SUN    03:00  Automated ZFS Scrub & SMART long test (Autonomous background)  |
|        09:00  Sunday Morning Digest (Scrub results clean; 0 action needed)  |
+-----------------------------------------------------------------------------+
```

### Rate Limiting & Escalation Rules:
1. **Max Interrupt Frequency:** In *Balanced* mode, Halbert will initiate at most **2 proactive interrupts per day** (excluding Critical emergencies like hardware failure or active security compromise).
2. **Batching:** Minor and notice-level findings are never dispatched as standalone interrupts; they are grouped into the next **Morning Report**.
3. **Decay & Re-check:** Snoozed findings remain silent until their snooze period expires, at which point the detector re-evaluates the system. If the issue was resolved manually in the interim, the finding auto-resolves silently without bothering the user.

---

## 6. Accessibility & Keyboard Navigation Specification

Power users and administrators must be able to operate Halbert entirely from the keyboard.

### 6.1 Global Keyboard Shortcuts Map

| Shortcut | Action | Scope |
|---|---|---|
| `Cmd/Ctrl + K` | Open Module Summoning Palette | Global |
| `Cmd/Ctrl + /` | Focus Conversation Input Field | Global |
| `Cmd/Ctrl + B` | Toggle between ENGAGED mode and BROWSING mode | Global |
| `Cmd/Ctrl + Shift + A` | Open Pending Approvals Queue | Global |
| `Cmd/Ctrl + Shift + W` | Toggle Context Region Drawer (Evidence / Whys) | ENGAGED Mode |
| `Cmd/Ctrl + Enter` | Submit Prompt / Confirm Active Proposal | Inside Prompt / Proposal |
| `Esc` | Close Palette / Dismiss Drawer / Unfocus | Global |
| `J` / `K` | Navigate between Message Cards / Digest Items | Conversation Spine |
| `A` | Approve focused proposal | On Focused Card |
| `S` | Snooze focused finding | On Focused Card |
| `D` | Dismiss focused finding | On Focused Card |

### 6.2 Screen Reader & Semantic ARIA Structure
- **Live Regions:** Conversation updates utilize `aria-live="polite"` so screen readers narrate new messages without interrupting active reading.
- **DiffBlocks:** Structured with `<ins>` and `<del>` semantic markup alongside `aria-label="Addition: line..."` for unambiguous diff auditing.
- **WhyChips:** Rendered as interactive `<button aria-expanded="false" aria-haspopup="dialog">` elements with descriptive labels (`aria-label="View provenance and rationale for SSH conflict finding"`).

---

## 7. Design Recommendations & Prioritization Matrix

| Priority | Feature / Flow | User Value | Architectural Readiness | Recommended Action |
|---|---|---|---|---|
| **P0** | **Two-Column ENGAGED Layout (`SidePanel.tsx` -> `AgentChat.tsx`)** | Essential (Defines product identity) | High (AgentPanel & SSE streaming exist) | Refactor `Layout.tsx` to mount conversation spine + context container. |
| **P0** | **`WhyChip` & Provenance Card (`WhyChip.tsx`)** | Core Law (No hallucination / full trust) | Medium (Needs structured SSE events) | Build unified component consuming SQLite findings & SourcePrep locators. |
| **P0** | **Interactive Config Proposal & DiffBlock** | Essential for Slice 1 | High (`write_config.py` & `DiffBlock.tsx` exist) | Wire `DiffBlock` into context region with direct Polkit/approval execution. |
| **P1** | **Morning Report Structured Digest** | High (Cheapest "alive" behavior) | High (Autonomous task scheduler exists) | Build scheduled morning tick producing consolidated digest container. |
| **P1** | **Cmd+K Module Palette** | High (Power user workflow) | Medium (Needs Module Registry map) | Implement Radix Command Dialog with initial 4 core modules. |
| **P2** | **Being Settings Tab (Voice, Proactivity Dial)** | Medium (User comfort & uncanny prevention) | High (`being.yml` schema defined) | Add Being tab in `Settings.tsx` with live preview components. |
| **P2** | **Tauri System Tray Indicator (Calm / Urgent)** | Medium (Ambient presence) | Medium (Tauri v2 tray APIs available) | Wire tray icon states to SSE push event stream. |

---

*This specification serves as the formal UX & Interaction Design counterpart to the engineering roadmap. Development of Phase 5 (Config Brain / Why Data Model), Phase 6 (Being Config), and Phase 7/8 (Proactive Channel & Reactive Slices) should implement against the interaction flows and component wireframes detailed herein.*
