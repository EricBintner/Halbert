// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The stored conversation renders with roles: day dividers as headings with
 * a machine-readable date, one article per turn, static tool cards, an
 * "ended" chip for a terminal the store no longer has, and diffs that can
 * no longer be applied.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Timeline } from './Timeline'
import { groupByDay } from '../../hooks/useTimeline'
import type { TimelineTurn } from '../../types/timeline'

// The live tile needs xterm + a real font pipeline; the timeline test is
// about records, so the tile is a stub here.
vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

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
