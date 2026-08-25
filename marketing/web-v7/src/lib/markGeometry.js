/**
 * Halbert mark — parametric geometry model.
 *
 * The brand mark lives in a 1024 x 1024 coordinate space:
 *   - a vertical spine at x = 512 from y = 80 down to y = 512
 *   - nine concentric U-shaped lanes, radius R_i = 48 * i, each drawn as
 *     left leg (down) -> bottom semicircle -> right leg (up)
 *   - every stroke is 32 wide with round caps; lanes are pitched 48 apart,
 *     so the *gap* between neighbouring strokes is exactly 16 units
 *   - the leg tops sit on a circle of radius 432 around (512, 512), which is
 *     also the radius of lane 9 (a pure semicircle with no legs)
 *
 * Everything the camera engine needs is derived from this model:
 * edge paths (the *boundary* between stroke colour and canvas colour), the
 * tangent / normal along those edges, the clearance to the next edge, and the
 * minimum zoom that keeps only ONE edge on screen.
 */

export const MARK = Object.freeze({
  cx: 512,
  cy: 512,
  outerR: 432,
  laneStep: 48,
  strokeWidth: 32,
  halfStroke: 16,
  lanes: 9,
  spine: { x: 512, top: 80, bottom: 512 },
});

export const GAP = MARK.laneStep - MARK.strokeWidth; // 16

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const lerp = (a, b, t) => a + (b - a) * t;

export function laneRadius(lane) {
  return MARK.laneStep * lane;
}

/** y of the top of a lane's legs (round cap centre). Lane 9 has no legs. */
export function laneTop(lane) {
  const R = laneRadius(lane);
  return MARK.cy - Math.sqrt(Math.max(0, MARK.outerR ** 2 - R ** 2));
}

/** Radius of the stroke *boundary* on the inner or outer side of a lane. */
export function edgeRadius(lane, side) {
  return laneRadius(lane) + (side === 'outer' ? MARK.halfStroke : -MARK.halfStroke);
}

/** The authentic SVG path data, generated from the model. */
export const MARK_PATH_D = (() => {
  const parts = [`M ${MARK.spine.x} ${MARK.spine.top} V ${MARK.spine.bottom}`];
  for (let i = 1; i <= MARK.lanes; i += 1) {
    const R = laneRadius(i);
    const x0 = MARK.cx - R;
    const x1 = MARK.cx + R;
    if (i === MARK.lanes) {
      parts.push(`M ${x0} ${MARK.cy} A ${R} ${R} 0 0 0 ${x1} ${MARK.cy}`);
    } else {
      const top = laneTop(i).toFixed(2);
      parts.push(`M ${x0} ${top} V ${MARK.cy} A ${R} ${R} 0 0 0 ${x1} ${MARK.cy} V ${top}`);
    }
  }
  return parts.join(' ');
})();

/* ------------------------------------------------------------------------ */
/* Edge paths                                                                */
/* ------------------------------------------------------------------------ */

/**
 * An edge path is the colour boundary on one side of a lane. It has the same
 * U shape as the lane centreline, just with radius R ± 16. Arc-length
 * parameter `u` runs: left leg (top -> bottom), semicircle, right leg
 * (bottom -> top).
 */
export function edgePath(lane, side) {
  const r = edgeRadius(lane, side);
  const top = laneTop(lane);
  const legLen = MARK.cy - top;
  const arcLen = Math.PI * r;
  return { lane, side, r, top, legLen, arcLen, length: 2 * legLen + arcLen };
}

export function sameEdge(a, b) {
  return !!a && !!b && a.lane === b.lane && a.side === b.side;
}

/**
 * Point on an edge path at arc-length u. Returns the position, the unit
 * tangent (direction of increasing u) and `toStroke`, the unit normal that
 * points from the edge INTO the coloured stroke.
 */
export function edgePointAt(edge, u) {
  const { r, top, legLen, arcLen } = edge;
  const uu = clamp(u, 0, edge.length);
  let x;
  let y;
  let tx;
  let ty;
  if (uu <= legLen) {
    x = MARK.cx - r;
    y = top + uu;
    tx = 0;
    ty = 1;
  } else if (uu <= legLen + arcLen) {
    const th = (uu - legLen) / r; // 0 at left-bottom, PI/2 at apex, PI at right-bottom
    x = MARK.cx - r * Math.cos(th);
    y = MARK.cy + r * Math.sin(th);
    tx = Math.sin(th);
    ty = Math.cos(th);
  } else {
    const v = uu - legLen - arcLen;
    x = MARK.cx + r;
    y = MARK.cy - v;
    tx = 0;
    ty = -1;
  }
  // Rotating the tangent (0,1)->(-1,0) gives the outward normal (away from the mark centre).
  const outward = { x: -ty, y: tx };
  const toStroke = edge.side === 'inner' ? outward : { x: -outward.x, y: -outward.y };
  return { x, y, tangent: { x: tx, y: ty }, toStroke, onArc: uu > legLen && uu < legLen + arcLen };
}

/**
 * Convert an author-friendly location on an edge into arc-length u.
 *   { leg: 'left' | 'right', y }   a point on a leg
 *   { angle }                      degrees along the semicircle: 0 = left-bottom,
 *                                  90 = apex, 180 = right-bottom
 */
export function edgeU(edge, at) {
  if (at.angle != null) {
    const deg = clamp(at.angle, 0, 180);
    return edge.legLen + (deg * Math.PI) / 180 * edge.r;
  }
  const y = clamp(at.y, edge.top, MARK.cy);
  if (at.leg === 'right') return edge.legLen + edge.arcLen + (MARK.cy - y);
  return y - edge.top;
}

/**
 * Distance (in mark units) from this edge to the nearest *other* colour
 * boundary, measured along the normal. Normally the 16-unit gap; the outside
 * of the mark is open, so the far side of the stroke (32) governs there.
 */
export function edgeClearance(edge, u) {
  if (edge.side === 'outer') {
    if (edge.lane === MARK.lanes) return MARK.strokeWidth;
    const p = edgePointAt(edge, u);
    if (edge.lane === MARK.lanes - 1 && !p.onArc) return MARK.strokeWidth; // lane 9 has no legs
  }
  return GAP;
}

/* ------------------------------------------------------------------------ */
/* Caps                                                                      */
/* ------------------------------------------------------------------------ */

/**
 * The rounded terminal of a stroke. The focal point is the crest of the cap so
 * the dome rises exactly to the screen centre.
 *   'spine'                 the top of the central spine
 *   { lane, leg }           the top of a lane's leg
 */
export function capPoint(which) {
  if (which === 'spine') {
    return {
      x: MARK.spine.x,
      y: MARK.spine.top - MARK.halfStroke,
      toStroke: { x: 0, y: 1 },
      // lane 1's inner edges sit 32 units either side of the spine centre
      clearanceX: MARK.laneStep - MARK.halfStroke,
      clearanceY: Infinity,
    };
  }
  const R = laneRadius(which.lane);
  return {
    x: which.leg === 'left' ? MARK.cx - R : MARK.cx + R,
    y: laneTop(which.lane) - MARK.halfStroke,
    toStroke: { x: 0, y: 1 },
    clearanceX: MARK.laneStep - MARK.halfStroke,
    clearanceY: Infinity,
  };
}

/* ------------------------------------------------------------------------ */
/* Zoom                                                                      */
/* ------------------------------------------------------------------------ */

/**
 * Minimum camera scale (1 = the full 1024 space fits the viewport height)
 * such that the viewport's half-extent along `normal` stays inside
 * `clearance`. This is what guarantees "only one line on screen".
 */
export function requiredScale(normal, clearance, aspect, margin = 0.12) {
  if (!Number.isFinite(clearance)) return 1;
  const extent = aspect * Math.abs(normal.x) + Math.abs(normal.y);
  return (512 * extent) / (clearance * (1 - margin));
}

/** Scale at which the whole mark occupies `fraction` of the shorter viewport side. */
export function fitScale(aspect, fraction = 0.55) {
  const diameter = 2 * (MARK.outerR + MARK.halfStroke);
  return (1024 * fraction * Math.min(1, aspect)) / diameter;
}

/** ViewBox for a camera pose in a viewport of the given aspect ratio. */
export function viewBoxFor(camera, aspect) {
  const h = 1024 / Math.max(0.05, camera.scale);
  const w = h * aspect;
  return { minX: camera.cx - w / 2, minY: camera.cy - h / 2, w, h };
}
