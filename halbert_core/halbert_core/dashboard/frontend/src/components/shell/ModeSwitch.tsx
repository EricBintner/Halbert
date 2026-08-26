// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ModeSwitch — one click between Halbert's two surfaces.
 *
 * Engaged is the machine you talk to; Browsing is the dashboard you inspect.
 * Both are always one keystroke away (Cmd/Ctrl+B), which is the point: the
 * dashboard was never removed, it stopped being the only thing on screen.
 */

import { MessageSquare, LayoutDashboard } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useShellMode, type ShellMode } from '@/contexts/ShellModeContext';

const MODES: Array<{ mode: ShellMode; label: string; icon: typeof MessageSquare }> = [
  { mode: 'engaged', label: 'Sovereign Host', icon: MessageSquare },
  { mode: 'browsing', label: 'Dashboard', icon: LayoutDashboard },
];

export function ModeSwitch() {
  const { mode, setMode } = useShellMode();
  const shortcut = typeof navigator !== 'undefined' && /Mac|iP(hone|ad)/.test(navigator.platform)
    ? '⌘B'
    : 'Ctrl+B';

  return (
    <div
      className="flex items-center gap-0.5 rounded-md border bg-muted/40 p-0.5"
      role="tablist"
      aria-label="Shell mode"
    >
      {MODES.map(({ mode: m, label, icon: Icon }) => (
        <button
          key={m}
          type="button"
          role="tab"
          aria-selected={mode === m}
          onClick={() => setMode(m)}
          title={`${label} (${shortcut})`}
          className={cn(
            'flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors',
            mode === m
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{label}</span>
        </button>
      ))}
      <span className="hidden lg:inline px-1.5 text-[10px] font-mono text-muted-foreground/70">
        {shortcut}
      </span>
    </div>
  );
}

export default ModeSwitch;
