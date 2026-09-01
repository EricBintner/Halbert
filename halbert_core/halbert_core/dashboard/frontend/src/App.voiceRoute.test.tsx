// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * App — the /voice route registration (O8).
 *
 * The plan pins Voice Mode as a route of the same SPA (Decision 5), mounted
 * beside the dashboard pages, with the screen's `onExitToCanvas` seam wired
 * to the Host Canvas return edge (navigate home + the engaged surface).
 * The screen itself has its own 33-test suite; here only the wiring is
 * under test.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'

vi.mock('@/pages/VoiceMode', () => ({
  VoiceMode: ({ onExitToCanvas }: { onExitToCanvas?: () => void }) => (
    <div data-testid="voice-screen">
      <button type="button" onClick={() => onExitToCanvas?.()}>
        exit-to-canvas
      </button>
    </div>
  ),
  default: () => null,
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
          // Every panel on the dashboard hydrates from this one payload
          // shape; HostVitals reads storage.pools unconditionally.
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
  const view = render(<App />)
  // The onboarding gate renders "Loading..." until its status check lands.
  await screen.findByTestId('app-shell')
  return view
}

describe('App /voice route', () => {
  beforeEach(() => {
    localStorage.clear()
    stubAppFetches()
    // Engaged mode mounts the whole host canvas; jsdom lacks the two browser
    // surfaces that canvas leans on (scroll anchoring, being-event SSE).
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

  it('mounts the voice screen at /voice inside the shell', async () => {
    await renderAppAt('/voice')

    expect(screen.getByTestId('voice-screen')).toBeInTheDocument()
  })

  it('does not mount the voice screen at the dashboard route', async () => {
    await renderAppAt('/')

    expect(screen.queryByTestId('voice-screen')).not.toBeInTheDocument()
  })

  it('wires onExitToCanvas to the host canvas return edge', async () => {
    await renderAppAt('/voice')

    act(() => {
      screen.getByText('exit-to-canvas').click()
    })

    expect(window.location.pathname).toBe('/')
    expect(screen.getByTestId('app-shell')).toBeInTheDocument()
  })
})
