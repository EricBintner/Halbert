// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ModeSwitch — one click between Halbert's two surfaces.
 *
 * The first tab is named after the machine itself, using the name chosen in
 * onboarding ("What should I call this computer?"). That is the product's
 * whole thesis in a label: you are not switching to a feature, you are
 * switching to the computer. The second tab is the dashboard, which was never
 * removed — it simply stopped being the only thing on screen.
 *
 * Both are always one keystroke away (Cmd/Ctrl+B).
 */

import { MessageSquare, LayoutDashboard } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useShellMode } from '@/contexts/ShellModeContext';
import { useHostIdentity } from '@/hooks/useHostIdentity';

// The switch only needs the machine's name, which effectively never changes.
// Asking for a slow refresh keeps browsing mode — where the vitals panel is
// unmounted — from polling identity every few seconds.
const NAME_POLL_MS = 60_000;

// Long enough for "Erics-Mac-Studio", short enough not to crowd the top bar.
// Overflow is ellipsised by CSS and the full name stays in the tooltip.
const MAX_LABEL_CH = 22;

export function ModeSwitch() {
  const { mode, setMode } = useShellMode();
  const { identity } = useHostIdentity(NAME_POLL_MS);

  const shortcut =
    typeof navigator !== 'undefined' && /Mac|iP(hone|ad)/.test(navigator.platform)
      ? '⌘B'
      : 'Ctrl+B';

  // Before identity resolves the tab still has to say something; the app name
  // is the same fallback the backend uses when onboarding never ran.
  const hostLabel = identity?.display_name || 'Halbert';

  const modes = [
    { mode: 'engaged' as const, label: hostLabel, icon: MessageSquare },
    { mode: 'browsing' as const, label: 'Dashboard', icon: LayoutDashboard },
  ];

  return (
    <div
      className="flex items-center gap-0.5 rounded-md border bg-muted/40 p-0.5"
      role="tablist"
      aria-label="Shell mode"
    >
      {modes.map(({ mode: m, label, icon: Icon }) => (
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
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span
            className="hidden sm:inline truncate"
            style={{ maxWidth: `${MAX_LABEL_CH}ch` }}
          >
            {label}
          </span>
        </button>
      ))}
      <span className="hidden lg:inline px-1.5 text-[10px] font-mono text-muted-foreground/70">
        {shortcut}
      </span>
    </div>
  );
}

export default ModeSwitch;
