// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The wiring, not the widget (TERM-1's last row).
 *
 * AggregateStatusLight has its own unit tests, and unit tests of a component
 * nobody mounts are how the whole Plan B block surface came to be green in CI
 * and unreachable in the product. This drives the real Layout with a real
 * promoted block in the store.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'
import { ShellModeProvider } from '@/contexts/ShellModeContext'
import { terminalSessionStore as store } from '@/hooks/useTerminalSessions'

vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, NavRail: () => <div data-testid="nav-rail" /> }
})

function renderShell() {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({ role: 'standalone', features: { home: true }, enabled: false, pending: [] }),
  })))
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ShellModeProvider>
        <Layout>
          <Routes><Route path="*" element={<div />} /></Routes>
        </Layout>
      </ShellModeProvider>
    </MemoryRouter>,
  )
}

describe('Layout — the aggregate status light', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('halbert:shell-mode', 'browsing')
    store.closeAll()
    vi.stubGlobal('WebSocket', class {
      onmessage: unknown = null; onclose: unknown = null; onerror: unknown = null
      readyState = 1
      constructor(public url: string) {}
      send() {} close() {}
    } as unknown as typeof WebSocket)
  })
  afterEach(() => { store.closeAll(); vi.unstubAllGlobals(); localStorage.clear() })

  it('shows nothing in the top bar while nothing is running', () => {
    renderShell()
    expect(document.querySelector('[data-aggregate-status]')).toBeNull()
  })

  it('lights up when a command is promoted', async () => {
    store.adopt('term-1', { command: 'npm run build', pid: 9, blockId: 'blk-1', owner: 'agent' })
    store.addBlock('term-1', {
      block_id: 'blk-1', owner: 'agent', status: 'running', isTaskCard: true,
    })

    renderShell()

    await waitFor(() => {
      expect(document.querySelector('[data-aggregate-status]')).toBeTruthy()
    })
    expect(screen.getByLabelText(/1 task running/i)).toBeTruthy()
  })

  it('does not light up for a command that was never promoted', () => {
    store.adopt('term-1', { command: 'ls', pid: 9, blockId: 'blk-2', owner: 'agent' })
    store.addBlock('term-1', {
      block_id: 'blk-2', owner: 'agent', status: 'running', isTaskCard: false,
    })

    renderShell()
    // A fast command is a line in the conversation, not a light in the chrome.
    expect(document.querySelector('[data-aggregate-status]')).toBeNull()
  })
})
