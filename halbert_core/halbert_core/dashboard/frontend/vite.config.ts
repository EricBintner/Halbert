// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import os from 'os'

/**
 * The dev proxy target.
 *
 * The port was hardcoded to 8000 in six places, which meant a second backend
 * (on a machine where 8000 is already taken, or when running two checkouts at
 * once) could not be reached without editing this file. HALBERT_API_PORT keeps
 * the default behaviour and makes the other case possible.
 */
const API_PORT = process.env.HALBERT_API_PORT ?? '8000'
// 127.0.0.1, not localhost: Node resolves localhost to ::1 (IPv6) first,
// and the backend binds 127.0.0.1 (IPv4) only, so a localhost target makes
// every proxied request fail with a 500 and the chat shows "Idle" instantly.
const HTTP_TARGET = `http://127.0.0.1:${API_PORT}`
const WS_TARGET = `ws://127.0.0.1:${API_PORT}`

/**
 * SEC-1: the dev proxy authenticates as the owner.
 *
 * Every backend route requires a credential. In the Tauri desktop app the Rust
 * shell injects the token into the webview; in a browser the session cookie
 * from /auth/enter does the work. But the Vite dev server is neither — it is a
 * same-machine dev tool that proxies to the sidecar, and without a credential
 * every request comes back 401 and the dashboard is unusable.
 *
 * Reading the token file here is the dev equivalent of what the Tauri shell
 * does: the dev server runs as the owner on the same machine, so it can read
 * the token exactly as the owner's code always can. An explicit env override
 * (HALBERT_API_TOKEN) wins, matching the backend's own load_or_create_token.
 */
function devApiToken(): string | null {
  const env = process.env.HALBERT_API_TOKEN
  if (env) return env
  // Mirror halbert_core/utils/paths.py state_dir() — XDG_STATE_HOME or default.
  const xdgState = process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local', 'state')
  const tokenFile = path.join(xdgState, 'halbert', 'api-token')
  try {
    return fs.readFileSync(tokenFile, 'utf-8').trim() || null
  } catch {
    return null
  }
}

const DEV_TOKEN = devApiToken()

function authHeaders(): Record<string, string> {
  return DEV_TOKEN ? { 'X-Halbert-Token': DEV_TOKEN } : {}
}

function proxyTargets() {
  const http = ['/api', '/auth', '/global', '/llm', '/embedding', '/compute']
  const common = { target: HTTP_TARGET, changeOrigin: true, headers: authHeaders() }
  return {
    ...Object.fromEntries(http.map((prefix) => [prefix, common])),
    '/ws': { target: WS_TARGET, ws: true },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: proxyTargets(),
  },
  // vite preview does not read server.proxy, so the production build could not
  // be previewed against a running backend without this.
  preview: {
    proxy: proxyTargets(),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Only our own tests — node_modules holds plenty of files matching the
    // default include glob.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
