import React from 'react';
import { MARK, MARK_PATH_D, viewBoxFor } from '../lib/markGeometry';

/**
 * Renders the Halbert mark with the camera focal point (cx, cy) pinned to the
 * exact centre of the viewport. The viewBox is sized from the live aspect
 * ratio, so 1 mark unit is the same number of pixels horizontally and
 * vertically — edges stay straight and angles stay true on any screen.
 */
export function VectorCanvas({ camera, viewport }) {
  // Degenerate viewports (a hidden tab collapsing to 0x0) produce a 0 aspect,
  // which zeroes the viewBox width and yields NaN in the mask matrix below.
  // Floor the aspect — anything under 10% of height only happens off-screen.
  const aspect = Math.max(0.1, viewport.width / Math.max(1, viewport.height));
  const { minX, minY, w, h } = viewBoxFor(camera, aspect);

  const scaleX = viewport.width / w;
  const scaleY = viewport.height / h;
  const translateX = -minX * scaleX;
  const translateY = -minY * scaleY;

  return (
    <div className="fixed inset-0 w-full h-full pointer-events-none z-0 select-none" aria-hidden="true">
      <svg
        viewBox={`${minX} ${minY} ${w} ${h}`}
        preserveAspectRatio="none"
        className="w-full h-full block"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <mask
            id="stroke-intersection-mask"
            maskUnits="userSpaceOnUse"
            x="0"
            y="0"
            width={viewport.width}
            height={viewport.height}
          >
            <g transform={`matrix(${scaleX}, 0, 0, ${scaleY}, ${translateX}, ${translateY})`}>
              <g
                fill="none"
                stroke="white"
                strokeWidth={MARK.strokeWidth}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d={MARK_PATH_D} />
              </g>
            </g>
          </mask>
        </defs>
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
