import React from 'react';
import { Cpu, HardDrive, FileCode, Shield, Activity, RefreshCw } from 'lucide-react';

export function DesktopWindow({
  title = 'Halbert — Host Intelligence',
  activeTab = 'vitals',
  children,
  className = '',
}) {
  return (
    <div
      className={`rounded-2xl border border-[var(--color-hairline-strong)] bg-[var(--color-surface)] shadow-[var(--shadow-device)] overflow-hidden flex flex-col transition-all duration-500 ${className}`}
    >
      {/* Titlebar with Traffic Lights & Navigation Tabs */}
      <div className="h-12 px-4 bg-[var(--color-surface-subtle)] border-b border-[var(--color-hairline)] flex items-center justify-between select-none">
        {/* Native traffic lights */}
        <div className="flex items-center space-x-2">
          <span className="w-3 h-3 rounded-full bg-[#FF5F56] border border-[#E0443E]/50" />
          <span className="w-3 h-3 rounded-full bg-[#FFBD2E] border border-[#DEA123]/50" />
          <span className="w-3 h-3 rounded-full bg-[#27C93F] border border-[#1AAB29]/50" />
        </div>

        {/* Segmented Control / Module Tabs */}
        <div className="flex items-center space-x-1 p-1 bg-[var(--color-surface-muted)] rounded-lg text-[12px] font-medium text-[var(--color-ink-secondary)]">
          <div
            className={`px-3 py-1 rounded-md transition-all ${
              activeTab === 'vitals'
                ? 'bg-[var(--color-surface)] text-[var(--color-ink)] shadow-sm font-semibold'
                : 'hover:text-[var(--color-ink)]'
            }`}
          >
            Vitals
          </div>
          <div
            className={`px-3 py-1 rounded-md transition-all ${
              activeTab === 'config'
                ? 'bg-[var(--color-surface)] text-[var(--color-ink)] shadow-sm font-semibold'
                : 'hover:text-[var(--color-ink)]'
            }`}
          >
            Config Diff
          </div>
          <div
            className={`px-3 py-1 rounded-md transition-all ${
              activeTab === 'storage'
                ? 'bg-[var(--color-surface)] text-[var(--color-ink)] shadow-sm font-semibold'
                : 'hover:text-[var(--color-ink)]'
            }`}
          >
            Storage
          </div>
        </div>

        {/* Right Host Identifier */}
        <div className="flex items-center space-x-2 text-[12px] font-mono text-[var(--color-ink-tertiary)]">
          <span className="w-2 h-2 rounded-full bg-[var(--color-status-success)]" />
          <span>ubuntu-server-01</span>
        </div>
      </div>

      {/* Main Window Stage */}
      <div className="p-6 bg-[var(--color-surface)] flex-1 min-h-[380px] flex flex-col justify-center">
        {children}
      </div>
    </div>
  );
}
