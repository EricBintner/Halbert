// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * DiscoveredPeerCard — renders a single mDNS-discovered peer with Pair button.
 *
 * Referenced in §11.2 Storybook Verification list alongside NodeFleetCockpit
 * and PeerPairingModal. This component is extracted from the inline row
 * rendering in PeerPairingModal for reuse and Storybook isolation.
 *
 * Shows:
 * - Node name and endpoint (font-mono)
 * - Compute backends as badges (ollama, vllm — apple_foundation is never advertised)
 * - Capabilities as badges
 * - Pair button (starts the handshake), then a PIN field
 *
 * The handshake is deliberately two steps with a person in between: the
 * other machine shows a PIN once someone there approves the request, and
 * that PIN is typed in here. This card used to auto-verify with a PIN the
 * server handed back in the pairing response ("development mode"), which
 * made pairing self-service — see SE-16 / R10-F1.
 *
 * Design notes:
 * - No emojis (per global rules) — uses lucide-react icons
 * - Status color: discovered (unpaired) peers use a neutral blue accent
 */

import { useState } from 'react'
import { Radio, Loader2, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  requestPairing, verifyPairing, setPeerToken,
  type DiscoveredPeer, type PairResponse,
} from '@/lib/peerApi'

interface DiscoveredPeerCardProps {
  /** The discovered peer to render. */
  peer: DiscoveredPeer
  /** Called after pairing succeeds (triggers a refresh of the peers list). */
  onPaired: () => void
  /** Called after pairing succeeds (closes the parent modal). */
  onClose: () => void
}

export function DiscoveredPeerCard({ peer, onPaired, onClose }: DiscoveredPeerCardProps) {
  const [pairing, setPairing] = useState(false)
  const [pairResponse, setPairResponse] = useState<PairResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pin, setPin] = useState('')

  const handlePair = async () => {
    setPairing(true)
    setError(null)
    try {
      const resp = await requestPairing({
        node_id: peer.node_id,
        node_name: peer.node_name,
        role: peer.role,
        capabilities: peer.capabilities,
        endpoint: peer.endpoint,
      })
      setPairResponse(resp)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pairing failed')
    } finally {
      setPairing(false)
    }
  }

  const handleConfirm = async () => {
    if (!pairResponse) return
    setPairing(true)
    setError(null)
    try {
      const verified = await verifyPairing({
        request_id: pairResponse.request_id,
        pin: pin.trim(),
        node_id: peer.node_id,
      })
      setPeerToken(verified.token)
      onPaired()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pairing failed')
    } finally {
      setPairing(false)
    }
  }

  return (
    <div className="flex items-center gap-2 p-2 rounded border border-border hover:border-primary/30 transition-colors">
      <Radio className="h-4 w-4 text-info shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium truncate">{peer.node_name}</p>
        <p className="text-[10px] text-muted-foreground font-mono truncate">
          {peer.endpoint}
        </p>
        {peer.compute_backends.length > 0 && (
          <div className="flex flex-wrap gap-0.5 mt-0.5">
            {peer.compute_backends.map((backend) => (
              <Badge key={backend} variant="outline" className="text-[8px] px-1 py-0">
                {backend}
              </Badge>
            ))}
          </div>
        )}
      </div>
      {pairResponse ? (
        <div className="flex items-center gap-1 shrink-0">
          <label className="sr-only" htmlFor={`pin-${peer.node_id}`}>
            PIN shown on {peer.node_name}
          </label>
          <input
            id={`pin-${peer.node_id}`}
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            inputMode="numeric"
            maxLength={4}
            placeholder="PIN"
            className="h-7 w-14 rounded border border-border bg-background px-1 text-center text-[11px] font-mono"
          />
          <Button
            size="sm"
            className="h-7 text-[10px]"
            onClick={handleConfirm}
            disabled={pairing || pin.trim().length !== 4}
          >
            {pairing ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <>
                <Check className="h-3 w-3 mr-1" />
                Confirm
              </>
            )}
          </Button>
        </div>
      ) : (
        <Button
          size="sm"
          className="h-7 text-[10px] shrink-0"
          onClick={handlePair}
          disabled={pairing}
        >
          {pairing ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Pair'}
        </Button>
      )}
      {error && (
        <span className="text-[9px] text-destructive">{error}</span>
      )}
    </div>
  )
}
