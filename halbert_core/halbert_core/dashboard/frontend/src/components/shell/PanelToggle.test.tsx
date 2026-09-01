// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PanelToggle — the top-bar panel visibility control.
 *
 * Two buttons toggle the center (dashboard) and right (conversation) panels.
 * The right button is labeled with the machine's display name (from
 * onboarding), not the hostname and not a product word invented for the mode.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PanelToggle } from './PanelToggle'
import { ShellModeProvider, useShellMode } from '@/contexts/ShellModeContext'

const IDENTITY = {
  display_name: 'Macky-Mac',
  hostname: 'Erics-Mac-Studio.local',
  os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 20, physical_cores: 20, percent: 12, temperature: null },
  memory: { total_gb: 128, used_gb: 61, percent: 48 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true,
  first_person: 'I am Macky-Mac (macOS 26.5.1, Darwin 25.5.0).',
  timestamp: '',
}

/** Probe to read the current panel visibility state. */
function StateProbe() {
  const { centerVisible, rightVisible } = useShellMode()
  return (
    <div>
      <span data-testid="center-visible">{String(centerVisible)}</span>
      <span data-testid="right-visible">{String(rightVisible)}</span>
    </div>
  )
}

function renderToggle() {
  return render(
    <ShellModeProvider>
      <PanelToggle />
      <StateProbe />
    </ShellModeProvider>,
  )
}

describe('PanelToggle', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('labels the conversation button with the name chosen in onboarding', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    renderToggle()

    await waitFor(() => expect(screen.getByText('Macky-Mac')).toBeInTheDocument())
    // The hostname is never presented as the machine's name.
    expect(screen.queryByText(/Erics-Mac-Studio/)).not.toBeInTheDocument()
  })

  it('never says the word this product does not use', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    const { container } = renderToggle()

    await waitFor(() => expect(screen.getByText('Macky-Mac')).toBeInTheDocument())
    expect(container.textContent ?? '').not.toMatch(/sovereign/i)
  })

  it('has Dashboard and conversation toggle buttons, both pressed by default', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    renderToggle()

    const dashboardBtn = screen.getByRole('button', { name: /dashboard/i })
    const conversationBtn = await waitFor(() =>
      screen.getByRole('button', { name: /macky-mac/i }),
    )

    // Default mode is 'both' — both panels visible, both buttons pressed.
    expect(dashboardBtn).toHaveAttribute('aria-pressed', 'true')
    expect(conversationBtn).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('center-visible')).toHaveTextContent('true')
    expect(screen.getByTestId('right-visible')).toHaveTextContent('true')
  })

  it('toggles the center panel off when Dashboard is clicked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    renderToggle()

    const dashboardBtn = screen.getByRole('button', { name: /dashboard/i })
    await userEvent.click(dashboardBtn)

    expect(dashboardBtn).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('center-visible')).toHaveTextContent('false')
    // Right panel stays visible.
    expect(screen.getByTestId('right-visible')).toHaveTextContent('true')
  })

  it('toggles the right panel off when conversation is clicked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    renderToggle()

    const conversationBtn = await waitFor(() =>
      screen.getByRole('button', { name: /macky-mac/i }),
    )
    await userEvent.click(conversationBtn)

    expect(conversationBtn).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('right-visible')).toHaveTextContent('false')
    // Center panel stays visible.
    expect(screen.getByTestId('center-visible')).toHaveTextContent('true')
  })
})
