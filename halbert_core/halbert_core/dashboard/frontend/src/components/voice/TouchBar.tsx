// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
// Touch bar — the §6.2 bottom controls of the Voice Mode screen.
//
// Three actions: push-to-talk (the same gesture as tapping the mark in
// standby), the on-screen keyboard overlay (O9), and the return edge to
// the Host Canvas. The bar itself owns no navigation — O8 wires the Host
// Canvas edge to the router; this component only reports the tap.
//
// Touch targets are h-12 (48px) — above the 44px floor of spec §8 (P5
// hardware checklist). Vermilion accent for the primary action, canvas
// tokens for the rest, on the deliberately dark surface (plan Decision 5).

import { ArrowUpRight, Keyboard, Mic } from 'lucide-react'

interface TouchBarProps {
  /** "[Mic] Tap to Speak" — begin push-to-talk. */
  onPushToTalk: () => void
  /** "[Keyboard]" — glide the on-screen keyboard (O9) up. */
  onKeyboard: () => void
  /** "[ArrowUpRight] Host Canvas" — leave Voice Mode for the canvas. */
  onHostCanvas: () => void
}

const SECONDARY_BUTTON =
  'flex h-12 items-center gap-2 rounded-full border border-hairline bg-canvas/5 ' +
  'px-6 text-base text-canvas/80 transition-colors hover:bg-canvas/10 ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus'

export function TouchBar({ onPushToTalk, onKeyboard, onHostCanvas }: TouchBarProps) {
  return (
    <nav aria-label="Voice controls" className="flex items-center justify-center gap-3 px-6 pb-6 pt-2">
      <button
        type="button"
        onClick={onPushToTalk}
        aria-label="Tap to speak"
        className={
          'flex h-12 items-center gap-2 rounded-full border border-vermilion/40 bg-vermilion/15 ' +
          'px-6 text-base text-vermilion transition-colors hover:bg-vermilion/25 ' +
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus'
        }
      >
        <Mic className="h-5 w-5" aria-hidden="true" />
        Tap to Speak
      </button>
      <button type="button" onClick={onKeyboard} aria-label="Open keyboard" className={SECONDARY_BUTTON}>
        <Keyboard className="h-5 w-5" aria-hidden="true" />
        Keyboard
      </button>
      <button type="button" onClick={onHostCanvas} aria-label="Host canvas" className={SECONDARY_BUTTON}>
        Host Canvas
        <ArrowUpRight className="h-5 w-5" aria-hidden="true" />
      </button>
    </nav>
  )
}