// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One conversation: AgentChat mounts the stored timeline and the current
 * topic label, and the dropdown / "New Conversation" / "Session:" footer
 * are gone. The greeting shows only when there is nothing to show. The
 * thread chip is a real control: its title says why it is here and a click
 * loads the timeline around the recalled thread's last turn.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AgentChat } from './AgentChat'

vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

/** One SSE body: every event as a `data:` line, delivered in one chunk. */
function sseBody(events: Array<Record<string, unknown>>) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n`).join('')
  const chunks = [new TextEncoder().encode(text)]
  return {
    getReader: () => ({
      read: async () => {
        const value = chunks.shift()
        return value ? { done: false, value } : { done: true, value: undefined }
      },
    }),
  }
}

const PAGE = {
  has_more: false,
  current_thread: { thread_id: 'th-1', title: 'Samba share setup', status: 'open' },
  turns: [
    {
      turn_id: 't-1',
      thread_id: 'th-1',
      timestamp: 1_784_000_000,
      origin: 'human',
      user: { message_id: 1, content: 'is samba running?', timestamp: 1_784_000_000, status: 'complete' },
      assistant: { message_id: 2, content: 'smbd is active.', timestamp: 1_784_000_003, status: 'complete' },
      blocks: [],
      terminal_block_ids: [],
      diff_proposals: [],
    },
  ],
}

const EMPTY = { has_more: false, current_thread: null, turns: [] }

function routeFetch(timeline: unknown, events: Array<Record<string, unknown>> = []) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = String(url)
    if (path.includes('/api/agent/message')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
    }
    if (path.includes('/api/agent/timeline')) {
      return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => timeline })
    }
    if (path.includes('/api/discoveries/mentionables')) {
      return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => ({ mentionables: [] }) })
    }
    // Identity (HostGreeting) and anything else: the backend is "starting".
    return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('AgentChat', () => {
  beforeEach(() => {
    // jsdom has no layout; the auto-scroll effect must not throw.
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => vi.unstubAllGlobals())

  it('renders the stored conversation with the current topic pinned', async () => {
    routeFetch(PAGE)
    render(<AgentChat />)

    await screen.findByRole('feed')
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.getByText('smbd is active.')).toBeInTheDocument()
    expect(screen.getByTestId('current-topic')).toHaveTextContent('Samba share setup')

    // The greeting is the empty state only.
    expect(screen.queryByText(/Reading my own vitals|cannot read my own vitals/)).not.toBeInTheDocument()
  })

  it('has no conversation dropdown, no New Conversation, no session footer', async () => {
    routeFetch(PAGE)
    render(<AgentChat />)
    await screen.findByRole('feed')

    expect(screen.queryByText('New Conversation')).not.toBeInTheDocument()
    expect(screen.queryByTitle('New conversation')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Session:/)).not.toBeInTheDocument()
  })

  it('greets when the timeline is empty and nothing is in flight', async () => {
    routeFetch(EMPTY)
    render(<AgentChat />)

    await waitFor(() =>
      expect(screen.getByText(/Reading my own vitals|cannot read my own vitals/)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('feed')).not.toBeInTheDocument()
    expect(screen.queryByTestId('current-topic')).not.toBeInTheDocument()
  })

  it('does not greet when the stored conversation could not be reached', async () => {
    // Every route answers 503 — the backend is mid-restart. `turns` lands
    // empty for a reason that is not "nothing has ever been said", and
    // greeting here would print a first-contact card over a real history.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) }),
      ),
    )
    render(<AgentChat />)

    // The greeting shows its own text the moment it mounts (loading or
    // error), so polling for it is a real "it never appeared".
    await expect(
      screen.findByText(/Reading my own vitals|cannot read my own vitals/, {}, { timeout: 300 }),
    ).rejects.toThrow()
    expect(screen.getByPlaceholderText(/^Ask Halbert/)).toBeInTheDocument()
  })

  it('keeps a proposed change actionable until the admin decides', async () => {
    routeFetch(PAGE, [
      {
        type: 'diff_proposal',
        session_id: 's',
        timestamp: 0,
        diff_id: 'd-1',
        file_path: '/etc/samba/smb.conf',
        new_content: 'guest ok = no',
        additions: 1,
        deletions: 0,
      },
      { type: 'response_complete', session_id: 's', timestamp: 0, content: 'Ready when you are.' },
    ])
    render(<AgentChat />)
    await screen.findByRole('feed')

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'lock down guest access{Enter}')

    // The turn is waiting on the admin, so it stays live and Apply/Reject
    // stay wired — not the stored turn's read-only "proposed".
    const apply = await screen.findByRole('button', { name: /Apply/ })
    expect(screen.queryByText('proposed')).not.toBeInTheDocument()

    await userEvent.click(apply)

    // Decided: the turn folds into the timeline, recorded as applied.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Apply/ })).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Applied')).toBeInTheDocument()
    expect(screen.getByRole('feed')).toHaveTextContent('lock down guest access')
  })

  it('the thread chip shows its match terms and a click loads the timeline around the recalled turn', async () => {
    const fetchMock = routeFetch(PAGE, [
      {
        type: 'thread_recalled',
        session_id: 's',
        timestamp: 0,
        thread_id: 'th-0',
        title: 'ZFS scrub',
        date: '2026-07-14',
        match_terms: ['zfs'],
        mode: 'auto',
        last_turn_id: 't-7',
      },
      { type: 'response_complete', session_id: 's', timestamp: 0, content: 'It did.' },
    ])
    render(<AgentChat />)
    await screen.findByRole('feed')

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'did that scrub work?{Enter}')

    const chip = await screen.findByRole('button', { name: 'earlier subject: pulled in: ZFS scrub · 2026-07-14' })
    expect(chip).toHaveAttribute('title', 'matched: zfs')

    await userEvent.click(chip)

    await waitFor(() =>
      expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain('/api/agent/timeline?around=t-7&limit=50'),
    )
  })

  it('does not swallow a turn sent while the timeline sits on an earlier window', async () => {
    const fetchMock = routeFetch(PAGE, [
      {
        type: 'thread_recalled',
        session_id: 's',
        timestamp: 0,
        thread_id: 'th-0',
        title: 'ZFS scrub',
        date: '2026-07-14',
        match_terms: ['zfs'],
        mode: 'auto',
        last_turn_id: 't-7',
      },
      { type: 'response_complete', session_id: 's', timestamp: 0, content: 'It did.' },
    ])
    render(<AgentChat />)
    await screen.findByRole('feed')

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'did that scrub work?{Enter}')
    await userEvent.click(
      await screen.findByRole('button', { name: 'earlier subject: pulled in: ZFS scrub · 2026-07-14' }),
    )
    // The page is now a historical window, not the tail.
    await screen.findByRole('button', { name: 'Back to latest' })

    const tailLoads = () =>
      fetchMock.mock.calls.map(([url]) => String(url)).filter((u) => u === '/api/agent/timeline?limit=50').length
    const before = tailLoads()

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'and the pool?{Enter}')

    // appendLive is a no-op on an anchored window, so the finished turn
    // would simply vanish. Returning to the tail is what puts it back.
    await waitFor(() => expect(tailLoads()).toBeGreaterThan(before))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Back to latest' })).not.toBeInTheDocument(),
    )
  })
})
