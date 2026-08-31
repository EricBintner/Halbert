// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest'
import {
  TINE_COUNT,
  TINE_AMPLITUDES,
  TINE_MODES,
  laneRadius,
  laneTop,
  tinePathD,
  STATIC_TINE_PATHS,
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

describe('mark voice geometry', () => {
  it('matches the verified static mark model', () => {
    expect(TINE_COUNT).toBe(10) // spine + 9 lanes
    expect(laneRadius(9)).toBe(432)
    expect(laneTop(1)).toBeCloseTo(82.67, 2)
    expect(laneTop(9)).toBeCloseTo(512, 5) // lane 9 has no legs
  })

  it('static tine paths reproduce the display-density endpoints', () => {
    expect(STATIC_TINE_PATHS).toHaveLength(10)
    // spine: M 512 80 ... 512 512
    expect(firstPoint(STATIC_TINE_PATHS[0])).toEqual([512, 80])
    // lane 1 left-leg top
    expect(firstPoint(STATIC_TINE_PATHS[1])).toEqual([464, 82.67])
    // lane 9 bare semicircle: (80,512) .. (944,512)
    expect(firstPoint(STATIC_TINE_PATHS[9])).toEqual([80, 512])
    const lane9 = points(STATIC_TINE_PATHS[9])
    expect(lane9[lane9.length - 1]).toEqual([944, 512])
    // arc apex of lane 4 is at y = 512 + 192 = 704
    const lane4 = points(STATIC_TINE_PATHS[4])
    const apexY = Math.max(...lane4.map(([, y]) => y))
    expect(apexY).toBeCloseTo(704, 1)
  })

  it('pins all junctions under displacement (no tearing)', () => {
    for (let lane = 1; lane <= 9; lane++) {
      const displaced = tinePathD(lane, TINE_AMPLITUDES[lane], 1.234)
      const pts = points(displaced)
      const statik = points(STATIC_TINE_PATHS[lane])
      // leg tops and leg/arc junctions do not move
      expect(pts[0]).toEqual(statik[0])
      expect(pts[pts.length - 1]).toEqual(statik[statik.length - 1])
      if (lane < 9) {
        // the leg-bottom junction (start of the arc run) is pinned
        const legBottom = statik[24] // LEG_SAMPLES: 0..24 on the left leg
        expect(pts[24][0]).toBeCloseTo(legBottom[0], 2)
        expect(pts[24][1]).toBeCloseTo(legBottom[1], 2)
      }
    }
  })

  it('displaces interior points and mirrors leg directions', () => {
    const d = tinePathD(4, 10, 0)
    const pts = points(d)
    const statik = points(STATIC_TINE_PATHS[4])
    // left-leg midpoint moves outward (−x); right-leg midpoint moves outward (+x)
    const leftMid = 12
    expect(pts[leftMid][0]).toBeLessThan(statik[leftMid][0])
    const rightMid = pts.length - 1 - 12
    expect(pts[rightMid][0]).toBeGreaterThan(statik[rightMid][0])
  })

  it('keeps adjacent tine excursions inside the inter-lane gap', () => {
    // display-tier gap = 48 pitch − 26.67 stroke = 21.33 units
    for (let k = 0; k < TINE_COUNT - 1; k++) {
      expect(TINE_AMPLITUDES[k] + TINE_AMPLITUDES[k + 1]).toBeLessThan(21.33)
    }
    expect(TINE_MODES).toHaveLength(TINE_COUNT)
  })

  it('spine pins both ends and flexes in the middle', () => {
    const d = tinePathD(0, TINE_AMPLITUDES[0], 0)
    const pts = points(d)
    expect(pts[0]).toEqual([512, 80])
    expect(pts[pts.length - 1]).toEqual([512, 512])
    const midXs = pts.slice(4, -4).map(([x]) => x)
    expect(Math.max(...midXs.map((x) => Math.abs(x - 512)))).toBeGreaterThan(0.5)
  })
})
