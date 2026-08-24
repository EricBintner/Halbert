/**
 * DriveHealthModule — compact drive health (SMART status, capacity).
 *
 * Phase 8 / T8c.3.
 */

import { useState, useEffect } from 'react'
import { HardDrive, Loader2 } from 'lucide-react'

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export default function DriveHealthModule() {
  const [drives, setDrives] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/modules/drive-health/data')
      .then(r => r.json())
      .then(data => {
        if (data.status === 'ok') {
          setDrives(data.drives || [])
          setLoading(false)
        }
      })
      .catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading drive health...
      </div>
    )
  }

  // Filter to physical drives (skip virtual/special filesystems)
  const physicalDrives = drives.filter(d =>
    d.device && d.device.startsWith('/dev/') && d.total
  )

  if (physicalDrives.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        No physical drives found
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-2">
        <HardDrive className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Drive Health</span>
      </div>
      <div className="divide-y divide-border">
        {physicalDrives.map((drive, i) => (
          <div key={i} className="p-3 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-mono">{drive.device}</span>
              <span className="text-xs text-muted-foreground">{drive.fstype}</span>
            </div>
            <div className="text-xs text-muted-foreground">{drive.mountpoint}</div>
            {drive.percent !== null && (
              <>
                <div className="flex items-center justify-between text-xs">
                  <span>{formatBytes(drive.used)} / {formatBytes(drive.total)}</span>
                  <span className={drive.percent > 90 ? 'text-destructive font-medium' : ''}>
                    {drive.percent.toFixed(1)}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full transition-all ${
                      drive.percent > 90 ? 'bg-destructive' : 'bg-primary'
                    }`}
                    style={{ width: `${drive.percent}%` }}
                  />
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
