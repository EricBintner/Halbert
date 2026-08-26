# Handoff: Halbert Marketing Suite & Kinetic Vector-Guided Parallax

**Date:** 2026-08-25  
**Author / Creative Director:** Eric Bintner  
**Handoff Target:** Next AI Agent / Engineering Session  
**File Location:** `.handoff/HANDOFF-MARKETING-SUITE-AND-VECTOR-PARALLAX-2026-08-25.md`  

---

## 1. Executive Overview

This document summarizes the user requests, design philosophy, technical architecture, and current state of the **7 standalone Halbert marketing explorations** built in `/Volumes/4TB-BAD/Halbert/marketing/`.

> **Decision (2026-08-25):** Site 7 — the vector-guided parallax — is **the chosen direction**. Sites 1–6 are archived under `marketing/archive/` for reference. Site 7's palette is final: **Olivetti Vermilion & Bone** (`#D34E24` stroke on `#F7F4EE`), baked into `web-v7/shared-tokens/tokens.css`; the dev theme picker was removed.

Each site lives in its own directory with its own dependencies, Vite dev server, design token ramp, typography strategy, and bespoke interactive components.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              THE 7 MARKETING EXPLORATIONS                              │
│                                                                                        │
│  [ ARCHIVED ]  marketing/archive/web/     1960s DDB Print Ad ("I know what's wrong")   │
│  [ ARCHIVED ]  marketing/archive/web-v2/  Swiss Technical Grid + Live Oscilloscope     │
│  [ ARCHIVED ]  marketing/archive/web-v3/  Retro Serif Medium Blue & Fraunces Edition   │
│  [ ARCHIVED ]  marketing/archive/web-v4/  Minimalist Utility-First Studio Edition      │
│  [ ARCHIVED ]  marketing/archive/web-v5/  1960s Retro Graphic Typography Web Edition   │
│  [ ARCHIVED ]  marketing/archive/web-v6/  Experimental Parallax & CMYK Bleed Edition   │
│  [ CHOSEN  ]   marketing/web-v7/  PORT 5185  Vector-Guided Parallax · Vermilion & Bone │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Chronological User Requests & Directives

1. **Initial Marketing Foundation:** Build a landing page based on the 1960s first-person voice (*"I know what's wrong with me."*).
2. **A/B Theme & Copy Switcher:** Build a theme matrix tool (`ThemePicker.jsx`) to hot-swap mid-century design tokens (Archival Paper, Swiss Cobalt, Olivetti Vermilion, Charcoal Blueprint).
3. **Site 2 (Technical Grid):** Build a Swiss technical drafting edition with real-time hardware telemetry and an interactive black-box flight tape.
4. **Site 3 (Retro Serif Medium Blue):** Build a medium blue (`#1B447A`) retro serif edition with high-contrast white headlines (`Fraunces` / `DM Serif Display`).
5. **Site 4 (Minimalist Utility-First):** Build a clean Apple/Linear-style studio edition with lean copy focusing on system superpowers (*"I diagnose, remember, and protect your system."*).
6. **Site 5 (1960s Graphic Typography Web):** Rework from print ad simulator into a real, responsive website channeling 1960s bold graphic poster typography on medium cobalt blue (`#1D4ED8`).
7. **Site 6 (Experimental Parallax & CMYK Bleeds):** Break conventional rules with a 100vh hero, 148px centered logo, 80% light blue-violet SVG installation, procedural SVG noise shaders, and 2 full-window scrollytelling experiences.
8. **Site 7 (Kinetic Vector-Guided Parallax Traversal):**
   - Extreme macro zoom ($2600\%$) starting on the vertical vector stem.
   - Pure 50/50 screen split (Left: solid Chartreuse stroke with copy; Right: solid Teal background with interactive telemetry).
   - Normal downward vertical scroll at start.
   - Vector-guided curve following down to the bottom apex (transforming layout into a Top/Bottom split).
   - Perpendicular lane hops sliding laterally across concentric tracks.
   - Centering on the rounded stroke terminal cap.
   - Grand zoom-out finale pulling back to $100\%$ full mark reveal.
   - Content physically translating in sync with the camera motion.

---

## 3. Deep Dive into Site 7 (`marketing/web-v7/`) — v2 system rework (2026-08-25, later session)

The first build of Site 7 hand-tuned five camera phases. Eric's review: the trajectory was wrong — the parallax must *follow the vectors*, start with the screen split left/right, ease to rest only where the layout reads as a split through the **centre of the screen**, be zoomed in far enough that **only one line** divides the screen at any moment, and be a reusable vessel for layout, not a choreography. It was rebuilt as a data-driven system:

| File | Role |
|---|---|
| `src/lib/markGeometry.js` | Parametric model of the mark (spine + 9 lanes, stroke 32, gap 16). Generates `MARK_PATH_D`, edge paths (colour boundaries at R ± 16), tangent/normal, clearance to the next boundary, and `requiredScale()` — the zoom that guarantees a single line for a given split orientation and viewport aspect. |
| `src/lib/storyboard.js` | `STOPS[]` — pure data. Each stop = *where on the mark* (`edge+leg/y`, `edge+angle`, `cap`, or `full`) + *how to get there* (`via: 'follow' | 'fly'`, `dip`, `dwell`, `travel`). |
| `src/lib/cameraEngine.js` | Timeline (dwell/move segments), `stopPose()` (focal, zoom, layout derived from geometry), `getCameraState(s, aspect)`. `follow` rides the edge with zoom recomputed per frame; `fly` is a straight line with log-zoom and optional mid-flight dip. Smootherstep easing. |
| `src/components/LayoutStage.jsx` | Maps semantic slots (`stroke` / `canvas`, `above` / `below`) onto the fields the geometry produced: vertical, horizontal, diagonal (corner quadrants), cap, full. Content slides with the camera's direction of travel. |
| `src/content/stops.jsx` | Placeholder content per stop id. |
| `src/components/Reticle.jsx` | Press **D** for a centre crosshair + live focal/zoom/layout readout. |

Removed: `cameraMotion.js` (hard-coded phases + "magnetic plateau" easing) and `WaypointOverlay.jsx`. Added token `--color-ink-on-stroke` (tokens.css + every theme).

Current storyboard (7 stops, ≈1035vh): **open** (vertical, stroke left) → follow → **apex** (horizontal) → follow → **diagonal** (45°) → follow → **rise** (vertical, colours swapped) → fly/hop outward across three lanes → **hop** (vertical) → fly → **cap** (spine dome crest at centre) → fly → **reveal** (whole mark, 55% of short side). Verified with Playwright screenshots at every stop and mid-move at 1600×900 and 390×844: splits pass through the exact centre; one line during follows; stripes sweep during the hop.

**Round 2 (same day) — Eric's feedback and what changed:**
- *"Zoomed in too close; curve follows look like a straight line rotating."* The single-line zoom is fixed by the 16-unit gap, so zooming out always admits a second line. The fix is the **lane**: the ride moved from lane 5 (r = 224) to lane 2 inner edge (r = 80) — apex sag went from ~5% to ~14% of screen height, arc follows read as real curves, legs stay straight, zoom unchanged. `RIDE` in `storyboard.js`; per-stop `zoom` multiplier added for taste.
- *"Landscape vs portrait; only the left/right stops need a major update."* Stops now take a `portrait: {…}` override (timeline built per orientation via `timelineFor(aspect)`). Phones **open sideways** on lane 1's outer-edge apex (stroke top / canvas bottom); the first scroll flies 16 units down into the apex stop so the gap slides up and the colours flip. The remaining vertical splits (`rise`, `hop`) keep the geometry but render a **straddled** single column — each slot drawn twice, clipped to the two halves, so the type changes ink at the line (`Straddle` in `LayoutStage.jsx`).
- Horizontal layouts pad the top field by the curve's `layout.sag` so headlines clear the rising boundary.

**Round 3 (same day) — real copy + app-modelled plates.** Eric: keep the headlines, rewrite everything else; the grey plate "needs more purpose or less"; no CLI (users never use a CLI); model placeholders on the newest app UI. Research (two Explore agents over `documentation/`, `marketing/web*/src/copy`, and `halbert_core/.../dashboard/frontend`) produced:
- *Voice rules used:* first person as the host machine; embodied not personified; every adjective backed by a measured number; never "assistant" for itself; foil is "a chatbot somewhere else", never a named rival; the HAL allusion stays in text only ("you can call me AI").
- *Plates* (`src/content/ui.jsx`): paper-coloured **app windows** (the shipped app is light shadcn; the design spec is explicitly light-first, warm paper `#F7F5F0`, vermilion `#D34E24`). Four surfaces, each using the app's real IA/microcopy: **Proactive Events** (Snooze 7d / Dismiss, real detector titles like `sshd config conflict: PermitRootLogin`), **System Vitals** stat tiles, **Why does this exist?** rationale + **Evidence & Sources** refs, **Knowledge Base Storage** stat strip + `Searched Documents · 3 found`. Stops without something real to show have no plate (apex is a strip, diagonal/cap/reveal none).
- *Honesty flags surfaced by research (not changed, headline is Eric's call):* "16,000 manuals" traces to a "16K+ docs" line in `MARKETING-WEBPAGE-PLAN-2026-08-23.md`; real corpus is 24,643 docs (5,603 of them man pages). Copy now says "Linux today · macOS in beta" (no macOS packaging exists) and "no telemetry — cloud models and web search are switches, off by default" (SearXNG web search + cloud LLMs are real opt-in egress paths). Also found a data bug: `data/manifest.json` claims 4,368 Linux man pages but `data/linux/man-pages/man_pages.jsonl` holds 142 records with macOS IDs.

Full specification: `marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md` (v2.1.0).

## 4. Key Reference Files & Specification Docs

- **Master Specification Document:** [`marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md`](file:///Volumes/4TB-BAD/Halbert/marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md)
- **Project Rules (CRITICAL):** [`/Volumes/4TB-BAD/Halbert/AGENTS.md`](file:///Volumes/4TB-BAD/Halbert/AGENTS.md)
  > *Rule:* Never add "Co-Authored-By" trailers (or any "Generated with Devin" attribution) to commit messages. Commits must be clean with no bot attribution.

---

## 5. Live Ports Matrix

| Site | Directory | Port | Status |
|---|---|---|---|
| **Site 7 (chosen)** | `marketing/web-v7/` | `5185` — `npx vite --port 5185 --strictPort` | Active. Vermilion & Bone, final palette. |
| Sites 1–6 | `marketing/archive/web`, `web-v2` … `web-v6` | — | Archived 2026-08-25. Still buildable (`npm install && npm run dev` inside each) for reference. |

---

## 6. Suggested Next Steps for the Next AI / Session

1. **Site 7 polish (structure is done; these are deliberately deferred):**
   - Real copy per stop (all current copy is placeholder).
   - Mobile variants per layout kind (the geometric split holds on phones, but columns get tight).
   - ~~Chrome legibility~~ — resolved by the final palette: chrome is plain ink (`--color-ink`), legible on both bone and vermilion; the palette pill is gone.
   - Optional: pin `scale` on the apex stop if a dead-straight horizontal line is preferred over the gentle R=224 curve.
   - Storyboard tuning is data-only — add/reorder stops in `src/lib/storyboard.js`; no engine changes needed.
2. **Consolidation / Final Selection:**
   - Once Eric selects a winning direction or combination (e.g. combining the kinetic vector camera of Site 7 with the copywriting of Site 1/5 and the live oscilloscope of Site 2), assemble the production marketing build for final deployment.
