# Halbert Marketing Site V7: Kinetic Vector-Guided Parallax Specification

**Document Version:** 1.0.0  
**Date:** 2026-08-25  
**Author:** Eric Bintner (Art Direction & Creative Vision)  
**Location:** [`marketing/web-v7/`](file:///Volumes/4TB-BAD/Halbert/marketing/web-v7/)  

---

## 1. Executive Summary & Creative Vision

Traditional SaaS marketing websites rely on predictable, repetitive patterns: a generic navbar, a hero section with floating glassmorphic cards, three icon boxes, and a generic dark-mode screenshot.

**Halbert Site V7 completely rejects this paradigm.** Instead, the website is built upon a **continuous, vector-guided camera traversal** through the physical geometry of Halbert’s authentic vector brand mark at **1000% macro zoom**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       KINETIC VECTOR TRAVERSAL CONCEPT                      │
│                                                                             │
│   STAGE 01: MACRO VERTICAL STEM      STAGE 02: THE SWEEPING APEX            │
│   ┌──────────────┬──────────────┐    ┌─────────────────────────────┐        │
│   │              │              │    │  HEADLINE & PROSE (TOP)     │        │
│   │   ALL COPY   │  INTERACTIVE │    ├─────────────────────────────┤        │
│   │  & HEADLINE  │   GRAPHIC    │    │ ═════ HORIZONTAL APEX ═════ │        │
│   │    (LEFT)    │   (RIGHT)    │    ├─────────────────────────────┤        │
│   │              │              │    │  SENSORY TELEMETRY (BOTTOM) │        │
│   └──────────────┴──────────────┘    └─────────────────────────────┘        │
│          ▲                                          ▲                       │
│     [CENTERLINE STROKE                     [CURVE SWEEP TRANSFORMS          │
│     SPLITS SCREEN L/R]                      SPLIT TO TOP/BOTTOM]            │
│                                                                             │
│   STAGE 03: PERPENDICULAR HOP        STAGE 04: ROUNDED SHAPE CAP            │
│   [Camera slides laterally           [Camera centers on rounded cap         │
│   across concentric lanes]           of the inner core vector]              │
│                                                                             │
│   STAGE 05: GRAND ZOOM-OUT REVEAL                                           │
│   [Camera pulls back from 1000% → 100%, revealing the entire Halbert mark]  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Geometric & Motion Principles

### 2.1 The Authentic SVG Geometry
The viewport travels along the **exact, authentic Halbert brand SVG** (`1024 × 1024` coordinate space), with no extraneous duplicate strokes or artificial fake paths:

- **Central Vertical Spine:** `M 512.00 80.00 V 512.00`
- **Concentric U-Curves (10 lanes):**
  - Lane 1: $R = 48$, starts at $x = 464, y = 82.67$, sweeps down to apex at $y = 560$, up to $x = 560$.
  - Lane 2: $R = 96$, starts at $x = 416, y = 90.80$, sweeps down to apex at $y = 608$, up to $x = 608$.
  - Lane 3: $R = 144$, starts at $x = 368, y = 104.71$, apex at $y = 656$.
  - Lane 4: $R = 192$, starts at $x = 320, y = 125.01$, apex at $y = 704$.
  - Lane 5: $R = 240$, starts at $x = 272, y = 152.80$, apex at $y = 752$.
  - Lane 6: $R = 288$, starts at $x = 224, y = 190.01$, apex at $y = 800$.
  - Lane 7: $R = 336$, starts at $x = 176, y = 240.47$, apex at $y = 848$.
  - Lane 8: $R = 384$, starts at $x = 128, y = 314.09$, apex at $y = 896$.
  - Lane 9: $R = 432$, starts at $x = 80.00, y = 512.00$, sweeps to apex at $y = 944$.

### 2.2 Screen-Splitting Alignment
At 1000% macro zoom, the center of the viewport is pinned directly to the vector centerline:
1. **Vertical Vector Alignment (Left / Right Division):**
   - When the vector is vertical, the massive colored stroke acts as the visual spine dividing the viewport into two balanced halves.
   - **Left Column:** All copy and headlines are strictly formatted within the left field.
   - **Right Column:** The interactive graphic, telemetry terminal, or data plate sits strictly within the right field.
2. **Horizontal Apex Alignment (Top / Bottom Division):**
   - As the camera follows the curve around to the apex, the vector tangent rotates to horizontal.
   - The layout seamlessly morphs into a **Top / Bottom division**:
     - **Top Field:** Headline, premise, and thesis prose.
     - **Bottom Field:** High-contrast sensory diagnostic meters (16 thermal diodes, SMART drive wear).
3. **Centered Shape Focus (The Rounded Cap):**
   - When deviating from path-following, the camera centers directly on the rounded circular cap / terminal end of a shape (e.g. $(x=512, y=80)$ or $(x=464, y=82.67)$), framing content radially around the focal cap.
4. **Perpendicular Lane Hops:**
   - The camera slides laterally perpendicular to the vector tangent, hopping across the concentric tracks to introduce the next chapter of information (e.g. Configuration Archaeology).
5. **Grand Zoom-Out Finale:**
   - The camera pulls back smoothly from $10\times \to 1\times$, revealing the monumental Halbert mark in full symmetry, accompanied by the soul statement (*"I am the machine."*) and early access dispatch registry.

---

## 3. Sophisticated Scroll Mechanics (Magnetic Plateau Easing)

To ensure the experience feels organic without rigidly locking the user out of fluid scrolling:
- **Continuous Parameter $s \in [0, 1]$:** Mapped across a $500\text{vh}$ virtual scroll track.
- **Trigonometric Magnetic Damping:**
  $$s_{\text{eased}} = s_k + (s - s_k) \cdot \left(0.35 + 0.65 \sin\left(\frac{|s - s_k|}{r} \cdot \frac{\pi}{2}\right)\right)$$
  Near waypoint centers ($|s - s_k| < r$), scroll velocity naturally slows down, allowing the user to effortlessly read content and interact with plates before resuming forward momentum.
- **Waypoint Scrubber HUD:** A minimalist vertical track on the screen edge displays exact travel percentage and enables one-click smooth tweening to any keyframe.

---

## 4. Color Palette & Physical Shader Grit

- **Primary Canvas:** Deep Aegean Teal / Cyan (`#0F766E` / `#008080`).
- **Vector Stroke:** Pop Chartreuse / Electric Lime (`#D4E157` / `#CCFF00`).
- **Typography:** Crisp Paper White (`#FFFFFF`) with subtle CMYK chromatic edge misregistrations (`cmyk-edge`).
- **Textures:** Procedural SVG fractal noise shader for authentic physical paper grit.
