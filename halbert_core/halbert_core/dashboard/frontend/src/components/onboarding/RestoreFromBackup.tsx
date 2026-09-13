// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Onboarding → "Restore from Backup" — the recovery door.
 *
 * A fresh install that used to be an entity: the operator points at a
 * .halbert-backup archive, types the passphrase, and this machine
 * becomes that entity again — key, config, autobiography. The report
 * names what came back (and what was quarantined) before onboarding
 * completes.
 */
import { useState } from 'react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Loader2, FileKey } from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'

interface RestoreReport {
  status: string
  entity_name: string
  backup_date: string
  memory_count: number
  thread_count: number
  files_restored: string[]
  quarantined: string[]
  warnings: string[]
}

export function RestoreFromBackup({ onRestored }: { onRestored: () => void }) {
  const [archivePath, setArchivePath] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<RestoreReport | null>(null)

  const doRestore = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/api/backup/restore'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archive_path: archivePath, passphrase }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `restore failed (${res.status})`)
      }
      setReport(await res.json())
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (report) {
    return (
      <div className="space-y-4 py-2">
        <p className="text-sm">
          Restored <span className="font-medium">{report.entity_name || 'the entity'}</span>
          {' '}— {report.memory_count.toLocaleString()} memories,{' '}
          {report.thread_count.toLocaleString()} threads.
        </p>
        {report.quarantined.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {report.quarantined.length} existing file
            {report.quarantined.length === 1 ? ' was' : 's were'} moved
            aside rather than overwritten.
          </p>
        )}
        {report.warnings.map((w, i) => (
          <p key={i} className="text-sm text-muted-foreground">{w}</p>
        ))}
        <Button onClick={onRestored} className="w-full" size="lg">
          Continue
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4 py-2">
      <div className="flex items-center gap-3 p-3 border rounded-lg">
        <FileKey className="h-8 w-8 text-primary" />
        <p className="text-sm text-muted-foreground">
          Restore this machine's entity from an encrypted backup archive —
          its key, its configuration, and everything it remembered.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="archive-path">Backup archive</Label>
        <Input
          id="archive-path"
          value={archivePath}
          onChange={(e) => setArchivePath(e.target.value)}
          placeholder="/path/to/halbert-20260913T120000Z.halbert-backup"
          aria-label="Backup archive path"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="backup-passphrase">Passphrase</Label>
        <Input
          id="backup-passphrase"
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          aria-label="Backup passphrase"
        />
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <Button
        onClick={doRestore}
        className="w-full"
        size="lg"
        disabled={busy || !archivePath || !passphrase}
      >
        {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />}
        {busy ? 'Restoring…' : 'Restore'}
      </Button>
    </div>
  )
}
