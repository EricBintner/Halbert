// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/global': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/llm': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/embedding': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/compute': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
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
