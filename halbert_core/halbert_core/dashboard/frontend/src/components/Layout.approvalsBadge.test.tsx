// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * R08-01/NAV-01: the top-bar approvals badge polls getPendingApprovals()
 * and surfaces the count; it must stay hidden at zero (an empty badge is
 * noise) and appear once there is something to review.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'
import { ShellModeProvider } from '@/contexts/ShellModeContext'

vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    NavRail: () => <div data-testid="nav-rail" />,
  }
})

function renderShell(pendingCount: number) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/api/settings/approvals/pending')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            pending: Array.from({ length: pendingCount }, (_, i) => ({ id: `r${i}` })),
            blocked_by_rules: 0,
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ role: 'standalone', features: { home: true }, enabled: false }),
      })
    }),
  )
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ShellModeProvider>
        <Layout>
          <Routes>
            <Route path="*" element={<div data-testid="page-child" />} />
          </Routes>
        </Layout>
      </ShellModeProvider>
    </MemoryRouter>,
  )
}

describe('Layout approvals badge', () => {
  beforeEach(() => {
    localStorage.clear()
    // 'browsing' keeps the right panel (HostShell/AgentChat) unmounted —
    // jsdom has no scrollIntoView, and this test only cares about the
    // top-bar badge, not the conversation panel.
    localStorage.setItem('halbert:shell-mode', 'browsing')
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('stays hidden when there are no pending approvals', async () => {
    renderShell(0)
    const approvalsButton = await screen.findByRole('button', { name: /open approvals/i })
    await waitFor(() => expect(approvalsButton.querySelector('div')).toBeNull())
  })

  it('shows the count once approvals are pending', async () => {
    renderShell(3)
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
  })
})
