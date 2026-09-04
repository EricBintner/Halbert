// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Promoted blocks, as task cards.
 *
 * A command that crosses PROMOTE_AFTER_SECONDS stops being a passing detail
 * and becomes a thing the machine is doing. The backend says so with
 * `terminal_block_promote`, which sets `isTaskCard` on the block — and until
 * this hook existed nothing read that flag, so the whole fast/slow
 * distinction ended at a boolean nobody looked at.
 *
 * Derived, never stored: the terminal store is the single source of what is
 * running, and a second list kept in step with it would only ever disagree.
 */

import { useMemo } from 'react';
import { useTerminalSessions, type TerminalSession } from './useTerminalSessions';
import type { StatusLightState } from '../components/agent/StatusLight';
import type { TaskCardData } from '../components/agent/TasksColumn';

export interface Tasks {
  running: TaskCardData[];
  finished: TaskCardData[];
}

/**
 * @param sessions every terminal session the page holds
 * @param threadTopic the current subject, shown under each card
 * @param now injected clock, for tests
 */
export function tasksFromSessions(
  sessions: TerminalSession[],
  threadTopic = '',
  now: number = Date.now(),
): Tasks {
  const running: TaskCardData[] = [];
  const finished: TaskCardData[] = [];

  for (const session of sessions) {
    for (const block of session.blocks ?? []) {
      // Only promoted blocks, and never the admin's own shell
      // (plan-b-contracts §12: "The admin's shell is never a task card").
      if (!block.isTaskCard || block.owner === 'user') continue;

      // A pool session is reused, so `session.command` describes whichever
      // block spawned it and not necessarily this one. The block's own label
      // is the truthful title whenever it has one.
      const title = block.label || session.command;
      const isDone = block.status === 'completed';
      const exitCode = isDone ? session.exitCode : null;

      let state: StatusLightState;
      if (block.status === 'needs_attention') state = 'needs_attention';
      else if (!isDone) state = 'running';
      // A non-zero exit is not a quiet completion. An unknown one is not an
      // error either — it is simply not yet known.
      else if (typeof exitCode === 'number' && exitCode !== 0) state = 'error';
      else state = 'done_unseen';

      const card: TaskCardData = {
        taskId: block.block_id,
        title,
        threadTopic,
        state,
        elapsedSeconds: Math.max(0, Math.round((now - session.startedAt) / 1000)),
        exitCode,
        blockId: block.block_id,
        // The jump target is the block, not the thread: every surface that
        // renders a block stamps `data-terminal-block`, in the live feed and
        // in the reloaded timeline alike.
        threadId: block.block_id,
        ...(isDone ? { finishedAt: session.startedAt } : {}),
      };
      (isDone ? finished : running).push(card);
    }
  }

  // Newest first: what the machine started most recently is what the reader
  // is most likely looking for.
  const newestFirst = (a: TaskCardData, b: TaskCardData) =>
    (b.elapsedSeconds ?? 0) - (a.elapsedSeconds ?? 0) === 0
      ? 0
      : (a.elapsedSeconds ?? 0) - (b.elapsedSeconds ?? 0);
  running.sort(newestFirst);
  finished.sort(newestFirst);
  return { running, finished };
}

/** Live tasks, recomputed whenever the terminal store changes. */
export function useTasks(threadTopic = ''): Tasks {
  const { sessions } = useTerminalSessions();
  return useMemo(
    () => tasksFromSessions(sessions, threadTopic),
    [sessions, threadTopic],
  );
}

export default useTasks;
