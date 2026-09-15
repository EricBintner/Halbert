// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'

import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import {
  staticTinePaths,
  TINE_AMPLITUDES,
  MAX_DISPLACEMENT_MULTIPLIER,
  laneRadius,
} from '../voice/geometry'
import { IDLE_PLUCK } from '../voice/excitation'
import type { AudioEnergySource } from '../voice/spectrum'

/** Controllable rAF: callbacks queue; pump drives frames by hand. */
let pending: Array<[number, FrameRequestCallback]> = []
let rafId = 0
let clock = 0

function installFakeRaf() {
  pending = []
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

/** Silent, then `level` on every tine for `frames` reads, then silent: one
 * strike with no sustained lean afterwards. */
function burstSource(level: number, afterFrames: number, frames = 2): AudioEnergySource {
  let reads = 0
  return {
    start: vi.fn(),
    stop: vi.fn(),
    readEnergies(out) {
      reads += 1
      out.fill(reads > afterFrames && reads <= afterFrames + frames ? level : 0)
      return out.length
    },
  }
}

const MEDIUM_STATIC = staticTinePaths('medium')

function xAt(d: string, index: number): number {
  return Number(d.split(' L ')[index].split(' ')[0])
}

/** Left-leg midpoint (index LEG_SAMPLES/2) x of a lane path — the crest of a
 * fundamental-mode leg. Positive displacement moves it left (outward). */
function legMidX(d: string): number {
  return xAt(d, 12)
}

/** Signed deviation of a probe point from the static mark. */
function deviation(d: string, k: number, index: number): number {
  return xAt(d, index) - xAt(MEDIUM_STATIC[k], index)
}

function signChanges(xs: number[]): number {
  let n = 0
  for (let i = 1; i < xs.length; i++) if (xs[i - 1] * xs[i] < 0) n++
  return n
}

/** Probe indices: spine antinode (u≈0.34 of 32), leg midpoint, outer arc
 * at θ=π/4 (index 12 of 48; θ=π/2 is a node of the fundamental). */
const SPINE_PROBE = 11
const LEG_PROBE = 12
const OUTER_PROBE = 12

describe('AudioReactiveHalbertMark', () => {
  beforeEach(installFakeRaf)
  afterEach(() => vi.unstubAllGlobals())

  it('defaults to the medium density: 6 tine paths, static medium geometry', () => {
    const { container } = render(<AudioReactiveHalbertMark size={512} />)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(6)
    paths.forEach((p, k) => expect(p.getAttribute('d')).toBe(MEDIUM_STATIC[k]))
    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 1024 1024')
    expect(container.querySelector('g')).toHaveAttribute('stroke-width', '48')
  })

  it('supports the 10-tine display density explicitly', () => {
    const { container } = render(<AudioReactiveHalbertMark size={512} density="display" />)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(10)
    paths.forEach((p, k) => expect(p.getAttribute('d')).toBe(staticTinePaths('display')[k]))
  })

  it('animates d attributes from the energy source without re-rendering React', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} source={constSource(1)} />,
    )
    const paths = container.querySelectorAll('path')
    pump(120) // ~2s of frames: the idle swell follows the level
    const d2 = paths[2].getAttribute('d')!
    expect(d2).not.toBe(MEDIUM_STATIC[2])
    expect(d2.startsWith(MEDIUM_STATIC[2].split(' L ')[0])).toBe(true)
    expect(d2.endsWith(MEDIUM_STATIC[2].split(' L ').pop()!)).toBe(true)
  })

  it('a band-level onset plucks the tine in speaking and listening; speaking strikes harder', () => {
    const ring = (state: 'speaking' | 'listening') => {
      const { container } = render(
        <AudioReactiveHalbertMark size={512} state={state} source={stepSource(0.3, 5, [2])} />,
      )
      const path = container.querySelectorAll('path')[2]
      const trace: number[] = []
      for (let i = 0; i < 60; i++) {
        pump(1)
        trace.push(deviation(path.getAttribute('d')!, 2, LEG_PROBE))
      }
      return trace
    }
    const speaking = ring('speaking')
    const listening = ring('listening')
    // A pluck rings through the rest position — a bounce never would.
    expect(signChanges(speaking)).toBeGreaterThanOrEqual(3)
    expect(signChanges(listening)).toBeGreaterThanOrEqual(3)
    const peak = (xs: number[]) => Math.max(...xs.map(Math.abs))
    expect(peak(speaking)).toBeGreaterThan(peak(listening) * 1.15)
    expect(peak(speaking)).toBeGreaterThan(0.4 * TINE_AMPLITUDES.medium[2])
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
      outer.push(deviation(paths[5].getAttribute('d')!, 5, OUTER_PROBE))
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
    expect(paths[0].getAttribute('d')).toBe(MEDIUM_STATIC[0])
    rerender(<AudioReactiveHalbertMark size={512} state="recognized" source={silence} />)
    pump(2) // ~33 ms: only the spine is due
    expect(Math.abs(deviation(paths[0].getAttribute('d')!, 0, SPINE_PROBE))).toBeGreaterThan(1)
    expect(paths[5].getAttribute('d')).toBe(MEDIUM_STATIC[5])
    pump(12) // ~230 ms: the outer arc has been struck
    expect(Math.abs(deviation(paths[5].getAttribute('d')!, 5, OUTER_PROBE))).toBeGreaterThan(1)
  })

  it('keeps ringing and still strums when the source is swapped in the same render', () => {
    // The app hands the mark a new analyser (mic tap -> TTS tap) in the same
    // render as a state change; the strings must not snap to rest.
    const { container, rerender } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={burstSource(0.4, 2)} />,
    )
    const paths = container.querySelectorAll('path')
    pump(8) // the burst has struck the outer arc, which rings for a second
    const ringing = Math.abs(deviation(paths[5].getAttribute('d')!, 5, OUTER_PROBE))
    expect(ringing).toBeGreaterThan(1)
    rerender(
      <AudioReactiveHalbertMark size={512} state="recognized" source={constSource(0)} />,
    )
    pump(1)
    // still mid-ring, not reset to the static arc
    expect(Math.abs(deviation(paths[5].getAttribute('d')!, 5, OUTER_PROBE))).toBeGreaterThan(0.5)
    // and the strum fired on the spine
    expect(Math.abs(deviation(paths[0].getAttribute('d')!, 0, SPINE_PROBE))).toBeGreaterThan(1)
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
      expect(breathingMax).toBeLessThan(0.8)
      expect(pluckMax).toBeGreaterThan(0.9)
    } finally {
      rng.mockRestore()
    }
  })

  it('a sustained level stays bounded and settles to a lean, never a ring', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={constSource(1)} sensitivity={1.2} />,
    )
    const path = container.querySelectorAll('path')[2]
    const amp = TINE_AMPLITUDES.medium[2]
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
    expect(Math.max(...tail.map(Math.abs))).toBeLessThan(0.45 * amp) // 1.2 × 0.3 swell
  })

  it('thinking neither plucks nor leans on level', () => {
    const rng = vi.spyOn(Math, 'random').mockReturnValue(0) // bulges land on the spine only
    try {
      const { container } = render(
        <AudioReactiveHalbertMark size={512} state="thinking" source={constSource(1)} />,
      )
      const lane2 = container.querySelectorAll('path')[2]
      pump(60)
      expect(lane2.getAttribute('d')).toBe(MEDIUM_STATIC[2])
    } finally {
      rng.mockRestore()
    }
  })

  it('thinking spawns a traveling bulge on a random tine and keeps the shrink', () => {
    const rng = vi.spyOn(Math, 'random').mockReturnValue(0) // tine 0, then 1, ...
    try {
      const { container } = render(<AudioReactiveHalbertMark state="thinking" />)
      const spine = container.querySelectorAll('path')[0]
      expect(spine.getAttribute('d')).toBe(MEDIUM_STATIC[0])
      pump(30) // ~0.5s: first bulge spawned at 0.3s is mid-journey
      const d = spine.getAttribute('d')!
      expect(d).not.toBe(MEDIUM_STATIC[0])
      expect(d.startsWith(MEDIUM_STATIC[0].split(' L ')[0])).toBe(true)
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
    expect(paths[2].getAttribute('d')).not.toBe(MEDIUM_STATIC[2])
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

  it('exposes the medium lane geometry constants used by the demo', () => {
    expect(laneRadius(1, 'medium')).toBe(86.4)
    expect(TINE_AMPLITUDES.medium).toHaveLength(6)
    expect(legMidX(MEDIUM_STATIC[2])).toBeCloseTo(339.2, 5)
  })
})
