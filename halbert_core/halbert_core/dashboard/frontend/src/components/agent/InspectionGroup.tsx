// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * InspectionGroup — a run of read-only calls, as one line.
 *
 * Collapsed by default and expandable: the steps are still there for anyone
 * who wants them, they just stop being the loudest thing in the turn. What
 * qualifies, and what may never be folded, is in groupInspections.ts.
 */

import { useState, type ReactNode } from 'react';
import type { ToolExecution } from '../../hooks/useAgentStream';
import { ToolExecutionCard } from './ToolExecutionCard';

interface InspectionGroupProps {
  items: ToolExecution[];
}

/** "3 files · 2 memories" — what was looked at, not which functions ran. */
export function summarise(items: ToolExecution[]): string {
  let files = 0;
  let memories = 0;
  let commands = 0;
  let other = 0;
  for (const item of items) {
    if (item.tool === 'read_file' || item.tool === 'read_log_tail') files += 1;
    else if (item.tool === 'recall_memory' || item.tool === 'recall_thread') memories += 1;
    else if (item.tool === 'run_command') commands += 1;
    else other += 1;
  }
  const parts: string[] = [];
  const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;
  if (files) parts.push(plural(files, 'file'));
  if (memories) parts.push(plural(memories, 'memory').replace('memorys', 'memories'));
  if (commands) parts.push(plural(commands, 'command'));
  if (other) parts.push(plural(other, 'check'));
  return parts.join(' · ');
}

export function InspectionGroup({ items }: InspectionGroupProps): ReactNode {
  const [open, setOpen] = useState(false);

  return (
    <div data-inspection-group={items.length}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground rounded-full border border-hairline bg-canvas-subtle px-2 py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span>Looked at {summarise(items)}</span>
      </button>

      {open && (
        <div className="space-y-2 mt-1.5">
          {items.map((item) => (
            <ToolExecutionCard key={item.executionId} execution={item} />
          ))}
        </div>
      )}
    </div>
  );
}

export default InspectionGroup;
