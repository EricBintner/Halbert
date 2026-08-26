/**
 * Resolve the backend origin.
 * - Browser / `vite` dev: '' (relative URLs; vite.config.ts proxies /api,/llm,/ws,...).
 * - Tauri webview (origin tauri://localhost): absolute http://127.0.0.1:<port>,
 *   injected synchronously by the Rust 'halbert-env' plugin init script.
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

export function apiBase(): string {
  if (typeof window === 'undefined') return ''
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
