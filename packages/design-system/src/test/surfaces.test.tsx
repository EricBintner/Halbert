// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { AppWindow } from '../surfaces/AppWindow'
import { MetricCard } from '../surfaces/MetricCard'

describe('AppWindow', () => {
  it('exposes itself as a landmark named by its title', () => {
    render(<AppWindow title="Proactive Events" meta="2 active">body</AppWindow>)
    expect(screen.getByRole('region', { name: 'Proactive Events' })).toBeInTheDocument()
  })

  it('collapses from the keyboard and reports expanded state', async () => {
    render(<AppWindow title="System Vitals" collapsible>readings</AppWindow>)
    const toggle = screen.getByRole('button', { name: /system vitals/i })

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('readings')).toBeVisible()

    toggle.focus()
    await userEvent.keyboard('{Enter}')

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('readings')).not.toBeVisible()
  })

  it('honours a controlled collapsed prop without self-toggling', async () => {
    const onCollapsedChange = vi.fn()
    render(
      <AppWindow title="Storage" collapsible collapsed onCollapsedChange={onCollapsedChange}>
        trays
      </AppWindow>,
    )
    const toggle = screen.getByRole('button', { name: /storage/i })
    await userEvent.click(toggle)

    expect(onCollapsedChange).toHaveBeenCalledWith(false)
    // Still collapsed: the parent owns the state.
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('has no toggle button when it is not collapsible', () => {
    render(<AppWindow title="Static">body</AppWindow>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('MetricCard', () => {
  it('exposes the gauge as a meter labelled by the metric', () => {
    render(<MetricCard label="CPU temp" value="45°C" bar={38} tone="nominal" />)
    const meter = screen.getByRole('meter', { name: 'CPU temp' })
    expect(meter).toHaveAttribute('aria-valuenow', '38')
  })

  it('clamps out-of-range readings instead of overflowing the gauge', () => {
    render(<MetricCard label="Memory" value="72 GB" bar={140} />)
    expect(screen.getByRole('meter', { name: 'Memory' })).toHaveAttribute('aria-valuenow', '100')
  })

  it('shows an honest degraded state rather than a plausible zero', () => {
    render(<MetricCard label="Fan speed" value="0 RPM" offline />)
    expect(screen.getByText('[Sensor offline]')).toBeInTheDocument()
    expect(screen.queryByText('0 RPM')).not.toBeInTheDocument()
    expect(screen.queryByRole('meter')).not.toBeInTheDocument()
  })
})
