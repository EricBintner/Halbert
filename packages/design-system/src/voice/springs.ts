// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Spring-physics core for the audio-reactive Halbert mark (spec §3.3).
 *
 * One critically-damped-ish 2nd-order spring per tine converts raw spectral
 * energy targets into organic motion: fast attack on transient phonemes,
 * smooth decay, no square-wave strobing. Integration is semi-implicit
 * (symplectic) Euler at a fixed 8ms substep, accumulator-driven from the
 * variable requestAnimationFrame delta, so behavior is identical at 60fps
 * and at the 30fps the N150 kiosk may dip to. omega = sqrt(k/m) ~ 11.8,
 * omega * dt = 0.094 — deep inside the stability region.
 */

import { TINE_COUNT, TINE_DRIFT } from './geometry'

export const SPRING_DEFAULTS = Object.freeze({ stiffness: 140, damping: 18.5, mass: 1 })
export const FIXED_TIMESTEP = 0.008

/** Never integrate more than this per step call — breaks the death spiral
 * after a backgrounded tab or a long GC pause. */
const MAX_ACCUMULATED = 0.25

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
}

export class ResonatorBank {
  private readonly currents = new Float64Array(TINE_COUNT)
  private readonly previous = new Float64Array(TINE_COUNT)
  private readonly velocities = new Float64Array(TINE_COUNT)
  private readonly targets = new Float64Array(TINE_COUNT)
  /** Continuous phase drift per tine, phi_k(t) = integral of omega_k. */
  readonly phases = new Float64Array(TINE_COUNT)
  private accumulator = 0

  constructor(
    private readonly stiffness = SPRING_DEFAULTS.stiffness,
    private readonly damping = SPRING_DEFAULTS.damping,
    private readonly mass = SPRING_DEFAULTS.mass,
  ) {}

  /** Set raw spectral energy targets (values are clamped to [0, 1]). */
  setTargets(energies: ArrayLike<number>): void {
    for (let k = 0; k < TINE_COUNT; k++) {
      this.targets[k] = clamp01(energies[k] ?? 0)
    }
  }

  /**
   * Advance physics by a render delta (seconds).
   * @returns render-interpolation alpha in [0, 1] for interpolated()
   */
  step(dtSeconds: number): number {
    this.accumulator = Math.min(this.accumulator + Math.max(0, dtSeconds), MAX_ACCUMULATED)
    const h = FIXED_TIMESTEP
    while (this.accumulator >= h) {
      for (let k = 0; k < TINE_COUNT; k++) {
        this.previous[k] = this.currents[k]
        const a =
          (this.stiffness * (this.targets[k] - this.currents[k]) -
            this.damping * this.velocities[k]) /
          this.mass
        this.velocities[k] += a * h
        this.currents[k] += this.velocities[k] * h
        this.phases[k] += TINE_DRIFT[k] * h
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
