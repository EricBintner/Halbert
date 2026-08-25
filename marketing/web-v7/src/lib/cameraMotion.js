/**
 * Kinetic Camera Motion Engine for Site V7
 * Implements 1000%+ Macro Zoom, Clean Vertical Split, Normal Downward Scroll,
 * Curve Sweeping to Apex, Lateral Lane Hops, Shape Cap Focus, and Grand Zoom-Out.
 */

export const WAYPOINTS = [
  {
    id: 0,
    name: '01 / Vertical Split',
    label: 'Left/Right 50-50 Split',
    sCenter: 0.08,
    // Lane 5 vertical line (stroke x=272, width=32 -> edge at 288). Scale=25.0 (2500% macro zoom!)
    camera: { cx: 288, cy: 220, scale: 26.0, rotation: 0 },
    layoutType: 'split-vertical',
  },
  {
    id: 1,
    name: '02 / Curve Apex',
    label: 'Top/Bottom Split',
    sCenter: 0.32,
    // Apex of Lane 5 curve at theta = PI/2 (x = 512, y = 752 + 16 = 768). Scale=22.0
    camera: { cx: 512, cy: 768, scale: 22.0, rotation: 0 },
    layoutType: 'split-horizontal',
  },
  {
    id: 2,
    name: '03 / Lane Hop',
    label: 'Concentric Hop',
    sCenter: 0.54,
    // Perpendicular lateral hop across concentric tracks to Lane 2 (x = 416, y = 608). Scale=12.0
    camera: { cx: 416, cy: 608, scale: 12.0, rotation: 0 },
    layoutType: 'split-vertical',
  },
  {
    id: 3,
    name: '04 / Shape Cap',
    label: 'Centered Rounded Cap',
    sCenter: 0.74,
    // Centered directly on the rounded terminal cap of inner lane (x = 464, y = 82.67). Scale=18.0
    camera: { cx: 464, cy: 82.67, scale: 18.0, rotation: 0 },
    layoutType: 'radial-cap',
  },
  {
    id: 4,
    name: '05 / Grand Reveal',
    label: '100% Full Mark',
    sCenter: 0.94,
    // Full zoom out revealing the entire 1024x1024 mark in centered symmetry. Scale=1.0
    camera: { cx: 512, cy: 512, scale: 1.0, rotation: 0 },
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
 * Continuous Parametric Camera Traversal
 * Computes exact camera position along the geometric vector paths
 */
export function getCameraState(sRaw) {
  const s = applyPlateauEasing(sRaw);

  let cx = 288;
  let cy = 220;
  let scale = 26.0;
  let rotation = 0;
  let layoutType = 'split-vertical';
  let activeWaypoint = 0;

  // Phase 1: Straight Downward Scroll along the vertical stem (s in [0.0, 0.18])
  if (s <= 0.18) {
    activeWaypoint = 0;
    layoutType = 'split-vertical';
    const t = smoothstep(0.0, 0.18, s);
    cx = 288;
    cy = 180 + t * (480 - 180); // Scrolls straight down from 180 to 480
    scale = 26.0;
    rotation = 0;
  }
  // Phase 2: Traversal along the U-curve arc down to the horizontal Apex (s in [0.18, 0.38])
  else if (s <= 0.38) {
    activeWaypoint = 1;
    layoutType = s > 0.28 ? 'split-horizontal' : 'split-vertical';
    const t = smoothstep(0.18, 0.38, s);
    // Radius R = 240 (Lane 5). Angle sweeps from theta = 0 to theta = PI/2
    const theta = t * (Math.PI / 2);
    const pathX = 512 - 240 * Math.cos(theta);
    const pathY = 512 + 240 * Math.sin(theta);
    
    // Offset camera to stroke edge (16px normal to tangent)
    const normX = Math.cos(theta) * 16;
    const normY = Math.sin(theta) * 16;

    cx = pathX + normX;
    cy = pathY + normY;
    scale = 26.0 - t * (26.0 - 22.0);
    rotation = 0;
  }
  // Phase 3: Perpendicular Lane Hop across concentric tracks (s in [0.38, 0.58])
  else if (s <= 0.58) {
    activeWaypoint = 2;
    layoutType = 'split-vertical';
    const t = smoothstep(0.38, 0.58, s);
    // Lateral slide from Lane 5 apex (512, 768) to Lane 2 (416, 608)
    cx = 512 + t * (416 - 512);
    cy = 768 + t * (608 - 768);
    scale = 22.0 - t * (22.0 - 12.0);
    rotation = 0;
  }
  // Phase 4: Focus on the Rounded Shape Cap (s in [0.58, 0.78])
  else if (s <= 0.78) {
    activeWaypoint = 3;
    layoutType = 'radial-cap';
    const t = smoothstep(0.58, 0.78, s);
    // Transition to the rounded stroke terminal cap at (464, 82.67)
    cx = 416 + t * (464 - 416);
    cy = 608 + t * (82.67 - 608);
    scale = 12.0 + t * (18.0 - 12.0);
    rotation = 0;
  }
  // Phase 5: Grand Zoom-Out Reveal to 100% full view (s in [0.78, 1.0])
  else {
    activeWaypoint = 4;
    layoutType = 'full-reveal';
    const t = smoothstep(0.78, 1.0, s);
    // Pull back from (464, 82.67) scale 18.0 to (512, 512) scale 1.0
    cx = 464 + t * (512 - 464);
    cy = 82.67 + t * (512 - 82.67);
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
