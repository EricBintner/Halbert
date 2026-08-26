import React from 'react';
import { Terminal } from 'lucide-react';

export function TerminalFrame({
  title = 'halbert — ubuntu-server-01',
  figure = 'FIG. A',
  isLive = true,
  children,
  className = '',
}) {
  return (
    <div
      className={`border-2 border-[var(--color-ink)] bg-[var(--color-surface)] shadow-[6px_6px_0px_0px_rgba(26,25,24,1)] overflow-hidden flex flex-col transition-all ${className}`}
    >
      {/* 60s Hardware Titlebar / Chrome */}
      <div className="h-10 px-3 bg-[var(--color-surface-subtle)] border-b-2 border-[var(--color-ink)] flex items-center justify-between select-none">
        {/* Window controls (Sharp vintage tactile pips) */}
        <div className="flex items-center space-x-1.5">
          <span className="w-3 h-3 bg-[#D34E24] border border-[var(--color-ink)]" />
          <span className="w-3 h-3 bg-[#E5E0D5] border border-[var(--color-ink)]" />
          <span className="w-3 h-3 bg-[var(--color-ink)] border border-[var(--color-ink)]" />
        </div>

        {/* Title / Figure */}
        <div className="flex items-center space-x-2 text-[12px] font-mono font-bold tracking-wider uppercase text-[var(--color-ink)]">
          <span className="text-[var(--color-accent)]">{figure}</span>
          <span className="text-[var(--color-ink-ghost)]">|</span>
          <span>{title}</span>
        </div>

        {/* Live Status Badge */}
        <div className="flex items-center space-x-1.5 font-mono text-[11px] font-bold">
          {isLive ? (
            <span className="inline-flex items-center px-2 py-0.5 bg-[#EEF6F2] text-[#2D7A56] border border-[#2D7A56]">
              <span className="w-1.5 h-1.5 bg-[#2D7A56] mr-1.5 animate-pulse" />
              LIVE
            </span>
          ) : (
            <span className="px-2 py-0.5 bg-[var(--color-surface-muted)] text-[var(--color-ink-tertiary)] border border-[var(--color-ink-tertiary)]">
              STANDBY
            </span>
          )}
        </div>
      </div>

      {/* Terminal Body */}
      <div className="p-5 md:p-6 bg-[var(--color-surface)] text-[var(--color-ink)] font-mono text-[13.5px] md:text-[14px] leading-relaxed flex-1 overflow-y-auto">
        {children}
      </div>
    </div>
  );
}
