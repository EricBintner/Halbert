# Streaming In-Chat Terminals & Accordion UI Orchestration

**Version:** 1.0.0  
**Date:** August 2026  
**Status:** Core Interaction & UI Specification  
**Reads with:**
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md)
- [SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md)
- [SUBAGENTS-AND-TASK-DAEMONS.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SUBAGENTS-AND-TASK-DAEMONS.md)

---

## 1. Executive Summary & Interaction Paradigm

A major friction in existing AI developer tools is terminal fragmentation:
1. **Disconnected Terminal Tabs:** Terminals are hidden in separate tabs or sub-windows, forcing users to constantly switch contexts away from the conversation.
2. **Static Text Dumps:** Chatbots dump massive, unformatted stdout text blobs into the chat window, polluting the conversation history and destroying token budgets.

Halbert introduces the **Flowing In-Chat Terminal with Out-of-View Accordion Docking**:
* **In-Stream Flow:** When a command, script, or autonomous subagent executes, an interactive **Streaming Terminal Tile** flows naturally inside the conversation spine at the active turn.
* **Auto-Docking Accordion:** When the user scrolls past the terminal or continues chatting, the terminal tile seamlessly docks into the right-hand **Context Stage**, collapsing into an **Active Terminal Accordion Dock**.
* **Bi-Directional Tether:** The user can interact with the terminal from the right-hand accordion dock, expand it, or click a button to immediately jump back to the exact conversational turn where the command was initiated.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 THE FLOWING TERMINAL LIFECYCLE & DOCKING                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [ CONVERSATION SPINE (LEFT) ]              [ CONTEXT STAGE (RIGHT) ]      │
│                                                                             │
│   Halbert: "Starting ZFS scrub..."                                          │
│   ┌───────────────────────────────┐                                         │
│   │ > zpool scrub rpool           │                                         │
│   │ [Live PTY Stream: 12% done]   │                                         │
│   └──────────────┬────────────────┘                                         │
│                  │                                                          │
│                  │ (User scrolls down or chats)                             │
│                  │ (IntersectionObserver triggers)                          │
│                  ▼                                                          │
│   [ Terminal scrolls OUT of view ] ─────────▶ ┌───────────────────────────┐ │
│   ┌───────────────────────────────┐           │ TERMINAL ACCORDION DOCK   │ │
│   │ Halbert: "Meanwhile, CPU is.."│           ├───────────────────────────┤ │
│   │                               │           │ ▼ [●] zpool scrub (14m)   │ │
│   │                               │           │   [Live Output View]      │ │
│   │                               │           ├───────────────────────────┤ │
│   │                               │           │ ▶ [✓] Subagent: SSH Audit │ │
│   │                               │           ├───────────────────────────┤ │
│   │                               │           │ ▶ [_] Interactive Shell   │ │
│   └───────────────────────────────┘           └───────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The In-Stream Flowing Terminal Tile (Inline Surface)

When Halbert or a subagent executes a command, an inline PTY terminal tile renders directly within the conversation stream.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ INLINE TERMINAL TILE: #term_01J5K                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ [● RUNNING]  $ sudo zfs scrub rpool                    [00:14:22] [PID 4192]│
├─────────────────────────────────────────────────────────────────────────────┤
│ scan: scrub in progress since Mon Aug 24 22:10:00 2026                      │
│       1.42T scanned at 1.12G/s, 420G issued at 340M/s, 3.84T total          │
│       0B repaired, 10.94% done, 02:48:12 to go                              │
│ config:                                                                     │
│       NAME        STATE     READ WRITE CKSUM                                │
│       rpool       ONLINE       0     0     0                                │
│         nvme0n1   ONLINE       0     0     0                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ [Pin to Stage]      [Send Input (stdin)]      [Terminate]      [Copy Output]│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Technical Characteristics:
1. **Interactive xterm.js / WebGL Canvas:** Fully supports ANSI color codes, curses/top interfaces, terminal resize signals (`SIGWINCH`), and keyboard navigation.
2. **Interactive Stdin & Privilege Input:** Supports interactive inputs, password elevation prompts (`[sudo] password for admin:`), or confirmations (`y/N`) without breaking the chat flow.
3. **Execution Metadata Header:**
   - Status badge: `[● RUNNING]`, `[✓ EXIT 0]`, `[⚠ EXIT 137 (OOM)]`.
   - Execution timer, active PID, and command name.
   - Quick action buttons: `[Pin to Stage]`, `[Maximize]`, `[Terminate]`.

---

## 3. The Out-of-View Transition & IntersectionObserver

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 INTERSECTION OBSERVER STATE MACHINE                         │
│                                                                             │
│  [ IN-VIEW ] (IntersectionRatio >= 0.25)                                    │
│       │                                                                     │
│       │ User scrolls away (IntersectionRatio < 0.25)                        │
│       ▼                                                                     │
│  [ TRANSITIONING ] ──(GSAP 300ms FLIP animation)                            │
│       │                                                                     │
│       ▼                                                                     │
│  [ DOCKED IN RIGHT ACCORDION ]                                              │
│       │                                                                     │
│       │ User scrolls back into view OR clicks [Jump to Origin]              │
│       ▼                                                                     │
│  [ RESTORED IN CHAT ]                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Logic:
1. **Viewport Watcher:** An `IntersectionObserver` instance monitors all inline terminal DOM containers inside the left conversation scroll container.
2. **Threshold Boundary:** When an active or recently completed terminal's visibility drops below **25%** (e.g. pushed up by new messages or scrolled past):
   - An indicator chip appears in the conversation stream: `[Terminal #1 docked in Stage →]`.
   - The terminal session dynamically mounts into the **Right-Column Accordion Dock**.
3. **State Persistence:** The PTY session and buffer are preserved across docking transitions using a shared singleton PTY store (`TerminalSessionManager`). Zero output is lost, and active processes remain uninterrupted.

---

## 4. The Right-Column Terminal Accordion Dock

In the right-hand Context Stage, active and recent terminals live in a clean, high-density accordion menu.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ACTIVE TERMINAL ACCORDION DOCK (Right Column)                  [+ New Shell]│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ▼ [● RUNNING] #1: zpool scrub rpool (PID 4192)                   [14m 22s]  │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ scan: scrub in progress since Mon Aug 24 22:10:00 2026                  │ │
│ │       1.42T scanned at 1.12G/s, 420G issued at 340M/s, 3.84T total      │ │
│ │       0B repaired, 10.94% done, 02:48:12 to go                          │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│   [Jump to Chat Origin]       [Full Screen]       [Send Ctrl+C]             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▶ [✓ DONE]    #2: StorageAuditor: SMART Long Test (/dev/nvme0n1) [0 Errors] │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▶ [✓ DONE]    #3: ConfigRefactor: sshd_config.d AST Precedence Check        │
├─────────────────────────────────────────────────────────────────────────────┤
│ ▶ [_ IDLE]    #4: Default Host Shell (zsh / bash)                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Accordion Capabilities:
* **Multi-Terminal Management:** Shows multiple background subagents, long-running scrubs, builds, and interactive shells simultaneously.
* **Status Badges:** Color-coded status icons indicating active CPU/IO activity, completed jobs, or failed commands.
* **Bi-Directional Navigation (`Jump to Chat Origin`):** Clicking jumps the left conversation spine directly to the message where the command was initiated, highlighting the corresponding Somatic Block.
* **Quick Expansion:** Expanding any accordion section grants full PTY interactivity with standard keyboard input.

---

## 5. The Unified Chat-Shell Console (The Input Bar)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ > sudo ufw status verbose█                                                  │
│   [Auto-detected: Shell Command]  [Target: Default Host PTY]                │
│   [Tab: Autocomplete]  [Enter: Run in Terminal]  [Cmd+Enter: Ask Halbert]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Rules:
1. **Intelligent Mode Detection:**
   - If input starts with a known shell command (`sudo`, `systemctl`, `ls`, `git`, `zpool`, `./`) $\rightarrow$ Highlighted with shell syntax colors; `Enter` executes immediately in an inline terminal tile.
   - If input is natural language (`"Why did docker restart?"`, `"Check my disk health"`) $\rightarrow$ `Enter` triggers Halbert's cognitive tick and agentic execution.
2. **Manual Overrides:**
   - `Enter`: Default execution based on auto-detection.
   - `Cmd+Enter`: Force interpret as conversational inquiry / agent goal.
   - `Ctrl+\``: Toggle focus directly into the currently active terminal tile.
   - `Cmd+K`: Open Module and Reflex summoning palette.
3. **Host-Aware Predictive Ghosting:**
   - As you type in the prompt bar, Halbert's local Tier 1 fast model predicts command parameters based on live host state (e.g. auto-suggesting failed systemd unit names, active device paths, or recent config files).
