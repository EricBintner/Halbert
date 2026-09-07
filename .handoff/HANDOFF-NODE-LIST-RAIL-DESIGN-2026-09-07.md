# Handoff: Node List in Left Rail — Design & Open Questions

**To:** External design reviewer / Implementation AI
**From:** Eric (founder) / GLM-5.2 session
**Date:** 2026-09-07
**Status:** Revised design approved by founder. **External review completed 2026-09-07 — resolutions for Q1–Q8 appended as Section 5R, pending founder ratification where noted.** Three newly discovered issues (Section 5R.3) must be folded into the implementation plan before dispatch.

**Supersedes:** `HANDOFF-NODE-LIST-RAIL-DESIGN-2026-09-07.md` (the first draft, which used the term "bodies" and kept the top-bar switcher — both rejected by the founder).

**Incorporates:** `HANDOFF-NODE-LIST-RAIL-REVISED-DESIGN-2026-09-07.md` (the external design feedback document, which the founder approved as more aligned with his vision).

---

## 1. The problem in one sentence

The left rail of the Halbert dashboard only shows pages for the currently connected computer. There is no way to see or navigate to another computer's dashboard. The user wants a **list of nodes (computers) at the top of the left rail**, grouped by entity, where clicking a node shows that machine's dashboard.

---

## 2. Background: What Halbert is and how it works

Halbert is an AI system admin assistant that runs on a computer (typically a Mac Studio or Linux workstation). It can also run on smaller always-on machines like an N150 mini-PC acting as a home automation server. When a user has more than one machine running Halbert on their network, those machines can be **linked** to each other.

### 2.1 Two ways machines can be linked

**Singular entity (one Halbert, multiple computers):**
Multiple computers share the same identity — same name, same memory, same conversation history. The user experiences them as one Halbert that happens to be present on multiple machines. Example: a Mac Studio on the desk and an N150 in the kitchen are the same "Halbert." If you tell Halbert something at your desk, the kitchen Halbert knows it too. This is the default mode when machines are linked.

**Independent entities (separate Halberts):**
Each computer is its own separate Halbert with its own name, memory, and personality. They share compute resources (e.g., the small machine can use the big machine's GPU) but they are different AIs. Example: "Halbert" on the Mac Studio and "Halley" on the laptop.

The switch between these modes is a configuration setting. If a machine is told to use a shared memory store (`canonical_memory_url` in the config), it's in singular mode. If not, it's independent. The UI reflects this — it does not drive it.

### 2.2 What "shared" vs "per-machine" means

**Shared across an entity (same for all computers in a singular group):**
- Home automation — cameras, lights, sensors, HA equipment. The data comes from Home Assistant, which is one system. It doesn't matter which computer you're looking at — the front door camera is the same.
- Conversation history — in singular mode, the conversation is the same across all machines because they share memory and threads.
- Compute resources — which machines have GPUs, who's providing compute power to whom. This is a property of the network of machines, not any single one.

**Per-machine (different for each computer):**
- Storage — the Mac Studio's hard drives are different from the N150's SSD.
- Services — what's running on that specific machine.
- Terminal — a shell on that specific machine.
- Security scan results — the security state of that specific machine.
- Agent approvals — permission requests from the AI agent running on that specific machine.
- Containers, GPU, network config, apps, development tools — all specific to the machine.

---

## 3. The approved revised design

This section describes the design the founder approved. It comes from the external design feedback document (`HANDOFF-NODE-LIST-RAIL-REVISED-DESIGN-2026-09-07.md`).

### 3.1 Core principles

1. **No top-bar switcher.** There was never supposed to be a dropdown or pill in the top bar for switching between machines. A previous AI session built one (called "PresencePill" in the code). It should be removed. The left rail is the single source of truth for which machine you're looking at.

2. **The node button IS the landing page.** Clicking a machine's name in the rail navigates directly to that machine's summary/dashboard page. There is no separate "Overview" or "Dashboard" sub-item to click — the machine name itself is the entry point. This eliminates the confusing "Dashboard > Dashboard" nesting that existed before.

3. **No section headlines.** The current rail has uppercase section headers like "SYSTEM," "WORKLOADS," "OVERVIEW," "FINDINGS & APPROVALS." These are removed. The rail uses clean negative space and subtle dividers between logical groups instead of text labels.

4. **Home automation is a shared environment.** It is not a machine tool. It appears once in the shared section, not per-machine.

5. **Shared compute only when more than one node exists.** A single-machine install sees nothing about compute sharing. When a second machine is linked, a "Shared Compute" item appears in the shared section.

6. **System and Workloads are merged.** The previous design split machine tools into "System" (Services, Storage, Backups, Terminal) and "Workloads" (Containers, GPU, Apps, Network, Development). This split is removed. All machine tools live together in one group.

7. **Single-node = zero friction.** A user with one machine sees a clean console with no cluster/multi-node chrome. The entity name, the machine name, home automation (if configured), and machine tools. That's it.

### 3.2 Rail layout: Single machine (the common case today)

```
┌────────────────────────────────────────┐
│ Halbert                                │  ← Entity name (clicking lands on /)
│ [ Mac Studio ]                         │  ← Machine name (the node button)
├────────────────────────────────────────┤
│ Home                                   │  ← Home automation (only if HA configured)
├────────────────────────────────────────┤
│ Terminal                               │  ← Machine tools (no section headers)
│ Storage                                │
│ Services                                │
│ Containers                             │  (only if the machine has containers)
│ GPU                                    │  (only if the machine has a GPU)
│ Network                                │
│ Backups                                │
│ Apps                                   │
│ Development                            │  (only if the machine has dev tools)
└────────────────────────────────────────┘
```

### 3.3 Rail layout: Multiple machines, same entity

```
┌────────────────────────────────────────┐
│ Halbert                                │  ← Entity name
│ [ Mac Studio (active) ]   [ N150 ]     │  ← Node buttons (click to switch)
├────────────────────────────────────────┤
│ Home                                   │  ← Shared (same data on both machines)
│ Shared Compute                         │  ← Shared (appears only with 2+ nodes)
├────────────────────────────────────────┤
│ Terminal                               │  ← Machine tools for the ACTIVE node
│ Storage                                │    (Mac Studio in this example)
│ Services                               │
│ Containers                             │
│ GPU                                    │
│ Network                                │
│ Backups                                │
└────────────────────────────────────────┘
```

Clicking `[ N150 ]` switches the API endpoint to the N150 and reloads. The machine tools section updates to show N150's tools (which may be fewer — no GPU, fewer services, etc.). Home and Shared Compute stay the same because the data is shared.

### 3.4 Rail layout: Multiple independent entities

```
┌────────────────────────────────────────┐
│ Halbert                                │
│ [ Mac Studio ]   [ N150 ]              │
│                                        │
│ Halley                                 │
│ [ Laptop ]                             │
├────────────────────────────────────────┤
│ Home                                   │  ← Shared section for the active entity
│ Shared Compute                         │
├────────────────────────────────────────┤
│ Terminal                               │  ← Machine tools for the active node
│ Storage                                │
│ ...                                    │
└────────────────────────────────────────┘
```

Each entity is its own block at the top. Clicking a node in any entity block switches to that machine. The shared section and machine tools update to reflect the selected entity and node.

---

## 4. What exists in the code today

This section explains what's currently built, in plain language, so the reviewer understands what can be reused and what needs to change. **Code names are included in parentheses for the implementation AI — they are not user-facing labels.**

### 4.1 The left rail (`Layout.tsx`, `NavRail.tsx`)

The left rail is implemented in `Layout.tsx` (the main shell component) which defines the navigation sections, and `NavRail.tsx` (a shared design-system component) which renders them.

Current rail structure (4 sections with headers):
- **Overview:** Dashboard, Home
- **Findings & Approvals:** Findings, Approvals
- **System:** Services, Storage, Backups, Terminal, Bodies (a page showing all linked machines)
- **Workloads:** Containers, GPU, Apps, Network, Sharing, Development

The `NavRail` component already supports:
- A `header` prop — an optional React node rendered at the very top of the rail (currently unused for the main dashboard, used by Settings). This is where the entity/node block would go.
- Adaptive section labels — if a section has only one visible item, the section header is automatically suppressed. This supports the "no headlines" principle.
- Item filtering — items can be hidden based on machine capabilities (e.g., GPU hides if no GPU, Home hides if no HA configured).

### 4.2 The top-bar switcher (`PresencePill.tsx`)

A previous AI session built a component in the top bar called `PresencePill` that shows "Halbert @ desk" and has a dropdown to switch between linked machines. The founder never wanted this — node switching belongs in the rail. The revised design says to remove it from the top bar entirely.

The component does contain useful logic that can be reused: it reads `/api/instance/info` (current machine identity) and manages the endpoint switching via `setInstanceEndpoint()` from `apiBase.ts`. The new rail node list will need this same logic.

### 4.3 The linked-machines health grid (`NodeFleetCockpit.tsx`)

A previous AI session built a component that shows a grid of cards, one per linked machine, with live health stats (CPU usage, RAM, temperature, uptime) and buttons to inspect or switch to that machine. It also has a "Pair" button to link a new machine. The internal code name is `NodeFleetCockpit` — a name the founder did not choose and does not recognize.

This component is currently used on the `/bodies` page (another name the founder did not approve). The revised design proposes repurposing this as the "Shared Compute" view at `/compute` — it shows all linked machines and their health, which is exactly what a shared compute overview should show.

### 4.4 The machine-switching mechanism (`apiBase.ts`)

The frontend switches between machines by changing which API endpoint it talks to. `setInstanceEndpoint(url)` saves the endpoint to localStorage and reloads the page. All data fetches then go to the new machine's API. This is the current behavior and the revised design keeps it — clicking a node in the rail reloads the page to point at that machine's API.

A future "no-reload" switch (where the dashboard data changes without a full page reload) is a separate backend workstream and is not part of this design.

### 4.5 The machine identity API (`instance.py`)

Each Halbert process exposes `GET /api/instance/info` which returns:
- `persona_id` — the entity identity (same across machines in singular mode)
- `display_name` — the entity's display name
- `body_name` — the machine's label (e.g., "desk", "home") — **note: this field is called `body_name` in the code, but the user-facing term is "node"**
- `role` — "host" (workstation) or "home" (home automation server)
- `variant` — "sysadmin" or "home" (determines which services run)
- `singular` — true if this machine is in singular entity mode
- `features` — which capabilities this machine has (home automation, GPU, development tools)

### 4.6 The linked-devices API (`devices.py`)

`GET /api/devices` returns the list of paired machines plus the current machine's entity mode. Each device entry includes:
- `node_id` — machine identifier
- `node_name` — display name for the machine
- `endpoint` — the API URL for that machine
- `capabilities` — what that machine can do
- `paired_at`, `last_seen` — timestamps
- `online` — whether the machine is currently reachable

### 4.7 The settings page for managing linked machines (`DevicesTab.tsx`)

Settings has a "Devices" tab (built by a previous AI session) where the user can:
- Toggle between singular and independent entity mode
- Set the machine's name (the `body_name` field)
- See linked machines with their capabilities
- Toggle Wake-on-LAN (allowing the machine to be woken up remotely for compute)
- Remove a linked machine
- Pair a new machine (via a modal that searches the network via mDNS or accepts a manual URL)

This is the **configuration** surface. It stays in Settings. The rail node list is the **navigation** surface — it shows the machines and lets you switch between them, but configuring them happens in Settings.

### 4.8 Security scan results page (`Findings.tsx`)

A page at `/findings` that shows the results of security scans. When Halbert scans its machine, it finds things like "SSH root login is enabled" or "a user account has no password set." Each finding has a severity (critical, high, medium, low) and a status (open, fixed, ignored). The page lets you review and address them.

This is **per-machine** — it's the security state of the specific computer you're looking at. The founder is unsure whether some findings might apply to the HA network rather than the machine, in which case they would be shared. See open question Q1.

### 4.9 Agent approval requests page (`Approvals.tsx`)

A page at `/approvals` that shows pending permission requests from the AI agent. When Halbert wants to do something risky (run a command, edit a config file, install a package), it creates an approval request. The user can approve or reject each one, and see a history of past decisions. There is also a badge in the top bar that shows a count when approvals are pending.

This is **per-machine** — the agent on that specific machine is asking for permission to do something on that machine. See open question Q1.

---

## 5. Open questions for external review

These are the questions that need to be resolved before implementation. They are documented here with full context so an external reviewer can give an informed opinion.

### Q1: Where do Findings and Approvals go in the new rail?

**What they are:**
- **Findings** (`/findings`): Security scan results for the machine — things like "SSH root login is enabled." Each finding has a severity and status.
- **Approvals** (`/approvals`): Pending permission requests from the AI agent — "can I run this command?" / "can I edit this config file?" The user approves or rejects. There's also a top-bar badge showing the pending count.

**Why this is a question:**
The revised design's rail layouts (Sections 3.2-3.4) do not include Findings or Approvals anywhere. The revised design document says only: "Findings & Approvals: Kept off the primary rail or kept as low-key utility items per future review." This leaves them with no entry point in the rail.

**The founder's thinking:**
The founder believes these are per-machine (the security state of this specific computer, the agent on this specific machine asking for permission). But he is unsure whether some findings might be about the HA network rather than the machine — in which case showing them per-computer would be redundant. He does not know enough about what will appear in these pages to design their placement with confidence.

**Options:**
- **(A) Put both in the machine tools section.** They are per-machine — the security scan and agent activity for the currently selected node. This is the simplest approach and matches the founder's instinct.
- **(B) Put them in a separate utility group at the bottom of the rail.** They are not machine tools (not storage, services, terminal) but they are per-machine. A separate group acknowledges this distinction.
- **(C) Keep Approvals as top-bar-only (the badge already exists) and put Findings in machine tools.** The top-bar badge already lets users see pending approvals and click through to the full page. Findings needs a rail entry because there's no top-bar equivalent.
- **(D) Split findings into per-machine and shared.** If a finding is about the machine (SSH config, disk encryption), it's per-machine. If it's about the HA network (a vulnerable camera, an exposed API), it's shared across the entity. This requires the backend to tag findings as machine-level or entity-level, which is more work.

**Founder's lean:** Option A (both in machine tools) is the simplest and most likely correct. Option D is the most correct but requires backend work the founder is not ready to commit to. He wants an external opinion on whether the per-machine vs. shared distinction matters enough to justify the complexity.

### Q2: What happens to the existing `/bodies` page and its health grid component?

**What it is:**
A previous AI session created a page at the URL `/bodies` in the rail under "System." The page shows a grid of cards — one per linked machine — with live health stats (CPU, RAM, temperature, uptime) and buttons to inspect or switch to that machine. It also has a "Pair" button to link a new machine. The internal code name for the component is `NodeFleetCockpit` (a name the founder did not choose).

**Why this is a question:**
The founder does not recognize the name "bodies" and never approved it. The page exists in the code but the founder wants everything called "nodes." The revised design proposes mapping the health grid component to `/compute` (Shared Compute) in the shared section. But the current `/bodies` route and its placement under "System" need to be explicitly dealt with.

**The founder's thinking:**
The founder does not know what `/bodies` is (he was never told in plain language). When explained that it's a grid showing all linked machines with health stats and a pairing button, he recognized it as the shared compute / node relationship view. He wants this functionality but not the name.

**Options:**
- **(A) Delete `/bodies`, move the health grid to `/compute` (Shared Compute).** The route name changes, the component is reused, the old route is removed. The "Pair" button stays in the Shared Compute view and also in Settings → Devices.
- **(B) Keep `/bodies` as a hidden route, redirect to `/compute`.** Backward compatibility for anyone who bookmarked it, but the rail entry is removed.
- **(C) Keep `/bodies` as a separate detailed fleet monitoring page, and have `/compute` be a different, simpler shared compute view.** Two different views: one for health monitoring (the grid), one for compute topology (which machine has a GPU, who's providing compute to whom). This is more work but separates two different concerns.

**Founder's lean:** Option A. The health grid IS the shared compute view. One page, one route, one purpose. No need for two separate views.

### Q3: Should node buttons in the rail show online/offline status?

**What this means:**
When the rail shows `[ Mac Studio ]` and `[ N150 ]`, should there be a colored dot or icon indicating whether each machine is currently reachable? Green = online, gray = offline, amber = degraded.

**Why this is a question:**
The existing health grid component (`NodeFleetCockpit`) already does health probes — it calls each machine's API to check if it responds. But doing this on every rail render could be slow (multiple network requests). The rail needs to be responsive.

**Options:**
- **(A) Yes, show status dots.** Poll machine health on a reasonable interval (e.g., every 15 seconds, same as the health grid). The rail shows a small colored dot next to each node name. This gives the user at-a-glance awareness of which machines are up.
- **(B) No, keep it simple.** The rail is for navigation, not monitoring. Status is visible in the Shared Compute view (`/compute`). Adding polling to the rail adds complexity and potential latency.
- **(C) Yes, but only for remote nodes.** The local machine (the one the browser is connected to) is always "online" from the browser's perspective. Only probe remote nodes. This reduces the number of network requests.

**Founder's lean:** Not yet decided. He wants the external reviewer's opinion on whether status dots in the rail add value or clutter.

### Q4: How does the entity/node block interact with the NavRail's existing header prop?

**What this means:**
The `NavRail` component (the shared design-system component that renders the rail) has a `header` prop — an optional React node rendered at the very top, above the navigation sections. The revised design proposes mounting the entity/node block (the "Halbert" name + node buttons) as this header.

**Why this is a question:**
A header is typically a static element (a brand logo, a back button). The entity/node block is interactive — clicking node buttons switches machines and reloads the page. This should work fine (it's just a React node), but there are design considerations:
- The `NavRail` has a search/filter feature. When the user types in the filter, it filters navigation items. The header is not filtered — it stays visible. This is correct behavior (the node list should always be visible), but the implementation should verify this.
- The `NavRail` is also used by the Settings page (in "tab mode"). The Settings page should NOT show the entity/node block in its rail — Settings has its own tab structure. The header prop should only be set for the main dashboard rail, not the Settings rail.

**This is primarily an implementation question, not a design question.** No external review needed — documented here for the implementation AI.

### Q5: What does the Shared Compute view actually show?

**What this means:**
The revised design adds a "Shared Compute" item in the shared section (when 2+ nodes exist). The proposal is to map the existing health grid component to this view. But "shared compute" could mean different things:

**Option A: Health monitoring (what the existing component does).**
A grid of cards showing each machine's live stats: CPU usage, RAM, temperature, uptime, and which services are active. Plus a "Pair" button to link a new machine. This is a monitoring view — "are my machines healthy?"

**Option B: Compute topology (what the backend was designed for but isn't fully wired).**
A view showing the compute relationship between machines: which machine has a GPU, which machine is providing compute to which, what the fallback chain is (if the Mac Studio is asleep, where does the N150 get its compute?). This is a topology view — "who's providing compute to whom?"

**Option C: Both.**
A combined view with health stats and compute topology. Tabs or sections within the page.

**Why this matters:**
The backend compute routing code (`compute_router.py` in the `federation/` directory) exists but is not fully wired — it was built by a previous AI session but the founder explicitly held it from production use because the proposed behavior would have interrupted the user too often. The health monitoring (Option A) works today. The compute topology (Option B) requires backend work that is on hold.

**Founder's lean:** Option A for now (health monitoring — it works today). Option B/C is a future enhancement when the compute routing backend is fully wired. He wants the external reviewer to confirm this is the right priority.

### Q6: Should the rail show the entity name as a clickable item, or just as a label?

**What this means:**
In the revised design, the top of the rail shows:
```
Halbert
[ Mac Studio ]   [ N150 ]
```

Is "Halbert" (the entity name) just a text label, or is it clickable? If clickable, what does it navigate to?

**Options:**
- **(A) Label only.** "Halbert" is a heading, not a button. Clicking a node button (`[ Mac Studio ]`) is how you navigate. The entity name just tells you which entity you're looking at.
- **(B) Clickable, navigates to a set-level overview.** Clicking "Halbert" shows a summary of the entire entity — all machines, aggregate health, shared resources. This would be a new page.
- **(C) Clickable, navigates to the active node's landing page.** Clicking "Halbert" does the same thing as clicking the active node button — goes to `/`. This is redundant with the node button but provides a larger click target.

**Founder's lean:** Not yet decided. He wants the external reviewer's opinion. Option A is simplest. Option B adds a new page but gives the entity its own landing surface. Option C is redundant but ergonomic.

### Q7: What happens to the "Sharing" page?

**What it is:**
There is currently a `/sharing` page in the rail under "Workloads." It handles file sharing configuration (SMB, NFS, etc.) for the machine.

**Why this is a question:**
The revised design merges "System" and "Workloads" into one machine tools group but does not explicitly mention "Sharing" in its rail layouts (Section 3.2-3.3). The current rail has it. The revised design's examples show Terminal, Storage, Services, Containers, GPU, Network, Backups, Apps, Development — but not Sharing.

**Options:**
- **(A) Keep it in machine tools.** It's a machine-specific configuration (file sharing on this computer). Add it to the machine tools group alongside Network and Storage.
- **(B) Remove it.** If file sharing is not a priority or is handled elsewhere (e.g., in Network settings), remove the standalone page.
- **(C) Fold it into Network.** Sharing is network-adjacent. Make it a tab or section within the Network page rather than a standalone rail item.

**Founder's lean:** Not yet decided. This is a minor question but needs an answer before implementation.

### Q8: Terminology cleanup — how far does it go?

**What this means:**
The founder has insisted on "nodes" not "bodies." The revised design uses "nodes" consistently. But the codebase has "bodies" in several places:
- The `/bodies` route and `Bodies.tsx` page component
- The `body_name` field in the config and API
- `EntityIdentityCard.tsx` in Settings, which labels the field "Body name"
- `PresencePill.tsx`, which shows "Halbert @ desk" (the `body_name`)
- Various test files

**The founder's ruling:** User-facing labels should say "node" or "machine," never "body." Code names (`body_name`, `BeingConfig`, etc.) stay unchanged — they are implementation details the user never sees.

**The question:** How thorough should the cleanup be?
- **(A) Only the rail and the new node list component.** Change the labels in the new rail. Leave existing Settings labels ("Body name") for now — they can be updated in a separate pass.
- **(B) All user-facing labels across the app.** Update Settings, the pairing modal, the devices page, everywhere a user might see the word "body." This is more thorough but touches more files.
- **(C) Everything including renaming the route and page.** Rename `/bodies` to `/nodes` (or remove it per Q2), rename `Bodies.tsx` to `Nodes.tsx`, update all references. Most thorough but largest blast radius.

**Founder's lean:** Option B at minimum. The user should never see "body" anywhere. Option C is ideal if the `/bodies` route is being removed anyway (per Q2).

---

## 5R. External review — resolutions, corrections, and newly discovered issues (2026-09-07)

Reviewer: Claude session (kimi-k3), working from the code, not just the document. Where a resolution differs from the founder's lean it says so and why. Items marked **[ratify]** await the founder's confirmation; everything else is confirmed guidance.

### 5R.1 Resolutions

**Q1 — Findings & Approvals: Option A, confirmed.** Both go in the machine tools group, appended at the end (… Backups, Findings, Approvals). Rationale:

- The per-machine vs shared split (Option D) is **not implementable today**: `routes/findings.py` has no scope/machine/network field in its model — a finding carries severity and status, nothing about what it applies to. Option D is schema work first, placement second. Defer it; when findings gain a scope field, shared findings can move to the shared group without re-litigating this.
- The top-bar approvals badge (polls `/api/approvals` every 5s, `Layout.tsx`) **stays** — it is the ambient signal and works from any route. The rail entries are for navigation; the badge is for attention. Both, not either/or.
- No header means ordering is the only grouping language: attention items at the end of the machine group reads as "things about this machine that want your eye," which matches their nature.

**Q2 — `/bodies`: Option A, confirmed.** Delete the route, move `NodeFleetCockpit` to `/compute`. No redirect, no hidden route — standing founder directive: no back-compat shims. Constraint 6 in Section 8 is amended accordingly ("all existing routes must stay reachable, **except `/bodies`, which is replaced by `/compute`**"). Details:

- The moved view keeps both existing actions: "Inspect" (the fleet-proxy diagnostic drawer) and "Switch Active Context" — switching from the fleet view is a natural path even though the rail is now the primary one.
- The "Pair" CTA (`PeerPairingModal`) stays reachable from `/compute` **and** Settings → Devices.
- One correctness caveat the implementation must not inherit: `routes/fleet.py` `list_fleet_nodes()` still contains `online=False  # TODO(federation-9.9): probe via FleetProxy` in a code path. Before the move is called done, verify the grid's Online/Offline badges are actually produced by live probes; if this TODO shadows the probe, wire it as part of this work.

**Q3 — Status dots in the rail: Option C, recommended [ratify].** Dots on the buttons for nodes other than the one currently serving the API (that node's reachability is self-evident — it served the page). But **derive status from `/api/devices`' `last_seen`, do not live-probe from the rail**:

- The rail block already fetches `/api/devices` to build itself; `last_seen` rides along for free. Fresh (seen within a few minutes) = filled dot; stale = hollow/gray dot. Zero added latency at render.
- Live per-node probing is what `/compute` is for. Do not put N network calls behind every rail render.
- Refresh cadence: 60s, plus on window focus. The 15s probing cadence belongs to the fleet view, not chrome.
- This matches the established indicator idiom (subtle fill/outline status lights used for terminal task state — same visual language, same restraint).

**Q4 — NavRail header prop: verified, no design risk.** Read of `packages/design-system/src/surfaces/NavRail.tsx` confirms:

- `header` renders in its own `hb-navrail__header` block **above** the search input and is never filtered — the filter only operates on `sections`. The node list will always stay visible under filtering. Requirement holds by construction.
- Implementation notes for the builder: pass `header` only on the dashboard rail (`Layout.tsx`); the Settings rail keeps its own usage. Node-button active state tracks the **endpoint** (which machine the page is pointed at), not the route — a user on `/storage` for the Mac Studio still sees `[ Mac Studio ]` highlighted; clicking it navigates to `/` of that same node.

**Q5 — Shared Compute content: Option A, confirmed.** Health grid now, topology later. The compute-topology view (who provides compute to whom, fallback chains) presupposes `federation/compute_router.py`, which is deliberately held from production. Do not design UI for a backend the founder has not released. When the router is un-held, compute topology becomes a section within `/compute`, not a second page.

**Q6 — Is the entity name clickable: Option A, recommended [ratify] — label only.** The redesign's whole second principle is "the node button IS the landing page," adopted because "Dashboard > Dashboard" gave the user two things that went to the same place. A clickable entity name that navigates to `/` recreates exactly that shape: two adjacent clickables, same destination. Keep "Halbert" a label. When Scenario C (multi-entity) eventually lands, revisit: the entity name is the natural selector for *that* entity's node, which is a different job, not a duplicate one.

**Q7 — Sharing page: Option A.** Keep it in machine tools, adjacent to Network. It is per-machine configuration (this computer's SMB/NFS), it has a real page (`Sharing.tsx`) and route already; removing or folding it buys nothing and costs a route. Not worth a UX refinement pass at this stage.

**Q8 — Terminology cleanup: Option B, and Option C collapses into it.** Since Q2 deletes `/bodies` rather than renaming it, there is no route-rename work — B is the whole job. Scope, concretely:

- Every user-visible string: "body/bodies" → "machine" or "node"; Settings' "**Body name**" field → "**Machine name**" (`EntityIdentityCard.tsx`).
- **Also in scope — the document missed this:** `NodeFleetCockpit` speaks of "**satellites**" ("Pair a Satellite" CTA, status copy) and the pairing flow says "peer." The founder's approved vocabulary is *node/machine*; satellites and peers join bodies on the way out of every user-facing string.
- Code identifiers (`body_name`, `BeingConfig`, `peers.json`, route names other than the deleted `/bodies`) unchanged, per constraint 2.

### 5R.2 Corrections to Section 4's codebase claims

These were verified against the code on 2026-09-07. The handoff's implementation AI should work from this table, not Section 4, where they differ.

| Section 4 says | The code says |
|---|---|
| `/api/devices` entries include `online` (4.6) | **They do not.** `DeviceInfo` has `last_seen` but no `online` flag, and it **includes revoked devices** (`include_revoked=True`) — the rail block must filter `revoked === false`. Online-ness is derived (5R.1 Q3). |
| `/api/devices` supports Q6/Scenario C grouping (implied) | **It cannot.** Peer records carry no `persona_id` and no entity display name. See 5R.3 N2. |
| `PresencePill` reads `/api/devices`-adjacent data (4.2) | **It does not.** Its switch list is a hand-maintained `localStorage` key (`halbert:paired-instances`) with a manual "Add" form, entirely disconnected from pairing. The new rail block replaces this with real `/api/devices` data; the localStorage list is retired with the pill (no migration — no legacy support). |
| `NodeFleetCockpit` "does health probes" (Q3 framing) | Partially. `last_seen`-based and telemetry path exist, but see the `federation-9.9` TODO caveat in Q2 — verify before relying on it. |
| GPU/Containers/Development gate on capability (existing logic, 6.1) | Today they all gate on `features.development` (`Layout.tsx` filter). `InstanceInfo.features` already has separate `gpu`, `home`, `development` flags — use the finer-grained ones in the new structure. |

### 5R.3 Newly discovered issues — must be folded into the plan before dispatch

**N1 — `PresencePill` is also the guest-persona surface. Split it, do not delete it.** [ratify]
The document says "remove `PresencePill` completely." But the component merged with the guest-persona work (2026-09-06) carries, in the same dropdown: the **fronting indicator** ("Halbert · as Ada" — *who is speaking right now*), "End guest session," the private-source hand-over checkboxes, and "Be someone else." Removing the whole component orphans the guest persona: a guest session would become invisible in the dashboard, which breaks the persona work's core transparency guarantee (design rule I4: the machine's name never disappears behind a borrowed face). Resolution:

- Node switching, the localStorage paired list, and the "Link Another Device" form leave the top bar and are replaced by the rail block (Settings → Devices already owns pairing).
- The guest-persona indicator **stays in the top bar** as its own small component — visible only while a guest fronts, plus the affordances to end the session and manage hand-overs. Suggested name: `GuestPresenceIndicator`. The "Halbert @ node" identity text moves into the rail block, where entity and node names now live.

**N2 — Scenario C (multiple independent entities) is not buildable from current APIs. Defer it, explicitly.** [ratify]
Rendering "Halbert [Mac Studio][N150] / Halley [Laptop]" requires knowing each node's `persona_id` and its entity's display name. `/api/devices` returns neither (5R.2). Recommendation: ship Scenarios A and B; declare Scenario C out of scope for this workstream. When wanted, the prerequisite is small and backend-side: record `persona_id` + entity `display_name` on the peer record during the pairing/verify handshake, then group on them. Writing that down now prevents an Opus session from discovering it mid-build.

**N3 — Retire the hand-maintained paired-instances list.** Covered under Q8/5R.2: `halbert:paired-instances` goes away with the pill. No import, no migration.

**N4 — Verify authentication after an endpoint switch before building on it.** [verify-first task]
SEC-1 made every backend route require a credential (`installAuthFetch` in `apiBase.ts` attaches the Tauri-injected token to requests against the active base). When the base is switched to a *remote* node, the token being sent is the **local** sidecar's — whether a remote Halbert accepts it is unverified in code inspection and, practically, the existing pill's switch may never have been exercised since SEC-1 landed. Make this the **first implementation task**: switch the endpoint to a second node, confirm the dashboard loads without 401s. If it fails, the token strategy for remote nodes (peer token reuse vs. per-node session) must be decided before the rail switcher ships, because it gates the entire design's core interaction.

**N5 — The route-fallback map must be one module, shared.** Section 6.5's fallback (switch to a node without GPU while on `/gpu` → land on `/`) and the rail's capability filtering must read the **same** route→capability table, or they will drift (the rail hides `/gpu`, the fallback forgets it). New small module, e.g. `lib/routeCapabilities.ts`, consumed by both.

### 5R.4 Suggested implementation order (for the Opus dispatch)

1. **N4 spike** — auth after endpoint switch. Gates everything; smallest task; do it first.
2. **Rail restructure** — `EntityNodeBlock` (from `/api/instance/info` + `/api/devices`, revoked filtered per 5R.2), mounted via NavRail `header`; headline-free groups; `/dashboard` item removed; `routeCapabilities.ts` + fallback; finer-grained feature gates.
3. **N1 pill split** — rail owns nodes; `GuestPresenceIndicator` stays top-bar.
4. **Q2 move** — `/bodies` → `/compute`, probe verification (federation-9.9), satellite→node wording.
5. **Q8 cleanup** — Settings labels and remaining user-facing strings.

### 5R.5 Already built by the review session (2026-09-07) — do NOT rebuild these

The hard part of packet 2 is done, with tests (14 passing, `tsc --noEmit` clean):

- **`src/lib/routeCapabilities.ts`** — the single route → capability table (N5) with `routeAllowed(pathname, features)` and `safeRouteAfterSwitch(pathname, features)`. Layout's new nav filter and the post-switch fallback both consume this. Uses the fine-grained `features.gpu` / `features.home` / `features.development` flags (§5R.2). Note: the role-based blanket hiding of machine tools on `role: 'home'` nodes was **not** carried over — the revised design (§3.1 note) says a home server shows "whatever limited IT tools exist," so gating is capability-only.
- **`src/components/shell/EntityNodeBlock.tsx`** — the rail header: entity label (not clickable, Q6), serving-node button (active by construction — the page's API is its API; click → `/`), peer buttons from `listDevices()` with revoked/devices-without-endpoint filtered, presence dots from `last_seen` (5-min window, Q3), 60s + window-focus refresh, switch via `setInstanceEndpoint()` + reload. Deliberately absent: multi-entity grouping (N2 — needs peer `persona_id`) and guest persona indication (N1 — stays top-bar).

**Packet 2 (rail restructure) starts from these.** What remains for it, mechanically: mount `<EntityNodeBlock />` as the NavRail `header` (dashboard rail only, not Settings); rebuild `navSections` as headline-free shared/machine-tools groups; remove the `/` "Dashboard" item and gate Shared Compute on `peers.length > 0` (devices minus revoked, i.e. node count > 1); apply `routeAllowed()` in the existing item filter in place of the coarse `features.development` collapse; add the post-reload fallback — after instance info loads, `if (!routeAllowed(location.pathname, info.features)) navigate(safeRouteAfterSwitch(...))`.

---

## 6. What needs to be built (summary)

This is a high-level summary for the implementation AI. Detailed implementation should wait until the open questions in Section 5 are resolved.

### 6.1 Rail restructure (primary deliverable)

Restructure the left rail in `Layout.tsx` to:
1. Mount an entity/node block at the top (via NavRail's `header` prop). The block shows the entity name and a button for each linked machine. Clicking a button switches the API endpoint and reloads.
2. Replace the 4 section structure (Overview, Findings & Approvals, System, Workloads) with two groups: shared (Home, Shared Compute) and machine tools (everything else, no section headers).
3. Remove the "Dashboard" nav item — the node button itself navigates to `/`.
4. Gate Shared Compute on node count > 1.
5. Gate Home on HA configured (existing logic).
6. Gate machine tools on machine capabilities (existing logic).

**Data sources:**
- Entity/node list: `GET /api/devices` (linked machines + entity mode) + `GET /api/instance/info` (current machine identity).
- Entity grouping: machines with the same `persona_id` and `singular: true` are in the same group. Independent machines are groups of one.

### 6.2 Remove the top-bar switcher

Remove `PresencePill` from the top bar in `Layout.tsx`. The rail is the single source of truth for node navigation. The top bar keeps: brand, voice button, audio indicator, progress pills, approvals badge, settings gear.

### 6.3 Repurpose the health grid as Shared Compute

Move the health grid component (currently at `/bodies`) to `/compute` in the shared section. Remove the `/bodies` route. Update the empty state text and button labels to use "node" not "body."

### 6.4 Terminology cleanup

Update all user-facing labels from "body" to "node" or "machine." Code names stay unchanged. See Q8 for scope.

### 6.5 Route fallback on node switch

When switching nodes, if the current route is not available on the target machine (e.g., `/gpu` on a machine with no GPU), navigate to `/` instead. This prevents landing on a blank or broken page.

---

## 7. Referenced documents (full design history)

Read these to understand the full context. They are listed in chronological order.

| Document | What it covers |
|----------|----------------|
| `.handoff/HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md` | **Aug 29.** The original "independent nodes" vision. Every machine is a sovereign Halbert. Compute sharing, fleet monitoring, mDNS discovery. This is where the health grid component and the compute routing backend were designed. |
| `.handoff/HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md` | **Aug 31.** The "one Halbert, multiple machines" vision. Singular entity mode, shared memory, machine names, canonical host. The two-mode switch (singular vs independent). **Note: this document uses "bodies" — the founder has since rejected this term in favor of "nodes."** |
| `.handoff/IMPL-PLAN-SINGULAR-ENTITY-2026-08-31.md` | **Aug 31.** Implementation plan for singular entity. 6 phases: config, shared memory, shared conversations, compute fallback, cross-machine tool proxy, Wake-on-LAN. |
| `.handoff/IMPL-PLAN-SINGULAR-ENTITY-TASKS-2026-08-31.md` | **Aug 31, corrected Sep 2.** Task breakdown with status. Documents what landed (code units complete) and what's still open (UI-driven pairing, compute router wiring, tool proxy injection). Read the corrected status block at the top. |
| `.handoff/REVIEW-REQUEST-SHELL-ARCHITECTURE-AND-ENTITY-NAV-2026-09-01.md` | **Sep 1.** The reconciliation document where the rail structure was debated, the top-bar switcher was designed (later rejected), and terminology was established (later partially overridden — "bodies" is now "nodes"). **Section 9 contains founder decisions that were binding at the time but have been partially superseded by this handoff.** |
| `.handoff/HANDOFF-G12-DEVICES-PAGE-DESIGN-REVIEW-2026-08-31.md` | **Aug 31.** Settings → Devices page design. Entity mode toggle, machine cards, pairing flow. The configuration surface for linked machines. |
| `.handoff/HALBERT-UI-REDESIGN-PLAN.md` | **Aug 29.** The original UI redesign plan. Consolidated 14 nav items into 4 domains. The starting point for all rail restructuring. |
| `.handoff/HANDOFF-NODE-LIST-RAIL-REVISED-DESIGN-2026-09-07.md` | **Sep 7.** The external design feedback that the founder approved. This is the basis for the revised rail layout in Section 3 of this handoff. |

---

## 8. Constraints & invariants

1. **No emojis** — use lucide icons (global rule).
2. **No backend renames** — code stays `body_name`, `BeingConfig`, `federation/`, etc. Only UI labels change.
3. **Tauri v2 desktop shell** — the app runs in Tauri, not a plain browser. Some features are Tauri-only.
4. **Each machine is a separate process** — each Halbert instance is a separate daemon with its own port. The frontend switches by changing the API endpoint and reloading.
5. **Entity mode is config-driven** — `canonical_memory_url` set = singular; unset = independent. The UI reflects this, it does not drive it.
6. **All existing routes must stay reachable** — all routes in `App.tsx` must remain navigable (unless explicitly removed, like `/bodies` per Q2).
7. **Page reload on node switch** — the short-term implementation reloads the page to the new API endpoint. A no-reload switch is a future backend workstream.
8. **Node set = shared persona_id + singular mode.** Independent machines are sets of one. The grouping logic is: same `persona_id` + `singular: true` = same set. Different `persona_id` = different set. `singular: false` = set of one.
9. **Single-node installs see zero cluster chrome.** No multi-node headers, no shared compute, no entity grouping complexity. Just the machine and its tools.

---

## 9. Implementation status (2026-09-07, GLM-5.2 session)

### 9.1 What was done in this session (small Opus-level work)

The rail restructure is wired up. All changes pass `tsc --noEmit` and 1017/1017 tests.

**Files modified:**

| File | Change |
|------|--------|
| `src/components/Layout.tsx` | Restructured `navSections` into two headline-free groups (shared: Home, Shared Compute; machine tools: everything else). Removed the `/` "Dashboard" nav item — the EntityNodeBlock node button IS the landing page. Replaced `/bodies` with `/compute`. Mounted `<EntityNodeBlock />` as the NavRail `header`. Replaced the coarse `features.development` collapse and `role === 'home'` blanket-hide with `routeAllowed()` from the shared route-capability table. Added post-reload route fallback: after instance info loads, if the current route isn't supported on this node, navigate to `/`. |
| `src/App.tsx` | Changed `/bodies` route to `/compute`, updated import from `Bodies` to `Compute`. |
| `src/pages/Compute.tsx` | New page (replaces `Bodies.tsx`). Wraps `NodeFleetCockpit` with updated heading "Shared Compute" and terminology ("nodes" not "bodies"). |
| `src/pages/Bodies.tsx` | Deleted. |
| `src/pages/Bodies.test.tsx` | Deleted. |
| `src/pages/Compute.test.tsx` | New test (replaces `Bodies.test.tsx`). Checks heading, terminology (no "body/bodies/satellite"), and "Link a node" CTA. |
| `src/components/Layout.navCoverage.test.tsx` | Added `/` to `ROUTES_WITHOUT_RAIL_ENTRY` (the node button is its entry point, not a rail item). |
| `src/components/fleet/NodeFleetCockpit.tsx` | Updated user-facing strings: "No other bodies yet" → "No other nodes yet", "Link a body" → "Link a node", comment "One card per body" → "One card per node". |
| `src/components/fleet/NodeFleetCockpit.test.tsx` | Updated test expectations to match new terminology. |

**Files already built by the review session (NOT rebuilt — reused as-is):**

| File | What it does |
|------|-------------|
| `src/lib/routeCapabilities.ts` | Single route → capability table. `routeAllowed(pathname, features)` and `safeRouteAfterSwitch(pathname, features)`. Uses fine-grained `features.gpu` / `features.home` / `features.development`. |
| `src/components/shell/EntityNodeBlock.tsx` | Entity label (not clickable) + node buttons. Reads `/api/instance/info` + `/api/devices`. Filters revoked devices. Presence dots from `last_seen` (5-min window). 60s + window-focus refresh. Switches via `setInstanceEndpoint()` + reload. |

### 9.2 What remains — Sonnet work (hand to another AI)

**STATUS 2026-09-07: DONE.** All four items below were executed (GLM-5.3 sonnet-level session) on the same working tree; frontend `tsc --noEmit` clean, **1020/1020 frontend tests**, 481 device/fleet/peer backend tests pass. What changed beyond the literal task list:

- Terminology cleanup went to Q8-Option-B full scope: `EntityIdentityCard.tsx`, `DevicesTab.tsx`, `PeerPairingModal.tsx` ("Peer Node ID" → "Node ID", title → "Link a Node"), `NodeFleetCockpit` (header "Fleet Cockpit" → "Linked Nodes", "Pair" → "Link a node", drawer copy), **plus two surfaces the task list did not name**: `PresencePill`'s mode string ("one Halbert, many bodies" → "many machines" — string-only fix; the split itself stays Task A) and `ComputePeerCard.tsx` (the AI tab's "compute peer" card, now "compute node" — every user-facing "peer" string). The repo-wide vocabulary guard (`vocabulary.guard.test.ts`) and `EntityIdentityCard.vocabulary.test.tsx` now also assert the machine noun.
- The Shared Compute gate (item 2) fetches `/api/devices` independently in `Layout.tsx` (revoked + endpoint-less excluded, same list `EntityNodeBlock` renders); `/compute` hides at 0 linked nodes. New test: `Layout.computeGate.test.tsx`.
- **federation-9.9 verification (item 4) found the probe unbuildable, and wired the honest alternative instead:** `routes/fleet.py` hardcoded `online=False`, but a live probe needs an outbound peer credential — `get_fleet_proxy()` returns `None` by design because the federation-9.4 token-custody design (M14: hashes only, raw tokens never persisted) has not landed, and peer tokens only pass `require_peer_auth` routes, not `require_owner` dashboard routes. Rather than hardcode a lie or silently make the custody decision, `online` is now **derived from `last_seen` freshness** (5-minute window, maintained by `peer_middleware` on every authenticated request) — the same derived-presence idiom §5R.1 Q3 ratified for the rail. `[ratify]` for the founder: the grid's Online badge now means "authenticated contact within 5 minutes," and a real live probe lands with federation-9.4/9.9. Backend test: `tests/federation/test_fleet_online_derivation.py`.

These are mechanical tasks that don't require deep architectural understanding:

1. **Terminology cleanup in Settings (Q8, partial).** Update user-facing strings in `EntityIdentityCard.tsx` ("Body name" → "Machine name"), `DevicesTab.tsx`, and `PeerPairingModal.tsx` (any "satellite"/"peer" in user-facing text → "node"/"machine"). Code identifiers stay unchanged. The vocabulary guard test (`vocabulary.guard.test.ts`) may need updating if it checks for specific strings.

2. **Gate Shared Compute on node count > 1.** Currently `/compute` is always in the rail. The revised design says it should only appear when 2+ nodes are linked. This requires checking `peers.length > 0` (from `/api/devices`, filtering revoked) in the nav filter. The `EntityNodeBlock` already fetches this data — either lift it to a shared context or have Layout fetch it independently.

3. **Update `NodeFleetCockpit` header text.** The component still says "Fleet Cockpit" in its internal header (line 143). Change to "Linked Nodes" or similar. Also update the "Pair" button text if needed.

4. **Verify the `federation-9.9` TODO (Q2 caveat).** `routes/fleet.py` `list_fleet_nodes()` may have `online=False` hardcoded with a TODO. Verify the grid's Online/Offline badges are produced by live probes, not stubbed. If stubbed, wire the probe.

### 9.3 What remains — large Opus work (hand to a 3rd AI)

These require deep understanding of existing systems or multi-component changes:

**Task A: Split PresencePill into GuestPresenceIndicator (N1)**

**What:** `PresencePill.tsx` currently serves two purposes: (1) node switching (now redundant — the rail's `EntityNodeBlock` handles this) and (2) guest persona indication (fronting sessions, private-source hand-over, "Be someone else"). The node-switching half should be removed. The guest-persona half should become its own small component (`GuestPresenceIndicator`) that stays in the top bar, visible only while a guest fronts.

**Why it's Opus:** The component is 540 lines and interleaves node switching with guest persona logic. The guest persona system includes fronting session polling (every 10s), private-source catalog fetching, hand-over assignment/release, available-persona loading, and the "End guest session" flow. Splitting it without breaking the guest persona's transparency guarantee (design rule I4: the machine's name never disappears behind a borrowed face) requires understanding the full guest persona system.

**Files involved:**
- `src/components/shell/PresencePill.tsx` (540 lines — the component to split)
- `src/components/Layout.tsx` (line 539 — where PresencePill is mounted; will become GuestPresenceIndicator)
- `src/components/shell/PresencePill.test.tsx` (tests to update)
- `src/lib/apiBase.ts` (the `setInstanceEndpoint` / `getInstanceEndpoint` / localStorage paired-instances list that the node-switching half uses — to be retired, N3)

**Key constraints:**
- The `halbert:paired-instances` localStorage key (the hand-maintained paired list) goes away with the pill's node-switching half. No migration — the rail's `EntityNodeBlock` uses real `/api/devices` data.
- The `InstanceInfo` type is exported from `PresencePill.tsx` and imported by `Layout.tsx`. After the split, this type should move to a shared location (e.g., `lib/instanceInfo.ts`) or stay in the guest component if Layout no longer needs it directly.
- The vocabulary guard test checks that `PresencePill.tsx` contains "Independent Node" — after the split, this check needs to point at whatever component carries the entity mode label.

**Task B: Auth verification spike (N4)**

**What:** SEC-1 made every backend route require a credential (`X-Halbert-Token` header, injected by the Tauri shell). When the frontend switches to a remote node's API endpoint, the token being sent is the local sidecar's. Whether a remote Halbert accepts it is unverified.

**Why it's Opus:** This gates the entire design's core interaction (clicking a node in the rail). If auth fails on remote nodes, the rail switcher doesn't work and a token strategy decision is needed (peer token reuse vs. per-node session). Requires two running Halbert instances to test.

**How to verify:**
1. Start two Halbert instances on different ports (e.g., 8000 and 8001).
2. From the frontend connected to instance A, use `setInstanceEndpoint('http://localhost:8001')` to switch to instance B.
3. Check whether the dashboard loads without 401s.
4. If it fails, investigate the token strategy: the peer bearer token (from `peers_config.py`) may need to be used instead of the Tauri-injected token for remote nodes.

**Files involved:**
- `src/lib/apiBase.ts` (`installAuthFetch`, `apiToken`, `setInstanceEndpoint`)
- `halbert_core/halbert_core/federation/peer_middleware.py` (peer bearer auth on the backend)
- `halbert_core/halbert_core/dashboard/auth.py` (SEC-1 auth middleware)

**Task C: Backend support for Scenario C — multiple independent entities (N2)**

**What:** The rail currently shows all linked nodes in one flat block (EntityNodeBlock). Scenario C (multiple independent entities, e.g., "Halbert [Mac Studio][N150]" and "Halley [Laptop]") requires grouping nodes by entity. This needs `persona_id` and entity `display_name` on each peer record.

**Why it's Opus:** Backend change to the pairing handshake. The peer record in `peers_config.py` and the `/api/devices` response need to carry `persona_id` and `display_name`. The `EntityNodeBlock` component already has a documented place for this grouping (its docstring says "Multi-ENTITY grouping is deliberately not here").

**Files involved:**
- `halbert_core/halbert_core/federation/peers_config.py` (add `persona_id`, `display_name` to peer records)
- `halbert_core/halbert_core/dashboard/routes/peers.py` (return the new fields in the pairing/verify response)
- `halbert_core/halbert_core/dashboard/routes/devices.py` (include the new fields in `/api/devices` response)
- `src/lib/peerApi.ts` (update `DeviceInfo` type)
- `src/components/shell/EntityNodeBlock.tsx` (group peers by `persona_id`)

**Priority:** Defer until Scenarios A and B are validated in production. The single-entity case works today.
