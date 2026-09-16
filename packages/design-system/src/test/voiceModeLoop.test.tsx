// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'

import { VoiceModeLoop, VOICE_MODE_LOOP } from '../voice/VoiceModeLoop'

/** The mark's own frame loop is not under test here; park rAF so fake
 * timers drive only the state loop. */
function parkRaf() {
  vi.stubGlobal('requestAnimationFrame', () => 1)
  vi.stubGlobal('cancelAnimationFrame', () => {})
}

const stateOf = (container: HTMLElement) =>
  Array.from(container.querySelector('svg')!.classList)
    .find((c) => c.startsWith('hb-reactive-mark--'))!
    .replace('hb-reactive-mark--', '')

describe('VoiceModeLoop — the kiosk conversation as a loop', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    parkRaf()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('walks listening, recognized, thinking, speaking and round again, 2.5 s each by default', () => {
    expect(VOICE_MODE_LOOP).toEqual(['listening', 'recognized', 'thinking', 'speaking'])
    const { container } = render(<VoiceModeLoop size={256} />)
    expect(container.querySelectorAll('path')).toHaveLength(7) // the brand mark
    expect(stateOf(container)).toBe('listening')
    act(() => vi.advanceTimersByTime(2500))
    expect(stateOf(container)).toBe('recognized')
    act(() => vi.advanceTimersByTime(2500))
    expect(stateOf(container)).toBe('thinking')
    act(() => vi.advanceTimersByTime(2500))
    expect(stateOf(container)).toBe('speaking')
    act(() => vi.advanceTimersByTime(2500))
    expect(stateOf(container)).toBe('listening')
  })

  it('takes its own pace and reports each state', () => {
    const seen: string[] = []
    render(<VoiceModeLoop intervalMs={1000} onStateChange={(s) => seen.push(s)} />)
    // one tick per act: React batches everything inside a single act, as it
    // would never do across real frames
    for (let i = 0; i < 3; i++) act(() => vi.advanceTimersByTime(1000))
    expect(seen).toEqual(['listening', 'recognized', 'thinking', 'speaking'])
  })

  it('passes the mark props through and plays the shared demo voice by default', () => {
    const { container } = render(<VoiceModeLoop size="100%" tone="ink" sensitivity={1.2} />)
    const svg = container.querySelector('svg')!
    expect(svg.getAttribute('width')).toBe('100%')
    expect(container.querySelector('g')!.getAttribute('stroke')).toContain('--color-ink')
  })

  it('stops its clock on unmount', () => {
    const seen: string[] = []
    const { unmount } = render(<VoiceModeLoop intervalMs={500} onStateChange={(s) => seen.push(s)} />)
    act(() => vi.advanceTimersByTime(500))
    unmount()
    const before = seen.length
    act(() => vi.advanceTimersByTime(5000))
    expect(seen.length).toBe(before)
  })
})
