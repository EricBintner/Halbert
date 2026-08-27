// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The stored conversation renders with roles: day dividers as headings with
 * a machine-readable date, one article per turn, static tool cards, an
 * "ended" chip for a terminal the store no longer has, and diffs that can
 * no longer be applied.
 */

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, it, expect, vi } from 'vitest'
import {
  Timeline,
  executionFromBlock,
  REDACTED,
  FORGET_FAILED,
  FORGET_NOT_STORED_YET,
  FORGET_PARTLY_FAILED,
} from './Timeline'
import { groupByDay } from '../../hooks/useTimeline'
import { lastAlert, lastAnnouncement } from '../../lib/announce'
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

    // The divider used to be a <header>; it is a plain element now (see the
    // feed-structure test below), so the selector asks for the divider, not
    // for the tag it happens to be made of.
    const times = Array.from(container.querySelectorAll('.thread-divider time')).map((t) => t.getAttribute('datetime'))
    expect(times).toEqual(['2026-07-14', '2026-07-16'])

    const articles = screen.getAllByRole('article')
    expect(articles).toHaveLength(2)
    expect(articles[0]).toHaveAttribute('data-turn-id', 't-1')
  })

  it('hangs every turn article directly off the feed, with its day divider in front of it', () => {
    const { container } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )
    const feed = screen.getByRole('feed')
    const articles = screen.getAllByRole('article')

    // ARIA's feed pattern expects the articles to be the feed's own
    // children: a <section> in between is a container the reader has to
    // account for, and it was a `region` landmark per day sitting inside
    // the conversation.
    articles.forEach((article) => expect(article.parentElement).toBe(feed))
    expect(container.querySelector('section')).toBeNull()

    // The dividers still render, still say the day out loud as a heading,
    // and still come in front of the turns they introduce.
    const children = Array.from(feed.children)
    const dividers = children.filter((el) => el.classList.contains('thread-divider'))
    expect(dividers.map((d) => d.querySelector('h2')?.textContent)).toEqual(['Tue, Jul 14', 'Today'])
    expect(children.indexOf(dividers[0])).toBe(children.indexOf(articles[0]) - 1)
    expect(children.indexOf(dividers[1])).toBe(children.indexOf(articles[1]) - 1)

    // A <header> that is no longer inside sectioning content is a `banner`
    // landmark — which would put one landmark per day inside the feed.
    expect(screen.queryByRole('banner')).toBeNull()

    // The one thing the <section> did that a heading does not: name the day
    // on the way INTO the group. Article-by-article navigation skips the
    // divider, so the first article of each day is described by that day's
    // heading — and only the first, or a fifty-turn day says "Today" fifty
    // times.
    const dayIds = dividers.map((d) => d.querySelector('h2')?.id)
    expect(dayIds.every((id) => typeof id === 'string' && id.length > 0)).toBe(true)
    expect(articles.map((a) => a.getAttribute('aria-describedby'))).toEqual(dayIds)
  })

  it('numbers the articles across the whole feed, and calls the set open while there is more', () => {
    // What role="feed" navigation announces is the position in the set. The
    // fixture is two turns on two different days, so a count that restarted
    // at each divider would read "1 of 2" twice.
    const { rerender } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )
    let articles = screen.getAllByRole('article')
    expect(articles.map((a) => a.getAttribute('aria-posinset'))).toEqual(['1', '2'])
    expect(articles.map((a) => a.getAttribute('aria-setsize'))).toEqual(['2', '2'])

    // While there are older pages the size is not known, and -1 is ARIA's
    // value for that. Announcing the loaded count instead would tell an
    // admin "2 of 2" in the middle of a six-month conversation — on the
    // paging path this whole feed exists for.
    rerender(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore loading={false} onLoadOlder={() => {}} />)
    articles = screen.getAllByRole('article')
    expect(articles.map((a) => a.getAttribute('aria-posinset'))).toEqual(['1', '2'])
    expect(articles.map((a) => a.getAttribute('aria-setsize'))).toEqual(['-1', '-1'])
  })

  it('names the feed for the machine when the page knows what it is called', () => {
    const { rerender } = render(
      <Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )
    // Nothing passed the name: the region still has one rather than none.
    expect(screen.getByRole('feed')).toHaveAttribute('aria-label', 'Conversation')

    rerender(
      <Timeline
        byDay={groupByDay(TURNS, NOW)}
        hasMore={false}
        loading={false}
        onLoadOlder={() => {}}
        displayName="Anvil"
      />,
    )
    // The name chosen in onboarding, never the DNS hostname.
    expect(screen.getByRole('feed')).toHaveAttribute('aria-label', 'Conversation with Anvil')
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

  it('lets a stored exit code win over the status beside it', () => {
    // The combination stored data actually holds: a run_command that ran and
    // failed. The executor returns the exit line as ordinary output rather
    // than raising (tools/executor.py:513), so the call is recorded
    // success=True (executor.py:369-374, state_machine.py:1853) while
    // _tool_block parses the real code back out — {status: 'success',
    // exit: 1}. Trusting the status here paints ✓ Success on a failed
    // `systemctl restart sshd`.
    expect(executionFromBlock(block({ status: 'success', exit: 1 }), 'f').status).toBe('error')
    expect(executionFromBlock(block({ status: 'success', exit: 127 }), 'f').status).toBe('error')
    // The same precedence must not flip a command that really did succeed.
    expect(executionFromBlock(block({ status: 'success', exit: 0 }), 'f').status).toBe('success')
  })

  it('reads the exit code on an older row that stored no status', () => {
    expect(executionFromBlock(block({ exit: 0 }), 'f').status).toBe('success')
    expect(executionFromBlock(block({ exit: 1 }), 'f').status).toBe('error')
    // exit is only ever set for run_command; unknown reads as success.
    expect(executionFromBlock(block({ exit: null }), 'f').status).toBe('success')
  })

  it("falls to the backend's own verdict when no exit code was stored", () => {
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

describe('Timeline — Forget this', () => {
  afterEach(() => vi.unstubAllGlobals())

  function redactFetch() {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '',
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  /** The control is guarded (it cannot be undone), so agreeing takes two clicks. */
  async function forget(opener: HTMLElement) {
    await userEvent.click(opener)
    await userEvent.click(screen.getByRole('button', { name: 'Yes, forget this turn' }))
  }

  it('asks before it forgets, and touches nothing when the answer is no', async () => {
    const fetchMock = redactFetch()
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    await userEvent.click(screen.getAllByRole('button', { name: 'Forget this turn' })[0])
    // The first click only opens the question: nothing is destroyed yet.
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Yes, forget this turn' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Cancel forgetting this turn' }))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Forget this turn' })).toHaveLength(2)
  })

  it('redacts both stored rows and replaces the turn with the marker', async () => {
    const fetchMock = redactFetch()
    render(<Timeline byDay={groupByDay(TURNS, NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    // Both fixture turns are stored (server ids 1/2 and 5), so both offer it.
    const buttons = screen.getAllByRole('button', { name: 'Forget this turn' })
    expect(buttons).toHaveLength(2)
    await forget(buttons[0])

    // The user words, the tool card and the assistant words — the same three
    // markers the next page load will read back off disk.
    await waitFor(() => expect(screen.getAllByText(REDACTED)).toHaveLength(3))
    const calls = fetchMock.mock.calls.map(([url, init]) => [String(url), (init as RequestInit).method])
    expect(calls).toEqual([
      ['/api/agent/message/1/redact', 'POST'],
      ['/api/agent/message/2/redact', 'POST'],
    ])
    expect(screen.queryByText('is samba running?')).not.toBeInTheDocument()
    expect(screen.queryByText('Answer to is samba running?')).not.toBeInTheDocument()
    expect(screen.queryByText('run_command')).not.toBeInTheDocument()
    // A forgotten tool call is not a successful one.
    expect(screen.queryByText('Success')).not.toBeInTheDocument()
    expect(screen.getByText('Forgotten')).toBeInTheDocument()
    // Terminal ids are not part of the redaction; the ended chip stays.
    expect(screen.getByText('terminal · ended')).toBeInTheDocument()
    // The row is never deleted: the article and its id remain.
    expect(screen.getAllByRole('article')[0]).toHaveAttribute('data-turn-id', 't-1')
    expect(screen.getAllByRole('button', { name: 'Forget this turn' })).toHaveLength(1)
    // The marker replaces text in place, which nothing reads out on its own.
    expect(lastAnnouncement()).toBe('Turn forgotten')
    // Nothing went wrong, so nothing on screen says anything did.
    expect(screen.queryByText(FORGET_FAILED)).not.toBeInTheDocument()
    expect(screen.queryByText(FORGET_PARTLY_FAILED)).not.toBeInTheDocument()
  })

  it('renders a stored marker block exactly as the clicked turn does', async () => {
    // What the server leaves on disk for a redacted row that had tool calls
    // (conversation_sqlite.redact_message) and hands back on the next load.
    const reloaded = turn('t-1', OLD, REDACTED, {
      user: { messageId: 1, content: REDACTED, timestamp: OLD, status: 'complete' },
      assistant: { messageId: 2, content: REDACTED, timestamp: OLD, status: 'complete' },
      blocks: [{ tool: REDACTED, args: {}, result: REDACTED, exit: null, redacted: true }],
    })
    render(<Timeline byDay={groupByDay([reloaded], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    expect(screen.getByText('Forgotten')).toBeInTheDocument()
    // The block has no exit code and no status, which is the shape that used
    // to fall through to the default and paint a green ✓ Success.
    expect(screen.queryByText('Success')).not.toBeInTheDocument()
    expect(screen.queryByText('✓')).not.toBeInTheDocument()
  })

  it('offers no control for rows without a server id, and keeps the turn when the server refuses', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, text: async () => 'locked', json: async () => ({}) }),
    )
    const local = turn('local-1', TODAY, 'not stored yet', {
      user: { messageId: -1, content: 'not stored yet', timestamp: TODAY, status: 'complete' },
      assistant: { messageId: -1, content: 'ok', timestamp: TODAY, status: 'complete' },
    })
    render(
      <Timeline byDay={groupByDay([TURNS[0], local], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )

    // The control that survives a HALF-landed redaction (above) must not be
    // loosened into this case: a turn the store never confirmed has nothing
    // on disk, so there is nothing to offer to scrub.
    const buttons = screen.getAllByRole('button', { name: 'Forget this turn' })
    expect(buttons).toHaveLength(1)
    expect(buttons[0].closest('article')).toHaveAttribute('data-turn-id', 't-1')

    await forget(buttons[0])
    await waitFor(() => expect(warn).toHaveBeenCalled())
    expect(screen.getByText('is samba running?')).toBeInTheDocument()
    expect(screen.queryByText(REDACTED)).not.toBeInTheDocument()
    // A console warning is invisible in the product; the admin is told.
    expect(lastAlert()).toBe(FORGET_FAILED)
    // And told ON SCREEN: a sighted admin sees no marker and no live region,
    // so without this the refusal is indistinguishable from a mis-click.
    expect(screen.getByText(FORGET_FAILED)).toBeInTheDocument()
  })

  it('marks only the rows that landed when the server refuses one of them', async () => {
    // The route answers 500 for a redaction that did not land in full
    // (routes/agent.py). Promise.all would abandon the sibling request and
    // report the whole turn unchanged while row 1 is already scrubbed.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).endsWith('/message/1/redact')
          ? { ok: true, status: 200, text: async () => '', json: async () => ({ ok: true }) }
          : { ok: false, status: 500, text: async () => 'Redaction failed', json: async () => ({}) },
      ),
    )
    render(<Timeline byDay={groupByDay([TURNS[0]], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    await forget(screen.getByRole('button', { name: 'Forget this turn' }))

    // Row 1 is scrubbed on disk, so the page says so...
    await waitFor(() => expect(screen.queryByText('is samba running?')).not.toBeInTheDocument())
    expect(screen.getAllByText(REDACTED)).toHaveLength(1)
    // ...and row 2 is not, so its words and its tool card still stand.
    expect(screen.getByText('Answer to is samba running?')).toBeInTheDocument()
    expect(screen.getByText('run_command')).toBeInTheDocument()
    expect(warn).toHaveBeenCalled()
    expect(lastAlert()).toBe(FORGET_PARTLY_FAILED)
    // Half a redaction is the worst thing to leave silent: the user bubble
    // reads as forgotten while the reply beside it is still stored, so the
    // reason is on screen and not only in the live region.
    expect(screen.getByText(FORGET_PARTLY_FAILED)).toBeInTheDocument()
    // The control stays, so the row that failed can be tried again.
    expect(screen.getByRole('button', { name: 'Forget this turn' })).toBeInTheDocument()
  })

  it('drops the visible failure when the turn is tried again', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const refused = { ok: false, status: 500, text: async () => 'locked', json: async () => ({}) }
    const agreed = { ok: true, status: 200, text: async () => '', json: async () => ({ ok: true }) }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(refused)
      .mockResolvedValueOnce(refused)
      .mockResolvedValue(agreed)
    vi.stubGlobal('fetch', fetchMock)
    render(<Timeline byDay={groupByDay([TURNS[0]], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    await forget(screen.getByRole('button', { name: 'Forget this turn' }))
    await waitFor(() => expect(screen.getByText(FORGET_FAILED)).toBeInTheDocument())

    // Asking again drops the stale verdict rather than leaving it beside a
    // question it has not answered yet...
    await userEvent.click(screen.getByRole('button', { name: 'Forget this turn' }))
    expect(screen.queryByText(FORGET_FAILED)).not.toBeInTheDocument()

    // ...and this time the store agrees, so nothing is left claiming it failed.
    await userEvent.click(screen.getByRole('button', { name: 'Yes, forget this turn' }))
    await waitFor(() => expect(screen.getAllByText(REDACTED)).toHaveLength(3))
    expect(screen.queryByText(FORGET_FAILED)).not.toBeInTheDocument()
  })

  it('keeps the control after a partial forget, and finishes once the store names the row', async () => {
    // The turn Stop leaves behind: the user row is stored and scrubbable,
    // the reply row has no id yet. Redacting the half that can be redacted
    // used to take the control away with it — `redactableIds` had nothing
    // left to offer — so the admin was left with a red line saying part of
    // their turn is still on disk and no way to finish. The id arrives a
    // moment later (useTimeline reads it back a second time); the button
    // has to still be there when it does.
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const fetchMock = redactFetch()
    const unnamedReply = {
      messageId: -1,
      content: 'Let me put that in',
      timestamp: TODAY,
      status: 'cancelled' as const,
    }
    const halfStored = turn('t-7', TODAY, 'my api key is hunter2', {
      user: { messageId: 41, content: 'my api key is hunter2', timestamp: TODAY, status: 'cancelled' },
      assistant: unnamedReply,
    })
    const { rerender } = render(
      <Timeline byDay={groupByDay([halfStored], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />,
    )

    await forget(screen.getByRole('button', { name: 'Forget this turn' }))
    await waitFor(() => expect(screen.getByText(FORGET_NOT_STORED_YET)).toBeInTheDocument())
    // The control survives the half-landing, beside the reason it did not
    // land in full.
    expect(screen.getByRole('button', { name: 'Forget this turn' })).toBeInTheDocument()

    // The store finishes writing the reply row and the page reads its id.
    rerender(
      <Timeline
        byDay={groupByDay([{ ...halfStored, assistant: { ...unnamedReply, messageId: 42 } }], NOW)}
        hasMore={false}
        loading={false}
        onLoadOlder={() => {}}
      />,
    )
    await forget(screen.getByRole('button', { name: 'Forget this turn' }))

    await waitFor(() => expect(screen.queryByText('Let me put that in')).not.toBeInTheDocument())
    // One row per POST, and the row that was already gone is not asked for
    // a second time.
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      '/api/agent/message/41/redact',
      '/api/agent/message/42/redact',
    ])
    expect(screen.getAllByText(REDACTED)).toHaveLength(2)
    // Nothing is left on disk now, so nothing is left to say or to press.
    expect(lastAnnouncement()).toBe('Turn forgotten')
    expect(screen.queryByText(FORGET_NOT_STORED_YET)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Forget this turn' })).not.toBeInTheDocument()
  })

  it('never calls a turn forgotten while one of its rows has no server id', async () => {
    // What Stop leaves on a turn the page has just folded in: `begin_turn`
    // stored the user row before the model was called, so it has an id and
    // can be scrubbed; `end_turn` has not written the reply row yet, so
    // there is nothing to send a redaction to. Redacting only what can be
    // redacted and then saying "Turn forgotten" would promise the admin
    // something the store never agreed to.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const fetchMock = redactFetch()
    const halfStored = turn('t-7', TODAY, 'my api key is hunter2', {
      user: { messageId: 41, content: 'my api key is hunter2', timestamp: TODAY, status: 'cancelled' },
      assistant: { messageId: -1, content: 'Let me put that in', timestamp: TODAY, status: 'cancelled' },
    })
    render(<Timeline byDay={groupByDay([halfStored], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    // The control is offered: one row CAN be forgotten, and it is the row
    // that holds what the admin regrets typing.
    await forget(screen.getByRole('button', { name: 'Forget this turn' }))

    // And the sentence names WHY, because the two reasons a redaction can
    // half-land need two different things from the admin: a row the server
    // refused will refuse again, a row with no id yet is one the store has
    // not finished writing.
    await waitFor(() => expect(screen.getByText(FORGET_NOT_STORED_YET)).toBeInTheDocument())
    expect(screen.queryByText(FORGET_PARTLY_FAILED)).not.toBeInTheDocument()
    expect(screen.queryByText('my api key is hunter2')).not.toBeInTheDocument()
    // The row that could not be reached is neither scrubbed on screen nor
    // claimed to be gone.
    expect(screen.getByText('Let me put that in')).toBeInTheDocument()
    expect(lastAlert()).toBe(FORGET_NOT_STORED_YET)
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual(['/api/agent/message/41/redact'])
    expect(warn).toHaveBeenCalled()
  })

  it('cannot be fired twice while the first redaction is in flight', async () => {
    let release: (() => void) | null = null
    const inFlight = new Promise<void>((resolve) => {
      release = resolve
    })
    const fetchMock = vi.fn(async () => {
      await inFlight
      return { ok: true, status: 200, text: async () => '', json: async () => ({ ok: true }) }
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Timeline byDay={groupByDay([TURNS[0]], NOW)} hasMore={false} loading={false} onLoadOlder={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Forget this turn' }))
    const yes = screen.getByRole('button', { name: 'Yes, forget this turn' })
    await userEvent.click(yes)
    expect(yes).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel forgetting this turn' })).toBeDisabled()

    release!()
    await waitFor(() => expect(screen.getAllByText(REDACTED)).toHaveLength(3))
    // One POST per row, not one per click.
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
