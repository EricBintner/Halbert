// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A tool card finds its terminal block.
 *
 * ToolExecutionCard has rendered its block — the one-line result for a fast
 * command, the live tile for a slow one, the frozen output when it ends —
 * since it was written, and every branch is gated on a `blockId` prop that
 * no caller passed. Its own unit tests supply the prop as a literal, so the
 * whole surface was green in CI and unreachable in the product.
 *
 * This is the wire. The backend stamps the running tool call's execution id
 * onto its block events; the hook uses it to put the block on the execution,
 * so the card is handed one by the app and not only by a test.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useAgentStream } from './useAgentStream'
import { terminalSessionStore as store } from './useTerminalSessions'

function sseBody(events: Array<Record<string, unknown>>) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n`).join('')
  const chunks = [new TextEncoder().encode(text)]
  return {
    getReader: () => ({
      read: async () => {
        const value = chunks.shift()
        return value ? { done: false, value } : { done: true, value: undefined }
      },
    }),
  }
}

function streamFetch(events: Array<Record<string, unknown>>) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes('/api/agent/message')) {
      return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
    }
    return Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type,
  session_id: 'turn-1',
  timestamp: 0,
  ...extra,
})

describe('useAgentStream — a tool execution carries its block', () => {
  beforeEach(() => {
    store.closeAll()
    vi.spyOn(console, 'log').mockImplementation(() => {})
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
    vi.restoreAllMocks()
  })

  it('puts the block id on the execution that ran it', async () => {
    streamFetch([
      ev('tool_start', { tool: 'run_command', args: { command: 'smbstatus' }, execution_id: 'exec-1' }),
      ev('terminal_spawn', {
        terminal_session_id: 'term-1', command: 'smbstatus', pid: 10, attach: 'ws',
        block_id: 'blk-1', owner: 'agent',
      }),
      ev('terminal_block', {
        terminal_session_id: 'term-1', block_id: 'blk-1', command: 'smbstatus',
        owner: 'agent', execution_id: 'exec-1',
      }),
      ev('response_complete', { content: 'two shares are up' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('check the shares', 'turn-1') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    expect(result.current.session!.toolExecutions).toHaveLength(1)
    expect(result.current.session!.toolExecutions[0].blockId).toBe('blk-1')
    expect(result.current.session!.toolExecutions[0].terminalSessionId).toBe('term-1')
  })

  it('leaves an execution alone when the block names a different one', async () => {
    streamFetch([
      ev('tool_start', { tool: 'run_command', args: { command: 'ls' }, execution_id: 'exec-1' }),
      ev('tool_start', { tool: 'run_command', args: { command: 'df' }, execution_id: 'exec-2' }),
      ev('terminal_block', {
        terminal_session_id: 'term-1', block_id: 'blk-2', command: 'df',
        owner: 'agent', execution_id: 'exec-2',
      }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('two commands', 'turn-1') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    expect(result.current.session!.toolExecutions).toHaveLength(2)
    // Two run_command calls in one turn is exactly the case a command-string
    // or tool-name match gets wrong.
    expect(result.current.session!.toolExecutions[0].blockId).toBeUndefined()
    expect(result.current.session!.toolExecutions[1].blockId).toBe('blk-2')
  })

  it('ignores a block with no execution id rather than guessing', async () => {
    streamFetch([
      ev('tool_start', { tool: 'run_command', args: { command: 'ls' }, execution_id: 'exec-1' }),
      // A watched user shell block: real, but not this turn's tool call.
      ev('terminal_block', {
        terminal_session_id: 'term-9', block_id: 'blk-9', command: 'vim', owner: 'user',
      }),
      ev('response_complete', { content: 'hi' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('hello', 'turn-1') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    expect(result.current.session!.toolExecutions).toHaveLength(1)
    expect(result.current.session!.toolExecutions[0].blockId).toBeUndefined()
  })
})

describe('useAgentStream — a finished block reports its result', () => {
  beforeEach(() => {
    store.closeAll()
    vi.spyOn(console, 'log').mockImplementation(() => {})
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
    vi.restoreAllMocks()
  })

  it('puts exit code, duration and the block’s own output on the execution', async () => {
    streamFetch([
      ev('tool_start', { tool: 'run_command', args: { command: 'smbstatus' }, execution_id: 'exec-1' }),
      ev('terminal_block', {
        terminal_session_id: 'term-1', block_id: 'blk-1', command: 'smbstatus',
        owner: 'agent', execution_id: 'exec-1',
      }),
      ev('terminal_complete', {
        terminal_session_id: 'term-1', block_id: 'blk-1', exit_code: 1,
        duration: 0.34, output_head: 'no shares', output_tail: 'no shares',
      }),
      ev('response_complete', { content: 'nothing is shared' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('check the shares', 'turn-1') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    const exec = result.current.session!.toolExecutions[0]
    expect(exec.blockExitCode).toBe(1)
    expect(exec.blockDuration).toBe(0.34)
    expect(exec.blockOutputHead).toBe('no shares')
    expect(exec.blockOutputTail).toBe('no shares')
  })

  it('matches the completion to the execution by block id, not by position', async () => {
    streamFetch([
      ev('tool_start', { tool: 'run_command', args: { command: 'sleep 5' }, execution_id: 'exec-1' }),
      ev('tool_start', { tool: 'run_command', args: { command: 'ls' }, execution_id: 'exec-2' }),
      ev('terminal_block', {
        terminal_session_id: 'term-1', block_id: 'blk-1', command: 'sleep 5',
        owner: 'agent', execution_id: 'exec-1',
      }),
      ev('terminal_block', {
        terminal_session_id: 'term-2', block_id: 'blk-2', command: 'ls',
        owner: 'agent', execution_id: 'exec-2',
      }),
      // The short one finishes first — out of start order, which is exactly
      // the case a positional or name-based match gets wrong.
      ev('terminal_complete', {
        terminal_session_id: 'term-2', block_id: 'blk-2', exit_code: 0,
        duration: 0.02, output_head: 'a  b', output_tail: 'a  b',
      }),
      ev('response_complete', { content: 'done' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('two commands', 'turn-1') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    const [first, second] = result.current.session!.toolExecutions
    expect(first.blockExitCode).toBeUndefined()
    expect(second.blockExitCode).toBe(0)
    expect(second.blockOutputHead).toBe('a  b')
  })

  it('ignores a completion for a block no execution owns', async () => {
    streamFetch([
      ev('tool_start', { tool: 'run_command', args: { command: 'ls' }, execution_id: 'exec-1' }),
      // A watched user shell block completing mid-turn.
      ev('terminal_complete', {
        terminal_session_id: 'term-9', block_id: 'blk-9', exit_code: 0, duration: 9,
      }),
      ev('response_complete', { content: 'hi' }),
    ])

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('hello', 'turn-1') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))

    expect(result.current.session!.toolExecutions[0].blockDuration).toBeUndefined()
  })
})
