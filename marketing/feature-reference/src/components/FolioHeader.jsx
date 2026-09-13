import React from 'react';
import { HalbertMark } from './HalbertMark';
import { Search, Sun, Moon } from 'lucide-react';

export function FolioHeader({
  theme,
  onToggleTheme,
  onOpenSearch,
}) {
  return (
    <header className="fixed top-0 inset-x-0 z-40 flex items-center justify-between px-6 py-3.5 text-xs font-mono text-[var(--color-ink)] bg-[var(--color-canvas)]/90 backdrop-blur-md border-b border-[var(--color-line)] transition-colors">
      {/* Brand identity matching marketing site */}
      <div className="flex items-center space-x-3">
        <HalbertMark size={20} density="medium" color="currentColor" />
        <span className="font-bold tracking-wider text-xs text-[var(--color-ink)]">
          HALBERT
        </span>
        <span className="text-[var(--color-line-strong)]">/</span>
        <span className="text-[var(--color-ink-secondary)] text-[11px]">
          Feature Reference
        </span>
      </div>

      {/* Right: Clean minimal actions (no pills) */}
      <div className="flex items-center space-x-4 text-xs font-mono">
        <button
          onClick={onOpenSearch}
          className="flex items-center space-x-2 text-[var(--color-ink-secondary)] hover:text-[var(--color-accent)] transition-colors"
          title="Search specifications (press '/')"
        >
          <Search className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Search</span>
          <span className="text-[10px] text-[var(--color-ink-tertiary)] opacity-60">
            [/]
          </span>
        </button>

        <button
          onClick={onToggleTheme}
          className="flex items-center space-x-1.5 text-[var(--color-ink-secondary)] hover:text-[var(--color-accent)] transition-colors"
          title="Toggle Daylight / After Hours"
        >
          {theme === 'dark' ? (
            <>
              <Sun className="w-3.5 h-3.5 text-[var(--color-accent)]" />
              <span className="hidden md:inline">Daylight</span>
            </>
          ) : (
            <>
              <Moon className="w-3.5 h-3.5 text-[var(--color-accent)]" />
              <span className="hidden md:inline">After Hours</span>
            </>
          )}
        </button>

        <a
          href="https://github.com/EricBintner/Halbert"
          target="_blank"
          rel="noreferrer"
          className="hidden sm:inline text-[var(--color-ink-secondary)] hover:text-[var(--color-accent)] transition-colors"
        >
          GitHub
        </a>
      </div>
    </header>
  );
}
