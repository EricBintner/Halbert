import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { getSystemMetrics, type SystemMetrics } from '@/lib/tauri'
import { api } from '@/lib/api'
import { 
  Cpu, 
  MemoryStick, 
  HardDrive, 
  Clock, 
  AlertCircle, 
  RefreshCw, 
  Archive,
  Server,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/components/domain'

interface Discovery {
  id: string
  type: string
  name: string
  title: string
  description: string
  severity: 'critical' | 'warning' | 'info' | 'success'
  status?: string
}

interface DiscoveryStats {
  total: number
  by_type: Record<string, number>
  by_severity: Record<string, number>
}

export function Dashboard() {
  const [systemStatus, setSystemStatus] = useState<SystemMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<DiscoveryStats | null>(null)
  const [issues, setIssues] = useState<Discovery[]>([])
  const [scanning, setScanning] = useState(false)

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const metrics = await getSystemMetrics()
        setSystemStatus(metrics)
        setLoading(false)
      } catch (error) {
        console.error('Failed to fetch system metrics:', error)
        setLoading(false)
      }
    }

    fetchMetrics()
    const interval = setInterval(fetchMetrics, 2000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      const statsData = await api.getDiscoveryStats()
      setStats(statsData)
      
      // Load critical and warning items
      const allData = await api.getDiscoveries()
      const criticalItems = (allData.discoveries || []).filter(
        (d: Discovery) => d.severity === 'critical' || d.severity === 'warning'
      )
      setIssues(criticalItems.slice(0, 5))
    } catch (error) {
      console.error('Failed to load stats:', error)
    }
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await api.scanDiscoveries()
      await loadStats()
    } catch (error) {
      console.error('Scan failed:', error)
    } finally {
      setScanning(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>
  }

  const criticalCount = stats?.by_severity?.critical || 0
  const warningCount = stats?.by_severity?.warning || 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            System overview and health status
          </p>
        </div>
        <Button variant="outline" onClick={handleScan} disabled={scanning}>
          <RefreshCw className={cn("h-4 w-4 mr-2", scanning && "animate-spin")} />
          {scanning ? 'Scanning...' : 'Scan System'}
        </Button>
      </div>

      {/* Alert Banner */}
      {(criticalCount > 0 || warningCount > 0) && (
        <Card className={cn(
          "border-l-4",
          criticalCount > 0 ? "border-l-red-500 bg-red-500/5" : "border-l-yellow-500 bg-yellow-500/5"
        )}>
          <CardContent className="p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              {criticalCount > 0 ? (
                <AlertCircle className="h-5 w-5 text-red-500" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-yellow-500" />
              )}
              <div>
                <p className="font-medium">
                  {criticalCount > 0 
                    ? `${criticalCount} critical issue${criticalCount > 1 ? 's' : ''} detected`
                    : `${warningCount} warning${warningCount > 1 ? 's' : ''} need attention`
                  }
                </p>
                <p className="text-sm text-muted-foreground">
                  Review and resolve these issues for optimal system health
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link to="/services">View Issues <ArrowRight className="h-4 w-4 ml-1" /></Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* System Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU Usage</CardTitle>
            <Cpu className={cn(
              "h-4 w-4",
              (systemStatus?.cpu_percent || 0) > 80 ? "text-red-500" : "text-muted-foreground"
            )} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{systemStatus?.cpu_percent.toFixed(1)}%</div>
            <Progress 
              value={systemStatus?.cpu_percent || 0} 
              className={cn("h-1 mt-2", (systemStatus?.cpu_percent || 0) > 80 && "[&>div]:bg-red-500")}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Memory</CardTitle>
            <MemoryStick className={cn(
              "h-4 w-4",
              (systemStatus?.memory_percent || 0) > 85 ? "text-yellow-500" : "text-muted-foreground"
            )} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{systemStatus?.memory_percent.toFixed(1)}%</div>
            <Progress 
              value={systemStatus?.memory_percent || 0} 
              className={cn("h-1 mt-2", (systemStatus?.memory_percent || 0) > 85 && "[&>div]:bg-yellow-500")}
            />
            <p className="text-xs text-muted-foreground mt-1">
              {systemStatus?.memory_available_gb.toFixed(1)} GB free
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Uptime</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatUptime(systemStatus?.uptime_seconds || 0)}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              System healthy
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Discoveries</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total || 0}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {stats?.by_type?.service || 0} services, {stats?.by_type?.backup || 0} backups
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Links Grid */}
      <div className="grid gap-4 md:grid-cols-3">
        <Link to="/services">
          <Card className="hover:bg-accent/50 transition-colors cursor-pointer h-full">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <Server className="h-8 w-8 text-blue-500 mb-2" />
                  <h3 className="font-semibold">Services</h3>
                  <p className="text-sm text-muted-foreground">
                    {stats?.by_type?.service || 0} discovered
                  </p>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to="/storage">
          <Card className="hover:bg-accent/50 transition-colors cursor-pointer h-full">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <HardDrive className="h-8 w-8 text-purple-500 mb-2" />
                  <h3 className="font-semibold">Storage</h3>
                  <p className="text-sm text-muted-foreground">
                    {stats?.by_type?.storage || 0} disks & mounts
                  </p>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link to="/backups">
          <Card className="hover:bg-accent/50 transition-colors cursor-pointer h-full">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <Archive className="h-8 w-8 text-green-500 mb-2" />
                  <h3 className="font-semibold">Backups</h3>
                  <p className="text-sm text-muted-foreground">
                    {stats?.by_type?.backup || 0} configurations
                  </p>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Issues List */}
      {issues.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              Issues Requiring Attention
            </CardTitle>
            <CardDescription>
              Critical and warning items from your system
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {issues.map((issue) => (
                <div
                  key={issue.id}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <div className="flex items-center gap-3">
                    {issue.severity === 'critical' ? (
                      <AlertCircle className="h-5 w-5 text-red-500" />
                    ) : (
                      <AlertTriangle className="h-5 w-5 text-yellow-500" />
                    )}
                    <div>
                      <p className="font-medium">{issue.name}</p>
                      <p className="text-sm text-muted-foreground">{issue.description}</p>
                    </div>
                  </div>
                  <StatusBadge status={issue.status || issue.severity} severity={issue.severity} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Storage Overview */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="h-5 w-5" />
                Storage Overview
              </CardTitle>
              <CardDescription>Mounted filesystems</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/storage">View All <ArrowRight className="h-4 w-4 ml-1" /></Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {systemStatus?.disks
              .filter((disk) => 
                // Exclude snap packages (loop mounts with squashfs)
                !disk.mount_point.startsWith('/snap/') &&
                disk.fs_type !== 'squashfs' &&
                // Exclude other virtual/system mounts
                !disk.mount_point.startsWith('/sys') &&
                !disk.mount_point.startsWith('/proc') &&
                !disk.mount_point.startsWith('/dev') &&
                !disk.mount_point.startsWith('/run') &&
                // Exclude boot partitions
                !disk.mount_point.startsWith('/boot') &&
                disk.mount_point !== '/efi' &&
                // Exclude btrfs subvolume paths (duplicates of /)
                !disk.mount_point.startsWith('/btrfs/')
              )
              .slice(0, 3)
              .map((disk) => (
              <div key={disk.mount_point} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{disk.mount_point}</span>
                  <span className={cn(
                    disk.usage_percent > 90 && "text-red-500",
                    disk.usage_percent > 80 && "text-yellow-500",
                  )}>
                    {disk.usage_percent.toFixed(0)}%
                  </span>
                </div>
                <Progress 
                  value={disk.usage_percent} 
                  className={cn(
                    "h-2",
                    disk.usage_percent > 90 && "[&>div]:bg-red-500",
                    disk.usage_percent > 80 && disk.usage_percent <= 90 && "[&>div]:bg-yellow-500",
                  )}
                />
                <p className="text-xs text-muted-foreground">
                  {disk.available_gb.toFixed(1)} GB free of {disk.total_gb.toFixed(1)} GB
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  
  if (days > 0) {
    return `${days}d ${hours}h`
  }
  return `${hours}h`
}
