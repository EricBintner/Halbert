// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The live block becomes a stored turn without a refetch: everything the
 * hook accumulated during the turn is folded into one TimelineTurn.
 */

import { describe, it, expect, vi } from 'vitest'
import { turnFromSession, isLocalTurnId } from './turnFromSession'
import { executionFromBlock } from '../components/agent/Timeline'
import type { AgentSession } from '../hooks/useAgentStream'

// Timeline pulls the terminal tile in through InlineTerminals; nothing here
// renders, so keep the xterm dependency out of this file's module graph.
vi.mock('../components/agent/TerminalTile', () => ({ TerminalTile: () => null }))

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
      { tool: 'run_command', args: { command: 'ls' }, result: 'a b', exit: 0, executionId: 'x1', status: 'success', error: undefined },
      { tool: 'run_command', args: { command: 'false' }, result: undefined, exit: 1, executionId: 'x2', status: 'error', error: 'exit 1' },
      { tool: 'read_file', args: { path: '/etc/hosts' }, result: undefined, exit: null, executionId: 'x3', status: 'running', error: undefined },
    ])
    expect(turn.terminalBlockIds).toEqual(['term-1'])
    expect(turn.diffProposals[0].id).toBe('d1')
  })

  it('falls back to a local id when the store never confirmed the turn', () => {
    const turn = turnFromSession(session({ turnId: null, thread: null }), USER, 'ok')
    expect(turn.turnId).toBe('local-sess-1')
    expect(turn.threadId).toBe('')
  })

  it('says which turn ids the server can be asked about', () => {
    // Anything that would go back to the server for this turn — reading its
    // row ids back so it can be forgotten, above all — has to tell the two
    // apart first: nothing on the server answers to the local id.
    expect(isLocalTurnId(turnFromSession(session({ turnId: null }), USER, 'ok').turnId)).toBe(true)
    expect(isLocalTurnId(turnFromSession(session(), USER, 'ok').turnId)).toBe(false)
  })

  it('keeps each call\'s own verdict, so an unfinished one never reads as a success', () => {
    const turn = turnFromSession(
      session({
        toolExecutions: [
          // Stop pressed mid-command: cancel() closes the stream and marks
          // nothing, so this call is still 'running' when the turn is folded.
          { executionId: 'x1', tool: 'run_command', args: { command: 'systemctl stop nginx' }, status: 'running' },
          // A failed tool that has no exit code of its own.
          { executionId: 'x2', tool: 'read_file', args: { path: '/etc/shadow' }, status: 'error', error: 'permission denied' },
        ],
      }),
      USER,
      'partial',
      { cancelled: true },
    )

    expect(turn.blocks[0]).toEqual({
      tool: 'run_command',
      args: { command: 'systemctl stop nginx' },
      result: undefined,
      exit: null,
      executionId: 'x1',
      status: 'running',
      error: undefined,
    })

    // What the timeline actually paints: `exit` is absent for both, so its
    // pass/fail reading falls through to the stored status. Without one it
    // defaults to success — a green tick on a privileged command that was
    // interrupted, and a failed read with its message gone.
    expect(executionFromBlock(turn.blocks[0], 'fallback').status).not.toBe('success')
    expect(executionFromBlock(turn.blocks[1], 'fallback').status).toBe('error')
    expect(executionFromBlock(turn.blocks[1], 'fallback').error).toBe('permission denied')
  })

  it('invents no exit code for a tool that has none', () => {
    const turn = turnFromSession(
      session({
        toolExecutions: [
          { executionId: 'x9', tool: 'read_file', args: { path: '/etc/hosts' }, status: 'success', result: '127.0.0.1' },
        ],
      }),
      USER,
      'ok',
    )
    // `exit` is the run_command convention (types/timeline.ts); a read_file
    // says how it went through its status.
    expect(turn.blocks[0].exit).toBeNull()
    expect(turn.blocks[0].status).toBe('success')
    expect(executionFromBlock(turn.blocks[0], 'fallback').status).toBe('success')
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
