// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * C4 (turn-event tee), first consumer: the voice HUD's dashboard-turn
 * reflection, as a hook contract. The tee publishes a REDUCED set (never
 * the token stream); app.py bridges it onto /ws as `turn_event` frames.
 * Pinned:
 *
 *  - a dashboard turn's lifecycle reflects (started → phase → ended);
 *  - a VOICE turn does not reflect — this page IS the voice surface, and
 *    its own turns already live here in full;
 *  - nothing but `turn_event` frames is consulted;
 *  - the frames carry no content, so there is no content to render.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDashboardTurnReflection } from './useDashboardTurnReflection'

type Frame = Record<string, unknown>

class FakeSocket {
  static opened: FakeSocket[] = []
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  constructor(public url: string) {
    FakeSocket.opened.push(this)
  }
  close() { this.closed = true }
  /** Deliver one /ws frame as the server would. */
  receive(frame: Frame) {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
}

beforeEach(() => {
  FakeSocket.opened = []
  vi.stubGlobal('WebSocket', FakeSocket as unknown as typeof WebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const turnEvent = (data: Frame) => ({ type: 'turn_event', data })

describe('useDashboardTurnReflection — the tee\'s first consumer', () => {
  it('reflects a dashboard turn\'s lifecycle', async () => {
    const { result } = renderHook(() => useDashboardTurnReflection())
    expect(result.current.active).toBe(false)
    expect(result.current.phase).toBeNull()

    const socket = FakeSocket.opened[0]
    expect(socket).toBeDefined()

    act(() => {
      socket.receive(turnEvent({ event: 'turn_started', session_id: 's-1', channel: 'dashboard' }))
    })
    expect(result.current.active).toBe(true)
    expect(result.current.phase).toBe('working')

    act(() => {
      socket.receive(turnEvent({ event: 'state_change', session_id: 's-1', channel: 'dashboard', from: 'planning', to: 'searching' }))
    })
    expect(result.current.phase).toBe('searching')

    act(() => {
      socket.receive(turnEvent({ event: 'turn_ended', session_id: 's-1', channel: 'dashboard' }))
    })
    expect(result.current.active).toBe(false)
    expect(result.current.phase).toBeNull()
  })

  it('never reflects a voice turn — this page is the voice surface', async () => {
    const { result } = renderHook(() => useDashboardTurnReflection())
    const socket = FakeSocket.opened[0]

    act(() => {
      socket.receive(turnEvent({ event: 'turn_started', session_id: 's-1', channel: 'voice' }))
      socket.receive(turnEvent({ event: 'state_change', session_id: 's-1', channel: 'voice', to: 'executing' }))
    })
    expect(result.current.active).toBe(false)
    expect(result.current.phase).toBeNull()
  })

  it('ignores everything that is not a turn_event frame', async () => {
    const { result } = renderHook(() => useDashboardTurnReflection())
    const socket = FakeSocket.opened[0]

    act(() => {
      socket.receive({ type: 'system_status', data: { cpu: 12 } })
      socket.receive({ type: 'approval_request', data: {} })
    })
    expect(result.current.active).toBe(false)
  })

  it('stops listening on unmount', async () => {
    const { unmount } = renderHook(() => useDashboardTurnReflection())
    const socket = FakeSocket.opened[0]
    unmount()
    expect(socket.closed).toBe(true)
  })
})