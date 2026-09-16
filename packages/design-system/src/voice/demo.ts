// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The shared demo voice for surfaces without a microphone: Storybook and
 * the marketing site's Voice Mode plate (design doc 17 §"Demo source").
 *
 * Speech is syllables — a sharp attack, an exponential decay, each syllable
 * with its own spectral centre — grouped into phrases with a breath between.
 * That is what makes the strings pluck the way they do on a real voice; a
 * smooth sweep never crosses the onset floor and never strikes anything.
 * Optionally a clap lands in a breath every few seconds: every band at once,
 * gone within a tenth of a second — the listening posture's startle.
 *
 * Deterministic per seed, so a page reload replays the same performance.
 */

import type { AudioEnergySource } from './spectrum'

export interface SpeechBurstOptions {
  /** Seed for the pseudo-random phrase generator. @default 1 */
  seed?: number
  /** Mean syllable rate. @default 4 */
  syllablesPerSecond?: number
  /** Clap in a breath every [min, max] seconds. Off when omitted. */
  clapEverySeconds?: readonly [number, number]
}

/** Syllable envelope: linear attack, then exponential decay. */
const ATTACK_SECONDS = 0.02
const DECAY_SECONDS = 0.12
/** A syllable below this fraction of its peak is dropped from the sum. */
const SYLLABLE_LIFETIME = ATTACK_SECONDS + DECAY_SECONDS * 4
const PHRASE_SYLLABLES: readonly [number, number] = [5, 9]
const BREATH_SECONDS: readonly [number, number] = [0.45, 0.8]
/** How far ahead of the frame clock syllables are laid out. */
const LOOKAHEAD_SECONDS = 0.5
/** The outermost arc is sub-bass and room; a voice barely reaches it. */
const SUB_BASS_WEIGHT = 0.5
/** A clap: every band, instantly, then a 25 ms decay. */
const CLAP_LEVEL = 0.85
const CLAP_DECAY_SECONDS = 0.025
const CLAP_LIFETIME = CLAP_DECAY_SECONDS * 6
/** A clap lands this long into a breath, once the last syllable has died. */
const CLAP_INTO_BREATH_SECONDS = 0.3

interface Syllable {
  start: number
  /** Spectral centre as a fraction of the register, 0 = spine, 1 = outer arc. */
  centre: number
  /** Gaussian width in register fractions. */
  width: number
  peak: number
}

/** mulberry32 — small, fast, deterministic. */
function seededRandom(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function between(random: () => number, [lo, hi]: readonly [number, number]): number {
  return lo + random() * (hi - lo)
}

export function createSpeechBurstSource(opts: SpeechBurstOptions = {}): AudioEnergySource {
  const seed = opts.seed ?? 1
  const spacing = 1 / (opts.syllablesPerSecond ?? 4)
  const clapEvery = opts.clapEverySeconds ?? null
  let random = seededRandom(seed)
  let started = false
  let syllables: Syllable[] = []
  let claps: number[] = []
  let nextStart: number | null = null
  let leftInPhrase = 0
  let clapDue = Infinity

  const layOut = (until: number) => {
    if (nextStart === null) return
    while (nextStart < until) {
      if (leftInPhrase <= 0) leftInPhrase = Math.round(between(random, PHRASE_SYLLABLES))
      syllables.push({
        start: nextStart,
        centre: between(random, [0.05, 0.95]),
        width: between(random, [0.16, 0.26]),
        peak: between(random, [0.5, 1]),
      })
      leftInPhrase--
      nextStart += spacing * between(random, [0.75, 1.25])
      if (leftInPhrase <= 0) {
        // a breath — and, when one is due, a clap in the quiet of it
        if (clapEvery && nextStart >= clapDue) {
          const clapAt = nextStart + CLAP_INTO_BREATH_SECONDS
          claps.push(clapAt)
          clapDue = clapAt + between(random, clapEvery)
        }
        nextStart += between(random, BREATH_SECONDS)
      }
    }
  }

  return {
    start() {
      random = seededRandom(seed)
      syllables = []
      claps = []
      nextStart = null
      leftInPhrase = 0
      clapDue = Infinity
      started = true
    },
    stop() {
      started = false
    },
    readEnergies(out: Float32Array, t: number): number {
      out.fill(0)
      if (!started) return out.length
      if (nextStart === null) {
        nextStart = t + 0.05
        if (clapEvery) clapDue = t + between(random, clapEvery)
      }
      layOut(t + LOOKAHEAD_SECONDS)
      syllables = syllables.filter((s) => t - s.start < SYLLABLE_LIFETIME)
      claps = claps.filter((c) => t - c < CLAP_LIFETIME)
      const count = out.length
      const span = Math.max(1, count - 1)
      for (const s of syllables) {
        const age = t - s.start
        if (age < 0) continue
        const env =
          age < ATTACK_SECONDS
            ? age / ATTACK_SECONDS
            : Math.exp(-(age - ATTACK_SECONDS) / DECAY_SECONDS)
        const level = s.peak * env
        for (let k = 0; k < count; k++) {
          const z = (k / span - s.centre) / s.width
          out[k] += level * Math.exp(-z * z)
        }
      }
      out[count - 1] *= SUB_BASS_WEIGHT
      let clap = 0
      for (const c of claps) {
        const age = t - c
        if (age >= 0) clap += CLAP_LEVEL * Math.exp(-age / CLAP_DECAY_SECONDS)
      }
      for (let k = 0; k < count; k++) out[k] = Math.min(1, out[k] + clap)
      return count
    },
  }
}
