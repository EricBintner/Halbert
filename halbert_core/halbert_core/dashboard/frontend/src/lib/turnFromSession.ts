// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * turnFromSession — fold the finished live turn into a TimelineTurn.
 *
 * The server stored this turn as it happened (turn_persisted carries the
 * id); the page already watched it happen, so it appends the same turn
 * locally rather than refetching. On the next load the server's copy wins
 * by id. When the store never confirmed the turn (thread_store_error), a
 * local id keeps the transcript continuous for this page load only.
 */

import type { AgentSession, ToolExecution } from '../hooks/useAgentStream';
import type { TimelineMessageStatus, TimelineToolBlock, TimelineTurn } from '../types/timeline';

export interface LiveUserMessage {
  id: string;
  content: string;
  /** Epoch milliseconds. */
  timestamp: number;
}

function exitOf(execution: ToolExecution): number | null {
  if (execution.status === 'success') return 0;
  if (execution.status === 'error') return 1;
  return null;
}

function blockFromExecution(execution: ToolExecution): TimelineToolBlock {
  return {
    tool: execution.tool,
    args: execution.args,
    result: execution.result,
    exit: exitOf(execution),
    executionId: execution.executionId,
  };
}

export function turnFromSession(
  session: AgentSession,
  userMessage: LiveUserMessage,
  response: string,
  opts: { cancelled?: boolean } = {},
): TimelineTurn {
  const status: TimelineMessageStatus = opts.cancelled
    ? 'cancelled'
    : session.error
      ? 'interrupted'
      : 'complete';
  const now = Date.now();
  return {
    turnId: session.turnId ?? `local-${session.sessionId}`,
    threadId: session.thread?.threadId ?? '',
    timestamp: userMessage.timestamp,
    origin: 'human',
    user: { messageId: -1, content: userMessage.content, timestamp: userMessage.timestamp, status },
    assistant: response
      ? { messageId: -1, content: response, timestamp: now, status }
      : null,
    blocks: session.toolExecutions.map(blockFromExecution),
    terminalBlockIds: session.terminalSessions ?? [],
    diffProposals: session.diffProposals,
  };
}

export default turnFromSession;
