// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The engaged tab is named after the machine.
 *
 * Onboarding asks "What should I call this computer?"; whatever the user typed
 * there is what the switch must say — not the hostname, and not a product
 * word invented for the mode.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ModeSwitch } from './ModeSwitch'
import { ShellModeProvider } from '@/contexts/ShellModeContext'

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

function renderSwitch() {
  return render(
    <ShellModeProvider>
      <ModeSwitch />
    </ShellModeProvider>,
  )
}

describe('ModeSwitch', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('labels the engaged tab with the name chosen in onboarding', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    renderSwitch()

    await waitFor(() => expect(screen.getByText('Macky-Mac')).toBeInTheDocument())
    // The hostname is never presented as the machine's name.
    expect(screen.queryByText(/Erics-Mac-Studio/)).not.toBeInTheDocument()
  })

  it('never says the word this product does not use', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    const { container } = renderSwitch()

    await waitFor(() => expect(screen.getByText('Macky-Mac')).toBeInTheDocument())
    expect(container.textContent ?? '').not.toMatch(/sovereign/i)
  })

  it('keeps the dashboard tab as the fixed second surface', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => IDENTITY,
    }))

    renderSwitch()

    const tabs = await screen.findAllByRole('tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[1]).toHaveTextContent('Dashboard')
    // Engaged is the default surface.
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })
})
