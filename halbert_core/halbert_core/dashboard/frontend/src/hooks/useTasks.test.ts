// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Promoted blocks become task cards.
 *
 * `terminal_block_promote` set `isTaskCard` on a block and nothing read it,
 * so a command crossing the two-second line had no user-visible effect at
 * all: the whole fast/slow distinction ended at a boolean. This is the
 * derivation that gives a promoted command somewhere to be.
 */

import { describe, it, expect } from 'vitest'
import { tasksFromSessions } from './useTasks'
import type { TerminalSession } from './useTerminalSessions'

function session(over: Partial<TerminalSession> = {}): TerminalSession {
  return {
    id: 'term-1',
    pid: 10,
    command: 'npm run build',
    status: 'running',
    output: '',
    droppedChars: 0,
    exitCode: null,
    visible: true,
    sandboxed: false,
    startedAt: Date.now() - 5_000,
    transport: 'ws',
    blocks: [],
    ...over,
  }
}

const block = (over = {}) => ({
  block_id: 'blk-1',
  owner: 'agent',
  status: 'running' as const,
  isTaskCard: true,
  ...over,
})

describe('tasksFromSessions', () => {
  it('ignores a block that was never promoted', () => {
    const { running, finished } = tasksFromSessions([
      session({ blocks: [block({ isTaskCard: false })] }),
    ])

    // A fast command is a line in the conversation, not an entry in a list
    // of what the machine is doing.
    expect(running).toEqual([])
    expect(finished).toEqual([])
  })

  it('turns a promoted running block into a running card', () => {
    const { running } = tasksFromSessions([session({ blocks: [block()] })])

    expect(running).toHaveLength(1)
    expect(running[0].taskId).toBe('blk-1')
    expect(running[0].blockId).toBe('blk-1')
    expect(running[0].title).toBe('npm run build')
    expect(running[0].state).toBe('running')
    expect(running[0].elapsedSeconds).toBeGreaterThanOrEqual(4)
  })

  it('moves a completed block to finished with its exit code', () => {
    const { running, finished } = tasksFromSessions([
      session({
        status: 'done',
        exitCode: 2,
        blocks: [block({ status: 'completed' })],
      }),
    ])

    expect(running).toEqual([])
    expect(finished).toHaveLength(1)
    expect(finished[0].exitCode).toBe(2)
    // A non-zero exit is not a quiet completion.
    expect(finished[0].state).toBe('error')
  })

  it('reads a clean completion as done, not as an error', () => {
    const { finished } = tasksFromSessions([
      session({ status: 'done', exitCode: 0, blocks: [block({ status: 'completed' })] }),
    ])

    expect(finished[0].state).toBe('done_unseen')
  })

  it('surfaces a block waiting on input', () => {
    const { running } = tasksFromSessions([
      session({ blocks: [block({ status: 'needs_attention' })] }),
    ])

    expect(running[0].state).toBe('needs_attention')
  })

  it('never makes a task card of the admin’s own shell', () => {
    // plan-b-contracts §12: "The admin's shell is never a task card."
    const { running, finished } = tasksFromSessions([
      session({ blocks: [block({ owner: 'user' })] }),
    ])

    expect(running).toEqual([])
    expect(finished).toEqual([])
  })

  it('prefers the block’s own label over the session command', () => {
    // A pool session is reused, so session.command describes whichever block
    // spawned it — not necessarily this one.
    const { running } = tasksFromSessions([
      session({ command: 'bash', blocks: [block({ label: 'rsync -a /mnt/a /mnt/b' })] }),
    ])

    expect(running[0].title).toBe('rsync -a /mnt/a /mnt/b')
  })

  it('keeps the newest task first', () => {
    const now = Date.now()
    const { running } = tasksFromSessions([
      session({ id: 'a', startedAt: now - 60_000, blocks: [block({ block_id: 'old' })] }),
      session({ id: 'b', startedAt: now - 1_000, blocks: [block({ block_id: 'new' })] }),
    ])

    expect(running.map((t) => t.taskId)).toEqual(['new', 'old'])
  })
})
