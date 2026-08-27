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
