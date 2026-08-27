// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A fallback is said out loud, once, when the server says it happened.
 *
 * "The model you pinned answered" and "something else answered instead" must
 * never look alike — and for someone who is not looking at the screen, must
 * never sound alike either. The visual notice (TurnModelNotice) cannot be the
 * thing that speaks it: AgentChat mounts that component twice over one turn,
 * so it would say the sentence twice. `model_selected` arrives once.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
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

describe('useAgentStream — a fallback is announced', () => {
  let said: string[]
  let stop: () => void

  beforeEach(() => {
    said = []
    stop = subscribeAnnouncements((text) => said.push(text))
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    stop()
    vi.unstubAllGlobals()
  })

  it('names both models, once, when the turn fell back', async () => {
    streamFetch([
      ev('model_selected', {
        model: 'answered-here', endpoint: 'http://localhost:11434', provider: 'ollama',
        tier: 'guide', pinned: true, escalated: false, reason: '',
        fallback_from: 'asked-for-this',
      }),
      ev('response_chunk', { content: 'Hello' }),
      ev('response_complete', { content: 'Hello' }),
    ])
    const { result } = renderHook(() => useAgentStream())
    await act(async () => { await result.current.sendMessage('hi') })

    await waitFor(() =>
      expect(said).toContain('asked-for-this was unavailable. answered-here answered instead.'),
    )
    expect(
      said.filter((s) => s.includes('was unavailable')),
    ).toHaveLength(1)
  })

  it('says nothing when the turn ran on the model it was meant to', async () => {
    streamFetch([
      ev('model_selected', {
        model: 'answered-here', endpoint: 'http://localhost:11434', provider: 'ollama',
        tier: 'guide', pinned: true, escalated: false, reason: '',
      }),
      ev('response_complete', { content: 'Hello' }),
    ])
    const { result } = renderHook(() => useAgentStream())
    await act(async () => { await result.current.sendMessage('hi') })

    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    // The turn still reported which model answered — it just had nothing
    // unusual to say about it.
    expect(result.current.turnModel?.model).toBe('answered-here')
    expect(said.filter((s) => s.includes('was unavailable'))).toHaveLength(0)
  })
})
