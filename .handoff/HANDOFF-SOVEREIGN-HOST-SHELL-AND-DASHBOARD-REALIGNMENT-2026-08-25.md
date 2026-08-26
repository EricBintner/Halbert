# Handoff: Sovereign Host Shell & Dashboard Realignment

**Date:** 2026-08-25  
**Author:** Antigravity (Systems Architect & Pair Partner)  
**Status:** Strategic Architecture Handoff & Frontend Alignment Blueprint  
**Target:** `.handoff/HANDOFF-SOVEREIGN-HOST-SHELL-AND-DASHBOARD-REALIGNMENT-2026-08-25.md`  
**Reads with:**
- [GEMINI-Opinion.md](file:///Volumes/4TB-BAD/Halbert/GEMINI-Opinion.md) — Strategic Architectural Assessment & Realignment Blueprint
- [REVIEW-DESIGN-MECHANICS-2026-08-23.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/REVIEW-DESIGN-MECHANICS-2026-08-23.md) — Interaction Lifecycles & Dual-Mode UI
- [SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md](file:///Volumes/4TB-BAD/Halbert/.handoff/SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md) — Wrap-up Review & Unwired Defects
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md) — Sovereign Host 2.0 Blueprint Suite

---

## 1. Executive Intent: The Original Ethos & Vision

The founding thesis of Halbert (`documentation/design/philosophy.md` and `GEMINI-Opinion.md`) remains the north star of this project:

> *"An LLM that identifies as the computer itself is fundamentally more useful than an LLM that merely answers questions about computers."*

### Core Tenets of the Vision:
1. **Self-Identification ("I AM"):** The AI is not a generic external chatbot roleplaying as an assistant; its identity is the host machine (`hostname`, kernel, storage topology, thermal state, running daemons).
2. **System State as Biography:** Telemetry and logs are experiential memory ("I experienced a thermal spike at 03:14", "My disk read error occurred on `/dev/nvme0n1`").
3. **Configuration as Physiology:** Config files (`/etc/fstab`, `systemd`, `sysctl`, drop-ins) represent the machine's bodily structure—understood, maintained, and cared for from the inside.
4. **Fluid Execution & Agency (Learning from Warp & Claude Code):**
   - Terminal commands flow directly within the conversation stream as interactive tiles.
   - Out-of-view terminals dock cleanly into a persistent accordion dock.
   - Long-running maintenance tasks are handed off to autonomous host subagents without freezing the main chat.
   - The user never has to manually manage, title, or resume sessions; the host maintains a continuous, autobiographical timeline.

---

## 2. What the User (Founder) Is Seeing Instead

When the founder launched the app following the recent 23-task implementation sprint, they uploaded a screenshot showing that **the app visually looks identical to the legacy 2025 build**.

### The Visual Reality in the User's Screenshot:
* **The Legacy 17-Tab Sidebar:** The left navigation rail still displays the full Cockpit-style IT administration list (Dashboard, Agent, Services, Storage, Backups, Apps, Security, Network, Sharing, Containers, GPU, Development, Approvals, Settings).
* **The Empty Agent Landing Page:** Clicking on `/agent` displays a generic, centered cartoon robot illustration with the text:
  > *"Halbert Agent: I can help you manage your system, search documentation, execute commands, and more. Ask me anything about your Linux environment."*  
  Followed by 4 static starter pills (`Check system status`, `Search docs`, `Manage services`, `Run diagnostics`).
* **The Disjointed Slide-Out Drawer:** The right side of the screen still mounts the legacy `SidePanel` with 3 separate tabs (`Agent`, `Chat`, `>_ Terminal`), maintaining an artificial split between "talking" and "terminal".
* **Complete Invisibility of New Work:** None of the newly built streaming terminal infrastructure (`TerminalAccordionDock`, `TerminalTile`, `TetherChip`, Somatic Blocks, Subagent feeds) is visible anywhere on screen.

To the user, it feels as though the entire vision was discussed and documented, but the actual app did not change.

---

## 3. The Root Cause: Engine vs. Shell Disconnect

The disconnect occurred because of a classic systems engineering trap: **the low-level engine was built, but the top-level application shell was never updated.**

1. **Under-the-Hood Work Landed, Shell Remained Frozen:**
   The sprint implemented Tracks A through F (async PTYs, WebSocket bridge, Somatic Blocks, SubagentManager, SQLite conversation store, Living Reflexes, and React components like `TerminalAccordionDock.tsx` and `TerminalTile.tsx`). However, **`Layout.tsx` and `App.tsx` were never refactored**. The main application shell continued rendering the legacy layout.
2. **Conditional Invisibility:**
   The `TerminalAccordionDock` was added to `AgentPanel.tsx`, but with this condition:
   ```tsx
   if (sessions.length === 0) {
     return null; // Renders NOTHING when no terminal is active!
   }
   ```
   Because no terminal was running at startup, the component rendered nothing, leaving the screen completely blank and unchanged.
3. **The Unwired SSE Gap (Flagged in Review):**
   As documented in [`.handoff/SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SOVEREIGN-HOST-REVIEW-FINDINGS-2026-08-25.md) (Item #9), `useAgentStream` was not yet connected to the backend `terminal_spawn` SSE events, meaning background terminal spawns never reached the frontend store to begin with.

---

## 4. CRITICAL CLARIFICATION: We Are NOT Getting Rid of the Dashboard

It is essential to clarify a fundamental misunderstanding:
**We are NOT deleting, abandoning, or getting rid of the Dashboard or its system pages.**

The dedicated system pages (**Services, Storage, Backups, Security, Network, Containers, Approvals**) provide enormous value for:
* Deep visual inspection of storage pools, mount points, and SMART disk health.
* Viewing systemd unit dependencies and service logs.
* Direct package and container management.
* High-density administrative browsing when you *want* a dashboard view.

### The Real Architecture: Two Operating Modes (Engaged vs. Browsing)

As formally specified in [REVIEW-DESIGN-MECHANICS-2026-08-23.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/REVIEW-DESIGN-MECHANICS-2026-08-23.md) (§2), Halbert is designed with **Two Complementary Modes**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HALBERT DUAL-MODE SHELL                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌───────────────────────────────────┐ ┌─────────────────────────────────┐ │
│   │ MODE 1: ENGAGED                   │ │ MODE 2: BROWSING                │ │
│   │ (The Sovereign Host Surface)      │ │ (The System Administration Hub) │ │
│   ├───────────────────────────────────┤ ├─────────────────────────────────┤ │
│   │ • Continuous Conversation Spine   │ │ • Full Dashboard Grid Overview  │ │
│   │   where Halbert speaks as host.   │ │ • Services, Storage, Backups,   │ │
│   │ • Dynamic Context Stage (Vitals,  │ │   Security, Network, Containers │ │
│   │   Diffs, Evidence Drawer).        │ │ • Deep Administrative Controls  │ │
│   │ • Flowing In-Chat Terminals &     │ │ • All Existing Dashboard Pages  │ │
│   │   Terminal Accordion Dock.        │ │   Preserved & Intact            │ │
│   └───────────────────────────────────┘ └─────────────────────────────────┘ │
│                     ▲                                     ▲                 │
│                     └────────── [ 1-Click Toggle ] ───────┘                 │
│                                (or Cmd+B Shortcut)                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

* **Mode 1 (Engaged):** The default primary workspace. A high-agency two-column conversational environment where you interact with the computer itself. Terminals flow in chat, and the right stage holds vitals, diff proposals, and the terminal dock.
* **Mode 2 (Browsing):** The comprehensive system dashboard. All existing pages remain completely accessible with one click (or `Cmd+B`), and individual dashboard modules can be summoned directly into the Engaged Stage via conversation or `Cmd+K`.

**The problem is not that the dashboard exists; the problem is that the dashboard is currently the *only* thing visible, and the Sovereign Host experience is trapped in a tiny sidecar.**

---

## 5. Concrete Execution Plan for the Next Sprint

To resolve this and bring the vision to life in the live UI:

### Task 1: Shell Re-Architecture in `Layout.tsx` & `App.tsx`
* Add a global **Mode Switcher** in the top navigation bar: `[💬 Sovereign Host (Engaged)]` $\leftrightarrow$ `[📊 Dashboard (Browsing)]` (toggleable via `Cmd+B`).
* In **Engaged Mode (Default)**:
  * Mount the **Two-Column Sovereign Host Canvas**:
    * **Left 50%:** Continuous Conversation Spine (`AgentChat.tsx` elevated to primary canvas).
    * **Right 50%:** Dynamic Context Stage (permanently displaying live Host Vitals and the `TerminalAccordionDock`).
* In **Browsing Mode**:
  * Render the traditional dashboard layout and full system navigation pages (Services, Storage, Backups, etc.) exactly as they exist today.

### Task 2: Fix the Idle State of `TerminalAccordionDock.tsx`
* Remove the `if (sessions.length === 0) return null;` hard suppression.
* When idle (0 active sessions), render a clean, subtle empty dock state with a `[+ New Terminal]` quick-launch button and status summary, demonstrating that the terminal nervous system is active and ready.

### Task 3: Complete the Terminal SSE Stream Wiring (E1f)
* Update `useAgentStream.ts` to consume the backend `terminal_spawn`, `terminal_output`, and `terminal_complete` SSE events.
* Connect these events directly to the frontend `useTerminalSessions` singleton store so that running commands and subagents immediately stream into the in-chat `TerminalTile` and populate the `TerminalAccordionDock`.

### Task 4: Replace the Generic Agent Greeting with Host Embodiment
* Remove the cartoon robot avatar and generic "Ask me anything about Linux" greeting on the `/agent` canvas.
* Replace with Halbert's true first-person initialization state:
  > *"I am `halbert-node-01` (Ubuntu 24.04, Linux 6.8.0-31-generic). Uptime is 18 days. All 16 cores and 3 storage pools are healthy. What would you like to inspect or configure?"*

---

## 6. Summary for the Incoming Developer / Partner

The backend primitives and React components for Sovereign Host v2.0 are **already written, tested, and pushed** to the repository. 

Your mission is **not** to reinvent the engine or delete the dashboard. Your mission is to **bridge the engine to the application shell**:
1. Implement the dual-mode switch in `Layout.tsx`.
2. Mount the two-column Engaged view as the primary workspace while preserving all dashboard pages.
3. Wire the terminal SSE stream to the frontend store so the user sees their machine running live.
