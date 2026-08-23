# Handoff: Marketing Webpage Build & Formalized Design System

**Date:** 2026-08-23  
**Status:** Completed, Verified & Committed (`marketing/web/` + `documentation/design/`)  
**From:** Antigravity Visual Design Lead & Front-End Engineering Session  
**To:** Project Maintainers, Reviewers & Engineering Team  
**Repository Root:** `/Volumes/4TB-BAD/Halbert`  
**Latest Commits:**
- `16b795e` (`docs(design): establish formalized design system, component architecture, and marketing web plan`)
- `9f63a0e` (`feat(marketing): build and launch daylight marketing website with animated terminal and scrollytelling`)

---

## 1. Executive Summary & Context

This handoff document provides a comprehensive record of the design foundations and front-end engineering completed for **Halbert** on 2026-08-23. 

Halbert represents a fundamental paradigm shift in systems tooling: **an AI assistant that identifies as your computer**, speaking in the first person ("I logged three read errors on `/dev/sda1` this morning"), grounded in live telemetry, configuration history, and diagnostic truth.

During this session, we accomplished three major milestones:
1. **Formalized Design System:** Established a Daylight Mid-Century Modern design standard (inspired by late-1960s futurism, Dieter Rams / Braun, Olivetti, NASA 1975 graphic standards, and early Apple) across four foundational specifications.
2. **Addressed External Review Feedback:** Resolved contrast ratios, accessibility mitigations, component audits, and framework coexistence notes identified in [`HANDOFF-MARKETING-DESIGN-REVIEW-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-MARKETING-DESIGN-REVIEW-2026-08-23.md).
3. **Built & Verified the Marketing Web Application:** Implemented and compiled the complete, responsive, desktop-first marketing landing page in [`marketing/web/`](file:///Volumes/4TB-BAD/Halbert/marketing/web/) with interactive CLI and desktop demonstrators, smooth scrolling, and scrollytelling.

---

## 2. Complete Design System & Visual Foundations

The design language establishes clear differentiation from generic AI tools and dark-mode "cyberpunk" terminals:

```
                                  [ VISUAL DNA ]
  
        BRAUN / RAMS                OLIVETTI                  NASA STANDARDS (1975)
    Restraint & Honesty        Tactile Humanity & Soul        Precision Grid & Bold Vermilion
             │                            │                               │
             └────────────────────────────┼───────────────────────────────┘
                                          ▼
                             [ HALBERT VISUAL LANGUAGE ]
                         • Light, warm archival paper canvas (#F7F5F0)
                         • Single iconic Vermilion accent (#D34E24)
                         • Crisp 1px hairlines & geometric typography
                         • Human, friendly desktop computing
```

### 2.1 Color Palette & Surface Ramp

| Token Name | Hex Value | Role & Semantic Intent | WCAG Contrast on Canvas |
|---|---|---|---|
| `--color-canvas` | `#F7F5F0` | Default application & marketing background. Warm unbleached paper tone. | Base |
| `--color-surface` | `#FFFFFF` | Elevated cards, desktop window interiors, active popovers. | 1.09:1 (Ambient elevation) |
| `--color-surface-subtle` | `#EFECE4` | Recessed diagnostic panels, code boxes, terminal interiors. | Recessed |
| `--color-surface-muted` | `#E5E0D5` | Inactive segment pills, disabled button fills, progress tracks. | Divider tier |
| `--color-ink` | `#1A1918` | Primary body text, headings, terminal user prompts, agent speech. | **16.11:1 (AAA)** |
| `--color-ink-secondary` | `#5E5B56` | Secondary prose, timestamps, telemetry metadata, tool arguments. | **6.20:1 (AA)** |
| `--color-ink-tertiary` | `#8C877D` | Captions, shortcut badges, inactive tabs, subtle borders. | 3.28:1 |
| `--color-ink-ghost` | `#B8B2A6` | Decorative placeholder text, guidelines, disabled icons. | 1.92:1 |
| `--color-accent` | `#D34E24` | **Signature Accent:** Olivetti Vermilion / NASA Red. CTA buttons, active focus. | 4.30:1 |
| `--color-accent-hover` | `#B83E18` | Darkened vermilion for hover and high-contrast button states. | **5.61:1 (AA)** |
| `--color-accent-tint` | `#FDF2EE` | Soft 8% vermilion background wash for active badges and tool highlights. | Accent wash |

#### Telemetry Semantics:
- **Nominal / Healthy (`--color-status-success`):** `#2D7A56` (Eames Forest Green) · Tint: `#EEF6F2`
- **Caution / Attention (`--color-status-warning`):** `#C4781C` (Braun Amber Ochre) · Tint: `#FDF8F0`
- **Critical / Danger (`--color-status-error`):** `#C83E2D` (Terracotta Crimson) · Tint: `#FDF2F0`
- **Diagnostic / RAG (`--color-status-info`):** `#386C8A` (Blueprint Slate Teal) · Tint: `#F0F6F9`

### 2.2 Typography & The "Al" / "AI" Visual Pun

The primary tagline is:
> **"Halbert. You can call me AI."**

- **Display Stack:** `Instrument Sans`, `Plus Jakarta Sans`, `-apple-system`, `sans-serif` (tight tracking `-0.035em`, geometric proportions with warm open counters).
- **Body Stack:** `Inter`, `-apple-system`, `sans-serif` (high x-height, maximum legibility, line height `1.6`).
- **Code & Telemetry Stack:** `JetBrains Mono`, `SF Mono`, `Menlo`, `monospace` (tabular numbers, clear distinction between `0`/`O` and `1`/`l`/`I`).
- **Tagline Visual Rhyme:** In geometric sans-serif typefaces, the uppercase letter **`I`** and lowercase letter **`l`** share identical vertical stem characteristics. The name **`Halbert`** contains the substring **`al`**, visually mirroring the **`AI`** in the tagline without requiring distracting graphic overlays.

### 2.3 Motion & Kinetic Tokens
- `--ease-hero`: `cubic-bezier(0.16, 1, 0.3, 1)` (Snappy Leica entrance curve)
- `--ease-smooth`: `cubic-bezier(0.25, 1, 0.5, 1)` (Scrollytelling module crossfades)
- `--ease-mechanical`: `cubic-bezier(0.32, 0.72, 0, 1)` (Physical switch and drawer reveals)
- `--ease-micro`: `cubic-bezier(0.2, 0, 0, 1)` (Button hover and tap states)
- Full `prefers-reduced-motion: reduce` fallback bypassing all transform animations and smooth scrolling.

---

## 3. Marketing Web Application Architecture (`marketing/web/`)

The marketing site was scaffolded and built from scratch using Vite 6, React 19, Tailwind CSS 4, GSAP, and Lenis:

```
marketing/web/
├── package.json               # Dependencies (React 19, Tailwind 4, GSAP, Lenis, Lucide)
├── vite.config.js             # Vite + Tailwind v4 + path aliases
├── index.html                 # Google Fonts preconnect, OpenGraph meta, SVG favicon
├── netlify.toml               # Netlify deployment directives
├── shared-tokens/
│   └── tokens.css             # Tailwind 4 @theme token scaffold
├── public/
│   └── favicon.svg            # Dual-ring Vermilion favicon
└── src/
    ├── main.jsx               # React application entrypoint
    ├── App.jsx                # Master page layout & scroll orchestrator
    ├── index.css              # Global styles, noise overlay, typography
    ├── lib/
    │   ├── demo-scripts.js    # Event scripts (howAreYou, enableCompression, whatChanged, proactiveAlert)
    │   └── useSmoothScroll.js # Lenis + GSAP ScrollTrigger ticker integration
    └── components/
        ├── Header.jsx         # Fixed glass header with "Halbert." wordmark and waitlist trigger
        ├── Hero.jsx           # Value prop, waitlist capture form, platform badges, live terminal
        ├── TerminalFrame.jsx  # Daylight precision instrument frame with stone titlebar pips
        ├── AnimatedCLI.jsx    # Typewriter engine with tool execution pills and pause loops
        ├── DesktopWindow.jsx  # Tauri desktop frame with traffic lights and segmented tabs
        ├── HowItWorks.jsx     # Sticky scrollytelling section (Vitals, Config Diff, Conversational Spine)
        ├── TheBeing.jsx       # The Soul philosophy center + morning triage live demo
        └── Footer.jsx         # Secondary email capture, local-first pledge, docs links, copyright
```

### 3.1 Interactive Demonstrators & Component Breakdown

#### `TerminalFrame.jsx` & `AnimatedCLI.jsx`
- Replaces the cliché black hacker terminal with a daylight precision instrument: warm titlebar (`#F4F0E8`), three stone-tinted window controls, live heartbeat indicator, and clear monospace dialogue.
- Engine executes `CliScript` event loops step-by-step:
  - `user_input`: Realistic keystroke delays (`30ms - 35ms`).
  - `tool_call`: Inset status pills in subtle vermilion/gray with active spinner.
  - `tool_result`: Formatted result chips (success botanical green / warning amber ochre).
  - `agent_output`: First-person speech typed out character-by-character with natural breath pauses.
  - Loops seamlessly with configurable delay (`loopDelayMs: 6000`).

#### `Hero.jsx`
- Viewport layout (`min-h-[92svh]`) featuring:
  - Eyebrow badge: `LOCAL-FIRST HOST INTELLIGENCE`.
  - Headline: `Your computer has something to say.`
  - Subhead: `A local-first AI assistant that knows your machine — because it is your machine.`
  - Tagline quote: `"Halbert. You can call me AI."`
  - Inline waitlist email capture form with validation, submitting spinner, and success state.
  - Platform support badges: `100% Local (Ollama)`, `macOS & Linux`, `Zero Cloud Telemetry`.
  - Live `AnimatedCLI` executing the `"How are you doing?"` founding ethos script.

#### `HowItWorks.jsx`
- Two-column scrollytelling stage:
  - **Left column:** 3 interactive step cards with click & scroll synchronization.
  - **Right column:** Sticky `DesktopWindow.jsx` dynamically rendering live HTML/CSS mockups:
    - *Step 1: It knows itself* (Live CPU temp 45°C, load average 0.15, NVMe health gauges).
    - *Step 2: It remembers* (AST config diff for `/etc/ssh/sshd_config.d/50-custom.conf` with "Why So" rationale tags).
    - *Step 3: It speaks* (Conversational dialogue with summoned storage diagnostic module).

#### `TheBeing.jsx`
- The emotional and philosophical climax of the page:
  - Centered quote: *“The most helpful colleague you have, who happens to be your computer.”*
  - Live demonstrator running `proactiveAlert` (overnight backup failure alert, kernel update notice, sshd drift triage).
  - 3 philosophical pillars: First-Person Voice, Zero Disclaimers, Safe Autonomy.

#### `Header.jsx` & `Footer.jsx`
- Fixed glass header with `"Halbert."` wordmark, release pill `v2026.8`, and smooth-scroll Early Access trigger.
- Footer featuring secondary email capture, architectural badges (Tauri, Ollama, SourcePrep, Polkit), and local-first open source pledge.

---

## 4. Resolution of Review Feedback

We audited and addressed all items raised in [`HANDOFF-MARKETING-DESIGN-REVIEW-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HANDOFF-MARKETING-DESIGN-REVIEW-2026-08-23.md):

| Review Item | Finding / Critique | Resolution & Action Taken |
|---|---|---|
| **Status Labels** | Marked "Approved" prematurely before user review | Updated all documents to `Active Specification (Web Build Standard)` or `Draft — Pending Review`. |
| **Accent Contrast** | White on Vermilion (`#D34E24`) is 4.30:1 (below 4.5:1 for normal text) | Documented mitigation in `DESIGN-SYSTEM-SPEC.md`: CTA buttons use `font-semibold` / `font-bold` at $\ge 16\text{–}18\text{px}$, or `--color-accent-hover: #B83E18` (5.61:1 AA). |
| **Component Audit** | `ThinkingPanel` described as pulsing loader; `ToolExecutionCard` proposed as new when it already exists | Corrected description: `ThinkingPanel` is a collapsible streaming text panel; noted that `ToolExecutionCard.tsx` already exists (3.7KB) and will be restyled for daylight mode in desktop. |
| **File Naming** | Review noted kebab-case vs PascalCase | Audited and aligned component references (`why-overlay.tsx`, `why-brain.tsx`). |
| **Framework Coexistence** | Tailwind 4 (Marketing) vs Tailwind 3 (Desktop) + Karla vs Inter | Added explicit framework coexistence matrix to `DESIGN-SYSTEM-SPEC.md` (§3.6). Token sharing is unified conceptually via semantic tokens; desktop refactoring is isolated to its own workstream. |
| **Workstream Scope** | Design docs covered desktop app refactoring alongside marketing | Explicitly scoped immediate deliverables to the marketing web application (`TerminalFrame`, `AnimatedCLI`, `DesktopWindow`, `WaitlistCapture`); desktop app refactoring is clearly partitioned. |
| **Implementation Plan Detail** | `IMPLEMENTATION-PLAN-WEB-BUILD` lacked phases and script references | Enriched plan with the full 5-phase breakdown, script integration, font loading strategy, and QA acceptance checklist. |

---

## 5. Formalized Design System Documentation Suite

All foundational design documents are committed under [`documentation/design/`](file:///Volumes/4TB-BAD/Halbert/documentation/design/) and indexed in [`README.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/README.md):

1. **[`DESIGN-SYSTEM-SPEC.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/DESIGN-SYSTEM-SPEC.md)**  
   *Foundational Token Architecture, Surface Taxonomy, Ink Hierarchy, Signature Accent, Telemetry Semantics, Modular Typography, Spatial Grid, and Motion Curves.*

2. **[`COMPONENT-ARCHITECTURE.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/COMPONENT-ARCHITECTURE.md)**  
   *Component Taxonomy (Atoms, Molecules, Organisms, Layout Stages), Existing Desktop Component Audit, and Full Prop Interfaces for New Components.*

3. **[`USER-JOURNEY-METHODOLOGY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/USER-JOURNEY-METHODOLOGY.md)**  
   *Attention Economics, Cognitive Load Budgets, Law of Four Whys Matrix, and 5 Detailed End-to-End User Workflows (First Boot, Reactive Query, Proactive Triage & Approval Gate, Config Archeology, Marketing Funnel).*

4. **[`DOMAIN-MODULES-AND-WHY-MECHANICS.md`](file:///Volumes/4TB-BAD/Halbert/documentation/design/DOMAIN-MODULES-AND-WHY-MECHANICS.md)**  
   *Dynamic Module Summoning Lifecycle FSM, 5 Domain Modules (Vitals, ConfigDiff, StorageSensors, EvidenceDrawer, ApprovalRollback), and `WhyPayload` Data Contracts.*

5. **[`marketing/MARKETING-WEBPAGE-PLAN-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/marketing/MARKETING-WEBPAGE-PLAN-2026-08-23.md)**  
   *Master marketing webpage strategy, brand voice, and demo script definitions.*

6. **[`marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md)**  
   *Visual design direction document establishing the late-1960s futurist daylight aesthetic.*

7. **[`marketing/creative-concepts/you-can-call-me-ai.md`](file:///Volumes/4TB-BAD/Halbert/marketing/creative-concepts/you-can-call-me-ai.md)**  
   *Creative concept and legal analysis for the tagline "Halbert. You can call me AI."*

8. **[`marketing/IMPLEMENTATION-PLAN-WEB-BUILD-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/marketing/IMPLEMENTATION-PLAN-WEB-BUILD-2026-08-23.md)**  
   *Step-by-step engineering plan for the static web build.*

---

## 6. Build Verification & Quality Assurance

The marketing web application was verified with automated build tooling:

```bash
cd /Volumes/4TB-BAD/Halbert/marketing/web
npm install
npm run build
```

### Verification Results:
- **Dependencies:** 82 packages installed with **0 vulnerabilities**.
- **Vite Build Output:**
  ```
  vite v6.4.3 building for production...
  ✓ 1832 modules transformed.
  rendering chunks...
  computing gzip size...
  dist/index.html                   1.84 kB │ gzip:   0.81 kB
  dist/assets/index-Cg6MigQe.css   28.96 kB │ gzip:   6.08 kB
  dist/assets/index-BxQQ8E-l.js   370.32 kB │ gzip: 121.81 kB
  ✓ built in 1.65s
  ```
- **Zero Errors / Zero Warnings:** Output builds cleanly to `dist/` ready for Netlify or static deployment.
- **Git State:** All source code and documentation committed cleanly to `main` (`9f63a0e`).

---

## 7. Next Steps & Recommended Follow-Ups

1. **Deploy to Netlify:** Connect `marketing/web/` to Netlify with domain `halbert.ai`.
2. **Form Backend:** Ensure Netlify Forms or a webhook destination is configured for the `waitlist` form submissions.
3. **Desktop App Refactoring Workstream (Post-Marketing):**
   - Refactor `AgentChat.tsx` $\rightarrow$ `AgentSpine.tsx` with daylight tokens.
   - Deconstruct `SidePanel.tsx` into summonable modules (`VitalsModule`, `StorageSensorsModule`, `EvidenceDrawer`).
   - Implement the `ApprovalGate.tsx` component with Polkit privilege elevation support.
