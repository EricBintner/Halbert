// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * apiBase() decides which origin every fetch in the app talks to. Getting it
 * wrong inside the Tauri webview means every request goes to tauri://localhost
 * and the whole UI is blank, which is exactly what happened before the
 * halbert-env init script existed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiBase, apiUrl, isTauri, wsUrl } from './apiBase'

const ACTIVE_BODY_KEY = 'halbert:active-body'

const clean = () => {
  delete window.__HALBERT_API_BASE__
  delete (window as any).__TAURI_INTERNALS__
  localStorage.removeItem(ACTIVE_BODY_KEY)
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

/**
 * The Presence Pill switches bodies by setting the endpoint override and
 * reloading the page (shell review §9.5, short-term implementation). A
 * module variable does not survive that reload, so the switch was a no-op:
 * every fetch after the reload went back to the local body. The override
 * is persisted and hydrated at module init, before any fetch can run.
 */
describe('instance endpoint persistence', () => {
  // Each test imports a fresh module instance, the way a reload does.
  const freshModule = async () => {
    vi.resetModules()
    return import('./apiBase')
  }

  beforeEach(() => {
    localStorage.removeItem(ACTIVE_BODY_KEY)
  })

  it('setInstanceEndpoint survives a re-import (page reload)', async () => {
    const before = await freshModule()
    before.setInstanceEndpoint('http://x:8001')

    const after = await freshModule()
    expect(after.getInstanceEndpoint()).toBe('http://x:8001')
    expect(after.apiBase()).toBe('http://x:8001')
    expect(after.apiUrl('/api/instance/info')).toBe('http://x:8001/api/instance/info')
  })

  it('strips a trailing slash before storing', async () => {
    const before = await freshModule()
    before.setInstanceEndpoint('http://x:8001/')

    const after = await freshModule()
    expect(after.getInstanceEndpoint()).toBe('http://x:8001')
  })

  it('clearing the override restores the local body across a reload', async () => {
    const before = await freshModule()
    before.setInstanceEndpoint('http://x:8001')
    before.setInstanceEndpoint(null)

    const after = await freshModule()
    expect(after.getInstanceEndpoint()).toBeNull()
    expect(after.apiBase()).toBe('')
    expect(localStorage.getItem(ACTIVE_BODY_KEY)).toBeNull()
  })

  it('a stored override wins over the Tauri-injected base', async () => {
    const before = await freshModule()
    before.setInstanceEndpoint('http://x:8001')

    ;(window as any).__TAURI_INTERNALS__ = {}
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const after = await freshModule()
    expect(after.apiBase()).toBe('http://x:8001')
  })

  it('the Tauri-injected base wins only when no override is stored', async () => {
    ;(window as any).__TAURI_INTERNALS__ = {}
    window.__HALBERT_API_BASE__ = 'http://127.0.0.1:8042'
    const mod = await freshModule()
    expect(mod.getInstanceEndpoint()).toBeNull()
    expect(mod.apiBase()).toBe('http://127.0.0.1:8042')
  })

  it('still applies the override for the session when storage is unavailable', async () => {
    const mod = await freshModule()
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    try {
      expect(() => mod.setInstanceEndpoint('http://x:8001')).not.toThrow()
      expect(mod.apiBase()).toBe('http://x:8001')
    } finally {
      setItem.mockRestore()
    }
  })
})
