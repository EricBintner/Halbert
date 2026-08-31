// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { ResonatorBank, FIXED_TIMESTEP, SPRING_DEFAULTS } from '../voice/springs'

/** Drive the bank in fixed render steps for `seconds`. */
function drive(bank: ResonatorBank, seconds: number, fps = 60): number {
  const frames = Math.round(seconds * fps)
  let alpha = 0
  for (let i = 0; i < frames; i++) alpha = bank.step(1 / fps)
  return alpha
}

describe('ResonatorBank', () => {
  it('converges to the target energy', () => {
    const bank = new ResonatorBank()
    const target = new Array(10).fill(0).map((_, k) => k / 9)
    bank.setTargets(target)
    drive(bank, 2)
    for (let k = 0; k < 10; k++) {
      expect(bank.interpolated(k, 1)).toBeCloseTo(target[k], 1)
    }
  })

  it('attacks fast and decays without runaway oscillation', () => {
    const bank = new ResonatorBank()
    bank.setTargets(new Array(10).fill(1))
    // closed-form 2nd-order step response at k=140, c=18.5, m=1:
    // zeta = 0.782, omega_n = 11.83 -> y(0.18s) ~= 0.72, y(0.12s) ~= 0.47
    drive(bank, 0.18)
    const v = bank.interpolated(3, 1)
    expect(v).toBeGreaterThan(0.6)
    drive(bank, 2)
    let peak = 0
    const now = bank.interpolated(3, 1)
    bank.setTargets(new Array(10).fill(0))
    // decay: bounded undershoot below zero, settles
    for (let i = 0; i < 120; i++) {
      bank.step(1 / 60)
      peak = Math.min(peak, bank.interpolated(3, 1))
    }
    expect(peak).toBeGreaterThan(-0.35) // undershoot bounded
    drive(bank, 2)
    expect(Math.abs(bank.interpolated(3, 1))).toBeLessThan(0.01)
    expect(now).toBeGreaterThan(0.9)
  })

  it('is stable at 30fps (N150 frame dips)', () => {
    const bank = new ResonatorBank()
    bank.setTargets(new Array(10).fill(1))
    drive(bank, 3, 30)
    for (let k = 0; k < 10; k++) {
      const v = bank.interpolated(k, 1)
      expect(Number.isFinite(v)).toBe(true)
      expect(v).toBeGreaterThan(0.9)
      expect(v).toBeLessThan(1.21)
    }
  })

  it('does not spiral after a long stall (accumulator clamp)', () => {
    const bank = new ResonatorBank()
    bank.setTargets(new Array(10).fill(1))
    bank.step(30) // a 30-second hitch (e.g. backgrounded tab restore)
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeLessThan(1.21)
  })

  it('advances per-tine phase drift at its own rate', () => {
    const bank = new ResonatorBank()
    bank.step(FIXED_TIMESTEP * 4)
    expect(bank.phases[0]).toBeCloseTo(1.4 * FIXED_TIMESTEP * 4, 6)
    expect(bank.phases[9]).toBeCloseTo(0.45 * FIXED_TIMESTEP * 4, 6)
  })

  it('clamps targets into [0, 1]', () => {
    const bank = new ResonatorBank()
    bank.setTargets([5, -3, Number.NaN, 0.5, 0, 0, 0, 0, 0, 0])
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeCloseTo(1, 1)
    expect(bank.interpolated(1, 1)).toBeCloseTo(0, 1)
    expect(bank.interpolated(3, 1)).toBeCloseTo(0.5, 1)
  })

  it('exposes the documented spring constants', () => {
    expect(SPRING_DEFAULTS).toEqual({ stiffness: 140, damping: 18.5, mass: 1 })
    expect(FIXED_TIMESTEP).toBe(0.008)
  })
})
