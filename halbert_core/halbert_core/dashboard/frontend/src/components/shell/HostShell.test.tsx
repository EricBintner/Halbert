// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The shell's job is to mount the two halves of the engaged surface and to be
 * the one place that knows how to leave it. AgentChat and ContextStage are
 * stubbed: what is under test is the wiring HostShell owns, not either panel.
 *
 * The defect this pins: the popover's "All models and endpoints…" link is
 * driven by `onOpenModelSettings`, and HostShell mounted AgentChat without
 * one — so the link either rendered and did nothing, or did not render at all.
 * Model settings live on a page in the *other* mode, so opening them is both
 * a mode change and a navigation, and only the shell knows about both.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { ShellModeProvider, useShellMode } from '@/contexts/ShellModeContext'
import { HostShell } from './HostShell'

vi.mock('../agent/AgentChat', () => ({
  AgentChat: ({ onOpenModelSettings }: { onOpenModelSettings?: () => void }) => (
    <button type="button" onClick={onOpenModelSettings}>
      open model settings
    </button>
  ),
}))

vi.mock('./ContextStage', () => ({
  ContextStage: () => <div data-testid="context-stage" />,
}))

function Probe() {
  const { mode } = useShellMode()
  const location = useLocation()
  return (
    <div data-testid="probe">{`${mode} ${location.pathname}${location.search}`}</div>
  )
}

function mount() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ShellModeProvider>
        <HostShell />
        <Probe />
      </ShellModeProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  try {
    localStorage.clear()
  } catch {
    // storage disabled — the provider defaults to engaged anyway
  }
})

describe('HostShell', () => {
  it('gives the conversation a way to open model settings', async () => {
    mount()

    await userEvent.click(screen.getByRole('button', { name: /open model settings/ }))

    // Browsing mode, because the settings page does not exist in engaged mode;
    // the tab hint so the page can open on the models tab rather than the first.
    await waitFor(() =>
      expect(screen.getByTestId('probe')).toHaveTextContent('both /settings?tab=ai'),
    )
  })

  it('is still on the both (side-by-side) surface until that link is used', () => {
    mount()
    expect(screen.getByTestId('probe')).toHaveTextContent('both /')
  })

  it('mounts one polite region and one assertive region for the whole shell', () => {
    const { container } = mount()

    expect(container.querySelectorAll('[role="status"], [aria-live="polite"]')).toHaveLength(1)
    expect(container.querySelectorAll('[role="alert"], [aria-live="assertive"]')).toHaveLength(1)
  })
})
