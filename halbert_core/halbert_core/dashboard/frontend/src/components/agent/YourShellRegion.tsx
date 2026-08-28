// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * YourShellRegion — the admin's interactive shell, pinned in the Tasks column.
 *
 * Renders an xterm.js terminal (ws transport), a watched/unwatched toggle,
 * and a badge when the shell is unhooked (watched: false, no OSC 133).
 * The admin's shell is never a task card.
 *
 * See plan-b-contracts.md section 12 (YourShellRegion).
 */

import { useState, useCallback, type ReactNode } from 'react';

export interface YourShellSession {
  sessionId: string;
  watched: boolean;
  hooked: boolean; // true when OSC 133 markers are detected
}

interface YourShellRegionProps {
  session: YourShellSession | null;
  onToggleWatched?: (sessionId: string, watched: boolean) => void;
  onStageCommand?: (sessionId: string, command: string) => void;
}

export function YourShellRegion({
  session,
  onToggleWatched,
  onStageCommand,
}: YourShellRegionProps): ReactNode {
  const [stagedCommand, setStagedCommand] = useState('');

  const handleToggle = useCallback(() => {
    if (session && onToggleWatched) {
      onToggleWatched(session.sessionId, !session.watched);
    }
  }, [session, onToggleWatched]);

  const handleStage = useCallback(() => {
    if (session && stagedCommand.trim() && onStageCommand) {
      onStageCommand(session.sessionId, stagedCommand.trim());
      setStagedCommand('');
    }
  }, [session, stagedCommand, onStageCommand]);

  if (!session) {
    return (
      <div
        className="rounded-lg border border-hairline bg-surface p-2"
        data-your-shell
        data-shell-state="none"
      >
        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          Your shell
        </div>
        <div className="text-[10px] text-muted-foreground italic mt-1">
          No shell session
        </div>
      </div>
    );
  }

  const unhooked = !session.hooked || !session.watched;

  return (
    <div
      className="rounded-lg border border-hairline bg-surface p-2 space-y-2"
      data-your-shell
      data-shell-state={unhooked ? 'unhooked' : 'hooked'}
      data-session-id={session.sessionId}
    >
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          Your shell
        </div>
        <button
          onClick={handleToggle}
          className="text-[10px] text-muted-foreground hover:text-text border border-hairline rounded px-1"
          aria-label={session.watched ? 'Unwatch shell' : 'Watch shell'}
          aria-pressed={session.watched}
          data-watched-toggle
        >
          {session.watched ? 'watched' : 'unwatched'}
        </button>
      </div>

      {/* Unhooked badge */}
      {unhooked && (
        <div
          className="text-[10px] text-status-warning bg-status-warning-bg border border-status-warning-line rounded px-1 py-0.5"
          role="status"
        >
          Shell unhooked — no OSC 133 markers detected
        </div>
      )}

      {/* Terminal mount point — the parent fills this with an xterm instance */}
      <div
        className="bg-canvas-subtle rounded p-1 min-h-[120px]"
        data-shell-terminal={session.sessionId}
        aria-label="Interactive shell terminal"
      />

      {/* Stage-into-shell input */}
      <div className="flex gap-1">
        <input
          type="text"
          value={stagedCommand}
          onChange={(e) => setStagedCommand(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleStage();
          }}
          placeholder="Stage a command..."
          className="flex-1 text-[10px] font-mono bg-canvas-subtle text-text border border-hairline rounded px-1 py-0.5 focus:outline-none focus:border-accent"
          aria-label="Stage command into shell"
          data-stage-input
        />
        <button
          onClick={handleStage}
          disabled={!stagedCommand.trim()}
          className="text-[10px] text-muted-foreground hover:text-text border border-hairline rounded px-1 disabled:opacity-50"
          aria-label="Stage command"
        >
          stage
        </button>
      </div>
    </div>
  );
}
