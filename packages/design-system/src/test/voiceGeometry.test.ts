// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  laneCount,
  tineCount,
  TINE_AMPLITUDES,
  TINE_MODES,
  MAX_DISPLACEMENT_MULTIPLIER,
  MARK,
  laneRadius,
  laneTop,
  tineLength,
  tineLengths,
  tinePathD,
  bulgePolygonPoints,
  staticTinePaths,
} from '../voice/geometry'

function firstPoint(d: string): [number, number] {
  const m = d.match(/^M ([\d.-]+) ([\d.-]+)/)!
  return [parseFloat(m[1]), parseFloat(m[2])]
}
function points(d: string): Array<[number, number]> {
  return d
    .replace(/^M /, '')
    .split(' L ')
    .map((p) => p.split(' ').map(Number) as [number, number])
}
const last = <T,>(arr: T[]): T => arr[arr.length - 1]

describe('mark voice geometry — brand density (the ratified 7-line mark, the default)', () => {
  it('is the default density: spine + 6 lanes at 72-unit pitch, 48 stroke, 24 gap', () => {
    expect(tineCount()).toBe(7)
    expect(laneCount()).toBe(6)
    expect(laneRadius(1)).toBe(72)
    expect(laneRadius(6)).toBe(432)
    expect(laneTop(1)).toBeCloseTo(86.04, 2)
    expect(laneTop(5)).toBeCloseTo(273.2, 2)
    expect(laneTop(6)).toBeCloseTo(512, 5) // outermost lane is a bare semicircle
  })

  it('static paths reproduce PATHS_7 from HalbertMark.tsx', () => {
    const statik = staticTinePaths()
    expect(statik).toHaveLength(7)
    expect(firstPoint(statik[0])).toEqual([512, 80])
    expect(firstPoint(statik[1])).toEqual([440, 86.04])
    expect(firstPoint(statik[2])).toEqual([368, 104.71])
    expect(firstPoint(statik[3])).toEqual([296, 137.88])
    expect(firstPoint(statik[4])).toEqual([224, 190.01])
    expect(firstPoint(statik[5])).toEqual([152, 273.2])
    expect(firstPoint(statik[6])).toEqual([80, 512])
    expect(last(points(statik[6]))).toEqual([944, 512])
    expect(last(points(statik[3]))).toEqual([728, 137.88])
    const lane3 = points(statik[3]) // r = 216 -> apex y = 728
    expect(Math.max(...lane3.map(([, y]) => y))).toBeCloseTo(728, 1)
  })

  it('knows every line\'s length in mark units (the listening travel is absolute)', () => {
    expect(tineLength(0)).toBeCloseTo(432, 6) // the spine
    expect(tineLength(6)).toBeCloseTo(Math.PI * 432, 6) // the bare outer arc
    expect(tineLength(2)).toBeCloseTo(2 * (512 - laneTop(2)) + Math.PI * 144, 6)
    expect(tineLengths()).toHaveLength(7)
    expect(tineLengths('display')).toHaveLength(10)
    // outer lines are longer: 5 % of the outer arc is ~68 units, of the spine ~22
    expect(tineLength(6)).toBeGreaterThan(3 * tineLength(0))
  })

  it('samples both leg/arc junctions of every U-lane, symmetrically', () => {
    for (let lane = 1; lane <= 5; lane++) {
      const pts = points(staticTinePaths()[lane])
      const r = laneRadius(lane)
      expect(pts).toHaveLength(2 * 25 + 47) // 25 per leg, 47 interior arc samples
      expect(pts[24]).toEqual([512 - r, 512]) // left junction
      expect(pts[pts.length - 25]).toEqual([512 + r, 512]) // right junction
    }
  })

  it('keeps adjacent tine excursions inside the 24-unit gap at the multiplier ceiling', () => {
    const amps = TINE_AMPLITUDES.brand
    expect(amps).toHaveLength(7)
    for (let k = 0; k < amps.length - 1; k++) {
      expect(MAX_DISPLACEMENT_MULTIPLIER * (amps[k] + amps[k + 1])).toBeLessThan(24)
    }
    expect(TINE_MODES.brand).toHaveLength(7)
  })
})

describe('mark voice geometry — display density (10 tines)', () => {
  it('matches the verified static mark model', () => {
    expect(tineCount('display')).toBe(10) // spine + 9 lanes
    expect(laneRadius(9, 'display')).toBe(432)
    expect(laneTop(1, 'display')).toBeCloseTo(82.67, 2)
    expect(laneTop(9, 'display')).toBeCloseTo(512, 5)
  })

  it('static paths reproduce the display-density endpoints', () => {
    const statik = staticTinePaths('display')
    expect(statik).toHaveLength(10)
    expect(firstPoint(statik[0])).toEqual([512, 80])
    expect(firstPoint(statik[1])).toEqual([464, 82.67])
    expect(firstPoint(statik[9])).toEqual([80, 512])
    const lane9 = points(statik[9])
    expect(lane9[lane9.length - 1]).toEqual([944, 512])
    const lane4 = points(statik[4])
    expect(Math.max(...lane4.map(([, y]) => y))).toBeCloseTo(704, 1)
  })
})

describe('mark voice geometry — medium density (6 tines)', () => {
  it('matches the verified medium tier: spine + 5 lanes at 86.4-unit pitch', () => {
    expect(tineCount('medium')).toBe(6)
    expect(laneCount('medium')).toBe(5)
    expect(laneRadius(1, 'medium')).toBe(86.4)
    expect(laneRadius(5, 'medium')).toBe(432)
    // leg tops still sit on the 432-radius circle
    expect(laneTop(1, 'medium')).toBeCloseTo(88.73, 2)
    expect(laneTop(5, 'medium')).toBeCloseTo(512, 5) // outermost lane is a bare semicircle
  })

  it('static paths reproduce the medium-tier endpoints', () => {
    const statik = staticTinePaths('medium')
    expect(statik).toHaveLength(6)
    expect(firstPoint(statik[1])).toEqual([425.6, 88.73])
    expect(firstPoint(statik[5])).toEqual([80, 512])
    const lane2 = points(statik[2]) // r = 172.8 -> apex y = 684.8
    expect(Math.max(...lane2.map(([, y]) => y))).toBeCloseTo(684.8, 1)
  })

  it('pins all junctions under displacement on every lane', () => {
    for (let lane = 1; lane <= 5; lane++) {
      const displaced = tinePathD(lane, TINE_AMPLITUDES.medium[lane], { density: 'medium' })
      const pts = points(displaced)
      const statik = points(staticTinePaths('medium')[lane])
      expect(pts[0]).toEqual(statik[0])
      expect(pts[pts.length - 1]).toEqual(statik[statik.length - 1])
      if (lane < 5) {
        expect(pts[24][0]).toBeCloseTo(statik[24][0], 2) // leg/arc junction
        expect(pts[24][1]).toBeCloseTo(statik[24][1], 2)
      }
    }
  })

  it('has stationary nodes: the spine midpoint never moves in its second mode', () => {
    // A plucked string's nodes never move (design doc 17): with no phase
    // input, the mode-2 spine's centre (u = 0.5, sample 16 of 32) stays on
    // the axis at every displacement, and a leg's ends stay pinned.
    for (const displacement of [-13, -4, 0, 4, 9, 13]) {
      const spine = points(tinePathD(0, displacement, { density: 'medium' }))
      expect(spine[16][0]).toBeCloseTo(512, 2)
      expect(spine[16][1]).toBeCloseTo(296, 2)
    }
  })

  it('positive displacement bows the legs outward (the strum direction)', () => {
    const statik = points(staticTinePaths('medium')[2])
    const bowed = points(tinePathD(2, 9, { density: 'medium' }))
    expect(bowed[12][0]).toBeLessThan(statik[12][0] - 5) // left-leg midpoint moves left
    const n = statik.length
    expect(bowed[n - 13][0]).toBeGreaterThan(statik[n - 13][0] + 5) // right-leg midpoint moves right
    // spine (mode 2): upper half bows right, lower half left. Sampled near
    // the antinodes of sin(2πu)·hann(u) (u ≈ 0.34 and 0.66 of 32 samples).
    const spine = points(tinePathD(0, 9, { density: 'medium' }))
    const spineStatic = points(staticTinePaths('medium')[0])
    expect(spine[11][0]).toBeGreaterThan(spineStatic[11][0] + 4)
    expect(spine[21][0]).toBeLessThan(spineStatic[21][0] - 4)
  })

  it('keeps adjacent tine excursions inside the inter-lane gap at the multiplier ceiling', () => {
    // The engine bounds each tine's multiplier at MAX_DISPLACEMENT_MULTIPLIER
    // (ring <= 1 plus swell <= 0.3). Two neighbours bowing toward each other
    // at that ceiling must still clear the gap between stroke edges:
    // medium tier 86.4 pitch − 48 stroke = 38.4; display 21.33.
    expect(MAX_DISPLACEMENT_MULTIPLIER).toBe(1.3)
    for (const [density, gap] of [
      ['medium', 38.4],
      ['display', 21.33],
    ] as const) {
      const amps = TINE_AMPLITUDES[density]
      for (let k = 0; k < amps.length - 1; k++) {
        expect(MAX_DISPLACEMENT_MULTIPLIER * (amps[k] + amps[k + 1])).toBeLessThan(gap)
      }
      expect(TINE_MODES[density]).toHaveLength(amps.length)
    }
  })
})

describe('retraction — a line withdraws its ends along its own path (listening)', () => {
  const r2 = laneRadius(2) // 144, brand lane 2
  const top2 = laneTop(2)
  const legLen = MARK.cy - top2
  const total = 2 * legLen + Math.PI * r2

  /** Distance from a point to the static lane-2 path (legs are vertical at
   * x = 368 / 656 from top to 512; the arc has radius 144 about the centre). */
  function offStatic([x, y]: [number, number]): number {
    if (y <= MARK.cy + 1e-9) return Math.min(Math.abs(x - 368), Math.abs(x - 656))
    return Math.abs(Math.hypot(x - MARK.cx, y - MARK.cy) - r2)
  }

  it('trims both ends by a fraction of the total length, interpolating the new tips', () => {
    const d = tinePathD(2, 0, { trim: { start: 0.12, end: 0.12 } })
    const pts = points(d)
    const statik = points(staticTinePaths()[2])
    expect(pts.length).toBeLessThan(statik.length)
    // new tips sit 12 % of the total length down each leg, on the leg line
    expect(pts[0][0]).toBeCloseTo(368, 2)
    expect(pts[0][1]).toBeCloseTo(top2 + 0.12 * total, 1)
    expect(last(pts)[0]).toBeCloseTo(656, 2)
    expect(last(pts)[1]).toBeCloseTo(top2 + 0.12 * total, 1)
    for (const p of pts) expect(offStatic(p)).toBeLessThan(0.05)
  })

  it('retracts asymmetrically when the two ends differ', () => {
    const pts = points(tinePathD(2, 0, { trim: { start: 0.3, end: 0.05 } }))
    expect(pts[0][1]).toBeCloseTo(top2 + 0.3 * total, 1)
    expect(last(pts)[1]).toBeCloseTo(top2 + 0.05 * total, 1)
  })

  it('fully retracted, a U-line is a dot at its apex', () => {
    for (const trim of [
      { start: 0.5, end: 0.5 },
      { start: 0.7, end: 0.7 },
    ]) {
      const pts = points(tinePathD(2, 0, { trim }))
      expect(pts.length).toBeGreaterThanOrEqual(2) // round caps render a dot
      for (const [x, y] of pts) {
        expect(Math.hypot(x - 512, y - (512 + r2))).toBeLessThan(3)
      }
    }
  })

  it('ends that cross unevenly collapse to a dot where the tips meet', () => {
    const pts = points(tinePathD(2, 0, { trim: { start: 0.6, end: 0.45 } }))
    expect(pts.length).toBeGreaterThanOrEqual(2)
    const [a, b] = [pts[0], last(pts)]
    expect(Math.hypot(a[0] - b[0], a[1] - b[1])).toBeLessThan(3)
    // the meeting point is on the arc, past the apex toward the right leg
    expect(a[0]).toBeGreaterThan(512)
    expect(offStatic(a)).toBeLessThan(0.05)
  })

  it('the spine withdraws from the top toward the mark centre', () => {
    const pts = points(tinePathD(0, 0, { trim: { start: 0.3, end: 0 } }))
    expect(pts[0]).toEqual([512, 80 + 0.3 * 432])
    expect(last(pts)).toEqual([512, 512])
    const dot = points(tinePathD(0, 0, { trim: { start: 1, end: 0 } }))
    for (const [x, y] of dot) expect(Math.hypot(x - 512, y - 512)).toBeLessThan(3)
  })

  it('the outer arc withdraws along the arc toward its lowest point', () => {
    const pts = points(tinePathD(6, 0, { trim: { start: 0.25, end: 0.25 } }))
    const th = 0.25 * Math.PI
    expect(pts[0][0]).toBeCloseTo(512 - 432 * Math.cos(th), 1)
    expect(pts[0][1]).toBeCloseTo(512 + 432 * Math.sin(th), 1)
    expect(last(pts)[0]).toBeCloseTo(512 + 432 * Math.cos(th), 1)
    const dot = points(tinePathD(6, 0, { trim: { start: 0.5, end: 0.5 } }))
    for (const [x, y] of dot) expect(Math.hypot(x - 512, y - 944)).toBeLessThan(3)
  })

  it('composes with the string warp: the trimmed path is a subset of the warped one', () => {
    const warped = points(tinePathD(2, 9, {}))
    const trimmed = points(tinePathD(2, 9, { trim: { start: 0.1, end: 0.1 } }))
    // every interior trimmed sample is one of the warped samples
    const key = ([x, y]: [number, number]) => `${x},${y}`
    const warpedSet = new Set(warped.map(key))
    for (const p of trimmed.slice(1, -1)) expect(warpedSet.has(key(p))).toBe(true)
    expect(trimmed.length).toBeLessThan(warped.length)
  })

  it('a zero trim is the untrimmed path', () => {
    expect(tinePathD(2, 4, { trim: { start: 0, end: 0 } })).toBe(tinePathD(2, 4, {}))
  })
})

describe('thinking bulges — a python that ate a baseball', () => {
  const SW = 48
  const ball = { center: 0.5, sigmaUnits: 36, height: 10 }
  const poly = (s: string) => s.trim().split(' ').map((p) => p.split(',').map(Number) as [number, number])
  const centroidX = (pts: Array<[number, number]>) => pts.reduce((s, [x]) => s + x, 0) / pts.length

  it('swells both sides of the line equally at its centre', () => {
    // lane 2's apex: the line is the r=144 arc about the mark's centre
    const pts = poly(bulgePolygonPoints(2, ball, { strokeWidth: SW }))
    const radii = pts.map(([x, y]) => Math.hypot(x - 512, y - 512))
    expect(Math.max(...radii)).toBeGreaterThan(144 + SW / 2 + 10)
    expect(Math.max(...radii)).toBeLessThan(144 + SW / 2 + 11)
    expect(Math.min(...radii)).toBeLessThan(144 - SW / 2 - 10)
    expect(Math.min(...radii)).toBeGreaterThan(144 - SW / 2 - 11)
  })

  it('is as wide as the stroke at its ends, so it merges into the line', () => {
    const pts = poly(bulgePolygonPoints(2, ball, { strokeWidth: SW }))
    const n = pts.length / 2 // one side forward, the other back
    const width = (i: number) => Math.hypot(pts[i][0] - pts[2 * n - 1 - i][0], pts[i][1] - pts[2 * n - 1 - i][1])
    expect(width(0)).toBeGreaterThanOrEqual(SW)
    expect(width(0)).toBeLessThan(SW + 2)
    expect(width(n - 1)).toBeLessThan(SW + 2)
    expect(width(Math.floor(n / 2))).toBeGreaterThan(SW + 18) // the ball in the middle
  })

  it('is the same physical size on every line: sigma is in mark units', () => {
    const along = (lane: number) => {
      const pts = poly(bulgePolygonPoints(lane, ball, { strokeWidth: SW }))
      const n = pts.length / 2
      const a = pts[0]
      const b = pts[n - 1]
      if (lane === 0) return Math.abs(b[1] - a[1]) // the spine is vertical
      // the outer arc: angle swept about the mark's centre, times its radius
      const ang = (p: [number, number]) => Math.atan2(p[1] - 512, p[0] - 512)
      return Math.abs(ang(b) - ang(a)) * 432
    }
    expect(along(0)).toBeGreaterThan(6 * 36 - 4)
    expect(along(0)).toBeLessThan(6 * 36 + 4)
    expect(along(6)).toBeGreaterThan(6 * 36 - 6) // measured on the offset curve, a little wider
    expect(along(6)).toBeLessThan(6 * 36 + 10)
  })

  it('fades over the last tenth of a line and never draws past its end', () => {
    expect(bulgePolygonPoints(0, { ...ball, center: 0.002 }, { strokeWidth: SW })).toBe('')
    const near = poly(bulgePolygonPoints(0, { ...ball, center: 0.99 }, { strokeWidth: SW }))
    for (const [, y] of near) expect(y).toBeLessThanOrEqual(512 + 0.5) // clipped at the spine's base
    // and nearly gone: a tenth of the way into the fade leaves under a unit of swelling
    expect(Math.max(...near.map(([x]) => Math.abs(x - 512)))).toBeLessThan(SW / 2 + 2)
    // while a ball in the middle rides at full size
    const mid = poly(bulgePolygonPoints(0, { ...ball, center: 0.3 }, { strokeWidth: SW }))
    expect(Math.max(...mid.map(([x]) => Math.abs(x - 512)))).toBeGreaterThan(SW / 2 + 9.5)
  })

  it('is clipped to the visible part of a withdrawn line', () => {
    const trim = { start: 0.4, end: 0 }
    expect(bulgePolygonPoints(2, { ...ball, center: 0.2 }, { strokeWidth: SW, trim })).toBe('')
    expect(bulgePolygonPoints(2, { ...ball, center: 0.6 }, { strokeWidth: SW, trim })).not.toBe('')
  })

  it('rides a warped line', () => {
    const onLeg = { ...ball, center: 0.15 } // lane 2's left leg, near its bow
    const still = poly(bulgePolygonPoints(2, onLeg, { strokeWidth: SW }))
    const bowed = poly(bulgePolygonPoints(2, onLeg, { strokeWidth: SW, displacement: 8 }))
    expect(centroidX(bowed)).toBeLessThan(centroidX(still) - 3) // the leg bows outward, to -x
  })

  it('the line itself no longer bends: a bulge is drawn over it, not into it', () => {
    // tinePathD accepts no bulge input; the swelling is a separate polygon
    expect((tinePathD as unknown as (...a: unknown[]) => string)(2, 0, { bulges: [ball] })).toBe(
      staticTinePaths()[2],
    )
  })
})

