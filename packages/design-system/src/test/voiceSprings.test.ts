// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  ResonatorBank,
  FIXED_TIMESTEP,
  SPRING_DEFAULTS,
  PLUCK_SPRING,
} from '../voice/springs'
import { TINE_DRIFT } from '../voice/geometry'

/** Drive the bank in fixed render steps for `seconds`. */
function drive(bank: ResonatorBank, seconds: number, fps = 60): number {
  const frames = Math.round(seconds * fps)
  let alpha = 0
  for (let i = 0; i < frames; i++) alpha = bank.step(1 / fps)
  return alpha
}

const six = (v: number) => new Array(6).fill(v)

describe('ResonatorBank — listening/idle spring (smooth, well-damped)', () => {
  it('defaults to the medium density (6 tines)', () => {
    const bank = new ResonatorBank()
    expect(bank.size).toBe(6)
    expect(bank.phases).toHaveLength(6)
  })

  it('converges to the target energy', () => {
    const bank = new ResonatorBank()
    bank.setTargets(six(0).map((_, k) => k / 5))
    drive(bank, 2)
    for (let k = 0; k < 6; k++) {
      expect(bank.interpolated(k, 1)).toBeCloseTo(k / 5, 1)
    }
  })

  it('attacks fast and decays without runaway oscillation', () => {
    const bank = new ResonatorBank()
    bank.setTargets(six(1))
    // closed-form 2nd-order step response at k=140, c=18.5, m=1:
    // zeta = 0.782, omega_n = 11.83 -> y(0.18s) ~= 0.72
    drive(bank, 0.18)
    expect(bank.interpolated(3, 1)).toBeGreaterThan(0.6)
    drive(bank, 2)
    const now = bank.interpolated(3, 1)
    expect(now).toBeGreaterThan(0.9)
    bank.setTargets(six(0))
    let peak = 0
    for (let i = 0; i < 120; i++) {
      bank.step(1 / 60)
      peak = Math.min(peak, bank.interpolated(3, 1))
    }
    expect(peak).toBeGreaterThan(-0.35)
    drive(bank, 2)
    expect(Math.abs(bank.interpolated(3, 1))).toBeLessThan(0.01)
  })

  it('is stable at 30fps (N150 frame dips)', () => {
    const bank = new ResonatorBank()
    bank.setTargets(six(1))
    drive(bank, 3, 30)
    for (let k = 0; k < 6; k++) {
      const v = bank.interpolated(k, 1)
      expect(Number.isFinite(v)).toBe(true)
      expect(v).toBeGreaterThan(0.9)
      expect(v).toBeLessThan(1.21)
    }
  })

  it('does not spiral after a long stall (accumulator clamp)', () => {
    const bank = new ResonatorBank()
    bank.setTargets(six(1))
    bank.step(30)
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeLessThan(1.21)
  })

  it('advances per-tine phase drift at its own rate', () => {
    const bank = new ResonatorBank()
    bank.step(FIXED_TIMESTEP * 4)
    expect(bank.phases[0]).toBeCloseTo(1.4 * FIXED_TIMESTEP * 4, 6)
    expect(bank.phases[5]).toBeCloseTo(0.55 * FIXED_TIMESTEP * 4, 6)
  })

  it('clamps targets into [0, 1]', () => {
    const bank = new ResonatorBank()
    bank.setTargets([5, -3, Number.NaN, 0.5, 0, 0])
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeCloseTo(1, 1)
    expect(bank.interpolated(1, 1)).toBeCloseTo(0, 1)
    expect(bank.interpolated(3, 1)).toBeCloseTo(0.5, 1)
  })

  it('supports the display density via its drift table', () => {
    const bank = new ResonatorBank(TINE_DRIFT.display)
    expect(bank.size).toBe(10)
  })
})

describe('ResonatorBank — plucked-string spring (speaking state)', () => {
  it('rings: overshoots the target and oscillates around it', () => {
    const bank = new ResonatorBank(TINE_DRIFT.medium, PLUCK_SPRING)
    bank.setTargets(six(1))
    let peak = 0
    let minAfterPeak = 1
    let crossed = false
    for (let i = 0; i < 240; i++) {
      // 4 seconds at 60fps
      bank.step(1 / 60)
      const v = bank.interpolated(2, 1)
      peak = Math.max(peak, v)
      if (peak > 1.05 && !crossed && v < 1) {
        crossed = true
      }
      if (crossed && i < 90) minAfterPeak = Math.min(minAfterPeak, v)
    }
    // underdamped (zeta ~= 0.16): clear overshoot, then a dip below target
    expect(peak).toBeGreaterThan(1.3)
    expect(peak).toBeLessThan(1.8)
    expect(crossed).toBe(true)
    expect(minAfterPeak).toBeLessThan(0.98)
    drive(bank, 3)
    expect(bank.interpolated(2, 1)).toBeCloseTo(1, 1)
  })

  it('injectVelocity plucks a resting tine (impulse, ring, settle)', () => {
    const bank = new ResonatorBank(TINE_DRIFT.medium, PLUCK_SPRING) // target 0
    bank.injectVelocity(3, 2.5)
    let peak = 0
    let swungNegative = false
    let frames = 0
    bank.step(1 / 60)
    while (frames++ < 300) {
      const alpha = bank.step(1 / 60)
      const v = bank.interpolated(3, alpha)
      peak = Math.max(peak, v)
      if (v < -0.05) swungNegative = true
    }
    expect(peak).toBeGreaterThan(0.15) // the strike displaces the string
    expect(swungNegative).toBe(true) // and it rings through zero
    expect(Math.abs(bank.interpolated(3, 1))).toBeLessThan(0.05) // settled
  })

  it('exposes the documented spring tunings', () => {
    expect(SPRING_DEFAULTS).toEqual({ stiffness: 140, damping: 18.5, mass: 1 })
    expect(PLUCK_SPRING.stiffness).toBe(120)
    expect(PLUCK_SPRING.damping).toBeLessThan(4)
    expect(FIXED_TIMESTEP).toBe(0.008)
  })
})
