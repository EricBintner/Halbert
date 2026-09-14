/**
 * Camera engine — turns the storyboard into a camera pose for any scroll
 * position, in any viewport.
 *
 *   timeline   scroll axis split into alternating DWELL / MOVE segments
 *   stopPose   a stop resolved against the geometry (focal point, zoom, layout)
 *   getCameraState(s, aspect)  the pose at normalised scroll s in [0, 1]
 *
 * Invariants the rest of the site relies on:
 *   - the focal point (cx, cy) is always rendered at the exact screen centre
 *   - while dwelling, and while following an edge, the screen centre lies ON a
 *     colour boundary of the mark and the zoom is high enough that no other
 *     boundary is visible
 *   - every move eases in and out, so the camera *arrives* at a stop
 */

import {
  MARK,
  capPoint,
  edgeClearance,
  edgePath,
  edgePointAt,
  edgeU,
  fitScale,
  lerp,
  requiredScale,
  sameEdge,
} from './markGeometry.js';
import { STOPS, DEFAULT_DWELL, DEFAULT_TRAVEL, resolveStop } from './storyboard.js';

const clamp01 = (v) => Math.max(0, Math.min(1, v));

/** Smootherstep: zero velocity and acceleration at both ends, without the long dead zones of a quintic ease. */
export function easeMove(x) {
  return x * x * x * (x * (x * 6 - 15) + 10);
}

/* ------------------------------------------------------------------------ */
/* Timeline                                                                  */
/* ------------------------------------------------------------------------ */

export function buildTimeline(stops = STOPS) {
  const segments = [];
  let acc = 0;
  stops.forEach((stop, i) => {
    if (i > 0) {
      const w = stop.travel ?? DEFAULT_TRAVEL;
      segments.push({ kind: 'move', from: i - 1, to: i, start: acc, end: acc + w });
      acc += w;
    }
    const d = stop.dwell ?? DEFAULT_DWELL;
    segments.push({ kind: 'dwell', stop: i, start: acc, end: acc + d });
    acc += d;
  });
  segments.forEach((g) => {
    g.s0 = g.start / acc;
    g.s1 = g.end / acc;
  });
  return { segments, totalWeight: acc, stops };
}

const TIMELINES = {};

/** The timeline for a viewport orientation (portrait stops may differ in travel/dwell). */
export function timelineFor(aspect = 16 / 9) {
  const key = aspect < 1 ? 'portrait' : 'landscape';
  if (!TIMELINES[key]) TIMELINES[key] = buildTimeline(STOPS.map((stop) => resolveStop(stop, aspect)));
  return TIMELINES[key];
}

/** Normalised scroll position at the middle of a stop's dwell. */
export function stopCenterS(index, aspect = 16 / 9) {
  const seg = timelineFor(aspect).segments.find((g) => g.kind === 'dwell' && g.stop === index);
  return seg ? (seg.s0 + seg.s1) / 2 : 0;
}

/* ------------------------------------------------------------------------ */
/* Poses                                                                     */
/* ------------------------------------------------------------------------ */

function layoutFromNormal(n) {
  const ax = Math.abs(n.x);
  const ay = Math.abs(n.y);
  const angle = (Math.atan2(n.y, n.x) * 180) / Math.PI;
  if (ax > 0.92) return { kind: 'vertical', strokeSide: n.x < 0 ? 'left' : 'right', angle };
  if (ay > 0.92) return { kind: 'horizontal', strokeSide: n.y < 0 ? 'top' : 'bottom', angle };
  return {
    kind: 'diagonal',
    strokeSide: `${n.y < 0 ? 'top' : 'bottom'}-${n.x < 0 ? 'left' : 'right'}`,
    angle,
  };
}

/** Resolve a stop against the geometry for a given viewport aspect ratio. */
export function stopPose(rawStop, aspect) {
  const stop = resolveStop(rawStop, aspect);
  const { at } = stop;
  const zoom = stop.zoom ?? 1;

  if (at.full) {
    return {
      cx: MARK.cx,
      cy: MARK.cy,
      scale: stop.scale ?? fitScale(aspect, 0.44) * zoom,
      normal: { x: 0, y: 0 },
      layout: { kind: 'full', strokeSide: 'none', angle: 0 },
    };
  }

  if (at.cap) {
    const c = capPoint(at.cap);
    const scale =
      stop.scale ??
      Math.max(
        requiredScale({ x: 1, y: 0 }, c.clearanceX, aspect),
        requiredScale({ x: 0, y: 1 }, c.clearanceY, aspect),
      ) * zoom;
    return {
      cx: c.x,
      cy: c.y,
      scale,
      normal: c.toStroke,
      layout: { kind: 'cap', strokeSide: 'bottom', angle: 90 },
    };
  }

  const edge = edgePath(at.edge.lane, at.edge.side);
  const u = edgeU(edge, at);
  const p = edgePointAt(edge, u);
  const scale = stop.scale ?? requiredScale(p.toStroke, edgeClearance(edge, u), aspect) * zoom;
  const layout = layoutFromNormal(p.toStroke);
  // How far the curve rises at the frame's side edges, as a fraction of the
  // viewport height — layouts use it to keep type clear of the boundary.
  const h = 1024 / scale;
  const w = h * aspect;
  layout.sag = p.onArc ? ((w / 2) ** 2) / (2 * edge.r) / h : 0;
  return {
    cx: p.x,
    cy: p.y,
    scale,
    zoom,
    normal: p.toStroke,
    layout,
    edge,
    u,
  };
}

/* ------------------------------------------------------------------------ */
/* Moves                                                                     */
/* ------------------------------------------------------------------------ */

function logLerp(a, b, t) {
  return Math.exp(lerp(Math.log(a), Math.log(b), t));
}

/** Pose at eased progress t of the move from stop A to stop B. */
function movePose(A, B, pa, pb, aspect, t) {
  const via = B.via ?? 'fly';
  const dip = B.dip ?? 0;
  const dipFactor = 1 - dip * Math.sin(Math.PI * t);

  if (via === 'follow' && sameEdge(pa.edge, pb.edge)) {
    const u = lerp(pa.u, pb.u, t);
    const p = edgePointAt(pa.edge, u);
    // Zoom breathes with the edge orientation so exactly one boundary stays on screen.
    let scale = requiredScale(p.toStroke, edgeClearance(pa.edge, u), aspect) * lerp(pa.zoom ?? 1, pb.zoom ?? 1, t);
    if (A.scale != null || B.scale != null) scale = logLerp(pa.scale, pb.scale, t);
    return { cx: p.x, cy: p.y, scale: scale * dipFactor, normal: p.toStroke };
  }

  if (via === 'follow' && typeof console !== 'undefined') {
    console.warn(`[camera] '${B.id}' asks to follow but is not on the same edge as '${A.id}'; flying instead.`);
  }

  const scale = logLerp(pa.scale, pb.scale, t) * dipFactor;
  return {
    cx: lerp(pa.cx, pb.cx, t),
    cy: lerp(pa.cy, pb.cy, t),
    scale,
    normal: t < 0.5 ? pa.normal : pb.normal,
  };
}

/* ------------------------------------------------------------------------ */
/* Public                                                                    */
/* ------------------------------------------------------------------------ */

function findSegment(s, timeline) {
  const { segments } = timeline;
  for (const seg of segments) if (s <= seg.s1) return seg;
  return segments[segments.length - 1];
}

/**
 * @param {number} sRaw   normalised scroll in [0, 1]
 * @param {number} aspect viewport width / height
 * @returns camera state
 */
export function getCameraState(sRaw, aspect = 16 / 9, timeline = timelineFor(aspect)) {
  const s = clamp01(sRaw);
  const { stops } = timeline; // already resolved for this orientation
  const poses = stops.map((stop) => stopPose(stop, aspect));
  const seg = findSegment(s, timeline);

  if (seg.kind === 'dwell') {
    const pose = poses[seg.stop];
    return {
      cx: pose.cx,
      cy: pose.cy,
      scale: pose.scale,
      rotation: 0,
      normal: pose.normal,
      layout: pose.layout,
      stopIndex: seg.stop,
      phase: 'dwell',
      move: null,
      s,
      aspect,
      poses,
    };
  }

  const A = stops[seg.from];
  const B = stops[seg.to];
  const raw = (s - seg.s0) / Math.max(1e-6, seg.s1 - seg.s0);
  const t = easeMove(clamp01(raw));
  const pose = movePose(A, B, poses[seg.from], poses[seg.to], aspect, t);

  // Instantaneous direction of camera travel (screen space == mark space here).
  const ahead = movePose(A, B, poses[seg.from], poses[seg.to], aspect, Math.min(1, t + 0.01));
  const behind = movePose(A, B, poses[seg.from], poses[seg.to], aspect, Math.max(0, t - 0.01));
  let dx = ahead.cx - behind.cx;
  let dy = ahead.cy - behind.cy;
  const len = Math.hypot(dx, dy);
  if (len < 1e-6) {
    dx = 0;
    dy = 1;
  } else {
    dx /= len;
    dy /= len;
  }

  return {
    cx: pose.cx,
    cy: pose.cy,
    scale: pose.scale,
    rotation: 0,
    normal: pose.normal,
    layout: t < 0.5 ? poses[seg.from].layout : poses[seg.to].layout,
    stopIndex: t < 0.5 ? seg.from : seg.to,
    phase: 'move',
    move: { from: seg.from, to: seg.to, t, raw: clamp01(raw), dir: { x: dx, y: dy }, via: B.via ?? 'fly' },
    s,
    aspect,
    poses,
  };
}
