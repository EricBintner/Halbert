import React from 'react';

export function GrainShaderOverlay() {
  return (
    <div className="pointer-events-none fixed inset-0 z-40 overflow-hidden mix-blend-multiply opacity-25 select-none">
      <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
        <filter id="procedural-grit">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.8"
            numOctaves="4"
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#procedural-grit)" />
      </svg>
    </div>
  );
}
