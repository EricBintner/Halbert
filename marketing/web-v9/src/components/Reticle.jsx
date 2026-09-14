import React from 'react';

/**
 * Debug reticle: marks the exact screen centre the camera is locked to.
 * Toggle with the D key. Useful for checking that every stop's split passes
 * through the centre.
 */
export function Reticle({ visible, camera }) {
  if (!visible) return null;
  return (
    <div className="fixed inset-0 z-40 pointer-events-none mix-blend-difference text-white" aria-hidden="true">
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-white/60 -translate-x-1/2" />
      <div className="absolute top-1/2 left-0 right-0 h-px bg-white/60 -translate-y-1/2" />
      <div className="absolute left-1/2 top-1/2 w-6 h-6 -translate-x-1/2 -translate-y-1/2 border border-white rounded-full" />
      <div className="absolute left-1/2 top-1/2 ml-5 mt-3 font-mono text-[10px] leading-tight whitespace-pre">
        {`focal (${camera.cx.toFixed(1)}, ${camera.cy.toFixed(1)})\nzoom ${Math.round(camera.scale * 100)}%\n${camera.phase} · ${camera.layout.kind} · stroke ${camera.layout.strokeSide}`}
      </div>
    </div>
  );
}
