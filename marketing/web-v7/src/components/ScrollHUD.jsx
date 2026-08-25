import React from 'react';
import { WAYPOINTS } from '../lib/cameraMotion';

export function ScrollHUD({ currentWaypoint, onSelectWaypoint, scrollProgress }) {
  return (
    <nav aria-label="Waypoint Navigation" className="fixed right-6 top-1/2 -translate-y-1/2 z-30 font-mono select-none hidden sm:flex flex-col items-end space-y-3">
      {WAYPOINTS.map((wp) => {
        const isActive = currentWaypoint === wp.id;
        return (
          <button
            key={wp.id}
            onClick={() => onSelectWaypoint(wp.id)}
            className="group flex items-center space-x-3 cursor-pointer text-left"
          >
            {/* Tooltip Label */}
            <span
              className={`text-[11px] font-bold transition-all px-2 py-0.5 rounded-sm ${
                isActive
                  ? 'text-[#042F2E] bg-[var(--color-vector-lime)] opacity-100 shadow-xs'
                  : 'text-white/60 opacity-0 group-hover:opacity-100 bg-black/40'
              }`}
            >
              {wp.name}
            </span>

            {/* Indicator Pip */}
            <span
              className={`w-3 h-3 rounded-full border transition-all ${
                isActive
                  ? 'bg-[var(--color-vector-lime)] border-[var(--color-vector-lime)] scale-125 shadow-[0_0_8px_rgba(212,225,87,0.8)]'
                  : 'border-white/40 bg-black/20 group-hover:border-white'
              }`}
            />
          </button>
        );
      })}

      {/* Progress Metric */}
      <div className="pt-2 text-[10px] text-[var(--color-vector-lime)] font-mono">
        {Math.round(scrollProgress * 100)}% TRAVEL
      </div>
    </nav>
  );
}
