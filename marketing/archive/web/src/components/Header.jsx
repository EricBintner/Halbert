import React from 'react';
import { HalbertMark } from './HalbertMark';

export function Header({ copy, onJoinWaitlistClick }) {
  const masthead = copy?.masthead || {
    vol: 'VOL. 1',
    issue: 'NO. 1 — AUGUST 2026',
    edition: 'FIRST EDITION',
    tagline: 'You can call me AI.',
    cta: 'Get Early Access',
  };

  return (
    <header className="w-full bg-[var(--color-canvas)] border-b-3 border-[var(--color-ink)] pt-6 pb-4 px-6 select-none">
      <div className="max-w-[var(--content-max-width)] mx-auto flex flex-col md:flex-row items-baseline justify-between gap-4">
        {/* Left: Brand Mark & Masthead Title */}
        <div className="flex items-center space-x-3.5">
          <HalbertMark size={32} color="var(--color-ink)" />
          <a href="#" className="flex items-baseline space-x-3 group">
            <span className="font-display font-extrabold text-3xl md:text-4xl tracking-tighter text-[var(--color-ink)]">
              Halbert<span className="text-[var(--color-accent)] font-black">.</span>
            </span>
            <span className="hidden sm:inline-block font-mono text-[12px] font-bold uppercase tracking-widest text-[var(--color-ink-tertiary)] border-l-2 border-[var(--color-ink)] pl-3">
              {masthead.edition}
            </span>
          </a>
        </div>

        {/* Center/Right: Edition Metadata & Direct Action */}
        <div className="flex items-center space-x-6 text-[12px] font-mono font-bold tracking-wider uppercase text-[var(--color-ink)]">
          <span className="hidden md:inline text-[var(--color-ink-secondary)]">
            {masthead.vol} · {masthead.issue}
          </span>
          <button
            onClick={onJoinWaitlistClick}
            className="px-3.5 py-1.5 bg-[var(--color-ink)] text-white hover:bg-[var(--color-accent)] transition-colors border border-[var(--color-ink)] shadow-[2px_2px_0px_0px_rgba(211,78,36,1)]"
          >
            {masthead.cta} →
          </button>
        </div>
      </div>
    </header>
  );
}
