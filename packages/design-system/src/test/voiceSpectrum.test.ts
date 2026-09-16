// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  TINE_BAND_HZ,
  TINE_BIN_RANGES_16K_64,
  SUB_BASS_ATTENUATION,
  DEFAULT_FFT_SIZE,
  binRangesFor,
  tineEnergies,
  SyntheticEnergySource,
  IdleBreathingSource,
  createAnalyserEnergySource,
  createNodeAnalyserSource,
} from '../voice/spectrum'

describe('FFT bin mapping', () => {
  it('reproduces the spec table exactly at 16kHz / 64 bins', () => {
    expect(binRangesFor(16000, 64, 'display')).toEqual(TINE_BIN_RANGES_16K_64.display)
    expect(binRangesFor(16000, 64, 'medium')).toEqual(TINE_BIN_RANGES_16K_64.medium)
    expect(binRangesFor(16000, 64, 'brand')).toEqual(TINE_BIN_RANGES_16K_64.brand)
    expect(binRangesFor(16000, 64)).toEqual(TINE_BIN_RANGES_16K_64.brand) // the default
  })

  it('brand (7 tines, the default) is an octave ladder from 8 kHz air to 40 Hz room', () => {
    expect(TINE_BAND_HZ.brand).toEqual([
      [4000, 8000],
      [2000, 4000],
      [1000, 2000],
      [500, 1000],
      [250, 500],
      [100, 250],
      [40, 100],
    ])
    expect(TINE_BIN_RANGES_16K_64.brand).toEqual([
      [32, 64], [16, 32], [8, 16], [4, 8], [2, 4], [1, 2], [0, 1],
    ])
  })

  it('at a 48kHz context the default FFT keeps every brand band on its own bins', () => {
    // Browser contexts run at 44.1/48 kHz whatever the capture rate. With
    // the old 128-point FFT (375 Hz per bin) the three low bands collapsed
    // onto bin 0; the default is now 2048 points (23.4 Hz per bin), whose
    // 43 ms window also covers a whole 30 fps frame.
    expect(DEFAULT_FFT_SIZE).toBe(2048)
    const ranges = binRangesFor(48000, DEFAULT_FFT_SIZE / 2, 'brand')
    for (let k = 1; k < ranges.length; k++) {
      expect(ranges[k][1]).toBeLessThanOrEqual(ranges[k - 1][0]) // disjoint, descending
      expect(ranges[k][1]).toBeGreaterThan(ranges[k][0]) // non-empty
    }
    expect(ranges[ranges.length - 1]).toEqual([2, 4]) // 40-100 Hz
    expect(ranges[ranges.length - 2]).toEqual([4, 11]) // 100-250 Hz
  })

  it('rescales for a 48kHz context', () => {
    expect(binRangesFor(48000, 192, 'medium')).toEqual(TINE_BIN_RANGES_16K_64.medium)
    const coarse = binRangesFor(48000, 64, 'display') // 375 Hz per bin
    expect(coarse[0]).toEqual([11, 21]) // 4000/375=10.7->11, 8000/375=21.3->21
    expect(coarse[9]).toEqual([0, 1]) // 40..100 Hz clamps to 1 bin
  })

  it('keeps the low->outer / high->center ordering for every density', () => {
    for (const bands of [TINE_BAND_HZ.brand, TINE_BAND_HZ.medium, TINE_BAND_HZ.display]) {
      for (let k = 1; k < bands.length; k++) {
        // every tine's band sits strictly below the tine inside it
        expect(bands[k][1]).toBeLessThanOrEqual(bands[k - 1][0] + 1e-9)
      }
      expect(bands[0][1]).toBe(8000) // spine = brilliance
      expect(bands[bands.length - 1][0]).toBe(40) // outermost = sub-bass
    }
  })

  it('normalizes mean band energy to [0, 1] with sub-bass attenuation', () => {
    const out = tineEnergies(new Uint8Array(64).fill(255))
    expect(out).toHaveLength(7) // brand default
    expect(out[0]).toBeCloseTo(1, 5)
    expect(out[5]).toBeCloseTo(1, 5)
    expect(out[6]).toBeCloseTo(SUB_BASS_ATTENUATION, 5)
    const displayOut = tineEnergies(
      new Uint8Array(64).fill(255),
      TINE_BIN_RANGES_16K_64.display,
    )
    expect(displayOut).toHaveLength(10)
    expect(displayOut[9]).toBeCloseTo(SUB_BASS_ATTENUATION, 5)
    expect(Array.from(tineEnergies(new Uint8Array(64)))).toEqual(new Array(7).fill(0))
  })

  it('maps outer-lane bands and spine bins to the right tines', () => {
    // 16kHz reference grid, brand density: tine 5 (chest/fundamental
    // 100-250 Hz) = bin [1,2); tine 0 (spine, brilliance 4-8kHz) = [32,64)
    const outerLane = tineEnergies(new Uint8Array(64).fill(255, 1, 2))
    expect(outerLane[5]).toBeCloseTo(1, 5)
    expect(outerLane[0]).toBe(0)
    const spine = tineEnergies(new Uint8Array(64).fill(255, 32, 64))
    expect(spine[0]).toBeCloseTo(1, 5)
    expect(spine[5]).toBe(0)
  })
})

describe('energy sources', () => {
  it('SyntheticEnergySource replays a script deterministically', () => {
    const src = new SyntheticEnergySource((t, out) => {
      out[3] = t
    })
    const out = new Float32Array(6)
    src.readEnergies(out, 0.25)
    expect(out[3]).toBeCloseTo(0.25, 5)
    expect(out[0]).toBe(0)
  })

  it('IdleBreathingSource fills the caller buffer and stays in envelope', () => {
    const src = new IdleBreathingSource()
    const out = new Float32Array(6)
    for (const t of [0, 0.7, 1.4, 2.1, 2.8, 3.5, 100]) {
      const n = src.readEnergies(out, t)
      expect(n).toBe(6)
      for (const v of out) {
        expect(v).toBeGreaterThanOrEqual(0)
        expect(v).toBeLessThanOrEqual(0.12)
      }
    }
  })

  it('createAnalyserEnergySource maps byte spectra through computed ranges', () => {
    // 64 bins at 48kHz -> 375 Hz/bin; the brilliance band is bins [11, 21]
    const bins = new Uint8Array(64)
    bins.fill(255, 11, 21)
    const fakeAnalyser = {
      frequencyBinCount: 64,
      getByteFrequencyData(out: Uint8Array) {
        out.set(bins)
      },
    }
    const src = createAnalyserEnergySource(fakeAnalyser, 48000)
    const out = new Float32Array(7)
    expect(src.readEnergies(out, 0)).toBe(7) // brand default
    expect(out[0]).toBeCloseTo(1, 5)
    expect(out[3]).toBeCloseTo(0, 5) // vowel body stays dark
  })

  it('createNodeAnalyserSource disconnects its analyser on stop (no accumulation)', () => {
    // The mark effect re-runs start() on every state change; each restart
    // must not leave another permanently-connected analyser on a
    // long-lived node (the Voice Mode mic tap / TTS out live for hours).
    const analysers: Array<{
      fftSize: number
      connected: unknown[]
      disconnected: boolean
      frequencyBinCount: number
      getByteFrequencyData: (out: Uint8Array) => void
    }> = []
    const tap = {
      context: {
        sampleRate: 48000,
        createAnalyser() {
          const analyser = {
            fftSize: 0,
            smoothingTimeConstant: 0,
            minDecibels: 0,
            maxDecibels: 0,
            frequencyBinCount: 64,
            connected: [] as unknown[],
            disconnected: false,
            getByteFrequencyData(out: Uint8Array) {
              out.fill(128)
            },
            disconnect() {
              analyser.disconnected = true
            },
          }
          analysers.push(analyser)
          return analyser
        },
      },
      connect(dest: unknown) {
        analysers[analysers.length - 1].connected.push(dest)
      },
    }
    const src = createNodeAnalyserSource(tap as unknown as AudioNode)

    src.start()
    src.stop()
    src.start() // the mark effect's restart cycle

    expect(analysers).toHaveLength(2) // one per start, not one per lifetime
    expect(analysers[0].disconnected).toBe(true) // the retired one is gone
    expect(analysers[1].disconnected).toBe(false)
    expect(analysers[1].connected).toHaveLength(1)
    expect(analysers[1].fftSize).toBe(DEFAULT_FFT_SIZE)

    // The live analyser still flows energy (7 tines — the brand default).
    const out = new Float32Array(7)
    expect(src.readEnergies(out, 0)).toBe(7)
    expect(out.every((v) => v > 0)).toBe(true)

    // stop() is idempotent.
    src.stop()
    src.stop()
    expect(analysers[1].disconnected).toBe(true)
  })
})
