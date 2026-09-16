// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { Listener, LISTENING } from '../voice/listening'
import { createSpeechBurstSource } from '../voice/demo'

const COUNT = 7
const DT = 1 / 60

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
const speech = (() => {
  const v = new Float32Array(COUNT)
  v[2] = 0.3
  v[3] = 0.3
  return v
})()
const clap = new Float32Array(COUNT).fill(0.8)

function ends(l: Listener): Array<[number, number]> {
  return Array.from({ length: COUNT }, (_, k) => [l.retraction(k, 0), l.retraction(k, 1)])
}

describe('Listener — presence: sound raises attention fast and lets it go slowly', () => {
  it('is fully extended in silence', () => {
    const l = new Listener(COUNT)
    feed(l, silence, 60)
    expect(l.attention).toBe(0)
    for (const [a, b] of ends(l)) {
      expect(a).toBe(0)
      expect(b).toBe(0)
    }
  })

  it('steady speech settles every end between presenceMin and presenceMax', () => {
    const l = new Listener(COUNT)
    feed(l, speech, 60) // 1 s
    expect(l.attention).toBeGreaterThan(0.95)
    ends(l).forEach(([a, b], k) => {
      expect(a).toBeGreaterThanOrEqual(LISTENING.presenceMin - 0.01)
      expect(a).toBeLessThanOrEqual(LISTENING.presenceMax + 1e-6)
      if (k === 0) expect(b).toBe(0) // the spine's bottom end is the mark's centre
      else {
        expect(b).toBeGreaterThanOrEqual(LISTENING.presenceMin - 0.01)
        expect(b).toBeLessThanOrEqual(LISTENING.presenceMax + 1e-6)
      }
    })
  })

  it('drifts slowly while listening, ends and lines out of step', () => {
    const l = new Listener(COUNT)
    feed(l, speech, 60)
    let maxDiffBetweenEnds = 0
    let maxDiffBetweenLines = 0
    const lane3Start: number[] = []
    let t = 1
    for (let i = 0; i < 180; i++) {
      t = feed(l, speech, 1, t)
      lane3Start.push(l.retraction(3, 0))
      maxDiffBetweenEnds = Math.max(maxDiffBetweenEnds, Math.abs(l.retraction(3, 0) - l.retraction(3, 1)))
      maxDiffBetweenLines = Math.max(maxDiffBetweenLines, Math.abs(l.retraction(3, 0) - l.retraction(5, 0)))
    }
    expect(Math.max(...lane3Start) - Math.min(...lane3Start)).toBeGreaterThan(0.02)
    expect(maxDiffBetweenEnds).toBeGreaterThan(0.01)
    expect(maxDiffBetweenLines).toBeGreaterThan(0.01)
    // never a jump: frame-to-frame change stays tiny
    for (let i = 1; i < lane3Start.length; i++) {
      expect(Math.abs(lane3Start[i] - lane3Start[i - 1])).toBeLessThan(0.002)
    }
  })

  it('keeps listening for a moment after the sound stops, then lets go', () => {
    const l = new Listener(COUNT)
    let t = feed(l, speech, 60)
    t = feed(l, silence, 48, t) // +0.8 s
    expect(l.attention).toBeGreaterThan(0.5)
    expect(l.retraction(3, 0)).toBeGreaterThan(0.04)
    feed(l, silence, 480, t) // +8 s
    expect(l.attention).toBeLessThan(0.02)
    expect(l.retraction(3, 0)).toBeLessThan(0.003)
  })

  it('rises within a few frames once sound starts', () => {
    const l = new Listener(COUNT)
    feed(l, speech, 12) // 0.2 s
    expect(l.attention).toBeGreaterThan(0.6)
    expect(l.retraction(2, 0)).toBeGreaterThan(0.05)
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
      const l = new Listener(COUNT)
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
      expect(l.retraction(6, 0)).toBeLessThanOrEqual(LISTENING.presenceMax + 1e-6)
    }
  })

  it('the demo voice: no impacts without claps, one per clap with them, at both rates', () => {
    for (const fps of [60, 30]) {
      const run = (opts: Parameters<typeof createSpeechBurstSource>[0]) => {
        const src = createSpeechBurstSource(opts)
        src.start()
        const l = new Listener(COUNT)
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
      expect(clappy.maxImpact).toBeGreaterThan(0.9 * LISTENING.impactMax)
    }
  })

  it('a talker whose voice spans most bands at once still does not startle it', () => {
    // Even a broad voice leaves the extremes (air above 4 kHz, room below
    // 100 Hz) quiet; only something that lifts nearly every band is a hit.
    const l = new Listener(COUNT)
    const broad = new Float32Array([0, 0.2, 0.3, 0.3, 0.25, 0.1, 0.02])
    let maxImpact = 0
    let t = feed(l, silence, 10)
    for (let i = 0; i < 30; i++) {
      t = feed(l, broad, 1, t)
      maxImpact = Math.max(maxImpact, l.impact)
    }
    expect(maxImpact).toBeLessThan(0.01)
  })

  it('a broadband clap retracts every line within 100 ms, the outer lines most', () => {
    const l = new Listener(COUNT)
    let t = feed(l, silence, 30)
    t = feed(l, clap, 1, t)
    let outerPeak = 0
    let spinePeak = 0
    for (let i = 0; i < 6; i++) {
      t = feed(l, silence, 1, t)
      outerPeak = Math.max(outerPeak, l.retraction(6, 0))
      spinePeak = Math.max(spinePeak, l.retraction(0, 0))
    }
    expect(outerPeak).toBeGreaterThanOrEqual(0.2)
    expect(outerPeak).toBeLessThanOrEqual(LISTENING.maxPerEnd)
    expect(spinePeak).toBeGreaterThan(0.12)
    expect(spinePeak).toBeLessThan(outerPeak)
    expect(l.retraction(6, 1)).toBeCloseTo(l.retraction(6, 0), 2) // a clap is symmetric
  })

  it('even the hardest clap at full attention leaves a fifth of every line', () => {
    // The founder's brief: a handclap should not close a line. Presence at
    // its peak plus a saturated impact must still leave the tips well apart.
    const l = new Listener(COUNT)
    let t = feed(l, speech, 120) // attention fully up
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
    expect(LISTENING.impactMax + LISTENING.presenceMax).toBeLessThanOrEqual(0.4)
  })

  it('relaxes smoothly after the clap and never fully closes', () => {
    const l = new Listener(COUNT)
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
    const soft = new Listener(COUNT)
    const hard = new Listener(COUNT)
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
      softPeak = Math.max(softPeak, soft.retraction(4, 0))
      hardPeak = Math.max(hardPeak, hard.retraction(4, 0))
    }
    expect(softPeak).toBeGreaterThan(0.08)
    expect(hardPeak).toBeGreaterThan(softPeak + 0.07)
  })
})

describe('Listener — robustness', () => {
  it('is deterministic: two listeners fed the same frames agree exactly', () => {
    const a = new Listener(COUNT)
    const b = new Listener(COUNT)
    const script = (frame: number) => (frame % 40 < 20 ? speech : frame % 97 === 0 ? clap : silence)
    feed(a, script, 300)
    feed(b, script, 300)
    expect(ends(a)).toEqual(ends(b))
  })

  it('stays finite and bounded under hostile input', () => {
    const l = new Listener(COUNT)
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
          expect(r).toBeLessThanOrEqual(LISTENING.maxPerEnd)
        }
      }
    }
  })

  it('exposes the tuning the design record documents', () => {
    expect(LISTENING.presenceMin).toBe(0.1)
    expect(LISTENING.presenceMax).toBe(0.15)
    expect(LISTENING.releaseSeconds).toBeGreaterThan(LISTENING.attackSeconds * 5)
    expect(LISTENING.maxPerEnd).toBeLessThan(0.5)
  })

  it('the hardest clap actually reaches impactMax before the cap', () => {
    const l = new Listener(COUNT)
    let t = feed(l, silence, 30)
    t = feed(l, clap, 1, t)
    let peak = 0
    for (let i = 0; i < 12; i++) {
      t = feed(l, silence, 1, t)
      peak = Math.max(peak, l.impact)
    }
    expect(peak).toBeGreaterThan(0.95 * LISTENING.impactMax)
  })

  it('a stalled or backwards frame clock cannot latch an impact', () => {
    const l = new Listener(COUNT)
    l.feed(silence, DT, 1)
    l.feed(clap, DT, 1 + DT)
    // the clock now stands still (or goes backwards); time still passes by dt
    for (let i = 0; i < 120; i++) l.feed(silence, DT, 0.5)
    expect(l.impact).toBeLessThan(0.02)
  })
})
