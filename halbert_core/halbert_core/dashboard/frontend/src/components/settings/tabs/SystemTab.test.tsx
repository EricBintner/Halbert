// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Regression test for R08-07/FEAT-02: SystemTab's "Clear Cache" button used
 * to be a placebo — it waited a second and told the user the cache was
 * cleared without calling any backend route (none exists to clear
 * discoveries). It has been removed along with the `clearing` /
 * `onClearDiscoveries` props; this file asserts it stays gone and covers
 * what the tab actually renders now: system info, the discovery cache
 * count, the system profile, and the deep-scan button/state.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SystemTab } from './SystemTab'
import type { SystemInfo } from '@/lib/tauri'

const systemInfo: SystemInfo = {
  hostname: 'workstation',
  os_name: 'Arch Linux',
  os_version: 'rolling',
  kernel_version: '6.10.1-arch1-1',
  cpu_count: 16,
  total_memory_mb: 32768,
}

function baseProps() {
  return {
    systemInfo: null as SystemInfo | null,
    discoveryStats: null as { total: number; by_type: Record<string, number> } | null,
    systemProfile: null as { summary: string; scan_time: string | null; quick_scan_time: string | null } | null,
    isDeepScanning: false,
    onDeepScan: vi.fn(),
  }
}

describe('SystemTab', () => {
  it('shows loading placeholders when systemInfo and systemProfile are not loaded yet', () => {
    render(<SystemTab {...baseProps()} />)
    expect(screen.getByText(/loading system info/i)).toBeTruthy()
    expect(screen.getByText(/no system profile yet/i)).toBeTruthy()
  })

  it('renders system info fields when loaded', () => {
    render(<SystemTab {...baseProps()} systemInfo={systemInfo} />)
    expect(screen.getByText('workstation')).toBeTruthy()
    expect(screen.getByText('Arch Linux rolling')).toBeTruthy()
    expect(screen.getByText('6.10.1-arch1-1')).toBeTruthy()
    expect(screen.getByText('16')).toBeTruthy()
    expect(screen.getByText('32 GB total')).toBeTruthy()
  })

  it('renders the discovery cache count and breakdown by type', () => {
    render(
      <SystemTab
        {...baseProps()}
        discoveryStats={{ total: 42, by_type: { package: 30, service: 12 } }}
      />,
    )
    expect(screen.getByText('42 discoveries cached')).toBeTruthy()
    expect(screen.getByText('30 package, 12 service')).toBeTruthy()
  })

  it('shows zero discoveries cached when discoveryStats is null', () => {
    render(<SystemTab {...baseProps()} />)
    expect(screen.getByText('0 discoveries cached')).toBeTruthy()
  })

  it('has no Clear Cache button (R08-07: removed placebo)', () => {
    render(
      <SystemTab
        {...baseProps()}
        discoveryStats={{ total: 5, by_type: { package: 5 } }}
      />,
    )
    expect(screen.queryByRole('button', { name: /clear cache/i })).toBeNull()
  })

  it('renders the system profile summary and last scan time when present', () => {
    render(
      <SystemTab
        {...baseProps()}
        systemProfile={{
          summary: 'CPU: 16 cores\nMemory: 32GB',
          scan_time: '2026-08-30T12:00:00Z',
          quick_scan_time: null,
        }}
      />,
    )
    expect(screen.getByText(/cpu: 16 cores/i)).toBeTruthy()
    expect(screen.getByText(/last deep scan:/i)).toBeTruthy()
    expect(screen.queryByText(/never/i)).toBeNull()
  })

  it('shows "Never" for last deep scan when scan_time is null', () => {
    render(
      <SystemTab
        {...baseProps()}
        systemProfile={{ summary: 'some summary', scan_time: null, quick_scan_time: null }}
      />,
    )
    expect(screen.getByText(/last deep scan:\s*never/i)).toBeTruthy()
  })

  it('clicking Run Deep Scan calls onDeepScan', async () => {
    const user = userEvent.setup()
    const onDeepScan = vi.fn()
    render(<SystemTab {...baseProps()} onDeepScan={onDeepScan} />)
    await user.click(screen.getByRole('button', { name: /run deep scan/i }))
    expect(onDeepScan).toHaveBeenCalledTimes(1)
  })

  it('disables the deep scan button and shows Scanning... while isDeepScanning is true', () => {
    render(<SystemTab {...baseProps()} isDeepScanning />)
    const button = screen.getByRole('button', { name: /scanning/i })
    expect(button).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^run deep scan$/i })).toBeNull()
  })
})
