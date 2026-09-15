// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import { createSpeechBurstSource } from '../voice/demo'
import { ONSET_FLOOR } from '../voice/excitation'

/** Sample a source at 60 fps for `seconds`; returns per-frame level arrays. */
function sample(seed: number | undefined, seconds: number, count = 6): Float32Array[] {
  const src = createSpeechBurstSource(seed === undefined ? {} : { seed })
  src.start()
  const frames: Float32Array[] = []
  for (let i = 0; i < Math.round(seconds * 60); i++) {
    const out = new Float32Array(count)
    src.readEnergies(out, i / 60)
    frames.push(out)
  }
  src.stop()
  return frames
}

describe('createSpeechBurstSource — the shared demo voice', () => {
  it('is deterministic for a seed and differs across seeds', () => {
    const a = sample(7, 2)
    const b = sample(7, 2)
    const c = sample(8, 2)
    expect(a.map((f) => Array.from(f))).toEqual(b.map((f) => Array.from(f)))
    expect(a.map((f) => Array.from(f))).not.toEqual(c.map((f) => Array.from(f)))
  })

  it('keeps every level inside [0, 1]', () => {
    for (const f of sample(1, 6)) {
      for (const v of f) {
        expect(v).toBeGreaterThanOrEqual(0)
        expect(v).toBeLessThanOrEqual(1)
      }
    }
  })

  it('speaks in syllables: sharp onsets a few times a second', () => {
    const frames = sample(1, 3)
    let sharpest = 0
    let onsets = 0
    let lastOnset = -1
    for (let i = 1; i < frames.length; i++) {
      let rise = 0
      for (let k = 0; k < 6; k++) rise = Math.max(rise, frames[i][k] - frames[i - 1][k])
      sharpest = Math.max(sharpest, rise)
      // a new syllable: a strike-worthy rise at least 80 ms after the last
      if (rise > 4 * ONSET_FLOOR && i - lastOnset > 5) {
        onsets++
        lastOnset = i
      }
    }
    expect(sharpest).toBeGreaterThan(0.15)
    expect(onsets).toBeGreaterThanOrEqual(6)
    expect(onsets).toBeLessThanOrEqual(24)
  })

  it('walks the whole register over a few seconds', () => {
    const frames = sample(1, 8)
    for (let k = 0; k < 6; k++) {
      const peak = Math.max(...frames.map((f) => f[k]))
      expect(peak).toBeGreaterThan(0.15)
    }
  })

  it('breathes: leaves a pause of at least 0.3 s within eight seconds', () => {
    const frames = sample(1, 8)
    let quiet = 0
    let longest = 0
    for (const f of frames) {
      const loud = Math.max(...f) > 0.05
      quiet = loud ? 0 : quiet + 1
      longest = Math.max(longest, quiet)
    }
    expect(longest).toBeGreaterThanOrEqual(18) // 0.3 s at 60 fps
  })

  it('fills whatever tine count it is handed (display density)', () => {
    const frames = sample(1, 1, 10)
    expect(frames[30]).toHaveLength(10)
    expect(Math.max(...frames.map((f) => Math.max(...f)))).toBeGreaterThan(0.3)
  })

  it('reads as silence before it is started', () => {
    const src = createSpeechBurstSource({ seed: 1 })
    const out = new Float32Array(6).fill(0.5)
    expect(src.readEnergies(out, 1)).toBe(6)
    expect(Array.from(out)).toEqual([0, 0, 0, 0, 0, 0])
  })
})
