// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Replica status card — the warm-standby tile on the Devices tab.
 *
 * Shows what this body holds of the canonical host's mind: how fresh the
 * replica is and how much of the entity it carries. Promotion is a
 * deliberate, manual act (Phase 1: no auto-promotion), gated behind a
 * confirmation that names what happens — this machine becomes the
 * canonical, and the old host re-pairs when it returns.
 *
 * Renders nothing on a node with no replica — a canonical host or a body
 * that has never received one gets no card, not an empty one.
 */
import { useCallback, useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ConfirmDialog, Toast } from '@/components/ui/confirm-dialog'
import { DatabaseBackup } from 'lucide-react'
import { getReplicaStatus, promoteReplica } from '@/lib/peerApi'
import type { ReplicaStatus as ReplicaStatusData } from '@/lib/peerApi'

function formatAge(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'an unknown time'
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

export function ReplicaStatus() {
  const [status, setStatus] = useState<ReplicaStatusData | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [promoting, setPromoting] = useState(false)
  const [toast, setToast] = useState<{ open: boolean; message: string; variant: 'success' | 'error' | 'info' }>(
    { open: false, message: '', variant: 'info' },
  )

  const refresh = useCallback(async () => {
    try {
      setStatus(await getReplicaStatus())
    } catch {
      setStatus(null)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const onPromote = async () => {
    setConfirming(false)
    setPromoting(true)
    try {
      const result = await promoteReplica()
      setToast({
        open: true,
        message: `Promoted — ${result.memory_count} memories and ${result.thread_count} threads are live on this machine.`,
        variant: 'success',
      })
      await refresh()
    } catch (e) {
      setToast({ open: true, message: `Promotion failed: ${String(e)}`, variant: 'error' })
    } finally {
      setPromoting(false)
    }
  }

  if (!status?.has_replica || !status.replica) return null

  const meta = status.replica
  const age = formatAge(meta.created_at)

  return (
    <>
      <Card>
        <CardHeader className="space-y-1.5">
          <CardTitle className="text-sm flex items-center gap-2">
            <DatabaseBackup className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            Warm Standby
          </CardTitle>
          <CardDescription>
            This body keeps a copy of the mind in case the canonical host
            goes away.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Last synced {age} — {meta.memory_count.toLocaleString()} memories,{' '}
            {meta.thread_count.toLocaleString()} threads
            {meta.source_node_id ? ` from ${meta.source_node_id}` : ''}.
          </p>
          {!status.is_valid && (
            <p className="text-sm text-destructive">
              The replica failed its integrity check — do not promote it.
            </p>
          )}
          {status.can_promote && (
            <Button
              variant="outline"
              size="sm"
              disabled={promoting}
              onClick={() => setConfirming(true)}
              aria-label="Promote this body to canonical host"
            >
              {promoting ? 'Promoting…' : 'Promote to Canonical'}
            </Button>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={onPromote}
        title="Promote this machine to canonical host?"
        description={`This machine becomes the mind's home — the replica from ${age} (${meta.memory_count} memories, ${meta.thread_count} threads) becomes live. The old host will need to re-pair when it comes back; any stale push from it is refused.`}
        confirmText="Promote"
        variant="default"
      />
      <Toast
        open={toast.open}
        onClose={() => setToast({ ...toast, open: false })}
        message={toast.message}
        variant={toast.variant}
      />
    </>
  )
}
