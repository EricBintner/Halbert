// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * R11-03: the setSession updater must be a pure function of the previous
 * state.
 *
 * React calls updaters twice under StrictMode to surface exactly this. A
 * dozen side effects lived inside this one — announce(), setTurnModel,
 * setProvenance, setResponse, setIsStreaming, setModuleInvocations and the
 * five `options.on*` callbacks — so in development the module list gained a
 * duplicate entry on every invoke and the fallback sentence was said twice.
 * They now run in a switch before the updater, where the double call cannot
 * reach them.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { StrictMode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { useAgentStream } from './useAgentStream'
import { subscribeAnnouncements } from '../lib/announce'

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
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
    String(url).includes('/api/agent/message')
      ? Promise.resolve({ ok: true, status: 200, statusText: 'OK', body: sseBody(events) })
      : Promise.resolve({ ok: true, status: 200, statusText: 'OK', json: async () => ({}) }),
  ))
}

const ev = (type: string, extra: Record<string, unknown> = {}) => ({
  type, session_id: 'turn-1', timestamp: 0, ...extra,
})

describe('useAgentStream under StrictMode — the updater stays pure', () => {
  let said: string[]
  let stop: () => void

  beforeEach(() => {
    said = []
    stop = subscribeAnnouncements((text) => said.push(text))
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    stop()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('records one module invocation per module_invoke event', async () => {
    streamFetch([
      ev('session_started'),
      ev('module_invoke', { module: 'DiskUsageChart', props: { pool: 'tank' } }),
      ev('response_complete', { response: 'here is the disk usage' }),
      ev('session_ended'),
    ])

    const { result } = renderHook(() => useAgentStream(), { wrapper: StrictMode })
    result.current.sendMessage('show me disk usage')

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.moduleInvocations).toHaveLength(1)
    expect(result.current.moduleInvocations[0].module).toBe('DiskUsageChart')
  })

  it('announces a fallback once, not once per updater call', async () => {
    streamFetch([
      ev('session_started'),
      ev('model_selected', {
        model: 'answered-here',
        endpoint: 'http://localhost:11434',
        provider: 'ollama',
        tier: 'guide',
        fallback_from: 'the-pinned-one',
      }),
      ev('response_complete', { response: 'done' }),
      ev('session_ended'),
    ])

    const { result } = renderHook(() => useAgentStream(), { wrapper: StrictMode })
    result.current.sendMessage('anything')

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    const fallbacks = said.filter((s) => s.includes('was unavailable'))
    expect(fallbacks).toHaveLength(1)
  })

  it('fires each lifecycle callback once per event', async () => {
    streamFetch([
      ev('session_started'),
      ev('tool_start', { execution_id: 'x1', tool: 'run_command', args: { command: 'ls' } }),
      ev('tool_complete', { execution_id: 'x1', success: true, result: 'ok' }),
      ev('response_complete', { response: 'listed' }),
      ev('session_ended'),
    ])

    const onToolStart = vi.fn()
    const onToolComplete = vi.fn()
    const onComplete = vi.fn()

    const { result } = renderHook(
      () => useAgentStream({ onToolStart, onToolComplete, onComplete }),
      { wrapper: StrictMode },
    )
    result.current.sendMessage('list the directory')

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(onToolStart).toHaveBeenCalledTimes(1)
    expect(onToolComplete).toHaveBeenCalledTimes(1)
    // response_complete and session_ended each complete the turn.
    expect(onComplete).toHaveBeenCalledTimes(2)
  })
})
