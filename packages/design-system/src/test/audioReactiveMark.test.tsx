// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'

import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import {
  staticTinePaths,
  TINE_AMPLITUDES,
  MAX_DISPLACEMENT_MULTIPLIER,
  MARK,
  laneRadius,
  laneTop,
} from '../voice/geometry'
import { IDLE_PLUCK } from '../voice/excitation'
import type { AudioEnergySource } from '../voice/spectrum'

/** Controllable rAF: callbacks queue; pump drives frames by hand. */
let pending: Array<[number, FrameRequestCallback]> = []
let rafId = 0
let clock = 0

function installFakeRaf() {
  pending = []
  rafId = 0
  clock = 0
  // The component seeds its frame delta from performance.now(); tie it to
  // the fake frame clock so the first frame after any effect (re)run is one
  // real frame, not zero or a wall-clock-dependent clamp.
  vi.spyOn(performance, 'now').mockImplementation(() => clock)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    rafId += 1
    pending.push([rafId, cb])
    return rafId
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    pending = pending.filter(([pid]) => pid !== id)
  })
}

function pump(frames: number, dtMs = 16.7) {
  for (let i = 0; i < frames; i++) {
    const q = pending
    pending = []
    clock += dtMs
    for (const [, cb] of q) cb(clock)
  }
}

function constSource(v: number): AudioEnergySource {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    readEnergies(out) {
      out.fill(v)
      return out.length
    },
  }
}

/** Silent until `afterFrames` reads, then a steady level on `tines`. */
function stepSource(level: number, afterFrames: number, tines?: number[]): AudioEnergySource {
  let reads = 0
  return {
    start: vi.fn(),
    stop: vi.fn(),
    readEnergies(out) {
      out.fill(0)
      reads += 1
      if (reads > afterFrames) {
        if (tines) for (const k of tines) out[k] = level
        else out.fill(level)
      }
      return out.length
    },
  }
}

/** Silent, then `level` on `tines` (default all) for `frames` reads, then
 * silent: one strike with no sustained lean afterwards. */
function burstSource(
  level: number,
  afterFrames: number,
  tines?: number[],
  frames = 2,
): AudioEnergySource {
  let reads = 0
  return {
    start: vi.fn(),
    stop: vi.fn(),
    readEnergies(out) {
      reads += 1
      out.fill(0)
      if (reads > afterFrames && reads <= afterFrames + frames) {
        if (tines) for (const k of tines) out[k] = level
        else out.fill(level)
      }
      return out.length
    },
  }
}

/** The brand (7-line) mark is the default. Outer arc = tine 6. */
const STATIC = staticTinePaths()
const OUTER = 6

function xAt(d: string, index: number): number {
  return Number(d.split(' L ')[index].split(' ')[0])
}
function points(d: string): Array<[number, number]> {
  return d
    .replace(/^M /, '')
    .split(' L ')
    .map((p) => p.split(' ').map(Number) as [number, number])
}
const first = (d: string) => points(d)[0]
const last = (d: string) => {
  const p = points(d)
  return p[p.length - 1]
}

/** Left-leg midpoint (index LEG_SAMPLES/2) x of a lane path — the crest of a
 * fundamental-mode leg. Positive displacement moves it left (outward). */
function legMidX(d: string): number {
  return xAt(d, 12)
}

/** Signed deviation of a probe point from the static mark. */
function deviation(d: string, k: number, index: number): number {
  return xAt(d, index) - xAt(STATIC[k], index)
}

function signChanges(xs: number[]): number {
  let n = 0
  for (let i = 1; i < xs.length; i++) if (xs[i - 1] * xs[i] < 0) n++
  return n
}

/** Distance from a point to the static geometry of U-lane k (legs vertical
 * at 512 ± r above the centre line; a radius-r arc below it). */
function offStatic(k: number, [x, y]: [number, number]): number {
  const r = laneRadius(k)
  if (y <= MARK.cy + 1e-9) return Math.min(Math.abs(x - (512 - r)), Math.abs(x - (512 + r)))
  return Math.abs(Math.hypot(x - MARK.cx, y - MARK.cy) - r)
}

/** Probe indices: spine antinode (u≈0.34 of 32), leg midpoint, outer arc
 * at θ=π/4 (index 12 of 48; θ=π/2 is a node of the fundamental). */
const SPINE_PROBE = 11
const LEG_PROBE = 12
const OUTER_PROBE = 12

describe('AudioReactiveHalbertMark', () => {
  beforeEach(installFakeRaf)
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('defaults to the brand density: the ratified 7-line mark, 48 stroke', () => {
    const { container } = render(<AudioReactiveHalbertMark size={512} />)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(7)
    paths.forEach((p, k) => expect(p.getAttribute('d')).toBe(STATIC[k]))
    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 1024 1024')
    expect(container.querySelector('g')).toHaveAttribute('stroke-width', '48')
    expect(first(STATIC[1])).toEqual([440, 86.04])
  })

  it('supports the 10-tine display density explicitly', () => {
    const { container } = render(<AudioReactiveHalbertMark size={512} density="display" />)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(10)
    paths.forEach((p, k) => expect(p.getAttribute('d')).toBe(staticTinePaths('display')[k]))
    expect(container.querySelector('g')).toHaveAttribute('stroke-width', '26.67')
  })

  it('animates d attributes from the energy source without re-rendering React', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} source={constSource(1)} />,
    )
    const paths = container.querySelectorAll('path')
    pump(120) // ~2s of frames: the idle swell follows the level
    const d2 = paths[2].getAttribute('d')!
    expect(d2).not.toBe(STATIC[2])
    expect(d2.startsWith(STATIC[2].split(' L ')[0])).toBe(true)
    expect(d2.endsWith(STATIC[2].split(' L ').pop()!)).toBe(true)
  })

  it('a band-level onset plucks the tine while speaking', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={stepSource(0.3, 5, [2])} />,
    )
    const path = container.querySelectorAll('path')[2]
    const trace: number[] = []
    for (let i = 0; i < 60; i++) {
      pump(1)
      trace.push(deviation(path.getAttribute('d')!, 2, LEG_PROBE))
    }
    // A pluck rings through the rest position — a bounce never would.
    expect(signChanges(trace)).toBeGreaterThanOrEqual(3)
    expect(Math.max(...trace.map(Math.abs))).toBeGreaterThan(0.4 * TINE_AMPLITUDES.brand[2])
  })

  it('the plucked spine rings faster and dies sooner than the plucked outer arc', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={burstSource(0.3, 5)} />,
    )
    const paths = container.querySelectorAll('path')
    const spine: number[] = []
    const outer: number[] = []
    for (let i = 0; i < 66; i++) {
      pump(1)
      spine.push(deviation(paths[0].getAttribute('d')!, 0, SPINE_PROBE))
      outer.push(deviation(paths[OUTER].getAttribute('d')!, OUTER, OUTER_PROBE))
    }
    // ~1 s after the strike: 8 Hz spine vs 2 Hz arc
    expect(signChanges(spine)).toBeGreaterThan(2 * signChanges(outer))
    expect(signChanges(outer)).toBeGreaterThanOrEqual(1)
    const early = (xs: number[]) => Math.max(...xs.slice(5, 20).map(Math.abs))
    // last 0.1 s for the fast spine; last 0.33 s (two thirds of a cycle) for
    // the slow arc, so the window is sure to contain a crest
    expect(Math.max(...spine.slice(-6).map(Math.abs))).toBeLessThan(0.15 * early(spine))
    expect(Math.max(...outer.slice(-20).map(Math.abs))).toBeGreaterThan(0.25 * early(outer))
  })

  it('entering recognized strums the strings spine-first', () => {
    const silence = constSource(0)
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="listening" source={silence} />,
    )
    const paths = container.querySelectorAll('path')
    pump(5)
    expect(paths[0].getAttribute('d')).toBe(STATIC[0])
    rerender(<AudioReactiveHalbertMark size={512} state="recognized" source={silence} />)
    pump(2) // ~33 ms: only the spine is due
    expect(Math.abs(deviation(paths[0].getAttribute('d')!, 0, SPINE_PROBE))).toBeGreaterThan(1)
    expect(paths[OUTER].getAttribute('d')).toBe(STATIC[OUTER])
    // the outer arc is struck at 6 × 35 = 210 ms and, at 2 Hz, crests 125 ms
    // later; its brand amplitude is 8 and the probe sees a quarter of it
    pump(20)
    expect(Math.abs(deviation(paths[OUTER].getAttribute('d')!, OUTER, OUTER_PROBE))).toBeGreaterThan(0.8)
  })

  it('keeps ringing and still strums when the source is swapped in the same render', () => {
    // The app hands the mark a new analyser (mic tap -> TTS tap) in the same
    // render as a state change; the strings must not snap to rest. The burst
    // strikes lane 4 only, so any spine motion afterwards is the strum's.
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={burstSource(0.4, 2, [4])} />,
    )
    const paths = container.querySelectorAll('path')
    pump(8) // lane 4 rings for most of a second
    expect(Math.abs(deviation(paths[4].getAttribute('d')!, 4, LEG_PROBE))).toBeGreaterThan(3)
    expect(paths[0].getAttribute('d')).toBe(STATIC[0])
    rerender(
      <AudioReactiveHalbertMark size={512} state="recognized" source={constSource(0)} />,
    )
    pump(2)
    // lane 4 still mid-ring, not reset to rest
    expect(Math.abs(deviation(paths[4].getAttribute('d')!, 4, LEG_PROBE))).toBeGreaterThan(1)
    // and the strum has struck the spine
    expect(Math.abs(deviation(paths[0].getAttribute('d')!, 0, SPINE_PROBE))).toBeGreaterThan(1)
  })

  it('mounting directly in recognized strums too', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} state="recognized" source={constSource(0)} />,
    )
    const paths = container.querySelectorAll('path')
    pump(2)
    expect(Math.abs(deviation(paths[0].getAttribute('d')!, 0, SPINE_PROBE))).toBeGreaterThan(1)
    pump(20)
    expect(Math.abs(deviation(paths[OUTER].getAttribute('d')!, OUTER, OUTER_PROBE))).toBeGreaterThan(0.8)
  })

  it('ramps the lean across a state change instead of popping', () => {
    // speaking leans 0.3 x level; idle leans 1.0 x level. Switching must
    // glide between them over a few frames, never jump.
    const level = constSource(1)
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={level} />,
    )
    const spine = container.querySelectorAll('path')[0]
    const probe = () => Math.abs(deviation(spine.getAttribute('d')!, 0, SPINE_PROBE))
    pump(90) // the mount strike has died; only the settled lean remains
    const lean = probe()
    expect(lean).toBeGreaterThan(0.5)
    rerender(<AudioReactiveHalbertMark size={512} state="idle" source={level} />)
    pump(1)
    expect(probe()).toBeLessThan(1.45 * lean) // an instant switch would be ~3.3x
    pump(30)
    expect(probe()).toBeGreaterThan(2.8 * lean)
  })

  it('sensitivity scales how hard strikes land; the ring never exceeds RING_MAX', () => {
    const amp = TINE_AMPLITUDES.brand[2]
    const { container } = render(
      <AudioReactiveHalbertMark
        size={512}
        state="speaking"
        sensitivity={1.2}
        source={burstSource(0.5, 5, [2])}
      />,
    )
    const path = container.querySelectorAll('path')[2]
    let peak = 0
    for (let i = 0; i < 40; i++) {
      pump(1)
      peak = Math.max(peak, Math.abs(deviation(path.getAttribute('d')!, 2, LEG_PROBE)))
    }
    expect(peak).toBeGreaterThan(0.7 * amp)
    expect(peak).toBeLessThan(1.0 * amp)
  })

  it('switching density at runtime renders the new tine count with finite geometry', () => {
    const level = constSource(0.5)
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="listening" source={level} />,
    )
    pump(10)
    rerender(
      <AudioReactiveHalbertMark size={512} state="listening" density="display" source={level} />,
    )
    pump(10)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(10)
    paths.forEach((p) => expect(p.getAttribute('d')).not.toMatch(/NaN/))
    expect(container.querySelector('g')).toHaveAttribute('stroke-width', '26.67')
  })

  it('a density change keeps the current posture instead of the mount state', () => {
    const source = stepSource(0.3, 0, [2, 3])
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={source} />,
    )
    rerender(<AudioReactiveHalbertMark size={512} state="listening" source={source} />)
    pump(60) // withdrawn
    rerender(
      <AudioReactiveHalbertMark size={512} state="listening" density="display" source={source} />,
    )
    pump(1)
    // the new engine starts with listening's full retraction weight and the
    // carried attention, not speaking's zero ramping up from nothing. The
    // vowel sat on brand bands 2-3 (700-2000 Hz); by register that is display
    // tine 3 (1000-1500 Hz), whose tips must already be well in.
    const d3 = container.querySelectorAll('path')[3].getAttribute('d')!
    expect(first(d3)[1]).toBeGreaterThan(laneTop(3, 'display') + 30)
  })

  it('a density change while recognized does not strum again', () => {
    const silence = constSource(0)
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="recognized" source={silence} />,
    )
    pump(90) // the mount strum has rung out
    rerender(
      <AudioReactiveHalbertMark size={512} state="recognized" density="display" source={silence} />,
    )
    pump(3)
    const spine = container.querySelectorAll('path')[0].getAttribute('d')!
    expect(spine).toBe(staticTinePaths('display')[0])
  })

  it('tolerates an unknown state from an untyped consumer', () => {
    const { container } = render(
      // @ts-expect-error — JSX callers can pass anything
      <AudioReactiveHalbertMark size={512} state="dreaming" source={constSource(0.5)} />,
    )
    expect(() => pump(5)).not.toThrow()
    expect(container.querySelectorAll('path')).toHaveLength(7)
  })

  describe('listening — the lines withdraw their ends and never warp', () => {
    const speech = () => stepSource(0.3, 5, [2, 3])

    it('withdraws every line along its own static geometry', () => {
      const { container } = render(
        <AudioReactiveHalbertMark size={512} state="listening" source={speech()} />,
      )
      const paths = container.querySelectorAll('path')
      pump(45) // ~0.75 s: attention is up
      // lane 2 (the vowel's own register): tips have slid a fixed 45-70
      // units down both legs; every point still on the U
      const d2 = paths[2].getAttribute('d')!
      expect(first(d2)[1]).toBeGreaterThan(laneTop(2) + 40)
      expect(first(d2)[1]).toBeLessThan(laneTop(2) + 75)
      expect(last(d2)[1]).toBeGreaterThan(laneTop(2) + 40)
      for (const p of points(d2)) expect(offStatic(2, p)).toBeLessThan(0.05)
      // spine (a register the vowel does not reach): withdrawn a little from
      // the top, the whole mark listens; its base still at the mark's centre
      const d0 = paths[0].getAttribute('d')!
      expect(first(d0)[0]).toBe(512)
      expect(first(d0)[1]).toBeGreaterThan(80 + 8)
      expect(first(d0)[1]).toBeLessThan(80 + 25)
      expect(last(d0)).toEqual([512, 512])
      // outer arc: tips have slid a little along the arc, still at radius 432
      const d6 = paths[OUTER].getAttribute('d')!
      expect(Math.hypot(first(d6)[0] - 80, first(d6)[1] - 512)).toBeGreaterThan(8)
      expect(Math.hypot(first(d6)[0] - 80, first(d6)[1] - 512)).toBeLessThan(25)
      for (const [x, y] of points(d6)) {
        expect(Math.abs(Math.hypot(x - 512, y - 512) - 432)).toBeLessThan(0.05)
      }
    })

    it('leaves the ends where they are while speaking', () => {
      const { container } = render(
        <AudioReactiveHalbertMark size={512} state="speaking" source={speech()} />,
      )
      const paths = container.querySelectorAll('path')
      pump(45)
      expect(first(paths[2].getAttribute('d')!)).toEqual(first(STATIC[2]))
      expect(last(paths[2].getAttribute('d')!)).toEqual(last(STATIC[2]))
      expect(first(paths[OUTER].getAttribute('d')!)).toEqual(first(STATIC[OUTER]))
    })

    it('a clap withdraws far more than speech, and never closes a line', () => {
      const remaining = (source: AudioEnergySource) => {
        const { container } = render(
          <AudioReactiveHalbertMark size={512} state="listening" source={source} />,
        )
        const path = container.querySelectorAll('path')[3] // a ring the vowel attends
        let fewest = Infinity
        for (let i = 0; i < 45; i++) {
          pump(1)
          fewest = Math.min(fewest, points(path.getAttribute('d')!).length)
        }
        return fewest
      }
      const full = points(STATIC[3]).length
      const speechLeft = remaining(speech())
      const clapLeft = remaining(burstSource(0.8, 5))
      expect(speechLeft).toBeLessThan(full)
      expect(speechLeft).toBeGreaterThan(0.6 * full)
      expect(clapLeft).toBeLessThan(speechLeft - 15)
      expect(clapLeft).toBeGreaterThanOrEqual(3) // never a dot
    })

    it('releases the ends smoothly when listening ends', () => {
      const source = speech()
      const { container, rerender } = render(
        <AudioReactiveHalbertMark size={512} state="listening" source={source} />,
      )
      const path = container.querySelectorAll('path')[2]
      pump(45)
      const top = laneTop(2)
      const depth0 = first(path.getAttribute('d')!)[1] - top
      expect(depth0).toBeGreaterThan(30)
      rerender(<AudioReactiveHalbertMark size={512} state="thinking" source={source} />)
      const depths: number[] = []
      for (let i = 0; i < 24; i++) {
        pump(1)
        depths.push(first(path.getAttribute('d')!)[1] - top)
      }
      expect(depths[0]).toBeGreaterThan(0.5 * depth0) // no snap on the first frame
      for (let i = 1; i < depths.length; i++) expect(depths[i]).toBeLessThanOrEqual(depths[i - 1] + 1e-6)
      expect(depths[depths.length - 1]).toBeLessThan(0.4 * depth0)
    })
  })

  it('idle plucks a string now and then on top of the breathing', () => {
    const rng = vi.spyOn(Math, 'random').mockReturnValue(0) // spine, softest, soonest
    try {
      const { container } = render(<AudioReactiveHalbertMark size={512} state="idle" />)
      const spine = container.querySelectorAll('path')[0]
      const probe = () => Math.abs(deviation(spine.getAttribute('d')!, 0, SPINE_PROBE))
      let breathingMax = 0
      const quietFrames = Math.floor((IDLE_PLUCK.minInterval * 1000) / 16.7) - 3
      for (let i = 0; i < quietFrames; i++) {
        pump(1)
        breathingMax = Math.max(breathingMax, probe())
      }
      let pluckMax = 0
      for (let i = 0; i < 12; i++) {
        pump(1)
        pluckMax = Math.max(pluckMax, probe())
      }
      expect(breathingMax).toBeLessThan(0.6)
      expect(pluckMax).toBeGreaterThan(0.7)
    } finally {
      rng.mockRestore()
    }
  })

  it('a sustained level stays bounded and settles to a lean, never a ring', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={constSource(1)} sensitivity={1.2} />,
    )
    const path = container.querySelectorAll('path')[2]
    const amp = TINE_AMPLITUDES.brand[2]
    let peak = 0
    for (let i = 0; i < 120; i++) {
      pump(1)
      peak = Math.max(peak, Math.abs(deviation(path.getAttribute('d')!, 2, LEG_PROBE)))
    }
    expect(peak).toBeLessThanOrEqual(MAX_DISPLACEMENT_MULTIPLIER * amp + 0.01)
    const tail: number[] = []
    for (let i = 0; i < 30; i++) {
      pump(1)
      tail.push(deviation(path.getAttribute('d')!, 2, LEG_PROBE))
    }
    expect(signChanges(tail)).toBe(0)
    expect(Math.max(...tail.map(Math.abs))).toBeLessThan(0.45 * amp) // 0.3 swell
  })

  it('thinking neither plucks nor leans on level', () => {
    const rng = vi.spyOn(Math, 'random').mockReturnValue(0) // bulges land on the spine only
    try {
      const { container } = render(
        <AudioReactiveHalbertMark size={512} state="thinking" source={constSource(1)} />,
      )
      const lane2 = container.querySelectorAll('path')[2]
      pump(60)
      expect(lane2.getAttribute('d')).toBe(STATIC[2])
    } finally {
      rng.mockRestore()
    }
  })

  it('thinking spawns a traveling bulge on a random tine and keeps the shrink', () => {
    const rng = vi.spyOn(Math, 'random').mockReturnValue(0) // tine 0, then 1, ...
    try {
      const { container } = render(<AudioReactiveHalbertMark state="thinking" />)
      const spine = container.querySelectorAll('path')[0]
      expect(spine.getAttribute('d')).toBe(STATIC[0])
      pump(30) // ~0.5s: first bulge spawned at 0.3s is mid-journey
      const d = spine.getAttribute('d')!
      expect(d).not.toBe(STATIC[0])
      expect(d.startsWith(STATIC[0].split(' L ')[0])).toBe(true)
      // contraction: group transform has begun scaling down
      const transform = container.querySelector('g')!.getAttribute('transform')!
      expect(transform).toMatch(/scale\(0\.9\d/)
    } finally {
      rng.mockRestore()
    }
  })

  it('smoothly contracts when entering thinking and grows when exiting thinking', () => {
    const { container, rerender } = render(<AudioReactiveHalbertMark state="thinking" />)
    pump(30)
    const g = container.querySelector('g')!
    expect(g.getAttribute('transform')).toMatch(/scale\(0\.9\d/)

    // Exit thinking into speaking
    rerender(<AudioReactiveHalbertMark state="speaking" />)
    // On the immediate next frame, the spring has not popped to 1.0; it grows smoothly
    pump(1)
    expect(g.getAttribute('transform')).toMatch(/scale\(0\.9\d/)

    // After the spring settles (~0.5s), it has grown back to ~1.0
    pump(60)
    const scale = Number(g.getAttribute('transform')!.match(/scale\(([^)]+)\)/)![1])
    expect(scale).toBeGreaterThan(0.999)
  })

  it('starts and stops the source with mount lifecycle', () => {
    const src = constSource(0.5)
    const { unmount } = render(<AudioReactiveHalbertMark source={src} />)
    expect(src.start).toHaveBeenCalledTimes(1)
    pump(2)
    unmount()
    expect(src.stop).toHaveBeenCalledTimes(1)
    pump(5) // no callbacks survive unmount — nothing to assert but absence of throw
  })

  it('falls back to idle breathing when no source is given', () => {
    const { container } = render(<AudioReactiveHalbertMark />)
    const paths = container.querySelectorAll('path')
    pump(90)
    expect(paths[2].getAttribute('d')).not.toBe(STATIC[2])
  })

  it('applies state classes and the error tint', () => {
    const { container, rerender } = render(<AudioReactiveHalbertMark state="listening" />)
    expect(container.querySelector('svg')).toHaveClass('hb-reactive-mark--listening')
    rerender(<AudioReactiveHalbertMark state="error" />)
    expect(container.querySelector('svg')).toHaveClass('hb-reactive-mark--error')
    expect(container.querySelector('g')!.getAttribute('stroke')).toContain(
      '--color-status-error',
    )
  })

  it('exposes the brand lane geometry constants used by the demo', () => {
    expect(laneRadius(1)).toBe(72)
    expect(TINE_AMPLITUDES.brand).toHaveLength(7)
    expect(legMidX(STATIC[2])).toBeCloseTo(368, 5)
  })
})
