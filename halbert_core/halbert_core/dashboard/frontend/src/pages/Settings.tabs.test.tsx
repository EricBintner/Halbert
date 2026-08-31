// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The settings page's tab is addressable.
 *
 * The defect: the model picker's "All models and endpoints…" link navigates to
 * `/settings?tab=ai`, and the page's `<Tabs>` was uncontrolled with a hard
 * `defaultValue="system"`. So the link landed the user on the settings page —
 * on the System tab, with the thing they asked for one more click away and no
 * indication which tab it was on.
 *
 * Only the tab wiring is under test here. Everything the page loads on mount is
 * stubbed; none of it decides which tab is showing.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('@/contexts/ScanContext', () => ({
  useScan: () => ({ triggerDeepScan: vi.fn(), isDeepScanning: false }),
}))

vi.mock('@/contexts/DebugContext', () => ({
  useDebug: () => ({
    isDebugMode: false,
    setDebugMode: vi.fn(),
    logs: [],
    clearLogs: vi.fn(),
    chatMetrics: { totalRequests: 0, totalTokensEstimate: 0, averageResponseTime: 0 },
    updateChatMetrics: vi.fn(),
  }),
}))

vi.mock('@/lib/tauri', () => ({
  getSystemInfo: vi.fn().mockResolvedValue(null),
  isTauri: () => false,
}))

vi.mock('@/lib/api', () => ({
  api: new Proxy({}, { get: () => vi.fn().mockResolvedValue({}) }),
}))

// The AI tab's own content is a whole model-configuration surface with its own
// suite. Stubbing it keeps this file about the one thing it claims to test —
// which tab the URL opens — instead of about the picker's discovery state.
vi.mock('@/components/llm', () => ({
  ModelSettings: () => <div data-testid="model-settings" />,
  ComputePeerCard: () => <div data-testid="compute-peer-card" />,
}))

// The AI tab's surface is chosen by the instance's variant (U6 S3): the full
// picker on sysadmin, the compute-peer link card on home. Mocking
// the hook keeps this file off the network.
const useInstanceVariantMock = vi.hoisted(() => vi.fn((): string | null => null))
vi.mock('@/hooks/useInstanceVariant', () => ({
  useInstanceVariant: useInstanceVariantMock,
}))

import { Settings } from './Settings'

function Location() {
  const location = useLocation()
  return <span data-testid="url">{`${location.pathname}${location.search}`}</span>
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Settings />
      <Location />
    </MemoryRouter>,
  )
}

/** The trigger for one tab, by its visible name. */
const tab = (name: RegExp) => screen.getByRole('tab', { name })

afterEach(() => {
  vi.unstubAllGlobals()
  useInstanceVariantMock.mockReset()
  useInstanceVariantMock.mockReturnValue(null)
})

describe('Settings tabs follow the URL', () => {
  beforeEach(() => {
    useInstanceVariantMock.mockReturnValue(null)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
      text: async () => '',
    }))
  })

  it('opens the tab named in the URL, so a deep link lands where it points', async () => {
    renderAt('/settings?tab=ai')
    await waitFor(() =>
      expect(tab(/Models & Providers/i)).toHaveAttribute('aria-selected', 'true'),
    )
    expect(tab(/System Info/i)).toHaveAttribute('aria-selected', 'false')
  })

  it('still opens System when the URL names no tab', async () => {
    renderAt('/settings')
    await waitFor(() =>
      expect(tab(/System Info/i)).toHaveAttribute('aria-selected', 'true'),
    )
  })

  it('falls back to System for a tab name that is not one of the tabs', async () => {
    // Radix renders no panel at all for a value with no trigger, so an
    // unrecognised ?tab= would otherwise show a page of nothing but tabs.
    renderAt('/settings?tab=not-a-tab')
    await waitFor(() =>
      expect(tab(/System Info/i)).toHaveAttribute('aria-selected', 'true'),
    )
  })

  it('writes the tab back to the URL, so the tab someone is on is linkable', async () => {
    const user = userEvent.setup()
    renderAt('/settings')
    await waitFor(() => expect(tab(/System Info/i)).toBeInTheDocument())

    await user.click(tab(/Models & Providers/i))

    await waitFor(() =>
      expect(screen.getByTestId('url')).toHaveTextContent('/settings?tab=ai'),
    )
    expect(tab(/Models & Providers/i)).toHaveAttribute('aria-selected', 'true')
  })
})

describe('Settings AI tab follows the variant (U6 S3)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
      text: async () => '',
    }))
  })

  it.each(['home'])(
    'replaces the model picker with the compute-peer card on %s',
    async (variant) => {
      useInstanceVariantMock.mockReturnValue(variant)
      renderAt('/settings?tab=ai')
      await waitFor(() =>
        expect(screen.getByTestId('compute-peer-card')).toBeInTheDocument(),
      )
      expect(screen.queryByTestId('model-settings')).not.toBeInTheDocument()
    },
  )

  it('keeps the full picker on the sysadmin variant', async () => {
    useInstanceVariantMock.mockReturnValue('sysadmin')
    renderAt('/settings?tab=ai')
    await waitFor(() =>
      expect(screen.getByTestId('model-settings')).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('compute-peer-card')).not.toBeInTheDocument()
  })

  it('keeps the full picker when the variant is unknown — a failed info route must not shrink the surface', async () => {
    useInstanceVariantMock.mockReturnValue(null)
    renderAt('/settings?tab=ai')
    await waitFor(() =>
      expect(screen.getByTestId('model-settings')).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('compute-peer-card')).not.toBeInTheDocument()
  })
})
