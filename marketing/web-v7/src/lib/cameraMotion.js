/**
 * Kinetic Camera Motion Engine for Site V7
 * Computes exact viewBox, scale, rotation, and magnetic plateau easing
 * following the authentic Halbert SVG geometry.
 */

export const WAYPOINTS = [
  {
    id: 0,
    name: '01 / Vertical Split',
    label: 'Left/Right Division',
    sCenter: 0.08,
    // Lane 5 vertical line (x = 272)
    camera: { cx: 272, cy: 300, scale: 9.5, rotation: 0 },
    layoutType: 'split-vertical', // Left: Copy | Right: Interactive Graphic
  },
  {
    id: 1,
    name: '02 / Curve Apex',
    label: 'Top/Bottom Division',
    sCenter: 0.32,
    // Outer arc bottom apex (x = 512, y = 944)
    camera: { cx: 512, cy: 944, scale: 8.5, rotation: 0 },
    layoutType: 'split-horizontal', // Top: Copy | Bottom: Diagnostic Meters
  },
  {
    id: 2,
    name: '03 / Lane Hop',
    label: 'Concentric Matrix',
    sCenter: 0.54,
    // Inner lane hop across concentric tracks (x = 368, y = 656)
    camera: { cx: 368, cy: 656, scale: 8.0, rotation: 0 },
    layoutType: 'split-vertical', // Left: Copy | Right: AST Diff
  },
  {
    id: 3,
    name: '04 / Shape Cap',
    label: 'Centered Stroke Cap',
    sCenter: 0.74,
    // Centered directly on rounded terminal cap (x = 464, y = 82.67)
    camera: { cx: 464, cy: 82.67, scale: 9.0, rotation: 0 },
    layoutType: 'radial-cap', // Centered around rounded terminal cap
  },
  {
    id: 4,
    name: '05 / Grand Reveal',
    label: '100% Full Mark',
    sCenter: 0.94,
    // Centered zoom-out revealing the complete 1024x1024 mark
    camera: { cx: 512, cy: 512, scale: 1.0, rotation: 0 },
    layoutType: 'full-reveal', // Centered full mark + dispatch
  },
];

// Helper: Smooth Hermite curve
function smoothstep(min, max, value) {
  const x = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return x * x * (3 - 2 * x);
}

// Magnetic plateau easing: organically slows down near waypoint centers
export function applyPlateauEasing(s) {
  let eased = s;
  for (const wp of WAYPOINTS) {
    const dist = Math.abs(s - wp.sCenter);
    const radius = 0.08;
    if (dist < radius) {
      const norm = dist / radius; // 0 at center, 1 at boundary
      const pull = Math.sin(norm * (Math.PI / 2));
      const delta = (s - wp.sCenter) * (0.35 + 0.65 * pull);
      eased = wp.sCenter + delta;
      break;
    }
  }
  return Math.max(0, Math.min(1, eased));
}

// Compute interpolated camera state for any scroll progress
export function getCameraState(sRaw) {
  const s = applyPlateauEasing(sRaw);

  let i = 0;
  while (i < WAYPOINTS.length - 1 && s > WAYPOINTS[i + 1].sCenter) {
    i++;
  }

  const wpA = WAYPOINTS[i];
  const wpB = WAYPOINTS[Math.min(i + 1, WAYPOINTS.length - 1)];

  let t = 0;
  if (wpB.sCenter > wpA.sCenter) {
    t = smoothstep(wpA.sCenter, wpB.sCenter, s);
  }

  const cx = wpA.camera.cx + (wpB.camera.cx - wpA.camera.cx) * t;
  const cy = wpA.camera.cy + (wpB.camera.cy - wpA.camera.cy) * t;
  const scale = wpA.camera.scale + (wpB.camera.scale - wpA.camera.scale) * t;
  const rotation = wpA.camera.rotation + (wpB.camera.rotation - wpA.camera.rotation) * t;

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
    layoutType: WAYPOINTS[closestIndex].layoutType,
    s,
    sRaw,
  };
}
