// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Settings is laid OVER the rail and centre panel, not rendered beside them.
 *
 * The shell used to render Settings inside the centre panel while the
 * dashboard rail stayed put, so Settings — which brings its own rail — showed
 * up as a second column: dashboard rail | settings rail | content. The gear's
 * own comment already claimed it "overtakes the shell"; the implementation
 * never did.
 *
 * Two things are pinned here, because the layout reads correctly only if both
 * hold:
 *   1. Settings covers the rail and centre (one column, not two), and leaves
 *      the conversation panel beside it alone.
 *   2. The settings entry lives in the rail's FOOTER, not the top bar — so it
 *      lands on the same pixel as the settings rail's Back button, which comes
 *      down on top of it.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './Layout'
import { ShellModeProvider } from '@/contexts/ShellModeContext'

/** The footer node Layout last handed the rail, so the gear is assertable. */
vi.mock('@halbert/design-system', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    NavRail: (props: { footer?: React.ReactNode; header?: React.ReactNode }) => (
      <div data-testid="nav-rail">
        <div data-testid="nav-rail-footer">{props.footer}</div>
      </div>
    ),
  }
})

function renderShell(path: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ role: 'standalone', features: { home: true }, enabled: false, pending: [] }),
    }),
  )
  return render(
    <MemoryRouter initialEntries={[path]}>
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

describe('Layout settings overlay', () => {
  beforeEach(() => {
    localStorage.clear()
    // 'browsing' keeps the conversation panel unmounted — jsdom has no
    // scrollIntoView, and nothing here depends on the right panel's contents.
    localStorage.setItem('halbert:shell-mode', 'browsing')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('puts the settings entry in the rail footer, not the top bar', () => {
    renderShell('/')
    const gear = screen.getByRole('button', { name: 'Open settings' })
    expect(screen.getByTestId('nav-rail-footer')).toContainElement(gear)
  })

  it('lays the settings page over the rail and centre instead of beside them', () => {
    const { container } = renderShell('/settings')

    // The overlay exists and is positioned over its container rather than
    // taking a column in the flex row.
    const overlay = container.querySelector('.absolute.inset-0')
    expect(overlay).not.toBeNull()
    expect(overlay).toContainElement(screen.getByTestId('page-child'))

    // ...and the padded centre <main> is not also rendering the same page
    // underneath it, which is what produced the second column.
    expect(container.querySelector('main')).toBeNull()
  })

  it('still renders the centre panel normally off the settings route', () => {
    const { container } = renderShell('/')
    expect(container.querySelector('main')).not.toBeNull()
    expect(container.querySelector('.absolute.inset-0')).toBeNull()
    expect(screen.getByTestId('page-child')).toBeInTheDocument()
  })
})
