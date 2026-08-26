// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * E1f: the agent stream's terminal events must land in the terminal store.
 *
 * This is the wire that was missing — the backend announced terminals and
 * nothing on the frontend listened, so the dock was permanently empty.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { applyTerminalEvent, type StreamEvent } from './useAgentStream'
import { terminalSessionStore as store } from './useTerminalSessions'

function event(type: string, extra: Record<string, unknown> = {}): StreamEvent {
  return { type, session_id: 'turn-1', timestamp: 0, ...extra }
}

describe('applyTerminalEvent', () => {
  beforeEach(() => {
    store.closeAll()
    vi.stubGlobal('WebSocket', class {
      onmessage: unknown = null
      onclose: unknown = null
      onerror: unknown = null
      readyState = 1
      constructor(public url: string) {}
      send() {}
      close() {}
    } as unknown as typeof WebSocket)
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('adopts an SSE-attached spawn and records its origin turn', () => {
    applyTerminalEvent(event('terminal_spawn', {
      terminal_session_id: 'term-1',
      command: 'journalctl -f',
      pid: 1234,
      sandboxed: true,
      cwd: '/var/log',
    }))

    const session = store.get('term-1')!
    expect(session.transport).toBe('sse')
    expect(session.command).toBe('journalctl -f')
    expect(session.pid).toBe(1234)
    expect(session.sandboxed).toBe(true)
    expect(session.cwd).toBe('/var/log')
    expect(session.originSessionId).toBe('turn-1')
  })

  it('attaches a websocket when the backend says the PTY is live', () => {
    applyTerminalEvent(event('terminal_spawn', {
      terminal_session_id: 'pty-1',
      command: 'bash',
      pid: 7,
      attach: 'ws',
    }))

    expect(store.get('pty-1')!.transport).toBe('ws')
  })

  it('streams output and exit into the adopted session', () => {
    applyTerminalEvent(event('terminal_spawn', { terminal_session_id: 't', command: 'ls', pid: 1 }))
    applyTerminalEvent(event('terminal_output', { terminal_session_id: 't', data: 'a' }))
    applyTerminalEvent(event('terminal_output', { terminal_session_id: 't', data: 'b' }))
    applyTerminalEvent(event('terminal_complete', { terminal_session_id: 't', exit_code: 0 }))

    const session = store.get('t')!
    expect(session.output).toBe('ab')
    expect(session.status).toBe('done')
    expect(session.exitCode).toBe(0)
  })

  it('is idempotent for spawns — a replayed event cannot duplicate a session', () => {
    const spawn = event('terminal_spawn', { terminal_session_id: 't', command: 'ls', pid: 1 })
    applyTerminalEvent(spawn)
    applyTerminalEvent(spawn)

    expect(store.getSnapshot()).toHaveLength(1)
  })

  it('defaults a missing exit code to -1', () => {
    applyTerminalEvent(event('terminal_spawn', { terminal_session_id: 't', command: 'ls', pid: 1 }))
    applyTerminalEvent(event('terminal_complete', { terminal_session_id: 't' }))

    expect(store.get('t')!.exitCode).toBe(-1)
  })

  it('ignores events with no terminal id', () => {
    applyTerminalEvent(event('terminal_spawn', { command: 'ls' }))
    expect(store.getSnapshot()).toHaveLength(0)
  })

  it('tolerates output for a session it never saw spawn', () => {
    expect(() =>
      applyTerminalEvent(event('terminal_output', { terminal_session_id: 'ghost', data: 'x' })),
    ).not.toThrow()
    expect(store.getSnapshot()).toHaveLength(0)
  })
})
