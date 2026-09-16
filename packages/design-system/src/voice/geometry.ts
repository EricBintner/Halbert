// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Parametric geometry of the Halbert mark, split per tine, in the optical
 * densities that support per-tine deformation:
 *
 *   brand   (the voice mark, default): spine + 6 lanes, pitch 72, stroke 48
 *           — the ratified 7-line mark, 2:1 stroke:gap (gap 24)
 *   medium:                            spine + 5 lanes, pitch 86.4, stroke 48
 *   display:                           spine + 9 lanes, pitch 48, stroke 26.67
 *
 * Verified against packages/design-system/src/primitives/HalbertMark.tsx:
 * 1024x1024 viewBox; spine M 512 80 V 512; U-lanes drawn left-leg-down ->
 * bottom semicircle -> right-leg-up; leg tops sit on the 432-radius circle
 * around (512, 512); the outermost lane is a bare semicircle.
 *
 * Deformation models (design doc 15 §3, revised by doc 17 on 2026-09-15):
 *  - string mode shapes on the legs with Hann pinning at both ends. The
 *    shape is fixed in space — a plucked string's nodes never move — and
 *    the time behaviour (the damped cosine) is entirely the caller's
 *    signed `displacement`, supplied per frame by springs.ts;
 *  - radial cosine flex on the arcs, Hann-windowed over theta so leg/arc
 *    junctions never tear;
 *  - traveling bulges: a gaussian "ball" that slides along the tine's arc
 *    length in the outward-normal direction — the thinking-state signature,
 *    "a snake that ate a ball". A global Hann window over normalized path
 *    position keeps both path endpoints visually pinned while it travels;
 *  - retraction (listening): each end of a line withdraws along its own
 *    path by a fraction of the line's length. Fully retracted, a U-line is
 *    a dot at its apex, the outer arc a dot at its lowest point, the spine
 *    a dot at the mark's centre. Retraction is a trim of the sampled path,
 *    so it composes with every deformation above.
 */

export const MARK = Object.freeze({
  cx: 512,
  cy: 512,
  outerR: 432,
  spine: { top: 80, bottom: 512 },
} as const)

export type VoiceDensity = 'brand' | 'medium' | 'display'

export const DEFAULT_DENSITY: VoiceDensity = 'brand'

const LANE_STEP: Record<VoiceDensity, number> = { brand: 72, medium: 86.4, display: 48 }
const LANES: Record<VoiceDensity, number> = { brand: 6, medium: 5, display: 9 }

export function laneCount(density: VoiceDensity = DEFAULT_DENSITY): number {
  return LANES[density]
}

export function tineCount(density: VoiceDensity = DEFAULT_DENSITY): number {
  return LANES[density] + 1
}

export function laneRadius(lane: number, density: VoiceDensity = DEFAULT_DENSITY): number {
  return LANE_STEP[density] * lane
}

/** y of a lane's leg tops. The outermost lane returns 512 (no legs). */
export function laneTop(lane: number, density: VoiceDensity = DEFAULT_DENSITY): number {
  const r = laneRadius(lane, density)
  return MARK.cy - Math.sqrt(Math.max(0, MARK.outerR ** 2 - r ** 2))
}

/** Spatial harmonic mode per tine (n_k): the inner, higher-pitched strings
 * ring in their second mode (an S on the legs); outer legs use the
 * fundamental to avoid visible kinks. */
export const TINE_MODES: Record<VoiceDensity, readonly number[]> = {
  brand: [2, 2, 1, 1, 1, 1, 1],
  medium: [2, 2, 1, 1, 1, 1],
  display: [2, 2, 2, 1, 1, 1, 1, 1, 1, 1],
}

/**
 * The engine never asks a tine for more than this multiple of its A_k:
 * ring <= 1 (RING_MAX in springs.ts) plus swell <= 0.3 (excitation.ts).
 * TINE_AMPLITUDES is tuned against it below.
 */
export const MAX_DISPLACEMENT_MULTIPLIER = 1.3

/**
 * Max lateral excursion per tine (mark units) at multiplier 1.
 * Invariant: MAX_DISPLACEMENT_MULTIPLIER * (neighbouring sum) stays below the
 * inter-lane gap (brand 24, medium 38.4, display 21.33) so strokes can never
 * visually collide even with both neighbours bowing toward each other at the
 * ceiling (test-enforced).
 */
export const TINE_AMPLITUDES: Record<VoiceDensity, readonly number[]> = {
  brand: [6, 7, 8, 9, 9, 9, 8],
  medium: [9, 11, 13, 14, 15, 13],
  display: [4, 5, 6, 7, 7, 8, 8, 8, 8, 7],
}

/** A localized bump traveling along a tine, in normalized path position. */
export interface TravelingBulge {
  /** Normalized arc-length position, 0 = left leg top, 1 = right leg top. */
  center: number
  /** Gaussian width (same normalized units; ~0.07 reads as a single ball). */
  width: number
  /** Crest displacement in mark units along the outward normal. */
  height: number
}

/** How far each end of a line has withdrawn, as fractions of its length.
 * `start` is the path's first end (left leg top, spine top, arc's left end);
 * `end` its last. start + end >= 1 collapses the line to a dot. */
export interface Retraction {
  start: number
  end: number
}

export interface TinePathOptions {
  density?: VoiceDensity
  /** Traveling bulges layered on top of the mode-shape deformation. */
  bulges?: readonly TravelingBulge[]
  /** Withdraw the line's ends along its path (listening). */
  trim?: Retraction
}

export const LEG_SAMPLES = 24
export const ARC_SAMPLES = 48
export const SPINE_SAMPLES = 32

/** Shortest visible line, as a fraction of its length: with round caps a
 * segment this short renders as a dot of one stroke width. */
const DOT_LENGTH = 0.002

function hann(u: number): number {
  const s = Math.sin(Math.PI * u)
  return s * s
}

function bulgeOffset(u: number, bulges: readonly TravelingBulge[]): number {
  // The Hann window pins both path endpoints; junction continuity between
  // leg and arc is automatic because the outward normal is continuous there.
  let sum = 0
  for (const b of bulges) {
    const z = (u - b.center) / b.width
    sum += b.height * Math.exp(-z * z)
  }
  return hann(u) * sum
}

function fmt(v: number): string {
  return String(Math.round(v * 100) / 100)
}

interface Sample {
  x: number
  y: number
  /** Normalized arc-length position along the undeformed line, 0..1. */
  u: number
}

function clamp01(v: number): number {
  return Number.isNaN(v) ? 0 : Math.min(1, Math.max(0, v))
}

/**
 * One tine's deformed geometry as a function of path position u in [0, 1],
 * plus the sample grid the static mark is drawn on. Grid samples are built
 * from their segment-local parameters (so the static paths are exact to
 * the ratified marks); withdrawn tips are evaluated at their exact u, so a
 * retracted end always sits on the line, never on a chord between samples.
 */
interface TineShape {
  at(u: number): Sample
  grid(): Sample[]
}

function tineShape(
  lane: number,
  displacement: number,
  density: VoiceDensity,
  bulges: readonly TravelingBulge[],
): TineShape {
  const noBulges = bulges.length === 0
  const bo = (u: number) => (noBulges ? 0 : bulgeOffset(u, bulges))

  if (lane === 0) {
    const top = MARK.spine.top
    const len = MARK.spine.bottom - top
    const mode = TINE_MODES[density][0]
    const at = (u: number): Sample => {
      const dx = displacement * Math.sin(mode * Math.PI * u) * hann(u) + bo(u)
      return { x: MARK.cx + dx, y: top + u * len, u }
    }
    return {
      at,
      grid: () => Array.from({ length: SPINE_SAMPLES + 1 }, (_, i) => at(i / SPINE_SAMPLES)),
    }
  }

  const r = laneRadius(lane, density)
  const mode = TINE_MODES[density][lane]
  const lanes = LANES[density]

  if (lane === lanes) {
    // Outermost lane: bare semicircle (no legs), theta 0..PI, u = th/PI.
    const at = (u: number): Sample => {
      const th = u * Math.PI
      const rr = r + displacement * Math.cos(mode * th) * hann(u) + bo(u)
      return { x: MARK.cx - rr * Math.cos(th), y: MARK.cy + rr * Math.sin(th), u }
    }
    return {
      at,
      grid: () => Array.from({ length: ARC_SAMPLES + 1 }, (_, i) => at(i / ARC_SAMPLES)),
    }
  }

  const top = laneTop(lane, density)
  const legLen = MARK.cy - top
  const arcLen = Math.PI * r
  const total = 2 * legLen + arcLen
  const uLegEnd = legLen / total
  const uArcEnd = (legLen + arcLen) / total

  // Left leg, top -> bottom. Outward normal is -x.
  const leftLeg = (uLeg: number, u: number): Sample => ({
    x: MARK.cx - r - displacement * Math.sin(mode * Math.PI * uLeg) * hann(uLeg) - bo(u),
    y: top + uLeg * legLen,
    u,
  })
  // Base arc, theta 0..PI.
  const arc = (uArc: number, u: number): Sample => {
    const th = uArc * Math.PI
    const rr = r + displacement * Math.cos(mode * th) * hann(uArc) + bo(u)
    return { x: MARK.cx - rr * Math.cos(th), y: MARK.cy + rr * Math.sin(th), u }
  }
  // Right leg, bottom -> top (uLeg 1 -> 0). Outward normal is +x.
  const rightLeg = (uLeg: number, u: number): Sample => ({
    x: MARK.cx + r + displacement * Math.sin(mode * Math.PI * uLeg) * hann(uLeg) + bo(u),
    y: top + uLeg * legLen,
    u,
  })

  const at = (u: number): Sample => {
    if (u <= uLegEnd) return leftLeg((u * total) / legLen, u)
    if (u <= uArcEnd) return arc((u * total - legLen) / arcLen, u)
    return rightLeg(1 - (u * total - legLen - arcLen) / legLen, u)
  }
  const grid = (): Sample[] => {
    const out: Sample[] = []
    for (let i = 0; i <= LEG_SAMPLES; i++) {
      const uLeg = i / LEG_SAMPLES
      out.push(leftLeg(uLeg, (uLeg * legLen) / total))
    }
    for (let i = 1; i < ARC_SAMPLES; i++) {
      const uArc = i / ARC_SAMPLES
      out.push(arc(uArc, (legLen + uArc * arcLen) / total))
    }
    for (let i = 1; i <= LEG_SAMPLES; i++) {
      out.push(rightLeg(1 - i / LEG_SAMPLES, (legLen + arcLen + (i / LEG_SAMPLES) * legLen) / total))
    }
    return out
  }
  return { at, grid }
}

/** Withdraw each end along the path; a crossed or fully withdrawn line
 * collapses to a dot where the two tips meet. */
function trimSamples(shape: TineShape, samples: Sample[], trim: Retraction): Sample[] {
  const a = clamp01(trim.start)
  const b = 1 - clamp01(trim.end)
  if (a === 0 && b === 1) return samples
  if (b - a < DOT_LENGTH) {
    const c = Math.min(1 - DOT_LENGTH / 2, Math.max(DOT_LENGTH / 2, (a + b) / 2))
    return [shape.at(c - DOT_LENGTH / 2), shape.at(c + DOT_LENGTH / 2)]
  }
  const out: Sample[] = [shape.at(a)]
  for (const s of samples) if (s.u > a && s.u < b) out.push(s)
  out.push(shape.at(b))
  return out
}

function format(samples: Sample[]): string {
  return `M ${samples.map((s) => `${fmt(s.x)} ${fmt(s.y)}`).join(' L ')}`
}

/**
 * Build the `d` string for one tine.
 * @param lane 0 = spine, 1..laneCount = U-lanes (outermost is a bare arc)
 * @param displacement signed crest displacement in mark units; positive bows
 *        the legs outward (and the spine's upper half to the right). The
 *        caller passes A_k * m_k(t) where m is the per-tine multiplier from
 *        the string and swell oscillators.
 */
export function tinePathD(
  lane: number,
  displacement: number,
  opts: TinePathOptions = {},
): string {
  const density = opts.density ?? DEFAULT_DENSITY
  const shape = tineShape(lane, displacement, density, opts.bulges ?? [])
  let samples = shape.grid()
  if (opts.trim) samples = trimSamples(shape, samples, opts.trim)
  return format(samples)
}

/** The exact static mark for a density, one path per tine (first paint/SSR). */
export function staticTinePaths(density: VoiceDensity = DEFAULT_DENSITY): string[] {
  return Array.from({ length: tineCount(density) }, (_, k) => tinePathD(k, 0, { density }))
}
