// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react'
import { AudioReactiveHalbertMark, type AudioReactiveHalbertMarkProps } from './AudioReactiveHalbertMark'
import type { VoiceVisualState } from './excitation'
import { createSpeechBurstSource } from './demo'
import type { AudioEnergySource } from './spectrum'

/** The kiosk conversation, as a loop: the ends withdraw while it listens,
 * a strum when it has understood, the contraction and travelling swellings
 * while it thinks, plucks while it speaks. */
export const VOICE_MODE_LOOP: readonly VoiceVisualState[] = [
  'listening',
  'recognized',
  'thinking',
  'speaking',
]

export interface VoiceModeLoopProps
  extends Omit<AudioReactiveHalbertMarkProps, 'state' | 'source'> {
  /** Time in each state. @default 2500 */
  intervalMs?: number
  /** Energy source; omitted -> the shared demo voice with a clap every few
   * seconds, the same one Storybook plays. `null` -> idle breathing. */
  source?: AudioEnergySource | null
  /** Called with each state as the loop enters it (including the first). */
  onStateChange?: (state: VoiceVisualState) => void
}

/**
 * The full Voice Mode cycle on one mark, for surfaces that show the mark
 * without a live conversation behind it: the marketing kiosk plate and the
 * Storybook loop story. One component, so the two can never drift apart.
 */
export function VoiceModeLoop({
  intervalMs = 2500,
  source,
  onStateChange,
  ...mark
}: VoiceModeLoopProps): React.JSX.Element {
  const [index, setIndex] = React.useState(0)
  const demo = React.useMemo<AudioEnergySource | null>(
    () =>
      source === undefined
        ? createSpeechBurstSource({ seed: 3, clapEverySeconds: [5, 8] })
        : source,
    [source],
  )

  React.useEffect(() => {
    const timer = setInterval(
      () => setIndex((i) => (i + 1) % VOICE_MODE_LOOP.length),
      intervalMs,
    )
    return () => clearInterval(timer)
  }, [intervalMs])

  const state = VOICE_MODE_LOOP[index]
  React.useEffect(() => {
    onStateChange?.(state)
  }, [state, onStateChange])

  return <AudioReactiveHalbertMark {...mark} state={state} source={demo} />
}
