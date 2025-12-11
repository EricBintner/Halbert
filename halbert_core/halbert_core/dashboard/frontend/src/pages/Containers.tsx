/**
 * Containers Page - Docker and Podman container management.
 * 
 * Phase 15: Container Management
 * Shows running containers, images, and provides quick actions.
 */

import { useEffect, useState } from 'react'
import { useScan } from '@/contexts/ScanContext'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Container,
  RefreshCw,
  Play,
  Square,
  RotateCcw,
  Trash2,
  Search,
  HardDrive,
  Download,
  Box,
  FileText,
  AlertTriangle,
  CheckCircle,
  Clock,
  Cpu,
  MemoryStick,
  Network,
  ExternalLink,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface ContainerInfo {
  id: string
  name: string
  image: string
  status: 'running' | 'stopped' | 'paused' | 'restarting' | 'exited'
  created: string
  ports: string[]
  runtime: 'docker' | 'podman'
  // Stats (if available)
  cpu_percent: number | null
  memory_mb: number | null
  memory_limit_mb: number | null
}

interface ImageInfo {
  id: string
  repository: string
  tag: string
  size_mb: number
  created: string
}

interface ContainerData {
  runtime: 'docker' | 'podman' | null
  runtime_version: string | null
  containers: ContainerInfo[]
  images: ImageInfo[]
  stats: {
    running: number
    stopped: number
    total: number
    images: number
    disk_usage_mb: number
  }
  socket_available: boolean
  error: string | null
}

const statusColors: Record<string, string> = {
  running: 'bg-green-500',
  stopped: 'bg-gray-500',
  paused: 'bg-amber-500',
  restarting: 'bg-blue-500',
  exited: 'bg-red-500',
}

const statusIcons: Record<string, React.ReactNode> = {
  running: <CheckCircle className="h-4 w-4" />,
  stopped: <Square className="h-4 w-4" />,
  paused: <Clock className="h-4 w-4" />,
  restarting: <RefreshCw className="h-4 w-4 animate-spin" />,
  exited: <AlertTriangle className="h-4 w-4" />,
}

export function Containers() {
  const { refreshTrigger } = useScan()
  
  const [data, setData] = useState<ContainerData | null>(null)
  const [loading, setLoading] = useState(true)
  const [, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedContainer, setSelectedContainer] = useState<ContainerInfo | null>(null)
  const [containerLogs, setContainerLogs] = useState<string>('')
  const [logsLoading, setLogsLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const loadContainers = async () => {
    try {
      const response = await fetch('/api/containers/info')
      if (!response.ok) throw new Error('Failed to load container info')
      const result = await response.json()
      setData(result)
      setError(null)
    } catch (err) {
      setError('Failed to load container information')
      console.error(err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadContainers()
    // Refresh every 5 seconds for live stats
    const interval = setInterval(loadContainers, 5000)
    return () => clearInterval(interval)
  }, [])

  // Also refresh when system-wide scan completes (via context)
  useEffect(() => {
    if (refreshTrigger > 0) {
      loadContainers()
    }
  }, [refreshTrigger])

  // Also listen for window events (backup mechanism)
  useEffect(() => {
    const handleScanComplete = () => loadContainers()
    window.addEventListener('halbert-scan-complete', handleScanComplete)
    return () => window.removeEventListener('halbert-scan-complete', handleScanComplete)
  }, [])

  const handleRefresh = () => {
    setRefreshing(true)
    loadContainers()
  }

  const handleContainerAction = async (containerId: string, action: 'start' | 'stop' | 'restart' | 'remove') => {
    setActionLoading(containerId)
    try {
      const response = await fetch(`/api/containers/${containerId}/${action}`, {
        method: 'POST',
      })
      if (!response.ok) throw new Error(`Failed to ${action} container`)
      loadContainers()
    } catch (err) {
      console.error(`Failed to ${action} container:`, err)
    } finally {
      setActionLoading(null)
    }
  }

  const handleViewLogs = async (container: ContainerInfo) => {
    setSelectedContainer(container)
    setLogsLoading(true)
    setContainerLogs('')
    
    try {
      const response = await fetch(`/api/containers/${container.id}/logs?tail=100`)
      if (!response.ok) throw new Error('Failed to fetch logs')
      const result = await response.json()
      setContainerLogs(result.logs || 'No logs available')
    } catch (err) {
      setContainerLogs('Failed to fetch logs')
      console.error(err)
    } finally {
      setLogsLoading(false)
    }
  }

  const filteredContainers = data?.containers.filter(c => 
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.image.toLowerCase().includes(searchQuery.toLowerCase())
  ) || []

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // No container runtime installed
  if (!data?.runtime) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Containers</h1>
            <p className="text-muted-foreground">Docker and Podman container management</p>
          </div>
        </div>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-12">
              <Container className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-medium text-lg mb-2">No Container Runtime Found</h3>
              <p className="text-muted-foreground mb-6 max-w-md mx-auto">
                Install Docker or Podman to manage containers on this system.
              </p>
              <div className="flex justify-center gap-4">
                <Button variant="outline" asChild>
                  <a href="https://docs.docker.com/engine/install/" target="_blank" rel="noopener noreferrer">
                    <Download className="h-4 w-4 mr-2" />
                    Install Docker
                    <ExternalLink className="h-3 w-3 ml-2" />
                  </a>
                </Button>
                <Button variant="outline" asChild>
                  <a href="https://podman.io/getting-started/installation" target="_blank" rel="noopener noreferrer">
                    <Download className="h-4 w-4 mr-2" />
                    Install Podman
                    <ExternalLink className="h-3 w-3 ml-2" />
                  </a>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Containers</h1>
          <p className="text-muted-foreground">
            {data.runtime} {data.runtime_version} • {data.stats.running} running
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {data.runtime === 'docker' ? '🐳' : '🦭'} {data.runtime}
          </Badge>
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4 mr-2", refreshing && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-500/10 rounded-lg">
                <Play className="h-5 w-5 text-green-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.stats.running}</p>
                <p className="text-xs text-muted-foreground">Running</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gray-500/10 rounded-lg">
                <Square className="h-5 w-5 text-gray-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.stats.stopped}</p>
                <p className="text-xs text-muted-foreground">Stopped</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/10 rounded-lg">
                <Box className="h-5 w-5 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.stats.images}</p>
                <p className="text-xs text-muted-foreground">Images</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/10 rounded-lg">
                <HardDrive className="h-5 w-5 text-purple-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{(data.stats.disk_usage_mb / 1024).toFixed(1)}</p>
                <p className="text-xs text-muted-foreground">GB Used</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Analysis */}
      <AIAnalysisPanel
        type="containers"
        title="Container"
        canAnalyze={data.containers.length > 0}
        buildContext={() => {
          const parts = [`## Container Analysis Context\n`]
          parts.push(`Runtime: ${data.runtime} ${data.runtime_version}`)
          parts.push(`Containers: ${data.stats.running} running, ${data.stats.stopped} stopped`)
          parts.push(`Images: ${data.stats.images}`)
          parts.push(`Disk Usage: ${(data.stats.disk_usage_mb / 1024).toFixed(1)} GB\n`)
          
          parts.push(`### Running Containers:`)
          data.containers.filter(c => c.status === 'running').forEach(c => {
            parts.push(`- ${c.name}: ${c.image}`)
            if (c.ports.length > 0) parts.push(`  Ports: ${c.ports.join(', ')}`)
            if (c.cpu_percent !== null) parts.push(`  CPU: ${c.cpu_percent.toFixed(1)}%`)
            if (c.memory_mb !== null) parts.push(`  Memory: ${c.memory_mb.toFixed(0)} MB`)
          })
          
          return parts.join('\n')
        }}
        researchQuestion="Analyze my container setup and identify any issues or optimizations."
      />

      {/* Tabs for Containers and Images */}
      <Tabs defaultValue="containers" className="space-y-4">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="containers">
              <Container className="h-4 w-4 mr-2" />
              Containers ({data.stats.total})
            </TabsTrigger>
            <TabsTrigger value="images">
              <Box className="h-4 w-4 mr-2" />
              Images ({data.stats.images})
            </TabsTrigger>
          </TabsList>
          
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Containers Tab */}
        <TabsContent value="containers" className="space-y-3">
          {filteredContainers.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <div className="text-center py-8">
                  <Container className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">
                    {searchQuery ? 'No containers match your search' : 'No containers found'}
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            filteredContainers.map((container) => (
              <Card key={container.id} className={cn(
                "transition-colors",
                container.status === 'running' && "border-l-4 border-l-green-500",
                container.status === 'exited' && "border-l-4 border-l-red-500",
              )}>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={cn(
                        "p-2 rounded-lg",
                        container.status === 'running' ? "bg-green-500/10" : "bg-muted",
                      )}>
                        {statusIcons[container.status]}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium">{container.name}</h3>
                          <Badge 
                            variant="outline" 
                            className={cn("text-xs", statusColors[container.status])}
                          >
                            {container.status}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">{container.image}</p>
                        {container.ports.length > 0 && (
                          <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                            <Network className="h-3 w-3" />
                            {container.ports.join(', ')}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Stats */}
                    {container.status === 'running' && (container.cpu_percent !== null || container.memory_mb !== null) && (
                      <div className="flex items-center gap-6 text-sm">
                        {container.cpu_percent !== null && (
                          <div className="flex items-center gap-2">
                            <Cpu className="h-4 w-4 text-muted-foreground" />
                            <span>{container.cpu_percent.toFixed(1)}%</span>
                          </div>
                        )}
                        {container.memory_mb !== null && (
                          <div className="flex items-center gap-2">
                            <MemoryStick className="h-4 w-4 text-muted-foreground" />
                            <span>{container.memory_mb.toFixed(0)} MB</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-1">
                      {container.status === 'running' ? (
                        <>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => handleViewLogs(container)}
                          >
                            <FileText className="h-4 w-4" />
                          </Button>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => handleContainerAction(container.id, 'restart')}
                            disabled={actionLoading === container.id}
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => handleContainerAction(container.id, 'stop')}
                            disabled={actionLoading === container.id}
                          >
                            <Square className="h-4 w-4" />
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => handleContainerAction(container.id, 'start')}
                            disabled={actionLoading === container.id}
                          >
                            <Play className="h-4 w-4" />
                          </Button>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            className="text-destructive"
                            onClick={() => handleContainerAction(container.id, 'remove')}
                            disabled={actionLoading === container.id}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>

        {/* Images Tab */}
        <TabsContent value="images" className="space-y-3">
          {data.images.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <div className="text-center py-8">
                  <Box className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">No images found</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-4">
                <div className="space-y-2">
                  {data.images.map((image) => (
                    <div 
                      key={image.id}
                      className="flex items-center justify-between py-2 border-b last:border-0"
                    >
                      <div className="flex items-center gap-3">
                        <Box className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="font-medium text-sm">
                            {image.repository}:{image.tag}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {image.id.slice(0, 12)} • {image.created}
                          </p>
                        </div>
                      </div>
                      <Badge variant="outline">{(image.size_mb / 1024).toFixed(2)} GB</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Container Logs Sheet */}
      <Sheet open={!!selectedContainer} onOpenChange={() => setSelectedContainer(null)}>
        <SheetContent className="sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Logs: {selectedContainer?.name}
            </SheetTitle>
            <SheetDescription>
              Last 100 lines from {selectedContainer?.image}
            </SheetDescription>
          </SheetHeader>
          <div className="mt-4">
            {logsLoading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <pre className="bg-muted p-4 rounded-lg text-xs font-mono overflow-auto max-h-[70vh] whitespace-pre-wrap">
                {containerLogs}
              </pre>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
