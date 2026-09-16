// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Spring-physics core for the audio-reactive Halbert mark (design doc 17,
 * 2026-09-15; supersedes doc 15 §3.3 and the 2026-08-31 uniform tuning).
 *
 * Two banks of 2nd-order oscillators drive the mark, one oscillator per tine:
 *
 *   ring  — ResonatorBank.strings(STRING_LADDER[density]). Each tine is a
 *           lightly damped string at its own pitch and sustain, resting at 0
 *           and excited only by pluck(). Pitch falls and decay grows from the
 *           spine (8 Hz, 0.2 s) to the outer arc (2 Hz, 1.1 s); every
 *           intermediate tine is a geometric step between the two, so the
 *           same rule tunes 6 or 10 tines. The mode shape in geometry.ts is
 *           fixed in space (stationary nodes) — this bank supplies the
 *           damped cosine in time, which is what makes it read as a string
 *           rather than a bounce.
 *   swell — ResonatorBank.uniform(count, SWELL_SPRING): the well-damped
 *           follower of band level (k=140, c=18.5, zeta ~= 0.78). A sustained
 *           vowel leans the tine without ringing.
 *
 * Integration is semi-implicit (symplectic) Euler at a fixed 8 ms substep,
 * accumulator-driven from the variable requestAnimationFrame delta, so
 * behavior is identical at 60fps and at the 30fps the N150 kiosk may dip
 * to. Render output interpolates between the two latest physics states.
 */

import { tineCount, type VoiceDensity } from './geometry'

export interface SpringParams {
  readonly stiffness: number
  readonly damping: number
  readonly mass: number
}

/** A string's pitch (visible ring rate) and sustain (1/e amplitude decay). */
export interface StringTuning {
  readonly frequencyHz: number
  readonly decaySeconds: number
}

/** The two ends of the ladder; everything between is interpolated. */
export const STRING_TUNING = Object.freeze({
  inner: Object.freeze({ frequencyHz: 8, decaySeconds: 0.2 }),
  outer: Object.freeze({ frequencyHz: 2, decaySeconds: 1.1 }),
})

/** Geometric ladder of `count` strings from the inner to the outer tuning. */
export function tuneStrings(
  count: number,
  tuning: { inner: StringTuning; outer: StringTuning } = STRING_TUNING,
): StringTuning[] {
  const n = Math.max(1, Math.floor(count))
  const fRatio = tuning.outer.frequencyHz / tuning.inner.frequencyHz
  const tRatio = tuning.outer.decaySeconds / tuning.inner.decaySeconds
  return Array.from({ length: n }, (_, k) => {
    const u = n === 1 ? 0 : k / (n - 1)
    return {
      frequencyHz: tuning.inner.frequencyHz * fRatio ** u,
      decaySeconds: tuning.inner.decaySeconds * tRatio ** u,
    }
  })
}

export const STRING_LADDER: Record<VoiceDensity, readonly StringTuning[]> = {
  medium: tuneStrings(tineCount('medium')),
  display: tuneStrings(tineCount('display')),
}

/** Pitch and sustain -> spring constants on unit mass: k = omega^2, c = 2/tau. */
export function stringSpring(frequencyHz: number, decaySeconds: number): SpringParams {
  const omega = 2 * Math.PI * frequencyHz
  return { stiffness: omega * omega, damping: 2 / decaySeconds, mass: 1 }
}

export const SWELL_SPRING: SpringParams = Object.freeze({ stiffness: 140, damping: 18.5, mass: 1 })
export const FIXED_TIMESTEP = 0.008

/** pluck() never stores more than this amplitude (in units of the tine's A_k). */
export const RING_MAX = 1

/** Never integrate more than this per step call — breaks the death spiral
 * after a backgrounded tab or a long GC pause. */
const MAX_ACCUMULATED = 0.25

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
}

export class ResonatorBank {
  private readonly currents: Float64Array
  private readonly previous: Float64Array
  private readonly velocities: Float64Array
  private readonly targets: Float64Array
  private readonly stiffness: Float64Array
  private readonly damping: Float64Array
  private readonly mass: Float64Array
  /** Natural angular frequency per tine, sqrt(k/m). */
  private readonly omega: Float64Array
  private accumulator = 0

  /** One oscillator per entry; the bank size follows the list length. */
  constructor(springs: readonly SpringParams[]) {
    const n = springs.length
    this.currents = new Float64Array(n)
    this.previous = new Float64Array(n)
    this.velocities = new Float64Array(n)
    this.targets = new Float64Array(n)
    this.stiffness = new Float64Array(n)
    this.damping = new Float64Array(n)
    this.mass = new Float64Array(n)
    this.omega = new Float64Array(n)
    springs.forEach((s, k) => {
      this.stiffness[k] = s.stiffness
      this.damping[k] = s.damping
      this.mass[k] = s.mass
      this.omega[k] = Math.sqrt(s.stiffness / s.mass)
    })
  }

  /** `count` identical oscillators (the swell follower). */
  static uniform(count: number, spring: SpringParams): ResonatorBank {
    return new ResonatorBank(Array.from({ length: count }, () => spring))
  }

  /** One string per ladder entry (the ring component). */
  static strings(ladder: readonly StringTuning[]): ResonatorBank {
    return new ResonatorBank(ladder.map((s) => stringSpring(s.frequencyHz, s.decaySeconds)))
  }

  get size(): number {
    return this.currents.length
  }

  /** Set rest targets (values are clamped to [0, 1]). Strings stay at 0. */
  setTargets(energies: ArrayLike<number>): void {
    for (let k = 0; k < this.currents.length; k++) {
      this.targets[k] = clamp01(energies[k] ?? 0)
    }
  }

  /**
   * Pluck tine k by `amplitude` (units of the tine's A_k; sign = direction).
   * Injects velocity amplitude * omega_k, so the same strike displaces every
   * tine by the same fraction of its A_k regardless of pitch. Stored energy is
   * limited to RING_MAX by clamping velocity only — displacement is never
   * touched, so a limited strike cannot snap the path.
   */
  pluck(k: number, amplitude: number): void {
    if (!(k >= 0 && k < this.currents.length) || !Number.isFinite(amplitude)) return
    const w = this.omega[k]
    let v = this.velocities[k] + amplitude * w
    const x = this.currents[k] - this.targets[k]
    const room = RING_MAX * RING_MAX - x * x
    if (room <= 0) {
      v = 0
    } else {
      const vMax = w * Math.sqrt(room)
      if (v > vMax) v = vMax
      else if (v < -vMax) v = -vMax
    }
    this.velocities[k] = v
  }

  /**
   * Advance physics by a render delta (seconds).
   * @returns render-interpolation alpha in [0, 1] for interpolated()
   */
  step(dtSeconds: number): number {
    this.accumulator = Math.min(this.accumulator + Math.max(0, dtSeconds), MAX_ACCUMULATED)
    const h = FIXED_TIMESTEP
    while (this.accumulator >= h) {
      for (let k = 0; k < this.currents.length; k++) {
        this.previous[k] = this.currents[k]
        const a =
          (this.stiffness[k] * (this.targets[k] - this.currents[k]) -
            this.damping[k] * this.velocities[k]) /
          this.mass[k]
        this.velocities[k] += a * h
        this.currents[k] += this.velocities[k] * h
      }
      this.accumulator -= h
    }
    return clamp01(this.accumulator / h)
  }

  /** Oscillator value for tine k, interpolated for smooth rendering. */
  interpolated(k: number, alpha: number): number {
    return this.previous[k] + (this.currents[k] - this.previous[k]) * alpha
  }
}
