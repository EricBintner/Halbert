import React from 'react';
import { HalbertMark } from './HalbertMark';
import { BlueVioletInstallation } from './BlueVioletInstallation';

export function ExperimentalHero({ scrollY = 0 }) {
  return (
    <section className="full-window-section relative overflow-hidden bg-[var(--color-canvas)] border-b border-[var(--color-surface-muted)] select-none">
      {/* 80% Light Blue-Violet Generative Vector Installation */}
      <BlueVioletInstallation scrollY={scrollY} />

      {/* Top Folio Coordinate Strip */}
      <div className="absolute top-6 left-6 right-6 flex justify-between items-center text-[11px] font-mono text-[var(--color-ink-secondary)] z-20">
        <div className="flex items-center space-x-3">
          <span className="font-bold text-[var(--color-ink)]">HALBERT CORP.</span>
          <span className="text-[var(--color-ink-tertiary)]">// FIG. 01 EMBODIMENT</span>
        </div>

        {/* CMYK Calibration Color Wedge */}
        <div className="flex items-center space-x-2">
          <div className="cmyk-strip border border-black/20">
            <span className="bg-[#00E5FF]" title="Cyan" />
            <span className="bg-[#FF007A]" title="Magenta" />
            <span className="bg-[#FFD600]" title="Yellow" />
            <span className="bg-[#121417]" title="Key Black" />
          </div>
          <span className="text-[10px] text-[var(--color-ink-tertiary)] hidden sm:inline">
            ⨁ REG. 100%
          </span>
        </div>
      </div>

      {/* Centerpiece: Massive Centered Logo & Voluptuous Typography */}
      <div className="relative z-10 max-w-4xl mx-auto px-6 text-center space-y-8 flex flex-col items-center justify-center">
        {/* Massive Centered Halbert Vector Logo */}
        <div className="relative group cursor-pointer transition-transform duration-300 hover:scale-105">
          {/* Subtle CMYK shadow offset */}
          <div className="absolute -inset-1 opacity-40 blur-xs text-[#00E5FF] translate-x-[-2px] translate-y-[-1px]">
            <HalbertMark size={148} color="#00E5FF" strokeWidth={32} />
          </div>
          <div className="absolute -inset-1 opacity-40 blur-xs text-[#FF007A] translate-x-[2px] translate-y-[1px]">
            <HalbertMark size={148} color="#FF007A" strokeWidth={32} />
          </div>
          <HalbertMark size={148} color="#121417" strokeWidth={32} />
        </div>

        {/* Wordmark & Tagline */}
        <div className="space-y-3">
          <div className="inline-block px-3 py-1 bg-[var(--color-surface-subtle)] border border-[var(--color-surface-muted)] text-xs font-mono text-[var(--color-violet-dark)] tracking-widest uppercase font-bold">
            THE LOCAL-FIRST HOST APPARATUS
          </div>

          <h1 className="text-5xl sm:text-7xl lg:text-[84px] font-display font-black tracking-tight text-[var(--color-ink)] leading-[0.98] cmyk-bleed">
            I know what’s wrong with me<span className="text-[var(--color-violet-deep)]">.</span>
          </h1>

          <p className="text-base sm:text-xl text-[var(--color-ink-secondary)] max-w-2xl mx-auto font-sans font-medium leading-relaxed pt-2">
            A computer that speaks in first person, possesses configuration memory, and feels its own hardware diodes.
          </p>
        </div>

        {/* Scroll Indicator */}
        <div className="pt-6 flex flex-col items-center space-y-2 text-[11px] font-mono text-[var(--color-ink-tertiary)] uppercase tracking-widest animate-bounce">
          <span>SCROLL TO ENTER PRODUCT WORKSPACE</span>
          <span className="text-lg text-[var(--color-violet-deep)]">↓</span>
        </div>
      </div>

      {/* Bottom Registration Guide */}
      <div className="absolute bottom-4 left-6 right-6 flex justify-between text-[10px] font-mono text-[var(--color-ink-tertiary)] z-20">
        <div>COORDINATE: 37.4419° N, 122.1430° W</div>
        <div>100% HOST BOUND · ZERO CLOUD EGRESS</div>
      </div>
    </section>
  );
}
