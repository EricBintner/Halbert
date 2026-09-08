import React, { useEffect, useState } from 'react';

// Exact 8-line parametric Halbert mark geometry
const PATHS_8 = [
  'M 512.00 80.00 V 512.00',
  'M 450.29 84.43 V 512.00 A 61.71 61.71 0 0 0 573.71 512.00 V 84.43',
  'M 388.57 98.01 V 512.00 A 123.43 123.43 0 0 0 635.43 512.00 V 98.01',
  'M 326.86 121.68 V 512.00 A 185.14 185.14 0 0 0 697.14 512.00 V 121.68',
  'M 265.14 157.48 V 512.00 A 246.86 246.86 0 0 0 758.86 512.00 V 157.48',
  'M 203.43 209.66 V 512.00 A 308.57 308.57 0 0 0 820.57 512.00 V 209.66',
  'M 141.71 289.49 V 512.00 A 370.29 370.29 0 0 0 882.29 512.00 V 289.49',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
];

const STROKE_WIDTH = 34.29;

const LINE_PARAMS = [
  // Line 0: Center vertical spine
  { type: 'spine', top: 80, bottom: 512, x: 512 },
  // Lines 1-6: Concentric U-shape lanes with vertical legs
  { type: 'u', R: 61.71, top: 84.43 },
  { type: 'u', R: 123.43, top: 98.01 },
  { type: 'u', R: 185.14, top: 121.68 },
  { type: 'u', R: 246.86, top: 157.48 },
  { type: 'u', R: 308.57, top: 209.66 },
  { type: 'u', R: 370.29, top: 289.49 },
  // Line 7: Outermost semicircle
  { type: 'arc', R: 432 },
];

function getPointOnLine(lineIndex, t) {
  const clampT = Math.max(0, Math.min(1, t));
  const param = LINE_PARAMS[lineIndex] || LINE_PARAMS[0];

  if (param.type === 'spine') {
    return {
      x: param.x,
      y: param.top + clampT * (param.bottom - param.top),
    };
  }

  if (param.type === 'arc') {
    const phi = Math.PI * clampT;
    return {
      x: 512 - param.R * Math.cos(phi),
      y: 512 + param.R * Math.sin(phi),
    };
  }

  // U-shape with vertical legs and bottom semicircle
  const legLen = 512 - param.top;
  const arcLen = Math.PI * param.R;
  const totalLen = 2 * legLen + arcLen;
  const dist = clampT * totalLen;

  if (dist <= legLen) {
    // Down left leg
    return {
      x: 512 - param.R,
      y: param.top + dist,
    };
  } else if (dist <= legLen + arcLen) {
    // Around bottom semicircle
    const arcDist = dist - legLen;
    const phi = (arcDist / arcLen) * Math.PI;
    return {
      x: 512 - param.R * Math.cos(phi),
      y: 512 + param.R * Math.sin(phi),
    };
  } else {
    // Up right leg
    const rightDist = dist - (legLen + arcLen);
    return {
      x: 512 + param.R,
      y: 512 - rightDist,
    };
  }
}

// Smooth cosine-eased fade in and fade out envelope
function getFadeEnvelope(t, windowSize = 0.2) {
  if (t < windowSize) {
    const ratio = t / windowSize;
    return 0.5 - 0.5 * Math.cos(ratio * Math.PI);
  }
  if (t > 1 - windowSize) {
    const ratio = (1 - t) / windowSize;
    return 0.5 - 0.5 * Math.cos(ratio * Math.PI);
  }
  return 1;
}

export function VectorParallaxBackground() {
  const [scrollProgress, setScrollProgress] = useState(0);

  useEffect(() => {
    let raf = 0;
    const readScroll = () => {
      raf = 0;
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const current = maxScroll > 0 ? Math.max(0, Math.min(1, window.scrollY / maxScroll)) : 0;
      setScrollProgress(current);
    };

    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(readScroll);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    readScroll();

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // Map scroll progress across the 8 lines in REVERSE order:
  // Starts at the outside (Line 7) and travels inward to the center spine (Line 0)
  const scaled = scrollProgress * 8;
  const step = Math.min(7, Math.floor(scaled));
  const localT = scaled - step;

  // Inverted: 7 (outermost) down to 0 (center spine)
  const activeLineIndex = 7 - step;

  // Smooth fade out at the end of each line, fade in on the next line
  const lineFade = getFadeEnvelope(localT, 0.22);

  // Dynamic opacity stops ensuring 0% opacity on all gradient edges
  const peakOpacity = 0.45 * lineFade;
  const midOpacity = 0.20 * lineFade;
  const faintOpacity = 0.04 * lineFade;

  // Calculate current (x, y) focal coordinate along the active line path
  const focalPoint = getPointOnLine(activeLineIndex, localT);

  return (
    <div
      className="fixed inset-0 w-full h-full pointer-events-none z-0 overflow-hidden flex items-center justify-center select-none"
      aria-hidden="true"
    >
      {/* Static, centered, overflowing 8-line mark */}
      <div className="w-[130vmax] h-[130vmax] min-w-[1200px] min-h-[1200px] max-w-[2200px] max-h-[2200px] shrink-0 flex items-center justify-center">
        <svg
          viewBox="0 0 1024 1024"
          className="w-full h-full"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/*
              Scroll-driven gradient focal spotlight.
              Edges are feathered to 0% opacity at 100% radius.
              Opacity stops dynamically scale with the line's fade envelope
              so transitions between lines dissolve smoothly without popping.
            */}
            <radialGradient
              id="scrollDrivenGlow"
              cx={focalPoint.x}
              cy={focalPoint.y}
              r="280"
              gradientUnits="userSpaceOnUse"
            >
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={peakOpacity} />
              <stop offset="45%" stopColor="var(--color-accent)" stopOpacity={midOpacity} />
              <stop offset="85%" stopColor="var(--color-accent)" stopOpacity={faintOpacity} />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0} />
            </radialGradient>
          </defs>

          {/* Layer 1: Static base 8-line mark (calm architectural watermark) */}
          <g
            fill="none"
            stroke="var(--color-line-strong)"
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="opacity-[0.16] dark:opacity-[0.11]"
          >
            {PATHS_8.map((d, i) => (
              <path key={`base-${i}`} d={d} />
            ))}
          </g>

          {/* Layer 2: Animated gradient active on ONLY the current single line */}
          {lineFade > 0.001 && (
            <g
              fill="none"
              stroke="url(#scrollDrivenGlow)"
              strokeWidth={STROKE_WIDTH}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d={PATHS_8[activeLineIndex]} />
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}
