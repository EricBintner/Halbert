/**
 * Camera Motion Engine & Waypoint Interpolator for Site V7
 * Computes parametric camera transforms (cx, cy, scale, rotation, activeWaypoint, waypointProgress)
 * for any scroll position s in [0, 1].
 */

export const WAYPOINTS = [
  {
    id: 0,
    name: '01 / Vertical Entry',
    label: 'Left/Right Split',
    sCenter: 0.08,
    camera: { cx: 272, cy: 220, scale: 10.0, rotation: 0 },
  },
  {
    id: 1,
    name: '02 / Curve Apex',
    label: 'Top/Bottom Split',
    sCenter: 0.32,
    camera: { cx: 512, cy: 944, scale: 8.5, rotation: 0 },
  },
  {
    id: 2,
    name: '03 / Lane Hop',
    label: 'Concentric Matrix',
    sCenter: 0.54,
    camera: { cx: 368, cy: 656, scale: 7.5, rotation: 0 },
  },
  {
    id: 3,
    name: '04 / Inner Spine',
    label: 'Core Ascent',
    sCenter: 0.74,
    camera: { cx: 512, cy: 300, scale: 6.5, rotation: 0 },
  },
  {
    id: 4,
    name: '05 / Grand Reveal',
    label: '100% Full Mark',
    sCenter: 0.94,
    camera: { cx: 512, cy: 512, scale: 1.0, rotation: 0 },
  },
];

// Helper: Smooth Hermite interpolation
function smoothstep(min, max, value) {
  const x = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return x * x * (3 - 2 * x);
}

// Magnetic plateau easing: slows down near waypoint centers
export function applyPlateauEasing(s) {
  // Check if s is near any waypoint center
  let eased = s;
  for (const wp of WAYPOINTS) {
    const dist = Math.abs(s - wp.sCenter);
    const radius = 0.09;
    if (dist < radius) {
      const norm = dist / radius; // 0 at center, 1 at edge
      const pull = Math.sin(norm * (Math.PI / 2)); // Ease-in curve
      // Soft pull toward center
      const delta = (s - wp.sCenter) * (0.4 + 0.6 * pull);
      eased = wp.sCenter + delta;
      break;
    }
  }
  return Math.max(0, Math.min(1, eased));
}

// Main camera transformation function
export function getCameraState(sRaw) {
  const s = applyPlateauEasing(sRaw);

  // Determine which two waypoints we are between
  let i = 0;
  while (i < WAYPOINTS.length - 1 && s > WAYPOINTS[i + 1].sCenter) {
    i++;
  }

  const wpA = WAYPOINTS[i];
  const wpB = WAYPOINTS[Math.min(i + 1, WAYPOINTS.length - 1)];

  // Local progress t between wpA and wpB
  let t = 0;
  if (wpB.sCenter > wpA.sCenter) {
    t = smoothstep(wpA.sCenter, wpB.sCenter, s);
  }

  // Linear / curve interpolation of camera coordinates
  const cx = wpA.camera.cx + (wpB.camera.cx - wpA.camera.cx) * t;
  const cy = wpA.camera.cy + (wpB.camera.cy - wpA.camera.cy) * t;
  const scale = wpA.camera.scale + (wpB.camera.scale - wpA.camera.scale) * t;
  const rotation = wpA.camera.rotation + (wpB.camera.rotation - wpA.camera.rotation) * t;

  // Active waypoint index based on proximity
  let closestIndex = 0;
  let minDist = 999;
  WAYPOINTS.forEach((wp, idx) => {
    const dist = Math.abs(sRaw - wp.sCenter);
    if (dist < minDist) {
      minDist = dist;
      closestIndex = idx;
    }
  });

  return {
    cx,
    cy,
    scale,
    rotation,
    activeWaypoint: closestIndex,
    s,
    sRaw,
  };
}
