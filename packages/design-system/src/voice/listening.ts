// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The listening posture (design doc 17 §"Listening — retraction").
 *
 * While the mark listens, each line withdraws its ends along its own path.
 * Two things drive how far, and neither is a level meter:
 *
 *   presence — any sustained sound raises an attention envelope quickly
 *              (150 ms) and lets it go slowly (1.8 s), so the mark keeps
 *              listening for a moment after you stop. At full attention each
 *              end drifts on its own slow curve between presenceMin and
 *              presenceMax, ends and lines out of phase, so speech reads as
 *              "it is listening", not as syllables.
 *   impact   — only a broadband transient (a clap, a door) drives a quick,
 *              critically damped retraction that scales with the hit, up to
 *              impactMax on the outer lines, then relaxes. "Broadband" is
 *              the test: nearly every band must rise together over a fixed
 *              50 ms window. A syllable is a gaussian over the register and
 *              lifts at most five of seven bands; a clap lifts them all.
 *              Measuring over a window, not a frame, keeps 30 fps and 60 fps
 *              identical.
 *
 * The spine's bottom end is the mark's centre and never retracts; the
 * spine withdraws from the top. Everything here is deterministic, and all
 * timing runs on elapsed frame time, never on the absolute clock.
 */

export const LISTENING = Object.freeze({
  /** Loudest band above this counts as sound. */
  soundFloor: 0.04,
  /** Attention rises with this time constant… */
  attackSeconds: 0.15,
  /** …and releases with this one: the "still listening" afterglow. */
  releaseSeconds: 1.8,
  /** Retraction per end at full attention: the low and high of the drift. */
  presenceMin: 0.1,
  presenceMax: 0.15,
  /** The slow organic drift; outer lines drift a little slower than inner. */
  driftHz: 0.35,
  /** A band's rise is measured against its level this long ago. */
  riseWindowSeconds: 0.05,
  /** A band counts as risen when it climbed by more than this. */
  bandRiseFloor: 0.15,
  /** At most this many bands may sit a hit out and it still counts as
   * broadband (the sub-bass band is usually the one). */
  bandsAllowedQuiet: 1,
  /** Mean rise across all bands that reaches impactMax (the floor reaches 0). */
  impactFullRise: 0.65,
  /** Retraction per end on the hardest impact, outer line. With presence at
   * its peak this still leaves a quarter of the outer arc and more of every
   * other line: a clap startles, it never closes a line. */
  impactMax: 0.24,
  /** The impact rises this fast, holds, then releases. */
  impactRiseSeconds: 0.03,
  impactHoldSeconds: 0.12,
  impactReleaseSeconds: 0.45,
  /** The spine takes this share of the outer line's impact. */
  innerImpactShare: 0.7,
  /** No end withdraws past this: a fifth of every line always remains. */
  maxPerEnd: 0.4,
})

/** Golden angle: spreads per-end drift phases so nothing moves in step. */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))
/** Frames of level history kept for the rise window (67 ms at 240 fps). */
const HISTORY = 16

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
}

export class Listener {
  private readonly history: Float32Array[]
  private readonly historyElapsed: Float64Array
  private historyHead = -1
  private historyFilled = 0
  private elapsed = 0
  private attentionLevel = 0
  private impactTarget = 0
  private impactLevel = 0
  private impactHoldLeft = 0
  private now = 0

  constructor(private readonly count: number) {
    this.history = Array.from({ length: HISTORY }, () => new Float32Array(count))
    this.historyElapsed = new Float64Array(HISTORY)
  }

  /** 0 (silence for a while) … 1 (sound now). */
  get attention(): number {
    return this.attentionLevel
  }

  /** Current impact retraction before the per-line profile, 0 … impactMax. */
  get impact(): number {
    return this.impactLevel
  }

  /** Carry the envelopes over from another listener (a density change
   * rebuilds the engine; the posture must not restart from silence). */
  adopt(other: Listener): void {
    this.attentionLevel = other.attentionLevel
    this.impactTarget = other.impactTarget
    this.impactLevel = other.impactLevel
    this.impactHoldLeft = other.impactHoldLeft
    this.now = other.now
  }

  /** Feed one frame of band levels; `t` is the frame clock in seconds. */
  feed(levels: ArrayLike<number>, dt: number, t: number): void {
    const h = Number.isFinite(dt) && dt > 0 ? dt : 0
    if (Number.isFinite(t)) this.now = t
    this.elapsed += h
    const c = LISTENING

    // Record this frame, then find the newest frame at least a window old.
    this.historyHead = (this.historyHead + 1) % HISTORY
    const current = this.history[this.historyHead]
    let loudest = 0
    for (let k = 0; k < this.count; k++) {
      const v = clamp01(levels[k] ?? 0)
      current[k] = v
      if (v > loudest) loudest = v
    }
    this.historyElapsed[this.historyHead] = this.elapsed
    if (this.historyFilled < HISTORY) this.historyFilled++
    let baseline: Float32Array | null = null
    for (let back = 1; back < this.historyFilled; back++) {
      const i = (this.historyHead - back + HISTORY) % HISTORY
      baseline = this.history[i]
      if (this.elapsed - this.historyElapsed[i] >= c.riseWindowSeconds) break
    }

    const target = loudest > c.soundFloor ? 1 : 0
    const tau = target > this.attentionLevel ? c.attackSeconds : c.releaseSeconds
    this.attentionLevel += (target - this.attentionLevel) * (1 - Math.exp(-h / tau))

    let hit = 0
    if (baseline) {
      let risen = 0
      let riseSum = 0
      for (let k = 0; k < this.count; k++) {
        const rise = current[k] - baseline[k]
        if (rise > c.bandRiseFloor) risen++
        if (rise > 0) riseSum += rise
      }
      if (risen >= this.count - c.bandsAllowedQuiet) {
        const meanRise = riseSum / this.count
        const strength = (meanRise - c.bandRiseFloor) / (c.impactFullRise - c.bandRiseFloor)
        hit = clamp01(strength) * c.impactMax
      }
    }
    if (hit > this.impactTarget) {
      this.impactTarget = hit
      this.impactHoldLeft = c.impactHoldSeconds
    } else if (this.impactHoldLeft > 0) {
      this.impactHoldLeft -= h
    } else {
      this.impactTarget *= Math.exp(-h / c.impactReleaseSeconds)
    }
    if (this.impactTarget > this.impactLevel) {
      this.impactLevel +=
        (this.impactTarget - this.impactLevel) * (1 - Math.exp(-h / c.impactRiseSeconds))
    } else {
      this.impactLevel = this.impactTarget
    }
  }

  /**
   * How far end `side` of tine `k` has withdrawn, as a fraction of the
   * line's length. side 0 = the path's first end (left leg top, spine top,
   * arc's left end); side 1 = its last.
   */
  retraction(k: number, side: 0 | 1): number {
    if (k === 0 && side === 1) return 0 // the spine's bottom end is the mark's centre
    const c = LISTENING
    const u = this.count > 1 ? k / (this.count - 1) : 0
    const hz = c.driftHz * (1.15 - 0.3 * u)
    const phase = GOLDEN_ANGLE * (2 * k + side)
    const drift = 0.5 * (1 + Math.sin(2 * Math.PI * hz * this.now + phase))
    const presence =
      this.attentionLevel * (c.presenceMin + (c.presenceMax - c.presenceMin) * drift)
    const depth = c.innerImpactShare + (1 - c.innerImpactShare) * u
    return Math.min(c.maxPerEnd, presence + this.impactLevel * depth)
  }
}
