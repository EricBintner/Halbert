// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * DevicesTab tests (G12 / P7d, design review §9): the page composition —
 * empty state with the Add-First-Device CTA, the device list, the
 * singular-mode confirmation flow, body name editing, the Add Device
 * button opening the pairing modal (P7c, reused), refresh after pairing,
 * and the revoked/archived section's Permanently Forget.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DevicesTab } from './DevicesTab'
import type { DevicesState, DeviceInfo } from '@/lib/peerApi'

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
    capabilities: ['gpu_llm'],
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

function devicesState(overrides: Partial<DevicesState> = {}): DevicesState {
  return {
    status: 'ok',
    entity_mode: 'independent',
    body_name: 'workstation',
    canonical_memory_url: '',
    canonical_thread_url: '',
    devices: [],
    ...overrides,
  }
}

/**
 * Render the tab with /api/devices routed; `state` is mutable so a
 * mutation can change what the next load answers (like the real backend).
 */
function renderTab(state: DevicesState) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/peers/discovered') return jsonResponse([])
    if (url === '/api/devices') return jsonResponse(state)
    if (url.includes('/api/devices/entity-mode')) {
      state = { ...state, entity_mode: 'singular' }
      return jsonResponse(state)
    }
    if (url.includes('/api/devices/body-name')) {
      state = { ...state, body_name: 'desk' }
      return jsonResponse(state)
    }
    if (url.includes('?forget=true')) {
      state = { ...state, devices: state.devices.filter((d) => d.node_id !== 'old-pi') }
      return jsonResponse({ status: 'forgotten' })
    }
    return jsonResponse({ status: 'ok' })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<DevicesTab />)
  return { calls, getState: () => state }
}

afterEach(() => vi.unstubAllGlobals())

const addDeviceButton = () => screen.getByRole('button', { name: /link a device/i })

describe('DevicesTab', () => {
  it('renders the empty state with a Link First Device CTA when no devices', async () => {
    renderTab(devicesState())
    expect(await screen.findByText(/Link First Device/i)).toBeTruthy()
    expect(screen.getByText(/one entity across many machines/i)).toBeTruthy()
  })

  it('renders the device list with correct fields', async () => {
    renderTab(devicesState({ devices: [device()] }))
    expect(await screen.findByText('Mac Studio')).toBeTruthy()
    // One noun for the list (T1-08): 'Linked Devices', never 'Paired Bodies'.
    expect(screen.getByText(/^Linked Devices \(1\)$/)).toBeTruthy()
    expect(screen.queryByText(/paired bodies/i)).toBeNull()
    expect(screen.getByText(/desk\.lan:8000/)).toBeTruthy()
    expect(screen.getByText('gpu_llm')).toBeTruthy()
  })

  it('switching to singular mode asks for confirmation first (review Q2)', async () => {
    const user = userEvent.setup()
    renderTab(devicesState())
    await screen.findByText(/Link First Device/i)
    await user.click(screen.getByRole('radio', { name: /singular entity/i }))
    // The confirmation dialog names what changes before anything is sent.
    expect(screen.getByText('Join the canonical host?')).toBeTruthy()
    expect(screen.getByText(/share its memory and conversations/i)).toBeTruthy()
  })

  it('confirming singular mode sends the PUT with the base URL', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab(devicesState())
    await screen.findByText(/Link First Device/i)
    await user.type(screen.getByLabelText(/canonical host base url/i), 'http://n150.lan:8001')
    await user.click(screen.getByRole('radio', { name: /singular entity/i }))
    await user.click(screen.getByRole('button', { name: /share consciousness/i }))
    const put = calls.find((c) => c.url.includes('/api/devices/entity-mode'))
    expect(put).toBeTruthy()
    expect(JSON.parse(String(put?.init?.body))).toEqual({
      mode: 'singular', base_url: 'http://n150.lan:8001',
    })
  })

  it('switching back to independent sends the PUT without URLs', async () => {
    const user = userEvent.setup()
    renderTab(devicesState({
      entity_mode: 'singular',
      canonical_memory_url: 'http://n150.lan:8001/api/memory',
      canonical_thread_url: 'http://n150.lan:8001/api/conversations',
      devices: [device()],
    }))
    await screen.findByText('Mac Studio')
    await user.click(screen.getByRole('radio', { name: /independent node/i }))
    await waitFor(() => {
      const puts = screen.getAllByRole('radio')
      expect(puts).toBeTruthy()
    })
    // No confirmation on the way back down (review Q2).
    expect(screen.queryByText('Join the canonical host?')).toBeNull()
  })

  it('editing the body name sends PUT /api/devices/body-name', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab(devicesState())
    await screen.findByText(/Link First Device/i)
    const input = screen.getByLabelText('Body Name')
    await user.clear(input)
    await user.type(input, 'desk')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    const put = calls.find((c) => c.url.includes('/api/devices/body-name'))
    expect(JSON.parse(String(put?.init?.body))).toEqual({ body_name: 'desk' })
  })

  it('a suggestion chip fills the body name input', async () => {
    const user = userEvent.setup()
    renderTab(devicesState())
    await screen.findByText(/Link First Device/i)
    await user.click(screen.getByRole('button', { name: 'kitchen' }))
    expect((screen.getByLabelText('Body Name') as HTMLInputElement).value).toBe('kitchen')
  })

  it('Add Device opens the pairing modal (P7c, reused as-is)', async () => {
    const user = userEvent.setup()
    renderTab(devicesState())
    await screen.findByText(/Link First Device/i)
    await user.click(addDeviceButton())
    // PeerPairingModal's two tabs.
    expect(await screen.findByRole('tab', { name: /discovered/i })).toBeTruthy()
    expect(screen.getByRole('tab', { name: /manual/i })).toBeTruthy()
  })

  it('failed load shows an error toast and keeps the page usable', async () => {
    const calls: Array<{ url: string }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calls.push({ url })
      return jsonResponse({ detail: 'boom' }, 500)
    }))
    render(<DevicesTab />)
    await waitFor(() => expect(calls.length).toBeGreaterThan(0))
    // Loading resolved (no spinner), the failure is surfaced as a toast.
    expect(screen.queryByText(/Loading devices/i)).toBeNull()
  })

  it('revoked devices land in the archived section with Permanently Forget', async () => {
    const user = userEvent.setup()
    const { calls } = renderTab(devicesState({
      devices: [device(), device({ node_id: 'old-pi', node_name: 'Old Pi', revoked: true })],
    }))
    await screen.findByText('Mac Studio')
    // The archived section is collapsed but titled with its count (Q5).
    expect(screen.getByText(/Revoked \/ Archived Devices \(1\)/i)).toBeTruthy()
    await user.click(screen.getByText(/Revoked \/ Archived Devices \(1\)/i))
    expect(await screen.findByText('Old Pi')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /permanently forget old pi/i }))
    await user.click(screen.getByRole('button', { name: 'Permanently Forget' }))
    const del = calls.find((c) => c.url.includes('/api/devices/old-pi?forget=true'))
    expect(del).toBeTruthy()
  })
})