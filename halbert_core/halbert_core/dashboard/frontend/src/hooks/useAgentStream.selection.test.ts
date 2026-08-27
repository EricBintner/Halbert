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
import { renderHook, act, waitFor } from '@testing-library/react'
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


/**
 * Continuity is the server's job now, not the client's (Plan A).
 *
 * The stable session id and the `conversation_id` beside it were an interim
 * client-side fix for an agent that could not remember the previous message.
 * The server resolves the subject thread itself (ThreadManager) and reports
 * what it chose (thread_started / turn_persisted), so there is no conversation
 * left for the client to name — and naming one is worse than useless. The
 * reader it was written for is gone (tests/test_legacy_conversations_removed.py
 * keeps get_conversation_store deleted), and a stable id actively corrupts the
 * transcript: lib/turnFromSession falls back to `local-${sessionId}` for any
 * turn the server never persisted, so two turns sharing an id collide there.
 *
 * A session id names ONE TURN.
 */
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

  it('gives each send its own session id, because a session names one turn', async () => {
    // Not an oversight and not the old bug returning: the server threads the
    // turns together, and the timeline derives a turn's fallback id from the
    // session id, so two turns sharing one would overwrite each other in the
    // transcript instead of appending.
    const { bodies } = await sendTwice()
    expect(bodies).toHaveLength(2)
    expect(bodies[0].session_id).not.toBe(bodies[1].session_id)
  })

  it('sends no conversation_id: the server chooses the thread', async () => {
    // Nothing reads it any more — test_legacy_conversations_removed.py keeps
    // the conversation store deleted, so a client-supplied id has no reader.
    const { bodies } = await sendTwice()
    expect(bodies[0]).not.toHaveProperty('conversation_id')
  })

  it('honours an explicit session id for the turn it names', async () => {
    // The parameter is still live — it names the one turn being sent, which is
    // what confirm/cancel and the terminal tiles key on.
    const { result } = renderHook(() => useAgentStream())
    await act(async () => { result.current.sendMessage('first', 'conv-42') })
    const bodies = fetchMock.mock.calls
      .filter(([url]) => String(url).includes('/api/agent/message'))
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)))
    expect(bodies[0].session_id).toBe('conv-42')
  })

  it('reset() clears the live turn, not the conversation', async () => {
    // There is no "New Conversation" any more, so reset means only: drop the
    // turn on screen and the model that answered it. The terminal half of this
    // — that the tiles survive a reset — is held by
    // useAgentStream.thread.test.ts ('never forgets the terminals a turn
    // opened'), which owns the store.
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (!String(url).includes('/api/agent/message')) {
        return { ok: true, status: 200, statusText: 'OK', json: async () => ({}) } as unknown as Response
      }
      const text = [
        { type: 'model_selected', session_id: 's', timestamp: 0, model: 'model-b', endpoint: 'local', provider: 'p', tier: 'specialist', pinned: true, escalated: false, reason: '' },
        { type: 'response_complete', session_id: 's', timestamp: 0, content: 'done' },
      ].map((e) => `data: ${JSON.stringify(e)}\n`).join('')
      const chunks = [new TextEncoder().encode(text)]
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        body: { getReader: () => ({ read: async () => {
          const value = chunks.shift()
          return value ? { done: false, value } : { done: true, value: undefined }
        } }) },
      } as unknown as Response
    }))

    const { result } = renderHook(() => useAgentStream())
    act(() => { result.current.sendMessage('hello') })
    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.session).not.toBeNull()
    expect(result.current.turnModel?.model).toBe('model-b')

    act(() => { result.current.reset() })

    expect(result.current.session).toBeNull()
    expect(result.current.turnModel).toBeNull()
    expect(result.current.response).toBe('')
  })
})
