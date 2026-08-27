// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Timeline — the stored conversation, oldest first, grouped by day.
 *
 * Every turn here is a record: the user's words, the reply, tool calls as
 * static cards (status read from the stored exit code), terminals as live
 * tiles while the store still has them and as an "ended" chip when it does
 * not, and diffs read-only. Nothing in a past turn can act on a session that
 * no longer exists.
 *
 * The turn in flight is NOT rendered here — AgentChat keeps its live block
 * and appends the finished turn through useTimeline.appendLive.
 *
 * Markup, per the design: a `role="feed"` container that is `aria-busy`
 * while paging, `<header><h2>{day}</h2><time datetime></header>` dividers,
 * and one `role="article"` per turn.
 */

import { memo } from 'react';
import { useTerminalSessions } from '../../hooks/useTerminalSessions';
import type { ToolExecution } from '../../hooks/useAgentStream';
import type { TimelineDay } from '../../hooks/useTimeline';
import type { TimelineToolBlock, TimelineTurn } from '../../types/timeline';
import { ToolExecutionCard } from './ToolExecutionCard';
import { DiffBlock } from './DiffBlock';
import { InlineTerminals } from './InlineTerminals';
import { StaticTerminalChip } from './StaticTerminalChip';
import { MessageContent, type RunCommand } from './MessageContent';

interface TimelineProps {
  byDay: TimelineDay[];
  hasMore: boolean;
  loading: boolean;
  /** True while the page is a window around an earlier turn (a chip jump). */
  anchored?: boolean;
  onLoadOlder: () => void;
  /** Back to the newest page; rendered as a control only while `anchored`. */
  onLoadLatest?: () => void;
  onRunCommand?: RunCommand;
}

/**
 * A stored tool block in the shape the card renders. `block.status` is the
 * backend's own verdict (spec §8 messages.blocks_json / state_machine.py
 * _tool_block) and is authoritative WHENEVER IT IS PRESENT — not just for
 * the values this file happens to know. `exit` is only ever set for
 * `run_command` (state_machine.py:614-638), so a failed non-run_command
 * tool, or a call superseded before it ran (~line 446, `{exit: null, status:
 * "superseded"}`), would otherwise render as a green "success" card under
 * the exit-only heuristic. The backend's status vocabulary is wider than
 * success/error/superseded: a ToolCall is created `pending` (states.py:97,
 * state_machine.py:1221) and `_end_turn` (state_machine.py:660) persists
 * every call regardless of status, so a turn interrupted between dispatch
 * and completion stores `{status: "pending", exit: null}`. Anything that is
 * not the backend saying "success" is therefore rendered as a failed card:
 * a stored transcript must never tell an admin a command succeeded when it
 * never ran. Only when the backend sent no status at all (older, pre-status
 * rows) does this fall back to the exit heuristic: exit 0 or unknown reads
 * as success.
 */
export function executionFromBlock(block: TimelineToolBlock, fallbackId: string): ToolExecution {
  const exit = block.exit;
  const status: ToolExecution['status'] = block.status
    ? (block.status === 'success' ? 'success' : 'error')
    : exit == null || exit === 0 ? 'success' : 'error';
  return {
    executionId: block.executionId ?? fallbackId,
    tool: block.tool,
    args: block.args ?? {},
    status,
    result: block.result,
    error: block.error,
  };
}

/**
 * The terminal slot of one stored turn — and the ONLY thing in the timeline
 * that subscribes to the live terminal store.
 *
 * TerminalSessionStore.emit() fires on every output chunk (appendOutput and
 * the ws stdout handler), so a subscription at the top of Timeline would
 * re-render every day section, every turn, every tool card and every diff
 * (which re-splits both file contents line by line) once per byte of an
 * `apt upgrade`. Subscribing here means a chunk re-renders only the turns
 * that actually own a terminal.
 */
function TurnTerminals({ ids }: { ids: string[] }) {
  const { sessions } = useTerminalSessions();
  const liveIds = new Set(sessions.map((s) => s.id));
  const live = ids.filter((id) => liveIds.has(id));
  const ended = ids.filter((id) => !liveIds.has(id));

  return (
    <>
      {live.length > 0 && <InlineTerminals sessionIds={live} />}

      {ended.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {ended.map((id) => (
            <StaticTerminalChip key={id} id={id} />
          ))}
        </div>
      )}
    </>
  );
}

interface TurnArticleProps {
  turn: TimelineTurn;
  onRunCommand?: RunCommand;
}

/**
 * memo: a stored turn is immutable, so it should only re-render when the
 * turn object itself changes. Callers should pass a stable `onRunCommand`
 * (useCallback) or the memo buys nothing.
 */
const TurnArticle = memo(function TurnArticle({ turn, onRunCommand }: TurnArticleProps) {
  const hasAssistantSide =
    turn.assistant !== null ||
    turn.blocks.length > 0 ||
    turn.terminalBlockIds.length > 0 ||
    turn.diffProposals.length > 0;
  const label = turn.user ? turn.user.content.slice(0, 80) : turn.origin;

  return (
    <article
      role="article"
      aria-label={label}
      data-turn-id={turn.turnId}
      data-thread-id={turn.threadId}
      className="space-y-3"
    >
      {turn.user && (
        <div className="flex justify-end">
          <div className="max-w-[80%] bg-primary text-primary-foreground px-4 py-2 rounded-lg">
            <p className="text-sm whitespace-pre-wrap break-words">{turn.user.content}</p>
          </div>
        </div>
      )}

      {turn.user?.status === 'interrupted' && (
        <p className="text-center text-[11px] font-mono text-ink-tertiary">(Halbert restarted here)</p>
      )}

      {hasAssistantSide && (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
            {turn.blocks.map((block, i) => (
              <ToolExecutionCard
                key={block.executionId ?? `${turn.turnId}-block-${i}`}
                execution={executionFromBlock(block, `${turn.turnId}-block-${i}`)}
              />
            ))}

            {turn.terminalBlockIds.length > 0 && <TurnTerminals ids={turn.terminalBlockIds} />}

            {turn.diffProposals.map((diff) => (
              <DiffBlock
                key={diff.id}
                filePath={diff.filePath}
                oldContent={diff.oldContent}
                newContent={diff.newContent}
                additions={diff.additions}
                deletions={diff.deletions}
                status={diff.status}
                readOnly
                onApply={() => {}}
                onReject={() => {}}
              />
            ))}

            {turn.assistant && (
              <div className="text-sm text-foreground">
                <MessageContent content={turn.assistant.content} onRunCommand={onRunCommand} />
              </div>
            )}

            {turn.assistant?.status === 'cancelled' && (
              <p className="text-[11px] font-mono text-ink-tertiary">cancelled</p>
            )}
          </div>
        </div>
      )}
    </article>
  );
});

export function Timeline({
  byDay,
  hasMore,
  loading,
  anchored = false,
  onLoadOlder,
  onLoadLatest,
  onRunCommand,
}: TimelineProps) {
  if (byDay.length === 0 && !hasMore) return null;

  return (
    <div role="feed" aria-label="Conversation" aria-busy={loading} className="space-y-2">
      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={onLoadOlder}
            disabled={loading}
            className="rounded-full border border-hairline bg-canvas-subtle px-3 py-1 text-[11px] font-mono text-ink-secondary hover:bg-canvas-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {loading ? 'Loading…' : 'Load earlier'}
          </button>
        </div>
      )}

      {byDay.map((day) => (
        <section key={day.dayKey} aria-label={day.label} className="space-y-4">
          <header className="thread-divider flex items-center gap-3 pt-2">
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
            <h2 className="text-[11px] font-mono uppercase tracking-label text-ink-tertiary">{day.label}</h2>
            <time dateTime={day.dayKey} className="sr-only">{day.dayKey}</time>
            <span className="h-px flex-1 bg-hairline" aria-hidden="true" />
          </header>
          {day.turns.map((turn) => (
            <TurnArticle key={turn.turnId} turn={turn} onRunCommand={onRunCommand} />
          ))}
        </section>
      ))}

      {/* A chip jump replaced the page with an earlier window; the turns
          between that window and now are not on screen, so say so and offer
          the way back rather than letting the live turn append after a gap. */}
      {anchored && onLoadLatest && (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={onLoadLatest}
            disabled={loading}
            className="rounded-full border border-hairline bg-canvas-subtle px-3 py-1 text-[11px] font-mono text-ink-secondary hover:bg-canvas-muted disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Back to latest
          </button>
        </div>
      )}
    </div>
  );
}

export default Timeline;
