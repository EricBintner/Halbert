# Visual Design Direction: Halbert Marketing Webpage

**Document Date:** 2026-08-23  
**Status:** Approved Visual Design Direction (Handoff to Web Build)  
**Target Medium:** Single-page Desktop-First Marketing Site (`marketing/web/`)  
**Design Persona & Era:** Late 1960s Futurist · Mid-Century Modern · Braun & Olivetti Humanism · NASA Graphic Standards (1975)  

---

## 1. Executive Summary & Design Vision

Halbert is a local-first AI assistant that **identifies as your computer**. It is not a detached cloud bot, an operating system overhaul, or a sci-fi fantasy. It is your computer speaking to you in first person, grounded in real telemetry, configuration history, and diagnostic truth.

The marketing webpage must reflect this distinct identity through a visual design philosophy defined by **warmth, honesty of materials, geometric clarity, and domestic intelligence**:

```
                                  [ VISUAL DNA ]
  
        BRAUN / RAMS                OLIVETTI                  NASA STANDARDS (1975)
    Restraint & Honesty        Tactile Humanity & Soul        Precision Grid & Bold Vermilion
             │                            │                               │
             └────────────────────────────┼───────────────────────────────┘
                                          ▼
                             [ HALBERT VISUAL LANGUAGE ]
                         • Light, warm archival paper canvas
                         • Single iconic Vermilion accent (#D34E24)
                         • Crisp 1px hairlines & geometric typography
                         • Human, friendly desktop computing
```

### Core Design Pillars
1. **Light & Tactile (Anti-Sci-Fi):** Move away from the dark, neon "cyberpunk" tropes of generic AI tools. Halbert lives in the daylight—on warm paper, brushed aluminium, and clean mid-century desks.
2. **The Computer as a Helpful Colleague:** The tone is calm, capable, and approachable (reminiscent of 1960s Olivetti typewriter marketing and the 1984 Apple "Hello" introduction).
3. **The Conversation is the Stage:** The signature hero asset is the live, animated terminal conversation—not a generic laptop render or floating 3D orb.
4. **Typographic Wit:** The tagline *"Halbert. You can call me AI."* is visually rooted in humanist sans-serif typography where the interplay of "al" and "ai" rewards a second glance.

---

## 2. Color Palette & Surface Architecture

The color system is built around a **light, warm surface ramp** paired with high-contrast warm graphite ink and a single, vibrant 1960s primary accent: **Olivetti Vermilion**.

```
[ PALETTE OVERVIEW ]

Canvas:          #F7F5F0  (Warm Archival Paper)
Surface Raised:  #FFFFFF  (Crisp Window / Card Surface)
Surface Subtle:  #EFECE4  (Code Box / Recessed Trays)
Surface Muted:   #E5E0D5  (Pill Badges / Inactive Elements)

Ink Carbon:      #1A1918  (Primary Text / High Contrast)
Ink Secondary:   #5E5B56  (Subheads / Metadata / Timestamps)
Ink Tertiary:    #8C877D  (Captions / Muted Labels)

Accent:          #D34E24  (Olivetti Vermilion — Action / Active State)
Accent Tint:     #FDF2EE  (Soft Vermilion Glow / Highlight Fill)
```

### 2.1 Complete Palette Matrix

| Token Name | Hex Value | HSL / RGBA Equivalent | Intent & Semantic Role |
|------------|-----------|------------------------|------------------------|
| `--color-canvas` | `#F7F5F0` | `hsl(43, 24%, 95%)` | Page background. Warm unbleached paper / linen stock. Never harsh #FFFFFF. |
| `--color-surface` | `#FFFFFF` | `hsl(0, 0%, 100%)` | Card interiors, desktop window bodies, active elevated sheets. |
| `--color-surface-subtle` | `#EFECE4` | `hsl(43, 20%, 92%)` | Terminal canvas, recessed panels, config diff line backgrounds. |
| `--color-surface-muted` | `#E5E0D5` | `hsl(41, 19%, 87%)` | Inactive control pills, disabled buttons, subtle badge fills. |
| `--color-ink` | `#1A1918` | `hsl(30, 5%, 10%)` | High-contrast body text, headings, primary terminal dialogue. |
| `--color-ink-secondary` | `#5E5B56` | `hsl(38, 4%, 35%)` | Secondary copy, timestamps, tool arguments, system telemetry labels. |
| `--color-ink-tertiary` | `#8C877D` | `hsl(39, 6%, 52%)` | Footnotes, hotkey indicators, inactive tab labels, borders. |
| `--color-ink-ghost` | `#B8B2A6` | `hsl(39, 11%, 69%)` | Disabled text, subtle grid guidelines, decorative glyphs. |
| `--color-accent` | `#D34E24` | `hsl(14, 71%, 48%)` | **Signature Accent:** Olivetti Vermilion / NASA Red. CTA buttons, active focus states, live agent indicators. |
| `--color-accent-hover` | `#B83E18` | `hsl(14, 77%, 41%)` | Hover/pressed state for primary accent interactive elements. |
| `--color-accent-tint` | `#FDF2EE` | `hsl(16, 80%, 96%)` | Subtle accent wash, active filter pills, highlighted code tokens. |
| `--color-hairline` | `rgba(26, 25, 24, 0.08)` | `rgba(26,25,24, 0.08)` | Structural dividers, card borders, window container outlines. |
| `--color-hairline-strong` | `rgba(26, 25, 24, 0.16)` | `rgba(26,25,24, 0.16)` | Window frames, active input outlines, table headers. |

### 2.2 Telemetry & Diagnostic Semantics (Muted Mid-Century Accents)
When showing system telemetry (e.g. CPU temperature, storage status, log severity), colors are natural and desaturated—never neon:

- **Healthy / Nominal (`--color-status-success`):** `#2D7A56` (Eames forest green) · Tint: `#EEF6F2`
- **Attention / Caution (`--color-status-warning`):** `#C4781C` (Braun amber ochre) · Tint: `#FDF8F0`
- **Critical / Danger (`--color-status-error`):** `#C83E2D` (Terracotta brick red) · Tint: `#FDF2F0`
- **Diagnostic / RAG (`--color-status-info`):** `#386C8A` (Blueprint slate teal) · Tint: `#F0F6F9`

---

## 3. Typography & The "Al" / "AI" Visual Pun

Typography is the foundational voice of the brand. It combines mid-century geometric rigor with contemporary screen readability.

### 3.1 Font Stack Architecture

```
[ DISPLAY & HEADINGS ]    Instrument Sans / Plus Jakarta Sans
                          • Crisp geometric proportions
                          • Warm, open counters
                          • Negative letter-spacing for headlines

[ BODY & PROSE ]          Inter / System Sans
                          • High x-height, maximum legibility
                          • Open apertures, calm rhythm

[ CODE & TERMINAL ]       JetBrains Mono / SF Mono
                          • Tabular figures for telemetry data
                          • Clear glyph distinction (0 vs O, 1 vs l vs I)
```

1. **Display Font:** `Instrument Sans`, `Plus Jakarta Sans`, `-apple-system`, `BlinkMacSystemFont`, `sans-serif`
   - *Characteristics:* High geometric clarity reminiscent of Futura and Univers, but with humanist softness.
2. **Body Font:** `Inter`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `sans-serif`
   - *Characteristics:* Neutral, invisible workhorse for long-form scrollytelling narrative and philosophy copy.
3. **Monospace Font:** `JetBrains Mono`, `"SF Mono"`, `Menlo`, `Monaco`, `monospace`
   - *Characteristics:* Used in terminal frames, telemetry dashboards, configuration diffs, and inline code pills.

### 3.2 The "Al" / "AI" Tagline Execution

The primary tagline is:
> **"Halbert. You can call me AI."**

**Typographic Analysis & Typographic Direction:**
- In geometric sans-serif typefaces (like `Instrument Sans` or `Plus Jakarta Sans`), the uppercase letter **`I`** (India) is a clean vertical bar without top or bottom serifs, and the lowercase letter **`l`** (lima) is also a clean vertical bar.
- The name **`Halbert`** contains the substring **`al`** (`a` + vertical stem).
- When the tagline reads **`You can call me AI.`**, the word **`AI`** (uppercase A + uppercase I) creates a resonant visual rhyme with the **`Al`** in Halbert.
- **Rendering Guideline:** Set `AI` in all-caps display sans-serif with standard letter-spacing (`tracking-normal`). In the wordmark, give the letter combination `al` balanced, proportional kerning so the visual pun is felt intuitively without requiring gimmicky graphical arrows or callouts.

### 3.3 Type Hierarchy & Scale Spec

| Level | Size (Desktop / Mobile) | Line Height | Tracking | Weight | Style / Notes |
|-------|-------------------------|-------------|----------|--------|---------------|
| **Display XL (Hero)** | `clamp(2.75rem, 5.5vw, 4.25rem)` | `1.08` | `-0.04em` | 600 (Semibold) | Tight, confident, editorial title |
| **Display L (Sections)**| `clamp(2.0rem, 3.5vw, 2.75rem)` | `1.15` | `-0.03em` | 600 (Semibold) | Section introductions |
| **Display M (Cards)** | `1.5rem` (24px) / `1.35rem` | `1.25` | `-0.02em` | 600 (Semibold) | Step titles, module headers |
| **Lead Paragraph** | `1.1875rem` (19px) / `1.125rem` | `1.55` | `-0.01em` | 400 (Regular) | Hero subhead, philosophy statement |
| **Body Regular** | `1.0rem` (16px) | `1.60` | `0em` | 400 (Regular) | Narrative scrollytelling copy |
| **Body Small** | `0.875rem` (14px) | `1.50` | `0em` | 400 (Regular) | Card descriptions, feature notes |
| **Eyebrow / Badge** | `0.75rem` (12px) | `1.00` | `+0.08em` | 600 (Semibold) | Uppercase category markers (`TRACKING-WIDER`) |
| **Mono Terminal** | `0.875rem` (14px) / `0.8125rem` | `1.65` | `-0.01em` | 400 / 500 | Live CLI dialogue, code diffs, logs |

---

## 4. Grid, Rhythm & Layout Architecture

```
[ DESKTOP VIEWPORT GRID: 1200px MAX ]
┌────────────────────────────────────────────────────────────────────────┐
│  HEADER: Sticky, 64px height, Hairline bottom border, 20px edge pad    │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  HERO SECTION (min-h-[90svh])                                          │
│  ┌───────────────────────────────┬──────────────────────────────────┐  │
│  │ Headline + Subhead + CTAs     │ Signature Animated Conversation  │  │
│  │ (550px Column)                │ Terminal Frame (580px Column)    │  │
│  └───────────────────────────────┴──────────────────────────────────┘  │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  HORIZONTAL RULE: 1px rgba(26,25,24,0.08)                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  HOW IT WORKS (Scrollytelling Sticky Stage)                            │
│  ┌───────────────────────────────┬──────────────────────────────────┐  │
│  │ Scroll Narrative Steps (1..3) │ Sticky Desktop Window Display    │  │
│  │ (420px Column)                │ (Morphing Modules: 640px Column) │  │
│  └───────────────────────────────┴──────────────────────────────────┘  │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  HORIZONTAL RULE                                                       │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  THE SOUL / THE BEING (Centered Philosophy + Morning Report Demo)      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ "The most helpful colleague you have, who happens to be..."      │  │
│  │ Centered Editorial Window (820px Column)                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  FOOTER: Minimalist 4-Column / Legal / Copyright / Local-First Badge   │
└────────────────────────────────────────────────────────────────────────┘
```

### Grid Parameters
- **Max Page Width:** `1200px` (Wide Container) / `820px` (Reading & Soul Stage) / `640px` (Editorial Narrative)
- **Viewport Gutters:** `24px` on desktop (`md:` and above), `16px` on mobile.
- **Vertical Spacing Rhythm:**
  - Section-to-Section: `120px` to `160px` (`py-28` to `py-36`) on desktop; `80px` (`py-20`) on mobile.
  - Heading-to-Paragraph: `20px` to `24px`.
  - Paragraph-to-Component: `32px` to `48px`.
- **Horizontal Dividers:** Mid-century clean `1px` lines spanning the container (`border-t border-hairline`) to cleanly demarcate narrative chapters without cluttered card boxes.

---

## 5. Component Visual Language

### 5.1 The Light-Theme Terminal Frame (`TerminalFrame.jsx`)

The terminal frame is a precision instrument inspired by vintage Braun testing hardware and Olivetti desktop calculators. It rejects the dark hacker aesthetic in favor of a warm, daylight presentation.

```
┌──────────────────────────────────────────────────────────┐
│ [•] [•] [•]   halbert — ubuntu-server-01           ● LIVE │ ◄ Titlebar: #FAF8F4, border-b 1px
├──────────────────────────────────────────────────────────┤
│                                                          │
│ > how are you doing?                                     │ ◄ User Input: #1A1918 (Semibold)
│                                                          │
│   [ ⚙ Checking vitals… ]                                 │ ◄ Tool Call Pill: #EFECE4 + Vermilion icon
│   CPU 45°C · load 0.15 · /dev/nvme0n1 healthy            │ ◄ Tool Result: #5E5B56 (Muted Mono)
│                                                          │
│ I'm ubuntu-server-01. I've been up 42 days.              │ ◄ Agent Response: #1A1918 (Human Voice)
│ My primary drive logged three read errors this morning.  │
│ I'd keep an eye on that drive. Want a SMART test?        │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**Visual Specifications:**
- **Container:** Background `#FFFFFF` (or `#FAF8F5`), border `1px solid rgba(26, 25, 24, 0.12)`, border radius `16px` (`rounded-2xl`), shadow `0 20px 40px -15px rgba(26, 25, 24, 0.08), 0 1px 3px rgba(26, 25, 24, 0.04)`.
- **Window Chrome / Titlebar:**
  - Background `#F4F0E8` with a crisp `1px` bottom border (`rgba(26, 25, 24, 0.08)`).
  - Height `42px`, horizontal padding `16px`.
  - **Window Controls:** Three muted stone-tinted pips (`#D8D2C5`, `#CEC7B8`, `#C5BEAE`) or muted vintage hues (warm brick, amber ochre, sage green with subtle inset hairlines).
  - **Title Text:** `halbert — ubuntu-server-01` set in `JetBrains Mono` (`0.8125rem`, `#5E5B56`, medium weight).
  - **Status Pip:** Right-aligned pulse indicator (Green `#2D7A56` with soft glow).
- **Dialogue Typography:**
  - User command prompt: Warm graphite `#1A1918`, bold weight, prefixed by a subtle accent arrow `>`.
  - Tool Invocation Pill: Inset capsule with background `#EFECE4`, border `1px solid #DFD9CD`, icon in Olivetti Vermilion (`#D34E24`), text `#5E5B56`.
  - Halbert First-Person Output: High-contrast `#1A1918`, generous line height (`1.65`), typewriter rendering cadence.

### 5.2 The Desktop Application Frame (`DesktopWindow.jsx`)

Represents the Tauri-based Halbert desktop application.

- **Window Chrome:** Native macOS inspired traffic lights or neutral mid-century pips.
- **Top Navigation Bar:** Clean segmented control tabs (`Conversation`, `Vitals`, `Config Rationale`, `Audit Log`) with active state highlighted in white surface with subtle drop shadow.
- **Split Pane:** Left-hand conversational stream (`60%` width) paired with a summonable right-hand diagnostic panel (`40%` width) featuring real-time health gauges or configuration diffs.
- **Subtle Texture:** Soft `0.02` opacity SVG film grain / paper noise over background surfaces to give a tactile, printed feel.

### 5.3 Buttons, Badges & Interactive Controls

- **Primary CTA ("Join the Waitlist" / "Download for Mac & Linux"):**
  - Background: Olivetti Vermilion (`#D34E24`), Text: `#FFFFFF`, Weight: `600`, Radius: `10px` (`rounded-lg`).
  - Hover: Background `#B83E18`, slight upward translation (`-1px`), shadow `0 4px 12px rgba(211, 78, 36, 0.25)`.
- **Secondary CTA ("Read the Ethos" / "Explore Docs"):**
  - Background: `#FFFFFF`, Border: `1px solid rgba(26, 25, 24, 0.14)`, Text: `#1A1918`, Weight: `500`.
  - Hover: Background `#F7F5F0`, Border `rgba(26, 25, 24, 0.24)`.
- **Status / Pill Badges:**
  - Height `26px`, padding `0 10px`, font size `0.75rem`, weight `600`, tracking `+0.04em`.
  - Background: `#EFECE4`, Border: `1px solid rgba(26, 25, 24, 0.08)`, Text: `#5E5B56`.

---

## 6. Motion Philosophy & Animation Tokens

Motion in Halbert must feel **deliberate, mechanical, calm, and confident**—the digital equivalent of a finely engineered Braun mechanical switch or an optical shutter.

```
                     [ MOTION CURVE PHILOSOPHY ]

   Snappy Entrance (Leica Shutter)      Smooth Scrollytelling Transition
   ease-hero: [0.16, 1, 0.3, 1]         ease-smooth: [0.25, 1, 0.5, 1]
     100% ┌─────────────                  100% ┌────────────
          │     /                              │     /
          │    /                               │   /
          │   /                                │  /
       0% └──/────────                      0% └──/─────────
```

### 6.1 Easing & Timing Matrix

| Token Name | Cubic-Bezier Curve | Duration | Usage Context |
|------------|--------------------|----------|---------------|
| `--ease-hero` | `cubic-bezier(0.16, 1, 0.3, 1)` | `800ms` - `1000ms` | Page load hero typography reveal, main window entrance |
| `--ease-smooth` | `cubic-bezier(0.25, 1, 0.5, 1)` | `500ms` - `700ms` | Scrollytelling module crossfades, sticky window step transitions |
| `--ease-mechanical`| `cubic-bezier(0.32, 0.72, 0, 1)`| `300ms` - `400ms` | Tab switches, drawer sliding, tooltip popovers |
| `--ease-micro` | `cubic-bezier(0.2, 0, 0, 1)` | `150ms` - `200ms` | Button hover states, border highlight transitions |

### 6.2 Reduced Motion Strategy
Halbert strictly respects `prefers-reduced-motion: reduce`:
- When reduced motion is detected via GSAP matchMedia:
  - All ScrollTrigger pinning remains functional for page readability, but opacity crossfades replace sliding animations.
  - The animated CLI typewriter effect displays immediate complete responses rather than character-by-character typing.
  - Lenis smooth scrolling is disabled in favor of native instant scrolling.

---

## 7. Wordmark & Identity Direction

### 7.1 Wordmark Construction

```
   H a l b e r t .
   ───┬─── ───┬───
     Hal   Albert
   (2001)  (Human)
```

- **Typeface:** Custom-spaced `Instrument Sans Semibold` or `Plus Jakarta Sans Semibold`.
- **Character:** Tight kerning (`-0.035em`), perfectly balanced vertical stems between `H`, `l`, `b`, and `t`.
- **The Period:** The wordmark can include a subtle terminal period `Halbert.` in Olivetti Vermilion (`#D34E24`), grounding the name with finality and confidence.

### 7.2 What to Avoid (Negative Constraints)
- **NO Red Glowing Camera Lens / HAL 9000 Eye:** The allusion lives in the name and dialogue, not in overt copyrighted film iconography.
- **NO Sci-Fi Neon Glows or Hologram Grids:** Keep the design rooted in physical, daylight computing materials.
- **NO Generic Mobile Device Mockups:** Halbert is a desktop host assistant (Tauri on macOS/Linux). Show only Mac and desktop window frames.

---

## 8. Tailwind CSS v4 `@theme` Token Scaffold

The following block is production-ready for inclusion in `marketing/web/shared-tokens/tokens.css` or Tailwind 4 configuration:

```css
@theme {
  /* ===== Surface Ramp (Light / Warm Paper Canvas) ===== */
  --color-canvas:            #F7F5F0;   /* Warm archival paper canvas */
  --color-surface:           #FFFFFF;   /* Raised cards & window interiors */
  --color-surface-subtle:    #EFECE4;   /* Recessed panels & terminal canvas */
  --color-surface-muted:     #E5E0D5;   /* Inactive controls & pill tags */

  /* ===== Primary Signature Accent (Olivetti Vermilion) ===== */
  --color-accent:            #D34E24;   /* 60s futurist vermilion accent */
  --color-accent-hover:      #B83E18;   /* Deep vermilion for hover states */
  --color-accent-tint:       #FDF2EE;   /* Soft vermilion wash */

  /* ===== Ink Hierarchy (Warm Charcoal & Graphite) ===== */
  --color-ink:               #1A1918;   /* Deep carbon black for text */
  --color-ink-secondary:     #5E5B56;   /* Secondary metadata & labels */
  --color-ink-tertiary:      #8C877D;   /* Captions & subtle annotations */
  --color-ink-ghost:         #B8B2A6;   /* Disabled & placeholder text */

  /* ===== Functional Telemetry Accents (Desaturated 60s Palette) ===== */
  --color-status-success:    #2D7A56;   /* Eames forest green */
  --color-status-warning:    #C4781C;   /* Braun amber ochre */
  --color-status-error:      #C83E2D;   /* Terracotta brick red */
  --color-status-info:       #386C8A;   /* Blueprint slate teal */

  /* ===== Hairlines & Dividers ===== */
  --color-hairline:          rgba(26, 25, 24, 0.08);
  --color-hairline-strong:   rgba(26, 25, 24, 0.16);

  /* ===== Shadows (Soft Ambient Ambient Diffusions) ===== */
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

  /* ===== Motion Easing Tokens ===== */
  --ease-hero:               cubic-bezier(0.16, 1, 0.3, 1);
  --ease-smooth:             cubic-bezier(0.25, 1, 0.5, 1);
  --ease-mechanical:         cubic-bezier(0.32, 0.72, 0, 1);
  --ease-micro:              cubic-bezier(0.2, 0, 0, 1);

  /* ===== Layout Dimensions ===== */
  --content-max-width:       1200px;
  --readable-max-width:      820px;
  --editorial-max-width:     640px;
  --gutter-padding:          24px;
}
```

---

## 9. Recommendations for Open Plan Questions (§11 Resolution)

To ensure the build phase can proceed without blockers, here are the strategic recommendations for the 5 questions raised in `MARKETING-WEBPAGE-PLAN-2026-08-23.md`:

1. **Domain:**
   - **Recommendation:** Use `halbert.ai` as primary target, with fallback to `halbert.dev` or `usehalbert.com`. The code and metadata should default to `halbert.ai`.
2. **Waitlist vs. Coming Soon:**
   - **Recommendation:** Include a clean, high-conversion email capture input in the Hero and Footer ("Join the Early Access List — macOS & Linux"). Netlify Forms handles this with zero backend code required (`<form name="waitlist" netlify>`).
3. **Screenshots vs. HTML/CSS Mockups:**
   - **Recommendation:** Build **pure HTML/CSS interactive mockups** inside `DesktopWindow.jsx` and `TerminalFrame.jsx`. This avoids waiting for raster asset capture, ensures razor-sharp rendering on Retina displays, enables real-time animation, and maintains complete thematic token consistency.
4. **Copywriting Ownership:**
   - **Recommendation:** The build AI can populate the exact conversation scripts defined in §5 of the plan, with final human editorial review of the tagline and hero subheads during the polish phase.
5. **Scope:**
   - **Recommendation:** Phase 1 focuses on the high-impact single-page scroll (`Hero` → `HowItWorks` → `TheBeing` → `Footer`). Modal-based or sub-page `/privacy` and `/terms` templates can be cleanly linked in the footer.

---

## 10. Next Steps & Build Handoff

With this visual design direction established:
1. `MARKETING-WEBPAGE-PLAN-2026-08-23.md` is updated to status **Ready for Build**.
2. **Phase 1 Execution** can immediately scaffold `marketing/web/` with Vite + React 19 + Tailwind 4 + GSAP + Lenis, inserting the tokens above directly into `shared-tokens/tokens.css`.
