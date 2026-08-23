import React from 'react';
import { ArrowRight, Terminal } from 'lucide-react';
import { HalbertMark } from './HalbertMark';

export function Header({ onJoinWaitlistClick }) {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-16 bg-[var(--color-canvas)]/85 backdrop-blur-md border-b border-[var(--color-hairline)] transition-all duration-300">
      <div className="max-w-[var(--content-max-width)] mx-auto h-full px-6 flex items-center justify-between">
        {/* Wordmark & Brand Mark */}
        <a href="#" className="flex items-center space-x-2.5 group">
          <HalbertMark size={26} color="var(--color-accent, #D34E24)" className="transition-transform group-hover:scale-105" />
          <span className="font-display font-semibold text-2xl tracking-tight text-[var(--color-ink)]">
            Halbert<span className="text-[var(--color-accent)] font-bold">.</span>
          </span>
          <span className="hidden sm:inline-block text-[12px] font-mono text-[var(--color-ink-tertiary)] border border-[var(--color-hairline-strong)] px-2 py-0.5 rounded-full">
            v2026.8
          </span>
        </a>

        {/* Center Navigation Links */}
        <nav className="hidden md:flex items-center space-x-8 text-[14.5px] font-medium text-[var(--color-ink-secondary)]">
          <a href="#how-it-works" className="hover:text-[var(--color-ink)] transition-colors">
            How It Works
          </a>
          <a href="#the-being" className="hover:text-[var(--color-ink)] transition-colors">
            The Being
          </a>
          <a href="https://github.com/EricBintner/Halbert" target="_blank" rel="noreferrer" className="hover:text-[var(--color-ink)] transition-colors">
            GitHub
          </a>
        </nav>

        {/* Right CTA */}
        <div className="flex items-center space-x-4">
          <button
            onClick={onJoinWaitlistClick}
            className="inline-flex items-center px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-[14px] font-semibold hover:bg-[var(--color-accent-hover)] transition-all shadow-sm hover:shadow-[0_4px_12px_rgba(211,78,36,0.25)] active:translate-y-px"
          >
            <span>Early Access</span>
            <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
          </button>
        </div>
      </div>
    </header>
  );
}
