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
 *   impact   — only a sharp broadband transient (a clap, a door) drives a
 *              quick, critically damped retraction that scales with the hit,
 *              up to impactMax on the outer lines, then relaxes. Speech
 *              syllables raise one or two bands at a time and stay below
 *              its threshold.
 *
 * The spine's bottom end is the mark's centre and never retracts; the
 * spine withdraws from the top. Everything here is deterministic.
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
  /** Sum of per-band rises in one frame that starts an impact (a clap sums
   * to several units; a syllable to well under one). */
  impactThreshold: 1.2,
  /** Rise sum above the threshold that reaches impactMax. */
  impactScale: 1.5,
  /** Retraction per end on the hardest impact, outer line. With presence at
   * its peak this still leaves a tenth of the line: a clap startles, it
   * never closes a line. */
  impactMax: 0.32,
  /** The impact rises this fast, holds briefly, then releases. */
  impactRiseSeconds: 0.05,
  impactHoldSeconds: 0.08,
  impactReleaseSeconds: 0.45,
  /** The spine takes this share of the outer line's impact. */
  innerImpactShare: 0.7,
  /** No end withdraws past this, so two ends can never meet. */
  maxPerEnd: 0.45,
})

/** Golden angle: spreads per-end drift phases so nothing moves in step. */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

function clamp01(v: number): number {
  if (Number.isNaN(v)) return 0
  return Math.min(1, Math.max(0, v))
}

export class Listener {
  private readonly prev: Float32Array
  private attentionLevel = 0
  private impactTarget = 0
  private impactLevel = 0
  private impactHoldUntil = -Infinity
  private now = 0

  constructor(private readonly count: number) {
    this.prev = new Float32Array(count)
  }

  /** 0 (silence for a while) … 1 (sound now). */
  get attention(): number {
    return this.attentionLevel
  }

  /** Current impact retraction before the per-line profile, 0 … impactMax. */
  get impact(): number {
    return this.impactLevel
  }

  /** Feed one frame of band levels; `t` is the frame clock in seconds. */
  feed(levels: ArrayLike<number>, dt: number, t: number): void {
    const h = Number.isFinite(dt) && dt > 0 ? dt : 0
    if (Number.isFinite(t)) this.now = t
    const c = LISTENING

    let loudest = 0
    let riseSum = 0
    for (let k = 0; k < this.count; k++) {
      const v = clamp01(levels[k] ?? 0)
      if (v > loudest) loudest = v
      const rise = v - this.prev[k]
      if (rise > 0) riseSum += rise
      this.prev[k] = v
    }

    const target = loudest > c.soundFloor ? 1 : 0
    const tau = target > this.attentionLevel ? c.attackSeconds : c.releaseSeconds
    this.attentionLevel += (target - this.attentionLevel) * (1 - Math.exp(-h / tau))

    const hit =
      riseSum > c.impactThreshold
        ? Math.min(1, (riseSum - c.impactThreshold) / c.impactScale) * c.impactMax
        : 0
    if (hit > this.impactTarget) {
      this.impactTarget = hit
      this.impactHoldUntil = this.now + c.impactHoldSeconds
    } else if (this.now >= this.impactHoldUntil) {
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
