// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * FFT bin -> tine energy mapping and the AudioEnergySource abstraction.
 *
 * Spec §3.4 groups linear FFT bins into the 10 vocal registers of §2.2.
 * Browser AudioContexts typically run at 44.1/48kHz regardless of the 16kHz
 * capture rate, so bin edges are COMPUTED from the context sample rate and
 * bin count (spec formula: nearest bin center to each band edge). At the
 * reference 16kHz/64-bin configuration this reproduces the spec table
 * bit-for-bit (test-enforced).
 *
 * The AudioReactiveHalbertMark component only knows AudioEnergySource —
 * Web Audio types never appear in its props (SSR/Storybook-safe).
 */

import { TINE_COUNT } from './geometry'

/** Vocal register band edges in Hz, inner (tine 0) to outer (tine 9). */
export const TINE_BAND_HZ: ReadonlyArray<readonly [number, number]> = [
  [4000, 8000], // brilliance / air
  [2500, 4000], // sibilance
  [1500, 2500], // upper mids
  [1000, 1500], // vowel clarity
  [700, 1000], // vocal core
  [500, 700], // vowel body
  [350, 500], // warmth
  [200, 350], // chest formant
  [100, 200], // vocal fundamental
  [40, 100], // sub-bass / room
]

/** The spec §3.4 reference table (16kHz sample rate, 64 FFT bins). */
export const TINE_BIN_RANGES_16K_64: ReadonlyArray<readonly [number, number]> = [
  [32, 64],
  [20, 32],
  [12, 20],
  [8, 12],
  [6, 8],
  [4, 6],
  [3, 4],
  [2, 3],
  [1, 2],
  [0, 1],
]

/** Bins 0-1 are mostly DC and room rumble; keep the outer arc calm (§3.4). */
export const SUB_BASS_ATTENUATION = 0.3

/**
 * Bin ranges (inclusive lower, exclusive upper) for a given context rate and
 * bin count. Band edges are rounded to the nearest bin — the center-frequency
 * argmin rule from spec §3.4.
 */
export function binRangesFor(
  sampleRate: number,
  binCount: number,
): Array<[number, number]> {
  const hzPerBin = sampleRate / 2 / binCount
  return TINE_BAND_HZ.map(([lo, hi]) => {
    const a = Math.min(binCount - 1, Math.max(0, Math.round(lo / hzPerBin)))
    const b = Math.min(binCount, Math.max(a + 1, Math.round(hi / hzPerBin)))
    return [a, b] as [number, number]
  })
}

/** Mean-normalized per-tine energies for one byte-frequency frame. */
export function tineEnergies(
  freqData: Uint8Array,
  ranges: ReadonlyArray<readonly [number, number]> = TINE_BIN_RANGES_16K_64,
  out: Float32Array = new Float32Array(TINE_COUNT),
): Float32Array {
  for (let k = 0; k < TINE_COUNT; k++) {
    const [lo, hi] = ranges[k]
    let sum = 0
    for (let j = lo; j < hi && j < freqData.length; j++) sum += freqData[j]
    let e = hi > lo ? sum / (hi - lo) / 255 : 0
    if (k === TINE_COUNT - 1) e *= SUB_BASS_ATTENUATION
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
  /** Fill `out` with per-tine energies in [0, 1]; returns tine count. */
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
    return TINE_COUNT
  }
}

/** Slow 3.5s breathing for idle/standby (spec §4.1 state 1). */
export class IdleBreathingSource implements AudioEnergySource {
  start(): void {}
  stop(): void {}
  readEnergies(out: Float32Array, tSeconds: number): number {
    const w = (2 * Math.PI * tSeconds) / 3.5
    for (let k = 0; k < TINE_COUNT; k++) {
      out[k] = Math.max(0, 0.05 + 0.045 * Math.sin(w + k * 0.55))
    }
    return TINE_COUNT
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
): AudioEnergySource {
  const binCount = analyser.frequencyBinCount
  const ranges = binRangesFor(sampleRate, binCount)
  const bytes = new Uint8Array(binCount)
  return {
    start() {},
    stop() {},
    readEnergies(out: Float32Array): number {
      analyser.getByteFrequencyData(bytes)
      tineEnergies(bytes, ranges, out)
      return TINE_COUNT
    },
  }
}

export interface MediaStreamAnalyserOptions {
  /** fftSize 128 -> 64 bins (128-sample frames are plenty for 10 bands). */
  fftSize?: number
  minDecibels?: number // default -85 (voice floor)
  maxDecibels?: number // default -25
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
      inner = createAnalyserEnergySource(analyser, context.sampleRate)
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
  return {
    start() {
      const analyser = node.context.createAnalyser()
      analyser.fftSize = opts.fftSize ?? 128
      analyser.smoothingTimeConstant = 0
      analyser.minDecibels = opts.minDecibels ?? -85
      analyser.maxDecibels = opts.maxDecibels ?? -25
      node.connect(analyser)
      inner = createAnalyserEnergySource(analyser, node.context.sampleRate)
    },
    stop() {
      inner = null
    },
    readEnergies(out: Float32Array, t: number): number {
      return inner ? inner.readEnergies(out, t) : 0
    },
  }
}
