// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A stored turn folds its inspection calls too.
 *
 * Grouping has to happen at BOTH render sites or history and the live feed
 * disagree about what the same turn looked like. This is the stored half.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Timeline, REDACTED } from './Timeline'
import { groupByDay } from '../../hooks/useTimeline'
import type { TimelineTurn, TimelineToolBlock } from '../../types/timeline'
import { terminalSessionStore } from '../../hooks/useTerminalSessions'

const NOW = new Date(2026, 6, 16, 12, 0, 0)
const AT = new Date(2026, 6, 16, 8, 0).getTime()

const read = (id: string, path: string): TimelineToolBlock =>
  ({ tool: 'read_file', args: { path }, result: 'x', exit: null, executionId: id, status: 'success' })

function turn(blocks: TimelineToolBlock[]): TimelineTurn {
  return {
    turnId: 't-1', threadId: 'th-1', timestamp: AT, origin: 'human',
    user: { messageId: 1, content: 'why is samba down?', timestamp: AT, status: 'complete' },
    assistant: { messageId: 2, content: 'the share moved', timestamp: AT + 1, status: 'complete' },
    blocks, terminalBlockIds: [], diffProposals: [],
  }
}

const show = (t: TimelineTurn) =>
  render(<Timeline byDay={groupByDay([t], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, text: async () => '', json: async () => ({}) })))
  terminalSessionStore.closeAll()
})
afterEach(() => { vi.unstubAllGlobals(); terminalSessionStore.closeAll() })

describe('Timeline — inspection grouping', () => {
  it('folds a run of reads into one line', () => {
    show(turn([read('a', '/etc/fstab'), read('b', '/etc/hosts'), read('c', '/etc/passwd')]))

    expect(screen.getByText(/Looked at 3 files/)).toBeTruthy()
    expect(screen.queryByText('read_file')).toBeNull()
  })

  it('opens back up to the individual steps', () => {
    show(turn([read('a', '/etc/fstab'), read('b', '/etc/hosts')]))
    fireEvent.click(screen.getByRole('button', { name: /Looked at/ }))

    expect(screen.getAllByText('read_file')).toHaveLength(2)
  })

  it('never folds a forgotten call into a count', () => {
    // Timeline.tsx:104-108 exists because a redaction marker carries neither
    // exit code nor status, so a careless default paints a green tick on a
    // turn an admin asked to forget. Folding it into "3 files" is the same
    // mistake one layer up: the forgetting becomes an increment.
    show(turn([
      read('a', '/etc/fstab'),
      { tool: REDACTED, args: {}, result: undefined, exit: null, executionId: 'r', redacted: true },
      read('c', '/etc/passwd'),
    ]))

    expect(screen.getByText('Forgotten')).toBeTruthy()
    // Two lone reads either side, neither folded into a group of one.
    expect(screen.queryByText(/Looked at/)).toBeNull()
    expect(screen.getAllByText('read_file')).toHaveLength(2)
  })

  it('leaves a command that was not quiet standing on its own', () => {
    show(turn([
      read('a', '/etc/fstab'),
      { tool: 'run_command', args: { command: 'systemctl restart smbd' }, result: 'ok',
        exit: 0, executionId: 'cmd', status: 'success' },
      read('c', '/etc/passwd'),
    ]))

    expect(screen.getByText('systemctl restart smbd')).toBeTruthy()
    expect(screen.queryByText(/Looked at/)).toBeNull()
  })
})
