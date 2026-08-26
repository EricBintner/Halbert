# Halbert Brand Aesthetic, Living Style Guide (web-v7) & Storybook Design System Roadmap

**Version:** 1.0.0  
**Date:** August 2026  
**Status:** Approved Master Design System & Architectural Plan  
**Lead:** Visual Design Lead, Systems Architect & Brand Custodian  
**Scope:** Cross-Platform Design System (`marketing/web-v7` $\leftrightarrow$ `halbert_core/dashboard/frontend`)  
**Reads with:**
- [DESIGN-SYSTEM-SPEC.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/DESIGN-SYSTEM-SPEC.md) — Foundation Design Specification
- [COMPONENT-ARCHITECTURE.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/COMPONENT-ARCHITECTURE.md) — Component Architecture & Stage Lifecycles
- [HANDOFF-SOVEREIGN-HOST-SHELL-AND-DASHBOARD-REALIGNMENT-2026-08-25.md](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-SOVEREIGN-HOST-SHELL-AND-DASHBOARD-REALIGNMENT-2026-08-25.md) — Dual-Mode Shell & Dashboard Realignment
- [README.md](file:///Volumes/4TB-BAD/Halbert/documentation/sovereign-host-vision/README.md) — Sovereign Host 2.0 Vision Suite

---

## 1. Executive Summary & Paradigm Shift

For software to achieve genuine presence and authority, its brand cannot be an afterthought painted onto disjointed UI components. In Halbert, the visual language is an expression of its fundamental architectural truth:

> *"An LLM that identifies as the computer itself is fundamentally more useful than an LLM that merely answers questions about computers."*

Over the course of the project, Halbert explored multiple design trajectories. The creation of **`marketing/web-v7`** marked a decisive aesthetic breakthrough: it established the **Olivetti Vermilion & Bone** visual identity—a design language inspired by mid-century Italian and Swiss industrial computing, typography-first publishing, and tactile physical instrument panels.

Rather than building a brand style guide from scratch in isolation, **`marketing/web-v7` serves as the living interim Brand Style Guide**. It already renders miniature working app surfaces (`AppWindow`, `Pill`, `StatTile`, `VitalsPlate`, `WhyChipPlate`, `ScanPlate`).

This document details the complete roadmap to:
1. Formalize the core brand principles and aesthetic rules.
2. Standardize a shared 3-tier token system bridging Tailwind v4 and v3.
3. Audit the components in `web-v7` and map them to the desktop app.
4. Establish Storybook as the single source of truth for the entire organization.
5. Translate this identity into Halbert's Dual-Mode Desktop Shell.

---

## 2. Core Brand Principles: The Olivetti Vermilion & Bone Soul

Halbert rejects two pervasive industry clichés:
* **The Corporate SaaS Monotony:** Flat white cards, generic blue buttons, and sterile Sans-Serif fonts that look like an invoicing platform.
* **The Cyberpunk "Hacker" Trope:** Pitch-black backgrounds, lime green terminal text, and glowing neon borders that scream juvenile fantasy.

Instead, Halbert draws from the golden age of industrial computational design: **Marcello Nizzoli and Ettore Sottsass (Olivetti), Dieter Rams (Braun), Massimo Vignelli (NYC Subway & Unigrid), and the 1975 NASA Graphics Standards**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           THE FIVE BRAND PILLARS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. DAYLIGHT & PAPER (The Materiality of Thought)                          │
│      The canvas is warm, unbleached archival linen (#F7F4EE), evoking       │
│      physical engineering notebooks, punched cards, and daylight labs.      │
│                                                                             │
│   2. THE LETTERPRESS STROKE (Olivetti Vermilion #D34E24)                    │
│      A single, unmistakable mechanical orange-red used strictly for focal   │
│      intent, active pulse, and primary call-to-action. Never wallpaper.     │
│                                                                             │
│   3. EDITORIAL & COMPUTATIONAL TYPOGRAPHY                                   │
│      A strict triad: Humanist Serif (Fraunces), Modernist Sans (Space       │
│      Grotesk), and Tabular Engineering Monospace (JetBrains Mono).          │
│                                                                             │
│   4. INSTRUMENT TACTILITY (Plates, Trays & Hairlines)                       │
│      Windows are elevated plates with crisp 1px borders (rgba(26,25,24,0.12)│
│      and recessed data trays, feeling like precision laboratory instruments.│
│                                                                             │
│   5. HONESTY OF STATE & THE FOUR WHYS                                       │
│      Zero vanity metrics or decorative graphs. Every pixel represents real  │
│      telemetry, justified by Why Now, Why Care, Why So, and Why Trust.      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive Design Token Architecture

To bridge `marketing/web-v7` (built with Tailwind CSS v4 and `@theme`) and `halbert-dashboard` (built with Tailwind CSS v3 and `tailwind.config.js`), Halbert defines a **Universal CSS Custom Property Dictionary**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE 3-TIER TOKEN ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [ 1. PRIMITIVE TOKENS ] ──▶ [ 2. SEMANTIC TOKENS ] ──▶ [ 3. COMPONENT ]   │
│   Raw Hex, Base Fonts,        Canvas, Surface, Ink,       AppWindow Border, │
│   4px Grid Scale, Radii       Accent, Status Tones        WhyChip Background│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Color & Surface Hierarchy

> [!IMPORTANT]
> **The palette that was inlined here has moved.** The canonical dictionary is
> [`/shared-tokens/tokens.css`](file:///Volumes/4TB-BAD/Halbert/shared-tokens/tokens.css),
> verified in both themes by `python3 scripts/check_contrast.py`, with the rules
> governing it in
> [BRAND-GUIDELINES-AND-AESTHETIC.md](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md).
>
> The version inlined in this section was one of **three divergent palettes** in
> the repo, and several of its values did not pass the accessibility gate this
> same document specifies in §7 — the warning ochre measured 3.16:1, and white
> on the accent measured 4.30:1 against a stated 4.5:1 CTA floor. Reproducing
> values in a plan is how that drift happened, so the table is not restored
> here. See the Corrections Log in the brand guidelines for the full list.

---

## 4. Component Inventory & Audit (`web-v7` $\rightarrow$ Dashboard)

`marketing/web-v7/src/content/ui.jsx` already contains functional prototypes of core app surfaces. Here is the migration and formalization mapping:

| `web-v7` Component | Target Design System Component | Production Desktop Role |
|---|---|---|
| `AppWindow` | `AppWindow.tsx` / `Plate.tsx` | Universal container for dialogs, cards, and domain modules. |
| `Pill` | `StatusBadge.tsx` / `StateBadge.tsx` | Telemetry indicator pills (Nominal, Warning, Critical, Running). |
| `Btn` | `Button.tsx` (Radix Slot) | Primary Vermilion CTA, Outline secondary, and Ghost icon buttons. |
| `StatTile` | `MetricCard.tsx` | Live CPU, Memory, and ZFS Storage sensor cards. |
| `VitalsPlate` | `VitalsModule.tsx` | Host physiology inspection plate (temperatures, loads, memory). |
| `WhyChipPlate` | `WhyChip.tsx` | Clickable Four Whys provenance chip with slide-out drawer. |
| `ScanPlate` | `ScanBlock.tsx` | Real-time SourcePrep/RAG retrieval context streamer. |
| `ProactiveEventPlate`| `ProactiveEventCard.tsx` | Morning report and proactive interrupt proposal card. |
| *Missing (To Build)* | `Input.tsx`, `Textarea.tsx` | Tactile form fields matching `AppWindow` styling. |
| *Missing (To Build)* | `ParametricSlider.tsx` | Headroom preview slider for ZFS ARC and swappiness tuning. |
| *Missing (To Build)* | `TerminalTile.tsx` | Bone-canvas xterm.js theme with letterpress cursor. |

---

## 5. Storybook Monorepo Architecture

To ensure components are built, visually tested, and documented in total isolation before landing in production views, we establish **Storybook 8 with React & Vite**:

```
halbert/
├── shared-tokens/
│   └── tokens.css              <-- Single source of truth for design tokens
├── packages/
│   └── design-system/          <-- Shared component library & Storybook
│       ├── .storybook/
│       │   ├── main.js         <-- Storybook 8 Vite config
│       │   └── preview.jsx     <-- Global decorators, fonts, tokens.css import
│       ├── src/
│       │   ├── tokens/         <-- Color palettes, typography scales, rulers
│       │   ├── primitives/     <-- Buttons, Inputs, Pills, Sliders, Badges
│       │   ├── surfaces/       <-- AppWindow, DiffBlock, TerminalTile
│       │   └── modules/        <-- Vitals, Storage, EvidenceDrawer
│       └── package.json
├── marketing/web-v7/           <-- Imports @halbert/tokens & @halbert/design-system
└── halbert_core/dashboard/     <-- Imports @halbert/tokens & @halbert/design-system
```

### Story Taxonomy Structure:
1. **`Design Tokens /`**
   * `Color Palette`: Interactive swatches with contrast ratios and clipboard copy.
   * `Typography Hierarchy`: Type specimens across Fraunces, Space Grotesk, and JetBrains Mono.
   * `Elevation & Hairlines`: Border tests across dark and light surface tiers.
2. **`Primitives /`**
   * `Button`: Primary (Vermilion), Outline, Ghost, Disabled, and Loading states.
   * `Pill`: All 5 semantic tones with monospace telemetry labels.
   * `ParametricSlider`: Live interactive slider demonstrating RAM headroom recalculation.
3. **`Surfaces & Windows /`**
   * `AppWindow`: Resizable, collapsible instrument container.
   * `TerminalTile`: Live interactive PTY streaming tile with ANSI color support.
   * `DiffBlock`: AST unified diff view with `[Apply]` and `[Reject]` actions.
4. **`Modules /`**
   * `VitalsModule`: Live mock 1s tick sensor gauge.
   * `TerminalAccordionDock`: Collapsed and expanded accordion states with active PIDs.

---

## 6. The 5-Track Execution Roadmap

To execute this transition without stalling ongoing feature development, work is divided into **5 sequential research and implementation tracks**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         5-TRACK EXECUTION TIMELINE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [ Track 1: Brand Principles ] ──▶ [ Track 2: CSS Tokens ]                 │
│   Formalize voice & visual rules    Universal tokens.css file               │
│                                                   │                         │
│                                                   ▼                         │
│   [ Track 4: Storybook Setup ]  ◀── [ Track 3: Component Extraction ]       │
│   Storybook 8 + Vite in package     Audit & build core primitives           │
│         │                                                                   │
│         ▼                                                                   │
│   [ Track 5: Desktop Shell Realignment ]                                    │
│   Dual-Mode Switcher in Layout.tsx (Engaged Mode vs Browsing Dashboard)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Track 1: Brand Principles & Microcopy Codification
* **Goal:** Author the definitive brand guidelines document defining visual rules, voice, and tone.
* **Key Tasks:**
  - Codify the Olivetti Vermilion & Bone aesthetic principles.
  - Define rules of color restraint (Vermilion usage caps, dark mode charcoal guidelines).
  - Standardize Halbert's conversational microcopy (first-person computational embodiment).
* **Deliverable:** `documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md`. **DONE — 2026-08-26.**

### Track 2: Universal CSS Token Standardization
* **Goal:** Extract and formalize `shared-tokens/tokens.css` into a complete, zero-dependency token file.
* **Key Tasks:**
  - Expand surfaces, ink scales, telemetry tones, spacing, and radii.
  - Verify WCAG AA / AAA contrast across all surface and ink combinations.
  - Create the Tailwind v3 mapping (`tailwind.config.js`) for the desktop app and Tailwind v4 mapping (`@theme`) for marketing.
* **Deliverable:** `shared-tokens/tokens.css` and `halbert_core/.../tailwind.config.js` update. **DONE — 2026-08-26.**

### Track 3: Component Extraction & Primitive Library
* **Goal:** Extract prototypes from `marketing/web-v7/src/content/ui.jsx` into clean, production-ready React components with TypeScript types.
* **Key Tasks:**
  - Convert `AppWindow`, `Pill`, `Btn`, and `StatTile` to TypeScript.
  - Build missing form primitives: `Input`, `Select`, `ParametricSlider`.
  - Ensure full ARIA accessibility and keyboard navigation.
* **Deliverable:** `packages/design-system/src/primitives/`. **DONE — 2026-08-26.** Also `src/surfaces/`, 24 accessibility tests, and a `design-system` CI job.

### Track 4: Storybook Infrastructure Initialization
* **Goal:** Deploy a fully functional Storybook 8 development environment.
* **Key Tasks:**
  - Configure Storybook with `@storybook/react-vite`.
  - Import `tokens.css` and web fonts (`Fraunces`, `Space Grotesk`, `JetBrains Mono`).
  - Create stories for all tokens, primitives, and domain plates.
* **Deliverable:** Running Storybook accessible via `npm run storybook`. **DONE — 2026-08-26.** Includes a light/dark toolbar bound to `data-theme`, the a11y addon, and a live Contrast Audit story that recomputes every licensed pair in-browser.

### Track 5: Desktop App Shell Realignment
* **Goal:** Apply the design system to the live desktop application shell without breaking existing dashboard pages.
* **Key Tasks:**
  - Add the global Dual-Mode switcher to `Layout.tsx`:
    * **Mode 1: Engaged (Default):** Two-Column Sovereign Host Canvas.
    * **Mode 2: Browsing:** Full 17-tab System Dashboard.
  - Connect the `TerminalAccordionDock` to live backend PTY session streams.
  - Replace the generic cartoon robot on `/agent` with the embodied host status header.
* **Deliverable:** Live desktop app rendering the Olivetti Vermilion & Bone sovereign host interface. **DONE — 2026-08-26.**
* **Note on what was already built:** by the time this track was picked up, the
  sovereign-host workstream had already landed the dual-mode switcher
  (`ShellModeContext`, `ModeSwitch`, `Layout` branching on `isEngaged`), the
  `TerminalAccordionDock` wired to live PTY sessions via `useTerminalSessions`,
  and the embodied `/agent` surface. The remaining work was therefore the
  repaint, which is recorded in
  [BRAND-GUIDELINES-AND-AESTHETIC.md §10](file:///Volumes/4TB-BAD/Halbert/documentation/design/BRAND-GUIDELINES-AND-AESTHETIC.md).

---

## 7. Governance & Quality Gates

Every component and view in Halbert must satisfy three non-negotiable gates:

1. **Accessibility Gate (WCAG 2.1 AA/AAA):**
   - Body text (`--color-ink`) on canvas (`--color-canvas`) must exceed **7.0:1** (AAA standard).
   - Primary CTA buttons must maintain a minimum **4.5:1** contrast ratio.
2. **Computational Honesty Gate:**
   - No mock telemetry in production views. If a sensor is offline or unreadable, display an honest degraded status pill (`[Sensor Offline]`), never zero or simulated data.
3. **Motion Restraint Gate:**
   - Animations must feel like physical switches or optical shutters (crisp cubic-beziers, duration $\le 250\text{ms}$). No bouncy, cartoonish easing curves.
