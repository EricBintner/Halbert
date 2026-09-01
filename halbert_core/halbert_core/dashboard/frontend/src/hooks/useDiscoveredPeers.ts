// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * useDiscoveredPeers — hook that polls for mDNS-discovered Halbert peers.
 *
 * Implements finding C2 from the federated multi-node review.
 *
 * C2 — Extends the Instance Switcher (Phase 7), does not replace it.
 *      This hook feeds discovered peers into the existing InstanceSwitch
 *      dropdown (shell/PresencePill.tsx). Discovered peers appear
 *      alongside manually-paired instances, with an "mDNS" badge to
 *      distinguish them from "Manual" entries.
 *
 * The hook polls GET /api/peers/discovered every 10 seconds. mDNS
 * discovery is LAN-only (finding H9) — Tailscale peers use manual
 * pairing via the Instance Switcher's "Add Instance" form.
 *
 * If zeroconf is not installed on the backend (finding H10), the
 * endpoint returns an empty array and this hook silently degrades —
 * the user can still manually pair via the Instance Switcher.
 */

import { useState, useEffect, useCallback } from 'react'
import { listDiscoveredPeers, type DiscoveredPeer } from '@/lib/peerApi'

const POLL_INTERVAL_MS = 10_000  // 10 seconds

export interface UseDiscoveredPeersResult {
  /** Peers discovered via mDNS on the local LAN. */
  peers: DiscoveredPeer[]
  /** True while the initial fetch is in progress. */
  loading: boolean
  /** Error message if the last fetch failed (null if OK). */
  error: string | null
  /** Manually trigger a refresh (e.g., after pairing). */
  refresh: () => void
}

/**
 * Poll for mDNS-discovered Halbert peers.
 *
 * @param enabled If false, the hook does not poll. Useful for
 *                conditionally enabling discovery only when the
 *                Instance Switcher dropdown is open.
 */
export function useDiscoveredPeers(enabled: boolean = true): UseDiscoveredPeersResult {
  const [peers, setPeers] = useState<DiscoveredPeer[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const fetchPeers = useCallback(async () => {
    try {
      const discovered = await listDiscoveredPeers()
      setPeers(discovered)
      setError(null)
    } catch (err) {
      // Non-fatal — mDNS may be unavailable (H10: zeroconf not installed)
      setError(err instanceof Error ? err.message : 'Failed to fetch discovered peers')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }

    // Initial fetch
    fetchPeers()

    // Poll every 10 seconds
    const interval = setInterval(fetchPeers, POLL_INTERVAL_MS)

    return () => clearInterval(interval)
  }, [enabled, fetchPeers])

  return {
    peers,
    loading,
    error,
    refresh: fetchPeers,
  }
}
