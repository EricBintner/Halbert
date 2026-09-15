/**
 * Storyboard — the ordered list of STOPS the camera rests at.
 *
 * A stop is a *place on the mark* plus how we travel into it. Everything
 * visual (where the split line is, which side is stroke-coloured, how far to
 * zoom) is derived from the geometry by the camera engine, so authoring a
 * stop means answering only:
 *
 *   at        where the screen centre sits
 *               { edge: { lane, side }, leg: 'left'|'right', y }  on a leg
 *               { edge: { lane, side }, angle }                   on the arc (0..180)
 *               { cap: 'spine' | { lane, leg } }                  crest of a rounded cap
 *               { full: true }                                    the whole mark
 *   via       how we get here from the previous stop
 *               'follow'  ride the edge (only possible on the same edge)
 *               'fly'     straight line to the new focal point
 *   dip       0..1 — pull the zoom back mid-move so the lanes sweep past;
 *             0 keeps the zoom locked (default for follow)
 *   zoom      multiplier on the derived single-line zoom (1 = strict; <1 lets
 *             the neighbouring boundary into the frame edges)
 *   dwell     scroll length (in viewport heights) the camera holds still here
 *   travel    scroll length of the move INTO this stop
 *   portrait  any of the above, merged in when the viewport is taller than
 *             wide (`at` is replaced wholesale)
 *
 * Which lane we ride sets how much curve is visible: the zoom needed for a
 * single line is the same on every lane (it is fixed by the 32-unit gap), so
 * a tighter lane shows more curvature at the same zoom. Lane 2 (inner edge,
 * r = 124) gives a clearly curved apex/diagonal while the legs stay straight.
 */

const RIDE = { lane: 2, side: 'inner' };

export const STOPS = [
  {
    id: 'intro',
    name: 'Meet Halbert',
    at: { edge: { lane: 2, side: 'outer' }, leg: 'left', y: 330 },
    dwell: 0.6,
    // landscape — vertical split: canvas LEFT, stroke RIGHT
    portrait: {
      // phones: start at apex of lane 1's inner edge
      at: { edge: { lane: 1, side: 'inner' }, angle: 90 },
      // horizontal split: canvas TOP, stroke BOTTOM
    },
  },
  {
    id: 'open',
    name: 'Triage',
    at: { edge: RIDE, leg: 'left', y: 330 },
    via: 'fly',
    travel: 0.8,
    dwell: 0.55,
    // landscape — vertical split: stroke LEFT, canvas RIGHT
    portrait: {
      // phones start sideways: the apex of lane 1's outer edge, one gap above
      // the apex stop, so the first scroll slides the gap up and flips colours
      at: { edge: { lane: 1, side: 'outer' }, angle: 90 },
      via: 'fly',
      travel: 0.8,
      // horizontal split: stroke TOP, canvas BOTTOM
    },
  },
  {
    id: 'apex',
    name: 'Automation',
    at: { edge: RIDE, angle: 90 },
    via: 'follow',
    dwell: 0.6,
    // horizontal split: canvas TOP, stroke BOTTOM
    portrait: { via: 'fly', travel: 0.7 },
  },
  {
    id: 'diagonal',
    name: 'Local',
    at: { edge: RIDE, angle: 135 },
    via: 'follow',
    travel: 0.8,
    dwell: 0.6,
    // 45° split: canvas TOP-LEFT, stroke BOTTOM-RIGHT
  },
  {
    id: 'rise',
    name: 'Rationale',
    at: { edge: RIDE, leg: 'right', y: 330 },
    via: 'follow',
    travel: 0.8,
    dwell: 0.6,
    // vertical split, colours swapped: canvas LEFT, stroke RIGHT
    portrait: {
      // phones: the leg's vertical split would halve every column, so rest
      // on a horizontal boundary instead — lane 3's inner apex (a ring out
      // from the apex stop, keeping this dwell visually distinct). Split
      // runs across the phone: canvas TOP (headline), stroke BOTTOM (plate).
      at: { edge: { lane: 3, side: 'inner' }, angle: 90 },
      via: 'fly',
    },
  },
  {
    id: 'hop',
    name: 'Knowledge',
    at: { edge: { lane: 5, side: 'outer' }, leg: 'right', y: 330 },
    via: 'fly',
    dip: 0.6,
    dwell: 0.6,
    // perpendicular slide outward across three lanes; vertical split: stroke LEFT, canvas RIGHT
    portrait: {
      // phones: same treatment, keeping this stop's lane-5-outer character —
      // rest on lane 5's outer apex. Split runs across the phone with the
      // stroke TOP (headline) and canvas BOTTOM (plate).
      at: { edge: { lane: 5, side: 'outer' }, angle: 90 },
    },
  },
  {
    id: 'cap',
    name: 'Distributed',
    at: { cap: 'spine' },
    via: 'fly',
    dip: 0.25,
    dwell: 0.6,
    // rounded cap: canvas TOP half, stroke dome rising to the centre.
    // The derived cap zoom is set by the spine-to-lane-1 clearance
    // (52 units), which in the 7-line mark is wider than the stroke — the
    // dome would shrink to 44% of the frame and the tagline would spill
    // onto bone. 1.3 restores the framing the 10-line mark got for free
    // when its clearance equalled its stroke: dome 57% of the width,
    // dome base at the screen's bottom edge.
    zoom: 1.3,
    portrait: {
      // phones: zoomed in so the dome's 40-unit stroke fills the full
      // phone width — the white tagline stays on red instead of spilling
      // onto bone. 2.34 puts the viewport half-width at 19.6 units, just
      // inside the 20-unit half-stroke (aspect-independent), matching the
      // margin the 10-line mark had at zoom 1.8.
      zoom: 2.34,
    },
  },
  {
    id: 'reveal',
    name: 'Get Halbert',
    at: { full: true },
    via: 'fly',
    travel: 1.3,
    dwell: 0.9,
    // zoom out to the complete mark; content above / below it
    portrait: {
      // phones: fitScale(0.44) fits the mark to 44% of the *shorter* side —
      // the width — leaving it tiny in a tall frame. Double the derived zoom
      // so the mark spans 88% of the phone's width instead.
      zoom: 2.0,
    },
  },
];

export const DEFAULT_DWELL = 0.6;
export const DEFAULT_TRAVEL = 1.0;

/** A stop with its portrait overrides applied when the viewport is taller than wide. */
export function resolveStop(stop, aspect) {
  if (aspect < 1 && stop.portrait) {
    const { portrait, ...base } = stop;
    return { ...base, ...portrait };
  }
  return stop;
}
