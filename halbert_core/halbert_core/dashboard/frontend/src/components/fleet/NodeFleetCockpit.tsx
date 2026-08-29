// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * NodeFleetCockpit — fleet status grid for the Desktop's Fleet Cockpit view.
 *
 * Implements finding C2 from the federated multi-node review.
 *
 * C2 — This is the "Fleet Cockpit" from Pillar 4 of the handoff, but it
 *      is NOT a new "Node Switcher." The node switching UI is the
 *      existing InstanceSwitch.tsx (Phase 7). This component is the
 *      fleet *monitoring* view — a grid of satellite status cards
 *      showing CPU, RAM, temperature, uptime, and active services.
 *
 * The component fetches fleet node status from GET /api/fleet/nodes
 * (which proxies to each satellite's MCP server per finding C5) and
 * renders a card per node. Clicking a card opens a detail panel with
 * remote inspection capabilities (MCP tool proxy).
 *
 * Design notes:
 * - No emojis (per global rules) — uses lucide-react icons
 * - Status colors: green (online), amber (degraded), red (offline)
 * - Auto-refreshes every 15 seconds
 * - Graceful degradation: if no peers are paired, shows an empty state
 *   with a "Pair a Satellite" CTA that opens PeerPairingModal
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Cpu, MemoryStick, Thermometer, Clock,
  Server, Wifi, WifiOff, RefreshCw, Plus,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  listFleetNodes, type FleetNodeStatus,
} from '@/lib/peerApi'
import { PeerPairingModal } from './PeerPairingModal'

const REFRESH_INTERVAL_MS = 15_000

export function NodeFleetCockpit() {
  const [nodes, setNodes] = useState<FleetNodeStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showPairingModal, setShowPairingModal] = useState(false)
  const [selectedNode, setSelectedNode] = useState<FleetNodeStatus | null>(null)

  const refresh = useCallback(async () => {
    try {
      const fleetNodes = await listFleetNodes()
      setNodes(fleetNodes)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch fleet nodes')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [refresh])

  // Empty state — no peers paired yet
  if (!loading && nodes.length === 0 && !error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <Server className="h-12 w-12 text-muted-foreground/50" />
        <div className="text-center space-y-1">
          <h3 className="text-sm font-medium">No satellites paired</h3>
          <p className="text-xs text-muted-foreground max-w-sm">
            Pair a Raspberry Pi, homelab server, or laptop to monitor its
            health, stream logs, and offload compute to this machine's GPU.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowPairingModal(true)}>
          <Plus className="h-4 w-4 mr-1" />
          Pair a Satellite
        </Button>
        {showPairingModal && (
          <PeerPairingModal onClose={() => setShowPairingModal(false)} onPaired={refresh} />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Fleet Cockpit</h2>
          <Badge variant="secondary" className="text-[10px]">
            {nodes.filter(n => n.online).length}/{nodes.length} online
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={refresh} disabled={loading}>
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowPairingModal(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Pair
          </Button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="text-xs text-destructive bg-destructive/10 rounded px-3 py-2">
          {error}
        </div>
      )}

      {/* Node grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {nodes.map((node) => (
          <FleetNodeCard
            key={node.node_id}
            node={node}
            onClick={() => setSelectedNode(node)}
          />
        ))}
      </div>

      {/* Pairing modal */}
      {showPairingModal && (
        <PeerPairingModal onClose={() => setShowPairingModal(false)} onPaired={refresh} />
      )}

      {/* TODO(federation-9.9): Node detail panel with remote inspection
          (MCP tool proxy, log streaming, discovery snapshot) */}
      {selectedNode && (
        <div className="text-xs text-muted-foreground">
          Node detail panel for {selectedNode.node_name} — TODO(federation-9.9)
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Node card
// ---------------------------------------------------------------------------

function FleetNodeCard({
  node,
  onClick,
}: {
  node: FleetNodeStatus
  onClick: () => void
}) {
  const vitals = node.vitals
  const statusColor = node.online
    ? 'text-success'
    : 'text-muted-foreground'

  return (
    <Card
      className="cursor-pointer hover:border-primary/50 transition-colors"
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {node.online ? (
              <Wifi className={cn('h-4 w-4', statusColor)} />
            ) : (
              <WifiOff className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-xs font-medium truncate">{node.node_name}</span>
          </div>
          <Badge
            variant={node.online ? 'default' : 'outline'}
            className="text-[9px] uppercase"
          >
            {node.online ? 'Online' : 'Offline'}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="pb-2 space-y-1.5">
        {/* Vitals — only show if online and telemetry is available */}
        {node.online && vitals && (
          <>
            <VitalRow
              icon={<Cpu className="h-3 w-3" />}
              label="CPU"
              value={`${vitals.cpu_percent.toFixed(1)}%`}
              warn={vitals.cpu_percent > 80}
            />
            <VitalRow
              icon={<MemoryStick className="h-3 w-3" />}
              label="RAM"
              value={`${vitals.memory_percent.toFixed(1)}%`}
              warn={vitals.memory_percent > 85}
            />
            {vitals.temperature_c !== null && (
              <VitalRow
                icon={<Thermometer className="h-3 w-3" />}
                label="Temp"
                value={`${vitals.temperature_c.toFixed(0)}C`}
                warn={vitals.temperature_c > 70}
              />
            )}
            <VitalRow
              icon={<Clock className="h-3 w-3" />}
              label="Uptime"
              value={formatUptime(vitals.uptime_seconds)}
            />
          </>
        )}

        {/* Capabilities */}
        {node.capabilities.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {node.capabilities.map((cap) => (
              <Badge key={cap} variant="outline" className="text-[9px]">
                {cap}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-0">
        <span className="text-[9px] text-muted-foreground font-mono truncate">
          {node.endpoint || node.node_id}
        </span>
      </CardFooter>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function VitalRow({
  icon, label, value, warn,
}: {
  icon: React.ReactNode
  label: string
  value: string
  warn?: boolean
}) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-muted-foreground w-12">{label}</span>
      <span className={cn('font-mono', warn && 'text-amber-600 dark:text-amber-400')}>
        {value}
      </span>
    </div>
  )
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(0)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(0)}h`
  return `${(seconds / 86400).toFixed(0)}d`
}
