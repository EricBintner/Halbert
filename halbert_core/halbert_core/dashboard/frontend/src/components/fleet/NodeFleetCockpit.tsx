// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * NodeFleetCockpit — fleet status grid for the Desktop's Fleet Cockpit view.
 *
 * Implements findings C2 and §11.2 from the federated multi-node review.
 *
 * C2 — This is the "Fleet Cockpit" from Pillar 4 of the handoff, but it
 *      is NOT a new "Node Switcher." The node switching UI is the
 *      existing InstanceSwitch.tsx (Phase 7). This component is the
 *      fleet *monitoring* view — a grid of satellite status cards
 *      showing CPU, RAM, temperature, uptime, and active services.
 *
 * §11.2 Dual-Action Node Interaction:
 *      Clicking a node card offers two clear affordances:
 *      - [Inspect Node] (Default): Slides open a diagnostic drawer powered
 *        by fleet_proxy.py (Desktop as MCP client of the satellite) without
 *        interrupting the user's active desktop conversation or workflow.
 *      - [Switch Active Context]: Invokes setInstanceEndpoint(), transitioning
 *        the full desktop UI to directly interface with that node's dashboard.
 *
 * §11.2 StatusBadge variants:
 *      - online: emerald/green
 *      - fallback: amber/yellow (peer offline, running on local model)
 *      - offline: slate/red
 *
 * Design notes:
 * - No emojis (per global rules) — uses lucide-react icons
 * - Auto-refreshes every 15 seconds
 * - Graceful degradation: if no peers are paired, shows an empty state
 *   with a "Pair a Satellite" CTA that opens PeerPairingModal
 */

import * as React from 'react'
import { useState, useEffect, useCallback } from 'react'
import {
  Cpu, MemoryStick, Thermometer, Clock,
  Server, Wifi, WifiOff, RefreshCw, Plus,
  Search, ArrowRightLeft,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { setInstanceEndpoint } from '@/lib/apiBase'
import {
  listFleetNodes, type FleetNodeStatus,
} from '@/lib/peerApi'
import { PeerPairingModal } from './PeerPairingModal'

const REFRESH_INTERVAL_MS = 15_000

/** §11.2 StatusBadge variant — determines color from node state. */
type NodeStatus = 'online' | 'fallback' | 'offline'

function getNodeStatus(node: FleetNodeStatus): NodeStatus {
  if (node.online) return 'online'
  // TODO(federation-9.9): When telemetry includes fallback state, distinguish
  // 'fallback' (peer offline, running on local model) from 'offline' (no
  // response at all). For now, offline = not online.
  return 'offline'
}

const STATUS_STYLES: Record<NodeStatus, { badge: string; icon: string; label: string }> = {
  online: {
    badge: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
    icon: 'text-emerald-600 dark:text-emerald-400',
    label: 'Online',
  },
  fallback: {
    badge: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30',
    icon: 'text-amber-600 dark:text-amber-400',
    label: 'Fallback',
  },
  offline: {
    badge: 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30',
    icon: 'text-slate-500 dark:text-slate-400',
    label: 'Offline',
  },
}

export function NodeFleetCockpit() {
  const [nodes, setNodes] = useState<FleetNodeStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showPairingModal, setShowPairingModal] = useState(false)
  const [inspectedNode, setInspectedNode] = useState<FleetNodeStatus | null>(null)

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

  // §11.2: Switch Active Context — retargets the full desktop UI to the node
  const handleSwitchContext = (node: FleetNodeStatus) => {
    if (node.endpoint) {
      setInstanceEndpoint(node.endpoint)
    }
  }

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
            onInspect={() => setInspectedNode(node)}
            onSwitchContext={() => handleSwitchContext(node)}
          />
        ))}
      </div>

      {/* Pairing modal */}
      {showPairingModal && (
        <PeerPairingModal onClose={() => setShowPairingModal(false)} onPaired={refresh} />
      )}

      {/* §11.2: Inspect Node drawer — TODO(federation-9.9)
          Slides open a diagnostic drawer powered by fleet_proxy.py
          (Desktop as MCP client of the satellite) without interrupting
          the user's active desktop conversation or workflow. */}
      {inspectedNode && (
        <NodeInspectDrawer
          node={inspectedNode}
          onClose={() => setInspectedNode(null)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Node card — §11.2 dual-action (Inspect + Switch Context)
// ---------------------------------------------------------------------------

function FleetNodeCard({
  node,
  onInspect,
  onSwitchContext,
}: {
  node: FleetNodeStatus
  onInspect: () => void
  onSwitchContext: () => void
}) {
  const vitals = node.vitals
  const status = getNodeStatus(node)
  const statusStyle = STATUS_STYLES[status]

  return (
    <Card className="hover:border-primary/50 transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {node.online ? (
              <Wifi className={cn('h-4 w-4', statusStyle.icon)} />
            ) : (
              <WifiOff className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-xs font-medium truncate">{node.node_name}</span>
          </div>
          <Badge className={cn('text-[9px] uppercase border', statusStyle.badge)}>
            {statusStyle.label}
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

      <CardFooter className="pt-0 flex items-center justify-between gap-2">
        <span className="text-[9px] text-muted-foreground font-mono truncate flex-1">
          {node.endpoint || node.node_id}
        </span>
        {/* §11.2: Dual-action buttons */}
        <div className="flex items-center gap-1 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-[10px]"
            onClick={onInspect}
            disabled={!node.online}
          >
            <Search className="h-3 w-3 mr-0.5" />
            Inspect
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-[10px]"
            onClick={onSwitchContext}
            disabled={!node.endpoint}
          >
            <ArrowRightLeft className="h-3 w-3 mr-0.5" />
            Switch
          </Button>
        </div>
      </CardFooter>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// §11.2: Inspect Node drawer — diagnostic panel via MCP proxy
// ---------------------------------------------------------------------------

function NodeInspectDrawer({
  node,
  onClose,
}: {
  node: FleetNodeStatus
  onClose: () => void
}) {
  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md border-l bg-card shadow-lg">
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4" />
          <span className="text-sm font-medium">{node.node_name}</span>
          <Badge className={cn('text-[9px] uppercase border', STATUS_STYLES[getNodeStatus(node)].badge)}>
            {STATUS_STYLES[getNodeStatus(node)].label}
          </Badge>
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      <div className="p-4 space-y-3">
        <p className="text-xs text-muted-foreground">
          Remote inspection via MCP proxy (C5). The Desktop connects as an
          MCP client of this satellite's MCP server.
        </p>
        <div className="space-y-2">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Endpoint
          </div>
          <code className="text-xs font-mono block bg-muted/50 rounded px-2 py-1">
            {node.endpoint || 'N/A'}
          </code>
        </div>
        <div className="space-y-2">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Capabilities
          </div>
          <div className="flex flex-wrap gap-1">
            {node.capabilities.length > 0 ? (
              node.capabilities.map((cap) => (
                <Badge key={cap} variant="outline" className="text-[9px]">
                  {cap}
                </Badge>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">None advertised</span>
            )}
          </div>
        </div>
        {/* TODO(federation-9.9): MCP tool picker + result viewer
            - List available tools via FleetProxy.list_tools()
            - Tool selector dropdown
            - Execute button → FleetProxy.call_tool()
            - Result viewer with mcp_response() redaction indicator
            - Log SSE stream viewer */}
        <div className="text-xs text-muted-foreground border-t pt-3">
          MCP tool picker and log viewer — TODO(federation-9.9)
        </div>
      </div>
    </div>
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
