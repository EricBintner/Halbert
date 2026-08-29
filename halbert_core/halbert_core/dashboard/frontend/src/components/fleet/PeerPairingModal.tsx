// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * PeerPairingModal — discovered peers list + one-click pairing + PIN confirmation.
 *
 * Implements findings C1, C2, and H9 from the federated multi-node review.
 *
 * C1 — The pairing flow uses the same token system as MCP Phase 4b.
 *      The modal calls POST /api/peers/pair → gets a PIN → the user
 *      confirms → POST /api/peers/verify → gets a bearer token.
 *
 * C2 — This modal is opened from the InstanceSwitch dropdown's "Pair"
 *      button and from the NodeFleetCockpit's empty state. It does NOT
 *      replace InstanceSwitch — it's a child dialog that feeds paired
 *      peers back into the switcher.
 *
 * H9 — mDNS discovery is LAN-only. Discovered peers appear in the list
 *      only if zeroconf is installed and both nodes are on the same LAN.
 *      For Tailscale, the user uses the "Manual Pair" tab to enter the
 *      peer's URL directly.
 *
 * §11.2 — DiscoveredPeerCard is extracted to its own component for
 *      Storybook isolation. This modal imports and uses it instead of
 *      an inline row component.
 *
 * Design:
 * - Two tabs: "Discovered" (mDNS list) and "Manual" (URL + token entry)
 * - Discovered tab: list of DiscoveredPeerCard components
 * - Manual tab: URL input + optional token (for pre-shared token pairing)
 * - PIN confirmation step: 4-digit PIN displayed for the user to confirm
 * - No emojis (per global rules) — uses lucide-react icons
 */

import * as React from 'react'
import { useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Radio, Search, Link2, Loader2 } from 'lucide-react'
import { useDiscoveredPeers } from '@/hooks/useDiscoveredPeers'
import { DiscoveredPeerCard } from './DiscoveredPeerCard'

interface PeerPairingModalProps {
  /** Called when the modal is closed (X button or backdrop click). */
  onClose: () => void
  /** Called after a peer is successfully paired (triggers a refresh). */
  onPaired: () => void
}

export function PeerPairingModal({ onClose, onPaired }: PeerPairingModalProps) {
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <Radio className="h-4 w-4" />
            Pair Halbert Peer
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="discovered">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="discovered" className="text-xs">
              <Search className="h-3 w-3 mr-1" />
              Discovered
            </TabsTrigger>
            <TabsTrigger value="manual" className="text-xs">
              <Link2 className="h-3 w-3 mr-1" />
              Manual
            </TabsTrigger>
          </TabsList>

          {/* mDNS-discovered peers (LAN only — finding H9) */}
          <TabsContent value="discovered" className="space-y-2">
            <DiscoveredPeersList onClose={onClose} onPaired={onPaired} />
          </TabsContent>

          {/* Manual pairing (Tailscale or no mDNS — finding H9) */}
          <TabsContent value="manual" className="space-y-3">
            <ManualPairingForm onClose={onClose} onPaired={onPaired} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Discovered peers list (mDNS) — uses extracted DiscoveredPeerCard (§11.2)
// ---------------------------------------------------------------------------

function DiscoveredPeersList({ onClose, onPaired }: { onClose: () => void; onPaired: () => void }) {
  const { peers, loading, error } = useDiscoveredPeers(true)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-xs text-muted-foreground py-4 text-center space-y-1">
        <p>mDNS discovery unavailable</p>
        <p className="text-[10px]">
          Install zeroconf on the backend or use Manual pairing for Tailscale peers.
        </p>
      </div>
    )
  }

  if (peers.length === 0) {
    return (
      <div className="text-xs text-muted-foreground py-6 text-center space-y-1">
        <p>No Halbert peers discovered on this LAN</p>
        <p className="text-[10px]">
          Ensure the peer is running and on the same network.
          For Tailscale, use Manual pairing.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-1.5 max-h-64 overflow-y-auto">
      {peers.map((peer) => (
        <DiscoveredPeerCard
          key={peer.node_id}
          peer={peer}
          onClose={onClose}
          onPaired={onPaired}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Manual pairing (Tailscale / no mDNS)
// ---------------------------------------------------------------------------

function ManualPairingForm({ onClose, onPaired }: { onClose: () => void; onPaired: () => void }) {
  const [nodeId, setNodeId] = useState('')
  const [endpoint, setEndpoint] = useState('http://')
  const [pairing, setPairing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!nodeId.trim() || !endpoint.trim()) return

    setPairing(true)
    setError(null)
    try {
      // Manual pairing = request pairing with the remote Desktop
      // TODO(federation-9.1): For manual pairing, the flow is reversed —
      // the user enters the Desktop's URL and this node requests pairing
      // with it. The PIN is displayed on the Desktop and the user enters
      // it here. For now, this is a scaffold — the actual flow needs
      // the PIN entry step.
      //
      // For the Instance Switcher's existing "Add Instance" flow (which
      // just stores the endpoint without pairing), see InstanceSwitch.tsx.
      // This form is for the full pairing flow with token exchange.
      throw new Error('Manual pairing flow — TODO(federation-9.1)')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Manual pairing failed')
    } finally {
      setPairing(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="space-y-1">
        <label className="text-[10px] text-muted-foreground uppercase tracking-wider">
          Peer Node ID
        </label>
        <Input
          value={nodeId}
          onChange={(e) => setNodeId(e.target.value)}
          placeholder="e.g., studio-mac"
          className="h-8 text-xs"
        />
      </div>
      <div className="space-y-1">
        <label className="text-[10px] text-muted-foreground uppercase tracking-wider">
          Peer Endpoint (URL)
        </label>
        <Input
          value={endpoint}
          onChange={(e) => setEndpoint(e.target.value)}
          placeholder="http://desktop.lan:8000 or http://desktop.tailnet.ts.net:8000"
          className="h-8 text-xs font-mono"
        />
        <p className="text-[9px] text-muted-foreground">
          For Tailscale peers, use the Tailscale hostname or IP.
          mDNS does not cross Tailscale tunnels.
        </p>
      </div>
      {error && (
        <div className="text-[10px] text-destructive bg-destructive/10 rounded px-2 py-1">
          {error}
        </div>
      )}
      <DialogFooter>
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={pairing || !nodeId.trim() || !endpoint.trim()}>
          {pairing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Pair'}
        </Button>
      </DialogFooter>
    </form>
  )
}
