import React from 'react';
import { HalbertMark } from './HalbertMark';

export function Footer() {
  return (
    <footer className="py-12 px-6 bg-[var(--color-canvas)] text-[var(--color-ink-secondary)] text-xs font-sans">
      <div className="max-w-[var(--content-max-width)] mx-auto flex flex-col sm:flex-row justify-between items-center gap-6">
        <div className="flex items-center space-x-3">
          <HalbertMark size={20} color="#0F172A" />
          <span className="font-display font-bold text-sm text-[var(--color-ink)]">
            Halbert
          </span>
          <span className="text-[var(--color-ink-tertiary)]">
            — Local-First Host Intelligence
          </span>
        </div>

        <div className="flex items-center space-x-6">
          <a href="#features" className="hover:text-[var(--color-ink)] transition-colors">
            Capabilities
          </a>
          <a href="#console" className="hover:text-[var(--color-ink)] transition-colors">
            Demo
          </a>
          <a
            href="https://github.com/EricBintner/Halbert"
            target="_blank"
            rel="noreferrer"
            className="hover:text-[var(--color-ink)] transition-colors font-mono"
          >
            GitHub Repository ↗
          </a>
        </div>

        <div className="text-[11px] font-mono text-[var(--color-ink-tertiary)]">
          © 2026 Eric Bintner. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
