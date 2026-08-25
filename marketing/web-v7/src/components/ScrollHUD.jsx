import React from 'react';
import { STOPS } from '../lib/storyboard';

export function ScrollHUD({ currentStop, onSelectStop, scrollProgress }) {
  return (
    <nav aria-label="Stop navigation" className="fixed right-6 top-1/2 -translate-y-1/2 z-30 font-mono select-none hidden sm:flex flex-col items-end space-y-3 mix-blend-difference text-white">
      {STOPS.map((stop, i) => {
        const isActive = currentStop === i;
        return (
          <button
            key={stop.id}
            onClick={() => onSelectStop(i)}
            className="group flex items-center space-x-3 cursor-pointer text-left"
          >
            <span
              className={`text-[11px] font-bold transition-opacity px-2 py-0.5 ${
                isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              }`}
            >
              {stop.name}
            </span>
            <span
              className={`w-2.5 h-2.5 rounded-full border border-white transition-transform ${
                isActive ? 'bg-white scale-125' : 'bg-transparent group-hover:scale-110'
              }`}
            />
          </button>
        );
      })}
      <div className="pt-2 text-[10px]">{Math.round(scrollProgress * 100)}% TRAVEL</div>
    </nav>
  );
}
