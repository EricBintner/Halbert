// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import type { SystemInfo } from '@/lib/tauri'
import { Cpu, Database, RefreshCw, ScanSearch, Clock } from 'lucide-react'

export interface DiscoveryStats {
  total: number
  by_type: Record<string, number>
}

export interface SystemProfile {
  summary: string
  scan_time: string | null
  quick_scan_time: string | null
}

interface SystemTabProps {
  systemInfo: SystemInfo | null
  discoveryStats: DiscoveryStats | null
  systemProfile: SystemProfile | null
  isDeepScanning: boolean
  onDeepScan: () => void
}

/** The System tab: host info, discovery cache, and the system profile. */
export function SystemTab({
  systemInfo,
  discoveryStats,
  systemProfile,
  isDeepScanning,
  onDeepScan,
}: SystemTabProps) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            System Information
          </CardTitle>
        </CardHeader>
        <CardContent>
          {systemInfo ? (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Hostname</p>
                <p className="font-medium">{systemInfo.hostname}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Operating System</p>
                <p className="font-medium">{systemInfo.os_name} {systemInfo.os_version}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Kernel</p>
                <p className="font-medium">{systemInfo.kernel_version}</p>
              </div>
              <div>
                <p className="text-muted-foreground">CPU Cores</p>
                <p className="font-medium">{systemInfo.cpu_count}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Memory</p>
                <p className="font-medium">
                  {Math.round(systemInfo.total_memory_mb / 1024)} GB total
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading system info...</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Discovery Cache
          </CardTitle>
          <CardDescription>Manage cached system discoveries</CardDescription>
        </CardHeader>
        <CardContent>
          {/* R08-07: "Clear Cache" used to be a placebo — it waited a second
           * and told the user the cache was cleared without calling any
           * backend route (none exists yet to clear discoveries). A fake
           * success message is worse than no button; removed until a real
           * clear-discoveries endpoint backs it. */}
          <div>
            <p className="font-medium">{discoveryStats?.total || 0} discoveries cached</p>
            <p className="text-sm text-muted-foreground">
              {Object.entries(discoveryStats?.by_type || {})
                .map(([type, count]) => `${count} ${type}`)
                .join(', ')
              }
            </p>
          </div>
        </CardContent>
      </Card>

      {/* System Profile Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ScanSearch className="h-5 w-5" />
            System Profile
          </CardTitle>
          <CardDescription>
            Deep system awareness for AI context. Run a deep scan after major changes or updates.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {systemProfile ? (
            <>
              <div className="p-3 bg-muted rounded-lg font-mono text-xs whitespace-pre-wrap max-h-48 overflow-auto">
                {systemProfile.summary}
              </div>
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Last deep scan: {systemProfile.scan_time ? new Date(systemProfile.scan_time).toLocaleString() : 'Never'}
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No system profile yet. Run a deep scan to create one.</p>
          )}
          <div className="flex gap-2">
            <Button
              onClick={onDeepScan}
              disabled={isDeepScanning}
              variant="outline"
            >
              {isDeepScanning ? (
                <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Scanning...</>
              ) : (
                <><ScanSearch className="h-4 w-4 mr-2" />Run Deep Scan</>
              )}
            </Button>
            <p className="text-xs text-muted-foreground self-center">
              Scans hardware, packages, services, security, and more (~30-60 sec)
            </p>
          </div>
        </CardContent>
      </Card>
    </>
  )
}