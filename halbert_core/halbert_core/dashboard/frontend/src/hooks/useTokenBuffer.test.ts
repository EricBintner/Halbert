// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useTokenBuffer — the frame-rate cap on streaming text.
 *
 * LLMs emit tokens far faster than the screen paints, and writing each one
 * to React state as it arrives costs one re-render (and one growing-string
 * concatenation) per token — O(n²) across a reply. The buffer parks chunks
 * in a ref and commits them at most once per animation frame, so a 2000-token
 * reply costs ~60 renders instead of 2000, with one immediate flush at stream
 * end so the tail is never lost waiting on a frame that never comes.
 *
 * These tests pin the three properties that make that safe:
 *  - at most one commit per frame, however many chunks arrive;
 *  - nothing lost when the stream ends (or is replaced) before a frame fires;
 *  - the pending frame is cancelled on unmount, clear and set, so no state
 *    update lands on a component that is gone or a turn that is over.
 *
 * requestAnimationFrame is stubbed with a manual frame loop: jsdom's real
 * one runs on a timer the tests do not control, and the whole point is to
 * decide here when a frame does and does not fire.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTokenBuffer } from './useTokenBuffer'
import { useAgentStream } from './useAgentStream'

/**
 * A manual animation-frame loop.
 *
 * `fire()` runs everything scheduled exactly once and empties the queue —
 * one rendered frame. Callbacks a test never fires stand for a frame that
 * has not happened yet.
 */
function stubFrames() {
  const pending = new Map<number, FrameRequestCallback>()
  const request = vi.fn((cb: FrameRequestCallback) => {
    const handle = pending.size + 1
    pending.set(handle, cb)
    return handle
  })
  const cancel = vi.fn((handle: number) => {
    pending.delete(handle)
  })
  vi.stubGlobal('requestAnimationFrame', request)
  vi.stubGlobal('cancelAnimationFrame', cancel)
  return {
    cancel,
    fire: () => {
      const callbacks = [...pending.values()]
      pending.clear()
      for (const callback of callbacks) callback(16)
    },
    scheduled: () => pending.size,
  }
}

describe('useTokenBuffer — one commit per frame', () => {
  let frames: ReturnType<typeof stubFrames>

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    frames = stubFrames()
  })

  it('schedules a single frame for any number of chunks in that frame', () => {
    const { result } = renderHook(() => useTokenBuffer())

    act(() => {
      result.current.push('H')
      result.current.push('e')
      result.current.push('ll')
      result.current.push('o')
    })

    // However many chunks arrived, there is exactly one frame in flight —
    // the frame IS the render, so two would mean two renders.
    expect(frames.scheduled()).toBe(1)
    // And the chunks are not on screen before it fires.
    expect(result.current.value).toBe('')

    act(() => frames.fire())

    expect(result.current.value).toBe('Hello')
    expect(frames.scheduled()).toBe(0)
  })

  it('schedules a fresh frame for chunks that arrive after one fired', () => {
    const { result } = renderHook(() => useTokenBuffer())

    act(() => {
      result.current.push('one')
      frames.fire()
      result.current.push('two')
    })
    expect(frames.scheduled()).toBe(1)
    expect(result.current.value).toBe('one')

    act(() => frames.fire())

    expect(result.current.value).toBe('onetwo')
  })
})

describe('useTokenBuffer — nothing is lost at stream end', () => {
  let frames: ReturnType<typeof stubFrames>

  beforeEach(() => {
    frames = stubFrames()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('commits immediately when the frame has not fired yet', () => {
    const { result } = renderHook(() => useTokenBuffer())

    act(() => {
      result.current.push('tail ')
      result.current.push('text')
      // The stream ends before any frame fires.
      result.current.flush()
    })

    expect(result.current.value).toBe('tail text')
    // The pending frame was cancelled, not left to fire twice.
    expect(frames.cancel).toHaveBeenCalledTimes(1)
    expect(frames.scheduled()).toBe(0)

    // And draining frames afterwards cannot re-deliver anything.
    act(() => frames.fire())
    expect(result.current.value).toBe('tail text')
  })

  it('replaces the committed text and drops a still-pending frame', () => {
    const { result } = renderHook(() => useTokenBuffer())

    act(() => {
      result.current.push('streamed ')
      result.current.push('draft')
      result.current.set('final committed answer')
    })

    expect(result.current.value).toBe('final committed answer')
    expect(frames.cancel).toHaveBeenCalledTimes(1)

    // The draft chunks died with the frame that was cancelled.
    act(() => frames.fire())
    expect(result.current.value).toBe('final committed answer')
  })

  it('clear drops both the committed text and the buffered tail', () => {
    const { result } = renderHook(() => useTokenBuffer())

    act(() => {
      result.current.push('committed')
      frames.fire()
      result.current.push('buffered')
      result.current.clear()
    })

    expect(result.current.value).toBe('')
    act(() => frames.fire())
    expect(result.current.value).toBe('')
  })
})

describe('useTokenBuffer — no state update after unmount', () => {
  let frames: ReturnType<typeof stubFrames>

  beforeEach(() => {
    frames = stubFrames()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('cancels a pending frame when the component unmounts', () => {
    const { result, unmount } = renderHook(() => useTokenBuffer())

    act(() => result.current.push('in flight'))
    expect(frames.scheduled()).toBe(1)

    unmount()

    expect(frames.cancel).toHaveBeenCalledTimes(1)
    expect(frames.scheduled()).toBe(0)
  })
})

/**
 * The seam the hook-level tests cannot see: useAgentStream is the only
 * consumer, and it must flush at stream end even when no frame ever fires —
 * jsdom aside, the browser can be backgrounded, its rAF throttled to zero,
 * while the stream still completes.
 */
describe('useAgentStream — tokens survive a stream that ends frameless', () => {
  beforeEach(() => {
    // A browser that never paints: rAF is scheduled and never called.
    const pending = new Map<number, FrameRequestCallback>()
    vi.stubGlobal(
      'requestAnimationFrame',
      vi.fn((cb: FrameRequestCallback) => {
        pending.set(pending.size + 1, cb)
        return pending.size
      }),
    )
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('answers with every streamed token flushed at stream end', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) =>
        String(url).includes('/api/agent/message')
          ? Promise.resolve({
              ok: true, status: 200, statusText: 'OK',
              body: sseBody([
                { type: 'response_chunk', session_id: 'turn-1', timestamp: 0, content: 'Hello' },
                { type: 'response_chunk', session_id: 'turn-1', timestamp: 0, content: ' world' },
                { type: 'response_complete', session_id: 'turn-1', timestamp: 0 },
              ]),
            })
          : Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) }),
      ),
    )
    const { result } = renderHook(() => useAgentStream())
    await act(async () => {
      await result.current.sendMessage('hi')
    })

    expect(result.current.isStreaming).toBe(false)
    // No frame ever fired; nothing may be lost waiting on one.
    expect(result.current.response).toBe('Hello world')
  })

  it('does not carry buffered text from a cancelled turn into the next one', async () => {
    // First turn: one chunk arrives and the stream is held open — the chunk
    // sits in the buffer, uncommitted, when Stop is pressed.
    let call = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        const path = String(url)
        if (!path.includes('/api/agent/message')) {
          return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
        }
        call += 1
        return Promise.resolve({
          ok: true, status: 200, statusText: 'OK',
          body: call === 1 ? heldBody() : sseBody([
            { type: 'response_chunk', session_id: 'turn-2', timestamp: 0, content: 'fresh answer' },
            { type: 'response_complete', session_id: 'turn-2', timestamp: 0 },
          ]),
        })
      }),
    )
    const { result } = renderHook(() => useAgentStream())
    await act(async () => {
      await result.current.sendMessage('hi')
    })
    expect(result.current.isStreaming).toBe(true)
    // Stop flushes what was buffered, so the half-answer is not lost either.
    act(() => result.current.cancel())
    expect(result.current.response).toBe('Hello')

    await act(async () => {
      await result.current.sendMessage('again')
    })

    // The second turn's answer starts from a clean buffer: no leftover
    // 'Hello' prepended to it.
    expect(result.current.response).toBe('fresh answer')
  })
})

/** An SSE body that delivers one chunk, then never resolves: a held stream. */
function heldBody() {
  const chunk = new TextEncoder().encode(
    `data: ${JSON.stringify({ type: 'response_chunk', session_id: 'turn-1', timestamp: 0, content: 'Hello' })}\n`,
  )
  let sent = false
  return {
    getReader: () => ({
      read: async () => {
        if (sent) return new Promise<{ done: boolean; value?: undefined }>(() => {})
        sent = true
        return { done: false, value: chunk }
      },
    }),
  }
}

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