// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PanelToggle — the top-bar panel visibility control.
 *
 * Two buttons that toggle the center (dashboard/page) and right (conversation)
 * panels independently. Replaces the old ModeSwitch which flipped between
 * mutually-exclusive engaged/browsing modes.
 *
 *   [Dashboard]  toggles the center panel (Cmd+D)
 *   [Halbert]    toggles the right panel  (Cmd+J)
 *
 * Cmd+B still flips between the two focus states (center-only <-> right-only).
 */
import { LayoutDashboard, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useShellMode } from '@/contexts/ShellModeContext';
import { useHostIdentity } from '@/hooks/useHostIdentity';

const NAME_POLL_MS = 60_000;
const MAX_LABEL_CH = 18;

export function PanelToggle() {
  const { centerVisible, rightVisible, toggleCenter, toggleRight } = useShellMode();
  const { identity } = useHostIdentity(NAME_POLL_MS);

  const hostLabel = identity?.display_name || 'Halbert';

  return (
    <div
      className="flex items-center gap-0.5 rounded-md border bg-muted/40 p-0.5"
      role="toolbar"
      aria-label="Panel visibility"
    >
      {/* Center panel toggle (Dashboard / page) */}
      <button
        type="button"
        onClick={toggleCenter}
        title={`Toggle dashboard panel (Cmd+D)`}
        aria-pressed={centerVisible}
        className={cn(
          'flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors',
          centerVisible
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <LayoutDashboard className="h-3.5 w-3.5 shrink-0" />
        <span className="hidden sm:inline">Dashboard</span>
      </button>

      {/* Right panel toggle (Conversation / Halbert) */}
      <button
        type="button"
        onClick={toggleRight}
        title={`Toggle conversation panel (Cmd+J)`}
        aria-pressed={rightVisible}
        className={cn(
          'flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors',
          rightVisible
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <MessageSquare className="h-3.5 w-3.5 shrink-0" />
        <span
          className="hidden sm:inline truncate"
          style={{ maxWidth: `${MAX_LABEL_CH}ch` }}
        >
          {hostLabel}
        </span>
      </button>
    </div>
  );
}

export default PanelToggle;
