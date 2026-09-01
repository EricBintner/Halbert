// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StandbyController (P1): the in-app half of spec doc 15 §5.2's multi-tier
 * standby policy. Fake-timer transitions pin the tier ladder (full → tier 1
 * ultra-dim + room clock at 30s idle → tier 2 software blackout at 10min),
 * the restore paths (pointer / touch / keydown / machine wake), the idle
 * reset on machine events, and the fire-and-forget idle report P2 consumes.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { StandbyController } from './StandbyController'
import type { StandbyTier } from './StandbyController'
import type { VoiceModeState } from '@/hooks/useVoiceModeMachine'

const fetchMock = vi.fn(
  async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> =>
    ({ ok: true }) as Response,
)

function mount(machineState: VoiceModeState = 'standby') {
  const make = (s: VoiceModeState) => <StandbyController machineState={s} />
  const view = render(make(machineState))
  return {
    view,
    veil: () => screen.getByTestId('standby-veil'),
    clock: () => screen.queryByTestId('standby-clock'),
    rerender: (s: VoiceModeState) => view.rerender(make(s)),
  }
}

function advance(ms: number): void {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

function tierOf(veil: HTMLElement): StandbyTier {
  if (veil.className.includes('cursor-none')) return 'black'
  if (veil.className.includes('opacity-0')) return 'full'
  return 'dim'
}

function reportBodies(): Array<Record<string, unknown>> {
  return fetchMock.mock.calls.map((call) =>
    JSON.parse(String((call[1] as RequestInit | undefined)?.body)),
  )
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-31T23:47:00'))
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('StandbyController tiers', () => {
  it('starts fully visible: no veil, no clock, no report', () => {
    const h = mount()
    expect(tierOf(h.veil())).toBe('full')
    expect(h.clock()).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('dims to tier 1 after 30s idle: ultra-dim veil plus the room clock', () => {
    const h = mount()
    advance(29_999)
    expect(tierOf(h.veil())).toBe('full')

    advance(1)
    const veil = h.veil()
    expect(tierOf(veil)).toBe('dim')
    // The veil is a 90%-black layer over the page (the mark beneath keeps
    // breathing idle at ~10% effective opacity).
    expect(veil.className).toContain('opacity-90')
    // Tier 1 keeps the room clock (spec §5.2 tier 1) — large and dim.
    expect(h.clock()?.textContent).toBe('23:47')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('blacks out to tier 2 after 10 minutes idle: pure black, cursor hidden, clock gone', () => {
    const h = mount()
    advance(600_000)
    const veil = h.veil()
    expect(tierOf(veil)).toBe('black')
    expect(veil.className).toContain('cursor-none')
    expect(veil.className).toContain('bg-black')
    expect(veil.className).toContain('opacity-100')
    expect(h.clock()).toBeNull()
  })

  it('the room clock follows the minute while dimmed', () => {
    const h = mount()
    advance(30_000)
    expect(h.clock()?.textContent).toBe('23:47')
    advance(60_000)
    expect(h.clock()?.textContent).toBe('23:48')
  })

  it('keeps the veil inert to taps at tier 1 (kiosk taps reach the page)', () => {
    const h = mount()
    advance(30_000)
    expect(h.veil().className).toContain('pointer-events-none')
  })
})

describe('StandbyController restore paths', () => {
  it('any pointer event restores from tier 2 to full', () => {
    const h = mount()
    advance(600_000)
    expect(tierOf(h.veil())).toBe('black')

    act(() => {
      window.dispatchEvent(new Event('pointermove'))
    })
    expect(tierOf(h.veil())).toBe('full')
    expect(h.veil().className).not.toContain('cursor-none')
  })

  it('a touch restores from tier 2 to full', () => {
    const h = mount()
    advance(600_000)
    act(() => {
      window.dispatchEvent(new Event('touchstart'))
    })
    expect(tierOf(h.veil())).toBe('full')
  })

  it('a keypress restores from tier 1 to full', () => {
    const h = mount()
    advance(30_000)
    expect(tierOf(h.veil())).toBe('dim')

    act(() => {
      window.dispatchEvent(new Event('keydown'))
    })
    expect(tierOf(h.veil())).toBe('full')
  })

  it('a machine wake restores the tier (and a re-standby re-arms the ladder)', () => {
    const h = mount()
    advance(600_000)
    expect(tierOf(h.veil())).toBe('black')

    // Any dispatch that leaves standby (wake, acoustic_wake, a turn) counts.
    h.rerender('listening')
    expect(tierOf(h.veil())).toBe('full')

    // Back to standby: the idle clock restarted at the wake, so the screen
    // holds full for another 30s before dimming again.
    h.rerender('standby')
    expect(tierOf(h.veil())).toBe('full')
    advance(30_000)
    expect(tierOf(h.veil())).toBe('dim')
  })

  it('a machine event resets the idle clock (a speaking turn is not idle)', () => {
    const h = mount()
    advance(20_000)

    // A turn runs: listening -> thinking -> speaking. The transitions into
    // non-standby states reset the idle clock AND pin the tier full.
    h.rerender('thinking')
    advance(20_000)
    h.rerender('speaking')
    advance(600_000) // a long turn: far past the tier-2 boundary
    expect(tierOf(h.veil())).toBe('full') // an in-flight turn is never idle

    // The turn ends (turn_complete lands the machine in listening — a
    // transition, so the idle clock restarts there) and the machine then
    // decays to standby after its own 30s; the dim follows immediately.
    h.rerender('listening')
    h.rerender('standby')
    advance(30_000)
    expect(tierOf(h.veil())).toBe('dim')
  })
})

describe('StandbyController P2 report', () => {
  it('POSTs the idle duration to /api/system/display at each transition', () => {
    mount()
    advance(30_000) // -> tier 1
    advance(570_000) // -> tier 2 (10 minutes total idle)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [first] = fetchMock.mock.calls
    expect(String(first[0])).toContain('/api/system/display')
    expect((first[1] as RequestInit).method).toBe('POST')
    expect(reportBodies()).toEqual([{ idle_seconds: 30 }, { idle_seconds: 600 }])
  })

  it('reports the wake with idle_seconds 0 (the "screen is awake" report)', () => {
    mount()
    advance(30_000)
    act(() => {
      window.dispatchEvent(new Event('pointerdown'))
    })
    expect(reportBodies()).toEqual([{ idle_seconds: 30 }, { idle_seconds: 0 }])
  })

  it('does not report twice for a held tier', () => {
    mount()
    advance(30_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    advance(60_000) // still tier 1
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('a failed report is silent (P2 does not exist yet; 404/network swallowed)', () => {
    fetchMock.mockRejectedValue(new Error('404 not found'))
    mount()
    advance(30_000)
    expect(fetchMock).toHaveBeenCalledTimes(1) // fired, failure swallowed
  })

  it('stops reporting after unmount', () => {
    const { view } = mount()
    view.unmount()
    advance(60_000)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
