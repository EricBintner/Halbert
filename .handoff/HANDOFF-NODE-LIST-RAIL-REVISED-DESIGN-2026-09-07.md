# Revised Design: Left Rail Node Navigation & Shell Simplification

**Document:** `HANDOFF-NODE-LIST-RAIL-REVISED-DESIGN-2026-09-07.md`  
**Supersedes:** `HANDOFF-NODE-LIST-RAIL-DESIGN-2026-09-07.md`  
**Date:** 2026-09-07  
**Author:** Eric / Pair Programming Session  
**Status:** Approved design direction. Ready for execution.

---

## 1. Executive Summary & Problems Resolved

In previous design iterations and AI sessions, two key defects repeatedly caused confusion:
1. **Top-Bar PresencePill was a misunderstanding:** There was never supposed to be a top-bar dropdown or switcher pill. Node awareness and switching belong entirely in the left rail.
2. **The "Dashboard > Dashboard" / "Overview > Overview" nesting trap:** 
   - First, the rail had an "Overview" section containing a "Dashboard" item.
   - Then, the previous handoff proposed a "Set-Level Overview" and a "Node-Level Overview".
   - **Resolution:** There is **never** a clickable button called "Overview" or "Dashboard". **The node button itself is the landing page.** Clicking `[ Mac Studio ]` lands directly on the host's summary page (`/`).

---

## 2. Core Design Principles

1. **Top-Bar Cleaned:**
   - Remove `PresencePill` completely from the header. No top-bar switcher, no header dropdown.
2. **The Node Button IS the Landing Page:**
   - Clicking an entity's active node button (`[ Mac Studio ]`) navigates directly to `/` (the host vitals & status landing page).
   - There are no redundant sub-items called "Overview" or "Dashboard".
3. **No Noisy Category Headlines:**
   - Eliminate all uppercase/small-caps headers (`SYSTEM`, `WORKLOADS`, `OVERVIEW`, `FINDINGS & APPROVALS`, `SET-LEVEL`, `NODE-LEVEL`).
   - Use clean negative space and subtle dividers between logical groups.
4. **Home Automation as Shared Environment:**
   - Home Automation (`/home`) is not a sub-item of "Overview" or a machine tool. It is a shared environment surface across the entity.
5. **Shared Compute Only When >1 Node Exists:**
   - If only 1 node exists, no "Shared Compute" is shown.
   - When a 2nd node is paired on the network, "Shared Compute" unlocks in the shared section.
6. **Consolidated Machine Tools:**
   - The artificial split between "System" and "Workloads" is removed. All tools for the active machine (Terminal, Storage, Services, Containers, GPU, Network, Backups, Apps, Dev) live together as machine capabilities.
7. **Single-Node Default = Zero Friction:**
   - A solo machine install shows only the entity and its machine tools. No cluster chrome, no multi-node headers.

---

## 3. Rail Layout Specifications

### 3.1 Scenario A: Single Node (Default / Solo Install)
A user running Halbert on one machine (e.g. Mac Studio) sees a clean, focused console with zero cluster baggage:

```text
┌────────────────────────────────────────┐
│ Halbert                                │  ← Entity anchor (lands on /)
│ [ Mac Studio ]                         │  ← Machine identifier
├────────────────────────────────────────┤
│ Home                                   │  ← Shared HA (if enabled)
├────────────────────────────────────────┤
│ Terminal                               │  ← Machine tools & resources
│ Storage                                │    (No "System" or "Workloads" headers)
│ Services                               │
│ Containers                             │  (if dev/container capable)
│ GPU                                    │  (if GPU present)
│ Network                                │
│ Backups                                │
│ Apps                                   │
│ Development                            │  (if dev capable)
└────────────────────────────────────────┘
```

*If it is a dedicated home server (e.g. N150 appliance):* It shows `Home` and whatever limited IT tools exist on that box (e.g. single disk, basic services, no GPU).

---

### 3.2 Scenario B: Multi-Node on Same Network (e.g. Mac Studio + N150)
When two nodes share the same entity identity on the network, the top of the rail renders one entity block with buttons for each node:

```text
┌────────────────────────────────────────┐
│ Halbert                                │  ← Entity Block
│ [ Mac Studio (active) ]   [ N150 ]     │  ← Segmented node buttons
├────────────────────────────────────────┤
│ Home                                   │  ← Shared HA across Halbert
│ Shared Compute                         │  ← Shared compute mesh across nodes
├────────────────────────────────────────┤
│ Terminal                               │  ← Full IT dashboard for the
│ Storage                                │    ACTIVE node (Mac Studio)
│ Services                               │
│ Containers                             │
│ GPU                                    │
│ Network                                │
│ Backups                                │
└────────────────────────────────────────┘
```

#### Interaction Behavior:
1. **Active Node State:** `[ Mac Studio ]` is highlighted. Clicking it navigates to `/` (Mac Studio host dashboard).
2. **Switching Nodes:** Clicking `[ N150 ]`:
   - Switches the active instance API endpoint via `setInstanceEndpoint()`.
   - Reloads to N150's landing page (`/`).
   - The IT dashboard tools below immediately update to reflect N150's capabilities and data (e.g., its services, single disk, terminal).
   - `Home` and `Shared Compute` remain identical in place (shared data).
3. **Route Reconciliation:** If the user was on a route unsupported by the target node (e.g., `/gpu` switching to N150 which has no GPU), the app safely falls back to `/`.

---

### 3.3 Scenario C: Independent Entities (e.g. Halbert + Halley)
If distinct independent entities exist on the network, each entity renders its own block with its respective node buttons:

```text
┌────────────────────────────────────────┐
│ Halbert                                │
│ [ Mac Studio ]   [ N150 ]              │
│                                        │
│ Halley                                 │
│ [ Laptop ]                             │
├────────────────────────────────────────┤
│ Home                                   │
│ Shared Compute                         │
├────────────────────────────────────────┤
│ Terminal                               │
│ Storage                                │
│ Services                               │
...
```

---

## 4. Architectural Changes

### 4.1 Frontend (`halbert_core/dashboard/frontend/src/`)
1. **`components/Layout.tsx`:**
   - Remove `<PresencePill />` from the header bar (line 539) and remove its unused imports.
   - Mount `<EntityNodeBlock />` as the header component for `<NavRail />`.
   - Restructure `navSections` to eliminate `SYSTEM`, `WORKLOADS`, and `OVERVIEW` headlines.
   - Form two clean groups:
     - **Shared:** `Home` (`/home`), `Shared Compute` (`/compute` — conditional on `nodeCount > 1`).
     - **Node Tools:** `Terminal`, `Storage`, `Services`, `Containers`, `GPU`, `Network`, `Backups`, `Apps`, `Development` (filtered by node capability).
2. **New Component `components/shell/EntityNodeBlock.tsx`:**
   - Reads `/api/instance/info` and `/api/devices`.
   - Renders entity name and node button row (`[ Mac Studio ]`, `[ N150 ]`).
   - Manages active highlight and endpoint switching via `setInstanceEndpoint()`.
3. **`packages/design-system/src/surfaces/NavRail.tsx`:**
   - Ensure headline-free rendering when `section.label === ''` or section labels are suppressed.
   - Maintain consistent negative space between section groups without requiring text headers.

---

## 5. Clarifying Points for Implementation

1. **"Shared Compute" Screen:** Open [`NodeFleetCockpit.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/fleet/NodeFleetCockpit.tsx) (grid of all nodes, live CPU/RAM/thermals, compute capabilities) mapped to `/compute`.
2. **Node Button Labels:** Use configured `body_name` or hardware identifier (e.g. `Mac Studio`, `N150`).
3. **Findings & Approvals:** Kept off the primary rail or kept as low-key utility items per future review.
4. **Header Cleanliness:** Top bar has zero switcher clutter; Left Rail is the single source of truth for node navigation.
