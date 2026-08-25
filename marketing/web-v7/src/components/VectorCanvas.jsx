import React from 'react';

/**
 * Authentic Vector Canvas for Site V7
 * Renders the exact 1024x1024 Halbert SVG path with zero artificial shadow duplicates,
 * enabling pristine screen-splitting at 1000% zoom.
 */
export function VectorCanvas({ camera }) {
  const baseDim = 1024;
  const w = baseDim / Math.max(0.1, camera.scale);
  const h = baseDim / Math.max(0.1, camera.scale);
  const minX = camera.cx - w / 2;
  const minY = camera.cy - h / 2;

  const pathData = [
    'M 512.00 80.00 V 512.00',
    'M 464.00 82.67 V 512.00 A 48.00 48.00 0 0 0 560.00 512.00 V 82.67',
    'M 416.00 90.80 V 512.00 A 96.00 96.00 0 0 0 608.00 512.00 V 90.80',
    'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
    'M 320.00 125.01 V 512.00 A 192.00 192.00 0 0 0 704.00 512.00 V 125.01',
    'M 272.00 152.80 V 512.00 A 240.00 240.00 0 0 0 752.00 512.00 V 152.80',
    'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
    'M 176.00 240.47 V 512.00 A 336.00 336.00 0 0 0 848.00 512.00 V 240.47',
    'M 128.00 314.09 V 512.00 A 384.00 384.00 0 0 0 896.00 512.00 V 314.09',
    'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00'
  ].join(' ');

  return (
    <div
      className="fixed inset-0 w-full h-full pointer-events-none z-0 transition-transform duration-75 ease-out select-none"
      style={{
        transform: `rotate(${camera.rotation}deg)`,
      }}
    >
      <svg
        viewBox={`${minX} ${minY} ${w} ${h}`}
        preserveAspectRatio="xMidYMid slice"
        className="w-full h-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Solid Background Canvas */}
        <rect width="1024" height="1024" fill="var(--color-canvas)" />

        {/* Clean, Authentic Halbert Vector Paths in Pop Chartreuse */}
        <g
          fill="none"
          stroke="var(--color-vector-lime)"
          strokeWidth="32"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={pathData} />
        </g>
      </svg>
    </div>
  );
}
