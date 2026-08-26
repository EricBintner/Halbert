// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * The dev proxy target.
 *
 * The port was hardcoded to 8000 in six places, which meant a second backend
 * (on a machine where 8000 is already taken, or when running two checkouts at
 * once) could not be reached without editing this file. HALBERT_API_PORT keeps
 * the default behaviour and makes the other case possible.
 */
const MODEL_PICKER_SRC = path.resolve(
  __dirname,
  '../../../../packages/model-picker/src',
)

const API_PORT = process.env.HALBERT_API_PORT ?? '8000'
const HTTP_TARGET = `http://localhost:${API_PORT}`
const WS_TARGET = `ws://localhost:${API_PORT}`

function proxyTargets() {
  const http = ['/api', '/global', '/llm', '/embedding', '/compute']
  return {
    ...Object.fromEntries(
      http.map((prefix) => [prefix, { target: HTTP_TARGET, changeOrigin: true }]),
    ),
    '/ws': { target: WS_TARGET, ws: true },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Consumed from source rather than a built artifact: there is no npm
      // workspace in this repo, and the package is TypeScript with react as a
      // peer dependency, so vite transpiles it alongside the app.
      '@halbert/model-picker': MODEL_PICKER_SRC,
    },
  },
  server: {
    proxy: proxyTargets(),
    // The dev server refuses to serve files outside its root, which would make
    // the aliased package 403 on every import.
    fs: { allow: ['..', MODEL_PICKER_SRC] },
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
