/**
 * Backups Page - View and manage backup configurations.
 * 
 * Based on Phase 9 research: docs/Phase9/deep-dives/02-backups-discovery.md
 */

import { useEffect, useState } from 'react'
import { ConfigEditor } from '@/components/ConfigEditor'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { 
  Archive, 
  RefreshCw, 
  Play, 
  Clock,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Calendar,
  HardDrive,
  FileText,
  Settings,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  History,
  ExternalLink,
  Loader2,
  Pencil,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import { openChat } from '@/components/SendToChat'
import { SystemItemActions } from '@/components/domain'

interface BackupHistory {
  timestamp: string
  status: 'success' | 'failed' | 'warning'
  size?: string
  duration?: string
}

interface Backup {
  id: string
  name: string
  title: string
  description: string
  status: string
  severity: string
  status_detail?: string
  data: {
    tool: string
    schedule?: string
    last_run?: string
    destination?: string
    source_path?: string
    config_path?: string
    script_path?: string
    cron_source?: string
    timer_unit?: string
    timeshift_config?: Record<string, unknown>
  }
}

// Status overrides from actual service state
interface BackupStatus {
  last_run_status: 'success' | 'failed'
  severity: string
}

export function Backups() {
  const [backups, setBackups] = useState<Backup[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [expandedBackups, setExpandedBackups] = useState<Set<string>>(new Set())
  const [backupHistories, setBackupHistories] = useState<Record<string, BackupHistory[]>>({})
  const [loadingHistories, setLoadingHistories] = useState<Set<string>>(new Set())
  const [backupStatuses, setBackupStatuses] = useState<Record<string, BackupStatus>>({})
  const [historyLimits, setHistoryLimits] = useState<Record<string, number>>({})
  const [editingConfig, setEditingConfig] = useState<string | null>(null)
  const DEFAULT_HISTORY_LIMIT = 10
  const HISTORY_INCREMENT = 20

  useEffect(() => {
    loadBackups()
  }, [])

  const loadBackups = async () => {
    try {
      const data = await api.getDiscoveries('backup')
      setBackups(data.discoveries || [])
      
      // Also load actual run statuses
      try {
        const statusData = await api.getBackupStatuses()
        setBackupStatuses(statusData.statuses || {})
      } catch (err) {
        console.error('Failed to load backup statuses:', err)
      }
    } catch (error) {
      console.error('Failed to load backups:', error)
    } finally {
      setLoading(false)
    }
  }
  
  // Get effective severity (override with actual status if available)
  const getEffectiveSeverity = (backup: Backup): string => {
    const statusOverride = backupStatuses[backup.name]
    if (statusOverride) {
      return statusOverride.severity
    }
    return backup.severity
  }
  
  // Get effective status label
  const getEffectiveStatus = (backup: Backup): string => {
    const statusOverride = backupStatuses[backup.name]
    if (statusOverride?.last_run_status === 'failed') {
      return 'Failed'
    }
    return backup.status
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await api.scanDiscoveries('backup')
      await loadBackups()
    } catch (error) {
      console.error('Scan failed:', error)
    } finally {
      setScanning(false)
    }
  }

  const handleAction = async (backup: Backup, action: string) => {
    console.log(`Action ${action} on ${backup.name}`)
    alert(`Would ${action} backup: ${backup.name}`)
  }

  const toggleBackupExpanded = async (backup: Backup) => {
    const id = backup.id
    const isCurrentlyExpanded = expandedBackups.has(id)
    
    setExpandedBackups(prev => {
      const next = new Set(prev)
      if (isCurrentlyExpanded) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
    
    // Fetch history when expanding (if not already loaded)
    if (!isCurrentlyExpanded && !backupHistories[backup.name]) {
      await fetchHistory(backup.name, DEFAULT_HISTORY_LIMIT)
    }
  }
  
  const fetchHistory = async (backupName: string, limit: number) => {
    setLoadingHistories(prev => new Set(prev).add(backupName))
    try {
      const data = await api.getBackupHistory(backupName, limit)
      setBackupHistories(prev => ({
        ...prev,
        [backupName]: data.history || [],
      }))
      setHistoryLimits(prev => ({
        ...prev,
        [backupName]: limit,
      }))
    } catch (error) {
      console.error(`Failed to load history for ${backupName}:`, error)
      setBackupHistories(prev => ({
        ...prev,
        [backupName]: [],
      }))
    } finally {
      setLoadingHistories(prev => {
        const next = new Set(prev)
        next.delete(backupName)
        return next
      })
    }
  }
  
  const loadMoreHistory = async (backupName: string) => {
    const currentLimit = historyLimits[backupName] || DEFAULT_HISTORY_LIMIT
    const newLimit = currentLimit + HISTORY_INCREMENT
    await fetchHistory(backupName, newLimit)
  }

  // Build context for sending to chat (used by AIAnalysisPanel)
  const buildBackupContext = (): string => {
    const parts = [`## Backup Analysis Context\n`]
    parts.push(`Found ${backups.length} backup configurations:\n`)
    
    for (const backup of backups) {
      const status = backupStatuses[backup.name]?.last_run_status || 'unknown'
      parts.push(`- **${backup.name}**: ${status} (${backup.data.tool})`)
      if (backup.data.source_path) parts.push(`  Source: ${backup.data.source_path}`)
      if (backup.data.destination) parts.push(`  Destination: ${backup.data.destination}`)
    }
    
    return parts.join('\n')
  }

  const getToolIcon = (tool: string) => {
    switch (tool.toLowerCase()) {
      case 'timeshift':
        return <Clock className="h-5 w-5 text-blue-500" />
      case 'borg':
        return <Archive className="h-5 w-5 text-purple-500" />
      case 'restic':
        return <HardDrive className="h-5 w-5 text-green-500" />
      case 'rsync':
        return <RefreshCw className="h-5 w-5 text-orange-500" />
      case 'systemd':
        return <Settings className="h-5 w-5 text-gray-500" />
      default:
        return <Archive className="h-5 w-5 text-muted-foreground" />
    }
  }

  const getStatusBadgeClass = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-500 hover:bg-red-600'
      case 'warning': return 'bg-yellow-500 hover:bg-yellow-600'
      case 'success': return 'bg-green-500 hover:bg-green-600'
      case 'info': return 'bg-blue-500 hover:bg-blue-600'
      default: return 'bg-gray-500 hover:bg-gray-600'
    }
  }

  const stats = {
    total: backups.length,
    healthy: backups.filter(b => getEffectiveSeverity(b) === 'success').length,
    warning: backups.filter(b => getEffectiveSeverity(b) === 'warning').length,
    failed: backups.filter(b => getEffectiveSeverity(b) === 'critical').length,
  }


  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Show editor instead of normal content when editing
  if (editingConfig) {
    return (
      <ConfigEditor
        filePath={editingConfig}
        onClose={() => setEditingConfig(null)}
      />
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Archive className="h-8 w-8" />
            Backups
          </h1>
          <p className="text-muted-foreground">
            Discovered backup configurations on your system
          </p>
        </div>
        <Button variant="outline" onClick={handleScan} disabled={scanning}>
          <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
          {scanning ? 'Scanning...' : 'Scan'}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Backups</p>
                <p className="text-2xl font-bold">{stats.total}</p>
              </div>
              <Archive className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Healthy</p>
                <p className="text-2xl font-bold text-green-500">{stats.healthy}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Warnings</p>
                <p className="text-2xl font-bold text-yellow-500">{stats.warning}</p>
              </div>
              <AlertTriangle className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Failed</p>
                <p className="text-2xl font-bold text-red-500">{stats.failed}</p>
              </div>
              <AlertCircle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Backup List */}
      {backups.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <Archive className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">No Backups Discovered</h3>
            <p className="text-muted-foreground mb-4">
              Click Scan to discover backup configurations on your system.
            </p>
            <Button variant="outline" onClick={handleScan} disabled={scanning}>
              <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
              Scan for Backups
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {backups.map((backup) => {
            const isExpanded = expandedBackups.has(backup.id)
            const history = backupHistories[backup.name] || []
            const isLoadingHistory = loadingHistories.has(backup.name)
            
            return (
              <Card key={backup.id} className="overflow-hidden">
                <CardContent className="p-0">
                  {/* Main backup info - improved layout */}
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3 min-w-0 flex-1">
                        <div className="shrink-0 mt-0.5">
                          {getToolIcon(backup.data.tool)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-semibold">{backup.name}</h3>
                            <Badge className={getStatusBadgeClass(getEffectiveSeverity(backup))}>
                              {getEffectiveStatus(backup)}
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">
                            {backup.description}
                          </p>
                        </div>
                      </div>
                      {/* @ and Chat buttons */}
                      <SystemItemActions
                        item={{
                          name: backup.name,
                          type: 'backup',
                          id: backup.name,
                          context: `Backup: ${backup.name}\nTool: ${backup.data.tool}\nSchedule: ${backup.data.schedule || 'manual'}\nStatus: ${getEffectiveStatus(backup)}\nSource: ${backup.data.source_path || 'N/A'}\nDestination: ${backup.data.destination || 'N/A'}`,
                        }}
                        size="sm"
                      />
                    </div>

                    {/* Backup details grid - improved spacing */}
                    <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                      <div className="flex items-center gap-2">
                        <Settings className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground">Tool:</span>
                        <span className="font-medium">{backup.data.tool}</span>
                      </div>
                      {backup.data.schedule && (
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="text-muted-foreground">Schedule:</span>
                          <span className="font-medium break-words">{backup.data.schedule}</span>
                        </div>
                      )}
                      {backup.data.source_path && (
                        <div className="flex items-start gap-2 sm:col-span-2">
                          <FolderOpen className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                          <span className="text-muted-foreground shrink-0">Source:</span>
                          <code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded break-all">
                            {backup.data.source_path}
                          </code>
                        </div>
                      )}
                      {backup.data.destination && (
                        <div className="flex items-start gap-2 sm:col-span-2">
                          <HardDrive className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                          <span className="text-muted-foreground shrink-0">Destination:</span>
                          <a 
                            href={`file://${backup.data.destination}`}
                            className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded break-all hover:bg-muted/80 inline-flex items-center gap-1"
                            title="Open backup location"
                          >
                            {backup.data.destination}
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        </div>
                      )}
                      {backup.data.config_path && (
                        <div className="flex items-start gap-2 sm:col-span-2">
                          <FileText className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                          <span className="text-muted-foreground shrink-0">Config:</span>
                          <code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded break-all">
                            {backup.data.config_path}
                          </code>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs ml-auto"
                            onClick={() => {
                              const configPath = backup.data.config_path || ''
                              setEditingConfig(configPath)
                              openChat({
                                title: `Config: ${configPath.split('/').pop()}`,
                                type: 'config',
                              })
                            }}
                          >
                            <Pencil className="h-3 w-3 mr-1" />
                            Edit
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Expandable History Section */}
                  <div className="border-t">
                    <button
                      onClick={() => toggleBackupExpanded(backup)}
                      className="w-full px-4 py-2 flex items-center justify-between text-sm hover:bg-muted/50 transition-colors"
                    >
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <History className="h-4 w-4" />
                        Backup History
                        {isLoadingHistory ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : backupHistories[backup.name] !== undefined ? (
                          <span className="text-xs">({history.length} entries)</span>
                        ) : (
                          <span className="text-xs text-muted-foreground/60">click to load</span>
                        )}
                      </span>
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                    </button>
                    
                    {isExpanded && (
                      <div className="px-4 pb-4">
                        {isLoadingHistory ? (
                          <div className="bg-muted/30 rounded-lg p-4 text-center">
                            <Loader2 className="h-8 w-8 mx-auto text-muted-foreground mb-2 animate-spin" />
                            <p className="text-sm text-muted-foreground">
                              Loading backup history...
                            </p>
                          </div>
                        ) : history.length === 0 ? (
                          <div className="bg-muted/30 rounded-lg p-4 text-center">
                            <History className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                            <p className="text-sm text-muted-foreground">
                              No backup history found
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              History will appear after backups run
                            </p>
                          </div>
                        ) : (
                          <div className="bg-muted/30 rounded-lg overflow-hidden">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-border/50">
                                  <th className="text-left py-2 px-3 font-medium text-muted-foreground">Time</th>
                                  <th className="text-left py-2 px-3 font-medium text-muted-foreground">Status</th>
                                  <th className="text-left py-2 px-3 font-medium text-muted-foreground">Size</th>
                                  <th className="text-left py-2 px-3 font-medium text-muted-foreground">Duration</th>
                                </tr>
                              </thead>
                              <tbody>
                                {history.map((entry: BackupHistory, idx: number) => (
                                  <tr key={idx} className="border-b border-border/30 last:border-0">
                                    <td className="py-2 px-3 font-mono text-xs">
                                      {new Date(entry.timestamp).toLocaleString()}
                                    </td>
                                    <td className="py-2 px-3">
                                      <Badge 
                                        variant="outline"
                                        className={cn(
                                          "text-xs",
                                          entry.status === 'success' && "border-green-500 text-green-600",
                                          entry.status === 'warning' && "border-yellow-500 text-yellow-600",
                                          entry.status === 'failed' && "border-red-500 text-red-600",
                                        )}
                                      >
                                        {entry.status === 'success' && <CheckCircle className="h-3 w-3 mr-1" />}
                                        {entry.status === 'warning' && <AlertTriangle className="h-3 w-3 mr-1" />}
                                        {entry.status === 'failed' && <AlertCircle className="h-3 w-3 mr-1" />}
                                        {entry.status}
                                      </Badge>
                                    </td>
                                    <td className="py-2 px-3 text-muted-foreground">{entry.size}</td>
                                    <td className="py-2 px-3 text-muted-foreground">{entry.duration}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            {/* Load More button */}
                            {history.length >= (historyLimits[backup.name] || DEFAULT_HISTORY_LIMIT) && (
                              <div className="p-2 border-t border-border/30 text-center">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => loadMoreHistory(backup.name)}
                                  disabled={isLoadingHistory}
                                  className="text-xs"
                                >
                                  {isLoadingHistory ? (
                                    <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Loading...</>
                                  ) : (
                                    <>Load More History</>
                                  )}
                                </Button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="border-t p-3 bg-muted/30 flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleAction(backup, 'run')}
                    >
                      <Play className="h-4 w-4 mr-1" />
                      Run Now
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleAction(backup, 'logs')}
                    >
                      <FileText className="h-4 w-4 mr-1" />
                      Logs
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* AI Analysis Panel */}
      <AIAnalysisPanel
        type="backup"
        title="Backup"
        canAnalyze={backups.length > 0}
        buildContext={buildBackupContext}
        researchQuestion="Give me a detailed analysis of my backup strategy, including potential risks and improvement suggestions."
      />
    </div>
  )
}
