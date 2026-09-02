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

/** ws(s):// URL for a backend WebSocket path such as '/ws/terminal/<id>'. */
export function wsUrl(path: string): string {
  const base = apiBase()
  if (base) return base.replace(/^http/, 'ws') + path
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}
