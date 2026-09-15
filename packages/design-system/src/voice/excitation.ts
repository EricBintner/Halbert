// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * How the voice states strike the strings (design doc 17 §"Excitation").
 *
 * The string bank in springs.ts only knows pluck(). Everything that decides
 * WHEN and HOW HARD to pluck lives here, so the component stays a thin
 * frame loop and each rule is testable on its own:
 *
 *   STATE_EXCITATION — per state: onset pluck gain and swell weight.
 *   OnsetPlucker     — rising band level -> a strike of gain × rise. A sharp
 *                      consonant lands in two or three frames and sums to
 *                      one strike; a slow ramp becomes a slow push.
 *   PluckQueue/strum — scheduled strikes: the "recognized" strum walks the
 *                      strings spine-first, 35 ms apart.
 *   IdlePlucker      — a resting instrument touched now and then: one soft
 *                      pluck every 2.5–6 s, weighted toward the outer,
 *                      longer-sustaining tines.
 */

import type { ResonatorBank } from './springs'

/** Voice Mode visual states (spec §4.1), aligned with AudioState in
 * halbert_core/.../components/audio/AcousticAuraIndicator.tsx. */
export type VoiceVisualState =
  | 'idle'
  | 'listening'
  | 'recognized'
  | 'thinking'
  | 'speaking'
  | 'error'

export interface StateExcitation {
  /** Displacement (units of A_k) per unit of band-level rise. 0 = no plucks. */
  readonly pluckGain: number
  /** Multiplier on the swell follower's level, <= 0.3 wherever plucks happen. */
  readonly swellWeight: number
}

export const STATE_EXCITATION: Record<VoiceVisualState, StateExcitation> = Object.freeze({
  idle: Object.freeze({ pluckGain: 0, swellWeight: 1 }),
  listening: Object.freeze({ pluckGain: 2, swellWeight: 0.3 }),
  recognized: Object.freeze({ pluckGain: 0, swellWeight: 0.3 }),
  thinking: Object.freeze({ pluckGain: 0, swellWeight: 0 }),
  speaking: Object.freeze({ pluckGain: 2.5, swellWeight: 0.3 }),
  error: Object.freeze({ pluckGain: 0, swellWeight: 0 }),
})

/** A per-frame level rise at or below this is mic noise, not an onset. */
export const ONSET_FLOOR = 0.02

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
}

/** Turns rising band levels into strikes. Feed it every frame, even at gain
 * 0, so its level memory is current when a voiced state begins. */
export class OnsetPlucker {
  private readonly prev: Float32Array

  constructor(count: number) {
    this.prev = new Float32Array(count)
  }

  /** @returns the number of tines struck this frame */
  feed(levels: ArrayLike<number>, gain: number, bank: ResonatorBank): number {
    let plucks = 0
    for (let k = 0; k < this.prev.length; k++) {
      const level = clamp01(levels[k] ?? 0)
      const rise = level - this.prev[k]
      this.prev[k] = level
      if (gain > 0 && rise > ONSET_FLOOR) {
        bank.pluck(k, gain * rise)
        plucks++
      }
    }
    return plucks
  }

  reset(): void {
    this.prev.fill(0)
  }
}

export interface ScheduledPluck {
  /** Frame-clock time (seconds) at or after which the strike fires. */
  readonly at: number
  readonly tine: number
  readonly amplitude: number
}

/** Strikes waiting for their moment on the frame clock. */
export class PluckQueue {
  private pending: ScheduledPluck[] = []

  schedule(pluck: ScheduledPluck): void {
    this.pending.push(pluck)
  }

  /** Fire every pluck due at `t` into the bank, once. @returns fired count */
  flush(t: number, bank: ResonatorBank): number {
    if (this.pending.length === 0) return 0
    let fired = 0
    const keep: ScheduledPluck[] = []
    for (const p of this.pending) {
      if (p.at <= t) {
        bank.pluck(p.tine, p.amplitude)
        fired++
      } else {
        keep.push(p)
      }
    }
    this.pending = keep
    return fired
  }

  clear(): void {
    this.pending = []
  }

  get size(): number {
    return this.pending.length
  }
}

export const STRUM = Object.freeze({ amplitude: 0.7, staggerSeconds: 0.035 })

/** Schedule a strum: every tine at `amplitude`, spine first, `stagger` apart. */
export function strum(
  queue: PluckQueue,
  t: number,
  count: number,
  opts: { amplitude?: number; staggerSeconds?: number } = {},
): void {
  const amplitude = opts.amplitude ?? STRUM.amplitude
  const stagger = opts.staggerSeconds ?? STRUM.staggerSeconds
  for (let k = 0; k < count; k++) {
    queue.schedule({ at: t + k * stagger, tine: k, amplitude })
  }
}

export const IDLE_PLUCK = Object.freeze({
  minInterval: 2.5,
  maxInterval: 6,
  minAmplitude: 0.25,
  maxAmplitude: 0.45,
})

/** Sparse soft plucks for the idle state. Tick it every idle frame. */
export class IdlePlucker {
  private due: number | null = null
  private tine = 0
  private amplitude = 0

  constructor(
    private readonly count: number,
    private readonly random: () => number = Math.random,
  ) {}

  /** @returns the tine plucked this tick, or -1 */
  tick(t: number, bank: ResonatorBank): number {
    if (this.due === null) {
      this.arm(t)
      return -1
    }
    if (t < this.due) return -1
    const k = this.tine
    bank.pluck(k, this.amplitude)
    this.arm(t)
    return k
  }

  /** Forget the pending pluck; the next tick re-arms from its own time. */
  reset(): void {
    this.due = null
  }

  private arm(t: number): void {
    const { minInterval, maxInterval, minAmplitude, maxAmplitude } = IDLE_PLUCK
    this.due = t + minInterval + this.random() * (maxInterval - minInterval)
    this.amplitude = minAmplitude + this.random() * (maxAmplitude - minAmplitude)
    // sqrt warps a uniform draw toward the outer (long-sustain) tines
    this.tine = Math.min(this.count - 1, Math.floor(this.count * Math.sqrt(this.random())))
  }
}
