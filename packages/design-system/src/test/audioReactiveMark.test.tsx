// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'

import { AudioReactiveHalbertMark } from '../voice/AudioReactiveHalbertMark'
import { STATIC_TINE_PATHS } from '../voice/geometry'
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
      return 10
    },
  }
}

describe('AudioReactiveHalbertMark', () => {
  beforeEach(installFakeRaf)
  afterEach(() => vi.unstubAllGlobals())

  it('renders 10 tine paths with the exact static geometry on first paint', () => {
    const { container } = render(<AudioReactiveHalbertMark size={512} />)
    const paths = container.querySelectorAll('path')
    expect(paths).toHaveLength(10)
    paths.forEach((p, k) => expect(p.getAttribute('d')).toBe(STATIC_TINE_PATHS[k]))
    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 1024 1024')
  })

  it('animates d attributes from the energy source without re-rendering React', () => {
    const { container } = render(
      <AudioReactiveHalbertMark size={512} source={constSource(1)} />,
    )
    const paths = container.querySelectorAll('path')
    pump(120) // ~2s of frames: springs approach full energy
    const d4 = paths[4].getAttribute('d')!
    expect(d4).not.toBe(STATIC_TINE_PATHS[4])
    // junction pinning holds under animation: first/last points unchanged
    expect(d4.startsWith(STATIC_TINE_PATHS[4].split(' L ')[0])).toBe(true)
    expect(d4.endsWith(STATIC_TINE_PATHS[4].split(' L ').pop()!)).toBe(true)
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
    expect(paths[2].getAttribute('d')).not.toBe(STATIC_TINE_PATHS[2])
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
})
