# Handoff: Halbert Marketing Suite & Kinetic Vector-Guided Parallax

**Date:** 2026-08-25  
**Author / Creative Director:** Eric Bintner  
**Handoff Target:** Next AI Agent / Engineering Session  
**File Location:** `.handoff/HANDOFF-MARKETING-SUITE-AND-VECTOR-PARALLAX-2026-08-25.md`  

---

## 1. Executive Overview

This document summarizes the user requests, design philosophy, technical architecture, and current state of the **7 standalone Halbert marketing explorations** built in `/Volumes/4TB-BAD/Halbert/marketing/`.

Each site lives in its own directory with its own dependencies, Vite dev server, design token ramp, typography strategy, and bespoke interactive components.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              THE 7 MARKETING EXPLORATIONS                              │
│                                                                                        │
│  [ SITE 1 : PORT 5173 ]  marketing/web/     1960s DDB Print Ad ("I know what's wrong") │
│  [ SITE 2 : PORT 5174 ]  marketing/web-v2/  Swiss Technical Grid + Live Oscilloscope   │
│  [ SITE 3 : PORT 5176 ]  marketing/web-v3/  Retro Serif Medium Blue & Fraunces Edition │
│  [ SITE 4 : PORT 5177 ]  marketing/web-v4/  Minimalist Utility-First Studio Edition    │
│  [ SITE 5 : PORT 5178 ]  marketing/web-v5/  1960s Retro Graphic Typography Web Edition │
│  [ SITE 6 : PORT 5179 ]  marketing/web-v6/  Experimental Parallax & CMYK Bleed Edition │
│  [ SITE 7 : PORT 5185 ]  marketing/web-v7/  Kinetic Vector-Guided 2600% Zoom Edition   │
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

## 3. Deep Dive into Site 7 (`marketing/web-v7/`)

### 3.1 Mathematical Path & Camera Equations (`src/lib/cameraMotion.js`)
- **SVG Coordinate Space:** $1024 \times 1024$.
- **Camera State:** $(\text{cx}, \text{cy}, \text{scale}, \text{rotation})$ computed continuously for scroll parameter $s \in [0, 1]$.
- **Trajectory Stages:**
  - **Phase 1 ($s \in [0.00, 0.20]$) — Straight Downward Descent:**  
    $cx = 272.0$, $cy = 160.0 \to 512.0$, $\text{scale} = 22.0$. The vertical stroke pins to the screen center, splitting the viewport 50/50.
  - **Phase 2 ($s \in [0.20, 0.44]$) — Sweeping Arc to Apex:**  
    $\theta = t \cdot \frac{\pi}{2}$, $cx = 512.0 - 240.0 \cos(\theta)$, $cy = 512.0 + 240.0 \sin(\theta)$.  
    At apex ($s = 0.44$), $cx = 512.0, cy = 752.0$ (horizontal tangent, Top/Bottom split).
  - **Phase 3 ($s \in [0.44, 0.62]$) — Perpendicular Lane Hop:**  
    Lateral translation from $(512, 752)$ across to $(368, 656)$, $\text{scale} = 20.0 \to 14.0$.
  - **Phase 4 ($s \in [0.62, 0.80]$) — Centered Rounded Shape Cap:**  
    Camera moves to $(464, 82.67)$, $\text{scale} = 18.0$, centering the rounded terminal cap in the viewport.
  - **Phase 5 ($s \in [0.80, 1.00]$) — Grand Zoom-Out Reveal:**  
    Camera smoothly pulls back to $(512, 512)$ with $\text{scale} = 1.0$, revealing the complete centered Halbert mark.
- **Magnetic Plateau Easing:** Piecewise trigonometric damping ($s_{\text{eased}}$) gently slows down scroll velocity at key waypoints without locking the user out of fluid scrolling.

### 3.2 Viewport Aspect-Ratio Calibration (`src/components/VectorCanvas.jsx`)
To prevent slicing, stretching, or focal reticle drift on widescreen monitors (e.g. 16:9 or ultrawide):
```javascript
const aspect = dimensions.width / Math.max(1, dimensions.height);
const h = 1024 / Math.max(0.1, camera.scale);
const w = h * aspect;
const minX = camera.cx - w / 2;
const minY = camera.cy - h / 2;
```
This guarantees that $(\text{cx}, \text{cy})$ is **mathematically locked to $(50\text{vw}, 50\text{vh})$ in the dead center of the screen on every device**.

### 3.3 Synchronized Kinetic Content Motion (`src/components/WaypointOverlay.jsx`)
Content nodes translate continuously based on scroll offsets:
- Hero: `transform: translateY(-offset0 * 1400px)` (scrolls up as camera descends).
- Apex: `transform: translateY(-offset1 * 1200px)` (curves up into view).
- Lane Hop: `transform: translateX(-offset2 * 1000px)` (glides laterally).
- Shape Cap: `transform: translateY(-offset3 * 900px)`.
- Grand Reveal: `transform: scale(scale4)`.

---

## 4. Key Reference Files & Specification Docs

- **Master Specification Document:** [`marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md`](file:///Volumes/4TB-BAD/Halbert/marketing/VECTOR-PARALLAX-VISION-AND-SPECIFICATION.md)
- **Project Rules (CRITICAL):** [`/Volumes/4TB-BAD/Halbert/AGENTS.md`](file:///Volumes/4TB-BAD/Halbert/AGENTS.md)
  > *Rule:* Never add "Co-Authored-By" trailers (or any "Generated with Devin" attribution) to commit messages. Commits must be clean with no bot attribution.

---

## 5. Live Ports Matrix

| Site | Directory | Port | URL | Description |
|---|---|---|---|---|
| **Site 1** | `marketing/web/` | `5173` | `http://localhost:5173/` | 1960s DDB Print Ad Edition |
| **Site 2** | `marketing/web-v2/` | `5174` | `http://localhost:5174/` | Swiss Grid + Oscilloscope |
| **Site 3** | `marketing/web-v3/` | `5176` | `http://localhost:5176/` | Retro Serif Blue Editorial |
| **Site 4** | `marketing/web-v4/` | `5177` | `http://localhost:5177/` | Minimalist Studio Edition |
| **Site 5** | `marketing/web-v5/` | `5178` | `http://localhost:5178/` | 1960s Graphic Typography |
| **Site 6** | `marketing/web-v6/` | `5179` | `http://localhost:5179/` | Full-Window Parallax & CMYK |
| **Site 7** | `marketing/web-v7/` | `5185` | `http://localhost:5185/` | Vector-Guided Kinetic 2600% Zoom |

---

## 6. Suggested Next Steps for the Next AI / Session

1. **Fine-tune Site 7 Kinetic Polish (if requested):**
   - Add subtle SVG line-draw stroke dasharray animations along the active vector path during scroll traversal.
   - Add mouse parallax / cursor tilt response to the macro canvas.
2. **Consolidation / Final Selection:**
   - Once Eric selects a winning direction or combination (e.g. combining the kinetic vector camera of Site 7 with the copywriting of Site 1/5 and the live oscilloscope of Site 2), assemble the production marketing build for final deployment.
