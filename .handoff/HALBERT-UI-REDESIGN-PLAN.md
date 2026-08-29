# Halbert UI/UX Redesign & Information Architecture Plan

**Date:** 2026-08-29  
**Status:** Comprehensive UI/UX Redesign Specification  
**In Response To:** `HALBERT-UI-REDESIGN-INVESTIGATION-REQUEST.md` & Sentient Home Architecture  

---

## 1. Executive Summary & Core Philosophy

Halbert's user interface has evolved rapidly through feature additions, resulting in:
- A sprawling sidebar with **14 top-level nav items** across 5 fragmented sections.
- A **3,105-line megafile** (`Settings.tsx`) handling everything from LLM model endpoints to personality archetypes, MCP trust boundaries, vision redaction, and indexing dials.
- Redundant and confusing overlapping pages (e.g. `Security.tsx` for system findings vs `Settings > Security` for MCP trust gates).
- A disconnect between Halbert's role as a **Host Sysadmin** and its emerging role as a **Sentient Home Intelligence**.

### The Core Design Principle: "Cognitive Layer, Not Dashboard Sprawl"
Halbert is **not** trying to rebuild Home Assistant or Portainer. Halbert is the **ambient cognitive and orchestration layer**. The UI must reflect this:
1. **Never reinvent what Home Assistant does well** (no heavy custom 3D CAD floorplan builders; ingest HA Area Registry & Bermuda BLE presence automatically).
2. **Streamline 14 top-level nav items into 4 cohesive primary domains**.
3. **Decompose the 3,105-line `Settings.tsx` into clean, modular tabs with progressive disclosure**.
4. **Unify the Dual-Mode Shell** so switching between ambient browsing and focused chat interaction is natural and fluid.

---

## 2. Current State Inventory & Flaw Analysis

```
CURRENT SIDEBAR NAVIGATION (14 ITEMS)           SETTINGS.TSX (3,105 LINES)
├── Overview                                    ├── Main Tab (Profile, Models, Indexing, Sources)
│   ├── Dashboard (383 lines)                   ├── Safety Tab (AI rules, Guardrails)
│   └── Home (99 lines)                         ├── Alerts Tab (Alert rules)
├── System                                      ├── Being Tab (Personality, Voice, Senses)
│   ├── Services                                ├── Security Tab (MCP Trust Boundary)
│   ├── Storage                                 ├── Vision Tab (Screen/Webcam/Redaction)
│   ├── Backups                                 └── About Tab
│   ├── Apps
│   └── Security [Overlap with Settings]
├── Network
│   ├── Network
│   └── Sharing
├── Development
│   ├── Containers
│   ├── GPU
│   └── Development
└── Utility
    ├── Approvals [Better as a badge]
    └── Settings [3,105-line megafile]
```

### Critical Flaws Identified:
1. **Nav Bloat & Fragmentation:** 14 navigation targets create cognitive fatigue. Subsystems like `GPU` and `Development` belong under `Homelab/Compute`; `Backups` and `Storage` belong together.
2. **The "Wall of Settings" Megafile:** `Settings.tsx` mixes 6 distinct lifecycle domains into one file. State updates cause wide re-renders, and first-time users are overwhelmed by hundreds of form fields.
3. **Approvals Isolated on a Page:** Tool execution approvals (`/approvals`) belong in the active notification bar / chat context, not hidden on an isolated sub-page.
4. **Mobile & Responsive Failure:** A fixed `w-60` (240px) sidebar crushes the viewport on tablets and mobile screens without responsive collapse.

---

## 3. Proposed Information Architecture (IA)

We consolidate the application into **4 Primary Focus Areas** + an **Ambient Engaged Shell (Chat)**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               PROPOSED NAVIGATION (4 DOMAINS)                          │
├───────────────────────┬──────────────────────────────────┬─────────────────────────────┤
│ PRIMARY DOMAIN        │ SUB-VIEWS (TABS / ACCORDIONS)    │ PURPOSE                     │
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ 1. 🏠 Home & Spaces   │ • Living Areas (Auto-synced HA)  │ Sentient home spatial view, │
│                       │ • Chronicle (Autobiographical)   │ room status, Frigate cameras│
│                       │ • Devices & Automation           │                             │
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ 2. 🖥️ Host & Homelab   │ • Overview (CPU/RAM/Disks)       │ Sysadmin core: containers,  │
│                       │ • Storage & Backups (ZFS/Restic) │ services, GPU, dev tools,   │
│                       │ • Compute & Containers (Docker)  │ network, terminal sessions  │
│                       │ • Services & Packages            │                             │
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ 3. 🛡️ Security & Sentry│ • System Hygiene & Findings      │ Consolidated security: host │
│                       │ • MCP Trust & Data Gates         │ vulnerability scans + MCP   │
│                       │ • Access & Privacy Audit         │ camera/tool permissions     │
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ 4. ⚙️ Settings & Being │ • AI Models & Endpoints          │ Modularized configuration   │
│                       │ • Being & Personality            │ with clean progressive      │
│                       │ • Home & Spatial Connections     │ disclosure                  │
│                       │ • Senses & Vision Autonomy       │                             │
└───────────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

---

## 4. Leveraging Existing Tools (No Reinventing the Wheel)

### Home Topology & Spatial Knowledge
Rather than building a proprietary 2D/3D floorplan CAD engine from scratch:

```
                     ┌─────────────────────────────────────────────────────────┐
                     │          HOME ASSISTANT & FRIGATE ECOSYSTEM             │
                     └────────────────────────────┬────────────────────────────┘
                                                  │
            ┌─────────────────────────────────────┼─────────────────────────────────────┐
            │                                     │                                     │
            ▼                                     ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐             ┌───────────────────────┐
│ HA AREA REGISTRY      │             │ ROOM PRESENCE PLUGINS │             │ FRIGATE LOVELACE CARD │
│ (/api/config/area_reg)│             │ (Bermuda BLE/ESPres)  │             │ (Birdseye & Zones)    │
├───────────────────────┤             ├───────────────────────┤             ├───────────────────────┤
│ • Auto-imports Rooms  │             │ • Triangulates phone/ │             │ • Real-time bounding  │
│ • Groups Lights, HVAC │               watch to active room  │               boxes & zones         │
│ • Zero manual config  │             │ • sensor.eric_room    │             │ • Ingress / iframe    │
└───────────┬───────────┘             └───────────┬───────────┘             └───────────┬───────────┘
            │                                     │                                     │
            └─────────────────────────────────────┼─────────────────────────────────────┘
                                                  │
                                                  ▼
                     ┌─────────────────────────────────────────────────────────┐
                     │          HALBERT SPATIAL COGNITION ENGINE               │
                     │  • Auto-constructs Spatial Graph from HA Area Registry  │
                     │  • Understands "Turn off lights in here" via BLE sensor │
                     │  • Embeds existing HA Lovelace Floorplan if configured  │
                     └─────────────────────────────────────────────────────────┘
```

1. **Auto-Import HA Area Registry:**  
   Halbert connects to Home Assistant $\rightarrow$ reads all configured Areas (`Living Room`, `Kitchen`, `Garage`) and assigned entities $\rightarrow$ builds its internal spatial model with **zero manual layout work required by the user**.
2. **Native Bermuda BLE / ESPresense Tracking:**  
   Halbert listens to `sensor.user_room` to know what room the user is in, enabling spatial pronouns (*"Turn this light off"*).
3. **Lightweight Area Grid UI:**  
   The UI renders clean, auto-generated **Room Cards** grouped by Area. Users with advanced Lovelace/SweetHome3D floorplans can view them via an embedded Lovelace card view.

---

## 5. Concrete Settings Architecture & Modularization

### Decomposing `Settings.tsx` into `src/pages/settings/`

`Settings.tsx` is split into 6 focused, lightweight modules:

```
halbert_core/dashboard/frontend/src/pages/settings/
├── SettingsLayout.tsx          # Clean sidebar/tab wrapper (<100 lines)
├── ModelSettings.tsx           # Chat, Specialist, Vision model slots & Ollama endpoints (~250 lines)
├── BeingSettings.tsx           # Name, Voice, Archetype, Personality dials, Quiet hours (~300 lines)
├── HomeSettings.tsx            # HA Connection, Frigate MQTT, Spatial Area mapping, Safety Policy (~250 lines)
├── VisionSettings.tsx          # Screen capture, Webcam, OCR, Regex Redaction blocklist (~200 lines)
├── SecuritySettings.tsx        # MCP Trust Boundaries, AI Guardrails, Rate limits (~250 lines)
└── SystemSettings.tsx          # Indexing, Knowledge Sources, Alert Rules, Version (~200 lines)
```

---

### Exact Settings Fields & User Controls

#### 1. Home & Spatial Settings (`HomeSettings.tsx` $\rightarrow$ `home_config.json` & `being.yml`)
- **Home Assistant Connection:**
  - `HA Server URL`: `http://homeassistant.local:8123`
  - `Access Token`: `Bearer ••••••••••••` (masked with show/hide toggle)
  - `Auto-Sync Areas & Devices`: `[x] Enabled`
- **Frigate NVR Connection:**
  - `Frigate URL`: `http://frigate.local:5000`
  - `MQTT Broker`: `192.168.1.50:1883` (User, Password masked)
  - `Camera Area Mapping`: Dropdown mapping Frigate camera zones $\rightarrow$ HA Areas.
- **Presence Tracking Source:**
  - `Room Presence Sensor`: Dropdown populated from HA (`sensor.bermuda_eric_room`, etc.).
- **Physical Safety Policy:**
  - `Action Policy`: `[Autonomous (Safe)]` | `[Confirm High-Risk (Locks/Heaters)]` | `[Advisory Only]`
  - `Freeze Guard Minimum Temperature`: `[50°F / 10°C]`
  - `Quiet Hours`: `[22:00] to [07:00]` (mutes TTS and ambient audio alerts).

#### 2. Being & Senses Settings (`BeingSettings.tsx` $\rightarrow$ `being.yml`)
- **Persona Identity:** Name, Voice presentation (Male/Female/Neutral), Archetype selector.
- **Senses Autonomy Toggles:**
  - `[x] Enable Screen Vision`: Allows Halbert to capture active windows.
  - `[x] Proactive Visual Watcher`: Background anomaly detection.
  - `[x] Capture on Visual Intent`: Instant 1-turn capture when asking *"What's on my screen?"*.
  - `[ ] Capture on Command Error`: Diagnostic OCR on failed CLI tools.
  - `Watcher Interval`: Slider (10s – 300s, default 60s).

#### 3. Security & MCP Trust Settings (`SecuritySettings.tsx` $\rightarrow$ `mcp_security.json`)
- **Camera Data Gate:** `[x] Strip all binary images over external MCP connections`.
- **Allowed Tool Scopes:** Per-client permissions (Read-Only, Host CLI, Smart Home).

---

## 6. Progressive Disclosure & UX Hierarchy

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                            PROGRESSIVE DISCLOSURE MATRIX                               │
├───────────────────────┬──────────────────────────────────┬─────────────────────────────┤
│ LEVEL                 │ ACCESS LOCATION                  │ CONTENT                     │
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ Level 1: Everyday     │ Top Header / Main Canvas         │ • Chat Composer / Voice Mic │
│                       │                                  │ • Living Room Cards (Active)│
│                       │                                  │ • Host CPU/Disk Quick Status│
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ Level 2: Periodic     │ 1-Click Nav Domains              │ • Model Switcher (Auto/Spec)│
│                       │                                  │ • Service Restart Buttons   │
│                       │                                  │ • Room Climate / Light Dials│
├───────────────────────┼──────────────────────────────────┼─────────────────────────────┤
│ Level 3: Deep Config  │ Settings Sub-Tabs / Modals       │ • Regex Redaction Patterns  │
│                       │                                  │ • MCP Bearer Tokens         │
│                       │                                  │ • ZFS Pool Tuning           │
└───────────────────────┴──────────────────────────────────┴─────────────────────────────┘
```

### Contextual Settings Pattern:
Instead of forcing users to visit the Settings megafile to tweak a setting, expose **Contextual Settings Links**:
- In `Home.tsx`: A small gear icon in the corner opens a drawer with `HomeSettings.tsx`.
- In `Security.tsx`: A link at the top: *"Configure MCP Trust Boundaries $\rightarrow$"*.
- In `Chat`: Model picker dropdown has a direct *"Manage Endpoints..."* link.

---

## 7. Implementation Roadmap & Milestones

### Phase 1: Settings Modularization (High Priority, Immediate Impact)
- [ ] Create directory `src/pages/settings/`.
- [ ] Extract `ModelSettings.tsx`, `BeingSettings.tsx`, `HomeSettings.tsx`, `VisionSettings.tsx`, `SecuritySettings.tsx`, `SystemSettings.tsx`.
- [ ] Refactor `Settings.tsx` to a clean ~80-line router/tab layout.

### Phase 2: Navigation & Information Architecture Consolidation
- [ ] Update `Layout.tsx` navigation array: reduce 14 items to 4 primary domains (`Home`, `Host`, `Security`, `Settings`).
- [ ] Move `Storage`, `Backups`, `Containers`, `GPU`, `Services` into sub-views of `Host & Homelab`.
- [ ] Convert `Approvals` into a top-bar badge/drawer component.

### Phase 3: Spatial Area Grid & Home Assistant Integration
- [ ] Connect `Home.tsx` to HA Area Registry API (`/api/config/area_registry/list`).
- [ ] Render auto-generated Area Cards with room occupancy, temperature, and Frigate camera previews.
- [ ] Add `HomeSettings.tsx` with connection, presence sensor selection, and safety policy controls.

### Phase 4: Responsive & Tablet Enhancements
- [ ] Implement collapsible sidebar with icon-only rail mode on medium viewports (`md:w-16`, `lg:w-60`).
- [ ] Add touch-friendly walk-up wake styling for wall-mounted tablet displays.
