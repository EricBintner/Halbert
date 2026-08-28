// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TasksColumn — right-column task list (replaces TerminalAccordionDock).
 *
 * Running tasks at top, finished tasks in a collapsible section, and a
 * "Your shell" region pinned at the bottom. Each task card shows a
 * StatusLight, the command title, the owning thread topic, and a jump
 * arrow to the timeline turn.
 *
 * See plan-b-contracts.md section 12.
 */

import { useState, type ReactNode } from 'react';
import { StatusLight, type StatusLightState } from './StatusLight';

export interface TaskCardData {
  taskId: string;
  title: string;
  threadTopic: string;
  state: StatusLightState;
  elapsedSeconds?: number;
  exitCode?: number | null;
  blockId?: string;
  threadId: string;
}

interface TaskCardProps extends TaskCardData {
  onJumpToTurn?: (turnId: string) => void;
  onStop?: (taskId: string) => void;
  onCopy?: (output: string) => void;
}

export function TaskCard({
  taskId,
  title,
  threadTopic,
  state,
  elapsedSeconds,
  exitCode,
  threadId,
  onJumpToTurn,
  onStop,
}: TaskCardProps): ReactNode {
  const isRunning = state === 'running' || state === 'needs_attention';
  return (
    <div
      className="rounded-lg border border-hairline bg-surface p-2 space-y-1"
      data-task-card={taskId}
      data-task-state={state}
    >
      <div className="flex items-center gap-2">
        <StatusLight state={state} elapsedSeconds={elapsedSeconds} exitCode={exitCode} size="sm" />
        <span className="font-mono text-xs text-text truncate flex-1" title={title}>
          {title}
        </span>
        {isRunning && onStop && (
          <button
            onClick={() => onStop(taskId)}
            className="text-[10px] text-muted-foreground hover:text-text border border-hairline rounded px-1"
            aria-label="Stop task"
          >
            stop
          </button>
        )}
        {onJumpToTurn && (
          <button
            onClick={() => onJumpToTurn(threadId)}
            className="text-[10px] text-muted-foreground hover:text-text"
            aria-label="Jump to turn"
            title="Jump to turn"
          >
            &#x2191;
          </button>
        )}
      </div>
      <div className="text-[10px] text-muted-foreground truncate" title={threadTopic}>
        {threadTopic}
      </div>
    </div>
  );
}

interface TasksColumnProps {
  runningTasks: TaskCardData[];
  finishedTasks: TaskCardData[];
  onJumpToTurn?: (turnId: string) => void;
  onStop?: (taskId: string) => void;
  onClear?: () => void;
  yourShell?: ReactNode;
}

export function TasksColumn({
  runningTasks,
  finishedTasks,
  onJumpToTurn,
  onStop,
  onClear,
  yourShell,
}: TasksColumnProps): ReactNode {
  const [finishedOpen, setFinishedOpen] = useState(false);

  return (
    <div
      role="complementary"
      aria-label="Tasks"
      className="flex flex-col gap-2 p-2"
      data-tasks-column
    >
      {/* Running section */}
      <div className="space-y-1">
        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          Running
        </div>
        {runningTasks.length === 0 ? (
          <div className="text-[10px] text-muted-foreground italic">Nothing running</div>
        ) : (
          runningTasks.map((task) => (
            <TaskCard
              key={task.taskId}
              {...task}
              onJumpToTurn={onJumpToTurn}
              onStop={onStop}
            />
          ))
        )}
      </div>

      {/* Finished section — collapsible */}
      {finishedTasks.length > 0 && (
        <details open={finishedOpen} onToggle={(e) => setFinishedOpen(e.currentTarget.open)}>
          <summary className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide cursor-pointer">
            Finished {finishedTasks.length} {finishedOpen ? '\u203A' : '\u2039'}
          </summary>
          {finishedOpen && (
            <div className="space-y-1 mt-1">
              {finishedTasks.map((task) => (
                <TaskCard
                  key={task.taskId}
                  {...task}
                  onJumpToTurn={onJumpToTurn}
                />
              ))}
            </div>
          )}
        </details>
      )}

      {/* Clear button */}
      {finishedTasks.length > 0 && onClear && (
        <button
          onClick={onClear}
          className="text-[10px] text-muted-foreground hover:text-text text-left"
        >
          Clear
        </button>
      )}

      {/* Your shell — pinned, separate region */}
      {yourShell && (
        <div className="border-t border-hairline pt-2 mt-2">
          {yourShell}
        </div>
      )}
    </div>
  );
}

export default TasksColumn;
