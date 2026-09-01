// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  laneCount,
  tineCount,
  TINE_AMPLITUDES,
  TINE_MODES,
  laneRadius,
  laneTop,
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

describe('mark voice geometry — medium density (6 tines, the Voice Mode default)', () => {
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
      const displaced = tinePathD(lane, TINE_AMPLITUDES.medium[lane], 1.234, {
        density: 'medium',
      })
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

  it('keeps adjacent tine excursions inside the inter-lane gap', () => {
    // medium tier: 86.4 pitch − 48 stroke = 38.4 gap; display: 21.33
    for (const [density, gap] of [
      ['medium', 38.4],
      ['display', 21.33],
    ] as const) {
      const amps = TINE_AMPLITUDES[density]
      for (let k = 0; k < amps.length - 1; k++) {
        expect(amps[k] + amps[k + 1]).toBeLessThan(gap)
      }
      expect(TINE_MODES[density]).toHaveLength(amps.length)
    }
  })
})

describe('traveling bulges (thinking state — "snake ate a ball")', () => {
  const bulge = [{ center: 0.5, width: 0.07, height: 8 }]

  it('moves the arc apex outward at the bulge center', () => {
    const d = tinePathD(2, 0, 0, { density: 'medium', bulges: bulge })
    const pts = points(d)
    const statik = points(staticTinePaths('medium')[2])
    const apexY = (arr: Array<[number, number]>) => Math.max(...arr.map(([, y]) => y))
    expect(apexY(pts)).toBeGreaterThan(apexY(statik) + 6)
    expect(apexY(pts)).toBeLessThan(apexY(statik) + 9)
  })

  it('pins both path endpoints while a bulge travels', () => {
    for (const center of [0.05, 0.3, 0.5, 0.7, 0.95]) {
      const d = tinePathD(2, 0, 0, {
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
    const d = tinePathD(2, 0, 0, { density: 'medium', bulges: bulge })
    const pts = points(d)
    const statik = points(staticTinePaths('medium')[2])
    // left-leg top quarter (u < 0.05 path-normalized) is untouched to the cent
    for (let i = 1; i <= 3; i++) {
      expect(pts[i][0]).toBeCloseTo(statik[i][0], 2)
      expect(pts[i][1]).toBeCloseTo(statik[i][1], 2)
    }
  })

  it('sums stacked bulges on one tine', () => {
    const d = tinePathD(2, 0, 0, {
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
    const spine = points(tinePathD(0, 0, 0, { density: 'medium', bulges: bulge }))
    const midXs = spine.slice(4, -4).map(([x]) => x)
    expect(Math.max(...midXs)).toBeGreaterThan(512 + 6)
    const outer = points(tinePathD(5, 0, 0, { density: 'medium', bulges: bulge }))
    const apexY = Math.max(...outer.map(([, y]) => y))
    expect(apexY).toBeGreaterThan(944 + 6)
  })
})
