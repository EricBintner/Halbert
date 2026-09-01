// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'

import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import { staticTinePaths, TINE_AMPLITUDES, laneRadius } from '../voice/geometry'
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

const MEDIUM_STATIC = staticTinePaths('medium')

/** Left-leg midpoint (index LEG_SAMPLES/2) x of a lane path string — where
 * the standing wave crests, unlike the arc apex (a node at phase ~0). */
function legMidX(d: string): number {
  return Number(d.split(' L ')[12].split(' ')[0])
}

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
    pump(120) // ~2s of frames: springs approach full energy
    const d2 = paths[2].getAttribute('d')!
    expect(d2).not.toBe(MEDIUM_STATIC[2])
    expect(d2.startsWith(MEDIUM_STATIC[2].split(' L ')[0])).toBe(true)
    expect(d2.endsWith(MEDIUM_STATIC[2].split(' L ').pop()!)).toBe(true)
  })

  it('speaking rings past the amplitude ceiling (pluck), listening never does', () => {
    // medium lane 2: amplitude 11. The well-damped spring approaches 1*A
    // asymptotically; the pluck spring overshoots to ~1.6*A. Probed at the
    // left-leg midpoint (index 12 of the path), where the tine-2 standing
    // wave crests at |cos(phase)|.
    const staticX = legMidX(MEDIUM_STATIC[2])
    const amp = TINE_AMPLITUDES.medium[2]

    const { container: speakBox } = render(
      <AudioReactiveHalbertMark size={512} state="speaking" source={constSource(1)} />,
    )
    const speakPath = speakBox.querySelectorAll('path')[2]
    let speakMax = 0
    for (let i = 0; i < 60; i++) {
      pump(1)
      speakMax = Math.max(speakMax, Math.abs(legMidX(speakPath.getAttribute('d')!) - staticX))
    }
    expect(speakMax).toBeGreaterThan(1.2 * amp)

    const { container: listenBox } = render(
      <AudioReactiveHalbertMark size={512} state="listening" source={constSource(1)} />,
    )
    const listenPath = listenBox.querySelectorAll('path')[2]
    let listenMax = 0
    for (let i = 0; i < 60; i++) {
      pump(1)
      listenMax = Math.max(listenMax, Math.abs(legMidX(listenPath.getAttribute('d')!) - staticX))
    }
    expect(listenMax).toBeLessThan(1.08 * amp)
    expect(listenMax).toBeGreaterThan(0.5 * amp)
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
  })
})
