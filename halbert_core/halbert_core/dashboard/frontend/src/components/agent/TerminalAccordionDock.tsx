/**
 * TerminalAccordionDock — right-column accordion of all terminal sessions (E1c).
 *
 * Lists every session from the singleton store. Each row is a collapsible
 * accordion: collapsed shows a compact summary (status dot, command, PID,
 * exit code); expanded mounts a live TerminalTile for full PTY interactivity.
 * Expanding a row marks it visible (live xterm); the store caps visible
 * sessions at 3 and demotes the oldest. A "jump to origin" button scrolls
 * the conversation back to where the inline tile was (wired by the parent).
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
}

const STATUS_DOT: Record<string, string> = {
  running: 'bg-emerald-400',
  done: 'bg-slate-400',
  idle: 'bg-amber-400',
};

function RowSummary({ session }: { session: TerminalSession }) {
  const dot = STATUS_DOT[session.status] ?? STATUS_DOT.idle;
  const exitInfo = session.status === 'done' ? ` · exit ${session.exitCode ?? '?'}` : '';
  return (
    <div className="flex items-center gap-2 min-w-0 text-xs">
      <span className={`h-2 w-2 rounded-full shrink-0 ${dot}`} />
      <span className="text-slate-400 font-mono truncate flex-1" title={session.command}>
        $ {session.command}
      </span>
      <span className="text-slate-600 font-mono shrink-0">pid {session.pid}{exitInfo}</span>
    </div>
  );
}

export function TerminalAccordionDock({
  onJumpTo,
  onTerminated,
  title = 'Terminals',
}: TerminalAccordionDockProps) {
  const { sessions, setVisible } = useTerminalSessions();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        setVisible(id, false);
      } else {
        next.add(id);
        setVisible(id, true);
      }
      return next;
    });
  };

  if (sessions.length === 0) {
    return null; // no dock when there are no sessions
  }

  return (
    <div className="border-t border-slate-700/60 bg-slate-900/40">
      {/* Dock header */}
      <div className="flex items-center justify-between px-3 py-1.5 text-xs text-slate-400">
        <span className="font-semibold uppercase tracking-wide">{title}</span>
        <span className="text-slate-600">{sessions.length}</span>
      </div>

      {/* Session rows */}
      <div className="divide-y divide-slate-800/60">
        {sessions.map((s) => {
          const isOpen = expanded.has(s.id);
          return (
            <div key={s.id}>
              {/* Collapsed header */}
              <div className="flex items-center gap-1 px-3 py-1.5 hover:bg-slate-800/40 cursor-pointer" onClick={() => toggle(s.id)}>
                <span className="text-slate-500 text-[10px] w-3">{isOpen ? '▼' : '▶'}</span>
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
                    className="px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400 hover:text-slate-200 text-[10px] shrink-0"
                  >
                    ⤴
                  </button>
                )}
              </div>

              {/* Expanded: live TerminalTile */}
              {isOpen && (
                <div className="px-2 pb-2">
                  <TerminalTile session={s} onTerminated={onTerminated} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}