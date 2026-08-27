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

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTerminalSessions } from '../../hooks/useTerminalSessions';
import type { ToolExecution } from '../../hooks/useAgentStream';
import type { TimelineDay } from '../../hooks/useTimeline';
import type { TimelineToolBlock, TimelineTurn } from '../../types/timeline';
import { api } from '../../lib/api';
import { announce } from '../../lib/announce';
import { ToolExecutionCard } from './ToolExecutionCard';
import { DiffBlock } from './DiffBlock';
import { InlineTerminals } from './InlineTerminals';
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
 *
 * A redacted block never reaches any of this: `isRedactedBlock` answers it at
 * the render site first. The marker the store leaves behind for a forgotten
 * row carries neither an exit code nor a status, so it would land on that
 * same default and paint a green ✓ Success on a turn an admin asked to
 * forget — the one thing this whole ordering exists to prevent.
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
 *
 * What a turn's terminals render AS — a live tile for an id the store still
 * has, a "terminal · ended" chip for one it does not, in the turn's own
 * order — is InlineTerminals' call and its call alone; it is the same
 * component AgentChat uses for the turn in flight, so a turn has exactly one
 * rendering of that logic regardless of which page put it there.
 */
function TurnTerminals({ ids }: { ids: string[] }) {
  useTerminalSessions();
  return <InlineTerminals sessionIds={ids} />;
}

/** What a forgotten row reads as — the same marker the server stores. */
export const REDACTED = '[redacted by admin]';

/**
 * What a refused redaction reads as. One sentence per outcome, said in BOTH
 * channels: spoken through the assertive live region and printed in the row
 * that held the question.
 *
 * The live region is `sr-only` (LiveRegion.tsx), and a refusal leaves the
 * words exactly as they were, so to a sighted admin a total refusal was
 * indistinguishable from a mis-click — and a half-landed one showed the
 * marker over the user's words while the reply beside it stayed readable,
 * with nothing on screen saying why. A privacy promise that did not land is
 * the last thing that may be reported invisibly.
 */
export const FORGET_FAILED = 'Could not forget that turn';
export const FORGET_PARTLY_FAILED = 'Part of that turn could not be forgotten';

/**
 * What the store leaves in `blocks_json` for a forgotten row that had tool
 * calls: one marker block (conversation_sqlite.redact_message). Rendering
 * this on click is what makes the turn an admin just forgot and the turn the
 * next page load hands back identical — the reload gets this exact block.
 */
const REDACTED_BLOCK: TimelineToolBlock = {
  tool: REDACTED,
  args: {},
  result: REDACTED,
  exit: null,
  redacted: true,
};

/** Stored rows have server ids; a turn appended live carries -1 until the next load. */
export function redactableIds(turn: TimelineTurn): number[] {
  return [turn.user?.messageId, turn.assistant?.messageId].filter(
    (id): id is number => typeof id === 'number' && id >= 0,
  );
}

/**
 * A block the store has scrubbed. It must be answered before
 * `executionFromBlock`: the marker carries no exit code and no status, so
 * that function's last default would call it a success and paint a green ✓
 * on a tool call whose name and output are the redaction marker.
 */
function isRedactedBlock(block: TimelineToolBlock): boolean {
  return block.redacted === true;
}

/** A forgotten tool call: something ran here, and its record is gone. */
function RedactedToolCard() {
  return (
    <div className="rounded-lg border border-hairline bg-canvas-subtle overflow-hidden">
      <div className="flex items-center gap-2 p-2">
        <span className="text-ink-tertiary text-sm" aria-hidden="true">▪</span>
        <div>
          <div className="font-mono text-ink-secondary text-xs">{REDACTED}</div>
          <div className="text-[10px] text-ink-tertiary">Forgotten</div>
        </div>
      </div>
    </div>
  );
}

interface TurnArticleProps {
  turn: TimelineTurn;
  /** True once the user row has been redacted server-side. */
  userForgotten: boolean;
  /**
   * True once the assistant row has been. It is tracked apart from the user
   * row because a redaction can half-land: the two rows are two writes, and
   * the article must never show the marker over words another row still
   * holds on disk.
   */
  assistantForgotten: boolean;
  /**
   * Resolves when every row that could be redacted has been tried, with the
   * sentence to show the admin when some row refused, or null when the whole
   * turn is gone. It reports rather than throws.
   */
  onForget?: (turn: TimelineTurn) => Promise<string | null>;
  onRunCommand?: RunCommand;
}

/**
 * memo: a stored turn is immutable, so it should only re-render when the
 * turn object itself changes (or when it is forgotten). Callers should pass a
 * stable `onRunCommand` and `onForget` (useCallback) or the memo buys nothing.
 */
const TurnArticle = memo(function TurnArticle({
  turn,
  userForgotten,
  assistantForgotten,
  onForget,
  onRunCommand,
}: TurnArticleProps) {
  // Forgetting cannot be undone — content, blocks, diffs, the FTS row, the
  // thread's entity sets and (for a founding row) the thread title all go —
  // so the control asks first and stays busy until the server has answered.
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  // The last refusal, kept on screen beside the control until the admin asks
  // again — the live region says it once and is invisible.
  const [failure, setFailure] = useState<string | null>(null);
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  // Redaction replaces content and blocks_json (spec §5); the terminal ids
  // are not part of it, so the "ended" chips stay. Blocks and diffs follow
  // the ASSISTANT row: it is the row that carries them (ThreadManager stores
  // the user row with neither), and tying them to the wrong row would either
  // hide output that is still stored or leave scrubbed output on screen.
  const blocks = assistantForgotten
    ? turn.blocks.length > 0
      ? [REDACTED_BLOCK]
      : []
    : turn.blocks;
  const diffs = assistantForgotten ? [] : turn.diffProposals;
  const hasAssistantSide =
    turn.assistant !== null ||
    blocks.length > 0 ||
    turn.terminalBlockIds.length > 0 ||
    diffs.length > 0;
  const label = userForgotten ? REDACTED : turn.user ? turn.user.content.slice(0, 80) : turn.origin;
  // A half-landed redaction leaves one row still readable, so the control
  // stays until every stored row of this turn is forgotten.
  const canForget =
    onForget !== undefined &&
    ((turn.user !== null && turn.user.messageId >= 0 && !userForgotten) ||
      (turn.assistant !== null && turn.assistant.messageId >= 0 && !assistantForgotten));

  const confirm = async () => {
    if (pending) return;
    setPending(true);
    try {
      setFailure((await onForget?.(turn)) ?? null);
    } catch (err) {
      // onForget reports refusals in its return value; anything thrown is a
      // bug in this page, and even then the admin must not be left with a
      // closed dialog and unchanged words that look like nothing happened.
      console.warn('[TIMELINE] forget handler threw:', err);
      setFailure(FORGET_FAILED);
    } finally {
      setPending(false);
      setConfirming(false);
    }
  };

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
            <p className="text-sm whitespace-pre-wrap break-words">
              {userForgotten ? REDACTED : turn.user.content}
            </p>
          </div>
        </div>
      )}

      {turn.user?.status === 'interrupted' && (
        <p className="text-center text-[11px] font-mono text-ink-tertiary">(Halbert restarted here)</p>
      )}

      {hasAssistantSide && (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
            {blocks.map((block, i) =>
              isRedactedBlock(block) ? (
                <RedactedToolCard key={block.executionId ?? `${turn.turnId}-block-${i}`} />
              ) : (
                <ToolExecutionCard
                  key={block.executionId ?? `${turn.turnId}-block-${i}`}
                  execution={executionFromBlock(block, `${turn.turnId}-block-${i}`)}
                />
              ),
            )}

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
                {assistantForgotten ? (
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

      {(canForget || failure !== null) && !confirming && (
        <div className="flex flex-wrap items-center justify-end gap-2 text-[11px] font-mono">
          {/* Plain text, not a live region: `announce` has already spoken
              this sentence, and a second region here would say it twice. */}
          {failure !== null && <span className="text-error">{failure}</span>}
          {canForget && (
            <button
              type="button"
              aria-label="Forget this turn"
              title="Replace this turn's words and tool output with a redaction marker, everywhere it is stored"
              onClick={() => {
                // The old verdict does not describe the attempt about to be
                // made, so it goes as soon as the question is asked again.
                setFailure(null);
                setConfirming(true);
              }}
              className="rounded px-1 text-ink-tertiary hover:text-ink-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              Forget this
            </button>
          )}
        </div>
      )}

      {canForget && confirming && (
        <div
          className="flex flex-wrap items-center justify-end gap-2 text-[11px] font-mono text-ink-tertiary"
          onKeyDown={(e) => {
            if (e.key === 'Escape' && !pending) setConfirming(false);
          }}
        >
          <span id={`forget-warning-${turn.turnId}`}>
            Forget this turn? Its words and tool output are replaced wherever they are stored, and cannot be
            brought back.
          </span>
          <button
            ref={confirmRef}
            type="button"
            aria-label="Yes, forget this turn"
            aria-describedby={`forget-warning-${turn.turnId}`}
            disabled={pending}
            onClick={confirm}
            className="rounded border border-hairline px-1.5 py-0.5 text-ink-secondary hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            {pending ? 'Forgetting…' : 'Forget'}
          </button>
          <button
            type="button"
            aria-label="Cancel forgetting this turn"
            disabled={pending}
            onClick={() => setConfirming(false)}
            className="rounded px-1.5 py-0.5 hover:text-ink-secondary disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            Cancel
          </button>
        </div>
      )}
    </article>
  );
});

const NO_IDS: ReadonlySet<number> = new Set();

export function Timeline({
  byDay,
  hasMore,
  loading,
  anchored = false,
  onLoadOlder,
  onLoadLatest,
  onRunCommand,
}: TimelineProps) {
  // Message ids, not turn ids: the two rows of a turn are two server writes
  // and either can fail on its own.
  const [forgotten, setForgotten] = useState<ReadonlySet<number>>(NO_IDS);
  // The same set, readable inside the handler without making it depend on
  // (and re-identify with) the state it just wrote.
  const forgottenRef = useRef<ReadonlySet<number>>(NO_IDS);

  // "Forget this": every row is redacted server-side first; the article
  // shows the marker only for the rows the server has agreed to forget, so
  // the page never claims something is forgotten that is still on disk.
  //
  // Returns the sentence the article prints beside the control when some row
  // refused, or null when the whole turn is gone.
  const handleForget = useCallback(async (turn: TimelineTurn): Promise<string | null> => {
    const ids = redactableIds(turn).filter((id) => !forgottenRef.current.has(id));
    if (ids.length === 0) return null;

    // One row at a time, recording each. Promise.all rejects on the FIRST
    // failure and neither cancels nor rolls back its siblings, so a turn
    // whose user row returned 200 and whose assistant row returned 500 (the
    // route's "Redaction failed" / "receipt still holds the original text"
    // answers) was reported unchanged while half of it was already scrubbed.
    const landed: number[] = [];
    const failures: unknown[] = [];
    for (const id of ids) {
      try {
        await api.redactMessage(id);
        landed.push(id);
      } catch (err) {
        // Keep going: forgetting as much as the store will forget is the
        // point, and the rows that refuse are named to the admin below.
        failures.push(err);
      }
    }

    if (landed.length > 0) {
      const next = new Set(forgottenRef.current);
      landed.forEach((id) => next.add(id));
      forgottenRef.current = next;
      setForgotten(next);
    }

    if (failures.length === 0) {
      // The marker replaces text in place; nothing else would say so.
      announce('Turn forgotten');
      return null;
    }
    // A console warning is invisible in the product, and a privacy promise
    // that did not land is precisely what the person has to hear — so the
    // same sentence is both spoken and handed back to be shown.
    console.warn(
      `[TIMELINE] forget: ${failures.length} of ${ids.length} rows refused:`,
      failures[0],
    );
    const sentence = landed.length > 0 ? FORGET_PARTLY_FAILED : FORGET_FAILED;
    announce(sentence, { assertive: true });
    return sentence;
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
              userForgotten={turn.user !== null && forgotten.has(turn.user.messageId)}
              assistantForgotten={turn.assistant !== null && forgotten.has(turn.assistant.messageId)}
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
