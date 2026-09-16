// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { Listener, LISTENING } from '../voice/listening'
import { createSpeechBurstSource } from '../voice/demo'
import { tineLengths } from '../voice/geometry'

const LENGTHS = tineLengths() // brand: spine, five U-lanes, outer arc
const COUNT = LENGTHS.length
const DT = 1 / 60
const listener = () => new Listener(LENGTHS)

/** Feed `frames` frames of the given levels; returns the elapsed time. */
function feed(
  l: Listener,
  levels: ArrayLike<number> | ((frame: number) => ArrayLike<number>),
  frames: number,
  t0 = 0,
): number {
  let t = t0
  for (let i = 0; i < frames; i++) {
    t += DT
    l.feed(typeof levels === 'function' ? levels(i) : levels, DT, t)
  }
  return t
}

const silence = new Float32Array(COUNT)
/** A vowel: the middle of the register. */
const speech = (() => {
  const v = new Float32Array(COUNT)
  v[2] = 0.3
  v[3] = 0.3
  return v
})()
const clap = new Float32Array(COUNT).fill(0.8)

/** Retraction of end `side` of tine k in mark units. */
const units = (l: Listener, k: number, side: 0 | 1) => l.retraction(k, side) * LENGTHS[k]

function ends(l: Listener): Array<[number, number]> {
  return Array.from({ length: COUNT }, (_, k) => [l.retraction(k, 0), l.retraction(k, 1)])
}

describe('Listener — presence: a fixed travel, tuned to each ring\'s own register', () => {
  it('is fully extended in silence', () => {
    const l = listener()
    feed(l, silence, 60)
    expect(l.attention).toBe(0)
    for (const [a, b] of ends(l)) {
      expect(a).toBe(0)
      expect(b).toBe(0)
    }
  })

  it('a sound across every band moves every tip by the same distance', () => {
    const l = listener()
    const everywhere = new Float32Array(COUNT).fill(0.3)
    feed(l, everywhere, 60)
    const [lo, hi] = LISTENING.presenceUnits
    for (let k = 0; k < COUNT; k++) {
      expect(units(l, k, 0)).toBeGreaterThanOrEqual(lo - 1)
      expect(units(l, k, 0)).toBeLessThanOrEqual(hi + 1e-6)
      if (k === 0) expect(units(l, k, 1)).toBe(0) // the spine's base is the mark's centre
      else {
        expect(units(l, k, 1)).toBeGreaterThanOrEqual(lo - 1)
        expect(units(l, k, 1)).toBeLessThanOrEqual(hi + 1e-6)
      }
    }
    // the travel is about five percent of an outer ring and much more of the spine
    expect(l.retraction(0, 0)).toBeGreaterThan(2.5 * l.retraction(6, 0))
  })

  it('high sounds draw the inner rings in, low sounds the outer rings', () => {
    const high = new Float32Array(COUNT)
    high[0] = 0.4
    high[1] = 0.4
    const low = new Float32Array(COUNT)
    low[5] = 0.4
    low[6] = 0.4
    // an attended ring travels 45-70 units, an unattended one a quarter of that
    const hi = listener()
    feed(hi, high, 60)
    expect(units(hi, 0, 0)).toBeGreaterThan(2.2 * units(hi, 6, 0))
    expect(units(hi, 1, 0)).toBeGreaterThan(2.2 * units(hi, 5, 0))
    const lo = listener()
    feed(lo, low, 60)
    expect(units(lo, 6, 0)).toBeGreaterThan(2.2 * units(lo, 0, 0))
    expect(units(lo, 5, 0)).toBeGreaterThan(2.2 * units(lo, 1, 0))
  })

  it('a vowel attends its own rings fully and the rest a little (the whole mark listens)', () => {
    const l = listener()
    feed(l, speech, 60)
    expect(l.attention).toBeGreaterThan(0.95)
    const [lo, hi] = LISTENING.presenceUnits
    for (const k of [2, 3]) {
      expect(units(l, k, 0)).toBeGreaterThanOrEqual(lo - 1)
      expect(units(l, k, 0)).toBeLessThanOrEqual(hi + 1e-6)
    }
    for (const k of [0, 5, 6]) {
      expect(units(l, k, 0)).toBeGreaterThan(LISTENING.globalShare * lo - 2)
      expect(units(l, k, 0)).toBeLessThan(LISTENING.globalShare * hi + 2)
    }
  })

  it('drifts slowly while listening, ends and lines out of step', () => {
    const l = listener()
    feed(l, speech, 60)
    let maxDiffBetweenEnds = 0
    let maxDiffBetweenLines = 0
    const lane3Start: number[] = []
    let t = 1
    for (let i = 0; i < 180; i++) {
      t = feed(l, speech, 1, t)
      lane3Start.push(units(l, 3, 0))
      maxDiffBetweenEnds = Math.max(maxDiffBetweenEnds, Math.abs(units(l, 3, 0) - units(l, 3, 1)))
      maxDiffBetweenLines = Math.max(maxDiffBetweenLines, Math.abs(units(l, 3, 0) - units(l, 2, 0)))
    }
    expect(Math.max(...lane3Start) - Math.min(...lane3Start)).toBeGreaterThan(15)
    expect(maxDiffBetweenEnds).toBeGreaterThan(8)
    expect(maxDiffBetweenLines).toBeGreaterThan(8)
    // never a jump: frame-to-frame change stays tiny
    for (let i = 1; i < lane3Start.length; i++) {
      expect(Math.abs(lane3Start[i] - lane3Start[i - 1])).toBeLessThan(2)
    }
  })

  it('keeps listening for a moment after the sound stops, then lets go', () => {
    const l = listener()
    let t = feed(l, speech, 60)
    t = feed(l, silence, 48, t) // +0.8 s
    expect(l.attention).toBeGreaterThan(0.5)
    expect(units(l, 3, 0)).toBeGreaterThan(20)
    feed(l, silence, 480, t) // +8 s
    expect(l.attention).toBeLessThan(0.02)
    expect(units(l, 3, 0)).toBeLessThan(1)
  })

  it('rises within a few frames once sound starts', () => {
    const l = listener()
    feed(l, speech, 12) // 0.2 s
    expect(l.attention).toBeGreaterThan(0.6)
    expect(units(l, 2, 0)).toBeGreaterThan(20)
  })
})

/** A syllable as a voice (and the demo) makes them: a gaussian over the
 * register, several adjacent bands rising together, 20 ms attack, 120 ms
 * decay. `age` in seconds since the syllable started. */
function syllable(age: number, centre: number, peak = 1, width = 0.26): Float32Array {
  const v = new Float32Array(COUNT)
  if (age < 0) return v
  const env = age < 0.02 ? age / 0.02 : Math.exp(-(age - 0.02) / 0.12)
  for (let k = 0; k < COUNT; k++) {
    const z = (k / (COUNT - 1) - centre) / width
    v[k] = peak * env * Math.exp(-z * z)
  }
  v[COUNT - 1] *= 0.5
  return v
}

describe('Listener — impact: a clap retracts hard, speech does not', () => {
  it('syllables never count as an impact, at 60 or 30 fps', () => {
    for (const fps of [60, 30]) {
      const l = listener()
      let maxImpact = 0
      let t = 0
      for (const centre of [0.1, 0.3, 0.5, 0.7, 0.9]) {
        for (let i = 0; i < Math.round(0.35 * fps); i++) {
          t += 1 / fps
          l.feed(syllable(i / fps, centre), 1 / fps, t)
          maxImpact = Math.max(maxImpact, l.impact)
        }
      }
      expect(maxImpact).toBeLessThan(0.01)
      expect(units(l, 6, 0)).toBeLessThanOrEqual(LISTENING.presenceUnits[1] + 1e-6)
    }
  })

  it('the demo voice: no impacts without claps, one per clap with them, at both rates', () => {
    for (const fps of [60, 30]) {
      const run = (opts: Parameters<typeof createSpeechBurstSource>[0]) => {
        const src = createSpeechBurstSource(opts)
        src.start()
        const l = listener()
        const out = new Float32Array(COUNT)
        let maxImpact = 0
        let events = 0
        let above = false
        for (let i = 0; i < 30 * fps; i++) {
          const t = i / fps
          src.readEnergies(out, t)
          l.feed(out, 1 / fps, t)
          maxImpact = Math.max(maxImpact, l.impact)
          const isAbove = l.impact > 0.15
          if (isAbove && !above) events++
          above = isAbove
        }
        return { maxImpact, events }
      }
      const plain = run({ seed: 3 })
      expect(plain.maxImpact).toBeLessThan(0.01)
      const clappy = run({ seed: 3, clapEverySeconds: [5, 8] })
      expect(clappy.events).toBeGreaterThanOrEqual(3)
      expect(clappy.events).toBeLessThanOrEqual(6)
      expect(clappy.maxImpact).toBeGreaterThan(0.9) // impact is a 0..1 strength
    }
  })

  it('a talker whose voice spans most bands at once still does not startle it', () => {
    // Even a broad voice leaves the extremes (air above 4 kHz, room below
    // 100 Hz) quiet; only something that lifts nearly every band is a hit.
    const l = listener()
    const broad = new Float32Array([0, 0.2, 0.3, 0.3, 0.25, 0.1, 0.02])
    let maxImpact = 0
    let t = feed(l, silence, 10)
    for (let i = 0; i < 30; i++) {
      t = feed(l, broad, 1, t)
      maxImpact = Math.max(maxImpact, l.impact)
    }
    expect(maxImpact).toBeLessThan(0.01)
  })

  /** The impact travel of tine k at full strength, in mark units: a 60/40
   * blend of a fixed distance and a share of the line's own length. */
  const fullImpactUnits = (k: number) =>
    LISTENING.impactFixedShare * LISTENING.impactUnits +
    (1 - LISTENING.impactFixedShare) * LISTENING.impactFraction * LENGTHS[k]

  it('a broadband clap retracts every line within 100 ms; the centre reacts as visibly as the edge', () => {
    const l = listener()
    let t = feed(l, silence, 30)
    t = feed(l, clap, 1, t)
    let outerUnits = 0
    let spineUnits = 0
    for (let i = 0; i < 6; i++) {
      t = feed(l, silence, 1, t)
      outerUnits = Math.max(outerUnits, units(l, 6, 0))
      spineUnits = Math.max(spineUnits, units(l, 0, 0))
    }
    // the spine travels at least 60 % of the outer arc's distance (the fixed
    // share), and a larger fraction of its short length
    expect(spineUnits).toBeGreaterThan(0.55 * outerUnits)
    expect(spineUnits).toBeGreaterThan(100)
    expect(outerUnits).toBeGreaterThan(spineUnits) // the proportional share still favours long lines
    expect(outerUnits).toBeGreaterThan(200)
    expect(l.retraction(0, 0)).toBeGreaterThan(l.retraction(6, 0))
    expect(l.retraction(6, 1)).toBeCloseTo(l.retraction(6, 0), 2) // a clap is symmetric
  })

  it('even the hardest clap at full attention leaves a fifth of every line', () => {
    // The founder's brief: a handclap should not close a line. Presence at
    // its peak plus a saturated impact must still leave the tips well apart.
    const l = listener()
    let t = feed(l, new Float32Array(COUNT).fill(0.3), 120) // attention fully up, every band
    const hardest = new Float32Array(COUNT).fill(1)
    t = feed(l, hardest, 1, t)
    let worst = 0
    for (let i = 0; i < 12; i++) {
      t = feed(l, hardest, 1, t)
      for (let k = 0; k < COUNT; k++) {
        worst = Math.max(worst, l.retraction(k, 0) + l.retraction(k, 1))
      }
    }
    expect(worst).toBeLessThanOrEqual(0.8)
    // and by construction, per line: peak presence plus a saturated impact
    // fits under the cap (the spine spends its whole budget on one end)
    for (let k = 0; k < COUNT; k++) {
      const cap = k === 0 ? 2 * LISTENING.maxPerEnd : LISTENING.maxPerEnd
      expect((LISTENING.presenceUnits[1] + fullImpactUnits(k)) / LENGTHS[k]).toBeLessThanOrEqual(cap)
    }
  })

  it('relaxes smoothly after the clap and never fully closes', () => {
    const l = listener()
    let t = feed(l, silence, 30)
    t = feed(l, clap, 1, t)
    const trace: number[] = []
    for (let i = 0; i < 60; i++) {
      t = feed(l, silence, 1, t)
      trace.push(l.retraction(6, 0))
    }
    expect(trace[trace.length - 1]).toBeLessThan(0.2)
    // monotone after the peak: no bounce, no ring
    const peakAt = trace.indexOf(Math.max(...trace))
    for (let i = peakAt + 1; i < trace.length; i++) {
      expect(trace[i]).toBeLessThanOrEqual(trace[i - 1] + 1e-9)
    }
    for (let k = 0; k < COUNT; k++) {
      expect(l.retraction(k, 0) + l.retraction(k, 1)).toBeLessThanOrEqual(2 * LISTENING.maxPerEnd)
    }
  })

  it('a harder clap retracts further than a soft one, up to the cap', () => {
    const soft = listener()
    const hard = listener()
    const softClap = new Float32Array(COUNT).fill(0.4)
    let ts = feed(soft, silence, 30)
    let th = feed(hard, silence, 30)
    ts = feed(soft, softClap, 1, ts)
    th = feed(hard, clap, 1, th)
    let softPeak = 0
    let hardPeak = 0
    for (let i = 0; i < 8; i++) {
      ts = feed(soft, silence, 1, ts)
      th = feed(hard, silence, 1, th)
      softPeak = Math.max(softPeak, units(soft, 4, 0))
      hardPeak = Math.max(hardPeak, units(hard, 4, 0))
    }
    expect(softPeak).toBeGreaterThan(90)
    expect(hardPeak).toBeGreaterThan(softPeak + 80)
  })
})

describe('Listener — robustness', () => {
  it('is deterministic: two listeners fed the same frames agree exactly', () => {
    const a = listener()
    const b = listener()
    const script = (frame: number) => (frame % 40 < 20 ? speech : frame % 97 === 0 ? clap : silence)
    feed(a, script, 300)
    feed(b, script, 300)
    expect(ends(a)).toEqual(ends(b))
  })

  it('stays finite and bounded under hostile input', () => {
    const l = listener()
    const hostile = (frame: number) => {
      const v = new Float32Array(COUNT)
      v.fill(frame % 2 === 0 ? 1 : 0)
      if (frame % 7 === 0) v[3] = Number.NaN
      return v
    }
    let t = 0
    for (let i = 0; i < 300; i++) {
      t += i % 5 === 0 ? 0 : DT // include zero-length frames
      l.feed(hostile(i), i % 5 === 0 ? 0 : DT, t)
      for (let k = 0; k < COUNT; k++) {
        for (const side of [0, 1] as const) {
          const r = l.retraction(k, side)
          expect(Number.isFinite(r)).toBe(true)
          expect(r).toBeGreaterThanOrEqual(0)
          // the spine's one moving end may spend the whole per-line budget
          expect(r).toBeLessThanOrEqual(k === 0 ? 2 * LISTENING.maxPerEnd : LISTENING.maxPerEnd)
        }
        expect(l.retraction(k, 0) + l.retraction(k, 1)).toBeLessThanOrEqual(2 * LISTENING.maxPerEnd)
      }
    }
  })

  it('carries its envelopes to a listener of another density', () => {
    const a = listener()
    feed(a, speech, 60)
    const b = new Listener(tineLengths('display'))
    b.adopt(a)
    expect(b.attention).toBeCloseTo(a.attention, 9)
    // the vowel's rings (mid register) are attended in the new density too
    expect(b.retraction(4, 0) * tineLengths('display')[4]).toBeGreaterThan(30)
    expect(b.retraction(0, 0) * tineLengths('display')[0]).toBeLessThan(20)
  })

  it('exposes the tuning the design record documents', () => {
    expect(LISTENING.presenceUnits).toEqual([45, 70]) // ~3-5 % of an outer ring
    expect(LISTENING.globalShare).toBe(0.25)
    expect(LISTENING.impactFixedShare).toBe(0.6) // 60 % fixed distance, 40 % share of length
    expect(LISTENING.impactUnits).toBeGreaterThan(2 * LISTENING.presenceUnits[1])
    expect(LISTENING.releaseSeconds).toBeGreaterThan(LISTENING.attackSeconds * 5)
    expect(LISTENING.maxPerEnd).toBeLessThan(0.5)
  })

  it('the hardest clap actually reaches full strength before the cap', () => {
    const l = listener()
    let t = feed(l, silence, 30)
    t = feed(l, clap, 1, t)
    let peak = 0
    for (let i = 0; i < 12; i++) {
      t = feed(l, silence, 1, t)
      peak = Math.max(peak, l.impact)
    }
    expect(peak).toBeGreaterThan(0.95)
    expect(peak).toBeLessThanOrEqual(1)
  })

  it('a stalled or backwards frame clock cannot latch an impact', () => {
    const l = listener()
    l.feed(silence, DT, 1)
    l.feed(clap, DT, 1 + DT)
    // the clock now stands still (or goes backwards); time still passes by dt
    for (let i = 0; i < 120; i++) l.feed(silence, DT, 0.5)
    expect(l.impact).toBeLessThan(0.02)
  })
})
