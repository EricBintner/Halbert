// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AggregateStatusLight — one light for "is the machine doing anything".
 *
 * With the tasks column mounted, a long-running command is visible only while
 * the right column is open. This is how the machine says something is running
 * when you are not looking at it — the last row of TERM-1.
 *
 * It renders nothing when nothing is running. A permanent dim dot would be
 * furniture, and furniture trains the eye to stop seeing the spot it sits in.
 */

import { type ReactNode } from 'react';
import { StatusLight, type StatusLightState } from './StatusLight';
import type { TaskCardData } from './TasksColumn';

/**
 * The one state that stands for all of them, or null when none is live.
 *
 * `needs_attention` outranks `error`: both want the reader, but only one is
 * waiting on them *right now*. A finished task is not a state the top bar
 * reports — that is what the column is for.
 */
export function worstState(tasks: TaskCardData[]): StatusLightState | null {
  const live = tasks.filter(
    (t) => t.state === 'running' || t.state === 'needs_attention' || t.state === 'error',
  );
  if (live.length === 0) return null;
  if (live.some((t) => t.state === 'needs_attention')) return 'needs_attention';
  if (live.some((t) => t.state === 'error')) return 'error';
  return 'running';
}

const LABEL: Record<string, string> = {
  running: 'running',
  needs_attention: 'waiting for you',
  error: 'failed',
};

interface AggregateStatusLightProps {
  tasks: TaskCardData[];
  onClick?: () => void;
}

export function AggregateStatusLight({ tasks, onClick }: AggregateStatusLightProps): ReactNode {
  const state = worstState(tasks);
  if (state === null) return null;

  const live = tasks.filter(
    (t) => t.state === 'running' || t.state === 'needs_attention' || t.state === 'error',
  );
  const count = live.length;

  const body = (
    <>
      <StatusLight state={state} size="sm" />
      {/* A count only where one light stands for several. "1" beside a single
          light is noise: the light already says there is one. */}
      {count > 1 && (
        <span className="text-[10px] font-mono text-muted-foreground">{count}</span>
      )}
    </>
  );

  const label = `${count} task${count === 1 ? '' : 's'} ${LABEL[state] ?? state}`;

  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      data-aggregate-status
      className="flex items-center gap-1 rounded px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      {body}
    </button>
  ) : (
    <span
      aria-label={label}
      role="status"
      data-aggregate-status
      className="flex items-center gap-1 px-1"
    >
      {body}
    </span>
  );
}

export default AggregateStatusLight;
