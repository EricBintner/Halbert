/**
 * VitalsModule — compact system vitals (CPU, memory, disk, network).
 *
 * Phase 8 / T8c.2.
 */

import { useState, useEffect, useRef } from 'react'
import { Activity, Cpu, MemoryStick, HardDrive, Wifi, Loader2 } from 'lucide-react'
import { ModuleLoadError } from './ModuleLoadError'
import { apiUrl } from '@/lib/apiBase'

interface VitalsModuleProps {
  timeframe?: string
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

export default function VitalsModule({ timeframe = '1h' }: VitalsModuleProps) {
  const [vitals, setVitals] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const hasLoadedRef = useRef(false)

  useEffect(() => {
    const fetchVitals = () => {
      fetch(apiUrl(`/api/modules/vitals/data?timeframe=${encodeURIComponent(timeframe)}`))
        .then(async r => {
          const data = await r.json().catch(() => null)
          if (!r.ok) throw new Error(data?.error || `HTTP ${r.status}`)
          if (data?.status !== 'ok') throw new Error(data?.error || 'Failed to load vitals')
          return data
        })
        .then(data => {
          hasLoadedRef.current = true
          setVitals(data.vitals)
          setError(null)
          setLoading(false)
        })
        .catch(e => {
          // Keep last good data across transient poll failures; only surface
          // an error when we have never loaded successfully.
          if (!hasLoadedRef.current) {
            setError(e?.message || 'Failed to load vitals')
          }
          setLoading(false)
        })
    }
    fetchVitals()
    const interval = setInterval(fetchVitals, 5000)
    return () => clearInterval(interval)
  }, [timeframe])

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading vitals...
      </div>
    )
  }

  if (error) {
    return <ModuleLoadError module="vitals" message={error} />
  }

  if (!vitals) {
    return <div className="text-sm text-muted-foreground p-4">No vitals data</div>
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-2">
        <Activity className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">System Vitals</span>
        <span className="text-xs text-muted-foreground ml-auto">Updates every 5s</span>
      </div>
      <div className="grid grid-cols-2 gap-3 p-3">
        {/* CPU */}
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Cpu className="h-3 w-3" />
            CPU
          </div>
          <div className="text-lg font-semibold">{vitals.cpu.percent.toFixed(1)}%</div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${vitals.cpu.percent}%` }}
            />
          </div>
          <div className="text-xs text-muted-foreground">{vitals.cpu.count} cores</div>
        </div>

        {/* Memory */}
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <MemoryStick className="h-3 w-3" />
            Memory
          </div>
          <div className="text-lg font-semibold">{vitals.memory.percent.toFixed(1)}%</div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${vitals.memory.percent}%` }}
            />
          </div>
          <div className="text-xs text-muted-foreground">
            {formatBytes(vitals.memory.used)} / {formatBytes(vitals.memory.total)}
          </div>
        </div>

        {/* Disk */}
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <HardDrive className="h-3 w-3" />
            Disk
          </div>
          <div className="text-lg font-semibold">{vitals.disk.percent.toFixed(1)}%</div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${vitals.disk.percent}%` }}
            />
          </div>
          <div className="text-xs text-muted-foreground">
            {formatBytes(vitals.disk.used)} / {formatBytes(vitals.disk.total)}
          </div>
        </div>

        {/* Network */}
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Wifi className="h-3 w-3" />
            Network
          </div>
          <div className="text-sm font-medium">
            <span className="text-green-600">↓ {formatBytes(vitals.network.bytes_recv)}</span>
          </div>
          <div className="text-sm font-medium">
            <span className="text-blue-600">↑ {formatBytes(vitals.network.bytes_sent)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
