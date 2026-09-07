// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * SEC-1: the credential the frontend presents.
 *
 * Every backend route now requires one. In the Tauri webview the Rust shell
 * injects it; in a browser there is none here at all and the session cookie
 * from /auth/enter does the work instead. The case worth guarding hardest is
 * the last one in this file: the credential must never reach a third party.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiToken, authHeaders, installAuthFetch, wsUrl } from './apiBase'

describe('the API credential', () => {
  beforeEach(() => {
    delete window.__HALBERT_TOKEN__
    delete window.__HALBERT_API_BASE__
  })

  it('is null in a plain browser, where the session cookie does the work', () => {
    expect(apiToken()).toBeNull()
    expect(authHeaders()).toEqual({})
  })

  it('is whatever the Tauri shell injected', () => {
    window.__HALBERT_TOKEN__ = 'injected-token'
    expect(apiToken()).toBe('injected-token')
    expect(authHeaders()).toEqual({ 'X-Halbert-Token': 'injected-token' })
  })

  it('rides in the query string on a WebSocket, which cannot carry a header', () => {
    window.__HALBERT_TOKEN__ = 'tok en/+'
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    expect(wsUrl('/ws/terminal/abc')).toBe(
      'ws://127.0.0.1:8042/ws/terminal/abc?token=tok%20en%2F%2B',
    )
  })

  it('appends with & when the path already carries a query', () => {
    window.__HALBERT_TOKEN__ = 't'
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    expect(wsUrl('/api/audio/tts?session_id=x')).toBe(
      'ws://127.0.0.1:8042/api/audio/tts?session_id=x&token=t',
    )
  })

  it('leaves the WebSocket URL alone when there is no token', () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    expect(wsUrl('/ws')).toBe('ws://127.0.0.1:8042/ws')
  })
})

describe('installAuthFetch', () => {
  const realFetch = window.fetch

  afterEach(() => {
    window.fetch = realFetch
    delete window.__HALBERT_TOKEN__
    delete window.__HALBERT_API_BASE__
  })

  it('leaves fetch alone in a browser, so it does not compete with the cookie', () => {
    const spy = vi.fn(
      (_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response('{}')),
    )
    window.fetch = spy as unknown as typeof fetch
    installAuthFetch()
    expect(window.fetch).toBe(spy)
  })

  it('adds the credential to backend requests', async () => {
    window.__HALBERT_TOKEN__ = 'secret'
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const spy = vi.fn(
      (_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response('{}')),
    )
    window.fetch = spy as unknown as typeof fetch
    installAuthFetch()

    await window.fetch('http://127.0.0.1:8042/api/findings')
    const init = spy.mock.calls[0][1]
    expect(new Headers(init?.headers).get('X-Halbert-Token')).toBe('secret')
  })

  it('never sends the credential to a third party', async () => {
    window.__HALBERT_TOKEN__ = 'secret'
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const spy = vi.fn(
      (_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response('{}')),
    )
    window.fetch = spy as unknown as typeof fetch
    installAuthFetch()

    await window.fetch('https://api.example.com/v1/models')
    const init = spy.mock.calls[0][1]
    const sent = init?.headers ? new Headers(init.headers).get('X-Halbert-Token') : null
    expect(sent).toBeFalsy()
  })
})
