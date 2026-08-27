// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The stored conversation: first page on mount, older pages on demand, the
 * finished live turn appended, a jump to the window around one turn (the
 * thread chip) and back to the newest page, and everything grouped by
 * local day.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useTimeline, dayKeyOf, dayLabel, groupByDay, msUntilNextMidnight } from './useTimeline'
import type { TimelineTurn } from '@/types/timeline'

// Thu 16 Jul 2026, local noon. Dates are built with the local constructor so
// the day keys do not depend on the machine's zone.
const NOW = new Date(2026, 6, 16, 12, 0, 0)

function localMs(y: number, m: number, d: number, h = 9): number {
  return new Date(y, m - 1, d, h).getTime()
}

function turn(id: string, timestamp: number, text: string): TimelineTurn {
  return {
    turnId: id,
    threadId: 'th-1',
    timestamp,
    origin: 'human',
    user: { messageId: 1, content: text, timestamp, status: 'complete' },
    assistant: { messageId: 2, content: `re: ${text}`, timestamp: timestamp + 2000, status: 'complete' },
    blocks: [],
    terminalBlockIds: [],
    diffProposals: [],
  }
}

/**
 * A turn as `turnFromSession` folds it: the stream carries the turn id
 * (turn_persisted) but never the row ids, so both rows land at -1.
 */
function liveTurn(id: string, timestamp: number, text: string): TimelineTurn {
  return {
    ...turn(id, timestamp, text),
    user: { messageId: -1, content: text, timestamp, status: 'complete' },
    assistant: { messageId: -1, content: `re: ${text}`, timestamp: timestamp + 2000, status: 'complete' },
  }
}

function rawTurn(id: string, seconds: number, text: string) {
  return {
    turn_id: id,
    thread_id: 'th-1',
    timestamp: seconds,
    origin: 'human',
    user: { message_id: 1, content: text, timestamp: seconds, status: 'complete' },
    assistant: { message_id: 2, content: `re: ${text}`, timestamp: seconds + 2, status: 'complete' },
    blocks: [],
    terminal_block_ids: [],
    diff_proposals: [],
  }
}

function page(turns: unknown[], hasMore = false) {
  return {
    turns,
    has_more: hasMore,
    current_thread: { thread_id: 'th-1', title: 'Samba share setup', status: 'open' },
  }
}

function fetchPages(...bodies: unknown[]) {
  const fetchMock = vi.fn()
  for (const body of bodies) {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, text: async () => '', json: async () => body })
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('day grouping', () => {
  it('keys a timestamp by its local calendar day', () => {
    expect(dayKeyOf(localMs(2026, 7, 14, 23))).toBe('2026-07-14')
    expect(dayKeyOf(localMs(2026, 1, 3, 0))).toBe('2026-01-03')
  })

  it('labels today, yesterday, then absolute dates', () => {
    expect(dayLabel('2026-07-16', NOW)).toBe('Today')
    expect(dayLabel('2026-07-15', NOW)).toBe('Yesterday')
    expect(dayLabel('2026-07-14', NOW)).toBe('Tue, Jul 14')
    expect(dayLabel('2025-07-14', NOW)).toBe('Mon, Jul 14, 2025')
  })

  it('groups consecutive turns by day, oldest first', () => {
    const groups = groupByDay(
      [
        turn('a', localMs(2026, 7, 14, 9), 'one'),
        turn('b', localMs(2026, 7, 14, 17), 'two'),
        turn('c', localMs(2026, 7, 16, 8), 'three'),
      ],
      NOW,
    )
    expect(groups.map((g) => [g.dayKey, g.label, g.turns.length])).toEqual([
      ['2026-07-14', 'Tue, Jul 14', 2],
      ['2026-07-16', 'Today', 1],
    ])
  })

  it('measures the wait to the next local midnight', () => {
    expect(msUntilNextMidnight(new Date(2026, 6, 16, 23, 59, 30))).toBe(30_000)
    // Just after one midnight is a whole day short of the next (give or take
    // a DST hour, which is why this is a range and not an equality).
    const wholeDay = msUntilNextMidnight(new Date(2026, 6, 16, 0, 0, 0))
    expect(wholeDay).toBeGreaterThan(22 * 60 * 60 * 1000)
    expect(wholeDay).toBeLessThanOrEqual(25 * 60 * 60 * 1000)
    // A millisecond before the boundary the wait is a millisecond — the
    // shortest honest answer there is, and the reason the timer has to
    // re-arm from its own callback: a fire at 23:59:59.999 reads the day
    // that is already in state. (`Math.max(1, …)` never binds here; `next`
    // is the start of the following local day and is always after `now`.)
    expect(msUntilNextMidnight(new Date(2026, 6, 16, 23, 59, 59, 999))).toBe(1)
  })
})

describe('useTimeline', () => {
  it('loads the first page on mount and exposes the current thread', async () => {
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two')]))

    const { result } = renderHook(() => useTimeline())

    await waitFor(() => expect(result.current.turns).toHaveLength(2))
    expect(fetchMock.mock.calls[0][0]).toBe('/api/agent/timeline?limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2'])
    expect(result.current.hasMore).toBe(false)
    expect(result.current.loading).toBe(false)
    expect(result.current.currentThread?.title).toBe('Samba share setup')
    expect(result.current.byDay).toHaveLength(1)
    expect(result.current.loadFailed).toBe(false)
  })

  it('loadOlder pages backwards from the oldest turn and prepends', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-2', 1_784_000_100, 'two'), rawTurn('t-3', 1_784_000_200, 'three')], true),
      page([rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two')], false),
    )

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(2))
    expect(result.current.hasMore).toBe(true)

    await act(async () => {
      await result.current.loadOlder()
    })

    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline?before=t-2&limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2', 't-3'])
    expect(result.current.hasMore).toBe(false)
  })

  it('loadOlder is a no-op when there is nothing older', async () => {
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')], false))
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      await result.current.loadOlder()
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('appendLive appends a new turn and replaces one with the same id', async () => {
    fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')]))
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    act(() => {
      result.current.appendLive(turn('live-1', Date.now(), 'draft'))
    })
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 'live-1'])

    act(() => {
      result.current.appendLive(turn('live-1', Date.now(), 'final'))
    })
    expect(result.current.turns).toHaveLength(2)
    expect(result.current.turns[1].user?.content).toBe('final')
    expect(result.current.byDay[result.current.byDay.length - 1].label).toBe('Today')
  })

  it('survives a failed load with an empty timeline, and says so via loadFailed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend restarting')))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useTimeline())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.turns).toEqual([])
    expect(warn).toHaveBeenCalled()
    // An empty timeline because the fetch never came back must be
    // distinguishable from an empty timeline because there is truly no
    // history yet — otherwise a restart-timed request shows the "we have
    // never spoken" greeting over a real stored conversation.
    expect(result.current.loadFailed).toBe(true)
  })

  it('clears loadFailed once a later load succeeds', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('backend restarting'))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        text: async () => '',
        json: async () => page([rawTurn('t-1', 1_784_000_000, 'one')]),
      })
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.loadFailed).toBe(true))

    await act(async () => {
      await result.current.loadLatest()
    })

    expect(result.current.loadFailed).toBe(false)
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1'])
  })

  it('loadAround replaces the page with the window around a turn and scrolls to it', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
      page(
        [rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two'), rawTurn('t-3', 1_784_000_200, 'three')],
        true,
      ),
    )
    // jsdom has no layout: record which element was asked to scroll.
    const scrolled: Element[] = []
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled.push(this)
    }
    const article = document.createElement('article')
    article.setAttribute('data-turn-id', 't-2')
    document.body.appendChild(article)

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))
    expect(result.current.anchored).toBe(false)

    await act(async () => {
      await result.current.loadAround('t-2')
    })

    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline?around=t-2&limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2', 't-3'])
    expect(result.current.hasMore).toBe(true)
    expect(result.current.anchored).toBe(true)
    expect(scrolled).toEqual([article])
    article.remove()
  })

  it('appendLive is a no-op while anchored on a historical window', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
      page([rawTurn('t-1', 1_784_000_000, 'one'), rawTurn('t-2', 1_784_000_100, 'two')], true),
    )
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      await result.current.loadAround('t-1')
    })
    expect(result.current.anchored).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    // A turn finishes streaming elsewhere in the app while this window is
    // open on an old day; splicing it onto the tail of an unrelated
    // historical page would be a false ordering, so it is dropped here —
    // it is already persisted and comes back on loadLatest.
    act(() => {
      result.current.appendLive(turn('live-1', Date.now(), 'draft'))
    })

    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-2'])
  })

  it('reads a just-appended turn\'s row ids back off the server', async () => {
    // "Forget this" redacts by ROW id, and the stream never carries one: a
    // turn folded out of the live block has -1 on both rows, so the control
    // was missing on the one turn an admin has just had — exactly when
    // someone realises what they pasted. The turn id it does carry is enough
    // to ask the store what it wrote.
    const stored = rawTurn('t-9', 1_784_000_900, 'server copy')
    stored.user.message_id = 41
    stored.assistant.message_id = 42
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')]), page([stored]))

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    act(() => {
      result.current.appendLive(liveTurn('t-9', Date.now(), 'paste of a secret'))
    })
    expect(result.current.turns[1].user?.messageId).toBe(-1)

    await waitFor(() => expect(result.current.turns[1].user?.messageId).toBe(41))
    expect(result.current.turns[1].assistant?.messageId).toBe(42)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/agent/timeline?around=t-9&limit=1')

    // The ids and nothing else: what stays on screen is still the copy the
    // page watched happen, not a re-read of the row.
    expect(result.current.turns[1].user?.content).toBe('paste of a secret')
    expect(result.current.turns[1].assistant?.content).toBe('re: paste of a secret')
    // And a one-turn read must not disturb the page it was read into.
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-1', 't-9'])
    expect(result.current.hasMore).toBe(false)
    expect(result.current.loading).toBe(false)
    expect(result.current.currentThread?.title).toBe('Samba share setup')
  })

  it('takes the ids the store has even when a row is not written yet', async () => {
    // Stop pressed: `begin_turn` wrote the user row before the model was
    // called, `end_turn` has not written the reply yet. The row that exists
    // is still named, so the words the admin wants gone can go.
    const stored = { ...rawTurn('t-9', 1_784_000_900, 'server copy'), assistant: null }
    stored.user.message_id = 41
    fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')]), page([stored]))

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    act(() => {
      result.current.appendLive(liveTurn('t-9', Date.now(), 'paste of a secret'))
    })

    await waitFor(() => expect(result.current.turns[1].user?.messageId).toBe(41))
    expect(result.current.turns[1].assistant?.messageId).toBe(-1)
    expect(result.current.turns[1].assistant?.content).toBe('re: paste of a secret')
  })

  it('asks for nothing when the store never confirmed the turn', async () => {
    // `local-…` is this page's own id (thread_store_error): the server has
    // never heard of it, so asking would be a guaranteed empty round trip.
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')]))
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      result.current.appendLive(liveTurn('local-sess-1', Date.now(), 'nowhere'))
      await Promise.resolve()
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.current.turns[1].user?.messageId).toBe(-1)
  })

  it('asks for nothing when the turn already knows its row ids', async () => {
    const fetchMock = fetchPages(page([rawTurn('t-1', 1_784_000_000, 'one')]))
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      result.current.appendLive(turn('t-9', Date.now(), 'already stored'))
      await Promise.resolve()
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('relabels the day dividers when the page is left open across midnight', async () => {
    // `byDay` is memoised on the turns, so a page nobody touches kept
    // yesterday's "Today" over today's turns until the list next changed.
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date(2026, 6, 16, 23, 59, 30))
      const seconds = Math.floor(new Date(2026, 6, 16, 9, 0).getTime() / 1000)
      fetchPages(page([rawTurn('t-1', seconds, 'one')]))

      const { result } = renderHook(() => useTimeline())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Today'])

      // Thirty seconds later it is tomorrow, and nothing has touched the
      // turn list — the labels have to correct themselves.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(31_000)
      })
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Yesterday'])

      // And again the next night, from the same single re-armed timer.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(24 * 60 * 60 * 1000)
      })
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Thu, Jul 16'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps relabelling after a timer that fires a millisecond early', async () => {
    // The timer is armed for the milliseconds remaining to midnight, and a
    // browser is not obliged to be late: a backwards clock step near the
    // boundary (an NTP correction) moves the deadline under a timer that is
    // already pending, and it fires at 23:59:59.999. The day key it reads
    // there is the one already in state, React bails out of that write, and
    // anything that re-arms BECAUSE the day changed stops re-arming — the
    // dividers freeze on "Today" for as long as the page is open.
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date(2026, 6, 16, 23, 59, 30))
      const seconds = Math.floor(new Date(2026, 6, 16, 9, 0).getTime() / 1000)
      fetchPages(page([rawTurn('t-1', seconds, 'one')]))

      const { result } = renderHook(() => useTimeline())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Today'])

      // The clock steps back one millisecond: the timer armed for midnight
      // now lands just short of it, at 23:59:59.999...
      vi.setSystemTime(new Date(2026, 6, 16, 23, 59, 29, 999))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000)
      })
      // ...where it is still the 16th, so the write is the day already in
      // state and nothing on screen changes. This is the moment the old
      // timer chain ended.
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Today'])

      // One millisecond later it really is tomorrow. The label can only
      // follow if that early callback armed the next timer itself, rather
      // than waiting for a day key that never changed.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1)
      })
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Yesterday'])

      // And the chain survived it: the following night still lands.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(24 * 60 * 60 * 1000)
      })
      expect(result.current.byDay.map((d) => d.label)).toEqual(['Thu, Jul 16'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('asks a second time for a row the store had not written yet', async () => {
    // Stop, from the store's side: `begin_turn` wrote the user row before
    // the model was called and `end_turn` writes the reply as the turn
    // unwinds — after the page has already read the turn back. With a
    // single read that reply row keeps -1 until an unrelated page load, and
    // "Forget this" can only forget half of the one turn someone pressed
    // Stop because of.
    vi.useFakeTimers()
    try {
      const halfWritten = { ...rawTurn('t-9', 1_784_000_900, 'server copy'), assistant: null }
      halfWritten.user.message_id = 41
      const whole = rawTurn('t-9', 1_784_000_900, 'server copy')
      whole.user.message_id = 41
      whole.assistant.message_id = 42
      const fetchMock = fetchPages(
        page([rawTurn('t-1', 1_784_000_000, 'one')]),
        page([halfWritten]),
        page([whole]),
      )

      const { result } = renderHook(() => useTimeline())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      act(() => {
        result.current.appendLive(liveTurn('t-9', Date.now(), 'paste of a secret'))
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(result.current.turns[1].user?.messageId).toBe(41)
      expect(result.current.turns[1].assistant?.messageId).toBe(-1)

      // A moment later the store has finished writing, and the page asks
      // again rather than waiting for a load nothing is going to schedule.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000)
      })
      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(fetchMock.mock.calls[2][0]).toBe('/api/agent/timeline?around=t-9&limit=1')
      expect(result.current.turns[1].assistant?.messageId).toBe(42)
      // Still the copy the page watched happen — the ids and nothing else.
      expect(result.current.turns[1].assistant?.content).toBe('re: paste of a secret')

      // Twice, not forever: a turn abandoned before `end_turn` has a reply
      // row that is never written, and polling for it has no end.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })
      expect(fetchMock).toHaveBeenCalledTimes(3)
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops asking once the second read still has nothing to add', async () => {
    // The reply row was never written (the turn was abandoned): the second
    // attempt answers with the same half-written turn and that is the end
    // of it, rather than a request every second and a half for as long as
    // the page is open.
    vi.useFakeTimers()
    try {
      const halfWritten = { ...rawTurn('t-9', 1_784_000_900, 'server copy'), assistant: null }
      halfWritten.user.message_id = 41
      const fetchMock = fetchPages(
        page([rawTurn('t-1', 1_784_000_000, 'one')]),
        page([halfWritten]),
        page([halfWritten]),
        page([halfWritten]),
      )

      const { result } = renderHook(() => useTimeline())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      act(() => {
        result.current.appendLive(liveTurn('t-9', Date.now(), 'paste of a secret'))
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })

      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(result.current.turns[1].assistant?.messageId).toBe(-1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('makes a failed retry a transition, not a silent rewrite of the same true', async () => {
    // "Try again" on the failure notice calls loadLatest, and the sentence
    // a screen reader hears is announced on the CHANGE of loadFailed. A
    // retry that fails while the flag is already true writes the same
    // value, React bails, and the admin who pressed the button hears
    // nothing at all — they cannot tell a failed retry from an unfinished
    // one.
    let refuseRetry: ((err: Error) => void) | null = null
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('backend restarting'))
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            refuseRetry = reject
          }),
      )
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.loadFailed).toBe(true))

    let retry!: Promise<boolean>
    await act(async () => {
      retry = result.current.loadLatest()
    })
    // The attempt is in flight: nothing is claiming a failure yet.
    expect(result.current.loadFailed).toBe(false)

    await act(async () => {
      refuseRetry!(new Error('still restarting'))
      await retry
    })

    // ...and the second failure is written again, which is a change and not
    // a re-write, so the notice is announced a second time.
    expect(result.current.loadFailed).toBe(true)
  })

  it('reports whether the page actually came back, so a retry can be spoken', async () => {
    // The failure half of "Try again" is a state flag, which works because
    // failing is a change. Succeeding is not: the page fills with turns,
    // which is not something a screen reader reads out, and `loadFailed`
    // going false happens at the START of every attempt rather than at the
    // end of a good one. So the outcome has to be in the answer, or the only
    // caller that has to say something has nothing to say it from.
    const good = page([rawTurn('t-9', 1_784_000_900, 'nine')])
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('backend restarting'))
      .mockRejectedValueOnce(new Error('still restarting'))
      .mockResolvedValueOnce({ ok: true, status: 200, text: async () => '', json: async () => good })
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.loadFailed).toBe(true))

    // A retry that fails is false — announcing a load here would contradict
    // the failure sentence said in the same breath.
    let failed!: boolean
    await act(async () => {
      failed = await result.current.loadLatest()
    })
    expect(failed).toBe(false)
    expect(result.current.loadFailed).toBe(true)

    // A retry that works is true, and the turns really did arrive.
    let loaded!: boolean
    await act(async () => {
      loaded = await result.current.loadLatest()
    })
    expect(loaded).toBe(true)
    expect(result.current.loadFailed).toBe(false)
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-9'])
  })

  it('loadLatest returns to the newest page and clears the anchor', async () => {
    const fetchMock = fetchPages(
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
      page([rawTurn('t-2', 1_784_000_100, 'two')], true),
      page([rawTurn('t-9', 1_784_000_900, 'nine')], true),
    )
    const { result } = renderHook(() => useTimeline())
    await waitFor(() => expect(result.current.turns).toHaveLength(1))

    await act(async () => {
      await result.current.loadAround('t-2')
    })
    expect(result.current.anchored).toBe(true)

    await act(async () => {
      await result.current.loadLatest()
    })

    expect(fetchMock.mock.calls[2][0]).toBe('/api/agent/timeline?limit=50')
    expect(result.current.turns.map((t) => t.turnId)).toEqual(['t-9'])
    expect(result.current.anchored).toBe(false)
  })
})
