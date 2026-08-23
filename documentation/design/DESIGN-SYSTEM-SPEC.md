# Halbert Formalized Design System Specification

**Version:** 1.0.0  
**Date:** 2026-08-23  
**Status:** Active Foundation Specification (Web Build Standard)  
**Lead:** Visual Design Lead & System UX Architect  
**Scope:** Shared Design Language across Halbert Desktop (Tauri/React) & Halbert Marketing (`marketing/web`)  
**Design Aesthetic:** Late-1960s Futurist · Mid-Century Modern · Braun/Rams Restraint · Olivetti Tactile Soul · NASA Standards (1975)  

---

## 1. Design System Philosophy & Core Tenets

The Halbert design system transforms system administration and AI interaction from cold, disconnected telemetry graphs into an **embodied, tactile, daylight experience**. Halbert is not an outside utility monitoring a machine; Halbert *is* the machine speaking with voice, memory, and physiological self-awareness.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HALBERT DESIGN PILLARS                            │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│ 1. Daylight & Paper  │ 2. Honesty of State  │ 3. Mechanical Restraint       │
│ Warm unbleached      │ Every visual element │ Motion and layout mimic       │
│ archival canvas      │ is grounded in real  │ precision physical switches,   │
│ rejecting the dark   │ OS telemetry with    │ optical shutters, and crisp   │
│ sci-fi "hacker" neon │ clear four whys.     │ mid-century instruments.      │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

---

## 2. Design Token Architecture

The token system uses a **three-tier hierarchy**:
1. **Primitive Tokens (Raw Values):** Hex colors, font families, base scales.
2. **Semantic Tokens (Intent & Context):** Backgrounds, surface tiers, ink contrast levels, telemetry status, elevation.
3. **Component Tokens (Scoped):** Specific parameters for terminal frames, diff blocks, why-chips, and gauges.

```
  [ Primitive Tokens ] ──> [ Semantic Tokens ] ──> [ Component Tokens ]
   (e.g., #D34E24)          (e.g., --color-accent)   (e.g., --terminal-badge-bg)
```

---

## 3. Color & Surface Taxonomy

### 3.1 Surface Ramp (The Daylight Palette)

Halbert rejects sterile `#FFFFFF` canvases and dark hacker terminals. The background is a **warm archival paper** (`#F7F5F0`), layered with crisp elevated cards and recessed data trays:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SURFACE ELEVATION RAMP                                                     │
│                                                                             │
│  [ Canvas ]             #F7F5F0  (Base page / window background)           │
│    └─ [ Surface Subtle ]#EFECE4  (Recessed trays, code containers, terminal) │
│         └─ [ Surface ]  #FFFFFF  (Elevated cards, active dialogs, sheets)   │
│              └─ [ Muted]#E5E0D5  (Inactive pills, disabled controls)        │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Semantic Token | Value | Intent / Application |
|---|---|---|
| `--color-canvas` | `#F7F5F0` | Default application & marketing page background. Warm linen/paper tone. |
| `--color-surface` | `#FFFFFF` | Elevated cards, desktop window bodies, active dropdowns, popovers. |
| `--color-surface-subtle` | `#EFECE4` | Recessed diagnostic panels, terminal interior, telemetry trays. |
| `--color-surface-muted` | `#E5E0D5` | Inactive segment pills, disabled button fills, subtle progress tracks. |

### 3.2 Ink Hierarchy (Warm Charcoal & Graphite)

Text contrast never uses pitch black (`#000000`), preserving a printed editorial quality:

| Semantic Token | Value | Contrast Ratio (on Canvas `#F7F5F0`) | Role & Standard |
|---|---|---|---|
| `--color-ink` | `#1A1918` | `16.11:1` | Primary headings, terminal user prompt, agent voice (WCAG AAA). |
| `--color-ink-secondary` | `#5E5B56` | `6.20:1` | Secondary prose, timestamps, telemetry metadata, tool arguments (WCAG AA). |
| `--color-ink-tertiary` | `#8C877D` | `3.28:1` | Captions, shortcut badges, inactive tabs, subtle borders (UI non-body). |
| `--color-ink-ghost` | `#B8B2A6` | `1.92:1` | Decorative placeholder text, guideline dividers, disabled icons. |

### 3.3 The Signature Accent: Olivetti Vermilion

A single, iconic 1960s primary accent color used strictly for focus, action, and active state:

- **Primary Accent (`--color-accent`):** `#D34E24` (Olivetti Vermilion / NASA 1975 Red)
- **Accent Hover (`--color-accent-hover`):** `#B83E18` (5.61:1 contrast on white, WCAG AA compliant)
- **Accent Active / Pressed (`--color-accent-active`):** `#9C3212`
- **Accent Tint / Glow (`--color-accent-tint`):** `#FDF2EE` (Subtle 8% background wash)

> [!NOTE]
> **Accent Contrast & Button Accessibility:**
> White text on base Vermilion (`#D34E24`) renders at `4.30:1` contrast ratio. For primary CTA buttons, ensure semibold weight (`font-semibold` / `font-bold`) and minimum size `16px - 18px` (`text-base` or `text-lg`) to clear the large-text threshold, or leverage `--color-accent-hover` (`#B83E18` at `5.61:1`) for high-contrast accessibility requirements.

### 3.4 Telemetry & Diagnostic Semantics

Diagnostic signals are desaturated, mid-century pigments:

- **Nominal / Healthy (`--color-status-success`):** `#2D7A56` (Eames Botanical Green) · Tint: `#EEF6F2`
- **Caution / Attention (`--color-status-warning`):** `#C4781C` (Braun Amber Ochre) · Tint: `#FDF8F0`
- **Critical / Danger (`--color-status-error`):** `#C83E2D` (Terracotta Crimson) · Tint: `#FDF2F0`
- **Telemetry / RAG (`--color-status-info`):** `#386C8A` (Blueprint Slate Teal) · Tint: `#F0F6F9`

### 3.5 Hairlines & Shadows

- `--color-hairline`: `rgba(26, 25, 24, 0.08)` (Crisp structural separator)
- `--color-hairline-strong`: `rgba(26, 25, 24, 0.16)` (Window borders, input focus boundaries)
- `--shadow-sm`: `0 1px 2px rgba(26, 25, 24, 0.04)`
- `--shadow-card`: `0 4px 16px -2px rgba(26, 25, 24, 0.06), 0 1px 3px rgba(26, 25, 24, 0.04)`
- `--shadow-device`: `0 24px 48px -12px rgba(26, 25, 24, 0.12), 0 4px 12px rgba(26, 25, 24, 0.05)`
- `--shadow-popover`: `0 12px 32px -4px rgba(26, 25, 24, 0.12)`

### 3.6 Framework Implementation Coexistence

| Surface | Framework / Stack | Token Implementation Strategy |
|---|---|---|
| **Marketing Web (`marketing/web`)** | Vite + React 19 + Tailwind CSS 4 | Native `@theme` CSS custom properties in `shared-tokens/tokens.css` |
| **Desktop App (`halbert_core`)** | Tauri + React + Tailwind CSS 3 | Conceptual token alignment with HSL shadcn root variables |

*Note:* Full desktop app migration to Tailwind 4 is an independent future workstream and does not gate the marketing site build.

---

## 4. Typography & Glyphs

```
[ DISPLAY / HEADLINES ]    Instrument Sans / Plus Jakarta Sans
                           Geometric clarity, tight tracking (-0.035em), warm open counters.

[ BODY / INTERFACE ]       Inter / System Sans
                           High x-height, neutral legibility, generous line spacing (1.6).

[ CODE / TELEMETRY ]       JetBrains Mono / SF Mono
                           Tabular figures, high distinction for 0/O and 1/l/I.
```

### 4.1 Modular Type Scale

| Name | Font Size | Line Height | Tracking | Weight | Semantic HTML / Component Usage |
|---|---|---|---|---|---|
| `display-xl` | `clamp(2.75rem, 5.5vw, 4.25rem)` | `1.08` | `-0.04em` | `600` | Marketing Hero Headline |
| `display-l` | `clamp(2.0rem, 3.5vw, 2.75rem)` | `1.15` | `-0.03em` | `600` | Main Section Titles, Modal Headers |
| `display-m` | `1.5rem` (24px) | `1.25` | `-0.02em` | `600` | Card Titles, Summoned Module Headers |
| `display-s` | `1.25rem` (20px) | `1.35` | `-0.015em` | `600` | Subsection Headers, Diff File Titles |
| `body-lead` | `1.1875rem` (19px) | `1.55` | `-0.01em` | `400` | Hero Subtitle, Soul Statement |
| `body-reg` | `1.0rem` (16px) | `1.60` | `0em` | `400` | Conversational Speech, Scrollytelling Copy |
| `body-sm` | `0.875rem` (14px) | `1.50` | `0em` | `400` | Metadata, Tool descriptions, Settings labels |
| `caption` | `0.75rem` (12px) | `1.40` | `+0.02em` | `500` | Footnotes, Timestamp badges, Hotkey labels |
| `eyebrow` | `0.75rem` (12px) | `1.00` | `+0.08em` | `600` | Uppercase Section Markers (`TRACKING-WIDER`) |
| `mono-code` | `0.875rem` (14px) | `1.65` | `-0.01em` | `400` | Terminal dialogue, Config diffs, Logs |
| `mono-sm` | `0.8125rem` (13px) | `1.50` | `0em` | `500` | Gauge readouts, Sensor telemetry metrics |

---

## 5. Grid, Layout & Spatial Cadence

The layout relies on an **8px base grid** with a **4px sub-grid** for micro-alignments:

```
Spacing Scale:
  2px  (0.5) ── Sub-pixel borders & hairline nudges
  4px  (1)   ── Icon gutters, tag padding
  8px  (2)   ── Inner pill padding, button gap
  12px (3)   ── Card internal compact spacing
  16px (4)   ── Standard component padding
  24px (6)   ── Window chrome gutter, section sub-gap
  32px (8)   ── Module margins, large cards
  48px (12)  ── Major component stack gaps
  80px (20)  ── Mobile section spacing
  120px(30)  ── Desktop section spacing
  160px(40)  ── Major marketing chapter separation
```

### 5.1 Application Modes & Responsive Breakpoints

1. **Desktop App (Engaged 2-Column Mode):**
   - Left Pane (Spine / Dialogue): `45% - 50%` flex width (min `440px`, max `680px`).
   - Right Pane (Context / Summoned Module): `50% - 55%` flex width.
   - Fluid split with smooth spring transition upon summoning.
2. **Marketing Landing Page:**
   - Max Container: `1200px` (Wide Hero & Scrollytelling grid).
   - Reading Column: `820px` (The Soul philosophy center).
   - Editorial Text Column: `640px` (Step narration).

---

## 6. Motion & Kinetic Language

Motion is engineered to feel **tactile, mechanical, and calm**—mirroring precision physical hardware rather than floaty abstract web animations.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MOTION PROFILES & EASING CURVES                                            │
│                                                                             │
│  --ease-hero:       cubic-bezier(0.16, 1, 0.3, 1)  (Snappy Leica entrance)  │
│  --ease-smooth:     cubic-bezier(0.25, 1, 0.5, 1)  (Scrolly module morph)   │
│  --ease-mechanical: cubic-bezier(0.32, 0.72, 0, 1) (Physical switch/drawer) │
│  --ease-micro:      cubic-bezier(0.2, 0, 0, 1)     (Button hover/tap)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Duration Standards
- **Micro-interactions (Hover, Focus, Press):** `150ms - 200ms`
- **Drawer / Popover / Tooltip Reveals:** `250ms - 350ms`
- **Module Summoning / Stage Transitions:** `500ms - 650ms`
- **Hero Staggered Entrances:** `800ms - 1000ms`
- **Conversational Typewriter Cadence:** `14ms - 28ms` per character (with punctuation breath pauses of `300ms - 600ms`).

### 6.2 Accessibility & Reduced Motion
- When `prefers-reduced-motion: reduce` is active:
  - All positional slides (`y: 20 -> 0`) convert to instantaneous or pure opacity transitions (`150ms`).
  - Terminal text renders fully formed immediately without typing loops.
  - Smooth scrolling drivers (Lenis) are completely bypassed.

---

## 7. Accessibility (A11y) & Usability Standards

1. **Contrast Compliance:** All text tokens meet WCAG 2.1 AA (`4.5:1` for body text, `3.0:1` for large text). Primary ink on canvas exceeds WCAG AAA (`15.8:1`).
2. **Focus Rings:** High-visibility double ring: `2px solid var(--color-accent)` with `2px offset`.
3. **Keyboard Navigation:** Every actionable element (WhyChips, approval buttons, module controls, filter tags) is accessible via `Tab` / `Shift+Tab`, `Cmd+K` command bar, and localized arrow key navigation.
4. **ARIA & Semantics:** 
   - Animated terminal uses `aria-live="polite"` for agent output.
   - WhyChips declare `aria-expanded` and `aria-haspopup="dialog"`.
   - Telemetry gauges carry explicit `role="meter"` or `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, and `aria-valuemax`.

---

## 8. Tailwind CSS v4 Reference File (`tokens.css`)

```css
@theme {
  /* Surfaces */
  --color-canvas:            #F7F5F0;
  --color-surface:           #FFFFFF;
  --color-surface-subtle:    #EFECE4;
  --color-surface-muted:     #E5E0D5;

  /* Accent */
  --color-accent:            #D34E24;
  --color-accent-hover:      #B83E18;
  --color-accent-active:     #9C3212;
  --color-accent-tint:       #FDF2EE;

  /* Ink */
  --color-ink:               #1A1918;
  --color-ink-secondary:     #5E5B56;
  --color-ink-tertiary:      #8C877D;
  --color-ink-ghost:         #B8B2A6;

  /* Status */
  --color-status-success:    #2D7A56;
  --color-status-warning:    #C4781C;
  --color-status-error:      #C83E2D;
  --color-status-info:       #386C8A;

  /* Hairlines & Shadows */
  --color-hairline:          rgba(26, 25, 24, 0.08);
  --color-hairline-strong:   rgba(26, 25, 24, 0.16);
  --shadow-sm:               0 1px 2px rgba(26, 25, 24, 0.04);
  --shadow-card:             0 4px 16px -2px rgba(26, 25, 24, 0.06), 0 1px 3px rgba(26, 25, 24, 0.04);
  --shadow-device:           0 24px 48px -12px rgba(26, 25, 24, 0.12), 0 4px 12px rgba(26, 25, 24, 0.05);
  --shadow-popover:          0 12px 32px -4px rgba(26, 25, 24, 0.12);

  /* Fonts */
  --font-sans:               "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
  --font-display:            "Instrument Sans", "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --font-mono:               "JetBrains Mono", "SF Mono", Menlo, Monaco, Consolas, monospace;

  /* Motion */
  --ease-hero:               cubic-bezier(0.16, 1, 0.3, 1);
  --ease-smooth:             cubic-bezier(0.25, 1, 0.5, 1);
  --ease-mechanical:         cubic-bezier(0.32, 0.72, 0, 1);
  --ease-micro:              cubic-bezier(0.2, 0, 0, 1);
}
```
