// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Layout — the dashboard-to-conversation bridge respects hidden panels.
 *
 * A 'Run in Terminal' from a chat code block, an 'Ask Halbert' from a
 * finding, or a 'Send to chat' from GPU all park a request for the
 * conversation and make sure the conversation is on screen. They must not
 * touch the center panel: the user hides panels to focus (shell §9.6), so
 * a run-command issued while the conversation has the whole shell keeps
 * the dashboard hidden (W5-BUG-01).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'
import { ShellModeProvider, useShellMode } from '@/contexts/ShellModeContext'

vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    NavRail: () => <div data-testid="nav-rail" />,
  }
})

// The conversation panel mounts the whole chat; the bridge under test only
// decides whether the panel is on screen, so the panel itself is a stub.
vi.mock('./shell/HostShell', () => ({
  HostShell: () => <div data-testid="host-shell" />,
}))

function ModeProbe() {
  const { mode } = useShellMode()
  return <span data-testid="shell-mode">{mode}</span>
}

function renderShell(stored: 'engaged' | 'browsing' | 'both') {
  localStorage.setItem('halbert:shell-mode', stored)
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ShellModeProvider>
        <Layout>
          <Routes>
            <Route path="*" element={<div data-testid="page-child" />} />
          </Routes>
        </Layout>
        <ModeProbe />
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

function dispatch(name: string, detail: unknown) {
  act(() => {
    window.dispatchEvent(new CustomEvent(name, { detail }))
  })
}

describe('Layout bridge and panel visibility', () => {
  beforeEach(() => {
    localStorage.clear()
    stubFetches()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('run-command from engaged keeps the center hidden', () => {
    renderShell('engaged')
    expect(screen.queryByTestId('page-child')).not.toBeInTheDocument()
    expect(screen.getByTestId('host-shell')).toBeInTheDocument()

    dispatch('halbert:run-command', { command: 'ls -la', title: 'List' })

    expect(screen.getByTestId('shell-mode')).toHaveTextContent('engaged')
    expect(screen.queryByTestId('page-child')).not.toBeInTheDocument()
    expect(screen.getByTestId('host-shell')).toBeInTheDocument()
  })

  it('open-chat and send-to-chat from engaged keep the center hidden too', () => {
    renderShell('engaged')

    dispatch('halbert:open-chat', { prefillMessage: 'hello' })
    expect(screen.getByTestId('shell-mode')).toHaveTextContent('engaged')

    dispatch('halbert:send-to-chat', { command: 'nvidia-smi' })
    expect(screen.getByTestId('shell-mode')).toHaveTextContent('engaged')
    expect(screen.queryByTestId('page-child')).not.toBeInTheDocument()
  })

  it('run-command from browsing reveals the conversation beside the page', () => {
    renderShell('browsing')
    expect(screen.getByTestId('page-child')).toBeInTheDocument()
    expect(screen.queryByTestId('host-shell')).not.toBeInTheDocument()

    dispatch('halbert:run-command', { command: 'ls -la' })

    expect(screen.getByTestId('shell-mode')).toHaveTextContent('both')
    expect(screen.getByTestId('page-child')).toBeInTheDocument()
    expect(screen.getByTestId('host-shell')).toBeInTheDocument()
  })

  it('run-command from both leaves the layout as it is', () => {
    renderShell('both')
    dispatch('halbert:run-command', { command: 'ls -la' })
    expect(screen.getByTestId('shell-mode')).toHaveTextContent('both')
  })
})
