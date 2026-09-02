# Handoff: Semantic Audit & Terminology Alignment (2026-09-01)

> **SUPERSEDED 2026-09-01/02 by the shell review §9.2 lexicon and §9.1 rulings** (no backend renames; `identity.yml`, `mesh/`, `identity/` rejected; Tasks 3–4 closed). The remaining sweep work is tracked as ROADMAP row DOCS-1 and the lexicon extensions in `documentation/design/CORE-CONCEPTS-AND-ALIGNMENT-2026-09-02.md` §3.

**To:** Successor Agent / Review AI  
**From:** Initial Semantic Audit & Architecture Session  
**Date:** 2026-09-01  
**Status:** Initial Audit Complete; Ready for Deep Scrutiny, Lexicon Standardization & Phased Migration Planning  
**Primary Reference:** `semantic_audit.md` (in current conversation artifacts)

---

## 1. Executive Context & Motivation

A comprehensive semantic audit has been initiated across the entire Halbert codebase, documentation, blueprints, and UI components.

### The Core Problem
Over several development waves and blue-sky explorations, the codebase has accumulated:
1. **Uncanny / Mystical Sci-Fi Metaphors:** Biological and esoteric anthropomorphism (*"The Being"*, *"Soul Migration"*, *"Somatosensory Loop"*, *"Holographic Reincarnation"*, *"Auditory Cortex"*).
2. **Heavy Academic & Enterprise Jargon:** Clunky distributed-systems vocabulary (*"Federated Multi-Node Compute"*, *"Synthetic Intent VFS"*, *"Reciprocal Rank Fusion"* leaking into UI).
3. **Severe Alias Proliferation:** The same underlying concept is referred to by 3–4 different names depending on whether you are looking at database models, backend packages, config YAMLs, API routes, or React components.
4. **Unnamed Architectural Mechanics:** Powerful capabilities running without clear, crisp product nouns.

### The North Star: Apple-Style Language Consistency
All user-facing and architectural terminology must adhere to **Apple-style design principles**:
* **Human, Tactile, and Dignified:** Simple words that do what they say. Avoid both eerie sci-fi pretense and sterile bureaucratic jargon.
* **One Concept, Exactly One Name:** Eliminate alias confusion across all layers.
* **Direct Nouns and Active Verbs:** Clear, memorable, and explainable to non-technical users (*Pair*, *Restore*, *Approve*, *Self*, *Mesh*, *Vitals*).

---

## 2. Summary of Initial Audit Findings

The initial audit mapped all concepts across **8 architectural domains** into four distinct categories:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   AUDIT CLASSIFICATION                                      │
├───────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ 🔴 Disliked / Style   │ Terms that violate the design language or were explicitly flagged   │
│    Failures           │ by the user (e.g. "The Being", "Federated Network", "Soul Migration")│
├───────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 🟡 Conflicted /       │ Concepts where 2–4 competing names circulate across docs/code       │
│    Aliases            │ (e.g. Persona vs Being vs Identity; Workstation vs Compute Host)    │
├───────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 🟢 Established &      │ Resonant, clean terms to preserve and protect as gold standards     │
│    Strong             │ (e.g. Halbert Mark & Tines, WhyChip & 4 Whys, Proactivity Dial)     │
├───────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ ⚪ Unnamed /          │ Real capabilities lacking a crisp single product noun               │
│    Descriptive        │ (e.g. Unified Mode vs Standalone Mode switch, Voice States)         │
└───────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

### High-Priority Problem Terms & Proposed Replacements

| Current Name | Status | Proposed Primary Replacement | Key Rationale |
| :--- | :---: | :--- | :--- |
| **"The Being"** | 🔴 | **Self** (or **Identity**) | *"The Being"* is uncanny and pseudo-religious. *"Self"* is dignified, direct, and matches Python/code idioms. In UI: *"System & Self"* or *"Identity"*; in config: `identity.yml`. |
| **"Federated Network"** | 🔴 | **Compute Mesh** / **Mesh Computing** | *"Mesh"* immediately communicates peer-to-peer resilience without centralized cloud dependency. In UI: *"Linked Devices"* or *"Compute Mesh"*. |
| **"Soul Migration" / "Reincarnation"** | 🔴 | **Identity Vault** | High-trust, security-focused name for client-side encrypted backup & restore to user storage. |
| **"Somatosensory Loop" / "REM Sleep"** | 🔴 | **Nightly Maintenance & Idle Care** | Honest, functional systems terminology for off-hours index compression and proactive health checks. |
| **"Kernel Reflex Arc"** | 🔴 | **Fast Sentry** | Biological jargon; misleading on macOS/Windows where eBPF does not exist. |
| **"Auditory Cortex"** | 🔴 | **Audio Engine** / **Sound & Hearing** | Professional systems noun replacing neurobiology jargon. |
| **"Sovereign Host"** | 🔴 | **Local Machine** / **System Host** | Drops pompous crypto/political connotation. |
| **"Synthetic Intent VFS"** | 🔴 | **State Pipe & Socket Interface** | Replaces brittle kernel FUSE driver concept with rock-solid POSIX IPC (`/run/halbert.sock`). |

---

## 3. Tasks for the Successor AI

Please execute the following tasks:

### Task 1: Complete In-Depth Scrutiny & Gap Discovery
1. **Audit CLI subcommands & flags:** Inspect `Halbert/main.py` and `halbert_core/cli/` to check whether legacy terms appear in CLI help text or argument names.
2. **Audit System Prompts & XML schemas:** Inspect `config/prompts/v2/` for references to "The Being", "Sovereign Host", or biological metaphors.
3. **Audit Frontend Route & Component Naming:** Review:
   - `BeingTab.tsx` ➔ Candidate rename to `SelfTab.tsx` or `IdentityTab.tsx`
   - `NodeFleetCockpit.tsx` ➔ Candidate rename to `DeviceGrid.tsx` or `DevicesView.tsx`
   - `TouchBar.tsx` ➔ Candidate rename to `ControlStrip.tsx` or `VoiceActionBar.tsx` (to avoid Apple trademark collision)
4. **Audit Backend Packages:**
   - `halbert_core/federation/` ➔ Candidate rename to `halbert_core/mesh/`
   - `halbert_core/persona/` ➔ Candidate rename to `halbert_core/identity/`
   - `halbert_core/somatic/` ➔ Candidate rename to `halbert_core/maintenance/`

### Task 2: Produce the Definitive "Halbert Brand Lexicon & Dictionary"
Create a centralized reference table with the following schema:
- **Legacy / Competing Term(s)**
- **Canonical Product Name (User UI / Docs)**
- **Technical Identifier (Code / Python / TypeScript / Config)**
- **Domain / Layer**
- **Definition & User-Facing Explanation (One sentence)**
- **Rule of Usage (When to use, when NOT to use)**

### Task 3: Develop a Safe, Phased Migration Strategy
Ensure that renaming does not break running systems, test suites, or user databases:
1. **Phase 1 (Zero-Risk):** Documentation, Architecture Blueprints, Comments, System Prompts.
2. **Phase 2 (Low-Risk UI):** Frontend labels, Tab titles, Navigation menus, Tooltips, Storybook stories.
3. **Phase 3 (Config & Compatibility Shims):** 
   - Introduce `identity.yml` with fallback reading of `being.yml`.
   - Update `/api/settings/identity` with redirect / alias for `/api/settings/being`.
4. **Phase 4 (Backend Refactoring):** Module renames (`federation/` ➔ `mesh/`, `persona/` ➔ `identity/`) once all references and test suites are mapped.

### Task 4: Prepare Founder Decision Options
Prepare a crisp summary of key fork decisions ready for founder approval:
1. **"Self" vs "Identity"** as the primary replacement for "The Being".
2. **"Compute Mesh" vs "Mesh Computing" vs "Continuity Grid"** for the multi-machine peer infrastructure.
3. **Singular Entity Mode naming:** *"Unified Mode"* vs *"One Halbert"* vs *"Shared Presence"*.

---

## 4. Key Files to Reference

- Semantic Audit Artifact: [semantic_audit.md](file:///Users/ericbintner/.gemini/antigravity/brain/b690d9c9-3fe1-49a2-af7c-3069bf7e7378/semantic_audit.md)
- Experimental Blue-Sky Audits:
  - [SECOND-PASS-FEASIBILITY-AND-PRAGMATIC-BLUE-SKY.md](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/SECOND-PASS-FEASIBILITY-AND-PRAGMATIC-BLUE-SKY.md)
  - [BLUE-SKY-SENTIENT-SYSTEMS-AND-COGNITIVE-OS.md](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/BLUE-SKY-SENTIENT-SYSTEMS-AND-COGNITIVE-OS.md)
  - [SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md](file:///Volumes/4TB-BAD/Halbert/documentation/experimental/SINGULAR-ENTITY-HOME-ASSISTANT-AND-HALBERTOS-ECOSYSTEM.md)
- Multi-Node & Fleet Handoffs:
  - [.handoff/HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-FEDERATED-MULTI-NODE-COMPUTE-AND-FLEET-2026-08-29.md)
  - [.handoff/HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-SINGULAR-ENTITY-MULTI-BODY-2026-08-31.md)
- Identity & Philosophy Docs:
  - [documentation/design/the-being.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/the-being.md)
  - [documentation/design/philosophy.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/philosophy.md)
- Backend Packages:
  - [halbert_core/federation/](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/federation/)
  - [halbert_core/persona/](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/persona/)
  - [halbert_core/somatic/](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/somatic/)
- Frontend Components:
  - [BeingTab.tsx](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/settings/tabs/BeingTab.tsx)
  - [NodeFleetCockpit.tsx](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/fleet/NodeFleetCockpit.tsx)
  - [TouchBar.tsx](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/voice/TouchBar.tsx)
