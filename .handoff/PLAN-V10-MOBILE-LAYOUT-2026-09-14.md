# Plan: web-v10 — Mobile/Portrait Layout Pass (per-stop review)

**Date:** 2026-09-14
**Status:** BUILT — rise/hop rotated to horizontal splits, cap overflow fixed,
reveal enlarged; all verified at 375×812 with landscape confirmed unchanged.

v10 is a byte-copy of v9 (identity only: `halbert-marketing-v10`, port 5188).
Dev server: `.claude/launch.json` → `marketing-web-v10`. LAN phone testing:
`http://192.168.86.22:5188` (the .87 address is a dead second interface).

---

## How portrait works today (the machinery under review)

The storyboard already carries per-stop `portrait` overrides — but only some
stops have one, and the overrides only change **camera geometry** (where the
camera rests and what split orientation it produces). Content layout is then
derived from that geometry:

| Stop | Portrait split (measured) | Content placement |
|---|---|---|
| 01 open | horizontal (stroke top / canvas bottom) | headline top, plate bottom — OK |
| 02 apex | horizontal (canvas top / stroke bottom) | OK |
| 03 diagonal | 45° corner-to-corner | headline+body top-left corner, kicker bottom-right — tight but works |
| **04 rise** | **vertical (canvas left / stroke right)** | **two narrow columns** |
| **05 hop** | **vertical (stroke left / canvas right)** | **two narrow columns** |
| 06 cap | stroke dome rising to center | thesis top, tagline bottom — OK |
| 07 reveal | full mark | bands above/below — OK |

Note: `rise` and `hop` are the two stops from the v9 revert — and they are the
only two that need real work. Their portrait storyboard entries have **no
override**, so the camera keeps the landscape vertical split (the graphic
divides the screen left/right), and v9's fix renders the two slots into the two
half-width columns. On a 375px phone that's ~170px per column of body text and
a shrunken plate.

## The two problem stops — the founder's proposed fix

**Observed (screenshots):** on `rise` (04) and `hop` (05) in portrait, the
vermilion stroke runs vertically down the screen's midline. The headline +
body are crammed into the left half; the app plate is squeezed into the right
half. Readable but cramped — roughly half of each slot's desktop space.

**Founder's idea:** rotate the split 90° for these two stops in portrait — so
the boundary runs **horizontally** across the phone (top/bottom fields like
`open` and `apex` already do), giving each slot the full 375px width. Two ways
to implement:

- **A. Rotate the camera target (recommended).** Give `rise`/`hop` portrait
  overrides that rest the camera on a *horizontal* boundary of the mark
  (the arc apex or a leg crossing), like `open` and `apex` already do. The
  storyboard already supports this — `open.portrait.at` is exactly such an
  override. Data-only change: add `portrait: { at: … }` to `rise` and `hop`;
  no engine code.
- **B. Rotate the rendered scene.** Keep the camera on the vertical edge but
  rotate the whole vector canvas 90° in portrait for these stops. Hacky; the
  viewBox math (`viewBoxFor`) is aspect-derived and rotation would distort or
  letterbox. Not recommended.

Option A's risk: `rise` and `hop` currently ride lane 2's inner edge on a
*leg* (straight vertical segment) — there is no horizontal boundary at that
spot. The override would jump the camera to the nearest horizontal boundary
(arc apex / leg bottom), which changes the dwell composition slightly (the
visible curve differs from the landscape stop). Needs a visual check per stop
once applied; the storyboard makes this tunable (`angle`, `dip`, `zoom`).

### Questions for the founder (rise/hop) — RESOLVED

Founder approved option A (camera-override rotation). Applied:

- **rise (04)**: `portrait.at = { edge: { lane: 3, side: 'inner' }, angle: 90 }` —
  lane 3's arc apex (one ring out from the apex stop, keeping the dwell
  distinct). Canvas (headline) TOP, stroke (plate) BOTTOM. Verified.
- **hop (05)**: `portrait.at = { edge: { lane: 5, side: 'outer' }, angle: 90 }` —
  keeps its lane-5-outer character. Stroke (headline) TOP, canvas (plate)
  BOTTOM. Verified.

## Round 2 (same session, founder review on phone)

- **cap (06) — white text beyond the red area**: at the spine cap the
  vermilion is a 32-unit sliver; the white tagline was wider than the sliver
  and spilled onto bone. Fixed the same way: `portrait.at = { edge: { lane: 4,
  side: 'inner' }, angle: 90 }` (a ring in from hop's lane 5) — thesis on bone
  TOP, tagline on solid vermilion BOTTOM. Verified.
- **reveal (07) — mark tiny in the frame**: `fitScale(aspect, 0.44)` fits the
  mark to 44% of the *shorter* side = the phone's width (~165px in an 812px
  frame). Fixed with `portrait.zoom = 2.0` (mark spans 88% of the width,
  ~330px) and matched `FullLayout`'s spacer to the stop's zoom so the
  above/below bands clear the mark (spacer is now portrait-aware: 88vmin vs
  44vmin). Verified.
- Landscape re-verified at 1600×800: cap still renders its spine-dome `cap`
  layout, reveal spacer still 44% of height — desktop untouched.

## Other stops — minor, need founder eyes

- **03 diagonal (portrait):** content sits in opposite corners (top-left
  headline+body, bottom-right kicker "Runs on Ollama"). The corner grid leaves
  generous whitespace; the 45° line passes between them. Looks intentional.
  Q: any tightening wanted, or leave as-is?
- **06 cap (portrait):** thesis headline + body in the top canvas field,
  "I am the machine." italic + kicker in the vermilion dome below. Comfortable.
  Q: leave as-is?
- **07 reveal (portrait):** full mark centered at 44vmin, "// MEET HALBERT."
  + headline above, email form + links below. Comfortable. Q: leave as-is?
- **01 open / 02 apex (portrait):** already horizontal via storyboard
  portrait overrides; look good. No action proposed.

## Non-goals

- No desktop changes. All of this is portrait-only via storyboard `portrait`
  overrides and, if needed, a portrait branch in `LayoutStage` layouts.
- No content/copy changes.
- No redesign beyond the two problem stops; the other five get at most minor
  padding/scale tweaks if the founder asks.

## Next steps once founder answers

1. Add `portrait` overrides to `rise` and `hop` in `storyboard.js` (option A
   shape: `at: { edge: …, angle: 90 }` style targets).
2. Re-screenshot those stops at portrait; iterate on `zoom`/`dwell` until the
   split passes through center with both fields generous.
3. Apply any minor tweaks the founder requests on 03/06/07.
4. Commit v10.

## Capture method (for reproducibility)

Playwright npm package unavailable (offline); chrome-headless-shell crashes
under the app sandbox (MachPortRendezvous denied). Captured instead via the
Browser pane: `preview_resize` to mobile 375×812, `scrollTo` each stop's dwell
fraction, `preview_screenshot`. Scroll fractions measured from
`timelineFor(aspect)` weights: open .028, apex .159, diagonal .303, rise .446,
hop .610, cap .774, reveal .954.