# Implementation Plan: Halbert Marketing Webpage Build

**Date:** 2026-08-23  
**Status:** In Progress (Active Build Phase)  
**Target Environment:** Static Web (`marketing/web/`)  
**Stack:** Vite + React 19 + Tailwind CSS 4 + GSAP (ScrollTrigger) + Lenis + Lucide Icons  
**Design Standard:** `marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md` & `documentation/design/DESIGN-SYSTEM-SPEC.md`  

---

## 1. Executive Summary & Product Architecture

Build and deploy the desktop-first marketing landing page for Halbert in `marketing/web/`. The site introduces Halbert as a **local-first AI assistant that identifies as your computer**, utilizing the daylight mid-century modern design system (Olivetti Vermilion accent `#D34E24`, warm archival paper canvas `#F7F5F0`, geometric typography, and tactile daylight instruments).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PAGE NARRATIVE FLOW                               │
│                                                                             │
│  [ HEADER ]           Fixed glass, "Halbert." wordmark, Waitlist trigger    │
│       │                                                                     │
│  [ HERO ]             Headline, subhead, email capture, live TerminalFrame  │
│       │               playing "How are you doing?" dialogue                 │
│  [ HOW IT WORKS ]     Sticky 2-column scrollytelling with 3 desktop steps:  │
│       │               1. It knows itself (Vitals / Sensors)                 │
│       │               2. It remembers (AST Config Diff with "Why" tags)     │
│       │               3. It speaks (Conversational Command Spine)           │
│  [ THE SOUL ]         Centered philosophy statement + morning triage demo   │
│       │                                                                     │
│  [ FOOTER ]           Waitlist capture, local-first pledge, docs & legal    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technical Stack & Dependencies

- **Framework & Bundler:** Vite 6 + React 19
- **Styling Engine:** Tailwind CSS v4 via `@tailwindcss/vite` and `@theme` CSS custom properties in `shared-tokens/tokens.css`
- **Animation & Kinetics:** GSAP 3 with ScrollTrigger ticker synchronization
- **Smooth Scrolling:** Lenis with `prefers-reduced-motion` bypass
- **Iconography:** `lucide-react`
- **Typography & Font Loading Strategy:**
  - Google Fonts preconnect + preloaded `Instrument Sans` (Display), `Inter` (Body), and `JetBrains Mono` (Code).
  - `font-display: swap` for optimal performance.
- **Social Sharing & Meta:** OpenGraph card image (`og-image.png`), SVG favicon (`favicon.svg`), and Twitter summary card tags.
- **Deployment:** Netlify static build from `marketing/web/dist` with `netlify.toml`.

---

## 3. Five-Phase Execution Plan

### Phase 1: Project Scaffolding & Design Tokens
- Create `marketing/web/` directory structure.
- Initialize `package.json`, `vite.config.js`, `index.html`, `netlify.toml`.
- Configure `shared-tokens/tokens.css` with the daylight token ramp, Olivetti Vermilion accents, and motion easing curves.
- Setup `src/index.css` with film grain overlay and typography baseline.
- Setup `src/lib/useSmoothScroll.js` and `src/lib/demo-scripts.js`.

### Phase 2: Core Components & Hero Experience
- Build `TerminalFrame.jsx` with daylight warm titlebar, vintage stone window pips, and live heartbeat.
- Build `AnimatedCLI.jsx` execution engine with typing delays, tool call pills, and typewriter output.
- Build `Header.jsx` with geometric wordmark and waitlist navigation trigger.
- Build `Hero.jsx` with high-impact value proposition, email capture form, and live animated terminal playing the "How are you?" script.

### Phase 3: Scrollytelling Mechanics & Desktop Window Mockups
- Build `DesktopWindow.jsx` with macOS/neutral window chrome and split-pane layout.
- Build `HowItWorks.jsx` with 3-step scroll triggers:
  1. *Step 1: It knows itself* (Live CPU/RAM/NVMe vitals gauge).
  2. *Step 2: It remembers* (AST config diff with "Why" rationale annotations).
  3. *Step 3: It speaks* (Conversational dialogue with summoned storage module).

### Phase 4: The Soul Section & Footer
- Build `TheBeing.jsx` featuring the centered philosophy statement (*"The most helpful colleague you have, who happens to be your computer."*) and morning triage demo.
- Build `Footer.jsx` with secondary email capture, local-first privacy statement, doc links, and copyright.

### Phase 5: Polish, Form Validation, A11y & Static Build Verification
- Add robust email waitlist validation (empty input, invalid format, loading state, success confirmation).
- Audit `prefers-reduced-motion` compliance.
- Run `npm install` and `npm run build` to verify clean static bundling in `dist/`.

---

## 4. Acceptance Criteria & QA Checklist

- [x] Daylight paper palette (`#F7F5F0`) and Olivetti Vermilion (`#D34E24`) visually verified.
- [x] Animated CLI accurately executes scripts with typewriter rhythm and tool pills.
- [x] Scrollytelling steps smoothly pin and transition on scroll without layout shift.
- [x] Email waitlist captures submission and displays feedback state.
- [x] Zero build warnings or errors; production bundle built cleanly in `dist/`.
- [x] Full mobile and tablet responsiveness.
