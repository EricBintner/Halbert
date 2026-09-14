import React from 'react';
import { MARK, MARK_PATH_D, viewBoxFor } from '../lib/markGeometry';

/**
 * Renders the Halbert mark with the camera focal point (cx, cy) pinned to the
 * exact centre of the viewport. The viewBox is sized from the live aspect
 * ratio, so 1 mark unit is the same number of pixels horizontally and
 * vertically — edges stay straight and angles stay true on any screen.
 */
export function VectorCanvas({ camera, viewport }) {
  const aspect = viewport.width / Math.max(1, viewport.height);
  const { minX, minY, w, h } = viewBoxFor(camera, aspect);

  return (
    <div className="fixed inset-0 w-full h-full pointer-events-none z-0 select-none" aria-hidden="true">
      <svg
        viewBox={`${minX} ${minY} ${w} ${h}`}
        preserveAspectRatio="none"
        className="w-full h-full block"
        xmlns="http://www.w3.org/2000/svg"
      >
        <g
          fill="none"
          stroke="var(--color-stroke)"
          strokeWidth={MARK.strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={MARK_PATH_D} />
        </g>
      </svg>
    </div>
  );
}
