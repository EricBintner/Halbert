import React from 'react';
import { HalbertMark } from './HalbertMark';

export function EditorialMasthead({ onSubscribeClick }) {
  return (
    <header className="w-full border-b border-white/20 bg-[var(--color-canvas)]/90 backdrop-blur-md sticky top-0 z-50 select-none">
      {/* Top Edition Meta Ribbon */}
      <div className="border-b border-white/10 py-1.5 px-6 sm:px-12 flex justify-between items-center text-[11px] font-mono text-[var(--color-ink-tertiary)] tracking-widest uppercase">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 bg-[var(--color-accent)] rounded-full animate-pulse" />
          <span>FOLIO NO. 03 · RETRO SERIF EDITION · AUTUMN 2026</span>
        </div>
        <div className="hidden sm:inline text-white/80">100% LOCAL-FIRST HOST INTELLIGENCE</div>
      </div>

      {/* Main Masthead Bar */}
      <div className="max-w-[var(--content-max-width)] mx-auto px-6 sm:px-12 py-4 flex items-center justify-between">
        {/* Wordmark */}
        <div className="flex items-center space-x-3.5">
          <HalbertMark size={32} color="#FFFFFF" />
          <a href="#" className="flex items-baseline space-x-2">
            <span className="font-display font-bold text-3xl md:text-4xl tracking-tight text-white">
              Halbert<span className="text-[var(--color-accent)] font-black">.</span>
            </span>
          </a>
        </div>

        {/* Navigation Anchors */}
        <nav className="hidden md:flex items-center space-x-8 text-[14px] font-sans font-medium text-white/85">
          <a href="#hero" className="hover:text-[var(--color-accent)] transition-colors">Prologue</a>
          <a href="#chapters" className="hover:text-[var(--color-accent)] transition-colors">The Chapters</a>
          <a href="#confessional" className="hover:text-[var(--color-accent)] transition-colors">The Being</a>
          <a href="#colophon" className="hover:text-[var(--color-accent)] transition-colors">Colophon</a>
        </nav>

        {/* CTA */}
        <div>
          <button
            onClick={onSubscribeClick}
            className="px-4 py-2 bg-[var(--color-accent)] text-[#1B447A] text-xs font-mono font-bold uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition-all shadow-[0_4px_12px_rgba(252,211,77,0.3)] active:translate-y-0.5"
          >
            Early Access →
          </button>
        </div>
      </div>
    </header>
  );
}
