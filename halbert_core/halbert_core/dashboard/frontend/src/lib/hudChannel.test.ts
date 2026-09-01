// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * hudChannel — the BroadcastChannel relay for the floating voice HUD (P4).
 *
 * Covers the publish -> subscribe round-trip, stale/reordered message
 * dropping, publisher-restart recovery, malformed message guarding, and
 * the plain-browser no-op degradation.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  HUD_CHANNEL_NAME,
  createHudSpeechPublisher,
  isHudSpeechMessage,
  subscribeHudSpeech,
  type HudSpeechMessage,
} from './hudChannel'
import { FakeBroadcastChannel, installFakeBroadcastChannel } from '@/test/fakeBroadcastChannel'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

function segment(text: string): SpeechSegmentEvent {
  return { text, role: 'persona', prosody: { rate: 1, volume: 1, whisper: false } }
}

/** Post a raw payload straight onto the wire, bypassing the publisher —
 * for subscriber edge cases (reordering, malformed data, restarts). */
function injectRaw(payload: unknown): void {
  const injector = new FakeBroadcastChannel(HUD_CHANNEL_NAME)
  injector.postMessage(payload)
  injector.close()
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('hudChannel round-trip', () => {
  it('relays published speech to a subscriber', () => {
    installFakeBroadcastChannel()
    const received: HudSpeechMessage[] = []
    subscribeHudSpeech((message) => received.push(message))
    const publisher = createHudSpeechPublisher()

    publisher.publish({ segments: [segment('hello from the turn')], isActive: true })

    expect(received).toHaveLength(1)
    expect(received[0].segments).toEqual([segment('hello from the turn')])
    expect(received[0].isActive).toBe(true)
    expect(typeof received[0].instance).toBe('string')
    expect(received[0].instance).not.toBe('')
    expect(received[0].seq).toBe(1)
    publisher.close()
  })

  it('numbers a publisher’s messages monotonically', () => {
    installFakeBroadcastChannel()
    const received: HudSpeechMessage[] = []
    subscribeHudSpeech((message) => received.push(message))
    const publisher = createHudSpeechPublisher()

    publisher.publish({ segments: [], isActive: false })
    publisher.publish({ segments: [segment('second')], isActive: true })
    publisher.close()

    expect(received.map((m) => m.seq)).toEqual([1, 2])
  })
})

describe('hudChannel stale-message handling', () => {
  it('drops reordered messages that go backwards in seq', () => {
    installFakeBroadcastChannel()
    const received: HudSpeechMessage[] = []
    subscribeHudSpeech((message) => received.push(message))

    injectRaw({ instance: 'x', seq: 2, segments: [], isActive: true })
    injectRaw({ instance: 'x', seq: 1, segments: [], isActive: true })

    expect(received).toHaveLength(1)
    expect(received[0].seq).toBe(2)
  })

  it('resets the seq bar when the publishing window restarts', () => {
    installFakeBroadcastChannel()
    const received: HudSpeechMessage[] = []
    subscribeHudSpeech((message) => received.push(message))

    // The main window reloads: a fresh instance starts its seq over.
    injectRaw({ instance: 'a', seq: 5, segments: [], isActive: true })
    injectRaw({ instance: 'b', seq: 1, segments: [], isActive: false })

    expect(received).toHaveLength(2)
    expect(received[1].seq).toBe(1)
    expect(received[1].isActive).toBe(false)
  })

  it('ignores malformed messages without crashing', () => {
    installFakeBroadcastChannel()
    const received: HudSpeechMessage[] = []
    subscribeHudSpeech((message) => received.push(message))

    injectRaw('garbage')
    injectRaw(null)
    injectRaw({ instance: 'x' })
    injectRaw({ instance: 'x', seq: 'three', segments: [], isActive: true })
    injectRaw({ instance: 'x', seq: 1, segments: 'nope', isActive: true })

    expect(received).toHaveLength(0)
  })

  it('stops delivering after unsubscribe', () => {
    installFakeBroadcastChannel()
    const received: HudSpeechMessage[] = []
    const unsubscribe = subscribeHudSpeech((message) => received.push(message))

    unsubscribe()
    injectRaw({ instance: 'x', seq: 1, segments: [], isActive: true })

    expect(received).toHaveLength(0)
  })
})

describe('hudChannel browser degradation', () => {
  it('is a silent no-op when BroadcastChannel is unavailable', () => {
    vi.stubGlobal('BroadcastChannel', undefined)

    const received: HudSpeechMessage[] = []
    const publisher = createHudSpeechPublisher()
    const unsubscribe = subscribeHudSpeech((message) => received.push(message))

    expect(() => publisher.publish({ segments: [], isActive: true })).not.toThrow()
    expect(() => publisher.close()).not.toThrow()
    expect(() => unsubscribe()).not.toThrow()
    expect(received).toHaveLength(0)
  })
})

describe('isHudSpeechMessage', () => {
  it('accepts a well-formed message', () => {
    expect(
      isHudSpeechMessage({ instance: 'x', seq: 1, segments: [], isActive: false }),
    ).toBe(true)
  })

  it('rejects anything missing a field', () => {
    expect(isHudSpeechMessage(undefined)).toBe(false)
    expect(isHudSpeechMessage({ instance: 'x', seq: 1, segments: [] })).toBe(false)
    expect(isHudSpeechMessage({ instance: 'x', seq: 1, isActive: true })).toBe(false)
  })
})
