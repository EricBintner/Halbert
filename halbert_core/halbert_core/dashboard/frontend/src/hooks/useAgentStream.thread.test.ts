// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Thread events on the agent stream (Plan A).
 *
 * The server owns thread identity; the hook only mirrors what it is told:
 * which subject the turn landed in, what earlier subject was pulled in (one
 * chip, never two, carrying the recalled thread's last turn id so the chip
 * can jump there; it expires when a new subject starts), and the persisted
 * turn id. A store failure is a warning, not an error state — the turn
 * still answers.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useAgentStream } from './useAgentStream'
import { terminalSessionStore as store } from './useTerminalSessions'

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

/** fetch that streams `events` for /api/agent/message and 200s anything else. */
function streamFetch(events: Array<Record<string, unknown>>) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes('/api/agent/message')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
    }
    return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type,
  session_id: 'turn-1',
  timestamp: 0,
  ...extra,
})

describe('useAgentStream — thread events', () => {
  beforeEach(() => {
    store.closeAll()
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('records the subject the server started and the persisted turn id', async () => {
    streamFetch([
      ev('turn_persisted', { thread_id: 'th-1', turn_id: 't-42' }),
      ev('thread_started', { thread_id: 'th-1', title: 'Samba share setup', reason: '' }),
      ev('response_chunk', { content: 'Hello' }),
      ev('response_complete', { content: 'Hello' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('set up a samba share', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session?.turnId).toBe('t-42')
    expect(result.current.session?.thread).toEqual({ threadId: 'th-1', title: 'Samba share setup' })
    expect(result.current.response).toBe('Hello')
  })

  it('keeps exactly one thread chip across repeated recalls', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: ['zfs'], mode: 'auto', last_turn_id: 't-3' }),
      ev('context_loaded', { source: 'file', label: '/etc/fstab', count: 1 }),
      ev('thread_recalled', { thread_id: 'th-9', title: 'WireGuard tunnel', date: '2026-07-02', match_terms: ['wg'], mode: 'tool', last_turn_id: 't-7' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('did that work?', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    const items = result.current.session!.contextItems
    const threadChips = items.filter((i) => i.source === 'thread')
    expect(threadChips).toHaveLength(1)
    expect(threadChips[0]).toMatchObject({
      id: 'thread:th-9',
      source: 'thread',
      label: 'pulled in: WireGuard tunnel · 2026-07-02',
      count: 1,
    })
    expect(items.some((i) => i.source === 'file')).toBe(true)
    expect(result.current.session?.recalled).toEqual({
      threadId: 'th-9',
      title: 'WireGuard tunnel',
      date: '2026-07-02',
      matchTerms: ['wg'],
      lastTurnId: 't-7',
    })
  })

  it('stores the recalled thread\'s last turn id, null when the server has none', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: ['zfs'], mode: 'auto' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('hi', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session?.recalled?.lastTurnId).toBeNull()
  })

  it('clears the chip when a new subject starts (the pulled-in thread expires with the paused one)', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: ['zfs'], mode: 'auto', last_turn_id: 't-3' }),
      ev('context_loaded', { source: 'file', label: '/etc/fstab', count: 1 }),
      ev('thread_started', { thread_id: 'th-2', title: 'Scanner share', reason: 'new subject' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('now something else', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session?.thread).toEqual({ threadId: 'th-2', title: 'Scanner share' })
    expect(result.current.session?.recalled).toBeNull()
    expect(result.current.session?.contextItems.map((i) => i.source)).toEqual(['file'])
  })

  it('dismissContextItem drops the chip and clears the recall', async () => {
    streamFetch([
      ev('thread_recalled', { thread_id: 'th-0', title: 'ZFS scrub', date: '2026-07-14', match_terms: [], mode: 'auto' }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('hi', 'turn-1')
    })
    await waitFor(() => expect(result.current.session?.recalled).not.toBeNull())

    act(() => {
      result.current.dismissContextItem('thread:th-0')
    })

    expect(result.current.session?.contextItems).toEqual([])
    expect(result.current.session?.recalled).toBeNull()
  })

  it('warns once on thread_store_error and leaves the session error untouched', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    streamFetch([
      ev('thread_store_error', { message: 'database is locked' }),
      ev('thread_store_error', { message: 'database is locked' }),
      ev('response_complete', { content: 'still answered' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('hi', 'turn-1')
    })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(warn).toHaveBeenCalledTimes(1)
    expect(result.current.session?.error).toBeNull()
    expect(result.current.session?.state).not.toBe('error')
  })

  it('reset() clears local state but never forgets the terminals a turn opened', async () => {
    streamFetch([
      ev('terminal_spawn', { terminal_session_id: 'term-1', command: 'journalctl -f', pid: 12 }),
      ev('terminal_output', { terminal_session_id: 'term-1', data: 'tick' }),
      ev('response_complete', { content: 'watching' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => {
      result.current.sendMessage('tail the journal', 'turn-1')
    })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(store.get('term-1')).toBeDefined()

    act(() => {
      result.current.reset()
    })

    expect(result.current.session).toBeNull()
    expect(result.current.response).toBe('')
    // One conversation: the tile from turn 1 outlives the hook's local state.
    expect(store.get('term-1')?.output).toBe('tick')
  })
})
