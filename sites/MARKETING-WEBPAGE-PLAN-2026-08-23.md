# Marketing Webpage — Implementation Plan

**Date:** 2026-08-23
**Status:** Ready for Build (visual design direction delivered in `marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md`)

---

## 1. Product summary (what we're marketing)

Halbert is a **local-first AI assistant that identifies as your computer.** It runs on your machine using local LLMs (Ollama by default, cloud optional), ingests system logs and configs, and answers questions grounded in real system data — speaking in first person ("I'm worried about `/dev/sda1`; I logged three read errors this morning").

It is a **desktop application** (Tauri + web dashboard). There is no mobile app. All marketing imagery is desktop.

**Core value props:**
1. **The computer talks back** — first-person, grounded, no disclaimers. The LLM *is* the machine.
2. **Local-first** — runs on Ollama, no cloud required. Your system data never leaves your machine.
3. **System-aware** — ingests journald logs, hardware sensors, config files, knows its own state.
4. **RAG-powered** — answers grounded in 16K+ macOS/BSD/Linux docs (SourcePrep retrieval).
5. **Safe by default** — dry-run mode, approval system, policy engine, audit logs.
6. **It remembers** — config history, rationale ("why is it configured this way"), past incidents.

**Tagline:** "Halbert. You can call me AI." (see `marketing/creative-concepts/you-can-call-me-ai.md`)

---

## 2. Design direction (to be handed off to visual-design AI)

### What's decided

| Decision | Value | Rationale |
|----------|-------|-----------|
| Color scheme | **Light** | User directive. Apple-like, not sci-fi. |
| Brand voice | **Apple-like, less sci-fi** | Approachable, confident, human. Not "deploy to the mothership." |
| Visual era | **Late 1960s futurist + mid-century modern** | Optimistic, clean, geometric. Eames, Braun, early NASA graphic standards, Olivetti. |
| Imagery | **All desktop** | Halbert is a desktop app. No phone mockups. |
| Structure | **Like ApplicationBrowser marketing** | Single-page scroll: Hero → scrollytelling sections → soul section → footer. |
| Animations | **Steal CLI/IDE animations from CoDRAG** | AnimatedCLI + AnimatedIDE components, adapted to Halbert's conversation interface. |

### What the visual-design AI needs to produce

The visual-design AI should deliver a **design direction document** (not code) covering:

1. **Color palette** — light canvas, ink, accent, surface ramp, hairlines. Inspired by late-60s futurism: warm off-whites, muted primaries (mustard, teal, brick, or a single accent), not neon. Reference: Olivetti typewriter reds, Braun orange, Eames fiberglass palette.

2. **Typography** — display face + body face + mono. Mid-century modern leans geometric (Futura, Avenir, Gotham) or humanist sans. The Al/AI visual pun in the tagline depends on typeface choice — this is a hard constraint the design must satisfy.

3. **Layout grid** — content widths, section rhythm, whitespace philosophy. Mid-century modern advertising used generous whitespace, strong horizontal rules, asymmetric balance.

4. **Component visual language** — how the terminal/IDE animation frame looks in a light theme (currently dark in CoDRAG), how the dashboard mockup is presented, hairline vs. shadow depth strategy.

5. **Motion philosophy** — GSAP easing tokens, scroll behavior, reveal patterns. Calm and confident, not flashy.

6. **Iconography / marks** — the Halbert wordmark and any logomark. The name is Hal + Albert; the " Layers" mark from ApplicationBrowser is not ours.

### Era reference mood board (for the design AI)

- **Olivetti** advertising (1960s) — typewriters and early computers marketed as friendly, domestic, human
- **Braun** product photography (Dieter Rams) — restraint, honesty of materials
- **NASA Graphic Standards Manual** (1975, but rooted in 60s futurism) — the worm logotype, clean grid, optimistic red
- **Eames** fiberglass chairs — color as accent on neutral forms
- **Saul Bass** title sequences — geometric, confident, minimal
- **Early Apple** (1984 era, but the lineage) — the computer as a person, not a machine

The throughline: **technology presented as warm, human, and optimistic — the future as a friendly colleague, not a cold mainframe.** This maps perfectly onto Halbert's "the most helpful colleague you have, who happens to be your computer."

---

## 3. Technical stack

### Recommendation: Vite + React + Tailwind 4 + GSAP + Lenis

Match the ApplicationBrowser marketing stack exactly. Rationale:

- **Vite + React 19** — fast dev, simple deploy (static build to Netlify). Halbert's dashboard frontend is already Vite + React, so the team knows the tooling.
- **Tailwind 4** — the `@theme` token system in ApplicationBrowser's `shared-tokens/tokens.css` is the cleanest way to define brand tokens and have them flow into utilities. We mirror this structure.
- **GSAP + ScrollTrigger** — the scrollytelling in ApplicationBrowser (sticky Mac, scroll-driven step transitions, matchMedia for reduced-motion) is exactly the pattern we need. Reuse the approach.
- **Lenis** — smooth scroll, already used in ApplicationBrowser. Optional but nice.

**Not Next.js.** The CoDRAG marketing site is Next.js because it has many pages (blog, pricing, compare, docs). Halbert's marketing is a single landing page (+ maybe privacy/terms). Vite is simpler and ships faster.

### Project location

```
marketing/
  creative-concepts/
    you-can-call-me-ai.md          (exists)
  MARKETING-WEBPAGE-PLAN-2026-08-23.md  (this file)
  web/                             (to be created during build)
    shared-tokens/
      tokens.css                   (brand tokens — light palette, defined by visual-design AI)
    src/
      main.jsx
      App.jsx
      index.css
      components/
        Header.jsx
        Hero.jsx
        ConversationDemo.jsx       (the CLI/IDE animation, adapted)
        HowItWorks.jsx             (scrollytelling sections)
        TheBeing.jsx               (the "soul" section — the computer talks back)
        Footer.jsx
        TerminalFrame.jsx          (ported from CoDRAG, re-themed for light)
        DesktopWindow.jsx          (Mac window frame, like ApplicationBrowser's MacWindow)
      lib/
        useSmoothScroll.js
        demo-scripts.ts            (Halbert conversation scripts — see §5)
    index.html
    package.json
    vite.config.js
    netlify.toml
```

---

## 4. Page structure (section-by-section)

Modeled on ApplicationBrowser's `App.jsx` flow: Header → Hero → ProblemSolution → TheSoul → Footer.

### Header
- Fixed, translucent, hairline bottom border.
- Wordmark left ("Halbert" — with the Al/AI visual pun baked into the typeface).
- Right: "Coming Soon" pill or a "Join the waitlist" link (TBD based on launch state).

### Hero
- Full viewport (`min-h-[100svh]`), centered.
- **No device mockup in the hero.** Halbert's hero asset is the *conversation* — a live animated terminal/chat showing Halbert speaking in first person. This is the product's soul: the computer talks back.
- Layout: wordmark or logomark at top → headline → subhead → animated conversation demo below or beside.
- Headline candidates (to be finalized with copy):
  - "Your computer has something to say."
  - "The computer that talks back."
  - "Halbert. You can call me AI." (tagline as hero headline)
- Subhead: "A local-first AI assistant that knows your machine — because it *is* your machine."
- GSAP entrance: text line reveal + the conversation demo fades in and begins playing.

### ConversationDemo (the signature animation)
- This is the port of CoDRAG's `AnimatedCLI` / `AnimatedIDE`, re-themed for light mode and re-scripted for Halbert's voice.
- **Two variants to build:**
  1. **Terminal variant** — a terminal window showing a user asking a system question and Halbert responding in first person with grounded data. (Port of `AnimatedCLI` + `TerminalFrame`.)
  2. **IDE/dashboard variant** — a split-pane showing the conversation on one side and a live dashboard module (storage, network, config diff) on the other. (Port of `AnimatedIDE`, restyled.)
- The animation loops. Scripts are defined in `demo-scripts.ts` (see §5).
- **Light-theme re-skin:** the CoDRAG components are hardcoded to dark hex values (`#1e1e1e`, `#c9d1d9`, etc.). These need to become token-driven (`bg-canvas`, `text-ink`, etc.) so the light palette flows through. The terminal frame in a light theme should look like a warm paper-colored window with a thin frame — mid-century modern, not a black hacker terminal.

### HowItWorks (scrollytelling)
- Direct adaptation of ApplicationBrowser's `ProblemSolution.jsx`: two-column sticky layout on desktop, stacked on mobile.
- Left column: text steps that fade in/out as you scroll. Right column: sticky desktop window showing the relevant UI.
- **3 steps** (draft):
  1. **"It knows itself."** — Halbert reads its own logs, sensors, and configs. Desktop mockup: dashboard with system overview (CPU temp, disk health, uptime) rendered as Halbert's "vitals."
  2. **"It remembers."** — Config history, rationale, past incidents. Desktop mockup: a config diff view with "why" annotations ("You enabled compression on 2026-08-15 to improve I/O").
  3. **"It speaks."** — The conversation as the core interface. Desktop mockup: the conversation view with a summoned storage module.
- All mockups are desktop windows (Tauri app frames), not phones.

### TheBeing (soul section)
- Adaptation of ApplicationBrowser's `TheSoul.jsx`.
- A single centered statement of the product's philosophy, with one large animated conversation moment.
- Copy center: **"The most helpful colleague you have, who happens to be your computer."**
- Below: a single animated terminal showing the founding ethos exchange:
  > User: "How are you doing?"
  > Halbert: "I'm ubuntu-server-01. I've been up 42 days. My primary drive logged three read errors this morning — I'd keep an eye on that. Otherwise, I'm running cool and quiet."
- This is the emotional payoff of the page. The section that makes you *feel* the product.

### Footer
- Minimal. Wordmark, links (GitHub, docs, privacy, terms), copyright.
- Mid-century modern footer: strong horizontal rule, generous whitespace, small confident type.

---

## 5. Demo scripts (the conversation animations)

Port the `CliScript` type from CoDRAG's `cli-types.ts`. Write Halbert-specific scripts in `demo-scripts.ts`.

### Script 1: "How are you?" (the founding ethos — hero or soul section)

```typescript
const howAreYou: CliScript = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 6000,
  events: [
    { type: 'user_input', text: 'how are you doing?', typingDelayMs: 30 },
    { type: 'agent_thinking', durationMs: 800 },
    { type: 'tool_call', tool: 'read_sensors', args: '', durationMs: 700, statusText: 'Checking vitals…' },
    { type: 'tool_result', text: 'CPU 45°C · load 0.15 · disk /dev/nvme0n1 healthy', status: 'success' },
    { type: 'pause', durationMs: 300 },
    { type: 'tool_call', tool: 'query_memory', args: '"recent incidents"', durationMs: 600, statusText: 'Recalling…' },
    { type: 'tool_result', text: '3 read errors on /dev/sda1 at 08:00 today', status: 'success' },
    { type: 'pause', durationMs: 400 },
    {
      type: 'agent_output',
      text: "I'm ubuntu-server-01. I've been up 42 days. CPU is cool at 45°C, load is light.\n\nOne thing though — I logged three read errors on /dev/sda1 this morning. I'd keep an eye on that drive. Want me to schedule a SMART test?",
      typewriterDelayMs: 14,
    },
  ],
};
```

### Script 2: "Enable compression" (config as physiology — how-it-works step 1)

```typescript
const enableCompression: CliScript = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 5000,
  events: [
    { type: 'user_input', text: 'can we enable compression on the data volume?', typingDelayMs: 28 },
    { type: 'agent_thinking', durationMs: 700 },
    { type: 'tool_call', tool: 'read_config', args: '/etc/fstab', durationMs: 600, statusText: 'Reading my configuration…' },
    { type: 'tool_result', text: '/dev/nvme0n1 · bcachefs · compression=none', status: 'success' },
    { type: 'pause', durationMs: 300 },
    {
      type: 'agent_output',
      text: "I checked my fstab — I'm currently mounted with compression off. Enabling lz4 is safe for our workload and I can do it live without unmounting.\n\nShall I run a benchmark first, or go ahead and enable it?",
      typewriterDelayMs: 14,
    },
  ],
};
```

### Script 3: "What changed?" (it remembers — how-it-works step 2)

```typescript
const whatChanged: CliScript = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 5000,
  events: [
    { type: 'user_input', text: 'why is ssh on port 2222?', typingDelayMs: 28 },
    { type: 'agent_thinking', durationMs: 600 },
    { type: 'tool_call', tool: 'query_memory', args: '"ssh port change rationale"', durationMs: 800, statusText: 'Recalling…' },
    { type: 'tool_result', text: 'Changed 2026-07-14 · reason: "avoid scan noise on default port"', status: 'success' },
    { type: 'pause', durationMs: 300 },
    {
      type: 'agent_output',
      text: "I moved SSH to port 2222 on July 14th. You told me to — the auth log was filling up with scan attempts on port 22. It's been quiet since.\n\nThe change is in /etc/ssh/sshd_config. Want to see the diff?",
      typewriterDelayMs: 14,
    },
  ],
};
```

### Script 4: IDE variant — proactive interrupt (the being section)

For the `AnimatedIDE` port — shows the conversation + a summoned dashboard module:

```typescript
const proactiveAlert: CliScript = {
  title: 'halbert — ubuntu-server-01',
  loop: true,
  loopDelayMs: 6000,
  events: [
    { type: 'user_input', text: 'good morning. anything I should know?', typingDelayMs: 26 },
    { type: 'agent_thinking', durationMs: 800 },
    { type: 'tool_call', tool: 'triage', args: '', durationMs: 1000, statusText: 'Reviewing overnight logs…' },
    { type: 'tool_result', text: '1 urgent · 2 attention · 14 nominal', status: 'success' },
    { type: 'pause', durationMs: 400 },
    {
      type: 'agent_output',
      text: "Morning. One thing needs your attention: my backup job failed at 3am — the destination volume was full. I've queued a retry after you clear some space.\n\nTwo smaller things: a new kernel update is available, and I noticed sshd_config drifted from what you set last month. Want me to walk through both?",
      typewriterDelayMs: 14,
    },
  ],
};
```

---

## 6. Brand tokens (finalized — from `marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md`)

The visual-design direction delivers the finalized `@theme` block below (ready for `marketing/web/shared-tokens/tokens.css`):

```css
@theme {
  /* ===== Surface ramp (light — warm archival paper canvas) ===== */
  --color-canvas:            #F7F5F0;   /* page canvas — warm archival paper */
  --color-surface:           #FFFFFF;   /* raised cards, window interiors */
  --color-surface-subtle:    #EFECE4;   /* terminal canvas, recessed panels */
  --color-surface-muted:     #E5E0D5;   /* inactive controls, pill tags */

  /* ===== Primary signature accent (Olivetti Vermilion) ===== */
  --color-accent:            #D34E24;   /* 60s futurist vermilion accent */
  --color-accent-hover:      #B83E18;   /* deep vermilion for hover states */
  --color-accent-tint:       #FDF2EE;   /* soft vermilion wash */

  /* ===== Ink hierarchy (warm charcoal & graphite) ===== */
  --color-ink:               #1A1918;   /* deep carbon black text */
  --color-ink-secondary:     #5E5B56;   /* secondary metadata, timestamps */
  --color-ink-tertiary:      #8C877D;   /* captions, hairline markers */
  --color-ink-ghost:         #B8B2A6;   /* disabled text, grid lines */

  /* ===== Functional telemetry accents (desaturated 60s palette) ===== */
  --color-status-success:    #2D7A56;   /* Eames forest green */
  --color-status-warning:    #C4781C;   /* Braun amber ochre */
  --color-status-error:      #C83E2D;   /* terracotta brick red */
  --color-status-info:       #386C8A;   /* blueprint slate teal */

  /* ===== Hairlines & elevation ===== */
  --color-hairline:          rgba(26, 25, 24, 0.08);
  --color-hairline-strong:   rgba(26, 25, 24, 0.16);
  --shadow-sm:               0 1px 2px rgba(26, 25, 24, 0.04);
  --shadow-card:             0 4px 16px -2px rgba(26, 25, 24, 0.06), 0 1px 3px rgba(26, 25, 24, 0.04);
  --shadow-device:           0 24px 48px -12px rgba(26, 25, 24, 0.12), 0 4px 12px rgba(26, 25, 24, 0.05);
  --shadow-popover:          0 12px 32px -4px rgba(26, 25, 24, 0.12);

  /* ===== Typography ===== */
  --font-sans:               "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
  --font-display:            "Instrument Sans", "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --font-mono:               "JetBrains Mono", "SF Mono", Menlo, Monaco, Consolas, monospace;
  --tracking-display:        -0.035em;
  --tracking-eyebrow:        0.08em;

  /* ===== Motion eases ===== */
  --ease-hero:               cubic-bezier(0.16, 1, 0.3, 1);
  --ease-smooth:             cubic-bezier(0.25, 1, 0.5, 1);
  --ease-mechanical:         cubic-bezier(0.32, 0.72, 0, 1);
  --ease-micro:              cubic-bezier(0.2, 0, 0, 1);

  /* ===== Layout ===== */
  --content-max-width:       1200px;
  --readable-max-width:      820px;
  --editorial-max-width:     640px;
  --gutter-padding:          24px;
}
```

**Accent Choice:** **Olivetti Vermilion (`#D34E24`)**. Confident, warm 1960s primary with high graphic resonance against the warm unbleached paper canvas (`#F7F5F0`). Used purposefully for primary CTA actions, active agent indicators, and focus anchors.

---

## 7. What to port from CoDRAG (and how)

| Component | Source | What to do |
|-----------|--------|------------|
| `cli-types.ts` | `packages/ui/src/components/console/cli-types.ts` | Copy as-is. The `CliScript` / `CliEvent` types are product-agnostic. |
| `AnimatedCLI.tsx` | `packages/ui/src/components/console/AnimatedCLI.tsx` | Port to JSX (no `"use client"`). Replace hardcoded dark hex colors with token classes (`text-ink`, `text-ink-secondary`, `bg-card`, etc.). |
| `AnimatedIDE.tsx` | `packages/ui/src/components/console/AnimatedIDE.tsx` | Same treatment. Restyle the IDE frame for light theme. The "SourcePrep Project" status bar text becomes "Halbert" or the hostname. |
| `TerminalFrame.tsx` | `packages/ui/src/components/console/TerminalFrame.tsx` | Restyle for light — warm paper background, thin frame, mid-century window chrome (not a dark hacker terminal). |

**Do NOT port `@prep/ui` as a dependency.** Copy the three components into `marketing/web/src/components/` and adapt. They're self-contained (~600 lines total). Adding a monorepo package dependency for a static marketing site is overkill.

---

## 8. What to adapt from ApplicationBrowser

| Pattern | Source | What to do |
|---------|--------|------------|
| `App.jsx` structure | `src/App.jsx` | Mirror: Header → Hero → HowItWorks → TheBeing → Footer. Drop `PricingProvider` (no pricing yet). Keep `useSmoothScroll`. |
| `Hero.jsx` GSAP | `src/components/Hero.jsx` | Keep the matchMedia reduced-motion pattern, text-line reveal, scroll scrub. Replace the icon reveal with the conversation demo entrance. |
| `ProblemSolution.jsx` scrollytelling | `src/components/ProblemSolution.jsx` | Keep the two-column sticky layout, `ScrollTrigger.create` per step, `setActiveStep` pattern. Replace phone/Mac mockups with desktop windows. |
| `TheSoul.jsx` | `src/components/TheSoul.jsx` | Keep the centered philosophy statement + single device showcase. Replace IPhone with a desktop window running the conversation demo. |
| `Header.jsx` | `src/components/Header.jsx` | Mirror structure. Replace wordmark. |
| `Footer.jsx` | `src/components/Footer.jsx` | Mirror. |
| `MacWindow.jsx` | `src/components/MacWindow.jsx` | Port and restyle for light theme. This becomes `DesktopWindow.jsx`. |
| `tokens.css` | `shared-tokens/tokens.css` | Mirror the structure. Invert to light. Fill values from visual-design AI. |
| `index.css` | `src/index.css` | Keep noise overlay, reduced-motion safety net, legal-prose styles. Re-theme. |
| `useSmoothScroll.js` | `src/lib/useSmoothScroll.js` | Copy as-is (Lenis setup). |

---

## 9. Deployment

- **Netlify** static build (like ApplicationBrowser). `netlify.toml` with build command `vite build` and publish dir `dist`.
- Custom domain: `halbert.ai` (or wherever). TBD.
- No server-side rendering needed. No forms yet (waitlist can be a Netlify form or external link).

---

## 10. Build phases

### Phase 1: Scaffold + tokens (after visual-design AI delivers direction)
- Create `marketing/web/` project (Vite + React + Tailwind 4 + GSAP + Lenis).
- Set up `shared-tokens/tokens.css` with the design AI's palette.
- Port `MacWindow` → `DesktopWindow`, `TerminalFrame`, `AnimatedCLI`, `AnimatedIDE` (re-themed).
- Get a blank page with the header and footer rendering in the right palette.

### Phase 2: Hero + conversation demo
- Build `Hero.jsx` with the headline and the animated terminal playing the "How are you?" script.
- This is the single most important section. Get it right first.

### Phase 3: Scrollytelling sections
- Build `HowItWorks.jsx` with 3 steps and desktop window mockups.
- Write the dashboard mockup components (system overview, config diff, conversation view).

### Phase 4: The being section + footer
- Build `TheBeing.jsx` with the philosophy statement and the proactive-alert IDE animation.
- Finalize footer.

### Phase 5: Polish + deploy
- Reduced-motion audit (every animation has a static fallback).
- Mobile responsive pass.
- Lighthouse / performance check (GSAP and Lenis are the heavy deps).
- Deploy to Netlify.

---

## 11. Open questions & design recommendations

1. **Domain** — Default to `halbert.ai` in markup/metadata; fallbacks: `halbert.dev`, `usehalbert.com`.
2. **Waitlist** — Include a minimalist, high-conversion email capture form in the Hero and Footer ("Join the Early Access List — macOS & Linux") powered by Netlify Forms (`<form name="waitlist" netlify>`).
3. **Screenshots** — Build **interactive HTML/CSS mockups** directly in `DesktopWindow.jsx` and `TerminalFrame.jsx` for sharp Retina rendering, theme token synchronization, and real-time animation.
4. **Copy** — Build AI populates the exact conversation scripts from §5; human review on tagline and hero subhead during final polish.
5. **Scope** — Phase 1 targets the high-impact single-page scroll (`Hero` → `HowItWorks` → `TheBeing` → `Footer`) with modal/sub-page links for legal/privacy.

---

## 12. Visual-design direction handoff (completed)

The visual design direction document is complete and available at:
👉 [`marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md`](file:///Volumes/4TB-BAD/Halbert/marketing/VISUAL-DESIGN-DIRECTION-2026-08-23.md)

All tokens, typography specifications, component visual language, and motion curves are defined and ready for build execution (Phase 1).
