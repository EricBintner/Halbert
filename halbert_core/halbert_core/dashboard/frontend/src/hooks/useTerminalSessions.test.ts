// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * E1f: sessions the store did not open itself.
 *
 * The agent spawns terminals mid-turn and announces them over SSE; the store
 * has to hold those alongside PTY sessions it opened over WebSocket, without
 * ever sending a DELETE for a process it does not own.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { terminalSessionStore as store } from './useTerminalSessions'

describe('terminal session store — adopted (SSE) sessions', () => {
  beforeEach(() => {
    store.closeAll()
  })

  afterEach(() => {
    store.closeAll()
  })

  it('adopts a session without opening a socket', () => {
    const wsSpy = vi.fn()
    vi.stubGlobal('WebSocket', wsSpy)

    store.adopt('t1', { command: 'df -h', pid: 42, originSessionId: 's1' })

    expect(wsSpy).not.toHaveBeenCalled()
    const session = store.get('t1')
    expect(session).toBeDefined()
    expect(session!.transport).toBe('sse')
    expect(session!.command).toBe('df -h')
    expect(session!.pid).toBe(42)
    expect(session!.status).toBe('running')
    expect(session!.originSessionId).toBe('s1')

    vi.unstubAllGlobals()
  })

  it('ignores a repeated adopt for the same id', () => {
    store.adopt('t1', { command: 'first' })
    store.appendOutput('t1', 'partial output')
    store.adopt('t1', { command: 'second' })

    expect(store.get('t1')!.command).toBe('first')
    expect(store.get('t1')!.output).toBe('partial output')
  })

  it('appends output in order and completes with the exit code', () => {
    store.adopt('t1', { command: 'echo hi' })
    store.appendOutput('t1', 'hi')
    store.appendOutput('t1', '\r\n')
    store.complete('t1', 0)

    const session = store.get('t1')!
    expect(session.output).toBe('hi\r\n')
    expect(session.status).toBe('done')
    expect(session.exitCode).toBe(0)
  })

  it('ignores output and completion for unknown sessions', () => {
    expect(() => store.appendOutput('ghost', 'x')).not.toThrow()
    expect(() => store.complete('ghost', 1)).not.toThrow()
    expect(store.getSnapshot()).toHaveLength(0)
  })

  it('notifies subscribers on every mutation', () => {
    const listener = vi.fn()
    const unsubscribe = store.subscribe(listener)

    store.adopt('t1', { command: 'ls' })
    store.appendOutput('t1', 'a')
    store.complete('t1', 0)

    expect(listener).toHaveBeenCalledTimes(3)
    expect(store.getSnapshot()).toHaveLength(1)
    unsubscribe()
  })

  it('does not DELETE a backend session it never created', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    store.adopt('t1', { command: 'ls' })
    await store.kill('t1')

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(store.get('t1')).toBeUndefined()

    vi.unstubAllGlobals()
  })

  it('reports adopted sessions as non-interactive', () => {
    store.adopt('t1', { command: 'ls' })
    expect(store.isInteractive('t1')).toBe(false)
  })

  it('clears every session belonging to one agent turn', () => {
    store.adopt('t1', { command: 'a', originSessionId: 'turn-1' })
    store.adopt('t2', { command: 'b', originSessionId: 'turn-1' })
    store.adopt('t3', { command: 'c', originSessionId: 'turn-2' })

    store.clearOrigin('turn-1')

    expect(store.getSnapshot().map((s) => s.id)).toEqual(['t3'])
  })
})

describe('terminal session store — attached (PTY) sessions', () => {
  class FakeSocket {
    static OPEN = 1
    static instances: FakeSocket[] = []
    onmessage: ((ev: { data: string }) => void) | null = null
    onclose: (() => void) | null = null
    onerror: (() => void) | null = null
    readyState = 1
    sent: string[] = []
    constructor(public url: string) {
      FakeSocket.instances.push(this)
    }
    send(data: string) {
      this.sent.push(data)
    }
    close() {}
  }

  beforeEach(() => {
    store.closeAll()
    FakeSocket.instances = []
    vi.stubGlobal('WebSocket', FakeSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    store.closeAll()
    vi.unstubAllGlobals()
  })

  it('opens exactly one socket per attached session', () => {
    store.attach('pty-1', { command: 'htop', pid: 99 })
    store.attach('pty-1', { command: 'htop', pid: 99 })

    expect(FakeSocket.instances).toHaveLength(1)
    expect(FakeSocket.instances[0].url).toContain('/ws/terminal/pty-1')
    expect(store.get('pty-1')!.transport).toBe('ws')
  })

  it('streams stdout and exit from the socket into the session', () => {
    store.attach('pty-1', { command: 'htop', pid: 99 })
    const socket = FakeSocket.instances[0]

    socket.onmessage!({ data: JSON.stringify({ type: 'stdout', data: 'tick' }) })
    socket.onmessage!({ data: JSON.stringify({ type: 'exit', code: 2 }) })

    const session = store.get('pty-1')!
    expect(session.output).toBe('tick')
    expect(session.status).toBe('done')
    expect(session.exitCode).toBe(2)
  })

  it('forwards keystrokes only for PTY-backed sessions', () => {
    store.attach('pty-1', { command: 'bash', pid: 5 })
    store.adopt('sse-1', { command: 'ls', pid: 6 })

    expect(store.isInteractive('pty-1')).toBe(true)
    expect(store.isInteractive('sse-1')).toBe(false)

    store.sendInput('pty-1', 'x')
    store.sendInput('sse-1', 'x')

    expect(FakeSocket.instances[0].sent).toEqual([
      JSON.stringify({ type: 'stdin', data: 'x' }),
    ])
  })
})
