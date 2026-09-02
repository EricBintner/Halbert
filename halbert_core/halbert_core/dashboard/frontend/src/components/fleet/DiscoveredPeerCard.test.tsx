// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * DiscoveredPeerCard tests (FE-15 audit cleanup) — covers the two-step
 * pairing handshake: Pair kicks off requestPairing() and swaps the button
 * row for a PIN field, Confirm calls verifyPairing() and stores the token,
 * and a failure at either step surfaces inline instead of throwing.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DiscoveredPeerCard } from './DiscoveredPeerCard'
import type { DiscoveredPeer, PairResponse, VerifyResponse } from '@/lib/peerApi'

vi.mock('@/lib/peerApi', () => ({
  requestPairing: vi.fn(),
  verifyPairing: vi.fn(),
  setPeerToken: vi.fn(),
}))

import { requestPairing, verifyPairing, setPeerToken } from '@/lib/peerApi'

const requestPairingMock = vi.mocked(requestPairing)
const verifyPairingMock = vi.mocked(verifyPairing)
const setPeerTokenMock = vi.mocked(setPeerToken)

function peer(overrides: Partial<DiscoveredPeer> = {}): DiscoveredPeer {
  return {
    node_id: 'pi-1',
    node_name: 'kitchen-pi',
    role: 'satellite',
    host: '192.168.1.50',
    port: 8000,
    endpoint: 'http://192.168.1.50:8000',
    capabilities: ['telemetry'],
    compute_backends: ['ollama'],
    ...overrides,
  }
}

const PAIR_RESPONSE: PairResponse = {
  request_id: 'req-1',
  status: 'pending',
  expires_in: 120,
  message: 'Enter the PIN shown on kitchen-pi',
}

const VERIFY_RESPONSE: VerifyResponse = {
  token: 'tok-abc',
  status: 'paired',
  desktop_node_id: 'desk-1',
}

describe('DiscoveredPeerCard', () => {
  it('renders the node name, endpoint, and compute backend badges', () => {
    render(<DiscoveredPeerCard peer={peer()} onPaired={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText('kitchen-pi')).toBeTruthy()
    expect(screen.getByText('http://192.168.1.50:8000')).toBeTruthy()
    expect(screen.getByText('ollama')).toBeTruthy()
  })

  it('omits the backend badge row when no compute backends are advertised', () => {
    render(
      <DiscoveredPeerCard
        peer={peer({ compute_backends: [] })}
        onPaired={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(screen.queryByText('ollama')).toBeNull()
  })

  it('clicking Pair requests pairing with the peer identity and reveals the PIN field', async () => {
    const user = userEvent.setup()
    requestPairingMock.mockResolvedValue(PAIR_RESPONSE)
    render(<DiscoveredPeerCard peer={peer()} onPaired={vi.fn()} onClose={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Pair' }))

    expect(requestPairingMock).toHaveBeenCalledWith({
      node_id: 'pi-1',
      node_name: 'kitchen-pi',
      role: 'satellite',
      capabilities: ['telemetry'],
      endpoint: 'http://192.168.1.50:8000',
    })
    expect(await screen.findByLabelText('PIN shown on kitchen-pi')).toBeTruthy()
    expect(screen.getByRole('button', { name: /confirm/i })).toBeTruthy()
  })

  it('disables Confirm until a 4-digit PIN is entered', async () => {
    const user = userEvent.setup()
    requestPairingMock.mockResolvedValue(PAIR_RESPONSE)
    render(<DiscoveredPeerCard peer={peer()} onPaired={vi.fn()} onClose={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Pair' }))

    const confirmButton = await screen.findByRole('button', { name: /confirm/i })
    expect(confirmButton).toBeDisabled()

    const pinField = screen.getByLabelText('PIN shown on kitchen-pi')
    await user.type(pinField, '12')
    expect(confirmButton).toBeDisabled()

    await user.type(pinField, '34')
    expect(confirmButton).toBeEnabled()
  })

  it('confirming a valid PIN verifies pairing, stores the token, and closes the card', async () => {
    const user = userEvent.setup()
    const onPaired = vi.fn()
    const onClose = vi.fn()
    requestPairingMock.mockResolvedValue(PAIR_RESPONSE)
    verifyPairingMock.mockResolvedValue(VERIFY_RESPONSE)
    render(<DiscoveredPeerCard peer={peer()} onPaired={onPaired} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Pair' }))
    await user.type(await screen.findByLabelText('PIN shown on kitchen-pi'), '4821')
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    await waitFor(() =>
      expect(verifyPairingMock).toHaveBeenCalledWith({
        request_id: 'req-1',
        pin: '4821',
        node_id: 'pi-1',
      }),
    )
    expect(setPeerTokenMock).toHaveBeenCalledWith('tok-abc')
    expect(onPaired).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('shows an inline error and falls back to the Pair button when pairing fails', async () => {
    const user = userEvent.setup()
    requestPairingMock.mockRejectedValue(new Error('peer unreachable'))
    render(<DiscoveredPeerCard peer={peer()} onPaired={vi.fn()} onClose={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Pair' }))

    expect(await screen.findByText('peer unreachable')).toBeTruthy()
    // No PIN field to be confirmed — the card resets to the initial action.
    expect(screen.getByRole('button', { name: 'Pair' })).toBeTruthy()
  })

  it('shows an inline error on failed PIN verification without calling onPaired or onClose', async () => {
    const user = userEvent.setup()
    const onPaired = vi.fn()
    const onClose = vi.fn()
    requestPairingMock.mockResolvedValue(PAIR_RESPONSE)
    verifyPairingMock.mockRejectedValue(new Error('incorrect PIN'))
    render(<DiscoveredPeerCard peer={peer()} onPaired={onPaired} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Pair' }))
    await user.type(await screen.findByLabelText('PIN shown on kitchen-pi'), '0000')
    await user.click(screen.getByRole('button', { name: /confirm/i }))

    expect(await screen.findByText('incorrect PIN')).toBeTruthy()
    expect(onPaired).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })
})
