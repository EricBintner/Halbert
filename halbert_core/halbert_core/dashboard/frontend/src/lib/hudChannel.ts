// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * hudChannel — the cross-window relay for the floating voice HUD (P4).
 *
 * Data-path choice (plan §6 Task P4 wrinkle, option a): the HUD is a
 * separate Tauri webview, so it is a *separate JS context* — its own
 * useAgentStream has no turn and can never see the main window’s speech
 * segments. Both windows load this same SPA from the same origin, so a
 * BroadcastChannel carries the main window’s live speech-segment state to
 * the HUD with no backend round-trip and no useAgentStream refactor: the
 * conversation surface (AgentChat) publishes via useHudSpeechPublisher,
 * the HUD page subscribes via useHudSpeech.
 *
 * Limits (deliberate, documented):
 *  - Speech is relayed only while the conversation surface is mounted;
 *    the HUD shows nothing when no surface is streaming.
 *  - BroadcastChannel has no replay: a HUD summoned mid-turn would miss
 *    earlier posts, so the publisher re-posts its latest state on a
 *    heartbeat as well as on every change.
 *  - Every message carries a per-window instance id and a monotonic seq.
 *    Subscribers drop stale/reordered messages and reset the seq bar when
 *    the instance changes (the main window reloaded while the HUD stayed
 *    up).
 *  - In a plain browser without BroadcastChannel the relay degrades to a
 *    silent no-op: publishing is a no-op, subscribing never fires.
 */

import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'

/** BroadcastChannel name shared by the publisher window and the HUD window. */
export const HUD_CHANNEL_NAME = 'halbert-voice-hud'

/** What the main window sends to the HUD window. */
export interface HudSpeechMessage {
  /** Per-page-load id of the publishing window. */
  instance: string
  /** Monotonic message number within the instance. */
  seq: number
  /** Live speech segments of the current turn (may be empty). */
  segments: SpeechSegmentEvent[]
  /** Whether the turn is streaming — the pill’s own `isActive` semantics. */
  isActive: boolean
}

/** The state a publisher pushes; the relay adds instance and seq. */
export interface HudSpeechState {
  segments: SpeechSegmentEvent[]
  isActive: boolean
}

type Listener = (message: HudSpeechMessage) => void

function channelAvailable(): boolean {
  return typeof window !== 'undefined' && typeof window.BroadcastChannel === 'function'
}

function makeInstanceId(): string {
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `hud-${Math.random().toString(36).slice(2)}`
}

/** Runtime shape guard: a malformed message is ignored, never crashed on. */
export function isHudSpeechMessage(value: unknown): value is HudSpeechMessage {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.instance === 'string' &&
    typeof v.seq === 'number' &&
    typeof v.isActive === 'boolean' &&
    Array.isArray(v.segments)
  )
}

export interface HudSpeechPublisher {
  publish(state: HudSpeechState): void
  close(): void
}

/**
 * Open the publishing side of the relay. The publisher keeps one channel
 * for its lifetime; BroadcastChannel never echoes to the posting context,
 * so a publisher never hears its own messages.
 */
export function createHudSpeechPublisher(): HudSpeechPublisher {
  if (!channelAvailable()) {
    return { publish: () => {}, close: () => {} }
  }
  const channel = new window.BroadcastChannel(HUD_CHANNEL_NAME)
  const instance = makeInstanceId()
  let seq = 0
  return {
    publish(state) {
      seq += 1
      const message: HudSpeechMessage = {
        instance,
        seq,
        segments: state.segments,
        isActive: state.isActive,
      }
      channel.postMessage(message)
    },
    close() {
      channel.close()
    },
  }
}

/**
 * Subscribe to the relay; returns an unsubscribe function. Stale and
 * malformed messages are dropped silently. Ordering follows `seq` within
 * one publishing instance and resets when the instance changes.
 */
export function subscribeHudSpeech(listener: Listener): () => void {
  if (!channelAvailable()) return () => {}
  const channel = new window.BroadcastChannel(HUD_CHANNEL_NAME)
  let lastInstance: string | null = null
  let lastSeq = 0
  channel.onmessage = (event: MessageEvent) => {
    const data = event.data
    if (!isHudSpeechMessage(data)) return
    if (data.instance !== lastInstance) {
      lastInstance = data.instance
      lastSeq = 0
    }
    if (data.seq <= lastSeq) return
    lastSeq = data.seq
    listener(data)
  }
  return () => {
    channel.onmessage = null
    channel.close()
  }
}
