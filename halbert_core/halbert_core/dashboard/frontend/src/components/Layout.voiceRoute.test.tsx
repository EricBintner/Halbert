// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Layout — the /voice route overtakes the shell (O8).
 *
 * Voice is a full-bleed surface: the screen owns the window (its own dark
 * canvas, its own header with the mute control), so the Layout must render
 * neither the navigation rail nor the shell top bar over it. The route is
 * also a mode boundary: mounting /voice must put the shell into the voice
 * mode, and leaving it must return the previous surface.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { Layout } from './Layout'
import { ShellModeProvider, useShellMode } from '@/contexts/ShellModeContext'

vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    NavRail: () => <div data-testid="nav-rail" />,
  }
})

function LayoutProbe() {
  const { mode } = useShellMode()
  return <span data-testid="shell-mode">{mode}</span>
}

function GoToVoice() {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate('/voice')}>
      go-voice
    </button>
  )
}

function renderShellAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ShellModeProvider>
        <Layout>
          <Routes>
            <Route path="/voice" element={<div data-testid="voice-screen" />} />
            <Route path="*" element={<div data-testid="page-child" />} />
          </Routes>
        </Layout>
        <LayoutProbe />
        <GoToVoice />
      </ShellModeProvider>
    </MemoryRouter>,
  )
}

/** Everything Layout mounts fetches something on mount; answer all of it. */
function stubFetches() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: async () => ({ role: 'standalone', features: { home: true }, enabled: false }),
      }),
    ),
  )
}

describe('Layout /voice route', () => {
  beforeEach(() => {
    localStorage.clear()
    stubFetches()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('mounting /voice renders the screen full-bleed: no rail, no top bar', () => {
    renderShellAt('/voice')

    expect(screen.getByTestId('voice-screen')).toBeInTheDocument()
    expect(screen.queryByTestId('nav-rail')).not.toBeInTheDocument()
    // The shell header (banner) would put the mode switch and the gear over
    // the voice canvas; the screen carries its own header.
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
  })

  it('mounting /voice switches the shell into voice mode', () => {
    renderShellAt('/voice')

    expect(screen.getByTestId('shell-mode')).toHaveTextContent('voice')
  })

  it('a browsing page keeps the rail and top bar the voice route removes', async () => {
    localStorage.setItem('halbert:shell-mode', 'browsing')
    renderShellAt('/')

    // Sanity: the rail exists where the dashboard is browsed…
    expect(screen.getByTestId('page-child')).toBeInTheDocument()
    expect(screen.getByTestId('nav-rail')).toBeInTheDocument()
    expect(screen.getByRole('banner')).toBeInTheDocument()

    const before = document.querySelector('[data-testid="nav-rail"]')
    expect(before).not.toBeNull()

    // …and the voice route takes the whole shell when entered.
    screen.getByText('go-voice').click()
    await waitFor(() => expect(screen.getByTestId('voice-screen')).toBeInTheDocument())
    expect(screen.queryByTestId('nav-rail')).not.toBeInTheDocument()
    expect(screen.queryByRole('banner')).not.toBeInTheDocument()
    expect(screen.getByTestId('shell-mode')).toHaveTextContent('voice')
  })

  it('does not persist voice as the reopened shell mode', () => {
    renderShellAt('/voice')

    expect(localStorage.getItem('halbert:shell-mode')).not.toBe('voice')
  })
})
