// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Parametric geometry of the Halbert mark, display density, split per tine.
 *
 * Verified against packages/design-system/src/primitives/HalbertMark.tsx
 * (2026-08-31): 1024x1024 viewBox; spine M 512 80 V 512; nine U-lanes of
 * radius 48*lane drawn left-leg-down -> bottom semicircle -> right-leg-up;
 * leg tops sit on the 432-radius circle around (512, 512); lane 9 is a bare
 * semicircle; display stroke-width 26.67 (gap between lanes: 21.33).
 *
 * The audio deformation follows documentation/design/15-...spec §3:
 * standing waves on the vertical legs with a Hann window pinning both ends,
 * radial cosine flex on the base arc with a Hann window over theta in
 * [0, PI] pinning the leg/arc junctions (spec improvement — the un-windowed
 * cosine in spec §3.2 would tear the arc off the legs whenever the phase is
 * non-zero).
 */

export const MARK = Object.freeze({
  cx: 512,
  cy: 512,
  outerR: 432,
  laneStep: 48,
  lanes: 9,
  spine: { top: 80, bottom: 512 },
} as const)

/** Tine 0 is the spine; tines 1..9 are the U-lanes. */
export const TINE_COUNT = MARK.lanes + 1

export function laneRadius(lane: number): number {
  return MARK.laneStep * lane
}

/** y of a lane's leg tops (round-cap center sits half a stroke above). */
export function laneTop(lane: number): number {
  const r = laneRadius(lane)
  return MARK.cy - Math.sqrt(Math.max(0, MARK.outerR ** 2 - r ** 2))
}

/**
 * Spatial harmonic mode per tine (n_k in spec §3.1). Inner structures ripple
 * (mode 2), the long outer legs use the fundamental to avoid visible kinks.
 */
export const TINE_MODES: readonly number[] = [2, 2, 2, 1, 1, 1, 1, 1, 1, 1]

/**
 * Maximum lateral excursion per tine (mark units) at full spectral energy.
 * Invariant: neighboring sums stay below the 21.33-unit inter-lane gap so
 * strokes can never visually collide (test-enforced).
 */
export const TINE_AMPLITUDES: readonly number[] = [4, 6, 7, 8, 9, 9, 10, 10, 10, 8]

/** Phase drift rates (rad/s) — inner tines shimmer faster than outer ones. */
export const TINE_DRIFT: readonly number[] = [1.4, 1.2, 1.0, 0.9, 0.8, 0.7, 0.6, 0.55, 0.5, 0.45]

export const LEG_SAMPLES = 24
export const ARC_SAMPLES = 48
export const SPINE_SAMPLES = 32

function hann(u: number): number {
  const s = Math.sin(Math.PI * u)
  return s * s
}

function fmt(v: number): string {
  return String(Math.round(v * 100) / 100)
}

function pt(x: number, y: number): string {
  return `${fmt(x)} ${fmt(y)}`
}

/**
 * Build the `d` string for one tine.
 * @param lane 0 = spine, 1..9 = U-lanes
 * @param displacement signed crest displacement in mark units; the caller
 *        passes A_k * E_k(t) where E is the spring-smoothed band energy
 * @param phase current phase drift phi_k(t) in radians
 */
export function tinePathD(lane: number, displacement: number, phase: number): string {
  if (lane === 0) {
    const top = MARK.spine.top
    const len = MARK.spine.bottom - top
    const mode = TINE_MODES[0]
    const pts: string[] = []
    for (let i = 0; i <= SPINE_SAMPLES; i++) {
      const u = i / SPINE_SAMPLES
      const y = top + u * len
      const dx = displacement * Math.sin(mode * Math.PI * u + phase) * hann(u)
      pts.push(pt(MARK.cx + dx, y))
    }
    return `M ${pts.join(' L ')}`
  }

  const r = laneRadius(lane)
  const mode = TINE_MODES[lane]

  if (lane === MARK.lanes) {
    // Lane 9: bare semicircle (no legs), theta 0..PI from left to right.
    const pts: string[] = []
    for (let i = 0; i <= ARC_SAMPLES; i++) {
      const u = i / ARC_SAMPLES
      const th = u * Math.PI
      const rr = r + displacement * Math.cos(mode * th + phase) * hann(u)
      pts.push(pt(MARK.cx - rr * Math.cos(th), MARK.cy + rr * Math.sin(th)))
    }
    return `M ${pts.join(' L ')}`
  }

  const top = laneTop(lane)
  const legLen = MARK.cy - top
  const pts: string[] = []

  // Left leg, top -> bottom. Outward normal is -x.
  for (let i = 0; i <= LEG_SAMPLES; i++) {
    const u = i / LEG_SAMPLES
    const y = top + u * legLen
    const dx = -displacement * Math.sin(mode * Math.PI * u + phase) * hann(u)
    pts.push(pt(MARK.cx - r + dx, y))
  }

  // Base arc, theta 0..PI (left-bottom -> apex -> right-bottom), skipping
  // both endpoints: they coincide with the pinned leg bottoms.
  for (let i = 1; i < ARC_SAMPLES; i++) {
    const u = i / ARC_SAMPLES
    const th = u * Math.PI
    const rr = r + displacement * Math.cos(mode * th + phase) * hann(u)
    pts.push(pt(MARK.cx - rr * Math.cos(th), MARK.cy + rr * Math.sin(th)))
  }

  // Right leg, bottom -> top. Outward normal is +x.
  for (let i = 1; i <= LEG_SAMPLES; i++) {
    const u = 1 - i / LEG_SAMPLES
    const y = top + u * legLen
    const dx = displacement * Math.sin(mode * Math.PI * u + phase) * hann(u)
    pts.push(pt(MARK.cx + r + dx, y))
  }

  return `M ${pts.join(' L ')}`
}

/** The exact static mark, one path per tine (first paint / SSR / no audio). */
export const STATIC_TINE_PATHS: readonly string[] = Array.from(
  { length: TINE_COUNT },
  (_, k) => tinePathD(k, 0, 0),
)
