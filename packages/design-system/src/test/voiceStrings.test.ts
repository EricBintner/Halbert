// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  ResonatorBank,
  FIXED_TIMESTEP,
  SWELL_SPRING,
  STRING_LADDER,
  STRING_TUNING,
  stringSpring,
  tuneStrings,
} from '../voice/springs'

/** Drive the bank in fixed render steps for `seconds`. */
function drive(bank: ResonatorBank, seconds: number, fps = 60): number {
  const frames = Math.round(seconds * fps)
  let alpha = 0
  for (let i = 0; i < frames; i++) alpha = bank.step(1 / fps)
  return alpha
}

/** Displacement series of tine k, sampled at render rate. */
function trace(bank: ResonatorBank, k: number, seconds: number, fps = 60): number[] {
  const out: number[] = []
  for (let i = 0; i < Math.round(seconds * fps); i++) {
    const a = bank.step(1 / fps)
    out.push(bank.interpolated(k, a))
  }
  return out
}

function zeroCrossings(xs: number[]): number {
  let n = 0
  for (let i = 1; i < xs.length; i++) if (xs[i - 1] * xs[i] < 0) n++
  return n
}

function peak(xs: number[]): number {
  return Math.max(...xs.map(Math.abs))
}

const six = (v: number) => new Array(6).fill(v)
const strings = () => ResonatorBank.strings(STRING_LADDER.medium)

describe('stringSpring — pitch and sustain to spring constants', () => {
  it('maps 8 Hz / 0.2 s to stiffness (2πf)² and damping 2/τ on unit mass', () => {
    const s = stringSpring(8, 0.2)
    expect(s.stiffness).toBeCloseTo((2 * Math.PI * 8) ** 2, 6)
    expect(s.damping).toBeCloseTo(10, 9)
    expect(s.mass).toBe(1)
  })
})

describe('STRING_LADDER — pitch falls and sustain grows outward', () => {
  it('medium: six strings, 8 Hz / 0.20 s at the spine to 2 Hz / 1.10 s at the outer arc', () => {
    const l = STRING_LADDER.medium
    expect(l).toHaveLength(6)
    expect(l[0].frequencyHz).toBeCloseTo(8, 6)
    expect(l[0].decaySeconds).toBeCloseTo(0.2, 6)
    expect(l[5].frequencyHz).toBeCloseTo(2, 6)
    expect(l[5].decaySeconds).toBeCloseTo(1.1, 6)
    for (let k = 1; k < 6; k++) {
      expect(l[k].frequencyHz).toBeLessThan(l[k - 1].frequencyHz)
      expect(l[k].decaySeconds).toBeGreaterThan(l[k - 1].decaySeconds)
    }
  })

  it('steps geometrically: equal pitch ratios between neighbours', () => {
    const l = STRING_LADDER.medium
    const r = l[1].frequencyHz / l[0].frequencyHz
    for (let k = 2; k < 6; k++) {
      expect(l[k].frequencyHz / l[k - 1].frequencyHz).toBeCloseTo(r, 9)
    }
  })

  it('display: ten strings spanning the same endpoints', () => {
    const l = STRING_LADDER.display
    expect(l).toHaveLength(10)
    expect(l[0]).toEqual(STRING_LADDER.medium[0])
    expect(l[9].frequencyHz).toBeCloseTo(2, 6)
    expect(l[9].decaySeconds).toBeCloseTo(1.1, 6)
  })

  it('tuneStrings builds a ladder of any length from the two tuning endpoints', () => {
    const three = tuneStrings(3)
    expect(three).toHaveLength(3)
    expect(three[1].frequencyHz).toBeCloseTo(4, 6) // geometric midpoint of 8 and 2
    expect(three[1].decaySeconds).toBeCloseTo(Math.sqrt(0.2 * 1.1), 6)
    expect(STRING_TUNING.inner.frequencyHz).toBe(8)
    expect(STRING_TUNING.outer.frequencyHz).toBe(2)
  })

  it('every string is lightly damped (ζ below 0.12) so it visibly rings', () => {
    for (const s of [...STRING_LADDER.medium, ...STRING_LADDER.display]) {
      const zeta = 1 / (2 * Math.PI * s.frequencyHz * s.decaySeconds)
      expect(zeta).toBeLessThan(0.12)
    }
  })
})

describe('ResonatorBank — plucked strings (ring component)', () => {
  it('sizes the bank from the ladder', () => {
    expect(strings().size).toBe(6)
    expect(ResonatorBank.strings(STRING_LADDER.display).size).toBe(10)
  })

  it('a plucked spine rings at about 8 Hz, the plucked outer arc at about 2 Hz', () => {
    const bank = strings()
    bank.pluck(0, 0.6)
    bank.pluck(5, 0.6)
    const spine: number[] = []
    const outer: number[] = []
    for (let i = 0; i < 30; i++) {
      // 0.5 s: 8 Hz -> ~8 sign changes, 2 Hz -> ~2
      const a = bank.step(1 / 60)
      spine.push(bank.interpolated(0, a))
      outer.push(bank.interpolated(5, a))
    }
    expect(zeroCrossings(spine)).toBeGreaterThanOrEqual(6)
    expect(zeroCrossings(spine)).toBeLessThanOrEqual(9)
    expect(zeroCrossings(outer)).toBeGreaterThanOrEqual(1)
    expect(zeroCrossings(outer)).toBeLessThanOrEqual(3)
  })

  it('pitch falls monotonically from the spine to the outer arc', () => {
    const bank = strings()
    for (let k = 0; k < 6; k++) bank.pluck(k, 0.6)
    const traces: number[][] = Array.from({ length: 6 }, () => [])
    for (let i = 0; i < 60; i++) {
      const a = bank.step(1 / 60)
      for (let k = 0; k < 6; k++) traces[k].push(bank.interpolated(k, a))
    }
    const zc = traces.map(zeroCrossings)
    for (let k = 1; k < 6; k++) expect(zc[k]).toBeLessThanOrEqual(zc[k - 1])
    expect(zc[0]).toBeGreaterThan(2 * zc[5])
  })

  it('the spine dies within 0.7 s while the outer arc is still swinging', () => {
    const bank = strings()
    bank.pluck(0, 0.6)
    bank.pluck(5, 0.6)
    const spine: number[] = []
    const outer: number[] = []
    for (let i = 0; i < 42; i++) {
      const a = bank.step(1 / 60)
      spine.push(bank.interpolated(0, a))
      outer.push(bank.interpolated(5, a))
    }
    const early = (xs: number[]) => peak(xs.slice(0, 6))
    const late = (xs: number[]) => peak(xs.slice(-6))
    expect(late(spine)).toBeLessThan(0.08 * early(spine))
    expect(late(outer)).toBeGreaterThan(0.35 * early(outer))
  })

  it('a pluck displaces the string by about the requested amplitude regardless of pitch', () => {
    for (const k of [0, 2, 5]) {
      const bank = strings()
      bank.pluck(k, 0.5)
      const p = peak(trace(bank, k, 0.6))
      expect(p).toBeGreaterThan(0.36)
      expect(p).toBeLessThan(0.55)
    }
  })

  it('a negative pluck strikes the other way', () => {
    const bank = strings()
    bank.pluck(3, -0.5)
    const xs = trace(bank, 3, 0.1)
    expect(Math.min(...xs)).toBeLessThan(-0.3)
    expect(Math.max(...xs)).toBeLessThan(0.05)
  })

  it('limits stored energy to amplitude 1 under repeated strikes', () => {
    const bank = strings()
    for (let i = 0; i < 10; i++) {
      bank.pluck(3, 0.9)
      bank.step(1 / 60)
    }
    expect(peak(trace(bank, 3, 1))).toBeLessThanOrEqual(1.0)
  })

  it('stays finite and bounded at 30 fps and after a long stall', () => {
    const bank = strings()
    bank.pluck(0, 0.8)
    bank.step(30) // backgrounded tab
    for (const v of trace(bank, 0, 2, 30)) {
      expect(Number.isFinite(v)).toBe(true)
      expect(Math.abs(v)).toBeLessThanOrEqual(1.0)
    }
  })

  it('ignores plucks on out-of-range tines and NaN amplitudes', () => {
    const bank = strings()
    bank.pluck(9, 0.5)
    bank.pluck(-1, 0.5)
    bank.pluck(2, Number.NaN)
    for (let k = 0; k < 6; k++) expect(peak(trace(bank, k, 0.2))).toBe(0)
  })
})

describe('ResonatorBank — swell follower (level component)', () => {
  const swell = () => ResonatorBank.uniform(6, SWELL_SPRING)

  it('keeps the documented well-damped tuning', () => {
    expect(SWELL_SPRING).toEqual({ stiffness: 140, damping: 18.5, mass: 1 })
    expect(FIXED_TIMESTEP).toBe(0.008)
  })

  it('converges to the target level', () => {
    const bank = swell()
    bank.setTargets(six(0).map((_, k) => k / 5))
    drive(bank, 2)
    for (let k = 0; k < 6; k++) expect(bank.interpolated(k, 1)).toBeCloseTo(k / 5, 1)
  })

  it('attacks fast and decays without ringing', () => {
    const bank = swell()
    bank.setTargets(six(1))
    drive(bank, 0.18)
    expect(bank.interpolated(3, 1)).toBeGreaterThan(0.6)
    drive(bank, 2)
    bank.setTargets(six(0))
    let dip = 0
    for (let i = 0; i < 120; i++) {
      bank.step(1 / 60)
      dip = Math.min(dip, bank.interpolated(3, 1))
    }
    expect(dip).toBeGreaterThan(-0.35)
    drive(bank, 2)
    expect(Math.abs(bank.interpolated(3, 1))).toBeLessThan(0.01)
  })

  it('is stable at 30 fps and after a long stall', () => {
    const bank = swell()
    bank.setTargets(six(1))
    bank.step(30)
    drive(bank, 3, 30)
    for (let k = 0; k < 6; k++) {
      const v = bank.interpolated(k, 1)
      expect(Number.isFinite(v)).toBe(true)
      expect(v).toBeGreaterThan(0.9)
      expect(v).toBeLessThan(1.21)
    }
  })

  it('clamps targets into [0, 1]', () => {
    const bank = swell()
    bank.setTargets([5, -3, Number.NaN, 0.5, 0, 0])
    drive(bank, 2)
    expect(bank.interpolated(0, 1)).toBeCloseTo(1, 1)
    expect(bank.interpolated(1, 1)).toBeCloseTo(0, 1)
    expect(bank.interpolated(3, 1)).toBeCloseTo(0.5, 1)
  })
})
