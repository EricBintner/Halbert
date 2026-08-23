# Implementation Plan: Halbert Marketing Webpage Build

**Date:** 2026-08-23  
**Status:** Ready for External Review & Feedback Handoff  
**Target Environment:** Static Web (`marketing/web/`)  
**Stack:** Vite + React 19 + Tailwind CSS 4 + GSAP (ScrollTrigger) + Lenis  
**Design Standard:** `marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md` & `documentation/design/DESIGN-SYSTEM-SPEC.md`  

---

## 1. Executive Summary & Goals

Build and launch the desktop-first marketing landing page for Halbert located at `marketing/web/`. The site introduces Halbert as a **local-first AI assistant that identifies as your computer**, utilizing the daylight mid-century modern design system (Olivetti Vermilion accent `#D34E24`, warm archival paper canvas `#F7F5F0`, geometric typography, and tactile daylight instruments).

---

## 2. Technical Stack & Architecture

- **Bundler & Framework:** Vite + React 19
- **Styling Engine:** Tailwind CSS v4 via `@tailwindcss/vite` and `@theme` CSS custom properties
- **Animation & Kinetics:** GSAP 3 with ScrollTrigger ticker integration
- **Smooth Scroll:** Lenis (`lenis`) with `prefers-reduced-motion` bypass
- **Icons:** `lucide-react`
- **Deployment:** Netlify static build from `marketing/web/dist`

---

## 3. Component Architecture & File Manifest

### 3.1 Project Scaffolding & Configuration
- [`marketing/web/package.json`](file:///Volumes/4TB-BAD/Halbert/marketing/web/package.json): Core dependencies & scripts (`build`, `dev`, `preview`).
- [`marketing/web/vite.config.js`](file:///Volumes/4TB-BAD/Halbert/marketing/web/vite.config.js): Tailwind v4 plugin integration & path resolution.
- [`marketing/web/index.html`](file:///Volumes/4TB-BAD/Halbert/marketing/web/index.html): HTML shell with Google Fonts (`Instrument Sans`, `Inter`, `JetBrains Mono`).
- [`marketing/web/netlify.toml`](file:///Volumes/4TB-BAD/Halbert/marketing/web/netlify.toml): Netlify build & publish directives.

### 3.2 Tokens & Global Styles
- [`marketing/web/shared-tokens/tokens.css`](file:///Volumes/4TB-BAD/Halbert/marketing/web/shared-tokens/tokens.css): Daylight design tokens, surface ramp, Vermilion accents, and motion curves.
- [`marketing/web/src/index.css`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/index.css): Global rules, film grain overlay, and reduced-motion fallbacks.

### 3.3 Engine & Script Definitions
- [`marketing/web/src/lib/demo-scripts.js`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/lib/demo-scripts.js): Halbert-specific conversation playback scripts (`howAreYou`, `enableCompression`, `whatChanged`, `proactiveAlert`).
- [`marketing/web/src/lib/useSmoothScroll.js`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/lib/useSmoothScroll.js): Lenis smooth scrolling with GSAP ticker hook.

### 3.4 Page Components
- [`marketing/web/src/components/Header.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/Header.jsx): Translucent glass header with "Halbert." wordmark and waitlist trigger.
- [`marketing/web/src/components/Hero.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/Hero.jsx): Viewport hero with headline, value prop, waitlist capture, and live animated terminal.
- [`marketing/web/src/components/TerminalFrame.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/TerminalFrame.jsx): Daylight instrument terminal frame with stone titlebar pips and live status.
- [`marketing/web/src/components/AnimatedCLI.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/AnimatedCLI.jsx): Event loop typewriter playback engine.
- [`marketing/web/src/components/DesktopWindow.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/DesktopWindow.jsx): Tauri host desktop frame for split-pane previews.
- [`marketing/web/src/components/HowItWorks.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/HowItWorks.jsx): Sticky scrollytelling section with 3 interactive steps (Vitals, Config Diff, Conversational Spine).
- [`marketing/web/src/components/TheBeing.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/TheBeing.jsx): Soul section with philosophy statement and morning report demo.
- [`marketing/web/src/components/Footer.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/components/Footer.jsx): Minimalist mid-century footer.
- [`marketing/web/src/App.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/App.jsx): Master page container orchestrating GSAP contexts.
- [`marketing/web/src/main.jsx`](file:///Volumes/4TB-BAD/Halbert/marketing/web/src/main.jsx): React application bootstrap.

---

## 4. Verification & QA Plan

1. **Automated Verification:**
   - Run `npm install` inside `marketing/web/`.
   - Run `npm run build` to verify clean compilation with zero warnings/errors.
   - Run `npm run preview` to verify static production asset delivery.
2. **Visual & Interaction Verification:**
   - Daylight palette and typography hierarchy rendering correctly.
   - Terminal typewriter animation smoothly looping.
   - Scrollytelling scroll pins cleanly transitioning across steps.
   - Email waitlist form handling input validation and success state.
   - Complete `prefers-reduced-motion` compliance.
