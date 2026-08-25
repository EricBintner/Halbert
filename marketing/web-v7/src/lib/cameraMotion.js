/**
 * Kinetic Camera Motion Engine for Site V7
 * Precise parametric path-following along Halbert SVG geometry:
 * 1. Straight Downward Descent along vertical stem (x=272)
 * 2. Curve traversal following the exact circular arc (512 - 240*cos(theta), 512 + 240*sin(theta))
 * 3. Apex dwelling at (512, 752) where stroke is 100% horizontal
 * 4. Perpendicular slide across concentric lanes
 * 5. Focal centering on rounded stroke terminal cap (464, 82.67)
 * 6. Grand Zoom-Out Reveal to 100% full view (512, 512, scale=1.0)
 */

export const WAYPOINTS = [
  {
    id: 0,
    name: '01 / Vertical Descent',
    label: 'Left/Right Split',
    sCenter: 0.08,
    camera: { cx: 272.0, cy: 260.0, scale: 22.0, rotation: 0 },
    layoutType: 'split-vertical',
  },
  {
    id: 1,
    name: '02 / Curve Apex',
    label: 'Top/Bottom Split',
    sCenter: 0.35,
    camera: { cx: 512.0, cy: 752.0, scale: 20.0, rotation: 0 },
    layoutType: 'split-horizontal',
  },
  {
    id: 2,
    name: '03 / Lane Hop',
    label: 'Concentric Matrix',
    sCenter: 0.55,
    camera: { cx: 368.0, cy: 656.0, scale: 14.0, rotation: 0 },
    layoutType: 'split-vertical',
  },
  {
    id: 3,
    name: '04 / Shape Cap',
    label: 'Centered Rounded Cap',
    sCenter: 0.74,
    camera: { cx: 464.0, cy: 82.67, scale: 18.0, rotation: 0 },
    layoutType: 'radial-cap',
  },
  {
    id: 4,
    name: '05 / Grand Reveal',
    label: '100% Full Mark',
    sCenter: 0.94,
    camera: { cx: 512.0, cy: 512.0, scale: 1.0, rotation: 0 },
    layoutType: 'full-reveal',
  },
];

// Helper: Smooth Hermite curve
function smoothstep(min, max, value) {
  const x = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return x * x * (3 - 2 * x);
}

// Magnetic plateau easing: organically pauses near waypoint centers without locking scroll
export function applyPlateauEasing(s) {
  let eased = s;
  for (const wp of WAYPOINTS) {
    const dist = Math.abs(s - wp.sCenter);
    const radius = 0.07;
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

/**
 * Continuous Parametric Path Following
 * Computes exact camera position along the geometric vector paths
 */
export function getCameraState(sRaw) {
  const s = applyPlateauEasing(sRaw);

  let cx = 272.0;
  let cy = 200.0;
  let scale = 22.0;
  let rotation = 0;
  let layoutType = 'split-vertical';
  let activeWaypoint = 0;

  // Phase 1: Straight Downward Scroll along the vertical stem (s in [0.0, 0.20])
  if (s <= 0.20) {
    activeWaypoint = 0;
    layoutType = 'split-vertical';
    const t = smoothstep(0.0, 0.20, s);
    cx = 272.0; // Pinned directly to the vertical centerline
    cy = 160.0 + t * (512.0 - 160.0); // Moves straight down from 160 to 512
    scale = 22.0;
    rotation = 0;
  }
  // Phase 2: Traversal along the U-curve arc down to the horizontal Apex (s in [0.20, 0.44])
  else if (s <= 0.44) {
    activeWaypoint = 1;
    const t = smoothstep(0.20, 0.44, s);
    layoutType = t > 0.4 ? 'split-horizontal' : 'split-vertical';
    
    // Radius R = 240 (Lane 5). Angle sweeps from theta = 0 to theta = PI/2
    const theta = t * (Math.PI / 2);
    
    // Path centerline is strictly at:
    cx = 512.0 - 240.0 * Math.cos(theta);
    cy = 512.0 + 240.0 * Math.sin(theta);
    scale = 22.0 - t * (22.0 - 20.0);
    rotation = 0;
  }
  // Phase 3: Perpendicular Lane Hop across concentric tracks (s in [0.44, 0.62])
  else if (s <= 0.62) {
    activeWaypoint = 2;
    layoutType = 'split-vertical';
    const t = smoothstep(0.44, 0.62, s);
    // Lateral slide from Lane 5 apex (512, 752) to Lane 3 apex (368, 656)
    cx = 512.0 + t * (368.0 - 512.0);
    cy = 752.0 + t * (656.0 - 752.0);
    scale = 20.0 - t * (20.0 - 14.0);
    rotation = 0;
  }
  // Phase 4: Focus on the Rounded Shape Cap (s in [0.62, 0.80])
  else if (s <= 0.80) {
    activeWaypoint = 3;
    layoutType = 'radial-cap';
    const t = smoothstep(0.62, 0.80, s);
    // Transition to the rounded stroke terminal cap at (464, 82.67)
    cx = 368.0 + t * (464.0 - 368.0);
    cy = 656.0 + t * (82.67 - 656.0);
    scale = 14.0 + t * (18.0 - 14.0);
    rotation = 0;
  }
  // Phase 5: Grand Zoom-Out Reveal to 100% full view (s in [0.80, 1.0])
  else {
    activeWaypoint = 4;
    layoutType = 'full-reveal';
    const t = smoothstep(0.80, 1.0, s);
    // Pull back from (464, 82.67) scale 18.0 to (512, 512) scale 1.0
    cx = 464.0 + t * (512.0 - 464.0);
    cy = 82.67 + t * (512.0 - 82.67);
    scale = 18.0 - t * (18.0 - 1.0);
    rotation = 0;
  }

  return {
    cx,
    cy,
    scale,
    rotation,
    activeWaypoint,
    layoutType,
    s,
    sRaw,
  };
}
