// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The stored conversation renders with roles: day dividers as headings with
 * a machine-readable date, one article per turn, static tool cards, an
 * "ended" chip for a terminal the store no longer has, and diffs that can
 * no longer be applied.
 */

import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, it, expect, vi } from 'vitest'
import { Timeline, executionFromBlock } from './Timeline'
import { groupByDay } from '../../hooks/useTimeline'
import { terminalSessionStore } from '../../hooks/useTerminalSessions'
import type { TimelineToolBlock, TimelineTurn } from '../../types/timeline'

// The live tile needs xterm + a real font pipeline; the timeline test is
// about records, so the tile is a stub here.
vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

// A live tile watches itself with an IntersectionObserver (docking), which
// jsdom does not implement; docking is not what this file is about.
vi.stubGlobal(
  'IntersectionObserver',
  class {
    root = null
    rootMargin = ''
    thresholds: number[] = []
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return []
    }
  },
)

// The terminal store is a module singleton: a session seeded by one test must
// not decide the next test's live-vs-ended branch. Unmount first — closeAll()
// notifies its subscribers, and a store update landing on a still-mounted tree
// is a React state update outside act().
afterEach(() => {
  cleanup()
  terminalSessionStore.closeAll()
})

const NOW = new Date(2026, 6, 16, 12, 0, 0) // Thu 16 Jul 2026

function turn(id: string, timestamp: number, text: string, extra: Partial<TimelineTurn> = {}): TimelineTurn {
  return {
    turnId: id,
    threadId: 'th-1',
    timestamp,
    origin: 'human',
    user: { messageId: 1, content: text, timestamp, status: 'complete' },
    assistant: { messageId: 2, content: `Answer to ${text}`, timestamp: timestamp + 2000, status: 'complete' },
    blocks: [],
    terminalBlockIds: [],
    diffProposals: [],
    ...extra,
  }
}

const OLD = new Date(2026, 6, 14, 9, 30).getTime()
const TODAY = new Date(2026, 6, 16, 8, 0).getTime()

const TURNS = [
  turn('t-1', OLD, 'is samba running?', {
    blocks: [{ tool: 'run_command', args: { command: 'systemctl status smbd' }, result: 'active', exit: 0, executionId: 'x1' }],
    terminalBlockIds: ['term-gone'],
    diffProposals: [{ id: 'd1', filePath: '/etc/samba/smb.conf', newContent: 'b', oldContent: 'a', additions: 1, deletions: 1, status: 'pending' }],
  }),
  turn('t-2', TODAY, 'and now?', {
    user: { messageId: 5, content: 'and now?', timestamp: TODAY, status: 'interrupted' },
    assistant: null,
  }),
]

describe('Timeline', () => {
  it('renders day dividers as h2 + time and one article per turn', () => {
    const { container } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )

    const feed = screen.getByRole('feed')
    expect(feed).toHaveAttribute('aria-busy', 'false')

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Tue, Jul 14', 'Today'])

    const times = Array.from(container.querySelectorAll('header.thread-divider time')).map((t) => t.getAttribute('datetime'))
    expect(times).toEqual(['2026-07-14', '2026-07-16'])

    const articles = screen.getAllByRole('article')
    expect(articles).toHaveLength(2)
    expect(articles[0]).toHaveAttribute('data-turn-id', 't-1')
  })

  it('renders user and assistant content with their roles', () => {
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.getByText('Answer to is samba running?')).toBeInTheDocument()
    expect(screen.getByText('(Halbert restarted here)')).toBeInTheDocument()
  })

  it('renders static tool cards, an ended-terminal chip and a read-only diff', () => {
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    expect(screen.getByText('run_command')).toBeInTheDocument()
    expect(screen.getByText('terminal · ended')).toBeInTheDocument()
    expect(screen.queryByTestId('live-tile')).not.toBeInTheDocument()
    expect(screen.getByText('/etc/samba/smb.conf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
    expect(screen.getByText('proposed')).toBeInTheDocument()
  })

  it('renders a live tile instead of the chip while the store still holds the terminal', () => {
    // Same id as the stored turn's terminal, but this time the page still has
    // the session (a reload has not happened yet), so the turn shows the live
    // terminal rather than the record of one.
    terminalSessionStore.adopt('term-gone', { command: 'apt upgrade' })

    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    expect(screen.getByTestId('live-tile')).toHaveTextContent('term-gone')
    expect(screen.queryByText('terminal · ended')).not.toBeInTheDocument()
  })

  it('offers "Load earlier" only when there is more, and marks the feed busy while paging', async () => {
    const onLoadOlder = vi.fn()
    const { rerender } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore onLoadOlder={onLoadOlder} loading={false} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Load earlier' }))
    expect(onLoadOlder).toHaveBeenCalledTimes(1)

    rerender(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore onLoadOlder={onLoadOlder} loading />)
    expect(screen.getByRole('feed')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()

    rerender(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} onLoadOlder={onLoadOlder} loading={false} />)
    expect(screen.queryByRole('button', { name: 'Load earlier' })).not.toBeInTheDocument()
  })

  it('renders nothing at all for an empty, fully loaded timeline', () => {
    const { container } = render(<Timeline byDay={[]} hasMore={false} loading={false} onLoadOlder={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('offers "Back to latest" only while anchored on an earlier window', async () => {
    const onLoadLatest = vi.fn()
    const { rerender } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} onLoadLatest={onLoadLatest} />,
    )
    expect(screen.queryByRole('button', { name: 'Back to latest' })).not.toBeInTheDocument()

    rerender(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} anchored onLoadOlder={() => {}} onLoadLatest={onLoadLatest} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Back to latest' }))
    expect(onLoadLatest).toHaveBeenCalledTimes(1)
  })
})

describe('executionFromBlock', () => {
  function block(extra: Partial<TimelineToolBlock> = {}): TimelineToolBlock {
    return { tool: 'run_command', args: { command: 'ls /srv' }, ...extra }
  }

  it('reads the exit code only when the backend stored no status', () => {
    expect(executionFromBlock(block({ exit: 0 }), 'f').status).toBe('success')
    expect(executionFromBlock(block({ exit: 1 }), 'f').status).toBe('error')
    // exit is only ever set for run_command; unknown reads as success.
    expect(executionFromBlock(block({ exit: null }), 'f').status).toBe('success')
  })

  it("prefers the backend's own verdict over the exit code", () => {
    expect(executionFromBlock(block({ status: 'success', exit: null }), 'f').status).toBe('success')
    expect(executionFromBlock(block({ status: 'error', exit: null, error: 'no such file' }), 'f')).toMatchObject({
      status: 'error',
      error: 'no such file',
    })
    // Staged, then superseded before it ran (state_machine.py:410-455).
    expect(executionFromBlock(block({ status: 'superseded', exit: null }), 'f').status).toBe('error')
  })

  it('never calls a call that never finished a success', () => {
    // A ToolCall is born "pending" (states.py:97) and _end_turn persists every
    // call whatever its status (state_machine.py:660), so a turn interrupted
    // between dispatch and completion stores {status: 'pending', exit: null} —
    // which the exit heuristic on its own would render as a green success.
    expect(executionFromBlock(block({ status: 'pending', exit: null }), 'f').status).toBe('error')
    expect(executionFromBlock(block({ status: 'running' }), 'f').status).toBe('error')
  })

  it('falls back to the caller id only when the block has no execution id', () => {
    expect(executionFromBlock(block(), 't-1-block-0').executionId).toBe('t-1-block-0')
    expect(executionFromBlock(block({ executionId: 'x9' }), 't-1-block-0').executionId).toBe('x9')
  })
})
