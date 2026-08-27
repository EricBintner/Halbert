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
import { useTimeline, dayKeyOf, dayLabel, groupByDay } from './useTimeline'
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

  it('survives a failed load with an empty timeline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend restarting')))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useTimeline())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.turns).toEqual([])
    expect(warn).toHaveBeenCalled()
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
