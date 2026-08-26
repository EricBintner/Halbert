// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  Database, 
  HardDrive, 
  Trash2, 
  RefreshCw, 
  AlertTriangle,
  CheckCircle,
  Zap,
  FolderOpen,
  Clock,
  ChevronDown,
  ChevronUp,
  BookOpen,
  Brain,
  BarChart3,
  Link,
  Lightbulb,
  Edit3,
  X,
  ArrowRight,
  Check
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

interface CollectionInfo {
  name: string
  id: string
  count: number
  size_bytes: number
  size_human: string
}

interface OrphanedDir {
  id: string
  path: string
  size_bytes: number
  size_human: string
  modified: string | null
}

interface DiskInfo {
  mount_point: string
  total_bytes: number
  free_bytes: number
  used_bytes: number
  disk_type: string
  total_human: string
  free_human: string
}

interface StorageMetrics {
  status: 'healthy' | 'warning' | 'error'
  location: string
  total_size_bytes: number
  total_size_human: string
  sqlite_size_bytes: number
  sqlite_size_human: string
  active_collections: CollectionInfo[]
  orphaned_data: {
    count: number
    total_size_bytes: number
    total_size_human: string
    directories: OrphanedDir[]
  }
  disk_info: DiskInfo
  last_cleanup: string | null
  warnings: string[]
  tips: string[]
}

interface CleanupStatus {
  job_id: string
  status: 'running' | 'completed' | 'failed'
  total_items: number
  completed_items: number
  bytes_freed: number
  bytes_freed_human: string
  error?: string
}

interface MigrationStatus {
  job_id: string
  status: 'pending' | 'copying' | 'verifying' | 'completed' | 'failed'
  source_path: string
  dest_path: string
  total_bytes: number
  copied_bytes: number
  files_total: number
  files_copied: number
  verified: boolean
  error?: string
  progress_percent: number
}

export function ChromaDBSettings() {
  const [metrics, setMetrics] = useState<StorageMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [cleanupStatus, setCleanupStatus] = useState<CleanupStatus | null>(null)
  const [cleaning, setCleaning] = useState(false)
  
  const [showCollections, setShowCollections] = useState(false)
  const [showOrphans, setShowOrphans] = useState(false)
  
  // Migration state
  const [showMigration, setShowMigration] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [migrationStatus, setMigrationStatus] = useState<MigrationStatus | null>(null)
  const [migrating, setMigrating] = useState(false)
  const [deletingOld, setDeletingOld] = useState(false)
  
  // Cleanup completion fade-out state
  const [cleanupFadePhase, setCleanupFadePhase] = useState<'visible' | 'fading' | 'hidden'>('hidden')

  useEffect(() => {
    loadMetrics()
  }, [])

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null
    
    if (cleanupStatus?.status === 'running') {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/storage/chromadb/cleanup/${cleanupStatus.job_id}`)
          const data = await res.json()
          setCleanupStatus(data)
          
          if (data.status !== 'running') {
            setCleaning(false)
            loadMetrics()
          }
        } catch (err) {
          console.error('Failed to check cleanup status:', err)
        }
      }, 1000)
    }
    
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [cleanupStatus?.job_id, cleanupStatus?.status])

  // Handle cleanup completion fade-out timing
  useEffect(() => {
    let visibleTimeout: ReturnType<typeof setTimeout> | null = null
    let fadeTimeout: ReturnType<typeof setTimeout> | null = null
    
    if (cleanupStatus?.status === 'completed' && !cleaning) {
      // Show completed state
      setCleanupFadePhase('visible')
      
      // After 10 seconds, start fading
      visibleTimeout = setTimeout(() => {
        setCleanupFadePhase('fading')
        
        // After 5 more seconds, hide completely and clear status
        fadeTimeout = setTimeout(() => {
          setCleanupFadePhase('hidden')
          setCleanupStatus(null)
        }, 5000)
      }, 10000)
    }
    
    return () => {
      if (visibleTimeout) clearTimeout(visibleTimeout)
      if (fadeTimeout) clearTimeout(fadeTimeout)
    }
  }, [cleanupStatus?.status, cleaning])

  const loadMetrics = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/storage/chromadb`)
      if (!res.ok) throw new Error('Failed to load metrics')
      const data = await res.json()
      setMetrics(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load storage metrics')
    } finally {
      setLoading(false)
    }
  }

  const startCleanup = async (dryRun: boolean = false) => {
    setCleaning(true)
    try {
      const res = await fetch(`${API_BASE}/storage/chromadb/cleanup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun })
      })
      const data = await res.json()
      setCleanupStatus(data)
      
      if (dryRun || data.status === 'completed') {
        setCleaning(false)
        if (!dryRun) loadMetrics()
      }
    } catch (err) {
      setCleaning(false)
      setError('Failed to start cleanup')
    }
  }

  const startMigration = async () => {
    if (!newPath.trim()) return
    setMigrating(true)
    try {
      const res = await fetch(`${API_BASE}/storage/chromadb/migrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_path: newPath.trim() })
      })
      const data = await res.json()
      setMigrationStatus(data)
      
      // Poll for status updates
      if (data.status !== 'completed' && data.status !== 'failed') {
        pollMigrationStatus(data.job_id)
      }
    } catch (err) {
      setMigrating(false)
      setError('Failed to start migration')
    }
  }

  const pollMigrationStatus = async (jobId: string) => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/storage/chromadb/migrate/${jobId}`)
        const data = await res.json()
        setMigrationStatus(data)
        
        if (data.status === 'completed' || data.status === 'failed') {
          setMigrating(false)
          if (data.status === 'completed') {
            loadMetrics()
          }
        } else {
          setTimeout(poll, 500)
        }
      } catch (err) {
        setMigrating(false)
      }
    }
    poll()
  }

  const deleteOldLocation = async () => {
    setDeletingOld(true)
    try {
      const res = await fetch(`${API_BASE}/storage/chromadb/migrate/old`, {
        method: 'DELETE'
      })
      const data = await res.json()
      if (data.success) {
        setMigrationStatus(null)
        setShowMigration(false)
        setNewPath('')
        loadMetrics()
      }
    } catch (err) {
      setError('Failed to delete old location')
    } finally {
      setDeletingOld(false)
    }
  }

  const getDiskTypeIcon = (diskType: string) => {
    switch (diskType) {
      case 'optane': return <Zap className="h-4 w-4 text-yellow-500" />
      case 'nvme': return <Zap className="h-4 w-4 text-blue-500" />
      case 'ssd': return <HardDrive className="h-4 w-4 text-green-500" />
      case 'hdd': return <HardDrive className="h-4 w-4 text-orange-500" />
      default: return <HardDrive className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getDiskTypeBadge = (diskType: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      optane: 'default',
      nvme: 'default',
      ssd: 'secondary',
      hdd: 'destructive'
    }
    const labels: Record<string, string> = {
      optane: '⭐ Intel Optane',
      nvme: 'NVMe SSD',
      ssd: 'SATA SSD',
      hdd: '⚠️ HDD'
    }
    return (
      <Badge variant={variants[diskType] || 'outline'}>
        {labels[diskType] || diskType.toUpperCase()}
      </Badge>
    )
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading storage metrics...
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-destructive">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
          <div className="flex justify-center mt-4">
            <Button variant="outline" onClick={loadMetrics}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!metrics) return null

  // Categorize collections properly
  const ragDocs = metrics.active_collections.find(c => c.name === 'linux_docs')?.count || 0
  const learnedFacts = metrics.active_collections.find(c => c.name === 'self_knowledge')?.count || 0
  const telemetryDocs = metrics.active_collections
    .filter(c => ['self_hwmon', 'self_journald'].includes(c.name))
    .reduce((sum, c) => sum + c.count, 0)
  // Note: self_knowledge_all is a combined index (contains duplicates) - excluded from counts
  const hasOrphans = metrics.orphaned_data.count > 0

  return (
    <div className="space-y-4">
      {/* Main Storage Overview */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                Knowledge Base Storage
                {metrics.status === 'healthy' && (
                  <Badge variant="outline" className="ml-2 text-green-600 border-green-600">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    Healthy
                  </Badge>
                )}
                {metrics.status === 'warning' && (
                  <Badge variant="outline" className="ml-2 text-yellow-600 border-yellow-600">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    Warning
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>ChromaDB vector database powering semantic search and RAG</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={loadMetrics}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Size Overview */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Database Size</p>
              <p className="text-2xl font-bold">{metrics.sqlite_size_human}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Collections</p>
              <p className="text-2xl font-bold">{metrics.active_collections.length}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">RAG Docs</p>
              <p className="text-2xl font-bold">{ragDocs.toLocaleString()}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Learned Facts</p>
              <p className="text-2xl font-bold">{learnedFacts.toLocaleString()}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Telemetry</p>
              <p className="text-2xl font-bold text-muted-foreground">{telemetryDocs.toLocaleString()}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Disk Type</p>
              <div className="flex items-center gap-2">
                {getDiskTypeIcon(metrics.disk_info.disk_type)}
                {getDiskTypeBadge(metrics.disk_info.disk_type)}
              </div>
            </div>
          </div>

          {/* Location with Edit Button */}
          <div className="flex items-center justify-between bg-muted/50 rounded-md p-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <FolderOpen className="h-4 w-4" />
              <code className="text-xs">{metrics.location}</code>
            </div>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setShowMigration(!showMigration)}
              className="h-7 px-2"
            >
              <Edit3 className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Migration Panel */}
          {showMigration && (
            <div className="border rounded-lg p-4 space-y-4 bg-muted/30">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-sm">Move Database Location</h4>
                <Button variant="ghost" size="sm" onClick={() => setShowMigration(false)} className="h-6 w-6 p-0">
                  <X className="h-4 w-4" />
                </Button>
              </div>
              
              {!migrationStatus ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="newPath" className="text-sm">New Location</Label>
                    <Input
                      id="newPath"
                      value={newPath}
                      onChange={(e) => setNewPath(e.target.value)}
                      placeholder="/path/to/new/chromadb"
                      className="font-mono text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      Enter the full path where you want to move the database. The directory will be created if it doesn't exist.
                    </p>
                  </div>
                  <Button 
                    onClick={startMigration} 
                    disabled={!newPath.trim() || migrating}
                    className="w-full"
                  >
                    {migrating ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <ArrowRight className="h-4 w-4 mr-2" />
                    )}
                    Start Migration
                  </Button>
                </>
              ) : (
                <div className="space-y-3">
                  {/* Migration Progress */}
                  <div className="flex items-center justify-between text-sm">
                    <span className="capitalize">{migrationStatus.status}...</span>
                    <span>{migrationStatus.progress_percent.toFixed(0)}%</span>
                  </div>
                  <Progress value={migrationStatus.progress_percent} />
                  <p className="text-xs text-muted-foreground">
                    {migrationStatus.files_copied} / {migrationStatus.files_total} files
                  </p>
                  
                  {/* Migration Complete */}
                  {migrationStatus.status === 'completed' && migrationStatus.verified && (
                    <div className="space-y-3 pt-2 border-t">
                      <div className="flex items-center gap-2 text-sm text-green-600">
                        <Check className="h-4 w-4" />
                        Migration complete and verified!
                      </div>
                      <p className="text-xs text-muted-foreground">
                        New location: <code>{migrationStatus.dest_path}</code>
                      </p>
                      <Button 
                        variant="destructive" 
                        onClick={deleteOldLocation}
                        disabled={deletingOld}
                        className="w-full"
                      >
                        {deletingOld ? (
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4 mr-2" />
                        )}
                        Delete Old Location
                      </Button>
                      <p className="text-xs text-muted-foreground">
                        This will permanently delete {migrationStatus.source_path}
                      </p>
                    </div>
                  )}
                  
                  {/* Migration Failed */}
                  {migrationStatus.status === 'failed' && (
                    <div className="flex items-center gap-2 text-sm text-destructive">
                      <AlertTriangle className="h-4 w-4" />
                      {migrationStatus.error || 'Migration failed'}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Last Cleanup */}
          {metrics.last_cleanup && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              Last cleanup: {new Date(metrics.last_cleanup).toLocaleDateString()}
            </div>
          )}

          {/* Warnings */}
          {metrics.warnings.length > 0 && (
            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-md p-3 space-y-1">
              {metrics.warnings.map((warning, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-yellow-700 dark:text-yellow-400">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  {warning}
                </div>
              ))}
            </div>
          )}

          {/* Collections Accordion - Categorized */}
          <div className="border rounded-md">
            <button
              className="w-full flex items-center justify-between p-3 hover:bg-muted/50 transition-colors"
              onClick={() => setShowCollections(!showCollections)}
            >
              <span className="font-medium">Database Collections ({metrics.active_collections.length})</span>
              {showCollections ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {showCollections && (
              <div className="border-t p-3 space-y-4">
                <p className="text-xs text-muted-foreground mb-3">All embeddings stored in shared SQLite database</p>
                {/* RAG Documentation */}
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5"><BookOpen className="h-3.5 w-3.5" /> RAG Documentation</p>
                  {metrics.active_collections
                    .filter(col => col.name === 'linux_docs')
                    .map((col) => (
                      <div key={col.id} className="text-sm pl-2">
                        <span className="font-medium">{col.name}</span>
                        <span className="text-muted-foreground ml-2">({col.count.toLocaleString()} docs)</span>
                      </div>
                    ))}
                </div>
                {/* Learned Knowledge */}
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5"><Brain className="h-3.5 w-3.5" /> Learned Knowledge</p>
                  <p className="text-xs text-muted-foreground pl-2 mb-1">Facts Halbert learned about your system</p>
                  {metrics.active_collections
                    .filter(col => ['self_knowledge', 'discoveries', 'self_conversations'].includes(col.name))
                    .map((col) => (
                      <div key={col.id} className="text-sm pl-2">
                        <span className="font-medium">{col.name.replace('self_', '')}</span>
                        <span className="text-muted-foreground ml-2">({col.count.toLocaleString()})</span>
                      </div>
                    ))}
                </div>
                {/* System Telemetry */}
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5"><BarChart3 className="h-3.5 w-3.5" /> System Telemetry</p>
                  <p className="text-xs text-muted-foreground pl-2 mb-1">Sensor readings & logs (auto-collected)</p>
                  {metrics.active_collections
                    .filter(col => ['self_hwmon', 'self_journald'].includes(col.name))
                    .map((col) => (
                      <div key={col.id} className="text-sm pl-2">
                        <span className="font-medium">{col.name.replace('self_', '')}</span>
                        <span className="text-muted-foreground ml-2">({col.count.toLocaleString()})</span>
                      </div>
                    ))}
                </div>
                {/* Internal Index */}
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5"><Link className="h-3.5 w-3.5" /> Internal Index</p>
                  <p className="text-xs text-muted-foreground pl-2 mb-1">Combined search index (contains duplicates)</p>
                  {metrics.active_collections
                    .filter(col => col.name === 'self_knowledge_all')
                    .map((col) => (
                      <div key={col.id} className="text-sm pl-2 opacity-60">
                        <span className="font-medium">{col.name}</span>
                        <span className="text-muted-foreground ml-2">({col.count.toLocaleString()})</span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Orphan Cleanup Card */}
      {hasOrphans && (
        <Card className="border-yellow-500/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
              <Trash2 className="h-5 w-5" />
              Orphaned Data Detected
            </CardTitle>
            <CardDescription>
              {metrics.orphaned_data.count} stale collection directories using {metrics.orphaned_data.total_size_human}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              These are leftover files from deleted collections. They are safe to remove and will free up disk space.
            </p>

            {/* Orphan Details Accordion */}
            <div className="border rounded-md">
              <button
                className="w-full flex items-center justify-between p-3 hover:bg-muted/50 transition-colors"
                onClick={() => setShowOrphans(!showOrphans)}
              >
                <span className="text-sm">View orphaned directories</span>
                {showOrphans ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
              {showOrphans && (
                <div className="border-t p-3 space-y-2 max-h-48 overflow-y-auto">
                  {metrics.orphaned_data.directories.map((dir) => (
                    <div key={dir.id} className="flex items-center justify-between text-xs font-mono">
                      <span className="truncate max-w-[60%]">{dir.id}</span>
                      <span className="text-muted-foreground">{dir.size_human}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Cleanup Progress */}
            {cleanupStatus?.status === 'running' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span>Cleaning up...</span>
                  <span>{cleanupStatus.completed_items} / {cleanupStatus.total_items}</span>
                </div>
                <Progress value={(cleanupStatus.completed_items / cleanupStatus.total_items) * 100} />
                <p className="text-xs text-muted-foreground">
                  Freed: {cleanupStatus.bytes_freed_human}
                </p>
              </div>
            )}

            {/* Cleanup Complete - with fade out animation */}
            {cleanupStatus?.status === 'completed' && !cleaning && cleanupFadePhase !== 'hidden' && (
              <div 
                className={`space-y-2 transition-opacity duration-[5000ms] ${
                  cleanupFadePhase === 'fading' ? 'opacity-0' : 'opacity-100'
                }`}
              >
                <div className="flex items-center justify-between text-sm">
                  <span className="text-green-600 font-medium">Complete!</span>
                  <span className="text-muted-foreground">100%</span>
                </div>
                <Progress value={100} className="[&>div]:bg-green-500" />
                <div className="flex items-center gap-2 text-sm text-green-600">
                  <CheckCircle className="h-4 w-4" />
                  Freed {cleanupStatus.bytes_freed_human}
                </div>
              </div>
            )}

            {/* Cleanup Buttons - hide during running or completion display */}
            {cleanupStatus?.status !== 'running' && (cleanupFadePhase === 'hidden' || !cleanupStatus) && (
              <div className="flex gap-2">
                <Button 
                  onClick={() => startCleanup(false)} 
                  disabled={cleaning}
                  className="flex-1"
                >
                  {cleaning ? (
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-2" />
                  )}
                  Clean Up Now
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Performance Tips */}
      {metrics.tips.length > 0 && (
        <div className="rounded-lg border bg-muted/30 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Lightbulb className="h-4 w-4 text-yellow-500" />
            <span className="font-medium text-sm">Performance Tips</span>
          </div>
          <ul className="space-y-2 text-sm text-muted-foreground">
            {metrics.tips.map((tip, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-muted-foreground/60">•</span>
                {tip}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
