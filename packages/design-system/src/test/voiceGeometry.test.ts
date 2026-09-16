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

describe('traveling bulges (thinking state — "snake ate a ball")', () => {
  const bulge = [{ center: 0.5, width: 0.07, height: 8 }]

  it('moves the arc apex outward at the bulge center', () => {
    const d = tinePathD(2, 0, { density: 'medium', bulges: bulge })
    const pts = points(d)
    const statik = points(staticTinePaths('medium')[2])
    const apexY = (arr: Array<[number, number]>) => Math.max(...arr.map(([, y]) => y))
    expect(apexY(pts)).toBeGreaterThan(apexY(statik) + 6)
    expect(apexY(pts)).toBeLessThan(apexY(statik) + 9)
  })

  it('pins both path endpoints while a bulge travels', () => {
    for (const center of [0.05, 0.3, 0.5, 0.7, 0.95]) {
      const d = tinePathD(2, 0, {
        density: 'medium',
        bulges: [{ center, width: 0.07, height: 8 }],
      })
      const pts = points(d)
      const statik = points(staticTinePaths('medium')[2])
      expect(pts[0]).toEqual(statik[0])
      expect(pts[pts.length - 1]).toEqual(statik[statik.length - 1])
    }
  })

  it('leaves points far from the bulge untouched', () => {
    const d = tinePathD(2, 0, { density: 'medium', bulges: bulge })
    const pts = points(d)
    const statik = points(staticTinePaths('medium')[2])
    // left-leg top quarter (u < 0.05 path-normalized) is untouched to the cent
    for (let i = 1; i <= 3; i++) {
      expect(pts[i][0]).toBeCloseTo(statik[i][0], 2)
      expect(pts[i][1]).toBeCloseTo(statik[i][1], 2)
    }
  })

  it('sums stacked bulges on one tine', () => {
    const d = tinePathD(2, 0, {
      density: 'medium',
      bulges: [
        { center: 0.5, width: 0.07, height: 8 },
        { center: 0.52, width: 0.07, height: 8 },
      ],
    })
    const pts = points(d)
    const statik = points(staticTinePaths('medium')[2])
    const apexY = (arr: Array<[number, number]>) => Math.max(...arr.map(([, y]) => y))
    expect(apexY(pts)).toBeGreaterThan(apexY(statik) + 12)
  })

  it('bulges work on the spine and the bare outermost arc', () => {
    const spine = points(tinePathD(0, 0, { density: 'medium', bulges: bulge }))
    const midXs = spine.slice(4, -4).map(([x]) => x)
    expect(Math.max(...midXs)).toBeGreaterThan(512 + 6)
    const outer = points(tinePathD(5, 0, { density: 'medium', bulges: bulge }))
    const apexY = Math.max(...outer.map(([, y]) => y))
    expect(apexY).toBeGreaterThan(944 + 6)
  })
})
