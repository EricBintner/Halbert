# Plan & Result: Undo the Split-Headline Effect (web-v7 → web-v9)

**Date:** 2026-09-14
**Author:** Eric Bintner + session
**Status:** DONE — `marketing/web-v9/` built and verified

---

## Scope correction (supersedes the earlier draft of this doc)

The first attempt at this task (a "web-v8" with paper cards behind every stop's
content) was a redesign the founder never asked for, and it was **deleted**. The
founder clarified the actual target: the **split headline** — a headline rendered
half white and half black because text was drawn twice and clipped at the screen's
vertical midline so the ink flips at the colour boundary (the `Straddle`
component). That was the *only* thing to undo. Everything else — the field system,
the left/right grid, the plates, the copy, all post-split work — stays exactly
as v7 has it.

## What the split headline was

- `Straddle` (in `LayoutStage.jsx`): renders the slot content **twice**, in two
  absolutely-positioned copies clipped to the left and right halves of the
  viewport (`clipPath: inset(0 50% 0 0)` / `inset(0 0 0 50%)`), in the two ink
  colours, so a headline crossing the midline reads half `--color-ink-on-stroke`
  (white on vermilion) and half `--color-ink` (black on bone).
- It was used **only in portrait** (`PortraitVerticalLayout`), reached on exactly
  two stops: **`rise` (04)** and **`hop` (05)** — the two vertical-split stops in
  the portrait storyboard. Desktop never rendered it (landscape uses the plain
  `grid-cols-2` left/right slot layout, unchanged).
- It originated in `ead3d798` (Aug 25) as the portrait adaptation of the split
  layout, and was the "mobile friendly" change the founder asked to undo.

## What v9 is

`marketing/web-v9/` is a byte-copy of v7 (all post-split commit work — final
palette, token dictionary, type triad, logo suite, component consolidation — is
included because none of it touched the split) with **one purely subtractive
change** in `src/components/LayoutStage.jsx`:

- Deleted `Straddle` and `PortraitVerticalLayout`.
- `VerticalLayout` no longer branches on portrait; it renders the same
  left/right `grid-cols-2` slot layout in both orientations.
- Dropped the now-unused `portrait` prop plumbing in `LayoutStage`.
- Updated the file's doc comment to match.

`diff -r` confirms: **the only source-level difference from v7 is that one
file**, plus package name (`halbert-marketing-v9`), version (`9.0.0`), and dev
port (`5187`, in `vite.config.js` and `.claude/launch.json`). No content, no
copy, no plates, no engine files touched.

## Verification (dev server on 5187)

- No console errors.
- DOM: zero `clipPath` elements, zero duplicated aria-hidden text copies — the
  straddle machinery is gone from the render at any scroll position.
- Mobile viewport (375×812), `rise` stop: headline fully in the left bone field
  in black ink; plate fully in the right vermilion field in white ink; container
  is `grid grid-cols-2` — same layout as desktop. Screenshot confirmed.
- Mobile viewport, `hop` stop: same — plain grid, both slots one-ink-each.
  Screenshot confirmed.
- Desktop layout was never affected (it never used Straddle) and is untouched.

## Dev commands

```bash
cd marketing/web-v9 && npx vite --port 5187 --strictPort
```

Or `.claude/launch.json` → `marketing-web-v9`.

## Not done (deliberately)

- Nothing else. The founder's future mobile-only split-variant idea (splitting
  the screen via vector placement/orientation) is a separate task and was not
  touched.
- The failed v8 redesign no longer exists on disk; only this doc records it.