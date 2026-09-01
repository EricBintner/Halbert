// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useHudSpeechPublisher — the main window’s side of the hudChannel relay (P4).
 *
 * Mirrors the conversation’s live speech segments to the floating voice
 * HUD window — a separate webview/JS context whose own useAgentStream
 * sees no turn. Mounted from AgentChat, the pill’s data source, so the
 * relay publishes exactly what the in-conversation pill renders. No
 * useAgentStream refactor: the hook only reads what the destructure
 * already exposed.
 *
 * Publishes on every change AND on a low-frequency heartbeat, so a HUD
 * summoned mid-turn catches up within one beat (BroadcastChannel has no
 * replay). On unmount it publishes one final inactive state so the HUD
 * never floats a stale “speaking” pill after the conversation surface
 * goes away, then drops the channel.
 */

import { useEffect, useRef } from 'react'
import type { SpeechSegmentEvent } from '@/hooks/useAgentStream'
import { createHudSpeechPublisher, type HudSpeechPublisher } from '@/lib/hudChannel'

const HEARTBEAT_MS = 1000

const NO_SEGMENTS: SpeechSegmentEvent[] = []

export function useHudSpeechPublisher(segments: SpeechSegmentEvent[], isActive: boolean): void {
  const publisherRef = useRef<HudSpeechPublisher | null>(null)
  if (publisherRef.current === null) {
    publisherRef.current = createHudSpeechPublisher()
  }

  // Always publish the freshest state; the publish closure below must not
  // capture a stale snapshot.
  const latestRef = useRef({ segments, isActive })
  latestRef.current = { segments, isActive }

  useEffect(() => {
    publisherRef.current?.publish(latestRef.current)
  }, [segments, isActive])

  useEffect(() => {
    const heartbeat = setInterval(() => {
      publisherRef.current?.publish(latestRef.current)
    }, HEARTBEAT_MS)
    return () => clearInterval(heartbeat)
  }, [])

  useEffect(() => {
    return () => {
      // The surface is going away: park the relay as inactive so the HUD
      // shows no stale speaking pill, then drop the channel.
      publisherRef.current?.publish({ segments: NO_SEGMENTS, isActive: false })
      publisherRef.current?.close()
      publisherRef.current = null
    }
  }, [])
}
