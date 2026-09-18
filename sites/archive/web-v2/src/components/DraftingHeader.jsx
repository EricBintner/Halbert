import React from 'react';
import { HalbertMark } from './HalbertMark';

export function DraftingHeader({ onEarlyAccessClick }) {
  return (
    <header className="sticky top-0 z-50 bg-[var(--color-canvas)]/95 backdrop-blur-sm border-b border-[var(--color-ink)] select-none">
      {/* Top Coordinate Bar */}
      <div className="border-b border-[var(--color-grid-line-strong)]/20 py-1 px-4 sm:px-8 flex justify-between items-center text-[10.5px] font-mono uppercase tracking-widest text-[var(--color-ink-tertiary)]">
        <div>SPEC: HALBERT-CORE · ARCH: BARE-METAL · REV: 2026.8</div>
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 bg-[var(--color-status-success)] rounded-full animate-pulse" />
          <span className="text-[var(--color-ink)] font-bold">TELEMETRY ACTIVE (0.12ms)</span>
        </div>
      </div>

      {/* Main Masthead Bar */}
      <div className="max-w-[var(--content-max-width)] mx-auto px-4 sm:px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <HalbertMark size={28} color="#121417" />
          <a href="#" className="flex items-baseline space-x-2">
            <span className="font-display font-bold text-2xl tracking-tighter text-[var(--color-ink)]">
              HALBERT<span className="text-[var(--color-accent)] font-black">.</span>
            </span>
            <span className="hidden md:inline font-mono text-[11px] font-medium text-[var(--color-blueprint)] border border-[var(--color-blueprint)] px-1.5 py-0.5">
              HOST INTELLIGENCE
            </span>
          </a>
        </div>

        {/* Center Technical Anchors */}
        <nav className="hidden lg:flex items-center space-x-6 text-[13px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-secondary)]">
          <a href="#hero" className="hover:text-[var(--color-accent)] transition-colors">01. Host Ethos</a>
          <a href="#autobiography" className="hover:text-[var(--color-accent)] transition-colors">02. Memory Tape</a>
          <a href="#blueprint" className="hover:text-[var(--color-accent)] transition-colors">03. Config AST</a>
          <a href="#proof" className="hover:text-[var(--color-accent)] transition-colors">04. Proof Console</a>
        </nav>

        {/* Action Button */}
        <div>
          <button
            onClick={onEarlyAccessClick}
            className="px-4 py-2 bg-[var(--color-accent)] text-white text-xs font-mono font-bold uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition-all shadow-[2px_2px_0px_0px_rgba(18,20,23,1)] active:translate-x-0.5 active:translate-y-0.5"
          >
            Dispatch Build →
          </button>
        </div>
      </div>
    </header>
  );
}
