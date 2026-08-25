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
 * single line is the same on every lane (it is fixed by the 16-unit gap), so
 * a tighter lane shows more curvature at the same zoom. Lane 2 (inner edge,
 * r = 80) gives a clearly curved apex/diagonal while the legs stay straight.
 */

const RIDE = { lane: 2, side: 'inner' };

export const STOPS = [
  {
    id: 'open',
    name: '01 / Open',
    at: { edge: RIDE, leg: 'left', y: 330 },
    dwell: 0.55,
    // landscape — vertical split: stroke LEFT, canvas RIGHT
    portrait: {
      // phones start sideways: the apex of lane 1's outer edge, one gap above
      // the apex stop, so the first scroll slides the gap up and flips colours
      at: { edge: { lane: 1, side: 'outer' }, angle: 90 },
      // horizontal split: stroke TOP, canvas BOTTOM
    },
  },
  {
    id: 'apex',
    name: '02 / Apex',
    at: { edge: RIDE, angle: 90 },
    via: 'follow',
    dwell: 0.6,
    // horizontal split: canvas TOP, stroke BOTTOM
    portrait: { via: 'fly', travel: 0.7 },
  },
  {
    id: 'diagonal',
    name: '03 / Diagonal',
    at: { edge: RIDE, angle: 135 },
    via: 'follow',
    travel: 0.8,
    dwell: 0.6,
    // 45° split: canvas TOP-LEFT, stroke BOTTOM-RIGHT
  },
  {
    id: 'rise',
    name: '04 / Rise',
    at: { edge: RIDE, leg: 'right', y: 330 },
    via: 'follow',
    travel: 0.8,
    dwell: 0.6,
    // vertical split, colours swapped: canvas LEFT, stroke RIGHT
    // (portrait: straddled single-column type treatment over the same split)
  },
  {
    id: 'hop',
    name: '05 / Lane hop',
    at: { edge: { lane: 5, side: 'outer' }, leg: 'right', y: 330 },
    via: 'fly',
    dip: 0.6,
    dwell: 0.6,
    // perpendicular slide outward across three lanes; vertical split: stroke LEFT, canvas RIGHT
  },
  {
    id: 'cap',
    name: '06 / Cap',
    at: { cap: 'spine' },
    via: 'fly',
    dip: 0.25,
    dwell: 0.6,
    // rounded cap: canvas TOP half, stroke dome rising to the centre
  },
  {
    id: 'reveal',
    name: '07 / Reveal',
    at: { full: true },
    via: 'fly',
    travel: 1.3,
    dwell: 0.9,
    // zoom out to the complete mark; content above / below it
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
