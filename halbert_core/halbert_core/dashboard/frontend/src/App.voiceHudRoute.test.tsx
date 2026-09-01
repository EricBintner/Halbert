// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * App — the /voice-hud route registration (P4).
 *
 * The Rust `show_voice_hud` command (src-tauri/src/floating_panel.rs) loads
 * this same SPA into a second, borderless transparent webview at the
 * `voice-hud` path. Here only the wiring is under test: the route exists,
 * it renders inside the shell wrapper (whose HUD full-bleed exception
 * drops the shell chrome), and it never leaks onto other routes.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/pages/VoiceHud', () => ({
  VoiceHud: () => <div data-testid="voice-hud-page" />,
}))

import App from './App'

function stubAppFetches() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          // Onboarding check: complete, no startup scan.
          onboarding_complete: true,
          has_system_profile: false,
          role: 'standalone',
          features: { home: true },
          enabled: false,
          indexing: { is_running: false },
          is_running: false,
          display_name: 'Macky-Mac',
          hostname: 'Erics-Mac-Studio.local',
          os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
          storage: { pools: [], healthy: 0, total: 0 },
          cpu: { cores: 4, percent: 1, temperature: null },
          memory: { total_gb: 16, used_gb: 8, percent: 50 },
          uptime: { seconds: 60, human: 'a minute', boot_time: '' },
          load_average: { '1min': 1, '5min': 1, '15min': 1 },
          all_healthy: true,
          first_person: 'I am Macky-Mac.',
          timestamp: '',
        }),
      }),
    ),
  )
}

async function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  render(<App />)
  await screen.findByTestId('app-shell')
}

describe('App /voice-hud route', () => {
  beforeEach(() => {
    localStorage.clear()
    stubAppFetches()
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal(
      'EventSource',
      class FakeEventSource {
        onmessage: ((e: { data: string }) => void) | null = null
        onerror: (() => void) | null = null
        constructor(_url: string) {}
        addEventListener() {}
        close() {}
      },
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.replaceState({}, '', '/')
    localStorage.clear()
  })

  it('mounts the voice HUD page at /voice-hud inside the shell wrapper', async () => {
    await renderAppAt('/voice-hud')

    expect(screen.getByTestId('voice-hud-page')).toBeInTheDocument()
    expect(screen.getByTestId('app-shell')).toBeInTheDocument()
  })

  it('does not mount the voice HUD page at other routes', async () => {
    await renderAppAt('/')

    expect(screen.queryByTestId('voice-hud-page')).not.toBeInTheDocument()
  })
})
