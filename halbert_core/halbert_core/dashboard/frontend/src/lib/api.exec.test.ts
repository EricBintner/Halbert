// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Ruling B (2026-09-16): /exec asks on a HIGH verdict with a 428.
 *
 * `request()` used to flatten every non-2xx into one Error string, which
 * made a 428 indistinguishable from a 500 to the caller that has to render
 * the ask. The rejection now carries the status and the parsed detail, and
 * `executeCommand` can carry `force` back once a person has confirmed.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { api } from './api'

const detail = {
  requires_confirmation: true,
  risk_level: 'high',
  reason: 'Unrecognised command: not on the read-only list',
  confirmation_message: '**Execute command:**\n```\nhostname evil\n```',
}

afterEach(() => vi.unstubAllGlobals())

describe('api.executeCommand — the ask', () => {
  it('rejects a 428 with the status and the parsed detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail }), { status: 428 })))
    await expect(api.executeCommand('hostname evil')).rejects.toMatchObject({
      status: 428,
      detail: { requires_confirmation: true, risk_level: 'high' },
    })
  })

  it('carries force through to the request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ output: '', error: '', exit_code: 0, command: 'x' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.executeCommand('hostname evil', { force: true })
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(body.force).toBe(true)
  })

  it('still rejects an ordinary failure as an Error with a message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))
    await expect(api.executeCommand('ls')).rejects.toBeInstanceOf(Error)
  })
})
