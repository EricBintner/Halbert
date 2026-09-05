// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * NodeFleetCockpit tests (FE-15 audit cleanup) — covers the fleet grid
 * built from listFleetNodes(): the empty "Link a body" state, node
 * cards (status badge, vitals, capabilities, footer endpoint), the 15s
 * auto-refresh poll (REFRESH_INTERVAL_MS), a fetch failure surfaced as a
 * banner, and the dual-action Inspect/Switch affordances (§11.2).
 *
 * PeerPairingModal is mocked out — it has its own mDNS-polling hook and
 * its own test surface (DiscoveredPeerCard.test.tsx); here it only needs
 * to prove NodeFleetCockpit opens/wires it correctly.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NodeFleetCockpit } from './NodeFleetCockpit'
import type { FleetNodeStatus } from '@/lib/peerApi'

vi.mock('@/lib/peerApi', () => ({
  listFleetNodes: vi.fn(),
}))

vi.mock('@/lib/apiBase', () => ({
  setInstanceEndpoint: vi.fn(),
}))

vi.mock('./PeerPairingModal', () => ({
  PeerPairingModal: ({ onClose, onPaired }: { onClose: () => void; onPaired: () => void }) => (
    <div>
      <p>Mock Peer Pairing Modal</p>
      <button onClick={onPaired}>mock pairing complete</button>
      <button onClick={onClose}>mock close</button>
    </div>
  ),
}))

import { listFleetNodes } from '@/lib/peerApi'
import { setInstanceEndpoint } from '@/lib/apiBase'

const listFleetNodesMock = vi.mocked(listFleetNodes)
const setInstanceEndpointMock = vi.mocked(setInstanceEndpoint)

const ONLINE_NODE: FleetNodeStatus = {
  node_id: 'n1',
  node_name: 'kitchen-pi',
  role: 'satellite',
  endpoint: 'http://kitchen.lan:8000',
  online: true,
  last_seen: '2026-09-01T12:00:00Z',
  capabilities: ['telemetry', 'gpu_llm'],
  vitals: {
    cpu_percent: 12.3,
    memory_percent: 45.6,
    memory_available_mb: 2048,
    temperature_c: 55.2,
    uptime_seconds: 3661,
    load_average_1m: 0.5,
    disk_percent: 30,
  },
  discovery_count: 2,
}

const OFFLINE_NODE: FleetNodeStatus = {
  node_id: 'n2',
  node_name: 'garage-node',
  role: 'compute_provider',
  endpoint: null,
  online: false,
  last_seen: null,
  capabilities: [],
  vitals: null,
  discovery_count: 0,
}

describe('NodeFleetCockpit', () => {
  it('renders the empty state with a Link a body CTA and opens the pairing modal', async () => {
    const user = userEvent.setup()
    listFleetNodesMock.mockResolvedValue([])
    render(<NodeFleetCockpit />)

    expect(await screen.findByText('No other bodies yet')).toBeTruthy()
    expect(screen.getByText(/link a raspberry pi, homelab server, or laptop/i)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: /link a body/i }))
    expect(await screen.findByText('Mock Peer Pairing Modal')).toBeTruthy()
  })

  it('renders a fleet grid with per-node status, vitals, capabilities, and the online ratio', async () => {
    listFleetNodesMock.mockResolvedValue([ONLINE_NODE, OFFLINE_NODE])
    render(<NodeFleetCockpit />)

    expect(await screen.findByText('kitchen-pi')).toBeTruthy()
    expect(screen.getByText('1/2 online')).toBeTruthy()

    // Online node: status badge, vitals, capability badges, endpoint footer.
    expect(screen.getByText('Online')).toBeTruthy()
    expect(screen.getByText('12.3%')).toBeTruthy()
    expect(screen.getByText('45.6%')).toBeTruthy()
    expect(screen.getByText('55C')).toBeTruthy()
    expect(screen.getByText('1h')).toBeTruthy()
    expect(screen.getByText('telemetry')).toBeTruthy()
    expect(screen.getByText('gpu_llm')).toBeTruthy()
    expect(screen.getByText('http://kitchen.lan:8000')).toBeTruthy()

    // Offline node: status badge, no vitals, endpoint falls back to node_id.
    expect(screen.getByText('garage-node')).toBeTruthy()
    expect(screen.getByText('Offline')).toBeTruthy()
    expect(screen.getByText('n2')).toBeTruthy()
  })

  it('surfaces a fetch error in a banner while still rendering the grid shell', async () => {
    listFleetNodesMock.mockRejectedValue(new Error('Fleet nodes failed: 500'))
    render(<NodeFleetCockpit />)

    expect(await screen.findByText('Fleet nodes failed: 500')).toBeTruthy()
    expect(screen.getByText('Fleet Cockpit')).toBeTruthy()
    expect(screen.getByText('0/0 online')).toBeTruthy()
  })

  it('the header Refresh button re-fetches the node list', async () => {
    const user = userEvent.setup()
    listFleetNodesMock.mockResolvedValue([ONLINE_NODE])
    render(<NodeFleetCockpit />)
    await screen.findByText('kitchen-pi')
    expect(listFleetNodesMock).toHaveBeenCalledTimes(1)

    const headerRow = screen.getByRole('heading', { name: 'Fleet Cockpit' })
      .parentElement!.parentElement!
    const [refreshButton] = within(headerRow).getAllByRole('button')
    await user.click(refreshButton)

    expect(listFleetNodesMock).toHaveBeenCalledTimes(2)
  })

  it('polls the fleet list automatically every 15 seconds', async () => {
    listFleetNodesMock.mockResolvedValue([ONLINE_NODE])
    vi.useFakeTimers()
    try {
      render(<NodeFleetCockpit />)
      await act(async () => {}) // let the mount-time load settle
      expect(listFleetNodesMock).toHaveBeenCalledTimes(1)

      await act(async () => {
        vi.advanceTimersByTime(15_000)
      })
      expect(listFleetNodesMock).toHaveBeenCalledTimes(2)

      await act(async () => {
        vi.advanceTimersByTime(15_000)
      })
      expect(listFleetNodesMock).toHaveBeenCalledTimes(3)
    } finally {
      vi.useRealTimers()
    }
  })

  it('Switch Active Context calls setInstanceEndpoint with the node endpoint', async () => {
    const user = userEvent.setup()
    listFleetNodesMock.mockResolvedValue([ONLINE_NODE])
    render(<NodeFleetCockpit />)
    await screen.findByText('kitchen-pi')

    await user.click(screen.getByRole('button', { name: /switch/i }))
    expect(setInstanceEndpointMock).toHaveBeenCalledWith('http://kitchen.lan:8000')
  })

  it('disables Inspect and Switch for an offline node with no endpoint', async () => {
    listFleetNodesMock.mockResolvedValue([OFFLINE_NODE])
    render(<NodeFleetCockpit />)
    await screen.findByText('garage-node')

    expect(screen.getByRole('button', { name: /inspect/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /switch/i })).toBeDisabled()
  })

  it('clicking Inspect opens the diagnostic drawer and Close hides it', async () => {
    const user = userEvent.setup()
    const nodeWithoutCapabilities: FleetNodeStatus = {
      ...ONLINE_NODE,
      capabilities: [],
    }
    listFleetNodesMock.mockResolvedValue([nodeWithoutCapabilities])
    render(<NodeFleetCockpit />)
    await screen.findByText('kitchen-pi')

    await user.click(screen.getByRole('button', { name: /inspect/i }))
    expect(await screen.findByText(/remote inspection via mcp proxy/i)).toBeTruthy()
    expect(screen.getByText('None advertised')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByText(/remote inspection via mcp proxy/i)).toBeNull()
  })

  it('the header Pair button opens the pairing modal, and onPaired triggers a refresh', async () => {
    const user = userEvent.setup()
    listFleetNodesMock.mockResolvedValue([ONLINE_NODE])
    render(<NodeFleetCockpit />)
    await screen.findByText('kitchen-pi')
    expect(listFleetNodesMock).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Pair' }))
    expect(await screen.findByText('Mock Peer Pairing Modal')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'mock pairing complete' }))
    expect(listFleetNodesMock).toHaveBeenCalledTimes(2)
  })
})
