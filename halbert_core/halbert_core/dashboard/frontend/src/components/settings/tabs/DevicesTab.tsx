// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Settings → Linked Devices tab (G12 / P7b): the singular-entity
 * management surface. This body's identity, the linked devices list, and
 * the "Link a device to Halbert" flow (P7c — the existing PeerPairingModal,
 * reused as-is per the design review).
 *
 * One noun for the list, 'Linked Devices' (shell review §9.2; T1-08): a
 * linked device is a body when it shares the entity and a compute peer when
 * it only serves models — the card, not the list title, says which.
 *
 * "One mind (being), many bodies (devices)" — the tab sits in the
 * Personality & Identity section next to the being tab (review §15.1 Q1).
 * Every variant sees it; a lone install shows the empty state with an
 * "Link First Device" CTA (§15.3.1). Revoked devices collapse into an
 * archived section with Re-pair and Permanently Forget (Q5) — hidden
 * entirely, they would ghost-collide on re-pairing the same hostname.
 */
import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Collapsible } from '@/components/ui/collapsible'
import { ConfirmDialog, Toast } from '@/components/ui/confirm-dialog'
import { Plus, MonitorSmartphone } from 'lucide-react'
import { listDevices, removeDevice } from '@/lib/peerApi'
import type { DevicesState, DeviceInfo } from '@/lib/peerApi'
import { EntityIdentityCard } from '@/components/settings/devices/EntityIdentityCard'
import { DeviceCard } from '@/components/settings/devices/DeviceCard'
import { PeerPairingModal } from '@/components/fleet/PeerPairingModal'

export function DevicesTab() {
  const [state, setState] = useState<DevicesState | null>(null)
  const [loading, setLoading] = useState(true)
  const [showPairing, setShowPairing] = useState(false)
  const [forgetTarget, setForgetTarget] = useState<DeviceInfo | null>(null)
  const [toast, setToast] = useState<{ open: boolean; message: string; variant: 'success' | 'error' | 'info' }>(
    { open: false, message: '', variant: 'info' },
  )

  const showToast = (message: string, variant: 'success' | 'error' | 'info' = 'info') =>
    setToast({ open: true, message, variant })

  const refresh = useCallback(async () => {
    try {
      setState(await listDevices())
    } catch (e) {
      showToast(`Could not load devices: ${String(e)}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const onForget = async () => {
    if (!forgetTarget) return
    const target = forgetTarget
    setForgetTarget(null)
    try {
      await removeDevice(target.node_id, true)
      await refresh()
      showToast(`${target.node_name} permanently forgotten`, 'success')
    } catch (e) {
      showToast(`Could not forget ${target.node_name}: ${String(e)}`, 'error')
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Loading devices…</p>
  }

  const devices = state?.devices ?? []
  const active = devices.filter((d) => !d.revoked)
  const revoked = devices.filter((d) => d.revoked)
  const firstRun = active.length === 0

  return (
    <div className="space-y-4">
      {state && <EntityIdentityCard state={state} onRefresh={refresh} />}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div className="space-y-1.5">
            <CardTitle className="text-sm">
              Linked Devices ({active.length})
            </CardTitle>
            <CardDescription>
              Other machines that are part of this Halbert — or that it can
              lean on for compute.
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowPairing(true)} aria-label="Link a device">
            <Plus className="h-4 w-4 mr-1.5" />
            Link Device
          </Button>
        </CardHeader>
        <CardContent>
          {firstRun ? (
            /* Empty state (§15.3.1): explain the concept, then the CTA. */
            <div className="py-8 text-center space-y-3">
              <MonitorSmartphone className="h-10 w-10 mx-auto text-muted-foreground" aria-hidden="true" />
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                Halbert can be one entity across many machines — a desk
                body, a kitchen speaker, an always-on home server — sharing
                one memory and one conversation. Pair the first one to
                begin.
              </p>
              <Button onClick={() => setShowPairing(true)} aria-label="Link first device">
                <Plus className="h-4 w-4 mr-1.5" />
                Link First Device
              </Button>
            </div>
          ) : (
            <ul className="grid gap-3" aria-label="Linked devices" role="list">
              {active.map((device) => (
                <li key={device.node_id}>
                  <DeviceCard device={device} onRefresh={refresh} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Revoked / archived (Q5): visible so a re-pair doesn't ghost-collide,
          with the two explicit ways out. */}
      {revoked.length > 0 && (
        <Collapsible title={`Revoked / Archived Devices (${revoked.length})`} defaultOpen={false}>
          <ul className="grid gap-3 pt-1" aria-label="Revoked devices" role="list">
            {revoked.map((device) => (
              <li key={device.node_id} className="flex items-center justify-between gap-2 rounded-lg border p-3 opacity-75">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{device.node_name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {device.endpoint ?? 'no endpoint'}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button variant="outline" size="sm" onClick={() => setShowPairing(true)}>
                    Re-pair
                  </Button>
                  <Button
                    variant="ghost" size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setForgetTarget(device)}
                    aria-label={`Permanently forget ${device.node_name}`}
                  >
                    Permanently Forget
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {/* P7c: the existing pairing flow, reused as-is (review §3). */}
      {showPairing && (
        <PeerPairingModal
          onClose={() => setShowPairing(false)}
          onPaired={() => {
            setShowPairing(false)
            refresh()
          }}
        />
      )}

      <ConfirmDialog
        open={forgetTarget !== null}
        onClose={() => setForgetTarget(null)}
        onConfirm={onForget}
        title={`Permanently forget ${forgetTarget?.node_name ?? ''}?`}
        description="The record is erased entirely. A future pairing of the same machine starts clean — this cannot be undone."
        confirmText="Permanently Forget"
        variant="destructive"
      />
      <Toast
        open={toast.open}
        onClose={() => setToast({ ...toast, open: false })}
        message={toast.message}
        variant={toast.variant}
      />
    </div>
  )
}