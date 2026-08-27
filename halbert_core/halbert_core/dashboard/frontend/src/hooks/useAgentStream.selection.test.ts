// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-2/E-2: the per-turn model pin has to reach the wire.
 *
 * Everything behind this — SendMessageRequest.model, StateContext.model_override,
 * _resolve_turn_model bypassing the complexity router — was built and tested,
 * and was unreachable because nothing ever put a model in the request body.
 * These assert the body itself.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAgentStream, type ModelSelection } from './useAgentStream'

function sseResponse() {
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => ({ done: true, value: undefined }),
        releaseLock: () => {},
      }),
    },
  } as unknown as Response
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(async () => sseResponse())
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function sentBody(): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(([url]) =>
    String(url).includes('/api/agent/message'),
  )
  if (!call) throw new Error('no send-message request was made')
  return JSON.parse(String((call[1] as RequestInit).body))
}

async function send(selection?: ModelSelection) {
  const { result } = renderHook(() => useAgentStream())
  await act(async () => {
    result.current.sendMessage('hello', 'session-1', selection)
  })
  return sentBody()
}

describe('sendMessage model selection', () => {
  it('sends no model or tier when nothing is pinned', async () => {
    const body = await send()
    expect(body).not.toHaveProperty('model')
    expect(body).not.toHaveProperty('tier')
    expect(body).not.toHaveProperty('endpoint_id')
  })

  it('carries a pinned model', async () => {
    const body = await send({ model: 'model-b' })
    expect(body.model).toBe('model-b')
  })

  it('carries the endpoint the model came from, so an ambiguous name resolves', async () => {
    const body = await send({ model: 'model-b', endpointId: 'ep1' })
    expect(body.endpoint_id).toBe('ep1')
  })

  it('carries a pinned tier', async () => {
    const body = await send({ tier: 'specialist' })
    expect(body.tier).toBe('specialist')
  })

  it("omits tier 'auto' entirely, because it is the absence of a pin", async () => {
    // Sending it would make the backend treat "let the router decide" as an
    // explicit instruction, which is a different thing.
    const body = await send({ tier: 'auto' })
    expect(body).not.toHaveProperty('tier')
  })

  it('still carries the performance tweaks alongside a pin', async () => {
    const body = await send({ model: 'model-b' })
    expect(body).toHaveProperty('max_tokens')
    expect(body).toHaveProperty('temperature')
    expect(body.message).toBe('hello')
  })
})


describe('conversation continuity', () => {
  async function sendTwice() {
    const { result } = renderHook(() => useAgentStream())
    await act(async () => { result.current.sendMessage('first') })
    await act(async () => { result.current.sendMessage('second') })
    const bodies = fetchMock.mock.calls
      .filter(([url]) => String(url).includes('/api/agent/message'))
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)))
    return { result, bodies }
  }

  it('keeps one session id across consecutive sends', async () => {
    // Every send used to mint a fresh id, so the backend keyed each turn on a
    // different conversation and loaded an empty history — the agent could not
    // remember the previous message however well the backend was wired.
    const { bodies } = await sendTwice()
    expect(bodies).toHaveLength(2)
    expect(bodies[0].session_id).toBe(bodies[1].session_id)
  })

  it('sends conversation_id alongside session_id so the two cannot drift', async () => {
    const { bodies } = await sendTwice()
    expect(bodies[0].conversation_id).toBe(bodies[0].session_id)
  })

  it('starts a new conversation after reset', async () => {
    const { result, bodies } = await sendTwice()
    await act(async () => { result.current.reset() })
    await act(async () => { result.current.sendMessage('third') })
    const all = fetchMock.mock.calls
      .filter(([url]) => String(url).includes('/api/agent/message'))
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)))
    expect(all[2].session_id).not.toBe(bodies[0].session_id)
  })

  it('continues an explicitly named conversation', async () => {
    const { result } = renderHook(() => useAgentStream())
    await act(async () => { result.current.sendMessage('first', 'conv-42') })
    await act(async () => { result.current.sendMessage('second') })
    const bodies = fetchMock.mock.calls
      .filter(([url]) => String(url).includes('/api/agent/message'))
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)))
    expect(bodies[0].session_id).toBe('conv-42')
    expect(bodies[1].session_id).toBe('conv-42')
  })
})
