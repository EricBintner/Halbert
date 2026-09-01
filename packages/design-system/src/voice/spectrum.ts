// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * FFT bin -> tine energy mapping and the AudioEnergySource abstraction.
 *
 * Vocal registers map low -> outer/lower tines and high -> center/upper
 * tines: the spine is brilliance/air (4-8 kHz) and the outermost arc is
 * sub-bass (40-100 Hz), in both densities:
 *
 *   medium (6 tines, Voice Mode default):
 *     spine  4000-8000 | 86.4: 1500-4000 | 172.8: 700-1500
 *     259.2: 350-700   | 345.6: 100-350  | 432:   40-100
 *   display (10 tines): the full spec §2.2 table.
 *
 * Spec §3.4 groups linear FFT bins into these registers. Browser
 * AudioContexts typically run at 44.1/48kHz regardless of the 16kHz capture
 * rate, so bin edges are COMPUTED from the context sample rate and bin
 * count (nearest-bin-center rule). At the reference 16kHz/64-bin grid this
 * reproduces the reference tables bit-for-bit (test-enforced).
 *
 * The AudioReactiveHalbertMark component only knows AudioEnergySource —
 * Web Audio types never appear in its props (SSR/Storybook-safe).
 */

import { tineCount, type VoiceDensity } from './geometry'

/** Vocal register band edges in Hz per density, inner tine to outer. */
export const TINE_BAND_HZ: Record<VoiceDensity, ReadonlyArray<readonly [number, number]>> = {
  medium: [
    [4000, 8000], // spine: brilliance / air
    [1500, 4000], // sibilance + upper mids
    [700, 1500],  // vowel clarity + vocal core
    [350, 700],   // vowel body + warmth
    [100, 350],   // chest formant + fundamental
    [40, 100],    // outermost arc: sub-bass / room
  ],
  display: [
    [4000, 8000], [2500, 4000], [1500, 2500], [1000, 1500], [700, 1000],
    [500, 700], [350, 500], [200, 350], [100, 200], [40, 100],
  ],
}

/** Reference bin tables (16kHz sample rate, 64 FFT bins). */
export const TINE_BIN_RANGES_16K_64: Record<VoiceDensity, ReadonlyArray<readonly [number, number]>> = {
  medium: [
    [32, 64], [12, 32], [6, 12], [3, 6], [1, 3], [0, 1],
  ],
  display: [
    [32, 64], [20, 32], [12, 20], [8, 12], [6, 8],
    [4, 6], [3, 4], [2, 3], [1, 2], [0, 1],
  ],
}

/** Bin 0 is mostly DC and room rumble; keep the outermost arc calm (§3.4). */
export const SUB_BASS_ATTENUATION = 0.3

/**
 * Bin ranges (inclusive lower, exclusive upper) for a given context rate and
 * bin count. Band edges are rounded to the nearest bin — the center-frequency
 * argmin rule from spec §3.4.
 */
export function binRangesFor(
  sampleRate: number,
  binCount: number,
  density: VoiceDensity = 'medium',
): Array<[number, number]> {
  const hzPerBin = sampleRate / 2 / binCount
  return TINE_BAND_HZ[density].map(([lo, hi]) => {
    const a = Math.min(binCount - 1, Math.max(0, Math.round(lo / hzPerBin)))
    const b = Math.min(binCount, Math.max(a + 1, Math.round(hi / hzPerBin)))
    return [a, b] as [number, number]
  })
}

/** Mean-normalized per-tine energies for one byte-frequency frame. The last
 * band (sub-bass) is attenuated; output length follows the ranges. */
export function tineEnergies(
  freqData: Uint8Array,
  ranges: ReadonlyArray<readonly [number, number]> = TINE_BIN_RANGES_16K_64.medium,
  out: Float32Array = new Float32Array(ranges.length),
): Float32Array {
  for (let k = 0; k < ranges.length; k++) {
    const [lo, hi] = ranges[k]
    let sum = 0
    for (let j = lo; j < hi && j < freqData.length; j++) sum += freqData[j]
    let e = hi > lo ? sum / (hi - lo) / 255 : 0
    if (k === ranges.length - 1) e *= SUB_BASS_ATTENUATION
    out[k] = e
  }
  return out
}

/** What the mark consumes each frame. Implementations own their resources. */
export interface AudioEnergySource {
  /** Allocate resources. May reject; the component logs and renders static. */
  start(): void | Promise<void>
  /** Release resources. Idempotent. */
  stop(): void
  /** Fill `out` with per-tine energies in [0, 1]; returns entries written. */
  readEnergies(out: Float32Array, tSeconds: number): number
}

/** Scripted energies for tests and Storybook (no audio hardware needed). */
export class SyntheticEnergySource implements AudioEnergySource {
  constructor(
    private readonly script: (t: number, out: Float32Array) => void,
  ) {}
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array, tSeconds: number): number {
    out.fill(0)
    this.script(tSeconds, out)
    return out.length
  }
}

/** Slow 3.5s breathing for idle/standby (spec §4.1 state 1). */
export class IdleBreathingSource implements AudioEnergySource {
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array, tSeconds: number): number {
    const w = (2 * Math.PI * tSeconds) / 3.5
    for (let k = 0; k < out.length; k++) {
      out[k] = Math.max(0, 0.05 + 0.045 * Math.sin(w + k * 0.55))
    }
    return out.length
  }
}

/** Minimal structural view of an AnalyserNode (no DOM type leak, mockable). */
export interface ByteFrequencyNode {
  readonly frequencyBinCount: number
  getByteFrequencyData(out: Uint8Array): void
}

/** Adapt any analyser (real or mock) into an energy source. */
export function createAnalyserEnergySource(
  analyser: ByteFrequencyNode,
  sampleRate: number,
  density: VoiceDensity = 'medium',
): AudioEnergySource {
  const binCount = analyser.frequencyBinCount
  const ranges = binRangesFor(sampleRate, binCount, density)
  const bytes = new Uint8Array(binCount)
  const count = tineCount(density)
  return {
    start() {},
    stop() {},
    readEnergies(out: Float32Array): number {
      analyser.getByteFrequencyData(bytes)
      tineEnergies(bytes, ranges, out)
      return count
    },
  }
}

export interface MediaStreamAnalyserOptions {
  /** fftSize 128 -> 64 bins (128-sample frames are plenty for 6 bands). */
  fftSize?: number
  minDecibels?: number // default -85 (voice floor)
  maxDecibels?: number // default -25
  /** Tine density of the mark being driven. @default 'medium' */
  density?: VoiceDensity
}

/**
 * Browser glue: build an analyser source from a getUserMedia stream.
 * The AudioContext is created lazily in start() — call sites must invoke it
 * from a user gesture (browsers block audio startup otherwise).
 */
export function createMediaStreamAnalyserSource(
  stream: MediaStream,
  opts: MediaStreamAnalyserOptions = {},
): AudioEnergySource {
  let context: AudioContext | null = null
  let inner: AudioEnergySource | null = null
  return {
    start() {
      if (typeof window === 'undefined') return
      context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const analyser = context.createAnalyser()
      analyser.fftSize = opts.fftSize ?? 128
      analyser.smoothingTimeConstant = 0 // the spring bank smooths instead
      analyser.minDecibels = opts.minDecibels ?? -85
      analyser.maxDecibels = opts.maxDecibels ?? -25
      source.connect(analyser) // analyser is a terminal node — no audible tap
      inner = createAnalyserEnergySource(analyser, context.sampleRate, opts.density ?? 'medium')
    },
    stop() {
      inner = null
      void context?.close()
      context = null
    },
    readEnergies(out: Float32Array, t: number): number {
      return inner ? inner.readEnergies(out, t) : 0
    },
  }
}

/** Same glue for an existing node (e.g. the Phase-2 TTS playback tap). */
export function createNodeAnalyserSource(
  node: AudioNode,
  opts: MediaStreamAnalyserOptions = {},
): AudioEnergySource {
  let inner: AudioEnergySource | null = null
  let analyser: AnalyserNode | null = null
  return {
    start() {
      const created = node.context.createAnalyser()
      created.fftSize = opts.fftSize ?? 128
      created.smoothingTimeConstant = 0
      created.minDecibels = opts.minDecibels ?? -85
      created.maxDecibels = opts.maxDecibels ?? -25
      node.connect(created)
      analyser = created
      inner = createAnalyserEnergySource(created, node.context.sampleRate, opts.density ?? 'medium')
    },
    stop() {
      inner = null
      // The mark effect re-runs start() on every state change; without the
      // disconnect each restart would leave a permanently-connected
      // analyser on a long-lived node (the mic tap / TTS out), accumulating
      // unbounded over a kiosk session.
      analyser?.disconnect()
      analyser = null
    },
    readEnergies(out: Float32Array, t: number): number {
      return inner ? inner.readEnergies(out, t) : 0
    },
  }
}
