// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * One paired device row on the Settings → Devices page (G12 / P7b,
 * design review §15.2): identity, capability badges, Wake-on-LAN with an
 * inline MAC form, live capability discovery, and removal.
 *
 * Revoked devices render muted with interactive controls disabled
 * (their actions — Re-pair / Permanently Forget — live in the Devices
 * tab's archived section, not here).
 */
import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog, Toast } from '@/components/ui/confirm-dialog'
import { Radar, Trash2 } from 'lucide-react'
import { toggleDeviceWol, discoverCapabilities, removeDevice } from '@/lib/peerApi'
import type { DeviceInfo, DiscoverResult } from '@/lib/peerApi'

/** Capability badge colour map (design review §15.3.2). */
const CAPABILITY_STYLES: Record<string, string> = {
  gpu_llm: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
  mcp: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  terminal: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  canonical_memory: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  canonical_threads: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
}

/** Human descriptions for the badge title attribute (accessibility, §8). */
const CAPABILITY_TITLES: Record<string, string> = {
  gpu_llm: 'This device can run local LLM inference',
  mcp: 'This device exposes an MCP tool server',
  terminal: 'This device can run terminal sessions',
  sourceprep: 'This device has the SourcePrep documentation index',
  sysadmin_tools: 'This device can edit configs and manage files',
  home_tools: 'This device can drive Home Assistant',
  vision: 'This device has cameras or image processing',
}

const MAC_PATTERN = /^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/

interface DeviceCardProps {
  device: DeviceInfo
  onRefresh: () => Promise<void> | void
}

export function DeviceCard({ device, onRefresh }: DeviceCardProps) {
  const [wolEnabled, setWolEnabled] = useState(device.wol_enabled)
  const [macInput, setMacInput] = useState(device.wol_mac ?? '')
  const [broadcastInput, setBroadcastInput] = useState(device.wol_broadcast ?? '')
  const [wolFormOpen, setWolFormOpen] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [discovery, setDiscovery] = useState<DiscoverResult | null>(null)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [toast, setToast] = useState<{ open: boolean; message: string; variant: 'success' | 'error' | 'info' }>(
    { open: false, message: '', variant: 'info' },
  )

  const showToast = (message: string, variant: 'success' | 'error' | 'info' = 'info') =>
    setToast({ open: true, message, variant })

  const macValid = MAC_PATTERN.test(macInput.trim())

  /** Enable WoL: needs a MAC — the inline form appears when none is set
   *  (design review §15.3.4). Optimistic UI with rollback on rejection. */
  const onWolChange = async (next: boolean) => {
    const prev = { enabled: wolEnabled }
    setWolEnabled(next)  // optimistic
    if (next && !device.wol_mac && !macValid) {
      setWolFormOpen(true)
      return  // the form's Save performs the request
    }
    try {
      await toggleDeviceWol(device.node_id, {
        enabled: next,
        mac: next ? (macInput.trim() || device.wol_mac) : device.wol_mac,
        broadcast: broadcastInput.trim() || device.wol_broadcast || undefined,
      })
      await onRefresh()
    } catch (e) {
      setWolEnabled(prev.enabled)  // rollback
      showToast(`Could not toggle Wake-on-LAN: ${String(e)}`, 'error')
    }
  }

  const saveWolForm = async () => {
    try {
      await toggleDeviceWol(device.node_id, {
        enabled: true,
        mac: macInput.trim(),
        broadcast: broadcastInput.trim() || undefined,
      })
      setWolFormOpen(false)
      await onRefresh()
      showToast('Wake-on-LAN enabled', 'success')
    } catch (e) {
      setWolEnabled(false)  // rollback
      showToast(`Could not enable Wake-on-LAN: ${String(e)}`, 'error')
    }
  }

  const onDiscover = async () => {
    setDiscovering(true)
    setDiscovery(null)
    try {
      const result = await discoverCapabilities(device.node_id)
      setDiscovery(result)
      if (result.status === 'discovered') await onRefresh()
    } catch (e) {
      showToast(`Discovery failed: ${String(e)}`, 'error')
    } finally {
      setDiscovering(false)
    }
  }

  const onRemove = async () => {
    try {
      await removeDevice(device.node_id)
      await onRefresh()
      showToast(`${device.node_name} removed`, 'success')
    } catch (e) {
      showToast(`Could not remove ${device.node_name}: ${String(e)}`, 'error')
    }
  }

  return (
    <Card className={device.revoked ? 'opacity-60' : ''}>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{device.node_name}</p>
            <p className="text-xs text-muted-foreground truncate">
              {device.endpoint ?? 'no endpoint'} · paired {device.paired_at.slice(0, 10) || '—'}
            </p>
          </div>
          {device.revoked && <Badge variant="outline">Revoked</Badge>}
        </div>

        {/* Capability badges (colour map + title descriptions, §15.3.2/§8) */}
        {device.capabilities.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5" aria-label="Capabilities" role="list">
            {device.capabilities.map((cap) => (
              <li key={cap}>
                <Badge
                  variant="outline"
                  className={CAPABILITY_STYLES[cap] ?? undefined}
                  title={CAPABILITY_TITLES[cap] ?? cap}
                >
                  {cap}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">No capabilities recorded.</p>
        )}

        {/* WoL: switch + inline MAC form (§15.3.4) */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Switch
              id={`wol-${device.node_id}`}
              checked={wolEnabled}
              onCheckedChange={onWolChange}
              disabled={device.revoked}
              aria-label={`Wake-on-LAN for ${device.node_name}`}
            />
            <Label htmlFor={`wol-${device.node_id}`} className="text-sm">
              Wake-on-LAN
              {device.wol_mac && (
                <span className="ml-2 text-xs text-muted-foreground font-normal">
                  {device.wol_mac}
                </span>
              )}
            </Label>
          </div>
          {wolFormOpen && (
            <div className="space-y-2 rounded-lg border p-3">
              <Label htmlFor={`mac-${device.node_id}`}>MAC address</Label>
              <Input
                id={`mac-${device.node_id}`}
                value={macInput}
                onChange={(e) => setMacInput(e.target.value)}
                placeholder="00:1A:2B:3C:4D:5E"
                aria-invalid={!macValid && macInput !== ''}
              />
              {!macValid && macInput !== '' && (
                <p className="text-xs text-destructive" role="alert">
                  Expected AA:BB:CC:DD:EE:FF.
                </p>
              )}
              <Label htmlFor={`broadcast-${device.node_id}`}>Broadcast address (optional)</Label>
              <Input
                id={`broadcast-${device.node_id}`}
                value={broadcastInput}
                onChange={(e) => setBroadcastInput(e.target.value)}
                placeholder="255.255.255.255"
              />
              <div className="flex gap-2">
                <Button size="sm" disabled={!macValid} onClick={saveWolForm}>
                  Enable
                </Button>
                <Button
                  size="sm" variant="ghost"
                  onClick={() => {
                    setWolFormOpen(false)
                    setWolEnabled(false)  // the optimistic toggle never landed
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Discovery result: outcomes are results, not errors (§7) */}
        {discovery && (
          <p className="text-xs" role="status">
            {discovery.status === 'discovered'
              ? `Found ${discovery.tools ?? 0} tools → [${discovery.capabilities.join(', ')}]`
              : discovery.status === 'unreachable'
                ? 'Device unreachable — capabilities unchanged.'
                : discovery.status === 'no-token'
                  ? 'No token configured for this device — pair first.'
                  : 'No endpoint configured for this device.'}
          </p>
        )}

        <div className="flex gap-2">
          <Button
            variant="outline" size="sm"
            onClick={onDiscover}
            disabled={discovering || device.revoked}
            aria-label={`Discover capabilities on ${device.node_name}`}
          >
            <Radar className="h-4 w-4 mr-1.5" />
            {discovering ? 'Discovering…' : 'Discover Capabilities'}
          </Button>
          <Button
            variant="ghost" size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => setConfirmRemove(true)}
            disabled={device.revoked}
            aria-label={`Remove ${device.node_name}`}
          >
            <Trash2 className="h-4 w-4 mr-1.5" />
            Remove
          </Button>
        </div>
      </CardContent>

      <ConfirmDialog
        open={confirmRemove}
        onClose={() => setConfirmRemove(false)}
        onConfirm={() => {
          setConfirmRemove(false)
          onRemove()
        }}
        title={`Remove ${device.node_name}?`}
        description="The device's token is revoked immediately; its record is kept for audit and it can be re-paired later."
        confirmText="Remove Device"
        variant="destructive"
      />
      <Toast
        open={toast.open}
        onClose={() => setToast({ ...toast, open: false })}
        message={toast.message}
        variant={toast.variant}
      />
    </Card>
  )
}