// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StatusStrip — what is happening right now, on a layer that keeps nothing.
 *
 * The one idea worth lifting from open-claude-code is not a widget: it is
 * that progress and transcript have different lifetimes. Its REPL writes tool
 * progress to stderr and transcript content to stdout, and in a terminal that
 * is a real distinction — the progress scrolls past and is gone, the
 * transcript is what you scroll back through.
 *
 * Halbert rendered both in one layer, which is why a 200ms read left a
 * bordered box in the conversation forever. This strip is the ephemeral
 * layer, and it is what makes "quiet" honest: a fast call is never hidden
 * while it happens, it simply does not earn a permanent row afterwards.
 *
 * It renders nothing when nothing is running. A persistent empty bar would
 * be furniture, and furniture is the thing this exists to remove.
 */

import { type ReactNode } from 'react';
import type { ToolExecution } from '../../hooks/useAgentStream';

/** Plain language for what a call is doing, or the tool's own name. */
export function describeExecution(exec: ToolExecution): string {
  const args = (exec.args ?? {}) as Record<string, unknown>;
  const str = (key: string) => (typeof args[key] === 'string' ? (args[key] as string) : '');

  switch (exec.tool) {
    case 'run_command':
      return str('command') || exec.tool;
    case 'read_file':
      return `Reading ${str('path')}`.trim();
    case 'read_log_tail':
      return `Reading ${str('path') || 'the log'}`.trim();
    case 'list_directory':
      return `Listing ${str('path')}`.trim();
    case 'recall_memory':
    case 'recall_thread':
      return 'Remembering';
    case 'web_search':
      return `Searching for ${str('query')}`.trim();
    case 'write_file':
      return `Writing ${str('path')}`.trim();
    default:
      // A verb this does not know would be a label that is wrong rather than
      // plain. The tool's own name is at least true.
      return exec.tool;
  }
}

interface StatusStripProps {
  executions: ToolExecution[];
}

export function StatusStrip({ executions }: StatusStripProps): ReactNode {
  const inFlight = executions.filter((e) => e.status === 'running');
  if (inFlight.length === 0) return null;

  // The newest: it is what the machine turned its attention to last.
  const current = inFlight[inFlight.length - 1];
  const others = inFlight.length - 1;

  return (
    <div
      role="status"
      aria-live="polite"
      data-status-strip
      className="flex items-center gap-2 px-2 py-1 text-[11px] font-mono text-muted-foreground"
    >
      <span className="text-status-telemetry animate-pulse" aria-hidden="true">
        ⟳
      </span>
      <span className="truncate">{describeExecution(current)}</span>
      {others > 0 && <span className="shrink-0 text-ink-tertiary">+{others} more</span>}
    </div>
  );
}

export default StatusStrip;
