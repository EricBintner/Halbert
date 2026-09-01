// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useHudSpeech — the HUD window’s side of the hudChannel relay (P4).
 *
 * Subscribes to the main window’s speech-segment broadcasts for the life
 * of the component. Returns the freshest relayed message, or null before
 * the first message arrives — the HUD page renders nothing then, because
 * the companion pill is transient by design.
 */

import { useEffect, useState } from 'react'
import { subscribeHudSpeech, type HudSpeechMessage } from '@/lib/hudChannel'

export function useHudSpeech(): HudSpeechMessage | null {
  const [speech, setSpeech] = useState<HudSpeechMessage | null>(null)

  useEffect(() => {
    return subscribeHudSpeech((message) => setSpeech(message))
  }, [])

  return speech
}
