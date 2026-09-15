// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Parametric geometry of the Halbert mark, split per tine, in both optical
 * densities that support per-tine deformation:
 *
 *   medium  (Voice Mode default): spine + 5 lanes, pitch 86.4, stroke 48
 *   display:                      spine + 9 lanes, pitch 48, stroke 26.67
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
 *    position keeps both path endpoints visually pinned while it travels.
 */

export const MARK = Object.freeze({
  cx: 512,
  cy: 512,
  outerR: 432,
  spine: { top: 80, bottom: 512 },
} as const)

export type VoiceDensity = 'medium' | 'display'

const LANE_STEP: Record<VoiceDensity, number> = { medium: 86.4, display: 48 }
const LANES: Record<VoiceDensity, number> = { medium: 5, display: 9 }

export function laneCount(density: VoiceDensity = 'medium'): number {
  return LANES[density]
}

export function tineCount(density: VoiceDensity = 'medium'): number {
  return LANES[density] + 1
}

export function laneRadius(lane: number, density: VoiceDensity = 'medium'): number {
  return LANE_STEP[density] * lane
}

/** y of a lane's leg tops. The outermost lane returns 512 (no legs). */
export function laneTop(lane: number, density: VoiceDensity = 'medium'): number {
  const r = laneRadius(lane, density)
  return MARK.cy - Math.sqrt(Math.max(0, MARK.outerR ** 2 - r ** 2))
}

/** Spatial harmonic mode per tine (n_k): the inner, higher-pitched strings
 * ring in their second mode (an S on the legs); outer legs use the
 * fundamental to avoid visible kinks. */
export const TINE_MODES: Record<VoiceDensity, readonly number[]> = {
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
 * inter-lane gap (medium 38.4, display 21.33) so strokes can never visually
 * collide even with both neighbours bowing toward each other at the ceiling
 * (test-enforced).
 */
export const TINE_AMPLITUDES: Record<VoiceDensity, readonly number[]> = {
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

export interface TinePathOptions {
  density?: VoiceDensity
  /** Traveling bulges layered on top of the mode-shape deformation. */
  bulges?: readonly TravelingBulge[]
}

export const LEG_SAMPLES = 24
export const ARC_SAMPLES = 48
export const SPINE_SAMPLES = 32

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

function pt(x: number, y: number): string {
  return `${fmt(x)} ${fmt(y)}`
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
  const density = opts.density ?? 'medium'
  const bulges = opts.bulges ?? []
  const noBulges = bulges.length === 0
  const bo = (u: number) => (noBulges ? 0 : bulgeOffset(u, bulges))

  if (lane === 0) {
    const top = MARK.spine.top
    const len = MARK.spine.bottom - top
    const mode = TINE_MODES[density][0]
    const pts: string[] = []
    for (let i = 0; i <= SPINE_SAMPLES; i++) {
      const u = i / SPINE_SAMPLES
      const y = top + u * len
      const dx = displacement * Math.sin(mode * Math.PI * u) * hann(u) + bo(u)
      pts.push(pt(MARK.cx + dx, y))
    }
    return `M ${pts.join(' L ')}`
  }

  const r = laneRadius(lane, density)
  const mode = TINE_MODES[density][lane]
  const lanes = LANES[density]

  if (lane === lanes) {
    // Outermost lane: bare semicircle (no legs), theta 0..PI, u = th/PI.
    const pts: string[] = []
    for (let i = 0; i <= ARC_SAMPLES; i++) {
      const u = i / ARC_SAMPLES
      const th = u * Math.PI
      const rr = r + displacement * Math.cos(mode * th) * hann(u) + bo(u)
      pts.push(pt(MARK.cx - rr * Math.cos(th), MARK.cy + rr * Math.sin(th)))
    }
    return `M ${pts.join(' L ')}`
  }

  const top = laneTop(lane, density)
  const legLen = MARK.cy - top
  const arcLen = Math.PI * r
  const total = 2 * legLen + arcLen
  const pts: string[] = []

  // Left leg, top -> bottom. Outward normal is -x.
  for (let i = 0; i <= LEG_SAMPLES; i++) {
    const uLeg = i / LEG_SAMPLES
    const u = (uLeg * legLen) / total
    const y = top + uLeg * legLen
    const dx = -displacement * Math.sin(mode * Math.PI * uLeg) * hann(uLeg) - bo(u)
    pts.push(pt(MARK.cx - r + dx, y))
  }

  // Base arc, theta 0..PI, skipping endpoints (pinned leg bottoms).
  for (let i = 1; i < ARC_SAMPLES; i++) {
    const uArc = i / ARC_SAMPLES
    const u = (legLen + uArc * arcLen) / total
    const th = uArc * Math.PI
    const rr = r + displacement * Math.cos(mode * th) * hann(uArc) + bo(u)
    pts.push(pt(MARK.cx - rr * Math.cos(th), MARK.cy + rr * Math.sin(th)))
  }

  // Right leg, bottom -> top. Outward normal is +x.
  for (let i = 1; i <= LEG_SAMPLES; i++) {
    const uLeg = 1 - i / LEG_SAMPLES
    const u = (legLen + arcLen + (i / LEG_SAMPLES) * legLen) / total
    const y = top + uLeg * legLen
    const dx = displacement * Math.sin(mode * Math.PI * uLeg) * hann(uLeg) + bo(u)
    pts.push(pt(MARK.cx + r + dx, y))
  }

  return `M ${pts.join(' L ')}`
}

/** The exact static mark for a density, one path per tine (first paint/SSR). */
export function staticTinePaths(density: VoiceDensity = 'medium'): string[] {
  return Array.from({ length: tineCount(density) }, (_, k) => tinePathD(k, 0, { density }))
}
