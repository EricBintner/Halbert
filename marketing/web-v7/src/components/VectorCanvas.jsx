import React from 'react';

export function VectorCanvas({ camera }) {
  // Compute dynamic viewBox from camera center and scale
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
        <defs>
          <filter id="cmyk-misreg">
            <feOffset in="SourceGraphic" dx="-1.5" dy="-0.5" result="cyan" />
            <feOffset in="SourceGraphic" dx="1.5" dy="0.5" result="magenta" />
            <feMerge>
              <feMergeNode in="cyan" />
              <feMergeNode in="magenta" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Outer Background Canvas */}
        <rect width="1024" height="1024" fill="var(--color-canvas)" />

        {/* Architectural Tangent Guidelines & Crosshairs */}
        <g stroke="rgba(255,255,255,0.12)" strokeWidth="1" strokeDasharray="4 8">
          <line x1="512" y1="0" x2="512" y2="1024" />
          <line x1="0" y1="512" x2="1024" y2="512" />
          <circle cx="512" cy="512" r="432" fill="none" />
          <circle cx="512" cy="512" r="288" fill="none" />
          <circle cx="512" cy="512" r="144" fill="none" />
        </g>

        {/* CMYK Underprint Shadow (Offset Cyan & Magenta) */}
        <g
          fill="none"
          stroke="rgba(0, 240, 255, 0.4)"
          strokeWidth="38"
          strokeLinecap="round"
          strokeLinejoin="round"
          transform="translate(-2, -1)"
        >
          <path d={pathData} />
        </g>
        <g
          fill="none"
          stroke="rgba(255, 0, 127, 0.4)"
          strokeWidth="38"
          strokeLinecap="round"
          strokeLinejoin="round"
          transform="translate(2, 1)"
        >
          <path d={pathData} />
        </g>

        {/* Main Solid Vibrant Vector Tracks in Pop Chartreuse */}
        <g
          fill="none"
          stroke="var(--color-vector-lime)"
          strokeWidth="36"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={pathData} />
        </g>

        {/* Dynamic Camera Focal Target Reticle */}
        <g transform={`translate(${camera.cx}, ${camera.cy})`}>
          <circle r="12" fill="none" stroke="#FFFFFF" strokeWidth="1.5" opacity="0.6" strokeDasharray="3 3" />
          <line x1="-18" y1="0" x2="18" y2="0" stroke="#FFFFFF" strokeWidth="1" opacity="0.6" />
          <line x1="0" y1="-18" x2="0" y2="18" stroke="#FFFFFF" strokeWidth="1" opacity="0.6" />
        </g>
      </svg>
    </div>
  );
}
