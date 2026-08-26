import React from 'react';

export function DesktopWindow({
  title = 'Halbert — Host Intelligence',
  figure = 'FIG. 2',
  activeTab = 'vitals',
  children,
  className = '',
}) {
  return (
    <div
      className={`border-2 border-[var(--color-ink)] bg-[var(--color-surface)] shadow-[8px_8px_0px_0px_rgba(26,25,24,1)] overflow-hidden flex flex-col transition-all ${className}`}
    >
      {/* Titlebar with Industrial Print Controls */}
      <div className="h-11 px-4 bg-[var(--color-surface-subtle)] border-b-2 border-[var(--color-ink)] flex items-center justify-between select-none">
        {/* Hardware controls */}
        <div className="flex items-center space-x-1.5">
          <span className="w-3.5 h-3.5 bg-[var(--color-ink)]" />
          <span className="w-3.5 h-3.5 bg-[var(--color-surface-muted)] border border-[var(--color-ink)]" />
          <span className="w-3.5 h-3.5 bg-[var(--color-accent)]" />
        </div>

        {/* Tab Controls (Sharp 60s Editorial) */}
        <div className="flex items-center space-x-1 font-mono text-[12px] font-bold">
          <span className="text-[var(--color-accent)] mr-2">{figure}</span>
          <div
            className={`px-3 py-1 border border-[var(--color-ink)] uppercase tracking-wider ${
              activeTab === 'vitals'
                ? 'bg-[var(--color-ink)] text-white'
                : 'bg-[var(--color-surface)] text-[var(--color-ink)]'
            }`}
          >
            Vitals
          </div>
          <div
            className={`px-3 py-1 border border-[var(--color-ink)] uppercase tracking-wider ${
              activeTab === 'config'
                ? 'bg-[var(--color-ink)] text-white'
                : 'bg-[var(--color-surface)] text-[var(--color-ink)]'
            }`}
          >
            Diff
          </div>
          <div
            className={`px-3 py-1 border border-[var(--color-ink)] uppercase tracking-wider ${
              activeTab === 'storage'
                ? 'bg-[var(--color-ink)] text-white'
                : 'bg-[var(--color-surface)] text-[var(--color-ink)]'
            }`}
          >
            Storage
          </div>
        </div>

        {/* Host Label */}
        <div className="flex items-center space-x-2 text-[11px] font-mono font-bold uppercase text-[var(--color-ink)]">
          <span>HOST: UBUNTU-01</span>
        </div>
      </div>

      {/* Main Window Stage */}
      <div className="p-6 bg-[var(--color-surface)] flex-1 min-h-[360px] flex flex-col justify-center font-mono">
        {children}
      </div>
    </div>
  );
}
