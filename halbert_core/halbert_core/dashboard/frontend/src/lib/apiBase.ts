// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Resolve the backend origin.
 * - Browser / `vite` dev: '' (relative URLs; vite.config.ts proxies /api,/llm,/ws,...).
 * - Tauri webview (origin tauri://localhost): absolute http://127.0.0.1:<port>,
 *   injected synchronously by the Rust 'halbert-env' plugin init script.
 * - Multi-body: setInstanceEndpoint() overrides the base when the Presence Pill
 *   switches to another linked body. The switch reloads the page, so the
 *   override is persisted (localStorage) and hydrated here at module init,
 *   before any fetch runs. A stored override wins over the Tauri-injected
 *   base; with none stored the injected base wins as before.
 */
declare global {
  interface Window {
    __HALBERT_API_BASE__?: string
    __HALBERT_TOKEN__?: string
    __TAURI_INTERNALS__?: unknown
  }
}

export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

/** Where the active-body override lives between page loads. */
const ACTIVE_BODY_KEY = 'halbert:active-body'

function normalizeEndpoint(url: string | null | undefined): string | null {
  return url ? url.replace(/\/$/, '') : null
}

function readStoredEndpoint(): string | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return normalizeEndpoint(localStorage.getItem(ACTIVE_BODY_KEY))
  } catch {
    // private mode / storage disabled — the local body it is
    return null
  }
}

// The active-body override set by the Presence Pill, hydrated at module init
// so the very first fetch after a reload already talks to the switched-to body.
let _instanceOverride: string | null = readStoredEndpoint()

/** Set the active body endpoint (e.g., 'http://localhost:8001'). Pass null to reset to local. */
export function setInstanceEndpoint(url: string | null): void {
  _instanceOverride = normalizeEndpoint(url)
  try {
    if (_instanceOverride) localStorage.setItem(ACTIVE_BODY_KEY, _instanceOverride)
    else localStorage.removeItem(ACTIVE_BODY_KEY)
  } catch {
    // non-fatal: the override still applies for this page load
  }
}

/** Get the current active-body override (or null if using the local body). */
export function getInstanceEndpoint(): string | null {
  return _instanceOverride
}

export function apiBase(): string {
  if (typeof window === 'undefined') return ''
  if (_instanceOverride) return _instanceOverride
  const injected = window.__HALBERT_API_BASE__
  if (injected) return injected.replace(/\/$/, '')
  return isTauri() ? 'http://127.0.0.1:8000' : ''
}

/** Prefix a backend path ('/api/x', '/llm/x', '/ws/x'). */
export function apiUrl(path: string): string {
  return `${apiBase()}${path}`
}

/**
 * The API credential for this session, or null in a plain browser.
 *
 * SEC-1: every backend route now requires one. In the Tauri webview the Rust
 * shell injects it alongside the API base, because the webview is cross-origin
 * to its own sidecar and so can never be given a cookie. In a browser there is
 * no token here at all — the session cookie set by /auth/enter does the work,
 * and it rides along automatically on same-origin requests.
 */
export function apiToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.__HALBERT_TOKEN__ || null
}

/** Credential headers for a backend request, or an empty object in a browser. */
export function authHeaders(): Record<string, string> {
  const token = apiToken()
  return token ? { 'X-Halbert-Token': token } : {}
}

/**
 * Attach the credential to every backend request, once, at startup.
 *
 * Call sites reach the backend three ways — the `api` client, bare
 * `fetch(apiUrl(...))`, and EventSource — and threading a header through all of
 * them by hand is exactly the kind of change that gets 95% done. Wrapping fetch
 * puts it in one place that cannot be forgotten.
 *
 * Only requests to our own backend are touched: a model provider or any other
 * third party must never receive this header.
 */
export function installAuthFetch(): void {
  if (typeof window === 'undefined' || !window.fetch) return
  const token = apiToken()
  if (!token) return // browser: the session cookie carries it

  const original = window.fetch.bind(window)
  const base = apiBase()

  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const ours = base ? url.startsWith(base) : url.startsWith('/')
    if (!ours) return original(input, init)

    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
    if (!headers.has('X-Halbert-Token')) headers.set('X-Halbert-Token', token)
    return original(input, { ...init, headers })
  }
}

/** ws(s):// URL for a backend WebSocket path such as '/ws/terminal/<id>'. */
export function wsUrl(path: string): string {
  // A browser cannot set a header on a WebSocket handshake, so the credential
  // goes in the query string — the one place the door accepts it there.
  const token = apiToken()
  const withToken = token
    ? `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
    : path
  const base = apiBase()
  if (base) return base.replace(/^http/, 'ws') + withToken
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${withToken}`
}
