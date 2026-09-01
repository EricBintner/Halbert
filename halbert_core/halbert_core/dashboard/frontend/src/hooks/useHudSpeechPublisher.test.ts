// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useHudSpeechPublisher — the main window’s side of the hudChannel relay.
 *
 * The publisher must publish on change, keep late-joining HUD windows
 * caught up via the heartbeat, and park the relay as inactive when the
 * conversation surface unmounts (so no stale “speaking” pill floats).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useHudSpeechPublisher } from './useHudSpeechPublisher'
import { subscribeHudSpeech, type HudSpeechMessage } from '@/lib/hudChannel'
import { installFakeBroadcastChannel } from '@/test/fakeBroadcastChannel'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

function segment(text: string): SpeechSegmentEvent {
  return { text, role: 'persona', prosody: { rate: 1, volume: 1, whisper: false } }
}

let received: HudSpeechMessage[]

function collector(): void {
  received = []
  subscribeHudSpeech((message) => received.push(message))
}

beforeEach(() => {
  installFakeBroadcastChannel()
  collector()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function lastState(): HudSpeechMessage | undefined {
  return received[received.length - 1]
}

describe('useHudSpeechPublisher', () => {
  it('publishes the live speech state on mount and on change', () => {
    const { rerender } = renderHook(
      ({ segments, isActive }) => useHudSpeechPublisher(segments, isActive),
      { initialProps: { segments: [segment('first')], isActive: true } },
    )

    expect(lastState()).toMatchObject({ segments: [segment('first')], isActive: true })

    rerender({ segments: [segment('first'), segment('second')], isActive: true })

    expect(lastState()).toMatchObject({
      segments: [segment('first'), segment('second')],
      isActive: true,
    })

    rerender({ segments: [segment('first'), segment('second')], isActive: false })

    expect(lastState()).toMatchObject({ isActive: false })
  })

  it('re-publishes on the heartbeat so a late-joining HUD catches up', () => {
    const segments = [segment('hello')]
    renderHook(() => useHudSpeechPublisher(segments, true))

    const before = received.length
    act(() => {
      vi.advanceTimersByTime(1000)
    })

    // BroadcastChannel has no replay: without the heartbeat, a HUD window
    // summoned mid-turn would see nothing until the next segment arrives.
    expect(received.length).toBeGreaterThan(before)
    expect(lastState()).toMatchObject({ segments: [segment('hello')], isActive: true })
  })

  it('publishes a final inactive state and closes on unmount', () => {
    const { unmount } = renderHook(() =>
      useHudSpeechPublisher([segment('last words')], true),
    )

    expect(lastState()?.isActive).toBe(true)

    unmount()

    expect(lastState()).toMatchObject({ segments: [], isActive: false })

    // The channel is closed: no further posts arrive, even past a beat.
    const countAfterUnmount = received.length
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(received.length).toBe(countAfterUnmount)
  })

  it('never throws when BroadcastChannel is unavailable', () => {
    vi.stubGlobal('BroadcastChannel', undefined)

    expect(() => {
      const { unmount } = renderHook(() =>
        useHudSpeechPublisher([segment('x')], true),
      )
      unmount()
    }).not.toThrow()
  })
})
