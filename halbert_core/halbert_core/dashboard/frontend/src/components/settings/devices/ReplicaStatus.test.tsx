// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ReplicaStatus card: nothing without a replica, freshness + counts with
 * one, a deliberate manual promote behind a naming confirmation.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReplicaStatus } from './ReplicaStatus'
import type { ReplicaStatus as ReplicaStatusData } from '@/lib/peerApi'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

function replicaStatus(overrides: Partial<ReplicaStatusData> = {}): ReplicaStatusData {
  return {
    has_replica: true,
    is_valid: true,
    can_promote: true,
    canonical_reachable: true,
    replica: {
      source_node_id: 'halbert-mac',
      created_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
      received_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
      memory_count: 2847,
      thread_count: 156,
      file_digests: {},
    },
    ...overrides,
  }
}

function renderCard(status: ReplicaStatusData | null) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url === '/api/replica/status') {
      return jsonResponse(status ?? { has_replica: false, is_valid: false, can_promote: false, replica: null })
    }
    if (url === '/api/replica/promote') {
      return jsonResponse({
        status: 'promoted', old_canonical_url: 'http://dead:8000',
        replica_timestamp: '', memory_count: 2847, thread_count: 156,
        quarantined: [],
      })
    }
    return jsonResponse({})
  }))
  render(<ReplicaStatus />)
  return { calls }
}

afterEach(() => vi.unstubAllGlobals())

describe('ReplicaStatus', () => {
  it('renders nothing when there is no replica', async () => {
    renderCard(null)
    await waitFor(() => {
      expect(screen.queryByText(/warm standby/i)).not.toBeInTheDocument()
    })
  })

  it('shows freshness and counts when a replica exists', async () => {
    renderCard(replicaStatus())
    expect(await screen.findByText(/2 hours ago/)).toBeInTheDocument()
    expect(screen.getByText(/2,847 memories/)).toBeInTheDocument()
    expect(screen.getByText(/156 threads/)).toBeInTheDocument()
    expect(screen.getByText(/halbert-mac/)).toBeInTheDocument()
  })

  it('shows the unreachable banner when the canonical is dark', async () => {
    renderCard(replicaStatus({ canonical_reachable: false }))
    expect(await screen.findByText(/canonical host is unreachable/)).toBeInTheDocument()
    expect(screen.getByText(/local replica from 2 hours ago/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /promote/i })).toBeInTheDocument()
  })

  it('warns instead of offering promote when the replica fails integrity', async () => {
    renderCard(replicaStatus({ is_valid: false, can_promote: false }))
    expect(await screen.findByText(/failed its integrity check/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /promote/i })).not.toBeInTheDocument()
  })

  it('promotes only after the confirmation names what happens', async () => {
    const { calls } = renderCard(replicaStatus())
    await screen.findByText(/2 hours ago/)

    await userEvent.click(screen.getByRole('button', { name: /promote/i }))
    // The dialog names the replica's contents and the consequence.
    expect(await screen.findByText(/becomes the mind's home/)).toBeInTheDocument()
    expect(calls.filter((c) => c.url === '/api/replica/promote')).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: /^promote$/i }))
    await waitFor(() => {
      expect(calls.filter((c) => c.url === '/api/replica/promote')).toHaveLength(1)
    })
  })
})
