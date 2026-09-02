// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Regression test for R08-07: DebugTab's debug-logging toggle used to be a
 * plain Button whose only accessible name was its own state-dependent text
 * ("Debug ON"/"Debug OFF") — a Label's `for` pointed at it but said nothing
 * about what the control does. It is now the shared Switch (role="switch",
 * aria-checked), the same toggle idiom as AudioSettings/BeingTab. This
 * queries the toggle by role "switch" (never "button") and covers the log
 * list rendering and Clear behavior.
 */
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { DebugTab } from './DebugTab'
import { DebugProvider, useDebug } from '@/contexts/DebugContext'

/** Seeds a couple of log entries through the real context, then renders the tab. */
function Harness() {
  const { addLog } = useDebug()
  useEffect(() => {
    addLog({ type: 'error', category: 'api', message: 'Request failed' })
    addLog({ type: 'info', category: 'system', message: 'Started up' })
    // addLog is stable (useCallback), safe to depend on.
  }, [addLog])
  return <DebugTab />
}

function renderWithLogs() {
  return render(
    <DebugProvider>
      <Harness />
    </DebugProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})

describe('DebugTab', () => {
  it('renders the toggle as a switch, not a button, with a stable accessible name', () => {
    render(
      <DebugProvider>
        <DebugTab />
      </DebugProvider>,
    )
    const toggle = screen.getByRole('switch', { name: /enable debug logging/i })
    expect(toggle).toBeTruthy()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.queryByRole('button', { name: /debug (on|off)/i })).toBeNull()
  })

  it('clicking the switch flips aria-checked and persists to localStorage', async () => {
    const user = userEvent.setup()
    render(
      <DebugProvider>
        <DebugTab />
      </DebugProvider>,
    )
    const toggle = screen.getByRole('switch', { name: /enable debug logging/i })
    expect(toggle).toHaveAttribute('aria-checked', 'false')

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-checked', 'true')
    expect(localStorage.getItem('halbert_debug_mode')).toBe('true')
  })

  it('shows "No logs yet" when there are no captured logs', () => {
    render(
      <DebugProvider>
        <DebugTab />
      </DebugProvider>,
    )
    expect(screen.getByText('Logs (0)')).toBeTruthy()
    expect(screen.getByText(/no logs yet/i)).toBeTruthy()
  })

  it('renders captured log entries with their category and message', () => {
    renderWithLogs()
    expect(screen.getByText('Logs (2)')).toBeTruthy()
    expect(screen.getByText(/request failed/i)).toBeTruthy()
    expect(screen.getByText(/started up/i)).toBeTruthy()
    expect(screen.getByText('[api]')).toBeTruthy()
    expect(screen.getByText('[system]')).toBeTruthy()
  })

  it('Clear empties the log list', async () => {
    const user = userEvent.setup()
    renderWithLogs()
    expect(screen.getByText('Logs (2)')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Clear' }))

    expect(screen.getByText('Logs (0)')).toBeTruthy()
    expect(screen.getByText(/no logs yet/i)).toBeTruthy()
    expect(screen.queryByText(/request failed/i)).toBeNull()
  })
})
