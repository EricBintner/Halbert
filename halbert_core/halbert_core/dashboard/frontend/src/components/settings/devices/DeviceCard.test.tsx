// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * DeviceCard tests (G12 / P7d, design review §9): per-device surface —
 * capability badges, WoL toggle with the inline MAC form, capability
 * discovery outcomes, removal confirmation, and revoked-device muting.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DeviceCard } from './DeviceCard'
import type { DeviceInfo } from '@/lib/peerApi'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

function device(overrides: Partial<DeviceInfo> = {}): DeviceInfo {
  return {
    node_id: 'desk',
    node_name: 'Mac Studio',
    role: 'compute_provider',
    endpoint: 'http://desk.lan:8000',
    capabilities: ['gpu_llm', 'terminal'],
    compute_direction: 'outbound',
    wol_enabled: false,
    wol_mac: null,
    wol_broadcast: null,
    paired_at: '2026-08-31T12:00:00Z',
    last_seen: null,
    revoked: false,
    ...overrides,
  }
}

/**
 * Render the card with its endpoints routed; every fetch is recorded and
 * `onRefresh` (the parent's reload) is spied.
 */
function renderCard(dev: DeviceInfo, routes: Record<string, unknown> = {}) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const onRefresh = vi.fn(async () => {})
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    for (const [prefix, body] of Object.entries(routes)) {
      if (url.includes(prefix)) return jsonResponse(body)
    }
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<DeviceCard device={dev} onRefresh={onRefresh} />)
  return { calls, onRefresh }
}

afterEach(() => vi.unstubAllGlobals())

describe('DeviceCard', () => {
  it('renders device info and capability badges', () => {
    renderCard(device())
    expect(screen.getByText('Mac Studio')).toBeTruthy()
    expect(screen.getByText(/desk\.lan:8000/)).toBeTruthy()
    expect(screen.getByText('gpu_llm')).toBeTruthy()
    expect(screen.getByText('terminal')).toBeTruthy()
    // Badge titles carry full descriptions (accessibility, review §8).
    expect(screen.getByTitle('This device can run terminal sessions')).toBeTruthy()
  })

  it('enabling WoL with no MAC opens the inline form, not a modal', async () => {
    const user = userEvent.setup()
    const { calls } = renderCard(device())
    await user.click(screen.getByRole('switch', { name: /wake-on-lan/i }))
    // The form appears; nothing was sent yet — a MAC is required first.
    expect(screen.getByLabelText(/mac address/i)).toBeTruthy()
    expect(calls.filter((c) => c.url.includes('/wol'))).toHaveLength(0)
  })

  it('the MAC form sends the PUT once validated', async () => {
    const user = userEvent.setup()
    const { calls, onRefresh } = renderCard(device())
    await user.click(screen.getByRole('switch', { name: /wake-on-lan/i }))
    await user.type(screen.getByLabelText(/mac address/i), '00:1A:2B:3C:4D:5E')
    await user.click(screen.getByRole('button', { name: 'Enable' }))
    const wolCall = calls.find((c) => c.url.includes('/api/devices/desk/wol'))
    expect(wolCall).toBeTruthy()
    expect(JSON.parse(String(wolCall?.init?.body))).toEqual({
      enabled: true, mac: '00:1A:2B:3C:4D:5E', broadcast: undefined,
    })
    await waitFor(() => expect(onRefresh).toHaveBeenCalled())
  })

  it('enabling WoL with an existing MAC sends the PUT directly', async () => {
    const user = userEvent.setup()
    const { calls } = renderCard(device({ wol_mac: 'AA:BB:CC:DD:EE:FF' }))
    await user.click(screen.getByRole('switch', { name: /wake-on-lan/i }))
    const wolCall = calls.find((c) => c.url.includes('/api/devices/desk/wol'))
    expect(wolCall).toBeTruthy()
    expect(JSON.parse(String(wolCall?.init?.body)).enabled).toBe(true)
  })

  it('discovery shows loading then the found capabilities', async () => {
    const user = userEvent.setup()
    renderCard(device(), {
      '/api/devices/desk/discover': {
        status: 'discovered', node_id: 'desk', tools: 12,
        capabilities: ['mcp', 'terminal'],
      },
    })
    await user.click(screen.getByRole('button', { name: /discover capabilities/i }))
    await waitFor(() =>
      expect(screen.getByText(/Found 12 tools → \[mcp, terminal\]/)).toBeTruthy())
  })

  it('an unreachable device is a result, not an error', async () => {
    const user = userEvent.setup()
    renderCard(device(), {
      '/api/devices/desk/discover': {
        status: 'unreachable', node_id: 'desk', capabilities: ['gpu_llm'],
      },
    })
    await user.click(screen.getByRole('button', { name: /discover capabilities/i }))
    await waitFor(() =>
      expect(screen.getByText(/Device unreachable — capabilities unchanged/i)).toBeTruthy())
  })

  it('remove asks for confirmation, then sends DELETE', async () => {
    const user = userEvent.setup()
    const { calls, onRefresh } = renderCard(device())
    await user.click(screen.getByRole('button', { name: /remove mac studio/i }))
    // Confirm dialog names the device (review §8).
    expect(screen.getByText('Remove Mac Studio?')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Remove Device' }))
    const del = calls.find((c) => c.init?.method === 'DELETE')
    expect(del?.url).toBe('/api/devices/desk')
    await waitFor(() => expect(onRefresh).toHaveBeenCalled())
  })

  it('a revoked device is muted with interactive controls disabled', () => {
    renderCard(device({ revoked: true }))
    expect(screen.getByText('Revoked')).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: /discover capabilities/i }) as HTMLButtonElement).disabled,
    ).toBe(true)
    expect(
      (screen.getByRole('button', { name: /remove mac studio/i }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})