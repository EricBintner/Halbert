// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One conversation: AgentChat mounts the stored timeline and the current
 * topic label, and the dropdown / "New Conversation" / "Session:" footer
 * are gone. The greeting shows only when there is nothing to show. The
 * thread chip is a real control: its title says why it is here and a click
 * loads the timeline around the recalled thread's last turn.
 *
 * Three things this file also holds the line on, because each of them loses
 * something the admin can never get back by scrolling: a turn still parked
 * on an undecided change is folded into the transcript before the next
 * question replaces it; paging and chip jumps are not yanked back to the
 * newest message; and a timeline the page could not reach says so and can
 * be asked again.
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

/** The same newest page, with a page of history behind it. */
const PAGE_WITH_HISTORY = { ...PAGE, has_more: true }

/** What `before=t-1` answers with. */
const OLDER = {
  has_more: false,
  current_thread: PAGE.current_thread,
  turns: [
    {
      turn_id: 't-0',
      thread_id: 'th-1',
      timestamp: 1_783_900_000,
      origin: 'human',
      user: { message_id: -1, content: 'why is the disk full?', timestamp: 1_783_900_000, status: 'complete' },
      assistant: { message_id: -1, content: 'The journal grew.', timestamp: 1_783_900_004, status: 'complete' },
      blocks: [],
      terminal_block_ids: [],
      diff_proposals: [],
    },
  ],
}

const EMPTY = { has_more: false, current_thread: null, turns: [] }

/** What a proposed edit nobody has answered looks like on the wire. */
const PROPOSAL = {
  type: 'diff_proposal',
  session_id: 's',
  timestamp: 0,
  diff_id: 'd-1',
  file_path: '/etc/samba/smb.conf',
  new_content: 'guest ok = no',
  additions: 1,
  deletions: 0,
}

function routeFetch(
  timeline: unknown,
  // A plain list answers every turn the same way; a function is handed the
  // 0-based index of the message call, for tests that need two turns to
  // differ (a second `turn_persisted` with the same id would look like the
  // same turn to the append guard).
  events: Array<Record<string, unknown>> | ((call: number) => Array<Record<string, unknown>>) = [],
) {
  let call = 0
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const path = String(url)
    if (path.includes('/api/agent/message')) {
      const body = sseBody(typeof events === 'function' ? events(call++) : events)
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body })
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

/**
 * How many times the page has followed the conversation to the bottom.
 *
 * Two effects scroll: AgentChat's "follow the newest message"
 * (`{behavior: 'smooth'}`) and useTimeline's "centre the turn a chip jump
 * landed on" (`{block: 'center'}`). The options tell them apart, and only
 * the first one is allowed to undo the reader's own navigation.
 */
function smoothScrolls(): number {
  const spy = Element.prototype.scrollIntoView as unknown as { mock: { calls: unknown[][] } }
  return spy.mock.calls.filter(([opts]) => (opts as ScrollIntoViewOptions | undefined)?.behavior === 'smooth').length
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

  it('does not greet when the stored conversation could not be reached, and says so instead', async () => {
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
    // Silence would be indistinguishable from an empty conversation, and
    // the only way out would be restarting the app.
    expect(screen.getByText('Could not load the stored conversation')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/^Ask Halbert/)).toBeInTheDocument()
  })

  it('can be asked to fetch the stored conversation again', async () => {
    let reachable = false
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        const path = String(url)
        if (path.includes('/api/agent/timeline') && reachable) {
          return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => PAGE })
        }
        return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
      }),
    )
    render(<AgentChat />)

    const retry = await screen.findByRole('button', { name: 'Try again' })
    reachable = true
    await userEvent.click(retry)

    await screen.findByRole('feed')
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.queryByText('Could not load the stored conversation')).not.toBeInTheDocument()
  })

  it('keeps a proposed change actionable until the admin decides', async () => {
    routeFetch(PAGE, [
      PROPOSAL,
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

  it('keeps a turn parked on an undecided change when the next question replaces it', async () => {
    // The likeliest thing an admin does with a proposal they are not ready
    // for is ignore it and ask the next question. Sending starts a fresh
    // session, so the proposal is gone either way — but the exchange that
    // produced it must not go with it.
    routeFetch(PAGE, (call) => [
      PROPOSAL,
      { type: 'turn_persisted', session_id: 's', timestamp: 0, turn_id: `t-9${call}` },
      { type: 'response_complete', session_id: 's', timestamp: 0, content: 'Ready when you are.' },
    ])
    render(<AgentChat />)
    await screen.findByRole('feed')

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'lock down guest access{Enter}')
    await screen.findByRole('button', { name: /Apply/ })

    await userEvent.type(screen.getByPlaceholderText(/^Ask Halbert/), 'and the firewall?{Enter}')

    // The parked turn is in the transcript, proposal and all, recorded as
    // never decided rather than erased.
    await waitFor(() => expect(screen.getByRole('feed')).toHaveTextContent('lock down guest access'))
    expect(screen.getByRole('feed')).toHaveTextContent('Ready when you are.')
    expect(screen.getByRole('feed')).toHaveTextContent('/etc/samba/smb.conf')
    expect(screen.getAllByText('proposed').length).toBeGreaterThan(0)
  })

  it('does not scroll to the newest message when an earlier page is loaded', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        const path = String(url)
        if (path.includes('/api/agent/timeline?before=')) {
          return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => OLDER })
        }
        if (path.includes('/api/agent/timeline')) {
          return Promise.resolve({ ok: true, status: 200, text: async () => '', json: async () => PAGE_WITH_HISTORY })
        }
        return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
      }),
    )
    render(<AgentChat />)
    await screen.findByRole('feed')
    await waitFor(() => expect(smoothScrolls()).toBeGreaterThan(0))

    const before = smoothScrolls()
    await userEvent.click(screen.getByRole('button', { name: 'Load earlier' }))
    await screen.findByText('why is the disk full?')

    // "Load earlier" is a request to read what is above; answering it by
    // scrolling to the bottom is answering a different question.
    expect(smoothScrolls()).toBe(before)
  })

  it('leaves a chip jump where it landed instead of scrolling back to the newest message', async () => {
    routeFetch(PAGE, [
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
    // Let the finished turn land first — that scroll is the right one.
    await waitFor(() => expect(screen.getByRole('feed')).toHaveTextContent('did that scrub work?'))

    const before = smoothScrolls()
    await userEvent.click(chip)
    await screen.findByRole('button', { name: 'Back to latest' })

    // useTimeline has centred the recalled turn; scrolling away from it is
    // exactly what the click asked not to happen.
    expect(smoothScrolls()).toBe(before)
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
