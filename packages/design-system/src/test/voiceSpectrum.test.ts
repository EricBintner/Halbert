// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  TINE_BAND_HZ,
  TINE_BIN_RANGES_16K_64,
  SUB_BASS_ATTENUATION,
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
  })

  it('rescales for a 48kHz context', () => {
    expect(binRangesFor(48000, 192, 'medium')).toEqual(TINE_BIN_RANGES_16K_64.medium)
    const coarse = binRangesFor(48000, 64, 'display') // 375 Hz per bin
    expect(coarse[0]).toEqual([11, 21]) // 4000/375=10.7->11, 8000/375=21.3->21
    expect(coarse[9]).toEqual([0, 1]) // 40..100 Hz clamps to 1 bin
  })

  it('keeps the low->outer / high->center ordering for both densities', () => {
    for (const bands of [TINE_BAND_HZ.medium, TINE_BAND_HZ.display]) {
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
    expect(out).toHaveLength(6) // medium default
    expect(out[0]).toBeCloseTo(1, 5)
    expect(out[4]).toBeCloseTo(1, 5)
    expect(out[5]).toBeCloseTo(SUB_BASS_ATTENUATION, 5)
    const displayOut = tineEnergies(
      new Uint8Array(64).fill(255),
      TINE_BIN_RANGES_16K_64.display,
    )
    expect(displayOut).toHaveLength(10)
    expect(displayOut[9]).toBeCloseTo(SUB_BASS_ATTENUATION, 5)
    expect(Array.from(tineEnergies(new Uint8Array(64)))).toEqual(new Array(6).fill(0))
  })

  it('maps outer-lane bands and spine bins to the right tines', () => {
    // 16kHz reference grid, medium density: tine 4 (chest/fundamental
    // 100-350 Hz) = bins [1,3); tine 0 (spine, brilliance 4-8kHz) = [32,64)
    const outerLane = tineEnergies(new Uint8Array(64).fill(255, 1, 3))
    expect(outerLane[4]).toBeCloseTo(1, 5)
    expect(outerLane[0]).toBe(0)
    const spine = tineEnergies(new Uint8Array(64).fill(255, 32, 64))
    expect(spine[0]).toBeCloseTo(1, 5)
    expect(spine[4]).toBe(0)
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
    // 64 bins at 48kHz -> 375 Hz/bin; medium brilliance band is bins [11, 21]
    const bins = new Uint8Array(64)
    bins.fill(255, 11, 21)
    const fakeAnalyser = {
      frequencyBinCount: 64,
      getByteFrequencyData(out: Uint8Array) {
        out.set(bins)
      },
    }
    const src = createAnalyserEnergySource(fakeAnalyser, 48000)
    const out = new Float32Array(6)
    expect(src.readEnergies(out, 0)).toBe(6)
    expect(out[0]).toBeCloseTo(1, 5)
    expect(out[3]).toBeCloseTo(0, 5) // vowel body stays dark
  })

  it('createNodeAnalyserSource disconnects its analyser on stop (no accumulation)', () => {
    // The mark effect re-runs start() on every state change; each restart
    // must not leave another permanently-connected analyser on a
    // long-lived node (the Voice Mode mic tap / TTS out live for hours).
    const analysers: Array<{
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

    // The live analyser still flows energy (6 tines — v2 medium default).
    const out = new Float32Array(6)
    expect(src.readEnergies(out, 0)).toBe(6)
    expect(out.every((v) => v > 0)).toBe(true)

    // stop() is idempotent.
    src.stop()
    src.stop()
    expect(analysers[1].disconnected).toBe(true)
  })
})
