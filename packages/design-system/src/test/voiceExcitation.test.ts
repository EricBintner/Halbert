// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi } from 'vitest'
import { ResonatorBank, STRING_LADDER } from '../voice/springs'
import {
  STATE_EXCITATION,
  ONSET_FLOOR,
  IDLE_PLUCK,
  OnsetPlucker,
  PluckQueue,
  IdlePlucker,
  strum,
} from '../voice/excitation'

const strings = () => ResonatorBank.strings(STRING_LADDER.medium)

/** Peak |x| of tine k over `seconds` of free ringing at 60 fps. */
function peakOf(bank: ResonatorBank, k: number, seconds = 0.6): number {
  let p = 0
  for (let i = 0; i < Math.round(seconds * 60); i++) {
    const a = bank.step(1 / 60)
    p = Math.max(p, Math.abs(bank.interpolated(k, a)))
  }
  return p
}

describe('STATE_EXCITATION — how each voice state strikes the strings', () => {
  it('speaking plucks on onsets and leans a little on level; it never retracts', () => {
    expect(STATE_EXCITATION.speaking).toEqual({ pluckGain: 2.5, swellWeight: 0.3, retract: 0 })
  })

  it('listening retracts the ends instead of warping the lines', () => {
    expect(STATE_EXCITATION.listening).toEqual({ pluckGain: 0, swellWeight: 0, retract: 1 })
  })

  it('recognized strums (a warp) while still holding the listening posture', () => {
    expect(STATE_EXCITATION.recognized).toEqual({ pluckGain: 0, swellWeight: 0.3, retract: 1 })
  })

  it('idle breathes on level only; thinking and error neither pluck, lean nor retract', () => {
    expect(STATE_EXCITATION.idle).toEqual({ pluckGain: 0, swellWeight: 1, retract: 0 })
    expect(STATE_EXCITATION.thinking).toEqual({ pluckGain: 0, swellWeight: 0, retract: 0 })
    expect(STATE_EXCITATION.error).toEqual({ pluckGain: 0, swellWeight: 0, retract: 0 })
  })

  it('never leans past the 0.3 the geometry ceiling reserves for swell', () => {
    for (const s of Object.values(STATE_EXCITATION)) {
      if (s.pluckGain > 0) expect(s.swellWeight).toBeLessThanOrEqual(0.3)
    }
  })
})

describe('OnsetPlucker — rising band level becomes a strike', () => {
  it('a level step of 0.3 on one tine plucks that tine by gain × rise', () => {
    const bank = strings()
    const plucker = new OnsetPlucker(6)
    const levels = new Float32Array(6)
    plucker.feed(levels, 2.5, bank) // settle at silence
    levels[2] = 0.3
    expect(plucker.feed(levels, 2.5, bank)).toBe(1)
    const p = peakOf(bank, 2)
    expect(p).toBeGreaterThan(0.55) // ~0.75 less the first-quarter-cycle decay
    expect(p).toBeLessThan(0.8)
    for (const k of [0, 1, 3, 4, 5]) expect(peakOf(strings(), k)).toBe(0)
  })

  it('a rise below the onset floor is noise, not a strike', () => {
    const bank = strings()
    const plucker = new OnsetPlucker(6)
    const levels = new Float32Array(6)
    let plucks = 0
    for (let i = 0; i < 30; i++) {
      levels.fill(i * (ONSET_FLOOR * 0.5))
      plucks += plucker.feed(levels, 2.5, bank)
      bank.step(1 / 60)
    }
    expect(plucks).toBe(0)
    expect(peakOf(bank, 3)).toBe(0)
  })

  it('a falling level never strikes', () => {
    const bank = strings()
    const plucker = new OnsetPlucker(6)
    const levels = new Float32Array(6).fill(0.8)
    plucker.feed(levels, 2.5, bank)
    peakOf(bank, 3, 2) // ring the mount onset out
    const fresh = strings()
    levels.fill(0.1)
    expect(plucker.feed(levels, 2.5, fresh)).toBe(0)
    expect(peakOf(fresh, 3)).toBe(0)
  })

  it('an onset spread over two frames sums to one strike of the total rise', () => {
    const oneFrame = strings()
    const twoFrames = strings()
    const a = new OnsetPlucker(6)
    const b = new OnsetPlucker(6)
    const levels = new Float32Array(6)
    a.feed(levels, 2, oneFrame)
    b.feed(levels, 2, twoFrames)
    levels[4] = 0.3
    a.feed(levels, 2, oneFrame)
    levels[4] = 0.15
    b.feed(levels, 2, twoFrames)
    twoFrames.step(1 / 60)
    levels[4] = 0.3
    b.feed(levels, 2, twoFrames)
    expect(peakOf(twoFrames, 4)).toBeCloseTo(peakOf(oneFrame, 4), 1)
  })

  it('a zero gain feeds the level tracker but strikes nothing', () => {
    const bank = strings()
    const plucker = new OnsetPlucker(6)
    const levels = new Float32Array(6).fill(0.9)
    expect(plucker.feed(levels, 0, bank)).toBe(0)
    expect(peakOf(bank, 0)).toBe(0)
  })
})

describe('PluckQueue and strum — scheduled strikes', () => {
  it('flushes only the plucks whose time has come, each once', () => {
    const bank = strings()
    const queue = new PluckQueue()
    queue.schedule({ at: 1.0, tine: 1, amplitude: 0.5 })
    queue.schedule({ at: 1.2, tine: 5, amplitude: 0.5 })
    expect(queue.flush(0.9, bank)).toBe(0)
    expect(queue.flush(1.0, bank)).toBe(1)
    expect(queue.size).toBe(1)
    expect(queue.flush(1.5, bank)).toBe(1)
    expect(queue.flush(2.0, bank)).toBe(0)
    expect(queue.size).toBe(0)
  })

  it('strum plucks every tine at 0.7, spine first, 35 ms apart', () => {
    const bank = strings()
    const queue = new PluckQueue()
    strum(queue, 10, 6)
    expect(queue.size).toBe(6)
    expect(queue.flush(10, bank)).toBe(1) // spine now
    expect(queue.flush(10 + 0.035 * 5 - 1e-9, bank)).toBe(4) // lanes 1-4
    expect(queue.flush(10 + 0.035 * 5, bank)).toBe(1) // outer arc last
    const p = peakOf(bank, 5)
    expect(p).toBeGreaterThan(0.55)
    expect(p).toBeLessThan(0.75)
  })

  it('clear drops pending plucks', () => {
    const queue = new PluckQueue()
    strum(queue, 0, 6)
    queue.clear()
    expect(queue.size).toBe(0)
  })
})

describe('IdlePlucker — a resting instrument touched now and then', () => {
  it('waits at least the minimum interval, then plucks softly and re-arms', () => {
    const random = vi.fn(() => 0)
    const bank = strings()
    const idle = new IdlePlucker(6, random)
    expect(idle.tick(0, bank)).toBe(-1)
    expect(idle.tick(IDLE_PLUCK.minInterval - 0.01, bank)).toBe(-1)
    expect(idle.tick(IDLE_PLUCK.minInterval, bank)).toBe(0) // random 0 -> spine
    const p = peakOf(bank, 0)
    expect(p).toBeGreaterThan(0.15)
    expect(p).toBeLessThan(IDLE_PLUCK.minAmplitude + 0.01)
    expect(idle.tick(IDLE_PLUCK.minInterval + 0.1, bank)).toBe(-1) // re-armed, not due
    expect(idle.tick(2 * IDLE_PLUCK.minInterval, bank)).toBe(0)
  })

  it('at the top of the random range it picks the outer arc, the loudest, the latest', () => {
    const random = vi.fn(() => 0.999999)
    const bank = strings()
    const idle = new IdlePlucker(6, random)
    idle.tick(0, bank)
    expect(idle.tick(IDLE_PLUCK.maxInterval - 0.01, bank)).toBe(-1)
    expect(idle.tick(IDLE_PLUCK.maxInterval, bank)).toBe(5)
    const p = peakOf(bank, 5, 0.3)
    expect(p).toBeGreaterThan(IDLE_PLUCK.maxAmplitude * 0.8)
    expect(p).toBeLessThan(IDLE_PLUCK.maxAmplitude + 0.01)
  })

  it('favours the outer, longer-sustaining tines', () => {
    // Uniform draws over [0,1): a square-root warp sends more than half of
    // them to the outer half of the mark.
    const draws = Array.from({ length: 1000 }, (_, i) => (i + 0.5) / 1000)
    let cursor = 0
    const random = vi.fn(() => draws[cursor++ % draws.length])
    const idle = new IdlePlucker(6, random)
    const picks: number[] = []
    let t = 0
    for (let i = 0; i < 300; i++) {
      t += IDLE_PLUCK.maxInterval
      const k = idle.tick(t, strings())
      if (k >= 0) picks.push(k)
    }
    expect(picks.length).toBeGreaterThan(100)
    const outerShare = picks.filter((k) => k >= 3).length / picks.length
    expect(outerShare).toBeGreaterThan(0.6)
  })

  it('reset forgets the pending pluck', () => {
    const idle = new IdlePlucker(6, () => 0)
    idle.tick(0, strings())
    idle.reset()
    expect(idle.tick(IDLE_PLUCK.minInterval, strings())).toBe(-1) // re-armed from this tick
  })
})
