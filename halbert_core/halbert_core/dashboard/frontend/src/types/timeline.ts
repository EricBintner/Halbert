// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Timeline types (continuous conversation, Plan A).
 *
 * One conversation, stored as turns; threads are a hidden grouping the
 * server owns. The wire shape from GET /api/agent/timeline is snake_case
 * and its timestamps are epoch seconds — the mappers at the bottom are the
 * only place that shape is known. Everything client-side is camelCase and
 * milliseconds.
 */

import type { DiffProposal } from '../hooks/useAgentStream';

export interface TimelineToolBlock {
  tool: string;
  args: Record<string, unknown>;
  result?: unknown;
  exit?: number | null;
  executionId?: string;
  /**
   * The tool call's own status as the backend recorded it (e.g. "success",
   * "error", "superseded") — independent of `exit`, which is only ever a
   * number for `run_command`. A consumer rendering pass/fail must prefer
   * this over an exit-code heuristic, or a failed non-run_command tool (or
   * a staged call superseded before it ran) reads as a successful one.
   */
  status?: string;
  /** Set alongside status === "error"; the failure message. */
  error?: string;
}

export type TimelineOrigin =
  | 'human'
  | 'assistant'
  | 'terminal'
  | 'task-notification'
  | 'proactive'
  | 'system';

export type TimelineMessageStatus = 'in_progress' | 'complete' | 'interrupted' | 'cancelled';

export interface TimelineMessage {
  messageId: number;
  content: string;
  /** Epoch milliseconds. */
  timestamp: number;
  status: TimelineMessageStatus;
}

export interface TimelineTurn {
  turnId: string;
  threadId: string;
  /** Epoch milliseconds — the day divider is computed from this. */
  timestamp: number;
  origin: TimelineOrigin;
  user: TimelineMessage | null;
  assistant: { messageId: number; content: string; timestamp: number; status: string } | null;
  blocks: TimelineToolBlock[];
  terminalBlockIds: string[];
  diffProposals: DiffProposal[];
}

export interface TimelineCurrentThread {
  threadId: string;
  title: string;
  status: string;
}

export interface TimelinePage {
  turns: TimelineTurn[];
  hasMore: boolean;
  currentThread: TimelineCurrentThread | null;
}

// ---------------------------------------------------------------------------
// Wire -> client mappers
// ---------------------------------------------------------------------------

type Raw = Record<string, unknown>;

function asRecord(value: unknown): Raw | null {
  return value && typeof value === 'object' ? (value as Raw) : null;
}

/** Server seconds -> client milliseconds (already-ms values pass through). */
export function toMillis(ts: unknown): number {
  const n = typeof ts === 'number' ? ts : Number(ts ?? 0);
  if (!Number.isFinite(n) || n <= 0) return Date.now();
  return n < 1e12 ? Math.round(n * 1000) : n;
}

function messageFromServer(raw: unknown): TimelineMessage | null {
  const r = asRecord(raw);
  if (!r) return null;
  return {
    messageId: Number(r.message_id ?? r.id ?? -1),
    content: String(r.content ?? ''),
    timestamp: toMillis(r.timestamp),
    status: (r.status as TimelineMessageStatus) ?? 'complete',
  };
}

export function blockFromServer(raw: unknown): TimelineToolBlock {
  const r = asRecord(raw) ?? {};
  const exit = r.exit ?? r.exit_code;
  return {
    tool: String(r.tool ?? r.name ?? ''),
    args: asRecord(r.args) ?? {},
    result: r.result,
    exit: typeof exit === 'number' ? exit : exit == null ? null : Number(exit),
    executionId: typeof r.execution_id === 'string' ? r.execution_id
      : typeof r.executionId === 'string' ? r.executionId : undefined,
    status: typeof r.status === 'string' ? r.status : undefined,
    error: typeof r.error === 'string' ? r.error : undefined,
  };
}

/**
 * Stored diffs come from StateContext.pending_diffs, whose shape is
 * {file_path, edit_blocks: [{search, replace}], status}; older rows may carry
 * the diff_proposal event shape (new_content/old_content). Accept both.
 */
export function diffFromServer(raw: unknown): DiffProposal {
  const r = asRecord(raw) ?? {};
  const editBlocks = Array.isArray(r.edit_blocks)
    ? (r.edit_blocks as unknown[]).map((b) => asRecord(b) ?? {})
    : [];
  const newContent = typeof r.new_content === 'string'
    ? r.new_content
    : editBlocks.map((b) => String(b.replace ?? '')).join('\n');
  const oldContent = typeof r.old_content === 'string'
    ? r.old_content
    : editBlocks.length > 0 ? editBlocks.map((b) => String(b.search ?? '')).join('\n') : undefined;
  const status = r.status === 'applied' || r.status === 'rejected' ? r.status : 'pending';
  return {
    id: String(r.id ?? r.diff_id ?? ''),
    filePath: String(r.file_path ?? r.filePath ?? ''),
    oldContent,
    newContent,
    additions: Number(r.additions ?? 0),
    deletions: Number(r.deletions ?? 0),
    status,
  };
}

export function turnFromServer(raw: unknown): TimelineTurn {
  const r = asRecord(raw) ?? {};
  const assistant = messageFromServer(r.assistant);
  return {
    turnId: String(r.turn_id ?? r.turnId ?? ''),
    threadId: String(r.thread_id ?? r.threadId ?? ''),
    timestamp: toMillis(r.timestamp),
    origin: (r.origin as TimelineOrigin) ?? 'human',
    user: messageFromServer(r.user),
    assistant,
    blocks: Array.isArray(r.blocks) ? (r.blocks as unknown[]).map(blockFromServer) : [],
    terminalBlockIds: Array.isArray(r.terminal_block_ids)
      ? (r.terminal_block_ids as unknown[]).map(String)
      : [],
    diffProposals: Array.isArray(r.diff_proposals)
      ? (r.diff_proposals as unknown[]).map(diffFromServer)
      : [],
  };
}

/** The physical column is still `conversation_id`; accept it as the id. */
export function threadFromServer(raw: unknown): TimelineCurrentThread | null {
  const r = asRecord(raw);
  if (!r) return null;
  const threadId = r.thread_id ?? r.conversation_id ?? r.id;
  if (!threadId) return null;
  return {
    threadId: String(threadId),
    title: String(r.title ?? ''),
    status: String(r.status ?? 'open'),
  };
}

export function pageFromServer(raw: unknown): TimelinePage {
  const r = asRecord(raw) ?? {};
  return {
    turns: Array.isArray(r.turns) ? (r.turns as unknown[]).map(turnFromServer) : [],
    hasMore: !!r.has_more,
    currentThread: threadFromServer(r.current_thread),
  };
}
