// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A turn that finished must not tell the backend it was cancelled.
 *
 * R11-01. The cleanup that aborts a live stream was keyed on `isStreaming`,
 * so React ran it on the true -> false transition — that is, on every normal
 * completion — with the captured `isStreaming === true`. Each finished turn
 * therefore aborted its own (already closed) stream and POSTed
 * /api/agent/cancel, which the backend can persist as a cancelled reply. The
 * abort belongs to unmount, and only to unmount.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useAgentStream } from './useAgentStream'

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

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type, session_id: 'turn-1', timestamp: 0, ...extra,
})

/** A turn that streams a reply and completes normally. */
const COMPLETED_TURN = [
  ev('session_started'),
  ev('state_change', { state: 'responding' }),
  ev('response_chunk', { chunk: 'the samba share is at /etc/samba' }),
  ev('response_complete', { response: 'the samba share is at /etc/samba' }),
  ev('session_ended'),
]

function trackedFetch(events: Array<Record<string, unknown>>) {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
    calls.push(String(url))
    return String(url).includes('/api/agent/message')
      ? Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
      : Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
  }))
  return calls
}

const cancels = (calls: string[]) => calls.filter((u) => u.includes('/api/agent/cancel'))

describe('useAgentStream — cancel is not sent for a turn that finished', () => {
  beforeEach(() => {
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('sends no cancel when a turn completes normally', async () => {
    const calls = trackedFetch(COMPLETED_TURN)
    const { result } = renderHook(() => useAgentStream())

    act(() => { result.current.sendMessage('where is the samba share') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    expect(cancels(calls)).toEqual([])
  })

  it('still sends exactly one cancel when unmounted mid-stream', async () => {
    // A stream that never ends, so the hook is still streaming at unmount.
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      calls.push(String(url))
      if (String(url).includes('/api/agent/message')) {
        return Promise.resolve({
          ok: true, status: 200, statusText: 'OK',
          body: {
            getReader: () => ({
              read: () => new Promise(() => {}),  // never resolves
            }),
          },
        })
      }
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
    }))

    const { result, unmount } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('a long one') })
    await waitFor(() => expect(result.current.isStreaming).toBe(true))

    unmount()
    expect(cancels(calls)).toHaveLength(1)
  })

  it('sends no cancel when unmounted with no turn in flight', async () => {
    const calls = trackedFetch(COMPLETED_TURN)
    const { unmount } = renderHook(() => useAgentStream())
    unmount()
    expect(cancels(calls)).toEqual([])
  })

  it('still sends a cancel when the user actually stops a turn', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      calls.push(String(url))
      if (String(url).includes('/api/agent/message')) {
        return Promise.resolve({
          ok: true, status: 200, statusText: 'OK',
          body: { getReader: () => ({ read: () => new Promise(() => {}) }) },
        })
      }
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
    }))

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('a long one') })
    await waitFor(() => expect(result.current.isStreaming).toBe(true))

    act(() => { result.current.cancel() })
    expect(cancels(calls)).toHaveLength(1)
  })
})
