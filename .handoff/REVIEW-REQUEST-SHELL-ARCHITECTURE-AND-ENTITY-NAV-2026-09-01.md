# Review Request: Shell Architecture & Entity-Aware Navigation Redesign

**To:** Design review AI (Fable-level scrutiny)
**From:** Eric / GLM-5.2 session
**Date:** 2026-09-01
**Status:** Design thinking stage — no implementation yet. Seeking design feedback before any code changes.
**Review level:** Fable (highest scrutiny — challenge every assumption, including the ones the founder states as requirements)

---

## How to use this document

This is a **living review document**. The founder has written the problem analysis and design questions in Sections 1-7. The reviewer should:

1. Read Sections 1-7 to understand the problem space and the founder's thinking.
2. Write feedback, counter-arguments, alternative designs, and agreements **directly in Section 8 (Reviewer Feedback)** — do not edit Sections 1-7.
3. If a design question in Section 7 needs a deeper dive, add a sub-section under Section 8 with your analysis.
4. Be adversarial. The founder wants to be wrong about things before code is written, not after.

---

## 1. The trigger: a label rename that exposed a structural problem

The immediate trigger was renaming the left-rail section "Being & Ambient Home." That label was written by a previous AI session implementing TASK-PACKET-02 Task 2.3, which consolidated a 14-item sidebar into 3 "primary domains." The rename attempt surfaced that the label is incoherent:

- **"Dashboard" > "Dashboard"** — the section contains a "Dashboard" item, and the mode switch tab for browsing mode is also labeled "Dashboard." A user sees "Dashboard" twice.
- **"Home"** suggests "home page" but the Dashboard already is the home page. Also, "Home" is the HA spatial view — a different meaning of "home."
- **"Ambient Home"** — the founder rejects this as "weird."
- **"Spaces"** — close but inaccurate; these aren't spaces in the spatial-computing sense.
- **"Nodes"** — makes sense for the multi-device reality, but implies the user needs to toggle between nodes, which is currently a separate concern (the top-bar InstanceSwitch).

The label problem is a symptom. The real problem is that the **shell architecture** (the three surfaces: engaged, browsing, voice) and the **entity model** (singular vs independent, one Halbert vs many) and the **navigation model** (left rail, top bar, mode switch) were designed independently by different sessions and have never been reconciled into a single coherent picture.

---

## 2. Current shell architecture (as-built)

### 2.1 Three shell modes (`ShellModeContext.tsx`)

| Mode | What's on screen | Entry point |
|------|-----------------|-------------|
| **engaged** | `HostShell`: conversation spine (AgentChat) + context stage (vitals, terminal dock). The "you and the machine" surface. | Default on load. ModeSwitch tab labeled with the machine's name. Cmd/Ctrl+B. |
| **browsing** | Left NavRail + page content (Services, Storage, Findings, etc.). The sysadmin hub. | ModeSwitch tab labeled "Dashboard." Cmd/Ctrl+B. |
| **voice** | Full-bleed `/voice` route. Dark canvas, ear-first. Parks whatever surface was on. | `/voice` deep link or top-bar AudioLines button. |

### 2.2 The top bar (always present except on /voice and /voice-hud)

Left to right:
1. HalbertMark + "Halbert" text
2. **ModeSwitch** — two-tab toggle: [machine name] | Dashboard
3. **Voice button** (AudioLines icon) — enters voice mode
4. **VoiceHudSummonButton** — summons the floating companion pill (Tauri only)
5. **InstanceSwitch** — dropdown showing current instance name + role icon, with paired instances listed below. Switching reloads the page with a new API endpoint.
6. **AcousticAuraIndicator** — audio perception status
7. (flex spacer)
8. ProgressPills (scanning, indexing) — conditional
9. Version string
10. **Settings gear** — navigates to `/settings` (overtakes the shell)

### 2.3 The left NavRail (browsing mode only)

Currently 4 sections (after the "More" fix applied in this session):
1. Being & Ambient Home: Dashboard, Home
2. Intelligence & Findings: Findings
3. Host Controls: Services, Storage, Backups, Terminal
4. More: Apps, Network, Sharing, Containers, GPU, Development, Approvals

The NavRail is the shared `@halbert/design-system` component, also used by the Settings page (in tabMode).

### 2.4 The Settings page (overtakes the shell)

When on `/settings`, the dashboard NavRail is hidden and Settings renders its own NavRail with 5 sections:
1. Personality & Identity: Identity & Voice, Devices
2. Intelligence: Models & Providers, Knowledge
3. System & Security: Tool Permissions, Alert Rules, Trust Boundary, Vision, Audio & Voice
4. General: System Info, About
5. Developer: Debug

---

## 3. Current entity & identity model (as-built)

### 3.1 Instance identity (`instance.py` → `/api/instance/info`)

Each Halbert process reports:
- `persona_id` — slug (env: `HALBERT_PERSONA_ID`, default "halbert")
- `scene_context` — free text (env: `HALBERT_SCENE_CONTEXT`)
- `role` — "host" or "home" (derived from variant, not persona_id)
- `variant` — "sysadmin" or "home" (from being.yml or `HALBERT_VARIANT` env)
- `display_name` — capitalized persona_id or env override
- `features` — {home, gpu, development, wyoming_port}
- `data_dir`, `config_dir`

### 3.2 Singular entity mode (`being_config.py`, `cognition_wiring.py`)

Two modes, both first-class:
- **Singular Entity** (default for paired devices): `canonical_memory_url` is set → this node proxies memory and threads to the canonical host. One persona_id across all bodies. "One Halbert, many bodies."
- **Independent Node**: `canonical_memory_url` is unset → local memory and threads. Each node is its own entity.

Key fields in `being.yml`:
- `body_name` — physical location label ("desk", "home", "living room"). In singular mode, the prompt builder includes it so the entity knows where it is.
- `canonical_memory_url` / `canonical_thread_url` — the always-on host's endpoints
- `peer_token` — bearer token for canonical host auth

### 3.3 InstanceSwitch (the top-bar dropdown)

This is the component the founder wants to reconsider. Currently:
- Shows the current instance's display_name + role icon (Monitor for host, Home for home)
- Lists paired instances from localStorage (`halbert:paired-instances`)
- Switching calls `setInstanceEndpoint()` → reloads the page → all fetches now target the new endpoint
- "Pair / Connect Another Instance..." opens an add form (label, endpoint URL, role)

**Problem:** This is a "which API am I talking to" switcher, not an "which body of Halbert am I interacting with" switcher. In singular entity mode, switching instances changes the API endpoint but the entity is the same — the user shouldn't need to "switch" anything, they should just be talking to Halbert, and Halbert knows which body it's on. In independent mode, switching instances IS switching entities, but the UI doesn't communicate that distinction.

---

## 4. The founder's design vision (in their words, lightly edited)

> The chat/voice is the right bar and at any point we can hide the left bar, the right bar, or the center dashboard. The chat/voice can always sit there unless in fullscreen or kiosk mode. The left menu and settings remains the same.

> We can have unique Halberts on the same network and some are the HA server, some are primary compute, and some are additional compute. They could be one unified identity or each with an identity. We need to group if they identify as the same agent.

> Nodes sort of makes sense [for the rail label] but we'd need to be able to toggle between each, and honestly this makes more sense than the name in the top panel with the toggle. We should remove that [InstanceSwitch] and find another method to invoke the chat.

### 4.1 The core proposal

1. **Chat/voice becomes a persistent right panel** — always present (except fullscreen/kiosk), not a mode you switch into. The "engaged" mode as a separate surface goes away; the conversation is always there.
2. **The left rail and center content stay as-is** — browsing pages render in the center, the rail stays on the left.
3. **Panels are independently hideable** — left rail, center dashboard, right chat. The user controls what's visible.
4. **InstanceSwitch is removed from the top bar** — instance/body switching moves into the rail (or elsewhere), not the top bar.
5. **The mode switch (engaged/browsing) is reconsidered** — if chat is always present as a right panel, the engaged/browsing distinction may collapse into "what's in the center."

---

## 5. The unique problems to solve

These are the hard design problems that the reviewer should focus on. They are not independent — a decision on one constrains the others.

### 5.1 One entity, many bodies — how does the user switch between them?

In singular entity mode, all paired devices are the same Halbert. The user at the Mac Studio is talking to the same entity as the user at the N150 in the kitchen. But they're interacting through different bodies with different capabilities (the Mac has a terminal and GPU; the N150 has HA and voice).

**Question:** When the user is at the Mac Studio, do they need to "switch" to the N150 body at all? Or does the entity simply know "you're at the desk body, here's what you can do here"? If the N150 has a camera the Mac doesn't, does the entity say "I can see the front door through my kitchen body" or does the user need to explicitly switch?

**Current behavior:** The InstanceSwitch reloads the page to point at a different API endpoint. This is a hard switch — you're now talking to the N150's Halbert process, not the Mac's. In singular mode, this shouldn't be necessary for identity (it's the same entity), but it IS necessary for capability (the N150's tools are different).

### 5.2 Many entities on the same network — how are they grouped?

In independent mode, each device is its own entity with its own persona_id, memory, and threads. The user might have "Halbert" on the Mac Studio and "Halley" on the N150. These share compute (peer offload) but not identity.

**Question:** How does the UI distinguish "switch to another body of the same entity" from "switch to a different entity entirely"? The current InstanceSwitch treats them identically — it's just an endpoint switch.

**Sub-question:** If entities are grouped, what does the group look like in the UI? A section in the rail? A different visual treatment? Should independent entities even appear in the same UI, or should they require a separate browser tab / window?

### 5.3 The role of the top bar

The top bar currently carries: brand, mode switch, voice entry, instance switch, audio indicator, progress pills, version, settings gear. The founder wants to remove the instance switch and reconsider the mode switch.

**Question:** If chat is always present as a right panel, what does the mode switch become? Is there still a distinction between "engaged" (conversation-focused) and "browsing" (dashboard-focused)? Or does it collapse into "the center shows whatever page you navigated to, and the chat is always on the right"?

**Question:** What lives in the top bar after the instance switch is removed? Brand, voice entry, audio indicator, progress, settings — is that enough? Too much? Does the body/entity identity move here (e.g., "Halbert @ desk")?

### 5.4 The left rail: what are the sections?

If "Nodes" is the right label for the section that contains Dashboard + Home, then the rail is grouping by... what? The current sections are domain-based (Being & Ambient Home, Intelligence & Findings, Host Controls, More). If we add node switching to the rail, is "Nodes" a section that lists each body as an item? Or is it a header above the rail that shows which body you're on?

**Question:** Can the rail serve both navigation (which page) and identity (which body) without becoming confusing? Or should identity live in a different surface (the top bar, a dedicated switcher, the chat header)?

### 5.5 Three-panel layout: hide/show semantics

The founder proposes three independently hideable panels: left rail, center dashboard, right chat. This is a common IDE pattern (VS Code, Eclipse) but uncommon for a dashboard / assistant app.

**Questions:**
- What are the default panel states? (All visible? Chat hidden until invoked? Rail hidden on small screens?)
- How does the user toggle panel visibility? (Keyboard shortcuts? Buttons in the top bar? A view menu?)
- What happens on narrow screens (mobile, kiosk)? Do panels stack, or does only one show at a time?
- In fullscreen/kiosk mode, what's visible? (Just chat for voice kiosk? Just the dashboard for a wall display?)
- Does the voice mode (full-bleed `/voice`) still exist as a separate route, or does it become "chat panel expanded to fullscreen"?

### 5.6 The "More" section and page discoverability

This session added a "More" section to the rail with 7 previously-hidden pages. But the deeper question is: should all pages be in the rail, or should some live elsewhere?

**Question:** Are Apps, Network, Sharing, Containers, GPU, Development, and Approvals really "More" (secondary) pages, or should they be reorganized into the primary sections? For example, should GPU be under "Host Controls" since it's a hardware resource? Should Approvals be a top-bar badge (as the original task packet suggested) rather than a rail item?

### 5.7 Settings as shell-overtake vs. settings as panel

Currently Settings overtakes the entire shell — no dashboard rail, no chat, just Settings with its own rail. If chat becomes a persistent right panel, should Settings still overtake, or should it render in the center panel with the chat still visible on the right?

**Question:** Is there ever a reason to chat with Halbert while configuring settings? (e.g., "Help me set up my HA token" → Halbert guides you through the Settings → Integrations tab) If yes, Settings should not overtake the chat panel.

---

## 6. Constraints & invariants

These are hard constraints the design must respect:

1. **No emojis** — use icon fonts or graphic design (global rule).
2. **Subtractive contract** — the design system (`@halbert/design-system`) uses plain CSS on token variables, no Tailwind in library source.
3. **Tauri v2 desktop shell** — the app runs in Tauri, not a plain browser. Some features (VoiceHudSummonButton, screenshot capture) are Tauri-only.
4. **Multi-instance via separate processes** — no in-process multiplexing. Each Halbert instance is a separate daemon with its own port and data directory. The frontend switches by changing the API endpoint.
5. **Singular entity mode is config-driven** — `canonical_memory_url` set = singular; unset = independent. The UI should reflect this, not drive it.
6. **Variant is a preset, not a hard gate** (aspirational) — the singular-entity handoff (Section 4) argues that capability should emerge from hardware, not variant labels. The current code still hard-gates on variant. This is a known gap.
7. **Existing routes must stay reachable** — all 20 routes in App.tsx must remain navigable. The "More" section is a stopgap; the real design may reorganize them.
8. **Keyboard navigation** — Cmd/Ctrl+B currently toggles engaged/browsing. Any new panel-hide shortcuts should be equally ergonomic and documented.
9. **Voice mode is a route** — `/voice` is a deep-linkable full-bleed surface. This is a product feature (kiosk, bedroom display). The redesign must preserve a fullscreen voice experience.

---

## 7. Design questions for the reviewer

These are the specific questions the founder wants answered. The reviewer should answer each, with reasoning, and propose a concrete design if they disagree with the founder's instinct.

### Q1: Shell architecture — three-panel vs. mode-switch

**Founder's instinct:** Three independently hideable panels (left rail, center dashboard, right chat), replacing the engaged/browsing mode switch.

**Question:** Is the three-panel model better than the current mode-switch model? Consider:
- Cognitive load (mode switch is one click; panel management is three toggles)
- Screen real estate (three panels on a 13" laptop is cramped)
- The "engaged" mode's thesis (the machine IS the primary surface, the dashboard is secondary)
- Voice mode (does it become "right panel fullscreen" or stay a separate route?)

### Q2: Entity/body switching — where does it live?

**Founder's instinct:** Remove InstanceSwitch from the top bar; move body switching into the rail or elsewhere.

**Question:** Where should body/entity switching live? Options:
- A section in the left rail (e.g., "Bodies" section listing each body)
- The chat panel header (e.g., "Halbert @ desk" with a dropdown)
- A dedicated switcher in the top bar (redesigned, not the current InstanceSwitch)
- The Settings → Devices page (already exists, but requires navigating to settings)

Consider: in singular mode, do you "switch bodies" at all, or does the entity just know where it is? In independent mode, switching bodies IS switching entities — is that a bigger deal that deserves more ceremony?

### Q3: Left rail section labels — what replaces "Being & Ambient Home"?

**Question:** What should the rail sections be called, and what should they contain? Propose a complete rail structure. Consider:
- The section containing Dashboard + Home (currently "Being & Ambient Home")
- Whether "Nodes" or "Bodies" is the right concept
- Whether the section structure should be domain-based (current) or capability-based or something else
- Whether Settings should be a rail item or stay as a top-bar gear

### Q4: Top bar — what stays after InstanceSwitch is removed?

**Question:** What lives in the top bar in the new design? Consider:
- Brand identity (HalbertMark + name)
- Body/entity identity (where does "Halbert @ desk" go?)
- Voice entry (button? or is it the right panel?)
- Progress indicators (scanning, indexing)
- Settings gear
- Panel toggle controls (if three-panel model)

### Q5: Grouping entities on the same network

**Question:** How should the UI represent the relationship between multiple Halbert instances on the same network? Consider:
- Singular entity (one Halbert, many bodies) — bodies are grouped under one identity
- Independent entities (several Halberts) — each is its own thing, but they may share compute
- Mixed (some bodies are singular, some are independent) — is this possible? Should it be?

Should the UI show a "fleet" view (all instances, grouped by entity)? Should independent entities appear in the same window at all, or require separate windows/tabs?

### Q6: Settings — overtake or center panel?

**Question:** Should Settings continue to overtake the entire shell, or should it render in the center panel with chat still visible on the right? Consider:
- The value of chatting with Halbert while configuring settings
- The complexity of the Settings page (it has its own NavRail — does that work in a center panel?)
- The current "Settings is the fourth domain" framing

### Q7: Voice mode — route or panel state?

**Question:** If chat becomes a persistent right panel, does `/voice` (full-bleed) still need to be a separate route? Or does voice become "right panel expanded to fullscreen"? Consider:
- The kiosk/bedroom display use case (needs fullscreen, no other panels)
- The deep-linkable URL requirement (`/voice` must be shareable)
- The "park and restore" semantics (voice parks the current surface; leaving restores it)

---

## 8. Reviewer Feedback

### 8.1 Executive Summary & Architectural Reconciliation

The trigger for this review was an awkward rail label ("Being & Ambient Home"), but the underlying realization is profound: **Halbert's interface needs a unified spatial model that scales from deep machine conversation to rapid sysadmin multitasking without mode-switching friction.**

Following the **Semantic Audit** (`HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md`), we also establish an **Apple-style design lexicon**: eliminate eerie mystical anthropomorphism (*"The Being"*, *"Sovereign Host"*, *"Soul Migration"*, *"Somatosensory Loop"*) and heavy enterprise jargon (*"Federated Multi-Node Compute"*), replacing them with dignified, clean, human systems language (*"Identity & Voice"*, *"Host Canvas"*, *"Compute Mesh"*, *"Linked Devices"*, *"System Health"*).

#### The Unified Solution: "1 Left Navigation Panel + 2 Freely Togglable Main Panels"
Instead of treating "Engaged" and "Browsing" as mutually exclusive modal surfaces, the application shell is structured as **One Persistent Left Navigation Rail** and **Two Main Work Panels** that can be toggled independently:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR: [Logo] Halbert   [ @ desk • Unified ]      [Cmd+K]    (Scan 100%)  [🎙️] [⚙️]  │
├──────────────┬───────────────────────────────┬─────────────────────────────────────────┤
│ LEFT RAIL    │ MAIN PANEL 1: PAGE / WORKLOAD │ MAIN PANEL 2: HOST CANVAS / ASSISTANT   │
│ (Consistent  │ (Dashboard, Storage, Services,│ (Agent Conversation, Live Terminals,    │
│  ~220px)     │  Findings, Settings)          │  Context Stage & Vitals)                │
│              │                               │                                         │
│ [Overview]   │ ◄─── TOGGLED FREELY ───►      │ ◄─── TOGGLED FREELY ───►                │
│ [Findings]   │ (Cmd+D / Top Bar Toggle)      │ (Cmd+J / Top Bar Toggle)                │
│ [Storage]    │                               │                                         │
└──────────────┴───────────────────────────────┴─────────────────────────────────────────┘
```

This model provides effortless flexibility across 4 clean layout states:
1. **Host Focus (`[Left Rail] + [Right Host Panel]` — Center Hidden):**
   The center dashboard collapses completely. Main Panel 2 takes the remaining width ($\ge$1000px), automatically expanding into the full **Host Canvas**: left-hand conversation spine with full-width `InlineTerminals`, right-hand `ContextStage` (host vitals + PTY accordion dock). The Left Rail remains immediately accessible for navigation.
2. **Dashboard Focus (`[Left Rail] + [Center Page]` — Right Hidden):**
   Main Panel 2 collapses. Main Panel 1 takes full width ($\approx$1200px max), giving maximum breathing room for dense data tables, ZFS pool topologies, and security findings.
3. **Side-by-Side Co-pilot (`[Left Rail] + [Center Page] + [Right Assistant]` — Both Open):**
   Both main panels share the viewport (e.g. 60% Center / 40% Right or 50/50). Main Panel 2 renders in **Assistant Companion** posture (conversation + quick action suggestions + auto-injected page context via `askHost`), allowing the user to inspect and modify live system configurations simultaneously.
4. **Immersive Voice (`/voice` — Full-Bleed Route):**
   For wall-mounted kiosks, bedroom displays, or hands-free kitchen appliances, all desktop panels park and the screen becomes an ear-first dark canvas.

---

### 8.2 Semantic Audit Alignment (Apple-Style Lexicon)

Per `HANDOFF-SEMANTIC-AUDIT-AND-TERMINOLOGY-REVIEW-2026-09-01.md`, we formally purge mystical jargon and alias sprawl from the shell and navigation architecture:

| Legacy / Conflicted Term | Canonical Product Term | UI & Shell Usage | Rationale |
|---|---|---|---|
| **"The Being"** | **Identity & Voice** (or **Self**) | `Settings → Identity & Voice`<br>`config/identity.yml` | Drops creepy pseudo-religious anthropomorphism. Dignified, direct, human. |
| **"Being & Ambient Home"** | **Overview & Space** | Left Rail Section 1 | Replaces incoherent category error with clear overview + spatial home automation. |
| **"Sovereign Host Shell"** | **Host Canvas** | Top Bar / Shell State | Replaces pompous political/crypto metaphor with tactile systems noun. |
| **"Engaged Mode" vs "Browsing Mode"** | **Host Canvas** vs **Dashboard** | Main Panel 1 & 2 toggles | Mode switch becomes direct panel visibility controls (`Cmd+D`, `Cmd+J`). |
| **"Federated Multi-Node Compute"** | **Compute Mesh** / **Linked Devices** | `Settings → Devices`<br>`lib/meshApi.ts` | Immediate intuition of peer-to-peer resilience without cloud lock-in. |
| **"Singular Entity Mode"** | **Unified Presence** | *"One Halbert across devices"* badge | Simple, memorable product language. |
| **"Somatosensory Loop"** | **System Health & Maintenance** | Background telemetry & scheduler | Honest systems terminology for scans, health checks, and logs. |
| **"Acoustic Aura"** | **Audio Engine / Mic Status** | Top-bar hearing indicator | Direct, functional description. |

---

### 8.3 Systematic Answers to Founder Design Questions (Q1 – Q7)

---

#### Q1: Shell Architecture — Two Main Panels Freely Togglable

**Founder's instinct:** Three independently hideable panels, center dashboard collapsable too so user can have just left rail and right host panel.

**Reviewer Verdict: FULL AGREEMENT WITH REFINED ADAPTIVE BEHAVIOR.**

1. **The 3-Panel Topology:**
   - **Left Panel:** Navigation Rail (defaults to natural consistent width, ~220px; icon-only collapsible ~64px).
   - **Main Panel 1 (Center):** Active Page Content (`/overview`, `/storage`, `/findings`, `/services`, etc.).
   - **Main Panel 2 (Right):** Host Canvas / Agent Assistant.
2. **Adaptive Layout Mechanics:**
   - **When Center is HIDDEN and Right is OPEN (`[Left] + [Right]`):**
     Main Panel 2 has plenty of width ($\ge$1000px on desktop). It renders the **Full Host Canvas**:
     - Conversation Spine with full-width live PTY terminals (`InlineTerminals`).
     - `ContextStage` side-by-side (Host Vitals + PTY Accordion Dock).
     - The user experiences the full Sovereign Host embodiment without losing left-rail navigation!
   - **When Center is OPEN and Right is HIDDEN (`[Left] + [Center]`):**
     Main Panel 1 expands to fill the stage. Perfect for deep sysadmin work.
   - **When BOTH Main Panels are OPEN (`[Left] + [Center] + [Right]`):**
     - Main Panel 1 renders the active page.
     - Main Panel 2 automatically transitions into **Companion Posture** (compact conversation stream, docked PTY tiles, auto-injected page context).
3. **Keyboard Shortcuts & Ergonomics:**
   - `Cmd+D` (or `⌘1`): Toggle Center Dashboard / Page Panel.
   - `Cmd+J` (or `⌘2`): Toggle Right Host / Assistant Panel.
   - `Cmd+B`: Quick toggle between primary focus states (Host Focus $\leftrightarrow$ Dashboard Focus).
   - `Cmd+\`: Toggle Left Rail collapse (slim icon mode $\leftrightarrow$ full text mode).

---

#### Q2: Entity & Body Switching — Where Does It Live?

**Founder's instinct:** Remove `InstanceSwitch` from top bar; move body switching into the rail or elsewhere.

**Reviewer Verdict: REMOVE raw `InstanceSwitch`; REPLACE with Header Presence Pill + Devices Settings.**

1. **The Semantic Invariant:**
   - In **Unified Presence** (Singular Mode): You are ALWAYS talking to Halbert. You are currently connected to the local physical body (`desk` on Mac Studio, `home` on N150).
   - Halbert knows his physical location: *"I am at your desk body; my kitchen body is running Home Assistant."*
   - Switching instances via page-reloading port switchers (`:8000` vs `:8001`) is a legacy technical artifact. Cross-body capabilities are executed via internal tool proxying (`PeerToolProxy`), not frontend reloads.
2. **Header Presence Pill:**
   - Place a sleek **Presence Pill** in the top bar: `[ Halbert @ desk • Unified ]` with an emerald status dot.
   - Clicking the pill opens a quick **Body Info Card**:
     - *Local Body:* `desk` (Mac Studio) • Capabilities: `[gpu_llm, terminal, dev]`
     - *Canonical Brain:* `home` (N150 Appliance) • Connected `http://n150.lan:8001`
     - *Action:* `[ Manage Linked Devices... ]` $\rightarrow$ navigates to `Settings → Devices`.
3. **Independent Entities (Multi-Agent Fleets):**
   - If a user configures separate personas (`halbert-desk` and `halley-home`), the Presence Pill serves as an Entity Workspace Switcher.

---

#### Q3: Left Rail Information Architecture — 4 Domain Pillars (No "More" Drawer)

**Reviewer Verdict: ERADICATE "Being & Ambient Home" and "More". ADOPT 4 Clean Domain Pillars.**

```
┌────────────────────────────────────────────────────────────────┐
│ 1. OVERVIEW & SPACE                                            │
│    • Overview (/)            [LayoutDashboard]                 │
│    • Sentient Home (/home)   [Home] (gated: home capability)   │
├────────────────────────────────────────────────────────────────┤
│ 2. INTELLIGENCE & AUDIT                                        │
│    • Findings (/findings)    [ShieldAlert]                     │
│    • Approvals (/approvals)  [CheckCircle2] (with badge)       │
├────────────────────────────────────────────────────────────────┤
│ 3. HOST ADMINISTRATION                                         │
│    • Services (/services)    [Server]                          │
│    • Storage (/storage)      [HardDrive]                       │
│    • Backups (/backups)      [Archive]                         │
│    • Terminal (/terminal)    [Terminal]                        │
├────────────────────────────────────────────────────────────────┤
│ 4. WORKLOADS & COMPUTE                                         │
│    • Containers (/containers)[Container] (gated: dev)          │
│    • GPU & Compute (/gpu)    [Cpu] (gated: dev/gpu)            │
│    • Applications (/apps)    [Package]                         │
│    • Network & Sharing       [Wifi / Share2]                   │
│    • Development (/dev)      [Code2] (gated: dev)              │
└────────────────────────────────────────────────────────────────┘
```

* **Rationale:**
  - `Overview` (`/`): Replaces ambiguous "Dashboard".
  - `Sentient Home` (`/home`): Dedicated spatial home automation view.
  - `Approvals` (`/approvals`): Elevates agent proposal verification and blast-radius safety.
  - *No "More" junk drawer:* GPU, Containers, Apps, Network, and Development are logically grouped under *Workloads & Compute*.
  - *Settings gear:* Stays in the top bar as the global administrative gateway.

---

#### Q4: Top Bar Anatomy

**Reviewer Verdict: STREAMLINED TELEMETRY & PANEL CONTROLLER STRIP.**

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Halbert   [ @ desk • Unified ]   [ ◫ Dashboard | ◧ Host ]    (Scan 100%)    [🎙️] [⚙️]    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Left to Right:**
1. **Brand:** `HalbertMark` + `Halbert` text.
2. **Presence Pill:** `[ @ desk • Unified ]` with connectivity dot.
3. **Main Panel Toggles:** Segmented button group:
   - `[ ◫ Center ]` (Toggles Main Panel 1 • `⌘D`)
   - `[ ◧ Host ]` (Toggles Main Panel 2 • `⌘J`)
4. **Command Palette (`Cmd+K`):** Global action search & navigation.
5. **Background Telemetry:** `ProgressPill` (System Scan % / Doc Indexing %).
6. **Voice HUD Summoner:** `VoiceHudSummonButton` (Tauri desktop pill).
7. **Voice Mode Entry:** `Button` (`AudioLines` $\rightarrow$ full-bleed `/voice`).
8. **Audio Engine Indicator:** Microphone / hearing status.
9. **Pending Approvals Badge:** Amber counter if agent proposals need sign-off.
10. **Settings Gear:** Direct entry to `/settings`.

---

#### Q5: Grouping Entities & Multi-Node Topology

**Reviewer Verdict: STRICT SEPARATION OF "BODIES OF ONE MIND" VS "DISCRETE MINDS".**

1. **Unified Presence (Singular Entity):**
   - All paired hardware nodes are **bodies of Halbert**.
   - One shared autobiography (`PersonaMemoryStore`), one thread stream (`ThreadManager`), one `persona_id`.
   - The UI does not force instance-switching; cross-node telemetry is displayed under `Settings → Devices` or inline component widgets.
2. **Discrete Minds (Independent Entities):**
   - Distinct `persona_id`s, isolated memories, local thread stores.
   - Accessed via distinct workspaces or switched via the Presence Pill popover.

---

#### Q6: Settings — Full Stage with Summonable Assistant

**Reviewer Verdict: SETTINGS AS MAIN STAGE + OPTIONAL RIGHT ASSISTANT.**

1. **Dense Tab Integrity:**
   - `Settings.tsx` contains 12 deep tabs (`System`, `AI Models`, `Knowledge`, `Safety`, `Alerts`, `Identity & Voice`, `Devices`, `Security`, `Vision`, `Audio`, `About`, `Debug`).
   - Settings renders in Main Panel 1 with its dedicated sub-rail.
2. **Interactive Configuration Assistant:**
   - When in Settings, the user can toggle Main Panel 2 (`Cmd+J`) to summon Halbert alongside the settings form.
   - Halbert receives context from the active settings tab (e.g. `?tab=devices`) to guide token setup, model selection, or policy adjustments in real-time.

---

#### Q7: Voice Mode — Route Invariant vs. Panel State

**Reviewer Verdict: PRESERVE FULL-BLEED `/voice` ROUTE FOR APPLIANCES; USE TRANSIENT HUD FOR DESKTOP.**

1. **Full-Bleed Route Invariant (`/voice`):**
   - Essential for dedicated kiosks, wall mounts, and bedside appliances.
   - When active, all panel chrome (Rail, Center, Right) is hidden; dark canvas owns the screen.
2. **Desktop Voice Companion (`/voice-hud`):**
   - 480x72 floating overlay summoned via Tauri over macOS/Linux desktops.
3. **Inline Chat Voice:**
   - Mic recording directly inside Main Panel 2's composer.

---

### 8.4 Visual Wireframes Across Layout States

#### State A: Host Canvas Focus (`[Left Rail] + [Right Host Panel]` — Center Hidden)
*Trigger: `Cmd+B` or hiding Center Dashboard with `Cmd+D`*
```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Halbert   [ @ desk • Unified ]   [ [◫] | [◧ Host] ]                 (Scan 100%)  [🎙️] [⚙️]│
├──────────────┬──────────────────────────────────────────┬────────────────────────────────────────┤
│ LEFT RAIL    │ CONVERSATION SPINE (flex-1)              │ CONTEXT STAGE (480px - 600px)          │
│              │                                          │                                        │
│ • Overview   │ > Halbert: Host healthy. All 20 cores    │ ┌────────────────────────────────────┐ │
│ • Home       │   operating at 42°C. ZFS pool healthy.   │ │ HOST VITALS                        │ │
│ • Findings   │                                          │ │ CPU: 12%  RAM: 18.4GB  Pool: 88%   │ │
│ • Approvals  │ ┌──────────────────────────────────────┐ │ └────────────────────────────────────┘ │
│ • Services   │ │ Live Inline PTY (zfs list)           │ │                                        │
│ • Storage    │ │ $ zfs list -o name,avail,used        │ │ ┌────────────────────────────────────┐ │
│ • Backups    │ │ tank/data   1.2T   8.8T              │ │ │ TERMINALS ACCORDION DOCK           │ │
│ • Terminal   │ └──────────────────────────────────────┘ │ │ [ >_ zfs monitor (pid: 4921) ]     │ │
│ • Workloads  │                                          │ │ [ + New Interactive PTY Shell ]    │ │
│              │ [ Ask Halbert or stage a command...    ] │ └────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────┴────────────────────────────────────────┘
```

#### State B: Dashboard Focus (`[Left Rail] + [Center Dashboard]` — Right Hidden)
*Trigger: Hiding Right Panel with `Cmd+J`*
```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Halbert   [ @ desk • Unified ]   [ [◫ Dashboard] | [ ] ]            (Scan 100%)  [🎙️] [⚙️]│
├──────────────┬───────────────────────────────────────────────────────────────────────────────────┤
│ LEFT RAIL    │ ACTIVE PAGE CONTENT (/storage — Full Width Stage)                                 │
│              │                                                                                   │
│ • Overview   │ Storage Pools & Filesystems                                                       │
│ • Home       │ ┌───────────────────────────────────────────────────────────────────────────────┐ │
│ • Findings   │ │ tank/data (ZFS Mirror • 10 TB NVMe Array)                                     │ │
│ • Approvals  │ │ Capacity: [████████████████████░░░░] 88% (Healthy • 1.2 TB Free)              │ │
│ • Services   │ └───────────────────────────────────────────────────────────────────────────────┘ │
│ • Storage ◄  │                                                                                   │
│ • Backups    │ Physical Disks (4 NVMe Devices)                                                   │
│ • Terminal   │ ┌───────────────────────────────────────────────────────────────────────────────┐ │
│ • Workloads  │ │ nvme0n1: Samsung 990 Pro 4TB (42°C • Good • 0 Reallocated Sectors)           │ │
│              │ └───────────────────────────────────────────────────────────────────────────────┘ │
└──────────────┴───────────────────────────────────────────────────────────────────────────────────┘
```

#### State C: Side-by-Side Co-pilot (`[Left Rail] + [Center Dashboard] + [Right Assistant]`)
*Trigger: Opening both Main Panel 1 & Main Panel 2*
```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Halbert   [ @ desk • Unified ]   [ [◫ Dashboard] | [◧ Host] ]       (Scan 100%)  [🎙️] [⚙️]│
├──────────────┬──────────────────────────────────────────┬────────────────────────────────────────┤
│ LEFT RAIL    │ ACTIVE PAGE CONTENT (/storage)           │ HALBERT ASSISTANT COMPANION (380px)    │
│              │                                          │                                        │
│ • Overview   │ Storage Pools & Filesystems              │ Context: /storage (ZFS Mirror)         │
│ • Home       │ ┌──────────────────────────────────────┐ │                                        │
│ • Findings   │ │ tank/data (10 TB Mirror)             │ │ > Halbert: I see pool tank/data is   │
│ • Approvals  │ │ Capacity: [██████████░░] 88%         │ │   at 88%. Would you like me to prune │
│ • Services   │ └──────────────────────────────────────┘ │   unused Docker images to free ~45GB?  │
│ • Storage ◄  │                                          │                                        │
│ • Backups    │ Physical Disks                           │ [ Prune Build Cache ] [ Inspect Logs ] │
│ • Terminal   │ ┌──────────────────────────────────────┐ │                                        │
│ • Workloads  │ │ nvme0n1: Samsung 990 Pro (42°C)      │ │ [ Ask about storage or run tool... ] │
│              │ └──────────────────────────────────────┘ │                                        │
└──────────────┴──────────────────────────────────────────┴────────────────────────────────────────┘
```

---

### 8.5 Implementation Phasing

1. **Phase 1: NavRail Information Architecture & Semantic Purge (Immediate)**
   - Reorganize `Layout.tsx` `navSections` into the 4 Domain Pillars.
   - Eradicate "Being & Ambient Home" and "More" labels.
   - Promote `Approvals` alongside `Findings`.

2. **Phase 2: Header Presence Refactor & Panel Toggles**
   - Replace `InstanceSwitch.tsx` with `PresencePill.tsx` (`Halbert @ desk`).
   - Add segmented panel toggle buttons in the top bar for Center Dashboard (`Cmd+D`) and Right Host Canvas (`Cmd+J`).

3. **Phase 3: Two-Main-Panel Shell Layout Engine (`Layout.tsx`)**
   - Implement `showCenter` and `showHostPanel` state in `ShellModeContext.tsx`.
   - Update `HostShell.tsx` to automatically adapt between **Full Host Canvas** (when Center is hidden) and **Compact Assistant** (when Center is visible).

4. **Phase 4: Connected Device Management (G12 / P7)**
   - Wire `Settings → Devices` (`DevicesTab.tsx`) with capability discovery and entity identity management.

---

### 8.6 Review Summary Matrix

| Architectural Dimension | Founder Instinct | Final Approved Target Design | Status |
|---|---|---|---|
| **Shell Panel Model** | 3 independent panels; center collapsable to leave left+right | **1 Left Rail + 2 Freely Togglable Main Panels** (Adaptive Host Canvas vs Companion) | **Approved & Specified** |
| **Instance Switcher** | Move to rail as "Nodes" | **Header Presence Pill (`Halbert @ desk`)**; management in `Settings → Devices` | **Approved with Revision** |
| **Left Rail IA** | Rename section to "Nodes" | **4 Domain Pillars** (*Overview & Space*, *Intelligence & Audit*, *Host Admin*, *Workloads*); no "More" | **Redesigned** |
| **Top Bar Strip** | Remove switcher | **Presence Pill + Panel Toggles (`◫`, `◧`) + Global Approvals Badge + `Cmd+K`** | **Approved with Revision** |
| **Settings Experience** | Overtake shell | **Main Stage Viewport + Summonable AI Companion (`Cmd+J`)** | **Refined** |
| **Voice Mode** | Collapse into right panel | **Preserve `/voice` full-bleed route** for kiosks; `/voice-hud` overlay for desktop | **Invariant Upheld** |
| **Brand Semantics** | Sci-fi metaphors ("The Being", "Sovereign Host") | **Apple-Style Grounded Lexicon** (*Identity & Voice*, *Host Canvas*, *Compute Mesh*) | **Standardized** |

---

## 9. Founder Decisions & Finalized Terminology Pass (2026-09-01)

This section records the founder's decisions on the reviewer feedback (Section 8) and supersedes any conflicting proposals in Section 8. Where Section 8 and Section 9 disagree, **Section 9 wins.**

### 9.1 Founder rulings on reviewer proposals

| # | Reviewer proposal | Founder ruling |
|---|---|---|
| 1 | Emojis in wireframes (`[🎙️]`) | **Rejected.** No emojis — global rule. Use lucide icon names in specs. |
| 2 | "Sentient Home" as rail label for `/home` | **Accepted as not-banned** but not preferred for marketing. "The Being" was the real problem (in code, threatening the website). "Sentient Home" is fine in product/UI context. |
| 3 | "Overview & Space" as section 1 label | **Rejected as vague.** Founder likes "Nodes" but acknowledges it's technical. Adopted: adaptive section headers (see 9.4). |
| 4 | "Cross-body capabilities via PeerToolProxy, not frontend reloads" | **Rejected as factually wrong.** Dashboard pages fetch from the local instance's REST API. PeerToolProxy proxies agent tool calls, not dashboard data. See 9.5 for the correct cross-body data story. |
| 5 | `Cmd+K` command palette in the top bar | **Rejected as scope creep.** Not part of the shell restructure. Track separately if ever wanted. |
| 6 | "Network & Sharing" as a single merged rail line | **Rejected.** `/network` and `/sharing` are separate routes. Keep them as separate rail items. |
| 7 | What happens when center is hidden and you click a nav item | **Decided: auto-show the center panel.** Clicking a nav item when center is hidden opens the center panel and navigates to the page (in landscape / desktop). |
| 8 | Backend renames (`federation/` -> `mesh/`, `persona/` -> `identity/`, `being.yml` -> `identity.yml`) | **Rejected.** No backend renames. Code names stay. Only UI labels change. |
| 9 | "Host Canvas" as the canonical term for the conversation surface | **Rejected.** No "Host Canvas." The conversation surface is just "the conversation panel" or "Halbert" — it doesn't need a special name. |

### 9.2 Definitive terminology table

This is the canonical lexicon for the shell redesign. UI labels are what users see. Code names are what stays in the codebase (no renames). Where they differ, that's intentional — the code name is an implementation detail.

| Concept | Banned names | UI label (user-facing) | Code name (unchanged) | Notes |
|---------|-------------|----------------------|----------------------|-------|
| The AI entity | "The Being" | **Halbert** | `persona_id`, `BeingConfig` | "The Being" is purged from all UI. "Halbert" is the entity's name. `BeingConfig` stays in code — it's an implementation detail. |
| Entity config tab | "The Being", "Being" | **Identity & Voice** | `BeingTab.tsx`, `being_config.py` | Already the shipped Settings tab name. No code rename. |
| The conversation surface | "Engaged mode", "Sovereign Host Shell", "Host Canvas" | **Conversation** (or just "Halbert") | `HostShell.tsx`, `ShellMode = 'engaged'` | No special product name. In the 3-panel model it's the right panel. Code stays as-is. |
| The dashboard surface | "Browsing mode" | **Dashboard** | `ShellMode = 'browsing'` | Already what users call it. |
| The left rail | "sidebar", "navigation" | **Rail** | `NavRail.tsx` | Already established. |
| Entity mode (shared) | "Unified Presence" | **Singular Entity** | `singular`, `canonical_memory_url` | Already shipped in `EntityIdentityCard.tsx`. No change. |
| Entity mode (separate) | — | **Independent Node** | `independent` | Already shipped. No change. |
| Physical device label | — | **Body** | `body_name` | Already used in code and UI. Clean. |
| Multi-device network | "Federation", "Fleet", "Compute Mesh" | **Linked Devices** | `federation/`, `peers_config.py` | "Federation" is enterprise jargon. "Linked Devices" is what users see in Settings. Code stays `federation/`. |
| The always-on node | — | **Canonical Host** | `canonical_memory_url` | "Canonical" is clear and technical. No change needed. |
| System scans / health | "Somatosensory Loop", "REM Sleep" | **Health Checks** | existing code names | No biological jargon in UI. Code names stay. |
| Audio perception | "Auditory Cortex", "Acoustic Aura" | **Audio** | `audio/` | Direct and functional. Code already uses `audio/`. |
| The identity indicator | "InstanceSwitch" | **Presence Pill** | new `PresencePill.tsx` | Replaces `InstanceSwitch.tsx` in the top bar. |
| Voice full-bleed | — | **Voice Mode** | `ShellMode = 'voice'`, `/voice` | Already established. |
| Voice floating overlay | — | **Voice HUD** | `/voice-hud`, `VoiceHudSummonButton` | Already established. |

### 9.3 Definitive rail structure

Four sections. No "More" junk drawer. All 14 routed pages are placed into a domain. Section headers are **adaptive** — a section with only one visible item renders without a header label (see 9.4).

```
Section 1: Overview
  - Dashboard    (/)         [LayoutDashboard]
  - Home         (/home)     [Home]           (gated: home capability)

Section 2: Findings & Approvals
  - Findings     (/findings) [Shield]
  - Approvals    (/approvals)[CheckCircle]    (with pending-count badge)

Section 3: System
  - Services     (/services) [Server]
  - Storage      (/storage)  [HardDrive]
  - Backups      (/backups)  [Archive]
  - Terminal     (/terminal) [Terminal]

Section 4: Workloads
  - Containers   (/containers) [Container]    (gated: dev capability)
  - GPU          (/gpu)        [Cpu]          (gated: dev/gpu capability)
  - Apps         (/apps)       [Package]
  - Network      (/network)    [Wifi]
  - Sharing      (/sharing)    [Share2]
  - Development  (/development)[Code2]        (gated: dev capability)
```

**Instance-based filtering (unchanged from current logic):**
- Section 3 (System) hides entirely on a paired `home` instance (role === 'home').
- Section 1's Home item hides when the instance lacks the `home` feature.
- Section 4's Containers, GPU, and Development hide when the instance lacks the `dev` feature.
- Settings stays as the top-bar gear, not a rail item.

**Why these section names:**
- **Overview** — Direct. It's the overview of this machine and its environment. When only Dashboard is present (no HA), the header hides and the item stands alone.
- **Findings & Approvals** — Named after what it contains. No abstract "Intelligence & Audit" framing. These are the two surfaces where the agent surfaces things that need human attention.
- **System** — Simple, universally understood. These are the sysadmin pages for managing the host machine. Replaces "Host Controls" / "Host Administration" — "System" is cleaner and less pompous.
- **Workloads** — The things running on the machine that aren't core system services. Containers, GPU compute, apps, network config, sharing, and dev tools. Replaces "More" — these aren't secondary, they're a different category.

### 9.4 Adaptive section headers

**Rule:** A rail section with only one visible item renders without a header label. The item stands alone as a top-level nav entry. When the section has two or more visible items, the header label appears.

**When this applies:**
- **Section 1 (Overview):** On a standalone sysadmin machine with no HA, only Dashboard is visible → no header. On a machine with HA configured, Dashboard + Home → "Overview" header appears.
- **Section 2 (Findings & Approvals):** Always 2 items → header always shows.
- **Section 3 (System):** Always 4 items (or hidden entirely on home instances) → header always shows when visible.
- **Section 4 (Workloads):** Without dev feature: Apps, Network, Sharing (3 items) → header shows. With dev feature: 6 items → header shows. Never drops to 1.

**Implementation:** The `NavRail` component (or the `filteredSections` logic in `Layout.tsx`) skips rendering the `<p className="hb-navrail__section-label">` when `section.items.length === 1`. This is a ~3 line change in the design-system component or a filter in Layout.

**Why:** A section header for a single item is noise. "Overview" above a lone "Dashboard" entry adds nothing. The founder identified this directly: "if someone has only one space then it doesn't have a headline."

### 9.5 The cross-body data story (correcting the reviewer's error)

The reviewer claimed that cross-body capabilities work via `PeerToolProxy` and frontend reloads are a "legacy technical artifact." **This is wrong.** Here's the actual architecture:

**What `PeerToolProxy` does:** When the agent (in the conversation) calls a tool, and that tool exists on another body, the tool call is proxied to the other body's MCP server. This is agent-to-tool, not dashboard-to-data.

**What dashboard pages do:** Services, Storage, Backups, Findings, etc. fetch data from the **local instance's REST API** (`/api/services`, `/api/storage`, etc.). There is no cross-body data proxy for dashboard pages today. You cannot see the N150's storage pools from the Mac Studio's `/storage` page without switching the API endpoint.

**What this means for the Presence Pill:**

The Presence Pill replaces the InstanceSwitch for **identity and conversation**, not for **dashboard data**. The correct behavior is:

1. **In Singular Entity mode:**
   - The conversation panel (right) is always the same Halbert. Switching bodies does NOT change the conversation — same entity, same memory, same threads.
   - The dashboard pages (center) show data for the **currently selected body**. Switching bodies changes what data you see.
   - The Presence Pill shows "Halbert @ desk" and has a dropdown to switch to another body ("home", "laptop"). Switching changes the dashboard data source but not the conversation.

2. **In Independent Node mode:**
   - Switching bodies switches everything — conversation, memory, threads, and dashboard data. You're talking to a different entity.
   - The Presence Pill shows the entity name + body ("Halbert @ desk" vs "Halley @ home") and switching is a bigger deal — it's an entity switch.

3. **Short-term implementation:** The body switch in the Presence Pill still does what InstanceSwitch does today — changes the API endpoint and reloads. The difference is framing: it's "switch to another body" (identity language) not "switch instance" (infrastructure language). A future cross-body data proxy could eliminate the reload, but that's a separate backend workstream.

### 9.6 Panel interaction rules

**Clicking a nav item when center is hidden:** The center panel auto-shows and navigates to the clicked page. Navigation implies a target, and the target is the center panel. (Founder decision, point #7.)

**Default panel states on load:**
- Center: visible (showing the last-visited page, or Dashboard on first load)
- Right (Conversation): visible (Halbert is always present)
- Left (Rail): visible
- This is the "Side-by-Side Co-pilot" state — the default. The user hides panels to focus.

**Panel toggle shortcuts:**
- `Cmd/Ctrl+D`: Toggle center panel (Dashboard / page)
- `Cmd/Ctrl+J`: Toggle right panel (Conversation)
- `Cmd/Ctrl+B`: Toggle between "Dashboard Focus" (center only) and "Host Focus" (right only) — a quick flip between the two main work states
- `Cmd/Ctrl+\`: Collapse/expand the left rail (icon-only mode)

**Narrow screens (mobile, narrow kiosk):**
- Only one panel shows at a time. The rail collapses to icons. Center and right panel toggle exclusively (no side-by-side). This is a future concern — the desktop app targets landscape displays.

**Fullscreen/kiosk:**
- `/voice` route: all panels hidden, full-bleed dark canvas. Already implemented.
- A future `/kiosk` route could show dashboard-only (no rail, no conversation) for wall displays. Not part of this redesign.

### 9.7 What the 3-panel model replaces

The current `ShellModeContext` has three modes: `engaged`, `browsing`, `voice`. In the new model:

- `engaged` → center hidden, right visible ("Host Focus" state). The `HostShell` component renders in the right panel.
- `browsing` → center visible, right hidden ("Dashboard Focus" state). The rail + page renders in the center.
- Both visible → "Side-by-Side Co-pilot" (new state, not possible in the current mode-switch model).
- `voice` → unchanged. Full-bleed `/voice` route.

The `ShellMode` type changes from `'engaged' | 'browsing' | 'voice'` to a panel visibility model:
```typescript
type ShellState = {
  centerVisible: boolean
  rightVisible: boolean
  voiceMode: boolean  // /voice route, overrides everything
}
```

`Cmd/Ctrl+B` becomes a convenience that flips between `{centerVisible: true, rightVisible: false}` and `{centerVisible: false, rightVisible: true}` — the two most common focus states.

### 9.8 Implementation phasing (revised)

| Phase | Scope | Files |
|-------|-------|-------|
| **1. Rail restructure** | Replace 4 nav sections (incl. "More") with the 4 definitive domains. Implement adaptive section headers in NavRail. | `Layout.tsx`, `NavRail.tsx` (design-system) |
| **2. Presence Pill** | Replace `InstanceSwitch.tsx` with `PresencePill.tsx`. Shows entity + body. Dropdown switches body (endpoint). | `PresencePill.tsx` (new), `Layout.tsx`, `apiBase.ts` |
| **3. Panel toggle controls** | Add center/right toggle buttons to the top bar. Replace `ModeSwitch.tsx` with panel toggle segmented control. | `ModeSwitch.tsx` (rewrite or replace), `ShellModeContext.tsx` |
| **4. 3-panel layout engine** | Rewrite `Layout.tsx` render logic from mode-ternary to panel-visibility. `HostShell` renders in the right panel. Center panel renders the active route. | `Layout.tsx`, `HostShell.tsx`, `ShellModeContext.tsx` |
| **5. Settings as center panel** | Stop Settings from overtaking the shell. Render it in the center panel with its own sub-rail. Conversation panel stays visible on the right. | `Settings.tsx`, `Layout.tsx` |

Phase 1 is low-risk and can ship independently. Phases 2-5 are the shell restructure and should ship together.

---

## Appendix A: Key files for reference

| File | Role |
|------|------|
| `dashboard/frontend/src/components/Layout.tsx` | The shell — mode switching, top bar, NavRail, route exceptions |
| `dashboard/frontend/src/contexts/ShellModeContext.tsx` | The three-mode state machine (engaged/browsing/voice) |
| `dashboard/frontend/src/components/shell/ModeSwitch.tsx` | The two-tab mode toggle in the top bar |
| `dashboard/frontend/src/components/shell/InstanceSwitch.tsx` | The instance/body dropdown in the top bar |
| `dashboard/frontend/src/components/shell/HostShell.tsx` | The engaged surface (chat + context stage) |
| `dashboard/frontend/src/components/shell/ContextStage.tsx` | The right-side vitals/terminal panel in engaged mode |
| `dashboard/frontend/src/pages/Settings.tsx` | The Settings page (overtakes shell, own NavRail) |
| `packages/design-system/src/surfaces/NavRail.tsx` | The shared navigation rail component |
| `dashboard/routes/instance.py` | `/api/instance/info` — instance identity endpoint |
| `config/being_config.py` | `BeingConfig` — persona, variant, body_name, canonical_memory_url, entity mode |
| `integrations/cognition_wiring.py` | `_get_persona_id`, `_get_body_name`, `is_singular_entity_mode` |
| `dashboard/routes/devices.py` | Device & entity-mode API (Settings → Devices page) |
| `dashboard/frontend/src/components/settings/devices/EntityIdentityCard.tsx` | The entity-mode toggle UI (singular vs independent) |

## Appendix B: Existing handoffs on related topics

| Document | Scope |
|----------|-------|
| `HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md` | The singular entity design (one Halbert, many bodies) |
| `IMPL-PLAN-SINGULAR-ENTITY-2026-08-31.md` | Implementation plan for singular entity |
| `HALBERT-MULTI-INSTANCE-DESIGN.md` | Multi-instance via separate processes (the infra layer) |
| `HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md` | Federated compute & fleet proxy |
| `HANDOFF-G12-DEVICES-PAGE-DESIGN-REVIEW-2026-08-31.md` | Devices page design (entity identity card, pairing) |
| `TASK-PACKET-02-SETTINGS-DECOMPOSITION-AND-NAV.md` | The nav consolidation that created the current rail |
| `SOVEREIGN-HOST-SHELL-RESULTS-2026-08-25.md` | The engaged mode (HostShell) implementation results |
