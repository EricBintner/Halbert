// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The live block becomes a stored turn without a refetch: everything the
 * hook accumulated during the turn is folded into one TimelineTurn.
 */

import { describe, it, expect } from 'vitest'
import { turnFromSession } from './turnFromSession'
import type { AgentSession } from '../hooks/useAgentStream'

function session(extra: Partial<AgentSession> = {}): AgentSession {
  return {
    sessionId: 'sess-1',
    state: 'idle',
    plan: [],
    currentStep: 0,
    loopCount: 0,
    confidence: 0,
    cragAction: 'PENDING',
    toolExecutions: [
      { executionId: 'x1', tool: 'run_command', args: { command: 'ls' }, status: 'success', result: 'a b' },
      { executionId: 'x2', tool: 'run_command', args: { command: 'false' }, status: 'error', error: 'exit 1' },
      { executionId: 'x3', tool: 'read_file', args: { path: '/etc/hosts' }, status: 'running' },
    ],
    pendingConfirmation: null,
    error: null,
    activeScan: null,
    contextItems: [],
    diffProposals: [{ id: 'd1', filePath: '/etc/x', newContent: 'n', additions: 1, deletions: 0, status: 'pending' }],
    terminalSessions: ['term-1'],
    thread: { threadId: 'th-1', title: 'Samba share setup' },
    recalled: null,
    turnId: 't-42',
    ...extra,
  }
}

const USER = { id: 'user-1', content: 'list the dir', timestamp: 1_784_000_000_000 }

describe('turnFromSession', () => {
  it('folds the session into a complete turn keyed by the persisted turn id', () => {
    const turn = turnFromSession(session(), USER, 'Here you go.')
    expect(turn.turnId).toBe('t-42')
    expect(turn.threadId).toBe('th-1')
    expect(turn.timestamp).toBe(USER.timestamp)
    expect(turn.origin).toBe('human')
    expect(turn.user).toEqual({ messageId: -1, content: 'list the dir', timestamp: USER.timestamp, status: 'complete' })
    expect(turn.assistant?.content).toBe('Here you go.')
    expect(turn.assistant?.status).toBe('complete')
    expect(turn.blocks).toEqual([
      { tool: 'run_command', args: { command: 'ls' }, result: 'a b', exit: 0, executionId: 'x1' },
      { tool: 'run_command', args: { command: 'false' }, result: undefined, exit: 1, executionId: 'x2' },
      { tool: 'read_file', args: { path: '/etc/hosts' }, result: undefined, exit: null, executionId: 'x3' },
    ])
    expect(turn.terminalBlockIds).toEqual(['term-1'])
    expect(turn.diffProposals[0].id).toBe('d1')
  })

  it('falls back to a local id when the store never confirmed the turn', () => {
    const turn = turnFromSession(session({ turnId: null, thread: null }), USER, 'ok')
    expect(turn.turnId).toBe('local-sess-1')
    expect(turn.threadId).toBe('')
  })

  it('marks interrupted and cancelled turns, and omits an empty reply', () => {
    const errored = turnFromSession(session({ error: 'Connection error' }), USER, '')
    expect(errored.user?.status).toBe('interrupted')
    expect(errored.assistant).toBeNull()

    const cancelled = turnFromSession(session(), USER, 'partial', { cancelled: true })
    expect(cancelled.user?.status).toBe('cancelled')
    expect(cancelled.assistant?.status).toBe('cancelled')
  })
})
