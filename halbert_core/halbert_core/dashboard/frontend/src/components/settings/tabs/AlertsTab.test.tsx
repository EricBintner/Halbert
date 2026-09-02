// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AlertsTab (FE-15): a read-only render of whatever alertRules the parent
 * passes in — no fetch, no state. Covers the empty/loading placeholder and
 * that each rule's name, severity badge, description, and enabled/disabled
 * badge render correctly.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AlertsTab, type AlertRule } from './AlertsTab'

function rule(overrides: Partial<AlertRule> = {}): AlertRule {
  return {
    id: 'r1',
    name: 'High CPU',
    description: 'Fires when CPU usage stays above 90% for 5 minutes',
    severity: 'warning',
    enabled: true,
    ...overrides,
  }
}

describe('AlertsTab', () => {
  it('shows a loading placeholder when there are no alert rules yet', () => {
    render(<AlertsTab alertRules={[]} />)
    expect(screen.getByText(/loading alert rules/i)).toBeTruthy()
  })

  it('renders a rule with its name, severity, description, and enabled badge', () => {
    render(<AlertsTab alertRules={[rule()]} />)
    expect(screen.getByText('High CPU')).toBeTruthy()
    expect(screen.getByText('warning')).toBeTruthy()
    expect(screen.getByText(/fires when cpu usage/i)).toBeTruthy()
    expect(screen.getByText('Enabled')).toBeTruthy()
  })

  it('renders a disabled rule with the Disabled badge', () => {
    render(<AlertsTab alertRules={[rule({ id: 'r2', name: 'Low Disk', enabled: false })]} />)
    expect(screen.getByText('Low Disk')).toBeTruthy()
    expect(screen.getByText('Disabled')).toBeTruthy()
    expect(screen.queryByText('Enabled')).toBeNull()
  })

  it('renders multiple rules independently', () => {
    render(
      <AlertsTab
        alertRules={[
          rule({ id: 'r1', name: 'High CPU', enabled: true }),
          rule({ id: 'r2', name: 'Low Disk', enabled: false, severity: 'critical' }),
        ]}
      />,
    )
    expect(screen.getByText('High CPU')).toBeTruthy()
    expect(screen.getByText('Low Disk')).toBeTruthy()
    expect(screen.getByText('critical')).toBeTruthy()
    expect(screen.getByText('Enabled')).toBeTruthy()
    expect(screen.getByText('Disabled')).toBeTruthy()
  })
})
