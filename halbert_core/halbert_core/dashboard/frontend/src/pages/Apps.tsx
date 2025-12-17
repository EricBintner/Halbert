/**
 * Apps Page - View and manage installed applications across package formats.
 * 
 * Phase 26: Universal App Management
 * Displays Flatpak, Snap, AppImage, and native package discoveries.
 */

import { useEffect, useState, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { 
  Package,
  RefreshCw, 
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Info,
  Box,
  Layers,
  FileArchive,
  ChevronDown,
  ChevronRight,
  Loader2,
  ExternalLink,
  ArrowUpCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/domain'
import { useScanPage } from '@/hooks'

// App discovery from scanner
interface AppDiscovery {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  data: {
    count?: number
    apps?: Array<{
      name: string
      version?: string
      app_id?: string
      origin?: string
      installation?: string
      path?: string
      size_mb?: number
      executable?: boolean
      classic?: boolean
    }>
    updates?: Array<{
      name: string
      app_id?: string
      version?: string
    }>
    snaps?: Array<{
      name: string
      version: string
      revision: string
      tracking: string
      publisher: string
      classic: boolean
    }>
    appimages?: Array<{
      name: string
      path: string
      size_mb: number
      executable: boolean
    }>
    services?: Array<{
      name: string
      startup: string
      current: string
      running: boolean
    }>
    remotes?: Array<{
      name: string
      url: string
    }>
    has_flathub?: boolean
    classic_count?: number
    total_size_mb?: number
    non_executable?: number
  }
  actions?: Array<{
    id: string
    label: string
    command?: string
    requires_approval?: boolean
  }>
}

type SourceFilter = 'all' | 'flatpak' | 'snap' | 'appimage'

export function Apps() {
  const [apps, setApps] = useState<AppDiscovery[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set())
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')

  const loadApps = async () => {
    setLoading(true)
    try {
      const data = await api.getDiscoveries('package')
      // Filter to only app-related discoveries (flatpak, snap, appimage)
      const appDiscoveries = data.filter((d: AppDiscovery) => 
        d.name.includes('flatpak') || 
        d.name.includes('snap') || 
        d.name.includes('appimage')
      )
      setApps(appDiscoveries)
    } catch (error) {
      console.error('Failed to load apps:', error)
    } finally {
      setLoading(false)
    }
  }

  // Scan hook for refresh functionality
  const { scanning, handleScan } = useScanPage({
    scanType: 'all',
    onScanComplete: loadApps,
  })

  useEffect(() => {
    loadApps()
  }, [])

  const handleRefresh = async () => {
    await handleScan()
  }

  const toggleExpanded = (id: string) => {
    const newExpanded = new Set(expandedCards)
    if (newExpanded.has(id)) {
      newExpanded.delete(id)
    } else {
      newExpanded.add(id)
    }
    setExpandedCards(newExpanded)
  }

  // Filter apps by source
  const filteredApps = useMemo(() => {
    if (sourceFilter === 'all') return apps
    return apps.filter(app => app.name.includes(sourceFilter))
  }, [apps, sourceFilter])

  // Summary stats
  const stats = useMemo(() => {
    const flatpakApps = apps.find(a => a.name === 'flatpak-apps')
    const snapApps = apps.find(a => a.name === 'snap-apps')
    const appimageApps = apps.find(a => a.name === 'appimage-apps')
    const flatpakUpdates = apps.find(a => a.name === 'flatpak-updates')
    const snapUpdates = apps.find(a => a.name === 'snap-updates')

    return {
      flatpak: flatpakApps?.data?.count || 0,
      snap: snapApps?.data?.count || 0,
      appimage: appimageApps?.data?.count || 0,
      flatpakUpdates: flatpakUpdates?.data?.count || 0,
      snapUpdates: snapUpdates?.data?.count || 0,
      total: (flatpakApps?.data?.count || 0) + (snapApps?.data?.count || 0) + (appimageApps?.data?.count || 0),
      totalUpdates: (flatpakUpdates?.data?.count || 0) + (snapUpdates?.data?.count || 0),
    }
  }, [apps])

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical': return <AlertCircle className="h-5 w-5 text-red-500" />
      case 'warning': return <AlertTriangle className="h-5 w-5 text-yellow-500" />
      case 'success': return <CheckCircle className="h-5 w-5 text-green-500" />
      default: return <Info className="h-5 w-5 text-blue-500" />
    }
  }

  const getSourceIcon = (name: string) => {
    if (name.includes('flatpak')) return <Box className="h-5 w-5" />
    if (name.includes('snap')) return <Layers className="h-5 w-5" />
    if (name.includes('appimage')) return <FileArchive className="h-5 w-5" />
    return <Package className="h-5 w-5" />
  }

  const getSourceBadge = (name: string) => {
    if (name.includes('flatpak')) return <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/30">Flatpak</Badge>
    if (name.includes('snap')) return <Badge variant="outline" className="bg-orange-500/10 text-orange-400 border-orange-500/30">Snap</Badge>
    if (name.includes('appimage')) return <Badge variant="outline" className="bg-purple-500/10 text-purple-400 border-purple-500/30">AppImage</Badge>
    return <Badge variant="outline">Package</Badge>
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Apps"
        description="Installed applications across Flatpak, Snap, and AppImage"
        icon={<Package className="h-8 w-8" />}
        actions={
          <Button 
            variant="outline" 
            size="sm" 
            onClick={handleRefresh}
            disabled={scanning}
          >
            <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
            {scanning ? 'Scanning...' : 'Refresh'}
          </Button>
        }
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-card/50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Apps</p>
                <p className="text-2xl font-bold">{stats.total}</p>
              </div>
              <Package className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Updates Available</p>
                <p className="text-2xl font-bold text-yellow-500">{stats.totalUpdates}</p>
              </div>
              <ArrowUpCircle className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Flatpak</p>
                <p className="text-2xl font-bold">{stats.flatpak}</p>
              </div>
              <Box className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Snap</p>
                <p className="text-2xl font-bold">{stats.snap}</p>
              </div>
              <Layers className="h-8 w-8 text-orange-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Source Filter */}
      <div className="flex gap-2">
        {(['all', 'flatpak', 'snap', 'appimage'] as SourceFilter[]).map((filter) => (
          <Button
            key={filter}
            variant={sourceFilter === filter ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSourceFilter(filter)}
          >
            {filter === 'all' ? 'All Sources' : filter.charAt(0).toUpperCase() + filter.slice(1)}
          </Button>
        ))}
      </div>

      {/* App Discovery Cards */}
      <div className="space-y-4">
        {filteredApps.length === 0 ? (
          <Card className="bg-card/50">
            <CardContent className="p-8 text-center">
              <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No apps found for this filter.</p>
              <p className="text-sm text-muted-foreground mt-2">
                Try running a scan to discover installed applications.
              </p>
            </CardContent>
          </Card>
        ) : (
          filteredApps.map((app) => (
            <Card key={app.id} className="bg-card/50 hover:bg-card/70 transition-colors">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    {getSourceIcon(app.name)}
                    <div>
                      <CardTitle className="text-lg flex items-center gap-2">
                        {app.title}
                        {getSourceBadge(app.name)}
                      </CardTitle>
                      <p className="text-sm text-muted-foreground">{app.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {getSeverityIcon(app.severity)}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleExpanded(app.id)}
                    >
                      {expandedCards.has(app.id) ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </CardHeader>

              {expandedCards.has(app.id) && (
                <CardContent className="pt-0">
                  {/* Flatpak Apps List */}
                  {app.data.apps && app.data.apps.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-2">Installed Apps</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                        {app.data.apps.map((item, idx) => (
                          <div key={idx} className="flex items-center justify-between p-2 bg-muted/30 rounded">
                            <span className="text-sm">{item.name}</span>
                            <span className="text-xs text-muted-foreground">{item.version}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Snap Apps List */}
                  {app.data.snaps && app.data.snaps.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-2">Installed Snaps</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                        {app.data.snaps.map((snap, idx) => (
                          <div key={idx} className="flex items-center justify-between p-2 bg-muted/30 rounded">
                            <div>
                              <span className="text-sm">{snap.name}</span>
                              {snap.classic && (
                                <Badge variant="outline" className="ml-2 text-xs">classic</Badge>
                              )}
                            </div>
                            <span className="text-xs text-muted-foreground">{snap.version}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* AppImage List */}
                  {app.data.appimages && app.data.appimages.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-2">AppImage Files</h4>
                      <div className="space-y-2">
                        {app.data.appimages.map((ai, idx) => (
                          <div key={idx} className="flex items-center justify-between p-2 bg-muted/30 rounded">
                            <div className="flex items-center gap-2">
                              <span className="text-sm">{ai.name}</span>
                              {!ai.executable && (
                                <Badge variant="destructive" className="text-xs">Not Executable</Badge>
                              )}
                            </div>
                            <span className="text-xs text-muted-foreground">{ai.size_mb} MB</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Updates List */}
                  {app.data.updates && app.data.updates.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                        <ArrowUpCircle className="h-4 w-4 text-yellow-500" />
                        Available Updates
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                        {app.data.updates.map((update, idx) => (
                          <div key={idx} className="p-2 bg-yellow-500/10 border border-yellow-500/30 rounded">
                            <span className="text-sm">{update.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Remotes */}
                  {app.data.remotes && app.data.remotes.length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-2">Configured Remotes</h4>
                      <div className="space-y-1">
                        {app.data.remotes.map((remote, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-sm">
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                            <span>{remote.name}</span>
                            <span className="text-xs text-muted-foreground truncate">{remote.url}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  {app.actions && app.actions.length > 0 && (
                    <div className="mt-4 flex gap-2">
                      {app.actions.map((action) => (
                        <Button
                          key={action.id}
                          variant={action.requires_approval ? 'destructive' : 'outline'}
                          size="sm"
                        >
                          {action.label}
                        </Button>
                      ))}
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          ))
        )}
      </div>
    </div>
  )
}

export default Apps
