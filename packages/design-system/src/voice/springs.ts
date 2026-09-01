// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Spring-physics core for the audio-reactive Halbert mark (spec §3.3,
 * revised 2026-08-31).
 *
 * One 2nd-order spring per tine converts raw spectral energy into motion.
 * Two tunings:
 *
 *   SPRING_DEFAULTS (listening / idle) — k=140, c=18.5: fast attack on
 *     transient phonemes, smooth organic decay, no strobing.
 *   PLUCK_SPRING (speaking) — k=120, c=3.5: deliberately UNDERDAMPED
 *     (zeta ~= 0.16) so each tine behaves like a plucked string: a spectral
 *     onset injects velocity (see injectVelocity) and the tine rings with
 *     sign-alternating decay around its target. The standing-wave shape in
 *     geometry.ts turns that ringing into a vibrating-string look.
 *
 * Integration is semi-implicit (symplectic) Euler at a fixed 8ms substep,
 * accumulator-driven from the variable requestAnimationFrame delta, so
 * behavior is identical at 60fps and at the 30fps the N150 kiosk may dip
 * to. Render output interpolates between the two latest physics states.
 */

import { TINE_DRIFT } from './geometry'

export const SPRING_DEFAULTS = Object.freeze({ stiffness: 140, damping: 18.5, mass: 1 })
export const PLUCK_SPRING = Object.freeze({ stiffness: 120, damping: 3.5, mass: 1 })
export const FIXED_TIMESTEP = 0.008

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
  /** Continuous phase drift per tine, phi_k(t) = integral of omega_k. */
  readonly phases: Float64Array
  private readonly drift: readonly number[]
  private accumulator = 0

  /**
   * @param drift per-tine phase drift rates; the bank size follows the
   *        table length (TINE_DRIFT.medium = 6 tines, TINE_DRIFT.display = 10)
   * @param stiffness spring constant k (spec §3.3 default 140)
   * @param damping damping c (default 18.5; PLUCK_SPRING uses 3.5)
   * @param mass spring mass m (default 1)
   */
  constructor(
    drift: readonly number[] = TINE_DRIFT.medium,
    { stiffness, damping, mass }: { stiffness: number; damping: number; mass: number } = {
      ...SPRING_DEFAULTS,
    },
  ) {
    this.drift = drift
    this.currents = new Float64Array(drift.length)
    this.previous = new Float64Array(drift.length)
    this.velocities = new Float64Array(drift.length)
    this.targets = new Float64Array(drift.length)
    this.phases = new Float64Array(drift.length)
    this.stiffness = stiffness
    this.damping = damping
    this.mass = mass
  }

  private readonly stiffness: number
  private readonly damping: number
  private readonly mass: number

  get size(): number {
    return this.drift.length
  }

  /** Set raw spectral energy targets (values are clamped to [0, 1]). */
  setTargets(energies: ArrayLike<number>): void {
    for (let k = 0; k < this.drift.length; k++) {
      this.targets[k] = clamp01(energies[k] ?? 0)
    }
  }

  /**
   * Pluck tine k: add instantaneous velocity. Used by the speaking state to
   * strike a tine on spectral onsets — with PLUCK_SPRING this rings down
   * like a string instead of gliding to the new level.
   */
  injectVelocity(k: number, dv: number): void {
    this.velocities[k] += dv
  }

  /**
   * Advance physics by a render delta (seconds).
   * @returns render-interpolation alpha in [0, 1] for interpolated()
   */
  step(dtSeconds: number): number {
    this.accumulator = Math.min(this.accumulator + Math.max(0, dtSeconds), MAX_ACCUMULATED)
    const h = FIXED_TIMESTEP
    while (this.accumulator >= h) {
      for (let k = 0; k < this.drift.length; k++) {
        this.previous[k] = this.currents[k]
        const a =
          (this.stiffness * (this.targets[k] - this.currents[k]) -
            this.damping * this.velocities[k]) /
          this.mass
        this.velocities[k] += a * h
        this.currents[k] += this.velocities[k] * h
        this.phases[k] += this.drift[k] * h
      }
      this.accumulator -= h
    }
    return clamp01(this.accumulator / h)
  }

  /** Spring value for tine k, interpolated for smooth rendering. */
  interpolated(k: number, alpha: number): number {
    return this.previous[k] + (this.currents[k] - this.previous[k]) * alpha
  }
}
