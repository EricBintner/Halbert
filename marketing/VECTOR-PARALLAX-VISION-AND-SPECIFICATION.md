# Halbert Marketing Site V7: Vector-Guided Parallax — System Specification

**Document Version:** 2.2.0
**Date:** 2026-08-25
**Author:** Eric Bintner (Art Direction & Creative Vision)
**Location:** [`marketing/web-v7/`](file:///Volumes/4TB-BAD/Halbert/marketing/web-v7/)
**Supersedes:** v1.0.0 (the hand-tuned five-phase camera in `cameraMotion.js`, now removed)

---

## 1. What this is

The Halbert mark, zoomed in far enough that a single stroke boundary becomes a **line dividing the screen into two solid colour fields**. The camera rides that boundary; wherever it comes to rest, the screen is a clean split — left/right, top/bottom, or a 45° diagonal — with the stroke colour on one side and the canvas colour on the other. Those rests are the **stops**: vessels for typography and graphic-design layout. The copy in them is placeholder.

The point of v2 is that this is a *system*, not a choreography:

- **Stops are data** (`src/lib/storyboard.js`). A stop says *where on the mark* the screen centre sits and *how we travel* there. Nothing else.
- **Everything visual is derived** from the mark's geometry (`src/lib/markGeometry.js`) by the camera engine (`src/lib/cameraEngine.js`): the focal point, which side is which colour, the orientation of the split, and the zoom needed so that only one boundary is visible.
- **Content is authored per stop in semantic slots** — `stroke` (on the stroke-coloured field) and `canvas` (on the canvas-coloured field). The layout stage (`src/components/LayoutStage.jsx`) puts each slot wherever the geometry has placed that colour.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  STOP = where on the mark  ──►  ENGINE derives  ──►  STAGE places slots  │
│                                                                          │
│  { edge:{lane:5,side:'inner'},    focal (288, 330)       stroke ▌ canvas │
│    leg:'left', y:330 }            normal → stroke = −x   (left)  (right) │
│                                   split: vertical                        │
│                                   zoom: 6465% @16:9                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The geometry (`markGeometry.js`)

1024 × 1024 coordinate space, centre **C = (512, 512)**.

| Element | Definition |
|---|---|
| Spine | vertical, x = 512, y ∈ [80, 512] |
| Lane *i* (1‥9) | U-shape of radius **R = 48 i**: left leg down, bottom semicircle, right leg up |
| Leg tops | on the circle of radius 432 around C: `y_top = 512 − √(432² − R²)` (lane 9 has no legs) |
| Stroke | width **32**, round caps |
| Gap between strokes | **16** (pitch 48 − width 32) |

`MARK_PATH_D` is generated from this model and reproduces the original hand-written path to the same precision; `HalbertMark` and `VectorCanvas` both use it.

**Edge paths.** The colour boundary on either side of a lane has the same U shape with radius **R ± 16** (`edgePath(lane, side)`). It is parametrised by arc length `u`: left leg (top→bottom), semicircle, right leg (bottom→top). `edgePointAt(edge, u)` returns the point, the tangent, and `toStroke` — the unit normal pointing into the coloured stroke. Author-friendly locations convert to `u` with `edgeU`: `{ leg:'left'|'right', y }` on a leg, or `{ angle }` on the arc (0° = left-bottom, 90° = apex, 180° = right-bottom).

**Caps.** `capPoint('spine')` (or `{ lane, leg }`) is the crest of a rounded stroke terminal, with `toStroke` pointing down into the dome.

**Clearance.** `edgeClearance` is the distance from an edge to the next colour boundary along the normal — 16 (the gap) almost everywhere; 32 on the open outside of the mark.

**Zoom.** `requiredScale(normal, clearance, aspect)` is the minimum camera scale such that the viewport's half-extent along the normal stays inside the clearance (12% margin):

```
scale ≥ 512 · (aspect·|nₓ| + |n_y|) / (clearance · 0.88)
```

This is what keeps **exactly one line on screen**, and why the numbers are large: at 16:9 a vertical split needs ~6465%, a horizontal one ~3636%, a 45° diagonal ~7142%, the cap ~3232%; on a portrait phone the vertical split drops to ~1818%. Nothing is hard-coded — a stop may still pin `scale` explicitly or apply a `zoom` multiplier.

**Curvature is a lane choice, not a zoom choice.** Because the single-line zoom is fixed by the 16-unit gap, it is the same on every lane; what changes with the lane is how much of the curve you see at that zoom. Sag at the frame's side edges is `(w/2)² / 2r` — on lane 5 (r = 224) the apex bows only ~5% of the screen height and follows look like a straight line rotating; on lane 2 (r = 80) the apex bows ~14% and the arc follows read as real curves, while the legs stay dead straight. The storyboard rides lane 2's inner edge for this reason (`RIDE` in `storyboard.js`).

---

## 3. The camera engine (`cameraEngine.js`)

**Timeline.** The scroll axis is a sequence of `dwell` (camera still) and `move` segments built from the stops' `dwell` and `travel` weights (viewport heights). The page height is `totalWeight × 100vh` (currently ≈ 1035vh). `stopCenterS(i)` gives the normalised scroll position of a stop's dwell centre (used by the HUD).

**Poses.** `stopPose(stop, aspect)` resolves a stop into `{ cx, cy, scale, normal, layout }`. `layout.kind` is `vertical | horizontal | diagonal | cap | full`, with `strokeSide` (`left/right`, `top/bottom`, or a corner such as `bottom-right`).

**Moves** — the transition *into* a stop, chosen with `via`:

| via | motion | when to use |
|---|---|---|
| `follow` | focal point rides the same edge from `u_A` to `u_B`; zoom is recomputed every frame from the local tangent so one boundary stays on screen while the line rotates | consecutive stops on the same lane & side |
| `fly` | straight line between focal points, log-interpolated zoom; optional `dip` (0‥1) pulls the zoom back mid-flight so the lanes sweep past | lane hops, going to a cap, the zoom-out |

A `follow` between stops on different edges falls back to `fly` with a console warning.

**Per-stop knobs.** `zoom` multiplies the derived scale (1 = strict single line; < 1 lets the neighbouring boundary into the frame edges). `dip` works on both `fly` and `follow`. `portrait` holds any overrides (including a replacement `at`) merged in when the viewport is taller than wide — the timeline is built per orientation (`timelineFor(aspect)`), so dwell/travel may differ too.

**Easing.** Every move uses smootherstep (`6t⁵ − 15t⁴ + 10t³`): zero velocity *and* acceleration at both ends, so the camera settles into each stop rather than snapping. Within a dwell the pose is exactly constant.

**Invariants**
1. `(cx, cy)` renders at the exact centre of the viewport on every device (`viewBoxFor` sizes the viewBox from the live aspect; 1 mark unit is the same number of pixels in x and y).
2. While dwelling on an edge stop, and throughout a `follow`, the screen centre lies *on* a colour boundary and no other boundary is visible.
3. Rotation is never used. Split orientation comes from where we are on the U: legs give vertical splits, the apex a horizontal one, 45° along the arc a diagonal. Riding one edge from the left leg round to the right leg also swaps which side is stroke-coloured for free.

`getCameraState(s, aspect)` returns the pose plus `phase`, `stopIndex`, `layout`, `poses[]` for every stop, and during a move `{ from, to, t, dir }` where `dir` is the instantaneous direction of camera travel. Edge-stop layouts also carry `sag` — the curve's rise at the frame edges as a fraction of viewport height — so layouts can keep type clear of the boundary.

---

## 4. The layout stage (`LayoutStage.jsx`, `content/stops.jsx`)

| layout.kind | slot placement |
|---|---|
| `vertical` | two columns; `stroke` in the column on `strokeSide`. **Portrait:** one stacked column that *straddles* the split — each slot is rendered twice, clipped to the left and right halves of the viewport, so the type runs straight across the line and changes ink at it (`Straddle`). |
| `horizontal` | two rows; the top row's bottom padding grows by `layout.sag` so headlines don't touch the rising curve |
| `diagonal` | 2×2 grid; `stroke` in the `strokeSide` corner, `canvas` in the opposite corner (clean for 45° splits, since a 45° line through the centre never enters the opposite quadrants) |
| `cap` | `canvas` in the top half; `stroke` centred on the dome in the bottom half |
| `full` | `above` and `below` bands around the mark |

Ink colours: `--color-ink` on the canvas field, `--color-ink-on-stroke` on the stroke field (a new token in `shared-tokens/tokens.css` and every entry of `themes.js`).

**Content motion.** During a move the outgoing stop's content slides *against* `dir` and fades; the incoming stop's slides in *along* `dir`. Offsets are capped at 60% of the viewport so content never has to travel the (enormous) real camera distance.

---

## 5. The current storyboard

| # | id | at (landscape) | via | resulting split | portrait |
|---|---|---|---|---|---|
| 01 | `open` | lane 2 inner edge, left leg, y 330 | — | vertical · stroke left / canvas right | **starts sideways**: lane 1 outer edge, 90° → horizontal · stroke top / canvas bottom |
| 02 | `apex` | lane 2 inner edge, 90° | follow | horizontal · canvas top / stroke bottom | fly 16 units straight down from the portrait open — the gap slides up, colours flip |
| 03 | `diagonal` | lane 2 inner edge, 135° | follow | 45° · canvas top-left / stroke bottom-right | same |
| 04 | `rise` | lane 2 inner edge, right leg, y 330 | follow | vertical · canvas left / stroke right | same split, straddled single-column type |
| 05 | `hop` | lane 5 outer edge, right leg, y 330 | fly, dip 0.6 | vertical · stroke left / canvas right | same split, straddled single-column type |
| 06 | `cap` | crest of the spine's cap (512, 64) | fly, dip 0.25 | dome rising to the centre | same |
| 07 | `reveal` | whole mark (50% of the short side) | fly | headline above, CTA below | same |

In landscape, stops 01→04 are one continuous ride along a single edge (lane 2, inner); 05 is the perpendicular hop outward (three lanes sweep past); 06 and 07 are the two deliberate departures from path-following. In portrait only the vertical-split stops needed rethinking: the opener becomes a top/bottom split that the first scroll animates out of, and the two remaining vertical splits keep the geometry but change the type treatment.

---

## 6. Authoring guide

- **Add a stop:** append to `STOPS`. Choose `at`, choose `via` (`follow` if it is on the same lane & side as the previous stop), optionally `dwell`, `travel`, `dip`, `scale`. Add content under the same `id` in `content/stops.jsx` using the slots the resulting layout exposes.
- **Diagonal stops** should sit at 45° or 135° along the arc so the corner-quadrant placement stays inside the triangles.
- **More or less curve:** change `RIDE.lane` (smaller = curvier at the same zoom). Lane 1's inner edge (r = 32) is too tight — the apex stops reading as a split.
- **Portrait:** add a `portrait: { … }` block to a stop for anything that should differ on phones; leave it off when the landscape layout already works there (apex, diagonal, cap, reveal all do).
- **Reticle:** press **D** in the browser to show the screen-centre crosshair with the live focal point, zoom, and layout — the quickest way to verify that a new stop splits through the centre.
- **Verification:** `node --input-type=module -e 'import {getCameraState,stopPose} from "./src/lib/cameraEngine.js"; …'` runs the engine headlessly (it has no DOM dependency); `npx vite build` type-checks the wiring.

---

## 7. Palette (final)

**Olivetti Vermilion & Bone**, chosen 2026-08-25 and baked into `shared-tokens/tokens.css`; the dev theme picker was removed.

| Token | Value | Role |
|---|---|---|
| `--color-canvas` | `#F7F4EE` | bone — the canvas field |
| `--color-stroke` | `#D34E24` | letterpress vermilion — the vector stroke / stroke field |
| `--color-ink` | `#1C1917` | type on the bone field, and all fixed chrome |
| `--color-ink-on-stroke` | `#FFF7ED` | type on the vermilion field |
| `--color-ink-secondary` / `-tertiary` | `#44403C` / `#78716C` | secondary type on bone |

The app-window plates (`content/ui.jsx`) use the design-spec paper values (`#F7F5F0` / `#FFFFFF`, ink `#1A1918`, accent `#D34E24`), so on the bone field they read as a lifted window and on vermilion as a bright one — the same accent unifies the two.

---

## 8. Known polish items (deliberately deferred)

- Copy is real as of round 3 (headlines fixed by Eric; body/kickers/CTA written to the voice rules in `content/stops.jsx`). Plates in `content/ui.jsx` are static placeholders for the app's Proactive Events, Vitals, WhyBrain/WhyChip and Knowledge Base surfaces — to be replaced by animated library components.
- "I know 16,000 manuals by heart" overstates man pages (5,603) and understates the corpus (24,643 docs); flagged, not changed.
- The apex curve is now deliberate (lane 2); pin `scale` or raise `RIDE.lane` to flatten it.
- Portrait slot content is the same JSX as landscape; stops may want portrait-specific copy lengths once real copy lands.
