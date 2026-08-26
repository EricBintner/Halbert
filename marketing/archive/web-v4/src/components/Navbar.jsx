import React from 'react';
import { HalbertMark } from './HalbertMark';

export function Navbar({ onGetAccessClick }) {
  return (
    <header className="sticky top-0 z-50 bg-[var(--color-canvas)]/90 backdrop-blur-md border-b border-[var(--color-surface-muted)] transition-all">
      <div className="max-w-[var(--content-max-width)] mx-auto px-6 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center space-x-3">
          <HalbertMark size={26} color="#0F172A" />
          <a href="#" className="flex items-center space-x-2">
            <span className="font-display font-extrabold text-xl tracking-tight text-[var(--color-ink)]">
              Halbert
            </span>
            <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-full bg-[var(--color-surface-subtle)] text-[var(--color-ink-secondary)] border border-[var(--color-surface-muted)]">
              v2026.8
            </span>
          </a>
        </div>

        {/* Center Nav Links */}
        <nav className="hidden md:flex items-center space-x-8 text-[13.5px] font-medium text-[var(--color-ink-secondary)]">
          <a href="#features" className="hover:text-[var(--color-ink)] transition-colors">
            Capabilities
          </a>
          <a href="#console" className="hover:text-[var(--color-ink)] transition-colors">
            Interactive Demo
          </a>
          <a href="#privacy" className="hover:text-[var(--color-ink)] transition-colors">
            Privacy &amp; Safety
          </a>
        </nav>

        {/* CTA Button */}
        <div>
          <button
            onClick={onGetAccessClick}
            className="px-4 py-2 bg-[var(--color-ink)] text-white text-xs font-semibold rounded-lg hover:bg-[var(--color-accent-hover)] transition-all shadow-sm active:translate-y-0.5"
          >
            Get Early Access →
          </button>
        </div>
      </div>
    </header>
  );
}
