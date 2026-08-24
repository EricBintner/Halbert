import React from 'react';
import { HalbertMark } from './HalbertMark';

export function Navbar({ onEarlyAccessClick }) {
  return (
    <header className="w-full border-b border-white/25 bg-[var(--color-canvas)] sticky top-0 z-50">
      <div className="max-w-[var(--content-max-width)] mx-auto px-6 sm:px-10 h-20 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center space-x-3.5">
          <HalbertMark size={32} color="#FFFFFF" strokeWidth={32} />
          <a href="#" className="flex items-baseline space-x-1">
            <span className="font-display font-black text-2xl sm:text-3xl tracking-tight text-white">
              Halbert<span className="text-[var(--color-accent-amber)] font-black">.</span>
            </span>
          </a>
        </div>

        {/* Center Nav Links */}
        <nav className="hidden md:flex items-center space-x-8 text-[12.5px] font-mono tracking-widest uppercase font-semibold text-white/80">
          <a href="#features" className="hover:text-white transition-colors">
            01 / Sensations
          </a>
          <a href="#memory" className="hover:text-white transition-colors">
            02 / Memory
          </a>
          <a href="#manuals" className="hover:text-white transition-colors">
            03 / Manuals
          </a>
          <a href="#privacy" className="hover:text-white transition-colors">
            04 / Local Host
          </a>
        </nav>

        {/* Action Button */}
        <div>
          <button
            onClick={onEarlyAccessClick}
            className="px-5 py-2.5 bg-white text-[#1D4ED8] font-display font-bold text-xs uppercase tracking-wider hover:bg-amber-300 hover:text-[#1D4ED8] transition-all shadow-md active:translate-y-0.5 cursor-pointer"
          >
            Early Access →
          </button>
        </div>
      </div>
    </header>
  );
}
