// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { 
  Database, 
  RefreshCw, 
  Download, 
  Clock,
  ExternalLink,
  Info
} from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

interface DataVersionInfo {
  version: string
  release_date: string
  sources: Record<string, SourceInfo>
  total_documents: number
  total_chunks?: number
  update_available: boolean
  latest_version: string
  update_release_notes?: string
  update_download_url?: string
  message?: string
  error?: string
}

interface SourceInfo {
  document_count: number
  license: string
  scraped_at?: string
  description?: string
  mac_build?: boolean
}

interface FreshnessStats {
  sampled_documents: number
  freshness_breakdown: {
    fresh: number
    aging: number
    stale: number
    outdated: number
    unknown: number
  }
  thresholds_days: Record<string, number>
  sources: Record<string, { total: number; avg_age_days: number }>
  error?: string
}

export function DataVersionCard() {
  const [versionInfo, setVersionInfo] = useState<DataVersionInfo | null>(null)
  const [freshnessStats, setFreshnessStats] = useState<FreshnessStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [checkingUpdates, setCheckingUpdates] = useState(false)
  const [showDetails, setShowDetails] = useState(false)

  const fetchVersionInfo = async () => {
    try {
      const response = await fetch(`${API_BASE}/rag/data/version`)
      if (response.ok) {
        const data = await response.json()
        setVersionInfo(data)
      }
    } catch (err) {
      console.error('Failed to fetch version info:', err)
    }
  }

  const fetchFreshnessStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/rag/data/freshness`)
      if (response.ok) {
        const data = await response.json()
        setFreshnessStats(data)
      }
    } catch (err) {
      console.error('Failed to fetch freshness stats:', err)
    }
  }

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([fetchVersionInfo(), fetchFreshnessStats()])
      setLoading(false)
    }
    loadData()
  }, [])

  const checkForUpdates = async () => {
    setCheckingUpdates(true)
    await fetchVersionInfo()
    setCheckingUpdates(false)
  }

  const getFreshnessPercentage = () => {
    if (!freshnessStats) return 0
    const { freshness_breakdown: fb, sampled_documents } = freshnessStats
    if (sampled_documents === 0) return 0
    return Math.round(((fb.fresh + fb.aging) / sampled_documents) * 100)
  }

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Knowledge Base
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-5 w-5" />
          Knowledge Base
        </CardTitle>
        <CardDescription>
          RAG corpus version and data freshness
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Version Info */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Current Version</p>
            <div className="flex items-center gap-2">
              <p className="text-2xl font-bold">
                {versionInfo?.version || 'Unknown'}
              </p>
              {versionInfo?.update_available && (
                <Badge variant="destructive" className="animate-pulse">
                  Update Available
                </Badge>
              )}
            </div>
            {versionInfo?.release_date && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Released: {versionInfo.release_date}
              </p>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={checkForUpdates}
            disabled={checkingUpdates}
          >
            {checkingUpdates ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            <span className="ml-2">Check Updates</span>
          </Button>
        </div>

        {/* Update Available Banner */}
        {versionInfo?.update_available && (
          <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="flex items-start gap-3">
              <Download className="h-5 w-5 text-blue-500 mt-0.5" />
              <div className="flex-1">
                <p className="font-medium text-blue-500">
                  Version {versionInfo.latest_version} Available
                </p>
                {versionInfo.update_release_notes && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {versionInfo.update_release_notes}
                  </p>
                )}
                {versionInfo.update_download_url && (
                  <Button
                    variant="link"
                    size="sm"
                    className="p-0 h-auto mt-2 text-blue-500"
                    onClick={() => window.open(versionInfo.update_download_url, '_blank')}
                  >
                    Download Update
                    <ExternalLink className="h-3 w-3 ml-1" />
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Document Stats */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 bg-muted/30 rounded-lg">
            <p className="text-sm text-muted-foreground">Total Documents</p>
            <p className="text-xl font-bold">
              {versionInfo?.total_documents?.toLocaleString() || '—'}
            </p>
          </div>
          <div className="p-3 bg-muted/30 rounded-lg">
            <p className="text-sm text-muted-foreground">Data Sources</p>
            <p className="text-xl font-bold">
              {versionInfo?.sources ? Object.keys(versionInfo.sources).length : '—'}
            </p>
          </div>
        </div>

        {/* Freshness Indicator */}
        {freshnessStats && !freshnessStats.error && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Data Freshness</p>
              <p className="text-sm text-muted-foreground">
                {getFreshnessPercentage()}% current
              </p>
            </div>
            <div className="flex h-2 rounded-full overflow-hidden bg-muted">
              {freshnessStats.sampled_documents > 0 && (
                <>
                  <div 
                    className="bg-green-500 transition-all"
                    style={{ width: `${(freshnessStats.freshness_breakdown.fresh / freshnessStats.sampled_documents) * 100}%` }}
                  />
                  <div 
                    className="bg-yellow-500 transition-all"
                    style={{ width: `${(freshnessStats.freshness_breakdown.aging / freshnessStats.sampled_documents) * 100}%` }}
                  />
                  <div 
                    className="bg-orange-500 transition-all"
                    style={{ width: `${(freshnessStats.freshness_breakdown.stale / freshnessStats.sampled_documents) * 100}%` }}
                  />
                  <div 
                    className="bg-red-500 transition-all"
                    style={{ width: `${(freshnessStats.freshness_breakdown.outdated / freshnessStats.sampled_documents) * 100}%` }}
                  />
                  <div 
                    className="bg-gray-500 transition-all"
                    style={{ width: `${(freshnessStats.freshness_breakdown.unknown / freshnessStats.sampled_documents) * 100}%` }}
                  />
                </>
              )}
            </div>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                Fresh ({freshnessStats.freshness_breakdown.fresh})
              </span>
              <span className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-yellow-500" />
                Aging ({freshnessStats.freshness_breakdown.aging})
              </span>
              <span className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-orange-500" />
                Stale ({freshnessStats.freshness_breakdown.stale})
              </span>
              <span className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                Old ({freshnessStats.freshness_breakdown.outdated})
              </span>
            </div>
          </div>
        )}

        {/* Toggle Details */}
        <Button
          variant="ghost"
          size="sm"
          className="w-full"
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? 'Hide Details' : 'Show Source Details'}
        </Button>

        {/* Source Details */}
        {showDetails && versionInfo?.sources && (
          <div className="space-y-2 pt-2 border-t">
            <p className="text-sm font-medium">Data Sources</p>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {Object.entries(versionInfo.sources).map(([name, info]) => (
                <div 
                  key={name}
                  className="p-2 bg-muted/30 rounded-lg text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{name}</span>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {info.document_count.toLocaleString()} docs
                      </Badge>
                      {info.mac_build === false && (
                        <Badge variant="secondary" className="text-xs">
                          Linux only
                        </Badge>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {info.description || info.license}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Info Message */}
        {versionInfo?.message && (
          <div className="flex items-start gap-2 p-2 bg-muted/30 rounded-lg text-sm">
            <Info className="h-4 w-4 text-muted-foreground mt-0.5" />
            <p className="text-muted-foreground">{versionInfo.message}</p>
          </div>
        )}

        {/* Freshness Legend */}
        <div className="pt-2 border-t">
          <p className="text-xs text-muted-foreground">
            Freshness thresholds: Fresh (&lt;30d), Aging (30-90d), Stale (90-180d), Outdated (&gt;365d)
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
