// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TerminalAccordionDock — right-column accordion of all terminal sessions (E1c).
 *
 * Lists every session from the singleton store. Each row is a collapsible
 * accordion: collapsed shows a compact summary (status dot, command, PID,
 * exit code); expanded mounts a live TerminalTile for full PTY interactivity.
 * Expanding a row marks it visible (live xterm); the store caps visible
 * sessions at 3 and demotes the oldest, and only visible rows mount an xterm
 * so the cap is real rather than advisory.
 *
 * With no sessions the dock does NOT disappear. An empty dock that says the
 * nervous system is live — and offers a shell — is the difference between
 * "the feature isn't there" and "nothing is running right now".
 *
 * Sits below the ContextBar in the right column; coexists with it.
 */

import { useState } from 'react';
import { useTerminalSessions, type TerminalSession } from '../../hooks/useTerminalSessions';
import { TerminalTile } from './TerminalTile';

interface TerminalAccordionDockProps {
  /** Scroll the conversation back to this session's inline origin. */
  onJumpTo?: (sessionId: string) => void;
  /** Called when a session is terminated from within a tile. */
  onTerminated?: (sessionId: string) => void;
  /** Optional title for the dock header (defaults to "Terminals"). */
  title?: string;
  /** Hide the idle state's shell launcher (e.g. inside the conversation). */
  hideLauncher?: boolean;
}

const STATUS_DOT: Record<string, string> = {
  running: 'bg-success',
  done: 'bg-muted',
  idle: 'bg-warning',
};

// An interactive login shell. /bin/sh -c runs it, so $SHELL is expanded by the
// child; the fallback keeps this working on hosts with no $SHELL exported.
const NEW_SHELL_COMMAND = 'exec "${SHELL:-/bin/bash}" -i';

function RowSummary({ session }: { session: TerminalSession }) {
  const dot = STATUS_DOT[session.status] ?? STATUS_DOT.idle;
  const exitInfo = session.status === 'done' ? ` · exit ${session.exitCode ?? '?'}` : '';
  return (
    <div className="flex items-center gap-2 min-w-0 text-xs">
      <span className={`h-2 w-2 rounded-full shrink-0 ${dot}`} />
      <span className="text-foreground font-mono truncate flex-1" title={session.command}>
        $ {session.command}
      </span>
      <span className="text-muted-foreground font-mono shrink-0">pid {session.pid}{exitInfo}</span>
    </div>
  );
}

export function TerminalAccordionDock({
  onJumpTo,
  onTerminated,
  title = 'Terminals',
  hideLauncher = false,
}: TerminalAccordionDockProps) {
  const { sessions, setVisible, spawn } = useTerminalSessions();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  const toggle = (id: string) => {
    // The store write happens here, not inside the updater: a useState
    // updater must be pure (StrictMode calls it twice).
    const willOpen = !expanded.has(id);
    setVisible(id, willOpen);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (willOpen) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const launchShell = async () => {
    setLaunching(true);
    setLaunchError(null);
    try {
      await spawn(NEW_SHELL_COMMAND);
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : String(err));
    } finally {
      setLaunching(false);
    }
  };

  const runningCount = sessions.filter((s) => s.status === 'running').length;

  return (
    <div className="border-t border-border bg-background/70">
      {/* Dock header */}
      <div className="flex items-center justify-between px-3 py-1.5 text-xs text-foreground">
        <span className="font-semibold uppercase tracking-wide">{title}</span>
        <span className="text-muted-foreground font-mono">
          {sessions.length === 0 ? 'idle' : `${runningCount}/${sessions.length} running`}
        </span>
      </div>

      {/* Idle: the nervous system is up, nothing is running on it yet. */}
      {sessions.length === 0 ? (
        <div className="px-3 pb-3 space-y-2">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-muted" />
            <span>No terminals running. PTY bridge ready.</span>
          </div>
          {!hideLauncher && (
            <button
              type="button"
              onClick={launchShell}
              disabled={launching}
              className="w-full rounded border border-dashed border-border px-2 py-1.5 text-[11px] font-mono text-foreground hover:border-border hover:text-foreground disabled:opacity-50 transition-colors"
            >
              {launching ? 'Opening shell…' : '+ New Terminal'}
            </button>
          )}
          {launchError && (
            <p className="text-[10px] text-error font-mono break-words">{launchError}</p>
          )}
        </div>
      ) : (
        <div className="divide-y divide-border/70">
          {sessions.map((s) => {
            const isOpen = expanded.has(s.id);
            return (
              <div key={s.id}>
                {/* Collapsed header */}
                <div className="flex items-center gap-1 px-3 py-1.5 hover:bg-muted/50 cursor-pointer" onClick={() => toggle(s.id)}>
                  <span className="text-muted-foreground text-[10px] w-3">{isOpen ? '▼' : '▶'}</span>
                  <div className="flex-1 min-w-0">
                    <RowSummary session={s} />
                  </div>
                  {onJumpTo && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onJumpTo(s.id);
                      }}
                      title="Jump to origin in conversation"
                      className="px-1.5 py-0.5 rounded bg-muted text-foreground hover:text-foreground text-[10px] shrink-0"
                    >
                      ⤴
                    </button>
                  )}
                </div>

                {/* Expanded: live TerminalTile — but only for sessions the
                    store actually promoted to visible, so MAX_VISIBLE really
                    caps the number of live xterm instances. */}
                {isOpen && (
                  <div className="px-2 pb-2">
                    {s.visible ? (
                      <TerminalTile session={s} onTerminated={onTerminated} />
                    ) : (
                      <div className="rounded border border-border bg-background px-2 py-3 text-[11px] text-muted-foreground">
                        Held headless — too many live terminals. Collapse another
                        to bring this one back on screen; its output is still
                        being buffered.
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
