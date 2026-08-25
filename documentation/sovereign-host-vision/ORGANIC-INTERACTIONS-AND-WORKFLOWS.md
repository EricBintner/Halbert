# Utility-First Workflows & Direct Manipulation

**Version:** 1.0.0-REVISED  
**Date:** August 2026  
**Status:** Core Interaction & UX Specification  
**Reads with:**
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md)
- [SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SOMATIC-BLOCKS-AND-NERVOUS-SYSTEM.md)
- [SUBAGENTS-AND-TASK-DAEMONS.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/SUBAGENTS-AND-TASK-DAEMONS.md)
- [STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/STREAMING-TERMINALS-AND-UI-ORCHESTRATION.md)

---

## 1. Executive Summary: Utility Over Decoration

Every interaction pattern in Halbert must directly eliminate friction, save time, or prevent system breakages. We reject decorative UI fluff (such as pulsing animations or abstract graphs) in favor of high-leverage ergonomic tools:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE 5 DIRECT USER SUPERPOWERS                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. LASSO-TO-MIND DIAGNOSTICS                                              │
│      Highlight any traceback in a terminal -> 1-click grounded fix proposal.│
│                                                                             │
│   2. PARAMETRIC HEADROOM SLIDERS                                            │
│      Tune numerical configs visually with live RAM and blast-radius preview.│
│                                                                             │
│   3. BI-DIRECTIONAL TETHERED ACCORDION                                      │
│      Scroll chat freely while long commands run safely in a docked dock.    │
│                                                                             │
│   4. "WHAT CHANGED?" HISTORICAL STATE DIFF                                  │
│      Instantly diagnose post-upgrade breakages by comparing system snapshots│
│                                                                             │
│   5. LIVING REFLEXES (1-CLICK RUNBOOKS)                                     │
│      Turn resolved quirks into instant 1-click recovery actions for next time│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Superpower 1: "Lasso-to-Mind" Direct Diagnosis

### The Problem:
When a terminal command fails, developers normally undergo a 6-step chore: select traceback $\rightarrow$ copy $\rightarrow$ switch to chat prompt $\rightarrow$ paste $\rightarrow$ type explanation request $\rightarrow$ copy suggested fix back to terminal.

### The Halbert Solution:
1. Highlight any error line, warning, or log traceback in any terminal tile (inline or docked).
2. A contextual floating pill appears: `[✨ Fix with Halbert]`.
3. Clicking it extracts the text along with PID, working directory, exit code, and recent command history.
4. Halbert immediately generates a structured **Proposal Block** with an inline dry-run diff and `[Approve & Run]` button.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ INLINE TERMINAL TILE                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ $ docker run -d --name db postgres:16                                       │
│ ┌────────────────────────────────────────────────────────┐                  │
│ │ FATAL:  could not open directory "/var/lib/postgresql":│ ◄ USER SELECTS   │
│ │         Permission denied                              │   THIS TEXT      │
│ └────────────────────────────────────────────────────────┘                  │
│   ▲                                                                         │
│   │ [✨ Fix with Halbert]   [🔍 Spawn Investigator]   [📋 Copy]             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Superpower 2: Parametric Headroom Sliders

### The Problem:
Editing numerical system configuration files (e.g. `vm.swappiness=10`, `zfs_arc_max=25769803776`, or `cgroup memory.max=8G`) is intimidating. Users cannot easily verify units, valid min/max limits, or understand the side effects on running containers.

### The Halbert Solution:
When Halbert proposes modifying a numeric configuration directive, the Proposal Block renders an **Interactive Parametric Slider**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CONTEXT REGION: Interactive Parameter Tuning                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ TARGET: /etc/modprobe.d/zfs.conf -> zfs.zfs_arc_max                         │
│                                                                             │
│ Current: [ 32 GB (No Limit) ] ───▶ Proposed: [ 24 GB ]                      │
│                                                                             │
│ [ 8 GB ] ──────────[●]──────────────────────── [ 64 GB Total RAM ]           │
│                    ▲ 24 GB (Recommended)                                    │
│                                                                             │
│ LIVE HEADROOM & IMPACT SIMULATION:                                          │
│ • Free Host RAM Headroom: +8.0 GB (Guaranteed for Docker & Desktop apps)    │
│ • Estimated ARC Cache Hit Rate: 98.4% (-1.2% delta, nominal)                │
│ • Dependent Services: zfs.ko, dockerd, postgresql.service                   │
│                                                                             │
│ [ APPROVE & APPLY (24 GB) ]      [ DRY-RUN TEST ]      [ CANCEL ]           │
└─────────────────────────────────────────────────────────────────────────────┘
```

* Dragging the slider dynamically recalculates the RAM impact, ARC hit rate, and blast-radius score in real-time before applying the change.

---

## 4. Superpower 3: The Bi-Directional Tethered Accordion

### The Problem:
Long-running jobs (`apt upgrade`, `zfs scrub`, `docker build`) either lock the terminal interface or scroll far out of view as new chat messages arrive.

### The Halbert Solution:
* When an inline terminal tile scrolls out of the active conversation viewport ($<25\%$ visibility), it docks into the **Right-Column Terminal Accordion Dock**.
* A persistent **Tether Chip** remains in the chat stream: `[Terminal #1: zfs scrub → DOCKED IN STAGE]`.
* **Hovering** the Tether Chip highlights the active docked card on the right.
* **Clicking `[Jump to Origin]`** in the accordion smoothly scrolls the conversation spine back to the exact turn where the job started.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE BI-DIRECTIONAL TETHER                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [ CONVERSATION SPINE (LEFT) ]              [ CONTEXT STAGE (RIGHT) ]      │
│                                                                             │
│   Halbert: "Starting ZFS scrub..."                                          │
│   ┌───────────────────────────────┐          ┌────────────────────────────┐ │
│   │ [⚡ DOCKED IN STAGE →]         │ ═════════╡ ▼ [●] zpool scrub (PID 4192)│ │
│   │ #term_01J5K: zpool scrub      │ (Tether) │   [Live PTY Stream Active] │ │
│   └───────────────────────────────┘          └────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Superpower 4: "What Changed?" (Biographical State Diff)

### The Problem:
After a weekend reboot or automated package upgrade, a service stops working (e.g. DNS resolution fails or a port is blocked). Finding the root cause requires manually diffing config files and grepping `/var/log`.

### The Halbert Solution:
Halbert maintains point-in-time configuration snapshots and daily service baselines. Users can ask:
> *"What changed on this machine between Friday and today?"*

Halbert generates a clean, structured **System Delta View**:
* **Modified Configs:** `/etc/systemd/resolved.conf` (DNSStubListener enabled by upgrade).
* **Updated Packages:** `systemd` (255.4 $\rightarrow$ 255.7).
* **Active Port Conflicts:** Port 53 bound by `systemd-resolved`, blocking local Pi-hole/dnsmasq.
* **Root Cause & Fix:** *"The systemd update enabled DNSStubListener, conflicting with your DNS container. [Click to Apply 1-Click Fix]"*

---

## 6. Superpower 5: Living Reflexes (1-Click Runbooks)

### The Problem:
Machines frequently have recurring hardware or software quirks (e.g. an external audio interface requiring a reset after sleep, or a stale Docker lock file preventing restarts). Users waste time re-explaining the issue.

### The Halbert Solution:
1. When Halbert and the user successfully fix a recurring issue, Halbert prompts: `[Save this fix as a 1-Click Reflex?]`.
2. The user names it: `"Clear Stale Docker Lock"`.
3. Next time that exact error signature or journald trace appears, Halbert proactively prompts:
   > *"I detected the stale Docker daemon lock error. [Run 'Clear Stale Docker Lock' Reflex (1-Click)]"*

---

## 7. Codebase Reality Check (August 2026 Audit)

### 7.1 Superpower Status Summary

| Superpower | Backend | Frontend | Status |
|---|---|---|---|
| **1. Lasso-to-Mind** | `intake/signals.py` can extract error context; `findings/proposals.py` can generate proposals | No selection-to-fix UI in terminal tiles | **Backend ready, frontend missing** |
| **2. Parametric Sliders** | `approval/simulator.py` computes before/after state; `findings/blast_radius.py` scores impact | No slider component; no live headroom simulation UI | **Backend partial, frontend missing — deferred** |
| **3. Tethered Accordion** | PTY backend is `subprocess.run()` stub (see STREAMING-TERMINALS doc §6) | No `IntersectionObserver`, no accordion dock, no tether chips | **Hard blocked on PTY backend** |
| **4. "What Changed?"** | No config snapshot infrastructure exists; no package version tracking; no port conflict detection | No diff view UI | **Not started — deferred** |
| **5. Living Reflexes** | Zero `reflex`/`Reflex` matches in Python; no YAML store; no trigger matching | No 1-click reflex UI | **Not started — depends on Somatic Block unification** |

### 7.2 What Can Be Built Now vs. What Must Wait

**Build now (backend exists, needs frontend):**
- **Lasso-to-Mind (Superpower 1):** `intake/signals.py` already extracts error indicators, file paths, and code blocks via regex in <1ms. `findings/proposals.py` generates `Proposal` objects with dry-run diffs. The missing piece is a frontend pill (`[Fix with Halbert]`) on text selection in `pages/Terminal.tsx` that calls a new endpoint to generate a proposal from the selected text + terminal context. ~80 lines frontend + ~30 lines backend.

**Build after PTY backend (Stage 2):**
- **Tethered Accordion (Superpower 3):** Hard blocked on real PTY. See STREAMING-TERMINALS doc §6.4 for build sequence.

**Build after Somatic Block unification (Stage 1):**
- **Living Reflexes (Superpower 5):** The Reflection block must exist first to synthesize reflexes from resolved incidents. Then add `reflexes/` YAML store + Tier 0 trigger matching.

**Deferred (significant new infrastructure):**
- **Parametric Sliders (Superpower 2):** Requires live RAM/headroom simulation engine that doesn't exist. The `approval/simulator.py` computes static before/after but not live parameter sweeps. Defer until the core terminal + somatic pipeline is working.
- **"What Changed?" (Superpower 4):** Requires config snapshot infrastructure (periodic `/etc` snapshots, package version tracking, port state baselines). This is a new subsystem — defer.
