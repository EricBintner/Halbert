import React from 'react';
import { Terminal, Activity } from 'lucide-react';

export function TerminalFrame({
  title = 'halbert — ubuntu-server-01',
  isLive = true,
  children,
  className = '',
}) {
  return (
    <div
      className={`rounded-2xl border border-[var(--color-hairline-strong)] bg-[var(--color-surface)] shadow-[var(--shadow-device)] overflow-hidden flex flex-col transition-all duration-300 ${className}`}
    >
      {/* Titlebar / Chrome */}
      <div className="h-10.5 px-4 bg-[var(--color-surface-subtle)] border-b border-[var(--color-hairline)] flex items-center justify-between select-none">
        {/* Window controls (Mid-century stone/muted pips) */}
        <div className="flex items-center space-x-2">
          <span className="w-3 h-3 rounded-full bg-[#E57A64] border border-[#D0604A]/40" />
          <span className="w-3 h-3 rounded-full bg-[#E8B568] border border-[#CF9B4E]/40" />
          <span className="w-3 h-3 rounded-full bg-[#7CAE8E] border border-[#649676]/40" />
        </div>

        {/* Title */}
        <div className="flex items-center space-x-2 text-[13px] font-mono font-medium text-[var(--color-ink-secondary)]">
          <Terminal className="w-3.5 h-3.5 text-[var(--color-ink-tertiary)]" />
          <span>{title}</span>
        </div>

        {/* Live Status Badge */}
        <div className="flex items-center space-x-1.5">
          {isLive ? (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-[#EEF6F2] text-[#2D7A56] border border-[#C2E0D1]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#2D7A56] mr-1.5 animate-pulse" />
              LIVE
            </span>
          ) : (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono text-[var(--color-ink-tertiary)] bg-[var(--color-surface-muted)]">
              IDLE
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
