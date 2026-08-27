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

import { memo, useCallback, useState } from 'react';
import { useTerminalSessions } from '../../hooks/useTerminalSessions';
import type { ToolExecution } from '../../hooks/useAgentStream';
import type { TimelineDay } from '../../hooks/useTimeline';
import type { TimelineToolBlock, TimelineTurn } from '../../types/timeline';
import { api } from '../../lib/api';
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
 * A stored tool block (spec §8 messages.blocks_json / state_machine.py
 * _tool_block) in the shape the card renders.
 *
 * The row carries two verdicts that can disagree, so the order they are read
 * in decides what an admin is told. A REAL EXIT CODE WINS FIRST. A
 * `run_command` that exits non-zero is not an error to the executor: it
 * returns the exit line as ordinary output (`f"Exit code {returncode}\n…"`,
 * tools/executor.py:513) instead of raising, so the call is wrapped
 * `ExecutionResult(success=True, …)` (executor.py:369-374) and stored
 * `status: "success"` (state_machine.py:1853) while `_tool_block`
 * (state_machine.py:615-638) parses the real code back out — the persisted
 * block is `{status: "success", exit: 1}`. Letting the status win there
 * would paint a green ✓ Success on a `systemctl restart sshd` that exited 1,
 * which is the common case, not an edge one. `_tool_block` only ever writes
 * `exit: 0` when the status is already "success", so the two signals cannot
 * contradict each other the other way round.
 *
 * With no exit code stored, the backend's own verdict decides, and anything
 * that is not "success" is a failed card — not just the values this file
 * happens to know. `exit` is only ever set for `run_command`, so a failed
 * non-run_command tool, or a call superseded before it ran (~line 446,
 * `{exit: null, status: "superseded"}`), would otherwise render green. The
 * status vocabulary is wider than success/error/superseded: a ToolCall is
 * created `pending` (states.py:97, state_machine.py:1221) and `_end_turn`
 * (state_machine.py:660) persists every call regardless of status, so a turn
 * interrupted between dispatch and completion stores `{status: "pending",
 * exit: null}`. A stored transcript must never tell an admin a command
 * succeeded when it never ran.
 *
 * Only an older, pre-status row with no exit code at all reaches the last
 * default, where unknown reads as success.
 */
export function executionFromBlock(block: TimelineToolBlock, fallbackId: string): ToolExecution {
  const exit = block.exit;
  let status: ToolExecution['status'];
  if (typeof exit === 'number') {
    status = exit === 0 ? 'success' : 'error';
  } else if (block.status) {
    status = block.status === 'success' ? 'success' : 'error';
  } else {
    status = 'success';
  }
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

/** What a forgotten row reads as — the same marker the server stores. */
export const REDACTED = '[redacted by admin]';

/** Stored rows have server ids; a turn appended live carries -1 until the next load. */
export function redactableIds(turn: TimelineTurn): number[] {
  return [turn.user?.messageId, turn.assistant?.messageId].filter(
    (id): id is number => typeof id === 'number' && id >= 0,
  );
}

interface TurnArticleProps {
  turn: TimelineTurn;
  /** True once "Forget this" went through: the words and the blocks are the marker. */
  forgotten: boolean;
  onForget?: (turn: TimelineTurn) => void;
  onRunCommand?: RunCommand;
}

/**
 * memo: a stored turn is immutable, so it should only re-render when the
 * turn object itself changes (or when it is forgotten). Callers should pass a
 * stable `onRunCommand` and `onForget` (useCallback) or the memo buys nothing.
 */
const TurnArticle = memo(function TurnArticle({ turn, forgotten, onForget, onRunCommand }: TurnArticleProps) {
  // Redaction replaces content and blocks_json (spec §5); the terminal ids
  // are not part of it, so the "ended" chips stay.
  const blocks = forgotten ? [] : turn.blocks;
  const diffs = forgotten ? [] : turn.diffProposals;
  const hasAssistantSide =
    turn.assistant !== null ||
    blocks.length > 0 ||
    turn.terminalBlockIds.length > 0 ||
    diffs.length > 0;
  const label = forgotten ? REDACTED : turn.user ? turn.user.content.slice(0, 80) : turn.origin;
  const canForget = !forgotten && onForget !== undefined && redactableIds(turn).length > 0;

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
            <p className="text-sm whitespace-pre-wrap break-words">{forgotten ? REDACTED : turn.user.content}</p>
          </div>
        </div>
      )}

      {turn.user?.status === 'interrupted' && (
        <p className="text-center text-[11px] font-mono text-ink-tertiary">(Halbert restarted here)</p>
      )}

      {hasAssistantSide && (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
            {blocks.map((block, i) => (
              <ToolExecutionCard
                key={block.executionId ?? `${turn.turnId}-block-${i}`}
                execution={executionFromBlock(block, `${turn.turnId}-block-${i}`)}
              />
            ))}

            {turn.terminalBlockIds.length > 0 && <TurnTerminals ids={turn.terminalBlockIds} />}

            {diffs.map((diff) => (
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
                {forgotten ? (
                  <p className="font-mono text-ink-tertiary">{REDACTED}</p>
                ) : (
                  <MessageContent content={turn.assistant.content} onRunCommand={onRunCommand} />
                )}
              </div>
            )}

            {turn.assistant?.status === 'cancelled' && (
              <p className="text-[11px] font-mono text-ink-tertiary">cancelled</p>
            )}
          </div>
        </div>
      )}

      {canForget && (
        <div className="flex justify-end">
          <button
            type="button"
            aria-label="Forget this turn"
            title="Replace this turn's words and tool output with a redaction marker, everywhere it is stored"
            onClick={() => onForget?.(turn)}
            className="rounded px-1 text-[11px] font-mono text-ink-tertiary hover:text-ink-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Forget this
          </button>
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
  const [forgotten, setForgotten] = useState<ReadonlySet<string>>(() => new Set());

  // "Forget this": both stored rows are redacted server-side first; the
  // article shows the marker once the server has agreed, never before, so
  // the page never claims something is forgotten that is still on disk.
  const handleForget = useCallback(async (turn: TimelineTurn) => {
    try {
      await Promise.all(redactableIds(turn).map((id) => api.redactMessage(id)));
      setForgotten((prev) => new Set(prev).add(turn.turnId));
    } catch (err) {
      console.warn('[TIMELINE] forget failed; the turn is unchanged:', err);
    }
  }, []);

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
            <TurnArticle
              key={turn.turnId}
              turn={turn}
              forgotten={forgotten.has(turn.turnId)}
              onForget={handleForget}
              onRunCommand={onRunCommand}
            />
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
