// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * apiBase() decides which origin every fetch in the app talks to. Getting it
 * wrong inside the Tauri webview means every request goes to tauri://localhost
 * and the whole UI is blank, which is exactly what happened before the
 * halbert-env init script existed.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { apiBase, apiUrl, isTauri, wsUrl } from './apiBase'

const clean = () => {
  delete window.__HALBERT_API_BASE__
  delete (window as any).__TAURI_INTERNALS__
}

afterEach(clean)

describe('isTauri', () => {
  it('is false in a plain browser', () => {
    expect(isTauri()).toBe(false)
  })

  it('is true when Tauri injected its internals', () => {
    ;(window as any).__TAURI_INTERNALS__ = {}
    expect(isTauri()).toBe(true)
  })
})

describe('apiBase', () => {
  it('is relative in the browser so vite can proxy', () => {
    expect(apiBase()).toBe('')
  })

  it('uses the injected base when Rust provided one', () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    expect(apiBase()).toBe('http://127.0.0.1:8042')
  })

  it('strips a trailing slash so callers can concatenate paths', () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042/'
    expect(apiBase()).toBe('http://127.0.0.1:8042')
    expect(apiUrl('/api/x')).toBe('http://127.0.0.1:8042/api/x')
  })

  it('falls back to an absolute localhost URL inside Tauri', () => {
    // Only reachable if the init script did not run; a relative URL there
    // would resolve against tauri://localhost and fail outright.
    ;(window as any).__TAURI_INTERNALS__ = {}
    expect(apiBase()).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/)
  })

  it('prefers the injected base over the Tauri fallback', () => {
    ;(window as any).__TAURI_INTERNALS__ = {}
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8099'
    expect(apiBase()).toBe('http://127.0.0.1:8099')
  })
})

describe('wsUrl', () => {
  it('derives ws:// from an injected http base', () => {
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    expect(wsUrl('/ws/terminal/1')).toBe('ws://127.0.0.1:8042/ws/terminal/1')
  })

  it('uses the page host when there is no injected base', () => {
    expect(wsUrl('/ws/terminal/1')).toBe(
      `ws://${window.location.host}/ws/terminal/1`,
    )
  })
})
