// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Apps Page - View and manage installed applications across package formats.
 * 
 * Phase 26: Universal App Management
 * Unified app list with inline update status indicators.
 */

import { useEffect, useState, useMemo } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { 
  Package,
  RefreshCw, 
  CheckCircle,
  Box,
  Layers,
  FileArchive,
  ChevronDown,
  ChevronRight,
  Loader2,
  ExternalLink,
  ArrowUpCircle,
  MessageSquare,
  Terminal,
  Search,
  HardDrive,
  Shield,
  Cog,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { apiUrl } from '@/lib/apiBase'
import { PageHeader } from '@/components/domain'
import { useScanPage } from '@/hooks'
import { openChat } from '@/components/SendToChat'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'

// Unified app item - normalized from both Flatpak and Snap
interface UnifiedApp {
  id: string
  name: string
  displayName: string
  version: string
  source: 'flatpak' | 'snap' | 'appimage'
  hasUpdate: boolean
  icon?: string | null
  // Flatpak-specific
  appId?: string
  origin?: string
  installation?: string
  // Snap-specific
  revision?: string
  tracking?: string
  publisher?: string
  classic?: boolean
  // AppImage-specific
  path?: string
  sizeMb?: number
  executable?: boolean
}

// Runtime/extension update
interface RuntimeUpdate {
  name: string
  appId: string
  ref?: string
}

// Discovery response from API
interface AppDiscovery {
  id: string
  name: string
  title: string
  description: string
  severity: string
  data: {
    count?: number
    update_count?: number
    source?: string
    is_runtime?: boolean
    apps?: Array<{
      name: string
      version?: string
      app_id?: string
      origin?: string
      installation?: string
      icon?: string | null
      has_update?: boolean
      status?: string
    }>
    snaps?: Array<{
      name: string
      version: string
      revision: string
      tracking: string
      publisher: string
      classic: boolean
      icon?: string | null
      has_update?: boolean
      status?: string
    }>
    runtimes?: Array<{
      name: string
      app_id: string
      ref?: string
    }>
    appimages?: Array<{
      name: string
      path: string
      size_mb: number
      executable: boolean
    }>
  }
}

type StatusFilter = 'all' | 'has_update'
type SourceFilter = 'all' | 'flatpak' | 'snap' | 'appimage'

export function Apps() {
  const [discoveries, setDiscoveries] = useState<AppDiscovery[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [expandedApp, setExpandedApp] = useState<string | null>(null)
  const [runtimesExpanded, setRuntimesExpanded] = useState(false)

  const loadApps = async () => {
    setLoading(true)
    try {
      const data = await api.getDiscoveries('package')
      const allDiscoveries = data.discoveries || []
      // Filter to only app-related discoveries (flatpak, snap, appimage)
      const appDiscoveries = allDiscoveries.filter((d: AppDiscovery) => 
        d.name.includes('flatpak') || 
        d.name.includes('snap') || 
        d.name.includes('appimage')
      )
      setDiscoveries(appDiscoveries)
    } catch (error) {
      console.error('Failed to load apps:', error)
    } finally {
      setLoading(false)
    }
  }

  const { scanning, handleScan } = useScanPage({
    scanType: 'all',
    onScanComplete: loadApps,
  })

  useEffect(() => {
    loadApps()
  }, [])

  // Build unified app list from discoveries
  const { apps, runtimeUpdates, stats } = useMemo(() => {
    const appList: UnifiedApp[] = []
    const runtimes: RuntimeUpdate[] = []
    let flatpakCount = 0
    let snapCount = 0
    let appimageCount = 0
    let updateCount = 0

    for (const discovery of discoveries) {
      // Flatpak apps
      if (discovery.name === 'flatpak-apps' && discovery.data.apps) {
        for (const app of discovery.data.apps) {
          flatpakCount++
          if (app.has_update) updateCount++
          appList.push({
            id: `flatpak-${app.app_id || app.name}`,
            name: app.name,
            displayName: app.name,
            version: app.version || '',
            source: 'flatpak',
            hasUpdate: app.has_update || false,
            icon: app.icon,
            appId: app.app_id,
            origin: app.origin,
            installation: app.installation,
          })
        }
      }

      // Snap apps
      if (discovery.name === 'snap-apps' && discovery.data.snaps) {
        for (const snap of discovery.data.snaps) {
          snapCount++
          if (snap.has_update) updateCount++
          appList.push({
            id: `snap-${snap.name}`,
            name: snap.name,
            displayName: snap.name,
            version: snap.version,
            source: 'snap',
            hasUpdate: snap.has_update || false,
            icon: snap.icon,
            revision: snap.revision,
            tracking: snap.tracking,
            publisher: snap.publisher,
            classic: snap.classic,
          })
        }
      }

      // AppImage apps
      if (discovery.name === 'appimage-apps' && discovery.data.appimages) {
        for (const ai of discovery.data.appimages) {
          appimageCount++
          appList.push({
            id: `appimage-${ai.name}`,
            name: ai.name,
            displayName: ai.name,
            version: '',
            source: 'appimage',
            hasUpdate: false,
            path: ai.path,
            sizeMb: ai.size_mb,
            executable: ai.executable,
          })
        }
      }

      // Runtime updates (separate)
      if (discovery.name === 'flatpak-runtimes' && discovery.data.runtimes) {
        for (const rt of discovery.data.runtimes) {
          runtimes.push({
            name: rt.name,
            appId: rt.app_id,
            ref: rt.ref,
          })
        }
      }
    }

    return {
      apps: appList,
      runtimeUpdates: runtimes,
      stats: {
        total: appList.length,
        flatpak: flatpakCount,
        snap: snapCount,
        appimage: appimageCount,
        updates: updateCount,
      },
    }
  }, [discoveries])

  // Filter apps
  const filteredApps = useMemo(() => {
    return apps.filter(app => {
      // Source filter
      if (sourceFilter !== 'all' && app.source !== sourceFilter) return false
      
      // Status filter
      if (statusFilter === 'has_update' && !app.hasUpdate) return false
      
      // Search
      if (search) {
        const searchLower = search.toLowerCase()
        return (
          app.name.toLowerCase().includes(searchLower) ||
          app.displayName.toLowerCase().includes(searchLower) ||
          (app.appId && app.appId.toLowerCase().includes(searchLower)) ||
          (app.publisher && app.publisher.toLowerCase().includes(searchLower))
        )
      }
      
      return true
    })
  }, [apps, sourceFilter, statusFilter, search])

  const getSourceIcon = (source: string) => {
    switch (source) {
      case 'flatpak': return <Box className="h-5 w-5 text-blue-500" />
      case 'snap': return <Layers className="h-5 w-5 text-orange-500" />
      case 'appimage': return <FileArchive className="h-5 w-5 text-purple-500" />
      default: return <Package className="h-5 w-5" />
    }
  }

  const getSourceBadge = (source: string) => {
    switch (source) {
      case 'flatpak': return <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-blue-500/10 text-blue-400 border-blue-500/30">Flatpak</Badge>
      case 'snap': return <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-orange-500/10 text-orange-400 border-orange-500/30">Snap</Badge>
      case 'appimage': return <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-purple-500/10 text-purple-400 border-purple-500/30">AppImage</Badge>
      default: return null
    }
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
            onClick={handleScan}
            disabled={scanning}
          >
            <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
            {scanning ? 'Scanning...' : 'Refresh'}
          </Button>
        }
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => { setSourceFilter('all'); setStatusFilter('all') }}>
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

        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setStatusFilter('has_update')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Updates</p>
                <p className="text-2xl font-bold text-yellow-500">{stats.updates}</p>
              </div>
              <ArrowUpCircle className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>

        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setSourceFilter('flatpak')}>
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

        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setSourceFilter('snap')}>
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

        <Card className="cursor-pointer hover:bg-accent/50" onClick={() => setSourceFilter('appimage')}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">AppImage</p>
                <p className="text-2xl font-bold">{stats.appimage}</p>
              </div>
              <FileArchive className="h-8 w-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search & Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search apps..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-md border bg-background"
          />
        </div>
        <div className="flex gap-2">
          <Button
            variant={statusFilter === 'all' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('all')}
          >
            All
          </Button>
          <Button
            variant={statusFilter === 'has_update' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter('has_update')}
            className="gap-1"
          >
            <ArrowUpCircle className="h-3 w-3" />
            Has Update
            {stats.updates > 0 && (
              <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-xs">{stats.updates}</Badge>
            )}
          </Button>
        </div>
      </div>

      {/* Source Filters */}
      <div className="flex flex-wrap gap-2">
        {(['all', 'flatpak', 'snap', 'appimage'] as SourceFilter[]).map((source) => {
          const count = source === 'all' ? stats.total : stats[source]
          const icons = {
            all: <Package className="h-4 w-4" />,
            flatpak: <Box className="h-4 w-4" />,
            snap: <Layers className="h-4 w-4" />,
            appimage: <FileArchive className="h-4 w-4" />,
          }
          const colors = {
            all: 'text-muted-foreground',
            flatpak: 'text-blue-500',
            snap: 'text-orange-500',
            appimage: 'text-purple-500',
          }
          
          return (
            <Button
              key={source}
              variant={sourceFilter === source ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSourceFilter(source)}
              className="gap-1.5"
            >
              <span className={cn(sourceFilter !== source && colors[source])}>
                {icons[source]}
              </span>
              {source === 'all' ? 'All Sources' : source.charAt(0).toUpperCase() + source.slice(1)}
              <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-xs">{count}</Badge>
            </Button>
          )
        })}
      </div>

      {/* App List */}
      <Card>
        <CardContent className="p-0">
          <div className="divide-y">
            {filteredApps.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">
                {apps.length === 0 
                  ? "No apps discovered. Click Refresh to scan for installed applications."
                  : "No apps match your filters."}
              </div>
            ) : (
              filteredApps.map((app) => (
                <div key={app.id}>
                  <div
                    className="flex items-center justify-between p-4 hover:bg-accent/30 cursor-pointer group"
                    onClick={() => setExpandedApp(expandedApp === app.id ? null : app.id)}
                  >
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      {/* App Icon */}
                      {app.icon ? (
                        <img 
                          src={apiUrl(`/api/discoveries/icon?path=${encodeURIComponent(app.icon)}`)}
                          alt={app.name}
                          className="w-10 h-10 rounded-lg flex-shrink-0 object-contain bg-white/5"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                            const fallback = e.currentTarget.nextElementSibling
                            if (fallback) fallback.classList.remove('hidden')
                          }}
                        />
                      ) : null}
                      <div className={cn(
                        "w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0",
                        app.source === 'flatpak' && "bg-gradient-to-br from-blue-500/20 to-purple-500/20",
                        app.source === 'snap' && "bg-gradient-to-br from-orange-500/20 to-red-500/20",
                        app.source === 'appimage' && "bg-gradient-to-br from-purple-500/20 to-pink-500/20",
                        app.icon && "hidden"
                      )}>
                        {getSourceIcon(app.source)}
                      </div>
                      
                      {/* App Info */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{app.displayName}</p>
                          {getSourceBadge(app.source)}
                          {app.hasUpdate && (
                            <Badge className="text-[10px] px-1.5 py-0 bg-yellow-500/20 text-yellow-400 border-yellow-500/40">
                              <ArrowUpCircle className="h-3 w-3 mr-1" />
                              Update
                            </Badge>
                          )}
                          {app.classic && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0">classic</Badge>
                          )}
                          {app.executable === false && (
                            <Badge variant="destructive" className="text-[10px] px-1 py-0">Not Executable</Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground truncate">
                          {app.appId || app.publisher || app.path || ''}
                        </p>
                      </div>
                    </div>
                    
                    {/* Right side */}
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {app.version}{app.revision && ` (rev ${app.revision})`}
                        {app.sizeMb && ` • ${app.sizeMb} MB`}
                      </span>
                      {app.hasUpdate ? (
                        <CheckCircle className="h-4 w-4 text-yellow-500" />
                      ) : (
                        <CheckCircle className="h-4 w-4 text-green-500" />
                      )}
                      <ChevronRight className={cn(
                        "h-4 w-4 text-muted-foreground transition-transform",
                        expandedApp === app.id && "rotate-90"
                      )} />
                    </div>
                  </div>
                  
                  {/* Expanded App Tools */}
                  {expandedApp === app.id && (
                    <div className="px-4 pb-4 bg-muted/10">
                      <div className="p-3 bg-muted/20 rounded-lg border flex items-start justify-between gap-4">
                        {/* Left side - App-specific actions */}
                        <div className="flex flex-wrap gap-2">
                          {app.source === 'flatpak' && app.appId && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                window.open(`https://flathub.org/apps/${app.appId}`, '_blank')
                              }}
                            >
                              <ExternalLink className="h-3 w-3 mr-1" />
                              Flathub
                            </Button>
                          )}
                          {app.source === 'snap' && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                window.open(`https://snapcraft.io/${app.name}`, '_blank')
                              }}
                            >
                              <ExternalLink className="h-3 w-3 mr-1" />
                              Snap Store
                            </Button>
                          )}
                          {app.hasUpdate && (
                            <Button
                              variant="default"
                              size="sm"
                              className="bg-yellow-600 hover:bg-yellow-700"
                              onClick={(e) => {
                                e.stopPropagation()
                                openChat({ 
                                  title: app.displayName, 
                                  type: 'app', 
                                  prefillMessage: `Update ${app.displayName} to the latest version using ${app.source}` 
                                })
                              }}
                            >
                              <ArrowUpCircle className="h-3 w-3 mr-1" />
                              Update
                            </Button>
                          )}
                        </div>
                        
                        {/* Right side - Mentions & Chat */}
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <span className="text-xs text-muted-foreground mr-1">Mentions:</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2"
                            title="Ask about this app"
                            onClick={(e) => {
                              e.stopPropagation()
                              openChat({ title: app.displayName, type: 'app', prefillMessage: `Tell me about ${app.displayName}. What does this application do?` })
                            }}
                          >
                            <MessageSquare className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2"
                            title="Commands & usage"
                            onClick={(e) => {
                              e.stopPropagation()
                              openChat({ title: app.displayName, type: 'app', prefillMessage: `Show me commands to manage ${app.displayName} (${app.source})` })
                            }}
                          >
                            <Terminal className="h-3.5 w-3.5" />
                          </Button>
                          {app.source === 'flatpak' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2"
                              title="Check permissions"
                              onClick={(e) => {
                                e.stopPropagation()
                                openChat({ title: app.displayName, type: 'app', prefillMessage: `What permissions does ${app.displayName} (${app.appId}) have?` })
                              }}
                            >
                              <Shield className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2"
                            title="Check disk usage"
                            onClick={(e) => {
                              e.stopPropagation()
                              openChat({ title: app.displayName, type: 'app', prefillMessage: `How much disk space does ${app.displayName} use?` })
                            }}
                          >
                            <HardDrive className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Runtime Updates Section (Collapsible) */}
      {runtimeUpdates.length > 0 && (
        <Card className="bg-muted/30">
          <CardContent className="p-0">
            <div
              className="flex items-center justify-between p-4 cursor-pointer hover:bg-accent/30"
              onClick={() => setRuntimesExpanded(!runtimesExpanded)}
            >
              <div className="flex items-center gap-3">
                <Cog className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="font-medium">Flatpak Runtimes & Extensions</p>
                  <p className="text-sm text-muted-foreground">
                    {runtimeUpdates.length} update{runtimeUpdates.length !== 1 ? 's' : ''} available
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    openChat({ title: 'Runtime Updates', type: 'app', prefillMessage: 'Update all Flatpak runtimes with: flatpak update --runtime' })
                  }}
                >
                  Update All
                </Button>
                {runtimesExpanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </div>
            </div>
            
            {runtimesExpanded && (
              <div className="px-4 pb-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {runtimeUpdates.map((rt, idx) => (
                    <div key={idx} className="flex items-center gap-2 p-2 bg-muted/30 rounded text-sm">
                      <Cog className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      <span className="truncate">{rt.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* AI App Compatibility Analysis */}
      <AIAnalysisPanel
        type="package"
        title="App Compatibility"
        canAnalyze={apps.length > 0}
        buildContext={() => {
          const flatpakApps = apps.filter(a => a.source === 'flatpak')
          const snapApps = apps.filter(a => a.source === 'snap')
          const classicSnaps = snapApps.filter(a => a.classic)
          const appsWithUpdates = apps.filter(a => a.hasUpdate)
          
          return `## Installed Applications Summary

**Total Apps:** ${apps.length}
- Flatpak: ${flatpakApps.length} apps
- Snap: ${snapApps.length} apps (${classicSnaps.length} classic/unconfined)
- AppImage: ${apps.filter(a => a.source === 'appimage').length} files

**Updates Available:** ${appsWithUpdates.length}
${appsWithUpdates.slice(0, 5).map(a => `- ${a.displayName} (${a.source})`).join('\n')}
${appsWithUpdates.length > 5 ? `... and ${appsWithUpdates.length - 5} more` : ''}

**Runtime Updates:** ${runtimeUpdates.length} pending

## Apps List
${apps.slice(0, 20).map(a => `- ${a.displayName} (${a.source})${a.hasUpdate ? ' [UPDATE]' : ''}${a.classic ? ' [CLASSIC]' : ''}`).join('\n')}
${apps.length > 20 ? `... and ${apps.length - 20} more apps` : ''}`
        }}
        researchQuestion="Analyze my installed applications for potential compatibility issues. Check for: 1) Flatpak apps that may have permission issues or sandbox limitations, 2) Classic snaps that run unconfined (security risk), 3) Outdated apps that may have known vulnerabilities, 4) Any conflicts between similar apps from different sources."
        gradientFrom="from-violet-50/70"
        gradientTo="to-fuchsia-50/70"
        iconColor="text-violet-700 dark:text-violet-300"
      />
    </div>
  )
}

export default Apps
